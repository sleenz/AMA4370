# Wallet Ranking System

## Overview

The system ranks wallets based on **real on-chain trading performance** by analyzing historical DEX swap transactions. It identifies the best traders to copy by calculating 5 key metrics and combining them into a single rank score.

---

## Step-by-Step Process

```
1. Discover Wallets     → wallet_discovery.py
2. Fetch Transactions   → Etherscan API (90 days of history)
3. Parse DEX Swaps      → dex_parser.py (26+ protocols)
4. Match Buy/Sell Pairs → FIFO matching algorithm
5. Calculate Metrics    → 5 performance indicators
6. Apply Filters        → Minimum quality thresholds
7. Calculate Score      → Weighted formula
8. Allocate Capital     → Top wallets get higher %
```

---

## Performance Metrics (The 5 Pillars)

### 1. Win Rate (25% weight)
**What it measures:** Percentage of profitable trades

**Formula:**
```
Win Rate = (Profitable Closed Trades / Total Closed Trades) × 100
```

**Example:**
- 70 profitable trades out of 100 = **70% win rate**

**Interpretation:**
- `> 60%` = Excellent trader
- `50-60%` = Good trader
- `45-50%` = Acceptable (minimum threshold)
- `< 45%` = **REJECTED**

---

### 2. Sharpe Ratio (20% weight)
**What it measures:** Risk-adjusted returns (reward per unit of risk)

**Formula:**
```
Sharpe Ratio = Mean(returns) / StdDev(returns)
```

**Example:**
- Average return per trade: +15%
- Standard deviation: 25%
- Sharpe = 15 / 25 = **0.6**

**Interpretation:**
- `> 2.0` = Excellent (consistent profits)
- `1.0-2.0` = Good
- `< 1.0` = Poor (high volatility)

**Special handling:**
- Capped at **3.0** for ranking (prevents outlier skew)
- Returns capped at **500%** (ignores lottery wins)

---

### 3. Profit Factor (20% weight)
**What it measures:** Total profits vs total losses

**Formula:**
```
Profit Factor = Gross Profit / Gross Loss
```

**Example:**
- Winning trades: +$50,000
- Losing trades: -$20,000
- Profit Factor = 50,000 / 20,000 = **2.5**

**Interpretation:**
- `> 2.0` = Excellent (wins are 2x bigger than losses)
- `1.5-2.0` = Good
- `1.0-1.5` = Breakeven
- `< 1.0` = Losing trader

---

### 4. Max Drawdown (15% weight)
**What it measures:** Worst peak-to-trough loss

**Algorithm:**
1. Sort trades chronologically
2. Calculate cumulative P&L over time
3. Track running peak (highest portfolio value)
4. Calculate drawdown at each point: `(peak - current) / peak`
5. Return maximum drawdown observed

**Example:**
- Peak portfolio: $100,000
- Trough: $70,000
- Max Drawdown = (100k - 70k) / 100k = **30%**

**Interpretation:**
- `< 20%` = Excellent risk management
- `20-30%` = Good
- `30-40%` = Acceptable (maximum threshold)
- `> 40%` = **REJECTED** (too risky)

---

### 5. Consistency Score (20% weight)
**What it measures:** Stable performance (high win rate + low volatility)

**Formula:**
```
volatility_coefficient = std_dev(returns) / abs(mean(returns))
consistency = (win_rate / 100) × (1 - min(volatility_coef, 1.0))
```

**Logic:**
- High win rate + low volatility = **high consistency**
- High win rate + high volatility = moderate consistency
- Low win rate = low consistency

**Range:** 0.0 to 1.0

**Interpretation:**
- `> 0.7` = Excellent (very predictable)
- `0.5-0.7` = Good
- `< 0.5` = Poor (erratic performance)

**Example:**
- Win rate: 65%
- Volatility coefficient: 0.3
- Consistency = 0.65 × (1 - 0.3) = **0.455**

---

## Ranking Formula

### Weighted Score Calculation

