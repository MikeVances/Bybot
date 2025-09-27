# bot/strategy/implementations/cumdelta_sr_strategy.py
"""CumDelta Support/Resistance strategy built on the pipeline architecture."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from ..base import (
    BaseStrategy,
    CumDeltaConfig,
    SignalType,
    MarketRegime,
)
from ..pipeline import PipelineStrategyMixin, StrategyPipeline, StrategyIndicators
from ..modules.cumdelta_pipeline import (
    CumDeltaIndicatorEngine,
    CumDeltaSignalGenerator,
    CumDeltaPositionSizer,
)
from ..utils.indicators import TechnicalIndicators


class CumDeltaSRStrategy(PipelineStrategyMixin, BaseStrategy):
    """Pipeline-backed implementation of the CumDelta Support/Resistance strategy."""

    def __init__(self, config: CumDeltaConfig):
        super().__init__(config, "CumDelta_SR_v2")
        self.config = config

        self.config.min_risk_reward_ratio = max(0.8, self.config.min_risk_reward_ratio)
        if self.config.min_risk_reward_ratio > self.config.risk_reward_ratio:
            self.config.risk_reward_ratio = self.config.min_risk_reward_ratio

        pipeline = StrategyPipeline(
            indicator_engine=CumDeltaIndicatorEngine(
                self.config,
                base_indicator_fn=self.calculate_base_indicators,
            ),
            signal_generator=CumDeltaSignalGenerator(self.config),
            position_sizer=CumDeltaPositionSizer(
                self.config,
                round_price_fn=self.round_price,
                calc_levels_fn=self.calculate_dynamic_levels,
            ),
        )
        self._init_pipeline(pipeline)

        self.logger.info(
            "🎯 CumDelta Support/Resistance стратегия инициализирована: delta_window=%s, support_window=%s",
            self.config.delta_window,
            self.config.support_window,
        )

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def _on_market_analysis(self, market_analysis: Dict[str, Any], df: pd.DataFrame) -> None:
        self._update_market_regime(df)

    def _after_indicator_calculation(self, bundle: StrategyIndicators) -> None:
        cum_delta = bundle.latest('cum_delta', 0.0)
        delta_momentum = bundle.latest('delta_momentum', 0.0)
        trend_slope = bundle.latest('trend_slope', 0.0)
        self.logger.debug(
            "🔍 CumDelta индикаторы: cum_delta=%s, delta_momentum=%s, trend_slope=%s",
            f"{float(cum_delta):.0f}",
            f"{float(delta_momentum):.0f}",
            f"{float(trend_slope):.5f}",
        )

    # ------------------------------------------------------------------
    # Strategic exit logic
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
                df = self.get_primary_dataframe(market_data)
                if df is not None:
                    atr_result = TechnicalIndicators.calculate_atr_safe(df, 14)
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

            cum_delta = bundle.latest('cum_delta', 0.0)
            if position_side == 'BUY' and cum_delta < -self.config.min_delta_threshold:
                return {
                    'signal': SignalType.EXIT_LONG,
                    'reason': 'negative_delta',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                }
            if position_side == 'SELL' and cum_delta > self.config.min_delta_threshold:
                return {
                    'signal': SignalType.EXIT_SHORT,
                    'reason': 'positive_delta',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                }

            return None
        except Exception as exc:
            self.logger.error(f"Ошибка проверки условий выхода: {exc}")
            return None

    # ------------------------------------------------------------------
    # Market regime helper
    # ------------------------------------------------------------------

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
            'strategy_name': 'CumDelta_SupportResistance_v2',
            'version': '2.0.0',
            'description': 'CumDelta Support/Resistance стратегия с модульной архитектурой',
            'config': {
                'delta_window': self.config.delta_window,
                'support_window': self.config.support_window,
                'min_delta_threshold': self.config.min_delta_threshold,
                'support_resistance_tolerance': self.config.support_resistance_tolerance,
                'volume_multiplier': self.config.volume_multiplier,
                'use_enhanced_delta': self.config.use_enhanced_delta,
                'delta_divergence_detection': self.config.delta_divergence_detection,
                'support_resistance_breakout': self.config.support_resistance_breakout,
            },
            'current_market_regime': getattr(self.current_market_regime, 'value', 'unknown'),
            'is_active': self.is_active,
        }


# =========================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =========================================================================

def create_cumdelta_sr_strategy(config: Optional[CumDeltaConfig] = None, **kwargs) -> CumDeltaSRStrategy:
    if config is None:
        config = CumDeltaConfig()
    if kwargs:
        config = config.copy(**kwargs)
    return CumDeltaSRStrategy(config)


def create_conservative_cumdelta_sr() -> CumDeltaSRStrategy:
    config = CumDeltaConfig(
        min_delta_threshold=150.0,
        confluence_required=3,
        signal_strength_threshold=0.7,
        support_resistance_tolerance=0.003,
        volume_multiplier=2.0,
        risk_reward_ratio=2.0,
        stop_loss_atr_multiplier=1.2,
    )
    return CumDeltaSRStrategy(config)


def create_aggressive_cumdelta_sr() -> CumDeltaSRStrategy:
    config = CumDeltaConfig(
        min_delta_threshold=50.0,
        confluence_required=1,
        signal_strength_threshold=0.5,
        support_resistance_tolerance=0.001,
        volume_multiplier=1.2,
        risk_reward_ratio=1.2,
        stop_loss_atr_multiplier=1.8,
    )
    return CumDeltaSRStrategy(config)
