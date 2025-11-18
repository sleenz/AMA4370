"""
Edge Case Handlers for Signal Processor (Phase 3.2 Enhancements)

This module provides advanced edge case handling for signal processing:
1. Enhanced wallet balance estimation with confidence scoring
2. Extreme leverage capping and risk adjustment
3. Signal aggregation for correlated trades
4. Expected slippage calculation
5. Signal queue with retry logic for exchange downtime

Usage:
    from edge_case_handlers import (
        WalletBalanceEstimator,
        SignalAggregator,
        SlippageCalculator,
        SignalQueue
    )
"""

import sqlite3
import logging
import math
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class BalanceEstimate:
    """Result of wallet balance estimation."""
    wallet_address: str
    estimated_balance: float
    confidence: str  # 'low', 'medium', 'high'
    method: str  # 'largest_trade', 'volume_average', 'transaction_count', 'default'
    data_points: int  # Number of transactions used
    time_range_days: int  # Historical data range
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class AggregatedSignal:
    """Aggregated signal from multiple sources."""
    id: str
    pair: str
    side: str
    aggregated_size_usd: float
    aggregation_count: int
    aggregation_multiplier: float
    source_signals: List[str]  # Signal IDs
    source_wallets: List[str]  # Wallet addresses
    wallet_contributions: Dict[str, float]  # wallet → contribution %
    avg_leverage: int
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SlippageEstimate:
    """Expected slippage calculation."""
    pair: str
    side: str
    position_size_usd: float
    expected_slippage_pct: float
    expected_entry_price: float
    is_acceptable: bool
    orderbook_depth_usd: float
    checked_at: datetime = field(default_factory=datetime.now)


@dataclass
class QueuedSignal:
    """Signal queued for retry."""
    signal: Any  # TradeSignal
    token_mapping: Any  # TokenMapping
    queued_at: datetime
    retry_count: int = 0
    last_retry_at: Optional[datetime] = None
    rejection_reason: str = ""


# ============================================================================
# WALLET BALANCE ESTIMATOR
# ============================================================================

