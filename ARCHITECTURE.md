# System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         WALLET COPY TRADING SYSTEM                              │
└─────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────┐
│                            PHASE 1: DISCOVERY & SETUP                             │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────┐       ┌──────────────────┐       ┌──────────────────┐     │
│  │ Etherscan API   │──────▶│ wallet_discovery │──────▶│ wallet_analyzer  │     │
│  │ (Token Transfers)│       │  - Find wallets  │       │  - Calculate ROI │     │
│  └─────────────────┘       │  - Filter DEX    │       │  - Win rate      │     │
│                            │  - Dedup wallets │       │  - Risk score    │     │
│                            └──────────────────┘       └──────────────────┘     │
│                                     │                           │               │
│                                     ▼                           ▼               │
│                            ┌──────────────────────────────────────┐            │
│                            │      wallet_trading.db               │            │
│                            │  ┌────────────────────────────────┐  │            │
│                            │  │ wallets (address, rank_score)  │  │            │
│                            │  │ monitoring_state (last_block)  │  │            │
│                            │  │ wallet_transactions (trades)   │  │            │
│                            │  └────────────────────────────────┘  │            │
│                            └──────────────────────────────────────┘            │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────┐
│                       PHASE 2: REAL-TIME MONITORING                               │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         trade_monitor.py                                 │    │
│  │                         (Main Orchestrator)                              │    │
│  │                                                                          │    │
│  │  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │    │
│  │  │ Load Wallets │─▶│ Fetch TXs   │─▶│ Parse Swaps  │─▶│ Emit Signal │ │    │
│  │  │ from DB      │  │ (Etherscan) │  │ (DEX Parser) │  │ (If valid)  │ │    │
│  │  └──────────────┘  └─────────────┘  └──────────────┘  └─────────────┘ │    │
│  │         │                  │                 │                 │        │    │
│  │         │                  │                 │                 │        │    │
│  │    Every 60s          Block range      Transaction hash    Trade info   │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│           │                                      │                               │
│           ▼                                      ▼                               │
│  ┌──────────────────┐                 ┌────────────────────┐                   │
│  │ TransactionFetcher│                 │    dex_parser.py   │                   │
│  │ - Rate limiting   │                 │ ┌────────────────┐ │                   │
│  │ - Retry logic     │                 │ │ RPC Providers  │ │                   │
│  │ - Block queries   │                 │ │ - eth.drpc.org │ │                   │
│  └──────────────────┘                 │ │ - ankr         │ │                   │
│                                         │ │ - publicnode   │ │                   │
│                                         │ │ - 1rpc         │ │                   │
│                                         │ │ - llamarpc     │ │                   │
│                                         │ │ - cloudflare   │ │                   │
│                                         │ └────────────────┘ │                   │
│                                         │                     │                   │
│                                         │ ┌────────────────┐ │                   │
│                                         │ │ Retry Engine   │ │                   │
│                                         │ │ - 2 retries    │ │                   │
│                                         │ │ - 0.5s delay   │ │                   │
│                                         │ │ - Fast failover│ │                   │
│                                         │ │ - 400=no retry │ │                   │
│                                         │ └────────────────┘ │                   │
│                                         │                     │                   │
│                                         │ ┌────────────────┐ │                   │
│                                         │ │ Swap Parser    │ │                   │
│                                         │ │ - Uniswap V2/V3│ │                   │
│                                         │ │ - PancakeSwap  │ │                   │
│                                         │ │ - 1inch        │ │                   │
│                                         │ │ - CoinGecko $$ │ │                   │
│                                         │ └────────────────┘ │                   │
│                                         └────────────────────┘                   │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────┐
│                      PHASE 3: SIGNAL PROCESSING                                   │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                       signal_processor.py                                │    │
│  │                                                                          │    │
│  │  ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────┐  │    │
│  │  │ Risk Filters     │───▶│ Position Sizing  │───▶│ Order Details   │  │    │
│  │  │ - Max positions  │    │ - Capital alloc  │    │ - Entry price   │  │    │
│  │  │ - Token whitelist│    │ - Leverage calc  │    │ - Stop loss     │  │    │
│  │  │ - Market depth   │    │ - Slippage limit │    │ - Take profit   │  │    │
│  │  │ - Spread check   │    │                  │    │                 │  │    │
│  │  └──────────────────┘    └──────────────────┘    └─────────────────┘  │    │
│  │           │                       │                        │           │    │
│  │           │                       │                        │           │    │
│  │     REJECT if:                CALCULATE:              GENERATE:        │    │
│  │     - Too many positions      - size_usd           - pair (BTC/USDT)  │    │
│  │     - Token not whitelisted   - leverage          - side (LONG/SHORT) │    │
│  │     - Insufficient depth      - notional          - quantity          │    │
│  │     - Wide spread             - risk_amount       - stop/target       │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                       │                                          │
│                                       ▼                                          │
│                           ┌────────────────────────┐                            │
│                           │  Position Object       │                            │
│                           │  - Ready for execution │                            │
│                           └────────────────────────┘                            │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────┐
│                       PHASE 4: TRADE EXECUTION                                    │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    profitview_executor.py                                │    │
│  │                                                                          │    │
│  │  ┌────────────────┐     ┌────────────────┐     ┌────────────────┐     │    │
│  │  │ Format Order   │────▶│ Send to        │────▶│ Confirm & Log  │     │    │
│  │  │ - Pair format  │     │ ProfitView API │     │ - Order ID     │     │    │
│  │  │ - Quantities   │     │ - POST request │     │ - Fill price   │     │    │
│  │  │ - Stop/TP      │     │ - Auth token   │     │ - Status       │     │    │
│  │  └────────────────┘     └────────────────┘     └────────────────┘     │    │
│  │                                  │                                      │    │
│  └─────────────────────────────────│──────────────────────────────────────┘    │
│                                     │                                            │
│                                     ▼                                            │
│                          ┌─────────────────────┐                                │
│                          │   ProfitView API    │                                │
│                          │  (Trading Bridge)   │                                │
│                          └─────────────────────┘                                │
│                                     │                                            │
│                     ┌───────────────┼───────────────┐                           │
│                     ▼               ▼               ▼                           │
│              ┌──────────┐    ┌──────────┐    ┌──────────┐                     │
│              │ Binance  │    │  Bybit   │    │  Others  │                     │
│              │ Futures  │    │ Futures  │    │ Exchange │                     │
│              └──────────┘    └──────────┘    └──────────┘                     │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────┐
│                          DATA FLOW SUMMARY                                        │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  Wallet Address → Transactions → DEX Swaps → Trade Signals → Risk Filters →     │
│  Position Sizing → Order Execution → Exchange Order → Fill Confirmation          │
│                                                                                   │
│  Time: < 5 seconds from wallet trade detection to exchange order submission      │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Explanations

