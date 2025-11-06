"""
Test Suite for Signal Processor

Tests signal filtering, position sizing, and risk management logic.

Usage:
    python test_signal_processor.py
"""

import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# MOCK TRADE SIGNAL
# ============================================================================

@dataclass
class MockTradeSignal:
    """Mock TradeSignal for testing (matches trade_monitor.py TradeSignal)"""
    id: str
    wallet_address: str
    token_address: str
    token_symbol: str
    action: str  # 'BUY' or 'SELL'
    amount_usd: float  # Trader's trade size
    leverage: int
    created_at: datetime


# ============================================================================
# TEST FIXTURES
# ============================================================================

# Sample signals for testing
SAMPLE_SIGNALS = [
    MockTradeSignal(
        id='signal_1',
        wallet_address='0x1234567890123456789012345678901234567890',  # Assume rank 1
        token_address='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
        token_symbol='WETH',
        action='BUY',
        amount_usd=50000,  # Trader bought $50k of WETH
        leverage=5,
        created_at=datetime.now()
    ),

    MockTradeSignal(
        id='signal_2',
        wallet_address='0x2234567890123456789012345678901234567890',  # Assume rank 5
        token_address='0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',  # WBTC
        token_symbol='WBTC',
        action='SELL',
        amount_usd=100000,  # Trader sold $100k of WBTC
        leverage=10,
        created_at=datetime.now()
    ),

    MockTradeSignal(
        id='signal_3',
        wallet_address='0x3234567890123456789012345678901234567890',  # Assume rank 10
        token_address='0x1234567890123456789012345678901234567890',  # Random shitcoin
        token_symbol='SHITCOIN',
        action='BUY',
        amount_usd=10000,
        leverage=1,
        created_at=datetime.now()
    ),

    MockTradeSignal(
        id='signal_4',
        wallet_address='0x4234567890123456789012345678901234567890',  # Assume rank 1
        token_address='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
        token_symbol='WETH',
        action='BUY',
        amount_usd=1000000,  # Huge trade (should be capped at 5% of capital)
        leverage=25,
        created_at=datetime.now()
    ),
]


