"""Common data contracts for strategy execution pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StrategyIndicators:
    """Container for calculated indicators with helper accessors."""

    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def latest(self, key: str, fallback: Any = None) -> Any:
        """Return the latest value for a series-like indicator."""

        series = self.data.get(key)
        if series is None:
            return fallback

        try:
            return series.iloc[-1]
        except (AttributeError, IndexError):
            return series if series is not None else fallback

    def snapshot(self, keys: List[str]) -> Dict[str, Any]:
        """Build a snapshot dict with float-friendly values for logging."""

        snapshot: Dict[str, Any] = {}
        for key in keys:
            value = self.latest(key)
            if value is None:
                continue

            try:
                snapshot[key] = float(value)
            except (TypeError, ValueError):
                snapshot[key] = value
        return snapshot


@dataclass
class SignalDecision:
    """Represents the decision of the signal generation stage."""

    signal: Optional[str]
    confidence: float
    confluence: List[str] = field(default_factory=list)
    rationale: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return bool(self.signal)


@dataclass
class PositionPlan:
    """Describes how a position should be opened if a signal is actionable."""

    side: Optional[str]
    size: float = 0.0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return bool(self.side and self.entry_price is not None and self.stop_loss is not None and self.take_profit is not None)
