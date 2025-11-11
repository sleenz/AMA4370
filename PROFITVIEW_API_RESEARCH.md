# ProfitView API Research Report

**Date:** 2025-11-11
**Purpose:** Research ProfitView API for trade execution integration with wallet copy trading bot

---

## Executive Summary

After comprehensive research, I've discovered that **ProfitView operates differently than initially assumed**. ProfitView is NOT a webhook-based order execution service like TradersPost. Instead, it's a **platform for deploying and running custom trading bots** on their infrastructure.

### Critical Finding ⚠️

**Your bot cannot send webhook orders TO ProfitView.** Instead, you would need to **deploy your bot ON ProfitView** where it runs 24/7 and connects directly to exchanges.

---

## Understanding ProfitView Architecture

### Two ProfitView Products

#### 1. **ProfitView Chrome Extension** (profitview.app)
- Browser-based tool
- Integrates with TradingView alerts
- Uses command syntax in alert messages
- **Use Case:** Manual/semi-automated trading with TradingView strategies
- **Pricing:** $29-$299/month

#### 2. **ProfitView Trading Bot Platform** (profitview.net)
- Python-based bot hosting platform
- Deploy custom bots that run 24/7
- Direct exchange API connections
- **Use Case:** Fully automated custom trading strategies
- **Pricing:** Unknown (check profitview.net)

---

## How ProfitView Works

### Traditional Webhook Service (What We Expected)
```
Your Bot → Webhook POST → Service API → Exchange
                        ↑
                   (Like TradersPost)
```

### How ProfitView Actually Works
```
Your Bot Code → Deployed on ProfitView → Direct Exchange Connection
                ↑
           (Bot runs on their infrastructure)
```

---

## ProfitView Trading Bot Platform Details

### API Methods Available (Inside Your Bot)

When you deploy a bot ON ProfitView, you have access to these methods:

#### Order Management
```python
# Create market order
self.create_market_order(
    venue="Binance",      # Exchange name
    sym="BTCUSDT",        # Trading pair
    side="Buy",           # Buy or Sell
    size=0.001            # Quantity
)

# Create limit order
self.create_limit_order(
    venue="Binance",
    sym="BTCUSDT",
    side="Buy",
    size=0.001,
    price=50000.0
)

# Cancel order
self.cancel_order(venue="Binance", order_id="12345", sym="BTCUSDT")

# Amend order
self.amend_order(venue="Binance", order_id="12345", size=0.002, price=51000.0)
```

#### Account Queries
```python
# Get balances
balances = self.fetch_balances(venue="Binance")

# Get open orders
orders = self.fetch_open_orders(venue="Binance")

# Get positions
positions = self.fetch_positions(venue="Binance")

# Get candle data
candles = self.fetch_candles(venue="Binance", sym="BTCUSDT", level="1m", since=timestamp)
```

#### Custom Webhook Endpoints (For Receiving Signals)

You can create webhooks IN your bot to receive external signals:

```python
@http.route
def post_execute_trade(self, data):
    """
    Webhook endpoint: https://profitview.net/trading/bot/WEBHOOK_SECRET/execute_trade

    Receives trade signals and executes them
    """
    pair = data['pair']
    side = data['side']
    quantity = data['quantity']

    result = self.create_market_order(
        venue=data['exchange'],
        sym=pair.replace('/', ''),  # BTC/USDT → BTCUSDT
        side=side,
        size=quantity
    )

    return result
```

### Authentication

#### Webhook Secret
- Unique per account
- Found in code editor navigation panel (bolt icon)
- Used in webhook URLs: `https://profitview.net/trading/bot/WEBHOOK_SECRET/method_name`

#### API Key (Your Key: `35f7db8ad962540d62cc274c7d108abd07701b25`)
- Found in Account Settings
- Used for:
  - Private websocket feeds: `wss://profitview.net/stream?token=YOUR_API_KEY`
  - Managing bots on the platform

#### Exchange API Keys
- You provide your exchange API keys to ProfitView
- Must have read/write permissions
- ProfitView uses them to execute trades on your behalf

---

## Paper Trading / Testnet Support

### ✅ GOOD NEWS: Full Testnet Support

ProfitView supports multiple exchange testnets **for FREE** (no license required):

#### Supported Testnets
- ✅ **Binance Futures Testnet**
- ✅ **BitMEX Testnet**
- ✅ **Bybit Testnet**
- ✅ **Coinbase Pro Sandbox**
- ✅ **Deribit Testnet**
- ✅ **Gemini Sandbox**
- ✅ **Kraken Futures Demo**
- ✅ **KuCoin Sandbox**
- ✅ **KuCoin Futures Sandbox**
- ✅ **OANDA Sandbox**
- ✅ **OKEX Demo**
- ✅ **Phemex Testnet**
- ✅ **SimpleFX Demo**

### How to Use Testnet

