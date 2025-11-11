# Binance Integration Setup Guide

**Direct Binance Futures API Integration - FREE Paper Trading**

Complete guide for setting up Binance testnet (paper trading) and live trading.

---

## Why Binance Instead of ProfitView?

✅ **FREE** - No subscription costs ($0 vs $29-299/month)
✅ **Simple** - Direct API, no middleman
✅ **Fast** - Lower latency (direct exchange connection)
✅ **Flexible** - Easy to switch exchanges later
✅ **Proven** - Used by thousands of traders worldwide

**Same features as ProfitView integration:**
- Paper trading (via testnet)
- Live trading
- Order validation
- Database audit trail
- P&L tracking
- Position monitoring

---

## Quick Start (5 Minutes)

###Step 1: Create Binance Testnet Account (FREE)

1. **Visit Binance Futures Testnet:**
   - URL: https://testnet.binancefuture.com
   - Click "Register" (top right)

2. **Create Account:**
   - Enter email
   - Set password
   - Verify email (check spam folder)
   - **No KYC required for testnet!**

3. **Get FREE Test Funds:**
   - Log into testnet account
   - You'll receive **10,000 USDT** in test funds automatically
   - These are fake funds - perfect for paper trading!

### Step 2: Generate API Keys

1. **Access API Management:**
   - Log into https://testnet.binancefuture.com
   - Click your email (top right) → "API Management"

2. **Create New API Key:**
   - Click "Create API"
   - Label: "Wallet Copy Bot"
   - **IMPORTANT:** Enable "Futures" permissions
   - Click "Create"

3. **Save Your Keys:**
   ```
   API Key: xxxxxxxxxxxxxxxxxxxxxxxxxxx
   Secret Key: yyyyyyyyyyyyyyyyyyyyyyyyyyyy
   ```
   ⚠️  **Save these securely - you'll need them in Step 3**

### Step 3: Configure the Bot

1. **Install Dependencies:**
   ```bash
   pip install python-binance
   ```

2. **Copy Configuration Template:**
   ```bash
   cp config/binance_config.example.json config/binance_config.json
   ```

3. **Add Your API Keys:**
   ```bash
   nano config/binance_config.json
   ```

   Update these lines:
   ```json
   {
     "mode": "testnet",
     "api_key": "YOUR_API_KEY_FROM_STEP_2",
     "api_secret": "YOUR_SECRET_KEY_FROM_STEP_2"
   }
   ```

   Save and exit (Ctrl+O, Enter, Ctrl+X)

### Step 4: Test the Connection

```bash
python scripts/binance_executor.py
```

**Expected Output:**
```
📝 TESTNET MODE ACTIVE (Paper Trading)
════════════════════════════════════════════════════════════
• All orders are on Binance Testnet
• Using FREE test USDT
• No real money at risk
• Perfect for testing and validation
• Real-time market data
════════════════════════════════════════════════════════════

🧪 Testing Binance Connection...

📋 Test 1: Query account balance
💰 Account Balance:
   Total Balance: $10,000.00
   Available: $10,000.00
   Unrealized P&L: $0.00

📋 Test 2: Query open positions
📊 Retrieved 0 open positions from Binance

📋 Test 3: Send test order (testnet)
📤 Sending order to Binance (attempt 1/3)
   Mode: TESTNET
   Symbol: BTCUSDT
   Side: BUY
   Quantity: 0.001
   Leverage: 1x
✅ Order executed successfully
   Order ID: WCT_999_1699876543210
   Exchange Order ID: 12345678
   Filled Price: $50,050.25
   Filled Quantity: 0.001

📍 Placing stop loss at $49,000.00
✅ Stop loss placed: Order ID 12345679

✅ Connection test complete - ORDER EXECUTED!
```

**If you see this, you're ready to go! 🎉**

---

## Configuration Options

### Testnet Mode (Paper Trading) - Default

```json
{
  "mode": "testnet",
  "api_key": "your_testnet_key",
  "api_secret": "your_testnet_secret",

  "exchange_settings": {
    "exchange": "binance",
    "account_type": "futures",
    "default_leverage": 10,
    "max_leverage": 25,
    "testnet_enabled": true
  }
}
```

