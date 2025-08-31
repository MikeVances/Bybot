# bot/services/smart_notifications.py
# 💜 УМНЫЕ УВЕДОМЛЕНИЯ для Telegram бота
# Контекстные, персонализированные, не раздражающие!

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from .ux_config import (
    UXEmojis, NotificationType, ux_config, 
    get_status_emoji, format_money
)

@dataclass
class SmartNotification:
    """Умное уведомление с контекстом"""
    
    id: str
    type: NotificationType
    title: str
    message: str
    data: Dict[str, Any]
    priority: int
    expires_at: datetime
    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    action_buttons: Optional[List[Dict]] = None
    
    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    @property
    def is_read(self) -> bool:
        return self.read_at is not None

class NotificationManager:
    """🚀 Менеджер умных уведомлений"""
    
    def __init__(self, bot: Bot, admin_chat_id: str):
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.logger = logging.getLogger(__name__)
        
        # Активные уведомления
        self.active_notifications: Dict[str, SmartNotification] = {}
        self.notification_history: List[SmartNotification] = []
        
        # Настройки персонализации
        self.user_preferences: Dict[str, Dict] = {}
        
        # Rate limiting для предотвращения спама
        self.rate_limits: Dict[str, List[datetime]] = {}
        
        # Контекстный анализ
        self.context_analyzer = ContextAnalyzer()
        
    async def send_smart_notification(
        self, 
        notification_type: str,
        title: str,
        message: str,
        data: Dict = None,
        priority: int = 3,
        ttl_minutes: int = 60,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Отправка умного уведомления с контекстным анализом
        
        Args:
            notification_type: Тип уведомления
            title: Заголовок
            message: Текст сообщения
            data: Дополнительные данные
            priority: Приоритет (1-5, где 1 = критический)
            ttl_minutes: Время жизни уведомления
            user_id: ID пользователя (если None, то админу)
        """
        
        try:
            # Создаём уникальный ID уведомления
            notification_id = f"{notification_type}_{datetime.now().timestamp()}"
            
            # Проверяем rate limiting
            if not self._check_rate_limit(notification_type, priority):
                self.logger.debug(f"Rate limit exceeded for {notification_type}")
                return False
            
            # Анализируем контекст и персонализируем
            enhanced_notification = await self._enhance_notification(
                notification_type, title, message, data or {}, priority
            )
            
            # Проверяем, нужно ли отправлять это уведомление
            if not self._should_send_notification(enhanced_notification, user_id):
                return False
            
            # Создаём объект уведомления
            notification = SmartNotification(
                id=notification_id,
                type=NotificationType.HIGH,  # Определим динамически
                title=enhanced_notification['title'],
                message=enhanced_notification['message'],
                data=enhanced_notification['data'],
                priority=priority,
                expires_at=datetime.now() + timedelta(minutes=ttl_minutes),
                action_buttons=enhanced_notification.get('buttons')
            )
            
            # Отправляем уведомление
            success = await self._send_notification_to_telegram(notification, user_id)
            
            if success:
                notification.sent_at = datetime.now()
                self.active_notifications[notification_id] = notification
                self.logger.info(f"Smart notification sent: {notification_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error sending smart notification: {e}")
            return False
    
    def _check_rate_limit(self, notification_type: str, priority: int) -> bool:
        """Проверка rate limiting"""
        
        now = datetime.now()
        
        # Критические уведомления всегда пропускаем
        if priority == 1:
            return True
        
        # Получаем историю отправок для этого типа
        if notification_type not in self.rate_limits:
            self.rate_limits[notification_type] = []
        
        history = self.rate_limits[notification_type]
        
        # Очищаем старые записи (старше 1 часа)
        cutoff = now - timedelta(hours=1)
        history[:] = [ts for ts in history if ts > cutoff]
        
        # Проверяем лимиты в зависимости от приоритета
        limits = {
            1: 100,  # Критические - без лимита практически
            2: 20,   # Высокий приоритет - 20 в час
            3: 10,   # Средний - 10 в час
            4: 5,    # Низкий - 5 в час
            5: 3     # Информационные - 3 в час
        }
        
        limit = limits.get(priority, 5)
        
        if len(history) >= limit:
            return False
        
        # Добавляем текущую отправку
        history.append(now)
        return True
    
    async def _enhance_notification(
        self, 
        notification_type: str, 
        title: str, 
        message: str, 
        data: Dict, 
        priority: int
    ) -> Dict:
        """Улучшение уведомления с помощью контекстного анализа"""
        
        # Базовое улучшение
        enhanced = {
            'title': title,
            'message': message,
            'data': data,
            'buttons': []
        }
        
        # Добавляем контекстные улучшения в зависимости от типа
        if notification_type == 'trading_signal':
            enhanced = await self._enhance_trading_signal(enhanced)
        elif notification_type == 'balance_change':
            enhanced = await self._enhance_balance_notification(enhanced)
        elif notification_type == 'ai_insight':
            enhanced = await self._enhance_ai_notification(enhanced)
        elif notification_type == 'system_alert':
            enhanced = await self._enhance_system_alert(enhanced)
        
        # Добавляем временной контекст
        enhanced['title'] = f"{get_status_emoji('active')} {enhanced['title']}"
        
        # Добавляем временную метку для критических уведомлений
        if priority <= 2:
            time_str = datetime.now().strftime("%H:%M")
            enhanced['message'] = f"🕐 *{time_str}* | {enhanced['message']}"
        
        return enhanced
    
    async def _enhance_trading_signal(self, notification: Dict) -> Dict:
        """Улучшение торговых сигналов"""
        
        data = notification['data']
        
        # Добавляем контекстную информацию
        if 'strategy' in data:
            strategy = data['strategy']
            notification['title'] = f"📈 {strategy} Signal"
        
        if 'signal' in data and 'entry_price' in data:
            signal_type = data['signal']
            price = data['entry_price']
            
            emoji = "🟢" if signal_type == "BUY" else "🔴"
            notification['message'] = f"{emoji} *{signal_type}* at ${price:.2f}\n{notification['message']}"
        
        # Добавляем quick action кнопки
        notification['buttons'] = [
            {'text': '📊 View Position', 'callback': f"view_position_{data.get('symbol', 'BTCUSDT')}"},
            {'text': '⚙️ Settings', 'callback': 'trading_settings'},
            {'text': '🚫 Disable Strategy', 'callback': f"disable_{data.get('strategy', 'unknown')}"}
        ]
        
        return notification
    
    async def _enhance_balance_notification(self, notification: Dict) -> Dict:
        """Улучшение уведомлений о балансе"""
        
        data = notification['data']
        
        if 'balance_change' in data:
            change = data['balance_change']
            emoji = "📈" if change > 0 else "📉"
            formatted_change = format_money(abs(change))
            
            notification['title'] = f"{emoji} Balance {'Increased' if change > 0 else 'Decreased'}"
            notification['message'] = f"Change: {'+' if change > 0 else '-'}{formatted_change}\n{notification['message']}"
        
        # Кнопки для быстрых действий
        notification['buttons'] = [
            {'text': '💰 Full Balance', 'callback': 'balance_detail'},
            {'text': '📊 Analytics', 'callback': 'analytics_main'}
        ]
        
        return notification
    
    async def _enhance_ai_notification(self, notification: Dict) -> Dict:
        """Улучшение AI-уведомлений"""
        
        data = notification['data']
        
        # Добавляем AI-специфичную информацию
        if 'confidence' in data:
            confidence = data['confidence']
            confidence_emoji = "🎯" if confidence > 0.8 else "💡" if confidence > 0.6 else "🤔"
            
            notification['title'] = f"{confidence_emoji} AI Insight ({confidence*100:.0f}%)"
        
        if 'recommendation' in data:
            rec = data['recommendation']
            notification['message'] = f"🧠 *Recommendation:* {rec}\n{notification['message']}"
        
        # AI-специфичные кнопки
        notification['buttons'] = [
            {'text': '🧠 AI Dashboard', 'callback': 'ai_insights'},
            {'text': '📊 Model Stats', 'callback': 'ai_model_stats'},
            {'text': '🎯 Predictions', 'callback': 'ai_predictions'}
        ]
        
        return notification
    
    async def _enhance_system_alert(self, notification: Dict) -> Dict:
        """Улучшение системных алертов"""
        
        data = notification['data']
        
        # Определяем тип системного алерта
        alert_type = data.get('alert_type', 'general')
        
        type_emojis = {
            'error': '🚨',
            'warning': '⚠️',
            'info': 'ℹ️',
            'success': '✅',
            'maintenance': '🔧'
        }
        
        emoji = type_emojis.get(alert_type, '📢')
        notification['title'] = f"{emoji} System Alert"
        
        # Системные кнопки
        notification['buttons'] = [
            {'text': '📊 System Status', 'callback': 'system_status'},
            {'text': '🔧 Settings', 'callback': 'settings_main'}
        ]
        
        return notification
    
    def _should_send_notification(self, notification: Dict, user_id: Optional[str]) -> bool:
        """Определяем, нужно ли отправлять уведомление"""
        
        # Получаем предпочтения пользователя
        preferences = self.user_preferences.get(user_id or 'admin', {})
        
        # Проверяем, не отключены ли уведомления этого типа
        notification_type = notification['data'].get('type', 'general')
        
        if not preferences.get(f'enable_{notification_type}', True):
            return False
        
        # Проверяем время "не беспокоить"
        if self._is_quiet_hours(preferences):
            # Критические уведомления отправляем всегда
            if notification['data'].get('priority', 3) > 2:
                return False
        
        return True
    
    def _is_quiet_hours(self, preferences: Dict) -> bool:
        """Проверяем, не время ли 'не беспокоить'"""
        
        if not preferences.get('enable_quiet_hours', False):
            return False
        
        now = datetime.now()
        current_hour = now.hour
        
        quiet_start = preferences.get('quiet_hours_start', 23)
        quiet_end = preferences.get('quiet_hours_end', 7)
        
        # Обрабатываем случай, когда тихие часы переходят через полночь
        if quiet_start > quiet_end:
            return current_hour >= quiet_start or current_hour < quiet_end
        else:
            return quiet_start <= current_hour < quiet_end
    
    async def _send_notification_to_telegram(
        self, 
        notification: SmartNotification, 
        user_id: Optional[str]
    ) -> bool:
        """Отправка уведомления в Telegram"""
        
        try:
            # Формируем текст сообщения
            text = f"*{notification.title}*\n\n{notification.message}"
            
            # Создаём клавиатуру если есть кнопки
            reply_markup = None
            if notification.action_buttons:
                keyboard = []
                for button in notification.action_buttons:
                    keyboard.append([
                        InlineKeyboardButton(
                            button['text'], 
                            callback_data=button['callback']
                        )
                    ])
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Определяем chat_id
            chat_id = user_id if user_id else self.admin_chat_id
            
            # Отправляем сообщение
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
                disable_notification=notification.priority > 3  # Тихие уведомления для низкого приоритета
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending to Telegram: {e}")
            return False
    
    async def send_trading_signal_notification(
        self, 
        strategy: str, 
        signal: str, 
        entry_price: float, 
        symbol: str = "BTCUSDT"
    ):
        """Специализированное уведомление для торговых сигналов"""
        
        await self.send_smart_notification(
            notification_type='trading_signal',
            title=f'{strategy} Trading Signal',
            message=f'New {signal} signal detected',
            data={
                'strategy': strategy,
                'signal': signal,
                'entry_price': entry_price,
                'symbol': symbol,
                'type': 'trading_signal'
            },
            priority=2,  # Высокий приоритет
            ttl_minutes=30
        )
    
    async def send_balance_change_notification(
        self, 
        new_balance: float, 
        change: float, 
        reason: str = "Trading activity"
    ):
        """Уведомление об изменении баланса"""
        
        await self.send_smart_notification(
            notification_type='balance_change',
            title='Balance Update',
            message=f'Balance changed due to {reason}',
            data={
                'new_balance': new_balance,
                'balance_change': change,
                'reason': reason,
                'type': 'balance_change'
            },
            priority=3 if abs(change) < 100 else 2,  # Приоритет зависит от размера изменения
            ttl_minutes=120
        )
    
    async def send_ai_insight_notification(
        self, 
        insight: str, 
        confidence: float, 
        recommendation: str = None
    ):
        """AI-инсайт уведомление"""
        
        await self.send_smart_notification(
            notification_type='ai_insight',
            title='AI Market Insight',
            message=insight,
            data={
                'insight': insight,
                'confidence': confidence,
                'recommendation': recommendation,
                'type': 'ai_insight'
            },
            priority=3,
            ttl_minutes=90
        )
    
    def cleanup_expired_notifications(self):
        """Очистка просроченных уведомлений"""
        
        now = datetime.now()
        expired_ids = [
            notification_id for notification_id, notification 
            in self.active_notifications.items()
            if notification.is_expired
        ]
        
        for notification_id in expired_ids:
            expired_notification = self.active_notifications.pop(notification_id)
            self.notification_history.append(expired_notification)
            
        # Ограничиваем размер истории
        if len(self.notification_history) > 1000:
            self.notification_history = self.notification_history[-500:]
        
        if expired_ids:
            self.logger.debug(f"Cleaned up {len(expired_ids)} expired notifications")

class ContextAnalyzer:
    """🔍 Анализатор контекста для умных уведомлений"""
    
    def __init__(self):
        self.market_conditions = {}
        self.user_activity = {}
        self.trading_patterns = {}
    
    async def analyze_market_context(self) -> Dict:
        """Анализ рыночного контекста"""
        # Здесь будет логика анализа рыночных условий
        return {
            'volatility': 'medium',
            'trend': 'bullish',
            'volume': 'high',
            'sentiment': 'positive'
        }
    
    async def analyze_user_activity(self, user_id: str) -> Dict:
        """Анализ активности пользователя"""
        # Здесь будет логика анализа активности пользователя
        return {
            'last_active': datetime.now(),
            'activity_level': 'high',
            'preferred_notifications': ['trading_signals', 'balance_changes']
        }

# Экспорт
__all__ = [
    'SmartNotification', 'NotificationManager', 
    'ContextAnalyzer', 'NotificationType'
]