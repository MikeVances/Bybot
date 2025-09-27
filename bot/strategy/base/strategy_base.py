# bot/strategy/base/strategy_base.py
"""
Базовый абстрактный класс для всех торговых стратегий
Объединяет все миксины и предоставляет единый интерфейс
"""

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timezone, timedelta
import logging

from .config import BaseStrategyConfig
from .enums import MarketRegime, SignalType, PositionSide, ExitReason
from .mixins import (
    PositionManagerMixin, 
    StatisticsMixin, 
    PriceUtilsMixin,
    MarketAnalysisMixin,
    LoggingMixin
)
from ..utils.indicators import TechnicalIndicators
from ..utils.validators import DataValidator, ValidationLevel
from ..utils.levels import LevelsFinder
from ..utils.market_analysis import MarketRegimeAnalyzer


class BaseStrategy(ABC, PositionManagerMixin, StatisticsMixin, PriceUtilsMixin, 
                  MarketAnalysisMixin, LoggingMixin):
    """
    Базовый абстрактный класс для всех торговых стратегий
    
    Предоставляет:
    - Единый интерфейс для всех стратегий
    - Общую логику управления позициями
    - Систему валидации и безопасности
    - Статистику и мониторинг
    - Адаптацию под рыночные условия
    """
    
    def __init__(self, config: BaseStrategyConfig, strategy_name: str):
        """
        Инициализация базовой стратегии
        
        Args:
            config: Конфигурация стратегии
            strategy_name: Имя стратегии
        """
        # Инициализируем миксины
        StatisticsMixin.__init__(self)
        
        # Основные атрибуты
        self.config = config
        self.strategy_name = strategy_name
        self.strategy_version = config.strategy_version
        
        # Состояние стратегии
        self.current_market_regime = MarketRegime.NORMAL
        self.is_active = True
        self.last_analysis_time = None
        
        # Кэш для оптимизации производительности
        self._indicator_cache = {}
        self._cache_timestamp = None
        self._market_analysis_cache = {}
        
        # Настройка логирования
        self.logger = logging.getLogger(f'strategy.{strategy_name.lower()}')
        self.logger.setLevel(getattr(logging, config.log_level.value))
        
        # Счетчики для отладки
        self._execution_count = 0
        self._last_signal_time = None
        
        # Адаптивные параметры (копия базовых для модификации)
        self._adaptive_params = {}
        
        # Логируем инициализацию только в DEBUG режиме для уменьшения шума
        self.logger.debug(f"🚀 Инициализирована стратегия {strategy_name} v{self.strategy_version}")
    
    # =========================================================================
    # АБСТРАКТНЫЕ МЕТОДЫ (должны быть реализованы в дочерних классах)
    # =========================================================================
    
    @abstractmethod
    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        """
        Расчет специфичных для стратегии индикаторов
        
        Args:
            market_data: Рыночные данные (DataFrame или Dict[str, DataFrame])
        
        Returns:
            Dict с рассчитанными индикаторами
        """
        pass
    
    @abstractmethod
    def calculate_signal_strength(self, market_data, indicators: Dict, signal_type: str) -> float:
        """
        Расчет силы торгового сигнала
        
        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала ('BUY' или 'SELL')
        
        Returns:
            Сила сигнала от 0.0 до 1.0
        """
        pass
    
    @abstractmethod
    def check_confluence_factors(self, market_data, indicators: Dict, signal_type: str) -> Tuple[int, List[str]]:
        """
        Проверка подтверждающих факторов сигнала
        
        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала
        
        Returns:
            Tuple (количество_факторов, список_факторов)
        """
        pass
    
    @abstractmethod
    def execute(self, market_data, state=None, bybit_api=None, symbol='BTCUSDT') -> Optional[Dict]:
        """
        Основная логика выполнения стратегии
        
        Args:
            market_data: Рыночные данные
            state: Состояние бота
            bybit_api: API для логирования
            symbol: Торговый инструмент
        
        Returns:
            Торговый сигнал или None
        """
        pass
    
    # =========================================================================
    # ОБЩИЕ МЕТОДЫ БАЗОВОГО КЛАССА
    # =========================================================================
    
    def validate_market_data(self, market_data) -> Tuple[bool, str]:
        """
        Валидация входных рыночных данных
        
        Returns:
            Tuple (is_valid, error_message)
        """
        try:
            # Определяем тип данных
            max_staleness = timedelta(minutes=self.config.max_data_staleness_minutes)

            if isinstance(market_data, dict):
                # Мультитаймфрейм данные
                if not market_data:
                    return False, "Пустой словарь рыночных данных"
                
                # Валидируем каждый таймфрейм
                for tf, df in market_data.items():
                    if df is None or df.empty:
                        return False, f"Пустые данные для таймфрейма {tf}"
                    
                    result = DataValidator.validate_basic_data(df, self.config.validation_level)
                    if not result.is_valid:
                        return False, f"Ошибка валидации {tf}: {result.errors[0] if result.errors else 'Неизвестная ошибка'}"

                    safety = DataValidator.validate_market_data_safety(df, max_staleness=max_staleness)
                    if not safety.is_safe:
                        return False, f"Проблемы данных {tf}: {safety.reason}"
                    for warning in safety.warnings:
                        self.logger.warning(f"Предупреждение качества данных {tf}: {warning}")
            
            elif isinstance(market_data, pd.DataFrame):
                # Одиночный DataFrame
                result = DataValidator.validate_basic_data(market_data, self.config.validation_level)
                if not result.is_valid:
                    return False, f"Ошибка валидации данных: {result.errors[0] if result.errors else 'Неизвестная ошибка'}"

                safety = DataValidator.validate_market_data_safety(market_data, max_staleness=max_staleness)
                if not safety.is_safe:
                    return False, f"Проблемы данных: {safety.reason}"
                for warning in safety.warnings:
                    self.logger.warning(f"Предупреждение качества данных: {warning}")
            
            else:
                return False, f"Неподдерживаемый тип данных: {type(market_data)}"
            
            return True, "Данные валидны"
            
        except Exception as e:
            return False, f"Ошибка валидации: {str(e)}"
    
    def get_primary_dataframe(self, market_data) -> Optional[pd.DataFrame]:
        """
        Получение основного DataFrame для анализа
        
        Args:
            market_data: Рыночные данные
        
        Returns:
            Основной DataFrame или None
        """
        try:
            if isinstance(market_data, pd.DataFrame):
                return market_data
            elif isinstance(market_data, dict):
                # Ищем основной таймфрейм (5m, 1h, или первый доступный)
                priority_tfs = ['5m', '1h', '15m', '1m']
                
                for tf in priority_tfs:
                    if tf in market_data and market_data[tf] is not None:
                        return market_data[tf]
                
                # Если приоритетных нет, берем первый доступный
                for tf, df in market_data.items():
                    if df is not None and not df.empty:
                        return df
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка получения основного DataFrame: {e}")
            return None
    
    def calculate_base_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Расчет базовых индикаторов, общих для всех стратегий
        
        Args:
            df: DataFrame с OHLCV данными
        
        Returns:
            Dict с базовыми индикаторами
        """
        try:
            # Проверяем кэш
            cache_key = f"base_indicators_{len(df)}"
            current_time = datetime.now()
            
            if (cache_key in self._indicator_cache and 
                self._cache_timestamp and 
                (current_time - self._cache_timestamp).seconds < 60):  # Кэш на 1 минуту
                return self._indicator_cache[cache_key]
            
            indicators = {}
            
            # ATR - всегда нужен для SL/TP
            atr_result = TechnicalIndicators.calculate_atr_safe(df, self.config.atr_period)
            if atr_result.is_valid:
                indicators['atr'] = atr_result.value
            
            # RSI - для фильтрации перекупленности/перепроданности
            rsi_result = TechnicalIndicators.calculate_rsi(df, 14)
            if rsi_result.is_valid:
                indicators['rsi'] = rsi_result.value
            
            # Bollinger Bands - для определения волатильности
            bb_result = TechnicalIndicators.calculate_bollinger_bands(df, 20)
            if bb_result.is_valid:
                indicators['bb'] = bb_result.value
            
            # Volume SMA если есть объемы
            if 'volume' in df.columns:
                indicators['volume_sma'] = df['volume'].rolling(20, min_periods=1).mean()
                indicators['volume_ratio'] = df['volume'] / indicators['volume_sma']
            
            # Базовые SMA для трендового анализа
            indicators['sma_20'] = TechnicalIndicators.calculate_sma(df, 20).value
            indicators['sma_50'] = TechnicalIndicators.calculate_sma(df, 50).value
            
            # Кэшируем результат
            self._indicator_cache[cache_key] = indicators
            self._cache_timestamp = current_time
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета базовых индикаторов: {e}")
            return {}
    
    def calculate_dynamic_levels(self, df: pd.DataFrame, entry_price: float, side: str) -> Tuple[float, float]:
        """
        Расчет динамических уровней SL/TP с адаптацией под рыночный режим
        
        Args:
            df: DataFrame с данными
            entry_price: Цена входа
            side: Сторона сделки ('BUY' или 'SELL')
        
        Returns:
            Tuple (stop_loss, take_profit)
        """
        try:
            # Анализируем рыночный режим для адаптивной валидации
            if hasattr(self, 'analyze_current_market'):
                market_analysis = self.analyze_current_market(df)
                if market_analysis and 'condition' in market_analysis:
                    self.current_market_regime = market_analysis['condition'].regime
            
            # Получаем ATR
            atr_result = TechnicalIndicators.calculate_atr_safe(df, self.config.atr_period)
            atr = float(atr_result.last_value) if atr_result.is_valid and atr_result.last_value else None

            # Базовые множители
            sl_multiplier = self.config.stop_loss_atr_multiplier
            rr_ratio = self.config.risk_reward_ratio

            # Адаптация под рыночный режим
            if hasattr(self, 'current_market_regime'):
                if self.current_market_regime == MarketRegime.VOLATILE:
                    sl_multiplier *= 1.2  # Больше места для волатильности
                elif self.current_market_regime == MarketRegime.TRENDING:
                    sl_multiplier *= 0.8  # Меньше места в тренде
                    rr_ratio *= 1.2      # Больше прибыли в тренде
            
            # Адаптивное R:R на основе волатильности
            if self.config.adaptive_parameters:
                rr_ratio = self.calculate_adaptive_rr_ratio(df)
            
            # Минимальные и максимальные отступы для безопасности
            min_sl_distance = entry_price * 0.005  # 0.5% минимум
            max_sl_distance = entry_price * 0.03   # 3% максимум

            if not atr or atr <= 0:
                # Если ATR не рассчитан, используем запас 1% цены
                atr = entry_price * 0.01

            if side in ['BUY', PositionSide.LONG]:
                # Расчет SL с ограничениями
                raw_sl = entry_price - (atr * sl_multiplier)
                stop_loss = max(raw_sl, entry_price - max_sl_distance)
                stop_loss = min(stop_loss, entry_price - min_sl_distance)
                
                # Динамический TP на основе структуры рынка
                if self.config.dynamic_tp:
                    resistance_levels = LevelsFinder.find_swing_levels(df, lookback=20)
                    resistance = self._find_nearest_resistance(resistance_levels, entry_price, atr)
                    
                    if resistance:
                        take_profit = resistance
                    else:
                        # Fallback к стандартному расчету
                        sl_distance = entry_price - stop_loss
                        take_profit = entry_price + (sl_distance * rr_ratio)
                else:
                    sl_distance = entry_price - stop_loss
                    take_profit = entry_price + (sl_distance * rr_ratio)
                    
            else:  # SELL/SHORT
                raw_sl = entry_price + (atr * sl_multiplier)
                stop_loss = min(raw_sl, entry_price + max_sl_distance)
                stop_loss = max(stop_loss, entry_price + min_sl_distance)
                
                if self.config.dynamic_tp:
                    support_levels = LevelsFinder.find_swing_levels(df, lookback=20)
                    support = self._find_nearest_support(support_levels, entry_price, atr)
                    
                    if support:
                        take_profit = support
                    else:
                        sl_distance = stop_loss - entry_price
                        take_profit = entry_price - (sl_distance * rr_ratio)
                else:
                    sl_distance = stop_loss - entry_price
                    take_profit = entry_price - (sl_distance * rr_ratio)
            
            # Округляем цены
            stop_loss = self.round_price(stop_loss)
            take_profit = self.round_price(take_profit)
            
            # Валидация уровней
            is_valid, error = self.validate_price_levels(entry_price, stop_loss, take_profit, side)
            if not is_valid:
                self.logger.warning(f"Невалидные уровни: {error}")
                # Fallback к простому расчету
                if side in ['BUY', PositionSide.LONG]:
                    stop_loss = self.round_price(entry_price - (atr * 1.5))
                    take_profit = self.round_price(entry_price + (atr * 2.0))
                else:
                    stop_loss = self.round_price(entry_price + (atr * 1.5))
                    take_profit = self.round_price(entry_price - (atr * 2.0))
            
            return stop_loss, take_profit
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета динамических уровней: {e}")
            # Критический fallback
            if side in ['BUY', PositionSide.LONG]:
                return entry_price * 0.99, entry_price * 1.02  # 1% SL, 2% TP
            else:
                return entry_price * 1.01, entry_price * 0.98  # 1% SL, 2% TP
    
    def _find_nearest_resistance(self, levels: List, entry_price: float, atr: float) -> Optional[float]:
        """Поиск ближайшего уровня сопротивления"""
        try:
            suitable_levels = [
                level.price for level in levels 
                if (level.level_type.value in ['resistance', 'pivot'] and 
                    entry_price < level.price <= entry_price + (atr * 4))
            ]
            return min(suitable_levels) if suitable_levels else None
        except:
            return None
    
    def _find_nearest_support(self, levels: List, entry_price: float, atr: float) -> Optional[float]:
        """Поиск ближайшего уровня поддержки"""
        try:
            suitable_levels = [
                level.price for level in levels 
                if (level.level_type.value in ['support', 'pivot'] and 
                    entry_price > level.price >= entry_price - (atr * 4))
            ]
            return max(suitable_levels) if suitable_levels else None
        except:
            return None
    
    def should_exit_position(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Комплексная логика выхода из позиции
        
        Args:
            market_data: Рыночные данные
            state: Состояние бота
            current_price: Текущая цена
        
        Returns:
            Dict с сигналом выхода или None
        """
        try:
            # Базовая логика выхода (трейлинг стоп + время)
            df = self.get_primary_dataframe(market_data)
            if df is None:
                return None
            
            base_exit = self.should_exit_position_base(df, state, current_price)
            if base_exit:
                return base_exit
            
            # Стратегическая логика выхода (переопределяется в дочерних классах)
            strategic_exit = self._check_strategic_exit_conditions(market_data, state, current_price)
            if strategic_exit:
                return strategic_exit
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки выхода из позиции: {e}")
            return None
    
    def _check_strategic_exit_conditions(self, market_data, state, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Стратегические условия выхода (переопределяется в дочерних классах)
        """
        return None
    
    def create_signal(self, signal_type: str, entry_price: float, stop_loss: float, 
                     take_profit: float, indicators: Dict, confluence_factors: List[str],
                     signal_strength: float, symbol: str = 'BTCUSDT', 
                     additional_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Создание стандартизированного торгового сигнала
        
        Args:
            signal_type: Тип сигнала ('BUY' или 'SELL')
            entry_price: Цена входа
            stop_loss: Стоп-лосс
            take_profit: Тейк-профит
            indicators: Ключевые индикаторы
            confluence_factors: Подтверждающие факторы
            signal_strength: Сила сигнала
            symbol: Торговый инструмент
            additional_data: Дополнительные данные
        
        Returns:
            Стандартизированный сигнал
        """
        try:
            # Расчет R:R соотношения
            if signal_type in ['BUY', SignalType.BUY]:
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
            else:
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
            
            actual_rr = reward / risk if risk > 0 else 0
            
            # Базовая структура сигнала
            signal = {
                'symbol': symbol,
                'signal': signal_type,
                'entry_price': self.round_price(entry_price),
                'stop_loss': self.round_price(stop_loss),
                'take_profit': self.round_price(take_profit),
                'signal_strength': min(max(signal_strength, 0.0), 1.0),
                'risk_reward_ratio': actual_rr,
                'confluence_count': len(confluence_factors),
                'confluence_factors': confluence_factors,
                'market_regime': self.current_market_regime.value,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                
                # Метаданные стратегии
                'strategy': self.strategy_name,
                'strategy_version': self.strategy_version,
                
                # Ключевые индикаторы
                'indicators': {k: float(v) if isinstance(v, (int, float, np.number)) else v 
                             for k, v in indicators.items()},
                
                # Параметры стратегии
                'params': {
                    'stop_loss_atr_multiplier': self.config.stop_loss_atr_multiplier,
                    'risk_reward_ratio': self.config.risk_reward_ratio,
                    'signal_strength_threshold': self.config.signal_strength_threshold,
                    'confluence_required': self.config.confluence_required,
                    'adaptive_parameters': self.config.adaptive_parameters
                }
            }
            
            # Добавляем дополнительные данные
            if additional_data:
                signal.update(additional_data)
            
            # Генерируем комментарий
            signal['comment'] = self._generate_signal_comment(signal_type, signal_strength, actual_rr, len(confluence_factors))
            
            # Обновляем статистику
            self.signals_generated += 1
            self._last_signal_time = datetime.now(timezone.utc)
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Ошибка создания сигнала: {e}")
            return {}
    
    def _generate_signal_comment(self, signal_type: str, strength: float, rr: float, confluence: int) -> str:
        """Генерация комментария к сигналу"""
        direction = "Лонг" if signal_type in ['BUY', SignalType.BUY] else "Шорт"
        return f"{direction} вход (сила: {strength:.2f}, R:R: {rr:.2f}, confluence: {confluence})"
    
    def pre_execution_check(self, market_data, state) -> Tuple[bool, str]:
        """
        Предварительная проверка перед выполнением стратегии
        
        Returns:
            Tuple (can_execute, reason)
        """
        try:
            # 1. Проверка активности стратегии
            if not self.is_active:
                return False, "Стратегия неактивна"
            
            # 2. Валидация данных
            is_valid, error = self.validate_market_data(market_data)
            if not is_valid:
                return False, f"Невалидные данные: {error}"
            
            # 3. Проверка минимального интервала между сигналами
            if self._last_signal_time:
                time_since_last = datetime.now(timezone.utc) - self._last_signal_time
                min_interval = getattr(self.config, 'min_signal_interval_minutes', 1)
                if time_since_last.total_seconds() < min_interval * 60:
                    return False, f"Слишком частые сигналы (< {min_interval}м)"
            
            # 4. Проверка лимитов производительности
            if hasattr(self.config, 'max_daily_signals'):
                session_stats = self.get_session_summary()
                if session_stats.get('signals_generated', 0) >= self.config.max_daily_signals:
                    return False, "Достигнут дневной лимит сигналов"
            
            return True, "Готов к выполнению"
            
        except Exception as e:
            return False, f"Ошибка предварительной проверки: {e}"
    
    def post_execution_tasks(self, signal_result: Optional[Dict], market_data, state):
        """
        Задачи после выполнения стратегии
        
        Args:
            signal_result: Результат выполнения стратегии
            market_data: Рыночные данные
            state: Состояние бота
        """
        try:
            # Обновляем счетчик выполнений
            self._execution_count += 1
            
            # Обновляем анализ рынка периодически
            if self._execution_count % 10 == 0:  # Каждые 10 выполнений
                df = self.get_primary_dataframe(market_data)
                if df is not None:
                    market_analysis = self.analyze_current_market(df)
                    self._market_analysis_cache = market_analysis
                    
                    # Адаптируем параметры если включена адаптация
                    if self.config.adaptive_parameters:
                        condition = market_analysis.get('condition')
                        if condition:
                            self._adaptive_params = self.adapt_strategy_parameters(condition)
            
            # Логируем результат если был сигнал
            if signal_result:
                self.log_signal_generation(signal_result, {'execution_count': self._execution_count})
            
            # Очищаем старый кэш
            if len(self._indicator_cache) > 10:  # Ограничиваем размер кэша
                oldest_keys = list(self._indicator_cache.keys())[:5]
                for key in oldest_keys:
                    del self._indicator_cache[key]
                    
        except Exception as e:
            self.logger.error(f"Ошибка пост-обработки: {e}")
    
    # =========================================================================
    # ИНФОРМАЦИОННЫЕ МЕТОДЫ
    # =========================================================================
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Получение полной информации о стратегии"""
        return {
            'name': self.strategy_name,
            'version': self.strategy_version,
            'is_active': self.is_active,
            'current_regime': self.current_market_regime.value,
            'execution_count': self._execution_count,
            'last_signal_time': self._last_signal_time.isoformat() if self._last_signal_time else None,
            'config_summary': {
                'risk_reward_ratio': self.config.risk_reward_ratio,
                'stop_loss_atr_multiplier': self.config.stop_loss_atr_multiplier,
                'signal_strength_threshold': self.config.signal_strength_threshold,
                'adaptive_parameters': self.config.adaptive_parameters,
                'confluence_required': self.config.confluence_required
            },
            'performance': self.get_performance_metrics(),
            'adaptive_params': self._adaptive_params
        }
    
    def get_strategy_statistics(self) -> Dict[str, Any]:
        """Получение статистики стратегии (для обратной совместимости)"""
        base_stats = {
            'strategy_name': self.strategy_name,
            'version': self.strategy_version,
            'signals_generated': self.signals_generated,
            'signals_executed': self.signals_executed,
            'last_signal_time': self._last_signal_time.isoformat() if self._last_signal_time else None,
            'current_market_regime': self.current_market_regime.value,
            'execution_count': self._execution_count,
            'is_active': self.is_active
        }
        
        # Добавляем метрики производительности
        performance = self.get_performance_metrics()
        base_stats.update(performance)
        
        return base_stats
    
    def get_current_status(self) -> str:
        """Получение краткого статуса стратегии"""
        try:
            if not self.is_active:
                return "❌ Неактивна"
            
            performance = self.get_performance_metrics()
            total_trades = performance.get('total_trades', 0)
            win_rate = performance.get('win_rate', 0)
            
            if total_trades == 0:
                return f"🟢 Активна | Режим: {self.current_market_regime.value} | Сигналов: {self.signals_generated}"
            else:
                return f"🟢 Активна | Сделок: {total_trades} | Винрейт: {win_rate:.1f}% | Режим: {self.current_market_regime.value}"
                
        except Exception as e:
            return f"❓ Ошибка статуса: {e}"
    
    # =========================================================================
    # УПРАВЛЕНИЕ СТРАТЕГИЕЙ
    # =========================================================================
    
    def activate(self):
        """Активация стратегии"""
        self.is_active = True
        self.logger.info(f"✅ Стратегия {self.strategy_name} активирована")
    
    def deactivate(self):
        """Деактивация стратегии"""
        self.is_active = False
        self.logger.info(f"⏸️ Стратегия {self.strategy_name} деактивирована")
    
    def update_config(self, new_config: BaseStrategyConfig):
        """
        Обновление конфигурации стратегии
        
        Args:
            new_config: Новая конфигурация
        """
        try:
            old_config = self.config
            self.config = new_config
            
            # Обновляем логирование если изменился уровень
            if old_config.log_level != new_config.log_level:
                self.logger.setLevel(getattr(logging, new_config.log_level.value))
            
            self.logger.info(f"🔄 Конфигурация стратегии {self.strategy_name} обновлена")
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления конфигурации: {e}")
    
    def reset_state(self):
        """Сброс состояния стратегии"""
        try:
            # Сбрасываем статистику
            self.reset_statistics()
            
            # Очищаем кэши
            self._indicator_cache.clear()
            self._market_analysis_cache.clear()
            self._adaptive_params.clear()
            
            # Сбрасываем счетчики
            self._execution_count = 0
            self._last_signal_time = None
            self._cache_timestamp = None
            
            # Возвращаем к нормальному режиму
            self.current_market_regime = MarketRegime.NORMAL
            
            self.logger.info(f"🔄 Состояние стратегии {self.strategy_name} сброшено")
            
        except Exception as e:
            self.logger.error(f"Ошибка сброса состояния: {e}")
    
    # =========================================================================
    # МАГИЧЕСКИЕ МЕТОДЫ
    # =========================================================================
    
    def __str__(self) -> str:
        """Строковое представление стратегии"""
        status = "🟢" if self.is_active else "🔴"
        return f"{status} {self.strategy_name} v{self.strategy_version} | Сигналов: {self.signals_generated} | Режим: {self.current_market_regime.value}"
    
    def __repr__(self) -> str:
        """Подробное представление для отладки"""
        return (f"BaseStrategy(name='{self.strategy_name}', version='{self.strategy_version}', "
                f"active={self.is_active}, signals={self.signals_generated}, "
                f"regime={self.current_market_regime.value})")
    
    def __enter__(self):
        """Поддержка контекстного менеджера"""
        self.activate()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        if exc_type:
            self.logger.error(f"Ошибка в стратегии: {exc_val}")
        self.deactivate()


# =========================================================================
# УТИЛИТНЫЕ ФУНКЦИИ
# =========================================================================

def create_strategy_instance(strategy_class, config: BaseStrategyConfig, **kwargs):
    """
    Фабричная функция для создания экземпляра стратегии
    
    Args:
        strategy_class: Класс стратегии
        config: Конфигурация
        **kwargs: Дополнительные аргументы
    
    Returns:
        Экземпляр стратегии
    """
    try:
        if not issubclass(strategy_class, BaseStrategy):
            raise ValueError(f"Класс {strategy_class.__name__} должен наследоваться от BaseStrategy")
        
        instance = strategy_class(config, **kwargs)
        
        # Дополнительная инициализация если нужна
        if hasattr(instance, 'post_init'):
            instance.post_init()
        
        return instance
        
    except Exception as e:
        logger.error(f"Ошибка создания экземпляра стратегии: {e}")
        raise


def validate_strategy_implementation(strategy_class) -> Tuple[bool, List[str]]:
    """
    Валидация правильности реализации стратегии
    
    Args:
        strategy_class: Класс стратегии для проверки
    
    Returns:
        Tuple (is_valid, errors)
    """
    errors = []
    
    try:
        # Проверка наследования
        if not issubclass(strategy_class, BaseStrategy):
            errors.append("Класс должен наследоваться от BaseStrategy")
        
        # Проверка реализации абстрактных методов
        required_methods = [
            'calculate_strategy_indicators',
            'calculate_signal_strength', 
            'check_confluence_factors',
            'execute'
        ]
        
        for method_name in required_methods:
            if not hasattr(strategy_class, method_name):
                errors.append(f"Отсутствует метод {method_name}")
            elif method_name in strategy_class.__dict__ and getattr(strategy_class.__dict__[method_name], '__isabstractmethod__', False):
                errors.append(f"Метод {method_name} не реализован")
        
        # Проверка конструктора
        if not hasattr(strategy_class, '__init__'):
            errors.append("Отсутствует конструктор __init__")
        
        return len(errors) == 0, errors
        
    except Exception as e:
        errors.append(f"Ошибка валидации: {e}")
        return False, errors


# =========================================================================
# КОНСТАНТЫ
# =========================================================================

# Версия базового класса
BASE_STRATEGY_VERSION = "2.0.0"

# Минимальные требования к данным
MIN_DATA_REQUIREMENTS = {
    'min_bars': 50,
    'required_columns': ['open', 'high', 'low', 'close'],
    'optional_columns': ['volume']
}

# Настройки производительности
PERFORMANCE_SETTINGS = {
    'cache_timeout_seconds': 60,
    'max_cache_size': 10,
    'market_analysis_interval': 10,  # Каждые 10 выполнений
    'max_performance_history': 1000
}
