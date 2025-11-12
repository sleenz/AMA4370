# 🚀 Production Launch Guide - Wallet Copy Trading System

Complete step-by-step guide to launch your wallet copy trading bot into production testing.

---

## ✅ Prerequisites Checklist

Before starting, verify you have:

- [x] ProfitView bot deployed and working
- [x] WOO X paper trading configured
- [x] Test order executed successfully
- [ ] Etherscan API key (get from https://etherscan.io/myapikey)
- [ ] BSCScan API key (optional, for Binance Smart Chain)
- [ ] API keys configured in `config/api_keys.json`

---

## 📋 Phase 1: Discover Profitable Wallets

### Step 1.1: Configure API Keys

Create or update `config/api_keys.json`:

```json
{
  "etherscan": "YOUR_ETHERSCAN_API_KEY",
  "bscscan": "YOUR_BSCSCAN_API_KEY_OPTIONAL"
}
```

Get your Etherscan API key:
1. Go to https://etherscan.io/register
2. Create account and verify email
3. Go to https://etherscan.io/myapikey
4. Create new API key
5. Copy and paste into config file

### Step 1.2: Run Wallet Discovery

**Discover profitable wallets from recent Ethereum transactions:**

```bash
python wallet_discovery.py
```

**What this does:**
- Scans recent Ethereum blocks (last 7 days)
- Extracts wallet addresses from transactions
- Fetches full transaction history (90 days)
- Calculates performance metrics:
  - Total trades
  - Win rate
  - Total P&L
  - Sharpe ratio
  - Average return
  - Max drawdown
- Filters by criteria:
  - Minimum 50 trades in 90 days
  - Total volume > $50,000
  - Not a smart contract
  - Active within last 7 days

**Expected output:**
```
🔍 Wallet Discovery System - Starting...
============================================================
📊 Scanning recent blocks from last 7 days...
   Found 15,234 unique addresses
🔄 Fetching transaction histories (this may take a while)...
   Progress: [####################] 100%
✅ Discovery complete!
   Qualifying wallets: 47
📁 Output: discovered_wallets.csv
```

**Discovery time:** 15-30 minutes depending on API rate limits

### Step 1.3: Review Discovered Wallets

Open `discovered_wallets.csv` in Excel or text editor:

```csv
address,rank_score,total_trades,winning_trades,total_pnl,win_rate,sharpe_ratio,avg_return,max_drawdown
0x1234...abcd,85.5,127,89,45230.50,70.08,2.34,356.15,18.45
0x5678...efgh,82.3,94,67,32180.75,71.28,2.10,342.35,15.20
...
```

**Review criteria:**
- Rank score > 70 (higher is better)
- Win rate > 60%
- Sharpe ratio > 1.5 (risk-adjusted returns)
- Max drawdown < 25%

**Tip:** Start with top 5-10 wallets for initial testing

---

## 💾 Phase 2: Import Wallets to Database

### Step 2.1: Initialize Database (if not done)

```bash
python init_database.py --db-path database/wallets.db
```

**Expected output:**
```
============================================================
DATABASE INITIALIZATION SUCCESSFUL
============================================================
Database file: database/wallets.db
Tables created: 4
  - wallets, wallet_transactions, our_orders, open_positions
Indexes created: 14
============================================================
```

### Step 2.2: Import Top Wallets

**Import top 10 wallets with 5% allocation each:**

```bash
python scripts/import_wallets.py --top 10 --allocation 5.0
```

**What the parameters mean:**
- `--top 10`: Only import top 10 wallets by rank score
- `--allocation 5.0`: Allocate 5% of capital per wallet
  - Total allocation: 10 wallets × 5% = 50% of capital
  - Remaining 50% stays in reserve

**Expected output:**
```
📂 Reading wallets from: discovered_wallets.csv
   Found 47 wallets in CSV
   Limiting to top 10 wallets

💾 Importing wallets to database...

============================================================
📊 IMPORT SUMMARY
============================================================
  ✅ Imported:  10 new wallets
  🔄 Updated:   0 existing wallets
  ⏭️  Skipped:   0 inactive wallets
  📈 Total active wallets: 10
============================================================

✅ Wallets ready for monitoring!
```

**Advanced options:**

```bash
# Import all discovered wallets
python scripts/import_wallets.py

# Import from custom CSV file
python scripts/import_wallets.py --csv-path my_wallets.csv

# Import top 5 with 10% allocation each
python scripts/import_wallets.py --top 5 --allocation 10.0

# Import to different database
python scripts/import_wallets.py --db-path custom/path/wallets.db
```

### Step 2.3: Verify Import

**Check database contents:**

```bash
python -c "import sqlite3; conn = sqlite3.connect('database/wallets.db'); print('Active wallets:', conn.execute('SELECT COUNT(*) FROM wallets WHERE is_active=1').fetchone()[0]); [print(f'  {row[0][:10]}... Score: {row[1]:.1f}') for row in conn.execute('SELECT address, rank_score FROM wallets WHERE is_active=1 ORDER BY rank_score DESC').fetchall()]; conn.close()"
```

**Expected output:**
```
Active wallets: 10
  0x1234abcd... Score: 85.5
  0x5678efgh... Score: 82.3
  0x9abc1234... Score: 79.8
  ...
```

---

## 🎯 Phase 3: Configure Production Settings

### Step 3.1: Review ProfitView Config

Check `config/profitview_config.json`:

```json
{
  "mode": "paper_trade",           ← KEEP AS paper_trade FOR TESTING
  "api_key": "YOUR_WEBHOOK_SECRET",
  "woolive_api_key": "d8e4c5eb-d3b0-4f4f-a201-7c51e0444434",
  "endpoints": {
    "paper_trade": "https://profitview.net/trading/bot/YOUR_SECRET/execute_order",
    "positions": "https://profitview.net/trading/bot/YOUR_SECRET/position",
    "pnl": "https://profitview.net/trading/bot/YOUR_SECRET/pnl"
  },
  "exchange_settings": {
    "venue": "WooLive",
    "exchange": "woox",
    "max_leverage": 25
  },
  "safety": {
    "max_order_size_usd": 10000,
    "require_confirmation_for_live": true
  },
  "rate_limiting": {
    "requests_per_second": 2,
    "burst_size": 5
  }
}
```

**Important settings:**
- ✅ `mode: "paper_trade"` - Simulated orders only
- ✅ `max_order_size_usd: 10000` - Maximum $10k per order
- ✅ `require_confirmation_for_live: true` - Safety check

### Step 3.2: Configure Trade Monitor

The trade monitor has sensible defaults, but you can customize:

```bash
# Default: 60-second check interval, paper mode
python trade_monitor.py --paper-mode

# Custom check interval (30 seconds)
python trade_monitor.py --paper-mode --interval 30

# Monitor only top 5 wallets
python trade_monitor.py --paper-mode --max-wallets 5
```

**Recommended settings for testing:**
- Check interval: 60 seconds (balance between latency and API costs)
- Max wallets: 10-20 (start small, scale up)
- Paper mode: ALWAYS for initial testing

---

## 🚀 Phase 4: Launch Production Testing

### Step 4.1: Start Trade Monitor

**Open Terminal 1 - Trade Monitor:**

```bash
python trade_monitor.py --paper-mode --interval 60 --max-wallets 10
```

**Expected output:**
```
🚀 Trade Monitor Starting...
============================================================
Mode: PAPER TRADING (simulated orders only)
Check interval: 60 seconds
Max wallets: 10
Database: database/wallets.db
============================================================

📊 Loading active wallets from database...
   Found 10 active wallets

🔍 Starting monitoring loop...
   [2025-11-12 10:45:00] Checking 10 wallets...
   [2025-11-12 10:45:00] ✅ Wallet 0x1234... - No new transactions
   [2025-11-12 10:45:01] ✅ Wallet 0x5678... - No new transactions
   ...
   [2025-11-12 10:45:10] Next check in 60 seconds

   [2025-11-12 10:46:10] Checking 10 wallets...
```

**What to watch for:**
- ✅ All wallets loading correctly
- ✅ No API errors
- ✅ Regular check cycles (every 60 seconds)
- 🚨 "🔔 TRADE DETECTED!" - When a wallet makes a trade

### Step 4.2: Monitor Detected Trades

**When a trade is detected, you'll see:**

```
🔔 TRADE DETECTED!
============================================================
Wallet: 0x1234...abcd (Rank: 85.5, Allocation: 5%)
Transaction: 0xabcd1234...
Token: WETH (0x...)
Action: BUY
Amount: 2.5 WETH
Price: $3,450.00
Value: $8,625.00
DEX: Uniswap V3
============================================================

📤 Generating copy trade signal...
   Our order size: $431.25 (5% of $8,625)
   Symbol: WETH/USDT
   Side: BUY
   Quantity: 0.125 WETH

📝 PAPER MODE: Signal logged (not executed)

To execute in production, run without --paper-mode
============================================================
```

**What each line means:**
- **Wallet info**: Which wallet made the trade and its rank
- **Transaction details**: What they bought/sold and for how much
- **Our order**: What we would copy (scaled by allocation %)
- **Paper mode**: Confirms it's simulated

### Step 4.3: Check ProfitView Dashboard

**If trades are being executed (not in paper mode):**

1. Go to https://profitview.net/trading
2. Click on your bot
3. View:
   - **Orders tab**: All executed orders
   - **Positions tab**: Current holdings
   - **P&L tab**: Profit/loss summary
   - **Logs tab**: Execution details

**You should see:**
- Order IDs matching the detected trades
- Fill prices and quantities
- Current positions
- Real-time P&L

---

## 📊 Phase 5: Monitor & Optimize

### Step 5.1: Track Performance

**Check daily performance:**

```bash
python -c "import sqlite3; conn = sqlite3.connect('database/wallets.db'); print('Orders today:', conn.execute('SELECT COUNT(*) FROM orders WHERE DATE(submitted_at) = DATE(\"now\")').fetchone()[0]); print('Success rate:', conn.execute('SELECT ROUND(AVG(CASE WHEN status=\"FILLED\" THEN 1.0 ELSE 0.0 END)*100, 2) FROM orders').fetchone()[0], '%'); conn.close()"
```

**View recent orders:**

```bash
python -c "import sqlite3, json; conn = sqlite3.connect('database/wallets.db'); [print(f'{row[0]} | {row[1]} | {row[2]} | ${row[3]:.2f} | {row[4]}') for row in conn.execute('SELECT submitted_at, pair, side, size_usd, status FROM orders ORDER BY submitted_at DESC LIMIT 20').fetchall()]; conn.close()"
```

### Step 5.2: Adjust Allocations

**If wallets are performing well, increase allocation:**

```bash
python -c "import sqlite3; conn = sqlite3.connect('database/wallets.db'); conn.execute('UPDATE wallets SET allocation_pct = 10.0 WHERE rank_score > 80 AND is_active = 1'); conn.commit(); print('Updated allocations'); conn.close()"
```

**If wallets underperform, decrease or pause:**

```bash
# Decrease allocation
python -c "import sqlite3; conn = sqlite3.connect('database/wallets.db'); conn.execute('UPDATE wallets SET allocation_pct = 2.0 WHERE address = \"0x1234...\"'); conn.commit(); print('Decreased allocation'); conn.close()"

# Pause wallet
python -c "import sqlite3; conn = sqlite3.connect('database/wallets.db'); conn.execute('UPDATE wallets SET is_active = 0 WHERE address = \"0x1234...\"'); conn.commit(); print('Paused wallet'); conn.close()"
```

### Step 5.3: Monitor System Health

**Key metrics to track:**

1. **API health:**
   - Are all Etherscan calls succeeding?
   - Check for rate limit errors

2. **Execution latency:**
   - Time from wallet trade → our trade
   - Target: < 120 seconds

3. **Success rate:**
   - % of orders filled successfully
   - Target: > 95%

4. **Slippage:**
   - Difference between expected and actual price
   - Target: < 2%

**Check logs regularly:**
```bash
tail -f trade_monitor.log     # If logging to file
# Or just watch the terminal output
```

---

## ⚠️ Safety Guidelines

### 🚨 CRITICAL: Start with Paper Trading

**ALWAYS test with paper trading first:**
- ✅ Run with `--paper-mode` for at least 24-48 hours
- ✅ Verify trades are being detected correctly
- ✅ Check that order sizing makes sense
- ✅ Confirm ProfitView bot is working

**Only switch to live after:**
- ✅ Successfully detected 10+ trades in paper mode
- ✅ All orders size correctly
- ✅ No API errors
- ✅ System runs stable for 48+ hours

### 💰 Position Sizing Rules

**Conservative approach (recommended for testing):**
- Total allocation: 50% of capital max
- Per wallet: 2-5% of capital
- Max order size: $10,000
- Start with 5-10 wallets

**Example with $10,000 capital:**
- 5 wallets × 5% allocation = 25% total
- Each wallet can trigger up to $500 orders
- Max exposure: $2,500 at once
- Remaining $7,500 in reserve

### 🔄 Gradual Scale-Up Plan

**Week 1: Paper Trading + Small Size**
- Paper mode only
- 5 wallets × 2% allocation
- Monitor and verify

**Week 2: Live Trading - Minimal Risk**
- Switch to live mode
- 5 wallets × 2% allocation ($200 per wallet on $10k capital)
- Monitor closely

**Week 3: Moderate Risk**
- Increase to 10 wallets
- 3-5% allocation per wallet
- Total exposure: 30-50%

**Week 4+: Full Production**
- 10-20 wallets
- 5% allocation per wallet
- Total exposure: 50-100% (your risk tolerance)

---

## 🐛 Troubleshooting

### Issue: No trades detected

**Check:**
- Are wallets active recently? (Check Etherscan)
- Is check interval too long?
- API rate limits hit?
- Wallets might be inactive

**Solution:**
```bash
# Check wallet activity
python -c "import sqlite3; conn = sqlite3.connect('database/wallets.db'); [print(f'{row[0][:10]}... | Last: {row[1]}') for row in conn.execute('SELECT address, last_updated FROM wallets WHERE is_active=1').fetchall()]; conn.close()"

# Reduce check interval
python trade_monitor.py --paper-mode --interval 30
```

### Issue: API rate limit errors

**Check:**
```
Error: Max rate limit reached
```

**Solution:**
- Reduce check frequency: `--interval 120` (2 minutes)
- Reduce wallet count: `--max-wallets 5`
- Upgrade Etherscan plan (5 calls/sec vs 1)

### Issue: Orders failing on ProfitView

**Check ProfitView logs for:**
- Symbol format errors
- Insufficient balance
- Market unavailable

**Solution:**
- Verify WOO X markets enabled
- Check paper trading balance
- Review symbol translation in bot code

### Issue: Trade monitor crashes

**Check for:**
- Database locks
- Network errors
- Missing dependencies

**Solution:**
```bash
# Install missing dependencies
pip install -r requirements.txt

# Check database
python init_database.py --db-path database/wallets.db

# Restart with error logging
python trade_monitor.py --paper-mode 2>&1 | tee monitor.log
```

---

## 📈 Performance Tracking

### Daily Review Checklist

- [ ] Check trade monitor is running
- [ ] Review detected trades in logs
- [ ] Check ProfitView dashboard
  - [ ] Orders executed
  - [ ] Open positions
  - [ ] P&L summary
- [ ] Review wallet performance
- [ ] Adjust allocations if needed

### Weekly Review

- [ ] Calculate overall P&L
- [ ] Compare wallet performance vs rankings
- [ ] Remove underperforming wallets
- [ ] Add new discovered wallets
- [ ] Re-run discovery for fresh wallets
- [ ] Backup database

### Monthly Optimization

- [ ] Full system audit
- [ ] Re-calculate wallet rankings
- [ ] Optimize allocations
- [ ] Review and update strategy
- [ ] Consider scaling up

---

## 🎓 Best Practices

### 1. Diversification
- Monitor 10-20 wallets minimum
- Different trading styles
- Various tokens/sectors
- Spread allocations evenly

### 2. Risk Management
- Never allocate > 10% per wallet
- Keep 30-50% in reserve
- Use stop losses (ProfitView bot supports this)
- Set max order sizes

### 3. Continuous Improvement
- Run discovery weekly
- Replace underperformers
- Track why trades succeed/fail
- Adjust parameters based on results

### 4. Monitoring
- Check system daily
- Set up alerts (future feature)
- Monitor API health
- Track execution quality

---

## 🚀 You're Ready!

Your wallet copy trading system is now configured for production testing.

**Quick start command:**

```bash
# Terminal 1: Start monitoring
python trade_monitor.py --paper-mode --interval 60 --max-wallets 10

# Terminal 2: Watch ProfitView logs
# (Keep ProfitView dashboard open in browser)
```

**Next Steps:**
1. Run in paper mode for 24-48 hours
2. Verify trades are detected and sized correctly
3. Check ProfitView dashboard shows correct data
4. Gradually transition to live trading
5. Scale up allocations as confidence grows

**Questions or issues?**
- Check logs first
- Review this guide
- Check ProfitView bot logs
- Verify database integrity

**Good luck! 🎉**

Remember: Start small, test thoroughly, scale gradually.