### 1. **wallet_discovery.py** - Wallet Discovery Engine
**Purpose:** Find profitable traders on Ethereum by analyzing historical transactions.

**How it works:**
- Queries Etherscan API for token transfer events
- Filters for addresses that interact with DEX routers (Uniswap, 1inch, etc.)
- Deduplicates wallets across multiple tokens
- Rate-limited to avoid API throttling (5 req/sec)

**Output:** List of unique wallet addresses saved to database

---

### 2. **wallet_analyzer.py** - Performance Analyzer
**Purpose:** Rank wallets by trading performance to identify the best traders to copy.

**Metrics calculated:**
- **ROI (Return on Investment):** Profit/loss from all closed positions
- **Win Rate:** Percentage of profitable trades
- **Sharpe Ratio:** Risk-adjusted returns
- **Max Drawdown:** Largest peak-to-trough decline
- **Trade Frequency:** Average trades per day

**Ranking formula:**
```
rank_score = (win_rate × 0.4) + (roi × 0.3) + (sharpe × 0.2) + (frequency × 0.1)
```

**Output:** Ranked wallets with allocation percentages (top wallets get higher %)

---

### 3. **trade_monitor.py** - Real-Time Monitoring Orchestrator
**Purpose:** Main service that runs 24/7, watching tracked wallets for new trades.

**Architecture:**
```
Loop (every 60 seconds):
  1. Load tracked wallets from DB
  2. For each wallet:
     - Fetch new transactions (Etherscan API)
     - Parse DEX swaps (dex_parser)
     - Detect leverage (leverage_detector)
     - Emit copy signal (signal_emitter)
  3. Sleep until next cycle
```

**Key features:**
- **Block-based tracking:** Remembers last checked block per wallet
- **Error handling:** Exponential backoff on failures
- **Paper mode:** Test without real trades
- **Statistics:** Tracks total signals emitted

**Configuration:**
- `check_interval`: 60 seconds (default)
- `paper_mode`: True/False
- `max_wallets`: 20-50 recommended

---

### 4. **dex_parser.py** - Multi-Protocol DEX Transaction Parser
**Purpose:** Decode blockchain transactions to extract trade details (token pair, amounts, USD value).

**Supported DEXs:**
- Uniswap V2/V3
- PancakeSwap V2/V3
- 1inch (aggregator)
- SushiSwap
- Curve, Balancer, Kyber, ParaSwap

**RPC Provider System:**
```
6 providers with automatic fallback:
1. eth.drpc.org        (primary)
2. rpc.ankr.com
3. ethereum.publicnode.com
4. 1rpc.io
5. eth.llamarpc.com
6. cloudflare-eth.com

If provider returns 500/timeout:
  → Retry 2x with 0.5s, 0.75s delays
  → Rotate to next provider
  → Mark unhealthy after 3 failures
```

