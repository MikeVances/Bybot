# 🤖 Bybot - Advanced Crypto Trading System

**Статус:** ✅ Production Ready (Testing Phase)
**Последнее обновление:** 2025-10-05
**API:** Bybit v5 (Testnet/Mainnet)

## 📋 Описание

Bybot - автоматизированная торговая система для криптовалютного рынка с интеграцией нейронных сетей, институциональной рыночной аналитикой и продвинутым риск-менеджментом.

### 🎯 Ключевые возможности

- ✅ **6 активных торговых стратегий** с Market Context Engine
- ✅ **Neural Trader** - AI-based прогнозирование
- ✅ **Session-aware stops** - адаптация к Asian/London/NY сессиям
- ✅ **Liquidity-based targets** - институциональные уровни ликвидности
- ✅ **Dynamic R/R** - адаптивные Risk/Reward по market regime
- ✅ **USDT-based sizing** - позиционирование в USD (не BTC)
- ✅ **Advanced risk management** - глобальные лимиты и защита капитала

### 🚀 Быстрый старт

```bash
# 1. Настройка окружения
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Настройка API ключей
export BYBOT_API_KEY_PATH=/path/to/your/bot_api.key

# 3. Запуск системы
python main.py
```

### ⚙️ Конфигурация

**Основной конфиг:** `/home/mikevance/secrets/bot2_api.key`

**Критические параметры:**
```bash
# Торговые настройки
SYMBOL=BTCUSDT
TRADE_AMOUNT=100.0          # Размер позиции в USDT ($100)

# Риск-менеджмент
MAX_DAILY_TRADES=30
MAX_OPEN_POSITIONS=5
MAX_DAILY_LOSS_PCT=5.0
MAX_POSITION_SIZE_PCT=15.0  # 15% баланса на позицию
MIN_RISK_REWARD_RATIO=1.2
```

**API настройки:**
- `USE_TESTNET=True` (по умолчанию) - песочница Bybit
- `USE_V5_API=True` - всегда используем Bybit API v5

### 📊 Активные стратегии

1. **Volume VWAP** - основная, объем + VWAP confluence
2. **Volume VWAP Conservative** - консервативная версия
3. **CumDelta SR** - кумулятивная дельта + поддержка/сопротивление
4. **MultiTF Volume** - multi-timeframe анализ объема
5. **Fibonacci RSI** - Фибоначчи уровни + RSI
6. **Range Trading** - торговля в диапазоне (sideways markets)

**Управление стратегиями:**
```bash
# Активные стратегии хранятся в:
bot/strategy/active_strategies.txt

# Добавить/убрать стратегию:
echo "volume_vwap_default" >> bot/strategy/active_strategies.txt
```

### 🛠 Режимы запуска

```bash
# Полная система (рекомендуется)
python main.py

# Только торговые стратегии
python -m bot.core.trader

# Только Telegram бот
python run_enhanced_telegram_bot.py

# Системный сервис
sudo systemctl start bybot-trading.service
sudo systemctl status bybot-trading.service
```

### 🤖 Telegram управление

**Команды после запуска:**
- `/start` - Главное меню
- `/dashboard` - Панель управления
- `/market_context` - Анализ рынка real-time
- `/quick` - Быстрые действия

### 📈 Мониторинг

```bash
# Логи торговли (новый формат с fresh start)
tail -f full_system.log

# Системные логи
sudo journalctl -u bybot-trading.service -f

# Мониторинг нейромодуля
python scripts/monitor_neural.py

# Производительность стратегий
python scripts/monitor_performance.py
```

### ⚙️ Уровни агрессивности

**По умолчанию: BALANCED (сбалансированный)**

| Уровень | Risk/Reward | Signal Strength | Частота сделок |
|---------|------------|-----------------|----------------|
| Conservative | 2.0 | 0.7 | Низкая |
| **Default** | **1.5** | **0.6** | **Средняя** |
| Aggressive | 1.2 | 0.5 | Высокая |

См. `STRATEGY_FUNCTIONS_REFERENCE.md` для детальной настройки.

### 🔒 Безопасность

- ✅ Balance validator - защита от недостаточного баланса
- ✅ Position size limits - максимум 15% баланса на позицию
- ✅ Daily loss limits - остановка при 5% дневных потерь
- ✅ Emergency stop conditions - критический уровень баланса
- ✅ API resilience - retry, backoff, failover

### 📚 Документация

- `START_GUIDE.md` - Подробное руководство по запуску
- `BACKLOG.md` - Roadmap и история разработки
- `STRATEGY_FUNCTIONS_REFERENCE.md` - Справочник стратегий
- `MARKET_CONTEXT_ENGINE_SUMMARY.md` - Market Context архитектура
- `NEURAL_MONITORING_GUIDE.md` - Мониторинг нейромодуля

### 🚨 Важные изменения (2025-10-05)

**Критические исправления:**
1. ✅ Trade amount теперь в USDT (не BTC)
2. ✅ USD → BTC автоконвертация для Bybit API
3. ✅ Исправлен balance validator (удален hardcoded price)
4. ✅ Обновлены position size limits (2% → 15%)
5. ✅ Market Context интегрирован во ВСЕ стратегии
6. ✅ Проект очищен для production (удалены test файлы)

**Ожидаемые изменения в логах:**
```
💰 Позиция: $100.00 USDT = 0.0017 BTC
✅ Проверка баланса пройдена. Доступно: 1762.33, требуется: 110.00
✅ Позиция opened: BTCUSDT BUY 0.0017 @ 60000
```

### 🎯 Production Checklist

- [x] API v5 интеграция
- [x] USDT-based position sizing
- [x] Balance validation исправлен
- [x] Market Context во всех стратегиях
- [x] Логи очищены (fresh start)
- [x] Тестовые файлы удалены
- [ ] Первые сделки (мониторинг)
- [ ] 24h статистика
- [ ] Win rate verification

**🎉 СИСТЕМА ГОТОВА К PRODUCTION ТЕСТИРОВАНИЮ! 🎉**
