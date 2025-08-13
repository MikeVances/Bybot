"""
Fibonacci RSI Volume Strategy
Стратегия, вдохновленная выступлением Сергея на SoloConf.
Сочетает анализ нескольких таймфреймов, фильтры на основе EMA,
RSI и объёма, уровни Фибоначчи для целей и ATR для стоп‑лоссов.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
import logging

from bot.strategy.base import BaseStrategy, BaseStrategyConfig
from bot.strategy.base.mixins import (
    PositionManagerMixin,
    StatisticsMixin,
    PriceUtilsMixin,
    MarketAnalysisMixin,
    LoggingMixin
)
from dataclasses import dataclass, field
from enum import Enum


class FibonacciLevel(Enum):
    """Уровни Фибоначчи"""
    FIB_382 = "fib_382"
    FIB_618 = "fib_618"
    FIB_500 = "fib_500"
    FIB_786 = "fib_786"


class ConfluenceFactor(Enum):
    """Факторы confluence для стратегии"""
    TREND_ALIGNMENT = "trend_alignment"
    VOLUME_SPIKE = "volume_spike"
    RSI_FAVORABLE = "rsi_favorable"
    FIBONACCI_LEVEL = "fibonacci_level"
    ATR_VOLATILITY = "atr_volatility"
    MULTI_TIMEFRAME = "multi_timeframe"


@dataclass
class FibonacciRSIConfig(BaseStrategyConfig):
    """
    Конфигурация для Fibonacci RSI Volume стратегии
    """
    
    # === ТАЙМФРЕЙМЫ ===
    fast_tf: str = '15m'  # Быстрый таймфрейм для входов
    slow_tf: str = '1h'   # Медленный таймфрейм для тренда
    
    # === EMA ПАРАМЕТРЫ ===
    ema_short: int = 20   # Короткая EMA
    ema_long: int = 50    # Длинная EMA
    
    # === RSI ПАРАМЕТРЫ ===
    rsi_period: int = 14  # Период RSI
    rsi_overbought: float = 70.0  # Уровень перекупленности
    rsi_oversold: float = 30.0    # Уровень перепроданности
    rsi_favorable_zone: Tuple[float, float] = field(default=(40.0, 60.0))  # Благоприятная зона RSI
    
    # === ОБЪЕМНЫЕ ПАРАМЕТРЫ ===
    volume_multiplier: float = 1.5  # Множитель объема для всплеска
    volume_ma_period: int = 20      # Период MA для объема
    
    # === ATR ПАРАМЕТРЫ ===
    atr_period: int = 14  # Период ATR
    atr_multiplier_sl: float = 1.0  # Множитель ATR для стоп-лосса
    atr_multiplier_tp: float = 1.5  # Множитель ATR для тейк-профита
    
    # === ФИБОНАЧЧИ ПАРАМЕТРЫ ===
    fib_lookback: int = 50  # Количество баров для расчета Фибоначчи
    fib_levels: List[float] = field(default_factory=lambda: [0.382, 0.5, 0.618, 0.786])
    
    # === РИСК-МЕНЕДЖМЕНТ ===
    risk_reward_ratio: float = 1.5  # Соотношение риск/прибыль
    max_risk_per_trade_pct: float = 2.0  # Максимальный риск на сделку
    
    # === ФИЛЬТРЫ ===
    min_volume_threshold: float = 1000.0  # Минимальный объем для сигнала
    trend_strength_threshold: float = 0.001  # Минимальная сила тренда
    
    # === ДОПОЛНИТЕЛЬНЫЕ ПАРАМЕТРЫ ===
    use_fibonacci_targets: bool = True  # Использовать уровни Фибоначчи для целей
    require_volume_confirmation: bool = True  # Требовать подтверждения объема
    multi_timeframe_confirmation: bool = True  # Подтверждение на нескольких ТФ
    
    def __post_init__(self):
        """Дополнительная валидация для Fibonacci RSI стратегии"""
        super().__post_init__()
        self.strategy_name = "FibonacciRSI"
        
        # Валидация параметров
        if self.ema_short >= self.ema_long:
            raise ValueError("ema_short должен быть < ema_long")
        
        if self.rsi_overbought <= self.rsi_oversold:
            raise ValueError("rsi_overbought должен быть > rsi_oversold")
        
        if self.volume_multiplier <= 1.0:
            raise ValueError("volume_multiplier должен быть > 1.0")
        
        if self.atr_period < 1:
            raise ValueError("atr_period должен быть >= 1")
        
        if self.fib_lookback < 10:
            raise ValueError("fib_lookback должен быть >= 10")


class FibonacciRSIStrategy(BaseStrategy):
    """
    Fibonacci RSI Volume Strategy
    
    Стратегия, вдохновленная выступлением Сергея на SoloConf.
    Сочетает анализ нескольких таймфреймов, фильтры на основе EMA,
    RSI и объёма, уровни Фибоначчи для целей и ATR для стоп‑лоссов.
    """
    
    def __init__(self, config: FibonacciRSIConfig):
        super().__init__(config, config.strategy_name)
        self.config = config
        
        # Устанавливаем минимальное R:R соотношение для согласованности
        self.config.min_risk_reward_ratio = 0.8  # Снижаем для лучшей совместимости
        
        self.logger.info(f"🚀 Инициализирована стратегия {self.config.strategy_name} v{self.config.strategy_version}")
        self.logger.info(f"🎯 Fibonacci RSI Volume стратегия инициализирована")
        self.logger.info(f"📊 Параметры: fast_tf={self.config.fast_tf}, slow_tf={self.config.slow_tf}, "
                        f"ema_short={self.config.ema_short}, ema_long={self.config.ema_long}")
    
    def calculate_strategy_indicators(self, market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Расчет индикаторов для Fibonacci RSI стратегии
        
        Args:
            market_data: Словарь с данными по таймфреймам
            
        Returns:
            Словарь с рассчитанными индикаторами
        """
        try:
            df_fast = market_data.get(self.config.fast_tf)
            df_slow = market_data.get(self.config.slow_tf)
            
            if df_fast is None or df_slow is None:
                self.logger.warning(f"Отсутствуют данные для таймфреймов {self.config.fast_tf} или {self.config.slow_tf}")
                return {}
            
            # Проверка достаточности данных
            min_periods = max(self.config.ema_long, self.config.rsi_period, 
                            self.config.atr_period, self.config.fib_lookback)
            
            if len(df_fast) < min_periods or len(df_slow) < min_periods:
                self.logger.warning(f"Недостаточно данных: fast={len(df_fast)}, slow={len(df_slow)}, требуется={min_periods}")
                return {}
            
            # Конвертация данных
            for df in [df_fast, df_slow]:
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
            
            indicators = {}
            
            # 1. EMA анализ на медленном таймфрейме
            ema_analysis = self._calculate_ema_analysis(df_slow)
            indicators.update(ema_analysis)
            
            # 2. RSI анализ на быстром таймфрейме
            rsi_analysis = self._calculate_rsi_analysis(df_fast)
            indicators.update(rsi_analysis)
            
            # 3. Объемный анализ
            volume_analysis = self._calculate_volume_analysis(df_fast)
            indicators.update(volume_analysis)
            
            # 4. ATR анализ
            atr_analysis = self._calculate_atr_analysis(df_fast)
            indicators.update(atr_analysis)
            
            # 5. Фибоначчи уровни
            fib_analysis = self._calculate_fibonacci_levels(df_fast)
            indicators.update(fib_analysis)
            
            # 6. Многофреймовый анализ
            mtf_analysis = self._calculate_mtf_analysis(df_fast, df_slow)
            indicators.update(mtf_analysis)
            
            # Сохраняем DataFrame для использования в расчете уровней
            indicators['_df_fast'] = df_fast
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета индикаторов: {e}")
            return {}
    
    def _calculate_ema_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ EMA для определения тренда"""
        try:
            ema_short = df['close'].ewm(span=self.config.ema_short, adjust=False).mean()
            ema_long = df['close'].ewm(span=self.config.ema_long, adjust=False).mean()
            
            current_ema_short = ema_short.iloc[-1]
            current_ema_long = ema_long.iloc[-1]
            
            trend_up = current_ema_short > current_ema_long
            trend_down = current_ema_short < current_ema_long
            trend_strength = abs(current_ema_short - current_ema_long) / current_ema_long
            
            return {
                'ema_short': current_ema_short,
                'ema_long': current_ema_long,
                'trend_up': trend_up,
                'trend_down': trend_down,
                'trend_strength': trend_strength,
                'trend_neutral': not trend_up and not trend_down
            }
        except Exception as e:
            self.logger.error(f"Ошибка анализа EMA: {e}")
            return {}
    
    def _calculate_rsi_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ RSI"""
        try:
            rsi = self._calculate_rsi(df['close'], self.config.rsi_period)
            current_rsi = rsi.iloc[-1]
            
            rsi_overbought = current_rsi > self.config.rsi_overbought
            rsi_oversold = current_rsi < self.config.rsi_oversold
            rsi_favorable = (self.config.rsi_favorable_zone[0] <= current_rsi <= 
                           self.config.rsi_favorable_zone[1])
            
            return {
                'rsi': current_rsi,
                'rsi_overbought': rsi_overbought,
                'rsi_oversold': rsi_oversold,
                'rsi_favorable': rsi_favorable,
                'rsi_bullish': current_rsi > 50 and not rsi_overbought,
                'rsi_bearish': current_rsi < 50 and not rsi_oversold
            }
        except Exception as e:
            self.logger.error(f"Ошибка анализа RSI: {e}")
            return {}
    
    def _calculate_volume_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ объема"""
        try:
            volume_ma = df['volume'].rolling(self.config.volume_ma_period).mean()
            current_volume = df['volume'].iloc[-1]
            current_volume_ma = volume_ma.iloc[-1]
            
            volume_spike = current_volume > self.config.volume_multiplier * current_volume_ma
            volume_ratio = current_volume / current_volume_ma if current_volume_ma > 0 else 1.0
            
            return {
                'volume': current_volume,
                'volume_ma': current_volume_ma,
                'volume_spike': volume_spike,
                'volume_ratio': volume_ratio,
                'volume_sufficient': current_volume > self.config.min_volume_threshold
            }
        except Exception as e:
            self.logger.error(f"Ошибка анализа объема: {e}")
            return {}
    
    def _calculate_atr_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ ATR для волатильности"""
        try:
            atr = self._calculate_atr(df)
            
            return {
                'atr': atr,
                'atr_high': atr > df['close'].iloc[-1] * 0.02,  # Высокая волатильность
                'atr_low': atr < df['close'].iloc[-1] * 0.005,   # Низкая волатильность
                'atr_normal': not (atr > df['close'].iloc[-1] * 0.02 or atr < df['close'].iloc[-1] * 0.005)
            }
        except Exception as e:
            self.logger.error(f"Ошибка анализа ATR: {e}")
            return {}
    
    def _calculate_fibonacci_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Расчет уровней Фибоначчи"""
        try:
            if len(df) < self.config.fib_lookback:
                return {}
            
            recent = df.tail(self.config.fib_lookback)
            high_price = recent['high'].max()
            low_price = recent['low'].min()
            range_ = high_price - low_price
            
            fib_levels = {}
            for level in self.config.fib_levels:
                fib_price = high_price - level * range_
                fib_levels[f'fib_{int(level*1000)}'] = fib_price
            
            current_price = df['close'].iloc[-1]
            
            # Находим ближайшие уровни
            above_levels = [price for price in fib_levels.values() if price > current_price]
            below_levels = [price for price in fib_levels.values() if price < current_price]
            
            nearest_above = min(above_levels) if above_levels else None
            nearest_below = max(below_levels) if below_levels else None
            
            return {
                'fib_levels': fib_levels,
                'fib_high': high_price,
                'fib_low': low_price,
                'fib_range': range_,
                'nearest_above': nearest_above,
                'nearest_below': nearest_below,
                'current_price': current_price
            }
        except Exception as e:
            self.logger.error(f"Ошибка расчета Фибоначчи: {e}")
            return {}
    
    def _calculate_mtf_analysis(self, df_fast: pd.DataFrame, df_slow: pd.DataFrame) -> Dict[str, Any]:
        """Многофреймовый анализ"""
        try:
            # Синхронизация трендов
            fast_trend = df_fast['close'].iloc[-1] > df_fast['close'].iloc[-5]  # Краткосрочный тренд
            slow_trend = df_slow['close'].iloc[-1] > df_slow['close'].iloc[-3]   # Долгосрочный тренд
            
            trends_aligned_bullish = fast_trend and slow_trend
            trends_aligned_bearish = not fast_trend and not slow_trend
            
            return {
                'fast_trend': fast_trend,
                'slow_trend': slow_trend,
                'trends_aligned_bullish': trends_aligned_bullish,
                'trends_aligned_bearish': trends_aligned_bearish,
                'mtf_confirmation': trends_aligned_bullish or trends_aligned_bearish
            }
        except Exception as e:
            self.logger.error(f"Ошибка многофреймового анализа: {e}")
            return {}
    
    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Расчет RSI"""
        delta = series.diff()
        up, down = delta.clip(lower=0), -delta.clip(upper=0)
        roll_up = up.rolling(period).mean()
        roll_down = down.rolling(period).mean()
        rs = roll_up / roll_down
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """Расчет Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(self.config.atr_period).mean()
        
        return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else (high.iloc[-1] - low.iloc[-1])
    
    def calculate_signal_strength(self, market_data: Dict[str, pd.DataFrame], 
                                indicators: Dict[str, Any], signal_type: str) -> float:
        """
        Расчет силы сигнала для Fibonacci RSI стратегии
        
        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала ('BUY' или 'SELL')
            
        Returns:
            Сила сигнала от 0 до 1
        """
        try:
            strength = 0.0
            
            # 1. Тренд (30%)
            if signal_type == 'BUY' and indicators.get('trend_up', False):
                strength += 0.3
            elif signal_type == 'SELL' and indicators.get('trend_down', False):
                strength += 0.3
            
            # 2. RSI (25%)
            rsi = indicators.get('rsi', 50)
            if signal_type == 'BUY' and indicators.get('rsi_bullish', False):
                strength += 0.25
            elif signal_type == 'SELL' and indicators.get('rsi_bearish', False):
                strength += 0.25
            
            # 3. Объем (20%)
            if indicators.get('volume_spike', False):
                strength += 0.2
            
            # 4. Многофреймовое подтверждение (15%)
            if indicators.get('mtf_confirmation', False):
                strength += 0.15
            
            # 5. Волатильность (10%)
            if indicators.get('atr_normal', False):
                strength += 0.1
            
            return min(strength, 1.0)
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета силы сигнала: {e}")
            return 0.0
    
    def check_confluence_factors(self, market_data: Dict[str, pd.DataFrame], 
                               indicators: Dict[str, Any], signal_type: str) -> Tuple[int, List[str]]:
        """
        Проверка confluence факторов для Fibonacci RSI стратегии
        
        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала ('BUY' или 'SELL')
            
        Returns:
            Tuple: (количество факторов, список факторов)
        """
        try:
            confluence_count = 0
            factors = []
            
            # 1. Выравнивание трендов
            if signal_type == 'BUY' and indicators.get('trends_aligned_bullish', False):
                confluence_count += 1
                factors.append(ConfluenceFactor.TREND_ALIGNMENT.value)
            elif signal_type == 'SELL' and indicators.get('trends_aligned_bearish', False):
                confluence_count += 1
                factors.append(ConfluenceFactor.TREND_ALIGNMENT.value)
            
            # 2. Объемный всплеск
            if indicators.get('volume_spike', False):
                confluence_count += 1
                factors.append(ConfluenceFactor.VOLUME_SPIKE.value)
            
            # 3. Благоприятный RSI
            if indicators.get('rsi_favorable', False):
                confluence_count += 1
                factors.append(ConfluenceFactor.RSI_FAVORABLE.value)
            
            # 4. Уровни Фибоначчи
            if indicators.get('nearest_above') or indicators.get('nearest_below'):
                confluence_count += 1
                factors.append(ConfluenceFactor.FIBONACCI_LEVEL.value)
            
            # 5. Нормальная волатильность
            if indicators.get('atr_normal', False):
                confluence_count += 1
                factors.append(ConfluenceFactor.ATR_VOLATILITY.value)
            
            # 6. Многофреймовое подтверждение
            if indicators.get('mtf_confirmation', False):
                confluence_count += 1
                factors.append(ConfluenceFactor.MULTI_TIMEFRAME.value)
            
            return confluence_count, factors
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки confluence факторов: {e}")
            return 0, []
    
    def execute(self, market_data: Dict[str, pd.DataFrame], state=None, 
               bybit_api=None, symbol='BTCUSDT') -> Optional[Dict[str, Any]]:
        """
        Выполнение Fibonacci RSI стратегии
        
        Args:
            market_data: Рыночные данные по таймфреймам
            state: Состояние позиции
            bybit_api: API клиент
            symbol: Торговый символ
            
        Returns:
            Словарь с сигналом или None
        """
        try:
            # Проверяем состояние позиции
            in_position = self.is_in_position(state)
            position_side = getattr(state, 'position_side', None) if state else None
            
            # Рассчитываем индикаторы
            indicators = self.calculate_strategy_indicators(market_data)
            if not indicators:
                return None
            
            current_price = indicators.get('current_price', 0)
            if current_price == 0:
                return None
            
            # Логируем параметры
            self.logger.info(f"📊 Параметры: fast_tf={self.config.fast_tf}, slow_tf={self.config.slow_tf}, "
                           f"rsi={indicators.get('rsi', 0):.1f}, volume_ratio={indicators.get('volume_ratio', 0):.2f}")
            
            # Проверяем условия для входа
            if not in_position:
                signal = self._check_entry_conditions(indicators, current_price, symbol)
                if signal:
                    # Рассчитываем силу сигнала
                    signal_strength = self.calculate_signal_strength(market_data, indicators, signal['signal'])
                    signal['signal_strength'] = signal_strength
                    
                    # Проверяем confluence факторы
                    confluence_count, factors = self.check_confluence_factors(market_data, indicators, signal['signal'])
                    signal['confluence_count'] = confluence_count
                    signal['confluence_factors'] = factors
                    
                    # Проверяем минимальную силу сигнала
                    if signal_strength >= self.config.signal_strength_threshold:
                        self.logger.info(f"🎯 Сигнал {signal['signal']} с силой {signal_strength:.2f}")
                        return signal
                    else:
                        self.logger.debug(f"🔇 Сигнал {signal['signal']} отклонен: сила {signal_strength:.2f} < {self.config.signal_strength_threshold}")
                        return None
            
            # Проверяем условия для выхода
            elif in_position:
                exit_signal = self._check_exit_conditions(indicators, position_side, current_price)
                if exit_signal:
                    self.logger.info(f"🔚 Сигнал выхода: {exit_signal['signal']}")
                    return exit_signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка выполнения стратегии: {e}")
            return None
    
    def _check_entry_conditions(self, indicators: Dict[str, Any], current_price: float, symbol: str) -> Optional[Dict[str, Any]]:
        """Проверка условий для входа в позицию"""
        try:
            # Условия для LONG
            long_conditions = (
                indicators.get('trend_up', False) and
                indicators.get('rsi_bullish', False) and
                indicators.get('volume_spike', False) and
                indicators.get('volume_sufficient', False) and
                indicators.get('atr_normal', False)
            )
            
            # Условия для SHORT
            short_conditions = (
                indicators.get('trend_down', False) and
                indicators.get('rsi_bearish', False) and
                indicators.get('volume_spike', False) and
                indicators.get('volume_sufficient', False) and
                indicators.get('atr_normal', False)
            )
            
            if long_conditions:
                return self._create_long_signal(indicators, current_price, symbol)
            elif short_conditions:
                return self._create_short_signal(indicators, current_price, symbol)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки условий входа: {e}")
            return None
    
    def _create_long_signal(self, indicators: Dict[str, Any], current_price: float, symbol: str) -> Dict[str, Any]:
        """Создание сигнала на покупку"""
        try:
            # Получаем основной DataFrame для расчета уровней
            df_fast = indicators.get('_df_fast')  # Сохраняем DataFrame в индикаторах
            if df_fast is None:
                # Fallback к простому расчету
                atr = indicators.get('atr', current_price * 0.01)
                stop_loss = current_price - atr * self.config.atr_multiplier_sl
                take_profit = current_price + atr * self.config.atr_multiplier_tp
            else:
                # Используем базовую логику расчета уровней
                stop_loss, take_profit = self.calculate_dynamic_levels(df_fast, current_price, 'BUY')
            
            # Приоритет Фибоначчи уровней для тейк-профита
            if self.config.use_fibonacci_targets and indicators.get('nearest_above'):
                take_profit = indicators['nearest_above']
            
            # Округляем цены
            stop_loss = self.round_price(stop_loss)
            take_profit = self.round_price(take_profit)
            
            return {
                'symbol': symbol,
                'signal': 'BUY',
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': datetime.now().isoformat(),
                'indicators': indicators,
                'strategy': 'Fibonacci_RSI_Volume',
                'comment': 'Fibonacci RSI Volume Strategy - LONG'
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка создания LONG сигнала: {e}")
            return {}
    
    def _create_short_signal(self, indicators: Dict[str, Any], current_price: float, symbol: str) -> Dict[str, Any]:
        """Создание сигнала на продажу"""
        try:
            # Получаем основной DataFrame для расчета уровней
            df_fast = indicators.get('_df_fast')  # Сохраняем DataFrame в индикаторах
            if df_fast is None:
                # Fallback к простому расчету
                atr = indicators.get('atr', current_price * 0.01)
                stop_loss = current_price + atr * self.config.atr_multiplier_sl
                take_profit = current_price - atr * self.config.atr_multiplier_tp
            else:
                # Используем базовую логику расчета уровней
                stop_loss, take_profit = self.calculate_dynamic_levels(df_fast, current_price, 'SELL')
            
            # Приоритет Фибоначчи уровней для тейк-профита
            if self.config.use_fibonacci_targets and indicators.get('nearest_below'):
                take_profit = indicators['nearest_below']
            
            # Округляем цены
            stop_loss = self.round_price(stop_loss)
            take_profit = self.round_price(take_profit)
            
            return {
                'symbol': symbol,
                'signal': 'SELL',
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': datetime.now().isoformat(),
                'indicators': indicators,
                'strategy': 'Fibonacci_RSI_Volume',
                'comment': 'Fibonacci RSI Volume Strategy - SHORT'
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка создания SHORT сигнала: {e}")
            return {}
    
    def _check_exit_conditions(self, indicators: Dict[str, Any], position_side: str, current_price: float) -> Optional[Dict[str, Any]]:
        """Проверка условий для выхода из позиции"""
        try:
            if position_side == 'BUY':
                # Выход из LONG
                exit_conditions = (
                    indicators.get('trend_down', False) or
                    indicators.get('rsi_overbought', False)
                )
                if exit_conditions:
                    return {
                        'signal': 'EXIT_LONG',
                        'comment': 'Выход из LONG: разворот тренда или перекупленность RSI'
                    }
            
            elif position_side == 'SELL':
                # Выход из SHORT
                exit_conditions = (
                    indicators.get('trend_up', False) or
                    indicators.get('rsi_oversold', False)
                )
                if exit_conditions:
                    return {
                        'signal': 'EXIT_SHORT',
                        'comment': 'Выход из SHORT: разворот тренда или перепроданность RSI'
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки условий выхода: {e}")
            return None
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Получение информации о стратегии"""
        return {
            'name': self.config.strategy_name,
            'version': self.config.strategy_version,
            'description': 'Fibonacci RSI Volume Strategy - многофреймовый анализ с EMA, RSI, объемом и уровнями Фибоначчи',
            'parameters': {
                'fast_tf': self.config.fast_tf,
                'slow_tf': self.config.slow_tf,
                'ema_short': self.config.ema_short,
                'ema_long': self.config.ema_long,
                'rsi_period': self.config.rsi_period,
                'volume_multiplier': self.config.volume_multiplier,
                'atr_period': self.config.atr_period,
                'fib_lookback': self.config.fib_lookback
            }
        }


