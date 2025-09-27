# 🚀 BYBOT - Руководство по запуску

## Быстрый старт

### 1. 🎯 Основные скрипты запуска

```bash
# Интерактивный запуск с меню
./start_bybot.sh

# Прямой запуск компонентов
python main.py                      # Полная система
python run_enhanced_telegram_bot.py # Только Telegram бот
python -m bot.core.trader           # Только торговые стратегии
```

### 2. 📋 Режимы работы

#### Режим 1: Только Telegram бот 🤖
```bash
python run_enhanced_telegram_bot.py
```
- Современный интерфейс с UX
- Команды: /start, /dashboard, /quick
- Интеграция с торговыми стратегиями

#### Режим 2: Только торговые стратегии 📊
```bash
python -m bot.core.trader
```
- 6 активных стратегий
- Neural Trader с AI
- Автоматический риск-менеджмент

#### Режим 3: Полная система 🚀
```bash
python main.py
```
- Торговля + Telegram бот
- Полный мониторинг
- Централизованное управление

### 3. 🧪 Тестирование

```bash
# Тест всех стратегий
python ../test_all_strategies.py

# Статус системы
./start_bybot.sh  # выбор 2

# Тест отправки уведомления в Telegram
python send_test_message.py

# Тест нейронной сети
python -c "from bot.ai.neural_trader import NeuralTrader; print('Neural OK')"
```

### 4. 🛠 Системные сервисы

```bash
# Статус сервисов
sudo systemctl status bybot-trading.service
sudo systemctl status bybot-telegram.service

# Запуск сервисов
sudo systemctl start bybot-trading.service

# Перезапуск
./restart_bybot_services.sh
```

### 5. 📊 Мониторинг

#### Проверка балансов
```bash
python -c "
from bot.exchange.bybit_api_v5 import TradingBotV5
from config import get_strategy_config
config = get_strategy_config('volume_vwap_default')
api = TradingBotV5('BTCUSDT', config['api_key'], config['api_secret'], config['uid'])
balance = api.get_wallet_balance_v5()
print('Balance:', balance['result']['list'][0]['coin'][0]['walletBalance'])
"
```

#### Проверка стратегий
```bash
python -c "
from bot.core.trader import get_active_strategies
print('Active strategies:', get_active_strategies())
"
```

### 6. 🤖 Telegram команды

После запуска бота доступны команды:

- `/start` - Главное меню
- `/dashboard` - Панель управления
- `/quick` - Быстрые действия
- Интерактивные кнопки для всех операций

### 7. ⚙️ Конфигурация

Основные настройки в `config.py`:
- API ключи Bybit
- Telegram токен и admin ID
- Настройки стратегий
- Параметры риск-менеджмента

### 8. 📝 Логи

```bash
# Логи торговли
tail -f trading_bot.log

# Логи Telegram бота
tail -f telegram_bot.log

# Системные логи
journalctl -f -u bybot-trading.service
```

### 9. 🚨 Экстренные команды

```bash
# Остановить все
./start_bybot.sh  # выбор 4

# Принудительная остановка
pkill -f "python.*main.py"
pkill -f "python.*telegram_bot"

# Проверка процессов
ps aux | grep python | grep bybot
```

### 10. ✅ Статус системы

Все компоненты протестированы и готовы:
- ✅ 6 торговых стратегий активны
- ✅ Neural Trader с методом predict()
- ✅ API v5 подключение работает
- ✅ Telegram бот настроен
- ✅ Все зависимости установлены
- ✅ Balance validator активен

**🎉 СИСТЕМА ГОТОВА К РАБОТЕ! 🎉**
