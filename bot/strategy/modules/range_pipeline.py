"""Modular components for the range trading strategy pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from bot.strategy.pipeline.common import PositionPlan, SignalDecision, StrategyIndicators
from bot.strategy.utils.indicators import TechnicalIndicators


@dataclass
class RangeContext:
    """Helper container to keep commonly used configuration values."""

    volume_multiplier: float
    signal_strength_threshold: float
    confluence_required: int
    min_risk_reward_ratio: float
    trade_amount: float


def _infer_trade_amount(config: Any) -> float:
    value = getattr(config, "trade_amount", None)
    if value is None:
        return 0.001
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.001


class RangeIndicatorEngine:
    """Calculates indicators used by the range trading strategy."""

    def __init__(self, config: Any, base_indicator_fn=None):
        self.config = config
        self._base_indicator_fn = base_indicator_fn

    def calculate(self, df: pd.DataFrame) -> StrategyIndicators:
        indicators: Dict[str, Any] = {}

        if self._base_indicator_fn is not None:
            try:
                base_indicators = self._base_indicator_fn(df)
                indicators.update(base_indicators or {})
            except Exception:
                pass

        if "volume" in df.columns:
            vol_sma_period = 10
            indicators["vol_sma"] = df["volume"].rolling(vol_sma_period, min_periods=1).mean()
            indicators["volume_ratio"] = df["volume"] / indicators["vol_sma"]
            indicators["volume_spike"] = indicators["volume_ratio"] > self.config.volume_multiplier
            indicators["volume_momentum"] = df["volume"].pct_change(3)
            indicators["volume_momentum_positive"] = indicators["volume_momentum"] > 0
        else:
            fallback = pd.Series([1.0] * len(df), index=df.index)
            indicators.update({
                "vol_sma": fallback * 1000,
                "volume_ratio": fallback,
                "volume_spike": fallback.astype(bool),
                "volume_momentum": pd.Series([0] * len(df), index=df.index),
                "volume_momentum_positive": fallback.astype(bool),
            })

        price_change_period = 5
        indicators["price_momentum"] = df["close"].pct_change(price_change_period)
        indicators["momentum_bullish"] = indicators["price_momentum"] > 0
        indicators["momentum_bearish"] = indicators["price_momentum"] < 0

        vwap_result = TechnicalIndicators.calculate_vwap(df)
        if vwap_result.is_valid:
            indicators["vwap"] = vwap_result.value
            indicators["price_below_vwap"] = df["close"] < indicators["vwap"]
            indicators["price_above_vwap"] = df["close"] > indicators["vwap"]
        else:
            indicators["vwap"] = df["close"].rolling(10, min_periods=1).mean()
            indicators["price_below_vwap"] = pd.Series([False] * len(df), index=df.index)
            indicators["price_above_vwap"] = pd.Series([False] * len(df), index=df.index)

        rsi_period = 14
        rsi_result = TechnicalIndicators.calculate_rsi(df, rsi_period)
        if rsi_result.is_valid:
            indicators["rsi"] = rsi_result.value
            indicators["rsi_oversold"] = indicators["rsi"] < 30
            indicators["rsi_overbought"] = indicators["rsi"] > 70
            indicators["rsi_neutral"] = (indicators["rsi"] >= 30) & (indicators["rsi"] <= 70)
        else:
            fallback_series = pd.Series([50] * len(df), index=df.index)
            indicators.update({
                "rsi": fallback_series,
                "rsi_oversold": pd.Series([False] * len(df), index=df.index),
                "rsi_overbought": pd.Series([False] * len(df), index=df.index),
                "rsi_neutral": pd.Series([True] * len(df), index=df.index),
            })

        bb_result = TechnicalIndicators.calculate_bollinger_bands(df, 20, 2)
        if bb_result.is_valid:
            indicators["bb_upper"] = bb_result.value["upper"]
            indicators["bb_lower"] = bb_result.value["lower"]
            indicators["bb_middle"] = bb_result.value["middle"]
            indicators["price_near_bb_upper"] = df["close"] > indicators["bb_upper"] * 0.98
            indicators["price_near_bb_lower"] = df["close"] < indicators["bb_lower"] * 1.02
        else:
            indicators.update({
                "bb_upper": df["close"] * 1.02,
                "bb_lower": df["close"] * 0.98,
                "bb_middle": df["close"],
                "price_near_bb_upper": pd.Series([False] * len(df), index=df.index),
                "price_near_bb_lower": pd.Series([False] * len(df), index=df.index),
            })

        indicators["range_bullish_setup"] = (
            (indicators["price_near_bb_lower"] | indicators["rsi_oversold"]) &
            indicators["momentum_bullish"] &
            indicators["volume_momentum_positive"]
        )
        indicators["range_bearish_setup"] = (
            (indicators["price_near_bb_upper"] | indicators["rsi_overbought"]) &
            indicators["momentum_bearish"] &
            indicators["volume_momentum_positive"]
        )
        indicators["vwap_bullish_setup"] = (
            indicators["price_below_vwap"] &
            indicators["momentum_bullish"] &
            indicators["volume_spike"]
        )
        indicators["vwap_bearish_setup"] = (
            indicators["price_above_vwap"] &
            indicators["momentum_bearish"] &
            indicators["volume_spike"]
        )

        return StrategyIndicators(data=indicators, metadata={"rows": len(df)})

class RangeSignalGenerator:
    """Generates actionable signals based on indicator bundle."""

    def __init__(self, config: Any):
        self.ctx = RangeContext(
            volume_multiplier=getattr(config, "volume_multiplier", 1.2),
            signal_strength_threshold=getattr(config, "signal_strength_threshold", 0.3),
            confluence_required=getattr(config, "confluence_required", 1),
            min_risk_reward_ratio=getattr(config, "min_risk_reward_ratio", 1.0),
            trade_amount=_infer_trade_amount(config),
        )

    def calculate_strength(self, indicators: StrategyIndicators, signal_type: str) -> float:
        strength = 0.0
        if signal_type == "BUY":
            if indicators.latest("rsi_oversold", False):
                strength += 0.3
            if indicators.latest("momentum_bullish", False):
                strength += 0.2
            if indicators.latest("volume_momentum_positive", False):
                strength += 0.2
            if indicators.latest("price_near_bb_lower", False):
                strength += 0.3
        else:  # SELL
            if indicators.latest("rsi_overbought", False):
                strength += 0.3
            if indicators.latest("momentum_bearish", False):
                strength += 0.2
            if indicators.latest("volume_momentum_positive", False):
                strength += 0.2
            if indicators.latest("price_near_bb_upper", False):
                strength += 0.3
        return min(1.0, strength)

    def confluence_factors(self, indicators: StrategyIndicators, signal_type: str) -> List[str]:
        factors: List[str] = []
        if signal_type == "BUY":
            if indicators.latest("rsi_oversold", False):
                factors.append("RSI oversold")
            if indicators.latest("momentum_bullish", False):
                factors.append("Positive momentum")
            if indicators.latest("volume_momentum_positive", False):
                factors.append("Volume momentum")
            if indicators.latest("price_near_bb_lower", False):
                factors.append("Price near BB lower")
            if indicators.latest("price_below_vwap", False):
                factors.append("VWAP support")
        else:
            if indicators.latest("rsi_overbought", False):
                factors.append("RSI overbought")
            if indicators.latest("momentum_bearish", False):
                factors.append("Negative momentum")
            if indicators.latest("volume_momentum_positive", False):
                factors.append("Volume momentum")
            if indicators.latest("price_near_bb_upper", False):
                factors.append("Price near BB upper")
            if indicators.latest("price_above_vwap", False):
                factors.append("VWAP resistance")
        return factors

    def generate(
        self,
        df: pd.DataFrame,
        indicators: StrategyIndicators,
        current_price: float,
        market_analysis: Dict[str, Any],
    ) -> SignalDecision:
        long_setup = bool(
            indicators.latest("range_bullish_setup", False)
            or indicators.latest("vwap_bullish_setup", False)
        )
        short_setup = bool(
            indicators.latest("range_bearish_setup", False)
            or indicators.latest("vwap_bearish_setup", False)
        )

        signal_type: Optional[str] = None
        if long_setup and not short_setup:
            signal_type = "BUY"
        elif short_setup and not long_setup:
            signal_type = "SELL"
        elif long_setup and short_setup:
            # Если одновременно оба направления — выберем то, где сигнал сильнее
            buy_strength = self.calculate_strength(indicators, "BUY")
            sell_strength = self.calculate_strength(indicators, "SELL")
            if buy_strength > sell_strength:
                signal_type = "BUY"
            elif sell_strength > buy_strength:
                signal_type = "SELL"

        if signal_type is None:
            return SignalDecision(signal=None, confidence=0.0)

        confluence = self.confluence_factors(indicators, signal_type)
        if len(confluence) < self.ctx.confluence_required:
            return SignalDecision(signal=None, confidence=0.0, confluence=confluence)

        confidence = self.calculate_strength(indicators, signal_type)
        if confidence < self.ctx.signal_strength_threshold:
            return SignalDecision(signal=None, confidence=confidence, confluence=confluence)

        rationale = [f"market_condition={market_analysis.get('condition', 'unknown')}"]
        snapshot = indicators.snapshot([
            "volume_ratio",
            "rsi",
            "price_momentum",
            "vwap",
            "bb_lower",
            "bb_upper",
        ])

        context = {
            "indicators": snapshot,
            "market_analysis": market_analysis,
            "current_price": current_price,
        }

        return SignalDecision(
            signal=signal_type,
            confidence=confidence,
            confluence=confluence,
            rationale=rationale,
            context=context,
        )


class RangePositionSizer:
    """Derives position parameters (size, levels) for the strategy."""

    def __init__(self, config: Any, round_price_fn):
        self.round_price = round_price_fn
        self.ctx = RangeContext(
            volume_multiplier=getattr(config, "volume_multiplier", 1.2),
            signal_strength_threshold=getattr(config, "signal_strength_threshold", 0.3),
            confluence_required=getattr(config, "confluence_required", 1),
            min_risk_reward_ratio=getattr(config, "min_risk_reward_ratio", 1.0),
            trade_amount=_infer_trade_amount(config),
        )
        self._min_trade_size = max(0.001, getattr(config, 'min_trade_amount', 0.0) or 0.0)

    def plan(
        self,
        decision: SignalDecision,
        df: pd.DataFrame,
        current_price: float,
    ) -> PositionPlan:
        if not decision.is_actionable:
            return PositionPlan(side=None)

        entry_price = self.round_price(current_price)
        stop_loss, take_profit = self._calculate_range_levels(df, entry_price, decision.signal)

        if decision.signal == "BUY":
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            side = "Buy"
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
            side = "Sell"

        actual_rr = reward / risk if risk > 0 else 0.0
        if actual_rr < self.ctx.min_risk_reward_ratio:
            return PositionPlan(
                side=None,
                metadata={
                    "reject_reason": f"R/R {actual_rr:.2f} < {self.ctx.min_risk_reward_ratio}",
                    "risk_reward": actual_rr,
                },
            )

        size = max(self.ctx.trade_amount, self._min_trade_size)
        metadata = {
            "risk_reward": actual_rr,
            "trade_amount": size,
            "decision_context": decision.context,
        }
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

    def _calculate_range_levels(self, df: pd.DataFrame, entry_price: float, signal_type: str) -> Tuple[float, float]:
        atr_period = 14
        atr_result = TechnicalIndicators.calculate_atr_safe(df, atr_period)
        atr = atr_result.last_value if atr_result and atr_result.is_valid else None
        if not atr or atr <= 0:
            atr = entry_price * 0.01

        if signal_type == "BUY":
            stop_loss = entry_price - (atr * 1.5)
            take_profit = entry_price + (atr * 2.0)
        else:
            stop_loss = entry_price + (atr * 1.5)
            take_profit = entry_price - (atr * 2.0)

        return float(stop_loss), float(take_profit)
