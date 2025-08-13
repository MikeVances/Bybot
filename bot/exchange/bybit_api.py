import requests
import time
import hmac
import hashlib
import pandas as pd
import logging
from config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_API_URL
import os
import asyncio
import json
from websockets import connect
import csv
from datetime import datetime
from .endpoints import Position, Trade, Account, Market

# Настройка логгирования - убрано дублирование, основная настройка в main.py
# logging.basicConfig(filename='bot.log', level=logging.INFO, 
#                    format='%(asctime)s - %(levelname)s - %(message)s')

class BybitAPI:
    def __init__(self):
        self.base_url = BYBIT_API_URL
        self.api_key = BYBIT_API_KEY
        self.api_secret = BYBIT_API_SECRET
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Улучшенное логирование: отдельный логгер для BybitAPI
        log_dir = 'data/logs'
        os.makedirs(log_dir, exist_ok=True)
        self.logger = logging.getLogger('bybit_api')
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler(os.path.join(log_dir, 'bybit_api.log'))
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        if not self.logger.hasHandlers():
            self.logger.addHandler(handler)
        self._log_handler = handler  # Сохраняем для закрытия

        # Таймауты и ретраи
        self.timeout = 10  # секунд
        self.max_retries = 3

    def close_logger(self):
        """Явно закрыть файловый обработчик логгера (для тестов и завершения работы)."""
        if hasattr(self, '_log_handler'):
            self._log_handler.close()
            self.logger.removeHandler(self._log_handler)

    def _sign_request(self, params):
        param_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(self.api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()

    def _send_request(self, method, endpoint, params=None):
        params = params or {}
        params["api_key"] = self.api_key
        params["timestamp"] = str(int(time.time() * 1000))
        params["sign"] = self._sign_request(params)
        
        for attempt in range(self.max_retries):
            try:
                # Универсальный запрос с поддержкой таймаута
                response = self.session.request(
                    method,
                    self.base_url + endpoint,
                    params=params if method == "GET" else None,
                    json=params if method == "POST" else None,
                    timeout=self.timeout
                )
                response.raise_for_status()
                self.logger.info(f"Request to {endpoint} successful (attempt {attempt+1})")
                return response.json()
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout (attempt {attempt + 1}/{self.max_retries}) for {endpoint}")
                if attempt == self.max_retries - 1:
                    self.logger.error(f"Max retries reached for {endpoint} (timeout)")
                    return None
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Error in {endpoint} (attempt {attempt+1}): {str(e)}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(1)

    def get_wallet_balance_v5(self):
        return self._send_request("GET", Account.GET_WALLET_BALANCE, {"accountType": "UNIFIED"})        

    def format_balance_v5(self, balance_data):
        if not balance_data or balance_data.get('retCode') != 0:
            return "Ошибка получения баланса"

        result = balance_data['result']['list'][0]
        coins = "\n".join(
            f"{coin['coin']}: {coin['walletBalance']} (${coin['usdValue']})"
            for coin in result['coin']
        )
        return f"""Общий баланс: ${result['totalEquity']}
Доступно: ${result['totalAvailableBalance']}
Монеты:
{coins}"""
        

    def create_order(self, symbol, side, order_type, qty, price=None, stop_loss=None, take_profit=None, reduce_only=False, position_idx=None):
        """
        Размещает ордер на Bybit.
        :param symbol: Тикер (например, BTCUSDT)
        :param side: Buy или Sell
        :param order_type: Market или Limit
        :param qty: Количество
        :param price: Цена (для лимитных ордеров)
        :param stop_loss: Цена стоп-лосс (опционально)
        :param take_profit: Цена тейк-профит (опционально)
        :param reduce_only: Только для закрытия позиции (bool)
        :return: Ответ API при успехе, None при ошибке
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "accountType": "UNIFIED"
        }
        if order_type == "Limit":
            params["price"] = str(price)
        if reduce_only:
            params["reduceOnly"] = True
        if position_idx is not None:
            params["positionIdx"] = position_idx
            
        # Создаем ордер без SL/TP для избежания ошибок форматирования
        try:
            response = self._send_request("POST", Trade.PLACE_ORDER, params)
            print(f"Order response: {response}")  # Для отладки
            
            if response and response.get('retCode') == 0:
                self.logger.info(f"Order created: {response['result']}")
                
                # Если ордер создан успешно и нужно установить SL/TP, делаем это отдельно
                if (stop_loss is not None or take_profit is not None) and not reduce_only:
                    # Ждем и проверяем, что позиция действительно открылась
                    import time
                    max_attempts = 5
                    for attempt in range(max_attempts):
                        time.sleep(2)  # Увеличиваем задержку до 2 секунд
                        
                        # Проверяем, что позиция открылась
                        positions = self.get_positions(symbol)
                        if positions and positions.get('result') and positions['result'].get('list'):
                            for pos in positions['result']['list']:
                                if float(pos.get('size', 0)) > 0:
                                    self.logger.info(f"Position confirmed, setting SL/TP (attempt {attempt + 1})")
                                    
                                    # Устанавливаем SL/TP через отдельный запрос
                                    sl_tp_response = self.set_trading_stop(
                                        symbol=symbol,
                                        stop_loss=stop_loss,
                                        take_profit=take_profit
                                    )
                                    
                                    if sl_tp_response:
                                        self.logger.info(f"SL/TP set successfully: {sl_tp_response['result']}")
                                    else:
                                        self.logger.warning("Failed to set SL/TP, but order was created")
                                    break
                            else:
                                if attempt < max_attempts - 1:
                                    self.logger.info(f"Position not yet opened, waiting... (attempt {attempt + 1})")
                                    continue
                                else:
                                    self.logger.error("Position not opened after all attempts")
                                    break
                        else:
                            if attempt < max_attempts - 1:
                                self.logger.info(f"Could not get positions, waiting... (attempt {attempt + 1})")
                                continue
                            else:
                                self.logger.error("Could not get positions after all attempts")
                                break
                
                return response
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
                print(f"Order error: {error_msg}")  # Для отладки
                self.logger.error(f"Order failed: {error_msg}")
                return None
        except Exception as e:
            print(f"Order exception: {str(e)}")  # Для отладки
            self.logger.error(f"Order exception: {str(e)}")
            return None

    def cancel_all_orders(self, symbol):
        return self._send_request("POST", Trade.CANCEL_ALL_ORDERS, {
            "category": "linear",
            "symbol": symbol,
            "accountType": "UNIFIED"
        })

    def set_leverage(self, symbol, buy_leverage=1, sell_leverage=1):
        """
        Устанавливает плечо для деривативов (USDT-фьючерсы) на Bybit.
        :param symbol: Тикер (например, BTCUSDT)
        :param buy_leverage: Плечо для лонга (int или str)
        :param sell_leverage: Плечо для шорта (int или str)
        :return: Ответ API
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "buyLeverage": str(buy_leverage),
            "sellLeverage": str(sell_leverage),
            "accountType": "UNIFIED"
        }
        return self._send_request("POST", Position.SET_LEVERAGE, params)

    def get_positions(self, symbol=None):
        """
        Получение текущих позиций по всем инструментам или по конкретному symbol.
        :param symbol: Тикер (например, BTCUSDT) или None для всех позиций
        :return: Ответ API (dict) или None при ошибке
        """
        params = {
            "category": "linear",
            "accountType": "UNIFIED"
        }
        if symbol:
            params["symbol"] = symbol
        response = self._send_request("GET", Position.GET_POSITIONS, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Positions fetched: {response['result']}")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Get positions failed: {error_msg}")
            return None

    def log_trade(self, symbol, side, qty, entry_price, exit_price, pnl, stop_loss, take_profit, strategy, comment=""):
        """
        Записывает информацию о сделке в trades.csv (дневник трейдера).
        Если файл пустой — добавляет заголовки.
        """
        file_path = 'data/trades.csv'
        write_header = False
        try:
            with open(file_path, 'r') as f:
                if not f.read(1):
                    write_header = True
        except FileNotFoundError:
            write_header = True
        with open(file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow([
                    'datetime','symbol','side','qty','entry_price','exit_price','pnl','stop_loss','take_profit','strategy','comment'
                ])
            writer.writerow([
                datetime.now().isoformat(),
                symbol,
                side,
                qty,
                entry_price,
                exit_price,
                pnl,
                stop_loss,
                take_profit,
                strategy,
                comment
            ])

    def log_strategy_signal(self, strategy, symbol, signal, market_data, indicators, comment=""):
        """
        Записывает информацию о сигнале стратегии в strategy_signals.csv для ML/аналитики.
        Если файл пустой — добавляет заголовки.
        """
        file_path = 'data/strategy_signals.csv'
        write_header = False
        try:
            with open(file_path, 'r') as f:
                if not f.read(1):
                    write_header = True
        except FileNotFoundError:
            write_header = True
        with open(file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow([
                    'datetime', 'strategy', 'symbol', 'signal', 'market_data', 'indicators', 'comment'
                ])
            writer.writerow([
                datetime.now().isoformat(),
                strategy,
                symbol,
                signal,
                str(market_data),
                str(indicators),
                comment
            ])

    def set_trading_stop(self, symbol, stop_loss=None, take_profit=None, sl_trigger_by="MarkPrice", tp_trigger_by="MarkPrice"):
        """
        Устанавливает стоп-лосс и/или тейк-профит для открытой позиции.
        :param symbol: Тикер (например, BTCUSDT)
        :param stop_loss: Цена стоп-лосса (опционально)
        :param take_profit: Цена тейк-профита (опционально)
        :param sl_trigger_by: Триггер для SL (LastPrice или MarkPrice)
        :param tp_trigger_by: Триггер для TP (LastPrice или MarkPrice)
        :return: Ответ API (dict) или None при ошибке
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "accountType": "UNIFIED"
        }
        
        # Проверяем и форматируем цены
        if stop_loss is not None:
            try:
                stop_loss_float = float(stop_loss)
                # Для BTCUSDT используем 1 знак после запятой, для других - 2
                if symbol == "BTCUSDT":
                    params["stopLoss"] = f"{stop_loss_float:.1f}"
                else:
                    params["stopLoss"] = f"{stop_loss_float:.2f}"
                params["slTriggerBy"] = sl_trigger_by
                self.logger.info(f"Setting stop loss: {params['stopLoss']} (trigger: {sl_trigger_by})")
            except (ValueError, TypeError) as e:
                self.logger.error(f"Invalid stop loss value: {stop_loss}, error: {e}")
                return None
            
        if take_profit is not None:
            try:
                take_profit_float = float(take_profit)
                # Для BTCUSDT используем 1 знак после запятой, для других - 2
                if symbol == "BTCUSDT":
                    params["takeProfit"] = f"{take_profit_float:.1f}"
                else:
                    params["takeProfit"] = f"{take_profit_float:.2f}"
                params["tpTriggerBy"] = tp_trigger_by
                self.logger.info(f"Setting take profit: {params['takeProfit']} (trigger: {tp_trigger_by})")
            except (ValueError, TypeError) as e:
                self.logger.error(f"Invalid take profit value: {take_profit}, error: {e}")
                return None
            
        if not params.get("stopLoss") and not params.get("takeProfit"):
            self.logger.warning("No stop loss or take profit provided")
            return None
            
        response = self._send_request("POST", Position.SET_TRADING_STOP, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Trading stop set successfully: {response['result']}")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Set trading stop failed: {error_msg}")
            return None

    def close_position(self, symbol, current_side):
        """
        Универсальное закрытие позиции для Bybit (UNIFIED и обычные аккаунты).
        :param symbol: Тикер (например, BTCUSDT)
        :param current_side: Текущая сторона позиции ('Buy' или 'Sell')
        :return: Ответ API (dict) или None при ошибке
        """
        # Получаем информацию о позиции
        positions = self.get_positions(symbol)
        if not positions or not positions.get('result') or not positions['result'].get('list'):
            self.logger.error(f"Не удалось получить позицию для {symbol}")
            return None
        pos = None
        for p in positions['result']['list']:
            if float(p.get('size', 0)) > 0:
                pos = p
                break
        if not pos:
            self.logger.info(f"Нет открытой позиции для {symbol}")
            return None
        size = pos.get('size')
        if not size or float(size) == 0:
            self.logger.info(f"Позиция уже закрыта для {symbol}")
            return None
        # Определяем противоположную сторону
        close_side = 'Buy' if current_side == 'Sell' else 'Sell'
        # Для UNIFIED аккаунта нужен positionIdx=0
        position_idx = pos.get('positionIdx', 0)
        # Отправляем Market-ордер на закрытие
        result = self.create_order(
            symbol=symbol,
            side=close_side,
            order_type="Market",
            qty=str(size),
            reduce_only=True,
            position_idx=position_idx
        )
        if result and result.get('retCode') == 0:
            self.logger.info(f"Позиция {symbol} успешно закрыта: {result}")
        else:
            self.logger.error(f"Ошибка при закрытии позиции {symbol}: {result}")
        return result

    def get_server_time(self):
        """
        Получение времени сервера Bybit.
        :return: Ответ API с временем сервера или None при ошибке
        """
        response = self._send_request("GET", Market.GET_SERVER_TIME, {})
        if response and response.get('retCode') == 0:
            self.logger.info(f"Server time: {response['result']}")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Get server time failed: {error_msg}")
            return None

    def get_funding_rate_history(self, symbol, limit=100):
        """
        Получение истории ставок финансирования.
        :param symbol: Тикер (например, BTCUSDT)
        :param limit: Количество записей (максимум 200)
        :return: Ответ API или None при ошибке
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "limit": limit
        }
        response = self._send_request("GET", Market.GET_FUNDING_RATE_HISTORY, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Funding rate history fetched: {len(response['result']['list'])} records")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Get funding rate history failed: {error_msg}")
            return None

    def get_open_interest(self, symbol, period="1h", limit=200):
        """
        Получение открытого интереса.
        :param symbol: Тикер (например, BTCUSDT)
        :param period: Период (1h, 4h, 1d, 1w, 1m)
        :param limit: Количество записей (максимум 200)
        :return: Ответ API или None при ошибке
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "period": period,
            "limit": limit
        }
        response = self._send_request("GET", Market.GET_OPEN_INTEREST, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Open interest fetched: {len(response['result']['list'])} records")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Get open interest failed: {error_msg}")
            return None

    def get_long_short_ratio(self, symbol, period="1h", limit=200):
        """
        Получение соотношения лонг/шорт.
        :param symbol: Тикер (например, BTCUSDT)
        :param period: Период (1h, 4h, 1d, 1w, 1m)
        :param limit: Количество записей (максимум 200)
        :return: Ответ API или None при ошибке
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "period": period,
            "limit": limit
        }
        response = self._send_request("GET", Market.GET_LONG_SHORT_RATIO, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Long/short ratio fetched: {len(response['result']['list'])} records")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Get long/short ratio failed: {error_msg}")
            return None

    def amend_order(self, symbol, order_id, price=None, qty=None, take_profit=None, stop_loss=None):
        """
        Изменение существующего ордера.
        :param symbol: Тикер (например, BTCUSDT)
        :param order_id: ID ордера для изменения
        :param price: Новая цена (для лимитных ордеров)
        :param qty: Новое количество
        :param take_profit: Новая цена тейк-профита
        :param stop_loss: Новая цена стоп-лосса
        :return: Ответ API или None при ошибке
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id,
            "accountType": "UNIFIED"
        }
        
        if price is not None:
            params["price"] = str(price)
        if qty is not None:
            params["qty"] = str(qty)
        if take_profit is not None:
            params["takeProfit"] = f"{float(take_profit):.2f}"
        if stop_loss is not None:
            params["stopLoss"] = f"{float(stop_loss):.2f}"
            
        response = self._send_request("POST", Trade.AMEND_ORDER, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Order amended: {response['result']}")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Amend order failed: {error_msg}")
            return None

    def get_open_orders(self, symbol=None, category="linear"):
        """
        Получение активных ордеров.
        :param symbol: Тикер (опционально, для фильтрации)
        :param category: Категория (linear, inverse, spot, option)
        :return: Ответ API или None при ошибке
        """
        params = {
            "category": category,
            "accountType": "UNIFIED"
        }
        if symbol:
            params["symbol"] = symbol
            
        response = self._send_request("GET", Trade.GET_OPEN_ORDERS, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Open orders fetched: {len(response['result']['list'])} orders")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Get open orders failed: {error_msg}")
            return None

    def batch_place_orders(self, orders_list):
        """
        Пакетное создание ордеров.
        :param orders_list: Список словарей с параметрами ордеров
        :return: Ответ API или None при ошибке
        """
        params = {
            "category": "linear",
            "accountType": "UNIFIED",
            "request": orders_list
        }
        
        response = self._send_request("POST", Trade.BATCH_PLACE_ORDER, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Batch orders placed: {response['result']}")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Batch place orders failed: {error_msg}")
            return None

    def get_instruments_info(self, category="linear", symbol=None):
        """
        Получение информации об инструментах.
        :param category: Категория (linear, inverse, spot, option)
        :param symbol: Тикер (опционально, для фильтрации)
        :return: Ответ API или None при ошибке
        """
        params = {
            "category": category
        }
        if symbol:
            params["symbol"] = symbol
            
        response = self._send_request("GET", Market.GET_INSTRUMENTS_INFO, params)
        if response and response.get('retCode') == 0:
            self.logger.info(f"Instruments info fetched: {len(response['result']['list'])} instruments")
            return response
        else:
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            self.logger.error(f"Get instruments info failed: {error_msg}")
            return None

    async def listen_ws(self, callback, symbol="BTCUSDT", channel="orderbook.40"):
        """
        WebSocket подключение для получения рыночных данных Bybit.
        :param callback: функция, вызываемая при получении новых данных (на вход — dict)
        :param symbol: торговый инструмент (например, BTCUSDT)
        :param channel: канал подписки (например, orderbook.40, trade, kline.1)
        """
        ws_url = "wss://stream.bybit.com/v5/public/linear"
        sub_msg = json.dumps({
            "op": "subscribe",
            "args": [f"{channel}.{symbol}"]
        })
        while True:
            try:
                async with connect(ws_url) as ws:
                    await ws.send(sub_msg)
                    self.logger.info(f"WebSocket subscribed to {channel}.{symbol}")
                    while True:
                        data = await ws.recv()
                        callback(json.loads(data))
            except Exception as e:
                self.logger.error(f"WebSocket error: {str(e)}. Reconnecting in 5s...")
                await asyncio.sleep(5)

# Пример использования:
# api = BybitAPI()
# api.set_leverage("BTCUSDT", buy_leverage=1, sell_leverage=1)
    

class TradingBot(BybitAPI):
    def __init__(self, symbol="BTCUSDT", api_key=None, api_secret=None, uid=None):
        # Если переданы API ключи, используем их, иначе используем дефолтные
        if api_key and api_secret:
            self.base_url = BYBIT_API_URL
            self.api_key = api_key
            self.api_secret = api_secret
            self.session = requests.Session()
            self.session.headers.update({"Content-Type": "application/json"})
            
            # Улучшенное логирование: отдельный логгер для BybitAPI
            log_dir = 'data/logs'
            os.makedirs(log_dir, exist_ok=True)
            self.logger = logging.getLogger('bybit_api')
            self.logger.setLevel(logging.INFO)
            handler = logging.FileHandler(os.path.join(log_dir, 'bybit_api.log'))
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            if not self.logger.hasHandlers():
                self.logger.addHandler(handler)
            self._log_handler = handler  # Сохраняем для закрытия
            
            # Таймауты и ретраи
            self.timeout = 10  # секунд
            self.max_retries = 3
        else:
            # Используем дефолтные ключи
            super().__init__()
        
        self.symbol = symbol
        self.position_size = 0.0
        self.entry_price = 0.0
        self.position_side = None  # 'Buy', 'Sell' или None
        # OHLCV для Bybit v5: 7 столбцов
        self.df_columns = ["timestamp", "open", "high", "low", "close", "volume", "turnover"]
    
    def get_ohlcv(self, interval="1", limit=100):
        data = self._send_request("GET", Market.GET_KLINE, {
            "category": "linear",
            "symbol": self.symbol,
            "interval": interval,
            "limit": limit
        })
        if data and "result" in data:
            return pd.DataFrame(data["result"]["list"], columns=self.df_columns)
        return pd.DataFrame(columns=self.df_columns)
    
    def check_sma_signal(self, window_short=20, window_long=50):
        df = self.get_ohlcv()
        if df.empty:
            return None
            
        df["close"] = df["close"].astype(float)
        df["sma_short"] = df["close"].rolling(window_short).mean()
        df["sma_long"] = df["close"].rolling(window_long).mean()
        
        last_close = df["close"].iloc[-1]
        if df["sma_short"].iloc[-1] > df["sma_long"].iloc[-1] and last_close > df["sma_short"].iloc[-1]:
            return "BUY"
        elif df["sma_short"].iloc[-1] < df["sma_long"].iloc[-1] and last_close < df["sma_short"].iloc[-1]:
            return "SELL"
        return None

    def update_position_info(self):
        """
        Обновляет информацию о текущей позиции по инструменту.
        Сохраняет размер позиции, цену входа и сторону ('Buy'/'Sell') в атрибутах объекта.
        Если позиции нет — сбрасывает значения и пишет в лог.
        """
        positions = self.get_positions(self.symbol)
        if positions and positions.get('result') and positions['result'].get('list') and positions['result']['list']:
            pos = positions['result']['list'][0]
            self.position_size = float(pos.get('size', 0))
            self.entry_price = float(pos.get('avgPrice', 0))
            self.position_side = pos.get('side')
            self.logger.info(f"Position updated: size={self.position_size}, entry={self.entry_price}, side={self.position_side}")
        else:
            self.position_size = 0.0
            self.entry_price = 0.0
            self.position_side = None
            self.logger.info("No open position for this symbol.")

    def execute_strategy(self, risk_percent=0.01):
        signal = self.check_sma_signal()
        if not signal:
            return
            
        balance_data = self.get_wallet_balance_v5()
        if not balance_data or "result" not in balance_data:
            self.logger.warning("Failed to get balance data")
            return
            
        available_balance = float(balance_data["result"]["list"][0]["totalAvailableBalance"])
        qty = available_balance * risk_percent
        
        self.logger.info(f"Executing {signal} signal with {qty} USDT")
        self.create_order(self.symbol, signal, "Market", qty)

    def log_signal(self, strategy_name, signal_type, market_data, indicators=None, comment=""):
        """
        Логирование сигналов стратегий для анализа и отладки.
        :param strategy_name: Название стратегии
        :param signal_type: Тип сигнала (BUY, SELL, EXIT)
        :param market_data: Рыночные данные
        :param indicators: Индикаторы (опционально)
        :param comment: Комментарий (опционально)
        """
        try:
            self.log_strategy_signal(
                strategy=strategy_name,
                symbol=self.symbol,
                signal=signal_type,
                market_data=market_data,
                indicators=indicators or {},
                comment=comment
            )
            self.logger.info(f"Signal logged: {strategy_name} - {signal_type}")
        except Exception as e:
            self.logger.error(f"Ошибка логирования: {str(e)}")

if __name__ == "__main__":
    bot = TradingBot()
    
    while True:
        try:
            bot.execute_strategy()
            time.sleep(60)
        except KeyboardInterrupt:
            bot.logger.info("Bot stopped by user")
            break
        except Exception as e:
            bot.logger.error(f"Main loop error: {str(e)}")
            time.sleep(10)