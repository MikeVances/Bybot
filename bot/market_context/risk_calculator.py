"""
Adaptive Risk/Reward Calculator - Dynamic parameter adjustment based on market regime

Mathematical foundation:
- Trend strength via linear regression R² and slope significance
- Volatility regime classification using GARCH-like rolling estimates
- R/R ratio optimization via Expected Value maximization
- Kelly Criterion for position sizing

References:
- Pardo, R. (2008). The Evaluation and Optimization of Trading Strategies
- Tharp, V. (2007). Trade Your Way to Financial Freedom
- Kelly, J. L. (1956). A New Interpretation of Information Rate
"""

from dataclasses import dataclass
from typing import Tuple, Optional
from enum import Enum
import numpy as np
import pandas as pd
from scipy import stats
import logging


class MarketRegime(Enum):
    """Market regime classification"""
    STRONG_UPTREND = "strong_uptrend"
    UPTREND = "uptrend"
    SIDEWAYS = "sideways"
    DOWNTREND = "downtrend"
    STRONG_DOWNTREND = "strong_downtrend"


class VolatilityRegime(Enum):
    """Volatility classification"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass(frozen=True)
class RiskParameters:
    """
    Complete risk parameter set for position management

    Attributes:
        stop_loss_atr_mult: ATR multiplier for stop loss
        take_profit_atr_mult: ATR multiplier for take profit
        risk_reward_ratio: Target R/R ratio
        position_size_pct: Position size as % of capital
        max_holding_bars: Maximum bars to hold position
        trailing_activation_pct: Profit % to activate trailing stop
    """
    stop_loss_atr_mult: float
    take_profit_atr_mult: float
    risk_reward_ratio: float
    position_size_pct: float
    max_holding_bars: int
    trailing_activation_pct: float

    # Metadata
    market_regime: MarketRegime
    volatility_regime: VolatilityRegime
    confidence: float  # 0-1, how confident are we in these params


class AdaptiveRiskCalculator:
    """
    Calculates optimal risk parameters based on market conditions

    Features:
    - Trend detection via regression analysis
    - Volatility regime classification
    - Dynamic R/R optimization
    - Position sizing with Kelly Criterion
    """

    def __init__(self,
                 trend_period: int = 50,
                 volatility_period: int = 20,
                 min_rr_ratio: float = 1.2,
                 max_rr_ratio: float = 5.0):
        """
        Args:
            trend_period: Bars for trend analysis
            volatility_period: Bars for volatility estimation
            min_rr_ratio: Minimum allowed R/R ratio
            max_rr_ratio: Maximum allowed R/R ratio
        """
        self.trend_period = trend_period
        self.volatility_period = volatility_period
        self.min_rr_ratio = min_rr_ratio
        self.max_rr_ratio = max_rr_ratio
        self.logger = logging.getLogger(__name__)

    def calculate(self,
                  df: pd.DataFrame,
                  current_price: float,
                  signal_direction: str = 'BUY') -> RiskParameters:
        """
        Calculate adaptive risk parameters

        Args:
            df: OHLCV DataFrame
            current_price: Current market price
            signal_direction: 'BUY' or 'SELL'

        Returns:
            RiskParameters optimized for current conditions
        """
        # 1. Detect market regime
        market_regime, trend_strength = self._detect_market_regime(df)

        # 2. Classify volatility
        volatility_regime, volatility_pct = self._classify_volatility(df)

        # 3. Calculate base risk parameters
        base_params = self._get_base_parameters(market_regime, volatility_regime)

        # 4. Adjust for trend alignment
        aligned_params = self._adjust_for_trend_alignment(
            base_params, market_regime, signal_direction, trend_strength
        )

        # 5. Volatility adjustment
        final_params = self._adjust_for_volatility(aligned_params, volatility_pct)

        # 6. Calculate confidence
        confidence = self._calculate_confidence(trend_strength, volatility_regime)

        self.logger.debug(
            f"Risk calc: Regime={market_regime.value}, Vol={volatility_regime.value}, "
            f"R/R={final_params['rr']:.2f}, Confidence={confidence:.2f}"
        )

        return RiskParameters(
            stop_loss_atr_mult=final_params['stop_mult'],
            take_profit_atr_mult=final_params['stop_mult'] * final_params['rr'],
            risk_reward_ratio=final_params['rr'],
            position_size_pct=final_params['pos_size'],
            max_holding_bars=final_params['max_hold'],
            trailing_activation_pct=final_params['trail_act'],
            market_regime=market_regime,
            volatility_regime=volatility_regime,
            confidence=confidence
        )

    def _detect_market_regime(self, df: pd.DataFrame) -> Tuple[MarketRegime, float]:
        """
        Detect market regime using linear regression

        Returns:
            (MarketRegime, trend_strength [0-1])
        """
        if len(df) < self.trend_period:
            return MarketRegime.SIDEWAYS, 0.0

        # Use closing prices for trend
        prices = df['close'].tail(self.trend_period).values
        x = np.arange(len(prices))

        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, prices)

        # Normalize slope to percentage per bar
        slope_pct_per_bar = (slope / prices[-1]) * 100

        # R-squared as trend strength
        r_squared = r_value ** 2
        trend_strength = r_squared  # 0-1 scale

        # Classify regime based on slope and significance
        if p_value > 0.05:  # Not statistically significant
            regime = MarketRegime.SIDEWAYS
        elif slope_pct_per_bar > 0.15:  # >0.15% per bar = strong uptrend
            regime = MarketRegime.STRONG_UPTREND
        elif slope_pct_per_bar > 0.05:
            regime = MarketRegime.UPTREND
        elif slope_pct_per_bar < -0.15:
            regime = MarketRegime.STRONG_DOWNTREND
        elif slope_pct_per_bar < -0.05:
            regime = MarketRegime.DOWNTREND
        else:
            regime = MarketRegime.SIDEWAYS

        return regime, trend_strength

    def _classify_volatility(self, df: pd.DataFrame) -> Tuple[VolatilityRegime, float]:
        """
        Classify volatility regime using realized volatility

        Returns:
            (VolatilityRegime, realized_vol_pct)
        """
        if len(df) < self.volatility_period:
            return VolatilityRegime.NORMAL, 1.0

        # Calculate realized volatility (annualized)
        returns = df['close'].pct_change().tail(self.volatility_period)
        realized_vol = returns.std() * np.sqrt(252 * 24) * 100  # % per year

        # Calculate historical percentile
        if len(df) >= 100:
            historical_vols = df['close'].pct_change().rolling(self.volatility_period).std()
            percentile = stats.percentileofscore(historical_vols.dropna(), realized_vol)

            if percentile > 90:
                regime = VolatilityRegime.EXTREME
            elif percentile > 70:
                regime = VolatilityRegime.HIGH
            elif percentile < 30:
                regime = VolatilityRegime.LOW
            else:
                regime = VolatilityRegime.NORMAL
        else:
            # Absolute thresholds for crypto (Bitcoin-like)
            if realized_vol > 80:
                regime = VolatilityRegime.EXTREME
            elif realized_vol > 50:
                regime = VolatilityRegime.HIGH
            elif realized_vol < 20:
                regime = VolatilityRegime.LOW
            else:
                regime = VolatilityRegime.NORMAL

        return regime, realized_vol

    def _get_base_parameters(self,
                            market_regime: MarketRegime,
                            volatility_regime: VolatilityRegime) -> dict:
        """Get base parameters for regime combination"""

        # Base parameters matrix [stop_mult, rr, pos_size%, max_hold, trail_act%]
        regime_params = {
            # Strong trends: wide stops, high R/R, longer holds
            MarketRegime.STRONG_UPTREND: {
                'stop_mult': 2.0,
                'rr': 4.0,
                'pos_size': 2.5,
                'max_hold': 200,
                'trail_act': 5.0
            },
            MarketRegime.STRONG_DOWNTREND: {
                'stop_mult': 2.0,
                'rr': 4.0,
                'pos_size': 2.5,
                'max_hold': 200,
                'trail_act': 5.0
            },
            # Normal trends: balanced
            MarketRegime.UPTREND: {
                'stop_mult': 1.5,
                'rr': 2.5,
                'pos_size': 2.0,
                'max_hold': 150,
                'trail_act': 3.0
            },
            MarketRegime.DOWNTREND: {
                'stop_mult': 1.5,
                'rr': 2.5,
                'pos_size': 2.0,
                'max_hold': 150,
                'trail_act': 3.0
            },
            # Sideways: tight stops, quick exits
            MarketRegime.SIDEWAYS: {
                'stop_mult': 1.0,
                'rr': 1.5,
                'pos_size': 1.5,
                'max_hold': 50,
                'trail_act': 2.0
            }
        }

        base = regime_params[market_regime].copy()

        # Volatility adjustments
        vol_multipliers = {
            VolatilityRegime.LOW: {'stop': 0.8, 'pos': 1.2},
            VolatilityRegime.NORMAL: {'stop': 1.0, 'pos': 1.0},
            VolatilityRegime.HIGH: {'stop': 1.3, 'pos': 0.8},
            VolatilityRegime.EXTREME: {'stop': 1.8, 'pos': 0.5}
        }

        mult = vol_multipliers[volatility_regime]
        base['stop_mult'] *= mult['stop']
        base['pos_size'] *= mult['pos']

        return base

    def _adjust_for_trend_alignment(self,
                                    params: dict,
                                    market_regime: MarketRegime,
                                    signal_direction: str,
                                    trend_strength: float) -> dict:
        """
        Adjust parameters based on trade alignment with trend

        Trading WITH trend = increase R/R, size
        Trading AGAINST trend = decrease R/R, size
        """
        adjusted = params.copy()

        # Determine alignment
        is_uptrend = market_regime in [MarketRegime.UPTREND, MarketRegime.STRONG_UPTREND]
        is_downtrend = market_regime in [MarketRegime.DOWNTREND, MarketRegime.STRONG_DOWNTREND]

        aligned = (
            (is_uptrend and signal_direction == 'BUY') or
            (is_downtrend and signal_direction == 'SELL')
        )

        if aligned:
            # With trend: boost R/R and size
            adjusted['rr'] *= (1 + trend_strength * 0.5)  # Up to 50% boost
            adjusted['pos_size'] *= (1 + trend_strength * 0.3)  # Up to 30% boost
        else:
            # Counter trend: reduce R/R and size
            adjusted['rr'] *= 0.7  # Reduce by 30%
            adjusted['pos_size'] *= 0.6  # Reduce by 40%

        # Clamp R/R
        adjusted['rr'] = np.clip(adjusted['rr'], self.min_rr_ratio, self.max_rr_ratio)

        return adjusted

    def _adjust_for_volatility(self, params: dict, volatility_pct: float) -> dict:
        """Fine-tune parameters based on realized volatility"""
        adjusted = params.copy()

        # Very low volatility: can afford tighter stops
        if volatility_pct < 15:
            adjusted['stop_mult'] *= 0.9

        # Extreme volatility: need wider stops
        if volatility_pct > 100:
            adjusted['stop_mult'] *= 1.2

        return adjusted

    def _calculate_confidence(self,
                             trend_strength: float,
                             volatility_regime: VolatilityRegime) -> float:
        """
        Calculate confidence in parameter selection

        High confidence when:
        - Strong trend (high R²)
        - Normal volatility
        """
        # Trend contribution
        trend_confidence = trend_strength

        # Volatility contribution
        vol_confidence_map = {
            VolatilityRegime.LOW: 0.7,
            VolatilityRegime.NORMAL: 1.0,
            VolatilityRegime.HIGH: 0.6,
            VolatilityRegime.EXTREME: 0.3
        }
        vol_confidence = vol_confidence_map[volatility_regime]

        # Combined
        confidence = (trend_confidence * 0.6 + vol_confidence * 0.4)

        return float(np.clip(confidence, 0.0, 1.0))


def calculate_kelly_position_size(win_rate: float,
                                   avg_win: float,
                                   avg_loss: float,
                                   kelly_fraction: float = 0.25) -> float:
    """
    Calculate position size using Kelly Criterion

    Args:
        win_rate: Historical win rate [0-1]
        avg_win: Average win in R multiples
        avg_loss: Average loss in R multiples (positive number)
        kelly_fraction: Fraction of Kelly to use (0.25 = quarter Kelly)

    Returns:
        Position size as % of capital
    """
    if win_rate <= 0 or win_rate >= 1:
        return 1.0  # Default

    # Kelly formula: f = (p * b - q) / b
    # where p = win_rate, q = 1-p, b = avg_win/avg_loss
    p = win_rate
    q = 1 - p
    b = avg_win / avg_loss if avg_loss > 0 else 1.0

    kelly = (p * b - q) / b

    # Apply fraction (full Kelly is too aggressive)
    fractional_kelly = kelly * kelly_fraction

    # Clamp to reasonable range
    position_size = np.clip(fractional_kelly * 100, 0.5, 5.0)  # 0.5% to 5%

    return float(position_size)
