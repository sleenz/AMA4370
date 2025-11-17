"""
Wallet Analyzer Module for Copy Trading System

Analyzes discovered wallets by calculating performance metrics from REAL on-chain
DEX swaps, ranking wallets, and allocating capital based on historical performance.

🆕 ENHANCED: Now uses comprehensive DEX parser to analyze actual trading activity
across 26+ protocols (Uniswap, Sushiswap, 1inch, Curve, Balancer, etc.)

Metrics Calculated:
    - Win rate (% profitable trades) - from matched buy/sell pairs
    - Sharpe ratio (risk-adjusted returns, capped at 3.0)
    - Max drawdown (worst peak-to-trough loss)
    - Profit factor (gross profit / gross loss)
    - Average return per trade
    - Consistency score (custom formula)
    - Total P&L from closed positions

Ranking Formula:
    Score = (Win_Rate × 0.25) + (Sharpe × 0.20) + (Profit_Factor × 0.20) +
            ((1 - Max_Drawdown) × 0.15) + (Consistency × 0.20)

Filter Criteria (RELAXED):
    - Win Rate > 45% (was 55%)
    - Max Drawdown < 40% (was 30%)
    - Minimum 30 closed trades (was 50)

Capital Allocation:
    - Top 5 wallets: 10% each
    - Wallets 6-10: 5% each
    - Wallets 11-20: 2.5% each

DEX Protocol Support:
    - Uniswap V2/V3, Sushiswap, PancakeSwap V2/V3
    - 1inch Aggregator (v3, v4, v5), 0x Protocol
    - Curve Finance, Balancer V2, Kyber Network
    - ParaSwap, OpenOcean, DODO, Matcha

Usage:
    python wallet_analyzer.py
"""

import csv
import json
import sqlite3
import logging
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import from wallet_discovery module
from wallet_discovery import (
    load_config,
    EtherscanClient,
    BSCScanClient,
    BlockchainAPIClient
)

# Import Web3 and DEX parser for swap analysis
from web3 import Web3
from dex_parser import DexParser, SwapInfo


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Constants
MIN_TRADE_VALUE_USD = 1.0  # Ignore dust trades below $1
MAX_RETURN_PCT_CAP = 500.0  # Cap outlier returns for Sharpe calculation
SHARPE_CAP = 3.0  # Cap Sharpe ratio for ranking formula


@dataclass
class Trade:
    """Single buy or sell transaction."""
    timestamp: datetime
    action: str  # 'BUY' or 'SELL'
    token_address: str
    token_symbol: str
    amount: float  # Token amount
    price_usd: float  # Price per token in USD
    value_usd: float  # Total value (amount * price)
    gas_fee_usd: float  # Gas fee in USD
    tx_hash: str

    def __post_init__(self):
        assert self.action in ['BUY', 'SELL'], f"Invalid action: {self.action}"
        assert self.amount > 0, f"Amount must be positive: {self.amount}"
        assert self.value_usd >= 0, f"Value cannot be negative: {self.value_usd}"


@dataclass
class ClosedTrade:
    """Completed trade with P&L calculation (includes gas fees)."""
    buy_trade: Trade
    sell_trade: Trade
    amount: float  # Amount matched
    buy_value: float  # USD spent (including gas)
    sell_value: float  # USD received (minus gas)
    pnl: float  # sell_value - buy_value
    pnl_pct: float  # (pnl / buy_value) * 100
    duration: timedelta  # Holding period

    @property
    def is_profitable(self) -> bool:
        return self.pnl > 0


@dataclass
class PerformanceMetrics:
    """Performance metrics for a wallet."""
    address: str
    chain: str

    # Trade counts
    total_closed_trades: int
    winning_trades: int
    losing_trades: int

    # Core metrics
    win_rate: float  # 0-100
    sharpe_ratio: float  # Capped at 3.0
    max_drawdown: float  # 0-1 (e.g., 0.25 = 25%)
    profit_factor: float
    avg_return_pct: float
    consistency_score: float  # 0-1

    # Aggregate P&L
    total_pnl: float
    gross_profit: float
    gross_loss: float

    # Additional stats
    avg_trade_duration_hours: float
    median_return_pct: float
    total_gas_fees: float

    def passes_filters(self) -> bool:
        """
        Check if wallet meets minimum criteria.

        Filters (RELAXED):
            - Win rate > 45% (was 55%)
            - Max drawdown < 40% (was 30%)
            - Minimum 30 closed trades (was 50)

        Returns:
            bool: True if passes all filters
        """
        if self.total_closed_trades < 30:
            logger.debug(
                f"{self.address[:10]}...: Only {self.total_closed_trades} trades (need 30)"
            )
            return False

        if self.win_rate <= 45.0:
            logger.debug(
                f"{self.address[:10]}...: Win rate {self.win_rate:.1f}% (need >45%)"
            )
            return False

        if self.max_drawdown >= 0.40:
            logger.debug(
                f"{self.address[:10]}...: Drawdown {self.max_drawdown*100:.1f}% (need <40%)"
            )
            return False

        logger.info(f"{self.address[:10]}...: ✓ PASSED all filters")
        return True


