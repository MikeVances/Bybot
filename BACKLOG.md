# 📋 BYBOT DEVELOPMENT BACKLOG

**Дата создания:** 2025-09-21
**Последнее обновление:** 2025-09-23
**Статус:** Active Development Roadmap
**Система:** Stabilization Phase (pre-production)

---

## 🚨 **БЛОК Б: ВАЖНЫЕ ПРОБЛЕМЫ НАДЕЖНОСТИ**
*Приоритет: HIGH - для полного production-ready статуса*

### 🔄 Текущие приоритеты (сентябрь 2025)
**Что уже сделано:** фундамент для стабильности
- `TradingBotAdapter` и логика OrderManager подняты до v5 API, добавлены queue/ретраи для команд.
- Конфигурация приведена к единому формату: schema-driven настройки и секреты не дублируются по слоям.
- Все стратегии переведены на модульную архитектуру (индикаторы → сигнал → позиционирование).
- Метрики и heartbeat выведены в отдельный сервис; пайплайн обрабатывает деградацию, кэш и переключение эндпоинтов.
- Телеграм-бот теперь исполняет команды только для `ADMIN_CHAT_ID` и используется как безопасный интерфейс наблюдения.
- Появились журналы сигналов (`signals_log.csv`) и снапшоты свечей для аналитики и обратного анализа.

**Что остаётся сделать (ключ к prod-ready) — в порядке приоритета**
1. **API resiliency & alerting**
   - Завершить алёртинг деградации (Б4.2.2): связать heartbeat, Telegram и runbook, документировать действия.
   - Добавить автоматическую реакцию на `FAILED`: safe-mode, запись в blocking-alerts, уведомления.

2. **Test Harness на реальных данных**
   - Собрать набор зафиксированных ответов песочного API (баланс, позиции, свечи) и прогонять регрессионные проверки.
   - Стартовать CI, который гоняет unit/contract тесты и регрессию на записанных данных.

3. **Нейромодуль → shadow MVP**
   - Ввести офлайн датасет: снапшоты, сигналы, результаты → отдельный pipeline.
   - Добавить shadow-режим: сбор рекомендаций без реальных ордеров, логирование метрик.
   - Запретить автообучение в бою до появления контролируемого процесса.

4. **Наблюдаемость и операционка**
   - Поднять structured JSON-логи и correlation-id.
   - Экспортировать метрики в Prometheus, собрать дашборд (API, стратегии, нейромодуль).
   - Реализовать health/readiness endpoints, описать деплой+rollback (blue/green), настроить секреты.

5. **Data lifecycle & retention**
   - Политика хранения: снепшоты свечей, trade_journal, AI модели → retention/backups.
   - Централизованный writer для CSV/JSON, мониторинг размера и алерты на дрейф данных.

6. **Security/compliance**
   - Интегрировать Secret Manager, убрать plaintext `.key` файлы.
   - Строгая валидация конфигов (pydantic/jsonschema), статический аудит.

7. **Testing (Б4.7)**
   - Переписать unit-тесты с моками адаптера/API.
   - Контрактные тесты для ордер-менеджера, риск-менеджера и стратегий.
   - Регрессионка на детерминированных данных перед релизом.

**Очередь следующая:**
- [ ] Запустить CI-пайплайн: unit/contract tests, песочный Bybit/записанные ответы, регрессионные проверки.
- [ ] Стандартизовать логирование (JSON, correlation-id) и метрики Prometheus.
- [ ] Подготовить health/readiness endpoints и описанный процесс деплоя (blue/green, секреты, smoke tests).

### **Б1: DATA QUALITY PROTECTION**
**Цель:** Защита от corrupted данных и API сбоев

#### Б1.1: Усиленная входная валидация ⭐⭐⭐
```python
def validate_market_data_safety(df):
    # Критические проверки
    if df.empty:
        return False, "Empty DataFrame - API failure"
    if df['volume'].sum() == 0:
        return False, "Zero volume detected - fake data"
    if (df['close'] == df['open']).all():
        return False, "Flat prices - market halt or bad data"
    if df['close'].isna().any():
        return False, "NaN prices detected"
    return True, "Data OK"
```

