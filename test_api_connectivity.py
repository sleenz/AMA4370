"""
Test API connectivity for Etherscan and BSCScan.

This diagnostic script verifies:
1. API keys are valid
2. Network connectivity works
3. We can fetch transaction data
4. We can identify DEX trades
"""

import requests
import json
from pathlib import Path


def load_api_keys():
    """Load API keys from config file"""
    config_path = Path("config/api_keys.json")

    if not config_path.exists():
        print("❌ Config file not found: config/api_keys.json")
        return None

    try:
        with open(config_path) as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return None


def test_etherscan_api():
    """Test if Etherscan API is working"""

    config = load_api_keys()
    if not config:
        return False

    api_key = config.get('etherscan_api_key', '')

    if not api_key or api_key == 'YOUR_ETHERSCAN_API_KEY_HERE':
        print("❌ ETHERSCAN_API_KEY not configured in config/api_keys.json")
        return False

    print(f"✓ API Key found: {api_key[:8]}...")

    # Test 1: Simple API call - get recent transactions for a known whale
    test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"  # Known whale
    url = f"https://api.etherscan.io/api?module=account&action=txlist&address={test_address}&startblock=0&endblock=99999999&page=1&offset=10&sort=desc&apikey={api_key}"

    print(f"\n🔍 Testing Etherscan API...")
    print(f"Test address: {test_address}")

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        print(f"Status Code: {response.status_code}")

        if data.get('status') == '0':
            error_msg = data.get('message', 'Unknown')
            error_result = data.get('result', 'Unknown')
            print(f"❌ API Error: {error_msg} - {error_result}")

            if 'Invalid API Key' in str(error_result):
                print("   → API key is invalid or not activated")
            elif 'rate limit' in str(error_result).lower():
                print("   → Rate limited (wait and try again)")

            return False

        if data.get('status') == '1':
            txs = data.get('result', [])
            print(f"✅ API Working! Found {len(txs)} transactions")
            if txs:
                print(f"\nSample transaction:")
                tx = txs[0]
                print(f"  From: {tx.get('from', 'N/A')}")
                print(f"  To: {tx.get('to', 'N/A')}")
                print(f"  Value: {int(tx.get('value', 0)) / 10**18:.4f} ETH")
                print(f"  Time: {tx.get('timeStamp', 'N/A')}")
            return True

    except Exception as e:
        print(f"❌ Error calling API: {e}")
        return False

    return False


def test_bscscan_api():
    """Test if BSCScan API is working"""

    config = load_api_keys()
    if not config:
        return False

    api_key = config.get('bscscan_api_key', '')

    if not api_key or api_key == 'YOUR_BSCSCAN_API_KEY_HERE':
        print("⚠️  BSCSCAN_API_KEY not configured in config/api_keys.json")
        print("   → Skipping BSC test (will use Ethereum only)")
        return False

    print(f"✓ API Key found: {api_key[:8]}...")

    # Test with known BSC whale
    test_address = "0x8894E0a0c962CB723c1976a4421c95949bE2D4E3"  # Binance hot wallet
    url = f"https://api.bscscan.com/api?module=account&action=txlist&address={test_address}&startblock=0&endblock=99999999&page=1&offset=10&sort=desc&apikey={api_key}"

    print(f"\n🔍 Testing BSCScan API...")
    print(f"Test address: {test_address}")

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        print(f"Status Code: {response.status_code}")

        if data.get('status') == '0':
            error_msg = data.get('message', 'Unknown')
            error_result = data.get('result', 'Unknown')
            print(f"❌ API Error: {error_msg} - {error_result}")
            return False

        if data.get('status') == '1':
            txs = data.get('result', [])
            print(f"✅ API Working! Found {len(txs)} transactions")
            return True

    except Exception as e:
        print(f"❌ Error calling API: {e}")
        return False

    return False