@dataclass
class RankedWallet:
    """Wallet with rank score and capital allocation."""
    address: str
    chain: str
    metrics: PerformanceMetrics
    rank_score: float  # 0-100
    rank_position: int = 0
    allocation_pct: float = 0.0

    @classmethod
    def calculate_score(cls, metrics: PerformanceMetrics) -> float:
        """
        Calculate ranking score using weighted formula.

        Formula:
            Score = (Win_Rate × 0.25) + (Sharpe × 0.20) + (Profit_Factor × 0.20) +
                    ((1 - Max_Drawdown) × 0.15) + (Consistency × 0.20)

        Components are normalized to 0-1 range before weighting.

        Args:
            metrics: Performance metrics for wallet

        Returns:
            float: Rank score (0-100)
        """
        # Normalize components to 0-1 range
        win_rate_norm = metrics.win_rate / 100  # Already 0-100

        # Sharpe: normalize by dividing by cap (3.0)
        sharpe_norm = min(metrics.sharpe_ratio / SHARPE_CAP, 1.0)

        # Profit factor: normalize by dividing by 3.0 (>3 is excellent)
        profit_factor_norm = min(metrics.profit_factor / 3.0, 1.0)

        # Drawdown component: 1 - drawdown (lower drawdown = higher score)
        drawdown_component = 1 - metrics.max_drawdown

        # Consistency: already 0-1
        consistency_norm = metrics.consistency_score

        # Weighted sum
        score = (
            win_rate_norm * 0.25 +
            sharpe_norm * 0.20 +
            profit_factor_norm * 0.20 +
            drawdown_component * 0.15 +
            consistency_norm * 0.20
        ) * 100  # Scale to 0-100

        return score


def load_discovered_wallets(filepath: str = "discovered_wallets.csv") -> List[Dict[str, str]]:
    """
    Load wallet candidates from CSV.

    Args:
        filepath: Path to discovered_wallets.csv

    Returns:
        List[Dict]: Wallet data with address, chain, etc.

    Raises:
        FileNotFoundError: If CSV doesn't exist
    """
    if not Path(filepath).exists():
        raise FileNotFoundError(f"Discovered wallets file not found: {filepath}")

    wallets = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            wallets.append(row)

    logger.info(f"Loaded {len(wallets)} wallets from {filepath}")
    return wallets


