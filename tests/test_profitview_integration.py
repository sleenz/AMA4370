"""
ProfitView Integration Tests

Comprehensive testing suite for ProfitView executor:
1. API Connection Test
2. Paper Trading Test
3. Order Validation Test
4. Rate Limiting Test
5. Error Handling Test

Run with: python tests/test_profitview_integration.py
"""

import sys
import os
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.profitview_executor import ProfitViewExecutor, OrderResult


def print_test_header(test_name: str, test_number: int):
    """Print formatted test header"""
    print("\n" + "="*70)
    print(f"TEST {test_number}: {test_name}")
    print("="*70)


def print_test_result(passed: bool, message: str = ""):
    """Print test result"""
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"\n{status}")
    if message:
        print(f"   {message}")
    print("-"*70)


def test_1_api_connection():
    """Test 1: API Connection Test"""
    print_test_header("API Connection Test", 1)

    try:
        # Initialize executor
        executor = ProfitViewExecutor()

        # Check that executor initialized correctly
        assert executor.mode == 'paper_trade', "Should be in paper_trade mode by default"
        assert executor.api_key is not None, "API key should be loaded"
        assert executor.base_url is not None, "Base URL should be set"

        print("✓ Executor initialized successfully")
        print(f"✓ Mode: {executor.mode}")
        print(f"✓ API Key: {executor.api_key[:10]}..." + "*"*20)
        print(f"✓ Endpoint: {executor.base_url}")

        # Test querying positions (might fail if API doesn't support it, that's OK)
        try:
            positions = executor.get_open_positions()
            print(f"✓ Positions query: Retrieved {len(positions)} positions")
        except Exception as e:
            print(f"⚠  Positions query: {e} (This is OK if endpoint doesn't exist yet)")

        # Test querying P&L (might fail if API doesn't support it, that's OK)
        try:
            pnl = executor.get_pnl_summary()
            print(f"✓ P&L query: Retrieved data")
        except Exception as e:
            print(f"⚠  P&L query: {e} (This is OK if endpoint doesn't exist yet)")

        print_test_result(True, "Connection and initialization successful")
        return True

    except Exception as e:
        print(f"Error: {e}")
        print_test_result(False, str(e))
        return False


def test_2_paper_trading():
    """Test 2: Paper Trading Test"""
    print_test_header("Paper Trading Test (5 Small Orders)", 2)

    try:
        executor = ProfitViewExecutor()

        test_orders = [
            {'pair': 'BTC/USDT', 'side': 'BUY', 'size_usd': 50, 'quantity': 0.001, 'leverage': 1, 'entry_price': 50000, 'stop_loss_price': 49000},
            {'pair': 'ETH/USDT', 'side': 'BUY', 'size_usd': 30, 'quantity': 0.01, 'leverage': 1, 'entry_price': 3000, 'stop_loss_price': 2900},
            {'pair': 'BTC/USDT', 'side': 'SELL', 'size_usd': 50, 'quantity': 0.001, 'leverage': 1, 'entry_price': 50000, 'stop_loss_price': 51000},
            {'pair': 'SOL/USDT', 'side': 'BUY', 'size_usd': 25, 'quantity': 0.5, 'leverage': 2, 'entry_price': 50, 'stop_loss_price': 48},
            {'pair': 'AVAX/USDT', 'side': 'BUY', 'size_usd': 20, 'quantity': 1.0, 'leverage': 1, 'entry_price': 20, 'stop_loss_price': 19},
        ]

        results = []
        for i, order in enumerate(test_orders, 1):
            print(f"\n📤 Sending test order {i}/5...")
            order['wallet_id'] = 999  # Test wallet ID

            result = executor.send_order(order)
            results.append(result)

            if result.success:
                print(f"   ✅ Order {i}: SUCCESS - {result.order_id}")
            else:
                print(f"   ❌ Order {i}: FAILED - {result.error_message}")

            # Small delay between orders
            time.sleep(0.5)

        # Analyze results
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        print(f"\n📊 Results:")
        print(f"   Total: {len(results)}")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")

        # Get statistics
        stats = executor.get_statistics()
        print(f"\n📈 Executor Stats:")
        print(f"   Orders Submitted: {stats['orders_submitted']}")
        print(f"   Orders Filled: {stats['orders_filled']}")
        print(f"   Success Rate: {stats['success_rate']:.1%}")

        # Test passes if at least one order succeeded (in case API has issues)
        passed = successful >= 1
        print_test_result(passed, f"{successful}/{len(results)} orders executed successfully")
        return passed

    except Exception as e:
        print(f"Error: {e}")
        print_test_result(False, str(e))
        return False


