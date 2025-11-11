"""
ProfitView Bot for Wallet Copy Trading

This bot should be deployed on ProfitView platform (profitview.net/trading)
It receives webhook calls from your local wallet copy bot and executes trades on WOO X (WooLive).

DEPLOYMENT INSTRUCTIONS:
1. Log into https://profitview.net/trading
2. Create new bot
3. Paste this code
4. Configure WooLive connection (your paper trade API: d8e4c5eb-d3b0-4f4f-a201-7c51e0444434)
5. Save and start the bot
6. Your webhook URL will be: https://profitview.net/trading/bot/YOUR_SECRET/execute_order

WEBHOOK SECRET: 517b3bcac35bc86e1bea1ec31101b9b583b34387
"""

import time


class Config:
    """Bot configuration"""
    # Exchange settings
    VENUE = 'WooLive'  # WOO X paper trading
    DEFAULT_LEVERAGE = 10
    MAX_LEVERAGE = 25

    # Safety limits
    MAX_ORDER_SIZE_USD = 10000
    MIN_ORDER_SIZE_USD = 10


class WalletCopyBot:
    """
    Wallet Copy Trading Execution Bot

    Receives orders from external wallet monitor system
    and executes them on WOO X exchange via ProfitView.
    """

    def __init__(self):
        self.venue = Config.VENUE
        self.orders_executed = 0
        self.total_volume = 0.0

        print(f"🤖 Wallet Copy Bot initialized for {self.venue}")
        print(f"📝 Paper Trading Mode Active")

    def post_execute_order(self, data):
        """
        Execute trade order from wallet copy system

        Expected payload:
        {
            "venue": "WooLive",
            "exchange": "woox",
            "symbol": "BTCUSDT",
            "side": "buy" or "sell",
            "type": "market",
            "quantity": 0.001,
            "leverage": 5,
            "stopLoss": {
                "type": "fixed",
                "price": 49000
            },
            "timestamp": 1699876543210,
            "metadata": {
                "wallet_id": 1,
                "size_usd": 100,
                "source": "wallet_copy_bot"
            }
        }

        Returns:
        {
            "success": true,
            "orderId": "...",
            "exchangeOrderId": "...",
            "status": "FILLED",
            "filledPrice": 50000,
            "filledQuantity": 0.001
        }
        """

        try:
            # Extract order details
            symbol = data.get('symbol', 'BTCUSDT')
            side = data.get('side', 'buy').capitalize()  # Buy or Sell
            quantity = float(data.get('quantity', 0))
            leverage = int(data.get('leverage', Config.DEFAULT_LEVERAGE))
            order_type = data.get('type', 'market').upper()
            stop_loss = data.get('stopLoss', {})

            # Validate order
            size_usd = data.get('metadata', {}).get('size_usd', 0)

            if size_usd < Config.MIN_ORDER_SIZE_USD:
                return {
                    'success': False,
                    'error': f'Order too small: ${size_usd} < ${Config.MIN_ORDER_SIZE_USD}',
                    'code': 'ORDER_TOO_SMALL'
                }

            if size_usd > Config.MAX_ORDER_SIZE_USD:
                return {
                    'success': False,
                    'error': f'Order too large: ${size_usd} > ${Config.MAX_ORDER_SIZE_USD}',
                    'code': 'ORDER_TOO_LARGE'
                }

            if leverage > Config.MAX_LEVERAGE:
                return {
                    'success': False,
                    'error': f'Leverage too high: {leverage}x > {Config.MAX_LEVERAGE}x',
                    'code': 'LEVERAGE_TOO_HIGH'
                }

            # Set leverage
            print(f"⚙️  Setting leverage to {leverage}x for {symbol}")
            # Note: ProfitView handles leverage automatically per exchange

            # Execute market order
            print(f"📤 Executing {side} order: {quantity} {symbol}")
            print(f"   Size: ${size_usd:.2f}")
            print(f"   Leverage: {leverage}x")

            if side == 'Buy':
                order = self.create_market_order(
                    venue=self.venue,
                    sym=symbol,
                    side='Buy',
                    size=quantity
                )
            else:
                order = self.create_market_order(
                    venue=self.venue,
                    sym=symbol,
                    side='Sell',
                    size=quantity
                )

            # Check if order filled
            if order.get('error'):
                print(f"❌ Order failed: {order.get('error')}")
                return {
                    'success': False,
                    'error': order.get('error'),
                    'code': 'EXCHANGE_ERROR',
                    'exchangeResponse': order
                }

            # Extract order ID
            order_id = order.get('order_id') or order.get('orderId')
            exchange_order_id = order.get('exchange_order_id') or order.get('exchangeOrderId')

            # Get fill info
            filled_price = order.get('order_price') or order.get('filledPrice')
            filled_qty = order.get('order_size') or order.get('filledQuantity') or quantity

            print(f"✅ Order filled: {exchange_order_id}")
            print(f"   Price: ${filled_price}")
            print(f"   Quantity: {filled_qty}")

            # Place stop loss if provided
            if stop_loss and stop_loss.get('price'):
                stop_price = stop_loss['price']
                print(f"📍 Placing stop loss at ${stop_price}")

                # Determine stop side (opposite of entry)
                stop_side = 'Sell' if side == 'Buy' else 'Buy'

                try:
                    stop_order = self.create_limit_order(
                        venue=self.venue,
                        sym=symbol,
                        side=stop_side,
                        size=quantity,
                        price=stop_price
                    )

                    if not stop_order.get('error'):
                        print(f"✅ Stop loss placed: {stop_order.get('order_id')}")
                    else:
                        print(f"⚠️  Could not place stop loss: {stop_order.get('error')}")

                except Exception as e:
                    print(f"⚠️  Stop loss error: {e}")

            # Update stats
            self.orders_executed += 1
            self.total_volume += size_usd

            # Return success response
            return {
                'success': True,
                'orderId': str(order_id),
                'exchangeOrderId': str(exchange_order_id),
                'status': 'FILLED',
                'filledPrice': filled_price,
                'filledQuantity': filled_qty,
                'timestamp': int(time.time() * 1000),
                'stats': {
                    'ordersExecuted': self.orders_executed,
                    'totalVolume': self.total_volume
                }
            }

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return {
                'success': False,
                'error': str(e),
                'code': 'INTERNAL_ERROR'
            }

    def get_positions(self, data):
        """
        Get open positions

        Query params: ?venue=WooLive

        Returns:
        {
            "success": true,
            "positions": [...]
        }
        """
        try:
            venue = data.get('venue', self.venue)

            # Get positions from exchange
            positions = self.fetch_positions(venue=venue)

            print(f"📊 Retrieved {len(positions)} open positions")

            return {
                'success': True,
                'positions': positions,
                'venue': venue
            }

        except Exception as e:
            print(f"❌ Error getting positions: {e}")
            return {
                'success': False,
                'error': str(e),
                'positions': []
            }

    def get_pnl(self, data):
        """
        Get P&L summary

        Query params: ?venue=WooLive

        Returns:
        {
            "success": true,
            "totalPnl": 1234.56,
            "realizedPnl": 800.00,
            "unrealizedPnl": 434.56
        }
        """
        try:
            venue = data.get('venue', self.venue)

            # Get account balance
            balance = self.fetch_balances(venue=venue)

            # Calculate P&L (this is exchange-specific)
            total_pnl = balance.get('totalPnl', 0)
            realized_pnl = balance.get('realizedPnl', 0)
            unrealized_pnl = balance.get('unrealizedPnl', 0)

            print(f"💰 P&L Summary:")
            print(f"   Total: ${total_pnl:.2f}")
            print(f"   Realized: ${realized_pnl:.2f}")
            print(f"   Unrealized: ${unrealized_pnl:.2f}")

            return {
                'success': True,
                'totalPnl': total_pnl,
                'realizedPnl': realized_pnl,
                'unrealizedPnl': unrealized_pnl,
                'venue': venue,
                'stats': {
                    'ordersExecuted': self.orders_executed,
                    'totalVolume': self.total_volume
                }
            }

        except Exception as e:
            print(f"❌ Error getting P&L: {e}")
            return {
                'success': False,
                'error': str(e),
                'totalPnl': 0,
                'realizedPnl': 0,
                'unrealizedPnl': 0
            }

    def get_status(self, data):
        """
        Get bot status

        Returns:
        {
            "success": true,
            "status": "active",
            "ordersExecuted": 42,
            "totalVolume": 12345.67
        }
        """
        return {
            'success': True,
            'status': 'active',
            'venue': self.venue,
            'ordersExecuted': self.orders_executed,
            'totalVolume': self.total_volume,
            'mode': 'paper_trade'
        }


