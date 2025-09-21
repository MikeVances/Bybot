# bot/strategy/implementations/cumdelta_sr_strategy.py
"""
CumDelta Support/Resistance стратегия - рефакторенная версия Strategy02
Использует новую базовую архитектуру для устранения дублирования кода

Торговая логика:
- Анализ кумулятивной дельты (Cumulative Delta)
- Поиск уровней поддержки и сопротивления
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
    CumDeltaConfig, 
    MarketRegime,
    SignalType,
    ConfluenceFactor,
    PositionSide
)
from ..utils.indicators import TechnicalIndicators
from ..utils.validators import DataValidator
from ..utils.market_analysis import MarketRegimeAnalyzer
from ..utils.levels import LevelsFinder


class CumDeltaSRStrategy(BaseStrategy):
    """
    CumDelta Support/Resistance стратегия v2.0
    
    Торговая логика:
    - Анализ кумулятивной дельты для определения давления покупателей/продавцов
    - Поиск и валидация уровней поддержки/сопротивления
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
    
    def __init__(self, config: CumDeltaConfig):
        """
        Инициализация CumDelta Support/Resistance стратегии
        
        Args:
            config: Конфигурация стратегии типа CumDeltaConfig
        """
        super().__init__(config, "CumDelta_SR_v2")
        
        # Специфичная конфигурация
        self.config: CumDeltaConfig = config
        
        # Устанавливаем минимальное R:R соотношение для согласованности
        self.config.min_risk_reward_ratio = 0.8  # Снижаем для лучшей совместимости
        
        # Кэш для расчетов
        self._delta_cache = {}
        self._levels_cache = {}
        
        self.logger.info(f"🎯 CumDelta Support/Resistance стратегия инициализирована")
        self.logger.info(f"📊 Параметры: delta_window={config.delta_window}, support_window={config.support_window}")
    
    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        """
        Расчет специфичных индикаторов для CumDelta стратегии
        
        Args:
            market_data: Рыночные данные (DataFrame или Dict)
        
        Returns:
            Dict с рассчитанными индикаторами
        """
        try:
            # Получаем основной DataFrame
            df = self.get_primary_dataframe(market_data)
            if df is None:
                self.logger.error("Не удалось получить данные для расчета индикаторов")
                return {}
            
            indicators = {}
            
            # 1. Базовые индикаторы (из родительского класса)
            base_indicators = self.calculate_base_indicators(df)
            indicators.update(base_indicators)
            
            # 2. Кумулятивная дельта
            indicators['cum_delta'] = self._calculate_enhanced_delta(df)
            indicators['delta_momentum'] = indicators['cum_delta'].diff(self.config.delta_momentum_period)
            indicators['delta_strength'] = abs(indicators['cum_delta']) / df['volume'].rolling(10, min_periods=1).mean()
            
            # 3. Уровни поддержки и сопротивления
            try:
                from bot.strategy.utils.levels import find_all_levels, get_trading_levels
                
                # Получаем все уровни
                all_levels = find_all_levels(df, current_price=df['close'].iloc[-1])
                
                # Разделяем на поддержку и сопротивление
                support_levels = [level.price for level in all_levels if level.level_type.value == 'support']
                resistance_levels = [level.price for level in all_levels if level.level_type.value == 'resistance']
            except ImportError:
                # Fallback если модуль уровней недоступен
                self.logger.warning("Модуль levels недоступен, используем fallback расчет")
                support_levels = [df['low'].tail(self.config.support_window).min()]
                resistance_levels = [df['high'].tail(self.config.support_window).max()]
            
            indicators['support_levels'] = support_levels
            indicators['resistance_levels'] = resistance_levels
            
            # Находим ближайшие уровни
            current_price = df['close'].iloc[-1]
            if support_levels:
                indicators['nearest_support'] = min(support_levels, key=lambda x: abs(x - current_price))
            else:
                indicators['nearest_support'] = None
                
            if resistance_levels:
                indicators['nearest_resistance'] = min(resistance_levels, key=lambda x: abs(x - current_price))
            else:
                indicators['nearest_resistance'] = None
            
            # Зоны поддержки/сопротивления с толерантностью
            if indicators['nearest_support']:
                indicators['support_zone'] = indicators['nearest_support'] * (1 + self.config.support_resistance_tolerance)
            else:
                indicators['support_zone'] = df['low'].tail(self.config.support_window).min()
            
            if indicators['nearest_resistance']:
                indicators['resist_zone'] = indicators['nearest_resistance'] * (1 - self.config.support_resistance_tolerance)
            else:
                indicators['resist_zone'] = df['high'].tail(self.config.support_window).max()
            
            # 4. Анализ тренда
            indicators['trend_slope'] = df['close'].rolling(self.config.trend_period, min_periods=1).mean().diff()
            indicators['trend_strength'] = abs(indicators['trend_slope']) / current_price
            
            # 5. Объемные индикаторы
            if 'volume' in df.columns:
                vol_sma = df['volume'].rolling(20, min_periods=1).mean()
                indicators['volume_ratio'] = df['volume'] / vol_sma
                indicators['volume_increasing'] = df['volume'].diff() > 0
                
                # Корреляция объема и дельты
                if self.config.volume_delta_correlation:
                    indicators['volume_delta_corr'] = self._calculate_volume_delta_correlation(df, indicators['cum_delta'])
            
            # 6. Дополнительные индикаторы
            # RSI для фильтрации
            rsi_result = TechnicalIndicators.calculate_rsi(df)
            if rsi_result.is_valid:
                indicators['rsi'] = rsi_result.value
            
            # Bollinger Bands
            bb_result = TechnicalIndicators.calculate_bollinger_bands(df)
            if bb_result.is_valid:
                indicators['bb_position'] = bb_result.value['position']
                indicators['bb_upper'] = bb_result.value['upper']
                indicators['bb_lower'] = bb_result.value['lower']
            
            # 7. Дивергенции (если включены)
            if self.config.delta_divergence_detection:
                indicators['delta_divergence'] = self._detect_delta_divergence(df, indicators['cum_delta'])
            
            # 8. Анализ пробоев (если включены)
            if self.config.support_resistance_breakout:
                indicators['support_breakout'] = self._detect_support_breakout(df, indicators['support_levels'])
                indicators['resistance_breakout'] = self._detect_resistance_breakout(df, indicators['resistance_levels'])
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета индикаторов CumDelta: {e}")
            return {}
    
    def _calculate_enhanced_delta(self, df: pd.DataFrame) -> pd.Series:
        """Улучшенный расчет кумулятивной дельты"""
        try:
            # Проверяем наличие колонок buy_volume и sell_volume
            if "buy_volume" in df.columns and "sell_volume" in df.columns:
                delta = df["buy_volume"] - df["sell_volume"]
            elif "delta" in df.columns:
                delta = df["delta"]
            else:
                # Fallback: используем улучшенную дельту на основе цены и объема
                price_change = df['close'].pct_change()
                volume_weighted_delta = price_change * df['volume'] * np.sign(price_change)
                delta = volume_weighted_delta.fillna(0)
            
            # Сглаживание дельты
            if self.config.delta_smoothing_period > 1:
                delta = delta.rolling(self.config.delta_smoothing_period, min_periods=1).mean()
            
            # Кумулятивная дельта
            cum_delta = delta.rolling(self.config.delta_window, min_periods=1).sum()
            
            return cum_delta
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета дельты: {e}")
            # Fallback к простому расчету
            return (df["close"] - df["open"]).rolling(self.config.delta_window, min_periods=1).sum()
    
    def _calculate_volume_delta_correlation(self, df: pd.DataFrame, cum_delta: pd.Series) -> float:
        """Расчет корреляции между объемом и дельтой"""
        try:
            # Используем последние 20 баров для расчета корреляции
            window = min(20, len(df))
            volume = df['volume'].tail(window)
            delta = cum_delta.tail(window)
            
            if len(volume) < 5:  # Минимум для корреляции
                return 0.0
            
            correlation = volume.corr(delta)
            return correlation if not pd.isna(correlation) else 0.0
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета корреляции объема и дельты: {e}")
            return 0.0
    
    def _detect_delta_divergence(self, df: pd.DataFrame, cum_delta: pd.Series) -> Dict[str, bool]:
        """Детекция дивергенций между ценой и дельтой"""
        try:
            # Анализируем последние 30 баров
            analysis_period = min(30, len(df))
            recent_price = df['close'].tail(analysis_period)
            recent_delta = cum_delta.tail(analysis_period)
            
            # Находим локальные экстремумы
            price_highs = self._find_local_extrema(recent_price, 'high')
            price_lows = self._find_local_extrema(recent_price, 'low')
            delta_highs = self._find_local_extrema(recent_delta, 'high')
            delta_lows = self._find_local_extrema(recent_delta, 'low')
            
            # Проверяем дивергенции
            bullish_divergence = False
            bearish_divergence = False
            
            if len(price_lows) >= 2 and len(delta_lows) >= 2:
                # Бычья дивергенция: цена делает новые минимумы, дельта - нет
                if price_lows[-1] < price_lows[-2] and delta_lows[-1] > delta_lows[-2]:
                    bullish_divergence = True
            
            if len(price_highs) >= 2 and len(delta_highs) >= 2:
                # Медвежья дивергенция: цена делает новые максимумы, дельта - нет
                if price_highs[-1] > price_highs[-2] and delta_highs[-1] < delta_highs[-2]:
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
                    if (series.iloc[i] > series.iloc[i-1] and series.iloc[i] > series.iloc[i-2] and
                        series.iloc[i] > series.iloc[i+1] and series.iloc[i] > series.iloc[i+2]):
                        extrema_indices.append(i)
                else:  # low
                    if (series.iloc[i] < series.iloc[i-1] and series.iloc[i] < series.iloc[i-2] and
                        series.iloc[i] < series.iloc[i+1] and series.iloc[i] < series.iloc[i+2]):
                        extrema_indices.append(i)
            
            return extrema_indices
            
        except Exception as e:
            self.logger.error(f"Ошибка поиска экстремумов: {e}")
            return []
    
    def _detect_support_breakout(self, df: pd.DataFrame, support_levels: List[float]) -> bool:
        """Детекция пробоя поддержки"""
        try:
            if not support_levels:
                return False
            
            current_price = df['close'].iloc[-1]
            previous_price = df['close'].iloc[-2]
            
            # Проверяем, была ли цена выше поддержки, а теперь ниже
            for support in support_levels:
                if previous_price > support and current_price < support:
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Ошибка детекции пробоя поддержки: {e}")
            return False
    
    def _detect_resistance_breakout(self, df: pd.DataFrame, resistance_levels: List[float]) -> bool:
        """Детекция пробоя сопротивления"""
        try:
            if not resistance_levels:
                return False
            
            current_price = df['close'].iloc[-1]
            previous_price = df['close'].iloc[-2]
            
            # Проверяем, была ли цена ниже сопротивления, а теперь выше
            for resistance in resistance_levels:
                if previous_price < resistance and current_price > resistance:
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Ошибка детекции пробоя сопротивления: {e}")
            return False
    
    def calculate_signal_strength(self, market_data, indicators: Dict, signal_type: str) -> float:
        """
        Расчет силы сигнала для CumDelta стратегии
        
        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала ('BUY' или 'SELL')
        
        Returns:
            Сила сигнала от 0 до 1
        """
        try:
            df = self.get_primary_dataframe(market_data)
            if df is None:
                return 0.0
            
            strength_factors = []
            current_price = df['close'].iloc[-1]
            
            # 1. Фактор кумулятивной дельты (0-1)
            cum_delta_series = indicators.get('cum_delta', pd.Series([0]))
            cum_delta = float(cum_delta_series.iloc[-1]) if not cum_delta_series.empty else 0.0
            delta_factor = min(abs(cum_delta) / (self.config.min_delta_threshold * 2), 1.0)
            strength_factors.append(delta_factor)
            
            # 2. Фактор близости к S/R уровням (0-1)
            if signal_type == 'BUY':
                # Для лонга: близость к поддержке
                support_zone = indicators.get('support_zone', current_price * 0.99)
                distance_to_support = abs(current_price - support_zone) / current_price
                sr_factor = max(0, 1 - (distance_to_support * 100))
            else:
                # Для шорта: близость к сопротивлению
                resist_zone = indicators.get('resist_zone', current_price * 1.01)
                distance_to_resistance = abs(current_price - resist_zone) / current_price
                sr_factor = max(0, 1 - (distance_to_resistance * 100))
            strength_factors.append(sr_factor)
            
            # 3. Фактор силы тренда (0-1)
            trend_strength_series = indicators.get('trend_strength', 0)
            trend_strength = float(trend_strength_series) if isinstance(trend_strength_series, (int, float)) else 0.0
            trend_factor = min(trend_strength * 1000, 1.0)
            strength_factors.append(trend_factor)
            
            # 4. Фактор RSI (0-1)
            rsi_series = indicators.get('rsi', pd.Series([50]))
            rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
            if signal_type == 'BUY':
                rsi_factor = max(0, (50 - rsi) / 50) if rsi < 50 else 0
            else:
                rsi_factor = max(0, (rsi - 50) / 50) if rsi > 50 else 0
            strength_factors.append(rsi_factor)
            
            # 5. Фактор объема (0-1)
            volume_ratio_series = indicators.get('volume_ratio', pd.Series([1]))
            volume_ratio = float(volume_ratio_series.iloc[-1]) if not volume_ratio_series.empty else 1.0
            volume_factor = min(volume_ratio / 3.0, 1.0)
            strength_factors.append(volume_factor)
            
            # 6. Фактор моментума дельты (0-1)
            delta_momentum_series = indicators.get('delta_momentum', pd.Series([0]))
            delta_momentum = float(delta_momentum_series.iloc[-1]) if not delta_momentum_series.empty else 0.0
            if signal_type == 'BUY':
                momentum_factor = max(0, delta_momentum / self.config.min_delta_threshold) if delta_momentum > 0 else 0
            else:
                momentum_factor = max(0, -delta_momentum / self.config.min_delta_threshold) if delta_momentum < 0 else 0
            momentum_factor = min(momentum_factor, 1.0)
            strength_factors.append(momentum_factor)
            
            # 7. Фактор корреляции объема и дельты (0-1)
            volume_delta_corr = indicators.get('volume_delta_corr', 0)
            correlation_factor = abs(volume_delta_corr) if self.config.volume_delta_correlation else 0.5
            strength_factors.append(correlation_factor)
            
            # Взвешенная сила сигнала
            weights = [0.25, 0.20, 0.15, 0.12, 0.10, 0.10, 0.08]  # Delta и S/R важнее
            signal_strength = sum(factor * weight for factor, weight in zip(strength_factors, weights))
            
            return min(signal_strength, 1.0)
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета силы сигнала: {e}")
            return 0.5
    
    def check_confluence_factors(self, market_data, indicators: Dict, signal_type: str) -> Tuple[int, List[str]]:
        """
        Проверка confluence факторов для CumDelta стратегии
        
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
            
            df = self.get_primary_dataframe(market_data)
            if df is None:
                return 0, []
            
            current_price = df['close'].iloc[-1]
            
            # 1. Delta фактор
            cum_delta = indicators.get('cum_delta', pd.Series([0])).iloc[-1]
            if signal_type == 'BUY' and cum_delta > self.config.min_delta_threshold:
                confluence_count += 1
                factors.append(ConfluenceFactor.POSITIVE_DELTA.value)
            elif signal_type == 'SELL' and cum_delta < -self.config.min_delta_threshold:
                confluence_count += 1
                factors.append(ConfluenceFactor.NEGATIVE_DELTA.value)
            
            # 2. S/R фактор
            if signal_type == 'BUY':
                support_zone = indicators.get('support_zone', current_price * 0.99)
                if current_price <= support_zone:
                    confluence_count += 1
                    factors.append(ConfluenceFactor.AT_SUPPORT.value)
            else:
                resist_zone = indicators.get('resist_zone', current_price * 1.01)
                if current_price >= resist_zone:
                    confluence_count += 1
                    factors.append(ConfluenceFactor.AT_RESISTANCE.value)
            
            # 3. Трендовый фактор
            trend_slope = indicators.get('trend_slope', pd.Series([0])).iloc[-1]
            if signal_type == 'BUY' and trend_slope > 0:
                confluence_count += 1
                factors.append(ConfluenceFactor.BULLISH_TREND.value)
            elif signal_type == 'SELL' and trend_slope < 0:
                confluence_count += 1
                factors.append(ConfluenceFactor.BEARISH_TREND.value)
            
            # 4. RSI фактор
            rsi = indicators.get('rsi', pd.Series([50])).iloc[-1]
            if signal_type == 'BUY' and 30 <= rsi <= 60:
                confluence_count += 1
                factors.append(ConfluenceFactor.RSI_FAVORABLE.value)
            elif signal_type == 'SELL' and 40 <= rsi <= 70:
                confluence_count += 1
                factors.append(ConfluenceFactor.RSI_FAVORABLE.value)
            
            # 5. Volume фактор
            volume_ratio = indicators.get('volume_ratio', pd.Series([1])).iloc[-1]
            if volume_ratio > self.config.volume_multiplier:
                confluence_count += 1
                factors.append(ConfluenceFactor.HIGH_VOLUME.value)
            
            # 6. Delta momentum фактор
            delta_momentum = indicators.get('delta_momentum', pd.Series([0])).iloc[-1]
            if signal_type == 'BUY' and delta_momentum > 0:
                confluence_count += 1
                factors.append(ConfluenceFactor.DELTA_MOMENTUM.value)
            elif signal_type == 'SELL' and delta_momentum < 0:
                confluence_count += 1
                factors.append(ConfluenceFactor.DELTA_MOMENTUM.value)
            
            # 7. Дивергенция фактор
            if self.config.delta_divergence_detection:
                divergence = indicators.get('delta_divergence', {})
                if signal_type == 'BUY' and divergence.get('bullish_divergence', False):
                    confluence_count += 1
                    factors.append('delta_bullish_divergence')
                elif signal_type == 'SELL' and divergence.get('bearish_divergence', False):
                    confluence_count += 1
                    factors.append('delta_bearish_divergence')
            
            # 8. Пробой фактор
            if self.config.support_resistance_breakout:
                if signal_type == 'BUY' and indicators.get('support_breakout', False):
                    confluence_count += 1
                    factors.append(ConfluenceFactor.BREAKOUT_SUPPORT.value)
                elif signal_type == 'SELL' and indicators.get('resistance_breakout', False):
                    confluence_count += 1
                    factors.append(ConfluenceFactor.BREAKOUT_RESISTANCE.value)
            
            return confluence_count, factors
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки confluence факторов: {e}")
            return 0, []
    
    def _check_strategic_exit_conditions(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Проверка стратегических условий выхода для CumDelta стратегии
        
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
            
            # 2. Обратные сигналы на основе дельты
            cum_delta = indicators.get('cum_delta', pd.Series([0])).iloc[-1]
            
            if position_side == 'BUY':
                # Выход из лонга при отрицательной дельте
                if cum_delta < -self.config.min_delta_threshold:
                    return {
                        'signal': SignalType.EXIT_LONG.value,
                        'reason': 'negative_delta',
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    }
            else:
                # Выход из шорта при положительной дельте
                if cum_delta > self.config.min_delta_threshold:
                    return {
                        'signal': SignalType.EXIT_SHORT.value,
                        'reason': 'positive_delta',
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки условий выхода: {e}")
            return None
    
    def execute(self, market_data, state=None, bybit_api=None, symbol='BTCUSDT') -> Optional[Dict]:
        """
        Главный метод выполнения CumDelta стратегии
        
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
            df = self.get_primary_dataframe(market_data)
            if df is None:
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
                exit_signal = self._check_strategic_exit_conditions(market_data, state, df['close'].iloc[-1])
                if exit_signal:
                    self.logger.info(f"Генерация сигнала выхода: {exit_signal['signal']}")
                    return self.create_signal(
                        signal_type=exit_signal['signal'],
                        entry_price=df['close'].iloc[-1],
                        stop_loss=df['close'].iloc[-1],  # Для выхода не важно
                        take_profit=df['close'].iloc[-1],  # Для выхода не важно
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
            current_price = df['close'].iloc[-1]
            cum_delta = indicators.get('cum_delta', pd.Series([0])).iloc[-1]
            
            # Условия для лонга
            delta_bullish = cum_delta > self.config.min_delta_threshold
            price_at_support = current_price <= indicators.get('support_zone', current_price * 0.99)
            trend_up = indicators.get('trend_slope', pd.Series([0])).iloc[-1] > 0
            
            # Условия для шорта
            delta_bearish = cum_delta < -self.config.min_delta_threshold
            price_at_resist = current_price >= indicators.get('resist_zone', current_price * 1.01)
            trend_down = indicators.get('trend_slope', pd.Series([0])).iloc[-1] < 0
            
            # 9. Проверка confluence факторов
            long_confluence, long_factors = self.check_confluence_factors(market_data, indicators, 'BUY')
            short_confluence, short_factors = self.check_confluence_factors(market_data, indicators, 'SELL')
            
            # 10. Генерация сигналов
            long_entry = (delta_bullish and price_at_support and trend_up and 
                         long_confluence >= self.config.confluence_required)
            short_entry = (delta_bearish and price_at_resist and trend_down and 
                          short_confluence >= self.config.confluence_required)
            
            # 11. Обработка сигнала лонга
            if long_entry:
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'BUY')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Сигнал BUY отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_dynamic_levels(df, entry_price, 'BUY')
                
                # Проверка R:R
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
                actual_rr = reward / risk if risk > 0 else 0
                
                if actual_rr < self.config.min_risk_reward_ratio:
                    self.logger.debug(f"Сигнал BUY отклонен: плохой R:R {actual_rr:.2f} < {self.config.min_risk_reward_ratio}")
                    return None
                
                self.logger.info(f"Генерация BUY сигнала: дельта {cum_delta:.0f}, сила {signal_strength:.3f}")
                
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
                        'cum_delta': float(cum_delta),
                        'support_zone': float(indicators.get('support_zone', 0)),
                        'delta_momentum': float(indicators.get('delta_momentum', pd.Series([0])).iloc[-1]),
                        'volume_delta_corr': float(indicators.get('volume_delta_corr', 0))
                    }
                )
            
            # 12. Обработка сигнала шорта
            elif short_entry:
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'SELL')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Сигнал SELL отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_dynamic_levels(df, entry_price, 'SELL')
                
                # Проверка R:R
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
                actual_rr = reward / risk if risk > 0 else 0
                
                if actual_rr < self.config.min_risk_reward_ratio:
                    self.logger.debug(f"Сигнал SELL отклонен: плохой R:R {actual_rr:.2f} < {self.config.min_risk_reward_ratio}")
                    return None
                
                self.logger.info(f"Генерация SELL сигнала: дельта {cum_delta:.0f}, сила {signal_strength:.3f}")
                
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
                        'cum_delta': float(cum_delta),
                        'resist_zone': float(indicators.get('resist_zone', 0)),
                        'delta_momentum': float(indicators.get('delta_momentum', pd.Series([0])).iloc[-1]),
                        'volume_delta_corr': float(indicators.get('volume_delta_corr', 0))
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
            'strategy_name': 'CumDelta_SupportResistance_v2',
            'version': '2.0.0',
            'description': 'CumDelta Support/Resistance стратегия с улучшенной архитектурой',
            'config': {
                'delta_window': self.config.delta_window,
                'support_window': self.config.support_window,
                'min_delta_threshold': self.config.min_delta_threshold,
                'support_resistance_tolerance': self.config.support_resistance_tolerance,
                'volume_multiplier': self.config.volume_multiplier,
                'use_enhanced_delta': self.config.use_enhanced_delta,
                'delta_divergence_detection': self.config.delta_divergence_detection,
                'support_resistance_breakout': self.config.support_resistance_breakout
            },
            'current_market_regime': self.current_market_regime.value,
            'is_active': self.is_active
        }


