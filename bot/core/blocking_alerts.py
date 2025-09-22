"""
🚨 СИСТЕМА УВЕДОМЛЕНИЙ О БЛОКИРОВКАХ ТОРГОВЛИ
Уведомляет пользователя о каждой блокировке ордера с детальным объяснением
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

class BlockingReason(Enum):
    """Причины блокировки торговли"""
    EMERGENCY_STOP = "emergency_stop"
    RISK_LIMIT = "risk_limit"
    RATE_LIMIT = "rate_limit"
    API_ERROR = "api_error"
    STRATEGY_FILTER = "strategy_filter"
    ORDER_CONFLICT = "order_conflict"
    POSITION_LIMIT = "position_limit"
    BALANCE_INSUFFICIENT = "balance_insufficient"
    API_PERFORMANCE = "api_performance"

@dataclass
class BlockingAlert:
    """Уведомление о блокировке"""
    timestamp: datetime
    reason: BlockingReason
    symbol: str
    strategy: str
    message: str
    severity: str
    details: Dict[str, Any]
    resolved: bool = False

class BlockingAlertsManager:
    """Менеджер уведомлений о блокировках"""

    def __init__(self, telegram_bot=None):
        self.logger = logging.getLogger('blocking_alerts')
        self.telegram_bot = telegram_bot
        self.active_blocks = {}  # {key: BlockingAlert}
        self.block_history = []
        self.notification_cooldown = {}  # Предотвращение спама

    def report_order_block(self, reason: str, symbol: str, strategy: str,
                          message: str, details: Dict[str, Any] = None) -> None:
        """
        Сообщить о блокировке ордера

        Args:
            reason: Причина блокировки
            symbol: Торговый инструмент
            strategy: Название стратегии
            message: Человекочитаемое сообщение
            details: Дополнительные детали
        """
        try:
            # Определяем серьезность
            severity = self._get_severity(reason)

            # Создаем уведомление
            alert = BlockingAlert(
                timestamp=datetime.now(),
                reason=BlockingReason(reason),
                symbol=symbol,
                strategy=strategy,
                message=message,
                severity=severity,
                details=details or {}
            )

            # Ключ для отслеживания
            alert_key = f"{reason}_{symbol}_{strategy}"

            # Проверяем cooldown для предотвращения спама
            if self._should_notify(alert_key, severity):
                self._send_notification(alert)
                self.notification_cooldown[alert_key] = datetime.now()

            # Сохраняем в истории
            self.active_blocks[alert_key] = alert
            self.block_history.append(alert)

            # Ограничиваем историю (последние 1000 записей)
            if len(self.block_history) > 1000:
                self.block_history = self.block_history[-1000:]

            # Логируем
            self.logger.warning(
                f"🚫 БЛОКИРОВКА: {strategy} ({symbol}) - {message}"
            )

        except Exception as e:
            self.logger.error(f"Ошибка при сообщении о блокировке: {e}")

    def _get_severity(self, reason: str) -> str:
        """Определить серьезность блокировки"""
        severity_map = {
            "emergency_stop": "CRITICAL",
            "risk_limit": "HIGH",
            "api_error": "HIGH",
            "api_performance": "HIGH",
            "rate_limit": "MEDIUM",
            "position_limit": "MEDIUM",
            "balance_insufficient": "MEDIUM",
            "strategy_filter": "LOW",
            "order_conflict": "MEDIUM"
        }
        return severity_map.get(reason, "MEDIUM")

    def _should_notify(self, alert_key: str, severity: str) -> bool:
        """Проверить, нужно ли отправлять уведомление"""
        last_notification = self.notification_cooldown.get(alert_key)

        if not last_notification:
            return True

        # Cooldown периоды по серьезности
        cooldown_minutes = {
            "CRITICAL": 0,    # Всегда уведомлять
            "HIGH": 5,       # 5 минут
            "MEDIUM": 15,    # 15 минут
            "LOW": 60        # 1 час
        }

        cooldown = cooldown_minutes.get(severity, 15)
        return datetime.now() - last_notification > timedelta(minutes=cooldown)

    def _send_notification(self, alert: BlockingAlert) -> None:
        """Отправить уведомление"""

        # Форматируем сообщение
        severity_emoji = {
            "CRITICAL": "🚨",
            "HIGH": "🔴",
            "MEDIUM": "🟡",
            "LOW": "🟢"
        }

        emoji = severity_emoji.get(alert.severity, "⚠️")

        notification_text = f"""{emoji} БЛОКИРОВКА ТОРГОВЛИ

📊 Стратегия: {alert.strategy}
💰 Символ: {alert.symbol}
⚠️ Причина: {alert.message}
🔒 Уровень: {alert.severity}
⏰ Время: {alert.timestamp.strftime('%H:%M:%S')}

📋 Детали: {self._format_details(alert.details)}

