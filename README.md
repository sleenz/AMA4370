# Wallet Copy Trading Bot - Complete Guide

**What this does:** Monitors profitable Ethereum wallets and automatically copies their trades via ProfitView.

---

## Quick Start (After ProfitView Bot Deployment)

You've already deployed `profitview_bot.py` to ProfitView. Now on your computer:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your API keys
cp config/profitview_config.example.json config/profitview_config.json
# (Already done - your keys are configured)

# 3. Run the system
python main.py --demo
```

That's it! The bot will send a test order to your ProfitView bot.

---

## System Architecture

```
┌─────────────────────────────────────────────────┐
│ YOUR COMPUTER (This Repository)                 │
│                                                  │
│  1. wallet_discovery.py                         │
│     └─> Finds profitable wallets                │
│                                                  │
│  2. wallet_analyzer.py                          │
│     └─> Monitors wallet transactions            │
│                                                  │
│  3. signal_processor.py                         │
│     └─> Generates trading signals               │
│                                                  │
│  4. profitview_executor.py                      │
│     └─> Sends orders to ProfitView (webhook)    │
└─────────────────────────────────────────────────┘
                    ↓ HTTP POST
┌─────────────────────────────────────────────────┐
│ PROFITVIEW SERVERS                               │
│                                                  │
│  profitview_bot.py (YOU DEPLOYED THIS)          │
│  └─> Receives webhooks                          │
│  └─> Executes trades on WOO X                   │
└─────────────────────────────────────────────────┘
                    ↓ Trade Execution
