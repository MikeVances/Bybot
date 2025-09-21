# bot/strategy/utils/indicators.py
"""
Централизованная библиотека технических индикаторов для торговых стратегий
Все индикаторы в одном месте для устранения дублирования кода
КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: TTL кэширование для производительности
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Union, Tuple, List
import logging
from dataclasses import dataclass
from enum import Enum
import time
import hashlib
from functools import lru_cache
from threading import Lock

# Настройка логирования
logger = logging.getLogger(__name__)

# КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: TTL Cache для индикаторов
class TTLCache:
    """Time-To-Live cache для критических индикаторов"""
    def __init__(self, maxsize: int = 100, ttl: int = 60):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache = {}
        self._timestamps = {}
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps[key] < self.ttl:
                    return self._cache[key]
                else:
                    # Устаревший кэш - удаляем
                    del self._cache[key]
                    del self._timestamps[key]
        return None

    def put(self, key, value):
        with self._lock:
            # Очищаем старые записи если кэш переполнен
            if len(self._cache) >= self.maxsize:
                oldest_key = min(self._timestamps.keys(), key=lambda k: self._timestamps[k])
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]

            self._cache[key] = value
            self._timestamps[key] = time.time()

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

# Глобальные кэши для критических индикаторов
_VWAP_CACHE = TTLCache(maxsize=50, ttl=30)    # VWAP - 30 сек
_RSI_CACHE = TTLCache(maxsize=100, ttl=60)     # RSI - 60 сек
_ATR_CACHE = TTLCache(maxsize=100, ttl=60)     # ATR - 60 сек
_SMA_CACHE = TTLCache(maxsize=200, ttl=120)    # SMA - 2 мин

def _create_data_hash(df: pd.DataFrame, params: str = "") -> str:
    """Создание хэша для кэширования данных"""
    try:
        # Используем последние 10 строк + параметры для хэша
        last_data = df.tail(10)
        data_str = f"{last_data.to_string()}{params}"
        return hashlib.md5(data_str.encode()).hexdigest()[:16]
    except:
        return f"fallback_{time.time()}"


class IndicatorError(Exception):
    """Исключение для ошибок расчета индикаторов"""
    pass


@dataclass
class IndicatorResult:
    """Результат расчета индикатора с метаданными"""
    value: Union[float, pd.Series, Dict]
    is_valid: bool = True
    error_message: Optional[str] = None
    calculation_time: Optional[float] = None
    
    @property
    def is_series(self) -> bool:
        """Проверка является ли результат Series"""
        return isinstance(self.value, pd.Series)
    
    @property
    def is_scalar(self) -> bool:
        """Проверка является ли результат скаляром"""
        return isinstance(self.value, (int, float))
    
    @property
    def last_value(self) -> Optional[float]:
        """Получение последнего значения"""
        if self.is_series and len(self.value) > 0:
            return float(self.value.iloc[-1])
        elif self.is_scalar:
            return float(self.value)
        elif isinstance(self.value, dict) and 'current' in self.value:
            return float(self.value['current'])
        return None


class TechnicalIndicators:
    """
    Централизованный класс для расчета всех технических индикаторов
    Содержит статические методы для безопасного расчета индикаторов
    """
    
    @staticmethod
    def _validate_dataframe(df: pd.DataFrame, required_columns: List[str], min_length: int = 1) -> None:
        """Валидация DataFrame перед расчетом индикаторов"""
        if df is None or df.empty:
            raise IndicatorError("DataFrame пуст или None")
        
        for col in required_columns:
            if col not in df.columns:
                raise IndicatorError(f"Отсутствует необходимая колонка: {col}")
        
        if len(df) < min_length:
            raise IndicatorError(f"Недостаточно данных: {len(df)} < {min_length}")
        
        # Проверка на NaN в требуемых колонках
        if df[required_columns].isnull().any().any():
            raise IndicatorError("Обнаружены NaN значения в данных")
    
    @staticmethod
    def _safe_calculation(func):
        """Декоратор для безопасного выполнения расчетов индикаторов"""
        def wrapper(*args, **kwargs):
            try:
                import time
                start_time = time.time()
                result = func(*args, **kwargs)
                calc_time = time.time() - start_time
                
                if isinstance(result, IndicatorResult):
                    result.calculation_time = calc_time
                    return result
                else:
                    return IndicatorResult(value=result, calculation_time=calc_time)
                    
            except Exception as e:
                logger.error(f"Ошибка расчета индикатора {func.__name__}: {e}")
                return IndicatorResult(
                    value=None, 
                    is_valid=False, 
                    error_message=str(e)
                )
        return wrapper
    
    # =========================================================================
    # БАЗОВЫЕ ИНДИКАТОРЫ
    # =========================================================================
    
    @staticmethod
    @_safe_calculation
    def calculate_sma(df: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
        """
        Simple Moving Average - Простая скользящая средняя
        
        Args:
            df: DataFrame с данными
            period: Период для расчета
            column: Колонка для расчета (по умолчанию 'close')
        
        Returns:
            IndicatorResult с Series значений SMA
        """
        TechnicalIndicators._validate_dataframe(df, [column], period)
        return df[column].rolling(window=period, min_periods=1).mean()
    
    @staticmethod
    @_safe_calculation
    def calculate_ema(df: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
        """
        Exponential Moving Average - Экспоненциальная скользящая средняя
        """
        TechnicalIndicators._validate_dataframe(df, [column], period)
        return df[column].ewm(span=period, min_periods=1).mean()
    
    @staticmethod
    @_safe_calculation
    def calculate_atr_safe(df: pd.DataFrame, period: int = 14) -> float:
        """
        Average True Range - Средний истинный диапазон (безопасная версия)
        
        Args:
            df: DataFrame с OHLC данными
            period: Период для расчета ATR
        
        Returns:
            IndicatorResult с последним значением ATR
        """
        required_cols = ['high', 'low', 'close']
        TechnicalIndicators._validate_dataframe(df, required_cols, period)
        
        # Если данных мало, возвращаем простой диапазон
        if len(df) < period:
            return float(df['high'].iloc[-1] - df['low'].iloc[-1])
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Компоненты True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        # Объединяем и находим максимум
        tr_df = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3})
        tr = tr_df.max(axis=1)
        
        # Рассчитываем ATR
        atr = tr.rolling(window=period, min_periods=1).mean()
        
        # Возвращаем последнее значение с проверкой
        last_atr = atr.iloc[-1]
        
        if pd.isna(last_atr) or last_atr <= 0:
            # Fallback к простому расчету
            fallback_atr = float(df['high'].iloc[-1] - df['low'].iloc[-1])
            logger.warning(f"ATR fallback: {fallback_atr}")
            return fallback_atr
        
        return float(last_atr)
    
    @staticmethod
    @_safe_calculation
    def calculate_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR как Series для графиков и дальнейшего анализа"""
        required_cols = ['high', 'low', 'close']
        TechnicalIndicators._validate_dataframe(df, required_cols, period)
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr_df = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3})
        tr = tr_df.max(axis=1)
        
        return tr.rolling(window=period, min_periods=1).mean()
    
    # =========================================================================
    # ОСЦИЛЛЯТОРЫ
    # =========================================================================
    
    @staticmethod
    @_safe_calculation
    def calculate_rsi(df: pd.DataFrame, period: int = 14, column: str = 'close') -> pd.Series:
        """
        Relative Strength Index - Индекс относительной силы
        КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: TTL кэширование + numpy ускорение

        Args:
            df: DataFrame с данными
            period: Период для расчета RSI
            column: Колонка для расчета

        Returns:
            IndicatorResult с Series значений RSI (0-100)
        """
        # КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: Проверяем кэш
        cache_key = _create_data_hash(df, f"rsi_{period}_{column}")
        cached_result = _RSI_CACHE.get(cache_key)
        if cached_result is not None:
            return cached_result

        TechnicalIndicators._validate_dataframe(df, [column], period + 1)

        # ОПТИМИЗАЦИЯ: Numpy векторизация для скорости
        prices = df[column].values
        deltas = np.diff(prices, prepend=prices[0])

        # Разделяем gains и losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Используем exponential moving average (быстрее rolling)
        alpha = 1.0 / period
        avg_gains = np.zeros_like(gains)
        avg_losses = np.zeros_like(losses)

        # Инициализация первого значения
        if len(gains) > period:
            avg_gains[period] = np.mean(gains[1:period + 1])
            avg_losses[period] = np.mean(losses[1:period + 1])

            # EMA расчет для остальных значений (намного быстрее)
            for i in range(period + 1, len(gains)):
                avg_gains[i] = alpha * gains[i] + (1 - alpha) * avg_gains[i - 1]
                avg_losses[i] = alpha * losses[i] + (1 - alpha) * avg_losses[i - 1]

        # Вычисление RSI
        rs = np.divide(avg_gains, avg_losses, out=np.full_like(avg_gains, np.inf), where=avg_losses != 0)
        rsi_values = 100 - (100 / (1 + rs))

        # Заполняем первые значения нейтральными
        rsi_values[:period] = 50

        # Создаем Series
        rsi = pd.Series(rsi_values, index=df.index, name=f'rsi_{period}')

        # КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: Сохраняем в кэш
        result = IndicatorResult(value=rsi, is_valid=True)
        _RSI_CACHE.put(cache_key, result)

        return result
    
    @staticmethod
    @_safe_calculation
    def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, 
                      signal: int = 9, column: str = 'close') -> Dict[str, pd.Series]:
        """
        MACD - Moving Average Convergence Divergence
        
        Returns:
            IndicatorResult с dict содержащим 'macd', 'signal', 'histogram'
        """
        TechnicalIndicators._validate_dataframe(df, [column], slow + signal)
        
        if fast >= slow:
            raise IndicatorError("Быстрый период должен быть меньше медленного")
        
        ema_fast = df[column].ewm(span=fast, min_periods=1).mean()
        ema_slow = df[column].ewm(span=slow, min_periods=1).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, min_periods=1).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram,
            'ema_fast': ema_fast,
            'ema_slow': ema_slow
        }
    
    @staticmethod
    @_safe_calculation
    def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, pd.Series]:
        """
        Stochastic Oscillator - Стохастический осциллятор
        """
        required_cols = ['high', 'low', 'close']
        TechnicalIndicators._validate_dataframe(df, required_cols, k_period)
        
        lowest_low = df['low'].rolling(window=k_period, min_periods=1).min()
        highest_high = df['high'].rolling(window=k_period, min_periods=1).max()
        
        k_percent = 100 * ((df['close'] - lowest_low) / (highest_high - lowest_low))
        d_percent = k_percent.rolling(window=d_period, min_periods=1).mean()
        
        return {
            'k_percent': k_percent.fillna(50),
            'd_percent': d_percent.fillna(50)
        }
    
    # =========================================================================
    # ПОЛОСЫ И КАНАЛЫ
    # =========================================================================
    
    @staticmethod
    @_safe_calculation
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0,
                                 column: str = 'close') -> Dict[str, pd.Series]:
        """
        Bollinger Bands - Полосы Боллинджера
        
        Returns:
            IndicatorResult с dict содержащим 'upper', 'lower', 'middle', 'position', 'width'
        """
        TechnicalIndicators._validate_dataframe(df, [column], period)
        
        sma = df[column].rolling(window=period, min_periods=1).mean()
        std = df[column].rolling(window=period, min_periods=1).std()
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        # Позиция цены в полосах (0 = нижняя полоса, 1 = верхняя полоса)
        position = (df[column] - lower) / (upper - lower)
        position = position.fillna(0.5)  # Средняя позиция для NaN
        
        # Ширина полос (нормализованная)
        width = (upper - lower) / sma
        
        return {
            'upper': upper,
            'lower': lower,
            'middle': sma,
            'position': position,
            'width': width.fillna(0)
        }
    
    @staticmethod
    @_safe_calculation
    def calculate_keltner_channels(df: pd.DataFrame, period: int = 20, atr_mult: float = 2.0) -> Dict[str, pd.Series]:
        """
        Keltner Channels - Каналы Кельтнера
        """
        required_cols = ['high', 'low', 'close']
        TechnicalIndicators._validate_dataframe(df, required_cols, period)
        
        ema = df['close'].ewm(span=period, min_periods=1).mean()
        atr_series = TechnicalIndicators.calculate_atr_series(df, period).value
        
        upper = ema + (atr_series * atr_mult)
        lower = ema - (atr_series * atr_mult)
        
        return {
            'upper': upper,
            'lower': lower,
            'middle': ema
        }
    
    # =========================================================================
    # ОБЪЕМНЫЕ ИНДИКАТОРЫ
    # =========================================================================
    
    @staticmethod
    @_safe_calculation
    def calculate_vwap(df: pd.DataFrame, period: Optional[int] = None) -> pd.Series:
        """
        Volume Weighted Average Price - Средневзвешенная по объему цена
        КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: TTL кэширование для уменьшения латентности

        Args:
            df: DataFrame с OHLCV данными
            period: Период для скользящего VWAP (None = кумулятивный)

        Returns:
            IndicatorResult с Series значений VWAP
        """
        # КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: Проверяем кэш
        cache_key = _create_data_hash(df, f"vwap_{period}")
        cached_result = _VWAP_CACHE.get(cache_key)
        if cached_result is not None:
            return cached_result

        required_cols = ['high', 'low', 'close', 'volume']
        TechnicalIndicators._validate_dataframe(df, required_cols, period or 1)

        # ОПТИМИЗАЦИЯ: Используем numpy для скорости
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        volume = df['volume'].values

        # Быстрое вычисление typical price
        typical_price = (high + low + close) / 3

        if period is None:
            # Кумулятивный VWAP - оптимизированный
            cumulative_volume = np.cumsum(volume)
            cumulative_tp_volume = np.cumsum(typical_price * volume)
            vwap_values = cumulative_tp_volume / cumulative_volume
        else:
            # Скользящий VWAP - оптимизированный
            vwap_values = np.full(len(df), np.nan)
            for i in range(period - 1, len(df)):
                start_idx = max(0, i - period + 1)
                period_volume = volume[start_idx:i + 1]
                period_tp = typical_price[start_idx:i + 1]
                vwap_values[i] = np.sum(period_tp * period_volume) / np.sum(period_volume)

        # Создаем Series с индексом оригинального DataFrame
        vwap = pd.Series(vwap_values, index=df.index, name='vwap')

        # КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: Сохраняем в кэш
        result = IndicatorResult(value=vwap, is_valid=True)
        _VWAP_CACHE.put(cache_key, result)

        return result
    
    @staticmethod
    @_safe_calculation
    def calculate_obv(df: pd.DataFrame) -> pd.Series:
        """
        On-Balance Volume - Балансовый объем
        """
        required_cols = ['close', 'volume']
        TechnicalIndicators._validate_dataframe(df, required_cols, 2)
        
        price_changes = df['close'].pct_change()
        volume_direction = price_changes.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
        
        obv = (volume_direction * df['volume']).cumsum()
        return obv.fillna(0)
    
    @staticmethod
    @_safe_calculation
    def calculate_ad_line(df: pd.DataFrame) -> pd.Series:
        """
        Accumulation/Distribution Line - Линия накопления/распределения
        """
        required_cols = ['high', 'low', 'close', 'volume']
        TechnicalIndicators._validate_dataframe(df, required_cols, 1)
        
        clv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        clv = clv.fillna(0)  # Если high == low
        
        ad_line = (clv * df['volume']).cumsum()
        return ad_line
    
    @staticmethod
    @_safe_calculation
    def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Money Flow Index - Индекс денежных потоков
        """
        required_cols = ['high', 'low', 'close', 'volume']
        TechnicalIndicators._validate_dataframe(df, required_cols, period + 1)
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        money_flow = typical_price * df['volume']
        
        # Определяем направление движения
        price_direction = typical_price.diff()
        
        positive_flow = money_flow.where(price_direction > 0, 0).rolling(window=period, min_periods=1).sum()
        negative_flow = money_flow.where(price_direction < 0, 0).rolling(window=period, min_periods=1).sum()
        
        money_ratio = positive_flow / negative_flow.replace(0, np.inf)
        mfi = 100 - (100 / (1 + money_ratio))
        
        return mfi.fillna(50)
    
    # =========================================================================
    # СПЕЦИАЛЬНЫЕ ИНДИКАТОРЫ ДЛЯ СТРАТЕГИЙ
    # =========================================================================
    
    @staticmethod
    @_safe_calculation
    def calculate_enhanced_delta(df: pd.DataFrame, window: int = 20, smoothing: int = 5) -> Dict[str, pd.Series]:
        """
        Улучшенная кумулятивная дельта для CumDelta стратегии
        
        Args:
            df: DataFrame с данными (должен содержать buy_volume, sell_volume или delta)
            window: Окно для кумулятивной дельты
            smoothing: Период сглаживания
        
        Returns:
            IndicatorResult с dict содержащим различные варианты дельты
        """
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        TechnicalIndicators._validate_dataframe(df, required_cols, window)
        
        # Определяем источник дельты
        if "buy_volume" in df.columns and "sell_volume" in df.columns:
            # Если есть данные о покупках/продажах
            delta = df["buy_volume"] - df["sell_volume"]
        elif "delta" in df.columns:
            # Если дельта уже рассчитана
            delta = df["delta"]
        else:
            # Fallback: используем простую дельту на основе цены
            delta = df["close"] - df["open"]
            
            # Добавляем объемный компонент
            price_change = df['close'].pct_change()
            volume_weighted_delta = delta * df['volume'] * np.sign(price_change)
            delta = volume_weighted_delta.fillna(delta)
        
        # Сглаживание дельты
        if smoothing > 1:
            delta_smooth = delta.rolling(window=smoothing, min_periods=1).mean()
        else:
            delta_smooth = delta
        
        # Кумулятивная дельта
        cum_delta = delta_smooth.rolling(window=window, min_periods=1).sum()
        
        # Дополнительные расчеты
        delta_momentum = delta_smooth.diff(5)
        delta_strength = abs(cum_delta) / df['volume'].rolling(10, min_periods=1).mean()
        
        return {
            'delta': delta,
            'delta_smooth': delta_smooth,
            'cum_delta': cum_delta,
            'delta_momentum': delta_momentum,
            'delta_strength': delta_strength.fillna(0)
        }
    
    @staticmethod
    @_safe_calculation
    def calculate_volume_profile(df: pd.DataFrame, price_levels: int = 50) -> Dict[str, Union[pd.Series, np.ndarray]]:
        """
        Volume Profile - Профиль объема по ценовым уровням
        
        Args:
            df: DataFrame с OHLCV данными
            price_levels: Количество ценовых уровней для анализа
        
        Returns:
            IndicatorResult с профилем объема
        """
        required_cols = ['high', 'low', 'close', 'volume']
        TechnicalIndicators._validate_dataframe(df, required_cols, 10)
        
        # Определяем ценовой диапазон
        min_price = df['low'].min()
        max_price = df['high'].max()
        price_bins = np.linspace(min_price, max_price, price_levels + 1)
        
        # Создаем профиль объема
        volume_profile = np.zeros(price_levels)
        
        for i, row in df.iterrows():
            # Распределяем объем по ценовым уровням внутри свечи
            low_idx = np.digitize(row['low'], price_bins) - 1
            high_idx = np.digitize(row['high'], price_bins) - 1
            
            # Ограничиваем индексы
            low_idx = max(0, min(low_idx, price_levels - 1))
            high_idx = max(0, min(high_idx, price_levels - 1))
            
            # Распределяем объем равномерно по затронутым уровням
            if low_idx == high_idx:
                volume_profile[low_idx] += row['volume']
            else:
                levels_count = high_idx - low_idx + 1
                volume_per_level = row['volume'] / levels_count
                for level in range(low_idx, high_idx + 1):
                    volume_profile[level] += volume_per_level
        
        # Находим уровень максимального объема (POC - Point of Control)
        poc_idx = np.argmax(volume_profile)
        poc_price = (price_bins[poc_idx] + price_bins[poc_idx + 1]) / 2
        
        return {
            'volume_profile': volume_profile,
            'price_levels': price_bins[:-1],  # Центры ценовых уровней
            'poc_price': poc_price,
            'poc_volume': volume_profile[poc_idx],
            'total_volume': volume_profile.sum()
        }
    
    # =========================================================================
    # КОМПЛЕКСНЫЕ ИНДИКАТОРЫ
    # =========================================================================
    
    @staticmethod
    @_safe_calculation
    def calculate_trend_strength(df: pd.DataFrame, period: int = 20) -> Dict[str, float]:
        """
        Расчет силы и направления тренда
        
        Returns:
            IndicatorResult с dict метрик тренда
        """
        TechnicalIndicators._validate_dataframe(df, ['close'], period)
        
        # SMA и наклон
        sma = df['close'].rolling(window=period, min_periods=1).mean()
        slope = sma.diff(period)
        
        # Нормализация наклона
        normalized_slope = slope.iloc[-1] / df['close'].iloc[-1] if df['close'].iloc[-1] > 0 else 0
        
        # R-squared для определения силы тренда
        x = np.arange(len(sma))
        if len(sma) >= 2:
            correlation = np.corrcoef(x, sma)[0, 1]
            r_squared = correlation ** 2 if not np.isnan(correlation) else 0
        else:
            r_squared = 0
        
        # Последовательность движений в одном направлении
        price_changes = df['close'].diff().tail(10)
        consecutive_up = 0
        consecutive_down = 0
        
        for change in reversed(price_changes.dropna()):
            if change > 0:
                consecutive_up += 1
                if consecutive_down > 0:
                    break
            elif change < 0:
                consecutive_down += 1
                if consecutive_up > 0:
                    break
            else:
                break
        
        return {
            'slope': float(normalized_slope),
            'strength': float(r_squared),
            'direction': 1 if normalized_slope > 0 else -1 if normalized_slope < 0 else 0,
            'consecutive_moves': max(consecutive_up, consecutive_down),
            'is_trending': r_squared > 0.7 and abs(normalized_slope) > 0.001
        }
    
    @staticmethod
    @_safe_calculation  
    def calculate_volatility_metrics(df: pd.DataFrame, period: int = 20) -> Dict[str, float]:
        """
        Расчет метрик волатильности
        """
        TechnicalIndicators._validate_dataframe(df, ['close'], period)
        
        returns = df['close'].pct_change().dropna()
        
        # Историческая волатильность
        volatility = returns.std()
        
        # Волатильность по ATR
        atr_result = TechnicalIndicators.calculate_atr_safe(df, period)
        atr_volatility = atr_result.value / df['close'].iloc[-1] if atr_result.is_valid else 0
        
        # Парkinson estimator (более эффективная оценка волатильности)
        if all(col in df.columns for col in ['high', 'low']):
            parkinson = np.sqrt((1 / (4 * np.log(2))) * ((np.log(df['high'] / df['low'])) ** 2).rolling(period).mean())
            parkinson_vol = parkinson.iloc[-1] if not pd.isna(parkinson.iloc[-1]) else volatility
        else:
            parkinson_vol = volatility
        
        return {
            'historical_volatility': float(volatility),
            'atr_volatility': float(atr_volatility),
            'parkinson_volatility': float(parkinson_vol),
            'volatility_percentile': float(np.percentile(returns.tail(100), 75)) if len(returns) >= 100 else 0.5
        }
    
    # =========================================================================
    # УТИЛИТНЫЕ МЕТОДЫ
    # =========================================================================
    
    @staticmethod
    def get_all_basic_indicators(df: pd.DataFrame, config: Optional[Dict] = None) -> Dict[str, IndicatorResult]:
        """
        Получение всех базовых индикаторов сразу
        
        Args:
            df: DataFrame с OHLCV данными
            config: Словарь с параметрами индикаторов
        
        Returns:
            Dict с результатами всех индикаторов
        """
        if config is None:
            config = {}
        
        indicators = {}
        
        try:
            # Базовые движущие средние
            indicators['sma_20'] = TechnicalIndicators.calculate_sma(df, config.get('sma_period', 20))
            indicators['ema_20'] = TechnicalIndicators.calculate_ema(df, config.get('ema_period', 20))
            
            # ATR
            indicators['atr'] = TechnicalIndicators.calculate_atr_safe(df, config.get('atr_period', 14))
            
            # Осцилляторы
            indicators['rsi'] = TechnicalIndicators.calculate_rsi(df, config.get('rsi_period', 14))
            indicators['macd'] = TechnicalIndicators.calculate_macd(df)
            
            # Полосы Боллинджера
            indicators['bb'] = TechnicalIndicators.calculate_bollinger_bands(df, config.get('bb_period', 20))
            
            # Объемные индикаторы
            if 'volume' in df.columns:
                indicators['vwap'] = TechnicalIndicators.calculate_vwap(df)
                indicators['obv'] = TechnicalIndicators.calculate_obv(df)
            
            # Метрики тренда и волатильности
            indicators['trend'] = TechnicalIndicators.calculate_trend_strength(df)
            indicators['volatility'] = TechnicalIndicators.calculate_volatility_metrics(df)
            
        except Exception as e:
            logger.error(f"Ошибка расчета комплексных индикаторов: {e}")
        
        return indicators
    
    @staticmethod
    def validate_indicator_data(df: pd.DataFrame, indicator_name: str) -> Tuple[bool, str]:
        """
        Валидация данных для конкретного индикатора
        
        Returns:
            Tuple (is_valid, error_message)
        """
        requirements = {
            'sma': (['close'], 1),
            'ema': (['close'], 1),
            'atr': (['high', 'low', 'close'], 2),
            'rsi': (['close'], 15),
            'macd': (['close'], 35),
            'bollinger_bands': (['close'], 21),
            'vwap': (['high', 'low', 'close', 'volume'], 1),
            'obv': (['close', 'volume'], 2),
            'mfi': (['high', 'low', 'close', 'volume'], 15)
        }
        
        if indicator_name not in requirements:
            return False, f"Неизвестный индикатор: {indicator_name}"
        
        required_cols, min_length = requirements[indicator_name]
        
        try:
            TechnicalIndicators._validate_dataframe(df, required_cols, min_length)
            return True, "Данные валидны"
        except IndicatorError as e:
            return False, str(e)

    # Алиасы для обратной совместимости
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
        """Алиас для calculate_atr_safe для обратной совместимости"""
        return TechnicalIndicators.calculate_atr_safe(df, period)


# =========================================================================
# КОНСТАНТЫ И ПРЕДУСТАНОВКИ
# =========================================================================

# Стандартные параметры индикаторов
DEFAULT_INDICATOR_PARAMS = {
    'sma_period': 20,
    'ema_period': 20,
    'atr_period': 14,
    'rsi_period': 14,
    'bb_period': 20,
    'bb_std_dev': 2.0,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'mfi_period': 14,
    'stoch_k': 14,
    'stoch_d': 3
}

# Рекомендуемые индикаторы для разных типов стратегий
STRATEGY_INDICATOR_SETS = {
    'volume_vwap': ['sma', 'vwap', 'atr', 'rsi', 'bollinger_bands', 'obv'],
    'cumdelta_sr': ['enhanced_delta', 'atr', 'rsi', 'bollinger_bands', 'trend_strength'],
    'multitf_volume': ['sma', 'ema', 'macd', 'atr', 'rsi', 'trend_strength', 'vwap'],
    'scalping': ['ema', 'atr', 'bb', 'rsi'],
    'swing': ['sma', 'macd', 'rsi', 'trend_strength', 'volatility']
}

# Пороговые значения для классификации
INDICATOR_THRESHOLDS = {
    'rsi_oversold': 30,
    'rsi_overbought': 70,
    'rsi_neutral_low': 40,
    'rsi_neutral_high': 60,
    'trend_strength_weak': 0.3,
    'trend_strength_strong': 0.7,
    'volatility_low': 0.01,
    'volatility_high': 0.03
}


# =============================================================================
# BATCH PROCESSING OPTIMIZATION - A1.3
# =============================================================================

class BatchIndicatorProcessor:
    """
    Критическая оптимизация A1.3: Batch обработка индикаторов для повышения производительности

    Вместо последовательного вызова каждого индикатора, рассчитывает несколько индикаторов
    одновременно используя векторизованные операции numpy/pandas.

    Целевое улучшение производительности: 40-60% снижение времени расчета
    """

    def __init__(self):
        self._cache = TTLCache(maxsize=50, ttl=30)  # Кэш для batch результатов

    @staticmethod
    def calculate_batch_core_indicators(df: pd.DataFrame, config: Dict = None) -> Dict[str, Any]:
        """
        Batch расчет основных индикаторов для ВСЕХ стратегий

        Рассчитывает одновременно: RSI, SMA, EMA, ATR, VWAP, Volume Analysis
        Использует векторизованные операции pandas/numpy для максимальной скорости

        Args:
            df: DataFrame с OHLCV данными
            config: Опциональная конфигурация параметров

        Returns:
            Dict с рассчитанными индикаторами
        """
        try:
            if df is None or len(df) < 5:
                return {}

            # Параметры по умолчанию (оптимизированы для скорости)
            config = config or {}
            rsi_period = config.get('rsi_period', 14)
            sma_period = config.get('sma_period', 20)
            ema_period = config.get('ema_period', 20)
            atr_period = config.get('atr_period', 14)

            results = {}
            close = df['close']
            high = df['high']
            low = df['low']
            volume = df['volume']

            # === BATCH RSI CALCULATION ===
            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # Используем ewm для экспоненциального сглаживания (быстрее rolling)
            avg_gain = gain.ewm(span=rsi_period, min_periods=1).mean()
            avg_loss = loss.ewm(span=rsi_period, min_periods=1).mean()

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            results['rsi'] = rsi.iloc[-1] if not rsi.empty else 50.0

            # === BATCH MOVING AVERAGES ===
            # Векторизованный расчет SMA и EMA одновременно
            results['sma'] = close.rolling(window=sma_period, min_periods=1).mean().iloc[-1]
            results['ema'] = close.ewm(span=ema_period, min_periods=1).mean().iloc[-1]

            # === BATCH ATR CALCULATION ===
            # Оптимизированный ATR через numpy
            tr1 = high - low
            tr2 = np.abs(high - close.shift(1))
            tr3 = np.abs(low - close.shift(1))

            # Используем numpy maximum для скорости
            true_range = np.maximum(tr1, np.maximum(tr2, tr3))
            atr = pd.Series(true_range).rolling(window=atr_period, min_periods=1).mean()
            results['atr'] = atr.iloc[-1] if not atr.empty else (high.iloc[-1] - low.iloc[-1])

            # === BATCH VWAP CALCULATION ===
            # Оптимизированный VWAP с кэшированием
            cumulative_volume = volume.cumsum()
            cumulative_volume_price = (close * volume).cumsum()

            vwap = cumulative_volume_price / cumulative_volume
            results['vwap'] = vwap.iloc[-1] if not vwap.empty else close.iloc[-1]
            results['vwap_deviation'] = abs(close.iloc[-1] - results['vwap']) / results['vwap'] * 100

            # === BATCH VOLUME ANALYSIS ===
            volume_sma = volume.rolling(window=20, min_periods=1).mean()
            volume_ratio = volume / volume_sma

            results['volume_ratio'] = volume_ratio.iloc[-1] if not volume_ratio.empty else 1.0
            results['volume_spike'] = results['volume_ratio'] > 2.0
            results['volume_increasing'] = volume.iloc[-1] > volume.iloc[-2] if len(volume) > 1 else False

            # === BATCH TREND ANALYSIS ===
            # Быстрый анализ тренда через линейную регрессию
            if len(close) >= 10:
                x = np.arange(len(close.tail(10)))
                y = close.tail(10).values

                # Векторизованная линейная регрессия
                x_mean = x.mean()
                y_mean = y.mean()
                slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)

                # Нормализация наклона
                price_range = y.max() - y.min()
                normalized_slope = slope / price_range if price_range > 0 else 0

                results['trend_slope'] = normalized_slope
                results['trend_strength'] = abs(normalized_slope)
                results['trend_bullish'] = normalized_slope > 0.001
                results['trend_bearish'] = normalized_slope < -0.001
            else:
                results['trend_slope'] = 0
                results['trend_strength'] = 0
                results['trend_bullish'] = False
                results['trend_bearish'] = False

            # === PRICE POSITION ANALYSIS ===
            results['price_above_sma'] = close.iloc[-1] > results['sma']
            results['price_above_ema'] = close.iloc[-1] > results['ema']
            results['price_above_vwap'] = close.iloc[-1] > results['vwap']
            results['price_below_vwap'] = close.iloc[-1] < results['vwap']

            return results

        except Exception as e:
            logger.error(f"Ошибка batch расчета индикаторов: {e}")
            return {}

    @staticmethod
    def calculate_batch_confluence_factors(df: pd.DataFrame, signal_type: str, indicators: Dict) -> Tuple[int, List[str]]:
        """
        Batch расчет confluence факторов для всех стратегий

        Унифицированная система подсчета confluence факторов с оптимизацией
        для максимальной скорости выполнения

        Args:
            df: DataFrame с данными
            signal_type: 'BUY' или 'SELL'
            indicators: Результаты batch_core_indicators

        Returns:
            Tuple: (количество_факторов, список_факторов)
        """
        try:
            confluence_count = 0
            factors = []

            if signal_type == 'BUY':
                # Фактор 1: Объемное подтверждение
                if indicators.get('volume_spike', False):
                    confluence_count += 1
                    factors.append('volume_confirmation')

                # Фактор 2: Позиция цены
                if indicators.get('price_above_vwap', False):
                    confluence_count += 1
                    factors.append('price_position')

                # Фактор 3: Трендовое выравнивание
                if indicators.get('trend_bullish', False):
                    confluence_count += 1
                    factors.append('trend_alignment')

            elif signal_type == 'SELL':
                # Фактор 1: Объемное подтверждение
                if indicators.get('volume_spike', False):
                    confluence_count += 1
                    factors.append('volume_confirmation')

                # Фактор 2: Позиция цены
                if indicators.get('price_below_vwap', False):
                    confluence_count += 1
                    factors.append('price_position')

                # Фактор 3: Трендовое выравнивание
                if indicators.get('trend_bearish', False):
                    confluence_count += 1
                    factors.append('trend_alignment')

            return confluence_count, factors

        except Exception as e:
            logger.error(f"Ошибка batch confluence: {e}")
            return 0, []

    @staticmethod
    def calculate_batch_signal_strength(indicators: Dict, signal_type: str) -> float:
        """
        Batch расчет силы сигнала для всех стратегий

        Унифицированный расчет силы сигнала на базе 3 ключевых факторов

        Args:
            indicators: Результаты batch_core_indicators
            signal_type: 'BUY' или 'SELL'

        Returns:
            Сила сигнала от 0.0 до 1.0
        """
        try:
            # 3 ключевых фактора (оптимизировано)
            factors = []

            # Фактор 1: Объемное подтверждение (40%)
            volume_factor = min(indicators.get('volume_ratio', 1.0) / 2.0, 1.0)
            factors.append(volume_factor)

            # Фактор 2: Позиция относительно VWAP (35%)
            vwap_deviation = indicators.get('vwap_deviation', 0)
            vwap_factor = min(vwap_deviation / 2.0, 1.0)  # Чем больше отклонение, тем сильнее потенциал
            factors.append(vwap_factor)

            # Фактор 3: Трендовое подтверждение (25%)
            if signal_type == 'BUY':
                trend_factor = 1.0 if indicators.get('trend_bullish', False) else 0.3
            else:
                trend_factor = 1.0 if indicators.get('trend_bearish', False) else 0.3
            factors.append(trend_factor)

            # Взвешенная сумма
            weights = [0.40, 0.35, 0.25]
            signal_strength = sum(factor * weight for factor, weight in zip(factors, weights))

            return min(max(signal_strength, 0.0), 1.0)

        except Exception as e:
            logger.error(f"Ошибка batch signal strength: {e}")
            return 0.5