"""
Wallet Ranking Algorithm

Analyzes discovered wallets and assigns a comprehensive rank score (0-100).
Higher score = better wallet performance.

Ranking Factors:
1. Trading Activity (30%):
   - Total number of trades
   - Recent activity (days since last trade)

2. Volume & Scale (25%):
   - Total trading volume in USD
   - Average trade size

3. Consistency (20%):
   - Regular trading pattern (not sporadic)
   - Number of unique tokens traded

4. Quality Metrics (25%):
   - If available: Win rate, P&L, Sharpe ratio
   - Fallback: Estimated based on volume patterns

Usage:
    python scripts/rank_wallets.py
    python scripts/rank_wallets.py --csv discovered_wallets.csv --output ranked_wallets.csv
    python scripts/rank_wallets.py --min-trades 20 --min-volume 10000
"""

import csv
import sys
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import argparse


def normalize_score(value, min_val, max_val):
    """Normalize value to 0-100 range."""
    if max_val == min_val:
        return 50.0
    normalized = ((value - min_val) / (max_val - min_val)) * 100
    return max(0, min(100, normalized))


def calculate_activity_score(wallet: Dict, max_trades: int, max_volume: float) -> float:
    """
    Calculate activity score (0-100) based on trading frequency and recency.
    Weight: 30% of total score
    """
    total_trades = int(wallet.get('total_trades', 0))
    days_since_last = int(wallet.get('days_since_last_activity', 365))

    # Trade frequency score (0-100)
    trade_score = normalize_score(total_trades, 0, max_trades)

    # Recency score (0-100) - recent activity is better
    # 0 days = 100, 7 days = 80, 30 days = 50, 90 days = 20, 180+ days = 0
    if days_since_last <= 7:
        recency_score = 100
    elif days_since_last <= 30:
        recency_score = 100 - ((days_since_last - 7) * 2.17)  # Linear decay
    elif days_since_last <= 90:
        recency_score = 50 - ((days_since_last - 30) * 0.5)
    else:
        recency_score = max(0, 20 - ((days_since_last - 90) * 0.22))

    # Combined activity score (70% trades, 30% recency)
    activity_score = (trade_score * 0.7) + (recency_score * 0.3)

    return activity_score


def calculate_volume_score(wallet: Dict, max_volume: float, max_trades: int) -> float:
    """
    Calculate volume & scale score (0-100).
    Weight: 25% of total score
    """
    total_volume = float(wallet.get('total_volume_usd', 0))
    total_trades = int(wallet.get('total_trades', 1))

    # Volume score (0-100)
    volume_score = normalize_score(total_volume, 0, max_volume)

    # Average trade size
    avg_trade_size = total_volume / total_trades if total_trades > 0 else 0

    # Avg trade size score (0-100)
    # Small trades (<$100) = low score, Medium ($1k-10k) = good, Large (>$50k) = excellent
    if avg_trade_size < 100:
        size_score = 20
    elif avg_trade_size < 1000:
        size_score = 40 + (avg_trade_size - 100) / 900 * 30  # 40-70
    elif avg_trade_size < 10000:
        size_score = 70 + (avg_trade_size - 1000) / 9000 * 20  # 70-90
    else:
        size_score = 90 + min(10, (avg_trade_size - 10000) / 40000 * 10)  # 90-100

    # Combined volume score (80% total volume, 20% avg size)
    return (volume_score * 0.8) + (size_score * 0.2)


def calculate_consistency_score(wallet: Dict, max_tokens: int) -> float:
    """
    Calculate consistency score (0-100) based on trading patterns.
    Weight: 20% of total score
    """
    unique_tokens = int(wallet.get('unique_tokens', 1))
    total_trades = int(wallet.get('total_trades', 1))

    # Token diversity score (0-100)
    # Trading many different tokens = more sophisticated
    token_score = normalize_score(unique_tokens, 0, min(max_tokens, 50))

    # Trading frequency consistency
    # More trades = more consistent activity
    if total_trades < 10:
        consistency = 20
    elif total_trades < 50:
        consistency = 40 + (total_trades - 10) / 40 * 30
    elif total_trades < 100:
        consistency = 70 + (total_trades - 50) / 50 * 20
    else:
        consistency = 90 + min(10, (total_trades - 100) / 200 * 10)

    # Combined consistency score (60% tokens, 40% frequency)
    return (token_score * 0.6) + (consistency * 0.4)


