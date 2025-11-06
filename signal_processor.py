"""
Signal Processor - Filter Trade Signals and Calculate Positions (Phase 3.1)

This module processes trade signals from trade_monitor.py and generates
executable position specifications after applying multiple filters:
    1. Token Mapping: DEX token → CEX trading pair
    2. Liquidity Check: Spread < 0.5%, depth > 10x position
    3. Risk Limits: Position count, concentration, capital allocation

Position sizing uses the 1/2 rule formula:
    our_position = capital × wallet_allocation × 0.5 × trader_position_%

Usage:
    >>> processor = SignalProcessor(config_path='config.json')
    >>> position = processor.process_signal(signal)
    >>> if position:
    ...     print(f"Position approved: {position.pair} {position.side} ${position.size_usd}")
"""

import sqlite3
import logging
import json
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Position:
    """
    Complete position specification ready for execution.

    See POSITION_DATACLASS_DESIGN.md for full documentation.
    """
    # Identifiers
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = ""
    wallet_address: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    # Trading parameters
    exchange: str = ""
    pair: str = ""
    side: str = ""

    # Position sizing
    size_usd: float = 0.0
    size_base: float = 0.0
    leverage: int = 1
    notional_usd: float = 0.0

    # Risk management
    stop_loss_price: float = 0.0
    stop_loss_usd: float = 0.0
    take_profit_price: Optional[float] = None

    # Allocation details
    wallet_allocation_pct: float = 0.0
    trade_multiplier: float = 0.5
    trader_position_pct: float = 0.0
    capital_at_risk_pct: float = 0.0

    # Source trade info
    source_token: str = ""
    source_token_symbol: str = ""
    source_amount_usd: float = 0.0
    source_leverage: int = 1

    # Execution details
    entry_price: float = 0.0
    slippage_tolerance: float = 0.5

    # Status tracking
    status: str = 'pending'
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    actual_entry_price: Optional[float] = None
    actual_size: Optional[float] = None
    pnl_usd: Optional[float] = None

    # Filter results
    passed_token_check: bool = False
    passed_liquidity_check: bool = False
    passed_risk_check: bool = False
    rejection_reason: Optional[str] = None

    @property
    def is_open(self) -> bool:
        """Check if position is open"""
        return self.status in ('pending', 'filled')


@dataclass
class PositionSummary:
    """Summary of current portfolio positions."""
    total_positions: int = 0
    total_notional_usd: float = 0.0
    total_capital_at_risk_usd: float = 0.0
    positions_by_pair: Dict[str, int] = field(default_factory=dict)
    positions_by_wallet: Dict[str, int] = field(default_factory=dict)
    largest_position_usd: float = 0.0
    average_leverage: float = 0.0


@dataclass
class TokenMapping:
    """Mapping from DEX token to CEX trading pair."""
    dex_address: str
    dex_symbol: str
    cex_symbol: str
    cex_pair: str
    exchange: str
    is_inverse: bool = False
    min_position_usd: float = 10.0
    max_leverage: int = 25


@dataclass
class LiquidityCheck:
    """Result of liquidity check."""
    pair: str
    bid_price: float
    ask_price: float
    spread_pct: float
    bid_depth_usd: float
    ask_depth_usd: float
    is_sufficient: bool
    checked_at: datetime


# ============================================================================
# TOKEN MAPPER
# ============================================================================

