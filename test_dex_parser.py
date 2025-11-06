"""
Test suite for DEX Parser

Tests parsing of swap transactions from:
- Uniswap V2 (simple and multi-hop)
- Uniswap V3 (single and multi-hop)
- PancakeSwap V2/V3

Usage:
    python test_dex_parser.py
"""

import logging
from web3 import Web3
from dex_parser import DexParser, SwapInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# Real transaction hashes for testing
# NOTE: Replace these with actual transaction hashes from Etherscan
TEST_TRANSACTIONS = {
    'uniswap_v2_simple': {
        'tx_hash': '0x...', #  TODO: Add real Uniswap V2 swap tx
        'expected_protocol': 'uniswap_v2',
        'expected_action': 'BUY',  # or 'SELL'
        'description': 'Uniswap V2 simple swap (USDC → WETH)'
    },

    'uniswap_v2_multihop': {
        'tx_hash': '0x...',  # TODO: Add real multi-hop tx
        'expected_protocol': 'uniswap_v2',
        'expected_multihop': True,
        'description': 'Uniswap V2 multi-hop (USDC → WETH → DAI)'
    },

    'uniswap_v3_single': {
        'tx_hash': '0x...',  # TODO: Add real Uniswap V3 tx
        'expected_protocol': 'uniswap_v3',
        'description': 'Uniswap V3 exactInputSingle (USDC → WETH)'
    },

    'uniswap_v3_multihop': {
        'tx_hash': '0x...',  # TODO: Add real V3 multi-hop tx
        'expected_protocol': 'uniswap_v3',
        'expected_multihop': True,
        'description': 'Uniswap V3 exactInput (USDC → WETH → DAI)'
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_swap_info(swap: SwapInfo) -> None:
    """Pretty print swap information."""
    print("\n" + "="*80)
    print(f"SWAP TRANSACTION: {swap.tx_hash}")
    print("="*80)
    print(f"Protocol:     {swap.dex_protocol}")
    print(f"Block:        {swap.block_number}")
    print(f"Timestamp:    {swap.timestamp}")
    print(f"Router:       {swap.router_address}")
    print()
    print(f"Action:       {swap.action}")
    print(f"Token IN:     {swap.token_in_symbol} ({swap.token_in})")
    print(f"Token OUT:    {swap.token_out_symbol} ({swap.token_out})")
    print()
    print(f"Amount IN:    {swap.amount_in:,.6f} {swap.token_in_symbol} (${swap.amount_in_usd:,.2f})")
    print(f"Amount OUT:   {swap.amount_out:,.6f} {swap.token_out_symbol} (${swap.amount_out_usd:,.2f})")
    print()
    print(f"Multi-hop:    {swap.is_multihop}")
    if swap.is_multihop:
        print(f"Path:         {' → '.join([addr[:10]+'...' for addr in swap.path])}")
    print()
    print(f"Wallet:       {swap.wallet_address}")
    print(f"Recipient:    {swap.recipient_address}")
    print("="*80)


def test_parser_with_tx(
    parser: DexParser,
    tx_hash: str,
    wallet_address: str,
    test_name: str,
    expected: dict
) -> bool:
    """
    Test parser with a single transaction.

    Returns:
        bool: True if test passed
    """
    print(f"\n\n{'#'*80}")
    print(f"# TEST: {test_name}")
    print(f"# {expected.get('description', 'No description')}")
    print(f"{'#'*80}")

    try:
        # Parse transaction
        swap = parser.parse_transaction(tx_hash, wallet_address)

        if not swap:
            print("❌ FAILED: Parser returned None")
            return False

        # Print results
        print_swap_info(swap)

        # Validate expectations
        passed = True

        if 'expected_protocol' in expected:
            if swap.dex_protocol != expected['expected_protocol']:
                print(f"❌ Protocol mismatch: expected {expected['expected_protocol']}, got {swap.dex_protocol}")
                passed = False

        if 'expected_action' in expected:
            if swap.action != expected['expected_action']:
                print(f"❌ Action mismatch: expected {expected['expected_action']}, got {swap.action}")
                passed = False

        if 'expected_multihop' in expected:
            if swap.is_multihop != expected['expected_multihop']:
                print(f"❌ Multi-hop mismatch: expected {expected['expected_multihop']}, got {swap.is_multihop}")
                passed = False

        if 'expected_token_in' in expected:
            if swap.token_in.lower() != expected['expected_token_in'].lower():
                print(f"❌ Token IN mismatch: expected {expected['expected_token_in']}, got {swap.token_in}")
                passed = False

        if 'expected_token_out' in expected:
            if swap.token_out.lower() != expected['expected_token_out'].lower():
                print(f"❌ Token OUT mismatch: expected {expected['expected_token_out']}, got {swap.token_out}")
                passed = False

        if passed:
            print("\n✅ TEST PASSED")
        else:
            print("\n❌ TEST FAILED")

        return passed

    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MANUAL TESTING EXAMPLES
# ============================================================================

def test_manual_example():
    """
    Manual testing example with placeholder data.

    This demonstrates how to use the parser without requiring real transactions.
    """
    print("\n\n" + "="*80)
    print("MANUAL TESTING EXAMPLE (No real transactions)")
    print("="*80)

    print("""
To test the DEX parser with real transactions:

1. Find transaction hashes on Etherscan:
   - Go to https://etherscan.io/
   - Find a recent Uniswap V2 or V3 swap transaction
   - Copy the transaction hash (0x...)

2. Initialize parser:
   ```python
   from web3 import Web3
   from dex_parser import DexParser

   # Connect to Ethereum node (Alchemy, Infura, or local)
   w3 = Web3(Web3.HTTPProvider('https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY'))

   # Create parser
   parser = DexParser(w3, etherscan_api_key='YOUR_KEY')
   ```

3. Parse transaction:
   ```python
   swap = parser.parse_transaction(
       tx_hash='0x...',
       wallet_address='0x...'
   )

   if swap:
       print(f"Swapped {swap.amount_in} {swap.token_in_symbol} for {swap.amount_out} {swap.token_out_symbol}")
       print(f"USD Value: ${swap.amount_out_usd:,.2f}")
   ```

Example Transaction Hashes (Replace with current ones):

Uniswap V2:
- Router: 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D
- Example TX: Find on Etherscan by filtering router transactions

Uniswap V3:
- Router: 0xE592427A0AEce92De3Edee1F18E0157C05861564
- Example TX: Find on Etherscan by filtering router transactions

Common Test Tokens:
- WETH:  0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
- USDC:  0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
- USDT:  0xdAC17F958D2ee523a2206206994597C13D831ec7
- DAI:   0x6B175474E89094C44Da98b954EedeAC495271d0F
    """)


# ============================================================================
# UNIT TESTS (Without requiring blockchain access)
# ============================================================================

def test_action_classification():
    """Test BUY/SELL classification logic."""
    print("\n\n" + "="*80)
    print("TEST: Action Classification")
    print("="*80)

    # Mock parser (no Web3 connection needed for this test)
    from unittest.mock import Mock
    parser = Mock(spec=DexParser)
    parser.STABLECOINS = DexParser.STABLECOINS
    parser.WETH = DexParser.WETH
    parser._classify_action = DexParser._classify_action.__get__(parser)

    test_cases = [
        # (token_in, token_out, expected_action, description)
        ('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', '0xabc...', 'BUY', 'USDC → Token = BUY'),
        ('0xabc...', '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', 'SELL', 'Token → USDC = SELL'),
        ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', '0xabc...', 'BUY', 'WETH → Token = BUY'),
        ('0xabc...', '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', 'SELL', 'Token → WETH = SELL'),
        ('0xabc...', '0xdef...', 'BUY', 'Token → Token = BUY (default)'),
    ]

    passed = 0
    failed = 0

    for token_in, token_out, expected, description in test_cases:
        result = parser._classify_action(token_in, token_out)
        if result == expected:
            print(f"✅ {description}: {result}")
            passed += 1
        else:
            print(f"❌ {description}: expected {expected}, got {result}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_path_decoding():
    """Test V3 path decoding logic."""
    print("\n\n" + "="*80)
    print("TEST: V3 Path Decoding")
    print("="*80)

    from unittest.mock import Mock
    parser = Mock(spec=DexParser)
    parser._decode_path_v3 = DexParser._decode_path_v3.__get__(parser)

    # Example V3 path: tokenA (20 bytes) + fee (3 bytes) + tokenB (20 bytes)
    # USDC → WETH path with 0.3% fee (3000)
    usdc = bytes.fromhex('a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48')  # 20 bytes
    fee = bytes.fromhex('000bb8')  # 3000 (0.3%) as 3 bytes
    weth = bytes.fromhex('c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2')  # 20 bytes

    path_bytes = usdc + fee + weth

    result = parser._decode_path_v3(path_bytes)

    expected = [
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
        '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
    ]

    if result == expected:
        print(f"✅ Decoded path correctly:")
        print(f"   {result[0]} → {result[1]}")
        return True
    else:
        print(f"❌ Path decoding failed:")
        print(f"   Expected: {expected}")
        print(f"   Got:      {result}")
        return False


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    """Run all tests."""
    print("""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                         DEX PARSER TEST SUITE                                  ║
╚═══════════════════════════════════════════════════════════════════════════════╝
    """)

    # Run unit tests (no blockchain required)
    print("\n" + "█"*80)
    print("UNIT TESTS (No blockchain connection required)")
    print("█"*80)

    unit_tests_passed = True
    unit_tests_passed &= test_action_classification()
    unit_tests_passed &= test_path_decoding()

    # Show manual example
    test_manual_example()

    # Integration tests would require real Web3 connection
    print("\n\n" + "█"*80)
    print("INTEGRATION TESTS (Require Web3 connection)")
    print("█"*80)

    print("""
To run integration tests with real transactions:

1. Set environment variables:
   export WEB3_PROVIDER_URI="https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
   export ETHERSCAN_API_KEY="YOUR_KEY"
   export COINGECKO_API_KEY="YOUR_KEY"  # Optional

2. Update TEST_TRANSACTIONS dict with real transaction hashes

3. Uncomment the integration test code below

Example code:
```python
import os
from web3 import Web3

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(os.environ['WEB3_PROVIDER_URI']))
assert w3.isConnected(), "Failed to connect to Ethereum node"

# Create parser
parser = DexParser(
    w3=w3,
    etherscan_api_key=os.environ.get('ETHERSCAN_API_KEY'),
    coingecko_api_key=os.environ.get('COINGECKO_API_KEY')
)

# Run tests
for test_name, test_data in TEST_TRANSACTIONS.items():
    if test_data['tx_hash'].startswith('0x') and len(test_data['tx_hash']) == 66:
        test_parser_with_tx(
            parser=parser,
            tx_hash=test_data['tx_hash'],
            wallet_address='0x0000000000000000000000000000000000000000',
            test_name=test_name,
            expected=test_data
        )
```
    """)

    # Summary
    print("\n\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    if unit_tests_passed:
        print("✅ All unit tests passed")
    else:
        print("❌ Some unit tests failed")

    print("""
Next steps:
1. Add real transaction hashes to TEST_TRANSACTIONS
2. Set up Web3 connection (Alchemy/Infura)
3. Run integration tests with actual blockchain data
    """)


if __name__ == "__main__":
    main()