def calculate_quality_score(wallet: Dict) -> float:
    """
    Calculate quality score (0-100) based on performance metrics.
    Weight: 25% of total score
    """
    # If we have actual performance metrics, use them
    if 'win_rate' in wallet:
        win_rate = float(wallet.get('win_rate', 50))
        quality_score = normalize_score(win_rate, 0, 100)
    elif 'total_pnl' in wallet:
        # Estimate quality from P&L
        total_pnl = float(wallet.get('total_pnl', 0))
        if total_pnl > 0:
            quality_score = 60 + min(40, total_pnl / 10000 * 40)
        else:
            quality_score = 40 + max(-40, total_pnl / 10000 * 40)
    else:
        # Fallback: Estimate quality from volume/trades ratio
        # Higher volume per trade = likely more successful
        total_volume = float(wallet.get('total_volume_usd', 0))
        total_trades = int(wallet.get('total_trades', 1))
        avg_trade = total_volume / total_trades if total_trades > 0 else 0

        # Assume wallets with larger avg trades are more successful
        if avg_trade < 500:
            quality_score = 40
        elif avg_trade < 2000:
            quality_score = 50 + (avg_trade - 500) / 1500 * 20
        elif avg_trade < 10000:
            quality_score = 70 + (avg_trade - 2000) / 8000 * 20
        else:
            quality_score = 90 + min(10, (avg_trade - 10000) / 40000 * 10)

    return quality_score


def calculate_rank_score(wallet: Dict, max_trades: int, max_volume: float, max_tokens: int) -> float:
    """
    Calculate comprehensive rank score (0-100) for a wallet.

    Weighting:
    - Activity: 30%
    - Volume: 25%
    - Quality: 25%
    - Consistency: 20%
    """
    activity = calculate_activity_score(wallet, max_trades, max_volume)
    volume = calculate_volume_score(wallet, max_volume, max_trades)
    consistency = calculate_consistency_score(wallet, max_tokens)
    quality = calculate_quality_score(wallet)

    # Weighted average
    rank_score = (
        activity * 0.30 +
        volume * 0.25 +
        quality * 0.25 +
        consistency * 0.20
    )

    return round(rank_score, 2)


