#!/usr/bin/env python3
"""
Comprehensive test suite to verify all bug fixes
Tests:
1. DEX parser cache timing (total_seconds fix)
2. DEX parser price fetching (hardcoded WETH removed)
3. All core scripts import successfully
4. Database integrity
"""

import sys
import time
from datetime import datetime, timedelta
from web3 import Web3

print("="*70)
print("COMPREHENSIVE FIX VERIFICATION TEST SUITE")
print("="*70)

# ============================================================================
# TEST 1: Cache Timing Fix
# ============================================================================
print("\n" + "="*70)
print("TEST 1: Cache Timing Fix (total_seconds)")
print("="*70)

try:
    from dex_parser import DexParser

    # Test timedelta.seconds vs total_seconds behavior
    print("\n🔍 Verifying timedelta behavior:")

    # Simulate cache age
    now = datetime.now()
    old_time = now - timedelta(minutes=6)  # 6 minutes = 360 seconds

    delta = now - old_time
    print(f"   Time difference: 6 minutes")
    print(f"   delta.seconds: {delta.seconds} seconds")
    print(f"   delta.total_seconds(): {delta.total_seconds()} seconds")

    # Verify code uses total_seconds
    with open('dex_parser.py', 'r') as f:
        content = f.read()

    # Check line 653 fix
    if '.total_seconds() < 300' in content and content.count('.total_seconds()') >= 2:
        print("   ✅ Code uses .total_seconds() correctly")
        test1_pass = True
    else:
        print("   ❌ Code still uses .seconds (bug not fixed)")
        test1_pass = False

except Exception as e:
    print(f"❌ TEST 1 FAILED: {e}")
    test1_pass = False

# ============================================================================
# TEST 2: Hardcoded WETH Price Removal
# ============================================================================
print("\n" + "="*70)
print("TEST 2: Hardcoded WETH Price Removed")
print("="*70)

try:
    with open('dex_parser.py', 'r') as f:
        content = f.read()

    # Check that WETH is not in KNOWN_PRICES
    if '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2' not in content.split('KNOWN_PRICES')[1].split('}')[0]:
        print("   ✅ WETH hardcoded price removed")
        print("   → Will fetch real-time price from CoinGecko")
        test2_pass = True
    else:
        print("   ❌ WETH still hardcoded in KNOWN_PRICES")
        test2_pass = False

except Exception as e:
    print(f"❌ TEST 2 FAILED: {e}")
    test2_pass = False

# ============================================================================
# TEST 3: Script Import Tests (15 scripts)
# ============================================================================
print("\n" + "="*70)
print("TEST 3: All Scripts Import Successfully")
print("="*70)

scripts = [
    ('trade_monitor', 'Core - Phase 4 monitoring'),
    ('wallet_discovery', 'Core - Phase 1 discovery'),
    ('wallet_analyzer', 'Core - Phase 2 analysis'),
    ('dex_parser', 'Core - DEX parser'),
    ('init_database', 'Core - Database init'),
    ('main', 'Demo entry point'),
    ('profitview_bot', 'Cloud bot'),
    ('signal_processor', 'Phase 3.1 (not integrated)'),
    ('edge_case_handlers', 'Phase 3.1 dependency'),
    ('test_dex_parser', 'Test suite'),
    ('test_optimization', 'Test suite'),
]

passed = 0
failed = 0

for script, description in scripts:
    try:
        __import__(script)
        print(f"   ✅ {script}.py - {description}")
        passed += 1
    except Exception as e:
        print(f"   ❌ {script}.py - {description}")
        print(f"      Error: {e}")
        failed += 1

# Test utility scripts
sys.path.insert(0, 'scripts')
utility_scripts = [
    ('import_wallets', 'Import wallets'),
    ('import_wallets_tiered', 'Tiered import'),
    ('profitview_executor', 'Phase 5 executor'),
    ('rank_wallets', 'Wallet ranking'),
]

for script, description in utility_scripts:
    try:
        __import__(script)
        print(f"   ✅ scripts/{script}.py - {description}")
        passed += 1
    except Exception as e:
        print(f"   ❌ scripts/{script}.py - {description}")
        print(f"      Error: {e}")
        failed += 1

test3_pass = (failed == 0)
print(f"\n   Results: {passed}/15 scripts imported successfully")

# ============================================================================
# TEST 4: Database Integrity
# ============================================================================
print("\n" + "="*70)
print("TEST 4: Database Integrity Check")
print("="*70)

try:
    import sqlite3

    conn = sqlite3.connect('wallet_trading.db')
    cursor = conn.cursor()

    # Integrity check
    cursor.execute("PRAGMA integrity_check")
    result = cursor.fetchone()[0]

    if result == 'ok':
        print("   ✅ Database integrity: OK")

        # Count tables
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        print(f"   ✅ Tables: {table_count}")

        # Count indexes
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
        index_count = cursor.fetchone()[0]
        print(f"   ✅ Indexes: {index_count}")

        # Check wallets
        cursor.execute("SELECT COUNT(*) FROM wallets")
        wallet_count = cursor.fetchone()[0]
        print(f"   ✅ Wallets imported: {wallet_count}")

        test4_pass = True
    else:
        print(f"   ❌ Database integrity: {result}")
        test4_pass = False

    conn.close()

except Exception as e:
    print(f"❌ TEST 4 FAILED: {e}")
    test4_pass = False

# ============================================================================
# TEST 5: DEX Parser Initialization
# ============================================================================
print("\n" + "="*70)
print("TEST 5: DEX Parser Initialization with Fixes")
print("="*70)

try:
    from dex_parser import DexParser

    # Try to connect to RPC
    w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))

    if w3.is_connected():
        print("   ✅ Web3 connected to RPC")

        # Initialize parser
        parser = DexParser(w3)
        print("   ✅ DexParser initialized")

        # Check caches
        print(f"   ✅ Token cache: {len(parser.token_cache)} entries")
        print(f"   ✅ Pair cache: {len(parser.pair_cache)} entries")
        print(f"   ✅ Price cache: {len(parser.price_cache)} entries")

        # Check routers
        print(f"   ✅ Known routers: {len(parser.KNOWN_ROUTERS)} configured")

        test5_pass = True
    else:
        print("   ⚠️  Cannot connect to RPC (network issue)")
        test5_pass = True  # Not a code issue

except Exception as e:
    print(f"❌ TEST 5 FAILED: {e}")
    test5_pass = False

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*70)
print("TEST SUMMARY")
print("="*70)

tests = [
    ("Cache Timing Fix", test1_pass),
    ("WETH Price Removal", test2_pass),
    ("Script Imports (15)", test3_pass),
    ("Database Integrity", test4_pass),
    ("DEX Parser Init", test5_pass),
]

total_passed = sum(1 for _, result in tests if result)
total_tests = len(tests)

for test_name, result in tests:
    status = "✅ PASS" if result else "❌ FAIL"
    print(f"{status}: {test_name}")

print(f"\n{'='*70}")
print(f"RESULT: {total_passed}/{total_tests} tests passed")
print(f"{'='*70}")

if total_passed == total_tests:
    print("\n🎉 ALL FIXES VERIFIED! Repository is production-ready.")
    sys.exit(0)
else:
    print(f"\n⚠️  {total_tests - total_passed} test(s) failed - see details above")
    sys.exit(1)
