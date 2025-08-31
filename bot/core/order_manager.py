# bot/core/order_manager.py
"""
💀 КРИТИЧЕСКИЙ КОМПОНЕНТ: Thread-Safe Order Manager
ПОЛНАЯ СИНХРОНИЗАЦИЯ ВСЕХ ТОРГОВЫХ ОПЕРАЦИЙ
ZERO TOLERANCE К ДУБЛИРОВАННЫМ ОРДЕРАМ!
"""

import threading
import time
import logging
from typing import Dict, Optional, Tuple, Any, List
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass

from bot.core.exceptions import OrderRejectionError, RateLimitError, PositionConflictError


@dataclass
class OrderRequest:
    """Структура запроса на создание ордера"""
    symbol: str
    side: str
    order_type: str
    qty: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reduce_only: bool = False
    position_idx: Optional[int] = None
    strategy_name: str = "unknown"
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ThreadSafeOrderManager:
    """
    🚨 КРИТИЧЕСКИЙ МЕНЕДЖЕР ОРДЕРОВ С ПОЛНОЙ СИНХРОНИЗАЦИЕЙ
    
    Функции:
    - Блокировка дублированных ордеров
    - Rate limiting на уровне символа
    - Контроль состояния позиций
    - Аварийная остановка
    - Полная thread-safety
    """
    
    def __init__(self, max_orders_per_minute: int = 10):
        # 🔒 ОСНОВНЫЕ БЛОКИРОВКИ
        self._global_lock = threading.RLock()
        self._symbol_locks: Dict[str, threading.RLock] = {}
        self._lock_creation_lock = threading.RLock()
        
        # 📊 СОСТОЯНИЕ МЕНЕДЖЕРА
        self._emergency_stop = False
        self._max_orders_per_minute = max_orders_per_minute
        
        # 📈 ОТСЛЕЖИВАНИЕ ПОЗИЦИЙ ПО СИМВОЛАМ
        self._active_positions: Dict[str, Dict[str, Any]] = {}
        self._pending_orders: Dict[str, Dict[str, Any]] = {}
        
        # ⏰ RATE LIMITING
        self._order_timestamps: Dict[str, list] = defaultdict(list)
        self._last_order_time: Dict[str, datetime] = {}
        
        # 📝 ЛОГИРОВАНИЕ
        self.logger = logging.getLogger('order_manager')
        self.logger.setLevel(logging.INFO)
        
        # 🔢 СТАТИСТИКА
        self._stats = {
            'total_orders': 0,
            'rejected_orders': 0,
            'duplicate_blocks': 0,
            'rate_limit_blocks': 0
        }
        
        self.logger.info("🛡️ ThreadSafeOrderManager инициализирован с максимальной защитой")
    
    def get_symbol_lock(self, symbol: str) -> threading.RLock:
        """Получение или создание блокировки для символа"""
        with self._lock_creation_lock:
            if symbol not in self._symbol_locks:
                self._symbol_locks[symbol] = threading.RLock()
                self.logger.debug(f"🔒 Создана блокировка для {symbol}")
            return self._symbol_locks[symbol]
    
    def set_emergency_stop(self, stop: bool = True):
        """🚨 АВАРИЙНАЯ ОСТАНОВКА ВСЕХ ОРДЕРОВ"""
        with self._global_lock:
            self._emergency_stop = stop
            if stop:
                self.logger.critical("🚨 АВАРИЙНАЯ ОСТАНОВКА АКТИВИРОВАНА! ВСЕ ОРДЕРА ЗАБЛОКИРОВАНЫ!")
            else:
                self.logger.info("✅ Аварийная остановка отключена")
    
    def _check_rate_limit(self, symbol: str) -> Tuple[bool, str]:
        """Проверка лимита частоты ордеров"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Очищаем старые записи
        self._order_timestamps[symbol] = [
            ts for ts in self._order_timestamps[symbol] 
            if ts > minute_ago
        ]
        
        if len(self._order_timestamps[symbol]) >= self._max_orders_per_minute:
            self._stats['rate_limit_blocks'] += 1
            return False, f"Rate limit exceeded: {len(self._order_timestamps[symbol])}/{self._max_orders_per_minute} orders per minute"
        
        # Проверяем минимальный интервал между ордерами (2 секунды)
        if symbol in self._last_order_time:
            time_since_last = (now - self._last_order_time[symbol]).total_seconds()
            if time_since_last < 2.0:
                return False, f"Too frequent orders: {time_since_last:.2f}s since last order (min 2.0s)"
        
        return True, "OK"
    
    def _check_position_conflict(self, symbol: str, request: OrderRequest, api) -> Tuple[bool, str]:
        """Проверка конфликтов с текущими позициями"""
        try:
            # Получаем актуальную информацию о позициях
            positions_response = api.get_positions(symbol)
            if not positions_response or positions_response.get('retCode') != 0:
                return False, "Не удалось получить информацию о позициях"
            
            position_list = positions_response['result']['list']
            active_position = None
            
            for pos in position_list:
                if float(pos.get('size', 0)) > 0:
                    active_position = pos
                    break
            
            # Обновляем локальное состояние позиции
            if active_position:
                self._active_positions[symbol] = {
                    'side': active_position['side'],
                    'size': float(active_position['size']),
                    'avg_price': float(active_position['avgPrice']),
                    'updated_at': datetime.now()
                }
                
                # Проверяем конфликт направлений
                current_side = active_position['side']
                if not request.reduce_only and current_side != request.side:
                    return False, f"Конфликт направлений: текущая позиция {current_side}, запрос {request.side}"
                    
            else:
                # Нет активной позиции
                if symbol in self._active_positions:
                    del self._active_positions[symbol]
                
                if request.reduce_only:
                    return False, "Нельзя создать reduce_only ордер без активной позиции"
            
            return True, "OK"
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки позиции {symbol}: {e}")
            return False, f"Ошибка проверки позиции: {str(e)}"
    
    def _check_duplicate_order(self, symbol: str, request: OrderRequest) -> Tuple[bool, str]:
        """Проверка дублированных ордеров"""
        if symbol not in self._pending_orders:
            self._pending_orders[symbol] = {}
        
        # Создаем ключ для идентификации похожих ордеров
        order_key = f"{request.side}_{request.order_type}_{request.qty}_{request.price}_{request.strategy_name}"
        
        if order_key in self._pending_orders[symbol]:
            pending = self._pending_orders[symbol][order_key]
            time_diff = (datetime.now() - pending['created_at']).total_seconds()
            
            # Блокируем дубликаты в течение 10 секунд
            if time_diff < 10:
                self._stats['duplicate_blocks'] += 1
                return False, f"Дублированный ордер заблокирован (создан {time_diff:.1f}s назад)"
        
        return True, "OK"
    
    def create_order_safe(self, api, request: OrderRequest) -> Optional[Dict[str, Any]]:
        """
        🛡️ БЕЗОПАСНОЕ СОЗДАНИЕ ОРДЕРА С ПОЛНОЙ СИНХРОНИЗАЦИЕЙ
        
        Args:
            api: API объект для создания ордера
            request: Запрос на создание ордера
            
        Returns:
            Результат создания ордера или None при отклонении
            
        Raises:
            OrderRejectionError: При отклонении ордера
            RateLimitError: При превышении лимитов
            PositionConflictError: При конфликте позиций
        """
        symbol = request.symbol
        
        # 🔒 БЛОКИРУЕМ СИМВОЛ
        with self.get_symbol_lock(symbol):
            try:
                self.logger.info(f"🔍 Обработка ордера {request.strategy_name}: {request.side} {request.qty} {symbol}")
                
                # 1. 🚨 ПРОВЕРКА АВАРИЙНОЙ ОСТАНОВКИ
                if self._emergency_stop:
                    raise OrderRejectionError("🚨 АВАРИЙНАЯ ОСТАНОВКА: Все ордера заблокированы")
                
                # 2. ⏰ ПРОВЕРКА RATE LIMIT
                rate_ok, rate_msg = self._check_rate_limit(symbol)
                if not rate_ok:
                    raise RateLimitError(f"Rate limit для {symbol}: {rate_msg}")
                
                # 3. 🔄 ПРОВЕРКА ДУБЛИКАТОВ
                dup_ok, dup_msg = self._check_duplicate_order(symbol, request)
                if not dup_ok:
                    raise OrderRejectionError(f"Дублированный ордер для {symbol}: {dup_msg}")
                
                # 4. 📈 ПРОВЕРКА КОНФЛИКТОВ ПОЗИЦИЙ
                pos_ok, pos_msg = self._check_position_conflict(symbol, request, api)
                if not pos_ok:
                    raise PositionConflictError(f"Конфликт позиции для {symbol}: {pos_msg}")
                
                # 5. 📝 РЕГИСТРАЦИЯ PENDING ОРДЕРА
                order_key = f"{request.side}_{request.order_type}_{request.qty}_{request.price}_{request.strategy_name}"
                self._pending_orders[symbol][order_key] = {
                    'request': request,
                    'created_at': datetime.now()
                }
                
                # 6. 🎯 СОЗДАНИЕ ОРДЕРА
                order_response = api.create_order(
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    qty=request.qty,
                    price=request.price,
                    stop_loss=request.stop_loss,
                    take_profit=request.take_profit,
                    reduce_only=request.reduce_only,
                    position_idx=request.position_idx
                )
                
                # 7. ✅ ОБРАБОТКА РЕЗУЛЬТАТА
                if order_response and order_response.get('retCode') == 0:
                    # Успешно создан
                    now = datetime.now()
                    self._order_timestamps[symbol].append(now)
                    self._last_order_time[symbol] = now
                    self._stats['total_orders'] += 1
                    
                    # Очищаем pending ордер
                    if order_key in self._pending_orders[symbol]:
                        del self._pending_orders[symbol][order_key]
                    
                    self.logger.info(f"✅ Ордер успешно создан для {symbol}: {order_response.get('result', {}).get('orderId', 'N/A')}")
                    return order_response
                    
                else:
                    # Ошибка создания
                    error_msg = order_response.get('retMsg', 'Unknown error') if order_response else 'No response'
                    self._stats['rejected_orders'] += 1
                    
                    # Очищаем pending ордер
                    if order_key in self._pending_orders[symbol]:
                        del self._pending_orders[symbol][order_key]
                    
                    raise OrderRejectionError(f"API отклонил ордер для {symbol}: {error_msg}")
                
            except (OrderRejectionError, RateLimitError, PositionConflictError):
                # Перебрасываем наши исключения
                raise
                
            except Exception as e:
                # Неожиданная ошибка
                self._stats['rejected_orders'] += 1
                self.logger.error(f"💥 Неожиданная ошибка при создании ордера {symbol}: {e}")
                
                # Очищаем pending ордер при ошибке
                order_key = f"{request.side}_{request.order_type}_{request.qty}_{request.price}_{request.strategy_name}"
                if symbol in self._pending_orders and order_key in self._pending_orders[symbol]:
                    del self._pending_orders[symbol][order_key]
                
                raise OrderRejectionError(f"Неожиданная ошибка для {symbol}: {str(e)}")
    
    def get_position_state(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Получение актуального состояния позиции"""
        with self.get_symbol_lock(symbol):
            return self._active_positions.get(symbol, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики работы менеджера"""
        with self._global_lock:
            return {
                **self._stats,
                'emergency_stop': self._emergency_stop,
                'active_positions': len(self._active_positions),
                'pending_orders': sum(len(orders) for orders in self._pending_orders.values()),
                'symbol_locks': len(self._symbol_locks)
            }
    
    def cleanup_old_pending(self, max_age_seconds: int = 60):
        """Очистка старых pending ордеров"""
        with self._global_lock:
            cutoff_time = datetime.now() - timedelta(seconds=max_age_seconds)
            
            for symbol in list(self._pending_orders.keys()):
                orders_to_remove = []
                for order_key, order_info in self._pending_orders[symbol].items():
                    if order_info['created_at'] < cutoff_time:
                        orders_to_remove.append(order_key)
                
                for order_key in orders_to_remove:
                    del self._pending_orders[symbol][order_key]
                    self.logger.warning(f"🧹 Удален старый pending ордер: {order_key}")
                
                # Удаляем пустые символы
                if not self._pending_orders[symbol]:
                    del self._pending_orders[symbol]


# 🌍 ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР МЕНЕДЖЕРА ОРДЕРОВ
_order_manager_instance = None
_order_manager_lock = threading.RLock()


def get_order_manager() -> ThreadSafeOrderManager:
    """Получение синглтона менеджера ордеров"""
    global _order_manager_instance
    
    if _order_manager_instance is None:
        with _order_manager_lock:
            if _order_manager_instance is None:
                _order_manager_instance = ThreadSafeOrderManager()
    
    return _order_manager_instance


def reset_order_manager():
    """Сброс менеджера ордеров (для тестов)"""
    global _order_manager_instance
    with _order_manager_lock:
        _order_manager_instance = None


def validate_order_parameters(symbol: str, side: str, order_type: str, qty: float, 
                             price: Optional[float] = None, 
                             stop_loss: Optional[float] = None,
                             take_profit: Optional[float] = None) -> Tuple[bool, List[str]]:
    """
    Валидация параметров ордера
    
    Args:
        symbol: Торговый инструмент
        side: Сторона (Buy/Sell)
        order_type: Тип ордера (Market/Limit)
        qty: Количество
        price: Цена (для лимитных ордеров)
        stop_loss: Стоп-лосс
        take_profit: Тейк-профит
        
    Returns:
        Tuple[bool, List[str]]: (валиден, список ошибок)
    """
    errors = []
    
    # Валидация символа
    if not symbol or not symbol.strip():
        errors.append("Символ не может быть пустым")
    elif not isinstance(symbol, str):
        errors.append("Символ должен быть строкой")
    elif len(symbol) < 3:
        errors.append("Символ слишком короткий")
    
    # Валидация стороны
    valid_sides = ['Buy', 'Sell', 'BUY', 'SELL', 'buy', 'sell']
    if side not in valid_sides:
        errors.append(f"Неверная сторона: {side}. Допустимые: {valid_sides}")
    
    # Валидация типа ордера
    valid_order_types = ['Market', 'Limit', 'MARKET', 'LIMIT', 'market', 'limit']
    if order_type not in valid_order_types:
        errors.append(f"Неверный тип ордера: {order_type}. Допустимые: {valid_order_types}")
    
    # Валидация количества
    if not isinstance(qty, (int, float)):
        errors.append("Количество должно быть числом")
    elif qty <= 0:
        errors.append("Количество должно быть больше нуля")
    elif qty > 1000:  # Разумный лимит
        errors.append("Количество слишком большое (>1000)")
    
    # Валидация цены для лимитных ордеров
    if order_type.lower() == 'limit':
        if price is None:
            errors.append("Цена обязательна для лимитных ордеров")
        elif not isinstance(price, (int, float)):
            errors.append("Цена должна быть числом")
        elif price <= 0:
            errors.append("Цена должна быть больше нуля")
    
    # Валидация стоп-лосс
    if stop_loss is not None:
        if not isinstance(stop_loss, (int, float)):
            errors.append("Стоп-лосс должен быть числом")
        elif stop_loss <= 0:
            errors.append("Стоп-лосс должен быть больше нуля")
    
    # Валидация тейк-профит
    if take_profit is not None:
        if not isinstance(take_profit, (int, float)):
            errors.append("Тейк-профит должен быть числом")
        elif take_profit <= 0:
            errors.append("Тейк-профит должен быть больше нуля")
    
    # Логическая валидация стопов
    if price and stop_loss and take_profit:
        if side.lower() in ['buy', 'long']:
            if stop_loss >= price:
                errors.append("Стоп-лосс для покупки должен быть ниже цены входа")
            if take_profit <= price:
                errors.append("Тейк-профит для покупки должен быть выше цены входа")
        elif side.lower() in ['sell', 'short']:
            if stop_loss <= price:
                errors.append("Стоп-лосс для продажи должен быть выше цены входа")
            if take_profit >= price:
                errors.append("Тейк-профит для продажи должен быть ниже цены входа")
    
    is_valid = len(errors) == 0
    return is_valid, errors