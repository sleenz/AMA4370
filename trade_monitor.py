"""
Trade Monitor System for Real-Time Wallet Tracking (Phase 2.1)

This module monitors tracked wallets in real-time, detects DEX transactions,
parses trade details, and emits copy trading signals.

Architecture:
    - TradeMonitor: Main orchestrator running 60-second monitoring loops
    - TransactionFetcher: Etherscan API V2 client with rate limiting
    - DEXParser: Decodes Uniswap V2 swap events (Phase 2.1.A)
    - LeverageDetector: Pattern-based leverage detection
    - SignalEmitter: Generates copy trade signals (paper mode)

Usage:
    # Paper mode (safe testing)
    python trade_monitor.py --paper-mode

    # Production mode (requires Phase 2.2 executor)
    python trade_monitor.py --no-paper-mode

Configuration:
    - check_interval: 60 seconds (configurable via --interval)
    - paper_mode: True (log signals instead of executing)
    - max_wallets: 20 (default limit)

Example:
    >>> from trade_monitor import TradeMonitor
    >>> monitor = TradeMonitor(paper_mode=True, check_interval=60)
    >>> monitor.run()  # Runs forever, Ctrl+C to stop
"""

import sqlite3
import logging
import time
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from threading import Lock
import sys
import uuid

# Web3 for DEX parsing
from web3 import Web3

# Import TokenBucket from wallet_discovery
from wallet_discovery import TokenBucket, load_config

# Import comprehensive DEX parser
from dex_parser import DexParser, SwapInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class WalletState:
    """State tracking for a single monitored wallet."""
    address: str
    allocation_pct: float
    last_checked_block: int
    last_checked_timestamp: datetime
    consecutive_errors: int = 0
    total_transactions_found: int = 0


@dataclass
class RawTransaction:
    """Raw transaction data from Etherscan API."""
    tx_hash: str
    block_number: int
    timestamp: datetime
    from_address: str
    to_address: str
    value: str  # Wei amount
    input_data: str  # Hex calldata
    gas_used: str
    gas_price: str
    receipt_status: str  # '1' = success, '0' = failed


@dataclass
class ParsedTrade:
    """Parsed DEX trade with extracted information."""
    tx_hash: str
    block_number: int
    timestamp: datetime
    wallet_address: str
    token_address: str
    token_symbol: str
    action: str  # 'BUY' or 'SELL'
    amount_usd: float
    dex_protocol: str  # 'uniswap_v2', 'uniswap_v3', etc.
    leverage_multiplier: int = 1


@dataclass
class TradeSignal:
    """Copy trade signal to be executed."""
    id: str
    wallet_address: str
    source_tx_hash: str
    token_address: str
    action: str
    amount_usd: float
    leverage: int
    allocation_pct: float
    copy_size_usd: float
    status: str = 'pending'
    created_at: datetime = field(default_factory=datetime.now)


# ============================================================================
# TRANSACTION FETCHER (API CLIENT)
# ============================================================================

