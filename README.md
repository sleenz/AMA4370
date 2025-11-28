# Wallet Copy Trading Bot

**Automatically copy trades from profitable Ethereum wallets via ProfitView.**

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Test ProfitView connection
python scripts/profitview_executor.py

# 3. Run demo
python main.py --demo

# 4. Find profitable wallets (10-15 min)
python wallet_discovery.py

# 5. Start copying trades
python main.py
```
**Core System:**
- `wallet_discovery.py` - Find profitable wallets
- `wallet_analyzer.py` - Monitor wallet activity
- `signal_processor.py` - Generate trading signals
- `dex_parser.py` - Decode DEX transactions
- `scripts/profitview_executor.py` - Send orders to ProfitView
- `main.py` - Main program

**Configuration:**
- `config/profitview_config.json` - Your ProfitView API keys (configured)
- `config/api_keys.json` - Etherscan API key (add yours)
- `config/config.json` - Trading parameters

## How It Works

```
1. DISCOVER WALLETS
   python wallet_discovery.py
   ↓
   Finds 10-50 profitable wallets
   Saves to: discovered_wallets.csv

2. MONITOR WALLETS
   python main.py
   ↓
   Watches wallet transactions in real-time
   Analyzes DEX trades
   Generates signals when they trade

3. EXECUTE TRADES
   Via ProfitView bot (you deployed)
   ↓
   Executes on WooLive (paper trading)
   Tracks P&L automatically
```

---

## 🛠️ Configuration

**Your ProfitView settings (already configured):**
- Webhook Secret: `517b3bcac35bc86e1bea1ec31101b9b583b34387`
- WooLive API: `d8e4c5eb-d3b0-4f4f-a201-7c51e0444434`
- Mode: Paper trading (safe testing)
- Exchange: WOO X (WooLive)

**What you need to add:**
- Etherscan API key (free): https://etherscan.io/apis
- Add to `config/api_keys.json`

---

**Local Database:**
```bash
# Recent orders
sqlite3 database/wallets.db "SELECT * FROM orders ORDER BY submitted_at DESC LIMIT 5;"

# Success rate
sqlite3 database/wallets.db "SELECT status, COUNT(*) FROM orders GROUP BY status;"

# Total volume
sqlite3 database/wallets.db "SELECT SUM(size_usd) FROM orders WHERE status='FILLED';"
```
## Files Overview

**10 Python files total:**

1. `wallet_discovery.py` - Find profitable wallets (run once or periodically)
2. `wallet_analyzer.py` - Monitor wallet activity (used by main.py)
3. `signal_processor.py` - Generate signals (used by main.py)
4. `dex_parser.py` - Decode transactions (used by wallet_analyzer.py)
5. `scripts/profitview_executor.py` - Send to ProfitView (used by main.py)
6. `profitview_bot.py` - Execute trades (deployed on ProfitView)
7. `main.py` - Main program (run this)
8. `init_database.py` - Setup database (auto-runs)
9. `trade_monitor.py` - Track performance (used by main.py)
10. `edge_case_handlers.py` - Handle edge cases (used by signal_processor.py)
