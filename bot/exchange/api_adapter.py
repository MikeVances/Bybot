# bot/exchange/api_adapter.py
"""
Современный адаптер для Bybit API v5
Единственный и лучший способ работы с биржей
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

# Импортируем только v5 API - никакого другого не существует!
from .bybit_api_v5 import BybitAPIV5, TradingBotV5


class APIAdapter:
    """
    Адаптер для Bybit API v5
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False):
        """
        Инициализация адаптера
        
        Args:
            api_key: API ключ
            api_secret: API секрет
            testnet: Использовать тестовую сеть
        """
        self.testnet = testnet
        
        # Создаем API v5
        self.api = BybitAPIV5(api_key, api_secret, testnet)
        self.logger = logging.getLogger('api_adapter_v5')
        
        self.logger.info(f"🔧 API Adapter инициализирован (v5, testnet: {testnet})")
    
    def get_wallet_balance_v5(self) -> Dict[str, Any]:
        """Получение баланса кошелька"""
        return self.api.get_wallet_balance_v5()
    
    def format_balance_v5(self, balance_data: Dict[str, Any]) -> str:
        """Форматирование баланса"""
        return self.api.format_balance_v5(balance_data)
    
    def create_order(self, symbol: str, side: str, order_type: str, qty: float, 
                    price: Optional[float] = None, stop_loss: Optional[float] = None, 
                    take_profit: Optional[float] = None, reduce_only: bool = False, 
                    position_idx: Optional[int] = None) -> Dict[str, Any]:
        """Создание ордера"""
        return self.api.create_order(symbol, side, order_type, qty, price, 
                                   stop_loss, take_profit, reduce_only, position_idx)
    
    def set_trading_stop(self, symbol: str, stop_loss: Optional[float] = None, 
                         take_profit: Optional[float] = None, 
                         sl_trigger_by: str = "MarkPrice", 
                         tp_trigger_by: str = "MarkPrice") -> Dict[str, Any]:
        """Установка стопов"""
        return self.api.set_trading_stop(symbol, stop_loss, take_profit, 
                                       sl_trigger_by, tp_trigger_by)
    
    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Получение позиций"""
        return self.api.get_positions(symbol)
    
    def get_ohlcv(self, symbol: str = "BTCUSDT", interval: str = "1", limit: int = 100):
        """Получение OHLCV данных"""
        return self.api.get_ohlcv(symbol, interval, limit)
    
    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Отмена всех ордеров"""
        return self.api.cancel_all_orders(symbol)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Получение открытых ордеров"""
        return self.api.get_open_orders(symbol)
    
    def get_server_time(self) -> Dict[str, Any]:
        """Получение времени сервера"""
        return self.api.get_server_time()
    
    def log_trade(self, symbol: str, side: str, qty: float, entry_price: float, 
                  exit_price: float, pnl: float, stop_loss: Optional[float] = None, 
                  take_profit: Optional[float] = None, strategy: str = "", 
                  comment: str = "") -> None:
        """Логирование сделки"""
        return self.api.log_trade(symbol, side, qty, entry_price, exit_price, 
                                pnl, stop_loss, take_profit, strategy, comment)
    
    def log_strategy_signal(self, strategy: str, symbol: str, signal: str, 
                           market_data: Dict[str, Any], indicators: Dict[str, Any], 
                           comment: str = "") -> None:
        """Логирование сигнала стратегии"""
        return self.api.log_strategy_signal(strategy, symbol, signal, 
                                         market_data, indicators, comment)


class TradingBotAdapter:
    """
    Адаптер для TradingBot v5
    """
    
    def __init__(self, symbol: str = "BTCUSDT", api_key: str = None, 
                 api_secret: str = None, uid: str = None, testnet: bool = False):
        """
        Инициализация адаптера торгового бота
        
        Args:
            symbol: Торговый инструмент
            api_key: API ключ
            api_secret: API секрет
            uid: UID аккаунта
            testnet: Использовать тестовую сеть
        """
        self.symbol = symbol
        self.uid = uid
        
        self.bot = TradingBotV5(symbol, api_key, api_secret, uid, testnet)
        self.logger = logging.getLogger('trading_bot_adapter')
        
        self.logger.info(f"🤖 TradingBot Adapter инициализирован (symbol: {symbol})")
    
    def update_position_info(self) -> None:
        """Обновление информации о позиции"""
        return self.bot.update_position_info()
    
    def execute_strategy(self, risk_percent: float = 0.01) -> None:
        """Выполнение стратегии"""
        return self.bot.execute_strategy(risk_percent)
    
    def get_ohlcv(self, interval: str = "1", limit: int = 100):
        """Получение OHLCV данных"""
        return self.bot.get_ohlcv(self.symbol, interval, limit)

    def get_wallet_balance_v5(self) -> Dict[str, Any]:
        """Получение баланса кошелька"""
        return self.bot.get_wallet_balance_v5()

    def format_balance_v5(self, balance_data: Dict[str, Any]) -> str:
        """Форматирование баланса"""
        return self.bot.format_balance_v5(balance_data)

    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Получение позиций"""
        return self.bot.get_positions(symbol or self.symbol)

    def log_strategy_signal(self, strategy: str, symbol: str, signal: str,
                           market_data: Dict[str, Any], indicators: Dict[str, Any],
                           comment: str = "") -> None:
        """Логирование сигнала стратегии"""
        return self.bot.log_strategy_signal(strategy, symbol, signal,
                                         market_data, indicators, comment)


# Фабричные функции для создания адаптеров
def create_api_adapter(api_key: str = None, api_secret: str = None, 
                      testnet: bool = False) -> APIAdapter:
    """
    Создание адаптера API
    
    Args:
        api_key: API ключ
        api_secret: API секрет
        testnet: Использовать тестовую сеть
        
    Returns:
        Экземпляр APIAdapter
    """
    return APIAdapter(api_key, api_secret, testnet)


def create_trading_bot_adapter(symbol: str = "BTCUSDT", api_key: str = None, 
                              api_secret: str = None, uid: str = None, 
                              testnet: bool = False) -> TradingBotAdapter:
    """
    Создание адаптера торгового бота
    
    Args:
        symbol: Торговый инструмент
        api_key: API ключ
        api_secret: API секрет
        uid: UID аккаунта
        testnet: Использовать тестовую сеть
        
    Returns:
        Экземпляр TradingBotAdapter
    """
    return TradingBotAdapter(symbol, api_key, api_secret, uid, testnet)


# Функция для тестирования API v5
def test_api_v5() -> Dict[str, Any]:
    """
    Функция для тестирования API v5
    
    Returns:
        Результат тестирования
    """
    try:
        # Тестируем API v5
        api = create_api_adapter(testnet=True)
        
        # Тестируем основные функции
        tests = {
            'server_time': api.get_server_time(),
            'balance': api.get_wallet_balance_v5(),
            'positions': api.get_positions(),
            'ohlcv': api.get_ohlcv("BTCUSDT", "1", 10)
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
            'api_status': 'working',
            'api_version': 'v5',
            'test_results': results,
            'recommendation': 'API v5 готов к использованию'
        }
        
    except Exception as e:
        return {
            'api_status': 'failed',
            'api_version': 'v5',
            'error': str(e),
            'recommendation': 'Проверьте установку pybit и настройки API'
        }


if __name__ == "__main__":
    # Тестирование API
    result = test_api_v5()
    print("Результат тестирования:", result)