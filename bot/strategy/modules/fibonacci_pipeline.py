"""Pipeline components for the Fibonacci RSI volume strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

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


@dataclass
class FibonacciContext:
    fast_tf: str
    slow_tf: str
    ema_short: int
    ema_long: int
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    rsi_favorable_low: float
    rsi_favorable_high: float
    volume_multiplier: float
    volume_ma_period: int
    atr_period: int
    atr_multiplier_sl: float
    atr_multiplier_tp: float
    fib_lookback: int
    risk_reward_ratio: float
    min_risk_reward_ratio: float
    signal_strength_threshold: float
    confluence_required: int
    trade_amount: float
    min_trade_amount: float
    require_volume_confirmation: bool
    multi_tf_confirmation: bool
    use_fibonacci_targets: bool
    trend_strength_threshold: float


class FibonacciIndicatorEngine(IndicatorEngine):
    """Calculates indicators for the Fibonacci RSI strategy."""

    def __init__(self, config: Any, base_indicator_fn):
        self.config = config
        self._base_indicator_fn = base_indicator_fn
        self.ctx = FibonacciContext(
            fast_tf=getattr(config, 'fast_tf', '15m'),
            slow_tf=getattr(config, 'slow_tf', '1h'),
            ema_short=getattr(config, 'ema_short', 20),
            ema_long=getattr(config, 'ema_long', 50),
            rsi_period=getattr(config, 'rsi_period', 14),
            rsi_overbought=getattr(config, 'rsi_overbought', 70.0),
            rsi_oversold=getattr(config, 'rsi_oversold', 30.0),
            rsi_favorable_low=getattr(config, 'rsi_favorable_zone', (40.0, 60.0))[0],
            rsi_favorable_high=getattr(config, 'rsi_favorable_zone', (40.0, 60.0))[1],
            volume_multiplier=getattr(config, 'volume_multiplier', 1.5),
            volume_ma_period=getattr(config, 'volume_ma_period', 20),
            atr_period=getattr(config, 'atr_period', 14),
            atr_multiplier_sl=getattr(config, 'atr_multiplier_sl', 1.0),
            atr_multiplier_tp=getattr(config, 'atr_multiplier_tp', 1.5),
            fib_lookback=getattr(config, 'fib_lookback', 50),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 1.0),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            confluence_required=getattr(config, 'confluence_required', 2),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            require_volume_confirmation=getattr(config, 'require_volume_confirmation', True),
            multi_tf_confirmation=getattr(config, 'multi_timeframe_confirmation', True),
            use_fibonacci_targets=getattr(config, 'use_fibonacci_targets', True),
            trend_strength_threshold=getattr(config, 'trend_strength_threshold', 0.001),
        )

    def calculate(self, market_data: Dict[str, pd.DataFrame]) -> StrategyIndicators:
        df_fast = market_data.get(self.ctx.fast_tf)
        df_slow = market_data.get(self.ctx.slow_tf)
        if df_fast is None or df_slow is None:
            raise ValueError('Недостаточно данных для стратегии Fibonacci RSI')

        indicators: Dict[str, Any] = {}
        if self._base_indicator_fn is not None:
            indicators.update(self._base_indicator_fn(df_fast) or {})

        ema_short = df_slow['close'].ewm(span=self.ctx.ema_short, adjust=False).mean()
        ema_long = df_slow['close'].ewm(span=self.ctx.ema_long, adjust=False).mean()
        trend_up = bool(ema_short.iloc[-1] > ema_long.iloc[-1])
        trend_down = bool(ema_short.iloc[-1] < ema_long.iloc[-1])
        trend_strength = abs(ema_short.iloc[-1] - ema_long.iloc[-1]) / ema_long.iloc[-1]

        rsi = self._calculate_rsi(df_fast['close'], self.ctx.rsi_period)
        rsi_value = float(rsi.iloc[-1])
        rsi_overbought = rsi_value > self.ctx.rsi_overbought
        rsi_oversold = rsi_value < self.ctx.rsi_oversold
        rsi_favorable = self.ctx.rsi_favorable_low <= rsi_value <= self.ctx.rsi_favorable_high

        vol_ma = df_fast['volume'].rolling(self.ctx.volume_ma_period, min_periods=1).mean().replace({0: np.nan})
        volume_ratio = (df_fast['volume'] / vol_ma).fillna(0)
        volume_spike = bool(volume_ratio.iloc[-1] > self.ctx.volume_multiplier)

        atr_result = TechnicalIndicators.calculate_atr_safe(df_fast, self.ctx.atr_period)
        atr_value = atr_result.value if atr_result and atr_result.is_valid else df_fast['close'].iloc[-1] * 0.01

        fib_levels = self._calculate_fibonacci_levels(df_fast)

        multi_tf_alignment = bool(np.sign(df_fast['close'].pct_change().iloc[-1]) == np.sign(df_slow['close'].pct_change().iloc[-1]))

        indicators.update({
            'ema_short': float(ema_short.iloc[-1]),
            'ema_long': float(ema_long.iloc[-1]),
            'trend_up': trend_up,
            'trend_down': trend_down,
            'trend_strength': trend_strength,
            'rsi': rsi_value,
            'rsi_overbought': rsi_overbought,
            'rsi_oversold': rsi_oversold,
            'rsi_favorable': rsi_favorable,
            'volume_ratio': volume_ratio,
            'volume_spike': volume_spike,
            'atr_value': atr_value,
            'fib_levels': fib_levels,
            'multi_tf_alignment': multi_tf_alignment,
            'price': df_fast['close'],
        })

        return StrategyIndicators(data=indicators, metadata={'rows': len(df_fast)})

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace({0: np.nan})
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50.0)

    def _calculate_fibonacci_levels(self, df: pd.DataFrame) -> Dict[str, float]:
        lookback = min(self.ctx.fib_lookback, len(df))
        recent = df.tail(lookback)
        high = recent['high'].max()
        low = recent['low'].min()
        diff = high - low
        levels = {
            'fib_382': high - diff * 0.382,
            'fib_500': high - diff * 0.5,
            'fib_618': high - diff * 0.618,
            'fib_786': high - diff * 0.786,
        }
        levels['target_long'] = high + diff * 0.272 if self.ctx.use_fibonacci_targets else high + diff
        levels['target_short'] = low - diff * 0.272 if self.ctx.use_fibonacci_targets else low - diff
        return levels


class FibonacciSignalGenerator(SignalGenerator):
    def __init__(self, config: Any):
        self.ctx = FibonacciContext(
            fast_tf=getattr(config, 'fast_tf', '15m'),
            slow_tf=getattr(config, 'slow_tf', '1h'),
            ema_short=getattr(config, 'ema_short', 20),
            ema_long=getattr(config, 'ema_long', 50),
            rsi_period=getattr(config, 'rsi_period', 14),
            rsi_overbought=getattr(config, 'rsi_overbought', 70.0),
            rsi_oversold=getattr(config, 'rsi_oversold', 30.0),
            rsi_favorable_low=getattr(config, 'rsi_favorable_zone', (40.0, 60.0))[0],
            rsi_favorable_high=getattr(config, 'rsi_favorable_zone', (40.0, 60.0))[1],
            volume_multiplier=getattr(config, 'volume_multiplier', 1.5),
            volume_ma_period=getattr(config, 'volume_ma_period', 20),
            atr_period=getattr(config, 'atr_period', 14),
            atr_multiplier_sl=getattr(config, 'atr_multiplier_sl', 1.0),
            atr_multiplier_tp=getattr(config, 'atr_multiplier_tp', 1.5),
            fib_lookback=getattr(config, 'fib_lookback', 50),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 1.0),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            confluence_required=getattr(config, 'confluence_required', 2),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            require_volume_confirmation=getattr(config, 'require_volume_confirmation', True),
            multi_tf_confirmation=getattr(config, 'multi_timeframe_confirmation', True),
            use_fibonacci_targets=getattr(config, 'use_fibonacci_targets', True),
            trend_strength_threshold=getattr(config, 'trend_strength_threshold', 0.001),
        )

    def calculate_strength(self, indicators: StrategyIndicators, signal_type: str) -> float:
        trend_strength = indicators.latest('trend_strength', 0.0)
        trend_factor = min(trend_strength / self.ctx.trend_strength_threshold, 2.0) / 2.0

        rsi_value = indicators.latest('rsi', 50.0)
        if signal_type == 'BUY':
            rsi_factor = 1.0 if self.ctx.rsi_oversold < rsi_value < self.ctx.rsi_overbought else 0.3
        else:
            rsi_factor = 1.0 if self.ctx.rsi_oversold < rsi_value < self.ctx.rsi_overbought else 0.3

        volume_ratio = indicators.latest('volume_ratio', 1.0)
        volume_factor = min(volume_ratio / self.ctx.volume_multiplier, 2.0) / 2.0

        weights = [0.4, 0.35, 0.25]
        strength = trend_factor * weights[0] + rsi_factor * weights[1] + volume_factor * weights[2]
        return float(min(strength, 1.0))

    def confluence_factors(self, indicators: StrategyIndicators, signal_type: str) -> List[str]:
        factors: List[str] = []

        if indicators.latest('trend_up', False) and signal_type == 'BUY':
            factors.append('trend_up')
        if indicators.latest('trend_down', False) and signal_type == 'SELL':
            factors.append('trend_down')

        if indicators.latest('volume_spike', False):
            factors.append('volume_spike')

        rsi_value = indicators.latest('rsi', 50.0)
        if signal_type == 'BUY' and rsi_value < self.ctx.rsi_oversold:
            factors.append('rsi_oversold')
        if signal_type == 'SELL' and rsi_value > self.ctx.rsi_overbought:
            factors.append('rsi_overbought')
        if self.ctx.multi_tf_confirmation and indicators.latest('multi_tf_alignment', False):
            factors.append('multi_tf_alignment')

        return factors

    def generate(self, df: pd.DataFrame, indicators: StrategyIndicators,
                 current_price: float, market_analysis: Dict[str, Any]) -> SignalDecision:
        trend_up = indicators.latest('trend_up', False)
        trend_down = indicators.latest('trend_down', False)
        rsi_value = indicators.latest('rsi', 50.0)
        rsi_favorable = indicators.latest('rsi_favorable', False)
        volume_confirm = (not self.ctx.require_volume_confirmation) or indicators.latest('volume_spike', False)
        multi_tf_alignment = indicators.latest('multi_tf_alignment', True)

        long_setup = trend_up and rsi_favorable and volume_confirm and multi_tf_alignment
        short_setup = trend_down and rsi_favorable and volume_confirm and multi_tf_alignment

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
            'trend_strength',
            'rsi',
            'volume_ratio',
            'atr_value',
        ])
        snapshot['price'] = current_price

        context = {
            'indicators': snapshot,
            'fib_levels': indicators.latest('fib_levels', {}),
            'market_analysis': market_analysis,
            'current_price': current_price,
        }

        rationale = [f"market_condition={market_analysis.get('condition', 'unknown')}"]

        return SignalDecision(
            signal=signal_type,
            confidence=confidence,
            confluence=confluence,
            rationale=rationale,
            context=context,
        )


class FibonacciPositionSizer(PositionSizer):
    def __init__(self, config: Any, round_price_fn):
        self.round_price = round_price_fn
        self.ctx = FibonacciContext(
            fast_tf=getattr(config, 'fast_tf', '15m'),
            slow_tf=getattr(config, 'slow_tf', '1h'),
            ema_short=getattr(config, 'ema_short', 20),
            ema_long=getattr(config, 'ema_long', 50),
            rsi_period=getattr(config, 'rsi_period', 14),
            rsi_overbought=getattr(config, 'rsi_overbought', 70.0),
            rsi_oversold=getattr(config, 'rsi_oversold', 30.0),
            rsi_favorable_low=getattr(config, 'rsi_favorable_zone', (40.0, 60.0))[0],
            rsi_favorable_high=getattr(config, 'rsi_favorable_zone', (40.0, 60.0))[1],
            volume_multiplier=getattr(config, 'volume_multiplier', 1.5),
            volume_ma_period=getattr(config, 'volume_ma_period', 20),
            atr_period=getattr(config, 'atr_period', 14),
            atr_multiplier_sl=getattr(config, 'atr_multiplier_sl', 1.0),
            atr_multiplier_tp=getattr(config, 'atr_multiplier_tp', 1.5),
            fib_lookback=getattr(config, 'fib_lookback', 50),
            risk_reward_ratio=getattr(config, 'risk_reward_ratio', 1.5),
            min_risk_reward_ratio=getattr(config, 'min_risk_reward_ratio', 1.0),
            signal_strength_threshold=getattr(config, 'signal_strength_threshold', 0.6),
            confluence_required=getattr(config, 'confluence_required', 2),
            trade_amount=getattr(config, 'trade_amount', 0.001),
            min_trade_amount=getattr(config, 'min_trade_amount', getattr(config, 'trade_amount', 0.001)),
            require_volume_confirmation=getattr(config, 'require_volume_confirmation', True),
            multi_tf_confirmation=getattr(config, 'multi_timeframe_confirmation', True),
            use_fibonacci_targets=getattr(config, 'use_fibonacci_targets', True),
            trend_strength_threshold=getattr(config, 'trend_strength_threshold', 0.001),
        )

    def plan(self, decision: SignalDecision, df: pd.DataFrame,
             current_price: float) -> PositionPlan:
        if not decision.is_actionable:
            return PositionPlan(side=None)

        entry_price = self.round_price(current_price)

        atr_result = TechnicalIndicators.calculate_atr_safe(df, self.ctx.atr_period)
        atr_value = atr_result.value if atr_result and atr_result.is_valid else entry_price * 0.01

        if decision.signal == 'BUY':
            stop_loss = entry_price - atr_value * self.ctx.atr_multiplier_sl
            if self.ctx.use_fibonacci_targets:
                fib_levels = decision.context.get('fib_levels', {})
                take_profit = fib_levels.get('target_long', entry_price + atr_value * self.ctx.atr_multiplier_tp)
            else:
                take_profit = entry_price + atr_value * self.ctx.atr_multiplier_tp
            side = 'Buy'
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            stop_loss = entry_price + atr_value * self.ctx.atr_multiplier_sl
            if self.ctx.use_fibonacci_targets:
                fib_levels = decision.context.get('fib_levels', {})
                take_profit = fib_levels.get('target_short', entry_price - atr_value * self.ctx.atr_multiplier_tp)
            else:
                take_profit = entry_price - atr_value * self.ctx.atr_multiplier_tp
            side = 'Sell'
            risk = stop_loss - entry_price
            reward = entry_price - take_profit

        if risk <= 0:
            return PositionPlan(side=None, metadata={'reject_reason': 'invalid_levels'})

        actual_rr = reward / risk
        if actual_rr < self.ctx.min_risk_reward_ratio:
            return PositionPlan(side=None, metadata={'reject_reason': f'R/R {actual_rr:.2f}'})

        size = max(self.ctx.trade_amount, self.ctx.min_trade_amount)
        metadata = {
            'risk_reward': actual_rr,
            'trade_amount': size,
            'atr': atr_value,
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
