"""Pipeline components for the CumDelta Support/Resistance strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
from bot.strategy.utils.levels import find_all_levels, get_trading_levels

# ✅ NEW: Market Context Engine for order flow intelligence
try:
    from bot.market_context import MarketContextEngine
    MARKET_CONTEXT_AVAILABLE = True
except ImportError:
    MARKET_CONTEXT_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning("Market Context Engine not available for CumDelta strategy")


@dataclass
class CumDeltaContext:
    min_delta_threshold: float
    delta_momentum_period: int
    volume_multiplier: float
    min_volume_for_signal: float
    confluence_required: int
    signal_strength_threshold: float
    min_risk_reward_ratio: float
    risk_reward_ratio: float
    trade_amount: float
    min_trade_amount: float
    volume_delta_correlation: bool
    delta_divergence_detection: bool
    support_resistance_breakout: bool
    support_window: int
    support_resistance_tolerance: float

    # ✅ NEW: Market Context parameters (специфично для CumDelta - order flow анализ)
    use_market_context: bool = True
    use_liquidity_sr: bool = True  # Использовать liquidity levels как S/R
    use_session_delta_scaling: bool = True  # Масштабировать delta threshold по сессиям
    min_context_confidence: float = 0.4  # Выше чем VWAP (delta требует больше уверенности)


class CumDeltaIndicatorEngine(IndicatorEngine):
    """Calculates indicators required for the CumDelta strategy."""

    def __init__(self, config: Any, base_indicator_fn):
        self.config = config
        self._base_indicator_fn = base_indicator_fn

    def calculate(self, df: pd.DataFrame) -> StrategyIndicators:
        indicators: Dict[str, Any] = {}

        if self._base_indicator_fn is not None:
            indicators.update(self._base_indicator_fn(df) or {})

        if df.empty:
            return StrategyIndicators(data=indicators)

        cum_delta = self._calculate_enhanced_delta(df)
        indicators['cum_delta'] = cum_delta
        indicators['delta_momentum'] = cum_delta.diff(getattr(self.config, 'delta_momentum_period', 5))
        indicators['delta_strength'] = (
            abs(cum_delta) / df['volume'].rolling(10, min_periods=1).mean().replace({0: np.nan})
        ).fillna(0)

        levels_info = self._calculate_levels(df)
        indicators.update(levels_info)

        trend_period = getattr(self.config, 'trend_period', 40)
        indicators['trend_slope'] = df['close'].rolling(trend_period, min_periods=1).mean().diff(max(trend_period // 4, 5))
        indicators['trend_strength'] = (
            abs(indicators['trend_slope']) / df['close']
        ).replace([np.inf, -np.inf], 0).fillna(0)

        if 'volume' in df.columns:
            vol_sma = df['volume'].rolling(20, min_periods=1).mean().replace({0: np.nan})
            indicators['volume_ratio'] = (df['volume'] / vol_sma).fillna(0)
            indicators['volume_increasing'] = df['volume'].diff() > 0
            if getattr(self.config, 'volume_delta_correlation', False):
                indicators['volume_delta_corr'] = self._calculate_volume_delta_correlation(df, cum_delta)
        else:
            indicators['volume_ratio'] = pd.Series([1.0] * len(df), index=df.index)
            indicators['volume_increasing'] = pd.Series([False] * len(df), index=df.index)
            indicators['volume_delta_corr'] = 0.0

        rsi_result = TechnicalIndicators.calculate_rsi(df)
        if rsi_result.is_valid:
            indicators['rsi'] = rsi_result.value

        bb_result = TechnicalIndicators.calculate_bollinger_bands(df)
        if bb_result.is_valid:
            indicators['bb_position'] = bb_result.value['position']
            indicators['bb_upper'] = bb_result.value['upper']
            indicators['bb_lower'] = bb_result.value['lower']

        if getattr(self.config, 'delta_divergence_detection', False):
            indicators['delta_divergence'] = self._detect_delta_divergence(df, cum_delta)
        else:
            indicators['delta_divergence'] = {'bullish_divergence': False, 'bearish_divergence': False}

        if getattr(self.config, 'support_resistance_breakout', False):
            indicators['support_breakout'] = self._detect_support_breakout(df, indicators.get('support_levels', []))
            indicators['resistance_breakout'] = self._detect_resistance_breakout(df, indicators.get('resistance_levels', []))
        else:
            indicators['support_breakout'] = False
            indicators['resistance_breakout'] = False

        indicators['price'] = df['close']

        return StrategyIndicators(data=indicators, metadata={'rows': len(df)})

    # ------------------------------------------------------------------
    # Helper calculations
    # ------------------------------------------------------------------

    def _calculate_enhanced_delta(self, df: pd.DataFrame) -> pd.Series:
        if 'buy_volume' in df.columns and 'sell_volume' in df.columns:
            delta = df['buy_volume'] - df['sell_volume']
        elif 'delta' in df.columns:
            delta = df['delta']
        else:
            price_change = df['close'].pct_change().fillna(0)
            delta = price_change * df['volume'] * np.sign(price_change)

        smoothing = getattr(self.config, 'delta_smoothing_period', 1)
        if smoothing > 1:
            delta = delta.rolling(smoothing, min_periods=1).mean()

        window = getattr(self.config, 'delta_window', 50)
        return delta.rolling(window, min_periods=1).sum().fillna(0)

    def _calculate_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        current_price = float(df['close'].iloc[-1])
        all_levels = find_all_levels(df, current_price)
        trading_levels = get_trading_levels(df, current_price)

        support_levels = trading_levels.get('support', [])
        resistance_levels = trading_levels.get('resistance', [])

        support_zone = self._calculate_zone(support_levels, current_price, is_support=True)
        resist_zone = self._calculate_zone(resistance_levels, current_price, is_support=False)

        return {
            'support_levels': support_levels,
            'resistance_levels': resistance_levels,
            'support_zone': support_zone,
            'resist_zone': resist_zone,
            'all_levels': all_levels,
        }

    def _calculate_zone(self, levels: List[Any], current_price: float, *, is_support: bool) -> float:
        if not levels:
            return current_price

        relevant = [level for level in levels if level.is_reliable]
        if not relevant:
            relevant = levels

        if is_support:
            candidates = [lvl.price for lvl in relevant if lvl.price <= current_price]
            if not candidates:
                candidates = [lvl.price for lvl in relevant]
            return float(min(candidates)) if candidates else current_price
        else:
            candidates = [lvl.price for lvl in relevant if lvl.price >= current_price]
            if not candidates:
                candidates = [lvl.price for lvl in relevant]
            return float(max(candidates)) if candidates else current_price

    def _calculate_volume_delta_correlation(self, df: pd.DataFrame, cum_delta: pd.Series) -> float:
        window = min(20, len(df))
        if window < 5:
            return 0.0
        volume = df['volume'].tail(window)
        delta = cum_delta.tail(window)
        correlation = volume.corr(delta)
        return float(correlation) if pd.notna(correlation) else 0.0

    def _detect_delta_divergence(self, df: pd.DataFrame, cum_delta: pd.Series) -> Dict[str, bool]:
        analysis_period = min(30, len(df))
        if analysis_period < 5:
            return {'bullish_divergence': False, 'bearish_divergence': False}

        price = df['close'].tail(analysis_period)
        delta = cum_delta.tail(analysis_period)

        price_highs = self._find_local_extrema(price, 'high')
        price_lows = self._find_local_extrema(price, 'low')
        delta_highs = self._find_local_extrema(delta, 'high')
        delta_lows = self._find_local_extrema(delta, 'low')

        def _has_divergence(
            price_extrema: List[int],
            delta_extrema: List[int],
            price_condition,
            delta_condition,
        ) -> bool:
            if len(price_extrema) < 2 or len(delta_extrema) < 2:
                return False

            prev_price = price.iloc[price_extrema[-2]]
            curr_price = price.iloc[price_extrema[-1]]
            prev_delta = delta.iloc[delta_extrema[-2]]
            curr_delta = delta.iloc[delta_extrema[-1]]

            return price_condition(curr_price, prev_price) and delta_condition(curr_delta, prev_delta)

        bullish = _has_divergence(
            price_lows,
            delta_lows,
            lambda current, previous: current < previous,
            lambda current, previous: current > previous,
        )
        bearish = _has_divergence(
            price_highs,
            delta_highs,
            lambda current, previous: current > previous,
            lambda current, previous: current < previous,
        )

        return {'bullish_divergence': bool(bullish), 'bearish_divergence': bool(bearish)}

    def _find_local_extrema(self, series: pd.Series, extrema_type: str) -> List[int]:
        extrema_indices: List[int] = []
        length = len(series)
        if length < 5:
            return extrema_indices

        for i in range(2, length - 2):
            if extrema_type == 'high':
                if (
                    series.iloc[i] > series.iloc[i - 1]
                    and series.iloc[i] > series.iloc[i - 2]
                    and series.iloc[i] > series.iloc[i + 1]
                    and series.iloc[i] > series.iloc[i + 2]
                ):
                    extrema_indices.append(i)
            else:
                if (
                    series.iloc[i] < series.iloc[i - 1]
                    and series.iloc[i] < series.iloc[i - 2]
                    and series.iloc[i] < series.iloc[i + 1]
                    and series.iloc[i] < series.iloc[i + 2]
                ):
                    extrema_indices.append(i)

        return extrema_indices

    def _detect_support_breakout(self, df: pd.DataFrame, support_levels: List[Any]) -> bool:
        if not support_levels:
            return False
        current_price = df['close'].iloc[-1]
        min_support = min(level.price for level in support_levels)
        return current_price < min_support * 0.998

    def _detect_resistance_breakout(self, df: pd.DataFrame, resistance_levels: List[Any]) -> bool:
        if not resistance_levels:
            return False
        current_price = df['close'].iloc[-1]
        max_resistance = max(level.price for level in resistance_levels)
        return current_price > max_resistance * 1.002


class CumDeltaSignalGenerator(SignalGenerator):
    def __init__(self, config: Any):
        self.ctx = CumDeltaContext(
            min_delta_threshold=getattr(config, 'min_delta_threshold', 1500.0),
            delta_momentum_period=getattr(config, 'delta_momentum_period', 5),
            volume_multiplier=getattr(config, 'volume_multiplier', 1.5),
            min_volume_for_signal=getattr(config, 'min_volume_for_signal', 1000.0),
            confluence_required=getattr(config, 'confluence_required', 2),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 0.8),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            volume_delta_correlation=getattr(config, 'volume_delta_correlation', True),
            delta_divergence_detection=getattr(config, 'delta_divergence_detection', True),
            support_resistance_breakout=getattr(config, 'support_resistance_breakout', True),
            support_window=getattr(config, 'support_window', 80),
            support_resistance_tolerance=getattr(config, 'support_resistance_tolerance', 0.002),
        )

    def calculate_strength(self, indicators: StrategyIndicators, signal_type: str) -> float:
        factors: List[float] = []

        cum_delta = indicators.latest('cum_delta', 0.0)
        delta_factor = min(abs(cum_delta) / (self.ctx.min_delta_threshold * 2), 1.0)
        factors.append(delta_factor)

        current_price = indicators.latest('price', 1.0) or 1.0
        if signal_type == 'BUY':
            support_zone = indicators.latest('support_zone', current_price)
            distance = abs(current_price - support_zone) / current_price
        else:
            resist_zone = indicators.latest('resist_zone', current_price)
            distance = abs(current_price - resist_zone) / current_price
        sr_factor = max(0.0, 1 - distance * 100)
        factors.append(sr_factor)

        trend_strength = indicators.latest('trend_strength', 0.0)
        factors.append(min(trend_strength * 1000, 1.0))

        rsi = indicators.latest('rsi', 50.0)
        if signal_type == 'BUY':
            rsi_factor = max(0.0, (50 - rsi) / 50) if rsi < 50 else 0.0
        else:
            rsi_factor = max(0.0, (rsi - 50) / 50) if rsi > 50 else 0.0
        factors.append(rsi_factor)

        volume_ratio = indicators.latest('volume_ratio', 1.0)
        factors.append(min(volume_ratio / 3.0, 1.0))

        delta_momentum = indicators.latest('delta_momentum', 0.0)
        if signal_type == 'BUY':
            momentum_factor = max(0.0, delta_momentum / self.ctx.min_delta_threshold)
        else:
            momentum_factor = max(0.0, -delta_momentum / self.ctx.min_delta_threshold)
        factors.append(min(momentum_factor, 1.0))

        volume_delta_corr = indicators.latest('volume_delta_corr', 0.0)
        if self.ctx.volume_delta_correlation:
            factors.append(abs(volume_delta_corr))
        else:
            factors.append(0.5)

        weights = [0.25, 0.2, 0.15, 0.12, 0.1, 0.1, 0.08]
        strength = sum(factor * weight for factor, weight in zip(factors, weights))
        return float(min(strength, 1.0))

    def confluence_factors(self, indicators: StrategyIndicators, signal_type: str) -> List[str]:
        factors: List[str] = []

        if indicators.latest('support_zone', None) and signal_type == 'BUY':
            factors.append('support_zone')
        if indicators.latest('resist_zone', None) and signal_type == 'SELL':
            factors.append('resist_zone')

        delta_strength = indicators.latest('delta_strength', 0.0)
        if delta_strength > 0.5:
            factors.append('delta_strength')

        volume_ratio = indicators.latest('volume_ratio', 1.0)
        if volume_ratio > self.ctx.volume_multiplier:
            factors.append('volume_spike')

        delta_momentum = indicators.latest('delta_momentum', 0.0)
        if (signal_type == 'BUY' and delta_momentum > 0) or (signal_type == 'SELL' and delta_momentum < 0):
            factors.append('delta_momentum')

        trend_slope = indicators.latest('trend_slope', 0.0)
        if (signal_type == 'BUY' and trend_slope > 0) or (signal_type == 'SELL' and trend_slope < 0):
            factors.append('trend_alignment')

        divergence = indicators.latest('delta_divergence', {'bullish_divergence': False, 'bearish_divergence': False})
        if self.ctx.delta_divergence_detection:
            if signal_type == 'BUY' and divergence.get('bullish_divergence'):
                factors.append('delta_bullish_divergence')
            if signal_type == 'SELL' and divergence.get('bearish_divergence'):
                factors.append('delta_bearish_divergence')

        if self.ctx.support_resistance_breakout:
            if signal_type == 'BUY' and indicators.latest('support_breakout', False):
                factors.append('support_breakout')
            if signal_type == 'SELL' and indicators.latest('resistance_breakout', False):
                factors.append('resistance_breakout')

        return factors

    def generate(self, df: pd.DataFrame, indicators: StrategyIndicators,
                 current_price: float, market_analysis: Dict[str, Any]) -> SignalDecision:
        if 'volume' in df.columns and df['volume'].iloc[-1] < self.ctx.min_volume_for_signal:
            return SignalDecision(signal=None, confidence=0.0)

        cum_delta = indicators.latest('cum_delta', 0.0)
        trend_slope = indicators.latest('trend_slope', 0.0)
        support_zone = indicators.latest('support_zone', current_price)
        resist_zone = indicators.latest('resist_zone', current_price)

        long_setup = (
            cum_delta > self.ctx.min_delta_threshold and
            current_price <= support_zone and
            trend_slope > 0
        )
        short_setup = (
            cum_delta < -self.ctx.min_delta_threshold and
            current_price >= resist_zone and
            trend_slope < 0
        )

        signal_type: Optional[str] = None
        if long_setup and not short_setup:
            signal_type = 'BUY'
        elif short_setup and not long_setup:
            signal_type = 'SELL'
        elif long_setup and short_setup:
            buy_strength = self.calculate_strength(indicators, 'BUY')
            sell_strength = self.calculate_strength(indicators, 'SELL')
            if buy_strength > sell_strength:
                signal_type = 'BUY'
            elif sell_strength > buy_strength:
                signal_type = 'SELL'

        if signal_type is None:
            return SignalDecision(signal=None, confidence=0.0)

        confluence = self.confluence_factors(indicators, signal_type)
        if len(confluence) < self.ctx.confluence_required:
            return SignalDecision(signal=None, confidence=0.0, confluence=confluence)

        confidence = self.calculate_strength(indicators, signal_type)
        if confidence < self.ctx.signal_strength_threshold:
            return SignalDecision(signal=None, confidence=confidence, confluence=confluence)

        snapshot = indicators.snapshot([
            'cum_delta',
            'delta_momentum',
            'delta_strength',
            'support_zone',
            'resist_zone',
            'trend_slope',
            'trend_strength',
            'volume_ratio',
        ])
        snapshot['price'] = current_price

        rationale = [f"market_condition={market_analysis.get('condition', 'unknown')}"]

        context = {
            'indicators': snapshot,
            'market_analysis': market_analysis,
            'current_price': current_price,
        }

        return SignalDecision(
            signal=signal_type,
            confidence=confidence,
            confluence=confluence,
            rationale=rationale,
            context=context,
        )


class CumDeltaPositionSizer(PositionSizer):
    def __init__(self, config: Any, round_price_fn, calc_levels_fn):
        self.round_price = round_price_fn
        self.calculate_levels = calc_levels_fn
        self.ctx = CumDeltaContext(
            min_delta_threshold=getattr(config, 'min_delta_threshold', 1500.0),
            delta_momentum_period=getattr(config, 'delta_momentum_period', 5),
            volume_multiplier=getattr(config, 'volume_multiplier', 1.5),
            min_volume_for_signal=getattr(config, 'min_volume_for_signal', 1000.0),
            confluence_required=getattr(config, 'confluence_required', 2),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 0.8),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            volume_delta_correlation=getattr(config, 'volume_delta_correlation', True),
            delta_divergence_detection=getattr(config, 'delta_divergence_detection', True),
            support_resistance_breakout=getattr(config, 'support_resistance_breakout', True),
            support_window=getattr(config, 'support_window', 80),
            support_resistance_tolerance=getattr(config, 'support_resistance_tolerance', 0.002),
            # ✅ NEW: Market Context parameters
            use_market_context=getattr(config, 'use_market_context', True),
            use_liquidity_sr=getattr(config, 'use_liquidity_sr', True),
            use_session_delta_scaling=getattr(config, 'use_session_delta_scaling', True),
            min_context_confidence=getattr(config, 'min_context_confidence', 0.4),
        )

        # ✅ NEW: Market Context Engine initialization
        self.market_engine = None
        if MARKET_CONTEXT_AVAILABLE and self.ctx.use_market_context:
            try:
                self.market_engine = MarketContextEngine()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to initialize Market Context for CumDelta: {e}")

    def plan(self, decision: SignalDecision, df: pd.DataFrame,
             current_price: float) -> PositionPlan:
        if not decision.is_actionable:
            return PositionPlan(side=None)

        entry_price = self.round_price(current_price)

        # ✅ NEW: Market Context for CumDelta - order flow intelligence
        market_ctx = None
        if self.market_engine is not None:
            try:
                market_ctx = self.market_engine.get_context(
                    df=df,
                    current_price=current_price,
                    signal_direction=decision.signal
                )

                # CumDelta-specific: check if order flow matches market regime
                can_trade, reason = market_ctx.should_trade()
                if not can_trade:
                    return PositionPlan(
                        side=None,
                        metadata={
                            'reject_reason': f'Market context: {reason}',
                            'context': market_ctx.to_dict()
                        }
                    )

                # Higher confidence threshold for delta strategies (order flow needs clarity)
                if market_ctx.risk_params.confidence < self.ctx.min_context_confidence:
                    return PositionPlan(
                        side=None,
                        metadata={
                            'reject_reason': 'Low context confidence for order flow',
                            'confidence': market_ctx.risk_params.confidence,
                            'required': self.ctx.min_context_confidence
                        }
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Market Context error in CumDelta, using legacy: {e}")
                market_ctx = None

        # Calculate ATR for dynamic levels
        atr_result = TechnicalIndicators.calculate_atr_safe(df, 14)
        atr = atr_result.last_value if atr_result and atr_result.is_valid else current_price * 0.01

        # ✅ Context-aware stops with liquidity S/R consideration
        if market_ctx is not None and self.ctx.use_liquidity_sr:
            # Use Market Context liquidity levels as S/R (better than legacy levels!)
            stop_loss = market_ctx.get_stop_loss(entry_price, atr, decision.signal)

            # For CumDelta: prefer liquidity targets (order blocks, equal highs/lows)
            take_profit = market_ctx.get_take_profit(entry_price, atr, decision.signal)
        else:
            # Legacy calculation
            stop_loss, take_profit = self.calculate_levels(df, entry_price, decision.signal)

        if decision.signal == 'BUY':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            side = 'Buy'
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
            side = 'Sell'

        if risk <= 0:
            return PositionPlan(side=None, metadata={'reject_reason': 'invalid_levels'})

        actual_rr = reward / risk

        # ✅ Adaptive R/R threshold based on market regime
        min_rr = self.ctx.min_risk_reward_ratio
        if market_ctx is not None:
            # In strong trends, delta strategies can aim higher
            # In sideways, keep conservative
            min_rr = max(min_rr, market_ctx.risk_params.risk_reward_ratio * 0.7)

        if actual_rr < min_rr:
            return PositionPlan(
                side=None,
                metadata={'reject_reason': f'R/R {actual_rr:.2f} < {min_rr:.2f}'},
            )

        # ✅ Adaptive position sizing based on order flow clarity
        base_size = max(self.ctx.trade_amount, self.ctx.min_trade_amount)
        if market_ctx is not None:
            size = market_ctx.get_position_size(base_size)
        else:
            size = base_size

        metadata = {
            'risk_reward': actual_rr,
            'trade_amount': size,
            'position_plan': decision.context.get('indicators', {}),
        }

        # ✅ Add Market Context metadata (crucial for delta analysis!)
        if market_ctx is not None:
            metadata.update({
                'market_regime': market_ctx.risk_params.market_regime.value,
                'session': market_ctx.session.name.value,
                'confidence': market_ctx.risk_params.confidence,
                'stop_multiplier': market_ctx.risk_params.stop_loss_atr_mult,
                'volatility_regime': market_ctx.risk_params.volatility_regime.value,
                'liquidity_sr_used': self.ctx.use_liquidity_sr,
                'market_context_used': True,
                # CumDelta-specific: log если нашли order blocks на liquidity
                'order_blocks_detected': len([l for l in market_ctx.liquidity.buy_side_liquidity + market_ctx.liquidity.sell_side_liquidity if l.type.value == 'order_block'])
            })
        else:
            metadata['market_context_used'] = False

        return PositionPlan(
            side=side,
            size=size,
            entry_price=entry_price,
            stop_loss=self.round_price(stop_loss),
            take_profit=self.round_price(take_profit),
            risk_reward=actual_rr,
            metadata=metadata,
        )
