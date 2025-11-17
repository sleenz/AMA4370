# Wallet Copy Trading Bot - Algorithm Phases & Tweaking Guide

**Complete breakdown of the trading system phases, parameters, and optimization points.**

---

## System Overview

This bot discovers profitable wallets, monitors their trades in real-time, and replicates positions via ProfitView API. The system runs in 5 distinct phases:

```
PHASE 1: Wallet Discovery → PHASE 2: Performance Analysis → PHASE 3: Database Import
                                    ↓
PHASE 4: Real-Time Monitoring ←→ PHASE 5: Trade Execution (ProfitView)
```

---

## PHASE 1: Wallet Discovery
**Purpose:** Find active traders on Ethereum/BSC by sampling recent blockchain activity

### File: `wallet_discovery.py`

### How It Works:
1. **Block Sampling:** Query last 7 days of blocks via Etherscan API
2. **Address Extraction:** Extract unique wallet addresses from transactions
3. **Activity Filtering:** Filter by minimum trade count, volume, and contract status
4. **CSV Export:** Save qualifying wallets to `discovered_wallets.csv`

### Key Tweakable Parameters:

#### Location: `wallet_discovery.py` (lines 15-19)
```python
# Filter Criteria
MIN_TRADES = 50              # Minimum trades in 90 days
MIN_VOLUME_USD = 50000       # Minimum total volume ($50k)
LOOKBACK_DAYS = 90           # Historical window to analyze
RECENT_ACTIVITY_DAYS = 7     # Must be active in last N days
```

**How to Tweak:**
- **Increase MIN_TRADES** (e.g., 100) → Find more experienced traders (fewer results)
- **Decrease MIN_VOLUME_USD** (e.g., 10000) → Find smaller traders (more results)
- **Increase LOOKBACK_DAYS** (e.g., 180) → Longer history = better data (slower)
- **Decrease RECENT_ACTIVITY_DAYS** (e.g., 3) → Only hyper-active wallets

#### Location: `wallet_discovery.py` (lines 85-86)
```python
# Rate Limiting (TokenBucket algorithm)
rate = 5.0           # 5 API calls per second
capacity = 5         # Burst capacity
```

**How to Tweak:**
- **Free Etherscan API:** Keep at 5 calls/sec (hard limit)
- **Paid Etherscan API:** Increase to 30-50 calls/sec for faster discovery

### How to Run:
```bash
# Basic discovery (Ethereum)
python wallet_discovery.py

# Discover from specific network
python wallet_discovery.py --network ethereum  # or bsc

# Adjust filters
python wallet_discovery.py --min-trades 100 --min-volume 100000
```

### Output:
- **File:** `discovered_wallets.csv`
- **Columns:** address, chain, total_trades, total_volume_usd, last_activity, unique_tokens

### Performance:
- **Time:** 10-30 minutes (depends on block sample size)
- **API Calls:** ~2000-5000 (free tier: 100k/day limit)
- **Results:** Typically 50-200 qualifying wallets

---

## PHASE 2: Performance Analysis
**Purpose:** Calculate REAL trading metrics (win rate, Sharpe ratio, P&L) from on-chain DEX swaps

### File: `wallet_analyzer.py`

### How It Works:
1. **Transaction Fetch:** Get 90 days of transaction history via Etherscan
2. **DEX Parsing:** Decode swaps across 26+ protocols (Uniswap, 1inch, Curve, etc.)
3. **Position Matching:** Match BUY/SELL pairs using FIFO algorithm
4. **Metrics Calculation:** Calculate win rate, Sharpe, P&L, drawdown, consistency
5. **Ranking:** Score wallets using weighted formula
6. **CSV Export:** Save ranked wallets to `ranked_wallets.csv`

### Key Tweakable Parameters:

#### Location: `wallet_analyzer.py` (lines 19-26)
```python
# Ranking Formula Weights
Win_Rate_Weight = 0.25        # 25% weight on win rate
Sharpe_Weight = 0.20          # 20% weight on Sharpe ratio
Profit_Factor_Weight = 0.20   # 20% weight on profit factor
Drawdown_Weight = 0.15        # 15% weight on (1 - max_drawdown)
Consistency_Weight = 0.20     # 20% weight on consistency score

# Filter Criteria
MIN_WIN_RATE = 0.45           # 45% minimum win rate
MAX_DRAWDOWN = 0.40           # 40% maximum drawdown
MIN_CLOSED_TRADES = 30        # Minimum closed positions
```

