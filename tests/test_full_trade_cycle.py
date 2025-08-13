import unittest
import time
import os
import csv
import requests
import hmac
import hashlib
from bot.exchange.api_adapter import create_trading_bot_adapter
from config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_API_URL

def manual_close_position(api_key, api_secret, symbol, qty, side, position_idx=0):
    url = f"{BYBIT_API_URL}/v5/order/create"
    timestamp = str(int(time.time() * 1000))
    params = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "reduceOnly": "true",
        "positionIdx": str(position_idx),
        "accountType": "UNIFIED",
        "api_key": api_key,
        "timestamp": timestamp
    }
    # Собираем строку для подписи (параметры в алфавитном порядке)
    param_string = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = hmac.new(api_secret.encode(), param_string.encode(), hashlib.sha256).hexdigest()
    params["sign"] = sign

    response = requests.post(url, json=params)
    print("Manual close position response:", response.json())
    return response.json()

class TestFullTradeCycle(unittest.TestCase):
    """
    Интеграционный тест полного торгового цикла.
    ВНИМАНИЕ: Запускать только на тестовой сети Bybit с тестовым API-ключом!
    """
    def setUp(self):
        self.symbol = "BTCUSDT"
        self.bot = create_trading_bot_adapter(symbol=self.symbol, use_v5=True, testnet=True)
        self.usdt_amount = 1000

    def test_full_trade_cycle(self):
        # Проверяем количество строк в trades.csv до теста
        trades_path = 'data/trades.csv'
        if os.path.exists(trades_path):
            with open(trades_path, 'r') as f:
                before_lines = sum(1 for _ in f)
        else:
            before_lines = 0

        # 1. Получить текущую цену
        ohlcv = self.bot.get_ohlcv(interval="1", limit=1)
        self.assertFalse(ohlcv.empty, "Не удалось получить цену")
        current_price = float(ohlcv["close"].iloc[-1])
        print(f"Текущая цена: {current_price}")

        # 2. Определить направление по стратегии (заглушка для теста)
        signal = "SELL"  # Заглушка: всегда открываем шорт для теста
        self.assertIn(signal, ["BUY", "SELL"], "Нет сигнала для входа")
        print(f"Сигнал стратегии: {signal}")

        # 3. Рассчитать стоп-лосс и тейк-профит (1:3)
        min_qty = 0.01  # Минимальный лот для BTCUSDT
        qty = max(round(self.usdt_amount / current_price, 4), min_qty)
        if signal == "BUY":
            stop_loss = current_price - (current_price * 0.01)
            take_profit = current_price + (current_price * 0.03)
            side = "Buy"
        else:
            stop_loss = current_price + (current_price * 0.01)
            take_profit = current_price - (current_price * 0.03)
            side = "Sell"
        print(f"Открываем {side} qty={qty} SL={stop_loss} TP={take_profit}")

        # 4. Открыть позицию
        order = self.bot.create_order(
            symbol=self.symbol,
            side=side,
            order_type="Market",
            qty=qty,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        self.assertIsNotNone(order, "Не удалось открыть позицию")
        print(f"Ордер создан: {order}")

        # 5. Проверить состояние позиции
        time.sleep(2)  # Дать бирже время обработать ордер
        self.bot.update_position_info()
        self.assertGreater(self.bot.position_size, 0, "Позиция не открыта")
        print(f"Позиция открыта: size={self.bot.position_size}, entry={self.bot.entry_price}")

        # 6. Подождать минуту
        print("Ждём 5 секунд...")
        time.sleep(5)

        # 7. Закрыть позицию ручным запросом
        api_key = BYBIT_API_KEY
        api_secret = BYBIT_API_SECRET
        close_qty = self.bot.position_size
        close_side = "Buy" if side == "Sell" else "Sell"
        manual_close_position(api_key, api_secret, self.symbol, close_qty, close_side, position_idx=0)

        # 7.1 Логируем сделку вручную для теста
        self.bot.log_trade(
            symbol=self.symbol,
            side=close_side,
            qty=close_qty,
            entry_price=self.bot.entry_price if hasattr(self.bot, 'entry_price') else '',
            exit_price='',  # Можно получить через get_positions или оставить пустым
            pnl='',
            stop_loss='',
            take_profit='',
            strategy='manual_test',
            comment='Manual close in test'
        )

        # 8. Проверить, что позиции нет
        time.sleep(2)
        self.bot.update_position_info()
        self.assertEqual(self.bot.position_size, 0.0, "Позиция не закрыта")
        print("Позиция полностью закрыта!")

        # 9. Проверить, что в trades.csv появилась новая запись
        if os.path.exists(trades_path):
            with open(trades_path, 'r') as f:
                after_lines = sum(1 for _ in f)
            print(f"Строк в trades.csv до: {before_lines}, после: {after_lines}")
            self.assertGreater(after_lines, before_lines, "В trades.csv не появилась новая запись о сделке!")
        else:
            self.fail("Файл trades.csv не найден после теста!")

if __name__ == "__main__":
    unittest.main() 