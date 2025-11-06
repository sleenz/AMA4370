# Signal Processor Implementation Plan

Comprehensive plan for filtering trade signals and calculating positions (Phase 3.1)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SIGNAL PROCESSING FLOW                         │
└─────────────────────────────────────────────────────────────────────────┘

TradeSignal (from trade_monitor.py)
    │
    ├─ Contains: wallet_address, token, action, amount_usd, leverage
    │
    ▼
SignalProcessor.process_signal()
    │
    ├─ Step 1: Token Mapping Filter
    │   ├─ Check: Is token tradeable on CEX (Binance/Bybit)?
    │   ├─ Map: WETH → ETH/USDT, WBTC → BTC/USDT, etc.
    │   └─ Result: Skip if no mapping found
    │
    ├─ Step 2: Liquidity Filter
    │   ├─ Query: Exchange orderbook depth
    │   ├─ Check: Bid-ask spread < 0.5%?
    │   ├─ Check: Depth > 10x position size?
    │   └─ Result: Skip if insufficient liquidity
    │
    ├─ Step 3: Risk Limits Filter
    │   ├─ Check: Total open positions < 20?
    │   ├─ Check: Same pair positions < 3?
    │   ├─ Check: Position size < 5% of capital?
    │   └─ Result: Skip if risk limits exceeded
    │
    ├─ Step 4: Position Sizing Calculator
    │   ├─ Calculate: Wallet allocation percentage
    │   ├─ Calculate: Trader position size estimate
    │   ├─ Calculate: Our position with 1/2 rule
    │   ├─ Calculate: Leverage (capped at 25x)
    │   └─ Calculate: Stop loss amount
    │
    ▼
Position (ready for execution)
    │
    ├─ Contains: pair, side, size, leverage, stop_loss, etc.
    │
    ▼
position_executor.py (Phase 3.2)
    │
    └─ Executes trade on exchange
```

---

## Data Structures

### 1. Position Dataclass (Complete Specification)

```python
@dataclass
class Position:
    """
    Complete position specification ready for execution.

    This is the output of signal processing and input to execution.
    """
    # Identifiers
    id: str  # UUID for position tracking
    signal_id: str  # Reference to original TradeSignal
    wallet_address: str  # Source wallet being copied
    created_at: datetime

    # Trading Parameters
    exchange: str  # 'binance' or 'bybit'
    pair: str  # 'ETHUSDT', 'BTCUSDT', etc.
    side: str  # 'BUY' or 'SELL'

    # Position Sizing
    size_usd: float  # Position size in USD (before leverage)
    size_base: float  # Position size in base currency (BTC, ETH, etc.)
    leverage: int  # 1-25x
    notional_usd: float  # size_usd × leverage

    # Risk Management
    stop_loss_price: float  # Stop loss price level
    stop_loss_usd: float  # Maximum loss in USD
    take_profit_price: Optional[float] = None  # Optional take profit

    # Allocation Details
    wallet_allocation_pct: float  # Wallet's portfolio allocation (10%, 8%, etc.)
    trade_multiplier: float  # Our 1/2 rule (default: 0.5)
    trader_position_pct: float  # Estimated % of trader's capital
    capital_at_risk_pct: float  # % of our total capital at risk

    # Source Trade Info
    source_token: str  # Original DEX token address
    source_token_symbol: str  # Original token symbol (WETH, WBTC, etc.)
    source_amount_usd: float  # Trader's original trade size
    source_leverage: int  # Trader's detected leverage

    # Execution Details
    entry_price: float  # Expected entry price
    slippage_tolerance: float  # Max acceptable slippage (%)

    # Status Tracking
    status: str = 'pending'  # 'pending', 'filled', 'rejected', 'closed'
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    actual_entry_price: Optional[float] = None
    actual_size: Optional[float] = None
    pnl_usd: Optional[float] = None

    # Risk Checks
    passed_token_check: bool = False
    passed_liquidity_check: bool = False
    passed_risk_check: bool = False
    rejection_reason: Optional[str] = None


@dataclass
class PositionSummary:
    """Summary of current portfolio positions."""
    total_positions: int
    total_notional_usd: float
    total_capital_at_risk_usd: float
    positions_by_pair: Dict[str, int]  # pair → count
    positions_by_wallet: Dict[str, int]  # wallet → count
    largest_position_usd: float
    average_leverage: float