┌─────────────────────────────────────────────────┐
│ WOO X EXCHANGE (WooLive - Paper Trading)        │
└─────────────────────────────────────────────────┘
```

---

## File Descriptions

### Core Trading System

**`wallet_discovery.py`** (300 lines)
- Discovers profitable wallets by scanning Ethereum blocks
- Filters wallets by: trade count, volume, recent activity
- Exports to `discovered_wallets.csv`
- **Run:** `python wallet_discovery.py`

**`wallet_analyzer.py`** (400 lines)
- Monitors wallet transactions in real-time
- Analyzes DEX trades (Uniswap, PancakeSwap, etc.)
- Calculates wallet performance metrics
- **Run:** `python wallet_analyzer.py --wallet 0x123...`

**`signal_processor.py`** (500 lines)
- Processes wallet trades into actionable signals
- Applies filters: minimum size, confidence score
- Calculates position sizing and risk
- Generates trading signals with entry/stop loss
- **Run:** Used by main.py (not standalone)

**`dex_parser.py`** (600 lines)
- Decodes DEX smart contract transactions
- Extracts: token pair, amount, price, direction
- Supports: Uniswap V2/V3, PancakeSwap, SushiSwap
- **Run:** Used by wallet_analyzer.py

### Execution Engines

**`scripts/profitview_executor.py`** (450 lines)
- **RUNS ON YOUR COMPUTER**
- Sends webhook requests TO your ProfitView bot
- Handles retry logic, validation, logging
- **Run:** `python scripts/profitview_executor.py` (test mode)

**`profitview_bot.py`** (400 lines)
- **RUNS ON PROFITVIEW SERVERS** (you deployed this)
- Receives webhook requests FROM profitview_executor.py
- Executes trades on WOO X via ProfitView
- **Run:** Already deployed and running on ProfitView

**`scripts/binance_executor.py`** (700 lines)
- Alternative: Direct Binance API integration (free)
- Use this if you want to skip ProfitView
- Supports testnet (paper trading) and live trading
- **Run:** `python scripts/binance_executor.py` (test mode)

### Main Entry Point

**`main.py`** (150 lines)
- Main program entry point
- Integrates all components
- Demo mode: Shows how everything works together
- **Run:** `python main.py --demo`

### Database & Setup

**`init_database.py`** (100 lines)
- Creates database schema
- Sets up tables: wallets, positions, orders
- **Run:** `python init_database.py` (auto-runs on first use)

**`update_database_schema.py`** (50 lines)
- Updates database schema if needed
- **Run:** Only if database structure changes

### Testing & Utilities

**`test_api_connectivity.py`** (100 lines)
- Tests Etherscan API connection
- Verifies API keys work
- **Run:** `python test_api_connectivity.py`

**`test_wallet_discovery.py`** (200 lines)
- Unit tests for wallet discovery
- **Run:** `pytest test_wallet_discovery.py`

**`test_wallet_analyzer.py`** (150 lines)
- Unit tests for wallet analyzer
- **Run:** `pytest test_wallet_analyzer.py`

**`test_signal_processor.py`** (100 lines)
- Unit tests for signal processor
- **Run:** `pytest test_signal_processor.py`

**`tests/test_profitview_integration.py`** (300 lines)
- Integration tests for ProfitView
- Tests order execution, validation, error handling
- **Run:** `python tests/test_profitview_integration.py`

**`debug_wallet_discovery.py`** (250 lines)
- Debug tool for wallet discovery
- Scans small number of blocks for testing
- **Run:** `python debug_wallet_discovery.py`

**`setup_test_data.py`** (100 lines)
- Creates test data for development
- **Run:** `python setup_test_data.py`

### Supporting Modules

**`trade_monitor.py`** (200 lines)
- Monitors ongoing trades
- Tracks P&L
- **Run:** Used by main.py

**`edge_case_handlers.py`** (150 lines)
- Handles edge cases in trade processing
- **Run:** Used by signal_processor.py

---

## Configuration Files

**`config/profitview_config.json`** (GITIGNORED - contains your keys)
```json
{
  "mode": "paper_trade",
  "api_key": "517b3bcac35bc86e1bea1ec31101b9b583b34387",
  "woolive_api_key": "d8e4c5eb-d3b0-4f4f-a201-7c51e0444434",
  "endpoints": {
    "paper_trade": "https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/execute_order",
    ...
  }
}
```

**`config/profitview_config.example.json`**
- Template for team members (no real keys)

**`config/binance_config.json`** (GITIGNORED)
- Binance API configuration (if using Binance instead)

**`config/binance_config.example.json`**
- Template for Binance setup

**`config/api_keys.json`** (GITIGNORED)
```json
{
  "etherscan_api_key": "YOUR_KEY",
  "bscscan_api_key": "YOUR_KEY"
}
```

**`config/config.json`**
- General system configuration
- Trading parameters, filters, risk management

---

## How to Run the System

### Option 1: Demo Mode (Test Everything)

```bash
python main.py --demo
```

**What it does:**
- Creates a test trading signal
- Sends it to your ProfitView bot
- Executes a test order on WooLive (paper trading)
- Shows results

**Expected output:**
```
📊 Demo Trading Signal:
   Pair: BTC/USDT
   Side: BUY
   Size: $100.00

🚀 Executing trade via ProfitView...
📤 Sending order to ProfitView...
✅ Order executed successfully
   Order ID: WCT_1_1699876543210
```

### Option 2: Discovery Mode (Find Wallets)

```bash
python wallet_discovery.py
```

**What it does:**
- Scans Ethereum blockchain for active traders
- Finds wallets with high volume and trade count
- Exports to `discovered_wallets.csv`
- Takes 10-15 minutes

**Output:**
- `discovered_wallets.csv` with profitable wallets

### Option 3: Monitor Mode (Watch Wallet)

```bash
python wallet_analyzer.py --wallet 0x28c6c06298d514db089934071355e5743bf21d60
```

**What it does:**
- Monitors specific wallet in real-time
- Analyzes each transaction
- Identifies DEX trades
- Generates signals when wallet trades

### Option 4: Full Production Mode

```bash
# 1. Discover wallets
python wallet_discovery.py

# 2. Load wallets into database
python init_database.py

