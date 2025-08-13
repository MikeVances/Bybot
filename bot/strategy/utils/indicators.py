# bot/strategy/utils/indicators.py
"""
Централизованная библиотека технических индикаторов для торговых стратегий
Все индикаторы в одном месте для устранения дублирования кода
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Union, Tuple, List
import logging
from dataclasses import dataclass
from enum import Enum

# Настройка логирования
logger = logging.getLogger(__name__)


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
        
        Args:
            df: DataFrame с данными
            period: Период для расчета RSI
            column: Колонка для расчета
        
        Returns:
            IndicatorResult с Series значений RSI (0-100)
        """
        TechnicalIndicators._validate_dataframe(df, [column], period + 1)
        
        delta = df[column].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
        
        # Избегаем деления на ноль
        rs = gain / loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        
        # Заполняем NaN значения
        rsi = rsi.fillna(50)  # Нейтральное значение для начальных баров
        
        return rsi
    
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
        
        Args:
            df: DataFrame с OHLCV данными
            period: Период для скользящего VWAP (None = кумулятивный)
        
        Returns:
            IndicatorResult с Series значений VWAP
        """
        required_cols = ['high', 'low', 'close', 'volume']
        TechnicalIndicators._validate_dataframe(df, required_cols, period or 1)
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        
        if period is None:
            # Кумулятивный VWAP
            cumulative_volume = df['volume'].cumsum()
            cumulative_tp_volume = (typical_price * df['volume']).cumsum()
            vwap = cumulative_tp_volume / cumulative_volume
        else:
            # Скользящий VWAP
            tp_volume = typical_price * df['volume']
            vwap = tp_volume.rolling(window=period, min_periods=1).sum() / df['volume'].rolling(window=period, min_periods=1).sum()
        
        return vwap.fillna(df['close'])  # Fallback к цене закрытия
    
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