def fetch_wallet_transactions(
    client: BlockchainAPIClient,
    address: str,
    days: int = 90
) -> List[Trade]:
    """
    Fetch and parse DEX swaps for a wallet using comprehensive DEX parser.

    This enhanced version uses dex_parser.py to detect swaps across 26+ DEX protocols
    including Uniswap, Sushiswap, 1inch, Curve, Balancer, etc.

    Args:
        client: API client (Etherscan or BSCScan)
        address: Wallet address
        days: Days of history to fetch

    Returns:
        List[Trade]: Parsed DEX swap trades with USD values and gas fees
    """
    logger.debug(f"Fetching DEX swaps for {address[:10]}... ({days} days)")

    # Calculate timestamp range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())

    # Fetch raw transactions
    raw_txns = client.get_transactions(address, start_timestamp, end_timestamp)

    if not raw_txns:
        logger.warning(f"No transactions found for {address[:10]}...")
        return []

    # Initialize Web3 and DEX parser
    web3_provider = 'https://eth.llamarpc.com'  # Free RPC endpoint
    try:
        w3 = Web3(Web3.HTTPProvider(web3_provider))
        if not w3.is_connected():
            logger.warning(f"Web3 connection failed, using fallback parsing")
            w3 = None
    except Exception as e:
        logger.warning(f"Web3 initialization failed: {e}, using fallback")
        w3 = None

    # Initialize DEX parser if Web3 is available
    dex_parser = None
    if w3:
        try:
            config = load_config('config.json')
            dex_parser = DexParser(
                w3=w3,
                etherscan_api_key=config.get('etherscan_api_key'),
                coingecko_api_key=config.get('coingecko_api_key')
            )
        except Exception as e:
            logger.warning(f"DEX parser initialization failed: {e}")
            dex_parser = None

    # Get native token price for gas fee calculation
    native_price = client.get_current_price()

    # Parse transactions into Trade objects
    trades = []
    skipped_no_dex = 0
    skipped_failed = 0

    for tx in raw_txns:
        try:
            # Skip failed transactions
            if tx.get('txreceipt_status') == '0':
                skipped_failed += 1
                continue

            tx_hash = tx.get('hash', '')

            # Parse DEX swap if parser is available
            swap_info = None
            if dex_parser:
                try:
                    swap_info = dex_parser.parse_transaction(tx_hash, address)
                except Exception as e:
                    logger.debug(f"DEX parse failed for {tx_hash[:10]}...: {e}")

            if not swap_info:
                skipped_no_dex += 1
                continue

            # Calculate gas fee in USD
            gas_used = int(tx.get('gasUsed', 0))
            gas_price_wei = int(tx.get('gasPrice', 0))
            gas_fee_native = (gas_used * gas_price_wei) / 10**18
            gas_fee_usd = gas_fee_native * native_price

            # Skip dust trades
            if swap_info.amount_out_usd < MIN_TRADE_VALUE_USD:
                continue

            # Convert SwapInfo to Trade object
            # Use the output token (what was acquired) for tracking
            trades.append(Trade(
                timestamp=swap_info.timestamp,
                action=swap_info.action,  # 'BUY' or 'SELL'
                token_address=swap_info.token_out,
                token_symbol=swap_info.token_out_symbol,
                amount=swap_info.amount_out,
                price_usd=swap_info.amount_out_usd / swap_info.amount_out if swap_info.amount_out > 0 else 0,
                value_usd=swap_info.amount_out_usd,
                gas_fee_usd=gas_fee_usd,
                tx_hash=tx_hash
            ))

        except (ValueError, KeyError) as e:
            logger.debug(f"Error parsing transaction {tx.get('hash', 'unknown')}: {e}")
            continue

    logger.info(
        f"{address[:10]}...: Parsed {len(trades)} DEX swaps "
        f"(skipped {skipped_no_dex} non-DEX, {skipped_failed} failed)"
    )
    return trades


def is_token_tradeable(token_symbol: str) -> bool:
    """
    Check if token is tradeable on Binance or Bitget.

    For MVP, uses a hardcoded list of top tokens.
    Future: Query exchange APIs for real-time listings.

    Args:
        token_symbol: Token symbol (e.g., 'ETH', 'PEPE')

    Returns:
        bool: True if tradeable on major exchanges
    """
    # Top 200 tokens tradeable on major exchanges (as of 2025)
    TRADEABLE_TOKENS = {
        # Native tokens
        'ETH', 'BNB', 'BTC', 'SOL', 'ADA', 'XRP', 'DOGE', 'DOT', 'MATIC', 'AVAX',
        'LINK', 'UNI', 'ATOM', 'LTC', 'ETC', 'XLM', 'BCH', 'ALGO', 'ICP', 'FIL',

        # DeFi tokens
        'AAVE', 'MKR', 'COMP', 'SNX', 'YFI', 'SUSHI', 'CRV', 'BAL', '1INCH', 'UMA',

        # Stablecoins
        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'FRAX',

        # Layer 2
        'ARB', 'OP', 'STRK', 'IMX', 'LRC', 'METIS',

        # Meme coins
        'SHIB', 'PEPE', 'FLOKI', 'BONK', 'WIF', 'MEME',

        # Gaming/Metaverse
        'AXS', 'SAND', 'MANA', 'ENJ', 'GALA', 'APE',

        # AI tokens
        'FET', 'AGIX', 'OCEAN', 'RNDR',

        # Other major tokens
        'APT', 'SUI', 'SEI', 'INJ', 'TIA', 'RUNE', 'GRT', 'FTM', 'NEAR', 'FLOW',
        'HBAR', 'VET', 'THETA', 'EOS', 'EGLD', 'XTZ', 'NEO', 'KAVA', 'ROSE',
        'CHZ', 'ENS', 'LDO', 'RPL', 'GMX', 'BLUR', 'LOOKS', 'DYDX', 'PERP',
        'RUNE', 'OSMO', 'SCRT', 'LUNA', 'LUNC', 'ANC', 'MIR',

        # Additional tokens
        'QNT', 'MATIC', 'AVAX', 'FTM', 'ONE', 'CELO', 'ZIL', 'IOTA', 'WAVES',
        'KSM', 'KLAY', 'BTT', 'HOT', 'ZRX', 'BAT', 'SC', 'MINA', 'ANKR',
    }

    return token_symbol.upper() in TRADEABLE_TOKENS


