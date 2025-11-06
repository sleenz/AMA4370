# Signal Aggregation Algorithm Design

Comprehensive design for aggregating correlated signals when multiple wallets buy the same token simultaneously.

## Problem Statement

When multiple top wallets buy the same token within a short time window:
- **Naive approach**: Open 3 separate positions → 3x capital allocation
- **Risk**: Over-concentration in single asset
- **Better approach**: Aggregate signals into single position with adjusted size

## Design Goals

1. **Prevent over-concentration**: Don't linearly scale position with signal count
2. **Maintain risk profile**: Keep total capital at risk within limits
3. **Respect wallet weights**: Higher-ranked wallets should have more influence
4. **Track attribution**: Know which wallets contributed to aggregated position
5. **Handle timing**: Define "simultaneous" time window
6. **Support PnL distribution**: Attribute results back to source wallets

---

## Algorithm Overview

```
Input: New signal arrives
↓
Step 1: Check for recent signals (within time window)
↓
Step 2: Group signals by target pair (ETHUSDT, BTCUSDT, etc.)
↓
Step 3: If multiple signals for same pair:
  ├─ Calculate individual position sizes
  ├─ Apply aggregation formula (dampened sum)
  ├─ Create aggregated position
  └─ Link to all source signals
↓
Step 4: Execute single aggregated position
↓
Output: One position tracking multiple signals
```

---

## Detailed Design

### Step 1: Time Window Definition

**Concept**: Signals are "simultaneous" if they arrive within a time window.

```python
TIME_WINDOW_SECONDS = 120  # 2 minutes

def is_simultaneous(signal_a, signal_b):
    """
    Check if two signals are within aggregation time window.

    Returns:
        bool: True if signals should be aggregated
    """
    time_diff = abs((signal_a.created_at - signal_b.created_at).total_seconds())
    return time_diff <= TIME_WINDOW_SECONDS
```

**Rationale**:
- 2 minutes allows for DEX transaction confirmation delays
- Catches coordinated smart money moves
- Not so wide that unrelated trades get lumped together

---

### Step 2: Signal Grouping

**Concept**: Group pending signals by target trading pair.

```python
class SignalAggregator:
    def __init__(self):
        self.pending_signals: Dict[str, List[Signal]] = {}
        # Key: cex_pair (e.g., 'ETHUSDT')
        # Value: List of signals targeting that pair

    def add_signal(self, signal: TradeSignal, token_mapping: TokenMapping):
        """Add signal to pending queue, grouped by pair."""
        pair = token_mapping.cex_pair

        if pair not in self.pending_signals:
            self.pending_signals[pair] = []

        self.pending_signals[pair].append({
            'signal': signal,
            'mapping': token_mapping,
            'added_at': datetime.now()
        })

        # Clean up old signals (>5 minutes)
        self._cleanup_expired_signals(pair)

    def _cleanup_expired_signals(self, pair: str):
        """Remove signals older than 5 minutes."""
        cutoff = datetime.now() - timedelta(minutes=5)
        self.pending_signals[pair] = [
            s for s in self.pending_signals[pair]
            if s['added_at'] > cutoff
        ]
```

---

### Step 3: Aggregation Formula

**Concept**: Calculate aggregated position size using dampened sum.

#### Option A: Square Root Dampening (Conservative)

```python
def aggregate_position_sizes_sqrt(individual_sizes: List[float]) -> float:
    """
    Aggregate using square root dampening.

    Formula: total = sum(sizes) * sqrt(count) / count

    Examples:
        1 signal: $250 × sqrt(1) / 1 = $250 (1.0x)
        2 signals: $500 × sqrt(2) / 2 = $354 (1.41x)
        3 signals: $750 × sqrt(3) / 3 = $433 (1.73x)
        4 signals: $1000 × sqrt(4) / 4 = $500 (2.0x)

    Rationale: Increases with more signals, but sub-linearly
    """
    count = len(individual_sizes)
    total = sum(individual_sizes)
    dampening_factor = math.sqrt(count) / count
    return total * dampening_factor
```

#### Option B: Fixed Multiplier (As Specified)

```python
def aggregate_position_sizes_fixed(individual_sizes: List[float]) -> float:
    """
    Aggregate using fixed 1.5x multiplier.

    Formula: total = average(sizes) × 1.5

    Examples:
        1 signal: $250 × 1.0 = $250
        2 signals: avg($250, $200) × 1.5 = $338
        3 signals: avg($250, $200, $150) × 1.5 = $300

    Rationale: Simple, predictable, prevents over-concentration
    """
    avg_size = sum(individual_sizes) / len(individual_sizes)
    return avg_size * 1.5 if len(individual_sizes) > 1 else avg_size
```