#### Б1.2: Stale data detection ⭐⭐⭐
```python
# Проверка актуальности данных
last_timestamp = df.index[-1]
if (datetime.now() - last_timestamp) > timedelta(minutes=5):
    return None  # Не торгуем на старых данных
```

#### Б1.3: Graceful degradation ⭐⭐
```python
def execute_with_fallback(self, market_data):
    try:
        return self.full_strategy_execution(market_data)
    except DataQualityError:
        return self.simplified_execution(market_data)  # Базовые сигналы
    except Exception:
        return None  # Безопасная остановка
```

### **Б2: ERROR RECOVERY MECHANISMS**
**Цель:** Автоматическое восстановление после сбоев

#### Б2.1: Circuit breaker для стратегий ⭐⭐⭐
```python
class StrategyCircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=300):
        # После 5 ошибок подряд - отключить на 5 минут
```

#### Б2.2: Auto-recovery procedures ⭐⭐
- Автоматический restart стратегий после таймаута
- Переключение на backup data sources
- Degraded mode для критических ситуаций

#### Б2.3: Hierarchical error handling ⭐⭐
```python
# Уровень 1: Strategy level - пропустить итерацию
# Уровень 2: Symbol level - отключить стратегию на символе
# Уровень 3: System level - emergency stop
```

### **Б3: API FAILURE RESILIENCE**
**Цель:** Устойчивость к сбоям API Bybit

#### Б3.1: Enhanced connection management ⭐⭐⭐
```python
# Реконнекция с exponential backoff
# Heartbeat проверки каждые 30 секунд
# Fallback на cached data при недоступности API
```

#### Б3.2: Rate limiting protection ⭐⭐
```python
# Встроенная защита от превышения лимитов
# Adaptive delays при приближении к лимитам
# Приоритизация критических запросов
```

#### Б3.3: Multiple API endpoints ⭐
- Backup API endpoints для критических запросов
- Load balancing между доступными endpoints
- Failover mechanisms

### **Б4: ARCHITECTURE & OPERATIONS HARDENING**
**Цель:** Свести технический долг к нулю и вывести систему на production-grade уровень

#### Б4.1: Core Architecture ⭐⭐⭐
- [x] Вынести создание ордеров из per-symbol lock: очередь/воркер, идемпотентные retry, контроль таймаутов.
- [x] Разделить стратегии на модули (индикаторы → сигнал → позиционирование) и ввести контракт между слоями (RangeTrading v1 как эталон).
- [x] Устранить дублирующий запуск TelegramBot: выделить единый сервис уведомлений и исключить повторное создание event loop в `run_trading_with_risk_management`.
- [ ] Добавить горячее управление стратегиями: динамическое включение/выключение пресетов, reload конфигурации без рестарта.

#### Б4.2: Resilience & Network ⭐⭐⭐
- [x] Реализовать экспоненциальный backoff, кеш и failover endpoint для Bybit API при `NameResolutionError` и таймаутах (enhanced_api_connection + _call_api).
- [ ] Поднять алерты по деградации канала (DNS, rate limit, баланс = 0) с классификацией по приоритетам.

#### Б4.3: Observability ⭐⭐
- [ ] Перевести логи на JSON-формат без emoji, добавить correlation-id, уровни серьёзности и структуру событий.
- [ ] Экспортировать ключевые метрики (latency стратегий, баланс, ошибки API) в Prometheus + построить Grafana dashboard.
- [x] Привести metrics экспорт в соответствие prod-требованиям: единая точка запуска, устойчивый HTTP сервис, без хардкода путей и с тестами на сбои.

#### Б4.4: Operations & Deployment ⭐⭐
- [ ] Реализовать health/readiness endpoints, автоматический graceful shutdown и self-check при старте.
- [ ] Описать и автоматизировать деплой (blue/green или canary), подготовить runbook и процедуры rollback.
- [ ] Заменить `systemctl restart` скрипт на управляемый пайплайн (CI/CD + секреты, миграции, smoke-тест).
- [x] Синхронизировать стартовые скрипты/документацию с фактическим кодом (`quick_start.sh`, `test_telegram_simple.py`, порты метрик) и исключить команды, требующие `sudo` в продуктивной сборке.

