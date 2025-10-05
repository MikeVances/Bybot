"""Pipeline components for the multi-timeframe volume strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List

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


# ✅ NEW: Market Context Engine
try:
    from bot.market_context import MarketContextEngine
    MARKET_CONTEXT_AVAILABLE = True
except ImportError:
    MARKET_CONTEXT_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning("Market Context Engine not available for multitf_volume strategy")



@dataclass
class MultiTFContext:
    fast_tf: str
    slow_tf: str
    fast_window: int
    slow_window: int
    volume_multiplier: float
    volume_trend_window: int
    trend_strength_threshold: float
    signal_strength_threshold: float
    confluence_required: int
    trade_amount: float
    min_trade_amount: float
    risk_reward_ratio: float
    min_risk_reward_ratio: float
    momentum_analysis: bool
    mtf_divergence_detection: bool




    # ✅ NEW: Market Context parameters (специфично для multitf_volume)
    use_market_context: bool = True
    use_market_context: bool = True  # 
    use_session_filtering: bool = True  # 
    require_tf_regime_match: bool = True  # 
    min_context_confidence: float = 0.35  # 


class MultiTFIndicatorEngine(IndicatorEngine):
    """Calculates indicators on fast and slow timeframes."""

    def __init__(self, config: Any, base_indicator_fn):
        self.config = config
        self._base_indicator_fn = base_indicator_fn
        self.ctx = MultiTFContext(
            fast_tf=getattr(config.fast_tf, 'value', '5m'),
            slow_tf=getattr(config.slow_tf, 'value', '1h'),
            fast_window=getattr(config, 'fast_window', 24),
            slow_window=getattr(config, 'slow_window', 48),
            volume_multiplier=getattr(config, 'volume_multiplier', 2.5),
            volume_trend_window=getattr(config, 'volume_trend_window', 12),
            trend_strength_threshold=getattr(config, 'trend_strength_threshold', 0.002),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            confluence_required=getattr(config, 'confluence_required', 2),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 1.0),
            momentum_analysis=getattr(config, 'momentum_analysis', True),
            mtf_divergence_detection=getattr(config, 'mtf_divergence_detection', True),
        )

    def calculate(self, market_data: Any) -> StrategyIndicators:
        df_fast, df_slow = self._extract_timeframes(market_data)
        indicators: Dict[str, Any] = {}

        if self._base_indicator_fn is not None:
            indicators.update(self._base_indicator_fn(df_fast) or {})

        fast_trend = self._calculate_trend(df_fast, self.ctx.fast_window, advanced=getattr(self.config, 'advanced_trend_analysis', True))
        slow_trend = self._calculate_trend(df_slow, self.ctx.slow_window, advanced=getattr(self.config, 'advanced_trend_analysis', True))
        indicators.update({
            'fast_trend': fast_trend,
            'slow_trend': slow_trend,
        })

        volume_info = self._calculate_volume(df_fast)
        indicators.update(volume_info)

        indicators['trends_aligned_bullish'] = fast_trend['price_above_sma'] and slow_trend['price_above_sma']
        indicators['trends_aligned_bearish'] = (not fast_trend['price_above_sma']) and (not slow_trend['price_above_sma'])

        fast_momentum = df_fast['close'].pct_change(5).iloc[-1]
        slow_momentum = df_slow['close'].pct_change(3).iloc[-1]
        indicators['momentum_alignment'] = bool(np.sign(fast_momentum) == np.sign(slow_momentum))
        indicators['fast_momentum'] = fast_momentum
        indicators['slow_momentum'] = slow_momentum

        if self.ctx.momentum_analysis:
            indicators['momentum_analysis'] = self._calculate_momentum_metrics(df_fast, df_slow)

        if self.ctx.mtf_divergence_detection:
            indicators['mtf_divergence'] = self._detect_mtf_divergence(df_fast, df_slow)
        else:
            indicators['mtf_divergence'] = {'bullish': False, 'bearish': False}

        indicators['price'] = df_fast['close']
        indicators['slow_trend_strength'] = slow_trend['trend_strength']

        return StrategyIndicators(data=indicators, metadata={'rows': len(df_fast)})

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _extract_timeframes(self, market_data: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
        if isinstance(market_data, dict):
            df_fast = market_data.get(self.ctx.fast_tf)
            df_slow = market_data.get(self.ctx.slow_tf)
            if df_fast is None or df_slow is None:
                raise ValueError('Недостаточно данных для мультитаймфрейм анализа')
        else:
            df_fast = market_data
            df_slow = market_data
        return df_fast, df_slow

    def _calculate_trend(self, df: pd.DataFrame, window: int, *, advanced: bool) -> Dict[str, Any]:
        try:
            sma = df['close'].rolling(window, min_periods=1).mean()
            price_above_sma = bool(df['close'].iloc[-1] > sma.iloc[-1])
            trend_slope = sma.diff(5)
            trend_strength = abs(trend_slope.iloc[-1] / df['close'].iloc[-1]) if len(trend_slope) else 0.0

            result = {
                'sma': sma,
                'price_above_sma': price_above_sma,
                'trend_strength': trend_strength,
            }

            if advanced:
                ema = df['close'].ewm(span=window, min_periods=1).mean()
                trend_volatility = df['close'].pct_change().rolling(window).std().iloc[-1]
                result.update({
                    'ema': ema,
                    'trend_slope': trend_slope,
                    'trend_volatility': trend_volatility,
                })
            return result
        except Exception:
            return {'sma': df['close'], 'price_above_sma': False, 'trend_strength': 0.0}

    def _calculate_volume(self, df: pd.DataFrame) -> Dict[str, Any]:
        if 'volume' not in df.columns:
            return {'volume_ratio': pd.Series([1.0] * len(df), index=df.index), 'volume_spike': False, 'volume_increasing': False}

        vol_sma = df['volume'].rolling(20, min_periods=1).mean().replace({0: np.nan})
        volume_ratio = (df['volume'] / vol_sma).fillna(0)
        volume_spike = bool(volume_ratio.iloc[-1] > self.ctx.volume_multiplier)
        volume_trend = df['volume'].rolling(self.ctx.volume_trend_window, min_periods=1).mean().diff()
        volume_increasing = bool(volume_trend.iloc[-1] > 0) if len(volume_trend) else False

        high_volume_mask = volume_ratio > self.ctx.volume_multiplier
        consistency = getattr(self.config, 'min_volume_consistency', 3)
        volume_consistent = bool(high_volume_mask.rolling(consistency).sum().fillna(0).iloc[-1] >= consistency)

        return {
            'volume_ratio': volume_ratio,
            'volume_spike': volume_spike,
            'volume_increasing': volume_increasing,
            'volume_consistent': volume_consistent,
        }

    def _calculate_momentum_metrics(self, df_fast: pd.DataFrame, df_slow: pd.DataFrame) -> Dict[str, float]:
        fast_momentum = df_fast['close'].pct_change(5).iloc[-1]
        slow_momentum = df_slow['close'].pct_change(5).iloc[-1]
        return {
            'fast_momentum': fast_momentum,
            'slow_momentum': slow_momentum,
            'momentum_alignment': np.sign(fast_momentum) == np.sign(slow_momentum),
        }

    def _detect_mtf_divergence(self, df_fast: pd.DataFrame, df_slow: pd.DataFrame) -> Dict[str, bool]:
        try:
            fast_price = df_fast['close'].tail(30)
            slow_price = df_slow['close'].tail(30)

            fast_highs = self._find_local_extrema(fast_price, 'high')
            fast_lows = self._find_local_extrema(fast_price, 'low')
            slow_highs = self._find_local_extrema(slow_price, 'high')
            slow_lows = self._find_local_extrema(slow_price, 'low')

            bullish = bool(fast_lows and slow_lows and fast_lows[-1] < fast_lows[-2] and slow_lows[-1] > slow_lows[-2])
            bearish = bool(fast_highs and slow_highs and fast_highs[-1] > fast_highs[-2] and slow_highs[-1] < slow_highs[-2])
            return {'bullish': bullish, 'bearish': bearish}
        except Exception:
            return {'bullish': False, 'bearish': False}

    def _find_local_extrema(self, series: pd.Series, extrema_type: str) -> List[int]:
        indices: List[int] = []
        length = len(series)
        if length < 5:
            return indices
        for i in range(2, length - 2):
            if extrema_type == 'high':
                if (
                    series.iloc[i] > series.iloc[i - 1]
                    and series.iloc[i] > series.iloc[i - 2]
                    and series.iloc[i] > series.iloc[i + 1]
                    and series.iloc[i] > series.iloc[i + 2]
                ):
                    indices.append(i)
            else:
                if (
                    series.iloc[i] < series.iloc[i - 1]
                    and series.iloc[i] < series.iloc[i - 2]
                    and series.iloc[i] < series.iloc[i + 1]
                    and series.iloc[i] < series.iloc[i + 2]
                ):
                    indices.append(i)
        return indices


class MultiTFSignalGenerator(SignalGenerator):
    def __init__(self, config: Any):
        self.ctx = MultiTFContext(
            fast_tf=getattr(config.fast_tf, 'value', '5m'),
            slow_tf=getattr(config.slow_tf, 'value', '1h'),
            fast_window=getattr(config, 'fast_window', 24),
            slow_window=getattr(config, 'slow_window', 48),
            volume_multiplier=getattr(config, 'volume_multiplier', 2.5),
            volume_trend_window=getattr(config, 'volume_trend_window', 12),
            trend_strength_threshold=getattr(config, 'trend_strength_threshold', 0.002),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            confluence_required=getattr(config, 'confluence_required', 2),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 1.0),
            momentum_analysis=getattr(config, 'momentum_analysis', True),
            mtf_divergence_detection=getattr(config, 'mtf_divergence_detection', True),
        )

    def calculate_strength(self, indicators: StrategyIndicators, signal_type: str) -> float:
        alignment = indicators.latest('trends_aligned_bullish', False) if signal_type == 'BUY' else indicators.latest('trends_aligned_bearish', False)
        alignment_factor = 1.0 if alignment else 0.0

        volume_ratio = indicators.latest('volume_ratio', 1.0)
        volume_factor = min(volume_ratio / self.ctx.volume_multiplier, 2.0) / 2.0

        slow_trend_strength = indicators.latest('slow_trend_strength', 0.0)
        price_factor = min(slow_trend_strength / self.ctx.trend_strength_threshold, 1.0)

        weights = [0.5, 0.3, 0.2]
        strength = alignment_factor * weights[0] + volume_factor * weights[1] + price_factor * weights[2]
        return float(min(strength, 1.0))

    def confluence_factors(self, indicators: StrategyIndicators, signal_type: str) -> List[str]:
        factors: List[str] = []
        alignment = indicators.latest('trends_aligned_bullish', False) if signal_type == 'BUY' else indicators.latest('trends_aligned_bearish', False)
        if alignment:
            factors.append('trend_alignment')

        volume_spike = indicators.latest('volume_spike', False)
        if volume_spike:
            factors.append('volume_confirmation')

        slow_trend_strength = indicators.latest('slow_trend_strength', 0.0)
        if slow_trend_strength > self.ctx.trend_strength_threshold:
            factors.append('price_position')

        divergence = indicators.latest('mtf_divergence', {'bullish': False, 'bearish': False})
        if signal_type == 'BUY' and divergence.get('bullish'):
            factors.append('mtf_bullish_divergence')
        if signal_type == 'SELL' and divergence.get('bearish'):
            factors.append('mtf_bearish_divergence')

        return factors

    def generate(self, df: pd.DataFrame, indicators: StrategyIndicators,
                 current_price: float, market_analysis: Dict[str, Any]) -> SignalDecision:
        long_setup = bool(indicators.latest('trends_aligned_bullish', False) and indicators.latest('volume_spike', False))
        short_setup = bool(indicators.latest('trends_aligned_bearish', False) and indicators.latest('volume_spike', False))

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
            'fast_momentum',
            'slow_momentum',
            'slow_trend_strength',
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


class MultiTFPositionSizer(PositionSizer):
    def __init__(self, config: Any, round_price_fn, calc_levels_fn):
        self.round_price = round_price_fn
        self.calculate_levels = calc_levels_fn
        self.ctx = MultiTFContext(
            fast_tf=getattr(config.fast_tf, 'value', '5m'),
            slow_tf=getattr(config.slow_tf, 'value', '1h'),
            fast_window=getattr(config, 'fast_window', 24),
            slow_window=getattr(config, 'slow_window', 48),
            volume_multiplier=getattr(config, 'volume_multiplier', 2.5),
            volume_trend_window=getattr(config, 'volume_trend_window', 12),
            trend_strength_threshold=getattr(config, 'trend_strength_threshold', 0.002),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            confluence_required=getattr(config, 'confluence_required', 2),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 1.0),
            momentum_analysis=getattr(config, 'momentum_analysis', True),
            mtf_divergence_detection=getattr(config, 'mtf_divergence_detection', True),
            # ✅ Market Context parameters
            use_market_context=getattr(config, 'use_market_context', True),
            use_session_filtering=getattr(config, 'use_session_filtering', True),
            require_tf_regime_match=getattr(config, 'require_tf_regime_match', True),
            min_context_confidence=getattr(config, 'min_context_confidence', 0.35),
        )

        # ✅ Market Context Engine initialization
        self.market_engine = None
        if MARKET_CONTEXT_AVAILABLE and self.ctx.use_market_context:
            try:
                self.market_engine = MarketContextEngine()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to initialize Market Context Engine for MultiTF: {e}")

    def plan(self, decision: SignalDecision, df: pd.DataFrame,
             current_price: float) -> PositionPlan:
        if not decision.is_actionable:
            return PositionPlan(side=None)

        entry_price = self.round_price(current_price)

        # ✅ Market Context integration for MultiTF
        market_ctx = None
        if self.market_engine is not None:
            try:
                market_ctx = self.market_engine.get_context(
                    df=df,
                    current_price=current_price,
                    signal_direction=decision.signal
                )

                # Check trading filters
                can_trade, reason = market_ctx.should_trade()
                if not can_trade:
                    return PositionPlan(
                        side=None,
                        metadata={
                            'reject_reason': f'Market context filter: {reason}',
                            'context': market_ctx.to_dict()
                        }
                    )

                # Check confidence
                if market_ctx.risk_params.confidence < self.ctx.min_context_confidence:
                    return PositionPlan(
                        side=None,
                        metadata={
                            'reject_reason': 'Context confidence below threshold',
                            'confidence': market_ctx.risk_params.confidence
                        }
                    )

                # Multi-timeframe strategies benefit from regime matching
                if self.ctx.require_tf_regime_match:
                    regime = market_ctx.risk_params.market_regime.value
                    if regime == 'sideways':
                        # MultiTF works best in trending markets
                        return PositionPlan(
                            side=None,
                            metadata={'reject_reason': 'MultiTF requires trending market, detected sideways'}
                        )

            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Market Context error in MultiTF: {e}")
                market_ctx = None

        # Calculate levels with Market Context awareness
        if market_ctx and self.ctx.use_session_filtering:
            atr_result = TechnicalIndicators.calculate_atr_safe(df, 14)
            atr = atr_result.last_value if atr_result and atr_result.is_valid else current_price * 0.01

            stop_loss = market_ctx.get_stop_loss(entry_price, atr, decision.signal)
            take_profit = market_ctx.get_take_profit(entry_price, atr, decision.signal)
        else:
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
        if actual_rr < self.ctx.min_risk_reward_ratio:
            return PositionPlan(side=None, metadata={'reject_reason': f'R/R {actual_rr:.2f}'})

        size = max(self.ctx.trade_amount, self.ctx.min_trade_amount)
        metadata = {
            'risk_reward': actual_rr,
            'trade_amount': size,
            # ✅ Market Context metadata
            'market_context_used': market_ctx is not None,
        }

        # Add detailed context info
        if market_ctx:
            metadata.update({
                'session': market_ctx.session.name.value,
                'market_regime': market_ctx.risk_params.market_regime.value,
                'volatility_regime': market_ctx.risk_params.volatility_regime.value,
                'context_confidence': market_ctx.risk_params.confidence,
            })

        return PositionPlan(
            side=side,
            size=size,
            entry_price=entry_price,
            stop_loss=self.round_price(stop_loss),
            take_profit=self.round_price(take_profit),
            risk_reward=actual_rr,
            metadata=metadata,
        )