class TokenMapper:
    """
    Map DEX tokens to CEX trading pairs.

    Maintains mappings for common tokens like WETH, WBTC, etc.
    """

    # Hardcoded mappings for common tokens
    KNOWN_MAPPINGS = {
        '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': TokenMapping(
            dex_address='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
            dex_symbol='WETH',
            cex_symbol='ETH',
            cex_pair='ETHUSDT',
            exchange='binance',
            max_leverage=25
        ),
        '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': TokenMapping(
            dex_address='0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',
            dex_symbol='WBTC',
            cex_symbol='BTC',
            cex_pair='BTCUSDT',
            exchange='binance',
            max_leverage=25
        ),
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': TokenMapping(
            dex_address='0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
            dex_symbol='USDC',
            cex_symbol='USDC',
            cex_pair='BTCUSDT',  # Trade BTC with USDC as stable
            exchange='binance',
            max_leverage=25
        ),
        '0xdac17f958d2ee523a2206206994597c13d831ec7': TokenMapping(
            dex_address='0xdac17f958d2ee523a2206206994597c13d831ec7',
            dex_symbol='USDT',
            cex_symbol='USDT',
            cex_pair='BTCUSDT',  # Trade BTC with USDT as stable
            exchange='binance',
            max_leverage=25
        ),
    }

    def __init__(self, config: dict):
        self.config = config
        self.cache: Dict[str, Optional[TokenMapping]] = {}

    def map_token(self, token_address: str) -> Optional[TokenMapping]:
        """
        Map DEX token to CEX pair.

        Args:
            token_address: DEX token address

        Returns:
            TokenMapping if found, None otherwise
        """
        token_lower = token_address.lower()

        # Check cache
        if token_lower in self.cache:
            return self.cache[token_lower]

        # Check known mappings
        if token_lower in self.KNOWN_MAPPINGS:
            mapping = self.KNOWN_MAPPINGS[token_lower]
            self.cache[token_lower] = mapping
            logger.debug(f"Token mapped: {token_lower[:10]}... → {mapping.cex_pair}")
            return mapping

        # Unknown token
        logger.debug(f"Token not mapped: {token_lower[:10]}...")
        self.cache[token_lower] = None
        return None


# ============================================================================
# LIQUIDITY CHECKER
# ============================================================================

class LiquidityChecker:
    """
    Check exchange liquidity for trading pairs.

    Checks:
        1. Bid-ask spread < 0.5%
        2. Order book depth > 10x position size
    """

    def __init__(self, config: dict):
        self.config = config

        # Thresholds
        self.max_spread_pct = config.get('max_spread_pct', 0.5)
        self.min_depth_multiplier = config.get('min_depth_multiplier', 10)

        # Cache
        self.cache: Dict[str, Tuple[LiquidityCheck, datetime]] = {}
        self.cache_ttl = 30  # 30 seconds

    def check(
        self,
        pair: str,
        position_size_usd: float
    ) -> LiquidityCheck:
        """
        Check if pair has sufficient liquidity.

        Args:
            pair: Trading pair (e.g., 'ETHUSDT')
            position_size_usd: Planned position size

        Returns:
            LiquidityCheck with results
        """
        # Check cache
        cache_key = f"{pair}:{int(position_size_usd)}"
        if cache_key in self.cache:
            result, cached_at = self.cache[cache_key]
            if (datetime.now() - cached_at).seconds < self.cache_ttl:
                return result

        # Fetch orderbook (mock for Phase 3.1)
        orderbook = self._fetch_orderbook(pair)

        # Calculate spread
        bid_price = orderbook['bids'][0][0]
        ask_price = orderbook['asks'][0][0]
        spread_pct = ((ask_price - bid_price) / bid_price) * 100

        # Calculate depth (top 5 levels)
        bid_depth = sum(price * qty for price, qty in orderbook['bids'][:5])
        ask_depth = sum(price * qty for price, qty in orderbook['asks'][:5])

        # Check thresholds
        spread_ok = spread_pct < self.max_spread_pct
        depth_ok = min(bid_depth, ask_depth) > position_size_usd * self.min_depth_multiplier

        result = LiquidityCheck(
            pair=pair,
            bid_price=bid_price,
            ask_price=ask_price,
            spread_pct=spread_pct,
            bid_depth_usd=bid_depth,
            ask_depth_usd=ask_depth,
            is_sufficient=spread_ok and depth_ok,
            checked_at=datetime.now()
        )

        # Cache result
        self.cache[cache_key] = (result, datetime.now())

        logger.debug(
            f"Liquidity check {pair}: spread={spread_pct:.3f}%, "
            f"depth=${min(bid_depth, ask_depth):,.0f}, "
            f"sufficient={result.is_sufficient}"
        )

        return result

    def _fetch_orderbook(self, pair: str) -> Dict:
        """
        Fetch orderbook from exchange.

        TODO: Implement actual exchange API calls in Phase 3.2
        For now, return mock data for testing.
        """
        # Mock orderbook data
        if 'ETH' in pair:
            return {
                'bids': [(3400.0, 10.0), (3399.5, 5.0), (3399.0, 8.0), (3398.5, 12.0), (3398.0, 7.0)],
                'asks': [(3401.0, 10.0), (3401.5, 5.0), (3402.0, 8.0), (3402.5, 12.0), (3403.0, 7.0)]
            }
        elif 'BTC' in pair:
            return {
                'bids': [(45000.0, 2.0), (44999.0, 1.5), (44998.0, 2.5), (44997.0, 3.0), (44996.0, 1.8)],
                'asks': [(45001.0, 2.0), (45002.0, 1.5), (45003.0, 2.5), (45004.0, 3.0), (45005.0, 1.8)]
            }
        else:
            # Default
            return {
                'bids': [(100.0, 100.0)],
                'asks': [(101.0, 100.0)]
            }