```python
# Step 1: Normalize each metric to 0-1 range
win_rate_norm = win_rate / 100                    # 0-100 → 0-1
sharpe_norm = min(sharpe_ratio / 3.0, 1.0)        # Cap at 3.0
profit_factor_norm = min(profit_factor / 3.0, 1.0) # Cap at 3.0
drawdown_component = 1 - max_drawdown              # Invert (lower is better)
consistency_norm = consistency_score               # Already 0-1

# Step 2: Apply weights and scale to 0-100
rank_score = (
    win_rate_norm * 0.25 +
    sharpe_norm * 0.20 +
    profit_factor_norm * 0.20 +
    drawdown_component * 0.15 +
    consistency_norm * 0.20
) × 100
```

### Example Calculation

**Wallet 0xabc... metrics:**
- Win Rate: 65%
- Sharpe Ratio: 1.8
- Profit Factor: 2.2
- Max Drawdown: 25%
- Consistency: 0.55

**Normalized:**
```
win_rate_norm = 65 / 100 = 0.65
sharpe_norm = 1.8 / 3.0 = 0.60
profit_factor_norm = 2.2 / 3.0 = 0.73
drawdown_component = 1 - 0.25 = 0.75
consistency_norm = 0.55
```

**Weighted score:**
```
score = (0.65 × 0.25) + (0.60 × 0.20) + (0.73 × 0.20) + (0.75 × 0.15) + (0.55 × 0.20)
score = 0.1625 + 0.12 + 0.146 + 0.1125 + 0.11
score = 0.651 × 100
score = 65.1
```

**Rank Score: 65.1 / 100**

---

## Filtering Criteria

**All wallets must pass these minimum thresholds:**

| Filter | Threshold | Reason |
|--------|-----------|--------|
| **Min Closed Trades** | ≥ 30 trades | Need statistical significance |
| **Min Win Rate** | > 45% | Must be profitable |
| **Max Drawdown** | < 40% | Risk management limit |

**Wallets that fail ANY filter are rejected before ranking.**

---

## Capital Allocation

After ranking, capital is allocated using a **tiered system** that concentrates capital on top performers:

| Rank Position | Allocation | Total for Tier |
|--------------|-----------|----------------|
| **Top 5** (ranks 1-5) | 10% each | 50% |
| **Tier 2** (ranks 6-10) | 5% each | 25% |
| **Tier 3** (ranks 11-20) | 2.5% each | 25% |
| **Below rank 20** | 0% | 0% |

**Total capital allocated: 100%** (distributed across top 20 wallets)

### Example Allocation

**Capital available: $100,000**

| Rank | Address | Score | Allocation | Capital |
|------|---------|-------|-----------|---------|
| 1 | 0xabc... | 78.5 | 10% | $10,000 |
| 2 | 0xdef... | 75.2 | 10% | $10,000 |
| 3 | 0x123... | 72.8 | 10% | $10,000 |
| 4 | 0x456... | 70.1 | 10% | $10,000 |
| 5 | 0x789... | 68.9 | 10% | $10,000 |
| 6 | 0xaaa... | 67.5 | 5% | $5,000 |
| 7 | 0xbbb... | 66.2 | 5% | $5,000 |
| ... | ... | ... | ... | ... |
| 11 | 0xccc... | 60.5 | 2.5% | $2,500 |
| ... | ... | ... | ... | ... |
| 20 | 0xddd... | 52.1 | 2.5% | $2,500 |

---

## Trade Matching Algorithm (FIFO)

To calculate metrics, we need to match BUY → SELL pairs. The system uses **FIFO (First In, First Out)** matching:

```python
# Example: ETH trades
BUY  1 ETH @ $2000  (t=1)
BUY  2 ETH @ $2100  (t=2)
SELL 1.5 ETH @ $2500 (t=3)
SELL 1 ETH @ $2400   (t=4)

# Matching:
Closed Trade 1: BUY 1 ETH @ $2000 → SELL 1 ETH @ $2500 = +$500 profit
Closed Trade 2: BUY 0.5 ETH @ $2100 → SELL 0.5 ETH @ $2500 = +$200 profit
Closed Trade 3: BUY 1.5 ETH @ $2100 → SELL 1 ETH @ $2400 = +$450 profit

Open Position: BUY 0.5 ETH @ $2100 (not matched, excluded from metrics)
```

**Only closed trades are used for ranking** (positions with both entry and exit).

---

## Data Sources

### Transaction Fetching
- **Source:** Etherscan API
- **Period:** Last 90 days
- **Type:** All transactions for wallet address

