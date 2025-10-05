"""Pipeline components for Volume VWAP strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from bot.strategy.pipeline.common import (
    IndicatorEngine,
    SignalGenerator,
    PositionSizer,
    StrategyIndicators,
    SignalDecision,
    PositionPlan,
)
from bot.strategy.utils.indicators import TechnicalIndicators
from bot.strategy.utils.volume_seasonality import adjust_volume_for_seasonality

# ✅ NEW: Market Context Engine for intelligent trading
try:
    from bot.market_context import MarketContextEngine
    MARKET_CONTEXT_AVAILABLE = True
except ImportError:
    MARKET_CONTEXT_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning("Market Context Engine not available, using legacy logic")


@dataclass
class VolumeContext:
    volume_multiplier: float
    volume_sma_period: int
    volume_trend_window: int
    min_volume_consistency: int
    vwap_deviation_threshold: float
    vwap_confirmation_bars: int
    trend_period: int
    min_trend_slope: float
    price_momentum_period: int
    volume_momentum_period: int
    risk_reward_ratio: float
    min_risk_reward_ratio: float
    trade_amount: float
    min_trade_amount: float

    # ✅ NEW: Market Context parameters
    use_market_context: bool = True
    use_liquidity_targets: bool = True
    use_session_stops: bool = True
    min_context_confidence: float = 0.3


class VolumeVwapIndicatorEngine(IndicatorEngine):
    def __init__(self, config: Any, base_indicator_fn):
        self.config = config
        self._base_indicator_fn = base_indicator_fn

    def calculate(self, df: pd.DataFrame) -> StrategyIndicators:
        indicators: Dict[str, Any] = {}

        if self._base_indicator_fn is not None:
            indicators.update(self._base_indicator_fn(df) or {})

        if 'volume' not in df.columns:
            return StrategyIndicators(data=indicators)

        # 🚀 ПРОФЕССИОНАЛЬНОЕ УЛУЧШЕНИЕ: Seasonal Volume Adjustment
        # Корректируем объемы под intraday/weekly паттерны
        use_seasonality = getattr(self.config, 'use_volume_seasonality', True)

        if use_seasonality and len(df) >= 100:  # Минимум данных для калибровки
            try:
                df_adjusted = df.copy()
                df_adjusted['volume_adjusted'] = adjust_volume_for_seasonality(df, lookback_days=30)
                volume_series = df_adjusted['volume_adjusted']
                indicators['seasonality_enabled'] = True
            except Exception as e:
                # Fallback на обычные объемы если ошибка
                volume_series = df['volume']
                indicators['seasonality_enabled'] = False
        else:
            volume_series = df['volume']
            indicators['seasonality_enabled'] = False

        vol_sma_period = getattr(self.config, 'volume_sma_period', 20)
        indicators['vol_sma'] = volume_series.rolling(vol_sma_period, min_periods=1).mean()
        indicators['volume_ratio'] = volume_series / indicators['vol_sma']
        indicators['volume_spike'] = indicators['volume_ratio'] > getattr(self.config, 'volume_multiplier', 2.0)

        vol_trend_window = getattr(self.config, 'volume_trend_window', 10)
        indicators['volume_trend'] = df['volume'].rolling(vol_trend_window, min_periods=1).mean().diff()
        indicators['volume_increasing'] = indicators['volume_trend'] > 0

        consistency = getattr(self.config, 'min_volume_consistency', 3)
        high_volume_bars = (indicators['volume_ratio'] > getattr(self.config, 'volume_multiplier', 2.0)).rolling(consistency).sum()
        indicators['volume_consistent'] = high_volume_bars >= consistency

        vwap_result = TechnicalIndicators.calculate_vwap(df)
        if vwap_result.is_valid:
            indicators['vwap'] = vwap_result.value
        else:
            indicators['vwap'] = df['close'].rolling(10, min_periods=1).mean()

        indicators['vwap_deviation'] = abs(df['close'] - indicators['vwap']) / df['close']
        indicators['vwap_significant_deviation'] = indicators['vwap_deviation'] > getattr(self.config, 'vwap_deviation_threshold', 0.002)
        indicators['price_above_vwap'] = df['close'] > indicators['vwap']
        indicators['price_below_vwap'] = df['close'] < indicators['vwap']

        confirmation_bars = getattr(self.config, 'vwap_confirmation_bars', 3)
        indicators['vwap_bullish_confirmed'] = indicators['price_above_vwap'].rolling(confirmation_bars).sum() >= confirmation_bars
        indicators['vwap_bearish_confirmed'] = indicators['price_below_vwap'].rolling(confirmation_bars).sum() >= confirmation_bars

        trend_period = getattr(self.config, 'trend_period', 50)
        indicators['sma_trend'] = df['close'].rolling(trend_period, min_periods=1).mean()
        slope_period = max(trend_period // 4, 5)
        indicators['trend_slope'] = indicators['sma_trend'].diff(slope_period)
        indicators['trend_slope_normalized'] = indicators['trend_slope'] / df['close']
        min_slope = getattr(self.config, 'min_trend_slope', 0.0005)
        indicators['trend_bullish'] = indicators['trend_slope_normalized'] > min_slope
        indicators['trend_bearish'] = indicators['trend_slope_normalized'] < -min_slope
        indicators['trend_sideways'] = (~indicators['trend_bullish']) & (~indicators['trend_bearish'])

        if len(df) >= trend_period:
            price_series = indicators['sma_trend'].tail(trend_period)
            time_series = np.arange(len(price_series))
            correlation = np.corrcoef(time_series, price_series)[0, 1] if len(price_series) > 1 else 0
            indicators['trend_strength'] = abs(correlation) if not np.isnan(correlation) else 0
        else:
            indicators['trend_strength'] = 0

        momentum_period = getattr(self.config, 'price_momentum_period', 5)
        indicators['price_momentum'] = df['close'].pct_change(momentum_period)
        indicators['momentum_bullish'] = indicators['price_momentum'] > 0
        indicators['momentum_bearish'] = indicators['price_momentum'] < 0

        vol_momentum_period = getattr(self.config, 'volume_momentum_period', 5)
        indicators['volume_momentum'] = df['volume'].pct_change(vol_momentum_period)
        indicators['volume_momentum_positive'] = indicators['volume_momentum'] > 0

        indicators['bullish_setup'] = (
            indicators['volume_spike'] &
            indicators['price_above_vwap'] &
            (indicators['trend_bullish'] | indicators['momentum_bullish'])
        )

        indicators['bearish_setup'] = (
            indicators['volume_spike'] &
            indicators['price_below_vwap'] &
            (indicators['trend_bearish'] | indicators['momentum_bearish'])
        )

        return StrategyIndicators(data=indicators)


class VolumeVwapSignalGenerator(SignalGenerator):
    def __init__(self, config: Any):
        self.ctx = VolumeContext(
            volume_multiplier=getattr(config, 'volume_multiplier', 2.0),
            volume_sma_period=getattr(config, 'volume_sma_period', 20),
            volume_trend_window=getattr(config, 'volume_trend_window', 10),
            min_volume_consistency=getattr(config, 'min_volume_consistency', 3),
            vwap_deviation_threshold=getattr(config, 'vwap_deviation_threshold', 0.002),
            vwap_confirmation_bars=getattr(config, 'vwap_confirmation_bars', 3),
            trend_period=getattr(config, 'trend_period', 50),
            min_trend_slope=getattr(config, 'min_trend_slope', 0.0005),
            price_momentum_period=getattr(config, 'price_momentum_period', 5),
            volume_momentum_period=getattr(config, 'volume_momentum_period', 5),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 0.8),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
        )

    def _strength(self, indicators: StrategyIndicators, signal_type: str) -> float:
        strength = 0.0
        if signal_type == 'BUY':
            if indicators.latest('volume_spike', False):
                strength += 0.3
            if indicators.latest('price_above_vwap', False):
                strength += 0.2
            if indicators.latest('trend_bullish', False):
                strength += 0.2
            if indicators.latest('momentum_bullish', False):
                strength += 0.2
            if indicators.latest('vwap_bullish_confirmed', False):
                strength += 0.1
        else:
            if indicators.latest('volume_spike', False):
                strength += 0.3
            if indicators.latest('price_below_vwap', False):
                strength += 0.2
            if indicators.latest('trend_bearish', False):
                strength += 0.2
            if indicators.latest('momentum_bearish', False):
                strength += 0.2
            if indicators.latest('vwap_bearish_confirmed', False):
                strength += 0.1
        return min(1.0, strength)

    def _confluence(self, indicators: StrategyIndicators, signal_type: str) -> List[str]:
        factors: List[str] = []
        if signal_type == 'BUY':
            if indicators.latest('volume_spike', False):
                factors.append('Volume spike')
            if indicators.latest('price_above_vwap', False):
                factors.append('Price above VWAP')
            if indicators.latest('trend_bullish', False):
                factors.append('Bullish trend')
            if indicators.latest('momentum_bullish', False):
                factors.append('Positive momentum')
            if indicators.latest('volume_consistent', False):
                factors.append('Consistent volume')
        else:
            if indicators.latest('volume_spike', False):
                factors.append('Volume spike')
            if indicators.latest('price_below_vwap', False):
                factors.append('Price below VWAP')
            if indicators.latest('trend_bearish', False):
                factors.append('Bearish trend')
            if indicators.latest('momentum_bearish', False):
                factors.append('Negative momentum')
            if indicators.latest('volume_consistent', False):
                factors.append('Consistent volume')
        return factors

    def generate(self, df: pd.DataFrame, indicators: StrategyIndicators,
                 current_price: float, market_analysis: Dict[str, Any]) -> SignalDecision:
        bullish = bool(indicators.latest('bullish_setup', False))
        bearish = bool(indicators.latest('bearish_setup', False))

        signal_type: Optional[str] = None
        if bullish and not bearish:
            signal_type = 'BUY'
        elif bearish and not bullish:
            signal_type = 'SELL'
        elif bullish and bearish:
            buy_strength = self._strength(indicators, 'BUY')
            sell_strength = self._strength(indicators, 'SELL')
            if buy_strength > sell_strength:
                signal_type = 'BUY'
            elif sell_strength > buy_strength:
                signal_type = 'SELL'

        if signal_type is None:
            return SignalDecision(signal=None, confidence=0.0)

        confidence = self._strength(indicators, signal_type)
        if confidence < getattr(self.ctx, 'min_signal_strength', 0.3):
            return SignalDecision(signal=None, confidence=confidence)

        confluence = self._confluence(indicators, signal_type)
        if not confluence:
            return SignalDecision(signal=None, confidence=confidence)

        snapshot = indicators.snapshot([
            'volume_ratio',
            'rsi',
            'price_momentum',
            'vwap',
            'trend_strength',
        ])

        context = {
            'indicators': snapshot,
            'market_analysis': market_analysis,
            'current_price': current_price,
        }

        return SignalDecision(
            signal=signal_type,
            confidence=confidence,
            confluence=confluence,
            rationale=[f"market_condition={market_analysis.get('condition', 'unknown')}"],
            context=context,
        )


class VolumeVwapPositionSizer(PositionSizer):
    def __init__(self, config: Any, round_price_fn):
        self.round_price = round_price_fn
        self.ctx = VolumeContext(
            volume_multiplier=getattr(config, 'volume_multiplier', 2.0),
            volume_sma_period=getattr(config, 'volume_sma_period', 20),
            volume_trend_window=getattr(config, 'volume_trend_window', 10),
            min_volume_consistency=getattr(config, 'min_volume_consistency', 3),
            vwap_deviation_threshold=getattr(config, 'vwap_deviation_threshold', 0.002),
            vwap_confirmation_bars=getattr(config, 'vwap_confirmation_bars', 3),
            trend_period=getattr(config, 'trend_period', 50),
            min_trend_slope=getattr(config, 'min_trend_slope', 0.0005),
            price_momentum_period=getattr(config, 'price_momentum_period', 5),
            volume_momentum_period=getattr(config, 'volume_momentum_period', 5),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 0.8),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            # ✅ NEW: Market Context parameters
            use_market_context=getattr(config, 'use_market_context', True),
            use_liquidity_targets=getattr(config, 'use_liquidity_targets', True),
            use_session_stops=getattr(config, 'use_session_stops', True),
            min_context_confidence=getattr(config, 'min_context_confidence', 0.3),
        )

        # ✅ NEW: Market Context Engine initialization
        self.market_engine = None
        if MARKET_CONTEXT_AVAILABLE and self.ctx.use_market_context:
            try:
                self.market_engine = MarketContextEngine()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to initialize Market Context Engine: {e}")

    def plan(self, decision: SignalDecision, df: pd.DataFrame,
             current_price: float) -> PositionPlan:
        if not decision.is_actionable:
            return PositionPlan(side=None)

        entry_price = self.round_price(current_price)

        # ✅ NEW: Market Context-aware position sizing
        market_ctx = None
        if self.market_engine is not None:
            try:
                market_ctx = self.market_engine.get_context(
                    df=df,
                    current_price=current_price,
                    signal_direction=decision.signal
                )

                # Check if trading is allowed in current context
                can_trade, reason = market_ctx.should_trade()
                if not can_trade:
                    return PositionPlan(
                        side=None,
                        metadata={
                            'reject_reason': f'Market context filter: {reason}',
                            'context': market_ctx.to_dict()
                        }
                    )

                # Check confidence threshold
                if market_ctx.risk_params.confidence < self.ctx.min_context_confidence:
                    return PositionPlan(
                        side=None,
                        metadata={
                            'reject_reason': 'Context confidence below threshold',
                            'confidence': market_ctx.risk_params.confidence,
                            'min_confidence': self.ctx.min_context_confidence
                        }
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Market Context error, using legacy logic: {e}")
                market_ctx = None

        # Calculate ATR for stop/target calculation
        atr_result = TechnicalIndicators.calculate_atr_safe(df, 14)
        atr = atr_result.last_value if atr_result and atr_result.is_valid else current_price * 0.01

        # ✅ Context-aware stops and targets (with graceful fallback)
        if market_ctx is not None and self.ctx.use_session_stops:
            stop_loss = market_ctx.get_stop_loss(entry_price, atr, decision.signal)
            if self.ctx.use_liquidity_targets:
                take_profit = market_ctx.get_take_profit(entry_price, atr, decision.signal)
            else:
                # Use context stop but legacy target
                stop_loss_raw, take_profit = self._calculate_levels(df, entry_price, decision.signal)
        else:
            # Legacy calculation
            stop_loss, take_profit = self._calculate_levels(df, entry_price, decision.signal)

        if decision.signal == 'BUY':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            side = 'Buy'
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
            side = 'Sell'

        actual_rr = reward / risk if risk > 0 else 0.0

        # ✅ Adaptive R/R threshold
        min_rr = self.ctx.min_risk_reward_ratio
        if market_ctx is not None:
            # Use context's recommended R/R as baseline
            min_rr = max(min_rr, market_ctx.risk_params.risk_reward_ratio * 0.6)

        if actual_rr < min_rr:
            return PositionPlan(side=None, metadata={'reject_reason': 'R/R below threshold', 'risk_reward': actual_rr})

        # ✅ Adaptive position sizing
        base_size = max(self.ctx.trade_amount, self.ctx.min_trade_amount)
        if market_ctx is not None:
            size = market_ctx.get_position_size(base_size)
        else:
            size = base_size

        metadata = {
            'risk_reward': actual_rr,
            'trade_amount': size,
            'decision_context': decision.context,
        }

        # ✅ Add Market Context metadata
        if market_ctx is not None:
            metadata.update({
                'market_regime': market_ctx.risk_params.market_regime.value,
                'session': market_ctx.session.name.value,
                'confidence': market_ctx.risk_params.confidence,
                'stop_multiplier': market_ctx.risk_params.stop_loss_atr_mult,
                'volatility_regime': market_ctx.risk_params.volatility_regime.value,
                'liquidity_levels': len(market_ctx.liquidity.buy_side_liquidity) + len(market_ctx.liquidity.sell_side_liquidity),
                'market_context_used': True
            })
        else:
            metadata['market_context_used'] = False

        if size > self.ctx.trade_amount:
            metadata['min_size_applied'] = True
            metadata['original_trade_amount'] = self.ctx.trade_amount

        return PositionPlan(
            side=side,
            size=size,
            entry_price=entry_price,
            stop_loss=self.round_price(stop_loss),
            take_profit=self.round_price(take_profit),
            risk_reward=actual_rr,
            metadata=metadata,
        )

    def _calculate_levels(self, df: pd.DataFrame, entry_price: float, signal_type: str) -> tuple[float, float]:
        atr_period = 14
        atr_result = TechnicalIndicators.calculate_atr_safe(df, atr_period)
        atr = atr_result.last_value if atr_result and atr_result.is_valid else None
        if not atr or atr <= 0:
            atr = entry_price * 0.01

        rr = getattr(self.ctx, 'risk_reward_ratio', 1.5)
        stop_multiplier = 1.5
        take_multiplier = stop_multiplier * rr

        if signal_type == 'BUY':
            stop_loss = entry_price - (atr * stop_multiplier)
            take_profit = entry_price + (atr * take_multiplier)
        else:
            stop_loss = entry_price + (atr * stop_multiplier)
            take_profit = entry_price - (atr * take_multiplier)

        return float(stop_loss), float(take_profit)