# Factory функции для создания стратегий
def create_fibonacci_rsi_strategy(config: Optional[FibonacciRSIConfig] = None, **kwargs) -> FibonacciRSIStrategy:
    """Создание стандартной Fibonacci RSI стратегии"""
    if config is None:
        config = FibonacciRSIConfig()
    
    # Применяем переданные параметры
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    return FibonacciRSIStrategy(config)


def create_conservative_fibonacci_rsi() -> FibonacciRSIStrategy:
    """Создание консервативной Fibonacci RSI стратегии"""
    config = FibonacciRSIConfig(
        rsi_overbought=75.0,
        rsi_oversold=25.0,
        volume_multiplier=2.0,
        atr_multiplier_sl=1.5,
        atr_multiplier_tp=2.0,
        signal_strength_threshold=0.7,
        confluence_required=3
    )
    return FibonacciRSIStrategy(config)


def create_aggressive_fibonacci_rsi() -> FibonacciRSIStrategy:
    """Создание агрессивной Fibonacci RSI стратегии"""
    config = FibonacciRSIConfig(
        rsi_overbought=65.0,
        rsi_oversold=35.0,
        volume_multiplier=1.2,
        atr_multiplier_sl=0.8,
        atr_multiplier_tp=1.2,
        signal_strength_threshold=0.5,
        confluence_required=2
    )
    return FibonacciRSIStrategy(config) 