**Features:**
- ✅ FREE test USDT (10,000 default)
- ✅ Real-time market data
- ✅ Realistic fills and slippage
- ✅ No risk
- ✅ Perfect for testing strategies

### Live Mode (Real Trading)

⚠️  **DANGER: Real money will be used!**

```json
{
  "mode": "live",
  "api_key": "your_LIVE_binance_key",
  "api_secret": "your_LIVE_binance_secret",

  "exchange_settings": {
    "testnet_enabled": false  // ← IMPORTANT
  },

  "safety": {
    "require_confirmation_for_live": true,
    "max_order_size_usd": 100,  // Start SMALL!
    "daily_loss_limit_usd": 500
  }
}
```

**Before switching to live:**
- [ ] Tested on testnet for 1-2 weeks
- [ ] Success rate > 50%
- [ ] Verified stop losses work
- [ ] Set small position sizes
- [ ] Have real Binance account with funds
- [ ] Generated LIVE API keys (not testnet)

---

## Safety Features

### Order Validation

**Every order is validated before sending:**

```python
# Checks performed:
✓ Minimum size: $10
✓ Maximum size: $10,000 (configurable)
✓ Leverage limit: 25x max (configurable)
✓ Stop loss sanity: Below entry for LONG, above for SHORT
✓ Account balance sufficient
```

**Example rejection:**
```
❌ Order rejected: Order too small: $5.00 < $10.00
```

### Live Mode Confirmation

When switching to live mode, explicit confirmation required:

```
⚠️  LIVE TRADING MODE DETECTED
════════════════════════════════════════════════════════════
This will execute REAL trades with REAL money!
All orders will be sent to the actual Binance exchange.

Type 'I CONFIRM LIVE TRADING' to proceed: _
```

**Must type exactly:** `I CONFIRM LIVE TRADING`

### Database Audit Trail

Every order logged to `database/wallets.db`:

```sql
SELECT * FROM orders ORDER BY submitted_at DESC LIMIT 5;
```

**Logged data:**
- Order ID, wallet ID, exchange
- Symbol, side, size, leverage
- Expected vs executed price
- Status (PENDING/FILLED/REJECTED/FAILED)
- Complete API request and response
- Timestamps
- Mode (testnet/live)

---

## Usage Examples

### Basic Order Execution

```python
from scripts.binance_executor import BinanceExecutor

# Initialize (defaults to testnet mode)
executor = BinanceExecutor()

# Prepare order
position = {
    'wallet_id': 1,
    'pair': 'BTC/USDT',
    'side': 'BUY',
    'size_usd': 100.0,
    'quantity': 0.002,
    'leverage': 5,
    'entry_price': 50000,  # Estimate (actual price from market)
    'stop_loss_price': 49000
}

# Execute
result = executor.send_order(position)

if result.success:
    print(f"✅ Order filled at ${result.filled_price:,.2f}")
else:
    print(f"❌ Order failed: {result.error_message}")
```

### Query Positions

```python
# Get all open positions
positions = executor.get_open_positions()

for pos in positions:
    symbol = pos['symbol']
    qty = float(pos['positionAmt'])
    pnl = float(pos['unRealizedProfit'])
    print(f"{symbol}: {qty:+.4f} BTC | P&L: ${pnl:+,.2f}")
```

### Get Account Balance

```python
balance = executor.get_account_balance()

print(f"Total: ${balance['totalBalance']:,.2f}")
print(f"Available: ${balance['availableBalance']:,.2f}")
print(f"P&L: ${balance['unrealizedPnl']:+,.2f}")
```

### Check Statistics

```python
stats = executor.get_statistics()

print(f"Mode: {stats['mode']}")
print(f"Orders: {stats['orders_submitted']}")
print(f"Filled: {stats['orders_filled']}")
print(f"Success Rate: {stats['success_rate']:.1%}")
```

---

## Binance Testnet Features

### What Works on Testnet