**Parsing flow:**
```
Transaction hash →
  get_transaction() + get_receipt() →
  Find Swap event in logs →
  Extract token addresses →
  Get token symbol/decimals (ERC20.call) →
  Get token prices (CoinGecko API) →
  Calculate USD amounts →
  Return SwapInfo object
```

**Output:**
```python
SwapInfo(
    tx_hash='0x...',
    token_in='USDC',
    token_out='ETH',
    amount_in=1000.0,
    amount_out=0.5,
    amount_in_usd=1000.0,
    amount_out_usd=1250.0,
    action='BUY'  # or 'SELL'
)
```

**Optimizations:**
- **Caching:** Token info cached for 5 minutes
- **Fast-fail:** 400/404 errors don't retry (old tx not in archive)
- **Health check:** Tests providers at startup
- **1-day lookback:** Only monitors recent blocks (free RPC limitation)

---

### 5. **signal_processor.py** - Risk Management & Position Sizing
**Purpose:** Apply risk rules and calculate exact position sizes before execution.

**Risk Filters (REJECT if fails):**

| Filter | Rule | Example |
|--------|------|---------|
| Max Total Positions | ≤ 20 open positions | Prevent over-exposure |
| Max Same Pair | ≤ 3 BTC/USDT positions | Diversification |
| Token Whitelist | Only approved tokens | BTC, ETH, SOL, etc. |
| Market Depth | Liquidity ≥ 10x position | Prevent slippage |
| Spread Check | Bid/ask spread < 0.5% | Avoid illiquid markets |
| Max Position Size | ≤ 5% of capital per trade | Risk per trade limit |

**Position Sizing Logic:**
```python
# Example with $100k capital, 5% allocation
wallet_allocation = 10%  # Based on wallet rank
trade_size_usd = $1000   # From monitored wallet

copy_size = trade_size_usd × wallet_allocation
          = $1000 × 10%
          = $100

leverage = detect_leverage(tx)  # 1-10x
notional = copy_size × leverage
         = $100 × 5x
         = $500 position size
```

**Output:**
```python
Position(
    pair='BTC/USDT',
    side='LONG',
    size_usd=100.0,
    leverage=5,
    notional_usd=500.0,
    entry_price=45000.0,
    stop_loss_price=43500.0,     # -3%
    take_profit_price=47250.0    # +5%
)
```

---

### 6. **profitview_executor.py** - Exchange API Bridge
**Purpose:** Send approved positions to exchanges via ProfitView API.

**ProfitView** is a third-party trading platform that:
- Connects to multiple exchanges (Binance, Bybit, etc.)
- Provides unified API for order execution
- Handles exchange-specific quirks
- Manages API rate limits

**Order flow:**
```
Position object →
  Format for ProfitView API →
  POST to profitview.net/api/v1/order →
  Receive order_id + status →
  Log result (success/failure)
```

**API Request:**
```json
{
  "pair": "BTC/USDT",
  "side": "LONG",
  "quantity": 0.011,
  "leverage": 5,
  "stop_loss": 43500,
  "take_profit": 47250
}
```

**Response:**
```json
{
  "success": true,
  "order_id": "PV12345",
  "exchange_order_id": "BN67890",
  "status": "FILLED",
  "filled_price": 45050.0,
  "filled_quantity": 0.011
}
```

---

### 7. **init_database.py** - Database Schema
**Purpose:** Initialize SQLite database with required tables.

**Tables:**

**wallets**
```sql
address          TEXT PRIMARY KEY
rank_score       REAL        -- 0-100 score
allocation_pct   REAL        -- 5-20% allocation
is_active        INTEGER     -- 1=monitored, 0=paused
roi              REAL        -- Return on investment
win_rate         REAL        -- Win percentage
```

**monitoring_state**
```sql
wallet_address           TEXT PRIMARY KEY
last_checked_block       INTEGER  -- Resume from here
last_checked_timestamp   TEXT
consecutive_errors       INTEGER  -- Health tracking
total_transactions_found INTEGER  -- Statistics
```

**wallet_transactions**
```sql
wallet_id           INTEGER  -- FK to wallets.id
tx_hash             TEXT     -- Blockchain tx
token_address       TEXT     -- Token traded
action              TEXT     -- BUY or SELL
amount_usd          REAL     -- Trade size
leverage_multiplier INTEGER  -- 1-10x
dex_protocol        TEXT     -- uniswap_v3, etc.
was_copied          INTEGER  -- 1 if we copied it
```

---

## System Flow Example

**Scenario:** A tracked wallet buys $5000 of ETH on Uniswap V3

