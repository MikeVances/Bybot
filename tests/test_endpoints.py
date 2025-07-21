import unittest
from bot.exchange.endpoints import Position, Trade, Account, Market


class TestEndpoints(unittest.TestCase):
    def test_position_endpoints(self):
        """Тест перечислений эндпоинтов позиций"""
        self.assertEqual(str(Position.GET_POSITIONS), "/v5/position/list")
        self.assertEqual(str(Position.SET_LEVERAGE), "/v5/position/set-leverage")
        self.assertEqual(str(Position.SET_TRADING_STOP), "/v5/position/trading-stop")

    def test_trade_endpoints(self):
        """Тест перечислений эндпоинтов торговли"""
        self.assertEqual(str(Trade.PLACE_ORDER), "/v5/order/create")
        self.assertEqual(str(Trade.CANCEL_ALL_ORDERS), "/v5/order/cancel-all")
        self.assertEqual(str(Trade.AMEND_ORDER), "/v5/order/amend")
        self.assertEqual(str(Trade.BATCH_PLACE_ORDER), "/v5/order/create-batch")

    def test_account_endpoints(self):
        """Тест перечислений эндпоинтов аккаунта"""
        self.assertEqual(str(Account.GET_WALLET_BALANCE), "/v5/account/wallet-balance")

    def test_market_endpoints(self):
        """Тест перечислений эндпоинтов рынка"""
        self.assertEqual(str(Market.GET_SERVER_TIME), "/v5/market/time")
        self.assertEqual(str(Market.GET_KLINE), "/v5/market/kline")
        self.assertEqual(str(Market.GET_MARK_PRICE_KLINE), "/v5/market/mark-price-kline")
        self.assertEqual(str(Market.GET_ORDERBOOK), "/v5/market/orderbook")
        self.assertEqual(str(Market.GET_FUNDING_RATE_HISTORY), "/v5/market/funding/history")


if __name__ == '__main__':
    unittest.main() 