"""
Liquidity Pool Analyzer - Order flow and smart money footprint detection

Mathematical basis:
- Liquidity pools identified via swing point clustering (KDE)
- Order imbalance calculated from volume-weighted price levels
- Fair Value Gaps detected via price inefficiency analysis

References:
- Dalton, J. et al. (2007). Markets in Profile
- Williams, B. (2012). Trading Chaos
- SMC (Smart Money Concepts) methodology
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from enum import Enum
import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import find_peaks
import logging


class LiquidityType(Enum):
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    ORDER_BLOCK = "order_block"
    FAIR_VALUE_GAP = "fvg"
    DAILY_OPEN = "daily_open"
    WEEKLY_OPEN = "weekly_open"
    ROUND_NUMBER = "round_number"


@dataclass(frozen=True)
class LiquidityLevel:
    """Single liquidity level with strength scoring"""
    price: float
    type: LiquidityType
    strength: float  # 0-1 score
    volume_support: float  # Volume at this level
    age_bars: int  # How long ago this level formed
    touches: int = 1  # Number of times price tested this level

    def __lt__(self, other):
        """For sorting by price"""
        return self.price < other.price


@dataclass
class LiquidityPools:
    """Complete liquidity map for current market structure"""
    buy_side_liquidity: List[LiquidityLevel] = field(default_factory=list)  # Above price
    sell_side_liquidity: List[LiquidityLevel] = field(default_factory=list)  # Below price
    fair_value_gaps: List[Tuple[float, float]] = field(default_factory=list)  # (low, high) gaps
    current_price: float = 0.0

    def nearest_target_above(self, price: float, min_strength: float = 0.6) -> Optional[float]:
        """Find nearest strong liquidity level above price"""
        candidates = [
            level.price for level in self.buy_side_liquidity
            if level.price > price and level.strength >= min_strength
        ]
        return min(candidates) if candidates else None

    def nearest_support_below(self, price: float, min_strength: float = 0.6) -> Optional[float]:
        """Find nearest strong liquidity level below price"""
        candidates = [
            level.price for level in self.sell_side_liquidity
            if level.price < price and level.strength >= min_strength
        ]
        return max(candidates) if candidates else None

    def get_strongest_levels(self, n: int = 5) -> List[LiquidityLevel]:
        """Get top N strongest levels (both sides)"""
        all_levels = self.buy_side_liquidity + self.sell_side_liquidity
        return sorted(all_levels, key=lambda x: x.strength, reverse=True)[:n]


class LiquidityAnalyzer:
    """
    Institutional-grade liquidity pool detection

    Features:
    - Equal highs/lows detection (stop hunt zones)
    - Order blocks (last down candle before up move)
    - Fair Value Gaps (price inefficiencies)
    - Round number magnets
    - Daily/Weekly opens (institutional levels)
    """

    def __init__(self,
                 equal_tolerance: float = 0.0015,  # 0.15% tolerance
                 min_touches: int = 2,
                 fvg_threshold: float = 0.002):  # 0.2% gap
        """
        Args:
            equal_tolerance: Max price difference for "equal" levels (fraction)
            min_touches: Minimum touches to confirm equal high/low
            fvg_threshold: Minimum gap size as fraction of price
        """
        self.equal_tolerance = equal_tolerance
        self.min_touches = min_touches
        self.fvg_threshold = fvg_threshold
        self.logger = logging.getLogger(__name__)

    def analyze(self, df: pd.DataFrame, current_price: float) -> LiquidityPools:
        """
        Complete liquidity analysis

        Args:
            df: OHLCV DataFrame with DateTimeIndex
            current_price: Current market price

        Returns:
            LiquidityPools with all detected levels
        """
        pools = LiquidityPools(current_price=current_price)

        # 1. Equal Highs/Lows (swing points clustering)
        equal_highs = self._find_equal_highs(df)
        equal_lows = self._find_equal_lows(df)

        # 2. Order Blocks (last opposite candle before impulse)
        order_blocks = self._find_order_blocks(df)

        # 3. Fair Value Gaps
        fvgs = self._find_fair_value_gaps(df)
        pools.fair_value_gaps = fvgs

        # 4. Key institutional levels
        daily_opens = self._find_daily_opens(df)
        weekly_opens = self._find_weekly_opens(df)
        round_numbers = self._find_round_numbers(current_price)

        # Combine all levels and categorize
        all_levels = []

        # Equal highs (buy-side liquidity - stops above)
        for price, touches, age in equal_highs:
            strength = self._calculate_strength(price, touches, age, df)
            volume = self._get_volume_at_price(df, price)
            all_levels.append(LiquidityLevel(
                price=price,
                type=LiquidityType.EQUAL_HIGHS,
                strength=strength,
                volume_support=volume,
                age_bars=age,
                touches=touches
            ))

        # Equal lows (sell-side liquidity - stops below)
        for price, touches, age in equal_lows:
            strength = self._calculate_strength(price, touches, age, df)
            volume = self._get_volume_at_price(df, price)
            all_levels.append(LiquidityLevel(
                price=price,
                type=LiquidityType.EQUAL_LOWS,
                strength=strength,
                volume_support=volume,
                age_bars=age,
                touches=touches
            ))

        # Add other level types
        for ob_price in order_blocks:
            all_levels.append(LiquidityLevel(
                price=ob_price,
                type=LiquidityType.ORDER_BLOCK,
                strength=0.8,  # Order blocks are strong
                volume_support=0.0,
                age_bars=0
            ))

        for do_price in daily_opens:
            all_levels.append(LiquidityLevel(
                price=do_price,
                type=LiquidityType.DAILY_OPEN,
                strength=0.7,
                volume_support=0.0,
                age_bars=0
            ))

        for wo_price in weekly_opens:
            all_levels.append(LiquidityLevel(
                price=wo_price,
                type=LiquidityType.WEEKLY_OPEN,
                strength=0.75,
                volume_support=0.0,
                age_bars=0
            ))

        for rn_price in round_numbers:
            all_levels.append(LiquidityLevel(
                price=rn_price,
                type=LiquidityType.ROUND_NUMBER,
                strength=0.6,
                volume_support=0.0,
                age_bars=0
            ))

        # Categorize by side
        pools.buy_side_liquidity = sorted(
            [lvl for lvl in all_levels if lvl.price >= current_price],
            key=lambda x: x.price
        )
        pools.sell_side_liquidity = sorted(
            [lvl for lvl in all_levels if lvl.price < current_price],
            key=lambda x: x.price,
            reverse=True
        )

        self.logger.info(
            f"Liquidity analysis: {len(pools.buy_side_liquidity)} buy-side, "
            f"{len(pools.sell_side_liquidity)} sell-side, "
            f"{len(pools.fair_value_gaps)} FVGs"
        )

        return pools

    def _find_equal_highs(self, df: pd.DataFrame) -> List[Tuple[float, int, int]]:
        """
        Find equal highs using swing point clustering

        Returns:
            List of (price, num_touches, age_bars)
        """
        if len(df) < 20:
            return []

        # Find swing highs (local maxima)
        highs = df['high'].values
        peaks, _ = find_peaks(highs, distance=3)  # Min 3 bars apart

        if len(peaks) < 2:
            return []

        # Cluster peaks at similar prices
        clusters = []
        for i, peak_idx in enumerate(peaks):
            peak_price = highs[peak_idx]
            age = len(df) - peak_idx

            # Find existing cluster
            found_cluster = False
            for cluster in clusters:
                cluster_price = cluster['prices'][0]
                if abs(peak_price - cluster_price) / cluster_price < self.equal_tolerance:
                    cluster['prices'].append(peak_price)
                    cluster['indices'].append(peak_idx)
                    found_cluster = True
                    break

            if not found_cluster:
                clusters.append({
                    'prices': [peak_price],
                    'indices': [peak_idx]
                })

        # Filter clusters with min touches
        equal_highs = []
        for cluster in clusters:
            if len(cluster['prices']) >= self.min_touches:
                avg_price = np.mean(cluster['prices'])
                touches = len(cluster['prices'])
                youngest_age = len(df) - max(cluster['indices'])
                equal_highs.append((avg_price, touches, youngest_age))

        return equal_highs

    def _find_equal_lows(self, df: pd.DataFrame) -> List[Tuple[float, int, int]]:
        """Find equal lows (inverse of equal highs)"""
        if len(df) < 20:
            return []

        lows = df['low'].values
        troughs, _ = find_peaks(-lows, distance=3)  # Invert for troughs

        if len(troughs) < 2:
            return []

        clusters = []
        for trough_idx in troughs:
            trough_price = lows[trough_idx]

            found_cluster = False
            for cluster in clusters:
                cluster_price = cluster['prices'][0]
                if abs(trough_price - cluster_price) / cluster_price < self.equal_tolerance:
                    cluster['prices'].append(trough_price)
                    cluster['indices'].append(trough_idx)
                    found_cluster = True
                    break

            if not found_cluster:
                clusters.append({
                    'prices': [trough_price],
                    'indices': [trough_idx]
                })

        equal_lows = []
        for cluster in clusters:
            if len(cluster['prices']) >= self.min_touches:
                avg_price = np.mean(cluster['prices'])
                touches = len(cluster['prices'])
                youngest_age = len(df) - max(cluster['indices'])
                equal_lows.append((avg_price, touches, youngest_age))

        return equal_lows

    def _find_order_blocks(self, df: pd.DataFrame) -> List[float]:
        """
        Find order blocks (last opposite candle before strong move)

        Order Block logic:
        - Bullish OB: Last RED candle before strong UP move
        - Bearish OB: Last GREEN candle before strong DOWN move
        """
        order_blocks = []

        if len(df) < 10:
            return order_blocks

        # Look for strong moves (>1% in one candle)
        strong_move_threshold = 0.01
        returns = (df['close'] - df['open']) / df['open']

        for i in range(5, len(df) - 1):
            current_return = returns.iloc[i]

            # Strong bullish candle
            if current_return > strong_move_threshold:
                # Find last bearish candle before this
                for j in range(i-1, max(0, i-5), -1):
                    if returns.iloc[j] < 0:  # Red candle
                        # Order block at this candle's low
                        order_blocks.append(float(df['low'].iloc[j]))
                        break

            # Strong bearish candle
            elif current_return < -strong_move_threshold:
                for j in range(i-1, max(0, i-5), -1):
                    if returns.iloc[j] > 0:  # Green candle
                        # Order block at this candle's high
                        order_blocks.append(float(df['high'].iloc[j]))
                        break

        # Keep only recent (last 50 bars)
        recent_blocks = order_blocks[-10:] if len(order_blocks) > 10 else order_blocks

        return recent_blocks

    def _find_fair_value_gaps(self, df: pd.DataFrame) -> List[Tuple[float, float]]:
        """
        Find Fair Value Gaps (price inefficiencies)

        FVG = gap between candle[i-1] and candle[i+1] not filled by candle[i]
        """
        fvgs = []

        if len(df) < 3:
            return fvgs

        for i in range(1, len(df) - 1):
            prev_candle = df.iloc[i-1]
            curr_candle = df.iloc[i]
            next_candle = df.iloc[i+1]

            # Bullish FVG: gap between prev.high and next.low
            if prev_candle['high'] < next_candle['low']:
                gap_size = (next_candle['low'] - prev_candle['high']) / curr_candle['close']
                if gap_size > self.fvg_threshold:
                    fvgs.append((float(prev_candle['high']), float(next_candle['low'])))

            # Bearish FVG: gap between prev.low and next.high
            elif prev_candle['low'] > next_candle['high']:
                gap_size = (prev_candle['low'] - next_candle['high']) / curr_candle['close']
                if gap_size > self.fvg_threshold:
                    fvgs.append((float(next_candle['high']), float(prev_candle['low'])))

        # Keep recent gaps only
        return fvgs[-5:] if len(fvgs) > 5 else fvgs

    def _find_daily_opens(self, df: pd.DataFrame) -> List[float]:
        """Find recent daily open prices"""
        if not isinstance(df.index, pd.DatetimeIndex):
            return []

        try:
            daily_data = df.resample('D').first()['open'].dropna()
            return [float(p) for p in daily_data.tail(5)]
        except Exception:
            return []

    def _find_weekly_opens(self, df: pd.DataFrame) -> List[float]:
        """Find recent weekly open prices"""
        if not isinstance(df.index, pd.DatetimeIndex):
            return []

        try:
            weekly_data = df.resample('W').first()['open'].dropna()
            return [float(p) for p in weekly_data.tail(3)]
        except Exception:
            return []

    def _find_round_numbers(self, current_price: float) -> List[float]:
        """
        Find nearby round numbers (psychological levels)

        Example: if price = 51234, round numbers are 51000, 51500, 52000
        """
        # Determine order of magnitude
        magnitude = 10 ** int(np.log10(current_price))

        # Round number intervals based on magnitude
        if magnitude >= 10000:
            interval = 1000
        elif magnitude >= 1000:
            interval = 500
        elif magnitude >= 100:
            interval = 50
        else:
            interval = 10

        # Find rounds within ±5% of current price
        lower_bound = current_price * 0.95
        upper_bound = current_price * 1.05

        round_numbers = []
        test_price = (current_price // interval) * interval  # Round down

        # Check below
        while test_price >= lower_bound:
            if test_price != current_price:  # Don't include current price
                round_numbers.append(float(test_price))
            test_price -= interval

        # Check above
        test_price = ((current_price // interval) + 1) * interval
        while test_price <= upper_bound:
            round_numbers.append(float(test_price))
            test_price += interval

        return sorted(round_numbers)

    def _calculate_strength(self, price: float, touches: int, age: int, df: pd.DataFrame) -> float:
        """
        Calculate level strength score [0-1]

        Factors:
        - Number of touches (more = stronger)
        - Age (recent = stronger)
        - Volume at level (high = stronger)
        """
        # Touch factor: diminishing returns
        touch_score = min(touches / 5.0, 1.0)  # Max at 5 touches

        # Age factor: exponential decay (half-life = 100 bars)
        age_score = np.exp(-age / 100.0)

        # Volume factor (if available)
        volume_score = 0.5  # Default
        try:
            volume_at_level = self._get_volume_at_price(df, price)
            avg_volume = df['volume'].mean()
            if avg_volume > 0:
                volume_score = min(volume_at_level / avg_volume, 1.0)
        except Exception:
            pass

        # Weighted combination
        strength = (
            touch_score * 0.4 +
            age_score * 0.3 +
            volume_score * 0.3
        )

        return float(np.clip(strength, 0.0, 1.0))

    def _get_volume_at_price(self, df: pd.DataFrame, price: float) -> float:
        """Estimate volume traded at specific price level"""
        tolerance = price * 0.005  # 0.5% tolerance

        # Find bars where price level was touched
        mask = (
            ((df['low'] <= price) & (df['high'] >= price)) |
            (abs(df['close'] - price) < tolerance)
        )

        if mask.sum() > 0:
            return float(df.loc[mask, 'volume'].sum())

        return 0.0
