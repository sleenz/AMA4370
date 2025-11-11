# ProfitView Bot Deployment Guide

**IMPORTANT:** To use ProfitView for trade execution, you need to deploy a bot ON the ProfitView platform. This guide shows you how.

---

## Understanding ProfitView Architecture

ProfitView works differently than you might expect:

**❌ What ProfitView is NOT:**
- Not a simple webhook receiver API
- Not like TradersPost where you just send POST requests

**✅ What ProfitView IS:**
- A platform where you DEPLOY Python trading bots
- Your bot runs 24/7 on their infrastructure
- Your bot has webhook endpoints that YOU define
- You send signals TO your deployed bot
- Your bot executes trades on exchanges

**Architecture:**
```
Your Wallet Monitor Bot (local)
    ↓
    Sends webhook POST request
    ↓
Your ProfitView Bot (deployed on profitview.net)
    ↓
    Executes trade on exchange
    ↓
WOO X Exchange (WooLive - paper trading)
```

---

## Your Credentials

**ProfitView API Key (Webhook Secret):**
```
517b3bcac35bc86e1bea1ec31101b9b583b34387
```

**WooLive Paper Trading API:**
```
d8e4c5eb-d3b0-4f4f-a201-7c51e0444434
```

**Webhook URLs (after deployment):**
```
Execute Order:  https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/execute_order
Get Positions:  https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_positions
Get P&L:        https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_pnl
Get Status:     https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_status
```

---

## Step-by-Step Deployment

### Step 1: Access ProfitView Trading Platform

1. **Log in to ProfitView:**
   - URL: https://profitview.net/trading
   - Use your premium account credentials

2. **Navigate to Bots:**
   - Look for "Bots" or "Scripts" section
   - Or "Code Editor" / "IDE" area

### Step 2: Create New Bot

1. **Click "New Bot"** or "+" button

2. **Name your bot:**
   ```
   Wallet Copy Executor
   ```

3. **Select bot type:**
   - Choose "Python Bot" or "Custom Bot"
   - Choose "Futures Trading" if asked

### Step 3: Paste Bot Code

1. **Open the bot code file:**
   ```bash
   cat profitview_bot.py
   ```

2. **Copy the ENTIRE contents** of `profitview_bot.py`

3. **Paste into ProfitView editor:**
   - Clear any template code
   - Paste your bot code
   - Code should be ~400 lines

### Step 4: Configure Exchange Connection

1. **Find "Exchange Settings" or "Venues"** in ProfitView

2. **Add WooLive connection:**
   - Exchange: WOO X or WooLive
   - API Key: `d8e4c5eb-d3b0-4f4f-a201-7c51e0444434`
   - Enable "Paper Trading" or "Testnet"
   - Enable "Futures" trading

3. **Test connection:**
   - Click "Test Connection" or similar
   - Should show "Connected" or green checkmark

### Step 5: Save and Start Bot

1. **Save the bot:**
   - Click "Save" button
   - Wait for confirmation

2. **Start the bot:**
   - Click "Start" or "Run" button
   - Bot status should change to "Running" (green)

3. **Check console/logs:**
   - Look for:
     ```
     🤖 Wallet Copy Bot initialized for WooLive
     📝 Paper Trading Mode Active
     ```

### Step 6: Get Webhook URLs

1. **Find webhook URLs:**
   - Look for ⚡ (bolt) icon in editor
   - Or "Webhooks" section
   - Or "API Endpoints" section

2. **Your URLs should be:**
   ```
   https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/execute_order
   https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_positions
   https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_pnl
   https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_status
   ```

3. **Verify the webhook secret matches:**
   - Should contain: `517b3bcac35bc86e1bea1ec31101b9b583b34387`
   - This is your authentication

---

## Step 7: Test the Integration

### Test from your local machine:

```bash
# Test connection
python scripts/profitview_executor.py
```

**Expected output:**
```
📝 PAPER TRADING MODE ACTIVE
════════════════════════════════════════════════════════════
• All orders are simulated
• View results in ProfitView dashboard
• No real money at risk
• Perfect for testing and validation
════════════════════════════════════════════════════════════

🧪 Testing ProfitView Connection...

📋 Test 1: Query open positions
📊 Retrieved 0 open positions from ProfitView

📋 Test 2: Query P&L
💰 P&L Summary:
   Total P&L: $0.00
   Realized P&L: $0.00
   Unrealized P&L: $0.00

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

📊 Test Result:
════════════════════════════════════════════════════════════
  ✓ Success: True
  ✓ Order ID: WCT_999_1699876543210
  ✓ Status: FILLED
```

### Check ProfitView Dashboard:

1. **View bot logs:**
   - Should show "Order executed" messages
   - Check for any errors

2. **View WooLive account:**
   - Open positions should show test order
   - Balance should reflect paper trade

---

## Troubleshooting

### Issue 1: "Bot not found" or 404 errors

**Possible causes:**
- Bot not started
- Webhook secret mismatch
- Bot crashed

**Solutions:**
1. Check bot status in ProfitView (should be "Running")
2. Restart bot if needed
3. Verify webhook URL matches exactly
4. Check bot logs for errors

### Issue 2: "Exchange connection error"