✅ **Real-time market data** - Actual BTC, ETH, etc. prices
✅ **Order execution** - Market, limit, stop orders
✅ **Position tracking** - Long/short, leverage up to 125x
✅ **P&L calculation** - Realized and unrealized
✅ **Funding fees** - Realistic futures funding
✅ **Liquidation** - If leverage too high and price moves against you

### What's Different from Live

⚠️  **Test funds** - Not real money (can't withdraw)
⚠️  **Order book depth** - May have less liquidity
⚠️  **No trading fees** - Testnet is free

### Getting More Test Funds

If you run out of test USDT:
1. Create new testnet account (different email)
2. Generate new API keys
3. Update config

Or contact Binance testnet support for a refill.

---

## Switching from Testnet to Live

### Prerequisites Checklist

**Before going live:**
- [ ] Tested on testnet for minimum 1-2 weeks
- [ ] Made at least 50+ testnet trades
- [ ] Success rate above 50%
- [ ] Stop losses working correctly
- [ ] No API errors or timeouts
- [ ] Comfortable with the system

### Step-by-Step Process

**1. Create LIVE Binance Account**
- Visit https://www.binance.com (NOT testnet)
- Complete KYC verification
- Deposit funds (start small!)

**2. Generate LIVE API Keys**
- Binance.com → Profile → API Management
- Create new API key
- **IMPORTANT:** Enable "Futures" permissions
- Save API key and secret

**3. Update Configuration**
```bash
nano config/binance_config.json
```

Change:
```json
{
  "mode": "live",  // ← Changed from "testnet"
  "api_key": "LIVE_API_KEY",  // ← LIVE key, not testnet
  "api_secret": "LIVE_SECRET",  // ← LIVE secret

  "exchange_settings": {
    "testnet_enabled": false  // ← IMPORTANT!
  },

  "safety": {
    "max_order_size_usd": 100  // ← Start SMALL!
  }
}
```

**4. Test with ONE Small Order**
```bash
python scripts/binance_executor.py
```

- Confirm prompt appears
- Execute one $10-20 order
- Verify it appears in Binance app
- Check P&L calculation
- Verify stop loss placed

**5. Monitor Closely**
- Watch first 10 trades carefully
- Check fills match expectations
- Ensure stop losses execute
- Monitor for any errors

**6. Gradually Increase Size**
After 50+ successful trades:
- Increase max_order_size_usd by 50%
- Monitor for 1 week
- Repeat until target size

---

## Monitoring & Dashboards

### Binance Web Interface

**Testnet Dashboard:**
- URL: https://testnet.binancefuture.com
- View: Open positions, order history, P&L
- Charts: TradingView integration

**Live Dashboard:**
- URL: https://www.binance.com/en/futures
- Same features as testnet
- Real-time P&L tracking
- Notifications for fills

### Binance Mobile App

**Download:**
- iOS: App Store → "Binance"
- Android: Play Store → "Binance"

**Features:**
- Push notifications for orders
- Live P&L tracking
- Position management
- Emergency position close

### Database Queries

**Check recent orders:**
```sql
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
```sql
sqlite3 database/wallets.db "
SELECT
  status,
  COUNT(*) as count,
  ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 2) as percentage
FROM orders
GROUP BY status;
"
```

---

## Troubleshooting

### Issue 1: "Configuration file not found"

**Error:**
```
FileNotFoundError: Configuration file not found: config/binance_config.json
```

**Solution:**
```bash
cp config/binance_config.example.json config/binance_config.json
nano config/binance_config.json  # Add your API keys
```

### Issue 2: "API key invalid" or 401 Unauthorized

**Possible Causes:**
- Wrong API key/secret
- Testnet key used for live (or vice versa)
- API key missing "Futures" permissions

**Solution:**
1. Verify keys in Binance testnet/live account
2. Check mode matches keys (testnet keys only work on testnet)
3. Regenerate API keys with "Futures" enabled
4. Update config/binance_config.json

### Issue 3: "Insufficient balance"

**In Testnet:**
- Create new testnet account
- Get fresh 10,000 USDT

**In Live:**
- Deposit more funds to Binance
- Transfer from Spot to Futures wallet
- Reduce order size

### Issue 4: Orders rejected - "Invalid quantity"

**Cause:** Binance has minimum quantity requirements per symbol

**Solution:**
```python
# For BTC/USDT, minimum is usually 0.001 BTC
# For ETH/USDT, minimum is usually 0.01 ETH

