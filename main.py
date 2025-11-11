"""
Wallet Copy Trading Bot - Main Entry Point

Integrates wallet discovery, signal processing, and ProfitView execution.

Usage:
    python main.py --mode paper_trade    # Paper trading (default)
    python main.py --mode live           # Live trading (requires confirmation)
"""

import argparse
import time
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from profitview_executor import ProfitViewExecutor


def demo_execution():
    """
    Demo: Shows how to integrate ProfitView executor with your trading signals

    In production, you would:
    1. Get signals from wallet_analyzer.py
    2. Process signals with signal_processor.py
    3. Execute trades with profitview_executor.py
    """

    print("\n" + "="*70)
    print("WALLET COPY TRADING BOT - DEMO MODE")
    print("="*70)
    print("\nThis demo shows ProfitView integration.")
    print("In production, signals would come from wallet analyzer.\n")

    # Initialize executor
    executor = ProfitViewExecutor()

    # Example: Simulate a trading signal from wallet analyzer
    # In production, this would come from signal_processor.py
    demo_signal = {
        'wallet_id': 1,
        'pair': 'BTC/USDT',
        'side': 'BUY',
        'size_usd': 100.0,
        'quantity': 0.002,
        'leverage': 5,
        'entry_price': 50000,
        'stop_loss_price': 49000,
        'take_profit_price': 52000,
        'confidence': 0.85,
        'source': 'wallet_copy_bot_demo'
    }

    print("📊 Demo Trading Signal:")
    print("-" * 70)
    print(f"   Pair: {demo_signal['pair']}")
    print(f"   Side: {demo_signal['side']}")
    print(f"   Size: ${demo_signal['size_usd']}")
    print(f"   Leverage: {demo_signal['leverage']}x")
    print(f"   Entry: ${demo_signal['entry_price']:,}")
    print(f"   Stop Loss: ${demo_signal['stop_loss_price']:,}")
    print(f"   Confidence: {demo_signal['confidence']:.0%}")
    print("-" * 70)

    # Execute the trade
    print("\n🚀 Executing trade via ProfitView...")
    result = executor.send_order(demo_signal)

    # Display result
    print("\n" + "="*70)
    print("EXECUTION RESULT")
    print("="*70)

    if result.success:
        print("✅ Order executed successfully!")
        print(f"   Order ID: {result.order_id}")
        if result.exchange_order_id:
            print(f"   Exchange Order ID: {result.exchange_order_id}")
        print(f"   Status: {result.status}")
        if result.filled_price:
            print(f"   Filled Price: ${result.filled_price:,.2f}")
        if result.filled_quantity:
            print(f"   Filled Quantity: {result.filled_quantity}")
    else:
        print("❌ Order failed!")
        print(f"   Error: {result.error_message}")
        print(f"   Status: {result.status}")

    # Show statistics
    print("\n" + "="*70)
    print("EXECUTOR STATISTICS")
    print("="*70)
    stats = executor.get_statistics()
    print(f"   Mode: {stats['mode'].upper()}")
    print(f"   Orders Submitted: {stats['orders_submitted']}")
    print(f"   Orders Filled: {stats['orders_filled']}")
    print(f"   Orders Failed: {stats['orders_failed']}")
    print(f"   Success Rate: {stats['success_rate']:.1%}")
    print(f"   Total Volume: ${stats['total_volume_usd']:,.2f}")
    print("="*70)

    # Show next steps
    print("\n💡 Next Steps:")
    print("   1. Log into ProfitView dashboard to see the order")
    print("   2. Check P&L tracking")
    print("   3. Integrate with your wallet analyzer signals")
    print("   4. Run in paper trading mode for 1-2 weeks")
    print("   5. Switch to live mode when ready")
    print("\n")


def production_loop():
    """
    Production: Continuous monitoring and execution loop

    This is a template for production use. You would integrate:
    - wallet_discovery.py: Find profitable wallets
    - wallet_analyzer.py: Analyze wallet activity
    - signal_processor.py: Generate trading signals
    - profitview_executor.py: Execute trades
    """

    print("\n" + "="*70)
    print("WALLET COPY TRADING BOT - PRODUCTION MODE")
    print("="*70)
    print("\n⚠️  Production mode is not yet implemented.")
    print("\nTo implement production mode, you need to:")
    print("   1. Create signal_processor.py to generate signals from wallet data")
    print("   2. Integrate wallet_analyzer.py to monitor wallet activity")
    print("   3. Set up continuous monitoring loop")
    print("   4. Add risk management and position sizing")
    print("   5. Implement portfolio management")
    print("\nFor now, use demo mode to test ProfitView integration.")
    print("\nRun: python main.py --demo")
    print("="*70 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Wallet Copy Trading Bot')
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Run demo execution (shows ProfitView integration)'
    )
    parser.add_argument(
        '--production',
        action='store_true',
        help='Run production mode (continuous monitoring)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run integration tests'
    )

    args = parser.parse_args()

    # Default to demo if no args
    if not any([args.demo, args.production, args.test]):
        args.demo = True

    try:
        if args.test:
            print("Running integration tests...")
            import subprocess
            subprocess.run([sys.executable, 'tests/test_profitview_integration.py'])

        elif args.demo:
            demo_execution()

        elif args.production:
            production_loop()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