# ============================================================================
# POSITION MANAGER
# ============================================================================

class PositionManager:
    """
    Track open positions and portfolio state.

    Responsibilities:
        - Store positions in database
        - Query current positions
        - Calculate portfolio metrics
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create positions table if not exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                signal_id TEXT,
                wallet_address TEXT,
                created_at TIMESTAMP,

                exchange TEXT,
                pair TEXT,
                side TEXT,

                size_usd REAL,
                size_base REAL,
                leverage INTEGER,
                notional_usd REAL,

                stop_loss_price REAL,
                stop_loss_usd REAL,
                take_profit_price REAL,

                wallet_allocation_pct REAL,
                trade_multiplier REAL,
                trader_position_pct REAL,
                capital_at_risk_pct REAL,

                source_token TEXT,
                source_token_symbol TEXT,
                source_amount_usd REAL,
                source_leverage INTEGER,

                entry_price REAL,
                slippage_tolerance REAL,

                status TEXT,
                filled_at TIMESTAMP,
                closed_at TIMESTAMP,
                actual_entry_price REAL,
                actual_size REAL,
                pnl_usd REAL,

                passed_token_check BOOLEAN,
                passed_liquidity_check BOOLEAN,
                passed_risk_check BOOLEAN,
                rejection_reason TEXT
            )
        """)

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_status
            ON positions(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_pair
            ON positions(pair, status)
        """)

        conn.commit()
        conn.close()

    def save(self, position: Position) -> None:
        """Save position to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO positions (
                    id, signal_id, wallet_address, created_at,
                    exchange, pair, side,
                    size_usd, size_base, leverage, notional_usd,
                    stop_loss_price, stop_loss_usd, take_profit_price,
                    wallet_allocation_pct, trade_multiplier, trader_position_pct, capital_at_risk_pct,
                    source_token, source_token_symbol, source_amount_usd, source_leverage,
                    entry_price, slippage_tolerance,
                    status, passed_token_check, passed_liquidity_check, passed_risk_check, rejection_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.id, position.signal_id, position.wallet_address, position.created_at.isoformat(),
                position.exchange, position.pair, position.side,
                position.size_usd, position.size_base, position.leverage, position.notional_usd,
                position.stop_loss_price, position.stop_loss_usd, position.take_profit_price,
                position.wallet_allocation_pct, position.trade_multiplier, position.trader_position_pct, position.capital_at_risk_pct,
                position.source_token, position.source_token_symbol, position.source_amount_usd, position.source_leverage,
                position.entry_price, position.slippage_tolerance,
                position.status, position.passed_token_check, position.passed_liquidity_check, position.passed_risk_check, position.rejection_reason
            ))

            conn.commit()
            logger.info(f"Position saved: {position.id[:8]}... ({position.pair} {position.side})")

        except sqlite3.Error as e:
            logger.error(f"Failed to save position: {e}")
            raise

        finally:
            conn.close()

    def get_summary(self) -> PositionSummary:
        """Get current portfolio summary."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get open positions
        cursor.execute("""
            SELECT pair, notional_usd, stop_loss_usd, leverage, wallet_address
            FROM positions
            WHERE status IN ('pending', 'filled')
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return PositionSummary()

        # Calculate metrics
        positions_by_pair: Dict[str, int] = {}
        positions_by_wallet: Dict[str, int] = {}
        total_notional = 0.0
        total_risk = 0.0
        leverages = []
        max_notional = 0.0

        for pair, notional, risk, leverage, wallet in rows:
            positions_by_pair[pair] = positions_by_pair.get(pair, 0) + 1
            positions_by_wallet[wallet] = positions_by_wallet.get(wallet, 0) + 1
            total_notional += notional
            total_risk += risk
            leverages.append(leverage)
            max_notional = max(max_notional, notional)

        return PositionSummary(
            total_positions=len(rows),
            total_notional_usd=total_notional,
            total_capital_at_risk_usd=total_risk,
            positions_by_pair=positions_by_pair,
            positions_by_wallet=positions_by_wallet,
            largest_position_usd=max_notional,
            average_leverage=sum(leverages) / len(leverages) if leverages else 0
        )