position['quantity'] = 0.001  # BTC minimum
```

Check Binance symbol info for exact minimums.

### Issue 5: "python-binance not installed"

**Error:**
```
ModuleNotFoundError: No module named 'binance'
```

**Solution:**
```bash
pip install python-binance
```

Or install all dependencies:
```bash
pip install -r requirements.txt
```

---

## Best Practices

### Position Sizing

**Testnet (learning):**
```json
{
  "max_order_size_usd": 1000  // $1000 max per order
}
```

**Live (starting):**
```json
{
  "max_order_size_usd": 100  // $100 max - start SMALL!
}
```

**Live (experienced):**
```json
{
  "max_order_size_usd": 5000  // After 100+ successful trades
}
```

### Leverage Guidelines

**Testnet:**
- Test with 1x, 5x, 10x, 25x
- Learn how leverage affects P&L
- Understand liquidation prices

**Live:**
- Start with 1-2x leverage ONLY
- Increase gradually after experience
- Never exceed 10x unless very experienced
- Remember: Higher leverage = higher risk

### Stop Loss Strategy

**Always use stop losses:**
```python
position = {
    'entry_price': 50000,
    'stop_loss_price': 49000,  # 2% risk
}
```

**Calculate risk:**
```
Risk per trade = (Entry - Stop Loss) * Quantity
Max risk = 1-2% of account balance
```

### Daily Limits

```json
{
  "safety": {
    "max_order_size_usd": 1000,
    "daily_loss_limit_usd": 500  // Stop trading if lose $500/day
  }
}
```

---

## FAQ

**Q: Is testnet realistic?**
A: Yes! Real market data, realistic fills, actual order book dynamics.

**Q: Can I withdraw testnet profits?**
A: No - testnet uses fake USDT. It's only for practice.

**Q: How long should I paper trade?**
A: Minimum 1-2 weeks, ideally 1 month with 100+ trades.

**Q: What's the minimum deposit for live trading?**
A: Start with $500-1000. This allows proper position sizing.

**Q: Are there trading fees?**
A: Testnet: No fees. Live: 0.02% maker, 0.04% taker (varies by VIP level).

**Q: Can I use this for spot trading (not futures)?**
A: Currently configured for futures. Spot support can be added.

**Q: What's the maximum leverage?**
A: Binance allows up to 125x, but we limit to 25x for safety.

**Q: How do I check my testnet balance?**
A: Run `python scripts/binance_executor.py` or log into https://testnet.binancefuture.com

---

## Next Steps

1. ✅ **Create testnet account** (5 min)
   - https://testnet.binancefuture.com

2. ✅ **Generate API keys** (2 min)
   - Enable "Futures" permissions

3. ✅ **Configure bot** (3 min)
   - Copy config, add keys

4. ✅ **Test connection** (1 min)
   - `python scripts/binance_executor.py`

5. ✅ **Run paper trading** (1-2 weeks)
   - Test your strategies
   - Monitor performance
   - Refine parameters

6. ✅ **Switch to live** (when ready)
   - Follow safety checklist
   - Start with small sizes
   - Monitor closely

---

## Support & Resources

### Official Binance Resources
- **Testnet:** https://testnet.binancefuture.com
- **API Docs:** https://binance-docs.github.io/apidocs/futures/en
- **Support:** https://www.binance.com/en/support

### python-binance Library
- **GitHub:** https://github.com/sammchardy/python-binance
- **Docs:** https://python-binance.readthedocs.io

### Our Documentation
- **This Guide:** docs/BINANCE_SETUP.md
- **Integration Docs:** docs/PROFITVIEW_INTEGRATION.md (applicable architecture)
- **Code:** scripts/binance_executor.py

---

**Happy Trading! 🚀**

Remember: Always test on testnet first. Never risk more than you can afford to lose.
