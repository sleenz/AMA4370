"""
Debug version of wallet discovery that logs every step of the filtering process.

This will help identify where wallets are being filtered out.
"""

import json
import logging
from wallet_discovery import (
    load_config,
    EtherscanClient,
    discover_top_traders,
    fetch_wallet_metrics,
    apply_filters
)


# Setup verbose logging
logging.basicConfig(
    level=logging.INFO,  # Changed from DEBUG to INFO for cleaner output
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def debug_wallet_discovery():
    """
    Run wallet discovery with detailed step-by-step logging.
    """

    print("="*70)
    print("WALLET DISCOVERY DEBUG MODE")
    print("="*70)
    print("\nThis will analyze the filtering pipeline step-by-step.")
    print("We'll scan a SMALL sample (10 blocks) to quickly diagnose issues.\n")

    # Load configuration
    try:
        config = load_config()
        print("✅ Configuration loaded")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return

    # Initialize Etherscan client
    try:
        etherscan = EtherscanClient(
            api_key=config['etherscan_api_key'],
            rate_limit=config['rate_limit_per_second']
        )
        print("✅ Etherscan client initialized")
    except Exception as e:
        print(f"❌ Client initialization error: {e}")
        return

    print("\n" + "="*70)
    print("STEP 1: DISCOVERING ADDRESSES FROM RECENT BLOCKS")
    print("="*70)

    # Get recent blocks (limited to 10 for fast debugging)
    try:
        block_numbers = etherscan.get_recent_blocks(days=1)  # Just 1 day

        if not block_numbers:
            print("❌ No blocks returned - API may be down or rate limited")
            return

        # Sample just 10 blocks for quick testing
        sample_blocks = block_numbers[:10]
        print(f"✅ Got {len(block_numbers)} blocks, sampling {len(sample_blocks)} for testing")

        # Collect addresses from blocks
        address_tx_count = {}
        for i, block_num in enumerate(sample_blocks):
            params = {
                'module': 'proxy',
                'action': 'eth_getBlockByNumber',
                'tag': hex(block_num),
                'boolean': 'true'
            }

            try:
                response = etherscan._make_request(params)
                block_data = response.get('result', {})
                transactions = block_data.get('transactions', [])

                for tx in transactions:
                    from_addr = tx.get('from', '').lower()
                    if from_addr and from_addr != '0x0000000000000000000000000000000000000000':
                        address_tx_count[from_addr] = address_tx_count.get(from_addr, 0) + 1

                print(f"  Block {i+1}/10: Found {len(transactions)} transactions")

            except Exception as e:
                print(f"  ⚠️  Error fetching block {block_num}: {e}")
                continue

        print(f"\n✅ STEP 1 COMPLETE: Found {len(address_tx_count)} unique addresses")

        if len(address_tx_count) == 0:
            print("❌ PROBLEM: No addresses found in blocks")
            print("   → Blocks may be empty or API is not returning transaction data")
            return

        # Sort by transaction count
        sorted_addresses = sorted(
            address_tx_count.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Show top 5
        print(f"\nTop 5 most active addresses:")
        for addr, count in sorted_addresses[:5]:
            print(f"  {addr}: {count} transactions")

        # Take top 10 addresses for detailed analysis
        top_addresses = [addr for addr, count in sorted_addresses[:10]]

    except Exception as e:
        print(f"❌ Error in address discovery: {e}")
        return

    print("\n" + "="*70)
    print(f"STEP 2: ANALYZING {len(top_addresses)} ADDRESSES")
    print("="*70)
    print("\nWe'll fetch metrics and apply filters one by one.\n")

    filter_stats = {
        'total': len(top_addresses),
        'is_contract': 0,
        'min_trades': 0,
        'min_volume': 0,
        'recent_activity': 0,
        'passed': 0
    }

    passed_wallets = []

    for i, address in enumerate(top_addresses):
        print(f"\n--- Wallet {i+1}/{len(top_addresses)}: {address[:10]}... ---")

        # Fetch wallet metrics
        try:
            metrics = fetch_wallet_metrics(etherscan, address, days_back=90)

            if metrics is None:
                # Check if it's because it's a contract
                if etherscan.is_contract(address):
                    print(f"  ❌ FILTERED: Contract address")
                    filter_stats['is_contract'] += 1
                else:
                    print(f"  ❌ FILTERED: No transactions found")
                continue

            # Display metrics
            print(f"  Metrics:")
            print(f"    - Total trades: {metrics.total_trades}")
            print(f"    - Volume: ${metrics.total_volume_usd:,.2f}")
            print(f"    - Last active: {metrics.days_since_last_activity} days ago")
            print(f"    - Unique tokens: {metrics.unique_tokens}")
            print(f"    - Is contract: {metrics.is_contract}")

            # Apply filters one by one
            if metrics.is_contract:
                print(f"  ❌ FILTERED: Contract address")
                filter_stats['is_contract'] += 1
                continue

            if metrics.total_trades < 30:
                print(f"  ❌ FILTERED: Only {metrics.total_trades} trades (need 30+)")
                filter_stats['min_trades'] += 1
                continue

            if metrics.total_volume_usd < 10000:
                print(f"  ❌ FILTERED: Only ${metrics.total_volume_usd:,.2f} volume (need $10k+)")
                filter_stats['min_volume'] += 1
                continue

            if metrics.days_since_last_activity > 14:
                print(f"  ❌ FILTERED: Last active {metrics.days_since_last_activity} days ago (need <14 days)")
                filter_stats['recent_activity'] += 1
                continue

            # Passed all filters!
            print(f"  ✅ PASSED ALL FILTERS!")
            filter_stats['passed'] += 1
            passed_wallets.append(metrics)

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            continue

    # Summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)

    print(f"\nStarting addresses: {filter_stats['total']}")
    print(f"\nFiltered out by:")
    print(f"  - Contract address: {filter_stats['is_contract']}")
    print(f"  - Min trades (30): {filter_stats['min_trades']}")
    print(f"  - Min volume ($10k): {filter_stats['min_volume']}")
    print(f"  - Recent activity (14 days): {filter_stats['recent_activity']}")

    print(f"\n✅ PASSED ALL FILTERS: {filter_stats['passed']}")

    if filter_stats['passed'] > 0:
        print(f"\n{'='*70}")
        print("SUCCESS! Qualified wallets found:")
        print(f"{'='*70}")
        for wallet in passed_wallets:
            print(f"\n{wallet.address}")
            print(f"  Trades: {wallet.total_trades}")
            print(f"  Volume: ${wallet.total_volume_usd:,.2f}")
            print(f"  Last active: {wallet.days_since_last_activity} days ago")
    else:
        print(f"\n{'='*70}")
        print("⚠️  NO WALLETS PASSED FILTERS")
        print(f"{'='*70}")

        # Provide recommendations
        print("\nRECOMMENDATIONS:")

        if filter_stats['is_contract'] == filter_stats['total']:
            print("❌ All addresses were contracts!")
            print("   → The block sampling may be catching mainly contract interactions")
            print("   → Try a different time period or more blocks")

        elif filter_stats['min_trades'] > 0:
            print(f"⚠️  {filter_stats['min_trades']} wallets filtered by min trades")
            print("   → Consider reducing min_trades from 30 to 10-20")

        elif filter_stats['min_volume'] > 0:
            print(f"⚠️  {filter_stats['min_volume']} wallets filtered by min volume")
            print("   → Consider reducing min_volume from $10k to $5k")

        elif filter_stats['recent_activity'] > 0:
            print(f"⚠️  {filter_stats['recent_activity']} wallets filtered by activity")
            print("   → Consider increasing activity window from 14 to 30 days")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    debug_wallet_discovery()
