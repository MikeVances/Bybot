"""
Глобальный Circuit Breaker для защиты от каскадных сбоев API
Автоматически блокирует торговлю при множественных ошибках
"""

import threading
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Состояния Circuit Breaker"""
    CLOSED = "CLOSED"      # Нормальная работа
    OPEN = "OPEN"          # Блокировка запросов
    HALF_OPEN = "HALF_OPEN"  # Тестовые запросы


@dataclass
class APIErrorStats:
    """Статистика ошибок API"""
    total_errors: int = 0
    consecutive_errors: int = 0
    last_error_time: Optional[datetime] = None
    error_rate_1min: float = 0.0
    error_rate_5min: float = 0.0
    recent_errors: List[datetime] = None

    def __post_init__(self):
        if self.recent_errors is None:
            self.recent_errors = []


class GlobalCircuitBreaker:
    """
    Глобальный Circuit Breaker для всех API запросов
    Защищает от блокировки аккаунта при множественных ошибках
    """

    def __init__(self):
        self.state = CircuitBreakerState.CLOSED
        self.failure_threshold = 5  # Количество ошибок для открытия
        self.recovery_timeout = 300  # 5 минут до попытки восстановления
        self.success_threshold = 3   # Успешных запросов для закрытия

        # Статистика
        self.api_stats = APIErrorStats()
        self.consecutive_successes = 0
        self.state_change_time = datetime.now()

        # Блокировки
        self._lock = threading.RLock()
        self._state_lock = threading.Lock()

        # Мониторинг
        self.monitoring_thread = None
        self.monitoring_active = False

    def start_monitoring(self):
        """Запуск мониторинга ошибок"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="CircuitBreakerMonitor"
        )
        self.monitoring_thread.start()
        logger.info("🔌 Circuit Breaker мониторинг запущен")

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.monitoring_active = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)

    def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.monitoring_active:
            try:
                self._cleanup_old_errors()
                self._update_error_rates()
                self._check_state_transitions()

                time.sleep(10)  # Проверяем каждые 10 секунд

            except Exception as e:
                logger.error(f"❌ Ошибка в Circuit Breaker мониторинге: {e}")
                time.sleep(5)

    def _cleanup_old_errors(self):
        """Очистка старых записей об ошибках"""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(minutes=5)
            self.api_stats.recent_errors = [
                error_time for error_time in self.api_stats.recent_errors
                if error_time > cutoff_time
            ]

    def _update_error_rates(self):
        """Обновление частоты ошибок"""
        with self._lock:
            now = datetime.now()

            # Ошибки за последнюю минуту
            one_min_ago = now - timedelta(minutes=1)
            errors_1min = sum(1 for error_time in self.api_stats.recent_errors
                            if error_time > one_min_ago)
            self.api_stats.error_rate_1min = errors_1min

            # Ошибки за последние 5 минут
            five_min_ago = now - timedelta(minutes=5)
            errors_5min = sum(1 for error_time in self.api_stats.recent_errors
                            if error_time > five_min_ago)
            self.api_stats.error_rate_5min = errors_5min / 5.0  # Среднее в минуту

    def _check_state_transitions(self):
        """Проверка необходимости смены состояния"""
        with self._state_lock:
            now = datetime.now()
            time_since_change = (now - self.state_change_time).total_seconds()

            if self.state == CircuitBreakerState.OPEN:
                # Попытка перехода в HALF_OPEN после timeout
                if time_since_change >= self.recovery_timeout:
                    self._change_state(CircuitBreakerState.HALF_OPEN)
                    logger.warning("🔶 Circuit Breaker: OPEN → HALF_OPEN (тестирование)")

    def _change_state(self, new_state: CircuitBreakerState):
        """Смена состояния Circuit Breaker"""
        old_state = self.state
        self.state = new_state
        self.state_change_time = datetime.now()

        if old_state != new_state:
            logger.critical(f"🔌 Circuit Breaker: {old_state.value} → {new_state.value}")

            # Уведомляем Emergency Stop о критических изменениях
            if new_state == CircuitBreakerState.OPEN:
                global_emergency_stop.report_api_error()

    def can_execute_request(self) -> Tuple[bool, str]:
        """
        Проверить, можно ли выполнить API запрос

        Returns:
            Tuple[bool, str]: (можно_выполнить, причина_если_нет)
        """
        with self._state_lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True, "✅ Нормальная работа"

            elif self.state == CircuitBreakerState.OPEN:
                return False, f"🔴 Circuit Breaker ОТКРЫТ: {self.api_stats.consecutive_errors} ошибок подряд"

            elif self.state == CircuitBreakerState.HALF_OPEN:
                # В половинном режиме разрешаем ограниченные запросы
                return True, "🔶 Тестовый режим"

            return False, "❓ Неизвестное состояние"

    def record_success(self):
        """Зафиксировать успешный API запрос"""
        with self._lock:
            self.consecutive_successes += 1
            self.api_stats.consecutive_errors = 0

            # Уведомляем Emergency Stop об успехе
            global_emergency_stop.report_api_success()

            with self._state_lock:
                if self.state == CircuitBreakerState.HALF_OPEN:
                    if self.consecutive_successes >= self.success_threshold:
                        self._change_state(CircuitBreakerState.CLOSED)
                        self.consecutive_successes = 0
                        logger.info("✅ Circuit Breaker: HALF_OPEN → CLOSED (восстановлен)")

    def record_failure(self, error_type: str = "API_ERROR"):
        """
        Зафиксировать ошибку API запроса

        Args:
            error_type: Тип ошибки для статистики
        """
        with self._lock:
            now = datetime.now()

            # Обновляем статистику
            self.api_stats.total_errors += 1
            self.api_stats.consecutive_errors += 1
            self.api_stats.last_error_time = now
            self.api_stats.recent_errors.append(now)

            # Сбрасываем счетчик успехов
            self.consecutive_successes = 0

            logger.warning(f"⚠️ API ошибка #{self.api_stats.consecutive_errors}: {error_type}")

            with self._state_lock:
                # Проверяем превышение порога ошибок
                if (self.state == CircuitBreakerState.CLOSED and
                    self.api_stats.consecutive_errors >= self.failure_threshold):

                    self._change_state(CircuitBreakerState.OPEN)
                    logger.critical(f"🔴 Circuit Breaker ОТКРЫТ: {self.api_stats.consecutive_errors} ошибок")

                elif self.state == CircuitBreakerState.HALF_OPEN:
                    # Возвращаемся в OPEN при любой ошибке в тестовом режиме
                    self._change_state(CircuitBreakerState.OPEN)
                    logger.warning("🔶 Circuit Breaker: HALF_OPEN → OPEN (ошибка в тесте)")

    def force_open(self, reason: str):
        """
        Принудительно открыть Circuit Breaker

        Args:
            reason: Причина принудительного открытия
        """
        with self._state_lock:
            self._change_state(CircuitBreakerState.OPEN)
            logger.critical(f"🚨 Circuit Breaker ПРИНУДИТЕЛЬНО ОТКРЫТ: {reason}")

    def reset(self, admin_confirmation: bool = False):
        """
        Сброс Circuit Breaker (только для администратора)

        Args:
            admin_confirmation: Подтверждение администратора
        """
        if not admin_confirmation:
            logger.warning("⚠️ Попытка сброса Circuit Breaker без подтверждения")
            return False

        with self._lock:
            self.api_stats = APIErrorStats()
            self.consecutive_successes = 0

            with self._state_lock:
                self._change_state(CircuitBreakerState.CLOSED)

        logger.warning("🔄 Circuit Breaker СБРОШЕН АДМИНИСТРАТОРОМ")
        return True

    def get_status(self) -> Dict:
        """Получить текущий статус Circuit Breaker"""
        with self._lock:
            return {
                'state': self.state.value,
                'total_errors': self.api_stats.total_errors,
                'consecutive_errors': self.api_stats.consecutive_errors,
                'consecutive_successes': self.consecutive_successes,
                'error_rate_1min': self.api_stats.error_rate_1min,
                'error_rate_5min': self.api_stats.error_rate_5min,
                'last_error_time': self.api_stats.last_error_time.isoformat() if self.api_stats.last_error_time else None,
                'state_change_time': self.state_change_time.isoformat(),
                'failure_threshold': self.failure_threshold,
                'recovery_timeout': self.recovery_timeout
            }

    def get_health_check(self) -> Tuple[bool, str]:
        """
        Проверка здоровья системы

        Returns:
            Tuple[bool, str]: (здоровая, описание_состояния)
        """
        with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                if self.api_stats.error_rate_1min > 3:
                    return False, f"⚠️ Высокая частота ошибок: {self.api_stats.error_rate_1min}/мин"
                return True, "✅ Система работает нормально"

            elif self.state == CircuitBreakerState.HALF_OPEN:
                return False, "🔶 Система в тестовом режиме"

            else:  # OPEN
                return False, f"🔴 Система заблокирована: {self.api_stats.consecutive_errors} ошибок"


# Декоратор для автоматического использования Circuit Breaker
def with_circuit_breaker(circuit_breaker):
    """
    Декоратор для автоматической интеграции с Circuit Breaker

    Args:
        circuit_breaker: Экземпляр GlobalCircuitBreaker
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Проверяем, можно ли выполнить запрос
            can_execute, reason = circuit_breaker.can_execute_request()

            if not can_execute:
                logger.warning(f"🚫 Запрос заблокирован Circuit Breaker: {reason}")
                raise Exception(f"Circuit Breaker: {reason}")

            try:
                # Выполняем запрос
                result = func(*args, **kwargs)
                circuit_breaker.record_success()
                return result

            except Exception as e:
                # Фиксируем ошибку
                circuit_breaker.record_failure(str(type(e).__name__))
                raise

        return wrapper
    return decorator


# Глобальный экземпляр Circuit Breaker
global_circuit_breaker = GlobalCircuitBreaker()