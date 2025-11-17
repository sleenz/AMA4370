#!/usr/bin/env python3
"""
Test script to verify transaction caching optimization works correctly.
"""

import sqlite3
import time
import json
from pathlib import Path
import sys

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

def test_database_schema():
    """Test 1: Verify new caching tables exist"""
    print("\n" + "="*70)
    print("TEST 1: Database Schema Verification")
    print("="*70)

    conn = sqlite3.connect('wallet_trading.db')
    cursor = conn.cursor()

    # Check if cached_transactions table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='cached_transactions'
    """)
    result = cursor.fetchone()

    if result:
        print("✅ cached_transactions table exists")

        # Check schema
        cursor.execute("PRAGMA table_info(cached_transactions)")
        columns = cursor.fetchall()
        print("\n   Columns:")
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
    else:
        print("❌ cached_transactions table NOT FOUND")
        print("   Run: python init_database.py")
        return False

    # Check if token_metadata table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='token_metadata'
    """)
    result = cursor.fetchone()

    if result:
        print("\n✅ token_metadata table exists")

        cursor.execute("PRAGMA table_info(token_metadata)")
        columns = cursor.fetchall()
        print("\n   Columns:")
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
    else:
        print("\n❌ token_metadata table NOT FOUND")
        print("   Run: python init_database.py")
        return False

    conn.close()
    return True


def test_wallet_fetch():
    """Test 2: Test fetching wallet transactions with caching"""
    print("\n" + "="*70)
    print("TEST 2: Wallet Transaction Fetch with Caching")
    print("="*70)

    # Check if we have any wallets imported
    conn = sqlite3.connect('wallet_trading.db')
    cursor = conn.cursor()

    cursor.execute("SELECT address, rank_score FROM wallets LIMIT 1")
    wallet = cursor.fetchone()

    if not wallet:
        print("❌ No wallets found in database")
        print("   Import wallets first: python scripts/import_wallets.py")
        conn.close()
        return False

    wallet_address = wallet[0]
    rank_score = wallet[1]

    print(f"\n📊 Testing with wallet: {wallet_address[:10]}... (rank: {rank_score:.2f})")

    # Check if config.json exists
    import os
    if not os.path.exists('config.json'):
        print("❌ config.json not found")
        print("   Create config.json with Etherscan API key")
        conn.close()
        return False

    # Load config
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)

        if not config.get('etherscan_api_key'):
            print("❌ Etherscan API key not found in config.json")
            conn.close()
            return False

        print("✅ Config loaded successfully")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        conn.close()
        return False

    # Import required modules
    try:
        from blockchain_api_client import EtherscanClient
        from wallet_analyzer import fetch_wallet_transactions
        print("✅ Modules imported successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        conn.close()
        return False

    # Test fetch with small time window (7 days to keep it fast)
    print("\n🔄 Fetching transactions (7 days, first run - no cache)...")

    try:
        client = EtherscanClient(config['etherscan_api_key'])

        start_time = time.time()
        trades_first = fetch_wallet_transactions(
            client=client,
            address=wallet_address,
            days=7,  # Small window for testing
            use_cache=True
        )
        first_run_time = time.time() - start_time

        print(f"✅ First run completed")
        print(f"   Trades found: {len(trades_first)}")
        print(f"   Time taken: {first_run_time:.2f} seconds")

        # Check cache
        cursor.execute("""
            SELECT COUNT(*) FROM cached_transactions
            WHERE wallet_address = ?
        """, (wallet_address.lower(),))
        cached_count = cursor.fetchone()[0]
        print(f"   Cached transactions: {cached_count}")

        if cached_count == 0 and len(trades_first) > 0:
            print("   ⚠️  Warning: Transactions found but cache is empty")
            print("   This might indicate cache storage is not working")

        # Second run (should use cache)
        if cached_count > 0:
            print("\n🔄 Fetching transactions (second run - should use cache)...")

            start_time = time.time()
            trades_second = fetch_wallet_transactions(
                client=client,
                address=wallet_address,
                days=7,
                use_cache=True
            )
            second_run_time = time.time() - start_time

            print(f"✅ Second run completed")
            print(f"   Trades found: {len(trades_second)}")
            print(f"   Time taken: {second_run_time:.2f} seconds")

            # Calculate speedup
            if second_run_time > 0 and first_run_time > 0:
                speedup = first_run_time / second_run_time
                print(f"\n📈 Performance Improvement: {speedup:.2f}x faster")

                if speedup > 2:
                    print("   ✅ EXCELLENT: Cache is working as expected!")
                elif speedup > 1.2:
                    print("   ✅ GOOD: Cache is providing speedup")
                else:
                    print("   ⚠️  WARNING: Cache speedup is minimal")
        else:
            print("\n⚠️  Skipping second run (no cache to test)")

    except Exception as e:
        print(f"❌ Error during fetch: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return False

    conn.close()
    return True


def test_cache_contents():
    """Test 3: Inspect cache contents"""
    print("\n" + "="*70)
    print("TEST 3: Cache Contents Inspection")
    print("="*70)

    conn = sqlite3.connect('wallet_trading.db')
    cursor = conn.cursor()

    # Check total cached transactions
    cursor.execute("SELECT COUNT(*) FROM cached_transactions")
    total_cached = cursor.fetchone()[0]
    print(f"\n📊 Total cached transactions: {total_cached}")

    if total_cached > 0:
        # Show sample cached data
        cursor.execute("""
            SELECT tx_hash, wallet_address, dex_protocol, amount_usd, cached_at
            FROM cached_transactions
            LIMIT 3
        """)
        samples = cursor.fetchall()

        print("\n   Sample cached transactions:")
        for tx_hash, wallet, dex, amount, cached_at in samples:
            print(f"   - {tx_hash[:10]}... | DEX: {dex} | ${amount:.2f} | Cached: {cached_at}")

        # Show DEX protocol distribution
        cursor.execute("""
            SELECT dex_protocol, COUNT(*) as count
            FROM cached_transactions
            GROUP BY dex_protocol
            ORDER BY count DESC
        """)
        dex_dist = cursor.fetchall()

        print("\n   DEX Protocol Distribution:")
        for dex, count in dex_dist:
            print(f"   - {dex}: {count} transactions")
    else:
        print("   No cached transactions yet")
        print("   Run wallet_analyzer.py or wallet_discovery.py to populate cache")

    # Check token metadata cache
    cursor.execute("SELECT COUNT(*) FROM token_metadata")
    total_tokens = cursor.fetchone()[0]
    print(f"\n📊 Total cached tokens: {total_tokens}")

    if total_tokens > 0:
        cursor.execute("""
            SELECT token_address, symbol, decimals
            FROM token_metadata
            LIMIT 5
        """)
        tokens = cursor.fetchall()

        print("\n   Sample cached tokens:")
        for addr, symbol, decimals in tokens:
            print(f"   - {symbol} ({addr[:10]}...) | {decimals} decimals")

    conn.close()
    return True


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("TRANSACTION CACHING OPTIMIZATION TEST SUITE")
    print("="*70)

    # Test 1: Database schema
    if not test_database_schema():
        print("\n❌ Database schema test failed. Run init_database.py first.")
        sys.exit(1)

    # Test 2: Wallet fetch with caching
    test_wallet_fetch()

    # Test 3: Cache contents
    test_cache_contents()

    print("\n" + "="*70)
    print("TESTING COMPLETE")
    print("="*70)
    print("\n")


if __name__ == "__main__":
    main()
