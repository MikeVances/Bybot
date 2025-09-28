# bot/strategy/implementations/fibonacci_rsi_strategy_v3.py
"""
РЕФАКТОРИРОВАННАЯ Fibonacci RSI стратегия v3.0
Использует унифицированные миксины для устранения дублирования
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from ..base import BaseStrategy
from ..base.config import BaseStrategyConfig
from ..pipeline import PipelineStrategyMixin, StrategyPipeline, StrategyIndicators
from ..modules.fibonacci_pipeline import (
    FibonacciIndicatorEngine,
    FibonacciSignalGenerator,
    FibonacciPositionSizer,
)

# Импорт унифицированных миксинов
from ..base.trailing_stop_mixin import TrailingStopMixin
from ..base.market_regime_mixin import MarketRegimeMixin
from ..base.factory_mixin import StrategyFactoryMixin
from ..utils.debug_logger import DebugLoggingMixin
from ..utils.exit_conditions import ExitConditionsCalculator


@dataclass
class FibonacciRSIConfigV3(BaseStrategyConfig):
    """Конфигурация для Fibonacci RSI стратегии v3."""
    fast_tf: str = '15m'
    slow_tf: str = '1h'
    ema_short: int = 20
    ema_long: int = 50
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    rsi_favorable_zone: tuple[float, float] = field(default=(40.0, 60.0))
    volume_multiplier: float = 1.5
    volume_ma_period: int = 20
    atr_period: int = 14
    atr_multiplier_sl: float = 1.0
    atr_multiplier_tp: float = 1.5
    fib_lookback: int = 50
    fib_levels: tuple[float, ...] = field(default=(0.382, 0.5, 0.618, 0.786))
    risk_reward_ratio: float = 1.5
    min_risk_reward_ratio: float = 1.0
    min_volume_threshold: float = 1000.0
    trend_strength_threshold: float = 0.001
    signal_strength_threshold: float = 0.6
    confluence_required: int = 2
    trade_amount: float = 0.001
    min_trade_amount: Optional[float] = None
    require_volume_confirmation: bool = True
    multi_timeframe_confirmation: bool = True
    use_fibonacci_targets: bool = True

    # Добавляем trailing stop параметры
    trailing_stop_activation_pct: float = 3.0
    trailing_stop_atr_multiplier: float = 0.7

    def __post_init__(self):
        super().__post_init__()
        if self.ema_short >= self.ema_long:
            raise ValueError('ema_short должен быть меньше ema_long')
        if self.rsi_overbought <= self.rsi_oversold:
            raise ValueError('rsi_overbought должен быть больше rsi_oversold')
        if self.volume_multiplier <= 1.0:
            raise ValueError('volume_multiplier должен быть > 1.0')
        if self.fib_lookback < 10:
            raise ValueError('fib_lookback должен быть >= 10')
        if self.min_trade_amount is None:
            self.min_trade_amount = self.trade_amount


class FibonacciRSIStrategyV3(
    TrailingStopMixin,           # Унифицированный trailing stop
    MarketRegimeMixin,           # Анализ рыночных режимов
    StrategyFactoryMixin,        # Унифицированные фабрики
    DebugLoggingMixin,           # Стандартизированное логирование
    PipelineStrategyMixin,       # Pipeline архитектура
    BaseStrategy                 # Базовая стратегия
):
    """
    РЕФАКТОРИРОВАННАЯ Fibonacci RSI стратегия v3.0

    🔥 УСТРАНЕНО ДУБЛИРОВАНИЕ:
    - Trailing stop логика → TrailingStopMixin (не было в оригинале, добавлено!)
    - Market regime анализ → MarketRegimeMixin (добавлено!)
    - Фабричные функции → StrategyFactoryMixin
    - Отладочное логирование → DebugLoggingMixin

    ✅ ТОРГОВАЯ ЛОГИКА СОХРАНЕНА:
    - Все расчеты Fibonacci уровней остались идентичными
    - RSI анализ работает как раньше
    - EMA crossover логика не изменена
    - Volume confirmation остался прежним
    """

    # Идентификатор для системы миксинов
    strategy_type = 'fibonacci_rsi'

    def __init__(self, config: FibonacciRSIConfigV3):
        super().__init__(config, "FibonacciRSI_v3")
        self.config = config

        # ТОРГОВАЯ ЛОГИКА СОХРАНЕНА: идентичная настройка pipeline
        pipeline = StrategyPipeline(
            indicator_engine=FibonacciIndicatorEngine(
                self.config,
                base_indicator_fn=self.calculate_base_indicators,
            ),
            signal_generator=FibonacciSignalGenerator(self.config),
            position_sizer=FibonacciPositionSizer(
                self.config,
                round_price_fn=self.round_price,
            ),
        )
        self._init_pipeline(pipeline)

        self.logger.info(
            "🎯 Fibonacci RSI v3.0 стратегия инициализирована: fib_levels=%s, rsi_period=%s",
            self.config.fib_levels,
            self.config.rsi_period,
        )

    # =========================================================================
    # ТОРГОВАЯ ЛОГИКА СОХРАНЕНА: Оригинальные методы
    # =========================================================================

    def calculate_strategy_indicators(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """ТОРГОВАЯ ЛОГИКА СОХРАНЕНА: Расчет Fibonacci + RSI индикаторов."""
        bundle = self.pipeline.indicator_engine.calculate(market_data)
        self._pipeline_indicators = bundle
        self._after_indicator_calculation(bundle)
        return bundle.data

    # =========================================================================
    # НОВЫЕ МЕТОДЫ (ДОБАВЛЯЮТ ФУНКЦИОНАЛЬНОСТЬ)
    # =========================================================================

    def _check_strategic_exit_conditions(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        """
        🚀 НОВАЯ ФУНКЦИОНАЛЬНОСТЬ: добавлен trailing stop для Fibonacci RSI!
        Раньше у этой стратегии не было продвинутых условий выхода
        """
        return ExitConditionsCalculator.calculate_strategic_exit(
            self, market_data, state, current_price
        )

    def _on_market_analysis(self, market_analysis: Dict[str, Any], df) -> None:
        """
        🚀 НОВАЯ ФУНКЦИОНАЛЬНОСТЬ: добавлен анализ рыночных режимов!
        """
        self.update_market_regime(df)

    # =========================================================================
    # КАСТОМНЫЕ ПРЕСЕТЫ ДЛЯ FACTORY MIXIN
    # =========================================================================

    @classmethod
    def _get_custom_presets(cls) -> Dict[str, Any]:
        """Кастомные пресеты для Fibonacci RSI стратегии."""

        return {
            'fibonacci_scalping': FibonacciRSIConfigV3(
                rsi_period=9,
                rsi_overbought=80.0,
                rsi_oversold=20.0,
                ema_short=12,
                ema_long=26,
                fib_lookback=20,
                risk_reward_ratio=1.2,
                signal_strength_threshold=0.5,
                trailing_stop_activation_pct=1.5,
            ),
            'fibonacci_swing': FibonacciRSIConfigV3(
                rsi_period=21,
                rsi_overbought=65.0,
                rsi_oversold=35.0,
                ema_short=50,
                ema_long=100,
                fib_lookback=100,
                risk_reward_ratio=3.0,
                signal_strength_threshold=0.8,
                trailing_stop_activation_pct=5.0,
            ),
            'fibonacci_crypto': FibonacciRSIConfigV3(
                volume_multiplier=2.5,
                rsi_overbought=75.0,
                rsi_oversold=25.0,
                fib_levels=(0.236, 0.382, 0.5, 0.618, 0.786),
                risk_reward_ratio=2.0,
                confluence_required=3,
            ),
        }


# =========================================================================
# АВТОМАТИЧЕСКИЕ ФАБРИЧНЫЕ ФУНКЦИИ
# =========================================================================

def create_fib_scalping(**kwargs) -> FibonacciRSIStrategyV3:
    """Быстрое создание Fibonacci стратегии для скальпинга."""
    return FibonacciRSIStrategyV3.create_preset('fibonacci_scalping', **kwargs)

def create_fib_swing(**kwargs) -> FibonacciRSIStrategyV3:
    """Быстрое создание Fibonacci стратегии для свинг торговли."""
    return FibonacciRSIStrategyV3.create_preset('fibonacci_swing', **kwargs)

def create_fib_crypto(**kwargs) -> FibonacciRSIStrategyV3:
    """Быстрое создание Fibonacci стратегии для криптовалют."""
    return FibonacciRSIStrategyV3.create_preset('fibonacci_crypto', **kwargs)

# Совместимость со старыми именами
def create_fibonacci_rsi_strategy(**kwargs) -> FibonacciRSIStrategyV3:
    """Обратная совместимость: создание стандартной Fibonacci RSI стратегии."""
    return FibonacciRSIStrategyV3.create_strategy(**kwargs)


# =========================================================================
# КОНСТАНТЫ И МЕТАДАННЫЕ
# =========================================================================

STRATEGY_INFO_V3 = {
    'name': 'FibonacciRSI_v3',
    'version': '3.0.0',
    'description': 'Рефакторированная Fibonacci RSI стратегия с добавленным функционалом',
    'author': 'TradingBot Team',
    'category': 'Technical Analysis',
    'trading_logic_preserved': {
        'fibonacci_calculations': '100% identical',
        'rsi_analysis': '100% identical',
        'ema_crossover': '100% identical',
        'volume_confirmation': '100% identical',
    },
    'new_features': [
        'Продвинутый trailing stop с ATR',
        'Анализ рыночных режимов',
        'Автоматические пресеты',
        'Унифицированное логирование',
    ]
}