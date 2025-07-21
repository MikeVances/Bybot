import unittest
from bot.exchange.bybit_api import TradingBot

class TestOrderPlacement(unittest.TestCase):
    def setUp(self):
        self.bot = TradingBot(symbol="BTCUSDT")

    def test_create_order(self):
        # Получаем актуальную цену
        ohlcv = self.bot.get_ohlcv(interval="1", limit=1)
        current_price = float(ohlcv["close"].iloc[-1])
        qty = 0.01  # Минимальный лот для BTCUSDT (проверь для своей пары)
        side = "Buy"
        stop_loss = current_price - 100  # SL ниже цены
        take_profit = current_price + 300  # TP выше цены
        order = self.bot.create_order(
            symbol="BTCUSDT",
            side=side,
            order_type="Market",
            qty=qty,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        self.assertIsNotNone(order, "Не удалось создать ордер")
        print('Создание ордера:', order)

if __name__ == "__main__":
    unittest.main() 