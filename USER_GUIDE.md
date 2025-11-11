# Wallet Copy Trading Bot - Complete User Guide

**What this does:** Automatically finds profitable crypto wallets on Ethereum, monitors their trades, and copies them via ProfitView.

**Current Status:** ✅ ProfitView bot deployed, ready to run on your computer

---

## 📁 What's in This Repository (Essential Files Only)

### Core System (9 files)

**1. `wallet_discovery.py`** - Find Profitable Wallets
- Scans Ethereum blockchain for active traders
- Filters by volume, trade count, and activity
- Outputs: `discovered_wallets.csv` with ~10-50 wallets
- **Run:** `python wallet_discovery.py`
- **Time:** 10-15 minutes

**2. `wallet_analyzer.py`** - Monitor Wallet Activity
- Watches specific wallet transactions in real-time
- Decodes DEX trades (Uniswap, PancakeSwap, etc.)
- Calculates profit/loss metrics
- **Run:** `python wallet_analyzer.py --wallet 0x123...`
- **Used by:** `main.py` (automatic)

**3. `signal_processor.py`** - Generate Trading Signals
- Converts wallet trades into actionable signals
- Applies filters: minimum size, confidence score
- Calculates position sizing and stop loss
- **Used by:** `main.py` (automatic)

**4. `dex_parser.py`** - Decode DEX Transactions
- Parses Uniswap, PancakeSwap, SushiSwap trades
- Extracts: token pair, amount, price, direction
- **Used by:** `wallet_analyzer.py` (automatic)

**5. `scripts/profitview_executor.py`** - Send Orders to ProfitView
- **Runs on YOUR computer**
- Sends webhook requests to your ProfitView bot
- Handles errors, retries, logging
- **Run:** `python scripts/profitview_executor.py` (test mode)

**6. `profitview_bot.py`** - Execute Trades (Already Deployed)
- **Runs on ProfitView servers** (you already deployed this)
- Receives webhooks from profitview_executor.py
- Executes trades on WOO X (WooLive)
- **Status:** Check ProfitView dashboard (should be "Running")

**7. `main.py`** - Main Program
- Ties everything together
- Monitors wallets → generates signals → executes trades
- **Run:** `python main.py --demo` (test) or `python main.py` (full)

**8. `init_database.py`** - Database Setup
- Creates database for wallets, positions, orders
- Auto-runs on first use
- **Run:** `python init_database.py` (if needed)

**9. `trade_monitor.py`** - Track Performance
- Monitors ongoing trades
- Calculates P&L
- **Used by:** `main.py` (automatic)

### Support Files

**10. `edge_case_handlers.py`** - Handle Edge Cases
- Deals with unusual trade scenarios
- **Used by:** `signal_processor.py` (automatic)

---

## 🚀 Complete Workflow - Step by Step

### STEP 1: Install Dependencies

```bash
pip install -r requirements.txt
```

**What gets installed:**
- `requests` - HTTP requests
- `web3` - Ethereum blockchain
- `eth-abi` - Decode transactions
- `numpy` - Math operations

**Verify installation:**
```bash
python -c "import requests, web3, eth_abi; print('✅ Ready!')"
```

---

### STEP 2: Configure API Keys

Your ProfitView keys are already configured in `config/profitview_config.json`.

**For Ethereum blockchain access, add Etherscan API key:**

1. Get free API key: https://etherscan.io/apis
2. Edit `config/api_keys.json`:
   ```json
   {
     "etherscan_api_key": "YOUR_KEY_HERE"
   }
   ```

---

### STEP 3: Test ProfitView Connection

```bash
python scripts/profitview_executor.py
```

**Expected output:**
```
📝 PAPER TRADING MODE ACTIVE
════════════════════════════════════════════════════════════
• All orders are simulated
• View results in ProfitView dashboard
• No real money at risk

🧪 Testing ProfitView Connection...

📋 Test 1: Query open positions
📊 Retrieved 0 open positions from ProfitView

📋 Test 2: Query P&L
💰 P&L Summary:
   Total P&L: $0.00

📋 Test 3: Send test order
────────────────────────────────────────────────────────────
📤 Sending order to ProfitView (attempt 1/3)
   Mode: PAPER_TRADE
   Symbol: BTCUSDT
   Side: BUY
   Quantity: 0.002
✅ Order executed successfully
   Order ID: WCT_999_1699876543210

✅ Connection test complete!
```

