# Миграция на Bybit API v5

## Обзор

Этот документ описывает процесс миграции с собственной реализации Bybit API на официальную библиотеку `pybit` версии 5.11.0.

## Преимущества API v5

### 🚀 Официальная поддержка
- **Официальная библиотека Bybit**: `pybit` поддерживается самой Bybit
- **Автоматические обновления**: API всегда актуальный
- **Надежность**: Протестированная и стабильная библиотека

### 🔧 Улучшенная функциональность
- **Лучшая обработка ошибок**: Подробные сообщения об ошибках
- **Поддержка всех функций v5**: Полный доступ к новым возможностям
- **WebSocket поддержка**: Встроенная поддержка WebSocket соединений
- **Типизация**: Лучшая поддержка типов данных

### 📊 Расширенные возможности
- **Unified Trading Account**: Полная поддержка UTA
- **Новые типы ордеров**: Поддержка всех типов ордеров v5
- **Улучшенная аутентификация**: Более безопасная система ключей
- **Rate Limiting**: Встроенная защита от превышения лимитов

## Структура файлов

```
bot/exchange/
├── bybit_api.py          # Старая реализация (v4)
├── bybit_api_v5.py       # Новая реализация (v5)
└── api_adapter.py        # Адаптер для миграции
```

## Новые классы

### BybitAPIV5
Основной класс для работы с Bybit API v5:

```python
from bot.exchange.bybit_api_v5 import BybitAPIV5

# Создание экземпляра
api = BybitAPIV5(
    api_key="your_api_key",
    api_secret="your_api_secret",
    testnet=False  # True для тестовой сети
)

# Основные методы
balance = api.get_wallet_balance_v5()
positions = api.get_positions("BTCUSDT")
ohlcv = api.get_ohlcv("BTCUSDT", "1", 100)
order = api.create_order("BTCUSDT", "Buy", "Market", 0.001)
```

### TradingBotV5
Расширенная версия торгового бота:

```python
from bot.exchange.bybit_api_v5 import TradingBotV5

# Создание торгового бота
bot = TradingBotV5(
    symbol="BTCUSDT",
    api_key="your_api_key",
    api_secret="your_api_secret",
    testnet=False
)

# Обновление информации о позиции
bot.update_position_info()
print(f"Position size: {bot.position_size}")
print(f"Entry price: {bot.entry_price}")
```

## Адаптер для миграции

### APIAdapter
Позволяет переключаться между старым и новым API:

```python
from bot.exchange.api_adapter import create_api_adapter

# Использование нового API v5
api_v5 = create_api_adapter(use_v5=True, testnet=True)

# Использование старого API v4
api_v4 = create_api_adapter(use_v5=False)

# Тестирование миграции
from bot.exchange.api_adapter import migrate_to_v5_api
result = migrate_to_v5_api()
print(result)
```

### TradingBotAdapter
Адаптер для торгового бота:

```python
from bot.exchange.api_adapter import create_trading_bot_adapter

# Создание адаптера
bot = create_trading_bot_adapter(
    symbol="BTCUSDT",
    use_v5=True,
    testnet=True
)

# Использование как обычного бота
bot.update_position_info()
data = bot.get_ohlcv("1", 100)
```

## Пошаговая миграция

### Шаг 1: Установка pybit
```bash
source /home/mikevance/bots/venv/bin/activate
pip install pybit
```

### Шаг 2: Тестирование API v5
```python
from bot.exchange.api_adapter import migrate_to_v5_api

result = migrate_to_v5_api()
if result['v5_api_available']:
    print("✅ API v5 готов к использованию")
else:
    print("❌ Проблемы с API v5:", result['error'])
```

### Шаг 3: Обновление конфигурации
В файле конфигурации стратегии добавьте:

```python
# Использование нового API v5
USE_V5_API = True
TESTNET = False  # True для тестирования

# В функции создания API клиента
from bot.exchange.api_adapter import create_trading_bot_adapter

strategy_apis[strategy_name] = create_trading_bot_adapter(
    symbol="BTCUSDT",
    api_key=config['api_key'],
    api_secret=config['api_secret'],
    uid=config.get('uid'),
    use_v5=USE_V5_API,
    testnet=TESTNET
)
```

### Шаг 4: Обновление трейдера
В `bot/core/trader.py` замените создание API клиентов:

```python
# Старый код
strategy_apis[strategy_name] = TradingBot(
    symbol="BTCUSDT",
    api_key=config['api_key'],
    api_secret=config['api_secret'],
    uid=config.get('uid')
)

# Новый код
from bot.exchange.api_adapter import create_trading_bot_adapter

strategy_apis[strategy_name] = create_trading_bot_adapter(
    symbol="BTCUSDT",
    api_key=config['api_key'],
    api_secret=config['api_secret'],
    uid=config.get('uid'),
    use_v5=True,  # Используем новый API
    testnet=False
)
```

## Основные изменения в API

### Создание ордеров
```python
# Старый API
order = api.create_order(
    symbol="BTCUSDT",
    side="Buy",
    order_type="Market",
    qty=0.001,
    stop_loss=50000,
    take_profit=52000
)

# Новый API v5 (тот же интерфейс)
order = api.create_order(
    symbol="BTCUSDT",
    side="Buy",
    order_type="Market",
    qty=0.001,
    stop_loss=50000,
    take_profit=52000
)
```

### Получение данных
```python
# Старый API
balance = api.get_wallet_balance_v5()
positions = api.get_positions("BTCUSDT")
ohlcv = api.get_ohlcv("1", 100)

# Новый API v5 (тот же интерфейс)
balance = api.get_wallet_balance_v5()
positions = api.get_positions("BTCUSDT")
ohlcv = api.get_ohlcv("BTCUSDT", "1", 100)
```

## Обработка ошибок

### Новые типы ошибок
```python
try:
    response = api.create_order(...)
    if response.get('retCode') == 0:
        print("✅ Ордер создан успешно")
    else:
        print(f"❌ Ошибка: {response.get('retMsg')}")
except Exception as e:
    print(f"❌ Исключение: {e}")
```

### Коды ошибок v5
- `10001`: Неверный параметр
- `10002`: Неверный API ключ
- `10003`: Неверная подпись
- `10004`: Превышен лимит запросов
- `10005`: Неверный timestamp

## Тестирование

### Тест подключения
```python
from bot.exchange.bybit_api_v5 import create_bybit_api_v5

api = create_bybit_api_v5(testnet=True)
server_time = api.get_server_time()
print(f"Время сервера: {server_time}")
```

### Тест получения данных
```python
# Получение OHLCV данных (работает без API ключей)
ohlcv = api.get_ohlcv("BTCUSDT", "1", 10)
if ohlcv is not None:
    print(f"Получено {len(ohlcv)} свечей")
    print(f"Последняя цена: {ohlcv['close'].iloc[-1]}")
```

### Тест создания ордера (требует API ключи)
```python
# Только с реальными API ключами
order = api.create_order(
    symbol="BTCUSDT",
    side="Buy",
    order_type="Market",
    qty=0.001
)
print(f"Результат: {order}")
```

## Рекомендации по миграции

### 1. Постепенная миграция
- Начните с тестовой сети (testnet=True)
- Протестируйте все функции
- Переходите на основную сеть только после полного тестирования

### 2. Мониторинг
- Внимательно следите за логами
- Проверяйте все ответы API
- Отслеживайте ошибки и их причины

### 3. Резервное копирование
- Сохраните старую реализацию API
- Используйте адаптер для быстрого переключения
- Подготовьте план отката

### 4. Обновление документации
- Обновите все примеры кода
- Добавьте информацию о новых возможностях
- Создайте руководство по устранению неполадок

## Проблемы и решения

### Ошибка 401 (Unauthorized)
**Причина**: Неверные API ключи или их отсутствие
**Решение**: Проверьте правильность ключей в конфигурации

### Ошибка 429 (Rate Limit)
**Причина**: Превышен лимит запросов
**Решение**: Добавьте задержки между запросами

### Ошибка 10001 (Invalid Parameter)
**Причина**: Неверные параметры запроса
**Решение**: Проверьте формат и значения параметров

### Проблемы с WebSocket
**Причина**: Неправильная настройка WebSocket соединения
**Решение**: Используйте официальные WebSocket методы из pybit

## Заключение

Миграция на Bybit API v5 предоставляет:
- ✅ Официальную поддержку Bybit
- ✅ Лучшую надежность и стабильность
- ✅ Расширенные возможности
- ✅ Улучшенную обработку ошибок
- ✅ Автоматические обновления

Рекомендуется выполнить миграцию в ближайшее время для получения всех преимуществ нового API. 