**How to Tweak:**
- **Aggressive Strategy:** Increase `Profit_Factor_Weight` to 0.30, reduce `Drawdown_Weight` to 0.10
- **Conservative Strategy:** Increase `Drawdown_Weight` to 0.25, reduce `Profit_Factor_Weight` to 0.15
- **Quality Filter:** Increase `MIN_CLOSED_TRADES` to 50-100 for more experienced traders
- **Loose Filter:** Decrease `MIN_WIN_RATE` to 0.40 for more wallet options

#### Location: `wallet_analyzer.py` (lines 28-30)
```python
# Capital Allocation Tiers
TOP_5_ALLOCATION = 10.0       # Top 5 wallets: 10% each
TIER_2_ALLOCATION = 5.0       # Wallets 6-10: 5% each
TIER_3_ALLOCATION = 2.5       # Wallets 11-20: 2.5% each
```

**How to Tweak:**
- **Concentrated Strategy:** Increase top tier to 15-20% (higher risk/reward)
- **Diversified Strategy:** Reduce top tier to 5-8%, increase tier 3 to 3-4%

#### Location: `wallet_analyzer.py` (line 96)
```python
MIN_TRADE_VALUE_USD = 100     # Skip trades below $100 (dust filtering)
```

**How to Tweak:**
- **Retail Traders:** Decrease to $50 to capture smaller trades
- **Whale Traders:** Increase to $500-1000 to focus on significant moves

#### Location: `wallet_analyzer.py` (lines 248-253) - **NEW OPTIMIZATION**
```python
def fetch_wallet_transactions(
    client: BlockchainAPIClient,
    address: str,
    days: int = 90,              # Historical window
    use_cache: bool = True,      # Enable transaction caching
    db_path: str = 'wallet_trading.db'
)
```

**How to Tweak:**
- **use_cache=True:** 3-10x faster on repeat analyses (recommended)
- **use_cache=False:** Fresh parse every time (for debugging)
- **days=30:** Faster analysis, less data (for testing)
- **days=180:** More historical data, slower (for production)

### How to Run:
```bash
# Analyze all wallets from discovery phase
python wallet_analyzer.py

# Analyze specific CSV
python wallet_analyzer.py --input discovered_wallets.csv

# Adjust analysis window
python wallet_analyzer.py --days 180  # 6 months instead of 90 days
```

### Output:
- **File:** `ranked_wallets.csv`
- **Columns:** address, rank_score, win_rate, sharpe_ratio, total_pnl, max_drawdown, total_trades, allocation_pct

### Performance (with caching optimization):
- **First Run (cold cache):** 15-30 minutes per wallet (~4000 RPC calls)
- **Subsequent Runs (warm cache):** 2-5 minutes per wallet (~100 RPC calls)
- **Speedup:** 3-10x faster on cached data
- **Analyzing 100 wallets:** ~5 hours (with cache) vs ~33 hours (without)

---

## PHASE 3: Database Import
**Purpose:** Load discovered/analyzed wallets into SQLite database for monitoring

### File: `scripts/import_wallets.py`

### How It Works:
1. **Read CSV:** Load `ranked_wallets.csv` or `discovered_wallets.csv`
2. **Database Insert:** Insert wallets into `wallets` table with metrics
3. **Allocation Setup:** Set capital allocation percentages per wallet
4. **Activation:** Mark wallets as active for monitoring

### Key Tweakable Parameters:

#### Command Line Arguments:
```bash
--csv-path       # CSV file to import (default: discovered_wallets.csv)
--db-path        # Database location (default: wallet_trading.db)
--top N          # Only import top N wallets by rank_score
--allocation X   # Override allocation percentage (default: 5.0%)
```

**How to Tweak:**
- **Import only top performers:** `--top 10` (monitor only best 10 wallets)
- **Equal allocation:** `--allocation 10.0` (give all wallets 10%)
- **Custom CSV:** `--csv-path my_custom_wallets.csv`

### How to Run:
```bash
# Import top 20 ranked wallets
python scripts/import_wallets.py --csv-path ranked_wallets.csv --top 20

# Import with custom allocation
python scripts/import_wallets.py --top 10 --allocation 8.0

# Import all discovered wallets for analysis
python scripts/import_wallets.py --csv-path discovered_wallets.csv
```

