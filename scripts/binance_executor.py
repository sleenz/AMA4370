"""
Binance Trade Executor

Direct integration with Binance Futures API for automated trade execution.
Supports both testnet (paper trading) and live trading modes.

Features:
- Testnet mode by default (FREE paper trading)
- Live trading with explicit confirmation
- Complete order validation
- Retry logic with exponential backoff
- Rate limiting
- Audit trail in database
- P&L tracking from Binance API

Requirements:
    pip install python-binance

Binance Testnet:
    - URL: https://testnet.binancefuture.com
    - FREE test USDT for paper trading
    - Real-time market data
    - No risk, perfect for testing
"""

import json
import time
import sqlite3
from typing import Dict, Optional, List
from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    from binance.enums import *
except ImportError:
    print("ERROR: python-binance not installed!")
    print("Install with: pip install python-binance")
    raise


@dataclass
class OrderResult:
    """Result of order execution"""
    success: bool
    order_id: Optional[str]
    exchange_order_id: Optional[str]
    status: str  # 'FILLED', 'PENDING', 'REJECTED', 'FAILED'
    filled_price: Optional[float]
    filled_quantity: Optional[float]
    error_message: Optional[str]
    exchange_response: Dict


class BinanceExecutor:
    """
    Binance Futures API Integration for Trade Execution

    Supports:
    - Testnet mode (default) - FREE paper trading
    - Live trading mode (requires confirmation)
    - Real-time P&L tracking via Binance API
    - Complete audit trail
    """

    def __init__(self, config_path: str = "config/binance_config.json"):
        """
        Initialize Binance executor

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        self.mode = self.config['mode']

        # Validate mode
        if self.mode not in ['testnet', 'live']:
            raise ValueError(f"Invalid mode: {self.mode}. Must be 'testnet' or 'live'")

        # Safety check for live mode
        if self.mode == 'live' and self.config['safety']['require_confirmation_for_live']:
            self._confirm_live_mode()

        # Initialize Binance client
        self.client = self._init_client()

        # Rate limiter
        self.rate_limiter = self._init_rate_limiter()

        # Statistics
        self.stats = {
            'orders_submitted': 0,
            'orders_filled': 0,
            'orders_rejected': 0,
            'orders_failed': 0,
            'total_volume_usd': 0.0
        }

        # Display mode prominently
        self._display_mode_warning()

        # Ensure database tables exist
        self._init_database()

    def _load_config(self, path: str) -> Dict:
        """Load configuration from JSON file"""
        config_file = Path(path)
        if not config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {path}\n"
                f"Please copy config/binance_config.example.json to {path} "
                f"and add your Binance API keys.\n\n"
                f"For testnet:\n"
                f"1. Visit https://testnet.binancefuture.com\n"
                f"2. Create account (FREE)\n"
                f"3. Generate API keys\n"
                f"4. Get free test USDT"
            )

        with open(path, 'r') as f:
            return json.load(f)

    def _init_client(self) -> Client:
        """Initialize Binance client with testnet or live API"""
        api_key = self.config['api_key']
        api_secret = self.config['api_secret']

        if self.mode == 'testnet':
            # Testnet client
            client = Client(api_key, api_secret, testnet=True)
        else:
            # Live client
            client = Client(api_key, api_secret)

        return client

    def _confirm_live_mode(self):
        """Require explicit confirmation for live trading"""
        print("="*60)
        print("⚠️  LIVE TRADING MODE DETECTED")
        print("="*60)
        print("This will execute REAL trades with REAL money!")
        print("All orders will be sent to the actual Binance exchange.")
        print("")

        confirmation = input("Type 'I CONFIRM LIVE TRADING' to proceed: ")

        if confirmation != "I CONFIRM LIVE TRADING":
            print("❌ Confirmation failed. Exiting.")
            exit(1)

        print("✅ Live trading confirmed.")
        print("="*60)

    def _display_mode_warning(self):
        """Display current mode prominently"""
        if self.mode == 'testnet':
            print("\n" + "="*60)
            print("📝 TESTNET MODE ACTIVE (Paper Trading)")
            print("="*60)
            print("• All orders are on Binance Testnet")
            print("• Using FREE test USDT")
            print("• No real money at risk")
            print("• Perfect for testing and validation")
            print("• Real-time market data")
            print("="*60 + "\n")
        else:
            print("\n" + "="*60)
            print("🔴 LIVE TRADING MODE ACTIVE")
            print("="*60)
            print("• Orders will execute on REAL Binance")
            print("• Real money will be used")
            print("• Losses are real and permanent")
            print("="*60 + "\n")

    def _init_database(self):
        """Initialize database tables for order tracking"""
        # Create database directory if it doesn't exist
        Path("database").mkdir(exist_ok=True)

        conn = sqlite3.connect('database/wallets.db')
        cursor = conn.cursor()

        # Create orders table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE,
                wallet_id INTEGER,
                exchange TEXT,
                pair TEXT,
                side TEXT,
                order_type TEXT,
                size_usd REAL,
                quantity REAL,
                leverage INTEGER,
                notional_value REAL,
                expected_price REAL,
                executed_price REAL,
                stop_loss_price REAL,
                stop_loss_usd REAL,
                status TEXT,
                api_request_payload TEXT,
                api_response TEXT,
                failure_reason TEXT,
                submitted_at TIMESTAMP,
                executed_at TIMESTAMP,
                mode TEXT
            )
        """)

        conn.commit()
        conn.close()

    def send_order(self, position: Dict) -> OrderResult:
        """
        Send order to Binance

        Args:
            position: Position dictionary with:
                - pair: Trading pair (e.g., 'BTC/USDT')
                - side: 'BUY' or 'SELL'
                - size_usd: Position size in USD
                - quantity: Asset quantity
                - leverage: Leverage multiplier
                - entry_price: Expected entry price
                - stop_loss_price: Stop loss price
                - wallet_id: Source wallet ID

        Returns:
            OrderResult with execution details
        """

        self.stats['orders_submitted'] += 1

        # Step 1: Validate order
        validation_error = self._validate_order(position)
        if validation_error:
            self.stats['orders_rejected'] += 1
            return OrderResult(
                success=False,
                order_id=None,
                exchange_order_id=None,
                status='REJECTED',
                filled_price=None,
                filled_quantity=None,
                error_message=validation_error,
                exchange_response={}
            )

        # Step 2: Generate order ID
        order_id = self._generate_order_id(position)

        # Step 3: Format symbol for Binance
        symbol = self._format_symbol(position['pair'])

        # Step 4: Log order BEFORE sending (audit trail)
        self._log_order_pre_execution(order_id, position, symbol)

        # Step 5: Rate limiting
        self.rate_limiter.wait_for_token()

        # Step 6: Set leverage first
        try:
            self.client.futures_change_leverage(
                symbol=symbol,
                leverage=int(position['leverage'])
            )
        except Exception as e:
            print(f"⚠️  Could not set leverage: {e} (continuing anyway)")

        # Step 7: Send market order with retry logic
        result = self._send_with_retry(order_id, symbol, position)

        # Step 8: If market order filled, place stop loss
        if result.success and result.exchange_order_id:
            self._place_stop_loss(symbol, position, result)

        # Step 9: Log result
        self._log_order_post_execution(order_id, result)

        # Step 10: Update statistics
        if result.success:
            self.stats['orders_filled'] += 1
            self.stats['total_volume_usd'] += position['size_usd']
        else:
            self.stats['orders_failed'] += 1

        return result

    def _validate_order(self, position: Dict) -> Optional[str]:
        """
        Validate order before submission

        Returns:
            Error message if invalid, None if valid
        """

        # Check 1: Minimum notional value
        min_notional = 10.0  # $10 minimum
        if position['size_usd'] < min_notional:
            return f"Order too small: ${position['size_usd']:.2f} < ${min_notional}"

        # Check 2: Maximum order size (safety)
        max_size = self.config['safety']['max_order_size_usd']
        if position['size_usd'] > max_size:
            return f"Order too large: ${position['size_usd']:.2f} > ${max_size}"

        # Check 3: Leverage within limits
        max_leverage = self.config['exchange_settings']['max_leverage']
        if position['leverage'] > max_leverage:
            return f"Leverage too high: {position['leverage']}x > {max_leverage}x"

        # Check 4: Stop loss sanity check
        if position['side'] == 'BUY':
            if position['stop_loss_price'] >= position['entry_price']:
                return f"Invalid stop loss for LONG: {position['stop_loss_price']} >= {position['entry_price']}"
        else:
            if position['stop_loss_price'] <= position['entry_price']:
                return f"Invalid stop loss for SHORT: {position['stop_loss_price']} <= {position['entry_price']}"

        return None  # Valid

    def _format_symbol(self, pair: str) -> str:
        """Convert pair format: BTC/USDT → BTCUSDT"""
        return pair.replace('/', '')

    def _generate_order_id(self, position: Dict) -> str:
        """Generate unique client order ID"""
        timestamp = int(time.time() * 1000)
        wallet_id = position['wallet_id']
        return f"WCT_{wallet_id}_{timestamp}"

    def _send_with_retry(self, order_id: str, symbol: str, position: Dict, max_retries: int = 3) -> OrderResult:
        """
        Send market order with exponential backoff retry

        Args:
            order_id: Client order ID
            symbol: Binance symbol (BTCUSDT)
            position: Position dict
            max_retries: Maximum retry attempts

        Returns:
            OrderResult
        """

        backoff_delays = [1, 2, 4]  # seconds

        for attempt in range(max_retries):
            try:
                # Log attempt
                print(f"\n📤 Sending order to Binance (attempt {attempt + 1}/{max_retries})")
                print(f"   Mode: {self.mode.upper()}")
                print(f"   Symbol: {symbol}")
                print(f"   Side: {position['side']}")
                print(f"   Quantity: {position['quantity']}")
                print(f"   Leverage: {position['leverage']}x")

                # Send market order
                if position['side'] == 'BUY':
                    order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_BUY,
                        type=ORDER_TYPE_MARKET,
                        quantity=position['quantity'],
                        newClientOrderId=order_id
                    )
                else:  # SELL
                    order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=ORDER_TYPE_MARKET,
                        quantity=position['quantity'],
                        newClientOrderId=order_id
                    )

                # Extract results
                exchange_order_id = order.get('orderId')
                filled_qty = float(order.get('executedQty', 0))

                # Get average fill price
                if 'avgPrice' in order and order['avgPrice']:
                    filled_price = float(order['avgPrice'])
                else:
                    filled_price = position['entry_price']  # Estimate

                print(f"✅ Order executed successfully")
                print(f"   Order ID: {order_id}")
                print(f"   Exchange Order ID: {exchange_order_id}")
                print(f"   Filled Price: ${filled_price:,.2f}")
                print(f"   Filled Quantity: {filled_qty}")

                return OrderResult(
                    success=True,
                    order_id=order_id,
                    exchange_order_id=str(exchange_order_id),
                    status='FILLED',
                    filled_price=filled_price,
                    filled_quantity=filled_qty,
                    error_message=None,
                    exchange_response=order
                )

            except BinanceAPIException as e:
                error_msg = f"Binance API Error: {e.message} (code: {e.code})"
                print(f"❌ Order rejected: {error_msg}")

                # Check if we should retry
                if 'insufficient balance' in str(e.message).lower():
                    # Don't retry on insufficient balance
                    return OrderResult(
                        success=False,
                        order_id=order_id,
                        exchange_order_id=None,
                        status='REJECTED',
                        filled_price=None,
                        filled_quantity=None,
                        error_message=error_msg,
                        exchange_response={'error': str(e)}
                    )

                # Retry on other errors
                if attempt < max_retries - 1:
                    sleep_time = backoff_delays[attempt]
                    print(f"   Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                    continue
                else:
                    return OrderResult(
                        success=False,
                        order_id=order_id,
                        exchange_order_id=None,
                        status='FAILED',
                        filled_price=None,
                        filled_quantity=None,
                        error_message=f"Max retries exceeded: {error_msg}",
                        exchange_response={'error': str(e)}
                    )

            except Exception as e:
                error_msg = f"Unexpected error: {e}"
                print(f"❌ {error_msg}")

                if attempt < max_retries - 1:
                    time.sleep(backoff_delays[attempt])
                    continue
                else:
                    return OrderResult(
                        success=False,
                        order_id=order_id,
                        exchange_order_id=None,
                        status='FAILED',
                        filled_price=None,
                        filled_quantity=None,
                        error_message=error_msg,
                        exchange_response={'error': str(e)}
                    )

        # Should not reach here
        return OrderResult(
            success=False,
            order_id=order_id,
            exchange_order_id=None,
            status='FAILED',
            filled_price=None,
            filled_quantity=None,
            error_message="Unknown failure",
            exchange_response={}
        )

    def _place_stop_loss(self, symbol: str, position: Dict, order_result: OrderResult):
        """
        Place stop loss order after market order fills

        Args:
            symbol: Binance symbol
            position: Position dict with stop_loss_price
            order_result: Result from market order
        """
        try:
            print(f"\n📍 Placing stop loss at ${position['stop_loss_price']:,.2f}")

            if position['side'] == 'BUY':
                # For LONG position, stop loss is SELL order
                stop_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    type=FUTURE_ORDER_TYPE_STOP_MARKET,
                    stopPrice=position['stop_loss_price'],
                    quantity=position['quantity'],
                    closePosition=True  # Close entire position
                )
            else:
                # For SHORT position, stop loss is BUY order
                stop_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_BUY,
                    type=FUTURE_ORDER_TYPE_STOP_MARKET,
                    stopPrice=position['stop_loss_price'],
                    quantity=position['quantity'],
                    closePosition=True
                )

            print(f"✅ Stop loss placed: Order ID {stop_order.get('orderId')}")

        except Exception as e:
            print(f"⚠️  Could not place stop loss: {e}")
            print(f"   You may need to set it manually!")

    def _log_order_pre_execution(self, order_id: str, position: Dict, symbol: str):
        """Log order before sending (for audit trail)"""
        conn = sqlite3.connect('database/wallets.db')

        payload = {
            'symbol': symbol,
            'side': position['side'],
            'quantity': position['quantity'],
            'leverage': position['leverage']
        }

        conn.execute("""
            INSERT INTO orders (
                order_id, wallet_id, exchange, pair, side, order_type,
                size_usd, quantity, leverage, notional_value,
                expected_price, stop_loss_price, stop_loss_usd,
                status, api_request_payload, submitted_at, mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """, (
            order_id,
            position['wallet_id'],
            'binance',
            position['pair'],
            position['side'],
            'MARKET',
            position['size_usd'],
            position['quantity'],
            position['leverage'],
            position['size_usd'] * position['leverage'],
            position['entry_price'],
            position['stop_loss_price'],
            position.get('stop_loss_usd', 0),
            'PENDING',
            json.dumps(payload),
            self.mode
        ))

        conn.commit()
        conn.close()

    def _log_order_post_execution(self, order_id: str, result: OrderResult):
        """Update order log after execution"""
        conn = sqlite3.connect('database/wallets.db')

        conn.execute("""
            UPDATE orders
            SET
                status = ?,
                executed_price = ?,
                executed_at = CURRENT_TIMESTAMP,
                api_response = ?,
                failure_reason = ?
            WHERE order_id = ?
        """, (
            result.status,
            result.filled_price,
            json.dumps(result.exchange_response),
            result.error_message,
            order_id
        ))

        conn.commit()
        conn.close()

    def get_open_positions(self) -> List[Dict]:
        """
        Query Binance for current open positions

        Returns:
            List of open positions
        """
        try:
            positions = self.client.futures_position_information()

            # Filter to only positions with size > 0
            open_positions = [
                p for p in positions
                if float(p.get('positionAmt', 0)) != 0
            ]

            print(f"📊 Retrieved {len(open_positions)} open positions from Binance")

            for pos in open_positions:
                symbol = pos['symbol']
                qty = float(pos['positionAmt'])
                entry_price = float(pos['entryPrice'])
                unrealized_pnl = float(pos['unRealizedProfit'])

                print(f"   {symbol}: {qty:+.4f} @ ${entry_price:,.2f} | P&L: ${unrealized_pnl:+,.2f}")

            return open_positions

        except Exception as e:
            print(f"❌ Error querying positions: {e}")
            return []

    def get_account_balance(self) -> Dict:
        """
        Get account balance and P&L summary

        Returns:
            Dictionary with balance info
        """
        try:
            account = self.client.futures_account()

            total_balance = float(account['totalWalletBalance'])
            available_balance = float(account['availableBalance'])
            total_unrealized_pnl = float(account['totalUnrealizedProfit'])
            total_margin_balance = float(account['totalMarginBalance'])

            print(f"\n💰 Account Balance:")
            print(f"   Total Balance: ${total_balance:,.2f}")
            print(f"   Available: ${available_balance:,.2f}")
            print(f"   Unrealized P&L: ${total_unrealized_pnl:+,.2f}")
            print(f"   Margin Balance: ${total_margin_balance:,.2f}")

            return {
                'totalBalance': total_balance,
                'availableBalance': available_balance,
                'unrealizedPnl': total_unrealized_pnl,
                'marginBalance': total_margin_balance
            }

        except Exception as e:
            print(f"❌ Error querying balance: {e}")
            return {}

    def get_statistics(self) -> Dict:
        """Get executor statistics"""
        return {
            **self.stats,
            'mode': self.mode,
            'success_rate': (
                self.stats['orders_filled'] / self.stats['orders_submitted']
                if self.stats['orders_submitted'] > 0 else 0
            )
        }

    def _init_rate_limiter(self):
        """Initialize rate limiter"""
        # Simple token bucket implementation
        class RateLimiter:
            def __init__(self, rate, burst):
                self.rate = rate
                self.burst = burst
                self.tokens = burst
                self.last_update = time.time()

            def wait_for_token(self):
                while True:
                    now = time.time()
                    elapsed = now - self.last_update
                    self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                    self.last_update = now

                    if self.tokens >= 1:
                        self.tokens -= 1
                        return

                    sleep_time = (1 - self.tokens) / self.rate
                    time.sleep(sleep_time)

        return RateLimiter(
            rate=self.config['rate_limiting']['requests_per_second'],
            burst=self.config['rate_limiting']['burst_size']
        )


