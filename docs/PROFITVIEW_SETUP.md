# ProfitView Setup Guide

Complete guide for setting up ProfitView integration with the wallet copy trading bot.

---

## Table of Contents

1. [Account Setup](#account-setup)
2. [API Key Configuration](#api-key-configuration)
3. [Testing the Integration](#testing-the-integration)
4. [Dashboard Navigation](#dashboard-navigation)
5. [Paper Trading Verification](#paper-trading-verification)
6. [Monitoring & Performance](#monitoring--performance)
7. [Switching to Live Trading](#switching-to-live-trading)
8. [Troubleshooting](#troubleshooting)

---

## 1. Account Setup

### Prerequisites

- ProfitView account (profitview.net or profitview.app)
- Active subscription plan (Hobby $29/mo, Active Trader $59/mo, or Professional $299/mo)
- Binance account with API keys

### Initial Setup Steps

1. **Create ProfitView Account**
   - Visit: https://profitview.net or https://profitview.app
   - Sign up for an account
   - Choose subscription plan based on your needs

2. **Connect Exchange**
   - Navigate to Settings → Exchange Connections
   - Click "Add Exchange"
   - Select "Binance Futures"
   - Enter your Binance API credentials
   - **Important:** For paper trading, use testnet credentials

3. **Enable Paper Trading Mode**
   - Go to Settings → Trading Mode
   - Select "Paper Trading" or "Testnet"
   - Confirm the change
   - Verify "PAPER" badge appears in dashboard

---

## 2. API Key Configuration

### Getting Your ProfitView API Key

Your API key: `35f7db8ad962540d62cc274c7d108abd07701b25`

This key is already configured in `config/profitview_config.json`.

### Verify Configuration

Check that your configuration file exists:

```bash
cat config/profitview_config.json
```

Should show:
```json
{
  "mode": "paper_trade",
  "api_key": "35f7db8ad962540d62cc274c7d108abd07701b25",
  ...
}
```

### Security Notes

- ✅ `profitview_config.json` is in `.gitignore` (not committed to Git)
- ✅ Use `profitview_config.example.json` as template for team members
- ⚠️  Never share your API key publicly
- ⚠️  Regenerate key if compromised

---

## 3. Testing the Integration

### Quick Connection Test

Run the basic connection test:

```bash
python scripts/profitview_executor.py
```

**Expected Output:**
```
📝 PAPER TRADING MODE ACTIVE
════════════════════════════════════════════════════════════
• All orders are simulated
• View results in ProfitView dashboard
• No real money at risk
• Perfect for testing and validation
════════════════════════════════════════════════════════════

🧪 Testing ProfitView Connection...
📤 Sending test order to ProfitView (attempt 1/3)
   Mode: PAPER_TRADE
   Symbol: BTCUSDT
   Side: BUY
   Quantity: 0.0002
   Leverage: 1x
   Stop Loss: $49500

✅ Order executed successfully
   Order ID: WCT_999_1699876543210
```

### Comprehensive Test Suite

Run all integration tests:

```bash
python tests/test_profitview_integration.py
```

**This will test:**
1. ✅ API connection
2. ✅ Paper trading orders (5 small orders)
3. ✅ Order validation (reject invalid orders)
4. ✅ Rate limiting (15 rapid orders)
5. ✅ Error handling

**Expected Results:**
```
═══════════════════════════════════════════════════════════════════
TEST RESULTS SUMMARY
═══════════════════════════════════════════════════════════════════
1. API Connection Test: ✅ PASSED
2. Paper Trading Test: ✅ PASSED
3. Order Validation Test: ✅ PASSED
4. Rate Limiting Test: ✅ PASSED
5. Error Handling Test: ✅ PASSED

Overall: 5/5 tests passed (100%)
═══════════════════════════════════════════════════════════════════

🎉 ALL TESTS PASSED! ProfitView integration ready for use.
```

---

## 4. Dashboard Navigation

### Accessing the Dashboard

1. **Login to ProfitView**
   - URL: https://profitview.net/dashboard or https://profitview.app
   - Use your account credentials

2. **Dashboard Sections**

   **A. Positions View**
   - Location: Main dashboard → "Positions" tab
   - Shows: Open positions, entry price, current P&L, size
   - Filter: By exchange, symbol, or wallet

   **B. Order History**
   - Location: Dashboard → "Orders" tab
   - Shows: All executed orders with timestamps
   - Filter: By date, symbol, status

   **C. P&L Tracking**
   - Location: Dashboard → "Performance" or "P&L" tab
   - Shows:
     - Total P&L (realized + unrealized)
     - Realized P&L (closed positions)
     - Unrealized P&L (open positions)
     - Win rate, average profit/loss

   **D. Chart Integration**
   - Location: Main chart area
   - Shows: TradingView charts with position markers
   - Features: Entry/exit points, stop loss levels

### Dashboard Features

**Real-time Updates:**
- Position P&L updates every few seconds
- Order status changes appear immediately
- Balance updates after trades execute

**Notifications:**
- Order fills
- Stop loss hits
- Position opens/closes
- Account alerts

---

## 5. Paper Trading Verification

### How to Confirm Paper Trading Mode

**Method 1: Visual Indicators**
- Look for "PAPER" or "TESTNET" badge in top-right corner
- Account balance shows testnet funds (not real balance)
- Orders show "Simulated" or "Paper" tag

**Method 2: Check Settings**
```
Settings → Trading Mode → Should show "Paper Trading" selected
```

**Method 3: Verify in Code**
```bash
grep "mode" config/profitview_config.json
```
Should output: `"mode": "paper_trade"`

### Paper Trading Behavior

**What Happens in Paper Mode:**
- ✅ Orders sent to testnet exchange (Binance Testnet)
- ✅ Fills simulated based on real market prices
- ✅ No real money used
- ✅ Full dashboard functionality
- ✅ Realistic latency and slippage
- ✅ Practice risk management

**What Doesn't Happen:**
- ❌ No real exchange API calls
- ❌ No actual positions opened
- ❌ No real P&L impact
- ❌ No withdrawal capability

### Safety Checks

Before every session, verify:
```python
# In your code
executor = ProfitViewExecutor()
assert executor.mode == 'paper_trade', "Should be in paper trading mode"
```

Console will display mode on startup:
```
📝 PAPER TRADING MODE ACTIVE
```

---

## 6. Monitoring & Performance

### Key Metrics to Track

**1. Order Success Rate**
```python
stats = executor.get_statistics()
print(f"Success Rate: {stats['success_rate']:.1%}")
```

**2. P&L Tracking**
```python
pnl = executor.get_pnl_summary()
print(f"Total P&L: ${pnl['totalPnl']:.2f}")
print(f"Win Rate: {pnl['winRate']:.1%}")
```

**3. Position Monitoring**
```python
positions = executor.get_open_positions()
for pos in positions:
    print(f"{pos['symbol']}: ${pos['unrealizedPnl']:.2f}")
```

### Setting Up Alerts

**In ProfitView Dashboard:**
1. Navigate to Settings → Notifications
2. Enable desired alerts:
   - ✅ Order fills
   - ✅ Stop loss triggers
   - ✅ Profit targets hit
   - ✅ Daily loss limit reached

**Telegram Integration (Optional):**
1. Settings → Integrations → Telegram
2. Click "Connect Telegram Bot"
3. Follow instructions to link bot
4. Configure alert types

### Performance Reports

**Daily Summary:**
- Dashboard → Reports → Daily
- Shows: Trades, P&L, win rate, largest win/loss

**Weekly Review:**
- Dashboard → Reports → Weekly
- Shows: Performance trends, top pairs, strategy analysis

**Export Data:**
- Dashboard → Export → CSV/Excel
- Download trade history for external analysis

---

## 7. Switching to Live Trading

### ⚠️ **Critical - Read Carefully**

Switching to live mode means **REAL MONEY** will be used.

### Prerequisites Before Going Live

**1. Testing Requirements:**
- [ ] Ran paper trading for at least 1-2 weeks
- [ ] Success rate above 50%
- [ ] Understood all error scenarios
- [ ] Tested all edge cases
- [ ] Verified stop losses work correctly
- [ ] Reviewed all filled orders in dashboard

**2. Risk Management:**
- [ ] Set appropriate position sizes
- [ ] Configured daily loss limits
- [ ] Tested stop loss execution
- [ ] Reviewed leverage settings
- [ ] Prepared for worst-case scenarios

**3. Technical Validation:**
- [ ] All tests passing (100%)
- [ ] No API errors or timeouts
- [ ] Rate limiting working correctly
- [ ] Database logging functional
- [ ] Monitoring systems in place

### How to Switch to Live Mode

**Step 1: Update Configuration**
```bash
nano config/profitview_config.json
```

Change:
```json
{
  "mode": "live",  // ← Changed from "paper_trade"
  ...
}
```

**Step 2: Update Exchange to Live**

In ProfitView dashboard:
1. Settings → Exchange Connections
2. Remove testnet connection
3. Add **LIVE** Binance connection
4. Use **LIVE** API keys (not testnet)

**Step 3: Reduce Position Sizes**

Start with 10% of intended size:
```json
{
  "safety": {
    "max_order_size_usd": 1000,  // Start small!
    "daily_loss_limit_usd": 500
  }
}
```

**Step 4: Enable Confirmation Prompt**

Keep this enabled:
```json
{
  "safety": {
    "require_confirmation_for_live": true  // ← Must be true
  }
}
```

**Step 5: Run Live Mode**

```bash
python scripts/profitview_executor.py
```

You'll see:
```
⚠️  LIVE TRADING MODE DETECTED
════════════════════════════════════════════════════════════
This will execute REAL trades with REAL money!
All orders will be sent to the actual exchange.

Type 'I CONFIRM LIVE TRADING' to proceed:
```

Type exactly: `I CONFIRM LIVE TRADING`

**Step 6: Monitor Closely**

- Watch first 5-10 trades carefully
- Verify fills match expectations
- Check P&L is calculated correctly
- Ensure stop losses execute
- Monitor for any errors

**Step 7: Gradually Increase Size**

After 50+ successful trades:
- Increase max order size by 50%
- Monitor for 1 week
- Repeat until target size reached

### Emergency Stop

**To immediately stop all trading:**

```bash
# Method 1: Change config to paper_trade
sed -i 's/"live"/"paper_trade"/' config/profitview_config.json

# Method 2: Close all positions manually in dashboard
# Dashboard → Positions → Close All

# Method 3: Disable API key in ProfitView settings
# Settings → API Keys → Disable/Revoke
```

---

## 8. Troubleshooting

### Common Issues

#### Issue 1: "Configuration file not found"

**Error:**
```
FileNotFoundError: Configuration file not found: config/profitview_config.json
```

**Solution:**
```bash
cp config/profitview_config.example.json config/profitview_config.json
nano config/profitview_config.json  # Add your API key
```

#### Issue 2: "API key invalid" or 401 Unauthorized

**Possible Causes:**
- API key incorrect in config
- API key expired or revoked
- Wrong endpoint URL

**Solution:**
1. Verify API key in ProfitView account settings
2. Check key hasn't been revoked
3. Regenerate new API key if needed
4. Update `config/profitview_config.json`

#### Issue 3: Orders rejected - "Insufficient balance"

**In Paper Trading:**
- Check testnet account has funds
- Reset testnet balance in ProfitView settings

**In Live Trading:**
- Verify exchange account has sufficient balance
- Check margin/futures wallet (not spot wallet)
- Reduce position size

#### Issue 4: Rate limiting errors

**Error:**
```
429 Too Many Requests
```

**Solution:**
- Rate limiter should prevent this
- Increase delays in config:
```json
{
  "rate_limiting": {
    "requests_per_second": 5  // Reduce from 10
  }
}
```

#### Issue 5: Orders not appearing in dashboard

**Possible Causes:**
- Wrong exchange selected in dashboard filter
- Dashboard not refreshing
- Paper/live mode mismatch

**Solution:**
1. Refresh dashboard (F5)
2. Check exchange filter (select "Binance")
3. Verify mode matches (Paper vs Live)
4. Check order history tab (not just positions)

#### Issue 6: Stop loss not executing

**Check:**
1. Stop loss price is valid (below entry for LONG, above for SHORT)
2. Exchange supports stop loss orders
3. Stop loss order was accepted (check logs)
4. Market moved to trigger price

**Debug:**
```bash
# Check database logs
sqlite3 database/wallets.db "SELECT * FROM orders WHERE status='FILLED' ORDER BY submitted_at DESC LIMIT 5;"
```

### Getting Help

**1. Check Logs:**
```bash
# Database audit trail
sqlite3 database/wallets.db "SELECT * FROM orders ORDER BY submitted_at DESC LIMIT 10;"

# Python errors
python scripts/profitview_executor.py 2>&1 | tee executor_debug.log
```

**2. Run Diagnostics:**
```bash
python tests/test_profitview_integration.py
```

**3. Review Documentation:**
- ProfitView Docs: https://profitview.net/docs
- ProfitView Wiki: https://wiki.profitview.app
- API Research: `PROFITVIEW_API_RESEARCH.md`

**4. Contact Support:**
- ProfitView Support: support@profitview.net
- Community Discord: (check ProfitView website for link)

---

## Quick Reference

### File Locations

```
config/profitview_config.json       ← Your API key & settings
config/profitview_config.example.json ← Template for team
scripts/profitview_executor.py      ← Main executor class
tests/test_profitview_integration.py ← Test suite
database/wallets.db                 ← Order audit trail
docs/PROFITVIEW_SETUP.md           ← This guide
PROFITVIEW_API_RESEARCH.md         ← API documentation
```

### Key Commands

```bash
# Test connection
python scripts/profitview_executor.py

# Run full test suite
python tests/test_profitview_integration.py

# Check configuration
cat config/profitview_config.json | grep "mode"

# View recent orders
sqlite3 database/wallets.db "SELECT order_id, pair, side, status, size_usd FROM orders ORDER BY submitted_at DESC LIMIT 10;"

# Check statistics
sqlite3 database/wallets.db "SELECT status, COUNT(*) as count FROM orders GROUP BY status;"
```

### Safety Checklist

Before each trading session:

- [ ] Verify mode (paper vs live)
- [ ] Check API key is valid
- [ ] Review position size limits
- [ ] Test stop loss functionality
- [ ] Confirm daily loss limits
- [ ] Verify exchange connection
- [ ] Check account balance
- [ ] Review open positions

---

## Next Steps

1. ✅ Run connection test: `python scripts/profitview_executor.py`
2. ✅ Run full test suite: `python tests/test_profitview_integration.py`
3. ✅ Log into ProfitView dashboard and verify test orders
4. ✅ Review P&L tracking in dashboard
5. ✅ Run paper trading for 1-2 weeks
6. ✅ When ready, switch to live mode (carefully!)

---

**Good luck with your trading! 🚀**

For questions or issues, refer to the troubleshooting section above or contact ProfitView support.
