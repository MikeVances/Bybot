# bot/strategy/implementations/range_trading_strategy.py
"""
Range Trading Strategy - стратегия для бокового рынка
Специально адаптирована для частых сделок с минимальным профитом
"""

import pandas as pd
from typing import Dict, Any

from ..base import (
    BaseStrategy,
    VolumeVWAPConfig,
)
from ..pipeline import PipelineStrategyMixin, StrategyPipeline, StrategyIndicators
from ..modules.range_pipeline import RangeIndicatorEngine, RangeSignalGenerator, RangePositionSizer


class RangeTradingStrategy(PipelineStrategyMixin, BaseStrategy):
    """
    Range Trading Strategy v1.0
    
    Специальная стратегия для бокового рынка:
    - Частые сделки с минимальным профитом
    - Низкие требования к объему
    - Фокус на краткосрочных движениях
    - Адаптивные SL/TP для диапазона
    """
    
    def __init__(self, config: VolumeVWAPConfig):
        """
        Инициализация Range Trading стратегии
        
        Args:
            config: Конфигурация стратегии
        """
        super().__init__(config, "RangeTrading_v1")
        
        # Специфичная конфигурация для диапазона
        self.config: VolumeVWAPConfig = config

        # Адаптируем параметры для бокового рынка
        self.config.volume_multiplier = 1.2  # Низкий порог объема
        self.config.signal_strength_threshold = 0.3  # Низкий порог силы сигнала
        self.config.confluence_required = 1  # Минимум подтверждений
        self.config.risk_reward_ratio = 1.2  # Низкий R:R для частых сделок
        self.config.min_risk_reward_ratio = 0.8  # Снижаем минимальное R:R для диапазона

        pipeline = StrategyPipeline(
            indicator_engine=RangeIndicatorEngine(self.config, base_indicator_fn=self.calculate_base_indicators),
            signal_generator=RangeSignalGenerator(self.config),
            position_sizer=RangePositionSizer(self.config, round_price_fn=self.round_price)
        )
        self._init_pipeline(pipeline)

        self.logger.info("🎯 Range Trading стратегия инициализирована")
        self.logger.info(
            "📊 Параметры: volume_mult=%s, signal_strength=%s",
            self.config.volume_multiplier,
            self.config.signal_strength_threshold,
        )

    def _on_market_analysis(self, market_analysis: Dict[str, Any], df: pd.DataFrame) -> None:
        condition = market_analysis.get('condition')
        if condition and self._execution_count % 10 == 0:
            self.log_market_analysis(market_analysis)

    def _after_indicator_calculation(self, bundle: StrategyIndicators) -> None:
        if self._execution_count % 5 != 0:
            return
        volume_ratio = bundle.latest('volume_ratio', 0.0)
        rsi = bundle.latest('rsi', 50.0)
        momentum = bundle.latest('price_momentum', 0.0)
        self.logger.info(
            "🔍 Range Trading отладка: vol_ratio=%s, rsi=%s, momentum=%s",
            f"{volume_ratio:.2f}",
            f"{rsi:.1f}",
            f"{momentum:.4f}",
        )


# =========================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =========================================================================


def create_range_trading_strategy() -> RangeTradingStrategy:
    """Создание Range Trading стратегии"""
    config = VolumeVWAPConfig(
        volume_multiplier=1.2,
        signal_strength_threshold=0.3,
        confluence_required=1,
        risk_reward_ratio=1.2,
        max_risk_per_trade_pct=0.5,  # Низкий риск для частых сделок
        min_volume_for_signal=100  # Низкий объем
    )
    return RangeTradingStrategy(config)


# =========================================================================
# КОНСТАНТЫ И МЕТАДАННЫЕ
# =========================================================================

STRATEGY_INFO = {
    'name': 'Range_Trading',
    'version': '1.0.0',
    'description': 'Стратегия для бокового рынка с частыми сделками и минимальным профитом',
    'author': 'TradingBot Team',
    'category': 'Range Trading',
    'timeframes': ['1m', '5m', '15m'],
    'min_data_points': 50,
    'supported_assets': ['crypto', 'forex', 'stocks'],
    'market_conditions': ['sideways', 'range', 'low_volatility']
} 