# ═══════════════════════════════════════════════════════════════
# TESTING & VALIDATION
# ═══════════════════════════════════════════════════════════════

def test_binance_connection():
    """Test Binance API connectivity and execution"""

    print("\n🧪 Testing Binance Connection...")
    print("="*60)

    try:
        executor = BinanceExecutor()

        # Test 1: Get account balance
        print("\n📋 Test 1: Query account balance")
        balance = executor.get_account_balance()

        # Test 2: Get open positions
        print("\n📋 Test 2: Query open positions")
        positions = executor.get_open_positions()

        # Test 3: Send small test order
        print("\n📋 Test 3: Send test order (testnet)")
        print("-" * 60)

        # VERY SMALL test order
        test_position = {
            'pair': 'BTC/USDT',
            'side': 'BUY',
            'size_usd': 20.0,  # $20 test
            'quantity': 0.001,  # 0.001 BTC
            'leverage': 1,
            'entry_price': 50000,  # Estimate
            'stop_loss_price': 49000,
            'wallet_id': 999  # Test wallet
        }

        result = executor.send_order(test_position)

        print("\n" + "="*60)
        print("📊 Test Result:")
        print("="*60)
        print(f"  ✓ Success: {result.success}")
        print(f"  ✓ Order ID: {result.order_id}")
        print(f"  ✓ Status: {result.status}")
        if result.filled_price:
            print(f"  ✓ Filled Price: ${result.filled_price:,.2f}")
        if result.filled_quantity:
            print(f"  ✓ Filled Quantity: {result.filled_quantity}")
        if result.error_message:
            print(f"  ✗ Error: {result.error_message}")

        # Statistics
        print(f"\n📈 Executor Statistics:")
        print("="*60)
        stats = executor.get_statistics()
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  • {key}: {value:.4f}")
            else:
                print(f"  • {key}: {value}")

        print("\n" + "="*60)
        if result.success:
            print("✅ Connection test complete - ORDER EXECUTED!")
            print("\n💡 Check your Binance Testnet account:")
            print("   https://testnet.binancefuture.com")
        else:
            print("⚠️  Connection test complete - with errors")
            print(f"\nError details: {result.error_message}")
        print("="*60)

    except FileNotFoundError as e:
        print(f"\n❌ Configuration Error:")
        print(f"   {e}")
        print("\n💡 To fix:")
        print("   1. Visit https://testnet.binancefuture.com")
        print("   2. Create account (FREE)")
        print("   3. Generate API keys")
        print("   4. Copy config/binance_config.example.json to config/binance_config.json")
        print("   5. Add your API keys to config/binance_config.json")
    except Exception as e:
        print(f"\n❌ Test Failed:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test connection
    test_binance_connection()