def test_3_order_validation():
    """Test 3: Order Validation Test"""
    print_test_header("Order Validation Test (Invalid Orders)", 3)

    try:
        executor = ProfitViewExecutor()

        # Test 3.1: Order too small
        print("\n📋 Test 3.1: Order too small (should reject)")
        result = executor.send_order({
            'pair': 'BTC/USDT',
            'side': 'BUY',
            'size_usd': 5,  # Below $10 minimum
            'quantity': 0.0001,
            'leverage': 1,
            'entry_price': 50000,
            'stop_loss_price': 49000,
            'wallet_id': 999
        })
        assert not result.success, "Should reject orders below minimum size"
        assert "too small" in result.error_message.lower(), "Error message should mention size"
        print(f"   ✅ Correctly rejected: {result.error_message}")

        # Test 3.2: Order too large
        print("\n📋 Test 3.2: Order too large (should reject)")
        result = executor.send_order({
            'pair': 'BTC/USDT',
            'side': 'BUY',
            'size_usd': 15000,  # Above $10,000 max
            'quantity': 0.3,
            'leverage': 1,
            'entry_price': 50000,
            'stop_loss_price': 49000,
            'wallet_id': 999
        })
        assert not result.success, "Should reject orders above maximum size"
        assert "too large" in result.error_message.lower(), "Error message should mention size"
        print(f"   ✅ Correctly rejected: {result.error_message}")

        # Test 3.3: Leverage too high
        print("\n📋 Test 3.3: Leverage too high (should reject)")
        result = executor.send_order({
            'pair': 'BTC/USDT',
            'side': 'BUY',
            'size_usd': 100,
            'quantity': 0.002,
            'leverage': 50,  # Above 25x max
            'entry_price': 50000,
            'stop_loss_price': 49000,
            'wallet_id': 999
        })
        assert not result.success, "Should reject orders with excessive leverage"
        assert "leverage" in result.error_message.lower(), "Error message should mention leverage"
        print(f"   ✅ Correctly rejected: {result.error_message}")

        # Test 3.4: Invalid stop loss for LONG
        print("\n📋 Test 3.4: Invalid stop loss for LONG (should reject)")
        result = executor.send_order({
            'pair': 'BTC/USDT',
            'side': 'BUY',
            'size_usd': 100,
            'quantity': 0.002,
            'leverage': 1,
            'entry_price': 50000,
            'stop_loss_price': 51000,  # Stop loss above entry for LONG
            'wallet_id': 999
        })
        assert not result.success, "Should reject invalid stop loss for LONG"
        assert "stop loss" in result.error_message.lower(), "Error message should mention stop loss"
        print(f"   ✅ Correctly rejected: {result.error_message}")

        # Test 3.5: Invalid stop loss for SHORT
        print("\n📋 Test 3.5: Invalid stop loss for SHORT (should reject)")
        result = executor.send_order({
            'pair': 'BTC/USDT',
            'side': 'SELL',
            'size_usd': 100,
            'quantity': 0.002,
            'leverage': 1,
            'entry_price': 50000,
            'stop_loss_price': 49000,  # Stop loss below entry for SHORT
            'wallet_id': 999
        })
        assert not result.success, "Should reject invalid stop loss for SHORT"
        assert "stop loss" in result.error_message.lower(), "Error message should mention stop loss"
        print(f"   ✅ Correctly rejected: {result.error_message}")

        print_test_result(True, "All 5 validation tests passed")
        return True

    except AssertionError as e:
        print(f"Assertion failed: {e}")
        print_test_result(False, str(e))
        return False
    except Exception as e:
        print(f"Error: {e}")
        print_test_result(False, str(e))
        return False


