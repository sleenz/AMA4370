# Wallet Copy Trading Bot

**Automatically copy trades from profitable Ethereum wallets via ProfitView.**

**Status:** ✅ Ready to run | Paper trading mode (no risk)

---

## 🚀 Quick Start

You've already deployed the ProfitView bot. Now on your computer:

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

**That's it!** The system will find profitable wallets and copy their trades.

---

## 📖 Complete Guide

**For detailed instructions, read:**
```bash
cat USER_GUIDE.md
```

The USER_GUIDE contains:
- ✅ Detailed explanation of every file
- ✅ Complete wallet discovery process
- ✅ Step-by-step workflow with examples
- ✅ Configuration guide
- ✅ Troubleshooting
- ✅ Performance monitoring
- ✅ Safety & risk management

---

## 📁 Essential Files

**Core System:**
- `wallet_discovery.py` - Find profitable wallets
- `wallet_analyzer.py` - Monitor wallet activity
- `signal_processor.py` - Generate trading signals
- `dex_parser.py` - Decode DEX transactions
- `scripts/profitview_executor.py` - Send orders to ProfitView
- `main.py` - Main program

**Already Deployed:**
- `profitview_bot.py` - Running on ProfitView servers

**Configuration:**
- `config/profitview_config.json` - Your ProfitView API keys (configured)
- `config/api_keys.json` - Etherscan API key (add yours)
- `config/config.json` - Trading parameters

---

## 🎯 How It Works

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

## 📊 Monitor Performance

**ProfitView Dashboard:**
- URL: https://profitview.net/trading
- Check: Bot logs, positions, P&L

**Local Database:**
```bash
# Recent orders
sqlite3 database/wallets.db "SELECT * FROM orders ORDER BY submitted_at DESC LIMIT 5;"

# Success rate
sqlite3 database/wallets.db "SELECT status, COUNT(*) FROM orders GROUP BY status;"

# Total volume
sqlite3 database/wallets.db "SELECT SUM(size_usd) FROM orders WHERE status='FILLED';"
```

---

## 🔧 Troubleshooting

**"Module not found"**
```bash
pip install -r requirements.txt
```

**"Order rejected - 403"**
- Check ProfitView bot is Running (green status)
- Check WooLive is connected
- Restart ProfitView bot if needed

**"No wallets found"**
```bash
python wallet_discovery.py  # Takes 10-15 minutes
```

**More help:** See `USER_GUIDE.md` troubleshooting section

---

## 🚨 Safety

**✅ You're in PAPER TRADING mode:**
- No real money used
- All trades on WooLive testnet
- Perfect for testing and learning
- Can run for weeks/months safely

**Only switch to live after:**
- 2-4 weeks successful paper trading
- 100+ executed orders
- Consistent profitability
- Full understanding of risks

---

## 📋 Quick Commands

```bash
# Test ProfitView
python scripts/profitview_executor.py

# Demo mode
python main.py --demo

# Find wallets
python wallet_discovery.py

# Start trading
python main.py

# Stop trading
Ctrl+C
```

---

## 📚 Files Overview

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

**See USER_GUIDE.md for detailed description of each file.**

---

## 🎯 Next Steps

1. Read the complete guide:
   ```bash
   cat USER_GUIDE.md
   ```

2. Install and test:
   ```bash
   pip install -r requirements.txt
   python scripts/profitview_executor.py
   ```

3. Run demo:
   ```bash
   python main.py --demo
   ```

4. Start for real:
   ```bash
   python wallet_discovery.py
   python main.py
   ```

**Questions?** Check USER_GUIDE.md - it has everything!

---

**Ready to start copying profitable traders! 📈**
