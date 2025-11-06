"""
Database Schema Update for Trade Monitoring System (Phase 2.1)

This module adds the necessary tables and columns for real-time trade monitoring:
1. monitoring_state - Tracks last checked block per wallet
2. trade_signals - Queue of copy trade signals
3. wallet_transactions enhancements - Add DEX protocol, leverage, tracking columns

Usage:
    python update_database_schema.py [--db-path wallet_trading.db]

Example:
    >>> from update_database_schema import update_schema
    >>> update_schema('wallet_trading.db')
    >>> # Schema is now ready for Phase 2.1
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_monitoring_state_table(cursor: sqlite3.Cursor) -> None:
    """
    Create monitoring_state table to track monitoring progress per wallet.

    This table prevents duplicate transaction processing by tracking the last
    checked block number for each wallet. It also tracks error counts for
    graceful degradation.

    Columns:
        wallet_address: FK to wallets.address (unique per wallet)
        last_checked_block: Last block number successfully processed
        last_checked_timestamp: When this wallet was last checked
        consecutive_errors: Count of consecutive failures (reset on success)
        last_error: Most recent error message for debugging
        total_transactions_found: Cumulative count of transactions detected

    Args:
        cursor: SQLite database cursor
    """
    logger.info("Creating monitoring_state table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_state (
            wallet_address TEXT PRIMARY KEY,
            last_checked_block INTEGER NOT NULL DEFAULT 0,
            last_checked_timestamp TIMESTAMP NOT NULL,
            consecutive_errors INTEGER DEFAULT 0,
            last_error TEXT,
            total_transactions_found INTEGER DEFAULT 0,
            FOREIGN KEY (wallet_address) REFERENCES wallets(address) ON DELETE CASCADE
        )
    """)

    # Create index for error tracking
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_monitoring_state_errors
        ON monitoring_state(consecutive_errors)
        WHERE consecutive_errors > 0
    """)

    logger.info("✓ monitoring_state table created")


def create_trade_signals_table(cursor: sqlite3.Cursor) -> None:
    """
    Create trade_signals table for copy trade signal queue.

    This table stores pending copy trade signals that will be executed by
    Phase 2.2. Each signal represents a decision to copy a wallet's trade.

    Columns:
        id: UUID primary key
        wallet_address: Source wallet being copied
        source_tx_hash: Original transaction hash from tracked wallet
        token_address: Token being traded
        action: 'BUY' or 'SELL'
        amount_usd: Trade size in USD from source wallet
        leverage: Leverage multiplier (1 = no leverage)
        allocation_pct: Wallet's allocation percentage (from wallets table)
        copy_size_usd: Calculated copy size (amount_usd × allocation_pct)
        status: 'pending', 'executed', 'failed', 'rejected'
        created_at: When signal was generated
        executed_at: When signal was executed (NULL if pending)
        rejection_reason: Why signal was rejected (risk limits, etc.)

    Args:
        cursor: SQLite database cursor
    """
    logger.info("Creating trade_signals table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_signals (
            id TEXT PRIMARY KEY,
            wallet_address TEXT NOT NULL,
            source_tx_hash TEXT NOT NULL,
            token_address TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
            amount_usd REAL NOT NULL,
            leverage INTEGER DEFAULT 1,
            allocation_pct REAL NOT NULL,
            copy_size_usd REAL NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'executed', 'failed', 'rejected')),
            created_at TIMESTAMP NOT NULL,
            executed_at TIMESTAMP,
            rejection_reason TEXT,
            FOREIGN KEY (wallet_address) REFERENCES wallets(address) ON DELETE CASCADE
        )
    """)

    # Index for pending signals (Phase 2.2 executor will query these)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_signals_status
        ON trade_signals(status, created_at)
    """)

    # Index for wallet-specific signal history
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_signals_wallet
        ON trade_signals(wallet_address, created_at DESC)
    """)

    logger.info("✓ trade_signals table created")


