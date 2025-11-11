# ProfitView Integration Documentation

Complete documentation for ProfitView trade execution integration.

---

## Overview

The wallet copy trading bot now integrates with ProfitView for automated trade execution. This integration supports:

- ✅ **Paper Trading Mode** (default) - Safe testing with no real money
- ✅ **Live Trading Mode** - Real execution when ready
- ✅ **Complete Order Validation** - Prevent invalid trades
- ✅ **Retry Logic** - Handle network issues gracefully
- ✅ **Rate Limiting** - Prevent API throttling
- ✅ **Audit Trail** - Full database logging
- ✅ **P&L Tracking** - Monitor performance in ProfitView dashboard

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Wallet Copy Trading Bot                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. wallet_discovery.py                                      │
│     └─> Discovers profitable wallets                         │
│                                                               │
│  2. wallet_analyzer.py                                       │
│     └─> Monitors wallet activity                             │
│                                                               │
│  3. signal_processor.py (to be implemented)                  │
│     └─> Generates trading signals                            │
│                                                               │
│  4. profitview_executor.py ⭐ NEW                            │
│     └─> Executes trades via ProfitView API                   │
│         │                                                     │
│         ├─> Paper Trading (Testnet)                          │
│         └─> Live Trading (Real Money)                        │
│                                                               │
│  5. database/wallets.db                                      │
│     └─> Stores orders, positions, audit trail                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  ProfitView API  │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Binance Futures │
                    │   (Paper/Live)   │
                    └──────────────────┘
```

---

## Files Created

### Configuration
- `config/profitview_config.json` - Your API key and settings (gitignored)
- `config/profitview_config.example.json` - Template for team members

### Code
- `scripts/profitview_executor.py` - Main executor class (450+ lines)
- `main.py` - Entry point with demo and production modes

### Testing
- `tests/test_profitview_integration.py` - Comprehensive test suite (5 tests)

### Documentation
- `docs/PROFITVIEW_SETUP.md` - Complete setup guide
- `docs/PROFITVIEW_INTEGRATION.md` - This file
- `PROFITVIEW_API_RESEARCH.md` - API research findings

---

## Quick Start

### 1. Test the Integration

Run basic connection test:
```bash
python scripts/profitview_executor.py
```

### 2. Run Full Test Suite

Run all integration tests:
```bash
python tests/test_profitview_integration.py
```

### 3. Try Demo Mode

Execute a demo trade:
```bash
python main.py --demo
```

### 4. Review Dashboard

Log into ProfitView and verify:
- Test orders appear in order history
- Paper trading mode is active
- P&L tracking works

---

## Usage Examples

### Basic Order Execution

```python
from scripts.profitview_executor import ProfitViewExecutor

# Initialize (defaults to paper_trade mode)
executor = ProfitViewExecutor()

# Prepare order
position = {
    'wallet_id': 1,
    'pair': 'BTC/USDT',
    'side': 'BUY',
    'size_usd': 100.0,
    'quantity': 0.002,
    'leverage': 5,
    'entry_price': 50000,
    'stop_loss_price': 49000
}

# Execute
result = executor.send_order(position)

if result.success:
    print(f"✅ Order filled: {result.order_id}")
else:
    print(f"❌ Order failed: {result.error_message}")
```

### Query Open Positions

```python
positions = executor.get_open_positions()

for pos in positions:
    print(f"{pos['symbol']}: ${pos['unrealizedPnl']:.2f}")
```

### Get P&L Summary

```python
pnl = executor.get_pnl_summary()

print(f"Total P&L: ${pnl['totalPnl']:.2f}")
print(f"Win Rate: {pnl['winRate']:.1%}")
```

### Check Statistics

```python
stats = executor.get_statistics()

