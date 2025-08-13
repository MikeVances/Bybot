# bot/strategy/base/__init__.py
"""
Экспорты базовой архитектуры торговых стратегий
Предоставляет удобный доступ ко всем компонентам
"""

# Базовые классы и интерфейсы
from .strategy_base import BaseStrategy, create_strategy_instance, validate_strategy_implementation

# Конфигурационные классы
from .config import (
    BaseStrategyConfig,
    VolumeVWAPConfig, 
    CumDeltaConfig,
    MultiTFConfig,
    get_conservative_vwap_config,
    get_aggressive_delta_config,
    get_scalping_mtf_config,
    create_config_from_preset,
    validate_config_compatibility,
    MIN_DATA_REQUIREMENTS,
    RECOMMENDED_CONFLUENCE_FACTORS
)

# Перечисления и типы
from .enums import (
    MarketRegime,
    SignalType,
    PositionSide,
    ConfluenceFactor,
    TimeFrame,
    StrategyType,
    ExitReason,
    OrderType,
    ValidationLevel,
    LogLevel,
    PerformanceMetric,
    DEFAULT_TIMEFRAMES,
    STANDARD_CONFLUENCE_FACTORS,
    SIGNAL_TYPE_MAPPING,
    POSITION_SIDE_MAPPING
)

# Миксины для расширения функциональности
from .mixins import (
    PositionManagerMixin,
    StatisticsMixin,
    PriceUtilsMixin,
    MarketAnalysisMixin,
    LoggingMixin,
    DEFAULT_STATS_CONFIG,
    ADAPTATION_THRESHOLDS
)

# Версия базовой архитектуры
__version__ = "2.0.0"

# Основные экспорты для удобного импорта
__all__ = [
    # Основные классы
    "BaseStrategy",
    "create_strategy_instance", 
    "validate_strategy_implementation",
    
    # Конфигурации
    "BaseStrategyConfig",
    "VolumeVWAPConfig",
    "CumDeltaConfig", 
    "MultiTFConfig",
    "get_conservative_vwap_config",
    "get_aggressive_delta_config",
    "get_scalping_mtf_config",
    "create_config_from_preset",
    "validate_config_compatibility",
    
    # Перечисления
    "MarketRegime",
    "SignalType",
    "PositionSide",
    "ConfluenceFactor",
    "TimeFrame",
    "StrategyType",
    "ExitReason",
    "OrderType",
    "ValidationLevel",
    "LogLevel",
    "PerformanceMetric",
    
    # Миксины
    "PositionManagerMixin",
    "StatisticsMixin", 
    "PriceUtilsMixin",
    "MarketAnalysisMixin",
    "LoggingMixin",
    
    # Константы
    "DEFAULT_TIMEFRAMES",
    "STANDARD_CONFLUENCE_FACTORS",
    "MIN_DATA_REQUIREMENTS",
    "RECOMMENDED_CONFLUENCE_FACTORS",
    "DEFAULT_STATS_CONFIG",
    "ADAPTATION_THRESHOLDS"
]

# Информация о модуле
__author__ = "TradingBot Development Team"
__description__ = "Базовая архитектура для торговых стратегий с поддержкой множественных индикаторов, адаптивных параметров и расширенной аналитики"

# Совместимость версий
COMPATIBLE_STRATEGY_VERSIONS = ["1.0.0", "1.1.0", "2.0.0"]
MINIMUM_PYTHON_VERSION = "3.8"

def get_version_info():
    """Получение информации о версии базовой архитектуры"""
    return {
        "version": __version__,
        "author": __author__, 
        "description": __description__,
        "compatible_versions": COMPATIBLE_STRATEGY_VERSIONS,
        "minimum_python": MINIMUM_PYTHON_VERSION
    }

def get_available_configs():
    """Получение списка доступных конфигураций"""
    return {
        "base": BaseStrategyConfig,
        "volume_vwap": VolumeVWAPConfig,
        "cumdelta_sr": CumDeltaConfig,
        "multitf_volume": MultiTFConfig
    }

def get_available_mixins():
    """Получение списка доступных миксинов"""
    return {
        "position_manager": PositionManagerMixin,
        "statistics": StatisticsMixin,
        "price_utils": PriceUtilsMixin,
        "market_analysis": MarketAnalysisMixin,
        "logging": LoggingMixin
    }

# Валидация импортов
def validate_imports():
    """Проверка успешности импорта всех компонентов"""
    try:
        components = [
            BaseStrategy, BaseStrategyConfig, MarketRegime, SignalType,
            PositionManagerMixin, StatisticsMixin
        ]
        
        missing = []
        for component in components:
            if component is None:
                missing.append(component.__name__)
        
        if missing:
            raise ImportError(f"Не удалось импортировать компоненты: {missing}")
        
        return True, "Все компоненты успешно импортированы"
        
    except Exception as e:
        return False, f"Ошибка импорта: {e}"

# Автоматическая валидация при импорте модуля
_import_status, _import_message = validate_imports()
if not _import_status:
    import warnings
    warnings.warn(f"Проблемы с импортом базовой архитектуры: {_import_message}", ImportWarning)