**✅ If you see this → Everything is working!**

**❌ If you see errors:**
- Check ProfitView bot status (should be "Running" - green)
- Check ProfitView bot logs for errors
- Verify WooLive is connected in ProfitView
- Restart ProfitView bot if needed

---

### STEP 4: Run Demo Mode

Test the complete system without discovering wallets:

```bash
python main.py --demo
```

**What it does:**
1. Creates a simulated trading signal
2. Sends it to ProfitView
3. Executes test order on WooLive
4. Shows result

**Expected output:**
```
🤖 Wallet Copy Trading Bot - DEMO MODE
════════════════════════════════════════════════════════════

📊 Demo Trading Signal:
   Pair: BTC/USDT
   Side: BUY
   Size: $100.00
   Leverage: 5x
   Entry: $50,000
   Stop Loss: $49,000

🚀 Executing trade via ProfitView...
📤 Sending order to ProfitView...
✅ Order executed successfully
   Order ID: WCT_1_1699876543210
   Exchange Order ID: 12345678
   Status: FILLED

📈 Executor Statistics:
   Mode: paper_trade
   Orders Submitted: 1
   Orders Filled: 1
   Success Rate: 100.0%
```

**✅ If demo works → Ready for real wallet discovery!**

---

### STEP 5: Discover Profitable Wallets

This is where the magic starts!

```bash
python wallet_discovery.py
```

**What it does:**
1. Scans last 7 days of Ethereum blocks
2. Samples recent blocks for active addresses
3. Analyzes top traders by transaction count
4. Filters wallets by criteria:
   - ✅ Minimum 30 trades in 90 days
   - ✅ Minimum $10,000 volume
   - ✅ Not a smart contract (real person)
   - ✅ Active within last 14 days
5. Exports to `discovered_wallets.csv`

**How long:** 10-15 minutes

**Progress output:**
```
🔍 Wallet Discovery Started
════════════════════════════════════════════════════════════

📅 Fetching blocks from last 7 days...
✓ Retrieved 50,000 blocks

📦 Sampling 1000 blocks...
✓ Found 25,432 unique addresses

📊 Analyzing top 1000 addresses by activity...

Progress: [========================================] 100%

✅ Discovery Complete!
════════════════════════════════════════════════════════════

📈 Results:
   Total Addresses Analyzed: 1,000
   Wallets Passed Filters: 15
   Combined Volume: $45,234,567
   Average Trades per Wallet: 127

💾 Saved to: discovered_wallets.csv

Top 5 Wallets:
1. 0x28c6c0629...  $15.2M volume, 543 trades
2. 0xa9ac43f5b...  $8.7M volume, 312 trades
3. 0x3ddfa8ec3...  $6.1M volume, 201 trades
4. 0xd8da6bf26...  $4.8M volume, 156 trades
5. 0x742d35cc6...  $3.2M volume, 94 trades
```

**Output file: `discovered_wallets.csv`**
```csv
address,chain,total_trades,total_volume_usd,last_activity,unique_tokens,days_since_last_activity
0x28c6c06298d514db089934071355e5743bf21d60,ethereum,543,15234567.89,2025-11-11 08:30:15,1382,0
0xa9ac43f5b5e38155a288d1a01d2cbc4478e14573,ethereum,312,8765432.10,2025-11-11 07:15:22,483,0
...
```

---

### STEP 6: Import Wallets to Database

```bash
python init_database.py
```

**What it does:**
1. Creates `database/wallets.db` if it doesn't exist
2. Reads `discovered_wallets.csv`
3. Imports wallets into database
4. Ready for monitoring

**Output:**
```
🗄️  Initializing Database
════════════════════════════════════════════════════════════

✓ Database created: database/wallets.db
✓ Tables created: wallets, positions, orders

📥 Importing wallets from discovered_wallets.csv...
✓ Imported 15 wallets

✅ Database ready!
```

**Verify database:**
```bash
sqlite3 database/wallets.db "SELECT address, total_trades, total_volume_usd FROM wallets LIMIT 5;"
```

---

### STEP 7: Start Monitoring Wallets

**This is the main program that runs continuously:**

```bash
python main.py
```

**What it does:**
1. Loads all wallets from database
2. Monitors their transactions in real-time
3. Analyzes each transaction
4. Generates trading signals when they match criteria
5. Sends signals to ProfitView
6. ProfitView executes on WooLive
7. Logs everything to database