class WalletBalanceEstimator:
    """
    Enhanced wallet balance estimation with confidence scoring.

    Strategies:
        1. Largest Trade Method: balance = largest_trade / 0.20
        2. Volume Average Method: 30-day rolling average
        3. Transaction Count Method: trade_count × avg_size
        4. Default by Rank: Fallback estimates

    Confidence Scoring:
        High: >20 transactions, <90 days old data
        Medium: 5-20 transactions or 90-180 days old
        Low: <5 transactions or >180 days old
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.cache: Dict[str, BalanceEstimate] = {}
        self.cache_ttl = 3600  # 1 hour

    def estimate(
        self,
        wallet_address: str,
        force_refresh: bool = False
    ) -> BalanceEstimate:
        """
        Estimate wallet balance with confidence scoring.

        Args:
            wallet_address: Wallet address to estimate
            force_refresh: Bypass cache

        Returns:
            BalanceEstimate with balance and confidence
        """
        wallet_lower = wallet_address.lower()

        # Check cache
        if not force_refresh and wallet_lower in self.cache:
            estimate = self.cache[wallet_lower]
            age = (datetime.now() - estimate.last_updated).seconds
            if age < self.cache_ttl:
                return estimate

        # Try multiple estimation methods
        methods = [
            self._estimate_from_volume_average,
            self._estimate_from_largest_trade,
            self._estimate_from_transaction_count,
            self._estimate_from_rank
        ]

        for method in methods:
            try:
                estimate = method(wallet_lower)
                if estimate:
                    self.cache[wallet_lower] = estimate
                    logger.info(
                        f"Balance estimated for {wallet_lower[:10]}...: "
                        f"${estimate.estimated_balance:,.0f} "
                        f"(confidence: {estimate.confidence}, method: {estimate.method})"
                    )
                    return estimate
            except Exception as e:
                logger.debug(f"Estimation method {method.__name__} failed: {e}")
                continue

        # All methods failed, use default
        return self._estimate_from_rank(wallet_lower)

    def _estimate_from_volume_average(self, wallet_address: str) -> Optional[BalanceEstimate]:
        """
        Estimate from 30-day rolling average transaction volume.

        Assumption: Traders use ~10-20% of capital actively
        Formula: balance = 30day_volume × 5
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get transactions from last 30 days
        cutoff = datetime.now() - timedelta(days=30)

        cursor.execute("""
            SELECT
                SUM(value_usd) as total_volume,
                COUNT(*) as trade_count,
                MAX(timestamp) as last_trade
            FROM wallet_transactions
            WHERE wallet_id = (SELECT id FROM wallets WHERE address = ?)
                AND timestamp > ?
        """, (wallet_address, cutoff.isoformat()))

        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            return None

        total_volume, trade_count, last_trade_str = row

        if total_volume < 10000:  # Less than $10k volume
            return None

        # Estimate balance (assume using 20% of capital)
        estimated_balance = total_volume * 5

        # Calculate confidence
        last_trade = datetime.fromisoformat(last_trade_str) if last_trade_str else None
        days_since_trade = (datetime.now() - last_trade).days if last_trade else 999

        if trade_count >= 20 and days_since_trade < 30:
            confidence = 'high'
        elif trade_count >= 10 and days_since_trade < 90:
            confidence = 'medium'
        else:
            confidence = 'low'

        return BalanceEstimate(
            wallet_address=wallet_address,
            estimated_balance=estimated_balance,
            confidence=confidence,
            method='volume_average',
            data_points=trade_count,
            time_range_days=30
        )

    def _estimate_from_largest_trade(self, wallet_address: str) -> Optional[BalanceEstimate]:
        """
        Estimate from largest trade (assume it's 20% of capital).

        Formula: balance = largest_trade / 0.20
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                MAX(value_usd) as largest_trade,
                COUNT(*) as trade_count,
                MAX(timestamp) as last_trade
            FROM wallet_transactions
            WHERE wallet_id = (SELECT id FROM wallets WHERE address = ?)
        """, (wallet_address,))

        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            return None

        largest_trade, trade_count, last_trade_str = row

        # Estimate balance
        estimated_balance = largest_trade / 0.20

        # Calculate confidence
        last_trade = datetime.fromisoformat(last_trade_str) if last_trade_str else None
        days_since_trade = (datetime.now() - last_trade).days if last_trade else 999

        if trade_count >= 10 and days_since_trade < 90:
            confidence = 'medium'
        elif trade_count >= 5:
            confidence = 'low'
        else:
            confidence = 'low'

        return BalanceEstimate(
            wallet_address=wallet_address,
            estimated_balance=estimated_balance,
            confidence=confidence,
            method='largest_trade',
            data_points=trade_count,
            time_range_days=999  # All time
        )

    def _estimate_from_transaction_count(self, wallet_address: str) -> Optional[BalanceEstimate]:
        """
        Estimate from transaction count and average size.

        Formula: balance = trade_count × avg_trade_size × 2
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                AVG(value_usd) as avg_size,
                COUNT(*) as trade_count
            FROM wallet_transactions
            WHERE wallet_id = (SELECT id FROM wallets WHERE address = ?)
        """, (wallet_address,))

        row = cursor.fetchone()
        conn.close()

        if not row or not row[0] or row[1] < 5:
            return None

        avg_size, trade_count = row

        # Estimate: active traders have capital for 2x their average trade
        estimated_balance = trade_count * avg_size * 2

        return BalanceEstimate(
            wallet_address=wallet_address,
            estimated_balance=estimated_balance,
            confidence='low',
            method='transaction_count',
            data_points=trade_count,
            time_range_days=999
        )

    def _estimate_from_rank(self, wallet_address: str) -> BalanceEstimate:
        """
        Fallback: Estimate from wallet rank.

        Rank-based estimates:
            Rank 1-3: $5M
            Rank 4-10: $2M
            Rank 11-20: $1M
            Default: $500k
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Calculate ordinal rank from rank_score
        cursor.execute("""
            SELECT (
                SELECT COUNT(*) + 1
                FROM wallets w2
                WHERE w2.rank_score > w1.rank_score AND w2.is_active = 1
            ) as rank
            FROM wallets w1
            WHERE w1.address = ?
        """, (wallet_address,))

        row = cursor.fetchone()
        conn.close()

        if row:
            rank = row[0]
            if rank <= 3:
                balance = 5_000_000
            elif rank <= 10:
                balance = 2_000_000
            elif rank <= 20:
                balance = 1_000_000
            else:
                balance = 500_000
        else:
            balance = 500_000

        return BalanceEstimate(
            wallet_address=wallet_address,
            estimated_balance=balance,
            confidence='low',
            method='default',
            data_points=0,
            time_range_days=0
        )


# ============================================================================
# SIGNAL AGGREGATOR
# ============================================================================

class SignalAggregator:
    """
    Aggregate correlated signals (multiple wallets buying same token).

    See SIGNAL_AGGREGATION_DESIGN.md for complete algorithm documentation.
    """

    def __init__(self, config: dict, db_path: str):
        self.config = config
        self.db_path = db_path

        # Configuration
        agg_config = config.get('signal_aggregation', {})
        self.enabled = agg_config.get('enabled', True)
        self.time_window_seconds = agg_config.get('time_window_seconds', 120)
        self.max_signals = agg_config.get('max_signals_per_aggregation', 5)
        self.boost_per_signal = agg_config.get('boost_per_signal', 0.3)
        self.max_multiplier = agg_config.get('max_multiplier', 2.0)

        # Pending signals grouped by pair
        self.pending_signals: Dict[str, List[Dict]] = defaultdict(list)

    def should_aggregate(self, pair: str, new_signal_time: datetime) -> bool:
        """
        Check if there are signals to aggregate for this pair.

        Returns:
            bool: True if multiple signals within time window
        """
        if not self.enabled:
            return False

        pending = self.pending_signals.get(pair, [])
        if len(pending) < 1:
            return False

        # Check if any pending signal is within time window
        for p in pending:
            time_diff = abs((new_signal_time - p['added_at']).total_seconds())
            if time_diff <= self.time_window_seconds:
                return True

        return False

    def add_signal(
        self,
        signal: Any,
        token_mapping: Any,
        individual_size: float,
        wallet_rank: int
    ) -> None:
        """Add signal to pending queue."""
        pair = token_mapping.cex_pair

        self.pending_signals[pair].append({
            'signal': signal,
            'mapping': token_mapping,
            'size': individual_size,
            'rank': wallet_rank,
            'added_at': datetime.now()
        })

        # Clean up old signals (>5 minutes)
        self._cleanup_expired_signals(pair)

    def _cleanup_expired_signals(self, pair: str) -> None:
        """Remove signals older than 5 minutes."""
        cutoff = datetime.now() - timedelta(minutes=5)
        self.pending_signals[pair] = [
            s for s in self.pending_signals[pair]
            if s['added_at'] > cutoff
        ]

    def get_signals_to_aggregate(
        self,
        pair: str,
        new_signal_time: datetime
    ) -> List[Dict]:
        """
        Get all signals within aggregation time window.

        Returns:
            List of signal dicts to aggregate
        """
        pending = self.pending_signals.get(pair, [])

        signals_in_window = [
            s for s in pending
            if abs((new_signal_time - s['added_at']).total_seconds()) <= self.time_window_seconds
        ]

        return signals_in_window

    def aggregate(
        self,
        signals: List[Dict]
    ) -> AggregatedSignal:
        """
        Aggregate multiple signals using weighted formula.

        Formula:
            base = sum(size × weight)
            multiplier = 1.0 + (count - 1) × boost_per_signal
            total = base × multiplier (capped at max_multiplier)

        Args:
            signals: List of signal dicts with 'signal', 'size', 'rank'

        Returns:
            AggregatedSignal
        """
        if len(signals) == 1:
            # No aggregation needed
            s = signals[0]
            return AggregatedSignal(
                id=s['signal'].id,
                pair=s['mapping'].cex_pair,
                side=s['signal'].action,
                aggregated_size_usd=s['size'],
                aggregation_count=1,
                aggregation_multiplier=1.0,
                source_signals=[s['signal'].id],
                source_wallets=[s['signal'].wallet_address],
                wallet_contributions={s['signal'].wallet_address: 100.0},
                avg_leverage=s['signal'].leverage
            )

        # Calculate weights
        weights = [self._get_wallet_weight(s['rank']) for s in signals]

        # Calculate weighted base
        base_size = sum(s['size'] * w for s, w in zip(signals, weights))

        # Apply boost for multiple signals
        signal_count = len(signals)
        multiplier = 1.0 + (signal_count - 1) * self.boost_per_signal
        multiplier = min(multiplier, self.max_multiplier)

        # Final aggregated size
        aggregated_size = base_size * multiplier

        # Calculate contributions
        total_individual = sum(s['size'] for s in signals)
        contributions = {
            s['signal'].wallet_address: (s['size'] / total_individual) * 100
            for s in signals
        }

        # Calculate average leverage (weighted)
        avg_leverage = sum(
            s['signal'].leverage * (s['size'] / total_individual)
            for s in signals
        )
        avg_leverage = int(round(avg_leverage))

        logger.info(
            f"Aggregated {len(signals)} signals: "
            f"${total_individual:.2f} → ${aggregated_size:.2f} "
            f"(multiplier: {multiplier:.2f}x)"
        )

        return AggregatedSignal(
            id=signals[0]['signal'].id,  # Use first signal ID
            pair=signals[0]['mapping'].cex_pair,
            side=signals[0]['signal'].action,
            aggregated_size_usd=aggregated_size,
            aggregation_count=len(signals),
            aggregation_multiplier=multiplier,
            source_signals=[s['signal'].id for s in signals],
            source_wallets=[s['signal'].wallet_address for s in signals],
            wallet_contributions=contributions,
            avg_leverage=avg_leverage
        )

    def _get_wallet_weight(self, rank: int) -> float:
        """
        Get aggregation weight for wallet based on rank.

        Weight schedule:
            Rank 1: 1.0
            Rank 2: 0.8
            Rank 3: 0.6
            Rank 4-5: 0.5
            Rank 6-10: 0.3
            Rank 11+: 0.2
        """
        if rank == 1:
            return 1.0
        elif rank == 2:
            return 0.8
        elif rank == 3:
            return 0.6
        elif rank <= 5:
            return 0.5
        elif rank <= 10:
            return 0.3
        else:
            return 0.2

    def clear_aggregated_signals(self, pair: str, signal_ids: List[str]) -> None:
        """Remove aggregated signals from pending queue."""
        self.pending_signals[pair] = [
            s for s in self.pending_signals.get(pair, [])
            if s['signal'].id not in signal_ids
        ]


# ============================================================================
# SLIPPAGE CALCULATOR
# ============================================================================

class SlippageCalculator:
    """
    Calculate expected slippage for position execution.

    Slippage calculation based on:
        1. Order book depth
        2. Position size
        3. Historical volatility
    """

    def __init__(self, config: dict):
        self.config = config

        # Thresholds
        self.acceptable_slippage_pct = config.get('acceptable_slippage_pct', 1.0)
        self.warning_slippage_pct = config.get('warning_slippage_pct', 0.5)

    def estimate(
        self,
        pair: str,
        side: str,
        position_size_usd: float,
        orderbook: Dict
    ) -> SlippageEstimate:
        """
        Estimate expected slippage.

        Args:
            pair: Trading pair
            side: 'BUY' or 'SELL'
            position_size_usd: Position size
            orderbook: Orderbook data {'bids': [...], 'asks': [...]}

        Returns:
            SlippageEstimate
        """
        # Select appropriate side of orderbook
        if side == 'BUY':
            orders = orderbook['asks']  # We're buying from sellers
            best_price = orders[0][0]
        else:
            orders = orderbook['bids']  # We're selling to buyers
            best_price = orders[0][0]

        # Calculate how much we can fill at each level
        filled_usd = 0
        weighted_price_sum = 0
        total_quantity = 0

        for price, quantity in orders:
            order_value_usd = price * quantity

            if filled_usd + order_value_usd >= position_size_usd:
                # This level completes our order
                remaining = position_size_usd - filled_usd
                quantity_needed = remaining / price

                weighted_price_sum += price * quantity_needed
                total_quantity += quantity_needed
                filled_usd += remaining
                break
            else:
                # Take entire level
                weighted_price_sum += price * quantity
                total_quantity += quantity
                filled_usd += order_value_usd

        if total_quantity == 0:
            # Insufficient liquidity
            expected_entry_price = best_price
            expected_slippage_pct = 99.9  # Effectively infinite
        else:
            # Calculate weighted average execution price
            expected_entry_price = weighted_price_sum / total_quantity

            # Calculate slippage
            if side == 'BUY':
                expected_slippage_pct = ((expected_entry_price - best_price) / best_price) * 100
            else:
                expected_slippage_pct = ((best_price - expected_entry_price) / best_price) * 100

        # Check if acceptable
        is_acceptable = expected_slippage_pct <= self.acceptable_slippage_pct

        if expected_slippage_pct > self.warning_slippage_pct:
            logger.warning(
                f"High expected slippage for {pair} {side}: {expected_slippage_pct:.2f}%"
            )

        return SlippageEstimate(
            pair=pair,
            side=side,
            position_size_usd=position_size_usd,
            expected_slippage_pct=expected_slippage_pct,
            expected_entry_price=expected_entry_price,
            is_acceptable=is_acceptable,
            orderbook_depth_usd=filled_usd
        )


# ============================================================================
# SIGNAL QUEUE (FOR EXCHANGE DOWNTIME)
# ============================================================================

class SignalQueue:
    """
    Queue signals for retry during exchange downtime.

    Features:
        - Max queue size (20 signals)
        - Signal expiration (5 minutes)
        - Retry logic with backoff
        - Priority based on wallet rank
    """

    def __init__(self, config: dict, db_path: str):
        self.config = config
        self.db_path = db_path

        # Configuration
        self.max_queue_size = config.get('max_queue_size', 20)
        self.signal_expiration_seconds = config.get('signal_expiration_seconds', 300)  # 5 min
        self.max_retries = config.get('max_retries', 3)

        # Queue (priority queue: higher rank = higher priority)
        self.queue: List[QueuedSignal] = []

    def add(
        self,
        signal: Any,
        token_mapping: Any,
        rejection_reason: str = "exchange_downtime"
    ) -> bool:
        """
        Add signal to queue.

        Returns:
            bool: True if added, False if queue full
        """
        if len(self.queue) >= self.max_queue_size:
            logger.warning(f"Signal queue full ({len(self.queue)} signals), dropping oldest")
            # Remove oldest signal
            self.queue.pop(0)

        queued_signal = QueuedSignal(
            signal=signal,
            token_mapping=token_mapping,
            queued_at=datetime.now(),
            retry_count=0,
            rejection_reason=rejection_reason
        )

        self.queue.append(queued_signal)

        # Sort by wallet rank (higher rank first)
        self.queue.sort(key=lambda x: self._get_wallet_rank(x.signal.wallet_address), reverse=False)

        logger.info(f"Signal queued for retry: {signal.token_symbol} (queue size: {len(self.queue)})")

        return True

    def get_retryable_signals(self) -> List[QueuedSignal]:
        """
        Get signals ready for retry.

        Returns:
            List of signals that should be retried now
        """
        now = datetime.now()
        retryable = []

        for queued in self.queue:
            # Check if expired
            age = (now - queued.queued_at).total_seconds()
            if age > self.signal_expiration_seconds:
                continue

            # Check if max retries reached
            if queued.retry_count >= self.max_retries:
                continue

            # Check retry backoff
            if queued.last_retry_at:
                # Exponential backoff: 10s, 30s, 60s
                backoff = 10 * (2 ** queued.retry_count)
                time_since_retry = (now - queued.last_retry_at).total_seconds()
                if time_since_retry < backoff:
                    continue

            retryable.append(queued)

        return retryable

    def mark_retry(self, queued: QueuedSignal) -> None:
        """Mark signal as retried."""
        queued.retry_count += 1
        queued.last_retry_at = datetime.now()

    def remove(self, queued: QueuedSignal) -> None:
        """Remove signal from queue."""
        if queued in self.queue:
            self.queue.remove(queued)

    def cleanup_expired(self) -> int:
        """
        Remove expired signals from queue.

        Returns:
            int: Number of signals removed
        """
        now = datetime.now()
        initial_size = len(self.queue)

        self.queue = [
            q for q in self.queue
            if (now - q.queued_at).total_seconds() <= self.signal_expiration_seconds
        ]

        removed = initial_size - len(self.queue)
        if removed > 0:
            logger.info(f"Removed {removed} expired signals from queue")

        return removed

    def _get_wallet_rank(self, wallet_address: str) -> int:
        """Get wallet rank from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Calculate ordinal rank from rank_score
            cursor.execute("""
                SELECT (
                    SELECT COUNT(*) + 1
                    FROM wallets w2
                    WHERE w2.rank_score > w1.rank_score AND w2.is_active = 1
                ) as rank
                FROM wallets w1
                WHERE w1.address = ?
            """, (wallet_address.lower(),))

            row = cursor.fetchone()
            conn.close()

            return row[0] if row else 999
        except:
            return 999

    def get_statistics(self) -> Dict[str, Any]:
        """Get queue statistics."""
        now = datetime.now()

        total = len(self.queue)
        expired = sum(
            1 for q in self.queue
            if (now - q.queued_at).total_seconds() > self.signal_expiration_seconds
        )
        max_retries_reached = sum(
            1 for q in self.queue
            if q.retry_count >= self.max_retries
        )

        return {
            'total_queued': total,
            'expired': expired,
            'max_retries_reached': max_retries_reached,
            'retryable': total - expired - max_retries_reached
        }


