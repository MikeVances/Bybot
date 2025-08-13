# bot/exchange/bybit_api_v5.py
"""
Новая реализация Bybit API v5 с использованием официальной библиотеки pybit
Предоставляет более надежный и актуальный интерфейс для работы с Bybit
"""

import os
import logging
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
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
        
        # Определяем URL в зависимости от testnet
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = BYBIT_API_URL or "https://api.bybit.com"
        
        # Создаем сессию с официальной библиотекой
        self.session = HTTP(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=testnet
        )
        
        # Настройка логирования
        log_dir = 'data/logs'
        os.makedirs(log_dir, exist_ok=True)
        self.logger = logging.getLogger('bybit_api_v5')
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler(os.path.join(log_dir, 'bybit_api_v5.log'))
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        if not self.logger.hasHandlers():
            self.logger.addHandler(handler)
        
        self.logger.info(f"🚀 Bybit API v5 инициализирован (testnet: {testnet})")
    
    def get_wallet_balance_v5(self) -> Dict[str, Any]:
        """
        Получение баланса кошелька (v5 API)
        
        Returns:
            Dict с информацией о балансе
        """
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")
            self.logger.info("✅ Баланс получен успешно")
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
            result = balance_data['result']['list'][0]
            coins = "\n".join(
                f"{coin['coin']}: {coin['walletBalance']} (${coin['usdValue']})"
                for coin in result['coin']
            )
            return f"""Общий баланс: ${result['totalEquity']}
Доступно: ${result['totalAvailableBalance']}
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
            
            # Добавляем стопы
            if stop_loss:
                params["stopLoss"] = str(stop_loss)
            if take_profit:
                params["takeProfit"] = str(take_profit)
            
            # Добавляем reduce_only
            if reduce_only:
                params["reduceOnly"] = True
            
            # Добавляем position_idx
            if position_idx is not None:
                params["positionIdx"] = position_idx
            
            self.logger.info(f"🎯 Создаем ордер: {symbol} {side} {order_type} {qty}")
            
            # Создаем ордер через официальную библиотеку
            response = self.session.place_order(**params)
            
            if response.get('retCode') == 0:
                self.logger.info(f"✅ Ордер создан: {response['result']}")
            else:
                self.logger.error(f"❌ Ошибка создания ордера: {response}")
            
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
            
            response = self.session.set_trading_stop(**params)
            
            if response.get('retCode') == 0:
                self.logger.info("✅ Стопы установлены успешно")
            else:
                self.logger.error(f"❌ Ошибка установки стопов: {response}")
            
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
            params = {
                "category": "linear",
                "accountType": "UNIFIED"
            }
            
            if symbol:
                params["symbol"] = symbol
            
            response = self.session.get_positions(**params)
            
            if response.get('retCode') == 0:
                self.logger.info("✅ Позиции получены успешно")
            else:
                self.logger.error(f"❌ Ошибка получения позиций: {response}")
            
            return response
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения позиций: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    def get_ohlcv(self, symbol: str = "BTCUSDT", interval: str = "1", limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Получение OHLCV данных (v5 API)
        
        Args:
            symbol: Торговый инструмент
            interval: Интервал (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, M, W)
            limit: Количество свечей
            
        Returns:
            DataFrame с OHLCV данными
        """
        try:
            # Конвертируем интервал в формат Bybit
            interval_map = {
                "1": "1", "3": "3", "5": "5", "15": "15", "30": "30",
                "60": "60", "120": "120", "240": "240", "360": "360", "720": "720",
                "D": "D", "M": "M", "W": "W"
            }
            
            bybit_interval = interval_map.get(interval, interval)
            
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=bybit_interval,
                limit=limit
            )
            
            if response.get('retCode') == 0:
                # Конвертируем в DataFrame
                data = response['result']['list']
                df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                
                # Конвертируем типы данных
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Конвертируем timestamp
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
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
            response = self.session.cancel_all_orders(
                category="linear",
                symbol=symbol
            )
            
            if response.get('retCode') == 0:
                self.logger.info(f"✅ Все ордера отменены: {symbol}")
            else:
                self.logger.error(f"❌ Ошибка отмены ордеров: {response}")
            
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
            params = {
                "category": "linear",
                "accountType": "UNIFIED"
            }
            
            if symbol:
                params["symbol"] = symbol
            
            response = self.session.get_open_orders(**params)
            
            if response.get('retCode') == 0:
                self.logger.info("✅ Открытые ордера получены успешно")
            else:
                self.logger.error(f"❌ Ошибка получения открытых ордеров: {response}")
            
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
            response = self.session.get_server_time()
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
            params = {"category": category}
            if symbol:
                params["symbol"] = symbol
                
            response = self.session.get_instruments_info(**params)
            
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