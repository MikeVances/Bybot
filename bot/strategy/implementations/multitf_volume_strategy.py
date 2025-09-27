# bot/strategy/implementations/multitf_volume_strategy.py
"""Multi-timeframe volume strategy built on the pipeline architecture."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from ..base import (
    BaseStrategy,
    MultiTFConfig,
    SignalType,
    MarketRegime,
)
from ..pipeline import PipelineStrategyMixin, StrategyPipeline, StrategyIndicators
from ..modules.multitf_pipeline import (
    MultiTFIndicatorEngine,
    MultiTFSignalGenerator,
    MultiTFPositionSizer,
)
from ..utils.indicators import TechnicalIndicators


class MultiTFVolumeStrategy(PipelineStrategyMixin, BaseStrategy):
    """Pipeline-backed implementation of the multi-timeframe volume strategy."""

    def __init__(self, config: MultiTFConfig):
        super().__init__(config, "MultiTF_Volume_v2")
        self.config = config

        pipeline = StrategyPipeline(
            indicator_engine=MultiTFIndicatorEngine(
                self.config,
                base_indicator_fn=self.calculate_base_indicators,
            ),
            signal_generator=MultiTFSignalGenerator(self.config),
            position_sizer=MultiTFPositionSizer(
                self.config,
                round_price_fn=self.round_price,
                calc_levels_fn=self.calculate_dynamic_levels,
            ),
        )
        self._init_pipeline(pipeline)

        self.logger.info(
            "🎯 MultiTF стратегия инициализирована: fast_tf=%s, slow_tf=%s",
            self.config.fast_tf.value,
            self.config.slow_tf.value,
        )

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        bundle = self.pipeline.indicator_engine.calculate(market_data)
        self._pipeline_indicators = bundle
        self._after_indicator_calculation(bundle)
        return bundle.data

    def _on_market_analysis(self, market_analysis: Dict[str, Any], df: pd.DataFrame) -> None:
        self._update_market_regime(df)

    def _after_indicator_calculation(self, bundle: StrategyIndicators) -> None:
        if self._execution_count % 5 != 0:
            return
        volume_ratio = bundle.latest('volume_ratio', 1.0)
        slow_strength = bundle.latest('slow_trend_strength', 0.0)
        self.logger.info(
            "🔍 MultiTF отладка: volume_ratio=%.2f, slow_trend_strength=%.4f",
            volume_ratio,
            slow_strength,
        )

    # ------------------------------------------------------------------
    # Strategic exit conditions
    # ------------------------------------------------------------------

    def _check_strategic_exit_conditions(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        try:
            if not state or not state.in_position:
                return None

            position_side = getattr(state, 'position_side', None)
            entry_price = getattr(state, 'entry_price', None)
            if not position_side or entry_price is None:
                return None

            indicators_dict = self.calculate_strategy_indicators(market_data)
            if not indicators_dict:
                return None
            bundle = self._ensure_bundle(indicators_dict)

            if position_side == 'BUY':
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - current_price) / entry_price * 100

            if pnl_pct > self.config.trailing_stop_activation_pct:
                df_fast, _ = self._extract_timeframes(market_data)
                atr_result = TechnicalIndicators.calculate_atr_safe(df_fast, 14)
                atr = atr_result.value if atr_result and atr_result.is_valid else entry_price * 0.01
                trailing_distance = atr * 0.7
                if position_side == 'BUY':
                    trailing_stop = current_price - trailing_distance
                    if current_price < trailing_stop:
                        return {
                            'signal': SignalType.EXIT_LONG,
                            'reason': 'trailing_stop',
                            'current_price': current_price,
                            'pnl_pct': pnl_pct,
                        }
                else:
                    trailing_stop = current_price + trailing_distance
                    if current_price > trailing_stop:
                        return {
                            'signal': SignalType.EXIT_SHORT,
                            'reason': 'trailing_stop',
                            'current_price': current_price,
                            'pnl_pct': pnl_pct,
                        }

            alignment_bull = bundle.latest('trends_aligned_bullish', False)
            alignment_bear = bundle.latest('trends_aligned_bearish', False)
            if position_side == 'BUY' and alignment_bear:
                return {
                    'signal': SignalType.EXIT_LONG,
                    'reason': 'trend_alignment_broken',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                }
            if position_side == 'SELL' and alignment_bull:
                return {
                    'signal': SignalType.EXIT_SHORT,
                    'reason': 'trend_alignment_broken',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                }

            return None
        except Exception as exc:
            self.logger.error(f"Ошибка проверки условий выхода: {exc}")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_timeframes(self, market_data: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
        if isinstance(market_data, dict):
            df_fast = market_data.get(self.config.fast_tf.value)
            df_slow = market_data.get(self.config.slow_tf.value)
            if df_fast is None or df_slow is None:
                raise ValueError('Недостаточно данных для мультитаймфрейм анализа')
        else:
            df_fast = market_data
            df_slow = market_data
        return df_fast, df_slow

    def _update_market_regime(self, df: pd.DataFrame) -> None:
        try:
            returns = df['close'].pct_change().dropna()
            if returns.empty:
                self.current_market_regime = MarketRegime.NORMAL
                return

            volatility = returns.std()
            if volatility > 0.03:
                self.current_market_regime = MarketRegime.VOLATILE
            elif volatility < 0.01:
                self.current_market_regime = MarketRegime.SIDEWAYS
            else:
                self.current_market_regime = MarketRegime.NORMAL
        except Exception as exc:
            self.logger.error(f"Ошибка обновления рыночного режима: {exc}")
            self.current_market_regime = MarketRegime.NORMAL

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_strategy_info(self) -> Dict[str, Any]:
        return {
            'strategy_name': 'MultiTF_Volume_v2',
            'version': '2.0.0',
            'description': 'Multi-timeframe volume стратегия с модульной архитектурой',
            'config': {
                'fast_tf': self.config.fast_tf.value,
                'slow_tf': self.config.slow_tf.value,
                'volume_multiplier': self.config.volume_multiplier,
                'trend_strength_threshold': self.config.trend_strength_threshold,
                'momentum_analysis': self.config.momentum_analysis,
                'mtf_divergence_detection': self.config.mtf_divergence_detection,
            },
            'current_market_regime': getattr(self.current_market_regime, 'value', 'unknown'),
            'is_active': self.is_active,
        }


def create_multitf_volume_strategy(config: Optional[MultiTFConfig] = None, **kwargs) -> MultiTFVolumeStrategy:
    if config is None:
        config = MultiTFConfig()
    if kwargs:
        config = config.copy(**kwargs)
    return MultiTFVolumeStrategy(config)


def create_conservative_multitf_volume() -> MultiTFVolumeStrategy:
    config = MultiTFConfig(
        volume_multiplier=3.0,
        trend_strength_threshold=0.003,
        signal_strength_threshold=0.7,
        confluence_required=3,
        fast_window=30,
        slow_window=60,
    )
    return MultiTFVolumeStrategy(config)


def create_aggressive_multitf_volume() -> MultiTFVolumeStrategy:
    config = MultiTFConfig(
        volume_multiplier=2.0,
        trend_strength_threshold=0.0015,
        signal_strength_threshold=0.5,
        confluence_required=1,
        fast_window=18,
        slow_window=36,
    )
    return MultiTFVolumeStrategy(config)
