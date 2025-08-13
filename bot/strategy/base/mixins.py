# bot/strategy/base/mixins.py
"""
Миксины для переиспользования общего функционала в торговых стратегиях
Устраняет дублирование кода между различными стратегиями
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timezone, timedelta
import logging
from abc import ABC

from .enums import MarketRegime, PositionSide, SignalType, ExitReason
from ..utils.indicators import TechnicalIndicators
from ..utils.levels import LevelsFinder
from ..utils.market_analysis import MarketRegimeAnalyzer

# Настройка логирования
logger = logging.getLogger(__name__)


class PositionManagerMixin:
    """
    Миксин для управления позициями
    Содержит общую логику работы с позициями, выходами и рисками
    """
    
    def is_in_position(self, state) -> bool:
        """
        Проверка состояния позиции с расширенной логикой
        
        Args:
            state: Объект состояния бота
        
        Returns:
            bool: True если в позиции
        """
        if state is None:
            return False
        
        in_position = getattr(state, 'in_position', False)
        
        # Дополнительная проверка времени последней позиции для избежания дублирования
        if in_position and hasattr(state, 'entry_time'):
            try:
                entry_time = state.entry_time
                if isinstance(entry_time, str):
                    entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                elif hasattr(entry_time, 'timestamp'):
                    # Проверяем, есть ли timezone info
                    if entry_time.tzinfo is None:
                        # Если naive datetime, добавляем UTC timezone
                        entry_dt = entry_time.replace(tzinfo=timezone.utc)
                    else:
                        entry_dt = entry_time
                else:
                    entry_dt = datetime.now(timezone.utc)
                
                # Если позиция очень старая (>48 часов), считаем что она закрыта
                current_dt = datetime.now(timezone.utc)
                hours_diff = (current_dt - entry_dt).total_seconds() / 3600
                
                if hours_diff > 48:
                    logger.warning(f"Позиция слишком старая ({hours_diff:.1f}ч), считаем закрытой")
                    return False
                    
            except Exception as e:
                logger.error(f"Ошибка проверки времени позиции: {e}")
        
        return in_position
    
    def get_position_info(self, state) -> Dict[str, Any]:
        """
        Получение полной информации о текущей позиции
        
        Returns:
            Dict с информацией о позиции
        """
        if not self.is_in_position(state):
            return {'in_position': False}
        
        try:
            position_info = {
                'in_position': True,
                'side': getattr(state, 'position_side', None),
                'entry_price': getattr(state, 'entry_price', None),
                'entry_time': getattr(state, 'entry_time', None),
                'stop_loss': getattr(state, 'stop_loss', None),
                'take_profit': getattr(state, 'take_profit', None),
                'quantity': getattr(state, 'quantity', None)
            }
            
            # Расчет дополнительных метрик если есть entry_price
            if position_info['entry_price'] and hasattr(self, 'config'):
                current_price = getattr(state, 'current_price', position_info['entry_price'])
                
                # P&L расчет
                entry_price = position_info['entry_price']
                side = position_info['side']
                
                if side == 'BUY' or side == PositionSide.LONG:
                    pnl_pct = (current_price - entry_price) / entry_price * 100
                elif side == 'SELL' or side == PositionSide.SHORT:
                    pnl_pct = (entry_price - current_price) / entry_price * 100
                else:
                    pnl_pct = 0
                
                position_info.update({
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                    'pnl_absolute': pnl_pct * entry_price / 100,
                    'is_profitable': pnl_pct > 0
                })
                
                # Время в позиции
                if position_info['entry_time']:
                    try:
                        entry_time = position_info['entry_time']
                        if isinstance(entry_time, str):
                            entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                        else:
                            # Проверяем, есть ли timezone info
                            if entry_time.tzinfo is None:
                                # Если naive datetime, добавляем UTC timezone
                                entry_dt = entry_time.replace(tzinfo=timezone.utc)
                            else:
                                entry_dt = entry_time
                        
                        current_dt = datetime.now(timezone.utc)
                        duration = current_dt - entry_dt
                        
                        position_info.update({
                            'duration_hours': duration.total_seconds() / 3600,
                            'duration_minutes': duration.total_seconds() / 60
                        })
                        
                    except Exception as e:
                        logger.error(f"Ошибка расчета длительности позиции: {e}")
            
            return position_info
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о позиции: {e}")
            return {'in_position': False, 'error': str(e)}
    
    def should_exit_position_base(self, df: pd.DataFrame, state, current_price: float,
                                 atr_period: int = 14) -> Optional[Dict[str, Any]]:
        """
        Базовая логика выхода из позиции (трейлинг стоп + временной выход)
        
        Args:
            df: DataFrame с данными
            state: Состояние бота
            current_price: Текущая цена
            atr_period: Период для расчета ATR
        
        Returns:
            Dict с сигналом выхода или None
        """
        try:
            if not self.is_in_position(state):
                return None
            
            position_info = self.get_position_info(state)
            position_side = position_info.get('side')
            entry_price = position_info.get('entry_price')
            entry_time = position_info.get('entry_time')
            
            if not position_side or not entry_price:
                return None
            
            # P&L расчет
            if position_side in ['BUY', PositionSide.LONG]:
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - current_price) / entry_price * 100
            
            # 1. Трейлинг стоп (если прибыль > 1.5%)
            trailing_activation = getattr(self.config, 'trailing_stop_activation_pct', 1.5)
            if hasattr(self.config, 'trailing_stop_enabled') and self.config.trailing_stop_enabled:
                if pnl_pct > trailing_activation:
                    atr = TechnicalIndicators.calculate_atr_safe(df, atr_period).value
                    trailing_distance = atr * 0.7
                    
                    if position_side in ['BUY', PositionSide.LONG]:
                        trailing_stop = current_price - trailing_distance
                        if current_price < trailing_stop:
                            return {
                                'signal': SignalType.EXIT_LONG,
                                'exit_reason': ExitReason.TRAILING_STOP,
                                'current_price': current_price,
                                'pnl_pct': pnl_pct,
                                'comment': f'Трейлинг стоп: прибыль {pnl_pct:.1f}%'
                            }
                    else:
                        trailing_stop = current_price + trailing_distance
                        if current_price > trailing_stop:
                            return {
                                'signal': SignalType.EXIT_SHORT,
                                'exit_reason': ExitReason.TRAILING_STOP,
                                'current_price': current_price,
                                'pnl_pct': pnl_pct,
                                'comment': f'Трейлинг стоп: прибыль {pnl_pct:.1f}%'
                            }
            
            # 2. Временной выход
            max_duration = getattr(self.config, 'max_position_duration_hours', 24)
            forced_exit_hours = getattr(self.config, 'forced_exit_on_low_profit_hours', 24)
            
            if entry_time:
                try:
                    if isinstance(entry_time, str):
                        entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    else:
                        entry_dt = entry_time
                    
                    current_dt = datetime.now(timezone.utc)
                    hours_in_position = (current_dt - entry_dt).total_seconds() / 3600
                    
                    # Принудительный выход после максимального времени
                    if hours_in_position > max_duration:
                        side_str = 'LONG' if position_side in ['BUY', PositionSide.LONG] else 'SHORT'
                        return {
                            'signal': f'EXIT_{side_str}',
                            'exit_reason': ExitReason.TIME_EXIT,
                            'current_price': current_price,
                            'pnl_pct': pnl_pct,
                            'comment': f'Временной выход: {hours_in_position:.1f}ч в позиции'
                        }
                    
                    # Выход при низкой прибыли после длительного времени
                    if hours_in_position > forced_exit_hours and pnl_pct < 0.5:
                        side_str = 'LONG' if position_side in ['BUY', PositionSide.LONG] else 'SHORT'
                        return {
                            'signal': f'EXIT_{side_str}',
                            'exit_reason': ExitReason.TIME_EXIT,
                            'current_price': current_price,
                            'pnl_pct': pnl_pct,
                            'comment': f'Принудительный выход: низкая прибыль {pnl_pct:.1f}% за {hours_in_position:.1f}ч'
                        }
                        
                except Exception as e:
                    logger.error(f"Ошибка обработки времени позиции: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка базовой логики выхода: {e}")
            return None


class StatisticsMixin:
    """
    Миксин для сбора и управления статистикой стратегий
    Содержит общую логику отслеживания производительности
    """
    
    def __init__(self):
        """Инициализация статистических счетчиков"""
        self.signals_generated = 0
        self.signals_executed = 0
        self.last_signal_time = None
        self.performance_history = []
        self._session_stats = {
            'trades_count': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'session_start': datetime.now(timezone.utc)
        }
    
    def reset_statistics(self):
        """Сброс всей статистики стратегии"""
        self.signals_generated = 0
        self.signals_executed = 0
        self.last_signal_time = None
        self.performance_history = []
        self._session_stats = {
            'trades_count': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'session_start': datetime.now(timezone.utc)
        }
        
        if hasattr(self, 'logger'):
            self.logger.info("Статистика стратегии сброшена")
    
    def update_performance(self, trade_result: Dict[str, Any]):
        """
        Обновление статистики производительности
        
        Args:
            trade_result: Результат сделки с ключами success, pnl, pnl_pct, duration_hours
        """
        try:
            # Создаем запись о производительности
            performance_record = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'success': trade_result.get('success', False),
                'pnl': trade_result.get('pnl', 0),
                'pnl_pct': trade_result.get('pnl_pct', 0),
                'trade_duration': trade_result.get('duration_hours', 0),
                'market_regime': getattr(self, 'current_market_regime', 'unknown'),
                'entry_reason': trade_result.get('entry_reason', 'strategy_signal'),
                'exit_reason': trade_result.get('exit_reason', 'unknown')
            }
            
            # Добавляем в историю
            self.performance_history.append(performance_record)
            
            # Ограничиваем размер истории
            max_history = getattr(self, 'max_performance_history', 1000)
            if len(self.performance_history) > max_history:
                self.performance_history = self.performance_history[-max_history:]
            
            # Обновляем сессионную статистику
            self._update_session_stats(trade_result)
            
            # Логирование
            if hasattr(self, 'logger'):
                status = '✅ успех' if trade_result.get('success') else '❌ неудача'
                pnl_pct = trade_result.get('pnl_pct', 0)
                self.logger.info(f"Обновлена производительность: {status}, P&L: {pnl_pct:.2f}%")
            
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Ошибка обновления производительности: {e}")
    
    def _update_session_stats(self, trade_result: Dict[str, Any]):
        """Обновление сессионной статистики"""
        try:
            self._session_stats['trades_count'] += 1
            
            pnl = trade_result.get('pnl', 0)
            success = trade_result.get('success', False)
            
            if success:
                self._session_stats['winning_trades'] += 1
            else:
                self._session_stats['losing_trades'] += 1
            
            # Обновляем общий P&L
            self._session_stats['total_pnl'] += pnl
            
            # Отслеживаем максимальную просадку
            if pnl < 0:
                current_drawdown = abs(pnl)
                if current_drawdown > self._session_stats['max_drawdown']:
                    self._session_stats['max_drawdown'] = current_drawdown
                    
        except Exception as e:
            logger.error(f"Ошибка обновления сессионной статистики: {e}")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Получение метрик производительности
        
        Returns:
            Dict с ключевыми метриками производительности
        """
        try:
            if not self.performance_history:
                return {
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'avg_pnl': 0.0,
                    'total_pnl': 0.0,
                    'best_trade': 0.0,
                    'worst_trade': 0.0,
                    'avg_duration': 0.0,
                    'sharpe_ratio': 0.0
                }
            
            # Базовые метрики
            total_trades = len(self.performance_history)
            winning_trades = sum(1 for trade in self.performance_history if trade['success'])
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            # P&L метрики
            pnl_values = [trade['pnl_pct'] for trade in self.performance_history]
            avg_pnl = np.mean(pnl_values) if pnl_values else 0
            total_pnl = sum(pnl_values)
            best_trade = max(pnl_values) if pnl_values else 0
            worst_trade = min(pnl_values) if pnl_values else 0
            
            # Временные метрики
            durations = [trade['trade_duration'] for trade in self.performance_history if trade['trade_duration'] > 0]
            avg_duration = np.mean(durations) if durations else 0
            
            # Sharpe ratio (упрощенный)
            if len(pnl_values) > 1:
                pnl_std = np.std(pnl_values)
                sharpe_ratio = avg_pnl / pnl_std if pnl_std > 0 else 0
            else:
                sharpe_ratio = 0
            
            # Дополнительные метрики
            profitable_trades = [p for p in pnl_values if p > 0]
            losing_trades = [p for p in pnl_values if p < 0]
            
            avg_win = np.mean(profitable_trades) if profitable_trades else 0
            avg_loss = np.mean(losing_trades) if losing_trades else 0
            profit_factor = abs(sum(profitable_trades) / sum(losing_trades)) if losing_trades else float('inf')
            
            return {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': total_trades - winning_trades,
                'win_rate': win_rate * 100,
                'avg_pnl': avg_pnl,
                'total_pnl': total_pnl,
                'best_trade': best_trade,
                'worst_trade': worst_trade,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'avg_duration_hours': avg_duration,
                'sharpe_ratio': sharpe_ratio,
                'signals_generated': self.signals_generated,
                'signals_executed': self.signals_executed,
                'signal_execution_rate': (self.signals_executed / self.signals_generated * 100) if self.signals_generated > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Ошибка расчета метрик производительности: {e}")
            return {'error': str(e)}
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Получение сводки текущей сессии"""
        try:
            session_duration = datetime.now(timezone.utc) - self._session_stats['session_start']
            
            summary = {
                'session_duration_hours': session_duration.total_seconds() / 3600,
                'trades_count': self._session_stats['trades_count'],
                'winning_trades': self._session_stats['winning_trades'], 
                'losing_trades': self._session_stats['losing_trades'],
                'win_rate': (self._session_stats['winning_trades'] / self._session_stats['trades_count'] * 100) if self._session_stats['trades_count'] > 0 else 0,
                'total_pnl': self._session_stats['total_pnl'],
                'max_drawdown': self._session_stats['max_drawdown'],
                'signals_generated': self.signals_generated,
                'session_start': self._session_stats['session_start'].isoformat()
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Ошибка получения сводки сессии: {e}")
            return {'error': str(e)}


class PriceUtilsMixin:
    """
    Миксин для работы с ценами и расчетов уровней
    Содержит общие утилиты для ценовых операций
    """
    
    def round_price(self, price: float) -> float:
        """
        Округление цены с проверкой
        
        Args:
            price: Цена для округления
        
        Returns:
            Округленная цена
        """
        try:
            if pd.isna(price) or price <= 0:
                return 0.0
            
            price_step = getattr(self.config, 'price_step', 0.1)
            return round(price / price_step) * price_step
        except:
            return 0.0
    
    def calculate_adaptive_rr_ratio(self, df: pd.DataFrame) -> float:
        """
        Расчет адаптивного Risk/Reward соотношения на основе волатильности
        
        Args:
            df: DataFrame с данными
        
        Returns:
            Адаптивное R:R соотношение
        """
        try:
            base_rr = getattr(self.config, 'risk_reward_ratio', 1.5)
            
            # Анализ волатильности для адаптации R:R
            returns = df['close'].pct_change().dropna()
            volatility = returns.tail(20).std()
            
            # В более волатильном рынке используем более высокий R:R
            if volatility > 0.025:  # 2.5%
                return base_rr * 1.3
            elif volatility < 0.01:  # 1%
                return base_rr * 0.8
            else:
                return base_rr
                
        except Exception as e:
            logger.error(f"Ошибка расчета адаптивного R:R: {e}")
            return getattr(self.config, 'risk_reward_ratio', 1.5)
    
    def calculate_position_size(self, entry_price: float, stop_loss: float, 
                              account_balance: float, risk_pct: Optional[float] = None) -> float:
        """
        Расчет размера позиции на основе риска
        
        Args:
            entry_price: Цена входа
            stop_loss: Уровень стоп-лосса
            account_balance: Баланс аккаунта
            risk_pct: Процент риска (если None, берется из конфига)
        
        Returns:
            Размер позиции
        """
        try:
            if risk_pct is None:
                risk_pct = getattr(self.config, 'max_risk_per_trade_pct', 1.0)
            
            # Расчет риска на сделку в абсолютных единицах
            risk_amount = account_balance * (risk_pct / 100)
            
            # Расчет риска на единицу (расстояние до стоп-лосса)
            risk_per_unit = abs(entry_price - stop_loss)
            
            if risk_per_unit == 0:
                return 0.0
            
            # Размер позиции
            position_size = risk_amount / risk_per_unit
            
            # Округление до разумного значения
            return round(position_size, 6)
            
        except Exception as e:
            logger.error(f"Ошибка расчета размера позиции: {e}")
            return 0.0
    
    def validate_price_levels(self, entry_price: float, stop_loss: float, 
                            take_profit: float, side: str) -> Tuple[bool, str]:
        """
        Валидация ценовых уровней для корректности
        
        Args:
            entry_price: Цена входа
            stop_loss: Стоп-лосс
            take_profit: Тейк-профит
            side: Сторона сделки ('BUY' или 'SELL')
        
        Returns:
            Tuple (is_valid, error_message)
        """
        try:
            # Проверка на валидность цен
            if any(price <= 0 for price in [entry_price, stop_loss, take_profit]):
                return False, "Все цены должны быть больше нуля"
            
            if side in ['BUY', PositionSide.LONG]:
                # Для лонга: SL < entry < TP
                if stop_loss >= entry_price:
                    return False, "Стоп-лосс должен быть ниже цены входа для лонга"
                
                if take_profit <= entry_price:
                    return False, "Тейк-профит должен быть выше цены входа для лонга"
                    
            elif side in ['SELL', PositionSide.SHORT]:
                # Для шорта: TP < entry < SL
                if stop_loss <= entry_price:
                    return False, "Стоп-лосс должен быть выше цены входа для шорта"
                
                if take_profit >= entry_price:
                    return False, "Тейк-профит должен быть ниже цены входа для шорта"
            
            else:
                return False, f"Неизвестная сторона сделки: {side}"
            
            # Проверка R:R соотношения
            if side in ['BUY', PositionSide.LONG]:
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
            else:
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
            
            rr_ratio = reward / risk if risk > 0 else 0
            min_rr = getattr(self.config, 'min_risk_reward_ratio', 1.0)
            
            # Адаптивная валидация для скальпинга
            if hasattr(self.config, 'adaptive_parameters') and self.config.adaptive_parameters:
                # При низкой волатильности снижаем требования к R:R
                if hasattr(self, 'current_market_regime'):
                    if self.current_market_regime == MarketRegime.SIDEWAYS:
                        min_rr = max(min_rr * 0.8, 0.5)  # Снижаем требования для бокового рынка
                    elif self.current_market_regime == MarketRegime.VOLATILE:
                        min_rr = min_rr * 1.2  # Повышаем требования для волатильного рынка
            
            if rr_ratio < min_rr:
                return False, f"R:R соотношение слишком низкое: {rr_ratio:.2f} < {min_rr}"
            
            return True, "Уровни валидны"
            
        except Exception as e:
            return False, f"Ошибка валидации уровней: {e}"


class MarketAnalysisMixin:
    """
    Миксин для анализа рыночных условий
    Содержит общие методы анализа рынка и адаптации стратегий
    """
    
    def analyze_current_market(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Анализ текущих рыночных условий
        
        Args:
            df: DataFrame с данными
        
        Returns:
            Dict с результатами анализа рынка
        """
        try:
            # Используем анализатор рыночных режимов
            market_condition = MarketRegimeAnalyzer.analyze_market_condition(df)
            
            # Сохраняем текущий режим
            self.current_market_regime = market_condition.regime
            
            # Дополнительный анализ для стратегии
            additional_analysis = {
                'price_action': self._analyze_price_action(df),
                'volume_analysis': self._analyze_volume_condition(df),
                'support_resistance': self._get_nearby_levels(df),
                'market_sentiment': self._determine_market_sentiment(market_condition)
            }
            
            return {
                'condition': market_condition,
                'analysis': additional_analysis,
                'recommendations': self._generate_trading_recommendations(market_condition)
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа рынка: {e}")
            return {
                'condition': None,
                'analysis': {},
                'recommendations': ['Ошибка анализа рынка']
            }
    
    def _analyze_price_action(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ ценового действия"""
        try:
            # Последние несколько свечей
            recent_bars = df.tail(5)
            
            # Анализ типов свечей
            green_candles = (recent_bars['close'] > recent_bars['open']).sum()
            red_candles = (recent_bars['close'] < recent_bars['open']).sum()
            
            # Анализ теней
            upper_shadows = recent_bars['high'] - recent_bars[['open', 'close']].max(axis=1)
            lower_shadows = recent_bars[['open', 'close']].min(axis=1) - recent_bars['low']
            bodies = abs(recent_bars['close'] - recent_bars['open'])
            
            avg_upper_shadow = upper_shadows.mean()
            avg_lower_shadow = lower_shadows.mean()
            avg_body = bodies.mean()
            
            return {
                'green_candles': green_candles,
                'red_candles': red_candles,
                'dominant_color': 'green' if green_candles > red_candles else 'red',
                'avg_body_size': avg_body,
                'avg_upper_shadow': avg_upper_shadow,
                'avg_lower_shadow': avg_lower_shadow,
                'shadow_dominance': 'upper' if avg_upper_shadow > avg_lower_shadow else 'lower'
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа ценового действия: {e}")
            return {}
    
    def _analyze_volume_condition(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ объемных условий"""
        try:
            if 'volume' not in df.columns:
                return {'status': 'no_volume_data'}
            
            # Сравнение с средним объемом
            avg_volume = df['volume'].tail(20).mean()
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Тренд объема
            volume_trend = df['volume'].tail(5).diff().mean()
            
            return {
                'current_volume': current_volume,
                'avg_volume': avg_volume,
                'volume_ratio': volume_ratio,
                'volume_status': 'high' if volume_ratio > 1.5 else 'low' if volume_ratio < 0.5 else 'normal',
                'volume_trend': 'increasing' if volume_trend > 0 else 'decreasing'
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа объема: {e}")
            return {}
    
    def _get_nearby_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Получение ближайших уровней поддержки/сопротивления"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Поиск swing уровней
            levels = LevelsFinder.find_swing_levels(df, lookback=20, min_touches=2)
            
            # Фильтрация ближайших уровней (в пределах 2% от цены)
            nearby_levels = [
                level for level in levels 
                if abs(level.price - current_price) / current_price <= 0.02
            ]
            
            # Разделение на поддержки и сопротивления
            supports = [level for level in nearby_levels if level.price < current_price]
            resistances = [level for level in nearby_levels if level.price > current_price]
            
            # Сортировка по близости
            supports.sort(key=lambda x: x.price, reverse=True)  # Ближайшая поддержка сверху
            resistances.sort(key=lambda x: x.price)  # Ближайшее сопротивление снизу
            
            return {
                'nearest_support': supports[0].price if supports else None,
                'nearest_resistance': resistances[0].price if resistances else None,
                'support_count': len(supports),
                'resistance_count': len(resistances),
                'in_range': len(supports) > 0 and len(resistances) > 0
            }
            
        except Exception as e:
            logger.error(f"Ошибка поиска уровней: {e}")
            return {}
    
    def _determine_market_sentiment(self, market_condition) -> str:
        """Определение рыночного настроения"""
        try:
            if market_condition.is_bullish:
                return 'bullish'
            elif market_condition.is_bearish:
                return 'bearish'
            elif market_condition.is_volatile:
                return 'volatile'
            elif market_condition.regime == MarketRegime.SIDEWAYS:
                return 'neutral'
            else:
                return 'uncertain'
                
        except Exception as e:
            logger.error(f"Ошибка определения настроения: {e}")
            return 'unknown'
    
    def _generate_trading_recommendations(self, market_condition) -> List[str]:
        """Генерация торговых рекомендаций"""
        recommendations = []
        
        try:
            if market_condition.is_trending:
                recommendations.append("✅ Благоприятные условия для трендовых стратегий")
            
            if market_condition.is_volatile:
                recommendations.append("⚠️ Высокая волатильность - уменьшите размер позиций")
            
            if market_condition.regime == MarketRegime.SIDEWAYS:
                recommendations.append("📊 Боковой рынок - рассмотрите стратегии диапазона")
            
            if market_condition.volume_activity > 1.5:
                recommendations.append("📈 Высокая объемная активность - хорошие условия для входа")
            
            if market_condition.confidence < 0.6:
                recommendations.append("🤔 Низкая уверенность в режиме - будьте осторожны")
            
            if not recommendations:
                recommendations.append("🔍 Нейтральные условия - используйте стандартные параметры")
            
        except Exception as e:
            logger.error(f"Ошибка генерации рекомендаций: {e}")
            recommendations.append("❌ Ошибка анализа условий")
        
        return recommendations
    
    def adapt_strategy_parameters(self, market_condition) -> Dict[str, float]:
        """
        Адаптация параметров стратегии под рыночные условия
        
        Returns:
            Dict с адаптированными параметрами
        """
        if not hasattr(self.config, 'adaptive_parameters') or not self.config.adaptive_parameters:
            return {}
        
        try:
            adaptations = {}
            
            if market_condition.regime == MarketRegime.VOLATILE:
                # В волатильном рынке - более консервативные параметры
                adaptations.update({
                    'stop_loss_multiplier': 1.2,
                    'signal_strength_threshold': min(self.config.signal_strength_threshold * 1.1, 0.9),
                    'confluence_required': getattr(self.config, 'confluence_required', 2) + 1
                })
                
            elif market_condition.regime == MarketRegime.TRENDING:
                # В трендовом рынке - более агрессивные параметры
                adaptations.update({
                    'stop_loss_multiplier': 0.8,
                    'risk_reward_ratio': self.config.risk_reward_ratio * 1.2,
                    'signal_strength_threshold': max(self.config.signal_strength_threshold * 0.9, 0.4)
                })
                
            elif market_condition.regime == MarketRegime.SIDEWAYS:
                # В боковом рынке - сбалансированные параметры
                adaptations.update({
                    'confluence_required': getattr(self.config, 'confluence_required', 2) + 1,
                    'signal_strength_threshold': min(self.config.signal_strength_threshold * 1.05, 0.8)
                })
            
            return adaptations
            
        except Exception as e:
            logger.error(f"Ошибка адаптации параметров: {e}")
            return {}


# =========================================================================
# ЛОГИРОВАНИЕ И ОТЛАДКА
# =========================================================================

class LoggingMixin:
    """
    Миксин для расширенного логирования
    Содержит утилиты для детального логирования работы стратегий
    """
    
    def log_signal_generation(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]):
        """Детальное логирование генерации сигнала"""
        try:
            if hasattr(self, 'logger'):
                signal_type = signal_data.get('signal', 'UNKNOWN')
                strength = signal_data.get('signal_strength', 0)
                entry_price = signal_data.get('entry_price', 0)
                
                self.logger.info(f"🎯 Сигнал {signal_type}: цена {entry_price}, сила {strength:.3f}")
                
                # Логируем confluence факторы если есть
                confluence_factors = signal_data.get('confluence_factors', [])
                if confluence_factors:
                    self.logger.debug(f"✅ Confluence факторы: {', '.join(confluence_factors)}")
                
                # Логируем ключевые индикаторы
                indicators = signal_data.get('indicators', {})
                if indicators:
                    key_indicators = {k: v for k, v in indicators.items() if k in ['rsi', 'atr', 'volatility']}
                    self.logger.debug(f"📊 Индикаторы: {key_indicators}")
                    
        except Exception as e:
            logger.error(f"Ошибка логирования сигнала: {e}")
    
    def log_market_analysis(self, market_analysis: Dict[str, Any]):
        """Логирование результатов анализа рынка"""
        try:
            if hasattr(self, 'logger'):
                condition = market_analysis.get('condition')
                if condition:
                    self.logger.info(f"📊 Рыночные условия: {condition}")
                    
                recommendations = market_analysis.get('recommendations', [])
                for rec in recommendations:
                    self.logger.info(f"💡 {rec}")
                    
        except Exception as e:
            logger.error(f"Ошибка логирования анализа рынка: {e}")
    
    def log_performance_update(self, trade_result: Dict[str, Any]):
        """Логирование обновления производительности"""
        try:
            if hasattr(self, 'logger'):
                success = trade_result.get('success', False)
                pnl_pct = trade_result.get('pnl_pct', 0)
                duration = trade_result.get('duration_hours', 0)
                
                status = "✅ Успешно" if success else "❌ Убыток"
                self.logger.info(f"📈 Сделка завершена: {status}, P&L: {pnl_pct:.2f}%, Время: {duration:.1f}ч")
                
        except Exception as e:
            logger.error(f"Ошибка логирования производительности: {e}")


# =========================================================================
# КОНСТАНТЫ ДЛЯ МИКСИНОВ
# =========================================================================

# Настройки по умолчанию для статистики
DEFAULT_STATS_CONFIG = {
    'max_performance_history': 1000,
    'session_reset_hours': 24,
    'enable_detailed_logging': True
}

# Пороги для адаптации параметров
ADAPTATION_THRESHOLDS = {
    'volatility_high': 0.03,
    'volatility_low': 0.01,
    'trend_strong': 0.7,
    'trend_weak': 0.3,
    'volume_high': 1.5,
    'volume_low': 0.5
}