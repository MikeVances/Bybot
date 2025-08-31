# bot/core/exceptions.py
"""
💀 КРИТИЧЕСКИЕ ИСКЛЮЧЕНИЯ ДЛЯ ТОРГОВОГО БОТА
ZERO TOLERANCE К ОШИБКАМ В ТОРГОВЛЕ!
"""


class TradingBotException(Exception):
    """Базовое исключение торгового бота"""
    pass


class OrderRejectionError(TradingBotException):
    """Исключение при отклонении ордера"""
    def __init__(self, message: str, symbol: str = None, strategy: str = None):
        super().__init__(message)
        self.symbol = symbol
        self.strategy = strategy
        self.message = message


class RateLimitError(TradingBotException):
    """Исключение при превышении лимита частоты запросов"""
    def __init__(self, message: str, symbol: str = None):
        super().__init__(message)
        self.symbol = symbol
        self.message = message


class PositionConflictError(TradingBotException):
    """Исключение при конфликте позиций"""
    def __init__(self, message: str, symbol: str = None, current_side: str = None, requested_side: str = None):
        super().__init__(message)
        self.symbol = symbol
        self.current_side = current_side
        self.requested_side = requested_side
        self.message = message


class EmergencyStopError(TradingBotException):
    """Исключение при аварийной остановке"""
    def __init__(self, message: str = "🚨 АВАРИЙНАЯ ОСТАНОВКА АКТИВНА!"):
        super().__init__(message)
        self.message = message


class APIKeyLeakError(TradingBotException):
    """Исключение при обнаружении утечки API ключей"""
    def __init__(self, message: str, file_path: str = None, line_number: int = None):
        super().__init__(message)
        self.file_path = file_path
        self.line_number = line_number
        self.message = message


class RiskLimitExceededError(TradingBotException):
    """Исключение при превышении лимитов риска"""
    def __init__(self, message: str, risk_type: str = None, limit_value=None, actual_value=None):
        super().__init__(message)
        self.risk_type = risk_type
        self.limit_value = limit_value
        self.actual_value = actual_value
        self.message = message


class ThreadSafetyViolationError(TradingBotException):
    """Исключение при нарушении thread-safety"""
    def __init__(self, message: str, resource: str = None):
        super().__init__(message)
        self.resource = resource
        self.message = message