# 3. Run the main loop (monitors all wallets)
python main.py
```

**What it does:**
- Monitors all discovered wallets continuously
- Generates signals when they trade
- Executes trades via ProfitView
- Logs everything to database

---

## What You Need to Do NOW

Since you've deployed the ProfitView bot, here's what to do on your computer:

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

**Installs:**
- requests (HTTP requests)
- web3 (Ethereum blockchain)
- eth-abi (Decode transactions)
- python-binance (optional, if using Binance)

### Step 2: Verify Configuration

Your keys are already configured in `config/profitview_config.json`. To verify:

```bash
# Check config exists
ls -la config/profitview_config.json

# Should NOT be in git (for security)
git status config/profitview_config.json
# Should say: "nothing to commit"
```

### Step 3: Test ProfitView Connection

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

📋 Test 3: Send test order (paper trading)
────────────────────────────────────────────────────────────
📤 Sending order to ProfitView (attempt 1/3)
   Mode: PAPER_TRADE
   Symbol: BTCUSDT
   Side: BUY
   Quantity: 0.002
   Leverage: 1x
✅ Order executed successfully
   Order ID: WCT_999_1699876543210
   Exchange Order ID: 12345678

✅ Connection test complete!
```

**If you see errors:**
- Check ProfitView bot is "Running" (status should be green)
- Check bot logs in ProfitView dashboard
- Verify WooLive connection is active
- Ensure webhook URLs match

### Step 4: Run Demo Mode

```bash
python main.py --demo
```

This shows how the full system works:
1. Creates a trading signal (simulated wallet trade)
2. Sends to ProfitView
3. Executes order
4. Shows results

### Step 5: Check Results

**In ProfitView:**
1. Open ProfitView dashboard
2. Check bot logs (should show "Order executed")
3. View WooLive positions (test order should appear)

**On your computer:**
```bash
# Check database
sqlite3 database/wallets.db "SELECT * FROM orders ORDER BY submitted_at DESC LIMIT 5;"
```

---

## Running the Full Algorithm

To run the complete wallet copy trading algorithm:

### Step 1: Discover Profitable Wallets

```bash
python wallet_discovery.py
```

- Takes 10-15 minutes
- Outputs: `discovered_wallets.csv`
- Finds ~10-50 wallets

### Step 2: Import Wallets to Database

```bash
python init_database.py
```

- Creates database if needed
- Imports wallets from CSV

### Step 3: Start Monitoring

```bash
python main.py
```

**This will:**
1. Load wallets from database
2. Monitor their transactions continuously
3. Analyze each trade
4. Generate signals when they match criteria
5. Send orders to ProfitView
6. ProfitView executes on WooLive
7. Log everything to database

**To stop:** Press Ctrl+C

### Step 4: Monitor Performance

**Check bot status:**
```bash
# ProfitView dashboard
# → Bot logs
# → WooLive positions
# → P&L tracking
```

**Check local database:**
```bash
sqlite3 database/wallets.db

# Recent orders
SELECT pair, side, size_usd, status FROM orders ORDER BY submitted_at DESC LIMIT 10;

# Success rate
SELECT status, COUNT(*) FROM orders GROUP BY status;

# Total volume
SELECT SUM(size_usd) FROM orders WHERE status='FILLED';
```

---

## Workflow Summary

```
┌──────────────────────────────────────────────┐
│ 1. DISCOVER WALLETS                          │
│    python wallet_discovery.py                │
│    → discovered_wallets.csv                  │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│ 2. IMPORT TO DATABASE                        │
│    python init_database.py                   │
│    → database/wallets.db                     │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│ 3. MONITOR & EXECUTE                         │
│    python main.py                            │
│    → Watches wallets                         │
│    → Generates signals                       │
│    → Sends to ProfitView                     │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│ PROFITVIEW BOT (you deployed)                │
│    Receives webhooks                         │
│    → Executes on WooLive                     │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│ WOO X WOOLIVE (Paper Trading)                │
│    Orders executed                           │
│    → P&L tracked                             │
└──────────────────────────────────────────────┘
```

