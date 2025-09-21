# bot/strategy/implementations/multitf_volume_strategy.py
"""
Multi-Timeframe Volume стратегия - рефакторенная версия Strategy03
Использует новую базовую архитектуру для устранения дублирования кода

Торговая логика:
- Анализ мультитаймфрейма (быстрый и медленный ТФ)
- Поиск объемных всплесков
- Синхронизация трендов между таймфреймами
- Фильтрация по confluence факторам
- Адаптивные SL/TP уровни
- Интеграция с риск-менеджментом
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import logging

from ..base import (
    BaseStrategy,
    MultiTFConfig, 
    MarketRegime,
    SignalType,
    ConfluenceFactor,
    PositionSide,
    TimeFrame
)
from ..utils.indicators import TechnicalIndicators
from ..utils.validators import DataValidator, MultiTimeframeValidator
from ..utils.market_analysis import MarketRegimeAnalyzer


class MultiTFVolumeStrategy(BaseStrategy):
    """
    Multi-Timeframe Volume стратегия v2.0
    
    Торговая логика:
    - Анализ трендов на быстром и медленном таймфреймах
    - Поиск объемных всплесков для подтверждения сигналов
    - Синхронизация трендов между таймфреймами
    - Фильтрация сигналов по множественным confluence факторам
    - Адаптивные стоп-лоссы и тейк-профиты на основе ATR
    - Интеграция с системой риск-менеджмента
    
    Улучшения в v2.0:
    - Использование базовой архитектуры
    - Устранение дублирования кода
    - Расширенная система фильтров
    - Адаптивные параметры под рыночные условия
    - Стандартизированные сигналы
    """
    
    def __init__(self, config: MultiTFConfig):
        """
        Инициализация Multi-Timeframe Volume стратегии
        
        Args:
            config: Конфигурация стратегии типа MultiTFConfig
        """
        super().__init__(config, "MultiTF_Volume_v2")
        
        # Специфичная конфигурация
        self.config: MultiTFConfig = config
        
        # Кэш для расчетов
        self._trend_cache = {}
        self._volume_cache = {}
        
        self.logger.info(f"🎯 Multi-Timeframe Volume стратегия инициализирована")
        self.logger.info(f"📊 Параметры: fast_tf={config.fast_tf.value}, slow_tf={config.slow_tf.value}")
    
    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        """
        Расчет специфичных индикаторов для MultiTF стратегии
        
        Args:
            market_data: Рыночные данные (Dict[str, DataFrame] или DataFrame)
        
        Returns:
            Dict с рассчитанными индикаторами
        """
        try:
            # Получаем данные для разных таймфреймов
            if isinstance(market_data, dict):
                # Мультитаймфрейм данные
                df_fast = market_data.get(self.config.fast_tf.value)
                df_slow = market_data.get(self.config.slow_tf.value)
                
                if df_fast is None or df_slow is None:
                    self.logger.error(f"Отсутствуют данные для таймфреймов: {self.config.fast_tf.value}, {self.config.slow_tf.value}")
                    return {}
            else:
                # Единый DataFrame - используем его для обоих ТФ
                df_fast = market_data
                df_slow = market_data
            
            indicators = {}
            
            # 1. Базовые индикаторы (из родительского класса)
            base_indicators = self.calculate_base_indicators(df_fast)
            indicators.update(base_indicators)
            
            # 2. Анализ тренда на быстром ТФ
            if self.config.advanced_trend_analysis:
                indicators['fast_trend'] = self._calculate_advanced_trend_analysis(df_fast, self.config.fast_window)
            else:
                indicators['fast_trend'] = self._calculate_simple_trend_analysis(df_fast, self.config.fast_window)
            
            # 3. Анализ тренда на медленном ТФ
            if self.config.advanced_trend_analysis:
                indicators['slow_trend'] = self._calculate_advanced_trend_analysis(df_slow, self.config.slow_window)
            else:
                indicators['slow_trend'] = self._calculate_simple_trend_analysis(df_slow, self.config.slow_window)
            
            # 4. Объемный анализ
            indicators['volume_analysis'] = self._calculate_advanced_volume_analysis(df_fast)
            
            # 5. Дополнительные индикаторы
            # RSI на быстром ТФ
            rsi_result = TechnicalIndicators.calculate_rsi(df_fast)
            if rsi_result.is_valid:
                indicators['rsi'] = rsi_result.value
            
            # MACD на медленном ТФ для подтверждения тренда
            macd_result = TechnicalIndicators.calculate_macd(df_slow)
            if macd_result.is_valid:
                indicators['macd'] = macd_result.value['macd']
                indicators['macd_signal'] = macd_result.value['signal']
                indicators['macd_histogram'] = macd_result.value['histogram']
            
            # Bollinger Bands на быстром ТФ
            bb_result = TechnicalIndicators.calculate_bollinger_bands(df_fast)
            if bb_result.is_valid:
                indicators['bb_position'] = bb_result.value['position']
                indicators['bb_upper'] = bb_result.value['upper']
                indicators['bb_lower'] = bb_result.value['lower']
            
            # 6. Синхронизация трендов
            fast_bullish = indicators['fast_trend'].get('price_above_sma', False)
            slow_bullish = indicators['slow_trend'].get('price_above_sma', False)
            
            # Обработка pandas Series для избежания ambiguity
            if isinstance(fast_bullish, pd.Series):
                fast_bullish = bool(fast_bullish.iloc[-1]) if not fast_bullish.empty else False
            if isinstance(slow_bullish, pd.Series):
                slow_bullish = bool(slow_bullish.iloc[-1]) if not slow_bullish.empty else False
            
            indicators['trends_aligned_bullish'] = fast_bullish and slow_bullish
            indicators['trends_aligned_bearish'] = (not fast_bullish) and (not slow_bullish)
            
            # 7. Momentum сравнение между ТФ
            fast_momentum = df_fast['close'].pct_change(5).iloc[-1]
            slow_momentum = df_slow['close'].pct_change(3).iloc[-1]
            indicators['momentum_alignment'] = bool(np.sign(fast_momentum) == np.sign(slow_momentum))
            
            # 8. Анализ моментума между ТФ
            if self.config.momentum_analysis:
                indicators['momentum_analysis'] = self._calculate_momentum_analysis(df_fast, df_slow)
            
            # 9. Детекция дивергенций между ТФ
            if self.config.mtf_divergence_detection:
                indicators['mtf_divergence'] = self._detect_mtf_divergence(df_fast, df_slow)
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета индикаторов MultiTF: {e}")
            return {}
    
    def _calculate_advanced_trend_analysis(self, df: pd.DataFrame, window: int) -> Dict[str, Any]:
        """Продвинутый анализ тренда"""
        try:
            # SMA
            sma = df['close'].rolling(window, min_periods=1).mean()
            
            # EMA
            ema = df['close'].ewm(span=window, min_periods=1).mean()
            
            # Наклон тренда
            trend_slope = sma.diff(5)
            
            # Сила тренда
            trend_strength = abs(trend_slope.iloc[-1] / df['close'].iloc[-1])
            
            # Положение цены относительно SMA
            price_above_sma = bool(df['close'].iloc[-1] > sma.iloc[-1])
            
            # Волатильность тренда
            trend_volatility = df['close'].pct_change().rolling(window).std().iloc[-1]
            
            return {
                'sma': sma,
                'ema': ema,
                'trend_slope': trend_slope,
                'trend_strength': trend_strength,
                'price_above_sma': price_above_sma,
                'trend_volatility': trend_volatility
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка продвинутого анализа тренда: {e}")
            return {}
    
    def _calculate_simple_trend_analysis(self, df: pd.DataFrame, window: int) -> Dict[str, Any]:
        """Простой анализ тренда"""
        try:
            sma = df['close'].rolling(window, min_periods=1).mean()
            price_above_sma = bool(df['close'].iloc[-1] > sma.iloc[-1])
            trend_strength = abs(sma.diff(5).iloc[-1] / df['close'].iloc[-1])
            
            return {
                'sma': sma,
                'price_above_sma': price_above_sma,
                'trend_strength': trend_strength
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка простого анализа тренда: {e}")
            return {}
    
    def _calculate_advanced_volume_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Продвинутый анализ объема"""
        try:
            # Volume SMA
            vol_sma = df['volume'].rolling(20, min_periods=1).mean()
            volume_ratio = df['volume'] / vol_sma
            
            # Volume spike
            volume_spike = bool(volume_ratio.iloc[-1] > self.config.volume_multiplier)
            
            # Volume trend
            volume_trend = df['volume'].rolling(self.config.volume_trend_window).mean().diff()
            volume_increasing = bool(volume_trend.iloc[-1] > 0)
            
            # Volume consistency
            # Создаем булевую маску для высокого объема
            high_volume_mask = volume_ratio > self.config.volume_multiplier
            # Приводим к булевым значениям для избежания Series ambiguity
            high_volume_bool = high_volume_mask.astype(bool)
            high_volume_bars = high_volume_bool.rolling(3).sum()
            volume_consistency = bool(high_volume_bars.iloc[-1] >= 2)
            
            # Volume momentum
            volume_momentum = df['volume'].pct_change(5).iloc[-1]
            
            return {
                'volume_ratio': volume_ratio,
                'volume_spike': volume_spike,
                'volume_increasing': volume_increasing,
                'volume_consistency': volume_consistency,
                'volume_momentum': volume_momentum
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа объема: {e}")
            return {}
    
    def _calculate_momentum_analysis(self, df_fast: pd.DataFrame, df_slow: pd.DataFrame) -> Dict[str, Any]:
        """Анализ моментума между таймфреймами"""
        try:
            # Momentum на разных ТФ
            fast_momentum_5 = df_fast['close'].pct_change(5).iloc[-1]
            fast_momentum_10 = df_fast['close'].pct_change(10).iloc[-1]
            slow_momentum_3 = df_slow['close'].pct_change(3).iloc[-1]
            slow_momentum_5 = df_slow['close'].pct_change(5).iloc[-1]
            
            # Синхронизация моментума
            momentum_aligned = bool(np.sign(fast_momentum_5) == np.sign(slow_momentum_3))
            
            # Сила моментума
            momentum_strength = (abs(fast_momentum_5) + abs(slow_momentum_3)) / 2
            
            return {
                'fast_momentum_5': fast_momentum_5,
                'fast_momentum_10': fast_momentum_10,
                'slow_momentum_3': slow_momentum_3,
                'slow_momentum_5': slow_momentum_5,
                'momentum_aligned': momentum_aligned,
                'momentum_strength': momentum_strength
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа моментума: {e}")
            return {}
    
    def _detect_mtf_divergence(self, df_fast: pd.DataFrame, df_slow: pd.DataFrame) -> Dict[str, bool]:
        """Детекция дивергенций между таймфреймами"""
        try:
            # Анализируем последние 20 баров
            analysis_period = min(20, len(df_fast), len(df_slow))
            
            fast_recent = df_fast.tail(analysis_period)
            slow_recent = df_slow.tail(analysis_period)
            
            # Находим локальные экстремумы
            fast_highs = self._find_local_extrema(fast_recent['close'], 'high')
            fast_lows = self._find_local_extrema(fast_recent['close'], 'low')
            slow_highs = self._find_local_extrema(slow_recent['close'], 'high')
            slow_lows = self._find_local_extrema(slow_recent['close'], 'low')
            
            # Проверяем дивергенции
            bullish_divergence = False
            bearish_divergence = False
            
            if len(fast_lows) >= 2 and len(slow_lows) >= 2:
                # Бычья дивергенция: быстрый ТФ делает новые минимумы, медленный - нет
                # Получаем значения по индексам
                fast_low_1 = float(fast_recent['close'].iloc[fast_lows[-1]])
                fast_low_2 = float(fast_recent['close'].iloc[fast_lows[-2]])
                slow_low_1 = float(slow_recent['close'].iloc[slow_lows[-1]])
                slow_low_2 = float(slow_recent['close'].iloc[slow_lows[-2]])
                
                if (fast_low_1 < fast_low_2 and slow_low_1 > slow_low_2):
                    bullish_divergence = True
            
            if len(fast_highs) >= 2 and len(slow_highs) >= 2:
                # Медвежья дивергенция: быстрый ТФ делает новые максимумы, медленный - нет
                # Получаем значения по индексам
                fast_high_1 = float(fast_recent['close'].iloc[fast_highs[-1]])
                fast_high_2 = float(fast_recent['close'].iloc[fast_highs[-2]])
                slow_high_1 = float(slow_recent['close'].iloc[slow_highs[-1]])
                slow_high_2 = float(slow_recent['close'].iloc[slow_highs[-2]])
                
                if (fast_high_1 > fast_high_2 and slow_high_1 < slow_high_2):
                    bearish_divergence = True
            
            return {
                'bullish_divergence': bullish_divergence,
                'bearish_divergence': bearish_divergence
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка детекции дивергенций: {e}")
            return {'bullish_divergence': False, 'bearish_divergence': False}
    
    def _find_local_extrema(self, series: pd.Series, extrema_type: str) -> List[int]:
        """Поиск локальных экстремумов"""
        try:
            extrema_indices = []
            
            for i in range(2, len(series) - 2):
                if extrema_type == 'high':
                    # Извлекаем скалярные значения для сравнения
                    current = float(series.iloc[i])
                    prev1 = float(series.iloc[i-1])
                    prev2 = float(series.iloc[i-2])
                    next1 = float(series.iloc[i+1])
                    next2 = float(series.iloc[i+2])
                    
                    if (current > prev1 and current > prev2 and current > next1 and current > next2):
                        extrema_indices.append(i)
                else:  # low
                    # Извлекаем скалярные значения для сравнения
                    current = float(series.iloc[i])
                    prev1 = float(series.iloc[i-1])
                    prev2 = float(series.iloc[i-2])
                    next1 = float(series.iloc[i+1])
                    next2 = float(series.iloc[i+2])
                    
                    if (current < prev1 and current < prev2 and current < next1 and current < next2):
                        extrema_indices.append(i)
            
            return extrema_indices
            
        except Exception as e:
            self.logger.error(f"Ошибка поиска экстремумов: {e}")
            return []
    
    def calculate_signal_strength(self, market_data, indicators: Dict, signal_type: str) -> float:
        """
        Расчет силы сигнала для MultiTF стратегии - ОПТИМИЗИРОВАНО до 3 ключевых факторов

        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала ('BUY' или 'SELL')

        Returns:
            Сила сигнала от 0 до 1
        """
        try:
            # КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: только 3 основных фактора
            strength_factors = []

            # 1. Фактор синхронизации трендов (0-1) - ГЛАВНЫЙ для MTF стратегии
            trends_aligned_bullish = indicators.get('trends_aligned_bullish', False)
            trends_aligned_bearish = indicators.get('trends_aligned_bearish', False)

            # Handle Series types for trend alignment
            if isinstance(trends_aligned_bullish, pd.Series):
                trends_aligned_bullish = bool(trends_aligned_bullish.iloc[-1]) if not trends_aligned_bullish.empty else False
            if isinstance(trends_aligned_bearish, pd.Series):
                trends_aligned_bearish = bool(trends_aligned_bearish.iloc[-1]) if not trends_aligned_bearish.empty else False

            if signal_type == 'BUY':
                trend_sync_factor = 1.0 if trends_aligned_bullish else 0.0
            else:
                trend_sync_factor = 1.0 if trends_aligned_bearish else 0.0
            strength_factors.append(trend_sync_factor)

            # 2. Фактор объемного подтверждения (0-1) - КРИТИЧЕСКИЙ для входа
            volume_data = indicators.get('volume_analysis', {})
            volume_ratio = volume_data.get('volume_ratio', pd.Series([1])).iloc[-1] if isinstance(volume_data.get('volume_ratio'), pd.Series) else 1.0
            volume_factor = min(volume_ratio / self.config.volume_multiplier, 2.0) / 2.0
            strength_factors.append(volume_factor)

            # 3. Фактор позиции цены (0-1) - упрощенный momentum
            slow_trend = indicators.get('slow_trend', {})
            trend_strength = slow_trend.get('trend_strength', 0)

            # Handle pandas Series for trend_strength
            if isinstance(trend_strength, pd.Series):
                trend_strength = float(trend_strength.iloc[-1]) if not trend_strength.empty else 0.0

            price_position_factor = min(trend_strength / self.config.trend_strength_threshold, 1.0)
            strength_factors.append(price_position_factor)

            # УПРОЩЕННЫЕ ВЕСА: равномерное распределение для ускорения
            weights = [0.50, 0.30, 0.20]  # Тренд доминирует, объем подтверждает, позиция уточняет
            signal_strength = sum(factor * weight for factor, weight in zip(strength_factors, weights))

            return min(signal_strength, 1.0)

        except Exception as e:
            self.logger.error(f"Ошибка расчета силы сигнала: {e}")
            return 0.5
    
    def check_confluence_factors(self, market_data, indicators: Dict, signal_type: str) -> Tuple[int, List[str]]:
        """
        Проверка confluence факторов для MultiTF стратегии - УПРОЩЕНО до 3 ключевых факторов

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

            # ФАКТОР 1: Синхронизация трендов между таймфреймами (ГЛАВНЫЙ)
            trends_aligned_bullish = indicators.get('trends_aligned_bullish', False)
            trends_aligned_bearish = indicators.get('trends_aligned_bearish', False)

            # Handle Series types for trend alignment
            if isinstance(trends_aligned_bullish, pd.Series):
                trends_aligned_bullish = bool(trends_aligned_bullish.iloc[-1]) if not trends_aligned_bullish.empty else False
            if isinstance(trends_aligned_bearish, pd.Series):
                trends_aligned_bearish = bool(trends_aligned_bearish.iloc[-1]) if not trends_aligned_bearish.empty else False

            if signal_type == 'BUY' and trends_aligned_bullish:
                confluence_count += 1
                factors.append('trend_alignment')
            elif signal_type == 'SELL' and trends_aligned_bearish:
                confluence_count += 1
                factors.append('trend_alignment')

            # ФАКТОР 2: Объемное подтверждение (КРИТИЧЕСКИЙ)
            volume_data = indicators.get('volume_analysis', {})
            volume_spike = volume_data.get('volume_spike', False)

            # Handle Series type for volume_spike
            if isinstance(volume_spike, pd.Series):
                volume_spike = bool(volume_spike.iloc[-1]) if not volume_spike.empty else False

            if volume_spike:
                confluence_count += 1
                factors.append('volume_confirmation')

            # ФАКТОР 3: Позиция цены (упрощенный trend strength)
            slow_trend = indicators.get('slow_trend', {})
            trend_strength = slow_trend.get('trend_strength', 0)

            # Handle Series type for trend_strength
            if isinstance(trend_strength, pd.Series):
                trend_strength = float(trend_strength.iloc[-1]) if not trend_strength.empty else 0.0

            if trend_strength > self.config.trend_strength_threshold:
                confluence_count += 1
                factors.append('price_position')

            return confluence_count, factors

        except Exception as e:
            self.logger.error(f"Ошибка проверки confluence факторов: {e}")
            return 0, []
    
    def _check_strategic_exit_conditions(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Проверка стратегических условий выхода для MultiTF стратегии
        
        Args:
            market_data: Рыночные данные
            state: Состояние позиции
            current_price: Текущая цена
        
        Returns:
            Словарь с сигналом выхода или None
        """
        try:
            if not state or not state.in_position:
                return None
            
            position_side = getattr(state, 'position_side', None)
            entry_price = getattr(state, 'entry_price', None)
            
            if not position_side or not entry_price:
                return None
            
            # Получаем индикаторы
            indicators = self.calculate_strategy_indicators(market_data)
            if not indicators:
                return None
            
            # Расчет текущего P&L
            if position_side == 'BUY':
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - current_price) / entry_price * 100
            
            # 1. Трейлинг стоп (если прибыль > 1.5%)
            if pnl_pct > self.config.trailing_stop_activation_pct:
                df = self.get_primary_dataframe(market_data)
                if df is not None:
                    atr = TechnicalIndicators.calculate_atr_safe(df, 14).value
                    trailing_distance = atr * 0.7
                    
                    if position_side == 'BUY':
                        trailing_stop = current_price - trailing_distance
                        if current_price < trailing_stop:
                            return {
                                'signal': SignalType.EXIT_LONG.value,
                                'reason': 'trailing_stop',
                                'current_price': current_price,
                                'pnl_pct': pnl_pct
                            }
                    else:
                        trailing_stop = current_price + trailing_distance
                        if current_price > trailing_stop:
                            return {
                                'signal': SignalType.EXIT_SHORT.value,
                                'reason': 'trailing_stop',
                                'current_price': current_price,
                                'pnl_pct': pnl_pct
                            }
            
            # 2. Обратные сигналы на основе тренда
            trends_aligned_bullish = indicators.get('trends_aligned_bullish', False)
            trends_aligned_bearish = indicators.get('trends_aligned_bearish', False)
            
            # Handle Series types
            if isinstance(trends_aligned_bullish, pd.Series):
                trends_aligned_bullish = bool(trends_aligned_bullish.iloc[-1]) if not trends_aligned_bullish.empty else False
            if isinstance(trends_aligned_bearish, pd.Series):
                trends_aligned_bearish = bool(trends_aligned_bearish.iloc[-1]) if not trends_aligned_bearish.empty else False
            
            if position_side == 'BUY' and trends_aligned_bearish:
                return {
                    'signal': SignalType.EXIT_LONG.value,
                    'reason': 'trend_reversal',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct
                }
            elif position_side == 'SELL' and trends_aligned_bullish:
                return {
                    'signal': SignalType.EXIT_SHORT.value,
                    'reason': 'trend_reversal',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки условий выхода: {e}")
            return None
    
    def execute(self, market_data, state=None, bybit_api=None, symbol='BTCUSDT') -> Optional[Dict]:
        """
        Главный метод выполнения MultiTF стратегии
        
        Args:
            market_data: Рыночные данные
            state: Состояние позиции
            bybit_api: API для логирования
            symbol: Торговый символ
        
        Returns:
            Словарь с сигналом или None
        """
        try:
            # 1. Предварительные проверки
            can_execute, reason = self.pre_execution_check(market_data, state)
            if not can_execute:
                self.logger.debug(f"Стратегия не выполняется: {reason}")
                return None
            
            # 2. Валидация данных
            is_valid, validation_msg = self.validate_market_data(market_data)
            if not is_valid:
                self.logger.warning(f"Валидация данных не пройдена: {validation_msg}")
                return None
            
            # 3. Получаем данные
            df_fast = self.get_primary_dataframe(market_data)
            if df_fast is None:
                return None
            
            # 4. Анализ рыночных условий
            self._update_market_regime(market_data)
            
            # 5. Расчет индикаторов
            indicators = self.calculate_strategy_indicators(market_data)
            if not indicators:
                self.logger.error("Ошибка расчета индикаторов")
                return None
            
            # 6. Проверка выхода из существующей позиции
            if self.is_in_position(state):
                exit_signal = self._check_strategic_exit_conditions(market_data, state, df_fast['close'].iloc[-1])
                if exit_signal:
                    self.logger.info(f"Генерация сигнала выхода: {exit_signal['signal']}")
                    return self.create_signal(
                        signal_type=exit_signal['signal'],
                        entry_price=df_fast['close'].iloc[-1],
                        stop_loss=df_fast['close'].iloc[-1],  # Для выхода не важно
                        take_profit=df_fast['close'].iloc[-1],  # Для выхода не важно
                        indicators=indicators,
                        confluence_factors=[exit_signal['reason']],
                        signal_strength=0.8,
                        symbol=symbol,
                        additional_data={'exit_reason': exit_signal['reason']}
                    )
            
            # 7. Если уже в позиции, не генерируем новые сигналы входа
            if self.is_in_position(state):
                return None
            
            # 8. Основная торговая логика
            current_price = df_fast['close'].iloc[-1]
            
            # Условия для лонга
            trends_bullish = indicators.get('trends_aligned_bullish', False)
            volume_analysis = indicators.get('volume_analysis', {})
            volume_spike = volume_analysis.get('volume_spike', False)
            
            # Handle Series types
            if isinstance(trends_bullish, pd.Series):
                trends_bullish = bool(trends_bullish.iloc[-1]) if not trends_bullish.empty else False
            if isinstance(volume_spike, pd.Series):
                volume_spike = bool(volume_spike.iloc[-1]) if not volume_spike.empty else False
            
            # Условия для шорта
            trends_bearish = indicators.get('trends_aligned_bearish', False)
            if isinstance(trends_bearish, pd.Series):
                trends_bearish = bool(trends_bearish.iloc[-1]) if not trends_bearish.empty else False
            
            # 9. Проверка confluence факторов
            long_confluence, long_factors = self.check_confluence_factors(market_data, indicators, 'BUY')
            short_confluence, short_factors = self.check_confluence_factors(market_data, indicators, 'SELL')
            
            # 10. Генерация сигналов - использование скалярных значений для логических выражений
            long_entry = (trends_bullish and volume_spike and 
                         long_confluence >= self.config.confluence_required)
            short_entry = (trends_bearish and volume_spike and 
                          short_confluence >= self.config.confluence_required)
            
            # 11. Обработка сигнала лонга
            if long_entry:
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'BUY')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Сигнал BUY отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_dynamic_levels(df_fast, entry_price, 'BUY')
                
                # Проверка R:R
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
                actual_rr = reward / risk if risk > 0 else 0
                
                if actual_rr < 1.0:
                    self.logger.debug(f"Сигнал BUY отклонен: плохой R:R {actual_rr:.2f}")
                    return None
                
                self.logger.info(f"Генерация BUY сигнала: сила {signal_strength:.3f}")
                
                return self.create_signal(
                    signal_type='BUY',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    indicators=indicators,
                    confluence_factors=long_factors,
                    signal_strength=signal_strength,
                    symbol=symbol,
                    additional_data={
                        'trends_aligned': trends_bullish,
                        'volume_spike': volume_spike,
                        'momentum_alignment': indicators.get('momentum_alignment', False)
                    }
                )
            
            # 12. Обработка сигнала шорта
            elif short_entry:
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'SELL')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Сигнал SELL отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_dynamic_levels(df_fast, entry_price, 'SELL')
                
                # Проверка R:R
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
                actual_rr = reward / risk if risk > 0 else 0
                
                if actual_rr < 1.0:
                    self.logger.debug(f"Сигнал SELL отклонен: плохой R:R {actual_rr:.2f}")
                    return None
                
                self.logger.info(f"Генерация SELL сигнала: сила {signal_strength:.3f}")
                
                return self.create_signal(
                    signal_type='SELL',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    indicators=indicators,
                    confluence_factors=short_factors,
                    signal_strength=signal_strength,
                    symbol=symbol,
                    additional_data={
                        'trends_aligned': trends_bearish,
                        'volume_spike': volume_spike,
                        'momentum_alignment': indicators.get('momentum_alignment', False)
                    }
                )
            
            # 13. Нет сигнала
            return None
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка в execute: {e}", exc_info=True)
            return None
    
    def _update_market_regime(self, market_data):
        """Обновление рыночного режима"""
        try:
            df = self.get_primary_dataframe(market_data)
            if df is None:
                return
            
            # Простой анализ рыночного режима
            returns = df['close'].pct_change().dropna()
            volatility = returns.std()
            
            if volatility > 0.03:  # 3%
                self.current_market_regime = MarketRegime.VOLATILE
            elif volatility < 0.01:  # 1%
                self.current_market_regime = MarketRegime.SIDEWAYS
            else:
                self.current_market_regime = MarketRegime.NORMAL
                
        except Exception as e:
            self.logger.error(f"Ошибка обновления рыночного режима: {e}")
            self.current_market_regime = MarketRegime.NORMAL
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Получение информации о стратегии"""
        return {
            'strategy_name': 'MultiTF_Volume_v2',
            'version': '2.0.0',
            'description': 'Multi-Timeframe Volume стратегия с улучшенной архитектурой',
            'config': {
                'fast_tf': self.config.fast_tf.value,
                'slow_tf': self.config.slow_tf.value,
                'fast_window': self.config.fast_window,
                'slow_window': self.config.slow_window,
                'volume_multiplier': self.config.volume_multiplier,
                'trend_strength_threshold': self.config.trend_strength_threshold,
                'advanced_trend_analysis': self.config.advanced_trend_analysis,
                'momentum_analysis': self.config.momentum_analysis,
                'mtf_divergence_detection': self.config.mtf_divergence_detection
            },
            'current_market_regime': self.current_market_regime.value,
            'is_active': self.is_active
        }


# =============================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ ДЛЯ СОЗДАНИЯ СТРАТЕГИЙ
# =============================================================================

def create_multitf_volume_strategy(config: Optional[MultiTFConfig] = None, **kwargs) -> MultiTFVolumeStrategy:
    """
    Создание экземпляра Multi-Timeframe Volume стратегии
    
    Args:
        config: Конфигурация стратегии (опционально)
        **kwargs: Дополнительные параметры для конфигурации
    
    Returns:
        Экземпляр MultiTFVolumeStrategy
    """
    if config is None:
        config = MultiTFConfig()
    
    # Применяем дополнительные параметры
    if kwargs:
        config = config.copy(**kwargs)
    
    return MultiTFVolumeStrategy(config)


def create_conservative_multitf_volume() -> MultiTFVolumeStrategy:
    """Создание консервативной версии MultiTF стратегии"""
    config = MultiTFConfig(
        fast_tf=TimeFrame.M5,
        slow_tf=TimeFrame.H1,
        fast_window=30,
        slow_window=50,
        volume_multiplier=3.0,  # Более высокий объем
        confluence_required=3,  # Больше подтверждений
        signal_strength_threshold=0.7,  # Более строгий фильтр
        trend_strength_threshold=0.002,  # Более высокий порог тренда
        risk_reward_ratio=2.0,  # Лучшее R:R
        stop_loss_atr_multiplier=1.2  # Более близкий SL
    )
    return MultiTFVolumeStrategy(config)


def create_aggressive_multitf_volume() -> MultiTFVolumeStrategy:
    """Создание агрессивной версии MultiTF стратегии"""
    config = MultiTFConfig(
        fast_tf=TimeFrame.M1,
        slow_tf=TimeFrame.M15,
        fast_window=10,
        slow_window=20,
        volume_multiplier=1.5,  # Более низкий объем
        confluence_required=1,  # Меньше подтверждений
        signal_strength_threshold=0.5,  # Более мягкий фильтр
        trend_strength_threshold=0.0005,  # Более низкий порог тренда
        risk_reward_ratio=1.5,  # Стандартное R:R
        stop_loss_atr_multiplier=2.0,  # Более дальний SL
        tf_sync_tolerance=5  # Больше толерантности
    )
    return MultiTFVolumeStrategy(config)