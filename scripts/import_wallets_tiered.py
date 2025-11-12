"""
Import Wallets with Tiered Allocation

Allocates more capital to higher-ranked wallets using a tiered system.

Example with 10 wallets:
  Rank 1-3:   10% allocation each (top performers)
  Rank 4-6:   7% allocation each (good performers)
  Rank 7-10:  5% allocation each (decent performers)

Total: (3×10%) + (3×7%) + (4×5%) = 30% + 21% + 20% = 71%

Usage:
    python scripts/import_wallets_tiered.py
    python scripts/import_wallets_tiered.py --top 20 --tier1 15 --tier2 10 --tier3 5
"""

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import argparse


def calculate_tiered_allocation(rank_position, total_wallets, tier1_pct, tier2_pct, tier3_pct):
    """
    Calculate allocation based on rank position.

    Args:
        rank_position: Position in ranking (1 = best, 2 = second best, etc.)
        total_wallets: Total number of wallets
        tier1_pct: Allocation for top tier (%)
        tier2_pct: Allocation for middle tier (%)
        tier3_pct: Allocation for bottom tier (%)

    Returns:
        Allocation percentage for this wallet
    """
    # Calculate tier boundaries
    tier1_size = max(1, int(total_wallets * 0.30))  # Top 30%
    tier2_size = max(1, int(total_wallets * 0.30))  # Next 30%
    # tier3 = remaining 40%

    if rank_position <= tier1_size:
        return tier1_pct
    elif rank_position <= tier1_size + tier2_size:
        return tier2_pct
    else:
        return tier3_pct


