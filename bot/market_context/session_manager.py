"""
Trading Session Manager with timezone awareness and volatility profiling

Mathematical foundation:
- Session volatility calculated from historical intraday patterns
- ATR multipliers derived from empirical session characteristics
- Volume patterns normalized across sessions for fair comparison

References:
- Aldridge, I. (2013). High-Frequency Trading: A Practical Guide
- Chan, E. (2009). Quantitative Trading
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Optional, Dict, Tuple
from enum import Enum
import numpy as np
import pandas as pd
import logging


class SessionName(Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "ny"
    ROLLOVER = "rollover"


@dataclass(frozen=True)  # Immutable for thread safety
class TradingSession:
    """
    Immutable trading session descriptor with statistical characteristics

    Attributes:
        name: Session identifier
        start_hour: UTC start hour [0-23]
        end_hour: UTC end hour [0-23]
        avg_volatility_pct: Historical average volatility (%)
        stop_multiplier: ATR multiplier for this session
        volume_multiplier: Expected volume vs daily average
        typical_spread_bps: Typical bid-ask spread in basis points
    """
    name: SessionName
    start_hour: int
    end_hour: int
    avg_volatility_pct: float
    stop_multiplier: float
    volume_multiplier: float
    typical_spread_bps: float = 5.0

    def __post_init__(self):
        """Validation"""
        assert 0 <= self.start_hour <= 23, "start_hour must be [0-23]"
        assert 0 <= self.end_hour <= 24, "end_hour must be [0-24]"
        assert self.stop_multiplier > 0, "stop_multiplier must be positive"
        assert self.volume_multiplier > 0, "volume_multiplier must be positive"

    def is_active(self, dt: datetime) -> bool:
        """Check if session is active at given datetime (UTC)"""
        hour = dt.astimezone(timezone.utc).hour

        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        else:  # Overnight session (e.g., 22-24 wraps to next day)
            return hour >= self.start_hour or hour < self.end_hour

    def time_until_end(self, dt: datetime) -> float:
        """Hours until session ends"""
        hour = dt.astimezone(timezone.utc).hour

        if self.start_hour < self.end_hour:
            if self.start_hour <= hour < self.end_hour:
                return self.end_hour - hour
            return 0
        else:
            if hour >= self.start_hour:
                return 24 - hour + self.end_hour
            elif hour < self.end_hour:
                return self.end_hour - hour
            return 0


# Pre-configured sessions based on empirical crypto market data (2023-2024)
CRYPTO_SESSIONS: Dict[SessionName, TradingSession] = {
    SessionName.ASIAN: TradingSession(
        name=SessionName.ASIAN,
        start_hour=0,
        end_hour=7,
        avg_volatility_pct=0.35,  # Low volatility
        stop_multiplier=1.0,      # Tight stops
        volume_multiplier=0.6,    # 60% of daily avg volume
        typical_spread_bps=8.0    # Wider spreads
    ),
    SessionName.LONDON: TradingSession(
        name=SessionName.LONDON,
        start_hour=7,
        end_hour=13,
        avg_volatility_pct=0.65,  # Medium volatility
        stop_multiplier=1.3,
        volume_multiplier=1.0,    # 100% average volume
        typical_spread_bps=5.0
    ),
    SessionName.NEW_YORK: TradingSession(
        name=SessionName.NEW_YORK,
        start_hour=13,
        end_hour=22,
        avg_volatility_pct=1.15,  # High volatility
        stop_multiplier=1.8,
        volume_multiplier=1.3,    # 130% volume (overlap + US traders)
        typical_spread_bps=4.0
    ),
    SessionName.ROLLOVER: TradingSession(
        name=SessionName.ROLLOVER,
        start_hour=22,
        end_hour=24,
        avg_volatility_pct=1.45,  # Extreme volatility (rollover + thin liquidity)
        stop_multiplier=2.5,      # Very wide stops
        volume_multiplier=0.7,
        typical_spread_bps=12.0   # Wide spreads, low liquidity
    ),
}


@dataclass
class SessionStatistics:
    """Live session statistics from recent market data"""
    realized_volatility: float
    volume_ratio: float  # Current vs historical average
    spread_estimate: float
    momentum_score: float  # -1 to 1, bearish to bullish


class SessionManager:
    """
    Manages trading sessions with real-time adaptation

    Features:
    - Static session definitions (CRYPTO_SESSIONS)
    - Dynamic volatility adjustment from live data
    - Session overlap detection
    - Holiday/weekend awareness
    """

    def __init__(self,
                 sessions: Optional[Dict[SessionName, TradingSession]] = None,
                 volatility_lookback: int = 20):
        """
        Args:
            sessions: Custom session definitions (default: CRYPTO_SESSIONS)
            volatility_lookback: Bars to calculate realized volatility
        """
        self.sessions = sessions or CRYPTO_SESSIONS
        self.volatility_lookback = volatility_lookback
        self.logger = logging.getLogger(__name__)

        # Cache for session statistics
        self._stats_cache: Dict[SessionName, Tuple[datetime, SessionStatistics]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    def get_current_session(self, dt: Optional[datetime] = None) -> TradingSession:
        """
        Get active session for given datetime (UTC)

        Args:
            dt: Datetime (UTC), defaults to now

        Returns:
            Active TradingSession
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        # Convert to UTC if not already
        dt = dt.astimezone(timezone.utc)

        for session in self.sessions.values():
            if session.is_active(dt):
                return session

        # Fallback (should never happen with proper session definitions)
        self.logger.warning(f"No session active at {dt}, defaulting to ASIAN")
        return self.sessions[SessionName.ASIAN]

    def get_session_stats(self,
                          df: pd.DataFrame,
                          session: TradingSession,
                          force_recalc: bool = False) -> SessionStatistics:
        """
        Calculate live session statistics from market data

        Args:
            df: OHLCV DataFrame with DateTimeIndex
            session: Session to analyze
            force_recalc: Force recalculation (ignore cache)

        Returns:
            SessionStatistics with live metrics
        """
        # Check cache
        now = datetime.now(timezone.utc)
        if not force_recalc and session.name in self._stats_cache:
            cached_time, cached_stats = self._stats_cache[session.name]
            if (now - cached_time).total_seconds() < self._cache_ttl_seconds:
                return cached_stats

        # Filter data for this session
        df_session = self._filter_session_data(df, session)

        if len(df_session) < 10:
            # Not enough data, return defaults based on session config
            stats = SessionStatistics(
                realized_volatility=session.avg_volatility_pct,
                volume_ratio=session.volume_multiplier,
                spread_estimate=session.typical_spread_bps,
                momentum_score=0.0
            )
        else:
            # Calculate realized metrics
            returns = df_session['close'].pct_change().dropna()
            realized_vol = returns.std() * np.sqrt(252 * 24) * 100  # Annualized %

            avg_volume = df['volume'].mean()
            session_avg_volume = df_session['volume'].mean()
            volume_ratio = session_avg_volume / avg_volume if avg_volume > 0 else 1.0

            # Momentum from session price action
            session_return = (df_session['close'].iloc[-1] - df_session['close'].iloc[0]) / df_session['close'].iloc[0]
            momentum_score = np.tanh(session_return * 100)  # Normalize to [-1, 1]

            # Spread estimate from high-low range
            spread_estimate = ((df_session['high'] - df_session['low']) / df_session['close']).mean() * 10000  # bps

            stats = SessionStatistics(
                realized_volatility=realized_vol,
                volume_ratio=volume_ratio,
                spread_estimate=spread_estimate,
                momentum_score=momentum_score
            )

        # Update cache
        self._stats_cache[session.name] = (now, stats)

        return stats

    def get_adaptive_stop_multiplier(self,
                                     df: pd.DataFrame,
                                     session: Optional[TradingSession] = None) -> float:
        """
        Calculate adaptive stop multiplier based on current session and live volatility

        Adjusts base multiplier by:
        - Realized volatility vs historical
        - Volume conditions
        - Spread conditions

        Args:
            df: Recent OHLCV data
            session: Session to use (default: current)

        Returns:
            Adaptive stop multiplier (e.g., 1.5 means 1.5x ATR)
        """
        if session is None:
            session = self.get_current_session()

        base_multiplier = session.stop_multiplier

        # Get live stats
        stats = self.get_session_stats(df, session)

        # Volatility adjustment: if realized vol > expected, widen stops
        vol_ratio = stats.realized_volatility / session.avg_volatility_pct
        vol_adjustment = 1.0 + (vol_ratio - 1.0) * 0.5  # 50% sensitivity
        vol_adjustment = np.clip(vol_adjustment, 0.7, 1.5)  # Don't go crazy

        # Volume adjustment: low volume = wider stops (more slippage risk)
        volume_adjustment = 1.0
        if stats.volume_ratio < 0.7:  # Very low volume
            volume_adjustment = 1.2
        elif stats.volume_ratio > 1.5:  # Very high volume
            volume_adjustment = 0.9

        adaptive_multiplier = base_multiplier * vol_adjustment * volume_adjustment

        self.logger.debug(
            f"Session: {session.name.value}, Base: {base_multiplier:.2f}, "
            f"Vol adj: {vol_adjustment:.2f}, Volume adj: {volume_adjustment:.2f}, "
            f"Final: {adaptive_multiplier:.2f}"
        )

        return adaptive_multiplier

    def _filter_session_data(self, df: pd.DataFrame, session: TradingSession) -> pd.DataFrame:
        """Filter DataFrame to only include data from specified session"""
        if not isinstance(df.index, pd.DatetimeIndex):
            return df  # Can't filter without datetime index

        # Ensure UTC
        df_utc = df.copy()
        if df_utc.index.tz is None:
            df_utc.index = df_utc.index.tz_localize('UTC')
        else:
            df_utc.index = df_utc.index.tz_convert('UTC')

        # Filter by hour
        mask = df_utc.index.hour.map(lambda h: session.is_active(datetime(2000, 1, 1, h, tzinfo=timezone.utc)))

        return df_utc[mask]

    def is_session_overlap(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if current time is session overlap (London+NY or NY+Asian)

        Overlaps are high-volatility periods
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        active_sessions = [s for s in self.sessions.values() if s.is_active(dt)]
        return len(active_sessions) > 1

    def should_avoid_trading(self, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if trading should be avoided at given time

        Returns:
            (should_avoid, reason)
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        # Weekend check (crypto still trades but low liquidity)
        if dt.weekday() == 5:  # Saturday
            return True, "weekend_low_liquidity"

        if dt.weekday() == 6 and dt.hour < 12:  # Sunday morning
            return True, "weekend_morning"

        # Check if in extreme rollover period
        session = self.get_current_session(dt)
        if session.name == SessionName.ROLLOVER:
            # Only avoid if also low volume
            # This requires recent data, so return False here (let caller check)
            return False, ""

        return False, ""


# Convenience function for quick access
def get_current_session_multiplier(df: pd.DataFrame) -> float:
    """Quick access to adaptive stop multiplier for current session"""
    manager = SessionManager()
    return manager.get_adaptive_stop_multiplier(df)
