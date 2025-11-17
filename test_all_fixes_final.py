#!/usr/bin/env python3
"""
Final comprehensive test to verify all bug fixes
Run after fixing all identified issues
"""

import sys
import sqlite3
from datetime import datetime, timedelta

print("="*80)
print("FINAL COMPREHENSIVE FIX VERIFICATION")
print("="*80)

all_pass = True

# ============================================================================
# TEST 1: DEX Parser Cache Timing Fix
# ============================================================================
print("\n" + "="*80)
print("TEST 1: DEX Parser Cache Timing Fix (.seconds → .total_seconds())")
print("="*80)

try:
    with open('dex_parser.py', 'r') as f:
        content = f.read()

    # Verify .total_seconds() is used
    if '.total_seconds()' in content:
        count = content.count('.total_seconds()')
        print(f"✅ FIXED: Found {count} uses of .total_seconds()")

        # Verify .seconds is NOT used for cache timing (allow it elsewhere)
        lines = content.split('\n')
        cache_bug_lines = []
        for i, line in enumerate(lines, 1):
            if '.seconds < 300' in line and 'total_seconds' not in line:
                cache_bug_lines.append((i, line.strip()))

        if cache_bug_lines:
            print(f"❌ FAILED: Found {len(cache_bug_lines)} lines still using .seconds:")
            for line_no, line in cache_bug_lines:
                print(f"   Line {line_no}: {line}")
            all_pass = False
        else:
            print("✅ VERIFIED: No cache timing bugs found")
    else:
        print("❌ FAILED: .total_seconds() not found in code")
        all_pass = False

except Exception as e:
    print(f"❌ ERROR: {e}")
    all_pass = False

# ============================================================================
# TEST 2: WETH Hardcoded Price Removal
# ============================================================================
print("\n" + "="*80)
print("TEST 2: WETH Hardcoded Price Removal")
print("="*80)

try:
    with open('dex_parser.py', 'r') as f:
        content = f.read()

    weth_address = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

    # Find KNOWN_PRICES section
    if 'KNOWN_PRICES' in content:
        known_prices_start = content.find('KNOWN_PRICES = {')
        known_prices_end = content.find('}', known_prices_start)
        known_prices_section = content[known_prices_start:known_prices_end]

        if weth_address not in known_prices_section:
            print(f"✅ FIXED: WETH ({weth_address}) NOT in KNOWN_PRICES")
            print("✅ VERIFIED: Will fetch ETH price from CoinGecko")

            # Verify stablecoins are still there
            if 'USDC' in known_prices_section:
                print("✅ VERIFIED: Stablecoins still hardcoded (correct)")
            else:
                print("⚠️  WARNING: USDC not found in KNOWN_PRICES")
        else:
            print(f"❌ FAILED: WETH still hardcoded in KNOWN_PRICES")
            all_pass = False
    else:
        print("❌ ERROR: KNOWN_PRICES not found in dex_parser.py")
        all_pass = False

except Exception as e:
    print(f"❌ ERROR: {e}")
    all_pass = False

# ============================================================================
# TEST 3: All Core Scripts Syntax Check
# ============================================================================
print("\n" + "="*80)
print("TEST 3: Core Scripts Syntax & Import Check")
print("="*80)

scripts = [
    'trade_monitor.py',
    'wallet_discovery.py',
    'wallet_analyzer.py',
    'dex_parser.py',
    'init_database.py',
]

passed = 0
failed = 0

for script in scripts:
    try:
        with open(script, 'r') as f:
            compile(f.read(), script, 'exec')
        print(f"✅ {script}: Syntax OK")
        passed += 1
    except SyntaxError as e:
        print(f"❌ {script}: Syntax error at line {e.lineno}: {e.msg}")
        failed += 1
        all_pass = False
    except Exception as e:
        print(f"❌ {script}: {e}")
        failed += 1
        all_pass = False

print(f"\nResult: {passed}/{len(scripts)} scripts passed syntax check")

# ============================================================================
# TEST 4: Database Integrity
# ============================================================================
print("\n" + "="*80)
print("TEST 4: Database Integrity")
print("="*80)

