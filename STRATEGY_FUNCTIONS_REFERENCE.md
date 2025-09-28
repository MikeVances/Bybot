# Справочник функций создания стратегий v3.0

## 📋 Обратная совместимость - основные функции

Эти функции обеспечивают совместимость со старым кодом:

```python
# Volume VWAP Strategy
from bot.strategy.implementations.volume_vwap_strategy_v3 import create_volume_vwap_strategy

# CumDelta Support/Resistance Strategy
from bot.strategy.implementations.cumdelta_sr_strategy_v3 import create_cumdelta_sr_strategy

# Multi-Timeframe Volume Strategy
from bot.strategy.implementations.multitf_volume_strategy_v3 import create_multitf_volume_strategy

# Fibonacci RSI Strategy
from bot.strategy.implementations.fibonacci_rsi_strategy_v3 import create_fibonacci_rsi_strategy

# Range Trading Strategy
from bot.strategy.implementations.range_trading_strategy_v3 import create_range_trading_strategy
```

## 🏭 Унифицированные фабричные методы v3

Все стратегии v3 поддерживают стандартные фабричные методы:

```python
# Основной метод создания
StrategyClass.create_strategy(**kwargs)

# Стандартные пресеты
StrategyClass.create_preset('conservative', **kwargs)
StrategyClass.create_preset('aggressive', **kwargs)
StrategyClass.create_preset('balanced', **kwargs)

# Список доступных пресетов
StrategyClass.list_presets()
```

## 🎯 Volume VWAP Strategy v3

```python
from bot.strategy.implementations.volume_vwap_strategy_v3 import (
    VolumeVWAPStrategyV3,
    create_volume_vwap_strategy,
    create_vwap_crypto_volatile,
    create_vwap_crypto_stable,
    create_vwap_forex,
    create_vwap_scalping
)

# Стандартные фабрики
VolumeVWAPStrategyV3.create_strategy()
VolumeVWAPStrategyV3.create_conservative()
VolumeVWAPStrategyV3.create_aggressive()
VolumeVWAPStrategyV3.create_balanced()

# Кастомные пресеты
VolumeVWAPStrategyV3.create_preset('crypto_volatile')
VolumeVWAPStrategyV3.create_preset('crypto_stable')
VolumeVWAPStrategyV3.create_preset('forex')
VolumeVWAPStrategyV3.create_preset('scalping')
```

## 📊 CumDelta Support/Resistance Strategy v3

```python
from bot.strategy.implementations.cumdelta_sr_strategy_v3 import (
    CumDeltaSRStrategyV3,
    create_cumdelta_sr_strategy,
    create_cumdelta_scalping,
    create_cumdelta_swing,
    create_cumdelta_institutional
)

# Стандартные фабрики
CumDeltaSRStrategyV3.create_strategy()
CumDeltaSRStrategyV3.create_conservative()
CumDeltaSRStrategyV3.create_aggressive()
CumDeltaSRStrategyV3.create_balanced()

# Кастомные пресеты
CumDeltaSRStrategyV3.create_preset('scalping')
CumDeltaSRStrategyV3.create_preset('swing')
CumDeltaSRStrategyV3.create_preset('institutional')
```

## 📈 Multi-Timeframe Volume Strategy v3

```python
from bot.strategy.implementations.multitf_volume_strategy_v3 import (
    MultiTFVolumeStrategyV3,
    create_multitf_volume_strategy,
    create_multitf_conservative,
    create_multitf_aggressive,
    create_multitf_scalping
)

# Стандартные фабрики
MultiTFVolumeStrategyV3.create_strategy()
MultiTFVolumeStrategyV3.create_conservative()
MultiTFVolumeStrategyV3.create_aggressive()
MultiTFVolumeStrategyV3.create_balanced()

# Кастомные пресеты
MultiTFVolumeStrategyV3.create_preset('conservative')
MultiTFVolumeStrategyV3.create_preset('aggressive')
MultiTFVolumeStrategyV3.create_preset('scalping')
```

## 🌊 Fibonacci RSI Strategy v3

```python
from bot.strategy.implementations.fibonacci_rsi_strategy_v3 import (
    FibonacciRSIStrategyV3,
    create_fibonacci_rsi_strategy,
    create_fib_scalping,
    create_fib_swing,
    create_fib_crypto
)

# Стандартные фабрики
FibonacciRSIStrategyV3.create_strategy()
FibonacciRSIStrategyV3.create_conservative()
FibonacciRSIStrategyV3.create_aggressive()
FibonacciRSIStrategyV3.create_balanced()

# Кастомные пресеты
FibonacciRSIStrategyV3.create_preset('fibonacci_scalping')
FibonacciRSIStrategyV3.create_preset('fibonacci_swing')
FibonacciRSIStrategyV3.create_preset('fibonacci_crypto')
```

## 📦 Range Trading Strategy v3

```python
from bot.strategy.implementations.range_trading_strategy_v3 import (
    RangeTradingStrategyV3,
    create_range_trading_strategy,
    create_range_tight,
    create_range_wide,
    create_range_crypto,
    create_range_forex
)

# Стандартные фабрики
RangeTradingStrategyV3.create_strategy()
RangeTradingStrategyV3.create_conservative()
RangeTradingStrategyV3.create_aggressive()
RangeTradingStrategyV3.create_balanced()

# Кастомные пресеты
RangeTradingStrategyV3.create_preset('tight_range')
RangeTradingStrategyV3.create_preset('wide_range')
RangeTradingStrategyV3.create_preset('crypto_range')
RangeTradingStrategyV3.create_preset('forex_range')
```