# ============================================================================
# RISK MANAGER
# ============================================================================

class RiskManager:
    """
    Enforce risk limits on positions.

    Limits:
        1. Total open positions < 20
        2. Same pair positions < 3
        3. Position size < 5% of capital
        4. Total capital at risk < 50%
    """

    def __init__(self, config: dict, position_manager: PositionManager):
        self.config = config
        self.position_manager = position_manager

        # Risk limits
        self.max_total_positions = config.get('max_total_positions', 20)
        self.max_same_pair_positions = config.get('max_same_pair_positions', 3)
        self.max_position_pct = config.get('max_position_pct', 5.0)
        self.max_total_risk_pct = config.get('max_total_risk_pct', 50.0)

        # Capital
        self.total_capital_usd = config.get('total_capital_usd', 100000)

    def check(self, position: Position) -> bool:
        """
        Check if position passes all risk limits.

        Returns:
            bool: True if position passes all checks
        """
        # Get current portfolio state
        summary = self.position_manager.get_summary()

        # Check 1: Total positions
        if summary.total_positions >= self.max_total_positions:
            position.rejection_reason = f"Max positions exceeded ({summary.total_positions} >= {self.max_total_positions})"
            logger.warning(f"Risk check failed: {position.rejection_reason}")
            return False

        # Check 2: Same pair concentration
        pair_count = summary.positions_by_pair.get(position.pair, 0)
        if pair_count >= self.max_same_pair_positions:
            position.rejection_reason = f"Max same pair positions exceeded ({pair_count} >= {self.max_same_pair_positions})"
            logger.warning(f"Risk check failed: {position.rejection_reason}")
            return False

        # Check 3: Position size
        position_pct = (position.size_usd / self.total_capital_usd) * 100
        if position_pct > self.max_position_pct:
            position.rejection_reason = f"Position size too large ({position_pct:.2f}% > {self.max_position_pct}%)"
            logger.warning(f"Risk check failed: {position.rejection_reason}")
            return False

        # Check 4: Total capital at risk
        new_total_risk = summary.total_capital_at_risk_usd + position.stop_loss_usd
        total_risk_pct = (new_total_risk / self.total_capital_usd) * 100
        if total_risk_pct > self.max_total_risk_pct:
            position.rejection_reason = f"Total risk too high ({total_risk_pct:.2f}% > {self.max_total_risk_pct}%)"
            logger.warning(f"Risk check failed: {position.rejection_reason}")
            return False

        logger.debug(
            f"Risk check passed: positions={summary.total_positions}/{self.max_total_positions}, "
            f"pair_count={pair_count}/{self.max_same_pair_positions}, "
            f"pos_pct={position_pct:.2f}%/{self.max_position_pct}%, "
            f"risk={total_risk_pct:.2f}%/{self.max_total_risk_pct}%"
        )

        return True


