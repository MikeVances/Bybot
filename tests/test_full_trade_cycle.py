import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from bot.exchange.api_adapter import create_trading_bot_adapter


class TestFullTradeCycle(unittest.TestCase):
    """Проверка того, что адаптер корректно проксирует ключевые вызовы."""

    def setUp(self):
        trading_bot_patcher = patch('bot.exchange.api_adapter.TradingBotV5')
        self.addCleanup(trading_bot_patcher.stop)
        self.mock_trading_bot_cls = trading_bot_patcher.start()

        self.fake_bot = MagicMock()
        self.fake_bot.get_ohlcv.return_value = pd.DataFrame({'close': [45000.0]})
        self.fake_bot.create_order.return_value = {'result': {'orderId': 'test-order'}}
        self.fake_bot.update_position_info = MagicMock()
        self.fake_bot.log_trade = MagicMock()
        self.mock_trading_bot_cls.return_value = self.fake_bot

        self.adapter = create_trading_bot_adapter(symbol="BTCUSDT", testnet=True)

    def test_full_trade_cycle(self):
        ohlcv = self.adapter.get_ohlcv(interval="1", limit=1)
        self.fake_bot.get_ohlcv.assert_called_once_with("BTCUSDT", "1", 1)
        current_price = float(ohlcv['close'].iloc[-1])

        qty = 0.01
        stop_loss = current_price * 0.99
        take_profit = current_price * 1.03

        order = self.adapter.create_order(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Market",
            qty=qty,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        self.fake_bot.create_order.assert_called_once_with(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Market",
            qty=qty,
            price=None,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reduce_only=False,
            position_idx=None
        )
        self.assertEqual(order, {'result': {'orderId': 'test-order'}})

        self.adapter.update_position_info()
        self.fake_bot.update_position_info.assert_called_once_with()

        self.adapter.log_trade(
            symbol="BTCUSDT",
            side="Buy",
            qty=qty,
            entry_price=current_price,
            exit_price=current_price + 100,
            pnl=25.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy='manual_test',
            comment='unit-test'
        )
        self.fake_bot.log_trade.assert_called_once()


if __name__ == "__main__":
    unittest.main()
