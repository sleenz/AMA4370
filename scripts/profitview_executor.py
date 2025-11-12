"""
ProfitView Trade Executor

Integrates with ProfitView API for automated trade execution.
Supports both paper trading (testnet) and live trading modes.

Features:
- Paper trading mode by default
- Live trading with explicit confirmation
- Complete order validation
- Retry logic with exponential backoff
- Rate limiting
- Audit trail in database
- P&L tracking from ProfitView dashboard
"""

import requests
import json
import time
import sqlite3
from typing import Dict, Optional
from dataclasses import dataclass
from pathlib import Path


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
    profitview_response: Dict


class ProfitViewExecutor:
    """
    ProfitView API Integration for Trade Execution

    Supports:
    - Paper trading mode (default)
    - Live trading mode (requires confirmation)
    - Real-time P&L tracking via ProfitView dashboard
    - Complete audit trail
    """

    def __init__(self, config_path: str = "config/profitview_config.json"):
        """
        Initialize ProfitView executor

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        self.mode = self.config['mode']

        # Validate mode
        if self.mode not in ['paper_trade', 'live']:
            raise ValueError(f"Invalid mode: {self.mode}. Must be 'paper_trade' or 'live'")

        # Safety check for live mode
        if self.mode == 'live' and self.config['safety']['require_confirmation_for_live']:
            self._confirm_live_mode()

        # Setup
        # Map mode to endpoint key: paper_trade -> paper_trade, live -> live_trade
        endpoint_key = 'paper_trade' if self.mode == 'paper_trade' else 'live_trade'
        self.base_url = self.config['endpoints'][endpoint_key]
        self.api_key = self.config['api_key']

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
                f"Please copy config/profitview_config.example.json to {path} "
                f"and add your API key."
            )

        with open(path, 'r') as f:
            return json.load(f)

    def _confirm_live_mode(self):
        """Require explicit confirmation for live trading"""
        print("="*60)
        print("⚠️  LIVE TRADING MODE DETECTED")
        print("="*60)
        print("This will execute REAL trades with REAL money!")
        print("All orders will be sent to the actual exchange.")
        print("")

        confirmation = input("Type 'I CONFIRM LIVE TRADING' to proceed: ")

        if confirmation != "I CONFIRM LIVE TRADING":
            print("❌ Confirmation failed. Exiting.")
            exit(1)

        print("✅ Live trading confirmed.")
        print("="*60)

    def _display_mode_warning(self):
        """Display current mode prominently"""
        if self.mode == 'paper_trade':
            print("\n" + "="*60)
            print("📝 PAPER TRADING MODE ACTIVE")
            print("="*60)
            print("• All orders are simulated")
            print("• View results in ProfitView dashboard")
            print("• No real money at risk")
            print("• Perfect for testing and validation")
            print("="*60 + "\n")
        else:
            print("\n" + "="*60)
            print("🔴 LIVE TRADING MODE ACTIVE")
            print("="*60)
            print("• Orders will execute on real exchange")
            print("• Real money will be used")
            print("• Losses are real and permanent")
            print("="*60 + "\n")

    def _init_database(self):
        """Initialize database tables for order tracking"""
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
        Send order to ProfitView

        Args:
            position: Position dictionary from SignalProcessor with:
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
                profitview_response={}
            )

        # Step 2: Format payload for ProfitView
        payload = self._format_payload(position)

        # Step 3: Generate order ID
        order_id = self._generate_order_id(position)

        # Step 4: Log order BEFORE sending (audit trail)
        self._log_order_pre_execution(order_id, position, payload)

        # Step 5: Rate limiting
        self.rate_limiter.wait_for_token()

        # Step 6: Send to ProfitView with retry logic
        result = self._send_with_retry(order_id, payload, position)

        # Step 7: Log result
        self._log_order_post_execution(order_id, result)

        # Step 8: Update statistics
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

    def _format_payload(self, position: Dict) -> Dict:
        """
        Format order for ProfitView API

        ProfitView webhook format based on user's specification
        """

        # Convert pair format: BTC/USDT → BTCUSDT
        symbol = position['pair'].replace('/', '')

        payload = {
            'venue': self.config['exchange_settings']['venue'],  # 'WooLive'
            'exchange': self.config['exchange_settings']['exchange'],  # 'binance'
            'symbol': symbol,
            'side': position['side'].lower(),  # 'buy' or 'sell'
            'type': 'market',
            'quantity': round(position['quantity'], 8),
            'leverage': int(position['leverage']),
            'stopLoss': {
                'type': 'fixed',
                'price': round(position['stop_loss_price'], 2)
            },
            'timestamp': int(time.time() * 1000)
        }

        # Optional: Add metadata for tracking
        payload['metadata'] = {
            'wallet_id': position['wallet_id'],
            'size_usd': position['size_usd'],
            'source': 'wallet_copy_bot',
            'mode': self.mode
        }

        return payload

    def _generate_order_id(self, position: Dict) -> str:
        """Generate unique client order ID"""
        timestamp = int(time.time() * 1000)
        wallet_id = position['wallet_id']
        return f"WCT_{wallet_id}_{timestamp}"

    def _send_with_retry(self, order_id: str, payload: Dict, position: Dict, max_retries: int = 3) -> OrderResult:
        """
        Send order with exponential backoff retry

        Args:
            order_id: Client order ID
            payload: Order payload
            position: Original position dict
            max_retries: Maximum retry attempts

        Returns:
            OrderResult
        """

        backoff_delays = [1, 2, 4]  # seconds

        for attempt in range(max_retries):
            try:
                # Prepare headers
                # Note: ProfitView webhook auth is in URL (webhook secret), not headers
                headers = {
                    'Content-Type': 'application/json'
                }

                # Log attempt
                print(f"\n📤 Sending order to ProfitView (attempt {attempt + 1}/{max_retries})")
                print(f"   Mode: {self.mode.upper()}")
                print(f"   Symbol: {payload['symbol']}")
                print(f"   Side: {payload['side'].upper()}")
                print(f"   Quantity: {payload['quantity']}")
                print(f"   Leverage: {payload['leverage']}x")
                print(f"   Stop Loss: ${payload['stopLoss']['price']}")

                # Send request
                response = requests.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                    timeout=10
                )

                # Parse response
                try:
                    response_data = response.json()
                except:
                    response_data = {'raw_response': response.text}

                # Check success - must check BOTH status code AND success field
                if response.status_code == 200:
                    # ProfitView wraps responses in 'data' field
                    # Response: {'status': 'success', 'data': {'success': True, 'orderId': ..., 'filledPrice': ...}}
                    bot_data = response_data.get('data', response_data)

                    # Check if the response indicates success
                    if bot_data.get('success') == False:
                        # Bot returned error in success response
                        error_msg = bot_data.get('error') or 'Unknown error from bot'
                        print(f"❌ Order failed: {error_msg}")

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
                                profitview_response=response_data
                            )

                    # Successful response - extract from nested data
                    exchange_order_id = bot_data.get('exchangeOrderId') or bot_data.get('orderId')
                    filled_price = bot_data.get('filledPrice')
                    filled_quantity = bot_data.get('filledQuantity')

                    # Verify we have real data
                    if not filled_price or not filled_quantity:
                        error_msg = "Response missing order data (price or quantity)"
                        print(f"❌ {error_msg}")
                        print(f"   Response: {response_data}")

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
                                error_message=error_msg,
                                profitview_response=response_data
                            )

                    print(f"✅ Order executed successfully")
                    print(f"   Order ID: {order_id}")
                    if exchange_order_id:
                        print(f"   Exchange Order ID: {exchange_order_id}")

                    return OrderResult(
                        success=True,
                        order_id=order_id,
                        exchange_order_id=exchange_order_id,
                        status='FILLED',
                        filled_price=filled_price,
                        filled_quantity=filled_quantity,
                        error_message=None,
                        profitview_response=response_data
                    )

                else:
                    # Order rejected by ProfitView or exchange
                    error_msg = response_data.get('error') or response_data.get('message') or f"HTTP {response.status_code}"
                    print(f"❌ Order rejected: {error_msg}")

                    # Check if we should retry
                    if 'insufficient_balance' in str(error_msg).lower():
                        # Don't retry on insufficient balance
                        return OrderResult(
                            success=False,
                            order_id=order_id,
                            exchange_order_id=None,
                            status='REJECTED',
                            filled_price=None,
                            filled_quantity=None,
                            error_message=error_msg,
                            profitview_response=response_data
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
                            profitview_response=response_data
                        )

            except requests.exceptions.Timeout:
                print(f"⏱️  Request timeout (attempt {attempt + 1}/{max_retries})")
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
                        error_message="Request timeout after retries",
                        profitview_response={}
                    )

            except Exception as e:
                print(f"❌ Unexpected error: {e}")
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
                        error_message=str(e),
                        profitview_response={}
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
            profitview_response={}
        )

    def _log_order_pre_execution(self, order_id: str, position: Dict, payload: Dict):
        """Log order before sending (for audit trail)"""
        conn = sqlite3.connect('database/wallets.db')

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
            self.config['exchange_settings']['exchange'],
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
            json.dumps(result.profitview_response),
            result.error_message,
            order_id
        ))

        conn.commit()
        conn.close()

    def get_open_positions(self) -> list:
        """
        Query ProfitView for current open positions

        Returns:
            List of open positions from ProfitView dashboard
        """

        try:
            # ProfitView webhook auth is in URL, send venue as query param
            response = requests.get(
                f"{self.config['endpoints']['positions']}?venue={self.config['exchange_settings']['venue']}",
                timeout=10
            )

            if response.status_code == 200:
                positions = response.json().get('positions', [])
                print(f"📊 Retrieved {len(positions)} open positions from ProfitView")
                return positions
            else:
                print(f"❌ Failed to get positions: {response.text}")
                return []

        except Exception as e:
            print(f"❌ Error querying positions: {e}")
            return []

    def get_pnl_summary(self) -> Dict:
        """
        Get P&L summary from ProfitView

        Returns:
            Dictionary with P&L metrics
        """

        try:
            # ProfitView webhook auth is in URL, send venue as query param
            response = requests.get(
                f"{self.config['endpoints']['pnl']}?venue={self.config['exchange_settings']['venue']}",
                timeout=10
            )

            if response.status_code == 200:
                pnl_data = response.json()
                print(f"\n📈 P&L Summary:")
                print(f"   Total P&L: ${pnl_data.get('totalPnl', 0):.2f}")
                print(f"   Realized P&L: ${pnl_data.get('realizedPnl', 0):.2f}")
                print(f"   Unrealized P&L: ${pnl_data.get('unrealizedPnl', 0):.2f}")
                return pnl_data
            else:
                print(f"❌ Failed to get P&L: {response.text}")
                return {}

        except Exception as e:
            print(f"❌ Error querying P&L: {e}")
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

def test_profitview_connection():
    """Test ProfitView API connectivity"""

    print("\n🧪 Testing ProfitView Connection...")
    print("="*60)

    try:
        executor = ProfitViewExecutor()

        # Test 1: Get open positions
        print("\n📋 Test 1: Query open positions")
        positions = executor.get_open_positions()

        # Test 2: Get P&L
        print("\n📋 Test 2: Query P&L")
        pnl = executor.get_pnl_summary()

        # Test 3: Send test order (very small size)
        print("\n📋 Test 3: Send test order (paper trading)")
        print("-" * 60)
        test_position = {
            'pair': 'BTC/USDT',
            'side': 'BUY',
            'size_usd': 100.0,  # $100 test
            'quantity': 0.002,
            'leverage': 1,
            'entry_price': 50000,
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
        print("✅ Connection test complete!")
        print("="*60)

    except FileNotFoundError as e:
        print(f"\n❌ Configuration Error:")
        print(f"   {e}")
    except Exception as e:
        print(f"\n❌ Test Failed:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test connection
    test_profitview_connection()