**Live output:**
```
🤖 Wallet Copy Trading Bot - Production Mode
════════════════════════════════════════════════════════════

📝 PAPER TRADING MODE ACTIVE
   Mode: paper_trade
   Exchange: WooLive (WOO X Paper Trading)
   Wallets Monitoring: 15

✓ ProfitView connection verified
✓ Database connected
✓ Monitoring started

════════════════════════════════════════════════════════════
Watching wallets for trading activity...
Press Ctrl+C to stop
════════════════════════════════════════════════════════════

[2025-11-11 10:30:15]
📡 New transaction from wallet 0x28c6c062...
   Hash: 0xabc123...
   Analyzing...

[2025-11-11 10:30:17]
✅ DEX Trade Detected
   Wallet: 0x28c6c062...
   DEX: Uniswap V3
   Action: SWAP
   Pair: WETH → USDC
   Amount: 5.5 ETH ($10,500)
   Price: $1,909.09 per ETH
   Direction: SELL

[2025-11-11 10:30:18]
🎯 Generating Signal...
   Confidence: 85%
   Signal Type: COPY TRADE
   Action: SELL ETH/USDT
   Size: $1,050 (10% of wallet trade)
   Leverage: 3x
   Entry: $1,909
   Stop Loss: $1,952 (2.25% risk)

[2025-11-11 10:30:19]
📤 Sending order to ProfitView...
✅ Order executed successfully
   Order ID: WCT_1_1699876543210
   Status: FILLED
   Filled Price: $1,909.25
   Filled Quantity: 0.55 ETH

💰 P&L Tracking:
   Position: SHORT 0.55 ETH @ $1,909.25
   Notional: $3,150 (with 3x leverage)
   Stop Loss: $1,952
   Risk: $23.65 (2.25%)

════════════════════════════════════════════════════════════
Statistics:
   Runtime: 00:05:42
   Wallets Active: 3/15
   Signals Generated: 1
   Orders Sent: 1
   Orders Filled: 1
   Success Rate: 100%
   Total Volume: $1,050
════════════════════════════════════════════════════════════

[Monitoring continues...]
```

**To stop:** Press `Ctrl+C`

---

## 📊 Monitoring & Results

### Check ProfitView Dashboard

1. Go to https://profitview.net/trading
2. Click your bot "Wallet Copy Executor"
3. View:
   - **Logs:** See all executed orders
   - **Positions:** Open positions on WooLive
   - **P&L:** Profit/loss tracking

### Check Local Database

**Recent orders:**
```bash
sqlite3 database/wallets.db "
SELECT
  pair,
  side,
  size_usd,
  status,
  executed_price,
  submitted_at
FROM orders
ORDER BY submitted_at DESC
LIMIT 10;
"
```

**Success rate:**
```bash
sqlite3 database/wallets.db "
SELECT
  status,
  COUNT(*) as count,
  ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 2) as percentage
FROM orders
GROUP BY status;
"
```

**Total volume:**
```bash
sqlite3 database/wallets.db "
SELECT
  SUM(size_usd) as total_volume,
  COUNT(*) as total_orders,
  AVG(size_usd) as avg_order_size
FROM orders
WHERE status='FILLED';
"
```

**Wallet performance:**
```bash
sqlite3 database/wallets.db "
SELECT
  w.address,
  COUNT(o.id) as trades_copied,
  SUM(o.size_usd) as total_volume
FROM wallets w
LEFT JOIN orders o ON o.wallet_id = w.id
GROUP BY w.id
ORDER BY total_volume DESC;
"
```

### Check WooLive Account

1. Log into your WooLive account
2. View:
   - **Positions:** All open positions
   - **Orders:** Order history
   - **P&L:** Real-time profit/loss
   - **Balance:** Account balance

---

## 🎯 Understanding the Signal Generation

When a wallet makes a trade, the system decides whether to copy it based on:

### Signal Criteria

**✅ Trade is copied IF:**
- Trade size ≥ $5,000 (configurable)
- Wallet confidence score ≥ 70% (based on past performance)
- Not a token launch/rug pull (security filters)
- Sufficient account balance
- Within daily trade limits

**❌ Trade is skipped IF:**
- Trade too small (< $5,000)
- Low confidence wallet (< 70%)
- Suspicious token detected
- Insufficient balance
- Daily limits exceeded

### Position Sizing