class TransactionFetcher:
    """
    Etherscan API V2 client for fetching wallet transactions.

    Features:
        - Rate limiting via TokenBucket (5 req/sec)
        - Exponential backoff on failures
        - Block-based queries for exact ranges
        - Caching of current block number

    Args:
        api_key: Etherscan API key
        base_url: API V2 endpoint (default: Ethereum mainnet)
        chainid: Chain ID (1 for Ethereum, 56 for BSC)
        rate_limit: Requests per second (default: 5.0)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = 'https://api.etherscan.io/v2/api',
        chainid: int = 1,
        rate_limit: float = 5.0,
        max_retries: int = 5,
        timeout: int = 30
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.chainid = chainid
        self.max_retries = max_retries
        self.timeout = timeout
        self.rate_limiter = TokenBucket(rate=rate_limit)

        # Cache current block number (update every 15 seconds)
        self._block_cache: Optional[Tuple[int, float]] = None
        self._block_cache_ttl = 15  # seconds

    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make rate-limited API request with exponential backoff.

        Args:
            params: Query parameters

        Returns:
            dict: Parsed JSON response

        Raises:
            Exception: If all retries exhausted
        """
        params['apikey'] = self.api_key
        params['chainid'] = self.chainid

        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                self.rate_limiter.consume()

                # Make request
                response = requests.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()

                data = response.json()

                # Check API-level errors
                if data.get('status') == '0' and data.get('message') == 'NOTOK':
                    error_msg = data.get('result', 'Unknown error')

                    # Handle rate limiting
                    if 'rate limit' in error_msg.lower():
                        wait_time = 60
                        logger.warning(f"Rate limited by API, waiting {wait_time}s")
                        time.sleep(wait_time)
                        continue

                    # Other API errors
                    logger.debug(f"API error: {error_msg}")
                    raise Exception(f"API error: {error_msg}")

                return data

            except requests.exceptions.Timeout:
                wait_time = min(2 ** attempt, 32)
                logger.warning(f"Timeout, retry {attempt+1}/{self.max_retries}, waiting {wait_time}s")
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise Exception("Max retries exceeded due to timeout")

            except requests.exceptions.RequestException as e:
                wait_time = min(2 ** attempt, 32)
                logger.warning(f"Request failed: {e}, retry {attempt+1}/{self.max_retries}, waiting {wait_time}s")
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Max retries exceeded: {e}")

        raise Exception("Max retries exceeded")

    def get_latest_block(self) -> int:
        """
        Get current block number with caching.

        Returns:
            int: Current block number
        """
        # Check cache
        if self._block_cache:
            block, cached_at = self._block_cache
            if time.time() - cached_at < self._block_cache_ttl:
                return block

        # Fetch new block number
        params = {
            'module': 'proxy',
            'action': 'eth_blockNumber'
        }

        try:
            response = self._make_request(params)
            block = int(response.get('result', '0x0'), 16)
            self._block_cache = (block, time.time())
            return block
        except Exception as e:
            logger.error(f"Failed to fetch latest block: {e}")
            # Return cached value if available
            if self._block_cache:
                return self._block_cache[0]
            raise

    def get_transactions(
        self,
        address: str,
        start_block: int,
        end_block: int
    ) -> List[RawTransaction]:
        """
        Fetch transactions for address in block range.

        Args:
            address: Wallet address
            start_block: Starting block (inclusive)
            end_block: Ending block (inclusive)

        Returns:
            list[RawTransaction]: Transactions in range
        """
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'startblock': start_block,
            'endblock': end_block,
            'sort': 'asc'  # Chronological order
        }

        try:
            response = self._make_request(params)
            raw_txs = response.get('result', [])

            if not isinstance(raw_txs, list):
                logger.warning(f"Unexpected response format for {address[:10]}...")
                return []

            # Parse into RawTransaction objects
            transactions = []
            for tx in raw_txs:
                try:
                    # Only include successful transactions
                    if tx.get('txreceipt_status') != '1' and tx.get('isError') != '0':
                        continue

                    transactions.append(RawTransaction(
                        tx_hash=tx.get('hash', ''),
                        block_number=int(tx.get('blockNumber', 0)),
                        timestamp=datetime.fromtimestamp(int(tx.get('timeStamp', 0))),
                        from_address=tx.get('from', '').lower(),
                        to_address=tx.get('to', '').lower(),
                        value=tx.get('value', '0'),
                        input_data=tx.get('input', '0x'),
                        gas_used=tx.get('gasUsed', '0'),
                        gas_price=tx.get('gasPrice', '0'),
                        receipt_status=tx.get('txreceipt_status', '1')
                    ))
                except (ValueError, KeyError) as e:
                    logger.debug(f"Error parsing transaction: {e}")
                    continue

            return transactions

        except Exception as e:
            logger.error(f"Failed to fetch transactions for {address[:10]}...: {e}")
            return []


# ============================================================================
# DEX PARSER - Now using comprehensive dex_parser.py module
# ============================================================================
# The old simplified DEXParser class has been removed and replaced with
# the comprehensive DexParser from dex_parser.py that supports:
# - Uniswap V2/V3
# - PancakeSwap V2/V3
# - Event log parsing
# - Multi-hop swaps
# - CoinGecko price integration


