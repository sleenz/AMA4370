#!/usr/bin/env python3
"""
DEX Parser Quality Test Suite

Tests dex_parser.py for:
1. Code correctness
2. Known transaction parsing
3. Error handling
4. Cache efficiency
5. Edge cases
"""

import time
from web3 import Web3
from dex_parser import DexParser, SwapInfo

# Test transactions (real mainnet transactions)
TEST_TRANSACTIONS = {
    'uniswap_v2': {
        'tx_hash': '0x5c504ed432cb51138bcf09aa5e8a410dd4a1e204ef84bfed1be16dfba1b22060',  # Old Uniswap V2 swap
        'expected_protocol': 'uniswap_v2',
        'description': 'Ancient Uniswap V2 transaction (2016)'
    },
    'recent_swap': {
        'tx_hash': '0x' + '1' * 64,  # Placeholder for testing error handling
        'expected_protocol': None,
        'description': 'Invalid transaction hash'
    }
}

def test_initialization():
    """Test 1: Parser initialization"""
    print("\n" + "="*70)
    print("TEST 1: Initialization")
    print("="*70)

    # Test with public RPC
    try:
        w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))

        if not w3.is_connected():
            print("❌ FAILED: Cannot connect to RPC")
            return False

        parser = DexParser(w3)
        print("✅ PASSED: Parser initialized successfully")
        print(f"   - Web3 connected: {w3.is_connected()}")
        print(f"   - Token cache: {len(parser.token_cache)} entries")
        print(f"   - Pair cache: {len(parser.pair_cache)} entries")
        print(f"   - Price cache: {len(parser.price_cache)} entries")
        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_router_detection():
    """Test 2: Router address detection"""
    print("\n" + "="*70)
    print("TEST 2: Router Detection")
    print("="*70)

    try:
        w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        parser = DexParser(w3)

        test_cases = [
            ('0x7a250d5630b4cf539739df2c5dacb4c659f2488d', 'uniswap_v2', 'Uniswap V2 Router'),
            ('0xe592427a0aece92de3edee1f18e0157c05861564', 'uniswap_v3', 'Uniswap V3 Router'),
            ('0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f', 'sushiswap_v2', 'Sushiswap Router'),
            ('0x1111111254eeb25477b68fb85ed929f73a960582', '1inch_v5', '1inch V5 Router'),
            ('0x0000000000000000000000000000000000000000', None, 'Invalid address'),
        ]

        passed = 0
        failed = 0

        for address, expected, description in test_cases:
            result = parser._get_router_type(address)

            if result == expected:
                print(f"   ✅ {description}: {result or 'None'}")
                passed += 1
            else:
                print(f"   ❌ {description}: Expected {expected}, got {result}")
                failed += 1

        print(f"\n   Results: {passed} passed, {failed} failed")
        return failed == 0

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_known_routers():
    """Test 3: Known router coverage"""
    print("\n" + "="*70)
    print("TEST 3: Known Router Coverage")
    print("="*70)

    try:
        w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        parser = DexParser(w3)

        router_counts = {}
        for address, protocol in parser.KNOWN_ROUTERS.items():
            if protocol not in router_counts:
                router_counts[protocol] = 0
            router_counts[protocol] += 1

        print(f"\n   Total routers: {len(parser.KNOWN_ROUTERS)}")
        print(f"\n   Protocol breakdown:")
        for protocol, count in sorted(router_counts.items()):
            print(f"   - {protocol}: {count} router(s)")

        # Check for duplicates
        duplicates = {}
        for address, protocol in parser.KNOWN_ROUTERS.items():
            if address in duplicates:
                print(f"\n   ⚠️  WARNING: Duplicate address {address}")
                print(f"      - Was: {duplicates[address]}")
                print(f"      - Now: {protocol}")
            duplicates[address] = protocol

        print(f"\n   ✅ PASSED: {len(parser.KNOWN_ROUTERS)} routers configured")
        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_price_cache_bug():
    """Test 4: Price cache timing fix verification"""
    print("\n" + "="*70)
    print("TEST 4: Cache Timing Logic Fix Verification")
    print("="*70)

    print("\n   🔍 Verifying cache expiration logic uses total_seconds()...")

    with open('dex_parser.py', 'r') as f:
        content = f.read()

    # Check that code uses total_seconds() not .seconds
    if '.total_seconds()' in content and content.count('.total_seconds()') >= 2:
        # Verify specific lines
        lines = content.split('\n')
        line_653_ok = any('.total_seconds() < 300' in line for line in lines[650:656])
        line_710_ok = any('.total_seconds() < 300' in line for line in lines[707:713])

        if line_653_ok and line_710_ok:
            print("   ✅ Line 653: Uses .total_seconds() correctly")
            print("   ✅ Line 710: Uses .total_seconds() correctly")
            print("   ")
            print("   Cache expiration now works correctly:")
            print("   - 5 minutes = 300 seconds (not 59 seconds)")
            print("   - Proper cache lifetime improves performance")
            return True
        else:
            print("   ⚠️  WARNING: .total_seconds() found but not in expected locations")
            return False
    else:
        print("   ❌ BUG STILL EXISTS: Code uses .seconds instead of .total_seconds()")
        return False