#### Б4.5: Security & Compliance ⭐⭐
- [ ] Интегрировать менеджер секретов (Vault/SM) и убрать plaintext `.key` файлы, обеспечить rotation.
- [ ] Сделать валидацию конфигурации строгой: падать при placeholder-ключах, ввести schema enforcement (pydantic/jsonschema) и статический аудит.

#### Б4.6: Data Lifecycle ⭐
- [ ] Ввести политику retention/backups для `data/logs`, `trade_journal.csv`, AI сохранений; автоматический контроль целостности.
- [ ] Упорядочить работу с CSV/JSON: централизованный writer, атомарные обновления, мониторинг размера и алерты на дрейф.

#### Б4.7: Testing & Simulation ⭐⭐⭐
- [ ] Переписать unit-тесты с рабочими моками адаптера/API и прогоном в CI.
- [ ] Построить контрактные тесты для ордер-менеджера, risk-менеджмента и стратегии (happy path + edge cases).
- [ ] Покрыть критические сценарии регрессионными прогонами на детерминированных данных перед релизом.
- [x] Убрать тесты, дергающие реальный Bybit (`tests/test_full_trade_cycle.py`, `tests/test_order_placement.py`), заменить на изолированные сценарии с моками/фикстурами и защитой токенов.

### 🚀 **PRODUCTION READINESS MILESTONES**
- [ ] **M1 – Stabilize Core & Resilience:** закрыть Б4.1 критические задачи + Б4.2 целиком, внедрить hot strategy control и устойчивость API.
- [ ] **M2 – Observability & Test Harness:** выполнить Б4.3 и Б4.7, включить structured логи, метрики и автоматизированные тестовые прогоны в CI.
- [ ] **M3 – Operations, Security & Data:** завершить Б4.4, Б4.5, Б4.6; задокументировать runbook, настроить деплой/retention, интегрировать secret manager.

---

## 🟢 **БЛОК В: УЛУЧШЕНИЯ И ОПТИМИЗАЦИЯ**
*Приоритет: MEDIUM - качество жизни разработчиков*

### **В1: CODE QUALITY IMPROVEMENTS**

#### В1.1: Унификация стратегий ⭐⭐
- Создание базового template для новых стратегий
- Устранение дублирующегося кода между MultiTF и VolumeVWAP
- Единая система валидации для всех стратегий

#### В1.2: Strategy Factory ⭐⭐
```python
class StrategyFactory:
    @staticmethod
    def create_strategy(strategy_type: str, config: Dict) -> BaseStrategy:
        # Единая точка создания всех стратегий
```

#### В1.3: API стандартизация ⭐
- Унифицированные параметры конфигурации
- Стандартизация названий методов
- Common interfaces для всех компонентов

### **В2: MONITORING ENHANCEMENTS**

#### В2.1: Real-time performance dashboards ⭐⭐⭐
- Live латентность каждой стратегии
- Memory usage графики
- TTL cache hit/miss rates
- Confluence factors distribution

#### В2.2: Alert systems ⭐⭐
```python
class PerformanceMonitor:
    def check_performance_alerts(self):
        if strategy_latency > 50:  # ms
            self.send_alert("LATENCY_WARNING", strategy_name)
        if memory_usage > 800:  # MB
            self.send_alert("MEMORY_WARNING")
```

#### В2.3: Detailed logging ⭐
- Structured logging с JSON format
- Correlation IDs для tracking
- Performance metrics в каждом log entry

### **В3: DOCUMENTATION & MAINTENANCE**

#### В3.1: Technical documentation ⭐
- Architecture diagrams
- API documentation
- Configuration guide

#### В3.2: Code cleanup ⭐
- Remove dead code
- Consistent naming conventions
- Type hints для всех functions

#### В3.3: Unit tests ⭐⭐
- Tests для критических functions
- Performance benchmarks
- Integration tests

---

## 📊 **БЛОК Г: РАСШИРЕННЫЕ ВОЗМОЖНОСТИ**
*Приоритет: LOW - новые фичи после стабилизации*

### **Г1: ADVANCED ANALYTICS**

#### Г1.1: Real-time метрики ⭐⭐
- Performance dashboard
- Strategy comparison metrics
- Market regime detection

#### Г1.2: Advanced backtesting ⭐⭐
- Historical performance с оптимизациями
- A/B testing разных confluence settings
- Monte Carlo симуляции

