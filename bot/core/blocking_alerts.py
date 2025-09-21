# bot/core/blocking_alerts.py
"""
🚨 СИСТЕМА ОПОВЕЩЕНИЙ О БЛОКИРОВКЕ ТОРГОВЛИ
КРИТИЧЕСКИ ВАЖНО: Каждая блокировка должна быть ГРОМКО озвучена!

Функции:
- Мгновенные уведомления в Telegram о любых блокировках
- Периодические отчеты о состоянии торговли
- Диагностика причин блокировки
- Эскалация при длительной блокировке
"""

import threading
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json


class BlockType(Enum):
    """Типы блокировок"""
    POSITION_CONFLICT = "position_conflict"
    RATE_LIMIT = "rate_limit"
    EMERGENCY_STOP = "emergency_stop"
    DUPLICATE_ORDER = "duplicate_order"
    RISK_LIMIT = "risk_limit"
    API_ERROR = "api_error"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    UNKNOWN = "unknown"


class Severity(Enum):
    """Уровни критичности"""
    LOW = "low"           # Единичная блокировка
    MEDIUM = "medium"     # Повторяющиеся блокировки
    HIGH = "high"         # Массовые блокировки
    CRITICAL = "critical" # Полная остановка торговли


@dataclass
class BlockEvent:
    """Событие блокировки"""
    timestamp: datetime
    block_type: BlockType
    severity: Severity
    symbol: str
    strategy: str
    reason: str
    details: Dict[str, Any]
    telegram_sent: bool = False


