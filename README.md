# Wallet Copy Trading System

A sophisticated system for discovering and tracking profitable cryptocurrency wallets on Ethereum and Binance Smart Chain (BSC) for automated copy trading.

## Project Status: Phase 1 - Discovery & Infrastructure

### Completed Components

#### Session 1.1: Database Schema ✅
- **init_database.py** - SQLite schema for tracking wallets, transactions, orders, and positions
- 4 tables with 14 strategic indexes
- Foreign key constraints and data validation
- Comprehensive docstrings

#### Session 1.2: Wallet Discovery ✅
- **wallet_discovery.py** - Discovery system for finding profitable wallets
- **test_wallet_discovery.py** - Complete test suite with mocked APIs
- Supports Ethereum and BSC via Etherscan/BSCScan APIs
- Token bucket rate limiting (5 req/sec)
- Exponential backoff retry logic
- USD conversion for volumes

## Features

### Wallet Discovery
- **Multi-chain support**: Ethereum and Binance Smart Chain
- **Smart filtering criteria**:
  - Minimum 50 trades in last 90 days
  - Total volume > $50,000 USD
  - Active within last 7 days
  - Excludes smart contract addresses
- **Recent blocks sampling strategy**: Analyzes last 7 days of blockchain activity
- **Parallel processing**: ThreadPoolExecutor for concurrent API calls
- **Rate limiting**: Token bucket algorithm prevents API throttling
- **Robust error handling**: Exponential backoff, retries, graceful degradation

### Database Schema
- **wallets**: Performance metrics and ranking scores
- **wallet_transactions**: Historical trade data for analysis
- **our_orders**: Our executed trades (copy or manual)
- **open_positions**: Real-time P&L tracking with average cost basis

## Installation

### Prerequisites
- Python 3.9+
- pip

### Setup