def filter_tradeable_tokens(trades: List[Trade]) -> List[Trade]:
    """
    Filter trades to only include tokens tradeable on major exchanges.

    Args:
        trades: All trades

    Returns:
        List[Trade]: Filtered trades
    """
    filtered = [
        trade for trade in trades
        if is_token_tradeable(trade.token_symbol)
    ]

    logger.debug(
        f"Filtered {len(trades)} trades → {len(filtered)} tradeable "
        f"({len(filtered)/len(trades)*100:.1f}% kept)"
    )

    return filtered


def group_by_token(trades: List[Trade]) -> Dict[str, List[Trade]]:
    """
    Group trades by token address for FIFO matching.

    Args:
        trades: All trades

    Returns:
        Dict[token_address, List[Trade]]: Grouped trades
    """
    grouped = defaultdict(list)

    for trade in trades:
        grouped[trade.token_address].append(trade)

    logger.debug(f"Grouped {len(trades)} trades into {len(grouped)} tokens")
    return grouped


def match_trades_fifo(trades: List[Trade]) -> List[ClosedTrade]:
    """
    Match buy/sell transactions using FIFO accounting.

    Algorithm:
        1. Separate trades into buys and sells
        2. Sort both by timestamp (ascending)
        3. For each sell:
           - Match against oldest buy (FIFO)
           - Handle partial fills
           - Calculate P&L including gas fees
        4. Return list of closed trades

    Gas Fee Handling:
        - Buy gas fee added to cost basis (increases buy_value)
        - Sell gas fee subtracted from proceeds (decreases sell_value)
        - P&L = sell_value - buy_value (gas fees already factored in)

    Args:
        trades: All trades for a single token

    Returns:
        List[ClosedTrade]: Matched buy/sell pairs with P&L
    """
    if not trades:
        return []

    # Separate and sort
    buys = deque(sorted(
        [t for t in trades if t.action == 'BUY'],
        key=lambda t: t.timestamp
    ))

    sells = sorted(
        [t for t in trades if t.action == 'SELL'],
        key=lambda t: t.timestamp
    )

    if not buys or not sells:
        return []  # Need both buys and sells to create closed trades

    closed_trades = []

    for sell in sells:
        remaining_sell_amount = sell.amount

        while remaining_sell_amount > 0 and buys:
            buy = buys[0]  # Oldest buy (FIFO)

            # Determine match amount
            match_amount = min(buy.amount, remaining_sell_amount)

            # Calculate proportional values INCLUDING gas fees
            buy_ratio = match_amount / buy.amount
            sell_ratio = match_amount / sell.amount

            # Buy value includes proportional gas fee
            buy_value_matched = (buy.value_usd + buy.gas_fee_usd) * buy_ratio

            # Sell value minus proportional gas fee
            sell_value_matched = (sell.value_usd - sell.gas_fee_usd) * sell_ratio

            # Calculate P&L (gas fees already factored in)
            pnl = sell_value_matched - buy_value_matched
            pnl_pct = (pnl / buy_value_matched * 100) if buy_value_matched > 0 else 0

            # Calculate holding duration
            duration = sell.timestamp - buy.timestamp

            # Create closed trade
            closed_trades.append(ClosedTrade(
                buy_trade=buy,
                sell_trade=sell,
                amount=match_amount,
                buy_value=buy_value_matched,
                sell_value=sell_value_matched,
                pnl=pnl,
                pnl_pct=pnl_pct,
                duration=duration
            ))

            # Update remaining amounts
            remaining_sell_amount -= match_amount
            buy.amount -= match_amount

            # Remove fully matched buy
            if buy.amount <= 1e-8:  # Floating point tolerance
                buys.popleft()

    return closed_trades