**Default strategy:**
```
Your position size = 10% of wallet's trade size

Example:
- Wallet trades: $50,000
- Your position: $5,000
- Leverage: 3x (configurable)
- Notional value: $15,000
```

**Risk management:**
```
- Maximum position size: $10,000 (configurable)
- Maximum leverage: 25x (configurable)
- Stop loss: 2-5% from entry (automatic)
- Daily loss limit: $5,000 (configurable)
```

### Configuration

Edit `config/config.json` to adjust:

```json
{
  "signal_filters": {
    "min_trade_size_usd": 5000,
    "min_confidence_score": 0.70,
    "position_size_multiplier": 0.10
  },
  "risk_management": {
    "max_position_size_usd": 10000,
    "max_leverage": 25,
    "default_leverage": 3,
    "stop_loss_percentage": 0.02,
    "daily_loss_limit_usd": 5000
  }
}
```

---

## 🔧 Configuration Files

### `config/profitview_config.json` (Your Settings - GITIGNORED)

```json
{
  "mode": "paper_trade",
  "api_key": "517b3bcac35bc86e1bea1ec31101b9b583b34387",
  "woolive_api_key": "d8e4c5eb-d3b0-4f4f-a201-7c51e0444434",

  "endpoints": {
    "paper_trade": "https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/execute_order",
    ...
  },

  "exchange_settings": {
    "venue": "WooLive",
    "exchange": "woox",
    "default_leverage": 10,
    "max_leverage": 25
  },

  "safety": {
    "max_order_size_usd": 10000,
    "daily_loss_limit_usd": 5000
  }
}
```

**✅ Already configured with your credentials**

### `config/api_keys.json` (Blockchain Access)

```json
{
  "etherscan_api_key": "YOUR_ETHERSCAN_KEY",
  "rate_limit_per_second": 5
}
```

**Get free key:** https://etherscan.io/apis

### `config/config.json` (Trading Parameters)

Main configuration for filters, risk management, and trading logic.

**Edit to customize:**
- Minimum trade size to copy
- Confidence score thresholds
- Position sizing
- Leverage settings
- Stop loss percentages

---

## 🛠️ Troubleshooting

### Issue: "Module not found"

```bash
pip install -r requirements.txt
```

### Issue: "Etherscan API key not found"

1. Get free key: https://etherscan.io/apis
2. Add to `config/api_keys.json`:
   ```json
   {
     "etherscan_api_key": "YOUR_KEY_HERE"
   }
   ```

### Issue: "Order rejected - HTTP 403"

**Check:**
1. Is ProfitView bot running? (status = green)
2. Is WooLive connected in ProfitView?
3. Is webhook secret correct?

**Fix:**
1. Go to ProfitView dashboard
2. Check bot status → restart if needed
3. Check bot logs for errors
4. Verify WooLive connection is active (green)

### Issue: "No wallets found"

```bash
# Run discovery again
python wallet_discovery.py

# Takes 10-15 minutes
# Outputs: discovered_wallets.csv
```

### Issue: "Database locked"

```bash
# Close all database connections
pkill -f sqlite3

# Or just restart terminal
```

### Issue: "Rate limit exceeded"

**Etherscan API rate limit (free tier: 5 req/sec)**

**Solution:**
- System has built-in rate limiting
- Wait a few seconds and retry
- Or upgrade Etherscan API plan

### Issue: "No transactions detected"

**Possible reasons:**
- Wallets not trading currently (normal)
- Blockchain sync delay (wait a few minutes)
- Etherscan API issues (check status)

**Check:**
```bash
# Verify wallet has recent activity
python wallet_analyzer.py --wallet 0x28c6c06298d514db089934071355e5743bf21d60
```

---

## 📈 Performance Monitoring

### Daily Checklist

**Every day:**
1. Check ProfitView bot is running (green status)
2. Review executed orders in dashboard
3. Check P&L in WooLive
4. Review database statistics
5. Monitor for any errors in logs

### Weekly Review

```bash
# Check weekly performance
sqlite3 database/wallets.db "
SELECT
  DATE(submitted_at) as date,
  COUNT(*) as orders,
  SUM(size_usd) as volume,
  SUM(CASE WHEN status='FILLED' THEN 1 ELSE 0 END) as filled,
  ROUND(AVG(CASE WHEN status='FILLED' THEN 1 ELSE 0 END) * 100, 2) as success_rate
FROM orders
WHERE submitted_at >= DATE('now', '-7 days')
GROUP BY DATE(submitted_at)
ORDER BY date DESC;
"
```

