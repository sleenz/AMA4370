# Position Dataclass Design

Complete specification for the Position dataclass used in signal processing and trade execution.

## Overview

The Position dataclass is the **central data structure** that bridges signal processing and trade execution. It contains:
- All information needed to execute a trade
- Risk management parameters
- Tracking for the complete position lifecycle
- Audit trail for analysis

---

## Complete Position Dataclass

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

@dataclass
class Position:
    """
    Complete position specification ready for execution.

    This dataclass represents a fully-calculated, risk-checked position
    that is ready to be executed on an exchange. It contains all the
    information needed for:
        - Trade execution
        - Risk management
        - Position tracking
        - Performance analysis
        - Audit trail

    Lifecycle:
        1. Created by SignalProcessor after passing all filters
        2. Saved to database with status='pending'
        3. Executed by PositionExecutor → status='filled'
        4. Monitored by PositionMonitor
        5. Closed manually or via stop loss/take profit → status='closed'
    """

    # ========================================================================
    # IDENTIFIERS
    # ========================================================================

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique position ID (UUID)"""

    signal_id: str = ""
    """Reference to original TradeSignal that triggered this position"""

    wallet_address: str = ""
    """Source wallet address being copied (lowercase)"""

    created_at: datetime = field(default_factory=datetime.now)
    """Timestamp when position was calculated"""

    # ========================================================================
    # TRADING PARAMETERS
    # ========================================================================

    exchange: str = ""
    """Exchange to execute on: 'binance' or 'bybit'"""

    pair: str = ""
    """Trading pair: 'ETHUSDT', 'BTCUSDT', etc."""

    side: str = ""
    """Order side: 'BUY' or 'SELL' (or 'LONG'/'SHORT' for futures)"""

    # ========================================================================
    # POSITION SIZING
    # ========================================================================

    size_usd: float = 0.0
    """
    Position size in USD before leverage.
    This is the capital we're allocating to this trade.

    Example: $250 position → with 20x leverage → $5,000 notional
    """

    size_base: float = 0.0
    """
    Position size in base currency (BTC, ETH, etc.)

    Calculated as: size_usd / entry_price

    Example: $250 / $3400 per ETH = 0.0735 ETH
    """

    leverage: int = 1
    """
    Leverage multiplier (1-25x)

    Determined by:
        min(source_leverage, max_leverage_config, exchange_max_leverage)

    Example: Trader uses 20x, config allows 25x, exchange allows 50x → use 20x
    """

    notional_usd: float = 0.0
    """
    Total notional value (size_usd × leverage)

    This is the total exposure.

    Example: $250 × 20x = $5,000 notional
    """

    # ========================================================================
    # RISK MANAGEMENT
    # ========================================================================

    stop_loss_price: float = 0.0
    """
    Stop loss price level

    For LONG: below entry price
    For SHORT: above entry price

    Calculated to limit loss to stop_loss_usd

    Example:
        Entry: $3400
        Stop loss USD: $100
        Size: $250
        Loss % = $100 / $250 = 40%
        Stop price = $3400 × (1 - 0.40) = $2040
    """

    stop_loss_usd: float = 0.0
    """
    Maximum loss in USD

    Formula: total_capital × trade_multiplier × wallet_allocation_pct

    Example:
        Capital: $100,000
        Multiplier: 0.5
        Wallet allocation: 10%
        Stop loss = $100k × 0.5 × 0.10 = $5,000
    """

    take_profit_price: Optional[float] = None
    """
    Take profit price level (optional)

    For LONG: above entry price
    For SHORT: below entry price

    Can be set based on:
        - Technical analysis
        - Risk/reward ratio (e.g., 2:1)
        - Trailing stop logic
    """

    # ========================================================================
    # ALLOCATION DETAILS
    # ========================================================================

    wallet_allocation_pct: float = 0.0
    """
    Portfolio allocation for source wallet based on rank

    Allocation schedule:
        Rank 1: 10%
        Rank 2: 8%
        Rank 3: 6%
        Rank 4-5: 5%
        Rank 6-10: 3%
        Rank 11-20: 2%

    Example: Wallet rank 1 → 10%
    """

    trade_multiplier: float = 0.5
    """
    Our 1/2 rule multiplier

    We take 1/2 of the calculated position to be conservative.

    Example: Calculated $500 → multiply by 0.5 → execute $250
    """

    trader_position_pct: float = 0.0
    """
    Estimated % of trader's capital in this trade

    Calculated as: source_amount_usd / estimated_trader_balance

    Example:
        Trader trades $50k
        Estimated balance: $1M
        Position %: 50k / 1M = 5%
    """

    capital_at_risk_pct: float = 0.0
    """
    % of our total capital at risk in this position

    Calculated as: stop_loss_usd / total_capital

    Example: $5,000 stop loss / $100k capital = 5%

    Risk limit: Typically should be < 5% per position
    """

    # ========================================================================
    # SOURCE TRADE INFO (For Audit Trail)
    # ========================================================================

    source_token: str = ""
    """Original DEX token address (e.g., 0xc02aaa...)"""

    source_token_symbol: str = ""
    """Original token symbol (e.g., 'WETH', 'WBTC')"""

    source_amount_usd: float = 0.0
    """Trader's original trade size in USD"""

    source_leverage: int = 1
    """Trader's detected leverage multiplier"""

    # ========================================================================
    # EXECUTION DETAILS
    # ========================================================================

    entry_price: float = 0.0
    """
    Expected entry price

    For BUY: Use ask price (we're buying from sellers)
    For SELL: Use bid price (we're selling to buyers)

    This is used for position sizing calculations.
    """

    slippage_tolerance: float = 0.5
    """
    Maximum acceptable slippage in %

    Example: 0.5% means we'll accept execution within 0.5% of entry_price

    If actual execution price exceeds this, order is rejected.
    """

    # ========================================================================
    # STATUS TRACKING
    # ========================================================================

    status: str = 'pending'
    """
    Position lifecycle status

    States:
        'pending': Position created, waiting for execution
        'filled': Order executed successfully
        'rejected': Order rejected by exchange or risk checks
        'closed': Position closed (manual, stop loss, or take profit)
        'cancelled': Order cancelled before fill
    """

    filled_at: Optional[datetime] = None
    """Timestamp when order was filled"""

    closed_at: Optional[datetime] = None
    """Timestamp when position was closed"""

    actual_entry_price: Optional[float] = None
    """
    Actual execution price (may differ from expected)

    Used to calculate:
        - Actual slippage
        - True position size
        - Adjusted stop loss levels
    """

    actual_size: Optional[float] = None
    """
    Actual filled size (may be partial fill)

    If actual_size < size_base:
        - Partial fill occurred
        - Adjust stop loss proportionally
    """

    pnl_usd: Optional[float] = None
    """
    Realized profit/loss in USD (when position closed)

    Calculated as:
        For LONG: (exit_price - entry_price) × size_base × leverage
        For SHORT: (entry_price - exit_price) × size_base × leverage
    """

    # ========================================================================
    # FILTER RESULTS (Audit Trail)
    # ========================================================================

    passed_token_check: bool = False
    """Did token pass mapping check (DEX → CEX)?"""

    passed_liquidity_check: bool = False
    """Did pair pass liquidity check (spread, depth)?"""

    passed_risk_check: bool = False
    """Did position pass risk limit checks?"""

    rejection_reason: Optional[str] = None
    """
    Reason for rejection if any filter failed

    Examples:
        'token_not_mapped'
        'insufficient_liquidity'
        'risk_limits_exceeded: max positions'
        'risk_limits_exceeded: max capital at risk'
    """

    # ========================================================================
    # CALCULATED PROPERTIES
    # ========================================================================

    @property
    def risk_reward_ratio(self) -> Optional[float]:
        """
        Calculate risk/reward ratio if take profit is set

        Returns:
            float: Ratio (e.g., 2.0 means 2:1 reward:risk)
        """
        if not self.take_profit_price or self.entry_price == 0:
            return None

        if self.side == 'BUY':
            risk = self.entry_price - self.stop_loss_price
            reward = self.take_profit_price - self.entry_price
        else:
            risk = self.stop_loss_price - self.entry_price
            reward = self.entry_price - self.take_profit_price

        if risk <= 0:
            return None

        return reward / risk

    @property
    def slippage_pct(self) -> Optional[float]:
        """
        Calculate actual slippage percentage

        Returns:
            float: Slippage % (positive = worse execution)
        """
        if not self.actual_entry_price or self.entry_price == 0:
            return None

        if self.side == 'BUY':
            # For buys, higher price = worse
            slippage = ((self.actual_entry_price - self.entry_price) / self.entry_price) * 100
        else:
            # For sells, lower price = worse
            slippage = ((self.entry_price - self.actual_entry_price) / self.entry_price) * 100

        return slippage

    @property
    def is_filled(self) -> bool:
        """Check if position is filled"""
        return self.status == 'filled'

    @property
    def is_open(self) -> bool:
        """Check if position is open (pending or filled)"""
        return self.status in ('pending', 'filled')

    @property
    def is_closed(self) -> bool:
        """Check if position is closed"""
        return self.status == 'closed'

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage"""
        return {
            'id': self.id,
            'signal_id': self.signal_id,
            'wallet_address': self.wallet_address,
            'created_at': self.created_at.isoformat(),
            'exchange': self.exchange,
            'pair': self.pair,
            'side': self.side,
            'size_usd': self.size_usd,
            'size_base': self.size_base,
            'leverage': self.leverage,
            'notional_usd': self.notional_usd,
            'stop_loss_price': self.stop_loss_price,
            'stop_loss_usd': self.stop_loss_usd,
            'take_profit_price': self.take_profit_price,
            'wallet_allocation_pct': self.wallet_allocation_pct,
            'trade_multiplier': self.trade_multiplier,
            'trader_position_pct': self.trader_position_pct,
            'capital_at_risk_pct': self.capital_at_risk_pct,
            'source_token': self.source_token,
            'source_token_symbol': self.source_token_symbol,
            'source_amount_usd': self.source_amount_usd,
            'source_leverage': self.source_leverage,
            'entry_price': self.entry_price,
            'slippage_tolerance': self.slippage_tolerance,
            'status': self.status,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'actual_entry_price': self.actual_entry_price,
            'actual_size': self.actual_size,
            'pnl_usd': self.pnl_usd,
            'passed_token_check': self.passed_token_check,
            'passed_liquidity_check': self.passed_liquidity_check,
            'passed_risk_check': self.passed_risk_check,
            'rejection_reason': self.rejection_reason
        }

    def __repr__(self) -> str:
        """Human-readable representation"""
        return (
            f"Position(id={self.id[:8]}..., "
            f"pair={self.pair}, side={self.side}, "
            f"size=${self.size_usd:.2f}, leverage={self.leverage}x, "
            f"notional=${self.notional_usd:.2f}, "
            f"status={self.status})"
        )
```

---

## Usage Examples

### Example 1: Create Position from Signal

```python
# Input: TradeSignal
signal = TradeSignal(
    id='sig_123',
    wallet_address='0xabc...',
    token_address='0xc02aaa...',  # WETH
    token_symbol='WETH',
    action='BUY',
    amount_usd=50000,  # Trader bought $50k of ETH
    leverage=5
)

# Process signal
processor = SignalProcessor(config_path='config.json')
position = processor.process_signal(signal)

if position:
    print(position)
    # Output: Position(id=a1b2c3d4..., pair=ETHUSDT, side=BUY,
    #         size=$250.00, leverage=5x, notional=$1250.00, status=pending)

    # Access fields
    print(f"Entry price: ${position.entry_price}")
    print(f"Stop loss: ${position.stop_loss_price} (max loss: ${position.stop_loss_usd})")
    print(f"Capital at risk: {position.capital_at_risk_pct}%")
```

### Example 2: Position Lifecycle Tracking

```python
# 1. Create position
position = Position(
    signal_id='sig_123',
    wallet_address='0xabc...',
    exchange='binance',
    pair='ETHUSDT',
    side='BUY',
    size_usd=250,
    leverage=5,
    entry_price=3400,
    stop_loss_price=3000,
    status='pending'
)

# 2. Execute trade
position.status = 'filled'
position.filled_at = datetime.now()
position.actual_entry_price = 3405  # 0.15% slippage
position.actual_size = 0.0734  # Slightly less due to slippage

# 3. Check slippage
print(f"Slippage: {position.slippage_pct:.2f}%")  # 0.15%

# 4. Monitor position
# ... position runs ...

# 5. Close position
position.status = 'closed'
position.closed_at = datetime.now()
exit_price = 3500
position.pnl_usd = (exit_price - position.actual_entry_price) * position.actual_size * position.leverage
print(f"PnL: ${position.pnl_usd:.2f}")  # $34.93
```

### Example 3: Risk Analysis

```python
# Analyze position risk
def analyze_risk(position: Position) -> None:
    print(f"\n{'='*60}")
    print(f"RISK ANALYSIS: {position.pair} {position.side}")
    print(f"{'='*60}")

    print(f"\nPosition Size:")
    print(f"  Capital allocated: ${position.size_usd:,.2f}")
    print(f"  Leverage: {position.leverage}x")
    print(f"  Notional exposure: ${position.notional_usd:,.2f}")

    print(f"\nRisk Parameters:")
    print(f"  Entry: ${position.entry_price:,.2f}")
    print(f"  Stop loss: ${position.stop_loss_price:,.2f}")
    print(f"  Max loss: ${position.stop_loss_usd:,.2f}")
    print(f"  Capital at risk: {position.capital_at_risk_pct:.2f}%")

    if position.take_profit_price:
        print(f"  Take profit: ${position.take_profit_price:,.2f}")
        print(f"  Risk/Reward: {position.risk_reward_ratio:.2f}:1")

    print(f"\nSource Trade:")
    print(f"  Wallet: {position.wallet_address[:10]}...")
    print(f"  Token: {position.source_token_symbol}")
    print(f"  Trader size: ${position.source_amount_usd:,.2f}")
    print(f"  Trader leverage: {position.source_leverage}x")
    print(f"  Wallet allocation: {position.wallet_allocation_pct}%")
```

---

## Database Schema

```sql
CREATE TABLE positions (
    -- Identifiers
    id TEXT PRIMARY KEY,
    signal_id TEXT,
    wallet_address TEXT,
    created_at TIMESTAMP NOT NULL,

    -- Trading parameters
    exchange TEXT NOT NULL,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,

    -- Position sizing
    size_usd REAL NOT NULL,
    size_base REAL NOT NULL,
    leverage INTEGER NOT NULL,
    notional_usd REAL NOT NULL,

    -- Risk management
    stop_loss_price REAL NOT NULL,
    stop_loss_usd REAL NOT NULL,
    take_profit_price REAL,

    -- Allocation details
    wallet_allocation_pct REAL NOT NULL,
    trade_multiplier REAL NOT NULL,
    trader_position_pct REAL NOT NULL,
    capital_at_risk_pct REAL NOT NULL,

    -- Source trade info
    source_token TEXT NOT NULL,
    source_token_symbol TEXT NOT NULL,
    source_amount_usd REAL NOT NULL,
    source_leverage INTEGER NOT NULL,

    -- Execution details
    entry_price REAL NOT NULL,
    slippage_tolerance REAL NOT NULL,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending',
    filled_at TIMESTAMP,
    closed_at TIMESTAMP,
    actual_entry_price REAL,
    actual_size REAL,
    pnl_usd REAL,

    -- Filter results
    passed_token_check BOOLEAN NOT NULL DEFAULT 0,
    passed_liquidity_check BOOLEAN NOT NULL DEFAULT 0,
    passed_risk_check BOOLEAN NOT NULL DEFAULT 0,
    rejection_reason TEXT,

    -- Foreign keys
    FOREIGN KEY (wallet_address) REFERENCES wallets(address) ON DELETE CASCADE,
    FOREIGN KEY (signal_id) REFERENCES trade_signals(id)
);

-- Indexes for fast queries
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_pair ON positions(pair, status);
CREATE INDEX idx_positions_wallet ON positions(wallet_address, status);
CREATE INDEX idx_positions_created ON positions(created_at DESC);
```

---

## Validation Rules

### Required Fields (Cannot be empty/zero)

- `id`: Must be valid UUID
- `wallet_address`: Must be valid Ethereum address
- `exchange`: Must be 'binance' or 'bybit'
- `pair`: Must be valid trading pair (e.g., 'ETHUSDT')
- `side`: Must be 'BUY' or 'SELL'
- `size_usd`: Must be > 0
- `size_base`: Must be > 0
- `leverage`: Must be 1-25
- `entry_price`: Must be > 0

### Business Logic Validation

```python
def validate_position(position: Position) -> List[str]:
    """
    Validate position meets all requirements.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Size validation
    if position.size_usd <= 0:
        errors.append("size_usd must be positive")

    if position.size_base <= 0:
        errors.append("size_base must be positive")

    # Leverage validation
    if not (1 <= position.leverage <= 25):
        errors.append("leverage must be between 1 and 25")

    # Notional validation
    expected_notional = position.size_usd * position.leverage
    if abs(position.notional_usd - expected_notional) > 0.01:
        errors.append(f"notional_usd mismatch: expected {expected_notional}, got {position.notional_usd}")

    # Stop loss validation
    if position.side == 'BUY':
        if position.stop_loss_price >= position.entry_price:
            errors.append("For LONG: stop loss must be below entry price")
    else:
        if position.stop_loss_price <= position.entry_price:
            errors.append("For SHORT: stop loss must be above entry price")

    # Risk validation
    if position.capital_at_risk_pct > 5.0:
        errors.append(f"Capital at risk too high: {position.capital_at_risk_pct}% > 5%")

    return errors
```

---

## Summary

The Position dataclass is designed to be:

✅ **Comprehensive**: Contains all information needed for execution and analysis
✅ **Traceable**: Full audit trail from signal to closure
✅ **Type-safe**: Uses dataclass with clear types
✅ **Extensible**: Easy to add new fields
✅ **Database-friendly**: Simple to_dict() conversion
✅ **Self-documenting**: Extensive comments and docstrings
✅ **Validated**: Clear validation rules
✅ **Analyzable**: Calculated properties for metrics

This design ensures that every position has complete information for:
- Trade execution
- Risk management
- Performance tracking
- Compliance and audit
- Strategy analysis