def import_wallets_tiered(
    csv_path: str = "discovered_wallets.csv",
    db_path: str = "database/wallets.db",
    top_n: int = None,
    tier1_pct: float = 10.0,
    tier2_pct: float = 7.0,
    tier3_pct: float = 5.0,
    score_column: str = "rank_score"
) -> None:
    """
    Import wallets with tiered allocation based on ranking.

    Args:
        csv_path: Path to discovered wallets CSV
        db_path: Path to database
        top_n: Only import top N wallets
        tier1_pct: Allocation for tier 1 (top 30%)
        tier2_pct: Allocation for tier 2 (middle 30%)
        tier3_pct: Allocation for tier 3 (bottom 40%)
        score_column: Column name for ranking score
    """

    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_path}")
        sys.exit(1)

    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ Database not found: {db_path}")
        print(f"\nInitialize database first:")
        print(f"   python init_database.py --db-path {db_path}")
        sys.exit(1)

    # Read wallets from CSV
    print(f"\n📂 Reading wallets from: {csv_path}")
    wallets = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            wallets.append(row)

    print(f"   Found {len(wallets)} wallets in CSV")

    # Sort by score (if column exists) or total_volume
    if score_column in wallets[0]:
        wallets.sort(key=lambda w: float(w.get(score_column, 0)), reverse=True)
    else:
        print(f"   Note: '{score_column}' not found, sorting by total_volume_usd")
        wallets.sort(key=lambda w: float(w.get('total_volume_usd', 0)), reverse=True)

    # Limit to top N if specified
    if top_n:
        wallets = wallets[:top_n]
        print(f"   Limiting to top {top_n} wallets")

    total_wallets = len(wallets)

    # Calculate tier sizes
    tier1_size = max(1, int(total_wallets * 0.30))
    tier2_size = max(1, int(total_wallets * 0.30))
    tier3_size = total_wallets - tier1_size - tier2_size

    print(f"\n📊 Allocation Strategy:")
    print(f"   Tier 1 (Top {tier1_size} wallets):    {tier1_pct}% each")
    print(f"   Tier 2 (Next {tier2_size} wallets):   {tier2_pct}% each")
    print(f"   Tier 3 (Bottom {tier3_size} wallets): {tier3_pct}% each")

    total_allocation = (tier1_size * tier1_pct) + (tier2_size * tier2_pct) + (tier3_size * tier3_pct)
    print(f"   Total Capital Allocated: {total_allocation:.1f}%")

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # Import wallets with tiered allocation
    print(f"\n💾 Importing wallets with tiered allocation...")

    imported = 0
    skipped = 0
    updated = 0

    now = datetime.now().isoformat()

    for rank, wallet in enumerate(wallets, start=1):
        address = wallet['address']

        # Calculate allocation for this wallet
        allocation = calculate_tiered_allocation(
            rank, total_wallets,
            tier1_pct, tier2_pct, tier3_pct
        )

        # Get metrics (handle different CSV formats)
        total_trades = int(wallet.get('total_trades', 0))
        total_volume = float(wallet.get('total_volume_usd', 0))

        # Calculate derived metrics if not in CSV
        rank_score = float(wallet.get('rank_score', 0)) if 'rank_score' in wallet else total_volume / 10000
        winning_trades = int(wallet.get('winning_trades', total_trades * 0.6))  # Estimate 60% win rate
        total_pnl = float(wallet.get('total_pnl', total_volume * 0.05))  # Estimate 5% return
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_return = (total_pnl / total_trades) if total_trades > 0 else 0

        # Check if wallet exists
        cursor.execute("SELECT id, is_active FROM wallets WHERE address = ?", (address,))
        existing = cursor.fetchone()

        if existing:
            wallet_id, is_active = existing
            if is_active:
                # Update with new allocation
                cursor.execute("""
                    UPDATE wallets
                    SET rank_score = ?,
                        total_trades = ?,
                        winning_trades = ?,
                        total_pnl = ?,
                        win_rate = ?,
                        avg_return = ?,
                        allocation_pct = ?,
                        last_updated = ?
                    WHERE address = ?
                """, (
                    rank_score, total_trades, winning_trades, total_pnl,
                    win_rate, avg_return, allocation,
                    now, address
                ))
                updated += 1
            else:
                skipped += 1
        else:
            # Insert new wallet
            cursor.execute("""
                INSERT INTO wallets (
                    address, rank_score, total_trades, winning_trades,
                    total_pnl, win_rate, avg_return,
                    allocation_pct, is_active,
                    first_seen, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                address, rank_score, total_trades, winning_trades,
                total_pnl, win_rate, avg_return,
                allocation, 1,  # is_active = 1
                now, now
            ))
            imported += 1

        # Show progress for top 10
        if rank <= 10:
            print(f"   #{rank:2d} | {address[:10]}... | Allocation: {allocation:5.1f}% | Score: {rank_score:6.1f}")

    conn.commit()

    # Get summary stats
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(allocation_pct) as total_allocation,
            AVG(allocation_pct) as avg_allocation,
            MAX(allocation_pct) as max_allocation,
            MIN(allocation_pct) as min_allocation
        FROM wallets WHERE is_active = 1
    """)
    stats = cursor.fetchone()

    conn.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 IMPORT SUMMARY")
    print(f"{'='*60}")
    print(f"  ✅ Imported:  {imported} new wallets")
    print(f"  🔄 Updated:   {updated} existing wallets")
    print(f"  ⏭️  Skipped:   {skipped} inactive wallets")
    print(f"\n📈 ALLOCATION SUMMARY")
    print(f"  Total Active Wallets: {stats[0]}")
    print(f"  Total Allocated:      {stats[1]:.1f}%")
    print(f"  Average per Wallet:   {stats[2]:.1f}%")
    print(f"  Highest Allocation:   {stats[3]:.1f}%")
    print(f"  Lowest Allocation:    {stats[4]:.1f}%")
    print(f"{'='*60}\n")

    if imported > 0 or updated > 0:
        print(f"✅ Wallets imported with tiered allocation!")
        print(f"\n💡 Capital Allocation Strategy:")
        print(f"   - Top performers get {tier1_pct}% (maximize gains)")
        print(f"   - Good performers get {tier2_pct}% (balanced risk)")
        print(f"   - Decent performers get {tier3_pct}% (diversification)")
        print(f"\nNext step:")
        print(f"   python trade_monitor.py --paper-mode --interval 60\n")


def main():
    parser = argparse.ArgumentParser(
        description='Import wallets with tiered allocation based on ranking'
    )
    parser.add_argument(
        '--csv-path',
        type=str,
        default='discovered_wallets.csv',
        help='Path to CSV file (default: discovered_wallets.csv)'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='database/wallets.db',
        help='Path to database (default: database/wallets.db)'
    )
    parser.add_argument(
        '--top',
        type=int,
        help='Only import top N wallets'
    )
    parser.add_argument(
        '--tier1',
        type=float,
        default=10.0,
        help='Allocation for top 30%% of wallets (default: 10%%)'
    )
    parser.add_argument(
        '--tier2',
        type=float,
        default=7.0,
        help='Allocation for middle 30%% of wallets (default: 7%%)'
    )
    parser.add_argument(
        '--tier3',
        type=float,
        default=5.0,
        help='Allocation for bottom 40%% of wallets (default: 5%%)'
    )
    parser.add_argument(
        '--score-column',
        type=str,
        default='rank_score',
        help='CSV column for ranking (default: rank_score, fallback: total_volume_usd)'
    )

    args = parser.parse_args()

    try:
        import_wallets_tiered(
            csv_path=args.csv_path,
            db_path=args.db_path,
            top_n=args.top,
            tier1_pct=args.tier1,
            tier2_pct=args.tier2,
            tier3_pct=args.tier3,
            score_column=args.score_column
        )
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