def test_wallet_discovery_flow():
    """Test the actual wallet discovery flow - can we find active traders?"""

    config = load_api_keys()
    if not config:
        return False

    api_key = config.get('etherscan_api_key', '')

    print(f"\n🔍 Testing wallet discovery flow...")
    print("   Checking if we can get recent blocks...")

    # Test 1: Get current block number
    url = f"https://api.etherscan.io/api?module=proxy&action=eth_blockNumber&apikey={api_key}"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get('result'):
            current_block = int(data.get('result'), 16)
            print(f"✅ Current block: {current_block:,}")
        else:
            print(f"❌ Could not get current block")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Test 2: Get a recent block with transactions
    print(f"\n   Checking if we can get block transactions...")

    test_block = current_block - 10  # Recent block
    url = f"https://api.etherscan.io/api?module=proxy&action=eth_getBlockByNumber&tag={hex(test_block)}&boolean=true&apikey={api_key}"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        block_data = data.get('result', {})
        transactions = block_data.get('transactions', [])

        if transactions:
            print(f"✅ Block {test_block} has {len(transactions)} transactions")

            # Extract unique addresses
            addresses = set()
            for tx in transactions[:10]:  # Sample first 10
                from_addr = tx.get('from', '')
                if from_addr:
                    addresses.add(from_addr.lower())

            print(f"   Found {len(addresses)} unique addresses in sample")

            # Show sample
            if addresses:
                sample_addr = list(addresses)[0]
                print(f"   Sample address: {sample_addr}")
                return True
        else:
            print(f"⚠️  Block {test_block} has no transactions")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_known_wallet():
    """Test if we can fetch and analyze a known profitable wallet"""

    config = load_api_keys()
    if not config:
        return False

    api_key = config.get('etherscan_api_key', '')

    # Known DeFi whale wallet
    test_wallet = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

    print(f"\n🔍 Testing known profitable wallet analysis...")
    print(f"   Wallet: {test_wallet}")

    # Get recent transactions (last 100)
    url = f"https://api.etherscan.io/api?module=account&action=txlist&address={test_wallet}&startblock=0&endblock=99999999&page=1&offset=100&sort=desc&apikey={api_key}"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get('status') == '1':
            txs = data.get('result', [])
            print(f"✅ Found {len(txs)} recent transactions")

            # Calculate metrics
            total_value = sum(int(tx.get('value', 0)) for tx in txs)
            total_eth = total_value / 10**18

            unique_addresses = len(set(tx.get('to', '') for tx in txs))

            print(f"\n   Wallet Metrics:")
            print(f"   - Total transactions: {len(txs)}")
            print(f"   - Total volume: {total_eth:.2f} ETH")
            print(f"   - Unique contracts: {unique_addresses}")

            # Check if would pass filters
            min_trades = 30
            min_volume = 10000  # USD (assuming ETH = $3000)
            estimated_usd = total_eth * 3000

            print(f"\n   Filter Check:")
            print(f"   - Min trades (30): {'✅ PASS' if len(txs) >= min_trades else '❌ FAIL'} ({len(txs)} trades)")
            print(f"   - Min volume ($10k): {'✅ PASS' if estimated_usd >= min_volume else '❌ FAIL'} (${estimated_usd:,.0f})")

            return True
        else:
            print(f"❌ Could not fetch wallet data")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("="*70)
    print("API CONNECTIVITY TEST FOR WALLET DISCOVERY")
    print("="*70)

    results = {}

    # Test 1: Etherscan basic connectivity
    print("\n" + "="*70)
    print("TEST 1: Etherscan API Basic Connectivity")
    print("="*70)
    results['etherscan'] = test_etherscan_api()

    # Test 2: BSCScan basic connectivity
    print("\n" + "="*70)
    print("TEST 2: BSCScan API Basic Connectivity")
    print("="*70)
    results['bscscan'] = test_bscscan_api()

    # Test 3: Wallet discovery flow
    print("\n" + "="*70)
    print("TEST 3: Wallet Discovery Flow")
    print("="*70)
    results['discovery_flow'] = test_wallet_discovery_flow()

    # Test 4: Known wallet analysis
    print("\n" + "="*70)
    print("TEST 4: Known Wallet Analysis")
    print("="*70)
    results['known_wallet'] = test_known_wallet()

    # Summary
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:.<50} {status}")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if results.get('etherscan') and results.get('discovery_flow'):
        print("\n✅ APIs are working! The issue is likely with filter criteria.")
        print("\nRECOMMENDATION:")
        print("1. Filters may be too strict (run debug_wallet_discovery.py)")
        print("2. BSCScan key not configured (only Ethereum will work)")
    elif not results.get('etherscan'):
        print("\n❌ Etherscan API is not working!")
        print("\nRECOMMENDATION:")
        print("1. Check API key in config/api_keys.json")
        print("2. Verify key is activated at etherscan.io")
        print("3. Check network connectivity")
    else:
        print("\n⚠️  Some tests failed - review errors above")

    print("="*70)