### Alternative: Tiered Import
```bash
# Import with tiered allocation (10% / 5% / 2.5%)
python scripts/import_wallets_tiered.py --csv-path ranked_wallets.csv
```

### Output:
- **Database:** `wallet_trading.db` (wallets table populated)
- **Tables Updated:** `wallets`, `monitoring_state`

---

## PHASE 4: Real-Time Monitoring
**Purpose:** Monitor tracked wallets in real-time, detect DEX swaps, generate copy signals

### File: `trade_monitor.py`

### How It Works:
1. **Load Wallets:** Read active wallets from database
2. **Polling Loop:** Check for new transactions every 60 seconds
3. **DEX Detection:** Parse transactions for swaps across 26+ protocols
4. **Signal Generation:** Create copy trade signals based on detected swaps
5. **Signal Emission:** Log signals (paper mode) or send to executor (live mode)
6. **State Tracking:** Update last checked block/timestamp per wallet

### Key Tweakable Parameters:

#### Location: `trade_monitor.py` (lines 22-24)
```python
# Monitoring Configuration
CHECK_INTERVAL = 60           # Seconds between checks (default: 1 minute)
PAPER_MODE = True             # Safe mode (log signals, don't execute)
MAX_WALLETS = 20              # Maximum wallets to monitor simultaneously
```

**How to Tweak:**
- **Faster Response:** Decrease `CHECK_INTERVAL` to 30 seconds (more API calls)
- **Lower API Usage:** Increase `CHECK_INTERVAL` to 120-300 seconds
- **Scale Up:** Increase `MAX_WALLETS` to 50-100 (requires better API plan)
- **Live Trading:** Set `PAPER_MODE = False` (dangerous without Phase 5 ready)

#### Location: `trade_monitor.py` (command line)
```bash
python trade_monitor.py --paper-mode              # Safe logging mode
python trade_monitor.py --no-paper-mode           # Live execution mode
python trade_monitor.py --interval 30             # Check every 30 seconds
python trade_monitor.py --max-wallets 50          # Monitor 50 wallets
```

### Signal Generation Logic:

#### Location: `trade_monitor.py` (SignalEmitter class)
```python
# Position Sizing (example logic)
WALLET_ALLOCATION_PCT = 5.0   # From database (per wallet)
POSITION_SIZE_USD = CAPITAL * (ALLOCATION_PCT / 100)

# Example: $10,000 capital, 5% allocation = $500 per position
```

**How to Tweak:**
- **Modify in database:** Update `allocation_pct` in wallets table
- **Global override:** Adjust in trade_monitor.py signal emission code

### How to Run:
```bash
# Paper mode (recommended for testing)
python trade_monitor.py --paper-mode

# Live mode (executes real trades via ProfitView)
python trade_monitor.py --no-paper-mode

# Custom interval (check every 2 minutes)
python trade_monitor.py --paper-mode --interval 120
```

### Output:
- **Logs:** Real-time monitoring status, detected trades, signals
- **Paper Mode File:** `signals_paper.log` (all generated signals)
- **Database:** `wallet_transactions` table (logged swaps)

### Performance:
- **API Calls:** ~20-50 calls per cycle (depends on wallet count)
- **Detection Latency:** 1-2 minutes (depends on CHECK_INTERVAL + blockchain confirmation)
- **CPU Usage:** Very low (mostly waiting/sleeping)

---

## PHASE 5: Trade Execution (ProfitView)
**Purpose:** Execute copy trades on Binance Futures via ProfitView API

### File: `scripts/profitview_executor.py`

### How It Works:
1. **Receive Signal:** Get trade signal from trade_monitor.py
2. **Order Construction:** Build ProfitView API payload (symbol, side, size, leverage, SL/TP)
3. **Validation:** Check order size limits, leverage limits, daily loss limits
4. **API Call:** Send webhook request to ProfitView
5. **Order Tracking:** Log order details to database for audit trail
6. **P&L Tracking:** Query ProfitView dashboard for real-time P&L

### Key Tweakable Parameters:

