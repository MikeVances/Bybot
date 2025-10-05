"""
Enhanced Volume VWAP Pipeline with Market Context Engine

This is a REFERENCE IMPLEMENTATION showing how to integrate
Market Context Engine into existing volume_vwap_pipeline.py

Key improvements:
1. Session-aware stop multipliers
2. Liquidity-based take profit targets
3. Adaptive R/R ratios
4. Confidence-based position sizing
5. Time-based trade filtering
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

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

# ✅ NEW: Import Market Context Engine
from bot.market_context import MarketContextEngine, MarketContext


@dataclass
class VolumeContext:
    """Enhanced with market context parameters"""
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
    risk_reward_ratio: float  # Now acts as MINIMUM, actual is dynamic
    min_risk_reward_ratio: float
    trade_amount: float
    min_trade_amount: float

    # ✅ NEW: Market context settings
    use_market_context: bool = True
    use_liquidity_targets: bool = True
    use_session_stops: bool = True
    min_context_confidence: float = 0.3


class VolumeVwapIndicatorEngineEnhanced(IndicatorEngine):
    """Same as before - no changes needed in indicator calculation"""

    def __init__(self, config: Any, base_indicator_fn):
        self.config = config
        self._base_indicator_fn = base_indicator_fn

    def calculate(self, df: pd.DataFrame) -> StrategyIndicators:
        # ... existing indicator logic unchanged ...
        indicators: Dict[str, Any] = {}

        if self._base_indicator_fn is not None:
            indicators.update(self._base_indicator_fn(df) or {})

        if 'volume' not in df.columns:
            return StrategyIndicators(data=indicators)

        # Volume seasonality (existing)
        use_seasonality = getattr(self.config, 'use_volume_seasonality', True)
        if use_seasonality and len(df) >= 100:
            try:
                df_adjusted = df.copy()
                df_adjusted['volume_adjusted'] = adjust_volume_for_seasonality(df, lookback_days=30)
                volume_series = df_adjusted['volume_adjusted']
                indicators['seasonality_enabled'] = True
            except Exception:
                volume_series = df['volume']
                indicators['seasonality_enabled'] = False
        else:
            volume_series = df['volume']
            indicators['seasonality_enabled'] = False

        # ... rest of existing indicator logic ...
        vol_sma_period = getattr(self.config, 'volume_sma_period', 20)
        indicators['vol_sma'] = volume_series.rolling(vol_sma_period, min_periods=1).mean()
        indicators['volume_ratio'] = volume_series / indicators['vol_sma']
        indicators['volume_spike'] = indicators['volume_ratio'] > getattr(self.config, 'volume_multiplier', 2.0)

        # ... (keep all existing indicator calculations) ...

        return StrategyIndicators(data=indicators)


class VolumeVwapSignalGeneratorEnhanced(SignalGenerator):
    """Enhanced signal generator with context awareness"""

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
            # ✅ NEW: Market context config
            use_market_context=getattr(config, 'use_market_context', True),
            use_liquidity_targets=getattr(config, 'use_liquidity_targets', True),
            use_session_stops=getattr(config, 'use_session_stops', True),
            min_context_confidence=getattr(config, 'min_context_confidence', 0.3)
        )

        # ✅ NEW: Initialize market context engine
        self.market_engine = MarketContextEngine() if self.ctx.use_market_context else None

    def generate(self, df: pd.DataFrame, indicators: StrategyIndicators,
                 current_price: float, market_analysis: Dict[str, Any]) -> SignalDecision:

        # Existing signal logic
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

        # ✅ NEW: Check market context before generating signal
        if self.market_engine:
            try:
                context = self.market_engine.get_context(
                    df=df,
                    current_price=current_price,
                    signal_direction=signal_type
                )

                # Check if we should trade
                can_trade, reason = context.should_trade()
                if not can_trade:
                    return SignalDecision(
                        signal=None,
                        confidence=confidence,
                        rationale=[f"Market context rejected: {reason}"]
                    )

                # Adjust confidence based on market context
                confidence *= context.risk_params.confidence

            except Exception as e:
                # Fallback: if context fails, continue with base logic
                import logging
                logging.getLogger(__name__).warning(f"Market context error: {e}")

        # Minimum confidence check
        if confidence < getattr(self.ctx, 'min_signal_strength', 0.3):
            return SignalDecision(signal=None, confidence=confidence)

        confluence = self._confluence(indicators, signal_type)
        if not confluence:
            return SignalDecision(signal=None, confidence=confidence)

        snapshot = indicators.snapshot([
            'volume_ratio', 'rsi', 'price_momentum', 'vwap', 'trend_strength'
        ])

        context_data = {
            'indicators': snapshot,
            'market_analysis': market_analysis,
            'current_price': current_price,
        }

        # ✅ NEW: Add market context to signal
        if self.market_engine:
            try:
                market_ctx = self.market_engine.get_context(df, current_price, signal_type)
                context_data['market_context'] = market_ctx.to_dict()
            except Exception:
                pass

        return SignalDecision(
            signal=signal_type,
            confidence=confidence,
            confluence=confluence,
            rationale=[f"market_condition={market_analysis.get('condition', 'unknown')}"],
            context=context_data,
        )

    def _strength(self, indicators: StrategyIndicators, signal_type: str) -> float:
        # ... existing strength calculation ...
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
        # ... existing confluence logic ...
        factors: List[str] = []
        if signal_type == 'BUY':
            if indicators.latest('volume_spike', False):
                factors.append('Volume spike')
            if indicators.latest('price_above_vwap', False):
                factors.append('Price above VWAP')
            if indicators.latest('trend_bullish', False):
                factors.append('Bullish trend')
        else:
            if indicators.latest('volume_spike', False):
                factors.append('Volume spike')
            if indicators.latest('price_below_vwap', False):
                factors.append('Price below VWAP')
            if indicators.latest('trend_bearish', False):
                factors.append('Bearish trend')
        return factors


class VolumeVwapPositionSizerEnhanced(PositionSizer):
    """
    Enhanced position sizer with Market Context Engine

    Key improvements:
    1. Session-aware stop multipliers (Asian vs NY)
    2. Liquidity-based take profit targets
    3. Adaptive R/R ratios based on trend
    4. Confidence-based position sizing
    """

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
            # Market context config
            use_market_context=getattr(config, 'use_market_context', True),
            use_liquidity_targets=getattr(config, 'use_liquidity_targets', True),
            use_session_stops=getattr(config, 'use_session_stops', True),
        )

        # ✅ NEW: Market context engine
        self.market_engine = MarketContextEngine() if self.ctx.use_market_context else None

    def plan(self, decision: SignalDecision, df: pd.DataFrame,
             current_price: float) -> PositionPlan:

        if not decision.is_actionable:
            return PositionPlan(side=None)

        entry_price = self.round_price(current_price)

        # Calculate ATR
        atr_result = TechnicalIndicators.calculate_atr_safe(df, 14)
        atr = atr_result.last_value if atr_result and atr_result.is_valid else entry_price * 0.01

        # ✅ NEW: Use market context for stop/target/size
        if self.market_engine:
            try:
                market_ctx = self.market_engine.get_context(
                    df=df,
                    current_price=current_price,
                    signal_direction=decision.signal
                )

                # Context-aware stop and target
                stop_loss = market_ctx.get_stop_loss(entry_price, atr, decision.signal)
                take_profit = market_ctx.get_take_profit(entry_price, atr, decision.signal)

                # Context-aware position size
                base_size = self.ctx.trade_amount
                size = market_ctx.get_position_size(base_size)

                # Calculate actual R/R
                if decision.signal == 'BUY':
                    risk = entry_price - stop_loss
                    reward = take_profit - entry_price
                    side = 'Buy'
                else:
                    risk = stop_loss - entry_price
                    reward = entry_price - take_profit
                    side = 'Sell'

                actual_rr = reward / risk if risk > 0 else 0.0

                # Use context's minimum R/R (dynamic!)
                min_rr = market_ctx.risk_params.risk_reward_ratio * 0.6  # 60% of optimal

                if actual_rr < min_rr:
                    return PositionPlan(
                        side=None,
                        metadata={
                            'reject_reason': 'R/R below context threshold',
                            'required_rr': min_rr,
                            'actual_rr': actual_rr,
                            'context_recommended_rr': market_ctx.risk_params.risk_reward_ratio
                        }
                    )

                metadata = {
                    'risk_reward': actual_rr,
                    'trade_amount': size,
                    'decision_context': decision.context,
                    # ✅ NEW: Market context metadata
                    'market_regime': market_ctx.risk_params.market_regime.value,
                    'volatility_regime': market_ctx.risk_params.volatility_regime.value,
                    'session': market_ctx.session.name.value,
                    'session_time_remaining_hours': market_ctx.session_time_remaining,
                    'stop_multiplier': market_ctx.risk_params.stop_loss_atr_mult,
                    'context_confidence': market_ctx.risk_params.confidence,
                    'liquidity_target_used': take_profit != (entry_price + atr * market_ctx.risk_params.take_profit_atr_mult),
                }

                return PositionPlan(
                    side=side,
                    size=size,
                    entry_price=entry_price,
                    stop_loss=self.round_price(stop_loss),
                    take_profit=self.round_price(take_profit),
                    risk_reward=actual_rr,
                    metadata=metadata,
                )

            except Exception as e:
                # Fallback to old logic if context fails
                import logging
                logging.getLogger(__name__).error(f"Market context error in position sizing: {e}")
                # Fall through to legacy logic below

        # ❌ LEGACY LOGIC (fallback if no market context)
        stop_loss, take_profit = self._calculate_levels_legacy(df, entry_price, decision.signal)

        if decision.signal == 'BUY':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            side = 'Buy'
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
            side = 'Sell'

        actual_rr = reward / risk if risk > 0 else 0.0
        if actual_rr < self.ctx.min_risk_reward_ratio:
            return PositionPlan(side=None, metadata={'reject_reason': 'R/R below threshold', 'risk_reward': actual_rr})

        size = max(self.ctx.trade_amount, self.ctx.min_trade_amount)

        return PositionPlan(
            side=side,
            size=size,
            entry_price=entry_price,
            stop_loss=self.round_price(stop_loss),
            take_profit=self.round_price(take_profit),
            risk_reward=actual_rr,
            metadata={'risk_reward': actual_rr, 'trade_amount': size, 'using_legacy_logic': True}
        )

    def _calculate_levels_legacy(self, df: pd.DataFrame, entry_price: float, signal_type: str) -> tuple[float, float]:
        """Legacy stop/target calculation (fallback)"""
        atr_period = 14
        atr_result = TechnicalIndicators.calculate_atr_safe(df, atr_period)
        atr = atr_result.last_value if atr_result and atr_result.is_valid else entry_price * 0.01

        rr = self.ctx.risk_reward_ratio
        stop_multiplier = 1.5  # Old fixed multiplier
        take_multiplier = stop_multiplier * rr

        if signal_type == 'BUY':
            stop_loss = entry_price - (atr * stop_multiplier)
            take_profit = entry_price + (atr * take_multiplier)
        else:
            stop_loss = entry_price + (atr * stop_multiplier)
            take_profit = entry_price - (atr * take_multiplier)

        return float(stop_loss), float(take_profit)
