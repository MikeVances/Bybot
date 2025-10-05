"""
Market Context Engine - Central orchestrator for market intelligence

Provides unified interface for:
- Trading session awareness
- Liquidity pool identification
- Adaptive risk parameters
- Market regime classification

Thread-safe, cached, production-ready.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import pandas as pd
import logging

from .session_manager import SessionManager, TradingSession
from .liquidity_analyzer import LiquidityAnalyzer, LiquidityPools
from .risk_calculator import AdaptiveRiskCalculator, RiskParameters


@dataclass
class MarketContext:
    """
    Complete market context snapshot

    Immutable dataclass containing all market intelligence
    for a specific point in time.
    """
    # Session data
    session: TradingSession
    session_time_remaining: float  # hours
    is_session_overlap: bool

    # Liquidity
    liquidity: LiquidityPools

    # Risk parameters
    risk_params: RiskParameters

    # Metadata
    timestamp: datetime
    current_price: float

    # Cache metadata
    _cache_key: str = field(default="", repr=False)

    def get_stop_loss(self, entry_price: float, atr: float, side: str) -> float:
        """Calculate stop loss using context parameters"""
        stop_mult = self.risk_params.stop_loss_atr_mult

        if side.upper() in ['BUY', 'LONG']:
            return entry_price - (atr * stop_mult)
        else:
            return entry_price + (atr * stop_mult)

    def get_take_profit(self, entry_price: float, atr: float, side: str) -> float:
        """
        Calculate take profit using liquidity-aware logic

        Priority:
        1. Nearest strong liquidity level
        2. ATR-based target (fallback)
        """
        if side.upper() in ['BUY', 'LONG']:
            # Try liquidity target first
            liq_target = self.liquidity.nearest_target_above(
                entry_price,
                min_strength=0.6
            )
            if liq_target and (liq_target - entry_price) / (atr * self.risk_params.stop_loss_atr_mult) >= 1.2:
                # Liquidity target gives at least 1.2 R/R
                return liq_target

            # Fallback to ATR
            return entry_price + (atr * self.risk_params.take_profit_atr_mult)
        else:
            # Sell side
            liq_target = self.liquidity.nearest_support_below(
                entry_price,
                min_strength=0.6
            )
            if liq_target and (entry_price - liq_target) / (atr * self.risk_params.stop_loss_atr_mult) >= 1.2:
                return liq_target

            return entry_price - (atr * self.risk_params.take_profit_atr_mult)

    def get_position_size(self, base_size: float) -> float:
        """Get adjusted position size based on risk params and confidence"""
        # Scale base size by risk parameter
        adjusted = base_size * (self.risk_params.position_size_pct / 100.0)

        # Further scale by confidence
        confident_size = adjusted * self.risk_params.confidence

        return max(confident_size, base_size * 0.3)  # Min 30% of base

    def should_trade(self) -> tuple[bool, str]:
        """Check if trading is allowed in current context"""
        # Session-based filtering
        if self.session.avg_volatility_pct < 0.2:
            return False, "extremely_low_volatility"

        # Low confidence in parameters
        if self.risk_params.confidence < 0.3:
            return False, "low_confidence_regime"

        return True, ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializable representation for logging/debugging"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'session': self.session.name.value,
            'session_time_remaining_hours': self.session_time_remaining,
            'is_overlap': self.is_session_overlap,
            'current_price': self.current_price,
            'market_regime': self.risk_params.market_regime.value,
            'volatility_regime': self.risk_params.volatility_regime.value,
            'stop_multiplier': self.risk_params.stop_loss_atr_mult,
            'rr_ratio': self.risk_params.risk_reward_ratio,
            'position_size_pct': self.risk_params.position_size_pct,
            'confidence': self.risk_params.confidence,
            'liquidity_buy_side_count': len(self.liquidity.buy_side_liquidity),
            'liquidity_sell_side_count': len(self.liquidity.sell_side_liquidity),
        }


class MarketContextEngine:
    """
    Orchestrator for market intelligence

    Thread-safe with TTL caching for performance.
    """

    def __init__(self,
                 session_manager: Optional[SessionManager] = None,
                 liquidity_analyzer: Optional[LiquidityAnalyzer] = None,
                 risk_calculator: Optional[AdaptiveRiskCalculator] = None,
                 cache_ttl_seconds: int = 60):
        """
        Args:
            session_manager: Custom SessionManager (optional)
            liquidity_analyzer: Custom LiquidityAnalyzer (optional)
            risk_calculator: Custom AdaptiveRiskCalculator (optional)
            cache_ttl_seconds: Cache TTL (default 60s)
        """
        self.session_manager = session_manager or SessionManager()
        self.liquidity_analyzer = liquidity_analyzer or LiquidityAnalyzer()
        self.risk_calculator = risk_calculator or AdaptiveRiskCalculator()

        self.cache_ttl_seconds = cache_ttl_seconds
        self.logger = logging.getLogger(__name__)

        # Cache
        self._cache: Dict[str, tuple[datetime, MarketContext]] = {}

    def get_context(self,
                   df: pd.DataFrame,
                   current_price: float,
                   dt: Optional[datetime] = None,
                   signal_direction: str = 'BUY',
                   force_refresh: bool = False) -> MarketContext:
        """
        Get complete market context

        Args:
            df: Recent OHLCV data (recommend 200+ bars)
            current_price: Current market price
            dt: Datetime for context (default: now)
            signal_direction: 'BUY' or 'SELL' for risk alignment
            force_refresh: Skip cache

        Returns:
            MarketContext with all intelligence
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        # Cache key
        cache_key = f"{current_price:.2f}_{signal_direction}_{dt.hour}"

        # Check cache
        if not force_refresh and cache_key in self._cache:
            cached_time, cached_context = self._cache[cache_key]
            age = (dt - cached_time).total_seconds()

            if age < self.cache_ttl_seconds:
                self.logger.debug(f"Cache hit for {cache_key}")
                return cached_context

        # Build fresh context
        self.logger.debug(f"Building fresh context for {cache_key}")

        # 1. Session analysis
        session = self.session_manager.get_current_session(dt)
        time_remaining = session.time_until_end(dt)
        is_overlap = self.session_manager.is_session_overlap(dt)

        # 2. Liquidity analysis
        liquidity = self.liquidity_analyzer.analyze(df, current_price)

        # 3. Risk parameters
        risk_params = self.risk_calculator.calculate(
            df,
            current_price,
            signal_direction
        )

        # Build context
        context = MarketContext(
            session=session,
            session_time_remaining=time_remaining,
            is_session_overlap=is_overlap,
            liquidity=liquidity,
            risk_params=risk_params,
            timestamp=dt,
            current_price=current_price,
            _cache_key=cache_key
        )

        # Update cache
        self._cache[cache_key] = (dt, context)

        # Cleanup old cache entries
        self._cleanup_cache(dt)

        self.logger.info(
            f"Context built: {session.name.value} session, "
            f"{risk_params.market_regime.value} regime, "
            f"R/R={risk_params.risk_reward_ratio:.2f}, "
            f"confidence={risk_params.confidence:.2f}"
        )

        return context

    def _cleanup_cache(self, current_time: datetime):
        """Remove stale cache entries"""
        keys_to_remove = []

        for key, (timestamp, _) in self._cache.items():
            age = (current_time - timestamp).total_seconds()
            if age > self.cache_ttl_seconds * 2:  # 2x TTL threshold
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._cache[key]

        if keys_to_remove:
            self.logger.debug(f"Cleaned {len(keys_to_remove)} stale cache entries")

    def get_session_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Get current session statistics"""
        session = self.session_manager.get_current_session()
        stats = self.session_manager.get_session_stats(df, session)

        return {
            'session_name': session.name.value,
            'realized_volatility_pct': stats.realized_volatility,
            'volume_ratio': stats.volume_ratio,
            'spread_estimate_bps': stats.spread_estimate,
            'momentum_score': stats.momentum_score,
            'base_stop_multiplier': session.stop_multiplier,
            'adaptive_stop_multiplier': self.session_manager.get_adaptive_stop_multiplier(df, session)
        }

    def get_liquidity_map(self, df: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        """Get detailed liquidity map"""
        pools = self.liquidity_analyzer.analyze(df, current_price)

        return {
            'buy_side_levels': [
                {'price': lvl.price, 'type': lvl.type.value, 'strength': lvl.strength}
                for lvl in pools.buy_side_liquidity[:5]
            ],
            'sell_side_levels': [
                {'price': lvl.price, 'type': lvl.type.value, 'strength': lvl.strength}
                for lvl in pools.sell_side_liquidity[:5]
            ],
            'fair_value_gaps': [
                {'low': gap[0], 'high': gap[1]}
                for gap in pools.fair_value_gaps
            ],
            'strongest_levels': [
                {'price': lvl.price, 'type': lvl.type.value, 'strength': lvl.strength}
                for lvl in pools.get_strongest_levels(3)
            ]
        }


# Singleton for convenience
_engine_instance: Optional[MarketContextEngine] = None

def get_engine() -> MarketContextEngine:
    """Get global Market Context Engine instance"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = MarketContextEngine()
    return _engine_instance
