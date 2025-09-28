# bot/strategy/base/market_regime_mixin.py
"""
Миксин для определения и управления рыночными режимами
Устраняет дублирование логики анализа рыночных условий
"""

from __future__ import annotations

from typing import Dict, Any, Optional, Callable, List
from enum import Enum
import pandas as pd
import numpy as np
from .enums import MarketRegime


class VolatilityMode(Enum):
    """Режимы волатильности."""
    VERY_LOW = "very_low"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class TrendMode(Enum):
    """Режимы тренда."""
    STRONG_BEARISH = "strong_bearish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    BULLISH = "bullish"
    STRONG_BULLISH = "strong_bullish"


class MarketRegimeMixin:
    """
    Миксин для унифицированного определения рыночных режимов.

    Предоставляет продвинутые методы анализа рыночных условий
    и устраняет дублирование между стратегиями.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_market_regime: MarketRegime = MarketRegime.NORMAL
        self.current_volatility_mode: VolatilityMode = VolatilityMode.NORMAL
        self.current_trend_mode: TrendMode = TrendMode.SIDEWAYS
        self._regime_history: List[Dict[str, Any]] = []

    def update_market_regime(
        self,
        df: pd.DataFrame,
        lookback_period: int = 20,
        custom_thresholds: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Комплексное обновление рыночного режима.

        Args:
            df: DataFrame с OHLCV данными
            lookback_period: Период для расчета характеристик
            custom_thresholds: Кастомные пороги для классификации
        """

        try:
            # Расчет характеристик рынка
            market_characteristics = self._calculate_market_characteristics(df, lookback_period)

            # Определение режимов
            volatility_mode = self._classify_volatility(
                market_characteristics['volatility'],
                custom_thresholds
            )
            trend_mode = self._classify_trend(
                market_characteristics['trend_strength'],
                market_characteristics['trend_direction'],
                custom_thresholds
            )
            market_regime = self._classify_market_regime(
                volatility_mode,
                trend_mode,
                market_characteristics
            )

            # Обновление состояния
            self._update_regime_state(
                market_regime, volatility_mode, trend_mode, market_characteristics
            )

        except Exception as exc:
            self.logger.error(f"Ошибка обновления рыночного режима: {exc}")
            self._set_default_regimes()

    def _calculate_market_characteristics(
        self,
        df: pd.DataFrame,
        lookback_period: int
    ) -> Dict[str, float]:
        """Расчет характеристик рынка для классификации."""

        if len(df) < lookback_period:
            lookback_period = len(df)

        # Расчет доходностей
        returns = df['close'].pct_change().dropna()
        recent_returns = returns.tail(lookback_period)

        if recent_returns.empty:
            return self._get_default_characteristics()

        # Волатильность
        volatility = recent_returns.std()

        # Характеристики тренда
        price_change = (df['close'].iloc[-1] - df['close'].iloc[-lookback_period]) / df['close'].iloc[-lookback_period]
        trend_strength = abs(price_change)
        trend_direction = 1 if price_change > 0 else -1 if price_change < 0 else 0

        # Дополнительные характеристики
        volume_characteristics = self._calculate_volume_characteristics(df, lookback_period)
        momentum_characteristics = self._calculate_momentum_characteristics(df, lookback_period)

        characteristics = {
            'volatility': volatility,
            'trend_strength': trend_strength,
            'trend_direction': trend_direction,
            'price_change_pct': price_change * 100,
            'avg_volume_ratio': volume_characteristics.get('avg_volume_ratio', 1.0),
            'momentum_score': momentum_characteristics.get('momentum_score', 0.0),
            'atr_normalized': self._calculate_normalized_atr(df, lookback_period),
        }

        return characteristics

    def _calculate_volume_characteristics(
        self,
        df: pd.DataFrame,
        lookback_period: int
    ) -> Dict[str, float]:
        """Расчет характеристик объема."""

        if 'volume' not in df.columns or df['volume'].empty:
            return {'avg_volume_ratio': 1.0}

        recent_volumes = df['volume'].tail(lookback_period)
        avg_volume = recent_volumes.mean()
        volume_ma = df['volume'].rolling(window=lookback_period*2).mean().iloc[-1]

        volume_ratio = avg_volume / volume_ma if volume_ma > 0 else 1.0

        return {
            'avg_volume_ratio': volume_ratio,
            'volume_trend': 1 if recent_volumes.iloc[-1] > recent_volumes.iloc[0] else -1,
        }

    def _calculate_momentum_characteristics(
        self,
        df: pd.DataFrame,
        lookback_period: int
    ) -> Dict[str, float]:
        """Расчет характеристик моментума."""

        try:
            # Простой RSI-подобный индикатор
            price_changes = df['close'].diff().tail(lookback_period)
            gains = price_changes.where(price_changes > 0, 0)
            losses = -price_changes.where(price_changes < 0, 0)

            avg_gain = gains.mean()
            avg_loss = losses.mean()

            if avg_loss == 0:
                momentum_score = 1.0
            else:
                rs = avg_gain / avg_loss
                momentum_score = 1 - (1 / (1 + rs))

            # Нормализация в диапазон [-1, 1]
            momentum_score = (momentum_score - 0.5) * 2

            return {'momentum_score': momentum_score}

        except Exception:
            return {'momentum_score': 0.0}

    def _calculate_normalized_atr(
        self,
        df: pd.DataFrame,
        period: int
    ) -> float:
        """Расчет нормализованного ATR."""

        try:
            high_low = df['high'] - df['low']
            high_close_prev = (df['high'] - df['close'].shift()).abs()
            low_close_prev = (df['low'] - df['close'].shift()).abs()

            true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
            atr = true_range.rolling(window=period).mean().iloc[-1]

            # Нормализация относительно цены
            current_price = df['close'].iloc[-1]
            normalized_atr = atr / current_price if current_price > 0 else 0

            return normalized_atr

        except Exception:
            return 0.01  # Fallback значение

    def _classify_volatility(
        self,
        volatility: float,
        custom_thresholds: Optional[Dict[str, float]] = None
    ) -> VolatilityMode:
        """Классификация режима волатильности."""

        # Дефолтные пороги (могут быть переопределены)
        default_thresholds = {
            'very_low': 0.005,
            'low': 0.015,
            'normal': 0.035,
            'high': 0.065,
        }

        thresholds = {**default_thresholds, **(custom_thresholds or {})}

        if volatility < thresholds['very_low']:
            return VolatilityMode.VERY_LOW
        elif volatility < thresholds['low']:
            return VolatilityMode.LOW
        elif volatility < thresholds['normal']:
            return VolatilityMode.NORMAL
        elif volatility < thresholds['high']:
            return VolatilityMode.HIGH
        else:
            return VolatilityMode.EXTREME

    def _classify_trend(
        self,
        trend_strength: float,
        trend_direction: int,
        custom_thresholds: Optional[Dict[str, float]] = None
    ) -> TrendMode:
        """Классификация режима тренда."""

        default_thresholds = {
            'weak_trend': 0.02,
            'strong_trend': 0.05,
        }

        thresholds = {**default_thresholds, **(custom_thresholds or {})}

        if trend_strength < thresholds['weak_trend']:
            return TrendMode.SIDEWAYS

        if trend_direction > 0:
            if trend_strength > thresholds['strong_trend']:
                return TrendMode.STRONG_BULLISH
            else:
                return TrendMode.BULLISH
        else:
            if trend_strength > thresholds['strong_trend']:
                return TrendMode.STRONG_BEARISH
            else:
                return TrendMode.BEARISH

    def _classify_market_regime(
        self,
        volatility_mode: VolatilityMode,
        trend_mode: TrendMode,
        characteristics: Dict[str, float]
    ) -> MarketRegime:
        """Определение общего рыночного режима на основе компонентов."""

        # Логика комбинирования режимов
        if volatility_mode in [VolatilityMode.HIGH, VolatilityMode.EXTREME]:
            return MarketRegime.VOLATILE

        if trend_mode == TrendMode.SIDEWAYS:
            return MarketRegime.SIDEWAYS

        if volatility_mode in [VolatilityMode.VERY_LOW, VolatilityMode.LOW]:
            if trend_mode in [TrendMode.BULLISH, TrendMode.BEARISH]:
                return MarketRegime.TRENDING
            else:
                return MarketRegime.SIDEWAYS

        # Дефолтный режим
        return MarketRegime.NORMAL

    def _update_regime_state(
        self,
        market_regime: MarketRegime,
        volatility_mode: VolatilityMode,
        trend_mode: TrendMode,
        characteristics: Dict[str, float]
    ) -> None:
        """Обновление состояния режимов и истории."""

        # Сохранение в историю
        regime_snapshot = {
            'timestamp': pd.Timestamp.now(),
            'market_regime': market_regime,
            'volatility_mode': volatility_mode,
            'trend_mode': trend_mode,
            'characteristics': characteristics.copy(),
        }

        self._regime_history.append(regime_snapshot)

        # Ограничение размера истории
        if len(self._regime_history) > 100:
            self._regime_history = self._regime_history[-50:]

        # Обновление текущего состояния
        previous_regime = self.current_market_regime
        self.current_market_regime = market_regime
        self.current_volatility_mode = volatility_mode
        self.current_trend_mode = trend_mode

        # Логирование изменений режима
        if previous_regime != market_regime:
            self.logger.info(
                f"🔄 Изменение рыночного режима: {previous_regime.value} → {market_regime.value}"
            )

    def _set_default_regimes(self) -> None:
        """Установка дефолтных режимов при ошибке."""
        self.current_market_regime = MarketRegime.NORMAL
        self.current_volatility_mode = VolatilityMode.NORMAL
        self.current_trend_mode = TrendMode.SIDEWAYS

    def _get_default_characteristics(self) -> Dict[str, float]:
        """Дефолтные характеристики рынка."""
        return {
            'volatility': 0.02,
            'trend_strength': 0.01,
            'trend_direction': 0,
            'price_change_pct': 0.0,
            'avg_volume_ratio': 1.0,
            'momentum_score': 0.0,
            'atr_normalized': 0.01,
        }

    # =========================================================================
    # ПУБЛИЧНЫЕ МЕТОДЫ ДЛЯ АНАЛИЗА РЕЖИМОВ
    # =========================================================================

    def is_volatile_market(self) -> bool:
        """Проверка на волатильный рынок."""
        return self.current_market_regime == MarketRegime.VOLATILE

    def is_trending_market(self) -> bool:
        """Проверка на трендовый рынок."""
        return self.current_trend_mode in [
            TrendMode.BULLISH, TrendMode.BEARISH,
            TrendMode.STRONG_BULLISH, TrendMode.STRONG_BEARISH
        ]

    def is_sideways_market(self) -> bool:
        """Проверка на боковой рынок."""
        return self.current_market_regime == MarketRegime.SIDEWAYS

    def get_market_analysis(self) -> Dict[str, Any]:
        """
        Получение полного анализа текущего рыночного режима.

        Returns:
            Детальная информация о рыночных условиях
        """

        if not self._regime_history:
            return {'status': 'no_data'}

        latest = self._regime_history[-1]

        analysis = {
            'market_regime': self.current_market_regime.value,
            'volatility_mode': self.current_volatility_mode.value,
            'trend_mode': self.current_trend_mode.value,
            'characteristics': latest['characteristics'],
            'is_volatile': self.is_volatile_market(),
            'is_trending': self.is_trending_market(),
            'is_sideways': self.is_sideways_market(),
            'regime_stability': self._calculate_regime_stability(),
            'recommendations': self._get_regime_recommendations(),
        }

        return analysis

    def _calculate_regime_stability(self) -> float:
        """Расчет стабильности текущего режима."""

        if len(self._regime_history) < 5:
            return 0.5  # Недостаточно данных

        recent_regimes = [entry['market_regime'] for entry in self._regime_history[-10:]]
        current_regime_count = recent_regimes.count(self.current_market_regime)

        stability = current_regime_count / len(recent_regimes)
        return stability

    def _get_regime_recommendations(self) -> Dict[str, str]:
        """Получение рекомендаций на основе текущего режима."""

        recommendations = {}

        if self.is_volatile_market():
            recommendations['trading'] = 'Осторожная торговля, широкие стопы'
            recommendations['position_sizing'] = 'Уменьшенные позиции'
            recommendations['strategy_type'] = 'Скальпинг или отложенные стратегии'

        elif self.is_trending_market():
            recommendations['trading'] = 'Следование тренду, трендовые стратегии'
            recommendations['position_sizing'] = 'Стандартные позиции'
            recommendations['strategy_type'] = 'Momentum и breakout стратегии'

        elif self.is_sideways_market():
            recommendations['trading'] = 'Range trading, mean reversion'
            recommendations['position_sizing'] = 'Стандартные позиции'
            recommendations['strategy_type'] = 'Отскоки от уровней, grid trading'

        else:
            recommendations['trading'] = 'Универсальные стратегии'
            recommendations['position_sizing'] = 'Стандартные позиции'
            recommendations['strategy_type'] = 'Адаптивные стратегии'

        return recommendations

    def get_regime_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение истории режимов."""
        return self._regime_history[-limit:] if self._regime_history else []


# =========================================================================
# ДЕКОРАТОР ДЛЯ АВТОМАТИЧЕСКОЙ ИНТЕГРАЦИИ
# =========================================================================

def with_market_regime_analysis(
    update_frequency: int = 1,
    custom_thresholds: Optional[Dict[str, float]] = None
):
    """
    Декоратор для автоматической интеграции анализа рыночных режимов.

    Args:
        update_frequency: Частота обновления режима (каждые N итераций)
        custom_thresholds: Кастомные пороги для классификации

    Usage:
        @with_market_regime_analysis(update_frequency=5)
        class MyStrategy(BaseStrategy):
            pass
    """

    def decorator(cls):
        # Добавление миксина если его нет
        if not issubclass(cls, MarketRegimeMixin):
            class_name = cls.__name__
            new_cls = type(class_name, (MarketRegimeMixin, cls), {})
            new_cls.__module__ = cls.__module__
            cls = new_cls

        # Замена или расширение метода _on_market_analysis
        original_method = getattr(cls, '_on_market_analysis', None)

        def enhanced_market_analysis(self, market_analysis: Dict[str, Any], df: pd.DataFrame):
            # Обновление режима с заданной частотой
            if hasattr(self, '_execution_count') and self._execution_count % update_frequency == 0:
                self.update_market_regime(df, custom_thresholds=custom_thresholds)

            # Вызов оригинального метода если есть
            if original_method:
                original_method(self, market_analysis, df)

        cls._on_market_analysis = enhanced_market_analysis

        # Сохранение ссылки на оригинальный метод
        if original_method:
            cls._original_on_market_analysis = original_method

        return cls

    return decorator