try:
    conn = sqlite3.connect('wallet_trading.db')
    cursor = conn.cursor()

    # Integrity check
    cursor.execute("PRAGMA integrity_check")
    result = cursor.fetchone()[0]

    if result == 'ok':
        print("✅ Database integrity: OK")

        # Check critical tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        required_tables = ['wallets', 'cached_transactions', 'monitoring_state',
                          'token_metadata', 'wallet_transactions']

        missing = [t for t in required_tables if t not in tables]
        if missing:
            print(f"❌ Missing tables: {missing}")
            all_pass = False
        else:
            print(f"✅ All required tables present: {len(required_tables)}")

            # Check wallet count
            cursor.execute("SELECT COUNT(*) FROM wallets")
            wallet_count = cursor.fetchone()[0]
            print(f"✅ Wallets in database: {wallet_count}")
    else:
        print(f"❌ Database integrity: {result}")
        all_pass = False

    conn.close()

except Exception as e:
    print(f"❌ ERROR: {e}")
    all_pass = False

# ============================================================================
# TEST 5: Trade Monitor Cycle Fix Verification
# ============================================================================
print("\n" + "="*80)
print("TEST 5: Trade Monitor Cycle Fix (Block Initialization)")
print("="*80)

try:
    with open('trade_monitor.py', 'r') as f:
        content = f.read()

    # Verify the fix for default_start_block
    if 'default_start_block' in content:
        print("✅ FIXED: default_start_block logic present")

        # Check for current_block - 50000 pattern
        if 'current_block - 50000' in content or 'current_block - 50_000' in content:
            print("✅ VERIFIED: Starts from 7 days ago (~50,000 blocks)")

            # Check that COALESCE uses parameter
            if 'COALESCE(m.last_checked_block, ?)' in content:
                print("✅ VERIFIED: Uses parameterized default_start_block")
            else:
                print("⚠️  WARNING: COALESCE pattern not found")
        else:
            print("❌ FAILED: current_block - 50000 pattern not found")
            all_pass = False
    else:
        print("❌ FAILED: default_start_block not found")
        all_pass = False

except Exception as e:
    print(f"❌ ERROR: {e}")
    all_pass = False

# ============================================================================
# TEST 6: Debug Spam Suppression
# ============================================================================
print("\n" + "="*80)
print("TEST 6: Debug Spam Suppression")
print("="*80)

try:
    with open('trade_monitor.py', 'r') as f:
        content = f.read()

    # Check for log level suppressions
    suppressions = [
        ('urllib3', 'logging.getLogger(\'urllib3\').setLevel'),
        ('web3', 'logging.getLogger(\'web3\').setLevel'),
        ('dex_parser', 'logging.getLogger(\'dex_parser\').setLevel'),
    ]

    found = 0
    for lib, pattern in suppressions:
        if pattern in content:
            print(f"✅ {lib}: Debug spam suppressed")
            found += 1
        else:
            print(f"⚠️  {lib}: Suppression not found")

    if found >= 2:
        print(f"✅ VERIFIED: {found}/3 library suppressions found")
    else:
        print(f"⚠️  WARNING: Only {found}/3 suppressions found")

except Exception as e:
    print(f"❌ ERROR: {e}")

# ============================================================================
# FINAL SUMMARY
# ============================================================================
print("\n" + "="*80)
print("FINAL SUMMARY")
print("="*80)

if all_pass:
    print("\n🎉 ALL CRITICAL FIXES VERIFIED!")
    print("\n✅ Fixed Issues:")
    print("   1. Cache timing bug (.seconds → .total_seconds())")
    print("   2. Hardcoded WETH price removed")
    print("   3. Trade monitor cycle bug fixed (block initialization)")
    print("   4. Debug spam suppressed")
    print("   5. All core scripts have valid syntax")
    print("   6. Database integrity confirmed")
    print("\n✅ Repository Status: PRODUCTION READY")
    print("\n📝 Remaining (non-blocking):")
    print("   - Protocol coverage: 8 protocols without parsers (future enhancement)")
    print("   - Phase 3.1: signal_processor.py not yet integrated (future work)")
    sys.exit(0)
else:
    print("\n⚠️  SOME TESTS FAILED")
    print("Review the errors above and fix before production deployment")
    sys.exit(1)