Simply configure your bot with testnet credentials:

```python
# Example: Bybit Testnet
venue = "bybit5-testnet"  # Instead of "bybit5"

# Or Binance Futures Testnet
venue = "binance-futures-testnet"  # Instead of "binance-futures"
```

**Recommendation:** "It is always recommended to use testnet/sandbox first!" - ProfitView Wiki

---

## Supported Exchanges

### Production Exchanges
- Binance (Spot, Margin, USD Futures, COIN Futures)
- Bybit (USDT, Futures, Spot, v5 API, Demo, UTA 2.0)
- Bitfinex (including Paper Trading & Derivatives)
- BitMEX
- Coinbase Advanced
- Deribit
- Kraken Futures
- KuCoin (Spot, Futures)
- OANDA
- OKX (all markets)
- Phemex
- SimpleFX

---

## Order Command Syntax (Chrome Extension)

For reference, if using the Chrome Extension with TradingView:

### Market Order with Leverage
```
cancel
long=25% leverage=10 mt=isolated type=market error=abort retries=3
```

### Stop Loss Order
```
close=long stoploss=-5% type=market expect=1
```

### Take Profit Order
```
close=long price=+10% priceref=pos expect=1
```

### Parameters
- `leverage`: Multiplier (e.g., 10x)
- `mt`: Margin type (`isolated` or `crossed`)
- `pm`: Position mode (`hedge` for hedging)
- `type`: Order type (`market` or `limit`)
- `error`: Error handling (`abort` or `closeside`)
- `retries`: Retry attempts on failure
- `expect`: Expected order count for confirmation
- `delay`: Wait time between commands

---

## Response Format

All API calls return a dictionary with:
```python
{
    'src': 'exchange_name',
    'venue': 'Binance',
    'error': None,  # or error message
    'data': {
        # Order/position/balance data
    },
    'rate_limits': {
        'remaining': 1000,
        'reset_time': 1678320000
    }
}
```

---

## Dashboard & Monitoring

### Available Through ProfitView Interface
- Real-time position tracking
- P&L monitoring (realized and unrealized)
- Trade history
- Balance tracking
- Chart integration with TradingView
- Notifications (Telegram bot integration)

### Telegram Bot Control
- ✅ **Remote control via Telegram**
- Supports Channels & Groups
- Can execute commands without TradingView
- Get position updates, balances, etc.

---

## Alternative Services (For External Webhook Execution)

If you want to send webhook orders FROM your bot TO an execution service, consider:

### 1. **TradersPost** (Recommended)
- **URL:** traderspost.io
- **Method:** REST API + Webhooks
- **Paper Trading:** ✅ Yes (built-in simulation)
- **Exchanges:** Multiple (including Binance, Bybit, etc.)
- **Cost:** ~$30-100/month
- **Use Case:** Perfect for external bot → webhook → execution

### 2. **SignalStack**
- **URL:** signalstack.com
- **Method:** Webhook-based
- **Paper Trading:** ✅ Yes
- **Exchanges:** Multiple
- **Cost:** Subscription-based

### 3. **NextLevelBot**
- **URL:** nextlevelbot.com
- **Method:** TradingView webhook relay
- **Paper Trading:** ✅ Yes
- **Cost:** Varies

### 4. **Direct Exchange APIs**
- Connect directly to Binance/Bybit testnet APIs
- No middleman service needed
- Free (just API keys)
- More complex implementation

---

## Deployment Options for Your Bot

### Option A: Deploy ON ProfitView Platform ⭐ (Use ProfitView as Intended)

**Architecture:**
```
Your Wallet Monitor Bot (local)
    → Sends signals via HTTP POST
    → ProfitView Bot (hosted on profitview.net)
    → Executes trades on exchange
```

**Pros:**
- ✅ 24/7 uptime (hosted by ProfitView)
- ✅ Free testnet support
- ✅ Direct exchange connections (low latency)
- ✅ Built-in monitoring and logging
- ✅ Telegram integration
- ✅ Chrome extension for manual control

**Cons:**
- ❌ Need to deploy bot on their platform
- ❌ Must write bot in their Python framework
- ❌ Less control over infrastructure
- ❌ Subscription cost ($29-$299/month)

**Implementation:**
1. Write ProfitView bot with webhook receiver
2. Deploy bot on profitview.net
3. Configure with testnet credentials
4. Your local bot sends signals to ProfitView webhook
5. ProfitView bot executes trades

### Option B: Use Alternative Service (TradersPost)

**Architecture:**
```
Your Wallet Monitor Bot (local)
    → Sends webhook to TradersPost
    → TradersPost API executes on exchange
```

**Pros:**
- ✅ Simple webhook integration (JSON POST)
- ✅ No bot deployment needed
- ✅ Built-in paper trading mode
- ✅ REST API for queries
- ✅ Well-documented

