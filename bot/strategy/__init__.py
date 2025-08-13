"""

# -----------------------------------------------------------------------------
# bot/strategy/__init__.py - Главные экспорты пакета
# -----------------------------------------------------------------------------

"""
# Основные экспорты для удобного использования
from .base import (
    BaseStrategy,
    BaseStrategyConfig,
    VolumeVWAPConfig,
    CumDeltaConfig,
    MultiTFConfig,
    MarketRegime
)

from .implementations import (
    VolumeVWAPStrategy,
    CumDeltaSRStrategy,
    MultiTFVolumeStrategy,
    FibonacciRSIStrategy
)

from .utils import TechnicalIndicators, DataValidator

__version__ = "2.0.0"
__all__ = [
    "BaseStrategy",
    "BaseStrategyConfig", 
    "VolumeVWAPStrategy",
    "CumDeltaSRStrategy",
    "MultiTFVolumeStrategy",
    "FibonacciRSIStrategy",
    "TechnicalIndicators",
    "MarketRegime"
]