def add_monitoring_columns_to_wallet_transactions(cursor: sqlite3.Cursor) -> None:
    """
    Add monitoring-specific columns to existing wallet_transactions table.

    New columns:
        leverage_multiplier: Detected leverage (1 = no leverage)
        dex_protocol: Which DEX was used ('uniswap_v2', 'uniswap_v3', etc.)
        was_copied: Boolean flag - did we copy this trade?
        copy_signal_id: FK to trade_signals.id if we copied it

    Note: SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS,
    so we check if column exists before adding.

    Args:
        cursor: SQLite database cursor
    """
    logger.info("Adding monitoring columns to wallet_transactions...")

    # Check existing columns
    cursor.execute("PRAGMA table_info(wallet_transactions)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Add leverage_multiplier if not exists
    if 'leverage_multiplier' not in existing_columns:
        cursor.execute("""
            ALTER TABLE wallet_transactions
            ADD COLUMN leverage_multiplier INTEGER DEFAULT 1
        """)
        logger.info("  ✓ Added leverage_multiplier column")
    else:
        logger.info("  - leverage_multiplier column already exists")

    # Add dex_protocol if not exists
    if 'dex_protocol' not in existing_columns:
        cursor.execute("""
            ALTER TABLE wallet_transactions
            ADD COLUMN dex_protocol TEXT
        """)
        logger.info("  ✓ Added dex_protocol column")
    else:
        logger.info("  - dex_protocol column already exists")

    # Add was_copied if not exists
    if 'was_copied' not in existing_columns:
        cursor.execute("""
            ALTER TABLE wallet_transactions
            ADD COLUMN was_copied BOOLEAN DEFAULT 0
        """)
        logger.info("  ✓ Added was_copied column")
    else:
        logger.info("  - was_copied column already exists")

    # Add copy_signal_id if not exists
    if 'copy_signal_id' not in existing_columns:
        cursor.execute("""
            ALTER TABLE wallet_transactions
            ADD COLUMN copy_signal_id TEXT
        """)
        logger.info("  ✓ Added copy_signal_id column")
    else:
        logger.info("  - copy_signal_id column already exists")

    # Create composite index for monitoring queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_monitoring
        ON wallet_transactions(wallet_id, block_number, was_copied)
    """)

    logger.info("✓ wallet_transactions enhanced for monitoring")


def initialize_monitoring_state_for_existing_wallets(cursor: sqlite3.Cursor) -> None:
    """
    Initialize monitoring_state entries for existing wallets in database.

    For each active wallet, create a monitoring_state entry with:
    - last_checked_block = 0 (will start from current block on first run)
    - last_checked_timestamp = now
    - consecutive_errors = 0

    Args:
        cursor: SQLite database cursor
    """
    logger.info("Initializing monitoring_state for existing wallets...")

    # Get all active wallets
    cursor.execute("SELECT address FROM wallets WHERE is_active = 1")
    active_wallets = cursor.fetchall()

    if not active_wallets:
        logger.warning("  No active wallets found in database")
        return

    now = datetime.now().isoformat()
    initialized_count = 0

    for (wallet_address,) in active_wallets:
        # Check if monitoring_state already exists
        cursor.execute(
            "SELECT 1 FROM monitoring_state WHERE wallet_address = ?",
            (wallet_address,)
        )

        if cursor.fetchone():
            logger.debug(f"  - {wallet_address[:10]}... already has monitoring_state")
            continue

        # Insert new monitoring_state
        cursor.execute("""
            INSERT INTO monitoring_state (
                wallet_address,
                last_checked_block,
                last_checked_timestamp
            ) VALUES (?, 0, ?)
        """, (wallet_address, now))

        initialized_count += 1
        logger.debug(f"  ✓ Initialized {wallet_address[:10]}...")

    logger.info(f"✓ Initialized monitoring for {initialized_count} wallets")


def update_schema(db_path: str = "wallet_trading.db") -> None:
    """
    Apply all Phase 2.1 schema updates to database.

    Updates are idempotent - safe to run multiple times.

    Args:
        db_path: Path to SQLite database file

    Raises:
        sqlite3.Error: If database operations fail
    """
    logger.info("="*70)
    logger.info("UPDATING DATABASE SCHEMA FOR PHASE 2.1")
    logger.info("="*70)

    # Check if database exists
    if not Path(db_path).exists():
        logger.error(f"Database not found: {db_path}")
        logger.error("Please run init_database.py first to create the database")
        sys.exit(1)

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        # Apply schema updates
        create_monitoring_state_table(cursor)
        create_trade_signals_table(cursor)
        add_monitoring_columns_to_wallet_transactions(cursor)
        initialize_monitoring_state_for_existing_wallets(cursor)

        # Commit changes
        conn.commit()

        logger.info("")
        logger.info("="*70)
        logger.info("✓ SCHEMA UPDATE COMPLETE")
        logger.info("="*70)
        logger.info(f"Database: {db_path}")
        logger.info("New tables: monitoring_state, trade_signals")
        logger.info("Enhanced: wallet_transactions (4 new columns)")
        logger.info("")
        logger.info("Database is ready for trade monitoring!")

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise

    finally:
        conn.close()


def verify_schema(db_path: str = "wallet_trading.db") -> bool:
    """
    Verify that all Phase 2.1 schema updates are applied.

    Args:
        db_path: Path to SQLite database file

    Returns:
        bool: True if schema is complete, False otherwise
    """
    logger.info("Verifying schema updates...")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check for monitoring_state table
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='monitoring_state'
        """)
        if not cursor.fetchone():
            logger.error("✗ monitoring_state table missing")
            return False
        logger.info("  ✓ monitoring_state table exists")

        # Check for trade_signals table
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='trade_signals'
        """)
        if not cursor.fetchone():
            logger.error("✗ trade_signals table missing")
            return False
        logger.info("  ✓ trade_signals table exists")

        # Check wallet_transactions columns
        cursor.execute("PRAGMA table_info(wallet_transactions)")
        columns = {row[1] for row in cursor.fetchall()}

        required_columns = {
            'leverage_multiplier',
            'dex_protocol',
            'was_copied',
            'copy_signal_id'
        }
        missing_columns = required_columns - columns

        if missing_columns:
            logger.error(f"✗ wallet_transactions missing columns: {missing_columns}")
            return False
        logger.info("  ✓ wallet_transactions has all monitoring columns")

        logger.info("✓ Schema verification passed")
        return True

    except sqlite3.Error as e:
        logger.error(f"Verification error: {e}")
        return False

    finally:
        conn.close()


def main():
    """Command-line interface for schema updates."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Update database schema for Phase 2.1 trade monitoring'
    )
    parser.add_argument(
        '--db-path',
        default='wallet_trading.db',
        help='Path to SQLite database (default: wallet_trading.db)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify schema, do not apply updates'
    )

    args = parser.parse_args()

    if args.verify_only:
        success = verify_schema(args.db_path)
        sys.exit(0 if success else 1)
    else:
        update_schema(args.db_path)
        verify_schema(args.db_path)


if __name__ == "__main__":
    main()