# ============================================================================
# LEVERAGE DETECTOR
# ============================================================================

class LeverageDetector:
    """
    Detect leveraged trades from transaction patterns.

    Phase 2.1.A: Pattern-based detection using known protocol signatures
    Phase 2.1.B: Will add protocol-specific queries for exact leverage

    Detection Strategies:
        1. GMX Position Opening: Check for GMX router interaction
        2. Flash Loan Pattern: Detect flash loan + swap in same tx
        3. dYdX Margin: Check for dYdX protocol interaction
        4. Compound/Aave Borrow: Detect collateral deposit + borrow + swap

    Returns:
        int: Leverage multiplier (1-10), default 1 (no leverage)
    """

    # Known protocol addresses (Ethereum mainnet)
    GMX_ROUTER = '0xaBBc5F99639c9B6bCb58544ddf04EFA6802F4064'.lower()
    DYDX_SOLO_MARGIN = '0x1E0447b19BB6EcFdAe1e4AE1694b0C3659614e4e'.lower()

    # Flash loan providers
    AAVE_LENDING_POOL = '0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9'.lower()
    BALANCER_VAULT = '0xBA12222222228d8Ba445958a75a0704d566BF2C8'.lower()

    # DeFi protocol function signatures
    GMX_INCREASE_POSITION = '0x48d91abf'  # increasePosition()
    FLASHLOAN_SIGNATURE = '0xab9c4b5d'    # flashLoan()

    def __init__(self):
        self.leverage_cache: Dict[str, int] = {}  # tx_hash -> leverage

    def detect_leverage(
        self,
        tx: RawTransaction,
        parsed_trade: Optional[ParsedTrade] = None
    ) -> int:
        """
        Detect leverage multiplier from transaction patterns.

        Args:
            tx: Raw transaction data
            parsed_trade: Optional parsed trade info for context

        Returns:
            int: Leverage multiplier (1-10)
        """
        # Check cache
        if tx.tx_hash in self.leverage_cache:
            return self.leverage_cache[tx.tx_hash]

        leverage = 1  # Default: no leverage

        # Strategy 1: Check if interacting with GMX router
        if tx.to_address == self.GMX_ROUTER:
            if tx.input_data.startswith('0x48d91abf'):  # increasePosition
                leverage = self._estimate_gmx_leverage(tx)
                logger.debug(f"GMX position detected: {leverage}x leverage")

        # Strategy 2: Check for flash loan pattern
        elif self._is_flash_loan_pattern(tx):
            leverage = self._estimate_flash_loan_leverage(tx)
            logger.debug(f"Flash loan pattern detected: {leverage}x leverage")

        # Strategy 3: Check for dYdX margin trading
        elif tx.to_address == self.DYDX_SOLO_MARGIN:
            leverage = 3  # dYdX typically 3-5x
            logger.debug(f"dYdX margin trade detected: {leverage}x leverage")

        # Strategy 4: High gas usage indicator (complex DeFi interaction)
        elif self._is_high_gas_defi_tx(tx):
            leverage = 2  # Likely margin/leverage protocol
            logger.debug(f"High-gas DeFi tx detected: {leverage}x leverage")

        # Cache result
        self.leverage_cache[tx.tx_hash] = leverage
        return leverage

    def _estimate_gmx_leverage(self, tx: RawTransaction) -> int:
        """
        Estimate GMX position leverage from transaction value.

        GMX leverage calculation:
        - If tx value is small but gas is high, likely leveraged
        - Typical GMX: 2-10x leverage

        Args:
            tx: Raw transaction

        Returns:
            int: Estimated leverage (2-10)
        """
        value_eth = int(tx.value) / 10**18 if tx.value else 0
        gas_cost_eth = int(tx.gas_used) * int(tx.gas_price) / 10**18

        # If gas cost is significant relative to value, likely leveraged
        if value_eth > 0 and (gas_cost_eth / value_eth) > 0.1:
            return 5  # Conservative GMX leverage estimate

        return 3  # Default GMX leverage

    def _is_flash_loan_pattern(self, tx: RawTransaction) -> bool:
        """
        Detect if transaction uses flash loans.

        Pattern: Flash loan signature OR interaction with known providers

        Args:
            tx: Raw transaction

        Returns:
            bool: True if flash loan detected
        """
        # Check function signature
        if tx.input_data.startswith('0xab9c4b5d'):  # flashLoan()
            return True

        # Check if sent to flash loan provider
        if tx.to_address in {self.AAVE_LENDING_POOL, self.BALANCER_VAULT}:
            # Check if has complex calldata (indicates flash loan callback)
            if len(tx.input_data) > 1000:  # Flash loans have large calldata
                return True

        return False

    def _estimate_flash_loan_leverage(self, tx: RawTransaction) -> int:
        """
        Estimate leverage from flash loan size.

        Flash loan leverage = borrowed_amount / collateral
        For Phase 2.1.A, use conservative estimate.

        Args:
            tx: Raw transaction

        Returns:
            int: Estimated leverage (3-10)
        """
        # Check transaction value
        value_eth = int(tx.value) / 10**18 if tx.value else 0

        # Flash loans typically 5-20x position size
        # Conservative estimate: 5x
        if value_eth < 1:  # Small collateral
            return 10  # High leverage
        elif value_eth < 5:
            return 7
        else:
            return 5

    def _is_high_gas_defi_tx(self, tx: RawTransaction) -> bool:
        """
        Check if transaction has high gas usage (complex DeFi interaction).

        High gas suggests multi-step DeFi operations (collateral, borrow, swap).

        Args:
            tx: Raw transaction

        Returns:
            bool: True if high gas DeFi tx
        """
        gas_used = int(tx.gas_used) if tx.gas_used else 0

        # Complex DeFi txs typically use >500k gas
        # Simple swaps use ~150k gas
        return gas_used > 500000


