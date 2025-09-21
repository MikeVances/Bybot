# bot/core/error_handler.py
"""
💀 КРИТИЧЕСКИЙ КОМПОНЕНТ: Централизованный Error Handler
ЕДИНАЯ ТОЧКА ОБРАБОТКИ ВСЕХ ОШИБОК В СИСТЕМЕ
ТИПИЗИРОВАННЫЕ ИСКЛЮЧЕНИЯ И RECOVERY STRATEGIES
"""

import logging
import traceback
import threading
from typing import Dict, Any, Optional, Callable, List, Type, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json

from bot.core.exceptions import (
    TradingBotException, OrderRejectionError, RateLimitError, 
    PositionConflictError, EmergencyStopError, APIKeyLeakError,
    RiskLimitExceededError, ThreadSafetyViolationError
)
from bot.core.secure_logger import get_secure_logger
from bot.core.emergency_stop import global_emergency_stop


class ErrorSeverity(Enum):
    """Уровни серьёзности ошибок"""
    CRITICAL = "CRITICAL"      # Останавливает всю торговлю
    HIGH = "HIGH"              # Останавливает стратегию  
    MEDIUM = "MEDIUM"          # Пропускает итерацию
    LOW = "LOW"                # Только логирует
    INFO = "INFO"              # Информационное сообщение


class RecoveryStrategy(Enum):
    """Стратегии восстановления после ошибок"""
    EMERGENCY_STOP = "emergency_stop"       # Полная остановка системы
    STRATEGY_RESTART = "strategy_restart"   # Перезапуск стратегии
    RETRY_WITH_BACKOFF = "retry_backoff"    # Повтор с экспоненциальной задержкой
    SKIP_ITERATION = "skip_iteration"       # Пропустить и продолжить
    IGNORE = "ignore"                       # Проигнорировать
    CUSTOM_HANDLER = "custom_handler"       # Пользовательский обработчик


@dataclass
class ErrorContext:
    """Контекст ошибки для анализа"""
    timestamp: datetime = field(default_factory=datetime.now)
    strategy_name: str = "unknown"
    symbol: str = "unknown" 
    operation: str = "unknown"
    user_data: Dict[str, Any] = field(default_factory=dict)
    stack_trace: str = ""
    correlation_id: str = ""


@dataclass 
class ErrorRule:
    """Правило обработки ошибки"""
    exception_type: Type[Exception]
    severity: ErrorSeverity
    recovery_strategy: RecoveryStrategy
    max_retries: int = 3
    backoff_seconds: int = 1
    custom_handler: Optional[Callable] = None
    description: str = ""