---

## Troubleshooting

### Issue: "Module not found"

```bash
pip install -r requirements.txt
```

### Issue: "Configuration file not found"

Your config is already set up. If missing:
```bash
cp config/profitview_config.example.json config/profitview_config.json
# Then add your keys
```

### Issue: "Order rejected - HTTP 403"

**Check:**
1. Is ProfitView bot running? (status should be green)
2. Is webhook secret correct? (`517b3bcac35bc86e1bea1ec31101b9b583b34387`)
3. Is WooLive connected in ProfitView?

**Fix:**
1. Go to ProfitView dashboard
2. Check bot status → restart if needed
3. Check bot logs for errors
4. Verify WooLive connection is active

### Issue: "Database locked"

```bash
# Close any database connections
pkill -f sqlite3
# Or restart terminal
```

### Issue: "No wallets found"

```bash
# Run discovery again
python wallet_discovery.py

# Or use debug version (faster, 10 blocks only)
python debug_wallet_discovery.py
```

---

## Important Notes

### Paper Trading

**You're currently in PAPER TRADING mode:**
- All orders go to WooLive (WOO X testnet)
- No real money is used
- Perfect for testing and learning
- Can test for weeks/months safely

### Switching to Live Trading

⚠️ **WARNING: Only after extensive paper trading!**

1. Test on paper trading for 1-2 weeks minimum
2. Verify success rate > 50%
3. Understand all risks
4. Start with VERY SMALL positions
5. Change config mode to "live"
6. Use LIVE WOO X credentials (not WooLive)

### Security

**Your API keys are safe:**
- `config/profitview_config.json` is gitignored
- Never committed to GitHub
- Only example configs are in repo

### Performance

**System requirements:**
- Python 3.8+
- 1GB RAM minimum
- Stable internet connection
- Can run on any computer, VPS, or cloud

**Blockchain access:**
- Uses Etherscan API (free tier: 5 req/sec)
- Rate limiting built-in
- Retries on failures

---

## Quick Command Reference

```bash
# Test ProfitView connection
python scripts/profitview_executor.py

# Run demo
python main.py --demo

# Discover wallets
python wallet_discovery.py

# Monitor specific wallet
python wallet_analyzer.py --wallet 0x123...

# Full system
python main.py

# Check database
sqlite3 database/wallets.db "SELECT * FROM orders LIMIT 5;"

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest
```

---

## Support & Resources

**Configuration:**
- ProfitView Webhook Secret: `517b3bcac35bc86e1bea1ec31101b9b583b34387`
- WooLive Paper API: `d8e4c5eb-d3b0-4f4f-a201-7c51e0444434`
- Webhook URL: `https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/execute_order`

**ProfitView:**
- Dashboard: https://profitview.net/trading
- Your bot should be running there

**WOO X:**
- Paper Trading: WooLive (configured in your ProfitView bot)

**Getting Help:**
- Check ProfitView bot logs first
- Check local terminal output
- Check database: `sqlite3 database/wallets.db`

---

## Summary - What to Do Right Now

1. ✅ **ProfitView bot deployed** (you did this)

2. **On your computer:**
   ```bash
   # Install dependencies
   pip install -r requirements.txt

   # Test connection
   python scripts/profitview_executor.py

   # Run demo
   python main.py --demo
   ```

3. **Check results:**
   - ProfitView dashboard (bot logs, orders)
   - WooLive account (positions)

4. **Run the algorithm:**
   ```bash
   # Discover wallets
   python wallet_discovery.py

   # Start monitoring
   python main.py
   ```

**That's it!** The system is now running and will automatically copy trades from profitable wallets.

---

## Next Steps

After successful testing:
- Let it run for 1-2 weeks on paper trading
- Monitor performance daily
- Analyze which wallets are most profitable
- Refine filters and parameters
- When ready, can switch to live (very carefully!)

**Questions?** Check the troubleshooting section above or examine the ProfitView bot logs.
