# bot/core/__init__.py
# Инициализация торгового модуля - точка входа для торговой логики
# Функции: экспорт основных компонентов, обеспечение чистой архитектуры

# Импортируем основные торговые функции
from .trader import (
    run_trading,
    run_trading_with_risk_management,
    load_strategy,
    get_active_strategies,
    BotState,
    setup_strategy_logger,
    log_trade_journal,
    get_current_balance,
    get_current_price,
    update_position_in_risk_manager,
    sync_position_with_exchange
)

# Определяем публичный API модуля
__all__ = [
    # Основные торговые функции
    'run_trading',                      # Обычная торговля (для обратной совместимости)
    'run_trading_with_risk_management', # Торговля с риск-менеджментом (новая версия)
    
    # Утилиты работы со стратегиями
    'load_strategy',                    # Загрузка стратегии по имени
    'get_active_strategies',            # Получение списка активных стратегий
    
    # Состояние и логирование
    'BotState',                         # Класс состояния позиции
    'setup_strategy_logger',            # Настройка логирования для стратегии
    'log_trade_journal',                # Запись в торговый журнал
    
    # Вспомогательные функции
    'get_current_balance',              # Получение баланса
    'get_current_price',                # Получение текущей цены
    'update_position_in_risk_manager',  # Обновление позиций в риск-менеджере
    'sync_position_with_exchange'       # Синхронизация с биржей
]

# Версия модуля для отслеживания изменений
__version__ = "2.0.0"

# Краткая информация о модуле
__doc__ = """
Торговый модуль с интегрированным риск-менеджментом

Основные компоненты:
- run_trading_with_risk_management: главная функция торгового цикла
- BotState: управление состоянием позиций
- Утилиты для работы со стратегиями и логированием

Пример использования:
    from bot.core import run_trading_with_risk_management
    from bot.risk import RiskManager
    
    risk_manager = RiskManager()
    run_trading_with_risk_management(risk_manager, shutdown_event)
"""