#### Option C: Weighted by Rank (Recommended)

```python
def aggregate_position_sizes_weighted(
    signals_with_sizes: List[Tuple[TradeSignal, float, float]]
) -> float:
    """
    Aggregate using wallet rank weights.

    Args:
        signals_with_sizes: List of (signal, size, wallet_weight)

    Formula:
        base = sum(size × weight)
        multiplier = 1.0 + (count - 1) × 0.3  # 30% boost per additional signal
        total = base × multiplier

    Examples:
        1 signal (rank 1, weight=1.0): $250 × 1.0 = $250
        2 signals (rank 1 + rank 5, weights=1.0, 0.5):
            base = ($250 × 1.0) + ($125 × 0.5) = $312.50
            multiplier = 1.0 + (2-1) × 0.3 = 1.3
            total = $312.50 × 1.3 = $406.25
        3 signals (rank 1, 3, 5, weights=1.0, 0.6, 0.5):
            base = ($250 × 1.0) + ($150 × 0.6) + ($125 × 0.5) = $402.50
            multiplier = 1.0 + (3-1) × 0.3 = 1.6
            total = $402.50 × 1.6 = $644

    Rationale:
        - Respects wallet hierarchy
        - Moderate scaling (not linear, not sqrt)
        - 30% boost per signal rewards correlated moves
    """
    if len(signals_with_sizes) == 1:
        return signals_with_sizes[0][1]  # Just return the single size

    # Calculate weighted base
    base_size = sum(size * weight for _, size, weight in signals_with_sizes)

    # Apply boost for multiple signals
    signal_count = len(signals_with_sizes)
    multiplier = 1.0 + (signal_count - 1) * 0.3

    # Cap total multiplier at 2.0x (prevents excessive scaling)
    multiplier = min(multiplier, 2.0)

    return base_size * multiplier
```

**Recommended**: Option C (Weighted by Rank) provides best balance.

---

### Step 4: Wallet Weight Calculation

```python
def get_wallet_weight(rank: int) -> float:
    """
    Get aggregation weight for wallet based on rank.

    Weight schedule:
        Rank 1: 1.0 (full weight)
        Rank 2: 0.8
        Rank 3: 0.6
        Rank 4-5: 0.5
        Rank 6-10: 0.3
        Rank 11+: 0.2

    Rationale:
        - Top wallets get higher influence in aggregation
        - Prevents low-ranked wallets from skewing position size
        - Mirrors the allocation percentages
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
```

---

### Step 5: Aggregated Position Creation

```python
@dataclass
class AggregatedPosition(Position):
    """
    Extended Position with aggregation tracking.

    Additional fields:
        source_signals: List[str]  # Signal IDs
        source_wallets: List[str]  # Wallet addresses
        aggregation_count: int  # Number of signals aggregated
        aggregation_multiplier: float  # Applied multiplier
        wallet_contributions: Dict[str, float]  # wallet → contribution %
    """
    source_signals: List[str] = field(default_factory=list)
    source_wallets: List[str] = field(default_factory=list)
    aggregation_count: int = 1
    aggregation_multiplier: float = 1.0
    wallet_contributions: Dict[str, float] = field(default_factory=dict)


def create_aggregated_position(
    signals: List[TradeSignal],
    individual_positions: List[Position],
    aggregated_size: float,
    token_mapping: TokenMapping
) -> AggregatedPosition:
    """
    Create aggregated position from multiple signals.

    Args:
        signals: List of original signals
        individual_positions: List of individually-calculated positions
        aggregated_size: Final aggregated position size
        token_mapping: Token mapping for the pair

    Returns:
        AggregatedPosition with tracking fields
    """
    # Use first signal as base
    base_signal = signals[0]
    base_position = individual_positions[0]

    # Calculate contributions
    total_individual = sum(p.size_usd for p in individual_positions)
    wallet_contributions = {
        p.wallet_address: (p.size_usd / total_individual) * 100
        for p in individual_positions
    }

    # Calculate average leverage (weighted by contribution)
    avg_leverage = sum(
        p.leverage * (p.size_usd / total_individual)
        for p in individual_positions
    )
    avg_leverage = int(round(avg_leverage))

    # Calculate aggregated stop loss
    # Use weighted average of individual stop losses
    aggregated_stop_loss = sum(
        p.stop_loss_usd * (p.size_usd / total_individual)
        for p in individual_positions
    )

    # Create aggregated position
    position = AggregatedPosition(
        signal_id=base_signal.id,  # Reference first signal
        wallet_address=base_position.wallet_address,  # First wallet

        # Trading parameters
        exchange=token_mapping.exchange,
        pair=token_mapping.cex_pair,
        side=base_signal.action,

        # Aggregated sizing
        size_usd=aggregated_size,
        size_base=aggregated_size / base_position.entry_price,
        leverage=avg_leverage,
        notional_usd=aggregated_size * avg_leverage,

        # Risk management
        stop_loss_price=base_position.stop_loss_price,
        stop_loss_usd=aggregated_stop_loss,

        # Aggregation tracking
        source_signals=[s.id for s in signals],
        source_wallets=[s.wallet_address for s in signals],
        aggregation_count=len(signals),
        aggregation_multiplier=aggregated_size / total_individual,
        wallet_contributions=wallet_contributions,

        # Other fields copied from base
        ...
    )

    return position
```