def rank_wallets(
    csv_path: str = "discovered_wallets.csv",
    output_path: str = "ranked_wallets.csv",
    min_trades: int = 0,
    min_volume: float = 0.0,
    min_tokens: int = 0
) -> None:
    """
    Rank wallets from CSV and output sorted results.

    Args:
        csv_path: Input CSV file
        output_path: Output CSV file
        min_trades: Minimum trades to include
        min_volume: Minimum volume to include
        min_tokens: Minimum unique tokens to include
    """

    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_path}")
        sys.exit(1)

    # Read all wallets
    print(f"\n📂 Reading wallets from: {csv_path}")
    wallets = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            wallets.append(row)

    print(f"   Found {len(wallets)} wallets")

    # Apply filters
    original_count = len(wallets)

    if min_trades > 0:
        wallets = [w for w in wallets if int(w.get('total_trades', 0)) >= min_trades]
        print(f"   Filtered by min trades ({min_trades}): {len(wallets)} remaining")

    if min_volume > 0:
        wallets = [w for w in wallets if float(w.get('total_volume_usd', 0)) >= min_volume]
        print(f"   Filtered by min volume (${min_volume:,.0f}): {len(wallets)} remaining")

    if min_tokens > 0:
        wallets = [w for w in wallets if int(w.get('unique_tokens', 0)) >= min_tokens]
        print(f"   Filtered by min tokens ({min_tokens}): {len(wallets)} remaining")

    if len(wallets) == 0:
        print(f"\n❌ No wallets pass the filters!")
        sys.exit(1)

    # Calculate max values for normalization
    max_trades = max(int(w.get('total_trades', 0)) for w in wallets)
    max_volume = max(float(w.get('total_volume_usd', 0)) for w in wallets)
    max_tokens = max(int(w.get('unique_tokens', 1)) for w in wallets)

    print(f"\n📊 Calculating rank scores...")
    print(f"   Max trades: {max_trades:,}")
    print(f"   Max volume: ${max_volume:,.2f}")
    print(f"   Max tokens: {max_tokens}")

    # Calculate rank scores
    for wallet in wallets:
        wallet['rank_score'] = calculate_rank_score(
            wallet, max_trades, max_volume, max_tokens
        )

    # Sort by rank score (descending)
    wallets.sort(key=lambda w: w['rank_score'], reverse=True)

    # Add rank position
    for i, wallet in enumerate(wallets, start=1):
        wallet['rank_position'] = i

    # Write ranked results
    print(f"\n💾 Writing ranked wallets to: {output_path}")

    # Get all column names from first wallet
    fieldnames = list(wallets[0].keys())

    # Ensure rank columns come first
    if 'rank_position' in fieldnames:
        fieldnames.remove('rank_position')
    if 'rank_score' in fieldnames:
        fieldnames.remove('rank_score')
    fieldnames = ['rank_position', 'rank_score'] + fieldnames

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(wallets)

    # Show top 20 preview
    print(f"\n{'='*80}")
    print(f"📈 TOP 20 RANKED WALLETS")
    print(f"{'='*80}")
    print(f"{'Rank':<6} {'Score':<7} {'Address':<44} {'Trades':<8} {'Volume':<12} {'Tokens':<7}")
    print(f"{'-'*80}")

    for wallet in wallets[:20]:
        rank = wallet['rank_position']
        score = wallet['rank_score']
        address = wallet['address']
        trades = int(wallet.get('total_trades', 0))
        volume = float(wallet.get('total_volume_usd', 0))
        tokens = int(wallet.get('unique_tokens', 0))

        print(f"#{rank:<5} {score:<7.2f} {address[:42]:<44} {trades:<8,} ${volume:<11,.0f} {tokens:<7}")

    # Summary statistics
    scores = [w['rank_score'] for w in wallets]
    avg_score = sum(scores) / len(scores)

    print(f"\n{'='*80}")
    print(f"📊 RANKING SUMMARY")
    print(f"{'='*80}")
    print(f"  Total Wallets Ranked: {len(wallets):,}")
    print(f"  Filtered Out: {original_count - len(wallets):,}")
    print(f"  Average Score: {avg_score:.2f}")
    print(f"  Highest Score: {max(scores):.2f}")
    print(f"  Lowest Score: {min(scores):.2f}")
    print(f"  Score Distribution:")
    print(f"    - Excellent (90-100): {sum(1 for s in scores if s >= 90):,}")
    print(f"    - Great (80-90):      {sum(1 for s in scores if 80 <= s < 90):,}")
    print(f"    - Good (70-80):       {sum(1 for s in scores if 70 <= s < 80):,}")
    print(f"    - Average (60-70):    {sum(1 for s in scores if 60 <= s < 70):,}")
    print(f"    - Below Avg (<60):    {sum(1 for s in scores if s < 60):,}")
    print(f"{'='*80}\n")

    print(f"✅ Ranked wallets saved to: {output_path}")
    print(f"\nNext steps:")
    print(f"   1. Review top wallets in {output_path}")
    print(f"   2. Import with tiered allocation:")
    print(f"      python scripts/import_wallets_tiered.py --csv-path {output_path} --top 20")
    print(f"   3. Start monitoring:")
    print(f"      python trade_monitor.py --paper-mode\n")


def main():
    parser = argparse.ArgumentParser(
        description='Rank discovered wallets by comprehensive scoring algorithm'
    )
    parser.add_argument(
        '--csv',
        type=str,
        default='discovered_wallets.csv',
        help='Input CSV file (default: discovered_wallets.csv)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='ranked_wallets.csv',
        help='Output CSV file (default: ranked_wallets.csv)'
    )
    parser.add_argument(
        '--min-trades',
        type=int,
        default=0,
        help='Minimum trades to include (default: 0)'
    )
    parser.add_argument(
        '--min-volume',
        type=float,
        default=0.0,
        help='Minimum total volume in USD (default: 0)'
    )
    parser.add_argument(
        '--min-tokens',
        type=int,
        default=0,
        help='Minimum unique tokens traded (default: 0)'
    )

    args = parser.parse_args()

    try:
        rank_wallets(
            csv_path=args.csv,
            output_path=args.output,
            min_trades=args.min_trades,
            min_volume=args.min_volume,
            min_tokens=args.min_tokens
        )
    except Exception as e:
        print(f"\n❌ Ranking failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
