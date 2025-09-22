"""
🔄 УЛУЧШЕННОЕ УПРАВЛЕНИЕ ПОДКЛЮЧЕНИЕМ К API
Heartbeat проверки, backup endpoints, fallback механизмы
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
import threading
import logging
from dataclasses import dataclass
from enum import Enum

class ConnectionState(Enum):
    """Состояния подключения"""
    HEALTHY = "healthy"           # Здоровое подключение
    DEGRADED = "degraded"        # Ухудшенное подключение
    UNSTABLE = "unstable"        # Нестабильное подключение
    FAILED = "failed"            # Отказ подключения
    MAINTENANCE = "maintenance"   # Техническое обслуживание

@dataclass
class APIEndpoint:
    """Информация о API endpoint"""
    url: str
    priority: int  # 1 = primary, 2 = secondary, etc.
    last_success: Optional[datetime] = None
    consecutive_failures: int = 0
    avg_response_time: float = 0.0
    is_available: bool = True

class EnhancedAPIConnectionManager:
    """Менеджер улучшенного подключения к API"""

    def __init__(self, primary_session, backup_endpoints: List[str] = None):
        self.primary_session = primary_session
        self.logger = logging.getLogger('api_connection')

        # Настройка endpoints
        self.endpoints = [
            APIEndpoint("https://api.bybit.com", 1),  # Primary
        ]

        if backup_endpoints:
            for i, url in enumerate(backup_endpoints, 2):
                self.endpoints.append(APIEndpoint(url, i))

        # Состояние подключения
        self.connection_state = ConnectionState.HEALTHY
        self.current_endpoint_index = 0

        # Heartbeat настройки
        self.heartbeat_interval = 30  # секунд
        self.heartbeat_thread = None
        self.heartbeat_running = False

        # Кэш для fallback данных
        self.cached_data = {}
        self.cache_ttl = timedelta(minutes=5)

        # Статистика
        self.connection_stats = {
            'total_requests': 0,
            'failed_requests': 0,
            'endpoint_switches': 0,
            'cache_hits': 0,
            'heartbeat_failures': 0
        }

        self.start_heartbeat_monitoring()

    def start_heartbeat_monitoring(self):
        """Запуск мониторинга heartbeat"""
        if not self.heartbeat_running:
            self.heartbeat_running = True
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat_worker,
                daemon=True
            )
            self.heartbeat_thread.start()
            self.logger.info("💓 Heartbeat мониторинг запущен")

    def _heartbeat_worker(self):
        """Рабочий поток heartbeat проверок"""
        while self.heartbeat_running:
            try:
                self._perform_heartbeat_check()
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Ошибка heartbeat: {e}")
                time.sleep(10)  # Короткая пауза при ошибке

    def _perform_heartbeat_check(self):
        """Выполнение heartbeat проверки"""
        try:
            start_time = time.time()

            # Простая проверка - получение времени сервера
            response = self.primary_session.get_server_time()

            response_time = time.time() - start_time

            if response and response.get('retCode') == 0:
                # Успешный heartbeat
                current_endpoint = self.endpoints[self.current_endpoint_index]
                current_endpoint.last_success = datetime.now()
                current_endpoint.consecutive_failures = 0
                current_endpoint.avg_response_time = (
                    current_endpoint.avg_response_time * 0.7 + response_time * 0.3
                )

                # Обновляем состояние подключения
                if response_time < 0.5:
                    self._update_connection_state(ConnectionState.HEALTHY)
                elif response_time < 2.0:
                    self._update_connection_state(ConnectionState.DEGRADED)
                else:
                    self._update_connection_state(ConnectionState.UNSTABLE)

                self.logger.debug(f"💓 Heartbeat OK: {response_time:.2f}s")

            else:
                # Неудачный heartbeat
                self._handle_heartbeat_failure(response)

        except Exception as e:
            self._handle_heartbeat_failure(f"Exception: {e}")

    def _handle_heartbeat_failure(self, error_info):
        """Обработка неудачного heartbeat"""
        self.connection_stats['heartbeat_failures'] += 1
        current_endpoint = self.endpoints[self.current_endpoint_index]
        current_endpoint.consecutive_failures += 1

        self.logger.warning(f"💔 Heartbeat failed: {error_info}")

        # Переключение на backup endpoint если много неудач
        if current_endpoint.consecutive_failures >= 3:
            self._switch_to_backup_endpoint()
        else:
            self._update_connection_state(ConnectionState.UNSTABLE)

    def _switch_to_backup_endpoint(self):
        """Переключение на резервный endpoint"""
        if len(self.endpoints) > 1:
            old_index = self.current_endpoint_index

            # Ищем доступный endpoint
            for i in range(len(self.endpoints)):
                if i != self.current_endpoint_index:
                    endpoint = self.endpoints[i]
                    if endpoint.consecutive_failures < 3:
                        self.current_endpoint_index = i
                        self.connection_stats['endpoint_switches'] += 1

                        self.logger.warning(
                            f"🔄 Переключение на backup endpoint: "
                            f"{self.endpoints[old_index].url} → {endpoint.url}"
                        )

                        self._update_connection_state(ConnectionState.DEGRADED)
                        return

            # Все endpoints недоступны
            self._update_connection_state(ConnectionState.FAILED)
        else:
            self._update_connection_state(ConnectionState.FAILED)

    def _update_connection_state(self, new_state: ConnectionState):
        """Обновление состояния подключения"""
        if self.connection_state != new_state:
            old_state = self.connection_state
            self.connection_state = new_state

            self.logger.info(f"🔌 Connection state: {old_state.value} → {new_state.value}")

            # Уведомляем о критических изменениях
            if new_state == ConnectionState.FAILED:
                self._handle_connection_failure()
            elif old_state == ConnectionState.FAILED and new_state != ConnectionState.FAILED:
                self._handle_connection_recovery()

    def _handle_connection_failure(self):
        """Обработка полного отказа подключения"""
        self.logger.critical("🚨 ВСЕ API ENDPOINTS НЕДОСТУПНЫ!")

        # Уведомляем через blocking alerts (если доступно)
        try:
            from bot.core.blocking_alerts import report_order_block
            report_order_block(
                reason="api_error",
                symbol="ALL",
                strategy="SYSTEM",
                message="Все API endpoints недоступны",
                details={
                    "failed_endpoints": len(self.endpoints),
                    "heartbeat_failures": self.connection_stats['heartbeat_failures']
                }
            )
        except ImportError:
            self.logger.warning("Blocking alerts система недоступна")

        # Активируем emergency stop (если доступно)
        try:
            from bot.core.emergency_stop import global_emergency_stop
            global_emergency_stop.activate("API connection completely failed")
        except ImportError:
            self.logger.warning("Emergency stop система недоступна")

    def _handle_connection_recovery(self):
        """Обработка восстановления подключения"""
        self.logger.info("✅ API подключение восстановлено")

        # Сбрасываем emergency stop если он был активирован
        try:
            from bot.core.emergency_stop import global_emergency_stop
            global_emergency_stop.deactivate("API connection recovered")
        except ImportError:
            pass

    def execute_with_fallback(self, operation: Callable, operation_name: str,
                            cache_key: str = None, **kwargs) -> Any:
        """
        Выполнение операции с fallback на кэшированные данные

        Args:
            operation: Функция для выполнения
            operation_name: Название операции для логирования
            cache_key: Ключ для кэширования результата
            **kwargs: Аргументы для функции
        """
        self.connection_stats['total_requests'] += 1

        try:
            # Проверяем состояние подключения
            if self.connection_state == ConnectionState.FAILED:
                if cache_key and cache_key in self.cached_data:
                    self.logger.warning(f"🗂️ Используем кэшированные данные для {operation_name}")
                    self.connection_stats['cache_hits'] += 1
                    return self.cached_data[cache_key]['data']
                else:
                    raise Exception("API недоступен и нет кэшированных данных")

            # Выполняем операцию
            result = operation(**kwargs)

            # Кэшируем результат если нужно
            if cache_key and result:
                self.cached_data[cache_key] = {
                    'data': result,
                    'timestamp': datetime.now()
                }

            return result

        except Exception as e:
            self.connection_stats['failed_requests'] += 1
            self.logger.error(f"API операция {operation_name} не удалась: {e}")

            # Пробуем кэшированные данные
            if cache_key and cache_key in self.cached_data:
                cached_item = self.cached_data[cache_key]
                data_age = datetime.now() - cached_item['timestamp']

                if data_age < self.cache_ttl:
                    self.logger.warning(
                        f"🗂️ Fallback на кэшированные данные для {operation_name} "
                        f"(возраст: {data_age.total_seconds():.0f}s)"
                    )
                    self.connection_stats['cache_hits'] += 1
                    return cached_item['data']

            # Нет fallback данных
            raise e

    def cleanup_expired_cache(self):
        """Очистка устаревшего кэша"""
        now = datetime.now()
        expired_keys = [
            key for key, item in self.cached_data.items()
            if now - item['timestamp'] > self.cache_ttl
        ]

        for key in expired_keys:
            del self.cached_data[key]

        if expired_keys:
            self.logger.debug(f"🧹 Очищено {len(expired_keys)} устаревших кэш записей")

    def get_connection_health(self) -> Dict[str, Any]:
        """Получить информацию о здоровье подключения"""
        current_endpoint = self.endpoints[self.current_endpoint_index]

        return {
            'state': self.connection_state.value,
            'current_endpoint': current_endpoint.url,
            'endpoint_response_time': current_endpoint.avg_response_time,
            'consecutive_failures': current_endpoint.consecutive_failures,
            'last_success': current_endpoint.last_success.isoformat() if current_endpoint.last_success else None,
            'cached_items': len(self.cached_data),
            'stats': self.connection_stats.copy()
        }

    def stop(self):
        """Остановка мониторинга"""
        self.heartbeat_running = False
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=5)
        self.logger.info("🛑 API connection manager остановлен")

# Глобальный экземпляр менеджера подключений
_connection_manager = None

def get_enhanced_connection_manager() -> Optional[EnhancedAPIConnectionManager]:
    """Получить глобальный менеджер подключений"""
    global _connection_manager
    return _connection_manager

def setup_enhanced_connection_manager(primary_session, backup_endpoints=None):
    """Настройка менеджера подключений"""
    global _connection_manager
    _connection_manager = EnhancedAPIConnectionManager(primary_session, backup_endpoints)
    return _connection_manager