#### Location: `config/profitview_config.json`
```json
{
  "mode": "paper_trade",              // "paper_trade" or "live"
  "api_key": "YOUR_API_KEY",

  "exchange_settings": {
    "venue": "WooLive",               // ProfitView venue name
    "exchange": "binance",            // Target exchange
    "account_type": "futures",        // "futures" or "spot"
    "default_leverage": 10,           // Default leverage (1-125x)
    "max_leverage": 25                // Maximum allowed leverage
  },

  "safety": {
    "require_confirmation_for_live": true,     // Prompt before live trades
    "max_order_size_usd": 10000,               // Per-order limit
    "daily_loss_limit_usd": 5000,              // Daily stop-loss
    "enable_audit_log": true                   // Log all orders to DB
  },

  "rate_limiting": {
    "requests_per_second": 10,                 // API rate limit
    "burst_size": 20                           // Burst capacity
  }
}
```

**How to Tweak:**

**For Testing:**
- Keep `mode: "paper_trade"` until confident
- Set `default_leverage: 3-5` for conservative testing

**For Aggressive Trading:**
- Increase `default_leverage: 15-20`
- Increase `max_order_size_usd: 20000`
- Decrease `daily_loss_limit_usd` if you want tighter risk control

**For Conservative Trading:**
- Set `default_leverage: 3-5`
- Set `max_order_size_usd: 1000-5000`
- Set `daily_loss_limit_usd: 1000-2000`

#### Location: `scripts/profitview_executor.py` (ProfitViewExecutor class)
```python
# Order Validation
MAX_RETRIES = 3               # Retry failed orders N times
RETRY_BACKOFF = 2.0           # Exponential backoff (2^n seconds)
```

**How to Tweak:**
- **Unreliable network:** Increase `MAX_RETRIES` to 5
- **Fast failure:** Decrease `MAX_RETRIES` to 1

### How to Run:

**Standalone Testing:**
```bash
# Run demo execution
python main.py --demo

# Run integration tests
python tests/test_profitview_integration.py
```

**Production (integrated with trade_monitor.py):**
```bash
# Trade monitor will call profitview_executor automatically when --no-paper-mode
python trade_monitor.py --no-paper-mode
```

### Output:
- **Database:** `our_orders` table (all order records)
- **Logs:** Order execution status, API responses, errors
- **ProfitView Dashboard:** Real-time positions, P&L, order history

### Safety Features:
1. **Paper Mode Default:** Must explicitly enable live trading
2. **Confirmation Prompt:** Asks "Are you sure?" before live mode
3. **Order Size Limits:** Prevents accidentally large orders
4. **Daily Loss Limit:** Stops trading if daily loss exceeds threshold
5. **Audit Trail:** Every order logged to database with timestamp

---

## Complete Workflow Example

### Scenario: Start from scratch and run paper trading

```bash
# STEP 1: Initialize database
python init_database.py

# STEP 2: Discover wallets (10-30 min)
python wallet_discovery.py --network ethereum

# STEP 3: Analyze discovered wallets (5-10 hours for 100 wallets)
python wallet_analyzer.py --input discovered_wallets.csv

# STEP 4: Import top 10 ranked wallets
python scripts/import_wallets.py --csv-path ranked_wallets.csv --top 10

# STEP 5: Configure ProfitView (edit config file)
cp config/profitview_config.example.json config/profitview_config.json
nano config/profitview_config.json  # Add your API key

# STEP 6: Start monitoring in paper mode
python trade_monitor.py --paper-mode

# STEP 7 (later): Switch to live trading when confident
# Edit config/profitview_config.json: "mode": "live"
python trade_monitor.py --no-paper-mode
```

---

## Performance Optimization Summary

### Phase 1 (Wallet Discovery)
- **Bottleneck:** Etherscan API rate limit (5 calls/sec free tier)
- **Optimization:** Upgrade to paid Etherscan API (50 calls/sec) → 10x faster
- **Cost:** $99-$299/month

### Phase 2 (Performance Analysis)
- **Bottleneck:** RPC calls for transaction parsing (~4000 per wallet)
- **Optimization:** ✅ **IMPLEMENTED** - Transaction caching (3-10x speedup)
- **Result:** First run 15-30 min, subsequent runs 2-5 min

### Phase 3 (Database Import)
- **No significant bottleneck** (instant for <1000 wallets)

### Phase 4 (Real-Time Monitoring)
- **Bottleneck:** Etherscan API rate limit (monitoring 50+ wallets)
- **Optimization:** Use websocket subscriptions (e.g., Alchemy, Infura) instead of polling
- **Cost:** $50-200/month for hosted blockchain indexer

### Phase 5 (Trade Execution)
- **No significant bottleneck** (ProfitView API is fast)

