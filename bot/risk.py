# bot/risk.py
# Централизованный риск-менеджер для торгового бота
# Функции: контроль лимитов, управление позициями, мониторинг рисков, аварийные остановки

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskLimits:
    max_daily_trades: int = 20
    max_open_positions: int = 3
    max_daily_loss_pct: float = 5.0  # % от баланса
    max_position_size_pct: float = 2.0  # % от баланса
    max_correlation_exposure: float = 50.0  # % суммарной экспозиции
    max_drawdown_pct: float = 10.0
    min_risk_reward_ratio: float = 1.0
    max_leverage: float = 1.0


@dataclass
class PositionRisk:
    strategy: str
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    risk_pct: float
    stop_loss: float
    take_profit: float


class RiskManager:
    def __init__(self, config_path: str = None):
        self.logger = logging.getLogger('risk_manager')
        
        # Лимиты по умолчанию
        self.global_limits = RiskLimits()
        self.strategy_limits = {}
        
        # Состояние риск-менеджера
        self.daily_trades = {}  # {date: count}
        self.daily_pnl = {}     # {date: pnl}
        self.open_positions = {}  # {strategy: PositionRisk}
        self.correlation_matrix = {}
        
        # Статистика
        self.risk_events = []
        self.blocked_strategies = set()
        self.emergency_stop = False
        
        # История для расчета корреляций
        self.price_history = {}  # {symbol: [prices]}
        self.pnl_history = []
        
        # Загружаем конфигурацию если есть
        if config_path:
            self.load_config(config_path)
    
    def load_config(self, config_path: str):
        """Загрузка конфигурации лимитов"""
        try:
            import json
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Глобальные лимиты
            if 'global_limits' in config:
                for key, value in config['global_limits'].items():
                    if hasattr(self.global_limits, key):
                        setattr(self.global_limits, key, value)
            
            # Лимиты по стратегиям
            self.strategy_limits = config.get('strategy_limits', {})
            
            self.logger.info("Конфигурация риск-менеджера загружена")
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации: {e}")
    
    def get_strategy_limits(self, strategy_name: str) -> RiskLimits:
        """Получение лимитов для конкретной стратегии"""
        if strategy_name in self.strategy_limits:
            limits = RiskLimits()
            for key, value in self.strategy_limits[strategy_name].items():
                if hasattr(limits, key):
                    setattr(limits, key, value)
            return limits
        return self.global_limits
    
    def check_pre_trade_risk(self, strategy_name: str, signal: Dict, 
                           current_balance: float, api_client) -> Tuple[bool, str]:
        """Проверка рисков ПЕРЕД размещением ордера"""
        
        # 1. Проверка emergency stop
        if self.emergency_stop:
            return False, "Активирован аварийный стоп"
        
        # 2. Проверка заблокированных стратегий
        if strategy_name in self.blocked_strategies:
            return False, f"Стратегия {strategy_name} заблокирована"
        
        # 3. Получаем лимиты для стратегии
        limits = self.get_strategy_limits(strategy_name)
        
        # 4. Проверка дневных лимитов
        today = datetime.now().date()
        daily_trades_count = self.daily_trades.get(today, 0)
        
        if daily_trades_count >= limits.max_daily_trades:
            return False, f"Превышен лимит дневных сделок ({limits.max_daily_trades})"
        
        # 5. Проверка дневных потерь
        daily_loss = abs(min(0, self.daily_pnl.get(today, 0)))
        max_daily_loss = current_balance * limits.max_daily_loss_pct / 100
        
        if daily_loss >= max_daily_loss:
            return False, f"Превышен лимит дневных потерь (${daily_loss:.2f} >= ${max_daily_loss:.2f})"
        
        # 6. Проверка количества открытых позиций
        open_positions_count = len([p for p in self.open_positions.values() 
                                  if p.strategy == strategy_name])
        
        if open_positions_count >= limits.max_open_positions:
            return False, f"Превышен лимит открытых позиций ({limits.max_open_positions})"
        
        # 7. Проверка размера позиции
        entry_price = signal.get('entry_price', 0)
        from config import get_strategy_config
        config = get_strategy_config(strategy_name)
        trade_amount = config.get('trade_amount', 0.001)
        
        position_value = entry_price * trade_amount
        max_position_value = current_balance * limits.max_position_size_pct / 100
        
        if position_value > max_position_value:
            return False, f"Размер позиции слишком большой (${position_value:.2f} > ${max_position_value:.2f})"
        
        # 8. Проверка Risk/Reward соотношения
        stop_loss = signal.get('stop_loss', 0)
        take_profit = signal.get('take_profit', 0)
        
        if stop_loss and take_profit and entry_price:
            if signal['signal'] == 'BUY':
                risk = abs(entry_price - stop_loss)
                reward = abs(take_profit - entry_price)
            else:  # SELL
                risk = abs(stop_loss - entry_price)
                reward = abs(entry_price - take_profit)
            
            rr_ratio = reward / risk if risk > 0 else 0
            
            if rr_ratio < limits.min_risk_reward_ratio:
                return False, f"Неудовлетворительное R/R соотношение ({rr_ratio:.2f} < {limits.min_risk_reward_ratio})"
        
        # 9. Проверка корреляций (если есть другие позиции)
        if not self._check_correlation_risk(strategy_name, signal['signal'], limits):
            return False, "Превышен лимит корреляционного риска"
        
        # 10. Проверка волатильности рынка
        market_risk_level = self._assess_market_risk(signal.get('market_data', {}))
        if market_risk_level == RiskLevel.CRITICAL:
            return False, "Критический уровень рыночного риска"
        
        # 11. Проверка времени торговли (избегаем новости, выходные)
        if not self._is_safe_trading_time():
            return False, "Небезопасное время для торговли"
        
        return True, "Риски в норме"
    
    def _check_correlation_risk(self, strategy_name: str, signal_direction: str, limits: RiskLimits) -> bool:
        """Проверка корреляционного риска"""
        try:
            same_direction_exposure = 0
            total_exposure = 0
            
            for position in self.open_positions.values():
                position_exposure = abs(position.size * position.current_price)
                total_exposure += position_exposure
                
                # Если направление совпадает, увеличиваем корреляционную экспозицию
                if position.side == signal_direction:
                    same_direction_exposure += position_exposure
            
            if total_exposure > 0:
                correlation_pct = (same_direction_exposure / total_exposure) * 100
                if correlation_pct > limits.max_correlation_exposure:
                    self.logger.warning(f"Корреляционный риск: {correlation_pct:.1f}% > {limits.max_correlation_exposure}%")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки корреляций: {e}")
            return True  # В случае ошибки разрешаем торговлю
    
    def _assess_market_risk(self, market_data: Dict) -> RiskLevel:
        """Оценка общего рыночного риска"""
        try:
            risk_factors = []
            
            # Проверяем волатильность по разным таймфреймам
            for tf, df in market_data.items():
                if df is not None and not df.empty and len(df) > 10:
                    # Волатильность (ATR/цена)
                    high_low_range = (df['high'] - df['low']) / df['close']
                    avg_volatility = high_low_range.tail(10).mean()
                    
                    if avg_volatility > 0.05:  # 5%
                        risk_factors.append('high_volatility')
                    
                    # Резкие движения цены
                    price_changes = df['close'].pct_change().abs()
                    max_change = price_changes.tail(5).max()
                    
                    if max_change > 0.03:  # 3%
                        risk_factors.append('sharp_movement')
            
            # Определяем уровень риска
            if len(risk_factors) >= 4:
                return RiskLevel.CRITICAL
            elif len(risk_factors) >= 2:
                return RiskLevel.HIGH
            elif len(risk_factors) >= 1:
                return RiskLevel.MEDIUM
            else:
                return RiskLevel.LOW
                
        except Exception as e:
            self.logger.error(f"Ошибка оценки рыночного риска: {e}")
            return RiskLevel.MEDIUM
    
    def _is_safe_trading_time(self) -> bool:
        """Проверка безопасного времени для торговли"""
        now = datetime.now()
        
        # Избегаем выходных для традиционных рынков
        if now.weekday() >= 5:  # Суббота = 5, Воскресенье = 6
            # Для крипты можно торговать, но с ограничениями
            pass
        
        # Избегаем важных новостных часов (примерные)
        risky_hours = [
            (8, 10),   # Европейское открытие
            (13, 15),  # US открытие
            (21, 23),  # Азиатское открытие
        ]
        
        current_hour = now.hour
        for start_hour, end_hour in risky_hours:
            if start_hour <= current_hour <= end_hour:
                # Не блокируем полностью, но увеличиваем осторожность
                pass
        
        return True  # Пока не блокируем по времени
    
    def register_trade(self, strategy_name: str, signal: Dict, order_response: Dict):
        """Регистрация совершенной сделки"""
        today = datetime.now().date()
        
        # Увеличиваем счетчик дневных сделок
        self.daily_trades[today] = self.daily_trades.get(today, 0) + 1
        
        # Создаем запись о позиции
        if order_response and order_response.get('retCode') == 0:
            position = PositionRisk(
                strategy=strategy_name,
                symbol=signal.get('symbol', 'BTCUSDT'),
                side=signal['signal'],
                size=float(order_response.get('result', {}).get('qty', 0)),
                entry_price=signal['entry_price'],
                current_price=signal['entry_price'],
                unrealized_pnl=0.0,
                risk_pct=0.0,
                stop_loss=signal.get('stop_loss', 0),
                take_profit=signal.get('take_profit', 0)
            )
            
            position_key = f"{strategy_name}_{signal.get('symbol', 'BTCUSDT')}"
            self.open_positions[position_key] = position
            
            self.logger.info(f"Зарегистрирована позиция: {position_key}")
    
    def update_position(self, strategy_name: str, symbol: str, current_price: float, 
                       current_balance: float):
        """Обновление информации о позиции"""
        position_key = f"{strategy_name}_{symbol}"
        
        if position_key in self.open_positions:
            position = self.open_positions[position_key]
            position.current_price = current_price
            
            # Пересчитываем P&L
            if position.side == 'BUY':
                position.unrealized_pnl = (current_price - position.entry_price) * position.size
            else:  # SELL
                position.unrealized_pnl = (position.entry_price - current_price) * position.size
            
            # Пересчитываем риск в процентах от баланса
            position_value = position.size * current_price
            position.risk_pct = (position_value / current_balance) * 100
            
            # Проверяем критические уровни
            self._check_position_risk(position, current_balance)
    
    def _check_position_risk(self, position: PositionRisk, current_balance: float):
        """Проверка рисков открытой позиции"""
        # Проверка на критические потери
        loss_pct = (position.unrealized_pnl / current_balance) * 100
        
        if loss_pct < -2.0:  # Потери больше 2%
            self.logger.warning(f"Критические потери по позиции {position.strategy}: {loss_pct:.2f}%")
            
            # Добавляем в события риска
            risk_event = {
                'timestamp': datetime.now().isoformat(),
                'type': 'critical_loss',
                'strategy': position.strategy,
                'loss_pct': loss_pct,
                'position': position
            }
            self.risk_events.append(risk_event)
        
        # Проверка стоп-лосса
        if position.stop_loss > 0:
            if ((position.side == 'BUY' and position.current_price <= position.stop_loss) or
                (position.side == 'SELL' and position.current_price >= position.stop_loss)):
                
                self.logger.warning(f"Цена достигла стоп-лосса: {position.strategy}")
                # Здесь можно добавить автоматическое закрытие позиции
    
    def close_position(self, strategy_name: str, symbol: str, exit_price: float, 
                      realized_pnl: float):
        """Закрытие позиции"""
        position_key = f"{strategy_name}_{symbol}"
        
        if position_key in self.open_positions:
            position = self.open_positions.pop(position_key)
            
            # Обновляем дневный P&L
            today = datetime.now().date()
            self.daily_pnl[today] = self.daily_pnl.get(today, 0) + realized_pnl
            
            # Сохраняем в историю
            self.pnl_history.append({
                'timestamp': datetime.now().isoformat(),
                'strategy': strategy_name,
                'symbol': symbol,
                'side': position.side,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'pnl': realized_pnl,
                'hold_time': datetime.now()  # Можно вычислить время удержания
            })
            
            self.logger.info(f"Позиция закрыта: {position_key}, P&L: ${realized_pnl:.2f}")
    
    def get_risk_report(self) -> Dict:
        """Получение отчета о рисках"""
        today = datetime.now().date()
        
        # Текущие позиции
        total_exposure = sum(pos.size * pos.current_price for pos in self.open_positions.values())
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in self.open_positions.values())
        
        # Статистика по стратегиям
        strategy_stats = {}
        for position in self.open_positions.values():
            strategy = position.strategy
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {
                    'positions': 0,
                    'exposure': 0,
                    'unrealized_pnl': 0
                }
            
            strategy_stats[strategy]['positions'] += 1
            strategy_stats[strategy]['exposure'] += position.size * position.current_price
            strategy_stats[strategy]['unrealized_pnl'] += position.unrealized_pnl
        
        return {
            'timestamp': datetime.now().isoformat(),
            'emergency_stop': self.emergency_stop,
            'blocked_strategies': list(self.blocked_strategies),
            'daily_trades': self.daily_trades.get(today, 0),
            'daily_pnl': self.daily_pnl.get(today, 0),
            'open_positions_count': len(self.open_positions),
            'total_exposure': total_exposure,
            'total_unrealized_pnl': total_unrealized_pnl,
            'strategy_stats': strategy_stats,
            'recent_risk_events': self.risk_events[-10:],  # Последние 10 событий
            'limits': {
                'max_daily_trades': self.global_limits.max_daily_trades,
                'max_open_positions': self.global_limits.max_open_positions,
                'max_daily_loss_pct': self.global_limits.max_daily_loss_pct
            }
        }
    
    def emergency_stop_all(self, reason: str):
        """Аварийная остановка всех операций"""
        self.emergency_stop = True
        
        risk_event = {
            'timestamp': datetime.now().isoformat(),
            'type': 'emergency_stop',
            'reason': reason,
            'open_positions': len(self.open_positions)
        }
        self.risk_events.append(risk_event)
        
        self.logger.critical(f"АВАРИЙНАЯ ОСТАНОВКА: {reason}")
    
    def block_strategy(self, strategy_name: str, reason: str, duration_hours: int = 24):
        """Блокировка стратегии"""
        self.blocked_strategies.add(strategy_name)
        
        # Можно добавить автоматическую разблокировку через время
        risk_event = {
            'timestamp': datetime.now().isoformat(),
            'type': 'strategy_blocked',
            'strategy': strategy_name,
            'reason': reason,
            'duration_hours': duration_hours
        }
        self.risk_events.append(risk_event)
        
        self.logger.warning(f"Стратегия {strategy_name} заблокирована: {reason}")
    
    def unblock_strategy(self, strategy_name: str):
        """Разблокировка стратегии"""
        if strategy_name in self.blocked_strategies:
            self.blocked_strategies.remove(strategy_name)
            self.logger.info(f"Стратегия {strategy_name} разблокирована")
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Очистка старых данных"""
        cutoff_date = datetime.now().date() - timedelta(days=days_to_keep)
        
        # Очищаем старые дневные данные
        self.daily_trades = {date: count for date, count in self.daily_trades.items() 
                           if date >= cutoff_date}
        self.daily_pnl = {date: pnl for date, pnl in self.daily_pnl.items() 
                         if date >= cutoff_date}
        
        # Очищаем старые события риска
        cutoff_datetime = datetime.now() - timedelta(days=days_to_keep)
        self.risk_events = [event for event in self.risk_events 
                          if datetime.fromisoformat(event['timestamp']) >= cutoff_datetime]
        
        # Ограничиваем историю P&L
        if len(self.pnl_history) > 1000:
            self.pnl_history = self.pnl_history[-1000:]


# Пример конфигурационного файла (risk_config.json):
"""
{
    "global_limits": {
        "max_daily_trades": 30,
        "max_open_positions": 5,
        "max_daily_loss_pct": 5.0,
        "max_position_size_pct": 2.0,
        "max_correlation_exposure": 60.0,
        "min_risk_reward_ratio": 1.2
    },
    "strategy_limits": {
        "strategy_01": {
            "max_daily_trades": 10,
            "max_position_size_pct": 1.5
        },
        "strategy_02": {
            "max_daily_trades": 15,
            "max_position_size_pct": 2.5
        }
    }
}
"""