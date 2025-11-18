"""
Import discovered wallets into the database for monitoring.

Usage:
    python import_wallets.py [csv_file]

Default: discovered_wallets.csv
"""

import csv
import sqlite3
import sys
from datetime import datetime


def import_wallets(csv_path: str = "discovered_wallets.csv", db_path: str = "wallet_trading.db"):
    """Import wallets from CSV into database."""

    # Read CSV
    wallets = []
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                wallets.append({
                    'address': row['address'].lower(),
                    'dex_router_pct': float(row.get('dex_router_pct', 0)),
                    'total_trades': int(row.get('total_trades', 0)),
                    'total_volume_usd': float(row.get('total_volume_usd', 0))
                })
    except FileNotFoundError:
        print(f"ERROR: {csv_path} not found")
        return
    except Exception as e:
        print(f"ERROR reading CSV: {e}")
        return

    if not wallets:
        print("No wallets found in CSV")
        return

    print(f"Found {len(wallets)} wallets in {csv_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Insert wallets
    now = datetime.now().isoformat()
    inserted = 0
    updated = 0

    for wallet in wallets:
        # Equal allocation across all wallets
        allocation = 100.0 / len(wallets)

        # Use dex_router_pct as initial rank score (higher DEX activity = better)
        rank_score = wallet['dex_router_pct']

        try:
            cursor.execute("""
                INSERT INTO wallets (
                    address, rank_score, total_trades, allocation_pct,
                    is_active, first_seen, last_updated, metadata
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET
                    rank_score = excluded.rank_score,
                    total_trades = excluded.total_trades,
                    allocation_pct = excluded.allocation_pct,
                    is_active = 1,
                    last_updated = excluded.last_updated
            """, (
                wallet['address'],
                rank_score,
                wallet['total_trades'],
                allocation,
                now,
                now,
                f'{{"dex_pct": {wallet["dex_router_pct"]}, "volume_usd": {wallet["total_volume_usd"]}}}'
            ))

            if cursor.rowcount == 1:
                inserted += 1
            else:
                updated += 1

        except sqlite3.Error as e:
            print(f"Error inserting {wallet['address'][:10]}...: {e}")

    conn.commit()
    conn.close()

    print(f"\nImported to {db_path}:")
    print(f"  - New wallets: {inserted}")
    print(f"  - Updated wallets: {updated}")
    print(f"  - Total active: {len(wallets)}")
    print(f"\nAllocation: {100.0/len(wallets):.2f}% per wallet")
    print("\nRun 'python trade_monitor.py' to start monitoring")


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "discovered_wallets.csv"
    import_wallets(csv_file)
