# bot/exchange/api_adapter.py
"""
Адаптер для интеграции нового Bybit API v5 в существующую систему
Позволяет постепенно переходить с старого API на новый
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

# Импортируем оба API
from .bybit_api import BybitAPI
from .bybit_api_v5 import BybitAPIV5, TradingBotV5


class APIAdapter:
    """
    Адаптер для переключения между старым и новым API
    Позволяет постепенно мигрировать на новый API
    """
    
    def __init__(self, use_v5: bool = True, api_key: str = None, 
                 api_secret: str = None, testnet: bool = False):
        """
        Инициализация адаптера
        
        Args:
            use_v5: Использовать новый API v5
            api_key: API ключ
            api_secret: API секрет
            testnet: Использовать тестовую сеть
        """
        self.use_v5 = use_v5
        self.testnet = testnet
        
        # Создаем соответствующий API
        if use_v5:
            self.api = BybitAPIV5(api_key, api_secret, testnet)
            self.logger = logging.getLogger('api_adapter_v5')
        else:
            self.api = BybitAPI()
            self.logger = logging.getLogger('api_adapter_v4')
        
        self.logger.info(f"🔧 API Adapter инициализирован (v5: {use_v5}, testnet: {testnet})")
    
    def get_wallet_balance_v5(self) -> Dict[str, Any]:
        """Получение баланса кошелька"""
        if self.use_v5:
            return self.api.get_wallet_balance_v5()
        else:
            return self.api.get_wallet_balance_v5()
    
    def format_balance_v5(self, balance_data: Dict[str, Any]) -> str:
        """Форматирование баланса"""
        if self.use_v5:
            return self.api.format_balance_v5(balance_data)
        else:
            return self.api.format_balance_v5(balance_data)
    
    def create_order(self, symbol: str, side: str, order_type: str, qty: float, 
                    price: Optional[float] = None, stop_loss: Optional[float] = None, 
                    take_profit: Optional[float] = None, reduce_only: bool = False, 
                    position_idx: Optional[int] = None) -> Dict[str, Any]:
        """Создание ордера"""
        if self.use_v5:
            return self.api.create_order(symbol, side, order_type, qty, price, 
                                       stop_loss, take_profit, reduce_only, position_idx)
        else:
            return self.api.create_order(symbol, side, order_type, qty, price, 
                                       stop_loss, take_profit, reduce_only, position_idx)
    
    def set_trading_stop(self, symbol: str, stop_loss: Optional[float] = None, 
                         take_profit: Optional[float] = None, 
                         sl_trigger_by: str = "MarkPrice", 
                         tp_trigger_by: str = "MarkPrice") -> Dict[str, Any]:
        """Установка стопов"""
        if self.use_v5:
            return self.api.set_trading_stop(symbol, stop_loss, take_profit, 
                                           sl_trigger_by, tp_trigger_by)
        else:
            return self.api.set_trading_stop(symbol, stop_loss, take_profit, 
                                           sl_trigger_by, tp_trigger_by)
    
    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Получение позиций"""
        if self.use_v5:
            return self.api.get_positions(symbol)
        else:
            return self.api.get_positions(symbol)
    
    def get_ohlcv(self, symbol: str = "BTCUSDT", interval: str = "1", limit: int = 100):
        """Получение OHLCV данных"""
        if self.use_v5:
            return self.api.get_ohlcv(symbol, interval, limit)
        else:
            return self.api.get_ohlcv(interval, limit)
    
    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Отмена всех ордеров"""
        if self.use_v5:
            return self.api.cancel_all_orders(symbol)
        else:
            return self.api.cancel_all_orders(symbol)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Получение открытых ордеров"""
        if self.use_v5:
            return self.api.get_open_orders(symbol)
        else:
            return self.api.get_open_orders(symbol)
    
    def get_server_time(self) -> Dict[str, Any]:
        """Получение времени сервера"""
        if self.use_v5:
            return self.api.get_server_time()
        else:
            return self.api.get_server_time()
    
    def log_trade(self, symbol: str, side: str, qty: float, entry_price: float, 
                  exit_price: float, pnl: float, stop_loss: Optional[float] = None, 
                  take_profit: Optional[float] = None, strategy: str = "", 
                  comment: str = "") -> None:
        """Логирование сделки"""
        if self.use_v5:
            return self.api.log_trade(symbol, side, qty, entry_price, exit_price, 
                                    pnl, stop_loss, take_profit, strategy, comment)
        else:
            return self.api.log_trade(symbol, side, qty, entry_price, exit_price, 
                                    pnl, stop_loss, take_profit, strategy, comment)
    
    def log_strategy_signal(self, strategy: str, symbol: str, signal: str, 
                           market_data: Dict[str, Any], indicators: Dict[str, Any], 
                           comment: str = "") -> None:
        """Логирование сигнала стратегии"""
        if self.use_v5:
            return self.api.log_strategy_signal(strategy, symbol, signal, 
                                             market_data, indicators, comment)
        else:
            return self.api.log_strategy_signal(strategy, symbol, signal, 
                                             market_data, indicators, comment)


