"""
Setup test data for signal processor tests.

Creates test wallets in the database with ranks.
"""

import sqlite3
from datetime import datetime

DB_PATH = 'wallet_trading.db'

# Test wallet addresses from test_signal_processor.py
TEST_WALLETS = [
    ('0x1234567890123456789012345678901234567890', 1),   # Rank 1
    ('0x2234567890123456789012345678901234567890', 5),   # Rank 5
    ('0x3234567890123456789012345678901234567890', 10),  # Rank 10
    ('0x4234567890123456789012345678901234567890', 1),   # Rank 1
]

def setup_database():
    """Create database schema and insert test wallets."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create wallets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT UNIQUE NOT NULL,
            rank INTEGER,
            score REAL DEFAULT 0.0,
            total_pnl_usd REAL DEFAULT 0.0,
            total_trades INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            is_active BOOLEAN DEFAULT 1,
            added_at TIMESTAMP,
            last_trade_at TIMESTAMP
        )
    """)

    # Create wallet_transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER,
            token_address TEXT,
            amount_usd REAL,
            action TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)

    # Insert test wallets
    for address, rank in TEST_WALLETS:
        cursor.execute("""
            INSERT OR REPLACE INTO wallets (address, rank, is_active, added_at, score)
            VALUES (?, ?, 1, ?, ?)
        """, (address.lower(), rank, datetime.now().isoformat(), 80.0 - rank * 5))

        # Get wallet ID
        cursor.execute("SELECT id FROM wallets WHERE address = ?", (address.lower(),))
        wallet_id = cursor.fetchone()[0]

        # Add some transaction history for balance estimation
        cursor.execute("""
            INSERT INTO wallet_transactions (wallet_id, token_address, amount_usd, action, timestamp)
            VALUES (?, ?, ?, 'BUY', ?)
        """, (wallet_id, '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', 50000.0, datetime.now().isoformat()))

        cursor.execute("""
            INSERT INTO wallet_transactions (wallet_id, token_address, amount_usd, action, timestamp)
            VALUES (?, ?, ?, 'SELL', ?)
        """, (wallet_id, '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', 30000.0, datetime.now().isoformat()))

    conn.commit()
    conn.close()

    print("✅ Test database created successfully")
    print(f"✅ Inserted {len(TEST_WALLETS)} test wallets")

if __name__ == "__main__":
    setup_database()