---

### Step 6: Complete Aggregation Flow

```python
class SignalAggregator:
    def process_signal_with_aggregation(
        self,
        signal: TradeSignal,
        token_mapping: TokenMapping
    ) -> Optional[Position]:
        """
        Process signal with aggregation logic.

        Flow:
            1. Calculate individual position for this signal
            2. Add to pending queue
            3. Check if we have multiple signals for same pair
            4. If yes: aggregate and create combined position
            5. If no: return individual position

        Returns:
            Position (may be individual or aggregated)
        """
        # Step 1: Calculate individual position
        individual_position = self.signal_processor._calculate_position(
            signal, token_mapping
        )

        # Step 2: Add to pending queue
        pair = token_mapping.cex_pair
        self.add_signal(signal, token_mapping)

        # Step 3: Get all pending signals for this pair
        pending = self.pending_signals.get(pair, [])

        # Step 4: Check if aggregation needed
        if len(pending) < 2:
            # Single signal, return individual position
            return individual_position

        # Step 5: Aggregate signals
        signals_in_window = [
            p for p in pending
            if self.is_simultaneous(p['signal'], signal)
        ]

        if len(signals_in_window) < 2:
            # Only one in time window
            return individual_position

        # Step 6: Calculate aggregated position
        logger.info(f"Aggregating {len(signals_in_window)} signals for {pair}")

        # Calculate individual positions for all signals
        individual_positions = []
        for s in signals_in_window:
            pos = self.signal_processor._calculate_position(
                s['signal'], s['mapping']
            )
            individual_positions.append(pos)

        # Get wallet weights
        signals_with_weights = []
        for sig, pos in zip(signals_in_window, individual_positions):
            rank = self._get_wallet_rank(sig['signal'].wallet_address)
            weight = self.get_wallet_weight(rank)
            signals_with_weights.append((sig['signal'], pos.size_usd, weight))

        # Aggregate
        aggregated_size = self.aggregate_position_sizes_weighted(signals_with_weights)

        # Create aggregated position
        aggregated_position = self.create_aggregated_position(
            [s['signal'] for s in signals_in_window],
            individual_positions,
            aggregated_size,
            token_mapping
        )

        # Clear aggregated signals from queue
        self.pending_signals[pair] = [
            p for p in pending
            if p not in signals_in_window
        ]

        logger.info(
            f"Aggregated position: ${aggregated_size:.2f} "
            f"(multiplier: {aggregated_position.aggregation_multiplier:.2f}x)"
        )

        return aggregated_position
```

---

## Examples

### Example 1: Two Top Wallets Buy ETH

**Scenario**:
- Wallet #1 (rank 1): Buys $50k ETH @ 5x leverage
- Wallet #5 (rank 5): Buys $30k ETH @ 3x leverage
- Both signals arrive within 60 seconds

**Individual Calculations**:
```
Wallet #1:
  Allocation: 10%
  Position: $100k × 0.10 × 0.5 × 0.05 = $250
  Weight: 1.0

Wallet #5:
  Allocation: 5%
  Position: $100k × 0.05 × 0.5 × 0.03 = $75
  Weight: 0.5
```

**Aggregation**:
```
Base: ($250 × 1.0) + ($75 × 0.5) = $287.50
Multiplier: 1.0 + (2-1) × 0.3 = 1.3
Aggregated: $287.50 × 1.3 = $373.75

Avg Leverage: (5 × $250 + 3 × $75) / $325 = 4.5x
```

**Result**: Single position of $373.75 @ 4.5x leverage instead of two positions totaling $325.

---

### Example 2: Three Wallets Buy BTC

**Scenario**:
- Wallet #1 (rank 1): $100k BTC @ 10x
- Wallet #3 (rank 3): $75k BTC @ 8x
- Wallet #8 (rank 8): $40k BTC @ 5x

**Individual Calculations**:
```
Wallet #1: $100k × 0.10 × 0.5 × 0.10 = $500 (weight: 1.0)
Wallet #3: $100k × 0.06 × 0.5 × 0.075 = $225 (weight: 0.6)
Wallet #8: $100k × 0.03 × 0.5 × 0.04 = $60 (weight: 0.3)
```