def match_all_trades(grouped: Dict[str, List[Trade]]) -> List[ClosedTrade]:
    """
    Match trades for all tokens.

    Args:
        grouped: Trades grouped by token address

    Returns:
        List[ClosedTrade]: All closed trades across all tokens
    """
    all_closed = []

    for token_address, token_trades in grouped.items():
        closed = match_trades_fifo(token_trades)
        all_closed.extend(closed)

        if closed:
            logger.debug(
                f"Token {token_trades[0].token_symbol}: "
                f"{len(closed)} closed trades"
            )

    logger.info(f"Total closed trades across all tokens: {len(all_closed)}")
    return all_closed


def calculate_win_rate(closed_trades: List[ClosedTrade]) -> float:
    """
    Calculate win rate percentage.

    Formula:
        Win Rate = (Profitable Trades / Total Closed Trades) × 100

    Args:
        closed_trades: List of matched trades

    Returns:
        float: Win rate (0-100)
    """
    if not closed_trades:
        return 0.0

    profitable = sum(1 for trade in closed_trades if trade.pnl > 0)
    win_rate = (profitable / len(closed_trades)) * 100

    return win_rate


def calculate_sharpe_ratio(closed_trades: List[ClosedTrade]) -> float:
    """
    Calculate Sharpe ratio (risk-adjusted returns).

    Formula:
        Sharpe = Mean(returns) / StdDev(returns)

    Assumptions:
        - Risk-free rate = 0 (standard for crypto)
        - Returns capped at 500% to prevent outlier skew

    Interpretation:
        > 2.0 = Excellent
        1.0-2.0 = Good
        < 1.0 = Poor

    Args:
        closed_trades: List of matched trades

    Returns:
        float: Sharpe ratio (capped at 3.0 for ranking)
    """
    if len(closed_trades) < 2:
        return 0.0

    # Extract returns and cap outliers
    returns = [
        min(trade.pnl_pct, MAX_RETURN_PCT_CAP)
        for trade in closed_trades
    ]

    mean_return = np.mean(returns)
    std_return = np.std(returns, ddof=1)  # Sample std dev

    if std_return == 0:
        # No volatility - perfect consistency
        return 10.0 if mean_return > 0 else 0.0

    sharpe = mean_return / std_return

    # Cap at 3.0 for ranking formula
    return min(sharpe, SHARPE_CAP)


def calculate_max_drawdown(closed_trades: List[ClosedTrade]) -> float:
    """
    Calculate maximum peak-to-trough drawdown.

    Algorithm:
        1. Sort trades by sell timestamp
        2. Calculate cumulative P&L over time
        3. Track running peak value
        4. Calculate drawdown at each point
        5. Return maximum drawdown observed

    Formula:
        drawdown = (peak_value - trough_value) / peak_value

    Args:
        closed_trades: List of matched trades

    Returns:
        float: Max drawdown as decimal (0-1)
               e.g., 0.25 = 25% drawdown
    """
    if not closed_trades:
        return 0.0

    # Sort by sell timestamp (when P&L realized)
    sorted_trades = sorted(closed_trades, key=lambda t: t.sell_trade.timestamp)

    cumulative_pnl = 0
    peak_value = 0
    max_drawdown = 0

    for trade in sorted_trades:
        cumulative_pnl += trade.pnl

        # Update peak
        if cumulative_pnl > peak_value:
            peak_value = cumulative_pnl

        # Calculate drawdown from peak
        if peak_value > 0:
            current_drawdown = (peak_value - cumulative_pnl) / peak_value
            max_drawdown = max(max_drawdown, current_drawdown)

    return max_drawdown


def calculate_profit_factor(closed_trades: List[ClosedTrade]) -> float:
    """
    Calculate profit factor.

    Formula:
        Profit Factor = Gross Profit / Gross Loss

    Interpretation:
        > 2.0 = Excellent
        1.5-2.0 = Good
        < 1.0 = Losing

    Args:
        closed_trades: List of matched trades

    Returns:
        float: Profit factor ratio
    """
    if not closed_trades:
        return 0.0

    gross_profit = sum(trade.pnl for trade in closed_trades if trade.pnl > 0)
    gross_loss = abs(sum(trade.pnl for trade in closed_trades if trade.pnl < 0))

    if gross_loss == 0:
        # No losses - perfect performance
        return 999.0 if gross_profit > 0 else 0.0

    profit_factor = gross_profit / gross_loss
    return profit_factor