# Initialize bot
bot = WalletCopyBot()

"""
DEPLOYMENT CHECKLIST:
---------------------

1. Copy this entire code

2. Go to https://profitview.net/trading

3. Create New Bot:
   - Click "New Bot" button
   - Name it "Wallet Copy Executor"
   - Paste this code

4. Configure Exchange Connection:
   - Add WooLive venue
   - Use your WooLive paper trade API: d8e4c5eb-d3b0-4f4f-a201-7c51e0444434
   - Enable paper trading mode

5. Save and Start Bot:
   - Click "Save"
   - Click "Start" to activate bot
   - Bot should show "Running" status

6. Get Your Webhook URLs:
   - Click the ⚡ (bolt) icon in the editor
   - Copy your webhook URLs:
     * Execute Order: https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/execute_order
     * Get Positions: https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_positions
     * Get P&L: https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_pnl
     * Get Status: https://profitview.net/trading/bot/517b3bcac35bc86e1bea1ec31101b9b583b34387/get_status

7. Test the Bot:
   - Run: python scripts/profitview_executor.py
   - Should connect successfully and execute test order

8. Monitor:
   - View bot logs in ProfitView dashboard
   - Check orders in WooLive
   - Track P&L

SUPPORT:
--------
If you encounter issues:
1. Check bot is "Running" in ProfitView
2. Verify WooLive connection is active
3. Check bot logs for errors
4. Ensure webhook secret matches: 517b3bcac35bc86e1bea1ec31101b9b583b34387
"""