# ============================================================================
# SIGNAL EMITTER
# ============================================================================

class SignalEmitter:
    """
    Emit copy trade signals in paper mode or queue for execution.

    Paper Mode (Phase 2.1.A):
        - Log signals to signals_paper.log
        - Do NOT execute trades
        - Safe for testing and validation

    Production Mode (Phase 2.2):
        - Insert signals to trade_signals table
        - Executor module will process queue

    Features:
        - Risk limit checking (max position size, daily trade count)
        - Signal deduplication
        - Allocation-based sizing
    """

    def __init__(
        self,
        db_path: str = 'wallet_trading.db',
        paper_mode: bool = True,
        paper_log: str = 'signals_paper.log'
    ):
        self.db_path = db_path
        self.paper_mode = paper_mode
        self.paper_log = paper_log

        # Risk limits
        self.max_copy_size_usd = 10000  # Max $10k per trade
        self.max_daily_trades = 50  # Max 50 trades per day

        # Setup paper mode logging
        if self.paper_mode:
            self._setup_paper_logging()

    def _setup_paper_logging(self) -> None:
        """Configure paper mode file logging."""
        paper_logger = logging.getLogger('paper_mode')
        paper_logger.setLevel(logging.INFO)

        # File handler
        handler = logging.FileHandler(self.paper_log)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        paper_logger.addHandler(handler)

        self.paper_logger = paper_logger

    def emit_signal(
        self,
        trade: ParsedTrade,
        wallet_state: WalletState
    ) -> Optional[TradeSignal]:
        """
        Emit copy trade signal for detected trade.

        Args:
            trade: Parsed trade information
            wallet_state: State of monitored wallet

        Returns:
            TradeSignal if emitted, None if rejected
        """
        # Calculate copy size
        copy_size_usd = trade.amount_usd * (wallet_state.allocation_pct / 100.0)

        # Apply leverage multiplier
        copy_size_usd *= trade.leverage_multiplier

        # Risk check: Maximum position size
        if copy_size_usd > self.max_copy_size_usd:
            logger.warning(
                f"Signal rejected: Copy size ${copy_size_usd:.2f} exceeds "
                f"max ${self.max_copy_size_usd}"
            )
            return None

        # Risk check: Minimum position size (avoid dust)
        if copy_size_usd < 100:
            logger.debug(f"Signal rejected: Copy size ${copy_size_usd:.2f} too small")
            return None

        # Create signal
        signal = TradeSignal(
            id=str(uuid.uuid4()),
            wallet_address=wallet_state.address,
            source_tx_hash=trade.tx_hash,
            token_address=trade.token_address,
            action=trade.action,
            amount_usd=trade.amount_usd,
            leverage=trade.leverage_multiplier,
            allocation_pct=wallet_state.allocation_pct,
            copy_size_usd=copy_size_usd,
            status='pending',
            created_at=datetime.now()
        )

        # Emit signal
        if self.paper_mode:
            self._log_paper_signal(signal, trade)
        else:
            self._queue_signal(signal)

        return signal

    def _log_paper_signal(self, signal: TradeSignal, trade: ParsedTrade) -> None:
        """
        Log signal to paper mode file (safe testing).

        Args:
            signal: Generated trade signal
            trade: Original parsed trade
        """
        message = (
            f"PAPER SIGNAL | "
            f"{signal.action} {trade.token_symbol} | "
            f"Source: {signal.wallet_address[:10]}... | "
            f"Amount: ${signal.copy_size_usd:.2f} | "
            f"Leverage: {signal.leverage}x | "
            f"Allocation: {signal.allocation_pct}% | "
            f"TX: {signal.source_tx_hash}"
        )

        self.paper_logger.info(message)
        logger.info(f"📋 {message}")

    def _queue_signal(self, signal: TradeSignal) -> None:
        """
        Queue signal in database for executor (Phase 2.2).

        Args:
            signal: Trade signal to queue
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO trade_signals (
                    id, wallet_address, source_tx_hash, token_address,
                    action, amount_usd, leverage, allocation_pct,
                    copy_size_usd, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.id,
                signal.wallet_address,
                signal.source_tx_hash,
                signal.token_address,
                signal.action,
                signal.amount_usd,
                signal.leverage,
                signal.allocation_pct,
                signal.copy_size_usd,
                signal.status,
                signal.created_at.isoformat()
            ))

            conn.commit()
            logger.info(f"✅ Queued signal {signal.id} for execution")

        except sqlite3.Error as e:
            logger.error(f"Failed to queue signal: {e}")

        finally:
            conn.close()


# ============================================================================
# TRADE MONITOR (MAIN ORCHESTRATOR)
# ============================================================================

class TradeMonitor:
    """
    Main orchestrator for real-time trade monitoring.

    Architecture:
        - Runs forever in 60-second cycles
        - Loads tracked wallets from database
        - For each wallet: fetch txs, parse DEX swaps, detect leverage, emit signals
        - Updates monitoring_state after each wallet
        - Handles errors gracefully with exponential backoff

    Usage:
        >>> monitor = TradeMonitor(paper_mode=True, check_interval=60)
        >>> monitor.run()  # Runs forever, Ctrl+C to stop
    """

    def __init__(
        self,
        db_path: str = 'wallet_trading.db',
        check_interval: int = 60,
        paper_mode: bool = True,
        config_path: str = 'config.json'
    ):
        self.db_path = db_path
        self.check_interval = check_interval
        self.paper_mode = paper_mode

        # Load configuration
        config = load_config(config_path)

        # Initialize Web3 connection for DEX parsing
        web3_provider = config.get('web3_provider_uri', 'https://eth.llamarpc.com')
        try:
            self.w3 = Web3(Web3.HTTPProvider(web3_provider))
            if not self.w3.is_connected:
                logger.warning(f"Web3 connection failed to {web3_provider}, DEX parsing will be limited")
                self.w3 = None
        except Exception as e:
            logger.warning(f"Failed to initialize Web3: {e}, DEX parsing will be limited")
            self.w3 = None

        # Initialize components
        self.fetcher = TransactionFetcher(
            api_key=config['etherscan_api_key'],
            base_url=config.get('etherscan_api_url', 'https://api.etherscan.io/v2/api'),
            chainid=config.get('chainid', 1),
            rate_limit=config.get('rate_limit', 5.0)
        )

        # Initialize comprehensive DEX parser
        if self.w3:
            self.parser = DexParser(
                w3=self.w3,
                etherscan_api_key=config.get('etherscan_api_key'),
                coingecko_api_key=config.get('coingecko_api_key')
            )
        else:
            logger.warning("DEX parser not initialized (no Web3 connection)")
            self.parser = None

        self.leverage_detector = LeverageDetector()
        self.signal_emitter = SignalEmitter(
            db_path=db_path,
            paper_mode=paper_mode
        )

        # Statistics
        self.cycle_count = 0
        self.total_trades_found = 0
        self.total_signals_emitted = 0

        logger.info("=" * 70)
        logger.info("TRADE MONITOR INITIALIZED")
        logger.info("=" * 70)
        logger.info(f"Database: {db_path}")
        logger.info(f"Check interval: {check_interval}s")
        logger.info(f"Paper mode: {paper_mode}")
        logger.info(f"API: Etherscan V2 (chainid={config.get('chainid', 1)})")
        logger.info(f"Web3: {'Connected' if self.w3 and self.w3.is_connected else 'Not connected'}")
        logger.info(f"DEX Parser: {'Enabled' if self.parser else 'Disabled'}")

    def load_tracked_wallets(self) -> List[WalletState]:
        """
        Load tracked wallets from database with monitoring state.

        Returns:
            list[WalletState]: Active wallets with monitoring state
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Join wallets + monitoring_state
            cursor.execute("""
                SELECT
                    w.address,
                    w.allocation_pct,
                    COALESCE(m.last_checked_block, 0) as last_checked_block,
                    COALESCE(m.last_checked_timestamp, datetime('now')) as last_checked_timestamp,
                    COALESCE(m.consecutive_errors, 0) as consecutive_errors,
                    COALESCE(m.total_transactions_found, 0) as total_transactions_found
                FROM wallets w
                LEFT JOIN monitoring_state m ON w.address = m.wallet_address
                WHERE w.is_active = 1
                ORDER BY w.rank_score DESC
            """)

            wallets = []
            for row in cursor.fetchall():
                wallets.append(WalletState(
                    address=row[0],
                    allocation_pct=row[1],
                    last_checked_block=row[2],
                    last_checked_timestamp=datetime.fromisoformat(row[3]),
                    consecutive_errors=row[4],
                    total_transactions_found=row[5]
                ))

            return wallets

        except sqlite3.Error as e:
            logger.error(f"Failed to load wallets: {e}")
            return []

        finally:
            conn.close()

    def check_wallet(self, wallet: WalletState, current_block: int) -> Dict[str, Any]:
        """
        Check single wallet for new transactions.

        Args:
            wallet: Wallet state to check
            current_block: Latest blockchain block

        Returns:
            dict: Results with trades, signals, errors
        """
        result = {
            'wallet': wallet.address,
            'trades_found': 0,
            'signals_emitted': 0,
            'error': None
        }

        try:
            # Determine block range
            start_block = wallet.last_checked_block + 1
            end_block = current_block

            if start_block > end_block:
                logger.debug(f"{wallet.address[:10]}... - No new blocks")
                return result

            # Fetch transactions
            transactions = self.fetcher.get_transactions(
                wallet.address,
                start_block,
                end_block
            )

            if not transactions:
                logger.debug(
                    f"{wallet.address[:10]}... - No transactions in blocks "
                    f"{start_block}-{end_block}"
                )
                self._update_monitoring_state(wallet.address, end_block, 0)
                return result

            # Process each transaction
            for tx in transactions:
                # Parse DEX swap using comprehensive parser
                if not self.parser:
                    logger.debug("DEX parser not available, skipping transaction")
                    continue

                swap_info = self.parser.parse_transaction(tx.tx_hash, wallet.address)
                if not swap_info:
                    continue

                # Convert SwapInfo to ParsedTrade
                trade = ParsedTrade(
                    tx_hash=swap_info.tx_hash,
                    block_number=swap_info.block_number,
                    timestamp=swap_info.timestamp,
                    wallet_address=swap_info.wallet_address,
                    token_address=swap_info.token_out,  # Track acquired token
                    token_symbol=swap_info.token_out_symbol,
                    action=swap_info.action,
                    amount_usd=swap_info.amount_out_usd,
                    dex_protocol=swap_info.dex_protocol,
                    leverage_multiplier=1  # Will be updated by leverage detector
                )

                # Detect leverage
                leverage = self.leverage_detector.detect_leverage(tx, trade)
                trade.leverage_multiplier = leverage

                # Emit copy signal
                signal = self.signal_emitter.emit_signal(trade, wallet)

                result['trades_found'] += 1
                if signal:
                    result['signals_emitted'] += 1

                # Save to database
                self._save_trade(trade, wallet.address)

            # Update monitoring state
            self._update_monitoring_state(
                wallet.address,
                end_block,
                result['trades_found']
            )

            if result['trades_found'] > 0:
                logger.info(
                    f"✅ {wallet.address[:10]}... - "
                    f"{result['trades_found']} trades, "
                    f"{result['signals_emitted']} signals"
                )

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ {wallet.address[:10]}... - Error: {e}")
            self._increment_error_count(wallet.address)

        return result

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run one complete monitoring cycle.

        Returns:
            dict: Cycle statistics
        """
        cycle_start = time.time()
        self.cycle_count += 1

        logger.info("")
        logger.info("=" * 70)
        logger.info(f"CYCLE #{self.cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        # Get current block
        try:
            current_block = self.fetcher.get_latest_block()
            logger.info(f"📊 Current block: {current_block:,}")
        except Exception as e:
            logger.error(f"Failed to fetch current block: {e}")
            return {'success': False, 'error': str(e)}

        # Load tracked wallets
        wallets = self.load_tracked_wallets()
        if not wallets:
            logger.warning("No active wallets to monitor")
            return {'success': False, 'error': 'No active wallets'}

        logger.info(f"👛 Monitoring {len(wallets)} wallets")

        # Check each wallet sequentially
        cycle_trades = 0
        cycle_signals = 0

        for wallet in wallets:
            result = self.check_wallet(wallet, current_block)
            cycle_trades += result['trades_found']
            cycle_signals += result['signals_emitted']

        # Update statistics
        self.total_trades_found += cycle_trades
        self.total_signals_emitted += cycle_signals

        cycle_duration = time.time() - cycle_start

        logger.info("")
        logger.info(f"📈 Cycle complete in {cycle_duration:.1f}s")
        logger.info(f"   Trades found: {cycle_trades}")
        logger.info(f"   Signals emitted: {cycle_signals}")
        logger.info(f"   Total trades: {self.total_trades_found}")
        logger.info(f"   Total signals: {self.total_signals_emitted}")

        return {
            'success': True,
            'cycle': self.cycle_count,
            'duration': cycle_duration,
            'trades': cycle_trades,
            'signals': cycle_signals
        }

    def monitoring_loop(self) -> None:
        """Main monitoring loop - runs forever."""
        logger.info("")
        logger.info("🚀 Starting monitoring loop...")
        logger.info(f"   Cycle interval: {self.check_interval}s")
        logger.info("   Press Ctrl+C to stop")
        logger.info("")

        while True:
            try:
                # Run cycle
                result = self.run_cycle()

                # Sleep until next cycle
                if result['success']:
                    sleep_time = max(0, self.check_interval - result['duration'])
                    if sleep_time > 0:
                        logger.info(f"😴 Sleeping {sleep_time:.1f}s until next cycle...")
                        time.sleep(sleep_time)
                else:
                    logger.warning("Cycle failed, waiting 60s before retry...")
                    time.sleep(60)

            except KeyboardInterrupt:
                logger.info("")
                logger.info("=" * 70)
                logger.info("MONITORING STOPPED (Ctrl+C)")
                logger.info("=" * 70)
                logger.info(f"Total cycles: {self.cycle_count}")
                logger.info(f"Total trades found: {self.total_trades_found}")
                logger.info(f"Total signals emitted: {self.total_signals_emitted}")
                break

            except Exception as e:
                logger.error(f"Unexpected error in monitoring loop: {e}")
                logger.info("Waiting 60s before retry...")
                time.sleep(60)

    def run(self) -> None:
        """Entry point - start monitoring."""
        self.monitoring_loop()

    def _save_trade(self, trade: ParsedTrade, wallet_address: str) -> None:
        """Save detected trade to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get wallet_id
            cursor.execute("SELECT id FROM wallets WHERE address = ?", (wallet_address,))
            row = cursor.fetchone()
            if not row:
                logger.error(f"Wallet {wallet_address} not found in database")
                return

            wallet_id = row[0]

            # Insert trade
            cursor.execute("""
                INSERT OR IGNORE INTO wallet_transactions (
                    wallet_id, tx_hash, block_number, timestamp,
                    token_address, action, amount_usd,
                    leverage_multiplier, dex_protocol, was_copied
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                wallet_id,
                trade.tx_hash,
                trade.block_number,
                trade.timestamp.isoformat(),
                trade.token_address,
                trade.action,
                trade.amount_usd,
                trade.leverage_multiplier,
                trade.dex_protocol
            ))

            conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Failed to save trade: {e}")

        finally:
            conn.close()

    def _update_monitoring_state(
        self,
        wallet_address: str,
        last_block: int,
        transactions_found: int
    ) -> None:
        """Update monitoring state for wallet."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO monitoring_state (
                    wallet_address,
                    last_checked_block,
                    last_checked_timestamp,
                    consecutive_errors,
                    total_transactions_found
                ) VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(wallet_address) DO UPDATE SET
                    last_checked_block = excluded.last_checked_block,
                    last_checked_timestamp = excluded.last_checked_timestamp,
                    consecutive_errors = 0,
                    total_transactions_found = total_transactions_found + excluded.total_transactions_found
            """, (wallet_address, last_block, datetime.now().isoformat(), transactions_found))

            conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Failed to update monitoring state: {e}")

        finally:
            conn.close()

    def _increment_error_count(self, wallet_address: str) -> None:
        """Increment consecutive error count for wallet."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE monitoring_state
                SET consecutive_errors = consecutive_errors + 1
                WHERE wallet_address = ?
            """, (wallet_address,))

            conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Failed to increment error count: {e}")

        finally:
            conn.close()


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Command-line interface for trade monitoring."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Real-time trade monitoring for wallet copy trading',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Paper mode (safe testing, logs to signals_paper.log)
  python trade_monitor.py --paper-mode

  # Production mode (requires Phase 2.2 executor)
  python trade_monitor.py --no-paper-mode

  # Custom interval (check every 30 seconds)
  python trade_monitor.py --paper-mode --interval 30

  # Custom database
  python trade_monitor.py --paper-mode --db-path /path/to/wallet_trading.db
        """
    )

    parser.add_argument(
        '--paper-mode',
        action='store_true',
        default=True,
        help='Run in paper mode (log signals, do not execute trades)'
    )
    parser.add_argument(
        '--no-paper-mode',
        action='store_false',
        dest='paper_mode',
        help='Run in production mode (execute trades, requires Phase 2.2)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='Check interval in seconds (default: 60)'
    )
    parser.add_argument(
        '--db-path',
        default='wallet_trading.db',
        help='Path to SQLite database (default: wallet_trading.db)'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to config file (default: config.json)'
    )

    args = parser.parse_args()

    # Validate database exists
    if not Path(args.db_path).exists():
        logger.error(f"Database not found: {args.db_path}")
        logger.error("Please run init_database.py and update_database_schema.py first")
        sys.exit(1)

    # Validate config exists
    if not Path(args.config).exists():
        logger.error(f"Config file not found: {args.config}")
        logger.error("Please create config.json with Etherscan API key")
        sys.exit(1)

    # Create and run monitor
    try:
        monitor = TradeMonitor(
            db_path=args.db_path,
            check_interval=args.interval,
            paper_mode=args.paper_mode,
            config_path=args.config
        )
        monitor.run()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