class BlockingAlertsManager:
    """
    🚨 МЕНЕДЖЕР ОПОВЕЩЕНИЙ О БЛОКИРОВКАХ

    Отслеживает все блокировки и громко о них сообщает!
    """

    def __init__(self, telegram_bot=None):
        self.telegram_bot = telegram_bot
        self.logger = logging.getLogger('blocking_alerts')

        # История блокировок
        self.block_events: List[BlockEvent] = []
        self.last_alert_time = {}

        # Счетчики для анализа
        self.block_counters = {block_type: 0 for block_type in BlockType}
        self.consecutive_blocks = 0
        self.last_successful_trade = None

        # Thread safety
        self._lock = threading.RLock()

        # Настройки
        self.alert_cooldown = 300  # 5 минут между повторными уведомлениями одного типа
        self.escalation_threshold = 10  # Эскалация после 10 блокировок
        self.critical_threshold = 50   # Критичный уровень после 50 блокировок

        # Запускаем фоновый мониторинг
        self._start_monitoring_thread()

        self.logger.info("🚨 BlockingAlertsManager активирован - все блокировки будут озвучены!")

    def report_block(self, block_type: BlockType, symbol: str, strategy: str,
                    reason: str, details: Dict[str, Any] = None) -> None:
        """
        🚨 ОСНОВНАЯ ФУНКЦИЯ: Сообщить о блокировке

        Args:
            block_type: Тип блокировки
            symbol: Торговая пара
            strategy: Стратегия
            reason: Причина блокировки
            details: Дополнительные детали
        """
        with self._lock:
            # Определяем критичность
            severity = self._calculate_severity(block_type)

            # Создаем событие
            event = BlockEvent(
                timestamp=datetime.now(timezone.utc),
                block_type=block_type,
                severity=severity,
                symbol=symbol,
                strategy=strategy,
                reason=reason,
                details=details or {}
            )

            # Добавляем в историю
            self.block_events.append(event)
            self.block_counters[block_type] += 1
            self.consecutive_blocks += 1

            # Логируем локально
            self._log_block_event(event)

            # Отправляем уведомление
            self._send_block_notification(event)

            # Проверяем эскалацию
            self._check_escalation()

            # Ограничиваем историю
            if len(self.block_events) > 1000:
                self.block_events = self.block_events[-500:]

    def report_successful_trade(self, symbol: str, strategy: str, order_id: str) -> None:
        """Сообщить об успешной сделке (сбрасывает счетчики)"""
        with self._lock:
            self.consecutive_blocks = 0
            self.last_successful_trade = datetime.now(timezone.utc)

            # Отправляем уведомление о восстановлении торговли если было много блокировок
            if sum(self.block_counters.values()) > 5:
                self._send_recovery_notification(symbol, strategy, order_id)

    def _calculate_severity(self, block_type: BlockType) -> Severity:
        """Определение критичности блокировки"""

        # Критичные типы блокировок
        if block_type in [BlockType.EMERGENCY_STOP, BlockType.POSITION_CONFLICT]:
            if self.consecutive_blocks >= self.critical_threshold:
                return Severity.CRITICAL
            elif self.consecutive_blocks >= self.escalation_threshold:
                return Severity.HIGH
            else:
                return Severity.MEDIUM

        # Средние типы
        elif block_type in [BlockType.RATE_LIMIT, BlockType.RISK_LIMIT]:
            if self.consecutive_blocks >= 20:
                return Severity.HIGH
            else:
                return Severity.MEDIUM

        # Низкие типы
        else:
            return Severity.LOW

    def _log_block_event(self, event: BlockEvent) -> None:
        """Логирование блокировки"""
        level = {
            Severity.LOW: logging.WARNING,
            Severity.MEDIUM: logging.ERROR,
            Severity.HIGH: logging.CRITICAL,
            Severity.CRITICAL: logging.CRITICAL
        }[event.severity]

        emoji = {
            Severity.LOW: "⚠️",
            Severity.MEDIUM: "🚫",
            Severity.HIGH: "🚨",
            Severity.CRITICAL: "💀"
        }[event.severity]

        self.logger.log(level, f"{emoji} БЛОКИРОВКА {event.block_type.value.upper()}: "
                             f"{event.strategy} на {event.symbol} - {event.reason}")

    def _send_block_notification(self, event: BlockEvent) -> None:
        """Отправка уведомления в Telegram"""
        if not self.telegram_bot:
            return

        # Проверяем cooldown для данного типа блокировки
        cooldown_key = f"{event.block_type.value}_{event.symbol}"
        now = datetime.now(timezone.utc)

        if cooldown_key in self.last_alert_time:
            time_diff = (now - self.last_alert_time[cooldown_key]).total_seconds()
            if time_diff < self.alert_cooldown and event.severity != Severity.CRITICAL:
                return  # Пропускаем повторное уведомление

        # Формируем сообщение
        emoji = {
            Severity.LOW: "⚠️",
            Severity.MEDIUM: "🚫",
            Severity.HIGH: "🚨",
            Severity.CRITICAL: "💀🚨💀"
        }[event.severity]

        severity_text = {
            Severity.LOW: "Предупреждение",
            Severity.MEDIUM: "Ошибка",
            Severity.HIGH: "КРИТИЧЕСКАЯ ОШИБКА",
            Severity.CRITICAL: "🚨 АВАРИЙНАЯ СИТУАЦИЯ 🚨"
        }[event.severity]

        message = f"""
{emoji} {severity_text}

🚫 ТОРГОВЛЯ ЗАБЛОКИРОВАНА!

📊 Детали:
• Тип: {event.block_type.value.replace('_', ' ').title()}
• Символ: {event.symbol}
• Стратегия: {event.strategy}
• Причина: {event.reason}

📈 Статистика:
• Подряд блокировок: {self.consecutive_blocks}
• Всего блокировок: {sum(self.block_counters.values())}
• Последняя сделка: {self._format_last_trade()}

⏰ Время: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""

        if event.severity == Severity.CRITICAL:
            message += f"\n💀 ТРЕБУЕТСЯ НЕМЕДЛЕННОЕ ВМЕШАТЕЛЬСТВО!"
            message += f"\n🔧 Проверьте состояние системы и позиции"

        try:
            self.telegram_bot.send_admin_message(message)
            event.telegram_sent = True
            self.last_alert_time[cooldown_key] = now

            self.logger.info(f"📱 Уведомление о блокировке отправлено в Telegram")

        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки уведомления в Telegram: {e}")

    def _send_recovery_notification(self, symbol: str, strategy: str, order_id: str) -> None:
        """Уведомление о восстановлении торговли"""
        if not self.telegram_bot:
            return

        total_blocks = sum(self.block_counters.values())

        message = f"""
✅ ТОРГОВЛЯ ВОССТАНОВЛЕНА!

🎉 Успешная сделка:
• Символ: {symbol}
• Стратегия: {strategy}
• Order ID: {order_id}

📊 Статистика восстановления:
• Было блокировок: {total_blocks}
• Подряд блокировок: {self.consecutive_blocks}
• Время восстановления: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

🎯 Система торгует нормально!
"""

        try:
            self.telegram_bot.send_admin_message(message)
            self.logger.info("📱 Уведомление о восстановлении отправлено")
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки уведомления о восстановлении: {e}")

    def _check_escalation(self) -> None:
        """Проверка необходимости эскалации"""
        if self.consecutive_blocks >= self.critical_threshold:
            self._send_critical_escalation()
        elif self.consecutive_blocks >= self.escalation_threshold:
            self._send_high_escalation()

    def _send_critical_escalation(self) -> None:
        """Критическая эскалация"""
        if not self.telegram_bot:
            return

        message = f"""
💀🚨💀 КРИТИЧЕСКАЯ ЭСКАЛАЦИЯ 💀🚨💀

🚫 СИСТЕМА ПОЛНОСТЬЮ ЗАБЛОКИРОВАНА!

⚠️ {self.consecutive_blocks} БЛОКИРОВОК ПОДРЯД!