# =============================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ ДЛЯ СОЗДАНИЯ СТРАТЕГИЙ
# =============================================================================

def create_cumdelta_sr_strategy(config: Optional[CumDeltaConfig] = None, **kwargs) -> CumDeltaSRStrategy:
    """
    Создание экземпляра CumDelta Support/Resistance стратегии
    
    Args:
        config: Конфигурация стратегии (опционально)
        **kwargs: Дополнительные параметры для конфигурации
    
    Returns:
        Экземпляр CumDeltaSRStrategy
    """
    if config is None:
        config = CumDeltaConfig()
    
    # Применяем дополнительные параметры
    if kwargs:
        config = config.copy(**kwargs)
    
    return CumDeltaSRStrategy(config)


def create_conservative_cumdelta_sr() -> CumDeltaSRStrategy:
    """Создание консервативной версии CumDelta стратегии"""
    config = CumDeltaConfig(
        min_delta_threshold=150.0,  # Более высокий порог
        confluence_required=3,  # Больше подтверждений
        signal_strength_threshold=0.7,  # Более строгий фильтр
        support_resistance_tolerance=0.003,  # Больше толерантности
        volume_multiplier=2.0,  # Более высокий объем
        risk_reward_ratio=2.0,  # Лучшее R:R
        stop_loss_atr_multiplier=1.2  # Более близкий SL
    )
    return CumDeltaSRStrategy(config)


def create_aggressive_cumdelta_sr() -> CumDeltaSRStrategy:
    """Создание агрессивной версии CumDelta стратегии"""
    config = CumDeltaConfig(
        min_delta_threshold=50.0,  # Более низкий порог
        confluence_required=1,  # Меньше подтверждений
        signal_strength_threshold=0.5,  # Более мягкий фильтр
        support_resistance_tolerance=0.001,  # Меньше толерантности
        volume_multiplier=1.2,  # Более низкий объем
        risk_reward_ratio=1.5,  # Стандартное R:R
        stop_loss_atr_multiplier=2.0,  # Более дальний SL
        delta_smoothing_period=3,  # Меньше сглаживания
        delta_momentum_period=3  # Более быстрый моментум
    )
    return CumDeltaSRStrategy(config)