```

### 2. TokenMapping Dataclass

```python
@dataclass
class TokenMapping:
    """Mapping from DEX token to CEX trading pair."""
    dex_address: str  # e.g., '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
    dex_symbol: str  # e.g., 'WETH'
    cex_symbol: str  # e.g., 'ETH'
    cex_pair: str  # e.g., 'ETHUSDT'
    exchange: str  # 'binance' or 'bybit'
    is_inverse: bool = False  # True for inverse contracts
    min_position_usd: float = 10.0  # Minimum position size
    max_leverage: int = 25  # Exchange max leverage for this pair


@dataclass
class LiquidityCheck:
    """Result of liquidity check."""
    pair: str
    bid_price: float
    ask_price: float
    spread_pct: float
    bid_depth_usd: float  # Depth at 5 levels
    ask_depth_usd: float
    is_sufficient: bool
    checked_at: datetime
```

---

## Implementation Plan

### Phase 3.1.A: Core Infrastructure

#### 1. SignalProcessor Class (Main Orchestrator)

```python
class SignalProcessor:
    """
    Process trade signals and generate executable positions.

    Responsibilities:
        - Filter signals through all checks
        - Calculate position sizes
        - Generate Position objects
        - Track rejected signals with reasons
    """

    def __init__(
        self,
        config_path: str = 'config.json',
        db_path: str = 'wallet_trading.db'
    ):
        # Load configuration
        self.config = load_config(config_path)
        self.db_path = db_path

        # Initialize components
        self.token_mapper = TokenMapper(config)
        self.liquidity_checker = LiquidityChecker(config)
        self.position_manager = PositionManager(db_path)
        self.risk_manager = RiskManager(config, self.position_manager)

        # Configuration
        self.total_capital_usd = config.get('total_capital_usd', 100000)
        self.trade_multiplier = config.get('trade_multiplier', 0.5)
        self.max_leverage = config.get('max_leverage', 25)

        # Statistics
        self.signals_processed = 0
        self.signals_accepted = 0
        self.signals_rejected = 0
        self.rejection_reasons: Dict[str, int] = {}

    def process_signal(self, signal: TradeSignal) -> Optional[Position]:
        """
        Main entry point: process a trade signal.

        Args:
            signal: TradeSignal from trade_monitor

        Returns:
            Position if signal passes all filters, None otherwise
        """
        self.signals_processed += 1

        # Step 1: Token Mapping
        token_mapping = self.token_mapper.map_token(signal.token_address)
        if not token_mapping:
            self._reject_signal(signal, 'token_not_mapped')
            return None

        # Step 2: Liquidity Check
        liquidity = self.liquidity_checker.check(token_mapping.cex_pair, signal.amount_out_usd)
        if not liquidity.is_sufficient:
            self._reject_signal(signal, 'insufficient_liquidity')
            return None

        # Step 3: Position Sizing
        position = self._calculate_position(signal, token_mapping, liquidity)

        # Step 4: Risk Checks
        if not self.risk_manager.check(position):
            self._reject_signal(signal, 'risk_limits_exceeded')
            return None

        # All checks passed
        position.passed_token_check = True
        position.passed_liquidity_check = True
        position.passed_risk_check = True

        self.signals_accepted += 1
        return position

    def _calculate_position(
        self,
        signal: TradeSignal,
        token_mapping: TokenMapping,
        liquidity: LiquidityCheck
    ) -> Position:
        """Calculate position size and risk parameters."""
        # Implementation in detail below
        ...

    def _reject_signal(self, signal: TradeSignal, reason: str) -> None:
        """Record rejected signal with reason."""
        self.signals_rejected += 1
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1

        # Log to database
        self._save_rejected_signal(signal, reason)
```

---

### Phase 3.1.B: Token Mapping

#### 2. TokenMapper Class

```python
class TokenMapper:
    """
    Map DEX tokens to CEX trading pairs.

    Strategy:
        1. Check hardcoded mappings (WETH, WBTC, etc.)
        2. Query token name/symbol from blockchain
        3. Search CEX for matching pairs
        4. Cache results
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
        # Add more common tokens...
    }

    def __init__(self, config):
        self.config = config
        self.cache: Dict[str, Optional[TokenMapping]] = {}

        # Initialize exchange clients for pair discovery
        self.binance_client = None  # Initialize in Phase 3.2
        self.bybit_client = None

    def map_token(self, token_address: str) -> Optional[TokenMapping]:
        """
        Map DEX token to CEX pair.

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
            return mapping

        # Try to discover mapping (Phase 3.2)
        # For now, return None for unknown tokens
        self.cache[token_lower] = None
        return None
