# bot/core/thread_safe_state.py
"""
💀 КРИТИЧЕСКИЙ КОМПОНЕНТ: Thread-Safe State Management
ПОЛНАЯ СИНХРОНИЗАЦИЯ ВСЕХ СОСТОЯНИЙ БОТА
ZERO TOLERANCE К RACE CONDITIONS!
"""

import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
import logging
from enum import Enum

from bot.core.exceptions import ThreadSafetyViolationError


class PositionSide(Enum):
    """Стороны позиции"""
    BUY = "Buy"
    SELL = "Sell"


@dataclass
class PositionInfo:
    """Информация о позиции"""
    symbol: str
    side: Optional[PositionSide] = None
    size: float = 0.0
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)
    avg_price: float = 0.0
    leverage: float = 1.0
    margin: float = 0.0
    strategy_name: Optional[str] = None  # Стратегия-владелец позиции
    
    @property
    def is_active(self) -> bool:
        """Проверка активности позиции"""
        return self.size > 0.0
    
    @property
    def is_long(self) -> bool:
        """Проверка лонг позиции"""
        return self.side == PositionSide.BUY
    
    @property
    def is_short(self) -> bool:
        """Проверка шорт позиции"""  
        return self.side == PositionSide.SELL


class ThreadSafeBotState:
    """
    🛡️ THREAD-SAFE СОСТОЯНИЕ ТОРГОВОГО БОТА
    
    Обеспечивает безопасный доступ к состоянию бота из множественных потоков:
    - Позиции по символам
    - P&L статистика
    - Глобальные флаги (emergency_stop, etc.)
    - Статистика стратегий
    """
    
    def __init__(self):
        # 🔒 ОСНОВНАЯ БЛОКИРОВКА
        self._lock = threading.RLock()
        
        # 📊 СОСТОЯНИЕ ПОЗИЦИЙ
        self._positions: Dict[str, PositionInfo] = {}
        
        # 📈 ГЛОБАЛЬНАЯ СТАТИСТИКА
        self._global_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'daily_pnl': 0.0,
            'max_drawdown': 0.0,
            'start_time': datetime.now(),
            'last_trade_time': None
        }
        
        # 🚨 КРИТИЧЕСКИЕ ФЛАГИ
        self._emergency_stop = False
        self._trading_enabled = True
        self._risk_limits_exceeded = False
        
        # 📝 СТАТИСТИКА ПО СТРАТЕГИЯМ
        self._strategy_stats: Dict[str, Dict[str, Any]] = {}
        
        # ⚡ ПРОИЗВОДИТЕЛЬНОСТЬ
        self._last_sync_time = {}
        self._sync_counts = {}
        
        # 📝 ЛОГИРОВАНИЕ
        self.logger = logging.getLogger('bot_state')
        self.logger.info("🛡️ ThreadSafeBotState инициализирован с полной защитой")
    
    # ==================== УПРАВЛЕНИЕ ПОЗИЦИЯМИ ====================
    
    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """Получение информации о позиции"""
        with self._lock:
            return self._positions.get(symbol)
    
    def set_position(self, symbol: str, side: Optional[str], size: float,
                    entry_price: float = 0.0, avg_price: float = 0.0,
                    unrealized_pnl: float = 0.0, leverage: float = 1.0,
                    strategy_name: Optional[str] = None) -> None:
        """Установка информации о позиции"""
        with self._lock:
            if symbol not in self._positions:
                self._positions[symbol] = PositionInfo(symbol=symbol)

            pos = self._positions[symbol]
            pos.side = PositionSide(side) if side else None
            pos.size = size
            pos.entry_price = entry_price
            pos.avg_price = avg_price or entry_price
            pos.unrealized_pnl = unrealized_pnl
            pos.leverage = leverage
            pos.strategy_name = strategy_name
            pos.last_update = datetime.now()
            
            # Если позиция закрыта
            if size == 0.0:
                pos.side = None
                pos.entry_price = 0.0
                pos.avg_price = 0.0
                pos.unrealized_pnl = 0.0
            
            self.logger.debug(f"📊 Позиция обновлена {symbol}: {side} {size} @ {entry_price}")
    
    def update_position_pnl(self, symbol: str, current_price: float) -> None:
        """Обновление P&L позиции по текущей цене"""
        with self._lock:
            if symbol not in self._positions:
                return
                
            pos = self._positions[symbol]
            if not pos.is_active or pos.entry_price == 0:
                return
            
            # Рассчитываем unrealized P&L
            if pos.is_long:
                pos.unrealized_pnl = (current_price - pos.entry_price) * pos.size
            elif pos.is_short:
                pos.unrealized_pnl = (pos.entry_price - current_price) * pos.size
            
            pos.last_update = datetime.now()
    
    def close_position(self, symbol: str, exit_price: float, realized_pnl: float = None) -> Optional[PositionInfo]:
        """Закрытие позиции с расчетом realized P&L"""
        with self._lock:
            if symbol not in self._positions:
                return None
            
            pos = self._positions[symbol]
            if not pos.is_active:
                return None
            
            # Рассчитываем realized P&L если не передан
            if realized_pnl is None:
                if pos.is_long:
                    realized_pnl = (exit_price - pos.entry_price) * pos.size
                elif pos.is_short:
                    realized_pnl = (pos.entry_price - exit_price) * pos.size
            
            # Обновляем статистику
            self._global_stats['total_trades'] += 1
            self._global_stats['total_pnl'] += realized_pnl
            self._global_stats['daily_pnl'] += realized_pnl
            self._global_stats['last_trade_time'] = datetime.now()
            
            if realized_pnl > 0:
                self._global_stats['winning_trades'] += 1
            else:
                self._global_stats['losing_trades'] += 1
            
            # Закрываем позицию
            closed_position = PositionInfo(
                symbol=pos.symbol,
                side=pos.side,
                size=pos.size,
                entry_price=pos.entry_price,
                unrealized_pnl=pos.unrealized_pnl,
                realized_pnl=realized_pnl,
                last_update=datetime.now()
            )
            
            # Очищаем позицию
            pos.size = 0.0
            pos.side = None
            pos.entry_price = 0.0
            pos.avg_price = 0.0
            pos.unrealized_pnl = 0.0
            pos.realized_pnl = realized_pnl
            pos.strategy_name = None  # Очищаем владельца
            
            self.logger.info(f"📊 Позиция закрыта {symbol}: P&L={realized_pnl:.2f}")
            return closed_position
    
    def clear_position(self, symbol: str) -> bool:
        """
        Принудительная очистка позиции без расчета P&L
        Используется для синхронизации с биржей
        
        Args:
            symbol: Символ для очистки
            
        Returns:
            bool: True если позиция была очищена
        """
        with self._lock:
            if symbol not in self._positions:
                return False
            
            pos = self._positions[symbol]
            if not pos.is_active:
                return False
            
            # Просто очищаем позицию без статистики
            pos.size = 0.0
            pos.side = None
            pos.entry_price = 0.0
            pos.avg_price = 0.0
            pos.unrealized_pnl = 0.0
            pos.realized_pnl = 0.0
            pos.strategy_name = None  # Очищаем владельца
            pos.last_update = datetime.now()
            
            self.logger.info(f"🧹 Позиция принудительно очищена: {symbol}")
            return True
    
    def get_all_positions(self) -> Dict[str, PositionInfo]:
        """Получение всех позиций"""
        with self._lock:
            return self._positions.copy()
    
    def get_active_positions(self) -> Dict[str, PositionInfo]:
        """Получение только активных позиций"""
        with self._lock:
            return {
                symbol: pos for symbol, pos in self._positions.items() 
                if pos.is_active
            }
    
    # ==================== ГЛОБАЛЬНЫЕ ФЛАГИ ====================
    
    @property
    def emergency_stop(self) -> bool:
        """Состояние аварийной остановки"""
        with self._lock:
            return self._emergency_stop
    
    @emergency_stop.setter
    def emergency_stop(self, value: bool) -> None:
        """Установка аварийной остановки"""
        with self._lock:
            if value != self._emergency_stop:
                self._emergency_stop = value
                if value:
                    self.logger.critical("🚨 АВАРИЙНАЯ ОСТАНОВКА АКТИВИРОВАНА!")
                else:
                    self.logger.info("✅ Аварийная остановка отключена")
    
    @property
    def trading_enabled(self) -> bool:
        """Состояние торговли"""
        with self._lock:
            return self._trading_enabled and not self._emergency_stop
    
    @trading_enabled.setter
    def trading_enabled(self, value: bool) -> None:
        """Включение/отключение торговли"""
        with self._lock:
            self._trading_enabled = value
            status = "включена" if value else "отключена"
            self.logger.info(f"📊 Торговля {status}")
    
    @property
    def risk_limits_exceeded(self) -> bool:
        """Состояние превышения лимитов риска"""
        with self._lock:
            return self._risk_limits_exceeded
    
    @risk_limits_exceeded.setter  
    def risk_limits_exceeded(self, value: bool) -> None:
        """Установка флага превышения лимитов"""
        with self._lock:
            self._risk_limits_exceeded = value
            if value:
                self.logger.warning("⚠️ ПРЕВЫШЕНЫ ЛИМИТЫ РИСКА!")
    
    # ==================== СТАТИСТИКА ====================
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Получение глобальной статистики"""
        with self._lock:
            stats = self._global_stats.copy()
            
            # Добавляем рассчитанные метрики
            total_trades = stats['total_trades']
            if total_trades > 0:
                stats['win_rate'] = (stats['winning_trades'] / total_trades) * 100
                stats['avg_pnl'] = stats['total_pnl'] / total_trades
            else:
                stats['win_rate'] = 0.0
                stats['avg_pnl'] = 0.0
            
            # Добавляем текущий unrealized P&L
            total_unrealized = sum(
                pos.unrealized_pnl for pos in self._positions.values() 
                if pos.is_active
            )
            stats['unrealized_pnl'] = total_unrealized
            stats['total_equity'] = stats['total_pnl'] + total_unrealized
            
            return stats
    
    def update_strategy_stats(self, strategy_name: str, trade_pnl: float, 
                            signal_strength: float = None) -> None:
        """Обновление статистики стратегии"""
        with self._lock:
            if strategy_name not in self._strategy_stats:
                self._strategy_stats[strategy_name] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0.0,
                    'avg_pnl': 0.0,
                    'win_rate': 0.0,
                    'last_trade_time': None,
                    'signal_strengths': []
                }
            
            stats = self._strategy_stats[strategy_name]
            stats['total_trades'] += 1
            stats['total_pnl'] += trade_pnl
            stats['last_trade_time'] = datetime.now()
            
            if trade_pnl > 0:
                stats['winning_trades'] += 1
            else:
                stats['losing_trades'] += 1
            
            # Рассчитываем метрики
            stats['win_rate'] = (stats['winning_trades'] / stats['total_trades']) * 100
            stats['avg_pnl'] = stats['total_pnl'] / stats['total_trades']
            
            # Сохраняем силу сигнала
            if signal_strength is not None:
                stats['signal_strengths'].append(signal_strength)
                # Храним только последние 100 значений
                if len(stats['signal_strengths']) > 100:
                    stats['signal_strengths'] = stats['signal_strengths'][-100:]
    
    def get_strategy_stats(self, strategy_name: str = None) -> Dict[str, Any]:
        """Получение статистики стратегий"""
        with self._lock:
            if strategy_name:
                return self._strategy_stats.get(strategy_name, {})
            return self._strategy_stats.copy()
    
    # ==================== СИНХРОНИЗАЦИЯ ====================
    
    def sync_with_exchange(self, symbol: str, exchange_position: Dict[str, Any]) -> bool:
        """Синхронизация с данными биржи"""
        with self._lock:
            try:
                # Отслеживаем частоту синхронизации
                now = datetime.now()
                if symbol not in self._sync_counts:
                    self._sync_counts[symbol] = 0
                    self._last_sync_time[symbol] = now
                
                self._sync_counts[symbol] += 1
                
                # Ограничиваем частоту логирования
                time_since_last = (now - self._last_sync_time[symbol]).total_seconds()
                if time_since_last > 30:  # Логируем каждые 30 секунд
                    self.logger.debug(f"📡 Синхронизация {symbol}: {self._sync_counts[symbol]} раз за {time_since_last:.1f}s")
                    self._last_sync_time[symbol] = now
                    self._sync_counts[symbol] = 0
                
                # Извлекаем данные из ответа биржи
                size = float(exchange_position.get('size', 0))
                side = exchange_position.get('side') if size > 0 else None
                avg_price = float(exchange_position.get('avgPrice', 0))
                unrealized_pnl = float(exchange_position.get('unrealisedPnl', 0))
                
                # Обновляем позицию
                self.set_position(
                    symbol=symbol,
                    side=side,
                    size=size,
                    entry_price=avg_price,
                    avg_price=avg_price,
                    unrealized_pnl=unrealized_pnl
                )
                
                return True
                
            except Exception as e:
                self.logger.error(f"❌ Ошибка синхронизации {symbol}: {e}")
                return False
    
    # ==================== ДИАГНОСТИКА ====================
    
    def get_diagnostic_info(self) -> Dict[str, Any]:
        """Получение диагностической информации"""
        with self._lock:
            return {
                'positions_count': len(self._positions),
                'active_positions_count': len(self.get_active_positions()),
                'strategies_count': len(self._strategy_stats),
                'emergency_stop': self._emergency_stop,
                'trading_enabled': self._trading_enabled,
                'risk_limits_exceeded': self._risk_limits_exceeded,
                'total_sync_operations': sum(self._sync_counts.values()),
                'uptime_seconds': (datetime.now() - self._global_stats['start_time']).total_seconds()
            }
    
    def validate_state_consistency(self) -> List[str]:
        """Проверка консистентности состояния"""
        with self._lock:
            issues = []
            
            # Проверяем позиции
            for symbol, pos in self._positions.items():
                if pos.size < 0:
                    issues.append(f"Отрицательный размер позиции {symbol}: {pos.size}")
                
                if pos.is_active and pos.entry_price <= 0:
                    issues.append(f"Активная позиция {symbol} с нулевой ценой входа")
                
                if pos.side and not pos.is_active:
                    issues.append(f"Неактивная позиция {symbol} имеет сторону {pos.side}")
            
            # Проверяем статистику
            stats = self._global_stats
            if stats['winning_trades'] + stats['losing_trades'] != stats['total_trades']:
                issues.append("Некорректная статистика трейдов")
            
            return issues


# 🌍 ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР СОСТОЯНИЯ БОТА
_bot_state_instance = None
_bot_state_lock = threading.RLock()


def get_bot_state() -> ThreadSafeBotState:
    """Получение синглтона состояния бота"""
    global _bot_state_instance
    
    if _bot_state_instance is None:
        with _bot_state_lock:
            if _bot_state_instance is None:
                _bot_state_instance = ThreadSafeBotState()
    
    return _bot_state_instance


def reset_bot_state():
    """Сброс состояния бота (для тестов)"""
    global _bot_state_instance
    with _bot_state_lock:
        _bot_state_instance = None