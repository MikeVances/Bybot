# 🔧 Конфигурация API и Окружения

## 📍 Централизованные настройки

Все настройки API и окружения находятся в **одном месте**: `config.py`

⚠️ **ВАЖНО: НЕ ДУБЛИРУЙТЕ НАСТРОЙКИ В ДРУГИХ ФАЙЛАХ!**

## 🎛️ Основные настройки

### `USE_TESTNET`
- `True` - Работа на тестовой сети (безопасно, виртуальные деньги)
- `False` - Работа на основной сети (реальные деньги!)

### `USE_V5_API`
- `True` - Использование API v5 (рекомендуется)
- `False` - Старый API (не рекомендуется)

## 🌐 Автоматические URL

Система автоматически выбирает правильные URL на основе настроек:

**Testnet:**
- API: `https://api-testnet.bybit.com`
- WebSocket: `wss://stream-testnet.bybit.com`

**Mainnet:**
- API: `https://api.bybit.com`
- WebSocket: `wss://stream.bybit.com`

## 📋 Как изменить настройки

1. Откройте `config.py`
2. Найдите секцию `# НАСТРОЙКИ API И ОКРУЖЕНИЯ`
3. Измените нужные параметры:
   ```python
   USE_TESTNET = True   # Для testnet
   USE_TESTNET = False  # Для mainnet
   ```
4. Перезапустите систему

## ✅ Валидация

При запуске система автоматически:
- Проверяет настройки
- Логирует текущую конфигурацию
- Показывает предупреждения

Пример вывода:
```
🔧 API Конфигурация: 🧪 TESTNET | API: v5
🌐 Base URL: https://api-testnet.bybit.com
🔌 WebSocket: wss://stream-testnet.bybit.com
```

## 🚨 Предупреждения безопасности

- **TESTNET** (🧪) - Безопасно, виртуальные деньги
- **MAINNET** (💰) - ⚠️ РЕАЛЬНЫЕ ДЕНЬГИ В ОПАСНОСТИ!

## 🔍 Функции для кода

```python
from config import get_api_config, validate_api_config

# Получить текущую конфигурацию
config = get_api_config()
print(config['environment'])  # 'testnet' или 'mainnet'
print(config['base_url'])     # Текущий API URL

# Валидировать настройки
validate_api_config()
```

## 📁 Файлы использующие настройки

- `bot/exchange/bybit_api_v5.py`
- `bot/exchange/api_adapter.py`
- `bot/services/telegram_bot.py`
- `bot/core/trader.py`
- `bot/core/trader_orchestrator.py`

⚠️ **НЕ МЕНЯЙТЕ настройки в этих файлах! Только в `config.py`!**