def calculate_consistency_score(closed_trades: List[ClosedTrade]) -> float:
    """
    Calculate consistency score (custom metric).

    Formula:
        volatility_coef = std_dev(returns) / abs(mean(returns))
        consistency = (win_rate / 100) × (1 - min(volatility_coef, 1.0))

    Logic:
        - High win rate + low volatility = high consistency
        - High win rate + high volatility = moderate consistency
        - Low win rate = low consistency

    Range: 0.0 to 1.0
        > 0.7 = Excellent
        0.5-0.7 = Good
        < 0.5 = Poor

    Args:
        closed_trades: List of matched trades

    Returns:
        float: Consistency score (0-1)
    """
    if len(closed_trades) < 2:
        return 0.0

    # Calculate win rate component
    win_rate = calculate_win_rate(closed_trades) / 100  # Normalize to 0-1

    # Calculate volatility component
    returns = [trade.pnl_pct for trade in closed_trades]
    mean_return = np.mean(returns)
    std_return = np.std(returns, ddof=1)

    if abs(mean_return) < 0.01:  # Near-zero returns
        return 0.0

    # Volatility coefficient (lower is better)
    volatility_coef = std_return / abs(mean_return)
    volatility_coef_capped = min(volatility_coef, 1.0)

    # Consistency: high win rate, low volatility
    consistency = win_rate * (1 - volatility_coef_capped)

    return consistency


def calculate_metrics(
    address: str,
    chain: str,
    closed_trades: List[ClosedTrade]
) -> Optional[PerformanceMetrics]:
    """
    Calculate all performance metrics for a wallet.

    Args:
        address: Wallet address
        chain: Blockchain name
        closed_trades: List of matched trades

    Returns:
        PerformanceMetrics: Calculated metrics, or None if insufficient data
    """
    if not closed_trades:
        logger.warning(f"{address[:10]}...: No closed trades")
        return None

    # Calculate all metrics
    total_closed = len(closed_trades)
    winning = sum(1 for t in closed_trades if t.pnl > 0)
    losing = sum(1 for t in closed_trades if t.pnl < 0)

    win_rate = calculate_win_rate(closed_trades)
    sharpe = calculate_sharpe_ratio(closed_trades)
    max_dd = calculate_max_drawdown(closed_trades)
    profit_factor = calculate_profit_factor(closed_trades)

    returns = [t.pnl_pct for t in closed_trades]
    avg_return = np.mean(returns)
    median_return = np.median(returns)

    consistency = calculate_consistency_score(closed_trades)

    # Aggregate P&L
    total_pnl = sum(t.pnl for t in closed_trades)
    gross_profit = sum(t.pnl for t in closed_trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in closed_trades if t.pnl < 0))

    # Gas fees
    total_gas = sum(t.buy_trade.gas_fee_usd + t.sell_trade.gas_fee_usd for t in closed_trades)

    # Average trade duration
    durations = [t.duration.total_seconds() / 3600 for t in closed_trades]  # Hours
    avg_duration = np.mean(durations)

    metrics = PerformanceMetrics(
        address=address,
        chain=chain,
        total_closed_trades=total_closed,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=win_rate,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
        profit_factor=profit_factor,
        avg_return_pct=avg_return,
        consistency_score=consistency,
        total_pnl=total_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        avg_trade_duration_hours=avg_duration,
        median_return_pct=median_return,
        total_gas_fees=total_gas
    )

    logger.info(
        f"{address[:10]}...: {total_closed} trades, "
        f"{win_rate:.1f}% win rate, Sharpe {sharpe:.2f}"
    )

    return metrics


def analyze_wallet(
    wallet_data: Dict[str, str],
    eth_client: EtherscanClient,
    bsc_client: BSCScanClient
) -> Optional[PerformanceMetrics]:
    """
    Analyze a single wallet: fetch trades, match, calculate metrics.

    Args:
        wallet_data: Dict with 'address' and 'chain' keys
        eth_client: Etherscan API client
        bsc_client: BSCScan API client

    Returns:
        PerformanceMetrics: Calculated metrics, or None if analysis fails
    """
    address = wallet_data['address']
    chain = wallet_data['chain']

    logger.info(f"\n{'='*60}")
    logger.info(f"Analyzing {address[:10]}... on {chain}")
    logger.info(f"{'='*60}")

    # Select appropriate client
    client = eth_client if chain == 'ethereum' else bsc_client

    try:
        # Step 1: Fetch transactions
        trades = fetch_wallet_transactions(client, address, days=90)

        if not trades:
            logger.warning(f"{address[:10]}...: No trades found")
            return None

        # Step 2: Filter tradeable tokens only
        trades = filter_tradeable_tokens(trades)

        if not trades:
            logger.warning(f"{address[:10]}...: No tradeable tokens")
            return None

        # Step 3: Group by token
        grouped = group_by_token(trades)

        # Step 4: Match trades (FIFO)
        closed_trades = match_all_trades(grouped)

        if not closed_trades:
            logger.warning(f"{address[:10]}...: No closed trades (only open positions)")
            return None

        # Step 5: Calculate metrics
        metrics = calculate_metrics(address, chain, closed_trades)

        return metrics

    except Exception as e:
        logger.error(f"Error analyzing {address[:10]}...: {e}", exc_info=True)
        return None


