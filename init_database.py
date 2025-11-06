"""
Database Initialization Module for Wallet Copy Trading System

This module provides comprehensive SQLite database schema creation and initialization
for tracking profitable wallets, their transactions, our trading orders, and open positions.

Schema Overview:
    - wallets: Track wallet addresses with performance metrics and rankings
    - wallet_transactions: Historical trades from tracked wallets for analysis
    - our_orders: Trades we execute (copying wallets or manual orders)
    - open_positions: Current holdings with real-time P&L tracking

Design Principles:
    - Efficient querying through strategic indexing
    - Data integrity via foreign key constraints
    - Performance optimization through denormalization where appropriate
    - Flexibility via JSON metadata fields

Usage:
    python init_database.py [--db-path PATH]

Example:
    >>> from init_database import init_database
    >>> conn = init_database('trading.db')
    >>> # Database is now ready for use
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_wallets_table(cursor: sqlite3.Cursor) -> None:
    """
    Create the wallets table for tracking wallet addresses and performance metrics.

    This table stores wallet addresses we're tracking along with their calculated
    performance metrics used for ranking and allocation decisions. Metrics are
    denormalized for query performance and recalculated periodically.

    Columns:
        id: Internal unique identifier (auto-increment)
        address: Blockchain wallet address (unique)
        rank_score: Overall ranking score 0-100 (higher is better)
        total_trades: Total number of trades executed by wallet
        winning_trades: Number of profitable trades
        total_pnl: Cumulative profit/loss in USD
        win_rate: Percentage of winning trades (0-100)
        sharpe_ratio: Risk-adjusted return metric (can be NULL if insufficient data)
        avg_return: Average return per trade as percentage
        max_drawdown: Maximum drawdown percentage (absolute value)
        allocation_pct: Percentage of our capital allocated to copying (0-100)
        is_active: Boolean flag for active tracking status
        first_seen: Timestamp when wallet was first discovered
        last_updated: Timestamp of last metrics recalculation
        metadata: JSON field for flexible additional data (tags, notes, etc.)

    Indexes:
        - idx_wallets_rank_score: Composite (rank_score DESC, is_active) for rankings
        - idx_wallets_address: Fast lookup by address
        - idx_wallets_active: Composite (is_active, rank_score DESC) for active wallet queries

    Args:
        cursor: SQLite database cursor

    Returns:
        None
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT UNIQUE NOT NULL,
            rank_score REAL DEFAULT 0.0,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            total_pnl REAL DEFAULT 0.0,
            win_rate REAL DEFAULT 0.0,
            sharpe_ratio REAL,
            avg_return REAL DEFAULT 0.0,
            max_drawdown REAL DEFAULT 0.0,
            allocation_pct REAL DEFAULT 0.0,
            is_active BOOLEAN DEFAULT 1,
            first_seen TIMESTAMP NOT NULL,
            last_updated TIMESTAMP NOT NULL,
            metadata TEXT
        )
    """)

    # Create indexes for efficient querying
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallets_rank_score
        ON wallets(rank_score DESC, is_active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallets_address
        ON wallets(address)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallets_active
        ON wallets(is_active, rank_score DESC)
    """)

    logger.info("Created wallets table with 3 indexes")


