import unittest
from unittest.mock import patch
from bot.exchange.bybit_api import TradingBot

class TestTradingBotPositionInfo(unittest.TestCase):
    def setUp(self):
        self.bot = TradingBot(symbol="BTCUSDT")

    @patch.object(TradingBot, 'get_positions')
    def test_update_position_info_with_position(self, mock_get_positions):
        # Мокаем ответ Bybit API с открытой позицией
        mock_get_positions.return_value = {
            'result': {
                'list': [{
                    'size': '0.05',
                    'avgPrice': '32000',
                    'side': 'Buy'
                }]
            },
            'retCode': 0
        }
        self.bot.update_position_info()
        self.assertEqual(self.bot.position_size, 0.05)
        self.assertEqual(self.bot.entry_price, 32000.0)
        self.assertEqual(self.bot.position_side, 'Buy')

    @patch.object(TradingBot, 'get_positions')
    def test_update_position_info_no_position(self, mock_get_positions):
        # Мокаем ответ Bybit API без открытых позиций
        mock_get_positions.return_value = {
            'result': {
                'list': []
            },
            'retCode': 0
        }
        self.bot.update_position_info()
        self.assertEqual(self.bot.position_size, 0.0)
        self.assertEqual(self.bot.entry_price, 0.0)
        self.assertIsNone(self.bot.position_side)

if __name__ == "__main__":
    unittest.main() 