# ============================================================================
# LEVERAGE CAPPER
# ============================================================================

def cap_extreme_leverage(
    trader_leverage: int,
    max_leverage: int = 25
) -> Tuple[int, bool]:
    """
    Cap extreme leverage and return warning flag.

    Args:
        trader_leverage: Trader's detected leverage
        max_leverage: Our maximum allowed leverage

    Returns:
        (capped_leverage, warning_flag)
    """
    if trader_leverage > max_leverage:
        logger.warning(
            f"Trader using extreme leverage ({trader_leverage}x), "
            f"capping at {max_leverage}x"
        )
        return max_leverage, True

    return trader_leverage, False


def adjust_position_for_leverage_cap(
    position_size: float,
    original_leverage: int,
    capped_leverage: int
) -> float:
    """
    Adjust position size to maintain risk profile when leverage is capped.

    If trader uses 100x but we cap at 25x, we should reduce position size
    to maintain similar notional exposure.

    Formula:
        adjusted_size = original_size × (capped_leverage / original_leverage)

    Example:
        Trader: $100 @ 100x = $10,000 notional
        Us (capped): $25 @ 25x = $625 notional
        Adjustment: $25 × (25/100) = $6.25 @ 25x = $156.25 notional

    Args:
        position_size: Original position size
        original_leverage: Trader's leverage
        capped_leverage: Our capped leverage

    Returns:
        Adjusted position size
    """
    if original_leverage <= capped_leverage:
        return position_size

    # Reduce position size proportionally
    adjustment_ratio = capped_leverage / original_leverage
    adjusted_size = position_size * adjustment_ratio

    logger.info(
        f"Adjusted position size for leverage cap: "
        f"${position_size:.2f} → ${adjusted_size:.2f} "
        f"(ratio: {adjustment_ratio:.2f})"
    )

    return adjusted_size