def create_wallet_transactions_table(cursor: sqlite3.Cursor) -> None:
    """
    Create the wallet_transactions table for historical trade data.

    This table stores all historical transactions from tracked wallets, enabling
    performance analysis, pattern recognition, and ranking calculations. Transaction
    data is immutable once recorded (append-only pattern).

    Columns:
        id: Internal unique identifier (auto-increment)
        wallet_id: Foreign key to wallets table
        tx_hash: Blockchain transaction hash (unique identifier)
        block_number: Block number for chronological ordering
        timestamp: Transaction execution timestamp
        action: Trade direction ('BUY' or 'SELL')
        token_address: Token contract address
        token_symbol: Token symbol (denormalized for performance)
        amount: Token amount traded
        price_usd: Price per token in USD at execution
        value_usd: Total trade value in USD (amount * price_usd)
        gas_fee: Gas fee in USD
        dex: DEX name (e.g., 'Uniswap', 'Raydium') - nullable

    Indexes:
        - idx_wallet_txns_wallet_time: Composite (wallet_id, timestamp DESC) for history queries
        - idx_wallet_txns_token: Composite (token_address, timestamp DESC) for token analysis
        - idx_wallet_txns_hash: Fast deduplication on tx_hash
        - idx_wallet_txns_block: Efficient blockchain scanning by block_number

    Foreign Keys:
        - wallet_id REFERENCES wallets(id) ON DELETE CASCADE
          (Cascade delete: if wallet removed, its transactions are also removed)

    Args:
        cursor: SQLite database cursor

    Returns:
        None
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            tx_hash TEXT UNIQUE NOT NULL,
            block_number INTEGER NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
            token_address TEXT NOT NULL,
            token_symbol TEXT NOT NULL,
            amount REAL NOT NULL,
            price_usd REAL NOT NULL,
            value_usd REAL NOT NULL,
            gas_fee REAL DEFAULT 0.0,
            dex TEXT,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        )
    """)

    # Create indexes for efficient querying
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallet_txns_wallet_time
        ON wallet_transactions(wallet_id, timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallet_txns_token
        ON wallet_transactions(token_address, timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallet_txns_hash
        ON wallet_transactions(tx_hash)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallet_txns_block
        ON wallet_transactions(block_number DESC)
    """)

    logger.info("Created wallet_transactions table with 4 indexes and foreign key constraints")


def create_our_orders_table(cursor: sqlite3.Cursor) -> None:
    """
    Create the our_orders table for tracking our executed trades.

    This table records all trades we execute, whether copying tracked wallets or
    manual orders. Includes execution details, status tracking, and links to
    source transactions for audit trail.

    Columns:
        id: Internal unique identifier (auto-increment)
        wallet_id: Foreign key to wallets table (NULL for manual trades)
        source_tx_hash: Original transaction we're copying (NULL for manual)
        our_tx_hash: Our transaction hash (unique identifier)
        timestamp: Execution timestamp
        action: Trade direction ('BUY' or 'SELL')
        token_address: Token contract address
        token_symbol: Token symbol
        amount: Token amount traded
        price_usd: Execution price per token in USD
        value_usd: Total trade value in USD
        gas_fee: Gas fee in USD
        slippage_pct: Actual slippage experienced (NULL if not applicable)
        status: Order status ('PENDING', 'CONFIRMED', 'FAILED')
        error_message: Error details if status is FAILED (NULL otherwise)

    Indexes:
        - idx_our_orders_wallet: Composite (wallet_id, timestamp DESC) for copy analysis
        - idx_our_orders_token: Composite (token_address, timestamp DESC) for P&L calc
        - idx_our_orders_status: Composite (status, timestamp DESC) for monitoring
        - idx_our_orders_hash: Fast lookup by transaction hash

    Foreign Keys:
        - wallet_id REFERENCES wallets(id) ON DELETE SET NULL
          (Set null: preserve order history even if wallet deleted)

    Args:
        cursor: SQLite database cursor

    Returns:
        None
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS our_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER,
            source_tx_hash TEXT,
            our_tx_hash TEXT UNIQUE,
            timestamp TIMESTAMP NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
            token_address TEXT NOT NULL,
            token_symbol TEXT NOT NULL,
            amount REAL NOT NULL,
            price_usd REAL NOT NULL,
            value_usd REAL NOT NULL,
            gas_fee REAL DEFAULT 0.0,
            slippage_pct REAL,
            status TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'CONFIRMED', 'FAILED')),
            error_message TEXT,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE SET NULL
        )
    """)

    # Create indexes for efficient querying
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_our_orders_wallet
        ON our_orders(wallet_id, timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_our_orders_token
        ON our_orders(token_address, timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_our_orders_status
        ON our_orders(status, timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_our_orders_hash
        ON our_orders(our_tx_hash)
    """)

    logger.info("Created our_orders table with 4 indexes and foreign key constraints")


