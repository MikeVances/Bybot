import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from bot.exchange.api_adapter import create_trading_bot_adapter


class TestOrderPlacement(unittest.TestCase):
    def setUp(self):
        trading_bot_patcher = patch('bot.exchange.api_adapter.TradingBotV5')
        self.addCleanup(trading_bot_patcher.stop)
        self.mock_trading_bot_cls = trading_bot_patcher.start()

        self.fake_bot = MagicMock()
        self.fake_bot.get_ohlcv.return_value = pd.DataFrame({'close': [45000.0]})
        self.fake_bot.create_order.return_value = {'result': {'orderId': 'test-order'}}
        self.mock_trading_bot_cls.return_value = self.fake_bot

        self.adapter = create_trading_bot_adapter(symbol="BTCUSDT", testnet=True)

    def test_create_order(self):
        ohlcv = self.adapter.get_ohlcv(interval="1", limit=1)
        self.fake_bot.get_ohlcv.assert_called_once_with("BTCUSDT", "1", 1)
        current_price = float(ohlcv["close"].iloc[-1])

        qty = 0.01
        side = "Buy"
        stop_loss = current_price - 100
        take_profit = current_price + 300

        order = self.adapter.create_order(
            symbol="BTCUSDT",
            side=side,
            order_type="Market",
            qty=qty,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        self.fake_bot.create_order.assert_called_once_with(
            symbol="BTCUSDT",
            side=side,
            order_type="Market",
            qty=qty,
            price=None,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reduce_only=False,
            position_idx=None
        )
        self.assertEqual(order, {'result': {'orderId': 'test-order'}})


if __name__ == "__main__":
    unittest.main()
