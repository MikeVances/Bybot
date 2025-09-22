# bot/core/rate_limiter.py
"""
💀 КРИТИЧЕСКИЙ КОМПОНЕНТ: Жесточайший Rate Limiter
ПОЛНАЯ ЗАЩИТА ОТ ПРЕВЫШЕНИЯ ЛИМИТОВ БИРЖИ
EMERGENCY SHUTDOWN ПРИ МАЛЕЙШЕЙ УГРОЗЕ!
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import deque, defaultdict
from dataclasses import dataclass
import logging

from bot.core.exceptions import RateLimitError, EmergencyStopError


@dataclass
class RateLimitConfig:
    """Конфигурация лимитов для различных типов запросов"""
    requests_per_minute: int = 10
    requests_per_second: int = 2
    burst_limit: int = 5
    cooldown_seconds: int = 60
    emergency_threshold: float = 0.8  # При достижении 80% лимита - предупреждение


class RateLimitViolation:
    """Информация о нарушении лимита"""
    def __init__(self, limit_type: str, current_count: int, limit_value: int, 
                 timestamp: datetime, client_id: str = "default"):
        self.limit_type = limit_type
        self.current_count = current_count
        self.limit_value = limit_value
        self.timestamp = timestamp
        self.client_id = client_id
        self.severity = self._calculate_severity()
    
    def _calculate_severity(self) -> str:
        """Расчёт серьёзности нарушения"""
        ratio = self.current_count / self.limit_value
        if ratio >= 1.0:
            return "CRITICAL"
        elif ratio >= 0.9:
            return "HIGH"
        elif ratio >= 0.7:
            return "MEDIUM"
        else:
            return "LOW"


class AggressiveRateLimiter:
    """
    💀 АГРЕССИВНЫЙ RATE LIMITER С EMERGENCY SHUTDOWN
    
    Особенности:
    - Жесточайшие лимиты для каждого типа запроса
    - Автоматический emergency shutdown при угрозе
    - Полное логирование всех попыток
    - Блокировка клиентов-нарушителей
    - Глобальные и пер-символьные лимиты
    """
    
    def __init__(self):
        # 🔒 ОСНОВНЫЕ БЛОКИРОВКИ
        self._lock = threading.RLock()
        self._client_locks = defaultdict(lambda: threading.RLock())
        
        # 📊 ОТСЛЕЖИВАНИЕ ЗАПРОСОВ
        self._request_timestamps: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        self._violation_history: List[RateLimitViolation] = []
        
        # ⚙️ КОНФИГУРАЦИЯ ЛИМИТОВ
        self._limits: Dict[str, RateLimitConfig] = {
            'order_create': RateLimitConfig(
                requests_per_minute=20,
                requests_per_second=1,
                burst_limit=3,
                cooldown_seconds=30,
                emergency_threshold=0.7
            ),
            'order_cancel': RateLimitConfig(
                requests_per_minute=30,
                requests_per_second=2,
                burst_limit=5,
                cooldown_seconds=15,
                emergency_threshold=0.8
            ),
            'position_query': RateLimitConfig(
                requests_per_minute=60,
                requests_per_second=5,
                burst_limit=10,
                cooldown_seconds=10,
                emergency_threshold=0.9
            ),
            'balance_query': RateLimitConfig(
                requests_per_minute=30,
                requests_per_second=3,
                burst_limit=5,
                cooldown_seconds=20,
                emergency_threshold=0.8
            ),
            'market_data': RateLimitConfig(
                requests_per_minute=120,
                requests_per_second=10,
                burst_limit=20,
                cooldown_seconds=5,
                emergency_threshold=0.95
            )
        }
        
        # 🚨 СИСТЕМА EMERGENCY SHUTDOWN
        self._emergency_stop = False
        self._emergency_reason = ""
        self._emergency_timestamp = None
        
        # 🔴 ЗАБЛОКИРОВАННЫЕ КЛИЕНТЫ
        self._banned_clients: Dict[str, datetime] = {}
        self._client_violation_counts = defaultdict(int)
        
        # 📊 ГЛОБАЛЬНЫЕ ЛИМИТЫ
        self._global_requests_per_minute = 200
        self._global_requests_per_second = 20

        # 🔄 АДАПТИВНЫЕ НАСТРОЙКИ
        self.adaptive_delays = {}
        self.success_streak = {}
        self.failure_streak = {}

        # 📝 СТАТИСТИКА
        self._stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'violations': 0,
            'emergency_activations': 0,
            'banned_clients': 0
        }
        
        # 📝 ЛОГИРОВАНИЕ
        self.logger = logging.getLogger('rate_limiter')
        self.logger.setLevel(logging.INFO)
        
        # 🧹 ФОНОВЫЙ ПОТОК ДЛЯ ОЧИСТКИ
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        
        self.logger.info("💀 AggressiveRateLimiter активирован с ЖЕСТОЧАЙШИМИ лимитами")
    
    def acquire(self, request_type: str, client_id: str = "default", 
               symbol: str = None, metadata: Dict[str, Any] = None) -> bool:
        """
        🛡️ ПОЛУЧЕНИЕ РАЗРЕШЕНИЯ НА ЗАПРОС
        
        Args:
            request_type: Тип запроса (order_create, position_query, etc.)
            client_id: Идентификатор клиента
            symbol: Торговый символ (опционально)
            metadata: Дополнительная информация
            
        Returns:
            True если запрос разрешён, иначе RateLimitError
            
        Raises:
            RateLimitError: При превышении лимитов
            EmergencyStopError: При активированном emergency stop
        """
        with self._lock:
            try:
                self._stats['total_requests'] += 1
                
                # 1. 🚨 ПРОВЕРКА EMERGENCY STOP
                if self._emergency_stop:
                    raise EmergencyStopError(
                        f"🚨 EMERGENCY STOP АКТИВЕН: {self._emergency_reason} "
                        f"(с {self._emergency_timestamp})"
                    )
                
                # 2. 🔴 ПРОВЕРКА ЗАБЛОКИРОВАННЫХ КЛИЕНТОВ
                if client_id in self._banned_clients:
                    ban_time = self._banned_clients[client_id]
                    if datetime.now() < ban_time:
                        remaining = (ban_time - datetime.now()).total_seconds()
                        raise RateLimitError(
                            f"🚫 Клиент {client_id} заблокирован на {remaining:.0f} секунд "
                            f"за нарушение лимитов"
                        )
                    else:
                        # Разблокируем клиента
                        del self._banned_clients[client_id]
                        self._client_violation_counts[client_id] = 0
                        self.logger.info(f"✅ Клиент {client_id} разблокирован")
                
                # 3. 📊 ПРОВЕРКА ГЛОБАЛЬНЫХ ЛИМИТОВ
                self._check_global_limits()
                
                # 4. 🎯 ПРОВЕРКА СПЕЦИФИЧНЫХ ЛИМИТОВ
                self._check_specific_limits(request_type, client_id, symbol)
                
                # 5. ✅ РЕГИСТРАЦИЯ УСПЕШНОГО ЗАПРОСА
                now = datetime.now()
                self._register_request(request_type, client_id, symbol, now)
                
                # 6. ⚠️ ПРОВЕРКА ПРИБЛИЖЕНИЯ К ЛИМИТАМ
                self._check_approaching_limits(request_type, client_id)
                
                self.logger.debug(
                    f"✅ Запрос разрешён: {request_type} для {client_id}"
                    + (f" ({symbol})" if symbol else "")
                )
                
                return True
                
            except (RateLimitError, EmergencyStopError):
                self._stats['blocked_requests'] += 1
                raise
                
            except Exception as e:
                # Неожиданная ошибка - активируем emergency stop
                self._activate_emergency_stop(f"Неожиданная ошибка в rate limiter: {str(e)}")
                raise EmergencyStopError(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
    
    def _check_global_limits(self) -> None:
        """Проверка глобальных лимитов"""
        now = datetime.now()
        
        # Проверяем глобальные лимиты за последнюю минуту
        minute_ago = now - timedelta(minutes=1)
        second_ago = now - timedelta(seconds=1)
        
        total_minute_requests = 0
        total_second_requests = 0
        
        for client_data in self._request_timestamps.values():
            for symbol_data in client_data.values():
                for request_time in symbol_data:
                    if request_time > minute_ago:
                        total_minute_requests += 1
                    if request_time > second_ago:
                        total_second_requests += 1
        
        # Проверяем лимиты
        if total_minute_requests >= self._global_requests_per_minute:
            self._activate_emergency_stop(
                f"Превышен глобальный лимит: {total_minute_requests}/{self._global_requests_per_minute} запросов в минуту"
            )
            raise RateLimitError(
                f"🚨 Глобальный лимит превышен: {total_minute_requests}/{self._global_requests_per_minute} запросов/мин"
            )
        
        if total_second_requests >= self._global_requests_per_second:
            raise RateLimitError(
                f"🚨 Глобальный лимит превышен: {total_second_requests}/{self._global_requests_per_second} запросов/сек"
            )
    
    def _check_specific_limits(self, request_type: str, client_id: str, symbol: str = None) -> None:
        """Проверка специфичных лимитов для типа запроса"""
        if request_type not in self._limits:
            # Для неизвестных типов используем самые жесткие лимиты
            config = RateLimitConfig(
                requests_per_minute=10,
                requests_per_second=1,
                burst_limit=2,
                cooldown_seconds=60,
                emergency_threshold=0.5
            )
        else:
            config = self._limits[request_type]
        
        # Создаем ключ для клиента и символа
        cache_key = f"{client_id}:{symbol}" if symbol else client_id
        
        if cache_key not in self._request_timestamps:
            self._request_timestamps[cache_key] = defaultdict(deque)
        
        timestamps = self._request_timestamps[cache_key][request_type]
        now = datetime.now()
        
        # Очищаем старые временные метки
        minute_ago = now - timedelta(minutes=1)
        second_ago = now - timedelta(seconds=1)
        
        while timestamps and timestamps[0] < minute_ago:
            timestamps.popleft()
        
        # Подсчитываем запросы
        minute_requests = len(timestamps)
        second_requests = sum(1 for ts in timestamps if ts > second_ago)
        
        # Проверяем лимиты
        if minute_requests >= config.requests_per_minute:
            violation = RateLimitViolation(
                f"{request_type}_per_minute", 
                minute_requests, 
                config.requests_per_minute,
                now, 
                client_id
            )
            self._handle_violation(violation)
            
            raise RateLimitError(
                f"🚫 Лимит {request_type}: {minute_requests}/{config.requests_per_minute} запросов/мин "
                f"для клиента {client_id}"
            )
        
        if second_requests >= config.requests_per_second:
            raise RateLimitError(
                f"🚫 Лимит {request_type}: {second_requests}/{config.requests_per_second} запросов/сек "
                f"для клиента {client_id}"
            )
        
        # Проверяем burst лимит (последние 10 секунд)
        burst_ago = now - timedelta(seconds=10)
        burst_requests = sum(1 for ts in timestamps if ts > burst_ago)
        
        if burst_requests >= config.burst_limit:
            raise RateLimitError(
                f"🚫 Burst лимит {request_type}: {burst_requests}/{config.burst_limit} запросов за 10 сек "
                f"для клиента {client_id}"
            )
    
    def _register_request(self, request_type: str, client_id: str, symbol: str, timestamp: datetime) -> None:
        """Регистрация выполненного запроса"""
        cache_key = f"{client_id}:{symbol}" if symbol else client_id
        self._request_timestamps[cache_key][request_type].append(timestamp)
        
        # Ограничиваем размер deque
        if len(self._request_timestamps[cache_key][request_type]) > 1000:
            self._request_timestamps[cache_key][request_type].popleft()
    
    def _check_approaching_limits(self, request_type: str, client_id: str) -> None:
        """Проверка приближения к лимитам"""
        if request_type not in self._limits:
            return
        
        config = self._limits[request_type]
        cache_key = client_id
        
        if cache_key in self._request_timestamps:
            timestamps = self._request_timestamps[cache_key][request_type]
            now = datetime.now()
            minute_ago = now - timedelta(minutes=1)
            
            minute_requests = sum(1 for ts in timestamps if ts > minute_ago)
            threshold = int(config.requests_per_minute * config.emergency_threshold)
            
            if minute_requests >= threshold:
                self.logger.warning(
                    f"⚠️ ПРИБЛИЖЕНИЕ К ЛИМИТУ: {request_type} для {client_id}: "
                    f"{minute_requests}/{config.requests_per_minute} "
                    f"(порог {config.emergency_threshold:.0%})"
                )
    
    def _handle_violation(self, violation: RateLimitViolation) -> None:
        """Обработка нарушения лимитов"""
        self._violation_history.append(violation)
        self._stats['violations'] += 1
        self._client_violation_counts[violation.client_id] += 1
        
        client_violations = self._client_violation_counts[violation.client_id]
        
        self.logger.error(
            f"🚫 НАРУШЕНИЕ ЛИМИТА: {violation.limit_type} "
            f"({violation.current_count}/{violation.limit_value}) "
            f"клиент {violation.client_id} (нарушений: {client_violations})"
        )
        
        # Блокируем клиента при множественных нарушениях
        if client_violations >= 3:
            ban_duration = min(300, 60 * client_violations)  # До 5 минут
            ban_until = datetime.now() + timedelta(seconds=ban_duration)
            
            self._banned_clients[violation.client_id] = ban_until
            self._stats['banned_clients'] += 1
            
            self.logger.critical(
                f"🚫 КЛИЕНТ ЗАБЛОКИРОВАН: {violation.client_id} на {ban_duration} секунд "
                f"за {client_violations} нарушений"
            )
        
        # Активируем emergency stop при критических нарушениях
        if violation.severity == "CRITICAL" or client_violations >= 5:
            self._activate_emergency_stop(
                f"Критическое нарушение лимитов: {violation.limit_type} "
                f"клиентом {violation.client_id}"
            )
    
    def _activate_emergency_stop(self, reason: str) -> None:
        """Активация emergency stop"""
        if not self._emergency_stop:
            self._emergency_stop = True
            self._emergency_reason = reason
            self._emergency_timestamp = datetime.now()
            self._stats['emergency_activations'] += 1
            
            self.logger.critical(
                f"🚨 EMERGENCY STOP АКТИВИРОВАН: {reason}"
            )
            
            # Можно добавить уведомления (Telegram, email, etc.)
    
    def can_make_request(self, request_type: str, client_id: str = "default",
                        symbol: str = None) -> bool:
        """
        🔍 ПРОВЕРКА ВОЗМОЖНОСТИ ВЫПОЛНЕНИЯ ЗАПРОСА с адаптивными задержками
        Безопасная проверка без исключений

        Args:
            request_type: Тип запроса
            client_id: ID клиента
            symbol: Символ (опционально)

        Returns:
            bool: True если запрос можно выполнить
        """
        try:
            # Используем acquire для проверки, но не регистрируем запрос
            with self._lock:
                # Проверяем emergency stop
                if self._emergency_stop:
                    return False

                # Проверяем заблокированных клиентов
                if client_id in self._banned_clients:
                    ban_time = self._banned_clients[client_id]
                    if datetime.now() < ban_time:
                        return False

                # 🔄 АДАПТИВНЫЕ ЗАДЕРЖКИ на основе состояния API
                self._apply_adaptive_delays(request_type)

                # Проверяем лимиты без их нарушения
                return self._can_make_request_internal(request_type, client_id, symbol)

        except Exception:
            # В случае любой ошибки возвращаем False (безопасная позиция)
            return False
    
    def _can_make_request_internal(self, request_type: str, client_id: str, symbol: str) -> bool:
        """Внутренняя проверка лимитов без побочных эффектов"""
        try:
            # Получаем конфигурацию лимитов
            config = self._limits.get(request_type, self._limits['market_data'])
            now = datetime.now()
            
            # Создаем ключ для отслеживания
            key = f"{client_id}:{request_type}"
            if symbol:
                key += f":{symbol}"
            
            # Получаем временные метки запросов
            timestamps = self._request_timestamps[key][request_type]
            
            # Очищаем старые записи
            minute_ago = now - timedelta(minutes=1)
            second_ago = now - timedelta(seconds=1)
            
            while timestamps and timestamps[0] < minute_ago:
                timestamps.popleft()
            
            # Проверяем лимиты
            recent_requests_minute = len(timestamps)
            recent_requests_second = sum(1 for ts in timestamps if ts > second_ago)
            
            # Проверяем все лимиты
            if recent_requests_minute >= config.requests_per_minute:
                return False
            if recent_requests_second >= config.requests_per_second:
                return False
            
            return True
            
        except Exception:
            return False

    def _apply_adaptive_delays(self, endpoint: str):
        """Применение адаптивных задержек на основе состояния API"""
        try:
            # Получаем текущее состояние подключения
            from bot.core.enhanced_api_connection import get_enhanced_connection_manager
            connection_manager = get_enhanced_connection_manager()

            if connection_manager:
                health = connection_manager.get_connection_health()

                # Адаптируем задержки в зависимости от состояния API
                if health['state'] == 'degraded':
                    self.adaptive_delays[endpoint] = 2.0  # Удваиваем задержку
                elif health['state'] == 'unstable':
                    self.adaptive_delays[endpoint] = 3.0  # Утраиваем задержку
                elif health['state'] == 'healthy':
                    # Постепенно уменьшаем задержку при стабильной работе
                    current_delay = self.adaptive_delays.get(endpoint, 1.0)
                    self.adaptive_delays[endpoint] = max(0.5, current_delay * 0.9)
        except ImportError:
            # Enhanced connection manager недоступен
            pass

    def record_api_success(self, endpoint: str):
        """Записать успешный API вызов"""
        self.success_streak[endpoint] = self.success_streak.get(endpoint, 0) + 1
        self.failure_streak[endpoint] = 0

        # Уменьшаем задержку при успешных запросах
        if self.success_streak[endpoint] >= 5:
            current_delay = self.adaptive_delays.get(endpoint, 1.0)
            self.adaptive_delays[endpoint] = max(0.1, current_delay * 0.8)

    def record_api_failure(self, endpoint: str):
        """Записать неудачный API вызов"""
        self.failure_streak[endpoint] = self.failure_streak.get(endpoint, 0) + 1
        self.success_streak[endpoint] = 0

        # Увеличиваем задержку при неудачах
        current_delay = self.adaptive_delays.get(endpoint, 1.0)
        self.adaptive_delays[endpoint] = min(10.0, current_delay * 1.5)

    def deactivate_emergency_stop(self, admin_override: bool = False) -> bool:
        """Деактивация emergency stop (только администратором)"""
        if not admin_override:
            return False
        
        with self._lock:
            if self._emergency_stop:
                self._emergency_stop = False
                self._emergency_reason = ""
                self._emergency_timestamp = None
                
                self.logger.info("✅ EMERGENCY STOP ДЕАКТИВИРОВАН администратором")
                return True
            
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики rate limiter
        
        Returns:
            Dict: Статистика запросов и лимитов
        """
        with self._lock:
            return {
                'total_requests': self._stats['total_requests'],
                'blocked_requests': self._stats['blocked_requests'],
                'violations': self._stats['violations'],
                'emergency_activations': self._stats['emergency_activations'],
                'banned_clients': self._stats['banned_clients'],
                'emergency_stop_active': self._emergency_stop,
                'emergency_reason': self._emergency_reason,
                'active_bans': len(self._banned_clients),
                'total_violations': len(self._violation_history)
            }
    
    def get_client_status(self, client_id: str) -> Dict[str, Any]:
        """Получение статуса клиента"""
        with self._lock:
            now = datetime.now()
            
            status = {
                'client_id': client_id,
                'is_banned': client_id in self._banned_clients,
                'ban_expires': None,
                'violation_count': self._client_violation_counts.get(client_id, 0),
                'current_requests': {}
            }
            
            if status['is_banned']:
                status['ban_expires'] = self._banned_clients[client_id].isoformat()
            
            # Подсчитываем текущие запросы
            cache_key = client_id
            if cache_key in self._request_timestamps:
                minute_ago = now - timedelta(minutes=1)
                
                for request_type, timestamps in self._request_timestamps[cache_key].items():
                    minute_requests = sum(1 for ts in timestamps if ts > minute_ago)
                    limit = self._limits.get(request_type, RateLimitConfig()).requests_per_minute
                    
                    status['current_requests'][request_type] = {
                        'current': minute_requests,
                        'limit': limit,
                        'percentage': (minute_requests / limit) * 100 if limit > 0 else 0
                    }
            
            return status
    
    def get_global_status(self) -> Dict[str, Any]:
        """Получение глобального статуса rate limiter'а"""
        with self._lock:
            return {
                'emergency_stop_active': self._emergency_stop,
                'emergency_reason': self._emergency_reason,
                'emergency_since': self._emergency_timestamp.isoformat() if self._emergency_timestamp else None,
                'banned_clients_count': len(self._banned_clients),
                'total_violations': len(self._violation_history),
                'stats': self._stats.copy(),
                'recent_violations': [
                    {
                        'type': v.limit_type,
                        'client': v.client_id,
                        'severity': v.severity,
                        'timestamp': v.timestamp.isoformat(),
                        'current': v.current_count,
                        'limit': v.limit_value
                    }
                    for v in self._violation_history[-10:]  # Последние 10
                ]
            }
    
    def _cleanup_loop(self) -> None:
        """Фоновая очистка старых данных"""
        while True:
            try:
                time.sleep(300)  # Каждые 5 минут
                
                with self._lock:
                    now = datetime.now()
                    hour_ago = now - timedelta(hours=1)
                    
                    # Очищаем старые временные метки
                    for client_data in self._request_timestamps.values():
                        for request_type, timestamps in client_data.items():
                            while timestamps and timestamps[0] < hour_ago:
                                timestamps.popleft()
                    
                    # Очищаем старые нарушения (старше 24 часов)
                    day_ago = now - timedelta(days=1)
                    self._violation_history = [
                        v for v in self._violation_history 
                        if v.timestamp > day_ago
                    ]
                    
                    # Очищаем истёкшие блокировки
                    expired_bans = [
                        client_id for client_id, ban_time in self._banned_clients.items()
                        if now >= ban_time
                    ]
                    
                    for client_id in expired_bans:
                        del self._banned_clients[client_id]
                        self._client_violation_counts[client_id] = 0
                        self.logger.info(f"✅ Автоматически разблокирован клиент: {client_id}")
                
            except Exception as e:
                self.logger.error(f"❌ Ошибка в cleanup loop: {e}")
                time.sleep(60)  # При ошибке ждём минуту


# 🌍 ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР RATE LIMITER
_rate_limiter_instance = None
_rate_limiter_lock = threading.RLock()


def get_rate_limiter() -> AggressiveRateLimiter:
    """Получение синглтона rate limiter"""
    global _rate_limiter_instance
    
    if _rate_limiter_instance is None:
        with _rate_limiter_lock:
            if _rate_limiter_instance is None:
                _rate_limiter_instance = AggressiveRateLimiter()
    
    return _rate_limiter_instance


def reset_rate_limiter():
    """Сброс rate limiter (для тестов)"""
    global _rate_limiter_instance
    with _rate_limiter_lock:
        _rate_limiter_instance = None