**Cons:**
- ❌ Subscription cost (~$30-100/month)
- ❌ Another service dependency
- ❌ Slightly higher latency (external service)

### Option C: Direct Exchange API Integration

**Architecture:**
```
Your Wallet Monitor Bot (local)
    → Calls Binance/Bybit API directly
    → Executes on exchange
```

**Pros:**
- ✅ No middleman (lowest latency)
- ✅ No subscription fees
- ✅ Full control
- ✅ Free testnet usage

**Cons:**
- ❌ More complex implementation
- ❌ Need to handle rate limiting, reconnections, etc.
- ❌ No built-in monitoring UI
- ❌ Must run bot 24/7 yourself (VPS needed)

---

## Recommendation

Based on your requirements for paper trading first with ability to switch to live:

### 🏆 **Recommended: Option C (Direct Exchange API)**

**Why:**
1. **Free** - No subscription costs
2. **Flexible** - Easy to switch exchanges
3. **Control** - Full control over execution logic
4. **Testnet** - Binance and Bybit offer free testnets
5. **Learning** - Best for understanding how trading systems work

**Implementation Plan:**
```python
# Use python-binance or ccxt library
from binance.client import Client

# Testnet credentials
client = Client(
    api_key="YOUR_TESTNET_KEY",
    api_secret="YOUR_TESTNET_SECRET",
    testnet=True  # ← Paper trading mode!
)

# Place order
order = client.futures_create_order(
    symbol='BTCUSDT',
    side='BUY',
    type='MARKET',
    quantity=0.001
)
```

### Alternative: TradersPost (If You Want a Service)
If you prefer a managed service with UI dashboard, TradersPost is the best alternative to ProfitView for external webhook execution.

---

## Next Steps

### If Using ProfitView:
1. ✅ Sign up for ProfitView account (profitview.net)
2. ✅ Choose subscription plan ($29-$299/month)
3. ✅ Get WEBHOOK_SECRET from editor
4. ✅ Write ProfitView bot with webhook receiver
5. ✅ Deploy bot on platform
6. ✅ Configure testnet exchange credentials
7. ✅ Test with small orders on testnet
8. ✅ Monitor via ProfitView dashboard

### If Using Direct Exchange API (Recommended):
1. ✅ Create Binance Futures Testnet account
2. ✅ Generate API keys
3. ✅ Install `python-binance` or `ccxt` library
4. ✅ Implement executor class (simpler than ProfitView integration)
5. ✅ Test on testnet
6. ✅ Switch to live when ready (just change credentials)

### If Using TradersPost:
1. ✅ Sign up for TradersPost account
2. ✅ Enable paper trading mode
3. ✅ Get API credentials
4. ✅ Implement webhook sender
5. ✅ Test with paper trading
6. ✅ Switch to live when ready

---

## Questions for User

1. **Do you want to use ProfitView specifically?** If so, are you okay with:
   - Deploying your bot ON their platform?
   - Monthly subscription cost?
   - Writing bot in their Python framework?

2. **Or would you prefer direct exchange API integration?** (Recommended)
   - Free (no subscription)
   - More control
   - Easier to implement for your use case

3. **What is your API key for?** (`35f7db8ad962540d62cc274c7d108abd07701b25`)
   - Is this a ProfitView API key?
   - Or an exchange API key?
   - Or a webhook secret?

---

## Resources

### ProfitView
- **Main Site:** https://profitview.net
- **Chrome Extension:** https://profitview.app
- **Documentation:** https://profitview.net/docs/trading/
- **Wiki:** https://wiki.profitview.app
- **GitHub Examples:** https://github.com/profitviews/bots

### Alternative Services
- **TradersPost:** https://traderspost.io
- **SignalStack:** https://signalstack.com
- **NextLevelBot:** https://nextlevelbot.com

### Exchange Testnets
- **Binance Futures Testnet:** https://testnet.binancefuture.com
- **Bybit Testnet:** https://testnet.bybit.com
- **BitMEX Testnet:** https://testnet.bitmex.com

### Python Libraries
- **python-binance:** https://github.com/sammchardy/python-binance
- **ccxt:** https://github.com/ccxt/ccxt (supports 100+ exchanges)
- **requests:** Standard HTTP library

---

## Conclusion

**ProfitView is not what we initially thought.** It's a bot hosting platform, not a webhook execution service.

**For your use case (external wallet monitor → trade execution), you have three options:**
1. ⭐ **Direct exchange API** (recommended - free, simple, full control)
2. 🔄 **TradersPost** (if you want a service with UI)
3. 🤔 **ProfitView** (requires deploying your bot on their platform)

**My recommendation:** Implement direct exchange API integration using `python-binance` or `ccxt` with testnet mode. This gives you paper trading for free, full control, and easy transition to live trading.

Let me know which direction you'd like to go, and I'll implement it accordingly!