```

---

### Phase 3.1.C: Liquidity Checks

#### 3. LiquidityChecker Class

```python
class LiquidityChecker:
    """
    Check exchange liquidity for trading pairs.

    Checks:
        1. Bid-ask spread < 0.5%
        2. Order book depth > 10x position size
    """

    def __init__(self, config):
        self.config = config

        # Thresholds
        self.max_spread_pct = config.get('max_spread_pct', 0.5)
        self.min_depth_multiplier = config.get('min_depth_multiplier', 10)

        # Exchange clients (Phase 3.2)
        self.binance_client = None
        self.bybit_client = None

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
        cache_key = f"{pair}:{position_size_usd}"
        if cache_key in self.cache:
            result, cached_at = self.cache[cache_key]
            if (datetime.now() - cached_at).seconds < self.cache_ttl:
                return result

        # Fetch orderbook
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

        return result

    def _fetch_orderbook(self, pair: str) -> Dict:
        """Fetch orderbook from exchange (mock for Phase 3.1)."""
        # TODO: Implement in Phase 3.2
        # For now, return mock data for testing
        return {
            'bids': [(3400.0, 10.0), (3399.5, 5.0)],  # (price, quantity)
            'asks': [(3401.0, 10.0), (3401.5, 5.0)]
        }
```

---

### Phase 3.1.D: Risk Management

#### 4. RiskManager Class

```python
class RiskManager:
    """
    Enforce risk limits on positions.

    Limits:
        1. Total open positions < 20
        2. Same pair positions < 3
        3. Position size < 5% of capital
        4. Total capital at risk < 50%
    """

    def __init__(self, config, position_manager: 'PositionManager'):
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
            return False

        # Check 2: Same pair concentration
        pair_count = summary.positions_by_pair.get(position.pair, 0)
        if pair_count >= self.max_same_pair_positions:
            position.rejection_reason = f"Max same pair positions exceeded ({pair_count} >= {self.max_same_pair_positions})"
            return False

        # Check 3: Position size
        position_pct = (position.size_usd / self.total_capital_usd) * 100
        if position_pct > self.max_position_pct:
            position.rejection_reason = f"Position size too large ({position_pct:.2f}% > {self.max_position_pct}%)"
            return False

        # Check 4: Total capital at risk
        new_total_risk = summary.total_capital_at_risk_usd + position.stop_loss_usd
        total_risk_pct = (new_total_risk / self.total_capital_usd) * 100
        if total_risk_pct > self.max_total_risk_pct:
            position.rejection_reason = f"Total risk too high ({total_risk_pct:.2f}% > {self.max_total_risk_pct}%)"
            return False

        return True