---

## Scalability Roadmap

### Current Limitations:
- **Wallet Discovery:** 100-200 wallets/day (free Etherscan API)
- **Analysis:** 20-50 wallets/day (with caching, single-threaded)
- **Monitoring:** 20-30 wallets (60-second polling, free API)
- **Execution:** Unlimited (ProfitView handles scaling)

### How to Scale to 1000+ Wallets:

**SHORT TERM (1-2 months):**
1. Upgrade to paid Etherscan API → 10x faster discovery
2. Implement parallel analysis → 5x faster (use ThreadPoolExecutor)
3. Add cache TTL and versioning → Prevent cache bloat

**MEDIUM TERM (3-6 months):**
1. Migrate to PostgreSQL → Support concurrent writes
2. Implement worker queue (Celery) → Distribute analysis across servers
3. Use blockchain indexer API (The Graph, Dune) → 100x faster queries

**LONG TERM (6-12 months):**
1. Switch to websocket subscriptions → Real-time monitoring (0 latency)
2. Implement distributed caching (Redis) → Share cache across servers
3. Add machine learning for wallet selection → Improve performance prediction

**Estimated Costs:**
- **Current (free tier):** $0/month (rate limits apply)
- **Small Scale (50-100 wallets):** $50-100/month (API upgrades)
- **Medium Scale (100-500 wallets):** $200-500/month (indexer + infrastructure)
- **Large Scale (1000+ wallets):** $500-2000/month (full infrastructure stack)

---

## Key Files Reference

| Phase | File | Purpose | Parameters Location |
|-------|------|---------|---------------------|
| 1 | `wallet_discovery.py` | Find active wallets | Lines 15-19, 85-86 |
| 2 | `wallet_analyzer.py` | Calculate metrics | Lines 19-30, 96, 248-253 |
| 3 | `scripts/import_wallets.py` | Import to DB | Command line args |
| 4 | `trade_monitor.py` | Real-time monitoring | Lines 22-24, command line |
| 5 | `scripts/profitview_executor.py` | Execute trades | `config/profitview_config.json` |
| - | `dex_parser.py` | DEX swap decoder | `KNOWN_ROUTERS` dict |
| - | `init_database.py` | Database schema | Table definitions |
| - | `config.json` | Etherscan API keys | - |
| - | `config/profitview_config.json` | ProfitView settings | - |

---

## Troubleshooting Guide

### "No wallets found in database"
- **Solution:** Run Phase 3 (import_wallets.py)

### "Only 1 monitoring cycle completed in 5 hours"
- **Cause:** Empty database or DEX parser not finding swaps
- **Solution:**
  1. Check wallets table has entries
  2. Verify dex_parser.py has 26 routers (not 6)
  3. Check if wallets actually have recent DEX activity

### "Rate limit exceeded"
- **Cause:** Too many API calls to Etherscan
- **Solution:**
  1. Increase CHECK_INTERVAL in trade_monitor.py
  2. Reduce MAX_WALLETS
  3. Upgrade to paid Etherscan API

### "Transaction caching not working"
- **Check:** Run `python test_optimization.py` to verify database schema
- **Solution:** Ensure init_database.py created cached_transactions table

### "ProfitView order rejected"
- **Check:** Verify API key in config/profitview_config.json
- **Check:** Ensure mode matches endpoint (paper_trade vs live)
- **Solution:** Run `python tests/test_profitview_integration.py`

---

## Next Steps

1. **Test the optimizations:**
   ```bash
   python test_optimization.py  # Verify caching works
   ```

2. **Run a full cycle:**
   ```bash
   # Discovery → Analysis → Import → Monitor
   python wallet_discovery.py && \
   python wallet_analyzer.py && \
   python scripts/import_wallets.py --top 10 && \
   python trade_monitor.py --paper-mode
   ```

3. **Monitor performance:**
   - Check `signals_paper.log` for detected trades
   - Query `cached_transactions` table for cache hit rate
   - Verify API call reduction in logs

4. **Scale up when ready:**
   - Upgrade Etherscan API tier
   - Implement parallel processing
   - Add worker queues for distributed analysis

---

**Created:** 2025-11-17
**Optimization Status:** Transaction caching ✅ IMPLEMENTED (3-10x speedup)
**Production Ready:** Phase 1-4 (Phase 5 requires ProfitView account)