def create_open_positions_table(cursor: sqlite3.Cursor) -> None:
    """
    Create the open_positions table for tracking current holdings and P&L.

    This table maintains one record per token we currently hold, with real-time
    price updates and P&L calculations. Uses average cost basis accounting for
    simplicity and standard industry practice.

    Columns:
        id: Internal unique identifier (auto-increment)
        token_address: Token contract address (unique - one position per token)
        token_symbol: Token symbol
        total_amount: Total tokens currently held
        avg_entry_price: Average entry price in USD (cost basis)
        total_invested_usd: Total USD invested (avg_entry_price * total_amount)
        current_price_usd: Current market price in USD
        current_value_usd: Current position value (total_amount * current_price_usd)
        unrealized_pnl: Unrealized profit/loss in USD (current_value - total_invested)
        unrealized_pnl_pct: Unrealized P&L as percentage
        realized_pnl: Realized profit/loss from partial sells (cost basis adjusted)
        first_buy_time: Timestamp of first purchase
        last_updated: Timestamp of last price update (for staleness detection)

    Indexes:
        - idx_positions_token: Fast lookup by token_address (UNIQUE constraint provides this)
        - idx_positions_pnl_pct: Sort by performance (unrealized_pnl_pct DESC)
        - idx_positions_value: Sort by position size (current_value_usd DESC)

    P&L Calculation Notes:
        - Average cost basis: (sum of all buys) / (total amount bought)
        - Unrealized P&L: (current_price - avg_entry_price) * total_amount
        - Realized P&L: Updated on partial sells, reduces cost basis
        - Total P&L: realized_pnl + unrealized_pnl

    Args:
        cursor: SQLite database cursor

    Returns:
        None
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS open_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT UNIQUE NOT NULL,
            token_symbol TEXT NOT NULL,
            total_amount REAL NOT NULL,
            avg_entry_price REAL NOT NULL,
            total_invested_usd REAL NOT NULL,
            current_price_usd REAL NOT NULL,
            current_value_usd REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            unrealized_pnl_pct REAL NOT NULL,
            realized_pnl REAL DEFAULT 0.0,
            first_buy_time TIMESTAMP NOT NULL,
            last_updated TIMESTAMP NOT NULL
        )
    """)

    # Create indexes for efficient querying
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_token
        ON open_positions(token_address)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_pnl_pct
        ON open_positions(unrealized_pnl_pct DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_value
        ON open_positions(current_value_usd DESC)
    """)

    logger.info("Created open_positions table with 3 indexes")


def enable_foreign_keys(conn: sqlite3.Connection) -> None:
    """
    Enable foreign key constraint enforcement in SQLite.

    SQLite has foreign key support disabled by default for backwards compatibility.
    This function enables it for the current connection, ensuring referential
    integrity is enforced.

    Must be called for each new connection to the database.

    Args:
        conn: SQLite database connection

    Returns:
        None
    """
    conn.execute("PRAGMA foreign_keys = ON")
    logger.info("Enabled foreign key constraints")


def init_database(db_path: str = "wallet_trading.db") -> sqlite3.Connection:
    """
    Initialize the complete database schema for the wallet copy trading system.

    This function creates all tables, indexes, and constraints required for the
    trading system. It's idempotent - safe to call multiple times as it uses
    CREATE TABLE IF NOT EXISTS.

    Database Schema:
        1. wallets: Track wallet addresses and performance metrics
        2. wallet_transactions: Historical trades from tracked wallets
        3. our_orders: Our executed trades (copies or manual)
        4. open_positions: Current holdings with P&L tracking

    Features:
        - Foreign key constraints for data integrity
        - Strategic indexes for query performance
        - CHECK constraints for data validation
        - JSON support for flexible metadata

    Args:
        db_path: Path to SQLite database file (default: 'wallet_trading.db')
                 Creates new database if file doesn't exist

    Returns:
        sqlite3.Connection: Database connection with foreign keys enabled

    Raises:
        sqlite3.Error: If database creation or table creation fails

    Example:
        >>> conn = init_database('trading.db')
        >>> cursor = conn.cursor()
        >>> # Use database...
        >>> conn.close()
    """
    try:
        # Create database connection
        db_file = Path(db_path)
        is_new_db = not db_file.exists()

        logger.info(f"{'Creating new' if is_new_db else 'Opening existing'} database: {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Enable foreign key constraints
        enable_foreign_keys(conn)

        # Create all tables
        logger.info("Creating database schema...")
        create_wallets_table(cursor)
        create_wallet_transactions_table(cursor)
        create_our_orders_table(cursor)
        create_open_positions_table(cursor)

        # Commit changes
        conn.commit()

        logger.info(f"Database initialization complete: {db_path}")
        logger.info("Schema created: 4 tables, 14 indexes, 2 foreign key constraints")

        return conn

    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def verify_schema(conn: sqlite3.Connection) -> dict:
    """
    Verify database schema and return statistics.

    Queries SQLite system tables to verify all expected tables and indexes exist.
    Useful for debugging and validation after initialization.

    Args:
        conn: SQLite database connection

    Returns:
        dict: Schema statistics including table names, index counts, row counts

    Example:
        >>> conn = init_database('trading.db')
        >>> stats = verify_schema(conn)
        >>> print(f"Tables created: {len(stats['tables'])}")
    """
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]

    # Get all indexes
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    indexes = [row[0] for row in cursor.fetchall()]

    # Get row counts for each table
    row_counts = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        row_counts[table] = cursor.fetchone()[0]

    stats = {
        'tables': tables,
        'table_count': len(tables),
        'indexes': indexes,
        'index_count': len(indexes),
        'row_counts': row_counts
    }

    return stats


def main():
    """
    Command-line interface for database initialization.

    Usage:
        python init_database.py [--db-path PATH]

    Arguments:
        --db-path: Optional path to database file (default: wallet_trading.db)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='Initialize SQLite database for wallet copy trading system'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='wallet_trading.db',
        help='Path to SQLite database file (default: wallet_trading.db)'
    )

    args = parser.parse_args()

    try:
        # Initialize database
        conn = init_database(args.db_path)

        # Verify schema
        stats = verify_schema(conn)

        print("\n" + "="*60)
        print("DATABASE INITIALIZATION SUCCESSFUL")
        print("="*60)
        print(f"\nDatabase file: {args.db_path}")
        print(f"Tables created: {stats['table_count']}")
        print(f"  - {', '.join(stats['tables'])}")
        print(f"\nIndexes created: {stats['index_count']}")
        print(f"\nRow counts:")
        for table, count in stats['row_counts'].items():
            print(f"  - {table}: {count}")
        print("\n" + "="*60)
        print("Database is ready for use!")
        print("="*60 + "\n")

        conn.close()

    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