print(f"Mode: {stats['mode']}")
print(f"Success Rate: {stats['success_rate']:.1%}")
print(f"Total Volume: ${stats['total_volume_usd']:,.2f}")
```

---

## Configuration

### Paper Trading (Default)

```json
{
  "mode": "paper_trade",
  "api_key": "35f7db8ad962540d62cc274c7d108abd07701b25",

  "endpoints": {
    "paper_trade": "https://profitview.net/api/v1/paper/webhook",
    "live_trade": "https://profitview.net/api/v1/webhook"
  },

  "exchange_settings": {
    "venue": "WooLive",
    "exchange": "binance",
    "default_leverage": 10,
    "max_leverage": 25
  },

  "safety": {
    "require_confirmation_for_live": true,
    "max_order_size_usd": 10000,
    "daily_loss_limit_usd": 5000
  }
}
```

### Safety Features

**Order Validation:**
- ✅ Minimum notional: $10
- ✅ Maximum order size: $10,000 (configurable)
- ✅ Maximum leverage: 25x (configurable)
- ✅ Stop loss validation (must be below entry for LONG, above for SHORT)

**Live Mode Protection:**
- ✅ Requires explicit confirmation prompt
- ✅ Shows prominent warning banner
- ✅ Logs mode in every order

**Rate Limiting:**
- ✅ Token bucket algorithm
- ✅ 10 requests/second default (configurable)
- ✅ Burst allowance: 20 requests

---

## Testing

### Test Suite Coverage

**Test 1: API Connection** ✅
- Executor initialization
- Config loading
- API key validation
- Endpoint connectivity

**Test 2: Paper Trading** ✅
- 5 small test orders
- Different pairs (BTC, ETH, SOL, AVAX)
- Both BUY and SELL sides
- Leverage testing

**Test 3: Order Validation** ✅
- Reject orders too small
- Reject orders too large
- Reject excessive leverage
- Reject invalid stop loss (LONG)
- Reject invalid stop loss (SHORT)

**Test 4: Rate Limiting** ✅
- 15 rapid orders
- No rate limit errors
- Proper throttling

**Test 5: Error Handling** ✅
- Configuration validation
- OrderResult structure
- Statistics tracking

### Running Tests

```bash
# Run specific test
python -c "from tests.test_profitview_integration import test_1_api_connection; test_1_api_connection()"

# Run all tests
python tests/test_profitview_integration.py

# Run with verbose output
python -v tests/test_profitview_integration.py
```

---

## Database Schema

### Orders Table

The executor logs all orders to `database/wallets.db`:

```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE,              -- WCT_wallet_timestamp
    wallet_id INTEGER,                 -- Source wallet
    exchange TEXT,                     -- binance
    pair TEXT,                         -- BTC/USDT
    side TEXT,                         -- BUY or SELL
    order_type TEXT,                   -- MARKET
    size_usd REAL,                     -- Position size
    quantity REAL,                     -- Asset quantity
    leverage INTEGER,                  -- Leverage multiplier
    notional_value REAL,               -- size_usd * leverage
    expected_price REAL,               -- Entry price
    executed_price REAL,               -- Actual fill price
    stop_loss_price REAL,              -- Stop loss level
    stop_loss_usd REAL,                -- Stop loss amount
    status TEXT,                       -- PENDING/FILLED/REJECTED/FAILED
    api_request_payload TEXT,          -- JSON request
    api_response TEXT,                 -- JSON response
    failure_reason TEXT,               -- Error message
    submitted_at TIMESTAMP,            -- When sent
    executed_at TIMESTAMP,             -- When filled
    mode TEXT                          -- paper_trade or live
);
```

### Query Examples

```sql
-- Recent orders
SELECT order_id, pair, side, status, size_usd
FROM orders
ORDER BY submitted_at DESC
LIMIT 10;

-- Success rate
SELECT
    status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 2) as percentage
FROM orders
GROUP BY status;

-- Total volume by mode
SELECT
    mode,
    SUM(size_usd) as total_volume,
    COUNT(*) as order_count
FROM orders
GROUP BY mode;

-- Failed orders analysis
SELECT failure_reason, COUNT(*) as count
FROM orders
WHERE status = 'FAILED'
GROUP BY failure_reason
ORDER BY count DESC;
```

---

## API Payload Format

### Request Format

```json
{
  "venue": "WooLive",
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "side": "buy",
  "type": "market",
  "quantity": 0.002,
  "leverage": 5,
  "stopLoss": {
    "type": "fixed",
    "price": 49000
  },
  "timestamp": 1699876543210,
  "metadata": {
    "wallet_id": 1,
    "size_usd": 100,
    "source": "wallet_copy_bot",
    "mode": "paper_trade"
  }
}
```

### Response Format (Success)

```json
{
  "success": true,
  "orderId": "WCT_1_1699876543210",
  "exchangeOrderId": "12345678",
  "status": "FILLED",
  "filledPrice": 50050.25,
  "filledQuantity": 0.002,
  "timestamp": 1699876543500
}
```

### Response Format (Error)

```json
{
  "success": false,
  "error": "Insufficient balance",
  "code": "INSUFFICIENT_BALANCE",
  "timestamp": 1699876543500
}
```

---

## Error Handling

### Retry Logic

The executor uses exponential backoff for retries:

```python
backoff_delays = [1, 2, 4]  # seconds

# Attempt 1: Immediate
# Attempt 2: Wait 1s
# Attempt 3: Wait 2s
# Attempt 4: Wait 4s (final)
```

### Non-Retryable Errors

These errors skip retry logic:
- Insufficient balance
- Invalid API key
- Order validation failures

### Retryable Errors

These errors trigger retry:
- Network timeout
- 5xx server errors
- Temporary API issues

### Error Logging

All errors are logged:
1. Console output (real-time)
2. Database `orders` table (`failure_reason` field)
3. API response stored in `api_response` field

---

## Performance & Monitoring

### Key Metrics

**Order Metrics:**
- Orders submitted
- Orders filled
- Orders rejected (validation)
- Orders failed (API errors)
- Success rate (filled / submitted)

**Volume Metrics:**
- Total volume (USD)
- Average order size
- Largest order
- Volume by pair

**Timing Metrics:**
- Average execution time
- Slowest execution
- Rate limit delays

### Monitoring Script

```python
import sqlite3

