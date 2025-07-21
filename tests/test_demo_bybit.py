import unittest
from bot.exchange.bybit_api import BybitAPI

class TestBybitAPI(unittest.TestCase):
    def setUp(self):
        self.api = BybitAPI()

    def test_get_wallet_balance_v5(self):
        balance = self.api.get_wallet_balance_v5()
        self.assertIsNotNone(balance, "Баланс не должен быть None")

    def test_format_balance_v5(self):
        balance = self.api.get_wallet_balance_v5()
        formatted = self.api.format_balance_v5(balance)
        self.assertIsInstance(formatted, str, "Форматированный баланс должен быть строкой")
        print(formatted)

if __name__ == "__main__":
    unittest.main()