# bot/exchange/bybit_api_v5.py
"""
Новая реализация Bybit API v5 с использованием официальной библиотеки pybit
Предоставляет более надежный и актуальный интерфейс для работы с Bybit
"""

import os
import logging
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union, Callable
import csv

from pybit.unified_trading import HTTP
from config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_API_URL


class BybitAPIV5:
    """
    Новая реализация Bybit API v5 с использованием официальной библиотеки pybit
    
    Преимущества:
    - Официальная поддержка Bybit
    - Автоматическое обновление API
    - Лучшая обработка ошибок
    - Поддержка всех новых функций v5
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False):
        """
        Инициализация Bybit API v5

        Args:
            api_key: API ключ (если None, используется из config)
            api_secret: API секрет (если None, используется из config)
            testnet: Использовать тестовую сеть
        """
        # Используем переданные ключи или дефолтные из config
        self.api_key = api_key or BYBIT_API_KEY
        self.api_secret = api_secret or BYBIT_API_SECRET

        # Используем централизованную конфигурацию API
        from config import get_api_config
        api_config = get_api_config()
        self.base_url = api_config['base_url']

        # Используем централизованную настройку testnet
        self.testnet = api_config['testnet']

        # Создаем сессию с официальной библиотекой
        # Отключаем системный прокси для стабильного соединения с Bybit API
        import os
        original_proxies = {}
        for proxy_key in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
            if proxy_key in os.environ:
                original_proxies[proxy_key] = os.environ.pop(proxy_key)

        try:
            self.session = HTTP(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet  # Используем централизованную настройку
            )
        finally:
            # Восстанавливаем прокси настройки
            for key, value in original_proxies.items():
                os.environ[key] = value

        # Для testnet сервера устанавливаем правильный endpoint
        if self.testnet:
            self.session.endpoint = self.base_url
            # Обязательно устанавливаем правильный базовый URL для demo сервера
            self.session.BASE_URL = self.base_url

        # Настройка защищённого логирования (ленивая инициализация)
        self._logger = None

        # Rate limiter будет инициализирован при первом использовании
        self._rate_limiter = None

        # 🔄 Enhanced Connection Manager с heartbeat мониторингом
        self._connection_manager = None

        # Настройка enhanced connection manager
        from bot.core.enhanced_api_connection import setup_enhanced_connection_manager
        self.connection_manager = setup_enhanced_connection_manager(
            self.session,
            base_url=self.base_url,
            backup_endpoints=None  # Используем только основной endpoint из конфигурации
        )

        # Логируем инициализацию через стандартный logger
        import logging
        logging.getLogger('bybit_api_v5').info(f"🚀 Bybit API v5 инициализирован (testnet: {self.testnet}, URL: {self.base_url})")

    @property
    def logger(self):
        """Ленивая инициализация logger для избежания циркулярного импорта"""
        if self._logger is None:
            try:
                from bot.core.secure_logger import get_secure_logger
                self._logger = get_secure_logger('bybit_api_v5')
            except ImportError:
                import logging
                self._logger = logging.getLogger('bybit_api_v5')
        return self._logger

    @property
    def rate_limiter(self):
        """Ленивая инициализация rate_limiter для избежания циркулярного импорта"""
        if self._rate_limiter is None:
            try:
                from bot.core.rate_limiter import get_rate_limiter
                self._rate_limiter = get_rate_limiter()
            except ImportError:
                # Fallback: создаем заглушку если rate_limiter недоступен
                class MockRateLimiter:
                    def can_make_request(self, endpoint): return True
                self._rate_limiter = MockRateLimiter()
        return self._rate_limiter

    def _call_api(self, operation_name: str, func: Callable[[], Dict[str, Any]],
                  *, cache_key: Optional[str] = None) -> Dict[str, Any]:
        if self.connection_manager:
            try:
                return self.connection_manager.execute_with_fallback(
                    operation=func,
                    operation_name=operation_name,
                    cache_key=cache_key
                )
            except Exception as exc:
                self.logger.error(f"❌ {operation_name}: {exc}")
                return {"retCode": -1, "retMsg": str(exc)}

        try:
            return func()
        except Exception as exc:
            self.logger.error(f"❌ {operation_name}: {exc}")
            return {"retCode": -1, "retMsg": str(exc)}

    def get_wallet_balance_v5(self) -> Dict[str, Any]:
        """
        Получение баланса кошелька (v5 API)
        
        Returns:
            Dict с информацией о балансе
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед API вызовом
            if not self.rate_limiter.can_make_request("get_wallet_balance"):
                return {"retCode": -1001, "retMsg": "Rate limit exceeded for get_wallet_balance"}
            
            response = self._call_api(
                "get_wallet_balance",
                lambda: self.session.get_wallet_balance(accountType="UNIFIED"),
                cache_key="wallet_balance"
            )
            self.logger.safe_log_api_response(
                response, 
                "Баланс получен успешно", 
                "Ошибка получения баланса"
            )
            return response
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения баланса: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def format_balance_v5(self, balance_data: Dict[str, Any]) -> str:
        """
        Форматирование баланса для отображения
        
        Args:
            balance_data: Данные баланса от API
            
        Returns:
            Отформатированная строка с балансом
        """
        if not balance_data or balance_data.get('retCode') != 0:
            return "Ошибка получения баланса"
        
        try:
            # Безопасная конвертация значений
            def safe_float_format(value, decimals=4):
                try:
                    if value == '' or value is None:
                        return "0.0000"
                    return f"{float(value):.{decimals}f}"
                except (ValueError, TypeError):
                    return "0.0000"

            result = balance_data['result']['list'][0]
            coins = "\n".join(
                f"{coin['coin']}: {safe_float_format(coin.get('walletBalance', 0))} (${safe_float_format(coin.get('usdValue', 0), 2)})"
                for coin in result.get('coin', [])
            )

            total_equity = safe_float_format(result.get('totalEquity', 0), 2)
            total_available = safe_float_format(result.get('totalAvailableBalance', 0), 2)

            return f"""Общий баланс: ${total_equity}
Доступно: ${total_available}
Монеты:
{coins}"""
        except Exception as e:
            self.logger.error(f"Ошибка форматирования баланса: {e}")
            return "Ошибка форматирования баланса"
    
    def create_order(self, symbol: str, side: str, order_type: str, qty: float, 
                    price: Optional[float] = None, stop_loss: Optional[float] = None, 
                    take_profit: Optional[float] = None, reduce_only: bool = False, 
                    position_idx: Optional[int] = None) -> Dict[str, Any]:
        """
        Создание ордера (v5 API)
        
        Args:
            symbol: Торговый инструмент (например, BTCUSDT)
            side: Сторона (Buy/Sell)
            order_type: Тип ордера (Market/Limit)
            qty: Количество
            price: Цена (для лимитных ордеров)
            stop_loss: Цена стоп-лосс
            take_profit: Цена тейк-профит
            reduce_only: Только для закрытия позиции
            position_idx: Индекс позиции
            
        Returns:
            Ответ API
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед критическим API вызовом
            if not self.rate_limiter.can_make_request("create_order"):
                return {"retCode": -1001, "retMsg": "Rate limit exceeded for create_order"}
            # Подготавливаем параметры
            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "accountType": "UNIFIED"
            }
            
            # Добавляем цену для лимитных ордеров
            if order_type == "Limit" and price:
                params["price"] = str(price)
            
            # Стопы устанавливаются отдельно через set_trading_stop()
            # Для рыночных ордеров stopLoss и takeProfit в create_order не поддерживаются
            
            # Добавляем reduce_only
            if reduce_only:
                params["reduceOnly"] = True
            
            # Добавляем position_idx
            if position_idx is not None:
                params["positionIdx"] = position_idx
            
            # Безопасное логирование запроса
            self.logger.safe_log_order_request(symbol, side, order_type, qty, price)
            
            response = self._call_api(
                "create_order",
                lambda: self.session.place_order(**params)
            )

            # Безопасное логирование ответа
            self.logger.safe_log_api_response(
                response,
                "Ордер создан успешно",
                "Ошибка создания ордера"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания ордера: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def set_trading_stop(self, symbol: str, stop_loss: Optional[float] = None, 
                         take_profit: Optional[float] = None, 
                         sl_trigger_by: str = "MarkPrice", 
                         tp_trigger_by: str = "MarkPrice") -> Dict[str, Any]:
        """
        Установка стоп-лосс и тейк-профит (v5 API)
        
        Args:
            symbol: Торговый инструмент
            stop_loss: Цена стоп-лосс
            take_profit: Цена тейк-профит
            sl_trigger_by: Триггер для SL
            tp_trigger_by: Триггер для TP
            
        Returns:
            Ответ API
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед API вызовом
            if not self.rate_limiter.can_make_request("set_trading_stop"):
                return {"retCode": -1001, "retMsg": "Rate limit exceeded for set_trading_stop"}
            params = {
                "category": "linear",
                "symbol": symbol,
                "accountType": "UNIFIED"
            }
            
            if stop_loss:
                params["stopLoss"] = str(stop_loss)
                params["slTriggerBy"] = sl_trigger_by
                self.logger.info(f"🛑 Устанавливаем SL: {stop_loss}")
            
            if take_profit:
                params["takeProfit"] = str(take_profit)
                params["tpTriggerBy"] = tp_trigger_by
                self.logger.info(f"🎯 Устанавливаем TP: {take_profit}")
            
            response = self._call_api(
                "set_trading_stop",
                lambda: self.session.set_trading_stop(**params)
            )
            
            self.logger.safe_log_api_response(
                response,
                "Стопы установлены успешно",
                "Ошибка установки стопов"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка установки стопов: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Получение позиций (v5 API)
        
        Args:
            symbol: Торговый инструмент (если None, возвращаются все позиции)
            
        Returns:
            Информация о позициях
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед API вызовом
            if not self.rate_limiter.can_make_request("get_positions"):
                return {"retCode": -1001, "retMsg": "Rate limit exceeded for get_positions"}
            params = {
                "category": "linear",
                "accountType": "UNIFIED"
            }
            
            if symbol:
                params["symbol"] = symbol
            
            response = self._call_api(
                "get_positions",
                lambda: self.session.get_positions(**params),
                cache_key=f"positions_{symbol or 'ALL'}"
            )
            
            self.logger.safe_log_api_response(
                response,
                "Позиции получены успешно",
                "Ошибка получения позиций"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения позиций: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def get_ohlcv(self, symbol: str = "BTCUSDT", interval: str = "1", limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Получение OHLCV данных (v5 API) с fallback поддержкой

        Args:
            symbol: Торговый инструмент
            interval: Интервал (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, M, W)
            limit: Количество свечей

        Returns:
            DataFrame с OHLCV данными
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед API вызовом
            if not self.rate_limiter.can_make_request("get_kline"):
                self.logger.error("Rate limit exceeded for get_kline")
                return None

            # Конвертируем интервал в формат Bybit
            interval_map = {
                "1": "1", "3": "3", "5": "5", "15": "15", "30": "30",
                "60": "60", "120": "120", "240": "240", "360": "360", "720": "720",
                "D": "D", "M": "M", "W": "W"
            }

            bybit_interval = interval_map.get(interval, interval)

            def _fetch_ohlcv():
                return self.session.get_kline(
                    category="linear",
                    symbol=symbol,
                    interval=bybit_interval,
                    limit=limit
                )

            # Используем connection manager с fallback
            cache_key = f"ohlcv_{symbol}_{interval}_{limit}"

            response = self.connection_manager.execute_with_fallback(
                operation=_fetch_ohlcv,
                operation_name=f"get_ohlcv_{symbol}",
                cache_key=cache_key
            )

            if response and response.get('retCode') == 0:
                # Конвертируем в DataFrame
                data = response['result']['list']
                df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])

                # Конвертируем типы данных
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                # Конвертируем timestamp (исправляем FutureWarning)
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')

                # Сортируем по времени
                df = df.sort_values('timestamp').reset_index(drop=True)

                self.logger.info(f"✅ OHLCV данные получены: {symbol} {interval} ({len(df)} свечей)")
                return df
            else:
                self.logger.error(f"❌ Ошибка получения OHLCV: {response}")
                return None

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения OHLCV: {e}")
            return None
    
    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """
        Отмена всех ордеров (v5 API)
        
        Args:
            symbol: Торговый инструмент
            
        Returns:
            Ответ API
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед критическим API вызовом
            if not self.rate_limiter.can_make_request("cancel_all_orders"):
                return {"retCode": -1001, "retMsg": "Rate limit exceeded for cancel_all_orders"}
            response = self._call_api(
                "cancel_all_orders",
                lambda: self.session.cancel_all_orders(
                    category="linear",
                    symbol=symbol
                )
            )
            
            self.logger.safe_log_api_response(
                response,
                f"Все ордера отменены: {symbol}",
                "Ошибка отмены ордеров"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отмены ордеров: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Получение открытых ордеров (v5 API)
        
        Args:
            symbol: Торговый инструмент (если None, возвращаются все ордера)
            
        Returns:
            Информация об открытых ордерах
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед API вызовом
            if not self.rate_limiter.can_make_request("get_open_orders"):
                return {"retCode": -1001, "retMsg": "Rate limit exceeded for get_open_orders"}
            params = {
                "category": "linear",
                "accountType": "UNIFIED"
            }
            
            if symbol:
                params["symbol"] = symbol
            
            response = self._call_api(
                "get_open_orders",
                lambda: self.session.get_open_orders(**params),
                cache_key=f"open_orders_{symbol or 'ALL'}"
            )
            
            self.logger.safe_log_api_response(
                response,
                "Открытые ордера получены успешно",
                "Ошибка получения открытых ордеров"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения открытых ордеров: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def get_server_time(self) -> Dict[str, Any]:
        """
        Получение времени сервера (v5 API)
        
        Returns:
            Время сервера
        """
        try:
            response = self._call_api(
                "get_server_time",
                lambda: self.session.get_server_time(),
                cache_key="server_time"
            )
            return response
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения времени сервера: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def get_instruments_info(self, category: str = "linear", symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Получение информации об инструментах (v5 API)
        
        Args:
            category: Категория (linear, inverse, spot, option)
            symbol: Тикер (опционально, для фильтрации)
            
        Returns:
            Информация об инструментах
        """
        try:
            # 🛡️ RATE LIMITING: Проверка перед API вызовом
            if not self.rate_limiter.can_make_request("get_instruments_info"):
                return {"retCode": -1001, "retMsg": "Rate limit exceeded for get_instruments_info"}
            params = {"category": category}
            if symbol:
                params["symbol"] = symbol
                
            response = self._call_api(
                "get_instruments_info",
                lambda: self.session.get_instruments_info(**params),
                cache_key=f"instruments_{category}_{symbol or 'ALL'}"
            )
            
            if response and response.get('retCode') == 0:
                self.logger.info(f"✅ Информация об инструментах получена: {len(response['result']['list'])} инструментов")
                return response
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
                self.logger.error(f"❌ Ошибка получения информации об инструментах: {error_msg}")
                return response or {"retCode": -1, "retMsg": "No response"}
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения информации об инструментах: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def log_trade(self, symbol: str, side: str, qty: float, entry_price: float, 
                  exit_price: float, pnl: float, stop_loss: Optional[float] = None, 
                  take_profit: Optional[float] = None, strategy: str = "", 
                  comment: str = "") -> None:
        """
        Логирование сделки в CSV файл
        
        Args:
            symbol: Торговый инструмент
            side: Сторона сделки
            qty: Количество
            entry_price: Цена входа
            exit_price: Цена выхода
            pnl: Прибыль/убыток
            stop_loss: Стоп-лосс
            take_profit: Тейк-профит
            strategy: Стратегия
            comment: Комментарий
        """
        try:
            # Создаем директорию для логов
            log_dir = "data/logs"
            os.makedirs(log_dir, exist_ok=True)
            
            # Файл для журнала сделок
            journal_file = "data/trade_journal.csv"
            
            # Проверяем, существует ли файл
            file_exists = os.path.exists(journal_file)
            
            with open(journal_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Записываем заголовки, если файл новый
                if not file_exists:
                    writer.writerow([
                        'timestamp', 'symbol', 'side', 'qty', 'entry_price', 'exit_price',
                        'pnl', 'stop_loss', 'take_profit', 'strategy', 'comment'
                    ])
                
                # Записываем данные сделки
                writer.writerow([
                    datetime.now(timezone.utc).isoformat(),
                    symbol, side, qty, entry_price, exit_price,
                    pnl, stop_loss, take_profit, strategy, comment
                ])
            
            self.logger.info(f"📝 Сделка записана в журнал: {symbol} {side} {qty}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка записи сделки в журнал: {e}")
    
    def log_strategy_signal(self, strategy: str, symbol: str, signal: str, 
                           market_data: Dict[str, Any], indicators: Dict[str, Any], 
                           comment: str = "") -> None:
        """
        Логирование сигнала стратегии
        
        Args:
            strategy: Название стратегии
            symbol: Торговый инструмент
            signal: Тип сигнала
            market_data: Рыночные данные
            indicators: Индикаторы
            comment: Комментарий
        """
        try:
            # Создаем директорию для логов стратегий
            log_dir = "data/logs/strategies"
            os.makedirs(log_dir, exist_ok=True)
            
            # Файл для логов стратегии
            strategy_log_file = f"{log_dir}/{strategy.lower().replace(' ', '_')}.log"
            
            # Формируем сообщение
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            message = f"{timestamp} - {strategy} - INFO - 📊 Сигнал: {signal} по цене {market_data.get('close', 'N/A')}"
            
            if comment:
                message += f" - {comment}"
            
            # Записываем в лог
            with open(strategy_log_file, 'a', encoding='utf-8') as f:
                f.write(message + "\n")
            
            self.logger.info(f"📝 Сигнал записан: {strategy} {signal}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка записи сигнала: {e}")


class TradingBotV5(BybitAPIV5):
    """
    Расширенная версия TradingBot с использованием Bybit API v5
    """
    
    def __init__(self, symbol: str = "BTCUSDT", api_key: str = None, 
                 api_secret: str = None, uid: str = None, testnet: bool = False):
        """
        Инициализация торгового бота v5
        
        Args:
            symbol: Торговый инструмент
            api_key: API ключ
            api_secret: API секрет
            uid: UID аккаунта
            testnet: Использовать тестовую сеть
        """
        super().__init__(api_key, api_secret, testnet)
        
        self.symbol = symbol
        self.uid = uid
        
        # Информация о позиции
        self.position_size = 0.0
        self.entry_price = 0.0
        self.position_side = None
        
        self.logger.info(f"🤖 TradingBot v5 инициализирован для {symbol}")
    
    def update_position_info(self) -> None:
        """
        Обновление информации о текущей позиции
        """
        try:
            positions = self.get_positions(self.symbol)
            
            if positions and positions.get('retCode') == 0:
                position_list = positions['result']['list']
                
                if position_list:
                    pos = position_list[0]
                    self.position_size = float(pos.get('size', 0))
                    self.entry_price = float(pos.get('avgPrice', 0))
                    self.position_side = pos.get('side')
                    
                    self.logger.info(f"📊 Позиция обновлена: size={self.position_size}, entry={self.entry_price}, side={self.position_side}")
                else:
                    self.position_size = 0.0
                    self.entry_price = 0.0
                    self.position_side = None
                    self.logger.info("📊 Нет открытых позиций")
            else:
                self.logger.error("❌ Ошибка получения позиций")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления позиции: {e}")
    
    def execute_strategy(self, risk_percent: float = 0.01) -> None:
        """
        Выполнение простой стратегии (пример)
        
        Args:
            risk_percent: Процент риска
        """
        try:
            # Получаем баланс
            balance_data = self.get_wallet_balance_v5()
            
            if not balance_data or balance_data.get('retCode') != 0:
                self.logger.warning("❌ Не удалось получить баланс")
                return
            
            available_balance = float(balance_data['result']['list'][0]['totalAvailableBalance'])
            qty = available_balance * risk_percent
            
            self.logger.info(f"💰 Доступный баланс: ${available_balance:.2f}, размер позиции: ${qty:.2f}")
            
            # Здесь можно добавить логику стратегии
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения стратегии: {e}")


# Функция для создания экземпляра API
def create_bybit_api_v5(api_key: str = None, api_secret: str = None, 
                        testnet: bool = False) -> BybitAPIV5:
    """
    Фабричная функция для создания экземпляра Bybit API v5
    
    Args:
        api_key: API ключ
        api_secret: API секрет
        testnet: Использовать тестовую сеть
        
    Returns:
        Экземпляр BybitAPIV5
    """
    return BybitAPIV5(api_key, api_secret, testnet)


def create_trading_bot_v5(symbol: str = "BTCUSDT", api_key: str = None, 
                          api_secret: str = None, uid: str = None, 
                          testnet: bool = False) -> TradingBotV5:
    """
    Фабричная функция для создания торгового бота v5
    
    Args:
        symbol: Торговый инструмент
        api_key: API ключ
        api_secret: API секрет
        uid: UID аккаунта
        testnet: Использовать тестовую сеть
        
    Returns:
        Экземпляр TradingBotV5
    """
    return TradingBotV5(symbol, api_key, api_secret, uid, testnet) 
