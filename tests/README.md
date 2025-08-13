# Тесты проекта ByBot

## 📁 Структура тестов

### 🧪 Стратегии
- `test_multitf_strategy.py` - Тест MultiTF Volume стратегии
- `test_cumdelta_strategy.py` - Тест CumDelta Support/Resistance стратегии  
- `test_fibonacci_rsi_strategy.py` - Тест Fibonacci RSI Volume стратегии

### 🔧 Интеграционные тесты
- `integration_test.py` - Полная интеграция системы
- `test_full_trade_cycle.py` - Полный торговый цикл
- `test_core.py` - Тест основных компонентов

### 🌐 API тесты
- `test_endpoints.py` - Тест API endpoints
- `test_order_placement.py` - Тест размещения ордеров
- `test_demo_bybit.py` - Тест демо Bybit API

## 🚀 Запуск тестов

```bash
# Тест конкретной стратегии
python tests/test_fibonacci_rsi_strategy.py

# Тест всех стратегий
python tests/test_multitf_strategy.py
python tests/test_cumdelta_strategy.py

# Интеграционный тест
python tests/integration_test.py
```

## ✅ Статус тестов

- **MultiTF Strategy**: ✅ Работает
- **CumDelta Strategy**: ✅ Работает  
- **Fibonacci RSI Strategy**: ✅ Работает (7/8 тестов)
- **Integration Tests**: ✅ Работают

## 📝 Примечания

- Все тесты используют мок-данные для изоляции
- Тесты стратегий проверяют создание, конфигурацию и выполнение
- Интеграционные тесты проверяют полную работу системы 