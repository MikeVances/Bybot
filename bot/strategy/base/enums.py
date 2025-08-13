# bot/strategy/base/enums.py
"""
Базовые перечисления для торговых стратегий
Содержит все enum'ы используемые в стратегиях
"""

from enum import Enum, auto
from typing import List


class MarketRegime(Enum):
    """Режимы рынка для адаптации параметров стратегий"""
    NORMAL = "normal"
    VOLATILE = "volatile" 
    TRENDING = "trending"
    SIDEWAYS = "sideways"
    HIGH_VOLUME = "high_volume"
    LOW_VOLUME = "low_volume"
    
    @classmethod
    def from_string(cls, value: str) -> 'MarketRegime':
        """Создание enum из строки"""
        for regime in cls:
            if regime.value.lower() == value.lower():
                return regime
        raise ValueError(f"Unknown market regime: {value}")
    
    def is_stable(self) -> bool:
        """Проверка стабильности режима"""
        return self in [MarketRegime.NORMAL, MarketRegime.SIDEWAYS]
    
    def is_volatile(self) -> bool:
        """Проверка волатильности режима"""
        return self in [MarketRegime.VOLATILE, MarketRegime.HIGH_VOLUME]


class SignalType(Enum):
    """Типы торговых сигналов"""
    BUY = "BUY"
    SELL = "SELL"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    HOLD = "HOLD"
    NO_SIGNAL = "NO_SIGNAL"
    
    @property
    def is_entry(self) -> bool:
        """Проверка является ли сигнал входом в позицию"""
        return self in [SignalType.BUY, SignalType.SELL]
    
    @property 
    def is_exit(self) -> bool:
        """Проверка является ли сигнал выходом из позиции"""
        return self in [SignalType.EXIT_LONG, SignalType.EXIT_SHORT]
    
    @property
    def is_long_direction(self) -> bool:
        """Проверка направления в лонг"""
        return self in [SignalType.BUY, SignalType.EXIT_SHORT]
    
    @property
    def is_short_direction(self) -> bool:
        """Проверка направления в шорт"""
        return self in [SignalType.SELL, SignalType.EXIT_LONG]


class PositionSide(Enum):
    """Стороны торговых позиций"""
    LONG = "BUY"
    SHORT = "SELL"
    FLAT = "FLAT"  # Нет позиции
    
    @classmethod
    def from_signal(cls, signal: SignalType) -> 'PositionSide':
        """Получение стороны позиции из сигнала"""
        if signal == SignalType.BUY:
            return cls.LONG
        elif signal == SignalType.SELL:
            return cls.SHORT
        else:
            return cls.FLAT
    
    @property
    def opposite(self) -> 'PositionSide':
        """Получение противоположной стороны"""
        if self == PositionSide.LONG:
            return PositionSide.SHORT
        elif self == PositionSide.SHORT:
            return PositionSide.LONG
        else:
            return PositionSide.FLAT
    
    @property
    def exit_signal(self) -> SignalType:
        """Получение сигнала выхода для текущей позиции"""
        if self == PositionSide.LONG:
            return SignalType.EXIT_LONG
        elif self == PositionSide.SHORT:
            return SignalType.EXIT_SHORT
        else:
            return SignalType.NO_SIGNAL


class ConfluenceFactor(Enum):
    """Факторы подтверждения сигналов (confluence)"""
    # Объемные факторы
    VOLUME_SPIKE = "volume_spike"
    VOLUME_INCREASING = "volume_increasing" 
    HIGH_VOLUME = "high_volume"
    POSITIVE_VOLUME_FLOW = "positive_volume_flow"
    NEGATIVE_VOLUME_FLOW = "negative_volume_flow"
    
    # Трендовые факторы
    BULLISH_TREND = "bullish_trend"
    BEARISH_TREND = "bearish_trend"
    STRONG_TREND = "strong_trend"
    TREND_ACCELERATION = "trend_acceleration"
    TRENDS_ALIGNED_BULLISH = "trends_aligned_bullish"
    TRENDS_ALIGNED_BEARISH = "trends_aligned_bearish"
    
    # Уровневые факторы
    AT_SUPPORT = "at_support"
    AT_RESISTANCE = "at_resistance"
    BREAKOUT_SUPPORT = "breakout_support"
    BREAKOUT_RESISTANCE = "breakout_resistance"
    
    # Индикаторные факторы
    RSI_FAVORABLE = "rsi_favorable"
    RSI_OVERSOLD = "rsi_oversold"
    RSI_OVERBOUGHT = "rsi_overbought"
    MACD_BULLISH = "macd_bullish"
    MACD_BEARISH = "macd_bearish"
    BB_OVERSOLD = "bb_oversold"
    BB_OVERBOUGHT = "bb_overbought"
    
    # VWAP факторы
    PRICE_ABOVE_VWAP = "price_above_vwap"
    PRICE_BELOW_VWAP = "price_below_vwap"
    VWAP_DEVIATION = "vwap_deviation"
    
    # Дельта факторы
    POSITIVE_DELTA = "positive_delta"
    NEGATIVE_DELTA = "negative_delta"
    DELTA_MOMENTUM = "delta_momentum"
    
    # Моментум факторы
    MOMENTUM_ALIGNED = "momentum_aligned"
    MOMENTUM_BULLISH = "momentum_bullish"
    MOMENTUM_BEARISH = "momentum_bearish"
    
    @classmethod
    def get_volume_factors(cls) -> List['ConfluenceFactor']:
        """Получение всех объемных факторов"""
        return [
            cls.VOLUME_SPIKE, cls.VOLUME_INCREASING, cls.HIGH_VOLUME,
            cls.POSITIVE_VOLUME_FLOW, cls.NEGATIVE_VOLUME_FLOW
        ]
    
    @classmethod
    def get_trend_factors(cls) -> List['ConfluenceFactor']:
        """Получение всех трендовых факторов"""
        return [
            cls.BULLISH_TREND, cls.BEARISH_TREND, cls.STRONG_TREND,
            cls.TREND_ACCELERATION, cls.TRENDS_ALIGNED_BULLISH, cls.TRENDS_ALIGNED_BEARISH
        ]
    
    @classmethod
    def get_indicator_factors(cls) -> List['ConfluenceFactor']:
        """Получение всех индикаторных факторов"""
        return [
            cls.RSI_FAVORABLE, cls.RSI_OVERSOLD, cls.RSI_OVERBOUGHT,
            cls.MACD_BULLISH, cls.MACD_BEARISH, cls.BB_OVERSOLD, cls.BB_OVERBOUGHT
        ]


