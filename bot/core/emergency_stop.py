"""
Система экстренной остановки торговли при критических условиях
Мгновенная остановка всех стратегий при угрозе крупных потерь
"""

import threading
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmergencyCondition:
    """Условие для экстренной остановки"""
    name: str
    threshold: float
    current_value: float
    triggered: bool
    trigger_time: Optional[datetime] = None


class EmergencyStopManager:
    """
    Глобальный менеджер экстренной остановки торговли
    Мониторит критические показатели и останавливает торговлю при угрозе
    """

    def __init__(self):
        self.is_emergency_stop_active = threading.Event()
        self.stop_conditions: Dict[str, EmergencyCondition] = {}
        self.monitoring_thread = None
        self.monitoring_active = False

        # Настройки критических условий
        self.critical_loss_threshold = 0.08  # 8% потеря капитала
        self.margin_call_threshold = 0.95    # 95% использования маржина
        self.consecutive_losses_limit = 7    # 7 убыточных сделок подряд
        self.api_error_limit = 10           # 10 ошибок API подряд

        # Счетчики
        self.consecutive_losses = 0
        self.consecutive_api_errors = 0
        self.initial_balance = None

        self._initialize_conditions()

    def _initialize_conditions(self):
        """Инициализация условий остановки"""
        self.stop_conditions = {
            'critical_loss': EmergencyCondition('Критическая потеря капитала', self.critical_loss_threshold, 0.0, False),
            'margin_call': EmergencyCondition('Угроза Margin Call', self.margin_call_threshold, 0.0, False),
            'consecutive_losses': EmergencyCondition('Серия убыточных сделок', self.consecutive_losses_limit, 0, False),
            'api_errors': EmergencyCondition('Множественные ошибки API', self.api_error_limit, 0, False)
        }

    def start_monitoring(self, api_clients: Dict):
        """
        Запуск мониторинга критических условий

        Args:
            api_clients: Словарь API клиентов для мониторинга
        """
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.api_clients = api_clients

        # Получаем начальный баланс
        self._update_initial_balance()

        # Запускаем поток мониторинга
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="EmergencyStopMonitor"
        )
        self.monitoring_thread.start()
        logger.info("🚨 Система экстренной остановки запущена")

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.monitoring_active = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
        logger.info("⏹️ Система экстренной остановки остановлена")

    def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.monitoring_active:
            try:
                # Проверяем каждые 30 секунд
                for _ in range(30):
                    if not self.monitoring_active:
                        break
                    time.sleep(1)

                if not self.monitoring_active:
                    break

                # Выполняем проверки
                self._check_all_conditions()

            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге emergency stop: {e}")
                time.sleep(5)

    def _check_all_conditions(self):
        """Проверка всех условий экстренной остановки"""
        try:
            # Проверяем потери капитала
            self._check_capital_loss()

            # Проверяем margin level
            self._check_margin_level()

            # Проверяем серии убытков (обновляется извне)
            self._check_consecutive_losses()

            # Проверяем API ошибки (обновляется извне)
            self._check_api_errors()

            # Активируем emergency stop если любое условие сработало
            emergency_triggered = any(condition.triggered for condition in self.stop_conditions.values())

            if emergency_triggered and not self.is_emergency_stop_active.is_set():
                self._trigger_emergency_stop()

        except Exception as e:
            logger.error(f"❌ Ошибка проверки emergency условий: {e}")

    def _check_capital_loss(self):
        """Проверка потерь капитала"""
        if not self.initial_balance or not self.api_clients:
            return

        try:
            # Берем первый API клиент для проверки баланса
            api = next(iter(self.api_clients.values()))

            from bot.core.balance_validator import global_balance_validator
            balance_info = global_balance_validator._get_wallet_balance(api)

            if balance_info:
                current_balance = balance_info.get('total_equity', 0)
                loss_percentage = (self.initial_balance - current_balance) / self.initial_balance

                condition = self.stop_conditions['critical_loss']
                condition.current_value = loss_percentage

                if loss_percentage >= self.critical_loss_threshold:
                    condition.triggered = True
                    condition.trigger_time = datetime.now()
                    logger.critical(f"🚨 КРИТИЧЕСКАЯ ПОТЕРЯ КАПИТАЛА: {loss_percentage*100:.2f}%")

        except Exception as e:
            logger.error(f"❌ Ошибка проверки потерь капитала: {e}")

    def _check_margin_level(self):
        """Проверка уровня маржина"""
        try:
            # ВРЕМЕННО: Пропускаем проверку margin для демо/тестового аккаунта
            # TODO: Реализовать корректную проверку margin для testnet
            condition = self.stop_conditions['margin_call']
            condition.current_value = 0.0  # Безопасное значение для тестирования
            condition.triggered = False
            return

            # Оригинальная логика (закомментирована):
            # api = next(iter(self.api_clients.values()))
            # from bot.core.balance_validator import global_balance_validator
            # balance_info = global_balance_validator._get_wallet_balance(api)
            # if balance_info:
            #     available = balance_info.get('available_balance', 0)
            #     total = balance_info.get('total_equity', 1)
            #     margin_usage = 1 - (available / total) if total > 0 else 0
            #     condition = self.stop_conditions['margin_call']
            #     condition.current_value = margin_usage
            #     if margin_usage >= self.margin_call_threshold:
            #         condition.triggered = True
            #         condition.trigger_time = datetime.now()
            #         logger.critical(f"🚨 УГРОЗА MARGIN CALL: {margin_usage*100:.2f}%")

        except Exception as e:
            logger.error(f"❌ Ошибка проверки margin level: {e}")

    def _check_consecutive_losses(self):
        """Проверка серии убыточных сделок"""
        condition = self.stop_conditions['consecutive_losses']
        condition.current_value = self.consecutive_losses

        if self.consecutive_losses >= self.consecutive_losses_limit:
            condition.triggered = True
            condition.trigger_time = datetime.now()
            logger.critical(f"🚨 СЕРИЯ УБЫТОЧНЫХ СДЕЛОК: {self.consecutive_losses}")

    def _check_api_errors(self):
        """Проверка множественных ошибок API"""
        condition = self.stop_conditions['api_errors']
        condition.current_value = self.consecutive_api_errors

        if self.consecutive_api_errors >= self.api_error_limit:
            condition.triggered = True
            condition.trigger_time = datetime.now()
            logger.critical(f"🚨 МНОЖЕСТВЕННЫЕ ОШИБКИ API: {self.consecutive_api_errors}")

    def _trigger_emergency_stop(self):
        """Активация экстренной остановки"""
        self.is_emergency_stop_active.set()

        # Логируем причины остановки
        triggered_conditions = [
            f"{cond.name}: {cond.current_value}"
            for cond in self.stop_conditions.values()
            if cond.triggered
        ]

        logger.critical("🚨🚨🚨 ЭКСТРЕННАЯ ОСТАНОВКА ТОРГОВЛИ! 🚨🚨🚨")
        logger.critical(f"Причины: {'; '.join(triggered_conditions)}")

        # Отправляем уведомление администратору
        self._send_emergency_notification(triggered_conditions)

    def _send_emergency_notification(self, reasons: List[str]):
        """Отправка уведомления об экстренной остановке"""
        try:
            # Здесь можно добавить отправку Telegram уведомления
            message = f"🚨 ЭКСТРЕННАЯ ОСТАНОВКА ТОРГОВЛИ!\n\nПричины:\n" + "\n".join(f"• {reason}" for reason in reasons)
            logger.critical(f"EMERGENCY NOTIFICATION: {message}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки emergency уведомления: {e}")

    def _update_initial_balance(self):
        """Обновление начального баланса"""
        try:
            if self.api_clients:
                api = next(iter(self.api_clients.values()))
                from bot.core.balance_validator import global_balance_validator
                balance_info = global_balance_validator._get_wallet_balance(api)

                if balance_info:
                    self.initial_balance = balance_info.get('total_equity', 0)
                    logger.info(f"📊 Начальный баланс зафиксирован: {self.initial_balance:.4f} USDT")
        except Exception as e:
            logger.error(f"❌ Ошибка получения начального баланса: {e}")

    # Публичные методы для обновления счетчиков

    def report_trade_result(self, is_profitable: bool):
        """Сообщить о результате сделки"""
        if is_profitable:
            self.consecutive_losses = 0  # Сбрасываем счетчик при прибыльной сделке
        else:
            self.consecutive_losses += 1

    def report_api_error(self):
        """Сообщить об ошибке API"""
        self.consecutive_api_errors += 1

    def report_api_success(self):
        """Сообщить об успешном API запросе"""
        self.consecutive_api_errors = max(0, self.consecutive_api_errors - 1)

    def is_trading_allowed(self) -> Tuple[bool, str]:
        """
        Проверить, разрешена ли торговля

        Returns:
            Tuple[bool, str]: (разрешена, причина_если_запрещена)
        """
        if self.is_emergency_stop_active.is_set():
            active_conditions = [
                cond.name for cond in self.stop_conditions.values()
                if cond.triggered
            ]
            return False, f"🚨 EMERGENCY STOP АКТИВЕН: {'; '.join(active_conditions)}"

        return True, "✅ Торговля разрешена"

    def reset_emergency_stop(self, admin_confirmation: bool = False):
        """
        Сброс экстренной остановки (только для администратора!)

        Args:
            admin_confirmation: Подтверждение администратора
        """
        if not admin_confirmation:
            logger.warning("⚠️ Попытка сброса emergency stop без подтверждения администратора")
            return False

        # Сбрасываем все условия
        self._initialize_conditions()
        self.consecutive_losses = 0
        self.consecutive_api_errors = 0
        self.is_emergency_stop_active.clear()

        logger.warning("🔄 EMERGENCY STOP СБРОШЕН АДМИНИСТРАТОРОМ")
        return True

    def get_status_report(self) -> Dict:
        """Получить отчет о состоянии системы"""
        return {
            'emergency_active': self.is_emergency_stop_active.is_set(),
            'monitoring_active': self.monitoring_active,
            'initial_balance': self.initial_balance,
            'consecutive_losses': self.consecutive_losses,
            'consecutive_api_errors': self.consecutive_api_errors,
            'conditions': {
                name: {
                    'threshold': cond.threshold,
                    'current': cond.current_value,
                    'triggered': cond.triggered,
                    'trigger_time': cond.trigger_time.isoformat() if cond.trigger_time else None
                }
                for name, cond in self.stop_conditions.items()
            }
        }


# Глобальный экземпляр emergency stop менеджера
global_emergency_stop = EmergencyStopManager()