**Possible causes:**
- WooLive not connected
- API key invalid
- Paper trading not enabled

**Solutions:**
1. Go to ProfitView → Exchange Settings
2. Check WooLive connection is active (green)
3. Re-enter WooLive API: `d8e4c5eb-d3b0-4f4f-a201-7c51e0444434`
4. Ensure "Paper Trading" is enabled
5. Test connection

### Issue 3: "Order validation failed"

**Possible causes:**
- Position size too small/large
- Leverage too high
- Invalid symbol

**Solutions:**
1. Check bot logs in ProfitView
2. Adjust safety limits in bot code:
   ```python
   MAX_ORDER_SIZE_USD = 10000
   MIN_ORDER_SIZE_USD = 10
   MAX_LEVERAGE = 25
   ```
3. Save and restart bot

### Issue 4: "Insufficient balance"

**For paper trading:**
- WooLive should provide test funds automatically
- Check WooLive account balance
- May need to request test funds from WOO X support

**Solutions:**
1. Log into WooLive directly
2. Check paper trading balance
3. Contact WOO X support for test funds

### Issue 5: Bot crashes or stops

**Check bot logs for:**
- Python errors
- Exchange API errors
- Rate limiting issues

**Solutions:**
1. Fix any code errors
2. Restart bot in ProfitView
3. Check exchange connection
4. Reduce order frequency if rate limited

---

## Monitoring Your Bot

### ProfitView Dashboard

**Bot Status:**
- Shows "Running" (green) when active
- Shows "Stopped" (red) if crashed
- Click bot name to view logs

**Bot Logs:**
- Real-time console output
- Shows order execution messages
- Displays errors and warnings

**Statistics:**
- Orders executed count
- Total volume
- Success/failure rates

### WooLive Dashboard

**Access:**
- Log into WOO X with your paper trading account
- Navigate to Futures trading

**View:**
- Open positions
- Order history
- P&L (realized/unrealized)
- Balance

---

## Configuration Changes

### To adjust safety limits:

1. **Edit bot code in ProfitView**
2. **Find Config class:**
   ```python
   class Config:
       MAX_ORDER_SIZE_USD = 10000  # Change this
       MIN_ORDER_SIZE_USD = 10     # And this
       MAX_LEVERAGE = 25            # And this
   ```
3. **Save changes**
4. **Restart bot**

### To switch from paper to live:

⚠️  **WARNING: This uses REAL MONEY!**

1. **Stop the bot**
2. **Change venue to live WOO X**
3. **Use LIVE WOO X API credentials**
4. **Update bot code if needed**
5. **Test with ONE small order first**
6. **Monitor very closely**

---

## Next Steps After Deployment

### 1. Verify Bot is Running

- Check status: "Running" (green)
- Check logs: No errors
- Test with: `python scripts/profitview_executor.py`

### 2. Test Order Execution

```bash
python scripts/profitview_executor.py
```

Should execute test order successfully.

### 3. Integrate with Your Wallet Monitor

```python
from scripts.profitview_executor import ProfitViewExecutor

# Initialize
executor = ProfitViewExecutor()

# Send signals from your wallet analyzer
position = {
    'wallet_id': 1,
    'pair': 'BTC/USDT',
    'side': 'BUY',
    'size_usd': 100,
    'quantity': 0.002,
    'leverage': 5,
    'entry_price': 50000,
    'stop_loss_price': 49000
}

result = executor.send_order(position)
```

### 4. Monitor for 1-2 Weeks

- Paper trade with real wallet signals
- Monitor execution quality
- Check P&L accuracy
- Verify stop losses work
- Refine parameters

### 5. Go Live (When Ready)

- Switch to live WOO X
- Start with SMALL positions
- Monitor extremely closely
- Scale gradually

---

## Support

**ProfitView Support:**
- Website: https://profitview.net
- Support: support@profitview.net
- Community: Check ProfitView Discord/Telegram

**WOO X Support:**
- Website: https://x.woo.org
- Paper Trading: https://support.woo.org
- Help: support@woo.org

**Bot Issues:**
- Check bot logs in ProfitView
- Review `profitview_bot.py` code
- Test with `python scripts/profitview_executor.py`

---

## Quick Reference

**Bot File:** `profitview_bot.py` (400 lines)

**Config File:** `config/profitview_config.json`

**Executor Script:** `scripts/profitview_executor.py`

**Test Command:**
```bash
python scripts/profitview_executor.py
```

**Webhook URLs:**
```
Execute: https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/execute_order
Status:  https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_status
```

---

## Summary

**What you need to do:**

1. ✅ Log into ProfitView (profitview.net/trading)
2. ✅ Create new bot named "Wallet Copy Executor"
3. ✅ Paste code from `profitview_bot.py`
4. ✅ Configure WooLive connection (API: `d8e4c5eb-d3b0-4f4f-a201-7c51e0444434`)
5. ✅ Start the bot (status: "Running")
6. ✅ Test with `python scripts/profitview_executor.py`
7. ✅ Monitor logs and check orders execute

**Your credentials are already configured in:**
- `config/profitview_config.json` (local)
- `profitview_bot.py` (for ProfitView deployment)

**Ready to deploy!** 🚀

Follow the steps above and let me know if you encounter any issues.
