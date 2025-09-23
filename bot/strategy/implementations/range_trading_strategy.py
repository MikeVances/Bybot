# bot/strategy/implementations/range_trading_strategy.py
"""
Range Trading Strategy - стратегия для бокового рынка
Специально адаптирована для частых сделок с минимальным профитом
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


class RangeTradingStrategy(BaseStrategy):
    """
    Range Trading Strategy v1.0
    
    Специальная стратегия для бокового рынка:
    - Частые сделки с минимальным профитом
    - Низкие требования к объему
    - Фокус на краткосрочных движениях
    - Адаптивные SL/TP для диапазона
    """
    
    def __init__(self, config: VolumeVWAPConfig):
        """
        Инициализация Range Trading стратегии
        
        Args:
            config: Конфигурация стратегии
        """
        super().__init__(config, "RangeTrading_v1")
        
        # Специфичная конфигурация для диапазона
        self.config: VolumeVWAPConfig = config
        
        # Адаптируем параметры для бокового рынка
        self.config.volume_multiplier = 1.2  # Низкий порог объема
        self.config.signal_strength_threshold = 0.3  # Низкий порог силы сигнала
        self.config.confluence_required = 1  # Минимум подтверждений
        self.config.risk_reward_ratio = 1.2  # Низкий R:R для частых сделок
        self.config.min_risk_reward_ratio = 0.8  # Снижаем минимальное R:R для диапазона
        
        self.logger.info(f"🎯 Range Trading стратегия инициализирована")
        self.logger.info(f"📊 Параметры: volume_mult={self.config.volume_multiplier}, "
                        f"signal_strength={self.config.signal_strength_threshold}")
    
    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        """
        Расчет индикаторов для Range Trading стратегии
        
        Args:
            market_data: Рыночные данные
        
        Returns:
            Dict с рассчитанными индикаторами
        """
        try:
            df = self.get_primary_dataframe(market_data)
            if df is None:
                self.logger.error("Не удалось получить данные для расчета индикаторов")
                return {}
            
            indicators = {}
            
            # 1. Базовые индикаторы
            base_indicators = self.calculate_base_indicators(df)
            indicators.update(base_indicators)
            
            # 2. Объемные индикаторы (сниженные требования)
            if 'volume' in df.columns:
                vol_sma_period = 10  # Короткий период
                indicators['vol_sma'] = df['volume'].rolling(vol_sma_period, min_periods=1).mean()
                indicators['volume_ratio'] = df['volume'] / indicators['vol_sma']
                indicators['volume_spike'] = indicators['volume_ratio'] > self.config.volume_multiplier
                
                # Volume momentum
                indicators['volume_momentum'] = df['volume'].pct_change(3)
                indicators['volume_momentum_positive'] = indicators['volume_momentum'] > 0
            else:
                indicators.update({
                    'vol_sma': pd.Series([1000] * len(df), index=df.index),
                    'volume_ratio': pd.Series([1.0] * len(df), index=df.index),
                    'volume_spike': pd.Series([True] * len(df), index=df.index),  # Всегда True для диапазона
                    'volume_momentum': pd.Series([0] * len(df), index=df.index),
                    'volume_momentum_positive': pd.Series([True] * len(df), index=df.index)
                })
            
            # 3. VWAP расчеты
            vwap_result = TechnicalIndicators.calculate_vwap(df, 20)  # Короткий период
            if vwap_result.is_valid:
                indicators['vwap'] = vwap_result.value
                indicators['vwap_deviation'] = abs(df['close'] - indicators['vwap']) / df['close']
                indicators['price_above_vwap'] = df['close'] > indicators['vwap']
                indicators['price_below_vwap'] = df['close'] < indicators['vwap']
            else:
                indicators.update({
                    'vwap': df['close'],
                    'vwap_deviation': pd.Series([0] * len(df), index=df.index),
                    'price_above_vwap': pd.Series([True] * len(df), index=df.index),
                    'price_below_vwap': pd.Series([False] * len(df), index=df.index)
                })
            
            # 4. Краткосрочные тренды (для диапазона)
            short_trend_period = 10
            indicators['sma_short'] = df['close'].rolling(short_trend_period, min_periods=1).mean()
            indicators['trend_slope_short'] = indicators['sma_short'].diff(3)
            indicators['trend_bullish_short'] = indicators['trend_slope_short'] > 0
            indicators['trend_bearish_short'] = indicators['trend_slope_short'] < 0
            
            # 5. Моментум индикаторы
            indicators['price_momentum'] = df['close'].pct_change(3)
            indicators['momentum_bullish'] = indicators['price_momentum'] > 0.001  # Низкий порог
            indicators['momentum_bearish'] = indicators['price_momentum'] < -0.001
            
            # 6. RSI для диапазона
            rsi_period = 14
            rsi_result = TechnicalIndicators.calculate_rsi(df, rsi_period)
            if rsi_result.is_valid:
                indicators['rsi'] = rsi_result.value
                indicators['rsi_oversold'] = indicators['rsi'] < 30
                indicators['rsi_overbought'] = indicators['rsi'] > 70
                indicators['rsi_neutral'] = (indicators['rsi'] >= 30) & (indicators['rsi'] <= 70)
            else:
                indicators.update({
                    'rsi': pd.Series([50] * len(df), index=df.index),
                    'rsi_oversold': pd.Series([False] * len(df), index=df.index),
                    'rsi_overbought': pd.Series([False] * len(df), index=df.index),
                    'rsi_neutral': pd.Series([True] * len(df), index=df.index)
                })
            
            # 7. Bollinger Bands для диапазона
            bb_period = 20
            bb_std = 2
            bb_result = TechnicalIndicators.calculate_bollinger_bands(df, bb_period, bb_std)
            if bb_result.is_valid:
                indicators['bb_upper'] = bb_result.value['upper']
                indicators['bb_lower'] = bb_result.value['lower']
                indicators['bb_middle'] = bb_result.value['middle']
                indicators['price_near_bb_upper'] = df['close'] > indicators['bb_upper'] * 0.98
                indicators['price_near_bb_lower'] = df['close'] < indicators['bb_lower'] * 1.02
            else:
                indicators.update({
                    'bb_upper': df['close'] * 1.02,
                    'bb_lower': df['close'] * 0.98,
                    'bb_middle': df['close'],
                    'price_near_bb_upper': pd.Series([False] * len(df), index=df.index),
                    'price_near_bb_lower': pd.Series([False] * len(df), index=df.index)
                })
            
            # 8. Комбинированные сигналы для диапазона
            # Лонг сигналы (отскок от нижней границы)
            indicators['range_bullish_setup'] = (
                (indicators['price_near_bb_lower'] | indicators['rsi_oversold']) &
                indicators['momentum_bullish'] &
                indicators['volume_momentum_positive']
            )
            
            # Шорт сигналы (отскок от верхней границы)
            indicators['range_bearish_setup'] = (
                (indicators['price_near_bb_upper'] | indicators['rsi_overbought']) &
                indicators['momentum_bearish'] &
                indicators['volume_momentum_positive']
            )
            
            # Дополнительные сигналы для диапазона
            indicators['vwap_bullish_setup'] = (
                indicators['price_below_vwap'] &
                indicators['momentum_bullish'] &
                indicators['volume_spike']
            )
            
            indicators['vwap_bearish_setup'] = (
                indicators['price_above_vwap'] &
                indicators['momentum_bearish'] &
                indicators['volume_spike']
            )
            
            self.logger.debug(f"Рассчитано {len(indicators)} индикаторов для Range Trading стратегии")
            return indicators
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета индикаторов Range Trading стратегии: {e}")
            return {}
    
    def calculate_signal_strength(self, market_data, indicators: Dict, signal_type: str) -> float:
        """
        Расчет силы сигнала для Range Trading стратегии
        
        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала ('BUY' или 'SELL')
        
        Returns:
            Сила сигнала (0.0 - 1.0)
        """
        try:
            strength = 0.0
            
            # Базовые факторы
            if signal_type == 'BUY':
                # RSI oversold
                if indicators.get('rsi_oversold', pd.Series([False])).iloc[-1]:
                    strength += 0.3
                
                # Momentum positive
                if indicators.get('momentum_bullish', pd.Series([False])).iloc[-1]:
                    strength += 0.2
                
                # Volume momentum
                if indicators.get('volume_momentum_positive', pd.Series([False])).iloc[-1]:
                    strength += 0.2
                
                # Price near BB lower
                if indicators.get('price_near_bb_lower', pd.Series([False])).iloc[-1]:
                    strength += 0.3
                
            elif signal_type == 'SELL':
                # RSI overbought
                if indicators.get('rsi_overbought', pd.Series([False])).iloc[-1]:
                    strength += 0.3
                
                # Momentum negative
                if indicators.get('momentum_bearish', pd.Series([False])).iloc[-1]:
                    strength += 0.2
                
                # Volume momentum
                if indicators.get('volume_momentum_positive', pd.Series([False])).iloc[-1]:
                    strength += 0.2
                
                # Price near BB upper
                if indicators.get('price_near_bb_upper', pd.Series([False])).iloc[-1]:
                    strength += 0.3
            
            return min(1.0, strength)
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета силы сигнала: {e}")
            return 0.0
    
    def check_confluence_factors(self, market_data, indicators: Dict, signal_type: str) -> Tuple[int, List[str]]:
        """
        Проверка confluence факторов для Range Trading стратегии
        
        Args:
            market_data: Рыночные данные
            indicators: Рассчитанные индикаторы
            signal_type: Тип сигнала
        
        Returns:
            Tuple (количество факторов, список факторов)
        """
        confluence_factors = []
        
        try:
            if signal_type == 'BUY':
                # RSI oversold
                if indicators.get('rsi_oversold', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("RSI oversold")
                
                # Momentum positive
                if indicators.get('momentum_bullish', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("Positive momentum")
                
                # Volume momentum
                if indicators.get('volume_momentum_positive', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("Volume momentum")
                
                # Price near BB lower
                if indicators.get('price_near_bb_lower', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("Price near BB lower")
                
                # VWAP support
                if indicators.get('price_below_vwap', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("VWAP support")
                
            elif signal_type == 'SELL':
                # RSI overbought
                if indicators.get('rsi_overbought', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("RSI overbought")
                
                # Momentum negative
                if indicators.get('momentum_bearish', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("Negative momentum")
                
                # Volume momentum
                if indicators.get('volume_momentum_positive', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("Volume momentum")
                
                # Price near BB upper
                if indicators.get('price_near_bb_upper', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("Price near BB upper")
                
                # VWAP resistance
                if indicators.get('price_above_vwap', pd.Series([False])).iloc[-1]:
                    confluence_factors.append("VWAP resistance")
            
            return len(confluence_factors), confluence_factors
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки confluence факторов: {e}")
            return 0, []
    
    def execute(self, market_data, state=None, bybit_api=None, symbol='BTCUSDT') -> Optional[Dict]:
        """
        Основная логика выполнения Range Trading стратегии
        
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
            
            # 2. Получаем основной DataFrame
            df = self.get_primary_dataframe(market_data)
            if df is None:
                self.logger.error("Не удалось получить данные для выполнения стратегии")
                return None
            
            # 3. Анализ рыночных условий
            market_analysis = self.analyze_current_market(df)
            condition = market_analysis.get('condition')
            if condition:
                if self._execution_count % 10 == 0:
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
                return None
            
            # 7. Отладочная информация
            if self._execution_count % 5 == 0:  # Логируем каждые 5 итераций
                volume_ratio = indicators.get('volume_ratio', pd.Series([0])).iloc[-1]
                rsi = indicators.get('rsi', pd.Series([50])).iloc[-1]
                momentum = indicators.get('price_momentum', pd.Series([0])).iloc[-1]
                
                self.logger.info(f"🔍 Range Trading отладка: vol_ratio={volume_ratio:.2f}, "
                               f"rsi={rsi:.1f}, momentum={momentum:.4f}")
            
            # 8. Проверяем сетапы для диапазона
            long_setup = (
                indicators.get('range_bullish_setup', pd.Series([False])).iloc[-1] or
                indicators.get('vwap_bullish_setup', pd.Series([False])).iloc[-1]
            )
            short_setup = (
                indicators.get('range_bearish_setup', pd.Series([False])).iloc[-1] or
                indicators.get('vwap_bearish_setup', pd.Series([False])).iloc[-1]
            )
            
            # 9. Обработка лонг сигнала
            if long_setup:
                confluence_count, confluence_factors = self.check_confluence_factors(market_data, indicators, 'BUY')
                
                if confluence_count < 1:  # Минимум 1 фактор
                    self.logger.debug(f"Лонг сигнал отклонен: недостаточно confluence ({confluence_count})")
                    return None
                
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'BUY')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Лонг сигнал отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                # Рассчитываем уровни входа (узкие для диапазона)
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_range_levels(df, entry_price, 'BUY')
                
                # Проверяем R:R соотношение
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
                actual_rr = reward / risk if risk > 0 else 0
                
                min_rr = getattr(self.config, 'min_risk_reward_ratio', 1.0)
                if actual_rr < min_rr:
                    self.logger.debug(f"Лонг сигнал отклонен: плохой R:R {actual_rr:.2f} < {min_rr}")
                    return None
                
                # Создаем сигнал
                signal = self.create_signal(
                    signal_type='BUY',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    indicators={
                        'volume_ratio': float(indicators['volume_ratio'].iloc[-1]) if 'volume_ratio' in indicators else 1.0,
                        'rsi': float(indicators['rsi'].iloc[-1]) if 'rsi' in indicators else 50.0,
                        'momentum': float(indicators['price_momentum'].iloc[-1]) if 'price_momentum' in indicators else 0.0,
                        'vwap': float(indicators['vwap'].iloc[-1]) if 'vwap' in indicators else entry_price,
                        'bb_lower': float(indicators['bb_lower'].iloc[-1]) if 'bb_lower' in indicators else entry_price * 0.98,
                        'bb_upper': float(indicators['bb_upper'].iloc[-1]) if 'bb_upper' in indicators else entry_price * 1.02
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
                            comment=f"Range Trading: {', '.join(confluence_factors)}"
                        )
                    except Exception as e:
                        self.logger.error(f"Ошибка логирования API: {e}")
                
                self.log_signal_generation(signal, {'market_analysis': market_analysis})
                return signal
            
            # 10. Обработка шорт сигнала
            elif short_setup:
                confluence_count, confluence_factors = self.check_confluence_factors(market_data, indicators, 'SELL')
                
                if confluence_count < 1:
                    self.logger.debug(f"Шорт сигнал отклонен: недостаточно confluence ({confluence_count})")
                    return None
                
                signal_strength = self.calculate_signal_strength(market_data, indicators, 'SELL')
                
                if signal_strength < self.config.signal_strength_threshold:
                    self.logger.debug(f"Шорт сигнал отклонен: слабая сила {signal_strength:.3f}")
                    return None
                
                entry_price = self.round_price(current_price)
                stop_loss, take_profit = self.calculate_range_levels(df, entry_price, 'SELL')
                
                # Проверяем R:R
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
                actual_rr = reward / risk if risk > 0 else 0
                
                min_rr = getattr(self.config, 'min_risk_reward_ratio', 1.0)
                if actual_rr < min_rr:
                    self.logger.debug(f"Шорт сигнал отклонен: плохой R:R {actual_rr:.2f} < {min_rr}")
                    return None
                
                signal = self.create_signal(
                    signal_type='SELL',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    indicators={
                        'volume_ratio': float(indicators['volume_ratio'].iloc[-1]) if 'volume_ratio' in indicators else 1.0,
                        'rsi': float(indicators['rsi'].iloc[-1]) if 'rsi' in indicators else 50.0,
                        'momentum': float(indicators['price_momentum'].iloc[-1]) if 'price_momentum' in indicators else 0.0,
                        'vwap': float(indicators['vwap'].iloc[-1]) if 'vwap' in indicators else entry_price,
                        'bb_lower': float(indicators['bb_lower'].iloc[-1]) if 'bb_lower' in indicators else entry_price * 0.98,
                        'bb_upper': float(indicators['bb_upper'].iloc[-1]) if 'bb_upper' in indicators else entry_price * 1.02
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
                            comment=f"Range Trading: {', '.join(confluence_factors)}"
                        )
                    except Exception as e:
                        self.logger.error(f"Ошибка логирования API: {e}")
                
                self.log_signal_generation(signal, {'market_analysis': market_analysis})
                return signal
            
            # 11. Нет торгового сигнала
            return None
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка выполнения Range Trading стратегии: {e}", exc_info=True)
            return None
        
        finally:
            signal_result = None
            self.post_execution_tasks(signal_result, market_data, state)
    
    def calculate_range_levels(self, df: pd.DataFrame, entry_price: float, signal_type: str) -> Tuple[float, float]:
        """
        Расчет уровней SL/TP для диапазонной торговли
        
        Args:
            df: DataFrame с данными
            entry_price: Цена входа
            signal_type: Тип сигнала
        
        Returns:
            Tuple (stop_loss, take_profit)
        """
        try:
            # Используем ATR для расчета уровней
            atr_period = 14
            atr_result = TechnicalIndicators.calculate_atr_safe(df, atr_period)
            atr = atr_result.last_value if atr_result and atr_result.is_valid else None
            
            if not atr or atr <= 0:
                atr = entry_price * 0.01  # 1% от цены
            
            # Узкие уровни для диапазона
            if signal_type == 'BUY':
                stop_loss = entry_price - (atr * 1.5)  # 1.5 ATR ниже
                take_profit = entry_price + (atr * 2.0)  # 2.0 ATR выше
            else:  # SELL
                stop_loss = entry_price + (atr * 1.5)  # 1.5 ATR выше
                take_profit = entry_price - (atr * 2.0)  # 2.0 ATR ниже
            
            return self.round_price(stop_loss), self.round_price(take_profit)
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета уровней диапазона: {e}")
            # Fallback уровни
            if signal_type == 'BUY':
                return entry_price * 0.985, entry_price * 1.015  # 1.5% диапазон
            else:
                return entry_price * 1.015, entry_price * 0.985


# =========================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =========================================================================

def create_range_trading_strategy() -> RangeTradingStrategy:
    """Создание Range Trading стратегии"""
    config = VolumeVWAPConfig(
        volume_multiplier=1.2,
        signal_strength_threshold=0.3,
        confluence_required=1,
        risk_reward_ratio=1.2,
        max_risk_per_trade_pct=0.5,  # Низкий риск для частых сделок
        min_volume_for_signal=100  # Низкий объем
    )
    return RangeTradingStrategy(config)


# =========================================================================
# КОНСТАНТЫ И МЕТАДАННЫЕ
# =========================================================================

STRATEGY_INFO = {
    'name': 'Range_Trading',
    'version': '1.0.0',
    'description': 'Стратегия для бокового рынка с частыми сделками и минимальным профитом',
    'author': 'TradingBot Team',
    'category': 'Range Trading',
    'timeframes': ['1m', '5m', '15m'],
    'min_data_points': 50,
    'supported_assets': ['crypto', 'forex', 'stocks'],
    'market_conditions': ['sideways', 'range', 'low_volatility']
} 