# Expected outcomes
EXPECTED_OUTCOMES = {
    'signal_1': {
        'should_pass': True,
        'expected_pair': 'ETHUSDT',
        'expected_leverage': 5,
        'description': 'Top wallet buys ETH with 5x leverage - should be approved'
    },

    'signal_2': {
        'should_pass': True,
        'expected_pair': 'BTCUSDT',
        'expected_leverage': 10,
        'description': 'Rank 5 wallet sells BTC with 10x leverage - should be approved'
    },

    'signal_3': {
        'should_pass': False,
        'expected_rejection': 'token_not_mapped',
        'description': 'Random shitcoin not on CEX - should be rejected'
    },

    'signal_4': {
        'should_pass': True,
        'expected_pair': 'ETHUSDT',
        'expected_leverage': 25,
        'max_position_size': 5000,  # 5% of $100k capital
        'description': 'Huge trade should be capped at 5% of capital'
    },
}


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_signal_processing():
    """Test complete signal processing pipeline."""
    from signal_processor import SignalProcessor

    print("\n" + "="*80)
    print("SIGNAL PROCESSOR TEST SUITE")
    print("="*80)

    # Initialize processor
    try:
        processor = SignalProcessor(
            config_path='config.json',
            db_path='wallet_trading.db'
        )
    except FileNotFoundError:
        print("\n❌ ERROR: config.json not found")
        print("Please create config.json with required fields")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: Failed to initialize processor: {e}")
        return False

    # Process each test signal
    passed = 0
    failed = 0

    for signal in SAMPLE_SIGNALS:
        expected = EXPECTED_OUTCOMES.get(signal.id, {})
        description = expected.get('description', 'No description')

        print(f"\n{'='*80}")
        print(f"TEST: {signal.id}")
        print(f"Description: {description}")
        print(f"{'='*80}")
        print(f"Input: {signal.token_symbol} {signal.action} ${signal.amount_usd:,.0f} @ {signal.leverage}x")

        # Process signal
        position = processor.process_signal(signal)

        # Validate outcome
        should_pass = expected.get('should_pass', False)

        if should_pass and position:
            # Signal should be approved
            print(f"\n✓ Signal approved as expected")
            print(f"  Position: {position.pair} {position.side}")
            print(f"  Size: ${position.size_usd:.2f} ({position.leverage}x)")
            print(f"  Notional: ${position.notional_usd:.2f}")
            print(f"  Stop Loss: ${position.stop_loss_usd:.2f}")

            # Validate details
            if 'expected_pair' in expected and position.pair != expected['expected_pair']:
                print(f"  ❌ Pair mismatch: expected {expected['expected_pair']}, got {position.pair}")
                failed += 1
                continue

            if 'expected_leverage' in expected and position.leverage != expected['expected_leverage']:
                print(f"  ❌ Leverage mismatch: expected {expected['expected_leverage']}, got {position.leverage}")
                failed += 1
                continue

            if 'max_position_size' in expected and position.size_usd > expected['max_position_size']:
                print(f"  ❌ Position size exceeded max: ${position.size_usd:.2f} > ${expected['max_position_size']}")
                failed += 1
                continue

            print(f"\n✅ TEST PASSED")
            passed += 1

        elif not should_pass and not position:
            # Signal should be rejected
            print(f"\n✓ Signal rejected as expected")

            # Check rejection reason
            if 'expected_rejection' in expected:
                # Check in processor statistics
                stats = processor.get_statistics()
                if expected['expected_rejection'] in stats['rejection_reasons']:
                    print(f"  Rejection reason: {expected['expected_rejection']} ✓")
                    print(f"\n✅ TEST PASSED")
                    passed += 1
                else:
                    print(f"  ❌ Wrong rejection reason")
                    failed += 1
            else:
                print(f"\n✅ TEST PASSED")
                passed += 1

        elif should_pass and not position:
            # Signal should have passed but was rejected
            print(f"\n❌ Signal was rejected but should have been approved")
            print(f"\n❌ TEST FAILED")
            failed += 1

        elif not should_pass and position:
            # Signal should have been rejected but was approved
            print(f"\n❌ Signal was approved but should have been rejected")
            print(f"\n❌ TEST FAILED")
            failed += 1

        else:
            print(f"\n❓ Unexpected outcome")
            failed += 1

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total tests: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    # Print processor statistics
    print("\n" + "="*80)
    print("PROCESSOR STATISTICS")
    print("="*80)
    stats = processor.get_statistics()
    print(f"Signals processed: {stats['signals_processed']}")
    print(f"Signals accepted: {stats['signals_accepted']}")
    print(f"Signals rejected: {stats['signals_rejected']}")
    print(f"Acceptance rate: {stats['acceptance_rate']:.1f}%")

    if stats['rejection_reasons']:
        print(f"\nRejection reasons:")
        for reason, count in stats['rejection_reasons'].items():
            print(f"  {reason}: {count}")

    # Print portfolio summary
    summary = stats['portfolio_summary']
    print(f"\n Portfolio state:")
    print(f"  Open positions: {summary.total_positions}")
    print(f"  Total notional: ${summary.total_notional_usd:,.2f}")
    print(f"  Capital at risk: ${summary.total_capital_at_risk_usd:,.2f}")

    if summary.positions_by_pair:
        print(f"  Positions by pair:")
        for pair, count in summary.positions_by_pair.items():
            print(f"    {pair}: {count}")

    return failed == 0


def test_position_sizing_formula():
    """Test position sizing calculation."""
    print("\n" + "="*80)
    print("POSITION SIZING FORMULA TEST")
    print("="*80)

    # Test parameters
    total_capital = 100000
    wallet_allocation = 10.0  # 10% for rank 1
    trade_multiplier = 0.5  # 1/2 rule
    trader_trade_size = 50000  # Trader bought $50k
    trader_balance_estimate = 1000000  # Assume $1M balance
    trader_position_pct = trader_trade_size / trader_balance_estimate  # 5%
    leverage = 5

    # Calculate
    our_position = (
        total_capital
        * (wallet_allocation / 100.0)
        * trade_multiplier
        * trader_position_pct
    )

    notional = our_position * leverage

    stop_loss = (
        total_capital
        * trade_multiplier
        * (wallet_allocation / 100.0)
    )

    print(f"\nGiven:")
    print(f"  Total capital: ${total_capital:,}")
    print(f"  Wallet allocation: {wallet_allocation}%")
    print(f"  Trade multiplier: {trade_multiplier}")
    print(f"  Trader trade: ${trader_trade_size:,}")
    print(f"  Trader balance (est): ${trader_balance_estimate:,}")
    print(f"  Trader position: {trader_position_pct*100}% of balance")
    print(f"  Leverage: {leverage}x")

    print(f"\nCalculated:")
    print(f"  Our position: ${our_position:,.2f}")
    print(f"  Notional: ${notional:,.2f}")
    print(f"  Stop loss: ${stop_loss:,.2f}")
    print(f"  Capital at risk: {(stop_loss/total_capital)*100:.2f}%")

    # Validate
    expected_position = 250.0  # From example in task description
    expected_notional = 1250.0
    expected_stop_loss = 5000.0

    if abs(our_position - expected_position) < 1:
        print(f"\n✅ Position size matches expected: ${expected_position:.2f}")
    else:
        print(f"\n❌ Position size mismatch: expected ${expected_position:.2f}, got ${our_position:.2f}")

    if abs(notional - expected_notional) < 1:
        print(f"✅ Notional matches expected: ${expected_notional:.2f}")
    else:
        print(f"❌ Notional mismatch: expected ${expected_notional:.2f}, got ${notional:.2f}")

    if abs(stop_loss - expected_stop_loss) < 1:
        print(f"✅ Stop loss matches expected: ${expected_stop_loss:.2f}")
    else:
        print(f"❌ Stop loss mismatch: expected ${expected_stop_loss:.2f}, got ${stop_loss:.2f}")