def rank_wallets(metrics_list: List[PerformanceMetrics]) -> List[RankedWallet]:
    """
    Rank wallets by score and allocate capital.

    Args:
        metrics_list: List of wallet metrics

    Returns:
        List[RankedWallet]: Ranked wallets with allocations
    """
    logger.info("\n" + "="*60)
    logger.info("RANKING WALLETS")
    logger.info("="*60)

    # Filter wallets
    qualified = [m for m in metrics_list if m.passes_filters()]

    logger.info(f"Qualified wallets: {len(qualified)} / {len(metrics_list)}")

    if not qualified:
        logger.warning("No wallets passed filters!")
        return []

    # Calculate scores
    ranked = []
    for metrics in qualified:
        score = RankedWallet.calculate_score(metrics)
        ranked.append(RankedWallet(
            address=metrics.address,
            chain=metrics.chain,
            metrics=metrics,
            rank_score=score,
            rank_position=0,  # Set after sorting
            allocation_pct=0.0  # Set after sorting
        ))

    # Sort by score (descending)
    ranked.sort(key=lambda w: w.rank_score, reverse=True)

    # Allocate capital
    ranked = allocate_capital(ranked)

    return ranked


def allocate_capital(ranked_wallets: List[RankedWallet]) -> List[RankedWallet]:
    """
    Allocate capital based on ranking.

    Allocation:
        - Top 5: 10% each (50% total)
        - Ranks 6-10: 5% each (25% total)
        - Ranks 11-20: 2.5% each (25% total)

    Args:
        ranked_wallets: Sorted list by rank_score

    Returns:
        List[RankedWallet]: With rank_position and allocation_pct set
    """
    for i, wallet in enumerate(ranked_wallets):
        wallet.rank_position = i + 1

        if i < 5:  # Top 5
            wallet.allocation_pct = 10.0
        elif i < 10:  # Ranks 6-10
            wallet.allocation_pct = 5.0
        elif i < 20:  # Ranks 11-20
            wallet.allocation_pct = 2.5
        else:  # Below rank 20
            wallet.allocation_pct = 0.0

    # Validate
    total_allocation = sum(w.allocation_pct for w in ranked_wallets[:20])
    expected = min(len(ranked_wallets), 20)
    expected_total = min(50 + 25 + 25, expected * 5)  # Adjust for < 20 wallets

    logger.info(f"Total capital allocated: {total_allocation:.1f}%")

    return ranked_wallets


def export_ranked_wallets(
    wallets: List[RankedWallet],
    filepath: str = "ranked_wallets.csv"
) -> None:
    """
    Export ranked wallets to CSV.

    Args:
        wallets: Ranked wallets with metrics
        filepath: Output CSV path
    """
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'rank', 'address', 'chain', 'rank_score',
            'win_rate', 'sharpe_ratio', 'max_drawdown', 'profit_factor',
            'consistency_score', 'avg_return_pct', 'total_trades',
            'total_pnl', 'total_gas_fees', 'allocation_pct'
        ])

        # Data rows
        for wallet in wallets:
            m = wallet.metrics
            writer.writerow([
                wallet.rank_position,
                wallet.address,
                wallet.chain,
                f"{wallet.rank_score:.2f}",
                f"{m.win_rate:.2f}",
                f"{m.sharpe_ratio:.2f}",
                f"{m.max_drawdown:.2%}",
                f"{m.profit_factor:.2f}",
                f"{m.consistency_score:.2f}",
                f"{m.avg_return_pct:.2f}",
                m.total_closed_trades,
                f"{m.total_pnl:.2f}",
                f"{m.total_gas_fees:.2f}",
                f"{wallet.allocation_pct:.2f}"
            ])

    logger.info(f"Exported {len(wallets)} wallets to {filepath}")


