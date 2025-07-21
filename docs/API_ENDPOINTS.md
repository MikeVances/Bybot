# Bybit API Endpoints - Перечисления

Этот документ описывает использование перечислений эндпоинтов Bybit API v5 в проекте BYBOT.

## Структура

Перечисления находятся в файле `bot/exchange/endpoints.py` и включают:

- `Position` - эндпоинты для работы с позициями
- `Order` - эндпоинты для работы с ордерами  
- `Account` - эндпоинты для работы с аккаунтом
- `Market` - эндпоинты для получения рыночных данных

## Использование

### Импорт

```python
from bot.exchange.endpoints import Position, Trade, Account, Market
```

### Примеры использования

#### Создание ордера
```python
from bot.exchange.bybit_api import BybitAPI

api = BybitAPI()
response = api._send_request("POST", Trade.PLACE_ORDER, {
    "category": "linear",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": "0.001"
})
```

#### Получение позиций
```python
positions = api._send_request("GET", Position.GET_POSITIONS, {
    "category": "linear",
    "accountType": "UNIFIED"
})
```

#### Установка плеча
```python
leverage_response = api._send_request("POST", Position.SET_LEVERAGE, {
    "category": "linear",
    "symbol": "BTCUSDT",
    "buyLeverage": "1",
    "sellLeverage": "1",
    "accountType": "UNIFIED"
})
```

#### Установка стоп-лосса и тейк-профита
```python
sl_tp_response = api._send_request("POST", Position.SET_TRADING_STOP, {
    "category": "linear",
    "symbol": "BTCUSDT",
    "stopLoss": "117520.60",
    "takeProfit": "117550.60",
    "slTriggerBy": "LastPrice",
    "tpTriggerBy": "LastPrice",
    "accountType": "UNIFIED"
})
```

#### Получение баланса
```python
balance = api._send_request("GET", Account.GET_WALLET_BALANCE, {
    "accountType": "UNIFIED"
})
```

#### Получение OHLCV данных
```python
ohlcv = api._send_request("GET", Market.GET_KLINE, {
    "category": "linear",
    "symbol": "BTCUSDT",
    "interval": "1",
    "limit": 100
})
```

## Преимущества использования перечислений

1. **Типобезопасность** - IDE может проверять правильность использования эндпоинтов
2. **Автодополнение** - IDE может предлагать доступные эндпоинты
3. **Централизованное управление** - все эндпоинты в одном месте
4. **Легкость рефакторинга** - изменение эндпоинта в одном месте
5. **Документация** - эндпоинты самодокументируемы

## Доступные эндпоинты

### Position
- `GET_POSITIONS` - получение списка позиций
- `SET_LEVERAGE` - установка плеча
- `SWITCH_MARGIN_MODE` - переключение режима маржи
- `SET_TP_SL_MODE` - установка режима TP/SL
- `SWITCH_POSITION_MODE` - переключение режима позиции
- `SET_RISK_LIMIT` - установка лимита риска
- `SET_TRADING_STOP` - установка стоп-лосса/тейк-профита
- `SET_AUTO_ADD_MARGIN` - установка автодобавления маржи
- `ADD_MARGIN` - добавление маржи
- `GET_EXECUTIONS` - получение исполнений
- `GET_CLOSED_PNL` - получение закрытого PnL

### Trade
- `PLACE_ORDER` - создание ордера
- `AMEND_ORDER` - изменение ордера
- `CANCEL_ORDER` - отмена ордера
- `GET_OPEN_ORDERS` - получение активных ордеров
- `CANCEL_ALL_ORDERS` - отмена всех ордеров
- `GET_ORDER_HISTORY` - получение истории ордеров
- `BATCH_PLACE_ORDER` - пакетное создание ордеров
- `BATCH_AMEND_ORDER` - пакетное изменение ордеров
- `BATCH_CANCEL_ORDER` - пакетная отмена ордеров
- `GET_BORROW_QUOTA` - получение квоты займа (спот)
- `SET_DCP` - установка отключенной отмены всех ордеров

### Account
- `GET_WALLET_BALANCE` - получение баланса кошелька
- `GET_ACCOUNT_INFO` - получение информации об аккаунте
- `GET_COLLATERAL_INFO` - получение информации о залоге
- `GET_ACCOUNT_RATIO` - получение соотношения аккаунта

### Market
- `GET_SERVER_TIME` - получение времени сервера
- `GET_KLINE` - получение свечей
- `GET_MARK_PRICE_KLINE` - получение свечей маркировочной цены
- `GET_INDEX_PRICE_KLINE` - получение свечей индексной цены
- `GET_PREMIUM_INDEX_PRICE_KLINE` - получение свечей премиум индексной цены
- `GET_INSTRUMENTS_INFO` - получение информации об инструментах
- `GET_ORDERBOOK` - получение стакана
- `GET_TICKERS` - получение тикеров
- `GET_FUNDING_RATE_HISTORY` - получение истории ставок финансирования
- `GET_PUBLIC_TRADING_HISTORY` - получение публичной истории торгов
- `GET_OPEN_INTEREST` - получение открытого интереса
- `GET_HISTORICAL_VOLATILITY` - получение исторической волатильности
- `GET_INSURANCE` - получение страховки
- `GET_RISK_LIMIT` - получение лимитов риска
- `GET_OPTION_DELIVERY_PRICE` - получение цены поставки опционов
- `GET_LONG_SHORT_RATIO` - получение соотношения лонг/шорт

## Новые методы в BybitAPI

### set_trading_stop()
Новый метод для установки стоп-лосса и тейк-профита через отдельный запрос:

```python
# Установка только стоп-лосса
api.set_trading_stop("BTCUSDT", stop_loss=117520.60)

# Установка только тейк-профита
api.set_trading_stop("BTCUSDT", take_profit=117550.60)

# Установка обоих
api.set_trading_stop("BTCUSDT", stop_loss=117520.60, take_profit=117550.60)
```

Этот метод решает проблемы с форматированием цен при создании ордера и позволяет устанавливать SL/TP после открытия позиции. 