class TradingBotAdapter:
    """
    Адаптер для TradingBot
    """
    
    def __init__(self, symbol: str = "BTCUSDT", api_key: str = None, 
                 api_secret: str = None, uid: str = None, use_v5: bool = True, 
                 testnet: bool = False):
        """
        Инициализация адаптера торгового бота
        
        Args:
            symbol: Торговый инструмент
            api_key: API ключ
            api_secret: API секрет
            uid: UID аккаунта
            use_v5: Использовать новый API v5
            testnet: Использовать тестовую сеть
        """
        self.use_v5 = use_v5
        self.symbol = symbol
        self.uid = uid
        
        if use_v5:
            self.bot = TradingBotV5(symbol, api_key, api_secret, uid, testnet)
            self.logger = logging.getLogger('trading_bot_adapter_v5')
        else:
            from .bybit_api import TradingBot
            self.bot = TradingBot(symbol, api_key, api_secret, uid)
            self.logger = logging.getLogger('trading_bot_adapter_v4')
        
        self.logger.info(f"🤖 TradingBot Adapter инициализирован (v5: {use_v5}, symbol: {symbol})")
    
    def update_position_info(self) -> None:
        """Обновление информации о позиции"""
        if self.use_v5:
            return self.bot.update_position_info()
        else:
            return self.bot.update_position_info()
    
    def execute_strategy(self, risk_percent: float = 0.01) -> None:
        """Выполнение стратегии"""
        if self.use_v5:
            return self.bot.execute_strategy(risk_percent)
        else:
            return self.bot.execute_strategy(risk_percent)
    
    def get_ohlcv(self, interval: str = "1", limit: int = 100):
        """Получение OHLCV данных"""
        if self.use_v5:
            return self.bot.get_ohlcv(self.symbol, interval, limit)
        else:
            return self.bot.get_ohlcv(interval, limit)
    
    def check_sma_signal(self, window_short: int = 20, window_long: int = 50):
        """Проверка SMA сигнала"""
        if self.use_v5:
            # В v5 нужно реализовать эту функцию
            self.logger.warning("SMA сигнал не реализован в v5")
            return None
        else:
            return self.bot.check_sma_signal(window_short, window_long)


# Фабричные функции для создания адаптеров
def create_api_adapter(use_v5: bool = True, api_key: str = None, 
                      api_secret: str = None, testnet: bool = False) -> APIAdapter:
    """
    Создание адаптера API
    
    Args:
        use_v5: Использовать новый API v5
        api_key: API ключ
        api_secret: API секрет
        testnet: Использовать тестовую сеть
        
    Returns:
        Экземпляр APIAdapter
    """
    return APIAdapter(use_v5, api_key, api_secret, testnet)


def create_trading_bot_adapter(symbol: str = "BTCUSDT", api_key: str = None, 
                              api_secret: str = None, uid: str = None, 
                              use_v5: bool = True, testnet: bool = False) -> TradingBotAdapter:
    """
    Создание адаптера торгового бота
    
    Args:
        symbol: Торговый инструмент
        api_key: API ключ
        api_secret: API секрет
        uid: UID аккаунта
        use_v5: Использовать новый API v5
        testnet: Использовать тестовую сеть
        
    Returns:
        Экземпляр TradingBotAdapter
    """
    return TradingBotAdapter(symbol, api_key, api_secret, uid, use_v5, testnet)


# Функция для миграции с v4 на v5
def migrate_to_v5_api() -> Dict[str, Any]:
    """
    Функция для тестирования миграции на v5 API
    
    Returns:
        Результат тестирования
    """
    try:
        # Тестируем v5 API
        v5_api = create_api_adapter(use_v5=True, testnet=True)
        
        # Тестируем основные функции
        tests = {
            'server_time': v5_api.get_server_time(),
            'balance': v5_api.get_wallet_balance_v5(),
            'positions': v5_api.get_positions(),
            'ohlcv': v5_api.get_ohlcv("BTCUSDT", "1", 10)
        }
        
        # Анализируем результаты
        results = {}
        for test_name, result in tests.items():
            if test_name == 'ohlcv':
                # Для OHLCV данных проверяем, что это DataFrame
                if result is not None and hasattr(result, 'shape') and result.shape[0] > 0:
                    results[test_name] = "✅ Успешно"
                else:
                    results[test_name] = "❌ Ошибка: Нет данных"
            elif result and result.get('retCode') == 0:
                results[test_name] = "✅ Успешно"
            else:
                results[test_name] = f"❌ Ошибка: {result.get('retMsg', 'Unknown') if result else 'No response'}"
        
        return {
            'migration_status': 'completed',
            'v5_api_available': True,
            'test_results': results,
            'recommendation': 'v5 API готов к использованию'
        }
        
    except Exception as e:
        return {
            'migration_status': 'failed',
            'v5_api_available': False,
            'error': str(e),
            'recommendation': 'Проверьте установку pybit и настройки API'
        }


if __name__ == "__main__":
    # Тестирование миграции
    result = migrate_to_v5_api()
    print("Результат миграции:", result) 