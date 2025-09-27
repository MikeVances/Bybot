import unittest
from unittest.mock import MagicMock, patch

from bot.exchange.api_adapter import create_trading_bot_adapter


class TestTradingBotPositionInfo(unittest.TestCase):
    def setUp(self):
        trading_bot_patcher = patch('bot.exchange.api_adapter.TradingBotV5')
        self.addCleanup(trading_bot_patcher.stop)
        self.mock_trading_bot_cls = trading_bot_patcher.start()

        self.fake_bot = MagicMock()
        self.mock_trading_bot_cls.return_value = self.fake_bot

        self.adapter = create_trading_bot_adapter(symbol="BTCUSDT", testnet=True)

    def test_update_position_info_with_position(self):
        self.fake_bot.position_size = 0.05
        self.fake_bot.entry_price = 32000.0
        self.fake_bot.position_side = 'Buy'

        self.adapter.update_position_info()

        self.fake_bot.update_position_info.assert_called_once_with()
        self.assertEqual(self.adapter.position_size, 0.05)
        self.assertEqual(self.adapter.entry_price, 32000.0)
        self.assertEqual(self.adapter.position_side, 'Buy')

    def test_update_position_info_no_position(self):
        self.fake_bot.position_size = 0.0
        self.fake_bot.entry_price = 0.0
        self.fake_bot.position_side = None

        self.adapter.update_position_info()

        self.fake_bot.update_position_info.assert_called_once_with()
        self.assertEqual(self.adapter.position_size, 0.0)
        self.assertEqual(self.adapter.entry_price, 0.0)
        self.assertIsNone(self.adapter.position_side)


if __name__ == "__main__":
    unittest.main()
