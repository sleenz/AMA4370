"""
Import Discovered Wallets to Database

This script imports wallets from discovered_wallets.csv into the database
for monitoring and copy trading.

Usage:
    python scripts/import_wallets.py
    python scripts/import_wallets.py --csv-path custom_wallets.csv
    python scripts/import_wallets.py --top 10  # Only import top 10 wallets
"""

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import argparse


def import_wallets_from_csv(
    csv_path: str = "discovered_wallets.csv",
    db_path: str = "database/wallets.db",
    top_n: int = None,
    allocation_pct: float = 5.0
) -> None:
    """
    Import wallets from CSV file to database.

    Args:
        csv_path: Path to discovered_wallets.csv
        db_path: Path to wallets database
        top_n: Only import top N wallets (by rank_score)
        allocation_pct: Default allocation percentage for each wallet
    """

    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_path}")
        print(f"\nRun wallet discovery first:")
        print(f"   python wallet_discovery.py")
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

    # Sort by rank_score (descending) and optionally limit
    wallets.sort(key=lambda w: float(w.get('rank_score', 0)), reverse=True)

    if top_n:
        wallets = wallets[:top_n]
        print(f"   Limiting to top {top_n} wallets")

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # Import wallets
    print(f"\n💾 Importing wallets to database...")

    imported = 0
    skipped = 0
    updated = 0

    now = datetime.now().isoformat()

    for wallet in wallets:
        address = wallet['address']
        rank_score = float(wallet.get('rank_score', 0))
        total_trades = int(wallet.get('total_trades', 0))
        winning_trades = int(wallet.get('winning_trades', 0))
        total_pnl = float(wallet.get('total_pnl', 0))
        win_rate = float(wallet.get('win_rate', 0))
        sharpe_ratio = float(wallet.get('sharpe_ratio', 0)) if wallet.get('sharpe_ratio') else None
        avg_return = float(wallet.get('avg_return', 0))
        max_drawdown = float(wallet.get('max_drawdown', 0))

        # Check if wallet already exists
        cursor.execute("SELECT id, is_active FROM wallets WHERE address = ?", (address,))
        existing = cursor.fetchone()

        if existing:
            wallet_id, is_active = existing
            if is_active:
                # Update metrics for active wallet
                cursor.execute("""
                    UPDATE wallets
                    SET rank_score = ?,
                        total_trades = ?,
                        winning_trades = ?,
                        total_pnl = ?,
                        win_rate = ?,
                        sharpe_ratio = ?,
                        avg_return = ?,
                        max_drawdown = ?,
                        last_updated = ?
                    WHERE address = ?
                """, (
                    rank_score, total_trades, winning_trades, total_pnl,
                    win_rate, sharpe_ratio, avg_return, max_drawdown,
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
                    total_pnl, win_rate, sharpe_ratio, avg_return,
                    max_drawdown, allocation_pct, is_active,
                    first_seen, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                address, rank_score, total_trades, winning_trades,
                total_pnl, win_rate, sharpe_ratio, avg_return,
                max_drawdown, allocation_pct, 1,  # is_active = 1
                now, now
            ))
            imported += 1

    conn.commit()

    # Get total active wallets
    cursor.execute("SELECT COUNT(*) FROM wallets WHERE is_active = 1")
    total_active = cursor.fetchone()[0]

    conn.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 IMPORT SUMMARY")
    print(f"{'='*60}")
    print(f"  ✅ Imported:  {imported} new wallets")
    print(f"  🔄 Updated:   {updated} existing wallets")
    print(f"  ⏭️  Skipped:   {skipped} inactive wallets")
    print(f"  📈 Total active wallets: {total_active}")
    print(f"{'='*60}\n")

    if imported > 0 or updated > 0:
        print(f"✅ Wallets ready for monitoring!")
        print(f"\nNext steps:")
        print(f"   1. Start the trade monitor: python trade_monitor.py --paper-mode")
        print(f"   2. Monitor the logs for detected trades")
        print(f"   3. Check ProfitView dashboard for executed orders\n")


def main():
    parser = argparse.ArgumentParser(
        description='Import discovered wallets from CSV to database'
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
        help='Only import top N wallets by rank score'
    )
    parser.add_argument(
        '--allocation',
        type=float,
        default=5.0,
        help='Default allocation percentage per wallet (default: 5.0%%)'
    )

    args = parser.parse_args()

    try:
        import_wallets_from_csv(
            csv_path=args.csv_path,
            db_path=args.db_path,
            top_n=args.top,
            allocation_pct=args.allocation
        )
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
