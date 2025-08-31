# bot/core/secure_logger.py
"""
💀 КРИТИЧЕСКИЙ КОМПОНЕНТ: Защищённое логирование
ZERO TOLERANCE К УТЕЧКАМ API КЛЮЧЕЙ!
ПОЛНАЯ ФИЛЬТРАЦИЯ ВСЕХ ЧУВСТВИТЕЛЬНЫХ ДАННЫХ!
"""

import re
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import hashlib
import json

from bot.core.exceptions import APIKeyLeakError


class SecurityFilter(logging.Filter):
    """
    🛡️ ФИЛЬТР БЕЗОПАСНОСТИ ДЛЯ ЛОГИРОВАНИЯ
    Блокирует ВСЕ утечки чувствительных данных
    """
    
    def __init__(self):
        super().__init__()
        
        # 🔑 ПАТТЕРНЫ ДЛЯ ПОИСКА ЧУВСТВИТЕЛЬНЫХ ДАННЫХ
        self.sensitive_patterns = [
            # API ключи
            re.compile(r'["\']?api[_\-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]{20,})["\']?', re.IGNORECASE),
            re.compile(r'["\']?api[_\-]?secret["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]{20,})["\']?', re.IGNORECASE),
            re.compile(r'["\']?secret["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]{20,})["\']?', re.IGNORECASE),
            
            # Bybit специфичные ключи  
            re.compile(r'BYBIT_API_KEY\s*[:=]\s*["\']?([a-zA-Z0-9]{20,})["\']?', re.IGNORECASE),
            re.compile(r'BYBIT_API_SECRET\s*[:=]\s*["\']?([a-zA-Z0-9]{20,})["\']?', re.IGNORECASE),
            
            # Telegram токены
            re.compile(r'[0-9]{8,10}:[a-zA-Z0-9_-]{35}'),  # Telegram Bot Token format
            re.compile(r'TELEGRAM_TOKEN\s*[:=]\s*["\']?([0-9]{8,10}:[a-zA-Z0-9_-]{35})["\']?', re.IGNORECASE),
            
            # Подписи запросов
            re.compile(r'["\']?sign["\']?\s*[:=]\s*["\']?([a-fA-F0-9]{64})["\']?', re.IGNORECASE),
            re.compile(r'signature\s*[:=]\s*["\']?([a-fA-F0-9]{64})["\']?', re.IGNORECASE),
            
            # Пароли
            re.compile(r'["\']?password["\']?\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', re.IGNORECASE),
            re.compile(r'["\']?passwd["\']?\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', re.IGNORECASE),
            
            # JWT токены
            re.compile(r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*'),
            
            # Private keys
            re.compile(r'-----BEGIN (?:RSA )?PRIVATE KEY-----.*?-----END (?:RSA )?PRIVATE KEY-----', re.DOTALL),
        ]
        
        # 🔍 КЛЮЧЕВЫЕ СЛОВА ДЛЯ ПОИСКА
        self.sensitive_keywords = [
            'api_key', 'api_secret', 'secret', 'password', 'token', 'key', 
            'signature', 'sign', 'auth', 'credential', 'private'
        ]
        
        # 📊 СТАТИСТИКА ЗАБЛОКИРОВАННЫХ УТЕЧЕК
        self.blocked_leaks = 0
        self.leak_types = {}
        
    def filter(self, record: logging.LogRecord) -> bool:
        """Фильтрация чувствительных данных из лог записи"""
        try:
            # Проверяем сообщение
            if hasattr(record, 'msg') and record.msg:
                original_msg = str(record.msg)
                filtered_msg, leak_found = self._filter_sensitive_data(original_msg)
                
                if leak_found:
                    self.blocked_leaks += 1
                    # Заменяем сообщение на отфильтрованное
                    record.msg = filtered_msg
                    
                    # Логируем попытку утечки (без чувствительных данных)
                    leak_hash = hashlib.md5(original_msg.encode()).hexdigest()[:8]
                    self._log_leak_attempt(record, leak_hash)
            
            # Фильтруем аргументы
            if hasattr(record, 'args') and record.args:
                filtered_args = []
                for arg in record.args:
                    if isinstance(arg, (str, bytes)):
                        filtered_arg, _ = self._filter_sensitive_data(str(arg))
                        filtered_args.append(filtered_arg)
                    elif isinstance(arg, dict):
                        filtered_args.append(self._filter_dict(arg))
                    else:
                        filtered_args.append(arg)
                record.args = tuple(filtered_args)
            
            return True  # Всегда пропускаем запись (уже отфильтрованную)
            
        except Exception as e:
            # Если фильтрация не удалась, блокируем запись полностью
            print(f"[SECURITY ERROR] Ошибка фильтрации логов: {e}")
            return False
    
    def _filter_sensitive_data(self, text: str) -> tuple[str, bool]:
        """Фильтрация чувствительных данных из текста"""
        filtered_text = text
        leak_found = False
        
        # Применяем регулярные выражения
        for pattern in self.sensitive_patterns:
            matches = pattern.findall(filtered_text)
            if matches:
                leak_found = True
                # Заменяем найденные совпадения на маскированные версии
                for match in matches:
                    if isinstance(match, tuple):
                        # Если группа захвата, берем первую группу
                        sensitive_value = match[0] if len(match) > 0 else str(match)
                    else:
                        sensitive_value = str(match)
                    
                    if len(sensitive_value) > 8:
                        masked_value = f"{sensitive_value[:2]}{'*' * (len(sensitive_value) - 4)}{sensitive_value[-2:]}"
                    else:
                        masked_value = '*' * len(sensitive_value)
                    
                    filtered_text = filtered_text.replace(sensitive_value, f"[MASKED:{masked_value}]")
                    
                    # Обновляем статистику
                    leak_type = self._identify_leak_type(sensitive_value)
                    self.leak_types[leak_type] = self.leak_types.get(leak_type, 0) + 1
        
        return filtered_text, leak_found
    
    def _filter_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Фильтрация чувствительных данных из словаря"""
        filtered_dict = {}
        
        for key, value in data.items():
            key_lower = key.lower()
            
            # Проверяем ключи на чувствительность
            is_sensitive_key = any(keyword in key_lower for keyword in self.sensitive_keywords)
            
            if is_sensitive_key and isinstance(value, (str, int, float)):
                # Маскируем чувствительное значение
                str_value = str(value)
                if len(str_value) > 8:
                    filtered_dict[key] = f"{str_value[:2]}{'*' * (len(str_value) - 4)}{str_value[-2:]}"
                else:
                    filtered_dict[key] = '*' * len(str_value)
            elif isinstance(value, dict):
                filtered_dict[key] = self._filter_dict(value)
            elif isinstance(value, list):
                filtered_dict[key] = [
                    self._filter_dict(item) if isinstance(item, dict) 
                    else item for item in value
                ]
            else:
                filtered_dict[key] = value
                
        return filtered_dict
    
    def _identify_leak_type(self, sensitive_value: str) -> str:
        """Определение типа утечки по значению"""
        if len(sensitive_value) == 64 and all(c in '0123456789abcdefABCDEF' for c in sensitive_value):
            return 'signature'
        elif ':' in sensitive_value and len(sensitive_value) > 40:
            return 'telegram_token'
        elif len(sensitive_value) > 30:
            return 'api_key_or_secret'
        else:
            return 'unknown'
    
    def _log_leak_attempt(self, record: logging.LogRecord, leak_hash: str):
        """Логирование попытки утечки чувствительных данных"""
        # Создаем отдельный лог для security событий
        security_logger = logging.getLogger('security_audit')
        
        if not security_logger.hasHandlers():
            # Создаем отдельный handler для security логов
            import os
            log_dir = 'data/logs'
            os.makedirs(log_dir, exist_ok=True)
            
            handler = logging.FileHandler(os.path.join(log_dir, 'security_audit.log'))
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - SECURITY LEAK BLOCKED - %(message)s'
            ))
            security_logger.addHandler(handler)
            security_logger.setLevel(logging.WARNING)
        
        security_logger.warning(
            f"BLOCKED API KEY LEAK - Logger: {record.name}, "
            f"Function: {record.funcName}, Line: {record.lineno}, "
            f"Hash: {leak_hash}, Time: {datetime.now().isoformat()}"
        )


class SecureLogger:
    """
    🛡️ ЗАЩИЩЁННЫЙ ЛОГГЕР ДЛЯ ТОРГОВОГО БОТА
    Автоматически фильтрует все чувствительные данные
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.security_filter = SecurityFilter()
        
        # Добавляем фильтр безопасности ко всем handlers
        for handler in self.logger.handlers:
            handler.addFilter(self.security_filter)
        
        # Если у логгера нет handlers, добавляем фильтр к root logger
        if not self.logger.handlers:
            root_logger = logging.getLogger()
            for handler in root_logger.handlers:
                if self.security_filter not in handler.filters:
                    handler.addFilter(self.security_filter)
    
    def safe_log_api_response(self, response: Optional[Dict[str, Any]], 
                             success_msg: str, error_msg: str, level: str = 'info') -> None:
        """Безопасное логирование API ответов"""
        if response and response.get('retCode') == 0:
            # Успешный ответ - логируем только безопасные поля
            safe_result = {
                'retCode': response.get('retCode'),
                'success': True
            }
            
            # Добавляем только безопасные поля из result
            if 'result' in response and isinstance(response['result'], dict):
                for safe_field in ['orderId', 'symbol', 'side', 'qty', 'status', 'orderType']:
                    if safe_field in response['result']:
                        safe_result[safe_field] = response['result'][safe_field]
            
            getattr(self.logger, level)(f"{success_msg}: {safe_result}")
        else:
            # Ошибка - логируем только код ошибки и сообщение
            safe_error = {
                'retCode': response.get('retCode') if response else None,
                'retMsg': response.get('retMsg') if response else 'No response'
            }
            self.logger.error(f"{error_msg}: {safe_error}")
    
    def safe_log_order_request(self, symbol: str, side: str, order_type: str, qty: float, 
                              price: Optional[float] = None) -> None:
        """Безопасное логирование запроса на создание ордера"""
        safe_request = {
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': qty
        }
        if price:
            safe_request['price'] = price
        
        self.logger.info(f"📝 Создание ордера: {safe_request}")
    
    def safe_log_position_update(self, symbol: str, side: Optional[str], size: float, 
                                avg_price: float, unrealized_pnl: float) -> None:
        """Безопасное логирование обновления позиции"""
        safe_position = {
            'symbol': symbol,
            'side': side,
            'size': size,
            'avgPrice': avg_price,
            'unrealizedPnl': round(unrealized_pnl, 2)
        }
        
        self.logger.info(f"📊 Позиция обновлена: {safe_position}")
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Получение статистики заблокированных утечек"""
        return {
            'blocked_leaks_total': self.security_filter.blocked_leaks,
            'leak_types': self.security_filter.leak_types.copy(),
            'filter_active': True
        }
    
    # Проксируем стандартные методы логгера
    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)


def get_secure_logger(name: str) -> SecureLogger:
    """Получение защищённого логгера"""
    return SecureLogger(name)


def setup_security_logging():
    """Настройка системы безопасного логирования"""
    # Создаем глобальный security filter
    security_filter = SecurityFilter()
    
    # Добавляем фильтр ко всем существующим loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            if security_filter not in handler.filters:
                handler.addFilter(security_filter)
    
    # Добавляем фильтр к root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if security_filter not in handler.filters:
            handler.addFilter(security_filter)
    
    print("🛡️ Система защищённого логирования активирована")
    return security_filter


# Автоматическая настройка при импорте
_security_filter = setup_security_logging()