# ============================================================================
# SIGNAL PROCESSOR (MAIN ORCHESTRATOR)
# ============================================================================

class SignalProcessor:
    """
    Process trade signals and generate executable positions.

    Filtering Pipeline:
        1. Token Mapping: DEX token → CEX pair
        2. Liquidity Check: Spread < 0.5%, depth > 10x position
        3. Position Sizing: Calculate size using 1/2 rule formula
        4. Risk Limits: Position count, concentration, capital

    Usage:
        >>> processor = SignalProcessor(config_path='config.json')
        >>> position = processor.process_signal(signal)
        >>> if position:
        ...     print(f"Approved: {position.pair} {position.side} ${position.size_usd}")
    """

    def __init__(
        self,
        config_path: str = 'config.json',
        db_path: str = 'wallet_trading.db'
    ):
        # Load configuration
        with open(config_path) as f:
            self.config = json.load(f)

        self.db_path = db_path

        # Initialize components
        self.token_mapper = TokenMapper(self.config)
        self.liquidity_checker = LiquidityChecker(self.config)
        self.position_manager = PositionManager(db_path)
        self.risk_manager = RiskManager(self.config, self.position_manager)

        # Configuration
        self.total_capital_usd = self.config.get('total_capital_usd', 100000)
        self.trade_multiplier = self.config.get('trade_multiplier', 0.5)
        self.max_leverage = self.config.get('max_leverage', 25)

        # Statistics
        self.signals_processed = 0
        self.signals_accepted = 0
        self.signals_rejected = 0
        self.rejection_reasons: Dict[str, int] = {}

        logger.info("=" * 70)
        logger.info("SIGNAL PROCESSOR INITIALIZED")
        logger.info("=" * 70)
        logger.info(f"Total capital: ${self.total_capital_usd:,}")
        logger.info(f"Trade multiplier: {self.trade_multiplier}")
        logger.info(f"Max leverage: {self.max_leverage}x")

    def process_signal(self, signal) -> Optional[Position]:
        """
        Main entry point: process a trade signal.

        Args:
            signal: TradeSignal from trade_monitor

        Returns:
            Position if signal passes all filters, None otherwise
        """
        self.signals_processed += 1

        logger.info(f"\n{'='*70}")
        logger.info(f"Processing signal {self.signals_processed}: {signal.token_symbol} {signal.action}")
        logger.info(f"{'='*70}")

        # Step 1: Token Mapping
        logger.info("Step 1: Token Mapping Check...")
        token_mapping = self.token_mapper.map_token(signal.token_address)
        if not token_mapping:
            self._reject_signal(signal, 'token_not_mapped')
            return None

        logger.info(f"✓ Token mapped: {signal.token_symbol} → {token_mapping.cex_pair}")

        # Step 2: Position Sizing (calculate before liquidity check to know size)
        logger.info("Step 2: Position Sizing Calculation...")
        position = self._calculate_position(signal, token_mapping)

        # Step 3: Liquidity Check
        logger.info("Step 3: Liquidity Check...")
        liquidity = self.liquidity_checker.check(token_mapping.cex_pair, position.size_usd)
        if not liquidity.is_sufficient:
            self._reject_signal(signal, 'insufficient_liquidity')
            return None

        logger.info(f"✓ Liquidity check passed: spread={liquidity.spread_pct:.3f}%")

        # Update position with liquidity data
        position.entry_price = liquidity.ask_price if signal.action == 'BUY' else liquidity.bid_price

        # Step 4: Risk Checks
        logger.info("Step 4: Risk Limits Check...")
        if not self.risk_manager.check(position):
            self._reject_signal(signal, 'risk_limits_exceeded')
            return None

        logger.info(f"✓ Risk check passed")

        # All checks passed
        position.passed_token_check = True
        position.passed_liquidity_check = True
        position.passed_risk_check = True

        # Save position
        self.position_manager.save(position)

        self.signals_accepted += 1

        logger.info("")
        logger.info("="*70)
        logger.info(f"✅ SIGNAL APPROVED")
        logger.info("="*70)
        logger.info(f"Position: {position.pair} {position.side}")
        logger.info(f"Size: ${position.size_usd:.2f} ({position.leverage}x leverage)")
        logger.info(f"Notional: ${position.notional_usd:.2f}")
        logger.info(f"Stop Loss: ${position.stop_loss_price:.2f} (max loss: ${position.stop_loss_usd:.2f})")
        logger.info(f"Capital at Risk: {position.capital_at_risk_pct:.2f}%")
        logger.info("="*70)

        return position

    def _calculate_position(
        self,
        signal,
        token_mapping: TokenMapping
    ) -> Position:
        """
        Calculate position size using the 1/2 rule formula.

        Formula:
            wallet_allocation = based on wallet rank (10% for top, 8% for 2nd, etc.)
            trader_position_pct = signal.amount_usd / estimated_balance
            our_position_usd = total_capital × wallet_allocation × trade_multiplier × trader_position_pct
            leverage = min(signal.leverage, max_leverage)
            stop_loss_usd = total_capital × (trade_multiplier × wallet_allocation)

        Args:
            signal: TradeSignal from trade_monitor
            token_mapping: Mapped CEX pair

        Returns:
            Position ready for execution
        """
        # Step 1: Get wallet allocation based on rank
        wallet_allocation_pct = self._get_wallet_allocation(signal.wallet_address)

        # Step 2: Estimate trader's position size as % of their capital
        estimated_trader_balance = self._estimate_trader_balance(signal.wallet_address)
        trader_position_pct = signal.amount_usd / estimated_trader_balance

        # Cap at reasonable levels (trader wouldn't use >50% of capital)
        trader_position_pct = min(trader_position_pct, 0.50)

        # Step 3: Calculate our position size (with 1/2 rule)
        size_usd = (
            self.total_capital_usd
            * (wallet_allocation_pct / 100.0)
            * self.trade_multiplier
            * trader_position_pct
        )

        # Apply minimum and maximum position sizes
        size_usd = max(size_usd, token_mapping.min_position_usd)
        size_usd = min(size_usd, self.total_capital_usd * 0.05)  # Cap at 5% of capital

        # Step 4: Calculate leverage (capped)
        leverage = min(signal.leverage, self.max_leverage, token_mapping.max_leverage)
        notional_usd = size_usd * leverage

        # Step 5: Calculate stop loss
        stop_loss_usd = (
            self.total_capital_usd
            * self.trade_multiplier
            * (wallet_allocation_pct / 100.0)
        )

        # Placeholder entry price (will be updated with liquidity check)
        entry_price = 0.0

        # Step 6: Create Position object
        position = Position(
            signal_id=signal.id,
            wallet_address=signal.wallet_address,
            created_at=datetime.now(),

            # Trading parameters
            exchange=token_mapping.exchange,
            pair=token_mapping.cex_pair,
            side=signal.action,

            # Position sizing
            size_usd=size_usd,
            size_base=0.0,  # Will be calculated after entry price known
            leverage=leverage,
            notional_usd=notional_usd,

            # Risk management
            stop_loss_price=0.0,  # Will be calculated after entry price known
            stop_loss_usd=stop_loss_usd,
            take_profit_price=None,

            # Allocation details
            wallet_allocation_pct=wallet_allocation_pct,
            trade_multiplier=self.trade_multiplier,
            trader_position_pct=trader_position_pct,
            capital_at_risk_pct=(stop_loss_usd / self.total_capital_usd) * 100,

            # Source trade info
            source_token=signal.token_address,
            source_token_symbol=signal.token_symbol,
            source_amount_usd=signal.amount_usd,
            source_leverage=signal.leverage,

            # Execution details
            entry_price=entry_price,
            slippage_tolerance=0.5,

            # Status
            status='pending'
        )

        logger.info(f"  Wallet allocation: {wallet_allocation_pct}%")
        logger.info(f"  Trader position: {trader_position_pct*100:.2f}% of balance")
        logger.info(f"  Our position: ${size_usd:.2f} ({leverage}x)")
        logger.info(f"  Notional: ${notional_usd:.2f}")
        logger.info(f"  Stop loss: ${stop_loss_usd:.2f}")

        return position

    def _get_wallet_allocation(self, wallet_address: str) -> float:
        """
        Get portfolio allocation for wallet based on rank.

        Allocation schedule:
            Rank 1: 10%
            Rank 2: 8%
            Rank 3: 6%
            Rank 4-5: 5%
            Rank 6-10: 3%
            Rank 11-20: 2%
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT rank FROM wallets
            WHERE address = ? AND is_active = 1
        """, (wallet_address.lower(),))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return 0.0

        rank = row[0]

        # Allocation schedule
        if rank == 1:
            return 10.0
        elif rank == 2:
            return 8.0
        elif rank == 3:
            return 6.0
        elif rank <= 5:
            return 5.0
        elif rank <= 10:
            return 3.0
        elif rank <= 20:
            return 2.0
        else:
            return 0.0

    def _estimate_trader_balance(self, wallet_address: str) -> float:
        """
        Estimate trader's total balance based on historical activity.

        Strategy:
            1. Query historical trades from database
            2. Find largest single trade
            3. Assume largest trade = ~20% of capital
            4. Estimate: balance = largest_trade / 0.20

        Fallback: Use rank-based estimates
            Rank 1-3: $5M
            Rank 4-10: $2M
            Rank 11-20: $1M
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get largest trade
        cursor.execute("""
            SELECT MAX(amount_usd)
            FROM wallet_transactions
            WHERE wallet_id = (SELECT id FROM wallets WHERE address = ?)
        """, (wallet_address.lower(),))

        row = cursor.fetchone()

        if row and row[0]:
            largest_trade = row[0]
            estimated_balance = largest_trade / 0.20
            conn.close()
            return estimated_balance

        # Fallback: rank-based estimate
        cursor.execute("""
            SELECT rank FROM wallets WHERE address = ?
        """, (wallet_address.lower(),))

        row = cursor.fetchone()
        conn.close()

        if row:
            rank = row[0]
            if rank <= 3:
                return 5_000_000
            elif rank <= 10:
                return 2_000_000
            else:
                return 1_000_000

        return 1_000_000  # Default

    def _reject_signal(self, signal, reason: str) -> None:
        """Record rejected signal with reason."""
        self.signals_rejected += 1
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1

        logger.warning(f"❌ Signal rejected: {reason}")

        # Save rejected signal to database
        position = Position(
            signal_id=signal.id,
            wallet_address=signal.wallet_address,
            source_token=signal.token_address,
            source_token_symbol=signal.token_symbol,
            source_amount_usd=signal.amount_usd,
            source_leverage=signal.leverage,
            status='rejected',
            rejection_reason=reason
        )

        self.position_manager.save(position)

    def get_statistics(self) -> Dict[str, Any]:
        """Get processor statistics."""
        return {
            'signals_processed': self.signals_processed,
            'signals_accepted': self.signals_accepted,
            'signals_rejected': self.signals_rejected,
            'acceptance_rate': (self.signals_accepted / self.signals_processed * 100) if self.signals_processed > 0 else 0,
            'rejection_reasons': self.rejection_reasons,
            'portfolio_summary': self.position_manager.get_summary()
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    with open(config_path) as f:
        return json.load(f)