## 🔄 Миграция с v2 на v3

### Старый код (v2):
```python
from bot.strategy.implementations.volume_vwap_strategy import create_volume_vwap_strategy
strategy = create_volume_vwap_strategy(config)
```

### Новый код (v3):
```python
# Опция 1: Использовать ту же функцию (автоматическая совместимость)
from bot.strategy.implementations.volume_vwap_strategy_v3 import create_volume_vwap_strategy
strategy = create_volume_vwap_strategy(config)

# Опция 2: Использовать новый API
from bot.strategy.implementations.volume_vwap_strategy_v3 import VolumeVWAPStrategyV3
strategy = VolumeVWAPStrategyV3.create_strategy(config)

# Опция 3: Использовать пресеты
strategy = VolumeVWAPStrategyV3.create_preset('conservative', **config_overrides)
```

## 🚀 Новые возможности v3

### 1. Унифицированные миксины:
- `TrailingStopMixin` - продвинутый trailing stop
- `MarketRegimeMixin` - анализ рыночных режимов
- `StrategyFactoryMixin` - автоматические фабрики
- `DebugLoggingMixin` - унифицированное логирование

### 2. Автоматические пресеты:
- conservative, aggressive, balanced
- Кастомные пресеты для каждой стратегии

### 3. Улучшенная архитектура:
- Pipeline система для обработки данных
- Централизованная логика выходов
- Стандартизированные конфигурации

## 📝 Примеры использования

```python
# Создание стратегии с настройками по умолчанию
strategy = VolumeVWAPStrategyV3.create_strategy()

# Создание консервативной стратегии
strategy = VolumeVWAPStrategyV3.create_conservative()

# Создание с кастомными параметрами
strategy = VolumeVWAPStrategyV3.create_preset('crypto_volatile',
                                            volume_multiplier=5.0,
                                            risk_reward_ratio=2.0)

# Получение списка доступных пресетов
presets = VolumeVWAPStrategyV3.list_presets()
print(f"Доступные пресеты: {presets}")

# Получение информации о стратегии
info = strategy.get_strategy_info()
print(f"Стратегия: {info['strategy_name']} v{info['version']}")
```

## ⚙️ Настройки стратегий и уровни агрессивности

### 📊 Сравнение уровней агрессивности

| Параметр | Conservative | **Default** | Aggressive |
|----------|--------------|-------------|------------|
| Risk/Reward Ratio | 2.0 | **1.5** | 1.2 |
| Signal Strength | 0.7 | **0.6** | 0.5 |
| Торговая частота | Низкая | **Средняя** | Высокая |
| Безопасность | Высокая | **Средняя** | Низкая |

### 🎯 Текущие активные стратегии (по умолчанию):

- `volume_vwap_default` - **сбалансированные** настройки
- `cumdelta_sr_default` - **сбалансированные** настройки
- `multitf_volume_default` - **сбалансированные** настройки
- `volume_vwap_conservative` - 🛡️ **консервативные** настройки
- `fibonacci_rsi_default` - **сбалансированные** настройки
- `range_trading_default` - **сбалансированные** настройки

> ✅ **Вывод**: Система по умолчанию использует СБАЛАНСИРОВАННЫЕ настройки (золотая середина), а НЕ агрессивные!

### 🔧 Как изменить уровень агрессивности:

1. **Для более агрессивной торговли** - в `main.py` замените:
   ```python
   # Было
   create_volume_vwap_strategy()
   # Стало
   create_aggressive_volume_vwap()
   ```

2. **Для более консервативной торговли**:
   ```python
   # Было
   create_volume_vwap_strategy()
   # Стало
   create_conservative_volume_vwap()
   ```

3. **Использование специальных пресетов**:
   ```python
   VolumeVWAPStrategyV3.create_preset('scalping')      # Максимально агрессивно
   VolumeVWAPStrategyV3.create_preset('crypto_stable') # Максимально консервативно
   ```

## 🌐 Настройки API подключения

По умолчанию система использует **реалистичные пороги** для API статуса:

| Статус API | Время отклика | Действие |
|-----------|---------------|----------|
| 🟢 HEALTHY | < 1.0 сек | Нормальная работа |
| 🟡 DEGRADED | 1.0 - 3.0 сек | Торговля с осторожностью |
| 🔴 UNSTABLE | > 3.0 сек | Ограничения торговли |

> ✅ **Исправлено**: Убраны ложные предупреждения "API DEGRADED" при нормальном времени отклика 0.3-0.5 сек

## ⚠️ Важные изменения

1. **Обратная совместимость**: Все старые функции `create_*_strategy()` работают без изменений
2. **Новые конфигурации**: Добавлены новые поля в конфигурациях (с значениями по умолчанию)
3. **Улучшенная производительность**: Благодаря устранению дублирования кода
4. **Лучшее тестирование**: Миксины легче тестировать в изоляции
5. **Гибкие настройки**: Простое переключение между уровнями агрессивности
6. **Оптимизированные пороги API**: Реалистичные пороги для определения качества соединения

---
*Обновлено: v3.0.0 - Полный рефакторинг с устранением дублирования + документация настроек*