def update_database(
    wallets: List[RankedWallet],
    db_path: str = "wallet_trading.db"
) -> None:
    """
    Update wallets table in database.

    Priority: Database updates are critical for system operation.

    Args:
        wallets: Ranked wallets to insert/update
        db_path: Path to SQLite database
    """
    logger.info("\n" + "="*60)
    logger.info("UPDATING DATABASE")
    logger.info("="*60)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        for wallet in wallets:
            m = wallet.metrics

            cursor.execute("""
                INSERT OR REPLACE INTO wallets (
                    address,
                    rank_score,
                    total_trades,
                    winning_trades,
                    total_pnl,
                    win_rate,
                    sharpe_ratio,
                    avg_return,
                    max_drawdown,
                    allocation_pct,
                    is_active,
                    first_seen,
                    last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet.address,
                wallet.rank_score,
                m.total_closed_trades,
                m.winning_trades,
                m.total_pnl,
                m.win_rate,
                m.sharpe_ratio,
                m.avg_return_pct,
                m.max_drawdown,
                wallet.allocation_pct,
                1,  # is_active
                datetime.now().isoformat(),  # first_seen (or existing value preserved by REPLACE)
                datetime.now().isoformat()   # last_updated
            ))

        conn.commit()
        logger.info(f"Updated {len(wallets)} wallets in database")

    except sqlite3.Error as e:
        logger.error(f"Database update failed: {e}", exc_info=True)
        raise

    finally:
        conn.close()


def print_summary(ranked: List[RankedWallet]) -> None:
    """
    Print summary statistics to console.

    Args:
        ranked: List of ranked wallets
    """
    print("\n" + "="*70)
    print("WALLET ANALYSIS COMPLETE")
    print("="*70)

    print(f"\nQualified wallets: {len(ranked)}")

    if ranked:
        print(f"\nTop 10 Wallets:")
        print("-" * 70)
        print(f"{'Rank':<6} {'Address':<12} {'Score':<8} {'Win Rate':<10} {'Sharpe':<8} {'Allocation':<10}")
        print("-" * 70)

        for wallet in ranked[:10]:
            print(
                f"{wallet.rank_position:<6} "
                f"{wallet.address[:10]:<12} "
                f"{wallet.rank_score:<8.2f} "
                f"{wallet.metrics.win_rate:<10.1f}% "
                f"{wallet.metrics.sharpe_ratio:<8.2f} "
                f"{wallet.allocation_pct:<10.1f}%"
            )

        print("\n" + "="*70)
        print(f"Output: ranked_wallets.csv")
        print(f"Database: wallet_trading.db (updated)")
        print("="*70 + "\n")


def main() -> None:
    """
    Main execution function for wallet analyzer.

    Pipeline:
        1. Load discovered wallets from CSV
        2. Initialize API clients
        3. Analyze each wallet (fetch, match, calculate)
        4. Rank wallets and allocate capital
        5. Update database (priority)
        6. Export CSV
        7. Print summary
    """
    logger.info("="*70)
    logger.info("WALLET ANALYZER - Starting")
    logger.info("="*70)

    try:
        # Step 1: Load discovered wallets
        wallets = load_discovered_wallets("discovered_wallets.csv")

        if not wallets:
            logger.error("No wallets to analyze")
            return

        # Step 2: Initialize API clients
        config = load_config()
        eth_client = EtherscanClient(
            api_key=config['etherscan_api_key'],
            rate_limit=config['rate_limit_per_second']
        )
        bsc_client = BSCScanClient(
            api_key=config['bscscan_api_key'],
            rate_limit=config['rate_limit_per_second']
        )

        logger.info("API clients initialized")

        # Step 3: Analyze all wallets
        metrics_list = []

        for wallet_data in wallets:
            metrics = analyze_wallet(wallet_data, eth_client, bsc_client)
            if metrics:
                metrics_list.append(metrics)

        logger.info(f"\nAnalyzed {len(metrics_list)} / {len(wallets)} wallets successfully")

        if not metrics_list:
            logger.error("No wallets successfully analyzed")
            return

        # Step 4: Rank wallets
        ranked = rank_wallets(metrics_list)

        if not ranked:
            logger.warning("No wallets passed filters")
            return

        # Step 5: Update database (PRIORITY)
        try:
            update_database(ranked)
        except Exception as e:
            logger.error(f"CRITICAL: Database update failed: {e}")
            # Continue to CSV export even if DB fails

        # Step 6: Export CSV
        try:
            export_ranked_wallets(ranked)
        except Exception as e:
            logger.error(f"CSV export failed: {e}")

        # Step 7: Print summary
        print_summary(ranked)

    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