#### Г1.3: Confluence analytics ⭐
- Визуализация 3 ключевых факторов
- Correlation analysis между факторами
- Predictive indicators

### **Г2: TRADING ENHANCEMENTS**

#### Г2.1: Multi-asset support ⭐⭐⭐
- ETH, SOL, другие топ криптопары
- Cross-asset арбитражные возможности
- Unified portfolio management

#### Г2.2: Dynamic position sizing ⭐⭐
```python
def calculate_position_size(confluence_score: float, account_balance: float):
    # Position size на основе confluence score (0.1-1.0)
    # Risk allocation по силе сигнала
```

#### Г2.3: Portfolio rebalancing ⭐
- Автоматическое распределение капитала
- Performance-based allocation
- Risk parity implementation

### **Г3: AI/ML ENHANCEMENTS**

#### Г3.1: Neural Network 2.0 ⭐⭐
- Переобучение на новых 3-факторных данных
- Интеграция с batch processing
- Specialized models для каждой стратегии

#### Г3.2: Reinforcement Learning ⭐
- RL агент для динамической оптимизации
- Adaptive strategy selection
- Market regime aware trading

#### Г3.3: Predictive Analytics ⭐
- Market regime prediction
- Volume spike forecasting
- Optimal entry timing

---

## 🎯 **ПРИОРИТЕТНАЯ МАТРИЦА**

### **🔥 КРИТИЧНО (следующие 2-4 недели):**
1. **Б1.1-Б1.2**: Data quality protection
2. **Б2.1**: Circuit breaker implementation
3. **Б3.1**: Enhanced API resilience
4. **В2.1**: Basic monitoring dashboard

### **📈 ВАЖНО (1-2 месяца):**
5. **Г2.1**: Multi-asset trading
6. **В1.1-В1.2**: Code quality improvements
7. **Г1.2**: Advanced backtesting
8. **Б2.2-Б2.3**: Full error recovery

### **💡 ЖЕЛАТЕЛЬНО (3+ месяцев):**
9. **Г3.1-Г3.2**: AI/ML enhancements
10. **Г2.2-Г2.3**: Advanced trading features
11. **В3.1-В3.3**: Documentation & tests
12. **Г1.3**: Advanced analytics

---

## 📋 **ИСПОЛЬЗОВАНИЕ BACKLOG**

### **Добавление новых задач:**
```markdown
#### Новая задача ⭐⭐⭐
**Описание:** Что нужно сделать
**Приоритет:** ⭐⭐⭐ (1-3 звезды)
**Блок:** Б/В/Г
**Estimated effort:** Small/Medium/Large
```

### **Статусы задач:**
- ❌ **Not Started** - задача в backlog
- 🟡 **In Progress** - работа начата
- ✅ **Completed** - задача завершена
- 🔒 **Blocked** - заблокирована другими задачами

### **Обновление приоритетов:**
Пересматривать каждые 2 недели на основе:
- Production метрик и проблем
- Пользовательской feedback
- Бизнес приоритетов

---

## 🚀 **ФИЛОСОФИЯ BACKLOG**

**"Ship working features incrementally"**

- ✅ Приоритет стабильности над новыми фичами
- ✅ Измеримый прогресс над теоретическими улучшениями
- ✅ Production feedback над предположениями
- ✅ Simple solutions over complex architectures

**Коротко: что делать сейчас**
1. Завершить сеть алёртов и safe-mode по API (Б4.2.2).
2. Собрать и автоматизировать регрессионные прогоны на записанных данных (CI + песочный API).
3. Перевести нейромодуль на контролируемый shadow/offline режим.


---

**Сводка статуса (2025-09-23):**
- ⚙️ Архитектура: Order queue + resilient API внедрены для core trade-флоу.
- 📊 Стратегии: Range Trading модульна, остальные ждут декомпозиции и юнит-тестов.
- 🧪 Тестирование/CI: отсутствуют автоматические тесты и регрессионные прогоны — критичный пробел.
- 📈 Observability: нет structured логов, метрик и промо-алертов.
- 🚀 Продакшн доступ: система остаётся pre-production до закрытия блоков Б4.2–Б4.7.