class TimeFrame(Enum):
    """Таймфреймы для мультитаймфрейм анализа"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    
    @property
    def minutes(self) -> int:
        """Получение количества минут в таймфрейме"""
        mapping = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
            "1w": 10080
        }
        return mapping.get(self.value, 5)
    
    @property
    def seconds(self) -> int:
        """Получение количества секунд в таймфрейме"""
        return self.minutes * 60
    
    @classmethod
    def from_string(cls, value: str) -> 'TimeFrame':
        """Создание TimeFrame из строки"""
        for tf in cls:
            if tf.value.lower() == value.lower():
                return tf
        raise ValueError(f"Unknown timeframe: {value}")
    
    def is_higher_than(self, other: 'TimeFrame') -> bool:
        """Проверка является ли таймфрейм выше другого"""
        return self.minutes > other.minutes
    
    def is_lower_than(self, other: 'TimeFrame') -> bool:
        """Проверка является ли таймфрейм ниже другого"""
        return self.minutes < other.minutes


class StrategyType(Enum):
    """Типы стратегий"""
    VOLUME_VWAP = "volume_vwap"
    CUMDELTA_SR = "cumdelta_sr"
    MULTITF_VOLUME = "multitf_volume"
    CUSTOM = "custom"
    
    @classmethod
    def get_available_strategies(cls) -> List[str]:
        """Получение списка доступных стратегий"""
        return [strategy.value for strategy in cls if strategy != cls.CUSTOM]


class ExitReason(Enum):
    """Причины выхода из позиции"""
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"
    REVERSE_SIGNAL = "reverse_signal"
    MANUAL_EXIT = "manual_exit"
    RISK_MANAGEMENT = "risk_management"
    MARKET_CLOSE = "market_close"
    ERROR_EXIT = "error_exit"
    
    @property
    def is_profitable(self) -> bool:
        """Проверка является ли выход прибыльным"""
        return self in [ExitReason.TAKE_PROFIT, ExitReason.TRAILING_STOP]
    
    @property
    def is_loss(self) -> bool:
        """Проверка является ли выход убыточным"""
        return self in [ExitReason.STOP_LOSS, ExitReason.RISK_MANAGEMENT]


class OrderType(Enum):
    """Типы ордеров"""
    MARKET = "Market"
    LIMIT = "Limit"
    STOP = "Stop"
    STOP_LIMIT = "StopLimit"
    TRAILING_STOP = "TrailingStop"
    
    @property
    def is_market_order(self) -> bool:
        """Проверка является ли ордер рыночным"""
        return self == OrderType.MARKET
    
    @property
    def requires_price(self) -> bool:
        """Проверка требует ли ордер указания цены"""
        return self in [OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT]


class ValidationLevel(Enum):
    """Уровни валидации данных"""
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"
    PARANOID = "paranoid"
    
    @property
    def min_data_points(self) -> int:
        """Минимальное количество точек данных для валидации"""
        mapping = {
            ValidationLevel.BASIC: 10,
            ValidationLevel.STANDARD: 50,
            ValidationLevel.STRICT: 100,
            ValidationLevel.PARANOID: 200
        }
        return mapping[self]


class LogLevel(Enum):
    """Уровни логирования"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class PerformanceMetric(Enum):
    """Метрики производительности стратегий"""
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    SHARPE_RATIO = "sharpe_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    TOTAL_RETURN = "total_return"
    AVERAGE_WIN = "average_win"
    AVERAGE_LOSS = "average_loss"
    TRADES_COUNT = "trades_count"
    AVERAGE_TRADE_DURATION = "average_trade_duration"
    
    @classmethod
    def get_core_metrics(cls) -> List['PerformanceMetric']:
        """Получение основных метрик"""
        return [
            cls.WIN_RATE, cls.PROFIT_FACTOR, cls.TOTAL_RETURN, 
            cls.MAX_DRAWDOWN, cls.TRADES_COUNT
        ]


# Константы для быстрого доступа
DEFAULT_TIMEFRAMES = [TimeFrame.M5, TimeFrame.H1]
STANDARD_CONFLUENCE_FACTORS = [
    ConfluenceFactor.VOLUME_SPIKE,
    ConfluenceFactor.BULLISH_TREND,
    ConfluenceFactor.RSI_FAVORABLE
]

# Маппинги для совместимости
SIGNAL_TYPE_MAPPING = {
    "BUY": SignalType.BUY,
    "SELL": SignalType.SELL,
    "EXIT_LONG": SignalType.EXIT_LONG,
    "EXIT_SHORT": SignalType.EXIT_SHORT
}

POSITION_SIDE_MAPPING = {
    "BUY": PositionSide.LONG,
    "SELL": PositionSide.SHORT,
    "LONG": PositionSide.LONG,
    "SHORT": PositionSide.SHORT
}