conn = sqlite3.connect('database/wallets.db')

# Daily summary
print("Daily Summary:")
cursor = conn.execute("""
    SELECT
        DATE(submitted_at) as date,
        COUNT(*) as orders,
        SUM(size_usd) as volume,
        SUM(CASE WHEN status='FILLED' THEN 1 ELSE 0 END) as filled,
        ROUND(AVG(CASE WHEN status='FILLED' THEN 1 ELSE 0 END) * 100, 2) as success_rate
    FROM orders
    WHERE submitted_at >= DATE('now', '-7 days')
    GROUP BY DATE(submitted_at)
    ORDER BY date DESC
""")

for row in cursor:
    print(f"  {row[0]}: {row[1]} orders, ${row[2]:.2f} volume, {row[4]}% success")

conn.close()
```

---

## Production Deployment

### Prerequisites

**Before Deployment:**
- [ ] All tests passing (100%)
- [ ] Ran paper trading for 1-2 weeks
- [ ] Reviewed all test orders in ProfitView dashboard
- [ ] Verified P&L tracking accuracy
- [ ] Set appropriate position sizes
- [ ] Configured safety limits
- [ ] Prepared monitoring scripts

### Deployment Checklist

**1. Environment Setup:**
```bash
# Clone repository
git clone <repo_url>
cd AMA4370

# Install dependencies
pip install -r requirements.txt

# Configure API key
cp config/profitview_config.example.json config/profitview_config.json
nano config/profitview_config.json  # Add your API key

# Verify configuration
python -c "import json; print(json.load(open('config/profitview_config.json'))['mode'])"
# Should output: paper_trade
```

**2. Test Integration:**
```bash
# Run connection test
python scripts/profitview_executor.py

# Run full test suite
python tests/test_profitview_integration.py

# Verify all tests pass
```

**3. Paper Trading Phase:**
```bash
# Run demo
python main.py --demo

# Monitor for 1-2 weeks
# Review performance daily
# Adjust parameters as needed
```

**4. Go Live (When Ready):**
```bash
# Update configuration
nano config/profitview_config.json
# Change "mode": "paper_trade" to "mode": "live"

# Start with reduced sizes
# Monitor closely
# Gradually increase
```

### Server Requirements

**Recommended:**
- VPS with 24/7 uptime
- Ubuntu 20.04+ or similar
- Python 3.8+
- 1GB RAM minimum
- SSD storage

**Network:**
- Stable internet connection
- Low latency to exchange API
- Backup connection recommended

---

## Troubleshooting

See detailed troubleshooting guide in `docs/PROFITVIEW_SETUP.md`.

### Common Issues

1. **"Configuration file not found"**
   - Copy example config to profitview_config.json
   - Add your API key

2. **"API key invalid"**
   - Verify key in ProfitView account settings
   - Check for typos
   - Regenerate if needed

3. **Orders rejected**
   - Check validation errors
   - Verify sufficient balance
   - Review order parameters

4. **Rate limiting errors**
   - Reduce requests_per_second in config
   - Add delays between orders

---

## Next Steps

### Immediate
1. ✅ Run tests: `python tests/test_profitview_integration.py`
2. ✅ Try demo: `python main.py --demo`
3. ✅ Review ProfitView dashboard
4. ✅ Verify paper trading mode

### Short-term (1-2 weeks)
1. ⏳ Implement `signal_processor.py`
2. ⏳ Integrate with `wallet_analyzer.py`
3. ⏳ Set up continuous monitoring
4. ⏳ Add risk management rules

### Long-term
1. ⏳ Run paper trading for 1-2 weeks
2. ⏳ Analyze performance
3. ⏳ Optimize parameters
4. ⏳ Switch to live mode (gradually)

---

## Support & Resources

### Documentation
- Setup Guide: `docs/PROFITVIEW_SETUP.md`
- API Research: `PROFITVIEW_API_RESEARCH.md`
- This Document: `docs/PROFITVIEW_INTEGRATION.md`

### ProfitView Resources
- Website: https://profitview.net
- Documentation: https://profitview.net/docs
- Wiki: https://wiki.profitview.app
- Support: support@profitview.net

### Code Examples
- Basic Usage: `scripts/profitview_executor.py` (see bottom)
- Demo Mode: `main.py --demo`
- Test Suite: `tests/test_profitview_integration.py`

---

**Happy Trading! 🚀**

For questions or issues, refer to the troubleshooting section or contact support.
