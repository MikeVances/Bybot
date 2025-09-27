import unittest
from unittest.mock import MagicMock, patch

from bot.exchange.api_adapter import create_api_adapter


class TestBybitAPI(unittest.TestCase):
    def setUp(self):
        bybit_patcher = patch('bot.exchange.api_adapter.BybitAPIV5')
        self.addCleanup(bybit_patcher.stop)
        self.mock_api_cls = bybit_patcher.start()

        self.fake_api = MagicMock()
        self.fake_api.get_wallet_balance_v5.return_value = {
            'retCode': 0,
            'result': {
                'list': [
                    {
                        'coin': [
                            {'coin': 'USDT', 'walletBalance': '100.0', 'usdValue': '100.0'}
                        ],
                        'totalEquity': '100.0',
                        'totalAvailableBalance': '80.0',
                    }
                ]
            },
        }
        self.fake_api.format_balance_v5.return_value = "Баланс: $100"
        self.mock_api_cls.return_value = self.fake_api

        self.adapter = create_api_adapter(testnet=True)

    def test_get_wallet_balance_v5(self):
        balance = self.adapter.get_wallet_balance_v5()
        self.fake_api.get_wallet_balance_v5.assert_called_once_with()
        self.assertEqual(balance['retCode'], 0)

    def test_format_balance_v5(self):
        balance = self.adapter.get_wallet_balance_v5()
        formatted = self.adapter.format_balance_v5(balance)
        self.fake_api.format_balance_v5.assert_called_once_with(balance)
        self.assertEqual(formatted, "Баланс: $100")


if __name__ == "__main__":
    unittest.main()
