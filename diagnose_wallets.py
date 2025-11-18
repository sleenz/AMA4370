#!/usr/bin/env python3
"""
Diagnostic script to analyze what contracts wallets are interacting with.
Helps identify why DEX swaps aren't being detected.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from wallet_discovery import load_config, EtherscanClient

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Known router addresses from dex_parser.py
KNOWN_ROUTERS = {
    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d': 'Uniswap V2',
    '0xe592427a0aece92de3edee1f18e0157c05861564': 'Uniswap V3',
    '0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45': 'Uniswap V3 Router2',
    '0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad': 'Uniswap Universal Router',
    '0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b': 'Uniswap Universal Router (old)',
    '0x1111111254eeb25477b68fb85ed929f73a960582': '1inch V5',
    '0xdef1c0ded9bec7f1a1670819833240f027b25eff': '0x Exchange',
    '0x881d40237659c251811cec9c364ef91dc08d300c': 'MetaMask Swap',
    '0x9008d19f58aabd9ed0d60971565aa8510560ab41': 'CoW Protocol',
}

def analyze_wallet_contracts(address: str, limit: int = 100):
    """Analyze what contracts a wallet is interacting with."""

    print(f"\n{'='*70}")
    print(f"ANALYZING WALLET: {address[:10]}...")
    print(f"{'='*70}")

    # Load config and initialize client
    config = load_config('config/api_keys.json')
    client = EtherscanClient(
        api_key=config['etherscan_api_key'],
        rate_limit=config['rate_limit_per_second']
    )

    # Fetch transactions
    end_time = datetime.now()
    start_time = end_time - timedelta(days=90)

    txns = client.get_transactions(
        address,
        int(start_time.timestamp()),
        int(end_time.timestamp())
    )

    print(f"\nTotal transactions in last 90 days: {len(txns)}")
    print(f"Analyzing first {min(limit, len(txns))} transactions...\n")

    # Analyze 'to' addresses
    to_addresses = Counter()
    function_selectors = Counter()
    tx_types = Counter()

    for tx in txns[:limit]:
        to_addr = tx.get('to', '').lower()

        # Count destination addresses
        if to_addr:
            to_addresses[to_addr] += 1

        # Extract function selector (first 10 chars of input)
        input_data = tx.get('input', '')
        if input_data and len(input_data) >= 10:
            selector = input_data[:10]
            function_selectors[selector] += 1
        elif input_data == '0x':
            function_selectors['0x (ETH transfer)'] += 1

        # Classify transaction type
        if to_addr in [k.lower() for k in KNOWN_ROUTERS.keys()]:
            tx_types['DEX Router'] += 1
        elif input_data == '0x':
            tx_types['ETH Transfer'] += 1
        elif input_data.startswith('0xa9059cbb'):
            tx_types['ERC20 Transfer'] += 1
        elif input_data.startswith('0x095ea7b3'):
            tx_types['ERC20 Approve'] += 1
        else:
            tx_types['Other Contract Call'] += 1

    # Print results
    print("Transaction Types:")
    print("-" * 40)
    for tx_type, count in tx_types.most_common():
        pct = count / min(limit, len(txns)) * 100
        print(f"  {tx_type}: {count} ({pct:.1f}%)")

    print("\nTop 10 Destination Addresses:")
    print("-" * 40)
    for addr, count in to_addresses.most_common(10):
        router_name = KNOWN_ROUTERS.get(addr, "Unknown")
        pct = count / min(limit, len(txns)) * 100
        print(f"  {addr[:10]}... : {count} ({pct:.1f}%) - {router_name}")

    print("\nTop 10 Function Selectors:")
    print("-" * 40)
    KNOWN_SELECTORS = {
        '0xa9059cbb': 'transfer()',
        '0x095ea7b3': 'approve()',
        '0x23b872dd': 'transferFrom()',
        '0x38ed1739': 'swapExactTokensForTokens()',
        '0x7ff36ab5': 'swapExactETHForTokens()',
        '0x18cbafe5': 'swapExactTokensForETH()',
        '0x3593564c': 'execute() [Universal Router]',
        '0x5ae401dc': 'multicall()',
        '0xac9650d8': 'multicall()',
    }

    for selector, count in function_selectors.most_common(10):
        name = KNOWN_SELECTORS.get(selector, "Unknown")
        pct = count / min(limit, len(txns)) * 100
        print(f"  {selector}: {count} ({pct:.1f}%) - {name}")

    # Verdict
    print("\n" + "="*70)
    dex_pct = tx_types.get('DEX Router', 0) / min(limit, len(txns)) * 100
    if dex_pct > 20:
        print(f"✅ This wallet appears to be a DEX trader ({dex_pct:.1f}% DEX transactions)")
    elif dex_pct > 0:
        print(f"⚠️ Low DEX activity ({dex_pct:.1f}% DEX transactions)")
    else:
        transfer_pct = (tx_types.get('ERC20 Transfer', 0) + tx_types.get('ETH Transfer', 0)) / min(limit, len(txns)) * 100
        if transfer_pct > 50:
            print(f"❌ This wallet is NOT a DEX trader - mostly transfers ({transfer_pct:.1f}%)")
            print("   Likely an exchange deposit wallet or transfer bot")
        else:
            print(f"❌ This wallet is NOT using known DEX routers")
            print("   May be using custom contracts or unknown routers")
    print("="*70 + "\n")


if __name__ == "__main__":
    # Use wallet addresses from user's logs
    wallets = [
        '0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4',  # First wallet from logs
    ]

    print("\n" + "="*70)
    print("WALLET CONTRACT ANALYSIS")
    print("="*70)
    print(f"\nAnalyzing {len(wallets)} wallets to determine why no DEX swaps found...")

    for address in wallets:
        analyze_wallet_contracts(address, limit=100)