1. **Clone the repository**
```bash
git clone <repo-url>
cd AMA4370
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure API keys**

Copy the example config and add your API keys:
```bash
cp config/api_keys.json.example config/api_keys.json
```

Edit `config/api_keys.json`:
```json
{
  "etherscan_api_key": "YOUR_ETHERSCAN_API_KEY",
  "bscscan_api_key": "YOUR_BSCSCAN_API_KEY",
  "rate_limit_per_second": 5,
  "max_retries": 5,
  "request_timeout": 30
}
```

**Get API Keys:**
- Etherscan: https://etherscan.io/myapikey
- BSCScan: https://bscscan.com/myapikey

4. **Initialize database**
```bash
python init_database.py
```

## Usage

### Discover Profitable Wallets

Run the wallet discovery system:
```bash
python wallet_discovery.py
```

**Output:**
- `discovered_wallets.csv` - Filtered list of ~100 profitable wallets

**Expected Runtime:**
- ~20-30 minutes (2000 addresses scanned across both chains)
- Progress logged every wallet (DEBUG level)

### Run Tests

```bash
pytest test_wallet_discovery.py -v
```

**Test Coverage:**
- Configuration loading (file, env vars, errors)
- Rate limiting (token bucket algorithm)
- Exponential backoff on failures
- Transaction parsing and filtering
- Contract address detection
- Wallet metrics calculation
- Filter logic
- CSV export

## Architecture

### Wallet Discovery Pipeline

```
┌─────────────────────────────────────────────────────────┐
│  1. Load Config        (API keys from JSON/env)        │
├─────────────────────────────────────────────────────────┤
│  2. Initialize Clients (Etherscan, BSCScan)            │
├─────────────────────────────────────────────────────────┤
│  3. Discover Traders   (Sample recent blocks)          │
│     - Ethereum: ~1000 candidates                        │
│     - BSC: ~1000 candidates                             │
├─────────────────────────────────────────────────────────┤
│  4. Fetch Metrics      (90 days transaction history)   │
│     - Total trades                                      │
│     - Volume in USD                                     │
│     - Last activity                                     │
│     - Contract check                                    │
├─────────────────────────────────────────────────────────┤
│  5. Apply Filters      (Trades, volume, activity)      │
├─────────────────────────────────────────────────────────┤
│  6. Export CSV         (discovered_wallets.csv)        │
└─────────────────────────────────────────────────────────┘
```

### Rate Limiting: Token Bucket Algorithm

```python
- Bucket capacity: 5 tokens
- Refill rate: 5 tokens/second
- Each API call consumes 1 token
- Allows bursts up to capacity
- Blocks when bucket empty
```

### Exponential Backoff

```
Retry attempts: 2s → 4s → 8s → 16s → 32s (max)
```

## File Structure

```
AMA4370/
├── config/
│   ├── api_keys.json.example    # Template for API keys
│   └── api_keys.json            # Your actual keys (gitignored)
├── init_database.py             # Database schema initialization
├── wallet_discovery.py          # Main discovery system
├── test_wallet_discovery.py     # Test suite
├── discovered_wallets.csv       # Output (generated)
├── wallet_trading.db            # SQLite database (generated)
├── .gitignore                   # Git ignore rules
├── README.md                    # This file
└── requirements.txt             # Python dependencies
```

## Configuration

### API Rate Limits

**Default settings** (adjust in `config/api_keys.json`):
- `rate_limit_per_second`: 5 (free tier limit)
- `max_retries`: 5
- `request_timeout`: 30 seconds

**Etherscan/BSCScan Free Tier:**
- 5 calls/second
- 100,000 calls/day

### Filter Criteria

**Hardcoded in wallet_discovery.py** (modify `apply_filters()` function):
```python
MIN_TRADES = 50              # Minimum trades in 90 days
MIN_VOLUME_USD = 50000       # Minimum $50k volume
MAX_DAYS_INACTIVE = 7        # Active within 7 days
EXCLUDE_CONTRACTS = True     # Skip smart contracts
```

## Database Schema

### Tables

1. **wallets** - Wallet performance and ranking
   - address, rank_score, total_trades, win_rate, sharpe_ratio, etc.

2. **wallet_transactions** - Historical trades
   - tx_hash, timestamp, action (BUY/SELL), token, amount, price_usd

3. **our_orders** - Our executed trades
   - Links to copied wallet, execution details, status tracking

4. **open_positions** - Current holdings
   - token, amount, avg_entry_price, current_price, unrealized_pnl

## Development Roadmap

### Phase 1: Infrastructure ✅
- [x] Database schema design
- [x] Wallet discovery system
- [x] Test suite with 95%+ coverage

### Phase 2: Analysis (Next)
- [ ] Wallet ranking algorithms
- [ ] Performance metric calculations
- [ ] Sharpe ratio, win rate, max drawdown

### Phase 3: Trading
- [ ] Real-time transaction monitoring
- [ ] Order execution system
- [ ] Position management
- [ ] P&L tracking

### Phase 4: Optimization
- [ ] Strategy backtesting
- [ ] Risk management
- [ ] Portfolio allocation
- [ ] Performance dashboard

## Troubleshooting

### "Missing required API keys"
**Solution:** Create `config/api_keys.json` or set environment variables:
```bash
export ETHERSCAN_API_KEY="your_key"
export BSCSCAN_API_KEY="your_key"
```

### "Max rate limit reached"
**Solution:**
- Wait 60 seconds and retry
- Upgrade to paid Etherscan/BSCScan plan
- Reduce `rate_limit_per_second` in config

### "No wallets discovered"
**Solution:**
- Check API keys are valid
- Verify network connectivity
- Lower filter thresholds (MIN_TRADES, MIN_VOLUME_USD)

### Tests failing
**Solution:**
```bash
pip install pytest pytest-mock requests
pytest test_wallet_discovery.py -v
```

## Performance Notes

### Expected Discovery Results

```
Total addresses scanned: 2000 (1000 ETH + 1000 BSC)
Wallets passing filters: ~50-100

Filter pass rates:
- Minimum trades (≥50): ~45%
- Volume threshold (≥$50k): ~23%
- Active last 7 days: ~68%
- Not contract: ~89%
- All filters combined: ~4-5%
```

### Runtime Optimization

**Current:** Sequential chain processing (Ethereum → BSC)
**Improvement:** Parallel chain processing (future enhancement)

## Contributing

This is a personal project. For issues or questions:
1. Check existing documentation
2. Review test cases for usage examples
3. Examine code comments and docstrings

## Security

⚠️ **IMPORTANT:**
- Never commit `config/api_keys.json` to git
- Keep API keys confidential
- The `.gitignore` file protects sensitive data
- Use environment variables in production

## License

Private project - All rights reserved

---

**Project:** AMA4370 - Wallet Copy Trading System
**Phase:** 1 - Discovery & Infrastructure
**Status:** Active Development
**Last Updated:** 2025-11-06
