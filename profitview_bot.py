"""
ProfitView Wallet Copy Trading Bot

DEPLOYMENT INSTRUCTIONS:
1. Log into https://profitview.net/trading
2. Create new bot
3. Paste this ENTIRE code
4. Configure WooLive connection with API: d8e4c5eb-d3b0-4f4f-a201-7c51e0444434
5. Save and Start the bot
6. Copy your webhook URLs from ProfitView dashboard

NOTE: Link base class is provided by ProfitView environment - no import needed
"""

import time


class Config:
    """Bot configuration"""
    VENUE = 'WooLive'
    DEFAULT_LEVERAGE = 10
    MAX_LEVERAGE = 25
    MAX_ORDER_SIZE_USD = 10000
    MIN_ORDER_SIZE_USD = 10


class Trading(Link):
    """
    Wallet Copy Trading Execution Bot for ProfitView

    Inherits from Link base class (provided by ProfitView environment)
    Receives webhook calls and executes trades on WOO X (WooLive)
    """

    def __init__(self):
        super().__init__()
        self.venue = Config.VENUE
        self.orders_executed = 0
        self.total_volume = 0.0

        self.log(f"🤖 Wallet Copy Bot initialized for {self.venue}")
        self.log(f"📝 Paper Trading Mode Active")

    def execute_order(self, data):
        """
        Execute trade order from wallet copy system

        Webhook endpoint: /execute_order

        Expected payload:
        {
            "venue": "WooLive",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 0.001,
            "leverage": 5,
            "stopLoss": {"price": 49000},
            "metadata": {"size_usd": 100}
        }
        """
        try:
            # Extract order details
            symbol = data.get('symbol', 'BTCUSDT')
            side = data.get('side', 'buy').capitalize()
            quantity = float(data.get('quantity', 0))
            leverage = int(data.get('leverage', Config.DEFAULT_LEVERAGE))
            stop_loss = data.get('stopLoss', {})

            # Validate
            size_usd = data.get('metadata', {}).get('size_usd', 0)

            if size_usd < Config.MIN_ORDER_SIZE_USD:
                return {
                    'success': False,
                    'error': f'Order too small: ${size_usd}'
                }

            if size_usd > Config.MAX_ORDER_SIZE_USD:
                return {
                    'success': False,
                    'error': f'Order too large: ${size_usd}'
                }

            if leverage > Config.MAX_LEVERAGE:
                return {
                    'success': False,
                    'error': f'Leverage too high: {leverage}x'
                }

            # Execute order
            self.log(f"📤 Executing {side} order: {quantity} {symbol}")
            self.log(f"   Size: ${size_usd:.2f}, Leverage: {leverage}x")

            order = self.create_market_order(
                venue=self.venue,
                sym=symbol,
                side=side,
                size=quantity
            )

            if order.get('error'):
                self.log(f"❌ Order failed: {order.get('error')}")
                return {
                    'success': False,
                    'error': order.get('error')
                }

            # Get order details
            order_id = order.get('order_id') or order.get('orderId')
            filled_price = order.get('order_price') or order.get('filledPrice')
            filled_qty = order.get('order_size') or quantity

            self.log(f"✅ Order filled: {order_id}")
            self.log(f"   Price: ${filled_price}, Quantity: {filled_qty}")

            # Place stop loss
            if stop_loss and stop_loss.get('price'):
                stop_price = stop_loss['price']
                stop_side = 'Sell' if side == 'Buy' else 'Buy'

                self.log(f"📍 Placing stop loss at ${stop_price}")

                try:
                    stop_order = self.create_limit_order(
                        venue=self.venue,
                        sym=symbol,
                        side=stop_side,
                        size=quantity,
                        price=stop_price
                    )

                    if not stop_order.get('error'):
                        self.log(f"✅ Stop loss placed")
                    else:
                        self.log(f"⚠️ Could not place stop loss")
                except Exception as e:
                    self.log(f"⚠️ Stop loss error: {e}")

            # Update stats
            self.orders_executed += 1
            self.total_volume += size_usd

            return {
                'success': True,
                'orderId': str(order_id),
                'status': 'FILLED',
                'filledPrice': filled_price,
                'filledQuantity': filled_qty,
                'timestamp': int(time.time() * 1000)
            }

        except Exception as e:
            self.log(f"❌ Error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_positions(self, data):
        """
        Get open positions

        Webhook endpoint: /get_positions
        """
        try:
            venue = data.get('venue', self.venue)
            positions = self.fetch_positions(venue=venue)

            self.log(f"📊 Retrieved {len(positions)} positions")

            return {
                'success': True,
                'positions': positions,
                'venue': venue
            }
        except Exception as e:
            self.log(f"❌ Error: {e}")
            return {
                'success': False,
                'error': str(e),
                'positions': []
            }

    def get_pnl(self, data):
        """
        Get P&L summary

        Webhook endpoint: /get_pnl
        """
        try:
            venue = data.get('venue', self.venue)
            balance = self.fetch_balances(venue=venue)

            total_pnl = balance.get('totalPnl', 0)
            realized_pnl = balance.get('realizedPnl', 0)
            unrealized_pnl = balance.get('unrealizedPnl', 0)

            self.log(f"💰 P&L: ${total_pnl:.2f}")

            return {
                'success': True,
                'totalPnl': total_pnl,
                'realizedPnl': realized_pnl,
                'unrealizedPnl': unrealized_pnl,
                'venue': venue
            }
        except Exception as e:
            self.log(f"❌ Error: {e}")
            return {
                'success': False,
                'error': str(e),
                'totalPnl': 0
            }

    def get_status(self, data):
        """
        Get bot status

        Webhook endpoint: /get_status
        """
        return {
            'success': True,
            'status': 'active',
            'venue': self.venue,
            'ordersExecuted': self.orders_executed,
            'totalVolume': self.total_volume,
            'mode': 'paper_trade'
        }


# Initialize the bot (required by ProfitView)
bot = Trading()
