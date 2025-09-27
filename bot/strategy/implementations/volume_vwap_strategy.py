# bot/strategy/implementations/volume_vwap_strategy.py
"""Volume VWAP strategy implemented on the shared pipeline architecture."""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from ..base import (
    BaseStrategy,
    VolumeVWAPConfig,
    SignalType,
    PositionSide,
)
from ..pipeline import PipelineStrategyMixin, StrategyPipeline, StrategyIndicators
from ..modules.volume_vwap_pipeline import (
    VolumeVwapIndicatorEngine,
    VolumeVwapSignalGenerator,
    VolumeVwapPositionSizer,
)


class VolumeVWAPStrategy(PipelineStrategyMixin, BaseStrategy):
    """Pipeline-backed implementation of the Volume VWAP strategy."""

    def __init__(self, config: VolumeVWAPConfig):
        super().__init__(config, "VolumeVWAP_v2")
        self.config = config

        self.config.min_risk_reward_ratio = max(0.8, self.config.min_risk_reward_ratio)
        if self.config.min_risk_reward_ratio > self.config.risk_reward_ratio:
            self.config.risk_reward_ratio = self.config.min_risk_reward_ratio

        pipeline = StrategyPipeline(
            indicator_engine=VolumeVwapIndicatorEngine(
                self.config,
                base_indicator_fn=self.calculate_base_indicators,
            ),
            signal_generator=VolumeVwapSignalGenerator(self.config),
            position_sizer=VolumeVwapPositionSizer(self.config, round_price_fn=self.round_price),
        )
        self._init_pipeline(pipeline)

        self.logger.info(
            "🎯 Volume VWAP стратегия инициализирована: volume_mult=%s, trend_period=%s",
            self.config.volume_multiplier,
            self.config.trend_period,
        )

    # ------------------------------------------------------------------
    # Indicator processing helpers
    # ------------------------------------------------------------------

    def _adjust_for_low_volatility(self, df: pd.DataFrame) -> Optional[float]:
        """Temporarily relax volume requirements when volatility is subdued."""

        if not self.config.adaptive_parameters or len(df) <= 20:
            return None

        returns = df['close'].pct_change().dropna()
        if returns.empty:
            return None

        volatility = returns.tail(10).std()
        if volatility < 0.02:
            original = self.config.volume_multiplier
            new_value = max(1.5, original * 0.5)
            if new_value != original:
                self.logger.info(
                    "🔄 Адаптация параметров для низкой волатильности: %.2f → %.2f",
                    original,
                    new_value,
                )
                self.config.volume_multiplier = new_value
                return original
        return None

    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        df = self.get_primary_dataframe(market_data)
        original_multiplier = None
        if df is not None:
            original_multiplier = self._adjust_for_low_volatility(df)
        try:
            return super().calculate_strategy_indicators(market_data)
        finally:
            if original_multiplier is not None:
                self.config.volume_multiplier = original_multiplier

    def _after_indicator_calculation(self, bundle: StrategyIndicators) -> None:
        if self._execution_count % 10 != 0:
            return
        volume_ratio = bundle.latest('volume_ratio', 0.0)
        price_above_vwap = bundle.latest('price_above_vwap', False)
        momentum = bundle.latest('price_momentum', 0.0)
        trend_bullish = bundle.latest('trend_bullish', False)
        self.logger.info(
            "🔍 Volume VWAP отладка: vol_ratio=%.2f, above_vwap=%s, momentum=%.4f, trend_bull=%s",
            volume_ratio,
            price_above_vwap,
            momentum,
            trend_bullish,
        )

    # ------------------------------------------------------------------
    # Execution hooks
    # ------------------------------------------------------------------

    def _on_market_analysis(self, market_analysis: Dict[str, Any], df: pd.DataFrame) -> None:
        condition = market_analysis.get('condition')
        if condition and self._execution_count % 20 == 0:
            self.log_market_analysis(market_analysis)

    def _before_signal_generation(
        self,
        df: pd.DataFrame,
        indicators: StrategyIndicators,
        market_analysis: Dict[str, Any],
    ) -> tuple[bool, Optional[str]]:
        if self.config.volatility_filter:
            returns = df['close'].pct_change().dropna()
            if not returns.empty:
                current_volatility = returns.tail(10).std()
                if current_volatility > self.config.max_volatility_threshold:
                    return False, (
                        f"volatility {current_volatility:.4f} > "
                        f"{self.config.max_volatility_threshold:.4f}"
                    )
        if 'volume' in df.columns:
            last_volume = float(df['volume'].iloc[-1])
            if last_volume < self.config.min_volume_for_signal:
                return False, (
                    f"volume {last_volume:.2f} < "
                    f"{self.config.min_volume_for_signal:.2f}"
                )
        return True, None

    def _check_strategic_exit_conditions(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        try:
            df = self.get_primary_dataframe(market_data)
            if df is None:
                return None

            indicators_dict = self.calculate_strategy_indicators(market_data)
            if not indicators_dict:
                return None

            bundle = self._ensure_bundle(indicators_dict)
            position_info = self.get_position_info(state)
            position_side = position_info.get('side')

            if position_side in ['BUY', PositionSide.LONG]:
                price_below_vwap = bundle.latest('price_below_vwap', False)
                volume_spike = bundle.latest('volume_spike', False)
                trend_bearish = bundle.latest('trend_bearish', False)
                if price_below_vwap and (volume_spike or trend_bearish):
                    return {
                        'signal': SignalType.EXIT_LONG,
                        'exit_reason': 'vwap_reversal',
                        'current_price': current_price,
                        'comment': 'Выход: цена ниже VWAP с подтверждением',
                    }

            if position_side in ['SELL', PositionSide.SHORT]:
                price_above_vwap = bundle.latest('price_above_vwap', False)
                volume_spike = bundle.latest('volume_spike', False)
                trend_bullish = bundle.latest('trend_bullish', False)
                if price_above_vwap and (volume_spike or trend_bullish):
                    return {
                        'signal': SignalType.EXIT_SHORT,
                        'exit_reason': 'vwap_reversal',
                        'current_price': current_price,
                        'comment': 'Выход: цена выше VWAP с подтверждением',
                    }

            return None
        except Exception as exc:
            self.logger.error(f"Ошибка стратегических условий выхода: {exc}")
            return None


# =========================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ И УТИЛИТЫ
# =========================================================================

def create_volume_vwap_strategy(config: Optional[VolumeVWAPConfig] = None, **kwargs) -> VolumeVWAPStrategy:
    """Фабричная функция для создания VolumeVWAP стратегии."""
    if config is None:
        config = VolumeVWAPConfig()
    if kwargs:
        config_dict = config.to_dict()
        config_dict.update(kwargs)
        config = VolumeVWAPConfig.from_dict(config_dict)
    return VolumeVWAPStrategy(config)


def create_conservative_volume_vwap() -> VolumeVWAPStrategy:
    """Создание консервативной версии VolumeVWAP стратегии."""
    from ..base.config import get_conservative_vwap_config

    config = get_conservative_vwap_config()
    return VolumeVWAPStrategy(config)


def create_aggressive_volume_vwap() -> VolumeVWAPStrategy:
    """Создание агрессивной версии VolumeVWAP стратегии."""
    config = VolumeVWAPConfig(
        volume_multiplier=2.0,
        signal_strength_threshold=0.5,
        risk_reward_ratio=2.0,
        confluence_required=1,
        max_risk_per_trade_pct=1.5,
    )
    return VolumeVWAPStrategy(config)


# =========================================================================
# КОНСТАНТЫ И МЕТАДАННЫЕ
# =========================================================================

STRATEGY_INFO = {
    'name': 'VolumeSpike_VWAP',
    'version': '2.0.0',
    'description': 'Стратегия на основе всплесков объема и VWAP анализа',
    'author': 'TradingBot Team',
    'category': 'Volume Analysis',
    'timeframes': ['1m', '5m', '15m'],
    'min_data_points': 100,
    'supported_assets': ['crypto', 'forex', 'stocks'],
}

MARKET_PRESETS = {
    'crypto_volatile': {
        'volume_multiplier': 4.0,
        'max_volatility_threshold': 0.08,
        'signal_strength_threshold': 0.7,
    },
    'crypto_stable': {
        'volume_multiplier': 2.5,
        'max_volatility_threshold': 0.04,
        'signal_strength_threshold': 0.6,
    },
    'forex': {
        'volume_multiplier': 1.8,
        'max_volatility_threshold': 0.02,
        'signal_strength_threshold': 0.65,
    },
}