📊 Анализ блокировок:
"""

        for block_type, count in self.block_counters.items():
            if count > 0:
                message += f"• {block_type.value}: {count}\n"

        message += f"""
⏰ Последняя сделка: {self._format_last_trade()}

🔧 ТРЕБУЕМЫЕ ДЕЙСТВИЯ:
1. Проверить позиции на бирже
2. Проверить баланс и лимиты
3. Перезапустить систему при необходимости
4. Связаться с администратором

💀 ТОРГОВЛЯ ОСТАНОВЛЕНА!
"""

        try:
            self.telegram_bot.send_admin_message(message)
            self.logger.critical("💀 Критическая эскалация отправлена!")
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки критической эскалации: {e}")

    def _send_high_escalation(self) -> None:
        """Высокая эскалация"""
        if not self.telegram_bot:
            return

        message = f"""
🚨 ВЫСОКАЯ ЭСКАЛАЦИЯ

⚠️ {self.consecutive_blocks} блокировок подряд!

Система испытывает серьезные проблемы с торговлей.
Рекомендуется проверить состояние и принять меры.

📊 Топ блокировок:
"""

        sorted_blocks = sorted(self.block_counters.items(), key=lambda x: x[1], reverse=True)
        for block_type, count in sorted_blocks[:3]:
            if count > 0:
                message += f"• {block_type.value}: {count}\n"

        try:
            self.telegram_bot.send_admin_message(message)
            self.logger.error("🚨 Высокая эскалация отправлена!")
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки высокой эскалации: {e}")

    def _format_last_trade(self) -> str:
        """Форматирование времени последней сделки"""
        if not self.last_successful_trade:
            return "Нет данных"

        now = datetime.now(timezone.utc)
        diff = now - self.last_successful_trade

        if diff.days > 0:
            return f"{diff.days} дней назад"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600} часов назад"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60} минут назад"
        else:
            return "Менее минуты назад"

    def _start_monitoring_thread(self) -> None:
        """Запуск фонового мониторинга"""
        def monitoring_loop():
            while True:
                try:
                    time.sleep(1800)  # Каждые 30 минут
                    self._periodic_health_check()
                except Exception as e:
                    self.logger.error(f"Ошибка в мониторинге: {e}")
                    time.sleep(300)  # При ошибке ждем 5 минут

        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()

    def _periodic_health_check(self) -> None:
        """Периодическая проверка здоровья системы"""
        with self._lock:
            now = datetime.now(timezone.utc)

            # Если нет сделок долгое время - отправляем предупреждение
            if self.last_successful_trade:
                time_since_trade = now - self.last_successful_trade

                if time_since_trade > timedelta(hours=2) and self.telegram_bot:
                    total_blocks = sum(self.block_counters.values())

                    if total_blocks > 0:
                        message = f"""
⏰ ПЕРИОДИЧЕСКИЙ ОТЧЕТ

🚫 Торговля заблокирована уже {self._format_last_trade()}

📊 Блокировки за период:
"""
                        for block_type, count in self.block_counters.items():
                            if count > 0:
                                message += f"• {block_type.value}: {count}\n"

                        message += f"\n💡 Рекомендуется проверить систему"

                        try:
                            self.telegram_bot.send_admin_message(message)
                        except Exception as e:
                            self.logger.error(f"Ошибка периодического отчета: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики блокировок"""
        with self._lock:
            return {
                "total_blocks": sum(self.block_counters.values()),
                "consecutive_blocks": self.consecutive_blocks,
                "block_breakdown": dict(self.block_counters),
                "last_successful_trade": self.last_successful_trade.isoformat() if self.last_successful_trade else None,
                "recent_events": len([e for e in self.block_events if (datetime.now(timezone.utc) - e.timestamp).seconds < 3600])
            }


# Глобальный экземпляр
_blocking_alerts_manager = None
_manager_lock = threading.RLock()


def get_blocking_alerts_manager(telegram_bot=None) -> BlockingAlertsManager:
    """Получение синглтона менеджера оповещений"""
    global _blocking_alerts_manager

    if _blocking_alerts_manager is None:
        with _manager_lock:
            if _blocking_alerts_manager is None:
                _blocking_alerts_manager = BlockingAlertsManager(telegram_bot)

    return _blocking_alerts_manager


def report_order_block(block_type: str, symbol: str, strategy: str, reason: str, details: Dict[str, Any] = None):
    """Быстрая функция для сообщения о блокировке ордера"""
    try:
        block_enum = BlockType(block_type)
    except ValueError:
        block_enum = BlockType.UNKNOWN

    manager = get_blocking_alerts_manager()
    manager.report_block(block_enum, symbol, strategy, reason, details)


def report_successful_order(symbol: str, strategy: str, order_id: str):
    """Быстрая функция для сообщения об успешном ордере"""
    manager = get_blocking_alerts_manager()
    manager.report_successful_trade(symbol, strategy, order_id)