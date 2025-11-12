"""
Add monitoring_state table to existing database

This table tracks which blocks have been checked for each wallet.
"""

import sqlite3
import sys

def add_monitoring_table(db_path='database/wallets.db'):
    """Add monitoring_state table to database."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create monitoring_state table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_state (
            wallet_address TEXT PRIMARY KEY,
            last_checked_block INTEGER NOT NULL,
            last_checked_timestamp TIMESTAMP NOT NULL,
            consecutive_errors INTEGER DEFAULT 0,
            total_transactions_found INTEGER DEFAULT 0,
            FOREIGN KEY (wallet_address) REFERENCES wallets(address) ON DELETE CASCADE
        )
    """)

    # Create index for efficient queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_monitoring_state_timestamp
        ON monitoring_state(last_checked_timestamp DESC)
    """)

    conn.commit()

    print("✅ Added monitoring_state table")
    print("   - Table: monitoring_state")
    print("   - Index: idx_monitoring_state_timestamp")

    conn.close()

if __name__ == "__main__":
    try:
        add_monitoring_table()
    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)