### DEX Swap Parsing
- **Parser:** `dex_parser.py`
- **Protocols:** 26+ DEX protocols including:
  - Uniswap V2/V3
  - SushiSwap, PancakeSwap V2/V3
  - 1inch (v3, v4, v5, v6)
  - 0x Protocol, Curve Finance
  - Balancer V2, Kyber Network
  - ParaSwap, OpenOcean, DODO
  - Matcha, MetaMask Swap

### Price Data
- **Source:** CoinGecko API
- **Caching:** 5 minutes
- **Fallback:** Hardcoded prices for USDC, USDT, DAI, BUSD ($1.00)

---

## Database Schema

### wallets table
```sql
address          TEXT PRIMARY KEY
rank_score       REAL        -- 0-100 calculated score
allocation_pct   REAL        -- 0-20% capital allocation
total_trades     INTEGER     -- Number of closed trades
win_rate         REAL        -- Win percentage
sharpe_ratio     REAL        -- Sharpe ratio
max_drawdown     REAL        -- Max drawdown (0-1)
total_pnl        REAL        -- Total P&L in USD
is_active        BOOLEAN     -- 1 = monitored, 0 = paused
```

---

## Example Ranking Output

```
================================================================
RANKING WALLETS
================================================================
Qualified wallets: 15 / 23

Rank 1: 0xabc...def (78.5 score)
  - Win Rate: 68.5%
  - Sharpe: 2.1
  - Profit Factor: 2.4
  - Max Drawdown: 22%
  - Consistency: 0.68
  - Allocation: 10%

Rank 2: 0x123...456 (75.2 score)
  - Win Rate: 65.2%
  - Sharpe: 1.9
  - Profit Factor: 2.2
  - Max Drawdown: 28%
  - Consistency: 0.62
  - Allocation: 10%

...

Total capital allocated: 100.0%
================================================================
```

---

## Quality Considerations

### Why 90 days?
- **Balance:** Long enough for statistical significance
- **Recency:** Recent performance more relevant than 1+ year ago
- **Data availability:** Most RPC providers only keep 90-180 days

### Why FIFO matching?
- **Simplicity:** Easy to implement and audit
- **Standard:** Widely used in accounting
- **Fair:** Matches oldest positions first (conservative)

### Why cap Sharpe at 3.0?
- **Outlier protection:** One lucky 1000% trade shouldn't dominate
- **Realistic:** Sharpe > 3.0 is extremely rare in trading
- **Normalization:** Allows fair comparison across wallets

### Why require 30+ trades?
- **Statistical significance:** 10 trades = luck, 30+ = skill
- **Sample size:** Need enough data for reliable metrics
- **Risk management:** More trades = more observable patterns

---

## Maintenance & Re-ranking

### When to re-rank?
- **Weekly:** Update metrics with latest transactions
- **After major events:** Market crashes, protocol hacks
- **Performance change:** Wallet win rate drops significantly

### Automated monitoring:
```python
# trade_monitor.py updates in real-time
# wallet_analyzer.py re-calculates metrics weekly
# System auto-pauses wallets with declining performance
```

---

## Advanced Features

### Dynamic Allocation Adjustment
Future enhancement: Adjust allocations based on recent performance

```python
# If wallet has 10% allocation but recent 10 trades are 30% win rate:
allocation_pct *= 0.5  # Reduce to 5% until performance improves
```

### Multi-wallet Signal Aggregation
If 3 top wallets all buy the same token within 1 hour:
```python
signal_strength = 3
position_size *= signal_strength  # 3x normal size
```

### Stop-Loss Triggers
Auto-pause wallet if:
- 5 consecutive losing trades
- Win rate drops below 40%
- Drawdown exceeds 50%

---

## Summary

**Ranking combines 5 metrics into one score:**
1. Win Rate (25%) - Are they profitable?
2. Sharpe Ratio (20%) - Is risk-adjusted return good?
3. Profit Factor (20%) - Do wins outweigh losses?
4. Max Drawdown (15%) - Do they manage risk well?
5. Consistency (20%) - Is performance stable?

**Quality filters ensure only proven traders:**
- ≥30 closed trades
- >45% win rate
- <40% max drawdown

**Capital allocation rewards top performers:**
- Top 5 wallets: 50% of capital
- Ranks 6-10: 25% of capital
- Ranks 11-20: 25% of capital

**Result:** A diversified portfolio copying the best 20 DeFi traders with proven track records.