### Monitor Best Wallets

```bash
# Which wallets generate most profitable signals?
sqlite3 database/wallets.db "
SELECT
  w.address,
  COUNT(o.id) as signals_generated,
  SUM(o.size_usd) as total_volume,
  AVG(o.size_usd) as avg_trade_size
FROM wallets w
JOIN orders o ON o.wallet_id = w.id
WHERE o.status = 'FILLED'
GROUP BY w.id
ORDER BY total_volume DESC
LIMIT 10;
"
```

---

## 🚨 Safety & Risk Management

### Paper Trading (Current Mode)

**✅ You are in PAPER TRADING mode:**
- All orders go to WooLive (WOO X testnet)
- Using fake money (no risk)
- Can test for weeks/months safely
- Perfect for learning and optimization

**Stay in paper trading until:**
- [ ] Tested for minimum 2-4 weeks
- [ ] Success rate consistently > 50%
- [ ] Understand all risks
- [ ] Optimized parameters
- [ ] Comfortable with system behavior

### Switching to Live Trading

⚠️ **ONLY after extensive paper trading!**

**Requirements:**
1. Minimum 2-4 weeks paper trading
2. 100+ executed orders
3. Consistent profitability
4. No system errors
5. Full understanding of risks

**How to switch:**
1. Change `config/profitview_config.json`:
   ```json
   {
     "mode": "live"
   }
   ```
2. In ProfitView, change WooLive to LIVE WOO X
3. Use LIVE WOO X API credentials
4. **Start with VERY SMALL positions**
5. Monitor extremely closely

**Live trading safety:**
```json
{
  "safety": {
    "max_order_size_usd": 100,  // Start SMALL!
    "daily_loss_limit_usd": 500
  }
}
```

---

## 📋 Quick Command Reference

```bash
# Installation
pip install -r requirements.txt

# Test ProfitView connection
python scripts/profitview_executor.py

# Run demo
python main.py --demo

# Discover wallets (10-15 min)
python wallet_discovery.py

# Initialize database
python init_database.py

# Start monitoring (runs continuously)
python main.py

# Monitor specific wallet
python wallet_analyzer.py --wallet 0x123...

# Check database
sqlite3 database/wallets.db "SELECT * FROM orders LIMIT 5;"

# Check statistics
sqlite3 database/wallets.db "SELECT status, COUNT(*) FROM orders GROUP BY status;"
```

---

## 🎯 Summary - Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Test ProfitView
python scripts/profitview_executor.py
# ✅ Should execute test order

# 3. Run demo
python main.py --demo
# ✅ Should show complete workflow

# 4. Discover wallets
python wallet_discovery.py
# ⏱️ Takes 10-15 minutes
# ✅ Creates discovered_wallets.csv

# 5. Import to database
python init_database.py
# ✅ Loads wallets into database

# 6. Start monitoring
python main.py
# ✅ Monitors wallets and copies trades
# Press Ctrl+C to stop
```

---

## ❓ FAQ

**Q: How many wallets will I find?**
A: Typically 10-50 profitable wallets per discovery run.

**Q: How often do wallets trade?**
A: Varies. Active wallets: multiple trades per day. Some wallets: once per week.

**Q: What's the minimum account size?**
A: For paper trading: no minimum. For live: recommend $5,000+ for proper diversification.

**Q: Can I add my own wallets?**
A: Yes! Add them to `discovered_wallets.csv` then run `python init_database.py`.

**Q: How do I stop the bot?**
A: Press `Ctrl+C` in terminal. Or stop ProfitView bot in dashboard.

**Q: Is this profitable?**
A: Paper trading lets you test without risk. Past performance doesn't guarantee future results. Always start small when going live.

**Q: What exchanges are supported?**
A: Currently: Uniswap, PancakeSwap, SushiSwap (Ethereum DEXes). Can be extended.

**Q: Can I use multiple ProfitView accounts?**
A: Yes, just create separate config files and run multiple instances.

---

## 🚀 You're Ready!

**Everything is set up. Now:**

1. Run `python scripts/profitview_executor.py` to test
2. Run `python main.py --demo` to see full workflow
3. Run `python wallet_discovery.py` to find profitable wallets
4. Run `python main.py` to start copying their trades!

**Good luck with your trading! 📈**