class TradingErrorHandler:
    """
    💀 ЦЕНТРАЛИЗОВАННЫЙ ОБРАБОТЧИК ОШИБОК
    
    Функции:
    - Классификация всех ошибок по типам и серьёзности  
    - Автоматические стратегии восстановления
    - Детальная статистика и аналитика ошибок
    - Integration с мониторингом и алертами
    - Thread-safe обработка из всех потоков
    """
    
    def __init__(self):
        # 🔒 THREAD-SAFETY
        self._lock = threading.RLock()
        
        # 📊 СТАТИСТИКА ОШИБОК
        self._error_counts: Dict[str, int] = {}
        self._error_history: List[Dict[str, Any]] = []
        self._recovery_stats: Dict[str, int] = {}
        
        # ⚙️ КОНФИГУРАЦИЯ ПРАВИЛ ОБРАБОТКИ
        self._error_rules: Dict[Type[Exception], ErrorRule] = {}
        self._setup_default_rules()
        
        # 🔄 RETRY МЕХАНИЗМЫ
        self._retry_attempts: Dict[str, Dict[str, Any]] = {}
        
        # 🚨 CIRCUIT BREAKER
        self._circuit_breaker_state: Dict[str, Dict[str, Any]] = {}
        
        # 📝 ЛОГИРОВАНИЕ  
        self.logger = get_secure_logger('error_handler')
        
        # 📊 МОНИТОРИНГ
        self._monitoring_callbacks: List[Callable] = []
        
        self.logger.info("💀 TradingErrorHandler инициализирован с централизованной обработкой")
    
    def _setup_default_rules(self):
        """Настройка правил обработки по умолчанию"""
        
        # 🚨 КРИТИЧЕСКИЕ ОШИБКИ - EMERGENCY STOP
        critical_errors = [
            EmergencyStopError,
            APIKeyLeakError, 
            ThreadSafetyViolationError,
        ]
        
        for error_type in critical_errors:
            self._error_rules[error_type] = ErrorRule(
                exception_type=error_type,
                severity=ErrorSeverity.CRITICAL,
                recovery_strategy=RecoveryStrategy.EMERGENCY_STOP,
                description=f"Critical system error: {error_type.__name__}"
            )
        
        # 🔴 ВЫСОКИЙ ПРИОРИТЕТ - ОСТАНОВКА СТРАТЕГИИ
        high_priority_errors = [
            RiskLimitExceededError,
            PositionConflictError,
        ]
        
        for error_type in high_priority_errors:
            self._error_rules[error_type] = ErrorRule(
                exception_type=error_type,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.STRATEGY_RESTART,
                max_retries=2,
                backoff_seconds=30,
                description=f"High priority error: {error_type.__name__}"
            )
        
        # 🟠 СРЕДНИЙ ПРИОРИТЕТ - RETRY С BACKOFF
        medium_priority_errors = [
            OrderRejectionError,
            RateLimitError,
        ]
        
        for error_type in medium_priority_errors:
            self._error_rules[error_type] = ErrorRule(
                exception_type=error_type,
                severity=ErrorSeverity.MEDIUM, 
                recovery_strategy=RecoveryStrategy.RETRY_WITH_BACKOFF,
                max_retries=3,
                backoff_seconds=5,
                description=f"Recoverable error: {error_type.__name__}"
            )
        
        # 🟡 СТАНДАРТНЫЕ ИСКЛЮЧЕНИЯ
        self._error_rules[ValueError] = ErrorRule(
            exception_type=ValueError,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.SKIP_ITERATION,
            description="Invalid parameter value"
        )
        
        self._error_rules[ConnectionError] = ErrorRule(
            exception_type=ConnectionError,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.RETRY_WITH_BACKOFF,
            max_retries=5,
            backoff_seconds=10,
            description="Network connection error"
        )
        
        # 🔵 ОБЩИЕ ИСКЛЮЧЕНИЯ
        self._error_rules[Exception] = ErrorRule(
            exception_type=Exception,
            severity=ErrorSeverity.HIGH,
            recovery_strategy=RecoveryStrategy.STRATEGY_RESTART,
            max_retries=1,
            description="Unhandled exception"
        )
    
    def handle_error(self, exception: Exception, context: ErrorContext = None, 
                    custom_recovery: RecoveryStrategy = None) -> Any:
        """
        🛡️ ГЛАВНЫЙ МЕТОД ОБРАБОТКИ ОШИБОК
        
        Args:
            exception: Возникшее исключение
            context: Контекст выполнения 
            custom_recovery: Пользовательская стратегия восстановления
            
        Returns:
            Результат обработки или None
        """
        with self._lock:
            try:
                # 1. Подготовка контекста
                if context is None:
                    context = ErrorContext()
                
                context.stack_trace = traceback.format_exc()
                
                # 2. Определение правила обработки
                error_rule = self._get_error_rule(exception)
                if custom_recovery:
                    error_rule.recovery_strategy = custom_recovery
                
                # 3. Логирование ошибки
                self._log_error(exception, context, error_rule)
                
                # 4. Обновление статистики
                self._update_error_stats(exception, context, error_rule)
                
                # 5. Circuit Breaker проверка
                if self._check_circuit_breaker(context, error_rule):
                    return self._execute_circuit_breaker(context)
                
                # 6. Выполнение стратегии восстановления
                return self._execute_recovery_strategy(exception, context, error_rule)
                
            except Exception as handler_error:
                # Критическая ошибка в самом обработчике!
                self.logger.critical(
                    f"💥 КРИТИЧЕСКАЯ ОШИБКА В ERROR HANDLER: {handler_error}"
                )
                # Fallback - аварийная остановка
                self._emergency_fallback()
                raise handler_error
    
    def _get_error_rule(self, exception: Exception) -> ErrorRule:
        """Получение правила обработки для исключения"""
        exception_type = type(exception)
        
        # Прямое соответствие
        if exception_type in self._error_rules:
            return self._error_rules[exception_type]
        
        # Поиск по иерархии наследования
        for rule_type, rule in self._error_rules.items():
            if isinstance(exception, rule_type):
                return rule
        
        # Fallback на общее исключение
        return self._error_rules[Exception]
    
    def _log_error(self, exception: Exception, context: ErrorContext, rule: ErrorRule):
        """Безопасное логирование ошибки"""
        error_data = {
            'exception_type': type(exception).__name__,
            'message': str(exception),
            'severity': rule.severity.value,
            'strategy': context.strategy_name,
            'symbol': context.symbol,
            'operation': context.operation,
            'recovery_strategy': rule.recovery_strategy.value,
            'timestamp': context.timestamp.isoformat()
        }
        
        # Логируем соответственно серьёзности
        if rule.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {error_data}")
        elif rule.severity == ErrorSeverity.HIGH:
            self.logger.error(f"❌ СЕРЬЁЗНАЯ ОШИБКА: {error_data}")
        elif rule.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"⚠️ ОШИБКА: {error_data}")
        else:
            self.logger.info(f"ℹ️ ИНФОРМАЦИЯ: {error_data}")
    
    def _update_error_stats(self, exception: Exception, context: ErrorContext, rule: ErrorRule):
        """Обновление статистики ошибок"""
        error_key = f"{type(exception).__name__}:{context.strategy_name}"
        
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        
        # Сохраняем в историю (последние 1000)
        error_record = {
            'timestamp': context.timestamp.isoformat(),
            'exception': type(exception).__name__,
            'message': str(exception),
            'strategy': context.strategy_name,
            'symbol': context.symbol,
            'operation': context.operation,
            'severity': rule.severity.value,
            'recovery': rule.recovery_strategy.value
        }
        
        self._error_history.append(error_record)
        
        # Ограничиваем размер истории
        if len(self._error_history) > 1000:
            self._error_history = self._error_history[-1000:]
    
    def _check_circuit_breaker(self, context: ErrorContext, rule: ErrorRule) -> bool:
        """Проверка circuit breaker для предотвращения каскадных отказов"""
        if rule.severity not in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
            return False
        
        circuit_key = f"{context.strategy_name}:{context.operation}"
        
        if circuit_key not in self._circuit_breaker_state:
            self._circuit_breaker_state[circuit_key] = {
                'failure_count': 0,
                'last_failure': None,
                'state': 'closed'  # closed, open, half_open
            }
        
        circuit = self._circuit_breaker_state[circuit_key]
        circuit['failure_count'] += 1
        circuit['last_failure'] = datetime.now()
        
        # Открываем circuit если слишком много ошибок
        if circuit['failure_count'] >= 5 and circuit['state'] == 'closed':
            circuit['state'] = 'open'
            self.logger.critical(
                f"🚨 CIRCUIT BREAKER ОТКРЫТ для {circuit_key}: {circuit['failure_count']} ошибок"
            )
            return True
        
        return circuit['state'] == 'open'
    
    def _execute_circuit_breaker(self, context: ErrorContext) -> None:
        """Выполнение действий при открытом circuit breaker"""
        self.logger.critical(
            f"⚡ CIRCUIT BREAKER: Блокировка операций для {context.strategy_name}:{context.operation}"
        )
        
        # Можно добавить уведомления, остановку стратегии и т.д.
        raise EmergencyStopError(
            f"Circuit breaker активирован для {context.strategy_name}:{context.operation}"
        )
    
    def _execute_recovery_strategy(self, exception: Exception, context: ErrorContext, 
                                 rule: ErrorRule) -> Any:
        """Выполнение стратегии восстановления"""
        recovery_key = f"{rule.recovery_strategy.value}:{context.strategy_name}"
        self._recovery_stats[recovery_key] = self._recovery_stats.get(recovery_key, 0) + 1
        
        if rule.recovery_strategy == RecoveryStrategy.EMERGENCY_STOP:
            return self._handle_emergency_stop(exception, context)
            
        elif rule.recovery_strategy == RecoveryStrategy.STRATEGY_RESTART:
            return self._handle_strategy_restart(exception, context)
            
        elif rule.recovery_strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
            return self._handle_retry_with_backoff(exception, context, rule)
            
        elif rule.recovery_strategy == RecoveryStrategy.SKIP_ITERATION:
            return self._handle_skip_iteration(exception, context)
            
        elif rule.recovery_strategy == RecoveryStrategy.IGNORE:
            return self._handle_ignore(exception, context)
            
        elif rule.recovery_strategy == RecoveryStrategy.CUSTOM_HANDLER:
            return self._handle_custom(exception, context, rule)
        
        else:
            self.logger.error(f"❌ Неизвестная стратегия восстановления: {rule.recovery_strategy}")
            return None
    
    def _handle_emergency_stop(self, exception: Exception, context: ErrorContext) -> None:
        """Аварийная остановка всей системы"""
        self.logger.critical("🚨 АВАРИЙНАЯ ОСТАНОВКА СИСТЕМЫ!")
        
        # Уведомления мониторинга
        for callback in self._monitoring_callbacks:
            try:
                callback('emergency_stop', {
                    'exception': str(exception),
                    'context': context.__dict__
                })
            except Exception as e:
                self.logger.error(f"Ошибка в мониторинг callback: {e}")
        
        # Поднимаем исключение для остановки
        raise EmergencyStopError(f"Emergency stop triggered by {type(exception).__name__}: {exception}")
    
    def _handle_strategy_restart(self, exception: Exception, context: ErrorContext) -> None:
        """Перезапуск стратегии"""
        self.logger.warning(f"🔄 ПЕРЕЗАПУСК СТРАТЕГИИ: {context.strategy_name}")
        
        # Логика перезапуска стратегии (может быть реализована через callback)
        return {'action': 'restart_strategy', 'strategy': context.strategy_name}
    
    def _handle_retry_with_backoff(self, exception: Exception, context: ErrorContext, 
                                 rule: ErrorRule) -> Any:
        """Повтор с экспоненциальной задержкой"""
        retry_key = f"{context.strategy_name}:{context.operation}:{context.symbol}"
        
        if retry_key not in self._retry_attempts:
            self._retry_attempts[retry_key] = {
                'count': 0,
                'last_attempt': None
            }
        
        retry_info = self._retry_attempts[retry_key]
        retry_info['count'] += 1
        retry_info['last_attempt'] = datetime.now()
        
        if retry_info['count'] <= rule.max_retries:
            backoff_time = rule.backoff_seconds * (2 ** (retry_info['count'] - 1))
            
            self.logger.info(
                f"🔄 RETRY {retry_info['count']}/{rule.max_retries} через {backoff_time}s "
                f"для {context.strategy_name}:{context.operation}"
            )
            
            import time
            time.sleep(backoff_time)
            
            return {'action': 'retry', 'attempt': retry_info['count'], 'backoff': backoff_time}
        else:
            # Максимум попыток исчерпан
            self.logger.error(
                f"❌ МАКСИМУМ ПОПЫТОК ИСЧЕРПАН для {retry_key}: {retry_info['count']} попыток"
            )
            
            # Очищаем счетчик для будущих попыток
            del self._retry_attempts[retry_key]
            
            # Эскалируем до более серьёзной стратегии
            return self._handle_strategy_restart(exception, context)
    
    def _handle_skip_iteration(self, exception: Exception, context: ErrorContext) -> None:
        """Пропуск текущей итерации"""
        self.logger.info(f"⏭️ ПРОПУСК итерации для {context.strategy_name}: {exception}")
        return {'action': 'skip', 'reason': str(exception)}
    
    def _handle_ignore(self, exception: Exception, context: ErrorContext) -> None:
        """Игнорирование ошибки"""
        self.logger.debug(f"🤫 ИГНОРИРУЕМ ошибку для {context.strategy_name}: {exception}")
        return {'action': 'ignore'}
    
    def _handle_custom(self, exception: Exception, context: ErrorContext, rule: ErrorRule) -> Any:
        """Пользовательский обработчик"""
        if rule.custom_handler:
            try:
                return rule.custom_handler(exception, context)
            except Exception as handler_error:
                self.logger.error(f"❌ Ошибка в custom handler: {handler_error}")
                return self._handle_skip_iteration(exception, context)
        else:
            return self._handle_skip_iteration(exception, context)
    
    def _emergency_fallback(self):
        """Аварийный fallback при критической ошибке в обработчике"""
        try:
            # Простейшее логирование в файл
            with open('emergency_error.log', 'a') as f:
                f.write(f"{datetime.now().isoformat()} - CRITICAL ERROR HANDLER FAILURE\n")
                f.write(traceback.format_exc())
                f.write("\n" + "="*50 + "\n")
        except:
            # Если даже файл не можем записать - print в stderr
            print("EMERGENCY: Critical error in error handler!")
    
    def add_monitoring_callback(self, callback: Callable):
        """Добавление callback для мониторинга"""
        self._monitoring_callbacks.append(callback)
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Получение статистики ошибок"""
        with self._lock:
            return {
                'total_errors': len(self._error_history),
                'error_counts': self._error_counts.copy(),
                'recovery_stats': self._recovery_stats.copy(),
                'circuit_breaker_states': {
                    k: {**v, 'last_failure': v['last_failure'].isoformat() if v['last_failure'] else None}
                    for k, v in self._circuit_breaker_state.items()
                },
                'recent_errors': self._error_history[-10:] if self._error_history else []
            }
    
    def reset_circuit_breaker(self, circuit_key: str) -> bool:
        """Сброс circuit breaker (для административного управления)"""
        with self._lock:
            if circuit_key in self._circuit_breaker_state:
                self._circuit_breaker_state[circuit_key] = {
                    'failure_count': 0,
                    'last_failure': None,
                    'state': 'closed'
                }
                self.logger.info(f"✅ Circuit breaker сброшен для {circuit_key}")
                return True
            return False


# 🌍 ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ERROR HANDLER
_error_handler_instance = None
_error_handler_lock = threading.RLock()


def get_error_handler() -> TradingErrorHandler:
    """Получение синглтона error handler"""
    global _error_handler_instance
    
    if _error_handler_instance is None:
        with _error_handler_lock:
            if _error_handler_instance is None:
                _error_handler_instance = TradingErrorHandler()
    
    return _error_handler_instance


def handle_trading_error(exception: Exception, context: ErrorContext = None, 
                        custom_recovery: RecoveryStrategy = None) -> Any:
    """Удобная функция для обработки ошибок"""
    error_handler = get_error_handler()
    return error_handler.handle_error(exception, context, custom_recovery)


def safe_execute(func: Callable, context: ErrorContext = None, 
                custom_recovery: RecoveryStrategy = None) -> Any:
    """Безопасное выполнение функции с обработкой ошибок"""
    try:
        return func()
    except Exception as e:
        return handle_trading_error(e, context, custom_recovery)


def classify_trading_error(exception: Exception) -> str:
    """
    Классификация торговых ошибок по типам
    
    Args:
        exception: Исключение для классификации
        
    Returns:
        str: Тип ошибки
    """
    error_message = str(exception).lower()
    
    # Ошибки API лимитов
    if any(keyword in error_message for keyword in ['rate limit', 'too many requests', '429']):
        return 'rate_limit_error'
    
    # Ошибки API ключей
    if any(keyword in error_message for keyword in ['api key', 'authentication', 'unauthorized', '401']):
        return 'authentication_error'
    
    # Ошибки ордеров
    if any(keyword in error_message for keyword in ['order', 'insufficient', 'balance', 'position']):
        return 'order_error'
    
    # Сетевые ошибки
    if any(keyword in error_message for keyword in ['connection', 'timeout', 'network', 'dns']):
        return 'network_error'
    
    # Ошибки биржи
    if any(keyword in error_message for keyword in ['bybit', 'exchange', 'market closed']):
        return 'exchange_error'
    
    # Ошибки валидации
    if any(keyword in error_message for keyword in ['validation', 'invalid', 'format']):
        return 'validation_error'
    
    # Критические системные ошибки
    if isinstance(exception, (EmergencyStopError, ThreadSafetyViolationError)):
        return 'critical_system_error'
    
    # Специфичные торговые ошибки
    if isinstance(exception, (OrderRejectionError, PositionConflictError)):
        return 'trading_logic_error'
    
    # Ошибки безопасности
    if isinstance(exception, APIKeyLeakError):
        return 'security_error'
    
    # Неизвестная ошибка
    return 'unknown_error'


# 🌍 ГЛОБАЛЬНЫЙ ERROR HANDLER
_error_handler_instance = None
_error_handler_lock = threading.RLock()


def get_error_handler() -> TradingErrorHandler:
    """Получение синглтона error handler"""
    global _error_handler_instance
    
    if _error_handler_instance is None:
        with _error_handler_lock:
            if _error_handler_instance is None:
                _error_handler_instance = TradingErrorHandler()
    
    return _error_handler_instance


def handle_trading_error(exception: Exception, context: ErrorContext = None, 
                        custom_recovery: RecoveryStrategy = None) -> Any:
    """Удобная функция для обработки ошибок"""
    error_handler = get_error_handler()
    return error_handler.handle_error(exception, context, custom_recovery)