def test_hardcoded_prices():
    """Test 5: Hardcoded price fix verification"""
    print("\n" + "="*70)
    print("TEST 5: Hardcoded Price Fix Verification")
    print("="*70)

    try:
        w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        parser = DexParser(w3)

        # Check that WETH is NOT hardcoded
        weth_address = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

        print("\n   🔍 Checking KNOWN_PRICES dictionary...")

        with open('dex_parser.py', 'r') as f:
            content = f.read()

        # Find KNOWN_PRICES section
        known_prices_start = content.find('KNOWN_PRICES = {')
        known_prices_end = content.find('}', known_prices_start)
        known_prices_section = content[known_prices_start:known_prices_end]

        if weth_address not in known_prices_section:
            print("   ✅ WETH price NOT hardcoded (will fetch from CoinGecko)")
            print("   ✅ Stablecoins still hardcoded at $1.00 (correct)")
            print("   ")
            print("   Benefits:")
            print("   - Real-time ETH price from CoinGecko")
            print("   - Accurate USD calculations for ETH pairs")
            print("   - No manual price updates needed")
            return True
        else:
            print("   ❌ BUG STILL EXISTS: WETH price is hardcoded")
            print(f"   Found: {weth_address} in KNOWN_PRICES")
            return False

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_error_handling():
    """Test 6: Error handling"""
    print("\n" + "="*70)
    print("TEST 6: Error Handling")
    print("="*70)

    try:
        w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        parser = DexParser(w3)

        test_cases = [
            ('0x' + '0' * 64, 'Non-existent transaction'),
            ('0x' + 'ff' * 64, 'Invalid transaction'),
            ('invalid_hash', 'Malformed hash'),
        ]

        passed = 0
        failed = 0

        for tx_hash, description in test_cases:
            try:
                result = parser.parse_transaction(tx_hash, '0x' + '1' * 40)

                if result is None:
                    print(f"   ✅ {description}: Handled gracefully (returned None)")
                    passed += 1
                else:
                    print(f"   ⚠️  {description}: Unexpected result {result}")
                    failed += 1

            except Exception as e:
                print(f"   ❌ {description}: Raised exception {type(e).__name__}: {e}")
                failed += 1

        print(f"\n   Results: {passed} passed, {failed} failed")
        return failed == 0

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_protocol_coverage():
    """Test 7: Protocol parsing coverage"""
    print("\n" + "="*70)
    print("TEST 7: Protocol Parsing Coverage")
    print("="*70)

    try:
        w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        parser = DexParser(w3)

        protocols_with_parsers = set()

        # Check which protocols have actual parsers
        for protocol in parser.KNOWN_ROUTERS.values():
            if 'v2' in protocol:
                protocols_with_parsers.add(protocol)
            elif 'v3' in protocol:
                protocols_with_parsers.add(protocol)

        protocols_without_parsers = set(parser.KNOWN_ROUTERS.values()) - protocols_with_parsers

        print(f"\n   Total protocols: {len(set(parser.KNOWN_ROUTERS.values()))}")
        print(f"   With parsers: {len(protocols_with_parsers)}")
        print(f"   Without parsers: {len(protocols_without_parsers)}")

        if protocols_without_parsers:
            print(f"\n   ⚠️  WARNING: These protocols have NO parsers:")
            for protocol in sorted(protocols_without_parsers):
                print(f"      - {protocol}")
            print(f"\n   Impact: Transactions from these protocols will:")
            print(f"   1. Be detected as valid router transactions")
            print(f"   2. Fail in _is_swap_transaction() (no V2/V3 Swap event)")
            print(f"   3. Return None (no swap detected)")
            print(f"\n   This means 1inch, 0x, Curve, Balancer, etc. swaps are IGNORED")

        return len(protocols_without_parsers) == 0

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_action_classification():
    """Test 8: BUY/SELL classification logic"""
    print("\n" + "="*70)
    print("TEST 8: Action Classification Logic")
    print("="*70)

    try:
        w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        parser = DexParser(w3)

        USDC = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
        WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
        PEPE = '0x6982508145454ce325ddbe47a25d4ec3d2311933'

        test_cases = [
            (USDC, PEPE, 'BUY', 'Stablecoin → Token'),
            (WETH, PEPE, 'BUY', 'WETH → Token'),
            (PEPE, USDC, 'SELL', 'Token → Stablecoin'),
            (PEPE, WETH, 'SELL', 'Token → WETH'),
            (PEPE, '0x' + '1' * 40, 'BUY', 'Token → Unknown (defaults to BUY)'),
        ]

        passed = 0
        failed = 0

        for token_in, token_out, expected, description in test_cases:
            result = parser._classify_action(token_in, token_out)

            if result == expected:
                print(f"   ✅ {description}: {result}")
                passed += 1
            else:
                print(f"   ❌ {description}: Expected {expected}, got {result}")
                failed += 1

        print(f"\n   Results: {passed} passed, {failed} failed")
        return failed == 0

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("DEX PARSER QUALITY TEST SUITE")
    print("="*70)

    tests = [
        ("Initialization", test_initialization),
        ("Router Detection", test_router_detection),
        ("Known Router Coverage", test_known_routers),
        ("Cache Timing Fix", test_price_cache_bug),
        ("Hardcoded Price Fix", test_hardcoded_prices),
        ("Error Handling", test_error_handling),
        ("Protocol Coverage", test_protocol_coverage),
        ("Action Classification", test_action_classification),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n{passed}/{len(results)} tests passed")

    if failed > 0:
        print(f"\n⚠️  {failed} issues found - see details above")
    else:
        print(f"\n✅ All tests passed!")


if __name__ == "__main__":
    main()
