# bot/services/notification_service.py
"""
🔔 УВЕДОМИТЕЛЬНЫЙ СЕРВИС
Централизованная система отправки уведомлений через Telegram
"""

from datetime import datetime
from typing import Optional
from bot.core.secure_logger import get_secure_logger


class TelegramNotificationService:
    """
    📱 Сервис для отправки уведомлений через Telegram
    """
    
    def __init__(self, telegram_bot):
        """
        Инициализация сервиса уведомлений
        
        Args:
            telegram_bot: Экземпляр Telegram бота
        """
        self.telegram_bot = telegram_bot
        self.logger = get_secure_logger('notification_service')
    
    def send_position_opened(self, signal_type: str, strategy_name: str, 
                            entry_price: float, stop_loss: float, take_profit: float, 
                            trade_amount: float, signal_strength: Optional[float] = None, 
                            comment: str = "") -> None:
        """
        Отправка уведомления об открытии позиции
        
        Args:
            signal_type: Тип сигнала (BUY/SELL)
            strategy_name: Название стратегии
            entry_price: Цена входа
            stop_loss: Стоп-лосс
            take_profit: Тейк-профит
            trade_amount: Размер позиции
            signal_strength: Сила сигнала (опционально)
            comment: Дополнительный комментарий
        """
        try:
            emoji = "🟢" if signal_type == "BUY" else "🔴"
            side_text = "LONG" if signal_type == "BUY" else "SHORT"
            
            message = f"""
{emoji} НОВАЯ ПОЗИЦИЯ ОТКРЫТА

📊 Стратегия: {strategy_name}
🎯 Сторона: {side_text} ({signal_type})
💰 Цена входа: ${entry_price:,.2f}
📈 Размер: {trade_amount} BTC

🛡️ Стоп-лосс: ${stop_loss:,.2f}
🎯 Тейк-профит: ${take_profit:,.2f}

📊 Risk/Reward: {((take_profit - entry_price) / (entry_price - stop_loss)):.2f}
"""
            
            if signal_strength:
                message += f"💪 Сила сигнала: {signal_strength:.2f}\n"
            
            if comment:
                message += f"💬 Комментарий: {comment}\n"
            
            message += f"\n⏰ **Время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.telegram_bot.send_admin_message(message)
            self.logger.info(f"📱 Уведомление об открытии позиции отправлено: {strategy_name} {signal_type}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки уведомления об открытии позиции: {e}")
    
    def send_position_closed(self, strategy_name: str, side: str, exit_price: float, 
                            pnl: float, entry_price: Optional[float] = None, 
                            duration: Optional[str] = None) -> None:
        """
        Отправка уведомления о закрытии позиции
        
        Args:
            strategy_name: Название стратегии
            side: Сторона позиции (BUY/SELL)
            exit_price: Цена выхода
            pnl: Прибыль/убыток
            entry_price: Цена входа (опционально)
            duration: Длительность позиции (опционально)
        """
        try:
            if pnl > 0:
                emoji = "✅"
                status = "ПРИБЫЛЬ"
                color = "🟢"
            else:
                emoji = "❌"
                status = "УБЫТОК"
                color = "🔴"
            
            side_text = "LONG" if side == "BUY" else "SHORT"
            
            message = f"""
{emoji} ПОЗИЦИЯ ЗАКРЫТА {color}

📊 Стратегия: {strategy_name}
🎯 Сторона: {side_text} ({side})
💰 Цена выхода: ${exit_price:,.2f}

💵 Результат: {status}
💸 P&L: ${pnl:,.2f} ({pnl:+.2f}%)
"""
            
            if entry_price:
                change_pct = ((exit_price - entry_price) / entry_price * 100)
                if side == "SELL":
                    change_pct = -change_pct
                message += f"📈 Изменение цены: {change_pct:+.2f}%\n"
            
            if duration:
                message += f"⏱️ Длительность: {duration}\n"
            
            message += f"\n⏰ **Время закрытия:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.telegram_bot.send_admin_message(message)
            self.logger.info(f"📱 Уведомление о закрытии позиции отправлено: {strategy_name} P&L: ${pnl:.2f}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки уведомления о закрытии позиции: {e}")
    
    def send_risk_alert(self, alert_type: str, strategy_name: str, message: str) -> None:
        """
        Отправка предупреждения о рисках
        
        Args:
            alert_type: Тип предупреждения
            strategy_name: Название стратегии
            message: Сообщение
        """
        try:
            emoji = "⚠️" if alert_type == "WARNING" else "🚨"
            
            notification = f"""
{emoji} РИСК ПРЕДУПРЕЖДЕНИЕ

📊 Стратегия: {strategy_name}
🔔 Тип: {alert_type}
📝 Сообщение: {message}

⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            self.telegram_bot.send_admin_message(notification)
            self.logger.warning(f"⚠️ Отправлено риск-предупреждение: {strategy_name} - {alert_type}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки риск-предупреждения: {e}")
    
    def send_neural_recommendation(self, strategy: str, confidence: float) -> None:
        """
        Отправка рекомендации нейронной сети
        
        Args:
            strategy: Рекомендуемая стратегия
            confidence: Уровень уверенности
        """
        try:
            message = f"""
🧠 НЕЙРОННАЯ РЕКОМЕНДАЦИЯ

🎯 Стратегия: {strategy}
💪 Уверенность: {confidence:.1%}

⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            self.telegram_bot.send_admin_message(message)
            self.logger.info(f"🧠 Отправлена нейронная рекомендация: {strategy} ({confidence:.1%})")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки нейронной рекомендации: {e}")


# Глобальный экземпляр для использования в системе
_notification_service = None


def get_notification_service(telegram_bot=None):
    """
    Получение глобального экземпляра сервиса уведомлений
    
    Args:
        telegram_bot: Экземпляр Telegram бота (для первой инициализации)
        
    Returns:
        TelegramNotificationService: Экземпляр сервиса
    """
    global _notification_service
    
    if _notification_service is None and telegram_bot:
        _notification_service = TelegramNotificationService(telegram_bot)
    
    return _notification_service