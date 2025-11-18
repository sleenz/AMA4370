#!/usr/bin/env python3
"""
Test script for SignalProcessor

Simulates trade signals and tests the full processing pipeline.
"""

import logging
import uuid
from datetime import datetime
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from signal_processor import SignalProcessor

# Mock signal class (matches what trade_monitor sends)
@dataclass
class MockTradeSignal:
    id: str
    wallet_address: str
    token_address: str
    token_symbol: str
    action: str  # 'BUY' or 'SELL'
    amount_usd: float
    leverage: int
    created_at: datetime


def test_signal_processor():
    """Test the signal processor with mock signals."""

    print("\n" + "="*70)
    print("SIGNAL PROCESSOR TEST")
    print("="*70)

    # Initialize processor
    try:
        processor = SignalProcessor(
            config_path='config.json',
            db_path='wallet_trading.db'
        )
    except Exception as e:
        print(f"\n❌ Failed to initialize SignalProcessor: {e}")
        print("\nMake sure:")
        print("  1. config.json exists with required fields")
        print("  2. wallet_trading.db exists with wallets table")
        return False

    # Test Case 1: WETH BUY signal (should pass - known token)
    print("\n" + "-"*70)
    print("TEST 1: WETH BUY Signal (should PASS)")
    print("-"*70)

    signal1 = MockTradeSignal(
        id=str(uuid.uuid4()),
        wallet_address='0x1234567890abcdef1234567890abcdef12345678',  # Mock address
        token_address='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
        token_symbol='WETH',
        action='BUY',
        amount_usd=5000.0,
        leverage=5,
        created_at=datetime.now()
    )

    position1 = processor.process_signal(signal1)

    if position1:
        print(f"\n✅ Test 1 PASSED: Position created")
        print(f"   Pair: {position1.pair}")
        print(f"   Size: ${position1.size_usd:.2f}")
        print(f"   Leverage: {position1.leverage}x")
    else:
        print(f"\n⚠️ Test 1: Signal rejected (may be expected if wallet not in DB)")

    # Test Case 2: WBTC SELL signal
    print("\n" + "-"*70)
    print("TEST 2: WBTC SELL Signal (should PASS)")
    print("-"*70)

    signal2 = MockTradeSignal(
        id=str(uuid.uuid4()),
        wallet_address='0x1234567890abcdef1234567890abcdef12345678',
        token_address='0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',  # WBTC
        token_symbol='WBTC',
        action='SELL',
        amount_usd=10000.0,
        leverage=10,
        created_at=datetime.now()
    )

    position2 = processor.process_signal(signal2)

    if position2:
        print(f"\n✅ Test 2 PASSED: Position created")
        print(f"   Pair: {position2.pair}")
        print(f"   Size: ${position2.size_usd:.2f}")
        print(f"   Leverage: {position2.leverage}x")
    else:
        print(f"\n⚠️ Test 2: Signal rejected")

    # Test Case 3: Unknown token (should fail - token not mapped)
    print("\n" + "-"*70)
    print("TEST 3: Unknown Token Signal (should FAIL - token not mapped)")
    print("-"*70)

    signal3 = MockTradeSignal(
        id=str(uuid.uuid4()),
        wallet_address='0x1234567890abcdef1234567890abcdef12345678',
        token_address='0x0000000000000000000000000000000000000001',  # Unknown token
        token_symbol='UNKNOWN',
        action='BUY',
        amount_usd=1000.0,
        leverage=3,
        created_at=datetime.now()
    )

    position3 = processor.process_signal(signal3)

    if position3:
        print(f"\n❌ Test 3 UNEXPECTED: Position should have been rejected")
    else:
        print(f"\n✅ Test 3 PASSED: Signal correctly rejected (token not mapped)")

    # Test Case 4: Extreme leverage (should be capped)
    print("\n" + "-"*70)
    print("TEST 4: Extreme Leverage Signal (should be CAPPED)")
    print("-"*70)

    signal4 = MockTradeSignal(
        id=str(uuid.uuid4()),
        wallet_address='0x1234567890abcdef1234567890abcdef12345678',
        token_address='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
        token_symbol='WETH',
        action='BUY',
        amount_usd=2000.0,
        leverage=100,  # Extreme leverage
        created_at=datetime.now()
    )

    position4 = processor.process_signal(signal4)

    if position4:
        if position4.leverage < 100:
            print(f"\n✅ Test 4 PASSED: Leverage capped from 100x to {position4.leverage}x")
        else:
            print(f"\n❌ Test 4 FAILED: Leverage should have been capped")
    else:
        print(f"\n⚠️ Test 4: Signal rejected")

    # Print statistics
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    stats = processor.get_statistics()
    print(f"\nSignals processed: {stats['signals_processed']}")
    print(f"Signals accepted: {stats['signals_accepted']}")
    print(f"Signals rejected: {stats['signals_rejected']}")
    print(f"Acceptance rate: {stats['acceptance_rate']:.1f}%")

    if stats['rejection_reasons']:
        print("\nRejection reasons:")
        for reason, count in stats['rejection_reasons'].items():
            print(f"  - {reason}: {count}")

    portfolio = stats['portfolio_summary']
    print(f"\nPortfolio Summary:")
    print(f"  Total positions: {portfolio.total_positions}")
    print(f"  Total notional: ${portfolio.total_notional_usd:,.2f}")
    print(f"  Capital at risk: ${portfolio.total_capital_at_risk_usd:,.2f}")

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70 + "\n")

    return True


if __name__ == "__main__":
    test_signal_processor()