**Aggregation**:
```
Base: ($500 × 1.0) + ($225 × 0.6) + ($60 × 0.3) = $653
Multiplier: 1.0 + (3-1) × 0.3 = 1.6
Aggregated: $653 × 1.6 = $1,044.80

Avg Leverage: (10×500 + 8×225 + 5×60) / 785 = 8.9x
```

**Result**: Single position of $1,044.80 @ 9x leverage

**Risk Check**: Must verify this passes risk limits!
- Position size: $1,044.80 / $100k = 1.05% ✓ (< 5%)
- Notional: $1,044.80 × 9 = $9,403 ✓
- Stop loss: Need to calculate weighted average

---

## PnL Attribution

When aggregated position closes, distribute PnL back to source wallets:

```python
def distribute_pnl(
    aggregated_position: AggregatedPosition,
    total_pnl: float
) -> Dict[str, float]:
    """
    Distribute PnL to source wallets based on contribution.

    Args:
        aggregated_position: Closed aggregated position
        total_pnl: Total realized PnL

    Returns:
        Dict mapping wallet_address → pnl_share
    """
    pnl_distribution = {}

    for wallet, contribution_pct in aggregated_position.wallet_contributions.items():
        pnl_share = total_pnl * (contribution_pct / 100.0)
        pnl_distribution[wallet] = pnl_share

    return pnl_distribution
```

---

## Database Schema Updates

```sql
-- Add aggregation fields to positions table
ALTER TABLE positions ADD COLUMN source_signals TEXT;  -- JSON array
ALTER TABLE positions ADD COLUMN source_wallets TEXT;  -- JSON array
ALTER TABLE positions ADD COLUMN aggregation_count INTEGER DEFAULT 1;
ALTER TABLE positions ADD COLUMN aggregation_multiplier REAL DEFAULT 1.0;
ALTER TABLE positions ADD COLUMN wallet_contributions TEXT;  -- JSON object

-- Create aggregation tracking table
CREATE TABLE signal_aggregations (
    id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    pair TEXT NOT NULL,
    aggregation_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,

    FOREIGN KEY (position_id) REFERENCES positions(id)
);

-- Track individual signal contributions
CREATE TABLE aggregation_contributions (
    id TEXT PRIMARY KEY,
    aggregation_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    wallet_address TEXT NOT NULL,
    contribution_pct REAL NOT NULL,
    individual_size_usd REAL NOT NULL,

    FOREIGN KEY (aggregation_id) REFERENCES signal_aggregations(id),
    FOREIGN KEY (signal_id) REFERENCES trade_signals(id)
);
```

---

## Configuration

Add to `config.json`:

```json
{
  "signal_aggregation": {
    "enabled": true,
    "time_window_seconds": 120,
    "max_signals_per_aggregation": 5,
    "aggregation_method": "weighted",  // "weighted", "sqrt", "fixed"
    "boost_per_signal": 0.3,  // 30% boost per additional signal
    "max_multiplier": 2.0  // Cap at 2x total
  }
}
```

---

## Testing Strategy

### Test Case 1: Two Signals Same Time
```python
# Input: 2 signals for ETHUSDT within 30 seconds
# Expected: Single aggregated position, ~1.3x size
```

### Test Case 2: Three Signals Staggered
```python
# Input: 3 signals spread over 5 minutes
# Expected: First two aggregate, third separate
```

### Test Case 3: Different Pairs
```python
# Input: 2 signals for ETHUSDT, 1 for BTCUSDT
# Expected: ETHUSDT aggregated, BTCUSDT separate
```

### Test Case 4: Risk Limit Exceeded
```python
# Input: Aggregation would exceed 5% position limit
# Expected: Aggregation reduced or rejected
```

---

## Advantages

✅ **Prevents over-concentration**: Dampened scaling protects against correlation risk
✅ **Respects hierarchy**: Top wallets have more influence
✅ **Tracks attribution**: Can analyze which wallets contribute to performance
✅ **Reduces fees**: One position instead of multiple
✅ **Simplifies management**: Easier to monitor and exit

## Disadvantages

⚠️ **Complexity**: More logic to maintain
⚠️ **Timing sensitivity**: Requires precise time window tuning
⚠️ **Attribution questions**: How to handle if one wallet typically fails?
⚠️ **Risk calculation**: Aggregated stop loss needs careful handling

---

## Recommendation

**Implement Option C (Weighted by Rank)** with:
- 2-minute time window
- 30% boost per additional signal
- 2.0x maximum multiplier
- Full tracking for PnL attribution