💡 Что делать: {self._get_recommendation(alert.reason.value)}"""

        # Отправляем через Telegram если доступен
        if self.telegram_bot:
            try:
                self.telegram_bot.send_admin_message(notification_text)
            except Exception as e:
                self.logger.error(f"Ошибка отправки Telegram: {e}")

        # Также логируем критические уведомления
        if alert.severity == "CRITICAL":
            self.logger.critical(notification_text)

    def _format_details(self, details: Dict[str, Any]) -> str:
        """Форматировать детали для уведомления"""
        if not details:
            return "Нет дополнительной информации"

        formatted = []
        for key, value in details.items():
            if key == 'current_balance':
                formatted.append(f"Баланс: ${value:.2f}")
            elif key == 'limit_value':
                formatted.append(f"Лимит: {value}")
            elif key == 'actual_value':
                formatted.append(f"Текущее: {value}")
            elif key == 'response_time':
                formatted.append(f"Время отклика: {value:.2f}s")
            elif key == 'failure_rate':
                formatted.append(f"Частота ошибок: {value*100:.1f}%")
            else:
                formatted.append(f"{key}: {value}")

        return ", ".join(formatted)

    def _get_recommendation(self, reason: str) -> str:
        """Получить рекомендацию по решению проблемы"""
        recommendations = {
            "emergency_stop": "Проверьте логи на критические ошибки, перезапустите систему",
            "risk_limit": "Увеличьте лимиты риска или дождитесь сброса дневных лимитов",
            "rate_limit": "Подождите несколько минут, система автоматически возобновит работу",
            "api_error": "Проверьте подключение к интернету и статус Bybit API",
            "api_performance": "API работает медленно, система автоматически адаптируется",
            "strategy_filter": "Нормальная работа, стратегия отфильтровала слабый сигнал",
            "order_conflict": "Проверьте открытые позиции и ордера",
            "position_limit": "Уменьшите размер позиции или увеличьте лимиты",
            "balance_insufficient": "Пополните баланс или уменьшите размер сделок"
        }
        return recommendations.get(reason, "Обратитесь к документации или логам системы")

    def get_active_blocks(self) -> List[BlockingAlert]:
        """Получить список активных блокировок"""
        return [alert for alert in self.active_blocks.values() if not alert.resolved]

    def resolve_block(self, alert_key: str) -> bool:
        """Пометить блокировку как решенную"""
        if alert_key in self.active_blocks:
            self.active_blocks[alert_key].resolved = True
            del self.active_blocks[alert_key]
            self.logger.info(f"✅ Блокировка решена: {alert_key}")
            return True
        return False

    def auto_resolve_expired_blocks(self) -> int:
        """Автоматически решить устаревшие блокировки"""
        resolved_count = 0
        current_time = datetime.now()

        # Время автоматического решения по типу блокировки
        auto_resolve_times = {
            "rate_limit": timedelta(minutes=10),
            "api_error": timedelta(minutes=15),
            "api_performance": timedelta(minutes=20),
            "strategy_filter": timedelta(minutes=5),
        }

        keys_to_resolve = []
        for key, alert in self.active_blocks.items():
            if alert.resolved:
                continue

            auto_resolve_time = auto_resolve_times.get(alert.reason.value)
            if auto_resolve_time and (current_time - alert.timestamp) > auto_resolve_time:
                keys_to_resolve.append(key)

        for key in keys_to_resolve:
            self.resolve_block(key)
            resolved_count += 1

        return resolved_count

    def get_blocking_stats(self) -> Dict[str, Any]:
        """Получить статистику блокировок"""
        total_blocks = len(self.block_history)

        if total_blocks == 0:
            return {"total_blocks": 0, "message": "Блокировок не было"}

        # Считаем по причинам
        by_reason = {}
        by_severity = {}

        for alert in self.block_history:
            reason = alert.reason.value
            severity = alert.severity

            by_reason[reason] = by_reason.get(reason, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1

        # Активные блокировки
        active_blocks = self.get_active_blocks()

        return {
            "total_blocks": total_blocks,
            "active_blocks": len(active_blocks),
            "by_reason": by_reason,
            "by_severity": by_severity,
            "last_24h": len([a for a in self.block_history
                           if datetime.now() - a.timestamp < timedelta(hours=24)]),
            "last_1h": len([a for a in self.block_history
                          if datetime.now() - a.timestamp < timedelta(hours=1)]),
            "most_common_reason": max(by_reason.items(), key=lambda x: x[1])[0] if by_reason else "none",
            "recent_blocks": [
                {
                    "strategy": alert.strategy,
                    "symbol": alert.symbol,
                    "reason": alert.reason.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp.strftime('%H:%M:%S'),
                    "severity": alert.severity
                }
                for alert in self.block_history[-10:]  # Последние 10
            ]
        }

    def clear_old_history(self, hours: int = 24) -> int:
        """Очистить старую историю блокировок"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        initial_count = len(self.block_history)

        self.block_history = [
            alert for alert in self.block_history
            if alert.timestamp > cutoff_time
        ]

        cleared_count = initial_count - len(self.block_history)
        if cleared_count > 0:
            self.logger.info(f"🧹 Очищено {cleared_count} старых блокировок")

        return cleared_count

# Глобальный экземпляр менеджера
_blocking_manager = None

def get_blocking_alerts_manager(telegram_bot=None) -> BlockingAlertsManager:
    """Получить глобальный менеджер блокировок"""
    global _blocking_manager
    if _blocking_manager is None:
        _blocking_manager = BlockingAlertsManager(telegram_bot)
    return _blocking_manager

def report_order_block(reason: str, symbol: str, strategy: str,
                      message: str, details: Dict[str, Any] = None) -> None:
    """Упрощенная функция для сообщения о блокировке"""
    manager = get_blocking_alerts_manager()
    manager.report_order_block(reason, symbol, strategy, message, details)