```

---

### Phase 3.1.E: Position Sizing Formula

#### 5. Position Sizing Calculator

```python
def _calculate_position(
    self,
    signal: TradeSignal,
    token_mapping: TokenMapping,
    liquidity: LiquidityCheck
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
        liquidity: Liquidity check results

    Returns:
        Position ready for execution
    """
    # Step 1: Get wallet allocation based on rank
    wallet_allocation_pct = self._get_wallet_allocation(signal.wallet_address)

    # Step 2: Estimate trader's position size as % of their capital
    # Assumption: Top wallets have ~$1M-$10M in capital
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
    # Stop loss = maximum we're willing to lose = trade_multiplier × wallet_allocation × capital
    stop_loss_usd = (
        self.total_capital_usd
        * self.trade_multiplier
        * (wallet_allocation_pct / 100.0)
    )

    # Calculate stop loss price (assuming liquidation at -100% of position)
    entry_price = liquidity.bid_price if signal.action == 'BUY' else liquidity.ask_price

    if signal.action == 'BUY':
        # For longs: stop loss below entry
        stop_loss_pct = (stop_loss_usd / size_usd) * 100
        stop_loss_price = entry_price * (1 - stop_loss_pct / 100)
    else:
        # For shorts: stop loss above entry
        stop_loss_pct = (stop_loss_usd / size_usd) * 100
        stop_loss_price = entry_price * (1 + stop_loss_pct / 100)

    # Step 6: Calculate position size in base currency
    size_base = size_usd / entry_price

    # Step 7: Create Position object
    position = Position(
        id=str(uuid.uuid4()),
        signal_id=signal.id,
        wallet_address=signal.wallet_address,
        created_at=datetime.now(),

        # Trading parameters
        exchange=token_mapping.exchange,
        pair=token_mapping.cex_pair,
        side=signal.action,  # 'BUY' or 'SELL'

        # Position sizing
        size_usd=size_usd,
        size_base=size_base,
        leverage=leverage,
        notional_usd=notional_usd,

        # Risk management
        stop_loss_price=stop_loss_price,
        stop_loss_usd=stop_loss_usd,
        take_profit_price=None,  # TODO: Implement TP logic

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
        slippage_tolerance=0.5,  # 0.5% max slippage

        # Status
        status='pending'
    )

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
    # Query wallet rank from database
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
        estimated_balance = largest_trade / 0.20  # Assume largest trade = 20% of capital
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
```

---

### Phase 3.1.F: Position Manager

#### 6. PositionManager Class

```python
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
                rejection_reason TEXT,

                FOREIGN KEY (wallet_address) REFERENCES wallets(address)
            )
        """)

        # Index for fast queries
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
            return PositionSummary(
                total_positions=0,
                total_notional_usd=0,
                total_capital_at_risk_usd=0,
                positions_by_pair={},
                positions_by_wallet={},
                largest_position_usd=0,
                average_leverage=0
            )

        # Calculate metrics
        positions_by_pair: Dict[str, int] = {}
        positions_by_wallet: Dict[str, int] = {}
        total_notional = 0
        total_risk = 0
        leverages = []
        max_notional = 0

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
```

---

## Testing Strategy

### Phase 3.1.G: Test Fixtures

```python
# test_signal_processor.py

# Sample signals for testing
SAMPLE_SIGNALS = [
    {
        'id': 'signal_1',
        'wallet_address': '0x123...',  # Rank 1 wallet
        'token_address': '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
        'token_symbol': 'WETH',
        'action': 'BUY',
        'amount_usd': 50000,  # Trader bought $50k of WETH
        'leverage': 5,
        'description': 'Top wallet buys ETH with 5x leverage'
    },
    {
        'id': 'signal_2',
        'wallet_address': '0x456...',  # Rank 5 wallet
        'token_address': '0x...',  # Random shitcoin
        'token_symbol': 'SHITCOIN',
        'action': 'BUY',
        'amount_usd': 10000,
        'leverage': 1,
        'description': 'Should be rejected: token not on CEX'
    },
    # Add more test cases...
]
```

### Expected Results

| Signal | Token Check | Liquidity Check | Risk Check | Expected Outcome |
|--------|-------------|-----------------|------------|------------------|
| 1 | ✅ WETH → ETHUSDT | ✅ High liquidity | ✅ Within limits | **Accepted** |
| 2 | ❌ No mapping | N/A | N/A | **Rejected: token_not_mapped** |
| 3 | ✅ Mapped | ❌ Spread >0.5% | N/A | **Rejected: insufficient_liquidity** |
| 4 | ✅ Mapped | ✅ Pass | ❌ 21st position | **Rejected: risk_limits_exceeded** |

---

## Configuration

### config.json additions

```json
{
  "total_capital_usd": 100000,
  "trade_multiplier": 0.5,
  "max_leverage": 25,

  "risk_limits": {
    "max_total_positions": 20,
    "max_same_pair_positions": 3,
    "max_position_pct": 5.0,
    "max_total_risk_pct": 50.0
  },

  "liquidity_thresholds": {
    "max_spread_pct": 0.5,
    "min_depth_multiplier": 10
  },

  "exchanges": {
    "binance": {
      "api_key": "YOUR_KEY",
      "api_secret": "YOUR_SECRET"
    },
    "bybit": {
      "api_key": "YOUR_KEY",
      "api_secret": "YOUR_SECRET"
    }
  }
}
```

---

## Next Steps

1. ✅ Review Position dataclass design
2. ⏳ Implement SignalProcessor class
3. ⏳ Implement TokenMapper
4. ⏳ Implement LiquidityChecker (mock for Phase 3.1)
5. ⏳ Implement RiskManager
6. ⏳ Implement PositionManager
7. ⏳ Create test_signal_processor.py
8. ⏳ Integration test with sample signals
9. ⏳ Connect to trade_monitor.py
10. ⏳ Phase 3.2: Implement actual exchange integration