```
1. trade_monitor (60s loop)
   → Checks wallet 0xabc... from block 23,800,000 to 23,800,100
   → Finds tx: 0x123...

2. dex_parser
   → Fetches tx from eth.drpc.org
   → Parses Uniswap V3 Swap event
   → Token in: USDC ($5000)
   → Token out: ETH (2.0 ETH @ $2500/ETH)
   → Action: BUY
   → Returns SwapInfo

3. signal_emitter
   → Wallet allocation: 15%
   → Copy size: $5000 × 15% = $750
   → Creates TradeSignal

4. signal_processor
   ✓ Pass: Only 5 open positions (< 20 max)
   ✓ Pass: ETH is whitelisted
   ✓ Pass: ETH/USDT depth = $50M (> $7500 needed)
   ✓ Pass: Spread = 0.05% (< 0.5% max)
   → Size: $750, Leverage: 1x
   → Returns Position

5. profitview_executor
   → Formats: ETH/USDT LONG, qty=0.3 ETH
   → POST to ProfitView API
   → Response: order_id=PV789, filled @ $2505
   → ✅ Trade executed!

Total time: ~3 seconds
```

---

## Configuration Files

### config.json.example
```json
{
  "etherscan_api_key": "YOUR_KEY",
  "coingecko_api_key": "OPTIONAL",
  "web3_provider_uri": "https://eth.drpc.org",
  "total_capital_usd": 100000,
  "max_position_pct": 5.0
}
```

### signal_processor_config.json
```json
{
  "max_total_positions": 20,
  "max_same_pair_positions": 3,
  "whitelisted_tokens": ["BTC", "ETH", "SOL", "ARB"],
  "stop_loss_pct": 3.0,
  "take_profit_pct": 5.0
}
```

### config/profitview_config.example.json
```json
{
  "api_url": "https://profitview.net/api/v1",
  "api_key": "YOUR_PROFITVIEW_KEY",
  "default_exchange": "binance_futures"
}
```

---

## Performance & Scalability

**Monitoring capacity:**
- 20-50 wallets: ~30s per cycle
- 100 wallets: ~60s per cycle
- Bottleneck: Etherscan API (5 req/sec)

**Trade execution speed:**
- Detection to signal: 1-2 seconds
- Signal to exchange: 2-3 seconds
- **Total latency: 3-5 seconds**

**RPC optimization:**
- Health check: Pre-validates providers
- Parallel queries: Token symbol + decimals
- Fast failover: 0.5s, 0.75s retries only
- Archive limit: 1-day lookback only

**Database:**
- SQLite: Good for < 1M transactions
- Indexed on: wallet_address, tx_hash, timestamp
- Upgrade path: PostgreSQL for production

---

## Error Handling

**Network failures:**
- Etherscan 429 (rate limit) → Wait 60s
- RPC 500/timeout → Retry 2x → Rotate provider
- RPC 400 (old tx) → Skip immediately

**Data failures:**
- Transaction not found → Log & continue
- Token price unavailable → Use $0 (skip)
- DEX not supported → Log & continue

**Exchange failures:**
- Order rejected → Log error + reason
- Insufficient balance → Pause trading
- API timeout → Retry 3x with backoff

---

## Security Considerations

**API Keys:**
- Store in config files (NOT in code)
- Use `.gitignore` to exclude configs
- Rotate keys every 90 days

**Database:**
- No sensitive data stored
- Wallet addresses are public
- Trade history is logged for audit

**Exchange API:**
- ProfitView handles exchange credentials
- No direct exchange API keys in system
- Rate limiting prevents abuse

---

## Deployment Modes

### Paper Mode (Testing)
```bash
python trade_monitor.py --paper-mode
```
- Logs signals to `signals_paper.log`
- No real trades executed
- Safe for testing and validation

### Production Mode
```bash
python trade_monitor.py --no-paper-mode
```
- Executes real trades via ProfitView
- Requires funded exchange account
- Monitor logs: `trade_monitor.log`

### Service Mode (24/7)
```bash
# Linux systemd
sudo systemctl start trade-monitor

# Docker
docker-compose up -d

# PM2 (Node.js)
pm2 start trade_monitor.py --interpreter python3
```

---

## Monitoring & Alerts

**Key metrics to watch:**
- Cycle duration (should be < 60s)
- RPC health (consecutive failures)
- Signal rejection rate
- Order execution success rate

**Alerts to configure:**
- Email on 5+ consecutive RPC failures
- Slack on order rejection
- SMS on exchange API errors
- Dashboard for open positions

---

## Future Enhancements

1. **Multi-chain support:** BSC, Polygon, Arbitrum
2. **Machine learning:** Predict wallet performance
3. **MEV protection:** Flashbots integration
4. **Portfolio rebalancing:** Auto-adjust allocations
5. **Backtesting engine:** Test strategies historically
