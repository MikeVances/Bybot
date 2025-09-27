# bot/strategy/implementations/fibonacci_rsi_strategy.py
"""Fibonacci RSI strategy implemented on the pipeline architecture."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from ..base import BaseStrategy
from ..pipeline import PipelineStrategyMixin, StrategyPipeline, StrategyIndicators
from ..modules.fibonacci_pipeline import (
    FibonacciIndicatorEngine,
    FibonacciSignalGenerator,
    FibonacciPositionSizer,
)

from dataclasses import dataclass, field
from ..base.config import BaseStrategyConfig


@dataclass
class FibonacciRSIConfig(BaseStrategyConfig):
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

    def __post_init__(self):
        super().__post_init__()  # type: ignore[misc]
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


class FibonacciRSIStrategy(PipelineStrategyMixin, BaseStrategy):
    """Pipeline-backed Fibonacci RSI strategy."""

    def __init__(self, config: FibonacciRSIConfig):
        super().__init__(config, "FibonacciRSI_v2")
        self.config = config

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

    def calculate_strategy_indicators(self, market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        bundle = self.pipeline.indicator_engine.calculate(market_data)
        self._pipeline_indicators = bundle
        self._after_indicator_calculation(bundle)
        return bundle.data

    def _after_indicator_calculation(self, bundle: StrategyIndicators) -> None:
        if self._execution_count % 5 != 0:
            return
        rsi_value = bundle.latest('rsi', 50.0)
        volume_ratio = bundle.latest('volume_ratio', 1.0)
        self.logger.info(
            "🔍 Fibonacci RSI отладка: rsi=%.2f, volume_ratio=%.2f",
            rsi_value,
            volume_ratio,
        )


def create_fibonacci_rsi_strategy(config: Optional[FibonacciRSIConfig] = None, **kwargs) -> FibonacciRSIStrategy:
    if config is None:
        config = FibonacciRSIConfig()
    if kwargs:
        config = config.copy(**kwargs)
    return FibonacciRSIStrategy(config)


def create_conservative_fibonacci_rsi() -> FibonacciRSIStrategy:
    config = FibonacciRSIConfig(
        risk_reward_ratio=2.0,
        signal_strength_threshold=0.7,
        volume_multiplier=1.8,
        confluence_required=3,
    )
    return FibonacciRSIStrategy(config)


def create_aggressive_fibonacci_rsi() -> FibonacciRSIStrategy:
    config = FibonacciRSIConfig(
        risk_reward_ratio=1.2,
        signal_strength_threshold=0.5,
        volume_multiplier=1.3,
        confluence_required=1,
    )
    return FibonacciRSIStrategy(config)
