# bot/strategy/implementations/volume_vwap_strategy.py
"""
VolumeSpike VWAP стратегия - рефакторенная версия Strategy01
Использует новую базовую архитектуру для устранения дублирования кода
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import logging

from ..base import (
    BaseStrategy,
    VolumeVWAPConfig, 
    MarketRegime,
    SignalType,
    ConfluenceFactor,
    PositionSide
)
from ..utils.indicators import TechnicalIndicators
from ..utils.validators import DataValidator
from ..utils.market_analysis import MarketRegimeAnalyzer


class VolumeVWAPStrategy(BaseStrategy):
    """
    VolumeSpike VWAP стратегия v2.0
    
    Торговая логика:
    - Поиск всплесков объема (volume spike)
    - Фильтрация по положению цены относительно VWAP
    - Подтверждение трендом
    - Адаптивные SL/TP уровни
    - Множественные confluence факторы
    
    Улучшения в v2.0:
    - Использование базовой архитектуры
    - Устранение дублирования кода
    - Расширенная система фильтров
    - Адаптивные параметры
    - Стандартизированные сигналы
    """
    
    def __init__(self, config: VolumeVWAPConfig):
        """
        Инициализация VolumeSpike VWAP стратегии
        
        Args:
            config: Конфигурация стратегии типа VolumeVWAPConfig
        """
        super().__init__(config, "VolumeVWAP_v2")
        
        # Специфичная конфигурация
        self.config: VolumeVWAPConfig = config
        
        # Устанавливаем минимальное R:R соотношение для скальпинга
        self.config.min_risk_reward_ratio = 0.8  # Снижаем для скальпинга (было 1.0)
        
        # Настраиваем адаптивные параметры для скальпинга
        self.config.adaptive_parameters = True  # Оставляем адаптивность
        self.config.market_regime_adaptation = True
        
        # Кэш для VWAP расчетов
        self._vwap_cache = {}
        
        self.logger.info(f"🎯 VolumeSpike VWAP стратегия инициализирована")
        self.logger.info(f"📊 Параметры: volume_mult={config.volume_multiplier}, trend_period={config.trend_period}")
        self.logger.info(f"📊 R:R настройки: risk_reward_ratio={config.risk_reward_ratio}, min_risk_reward_ratio={self.config.min_risk_reward_ratio}")
    
    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        """
        Расчет специфичных индикаторов для VWAP стратегии
        
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
            
            # 2. Объемные индикаторы
            if 'volume' in df.columns:
                # Volume SMA для определения всплесков
                vol_sma_period = self.config.volume_sma_period
                indicators['vol_sma'] = df['volume'].rolling(vol_sma_period, min_periods=1).mean()
                indicators['volume_ratio'] = df['volume'] / indicators['vol_sma']
                indicators['volume_spike'] = indicators['volume_ratio'] > self.config.volume_multiplier
                
                # Volume trend анализ
                vol_trend_window = self.config.volume_trend_window
                indicators['volume_trend'] = df['volume'].rolling(vol_trend_window).mean().diff()
                indicators['volume_increasing'] = indicators['volume_trend'] > 0
                
                # Volume consistency (последовательность высоких объемов)
                high_volume_bars = (indicators['volume_ratio'] > self.config.volume_multiplier).rolling(
                    self.config.min_volume_consistency
                ).sum()
                indicators['volume_consistent'] = high_volume_bars >= self.config.min_volume_consistency
                
            else:
                self.logger.warning("Отсутствуют данные об объеме - объемные индикаторы недоступны")
                indicators.update({
                    'vol_sma': pd.Series([1000] * len(df), index=df.index),
                    'volume_ratio': pd.Series([1.0] * len(df), index=df.index),
                    'volume_spike': pd.Series([False] * len(df), index=df.index),
                    'volume_increasing': pd.Series([False] * len(df), index=df.index),
                    'volume_consistent': pd.Series([False] * len(df), index=df.index)
                })
            
            # 3. VWAP расчеты
            vwap_result = TechnicalIndicators.calculate_vwap(df, self.config.vwap_period)
            if vwap_result.is_valid:
                indicators['vwap'] = vwap_result.value
                
                # Отклонение цены от VWAP
                indicators['vwap_deviation'] = abs(df['close'] - indicators['vwap']) / df['close']
                indicators['vwap_significant_deviation'] = indicators['vwap_deviation'] > self.config.vwap_deviation_threshold
                
                # Позиция относительно VWAP
                indicators['price_above_vwap'] = df['close'] > indicators['vwap']
                indicators['price_below_vwap'] = df['close'] < indicators['vwap']
                
                # VWAP confirmation (несколько баров подряд)
                confirmation_bars = self.config.vwap_confirmation_bars
                indicators['vwap_bullish_confirmed'] = indicators['price_above_vwap'].rolling(confirmation_bars).sum() >= confirmation_bars
                indicators['vwap_bearish_confirmed'] = indicators['price_below_vwap'].rolling(confirmation_bars).sum() >= confirmation_bars
                
            else:
                self.logger.error("Ошибка расчета VWAP")
                return {}
            
            # 4. Трендовые индикаторы
            trend_period = self.config.trend_period
            indicators['sma_trend'] = df['close'].rolling(trend_period, min_periods=1).mean()
            
            # Наклон тренда
            slope_period = max(trend_period // 4, 5)
            indicators['trend_slope'] = indicators['sma_trend'].diff(slope_period)
            indicators['trend_slope_normalized'] = indicators['trend_slope'] / df['close']
            
            # Направление тренда
            indicators['trend_bullish'] = indicators['trend_slope_normalized'] > self.config.min_trend_slope
            indicators['trend_bearish'] = indicators['trend_slope_normalized'] < -self.config.min_trend_slope
            indicators['trend_sideways'] = (~indicators['trend_bullish']) & (~indicators['trend_bearish'])
            
            # Сила тренда (на основе корреляции с временем)
            if len(df) >= trend_period:
                price_series = indicators['sma_trend'].tail(trend_period)
                time_series = np.arange(len(price_series))
                correlation = np.corrcoef(time_series, price_series)[0, 1] if len(price_series) > 1 else 0
                indicators['trend_strength'] = abs(correlation) if not np.isnan(correlation) else 0
            else:
                indicators['trend_strength'] = 0
            
            # 5. Моментум индикаторы
            momentum_period = self.config.price_momentum_period
            indicators['price_momentum'] = df['close'].pct_change(momentum_period)
            indicators['momentum_bullish'] = indicators['price_momentum'] > 0
            indicators['momentum_bearish'] = indicators['price_momentum'] < 0
            
            # Volume momentum
            if 'volume' in df.columns:
                vol_momentum_period = self.config.volume_momentum_period
                indicators['volume_momentum'] = df['volume'].pct_change(vol_momentum_period)
                indicators['volume_momentum_positive'] = indicators['volume_momentum'] > 0
            else:
                indicators['volume_momentum'] = pd.Series([0] * len(df), index=df.index)
                indicators['volume_momentum_positive'] = pd.Series([False] * len(df), index=df.index)
            
            # 6. Комбинированные сигналы
            # Bullish setup (адаптировано для бокового рынка)
            indicators['bullish_setup'] = (
                indicators['volume_spike'] & 
                indicators['price_above_vwap'] & 
                (indicators['trend_bullish'] | indicators['momentum_bullish'])  # Добавлен momentum
            )
            
            # Bearish setup (адаптировано для бокового рынка)
            indicators['bearish_setup'] = (
                indicators['volume_spike'] & 
                indicators['price_below_vwap'] & 
                (indicators['trend_bearish'] | indicators['momentum_bearish'])  # Добавлен momentum
            )
            
            # Дополнительные сетапы для бокового рынка
            indicators['range_bullish_setup'] = (
                indicators['volume_spike'] & 
                indicators['price_above_vwap'] & 
                indicators['trend_sideways'] & 
                indicators['momentum_bullish']
            )
            
            indicators['range_bearish_setup'] = (
                indicators['volume_spike'] & 
                indicators['price_below_vwap'] & 
                indicators['trend_sideways'] & 
                indicators['momentum_bearish']
            )
            
            self.logger.debug(f"Рассчитано {len(indicators)} индикаторов для VWAP стратегии")
            return indicators
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета индикаторов VWAP стратегии: {e}")
            return {}
    
    def calculate_signal_strength(self, market_data, indicators: Dict, signal_type: str) -> float:
        """
        Расчет силы сигнала для VWAP стратегии - ОПТИМИЗИРОВАНО до 3 ключевых факторов

        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала ('BUY' или 'SELL')

        Returns:
            Сила сигнала от 0.0 до 1.0
        """
        try:
            df = self.get_primary_dataframe(market_data)
            if df is None or not indicators:
                return 0.0

            # КРИТИЧЕСКАЯ ОПТИМИЗАЦИЯ: только 3 основных фактора для VWAP
            strength_factors = []
            last_idx = -1

            # 1. Фактор объемного подтверждения (0-1) - ГЛАВНЫЙ
            if 'volume_ratio' in indicators:
                volume_ratio = indicators['volume_ratio'].iloc[last_idx]
                volume_factor = min(volume_ratio / self.config.volume_multiplier, 3.0) / 3.0
                strength_factors.append(volume_factor)

            # 2. Фактор VWAP позиции (0-1) - КРИТИЧЕСКИЙ
            if 'vwap_deviation' in indicators:
                vwap_deviation = indicators['vwap_deviation'].iloc[last_idx]
                # Чем больше отклонение, тем сильнее потенциал возврата к VWAP
                vwap_factor = min(vwap_deviation / (self.config.vwap_deviation_threshold * 2), 1.0)
                strength_factors.append(vwap_factor)

            # 3. Фактор направления тренда (0-1) - ПОДТВЕРЖДАЮЩИЙ
            if signal_type in ['BUY', SignalType.BUY]:
                if 'trend_bullish' in indicators and indicators['trend_bullish'].iloc[last_idx]:
                    trend_factor = 1.0
                else:
                    trend_factor = 0.3  # Слабое подтверждение
            else:
                if 'trend_bearish' in indicators and indicators['trend_bearish'].iloc[last_idx]:
                    trend_factor = 1.0
                else:
                    trend_factor = 0.3
            strength_factors.append(trend_factor)

            # УПРОЩЕННЫЕ ВЕСА: равномерное распределение
            weights = [0.40, 0.35, 0.25]  # Объём доминирует, VWAP подтверждает, тренд уточняет

            # Обработка неполных данных
            if len(strength_factors) != len(weights):
                weights = weights[:len(strength_factors)]
                total_weight = sum(weights)
                weights = [w/total_weight for w in weights] if total_weight > 0 else [1.0/len(strength_factors)] * len(strength_factors)

            signal_strength = sum(factor * weight for factor, weight in zip(strength_factors, weights))

            # Финальная нормализация
            final_strength = max(0.0, min(1.0, signal_strength))

            self.logger.debug(f"Сила сигнала {signal_type}: {final_strength:.3f} (факторы: {len(strength_factors)})")
            return final_strength

        except Exception as e:
            self.logger.error(f"Ошибка расчета силы сигнала: {e}")
            return 0.5
    
    def check_confluence_factors(self, market_data, indicators: Dict, signal_type: str) -> Tuple[int, List[str]]:
        """
        Проверка подтверждающих факторов для VWAP стратегии - УПРОЩЕНО до 3 ключевых факторов

        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала

        Returns:
            Tuple (количество_факторов, список_факторов)
        """
        try:
            confluence_count = 0
            factors = []
            last_idx = -1

            if not indicators:
                return 0, []

            # ФАКТОР 1: Объёмное подтверждение (ГЛАВНЫЙ)
            if indicators.get('volume_spike', pd.Series([False])).iloc[last_idx]:
                confluence_count += 1
                factors.append('volume_confirmation')

            # ФАКТОР 2: VWAP позиция (КРИТИЧЕСКИЙ)
            if signal_type in ['BUY', SignalType.BUY]:
                if indicators.get('price_above_vwap', pd.Series([False])).iloc[last_idx]:
                    confluence_count += 1
                    factors.append('vwap_position')
            else:  # SELL
                if indicators.get('price_below_vwap', pd.Series([False])).iloc[last_idx]:
                    confluence_count += 1
                    factors.append('vwap_position')

            # ФАКТОР 3: Трендовое подтверждение (ПОДТВЕРЖДАЮЩИЙ)
            if signal_type in ['BUY', SignalType.BUY]:
                if indicators.get('trend_bullish', pd.Series([False])).iloc[last_idx]:
                    confluence_count += 1
                    factors.append('trend_alignment')
            else:
                if indicators.get('trend_bearish', pd.Series([False])).iloc[last_idx]:
                    confluence_count += 1
                    factors.append('trend_alignment')
            if signal_type in ['BUY', SignalType.BUY]:
                if indicators.get('momentum_bullish', pd.Series([False])).iloc[last_idx]:
                    confluence_count += 1
                    factors.append(ConfluenceFactor.MOMENTUM_BULLISH.value)
            else:
                if indicators.get('momentum_bearish', pd.Series([False])).iloc[last_idx]:
                    confluence_count += 1
                    factors.append(ConfluenceFactor.MOMENTUM_BEARISH.value)
            
            # 8. Значительное отклонение от VWAP
            if indicators.get('vwap_significant_deviation', pd.Series([False])).iloc[last_idx]:
                confluence_count += 1
                factors.append(ConfluenceFactor.VWAP_DEVIATION.value)
            
            
            return confluence_count, factors
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки confluence факторов: {e}")
            return 0, []
    
    def _check_strategic_exit_conditions(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Стратегические условия выхода для VWAP стратегии
        
        Returns:
            Dict с сигналом выхода или None
        """
        try:
            if not self.is_in_position(state):
                return None
            
            df = self.get_primary_dataframe(market_data)
            if df is None:
                return None
            
            # Получаем индикаторы
            indicators = self.calculate_strategy_indicators(market_data)
            if not indicators:
                return None
            
            position_info = self.get_position_info(state)
            position_side = position_info.get('side')
            
            # Обратные VWAP сигналы
            if position_side in ['BUY', PositionSide.LONG]:
                # Выход из лонга если цена ушла значительно ниже VWAP с объемом
                price_below_vwap = indicators.get('price_below_vwap', pd.Series([False])).iloc[-1]
                volume_spike = indicators.get('volume_spike', pd.Series([False])).iloc[-1]
                trend_bearish = indicators.get('trend_bearish', pd.Series([False])).iloc[-1]
                
                if price_below_vwap and (volume_spike or trend_bearish):
                    return {
                        'signal': SignalType.EXIT_LONG,
                        'exit_reason': 'vwap_reversal',
                        'current_price': current_price,
                        'comment': 'Выход: цена ниже VWAP с подтверждением'
                    }
                    
            elif position_side in ['SELL', PositionSide.SHORT]:
                # Выход из шорта если цена ушла значительно выше VWAP с объемом
                price_above_vwap = indicators.get('price_above_vwap', pd.Series([False])).iloc[-1]
                volume_spike = indicators.get('volume_spike', pd.Series([False])).iloc[-1]
                trend_bullish = indicators.get('trend_bullish', pd.Series([False])).iloc[-1]
                
                if price_above_vwap and (volume_spike or trend_bullish):
                    return {
                        'signal': SignalType.EXIT_SHORT,
                        'exit_reason': 'vwap_reversal',
                        'current_price': current_price,
                        'comment': 'Выход: цена выше VWAP с подтверждением'
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка стратегических условий выхода: {e}")
            return None
    
    def execute(self, market_data, state=None, bybit_api=None, symbol='BTCUSDT') -> Optional[Dict]:
        """
        Основная логика выполнения VolumeSpike VWAP стратегии
        
        Args:
            market_data: Рыночные данные
            state: Состояние бота
            bybit_api: API для логирования
            symbol: Торговый инструмент
        
        Returns:
            Торговый сигнал или None
        """
        try:
            # 1. Предварительные проверки
            can_execute, reason = self.pre_execution_check(market_data, state)
            if not can_execute:
                self.logger.debug(f"Выполнение отменено: {reason}")
                return None
            
            # 2. Адаптация параметров для бокового рынка
            df = self.get_primary_dataframe(market_data)
            if df is not None and len(df) > 20:
                # Анализируем рыночные условия
                returns = df['close'].pct_change().dropna()
                volatility = returns.tail(10).std()
                
                # Если низкая волатильность (боковой рынок), снижаем требования
                if volatility < 0.02:  # Низкая волатильность
                    self.logger.info("🔄 Адаптация параметров для бокового рынка")
                    # Временно снижаем требования к объему
                    self._original_volume_mult = self.config.volume_multiplier
                    self.config.volume_multiplier = max(1.5, self._original_volume_mult * 0.5)  # Снижаем в 2 раза
                    self.logger.info(f"📊 Volume multiplier: {self._original_volume_mult} → {self.config.volume_multiplier}")
            
            # 2. Получаем основной DataFrame
            df = self.get_primary_dataframe(market_data)
            if df is None:
                self.logger.error("Не удалось получить данные для выполнения стратегии")
                return None
            
            # 3. Анализ рыночных условий
            market_analysis = self.analyze_current_market(df)
            condition = market_analysis.get('condition')
            if condition:
                # Логируем условия периодически
                if self._execution_count % 20 == 0:
                    self.log_market_analysis(market_analysis)
            
            # 4. Расчет индикаторов
            indicators = self.calculate_strategy_indicators(market_data)
            if not indicators:
                self.logger.error("Ошибка расчета индикаторов")
                return None
            
            # 5. Получаем текущую цену
            current_price = df['close'].iloc[-1]
            
            # 6. Проверка выхода из существующей позиции
            if self.is_in_position(state):
                exit_signal = self.should_exit_position(market_data, state, current_price)
                if exit_signal:
                    self.logger.info(f"🚪 Генерация сигнала выхода: {exit_signal.get('signal')}")
                    return exit_signal
                
                # Если в позиции, не генерируем новые сигналы входа
                return None
            
            # 7. Фильтры перед входом
            
            # Фильтр волатильности
            if self.config.volatility_filter:
                returns = df['close'].pct_change().dropna()
                current_volatility = returns.tail(10).std()
                if current_volatility > self.config.max_volatility_threshold:
                    self.logger.debug(f"Сигнал отклонен: высокая волатильность {current_volatility:.4f}")
                    return None
            
            # Фильтр минимального объема
            if 'volume' in df.columns and df['volume'].iloc[-1] < self.config.min_volume_for_signal:
                self.logger.debug(f"Сигнал отклонен: низкий объем {df['volume'].iloc[-1]}")
                return None
            
            # 8. Основная торговая логика
            
            # Отладочная информация об индикаторах
            if self._execution_count % 10 == 0:  # Логируем каждые 10 итераций
                volume_ratio = indicators.get('volume_ratio', pd.Series([0])).iloc[-1]
                volume_spike = indicators.get('volume_spike', pd.Series([False])).iloc[-1]
                price_above_vwap = indicators.get('price_above_vwap', pd.Series([False])).iloc[-1]
                momentum_bullish = indicators.get('momentum_bullish', pd.Series([False])).iloc[-1]
                trend_bullish = indicators.get('trend_bullish', pd.Series([False])).iloc[-1]
                
                self.logger.info(f"🔍 Отладка индикаторов: vol_ratio={volume_ratio:.2f}, vol_spike={volume_spike}, "
                               f"above_vwap={price_above_vwap}, momentum_bull={momentum_bullish}, trend_bull={trend_bullish}")
            
            # Проверяем готовые сетапы (включая боковые)
            long_setup = (
                indicators.get('bullish_setup', pd.Series([False])).iloc[-1] or
                indicators.get('range_bullish_setup', pd.Series([False])).iloc[-1]
            )
            short_setup = (
                indicators.get('bearish_setup', pd.Series([False])).iloc[-1] or
                indicators.get('range_bearish_setup', pd.Series([False])).iloc[-1]
            )
            
            # 9. Обработка лонг сигнала
            if long_setup:
                # Проверяем confluence факторы
                confluence_count, confluence_factors = self.check_confluence_factors(market_data, indicators, 'BUY')
                
                # Снижаем требования к confluence для бокового рынка
                required_confluence = max(1, self.config.confluence_required - 1)  # Минимум 1
                if confluence_count < required_confluence:
                    self.logger.debug(f"Лонг сигнал отклонен: недостаточно confluence ({confluence_count} < {required_confluence})")
                    return None
                
                # Рассчитываем силу сигнала
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'BUY')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Лонг сигнал отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                # Рассчитываем уровни входа
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_dynamic_levels(df, entry_price, 'BUY')
                
                # Проверяем R:R соотношение
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
                actual_rr = reward / risk if risk > 0 else 0
                
                if actual_rr < 1.0:
                    self.logger.debug(f"Лонг сигнал отклонен: плохой R:R {actual_rr:.2f}")
                    return None
                
                # Создаем стандартизированный сигнал
                signal = self.create_signal(
                    signal_type='BUY',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    indicators={
                        'volume_ratio': float(indicators['volume_ratio'].iloc[-1]) if 'volume_ratio' in indicators else 1.0,
                        'vwap': float(indicators['vwap'].iloc[-1]) if 'vwap' in indicators else entry_price,
                        'vwap_deviation': float(indicators['vwap_deviation'].iloc[-1]) if 'vwap_deviation' in indicators else 0.0,
                        'trend_strength': float(indicators['trend_strength']) if 'trend_strength' in indicators else 0.0,
                        'rsi': float(indicators['rsi'].iloc[-1]) if 'rsi' in indicators else 50.0,
                        'atr': float(indicators['atr']) if 'atr' in indicators else 0.0,
                        'volatility': float(df['close'].pct_change().tail(10).std())
                    },
                    confluence_factors=confluence_factors,
                    signal_strength=signal_strength,
                    symbol=symbol
                )
                
                # Логирование через API
                if bybit_api:
                    try:
                        bybit_api.log_strategy_signal(
                            strategy=signal['strategy'],
                            symbol=symbol,
                            signal=signal['signal'],
                            market_data=signal['indicators'],
                            indicators=signal['indicators'],
                            comment=signal['comment']
                        )
                    except Exception as e:
                        self.logger.error(f"Ошибка логирования API: {e}")
                
                self.log_signal_generation(signal, {'market_analysis': market_analysis})
                return signal
            
            # 10. Обработка шорт сигнала
            elif short_setup:
                # Аналогичная логика для шорта
                confluence_count, confluence_factors = self.check_confluence_factors(market_data, indicators, 'SELL')
                
                # Снижаем требования к confluence для бокового рынка
                required_confluence = max(1, self.config.confluence_required - 1)  # Минимум 1
                if confluence_count < required_confluence:
                    self.logger.debug(f"Шорт сигнал отклонен: недостаточно confluence ({confluence_count} < {required_confluence})")
                    return None
                
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'SELL')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Шорт сигнал отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_dynamic_levels(df, entry_price, 'SELL')
                
                # Проверяем R:R
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
                actual_rr = reward / risk if risk > 0 else 0
                
                if actual_rr < 1.0:
                    self.logger.debug(f"Шорт сигнал отклонен: плохой R:R {actual_rr:.2f}")
                    return None
                
                signal = self.create_signal(
                    signal_type='SELL',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    indicators={
                        'volume_ratio': float(indicators['volume_ratio'].iloc[-1]) if 'volume_ratio' in indicators else 1.0,
                        'vwap': float(indicators['vwap'].iloc[-1]) if 'vwap' in indicators else entry_price,
                        'vwap_deviation': float(indicators['vwap_deviation'].iloc[-1]) if 'vwap_deviation' in indicators else 0.0,
                        'trend_strength': float(indicators['trend_strength']) if 'trend_strength' in indicators else 0.0,
                        'rsi': float(indicators['rsi'].iloc[-1]) if 'rsi' in indicators else 50.0,
                        'atr': float(indicators['atr']) if 'atr' in indicators else 0.0,
                        'volatility': float(df['close'].pct_change().tail(10).std())
                    },
                    confluence_factors=confluence_factors,
                    signal_strength=signal_strength,
                    symbol=symbol
                )
                
                # Логирование
                if bybit_api:
                    try:
                        bybit_api.log_strategy_signal(
                            strategy=signal['strategy'],
                            symbol=symbol,
                            signal=signal['signal'],
                            market_data=signal['indicators'],
                            indicators=signal['indicators'],
                            comment=signal['comment']
                        )
                    except Exception as e:
                        self.logger.error(f"Ошибка логирования API: {e}")
                
                self.log_signal_generation(signal, {'market_analysis': market_analysis})
                return signal
            
            # 11. Нет торгового сигнала
            return None
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка выполнения VolumeVWAP стратегии: {e}", exc_info=True)
            return None
        
        finally:
            # Восстанавливаем оригинальные параметры
            if hasattr(self, '_original_volume_mult'):
                self.config.volume_multiplier = self._original_volume_mult
                delattr(self, '_original_volume_mult')
            
            # Пост-обработка
            signal_result = None  # Результат который возвращаем
            self.post_execution_tasks(signal_result, market_data, state)


# =========================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ И УТИЛИТЫ
# =========================================================================

def create_volume_vwap_strategy(config: Optional[VolumeVWAPConfig] = None, **kwargs) -> VolumeVWAPStrategy:
    """
    Фабричная функция для создания VolumeVWAP стратегии
    
    Args:
        config: Конфигурация стратегии (если None, используется по умолчанию)
        **kwargs: Дополнительные параметры для переопределения конфигурации
    
    Returns:
        Экземпляр VolumeVWAPStrategy
    """
    if config is None:
        config = VolumeVWAPConfig()
    
    # Переопределяем параметры если указаны
    if kwargs:
        config_dict = config.to_dict()
        config_dict.update(kwargs)
        config = VolumeVWAPConfig.from_dict(config_dict)
    
    return VolumeVWAPStrategy(config)


def create_conservative_volume_vwap() -> VolumeVWAPStrategy:
    """Создание консервативной версии VolumeVWAP стратегии"""
    from ..base.config import get_conservative_vwap_config
    config = get_conservative_vwap_config()
    return VolumeVWAPStrategy(config)


def create_aggressive_volume_vwap() -> VolumeVWAPStrategy:
    """Создание агрессивной версии VolumeVWAP стратегии"""
    config = VolumeVWAPConfig(
        volume_multiplier=2.0,  # Меньший порог для объема
        signal_strength_threshold=0.5,  # Более низкий порог
        risk_reward_ratio=2.0,  # Более высокий R:R
        confluence_required=1,  # Меньше подтверждений
        max_risk_per_trade_pct=1.5  # Больший риск
    )
    return VolumeVWAPStrategy(config)


# =========================================================================
# КОНСТАНТЫ И МЕТАДАННЫЕ
# =========================================================================

# Информация о стратегии
STRATEGY_INFO = {
    'name': 'VolumeSpike_VWAP',
    'version': '2.0.0',
    'description': 'Торговая стратегия на основе всплесков объема и VWAP анализа',
    'author': 'TradingBot Team',
    'category': 'Volume Analysis',
    'timeframes': ['1m', '5m', '15m'],
    'min_data_points': 100,
    'supported_assets': ['crypto', 'forex', 'stocks']
}

# Рекомендуемые настройки для разных рынков
MARKET_PRESETS = {
    'crypto_volatile': {
        'volume_multiplier': 4.0,
        'max_volatility_threshold': 0.08,
        'signal_strength_threshold': 0.7
    },
    'crypto_stable': {
        'volume_multiplier': 2.5,
        'max_volatility_threshold': 0.04,
        'signal_strength_threshold': 0.6
    },
    'forex': {
        'volume_multiplier': 1.8,
        'max_volatility_threshold': 0.02,
        'signal_strength_threshold': 0.65
    }
}