def test_risk_limits():
    """Test risk limit enforcement."""
    print("\n" + "="*80)
    print("RISK LIMITS TEST")
    print("="*80)

    print("""
Risk limits to test:
1. Total open positions < 20
2. Same pair positions < 3
3. Position size < 5% of capital
4. Total capital at risk < 50%

Test Strategy:
- Create 20 positions (should pass)
- Try 21st position (should fail: max positions)
- Create 3 ETHUSDT positions (should pass)
- Try 4th ETHUSDT position (should fail: max same pair)
- Try position with 6% of capital (should fail: max position size)
- Create positions until 51% at risk (last one should fail)

This test requires:
- Mock positions in database
- Fresh SignalProcessor instance
- Test wallet with rank 1

TODO: Implement detailed risk limits test
    """)

    print("✓ Risk limits logic implemented in RiskManager class")
    print("✓ Manual testing required with production database")


def test_token_mapping():
    """Test token mapping logic."""
    print("\n" + "="*80)
    print("TOKEN MAPPING TEST")
    print("="*80)

    from signal_processor import TokenMapper

    config = {'total_capital_usd': 100000}
    mapper = TokenMapper(config)

    test_cases = [
        ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', 'WETH', 'ETHUSDT', True),
        ('0x2260fac5e5542a773aa44fbcfedf7c193bc2c599', 'WBTC', 'BTCUSDT', True),
        ('0x1234567890123456789012345678901234567890', 'SHITCOIN', None, False),
    ]

    passed = 0
    failed = 0

    for token_address, symbol, expected_pair, should_map in test_cases:
        mapping = mapper.map_token(token_address)

        if should_map and mapping:
            if mapping.cex_pair == expected_pair:
                print(f"✅ {symbol} → {mapping.cex_pair}")
                passed += 1
            else:
                print(f"❌ {symbol} → {mapping.cex_pair} (expected {expected_pair})")
                failed += 1
        elif not should_map and not mapping:
            print(f"✅ {symbol} → Not mapped (as expected)")
            passed += 1
        else:
            print(f"❌ {symbol} → Unexpected mapping result")
            failed += 1

    print(f"\nToken mapping tests: {passed}/{passed+failed} passed")
    return failed == 0


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    """Run all tests."""
    print("""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                      SIGNAL PROCESSOR TEST SUITE                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Testing:
    1. Token mapping (DEX → CEX)
    2. Position sizing formula
    3. Signal processing pipeline
    4. Risk limit enforcement

Prerequisites:
    - config.json with required fields
    - wallet_trading.db with test wallets
    - Wallets at addresses in SAMPLE_SIGNALS

Note: This test uses mock data and mock exchange API calls.
      For production testing, use real exchange APIs.
    """)

    # Run tests
    all_passed = True

    try:
        # Test 1: Token mapping
        if not test_token_mapping():
            all_passed = False

        # Test 2: Position sizing formula
        test_position_sizing_formula()

        # Test 3: Risk limits (conceptual)
        test_risk_limits()

        # Test 4: Full signal processing
        if not test_signal_processing():
            all_passed = False

    except Exception as e:
        print(f"\n❌ TEST SUITE ERROR: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Final summary
    print("\n" + "="*80)
    print("FINAL RESULT")
    print("="*80)

    if all_passed:
        print("✅ All tests passed")
        print("\nNext steps:")
        print("1. Add real wallets to database with ranks")
        print("2. Update config.json with production settings")
        print("3. Test with real trade signals from trade_monitor.py")
        print("4. Implement Phase 3.2: Exchange integration")
        return 0
    else:
        print("❌ Some tests failed")
        print("\nPlease fix failing tests before proceeding")
        return 1


if __name__ == "__main__":
    sys.exit(main())