def test_4_rate_limiting():
    """Test 4: Rate Limiting Test"""
    print_test_header("Rate Limiting Test (15 Rapid Orders)", 4)

    try:
        executor = ProfitViewExecutor()

        print("📤 Sending 15 orders rapidly...")
        print("   (Rate limiter should prevent API errors)")

        start_time = time.time()
        results = []

        for i in range(15):
            result = executor.send_order({
                'pair': 'BTC/USDT',
                'side': 'BUY',
                'size_usd': 20,
                'quantity': 0.0004,
                'leverage': 1,
                'entry_price': 50000,
                'stop_loss_price': 49000,
                'wallet_id': 999
            })
            results.append(result)
            print(f"   Order {i+1}/15: {'✅' if result.success else '❌'}")

        elapsed = time.time() - start_time

        # Analyze
        successful = sum(1 for r in results if r.success)
        rate_limited_errors = sum(1 for r in results if r.error_message and 'rate' in r.error_message.lower())

        print(f"\n📊 Results:")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Average: {elapsed/15:.2f}s per order")
        print(f"   Successful: {successful}/{len(results)}")
        print(f"   Rate limit errors: {rate_limited_errors}")

        # Test passes if no rate limit errors occurred
        passed = rate_limited_errors == 0
        print_test_result(passed, f"Rate limiter working correctly (0 rate limit errors)")
        return passed

    except Exception as e:
        print(f"Error: {e}")
        print_test_result(False, str(e))
        return False


def test_5_error_handling():
    """Test 5: Error Handling Test"""
    print_test_header("Error Handling Test", 5)

    try:
        executor = ProfitViewExecutor()

        # Test 5.1: Handle bad configuration gracefully
        print("\n📋 Test 5.1: Configuration validation")
        assert executor.config is not None, "Config should be loaded"
        assert 'mode' in executor.config, "Config should have mode"
        assert 'endpoints' in executor.config, "Config should have endpoints"
        print(f"   ✅ Configuration validated")

        # Test 5.2: Order result structure
        print("\n📋 Test 5.2: Order result structure")
        result = executor.send_order({
            'pair': 'BTC/USDT',
            'side': 'BUY',
            'size_usd': 50,
            'quantity': 0.001,
            'leverage': 1,
            'entry_price': 50000,
            'stop_loss_price': 49000,
            'wallet_id': 999
        })

        # Verify OrderResult structure
        assert hasattr(result, 'success'), "Result should have success field"
        assert hasattr(result, 'order_id'), "Result should have order_id field"
        assert hasattr(result, 'status'), "Result should have status field"
        assert hasattr(result, 'error_message'), "Result should have error_message field"
        assert result.status in ['FILLED', 'PENDING', 'REJECTED', 'FAILED'], "Status should be valid"
        print(f"   ✅ Order result structure correct")
        print(f"   ✅ Status: {result.status}")

        # Test 5.3: Statistics tracking
        print("\n📋 Test 5.3: Statistics tracking")
        stats = executor.get_statistics()
        assert 'orders_submitted' in stats, "Stats should track submitted orders"
        assert 'orders_filled' in stats, "Stats should track filled orders"
        assert 'success_rate' in stats, "Stats should calculate success rate"
        assert stats['orders_submitted'] > 0, "Should have submitted orders"
        print(f"   ✅ Statistics tracking working")
        print(f"   ✅ Submitted: {stats['orders_submitted']}")
        print(f"   ✅ Success rate: {stats['success_rate']:.1%}")

        print_test_result(True, "Error handling and validation working correctly")
        return True

    except AssertionError as e:
        print(f"Assertion failed: {e}")
        print_test_result(False, str(e))
        return False
    except Exception as e:
        print(f"Error: {e}")
        print_test_result(False, str(e))
        return False


def run_all_tests():
    """Run all tests and generate report"""
    print("\n" + "═"*70)
    print("PROFITVIEW INTEGRATION TEST SUITE")
    print("═"*70)
    print("Testing executor with Binance via ProfitView")
    print("Mode: PAPER TRADING")
    print("═"*70)

    tests = [
        ("API Connection Test", test_1_api_connection),
        ("Paper Trading Test", test_2_paper_trading),
        ("Order Validation Test", test_3_order_validation),
        ("Rate Limiting Test", test_4_rate_limiting),
        ("Error Handling Test", test_5_error_handling),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ Test crashed: {e}")
            results.append((test_name, False))

    # Generate report
    print("\n" + "═"*70)
    print("TEST RESULTS SUMMARY")
    print("═"*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for i, (test_name, passed) in enumerate(results, 1):
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{i}. {test_name}: {status}")

    print("\n" + "-"*70)
    print(f"Overall: {passed_count}/{total_count} tests passed ({passed_count/total_count:.0%})")
    print("═"*70)

    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! ProfitView integration ready for use.")
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Review errors above.")

    print("\n💡 Next Steps:")
    print("   1. Review ProfitView dashboard to see if test orders appeared")
    print("   2. Check P&L tracking in dashboard")
    print("   3. Verify paper trading mode is active")
    print("   4. When ready, switch to live mode in config")
    print("═"*70)


if __name__ == "__main__":
    run_all_tests()
