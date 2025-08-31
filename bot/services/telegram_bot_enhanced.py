# bot/services/telegram_bot_enhanced.py
# 💜 ENHANCED TELEGRAM BOT - Мост между старым и новым UX
# Постепенная миграция с сохранением всего функционала

import logging
from typing import Dict, Optional, List
from datetime import datetime

from telegram import Update, Bot
from telegram.ext import Application, ContextTypes

# Импорт старого бота для совместимости
from .telegram_bot import TelegramBot

# Импорт новых UX компонентов
from .telegram_bot_ux import TelegramBotUX
from .smart_notifications import NotificationManager
from .ux_config import ux_config, UXEmojis, QUICK_ACTIONS_CONFIG

try:
    from config import TELEGRAM_TOKEN, ADMIN_CHAT_ID
except ImportError:
    TELEGRAM_TOKEN = None
    ADMIN_CHAT_ID = None

class EnhancedTelegramBot:
    """
    🚀 Расширенный Telegram бот с современным UX
    
    Особенности:
    - Обратная совместимость со старым ботом
    - Постепенная миграция пользователей на новый UX
    - Smart notifications
    - Персонализация интерфейса
    - A/B тестирование новых фич
    """
    
    def __init__(self, token: str):
        self.token = token
        self.logger = logging.getLogger(__name__)
        
        # Инициализируем компоненты
        self.app = Application.builder().token(token).build()
        self.bot_instance = Bot(token)
        
        # Старый бот для fallback
        self.legacy_bot = TelegramBot(token)
        
        # Новый UX бот
        self.ux_bot = TelegramBotUX(token)
        
        # Менеджер уведомлений
        self.notification_manager = NotificationManager(
            self.bot_instance, 
            ADMIN_CHAT_ID or "default"
        )
        
        # Пользовательские настройки
        self.user_settings: Dict[str, Dict] = {}
        
        # A/B тестирование
        self.ab_test_groups: Dict[str, str] = {}  # user_id -> group_name
        
        # Статистика использования
        self.usage_stats: Dict[str, int] = {
            'total_users': 0,
            'legacy_users': 0,
            'ux_users': 0,
            'messages_sent': 0
        }
        
        # Регистрируем обработчики
        self._register_unified_handlers()
        
        self.logger.info("🚀 Enhanced Telegram Bot initialized")
    
    def _register_unified_handlers(self):
        """Регистрация объединённых обработчиков"""
        
        # Импортируем обработчики из обоих ботов
        from telegram.ext import CommandHandler, CallbackQueryHandler
        
        # Основные команды с роутингом
        self.app.add_handler(CommandHandler("start", self._unified_start))
        self.app.add_handler(CommandHandler("help", self._unified_help))
        self.app.add_handler(CommandHandler("menu", self._unified_menu))
        self.app.add_handler(CommandHandler("dashboard", self._unified_dashboard))
        
        # Legacy команды
        self.app.add_handler(CommandHandler("balance", self._legacy_balance))
        self.app.add_handler(CommandHandler("position", self._legacy_position))
        self.app.add_handler(CommandHandler("strategies", self._legacy_strategies))
        self.app.add_handler(CommandHandler("trades", self._legacy_trades))
        self.app.add_handler(CommandHandler("logs", self._legacy_logs))
        
        # Новые UX команды
        self.app.add_handler(CommandHandler("ux", self._enable_ux_mode))
        self.app.add_handler(CommandHandler("classic", self._enable_legacy_mode))
        self.app.add_handler(CommandHandler("quick", self._quick_actions))
        
        # Unified callback handler
        self.app.add_handler(CallbackQueryHandler(self._unified_callback_handler))
    
    async def _unified_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Унифицированный /start с выбором UX"""
        
        user_id = str(update.effective_user.id)
        first_name = update.effective_user.first_name or "Пользователь"
        
        # Обновляем статистику
        if user_id not in self.user_settings:
            self.usage_stats['total_users'] += 1
            
        # Загружаем настройки пользователя
        user_prefs = self.user_settings.get(user_id, {})
        
        # Определяем A/B группу для нового пользователя
        if user_id not in self.ab_test_groups:
            import random
            # 70% получают новый UX, 30% - старый (для постепенной миграции)
            self.ab_test_groups[user_id] = "ux" if random.random() < 0.7 else "legacy"
        
        ab_group = self.ab_test_groups[user_id]
        preferred_mode = user_prefs.get('interface_mode', ab_group)
        
        # Показываем приветствие с выбором интерфейса
        welcome_text = (
            f"👋 *Привет, {first_name}!*\n\n"
            f"🚀 *Добро пожаловать в торговый бот следующего поколения!*\n\n"
            f"💜 У нас есть два интерфейса на выбор:\n\n"
            f"🎨 *MODERN UX* - Современный, красивый интерфейс\n"
            f"   • Smart Dashboard\n"
            f"   • Живые уведомления\n"
            f"   • AI-инсайты\n"
            f"   • Быстрые действия\n\n"
            f"📱 *CLASSIC* - Привычный функциональный интерфейс\n"
            f"   • Все основные функции\n"
            f"   • Проверенная стабильность\n"
            f"   • Знакомая навигация\n\n"
            f"Рекомендуем: *{'MODERN UX' if preferred_mode == 'ux' else 'CLASSIC'}*"
        )
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [
                InlineKeyboardButton("🚀 MODERN UX", callback_data="switch_to_ux"),
                InlineKeyboardButton("📱 CLASSIC", callback_data="switch_to_legacy")
            ],
            [
                InlineKeyboardButton(
                    f"⚡ {'MODERN' if preferred_mode == 'ux' else 'CLASSIC'} (Рекомендуем)", 
                    callback_data=f"switch_to_{preferred_mode}"
                )
            ],
            [
                InlineKeyboardButton("ℹ️ Подробнее о различиях", callback_data="interface_comparison")
            ]
        ]
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Сохраняем пользователя
        self.user_settings[user_id] = user_prefs
        self.logger.info(f"User {user_id} started bot, A/B group: {ab_group}, preferred: {preferred_mode}")
    
    async def _unified_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Унифицированный обработчик callback запросов"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        callback_data = query.data
        
        # Роутинг по типу callback
        if callback_data.startswith("switch_to_"):
            await self._handle_interface_switch(update, context, callback_data)
        elif callback_data == "interface_comparison":
            await self._show_interface_comparison(update, context)
        elif callback_data.startswith("ux_"):
            # Роутим в новый UX бот
            await self._route_to_ux_bot(update, context, callback_data)
        else:
            # Роутим в legacy бот
            await self._route_to_legacy_bot(update, context, callback_data)
    
    async def _handle_interface_switch(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Обработка переключения интерфейса"""
        
        user_id = str(update.callback_query.from_user.id)
        interface_mode = callback_data.replace("switch_to_", "")
        
        # Сохраняем предпочтение пользователя
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
        
        self.user_settings[user_id]['interface_mode'] = interface_mode
        
        # Обновляем статистику
        if interface_mode == "ux":
            self.usage_stats['ux_users'] += 1
        else:
            self.usage_stats['legacy_users'] += 1
        
        # Показываем соответствующий интерфейс
        if interface_mode == "ux":
            await self._show_ux_interface(update, context)
        else:
            await self._show_legacy_interface(update, context)
        
        # Отправляем уведомление о переключении
        mode_name = "Modern UX" if interface_mode == "ux" else "Classic"
        await self.notification_manager.send_smart_notification(
            notification_type='system_alert',
            title=f'Interface Switched',
            message=f'Переключен на {mode_name} интерфейс',
            data={
                'user_id': user_id,
                'new_mode': interface_mode,
                'type': 'interface_switch'
            },
            priority=4,  # Низкий приоритет
            ttl_minutes=5,
            user_id=user_id
        )
        
        self.logger.info(f"User {user_id} switched to {interface_mode} interface")
    
    async def _show_interface_comparison(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать сравнение интерфейсов"""
        
        comparison_text = (
            "🔍 *Сравнение интерфейсов*\n\n"
            
            "🚀 *MODERN UX:*\n"
            "✅ Современный дизайн\n"
            "✅ Smart Dashboard с live-данными\n"
            "✅ Контекстные уведомления\n" 
            "✅ AI-инсайты и рекомендации\n"
            "✅ Быстрые действия (Quick Actions)\n"
            "✅ Персонализация интерфейса\n"
            "✅ Адаптивная навигация\n"
            "⚠️ Новые фичи (могут быть баги)\n\n"
            
            "📱 *CLASSIC:*\n"
            "✅ Проверенная стабильность\n"
            "✅ Все основные функции\n"
            "✅ Простая навигация\n"
            "✅ Быстрая загрузка\n"
            "✅ Знакомый интерфейс\n"
            "⚠️ Менее современный дизайн\n"
            "⚠️ Базовые уведомления\n\n"
            
            "💡 *Рекомендация:* Попробуйте Modern UX - вы всегда можете переключиться обратно командой /classic"
        )
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [
                InlineKeyboardButton("🚀 Попробовать MODERN UX", callback_data="switch_to_ux"),
                InlineKeyboardButton("📱 Остаться на CLASSIC", callback_data="switch_to_legacy")
            ],
            [
                InlineKeyboardButton("🔙 Назад к выбору", callback_data="back_to_start")
            ]
        ]
        
        await update.callback_query.edit_message_text(
            comparison_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _show_ux_interface(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать новый UX интерфейс"""
        
        # Используем UX бот для отображения dashboard
        await self.ux_bot._show_smart_dashboard(update, context)
        
        # Отправляем приветственное сообщение для нового UX
        welcome_ux_text = (
            f"✨ *Добро пожаловать в Modern UX!* ✨\n\n"
            f"🎯 *Что нового:*\n"
            f"• Live-обновления данных каждые 30 сек\n"
            f"• Smart-уведомления с контекстом\n"
            f"• AI-рекомендации на основе анализа\n"
            f"• Быстрые действия одним кликом\n\n"
            f"💡 *Совет:* Используйте /quick для быстрого доступа к основным функциям\n"
            f"🔄 Хотите вернуться к классическому интерфейсу? Команда /classic"
        )
        
        await update.callback_query.message.reply_text(
            welcome_ux_text,
            parse_mode='Markdown'
        )
    
    async def _show_legacy_interface(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать классический интерфейс"""
        
        # Используем legacy бот для отображения меню
        await self.legacy_bot._menu(update, context)
        
        # Отправляем информацию о классическом интерфейсе
        welcome_legacy_text = (
            f"📱 *Классический интерфейс активен*\n\n"
            f"✅ Все привычные функции доступны\n"
            f"✅ Стабильная работа\n"
            f"✅ Быстрая навигация\n\n"
            f"💡 *Совет:* Попробуйте новый интерфейс командой /ux\n"
            f"📋 Доступные команды: /help"
        )
        
        await update.callback_query.message.reply_text(
            welcome_legacy_text,
            parse_mode='Markdown'
        )
    
    async def _route_to_ux_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Роутинг в UX бот"""
        
        # Убираем префикс "ux_"
        clean_callback = callback_data[3:]
        
        # Создаём новый callback query с очищенными данными
        update.callback_query.data = clean_callback
        
        # Роутим в UX бот
        await self.ux_bot._handle_callback(update, context)
    
    async def _route_to_legacy_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Роутинг в legacy бот"""
        
        # Роутим в legacy бот
        await self.legacy_bot._on_menu_button(update, context)
    
    async def _unified_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Унифицированный dashboard"""
        
        user_id = str(update.effective_user.id)
        user_prefs = self.user_settings.get(user_id, {})
        interface_mode = user_prefs.get('interface_mode', 'ux')
        
        if interface_mode == 'ux':
            await self.ux_bot._dashboard(update, context)
        else:
            await self.legacy_bot._menu(update, context)
    
    async def _quick_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Быстрые действия (всегда используют UX)"""
        await self.ux_bot._quick_actions(update, context)
    
    async def _enable_ux_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Принудительное включение UX режима"""
        
        user_id = str(update.effective_user.id)
        
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
            
        self.user_settings[user_id]['interface_mode'] = 'ux'
        
        await update.message.reply_text(
            "🚀 *Modern UX активирован!*\n\n"
            "Добро пожаловать в будущее трейдинга! ✨\n"
            "Используйте /dashboard для доступа к Smart Dashboard",
            parse_mode='Markdown'
        )
        
        await self.ux_bot._dashboard(update, context)
    
    async def _enable_legacy_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Принудительное включение legacy режима"""
        
        user_id = str(update.effective_user.id)
        
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
            
        self.user_settings[user_id]['interface_mode'] = 'legacy'
        
        await update.message.reply_text(
            "📱 *Классический интерфейс активирован*\n\n"
            "Все привычные функции доступны.\n"
            "Используйте /menu для основного меню",
            parse_mode='Markdown'
        )
        
        await self.legacy_bot._menu(update, context)
    
    # Legacy команды для обратной совместимости
    async def _legacy_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.legacy_bot._balance(update, context)
    
    async def _legacy_position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.legacy_bot._position(update, context)
        
    async def _legacy_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.legacy_bot._strategies(update, context)
        
    async def _legacy_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.legacy_bot._trades(update, context)
        
    async def _legacy_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.legacy_bot._logs(update, context)
    
    async def _unified_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Унифицированная справка"""
        
        help_text = (
            "🤖 *Справка по торговому боту*\n\n"
            
            "🎨 *Интерфейсы:*\n"
            "/ux - Переключиться на Modern UX\n"
            "/classic - Переключиться на Classic\n"
            "/dashboard - Smart Dashboard\n"
            "/quick - Быстрые действия\n\n"
            
            "📊 *Основные команды:*\n"
            "/balance - Баланс аккаунта\n"
            "/position - Текущие позиции\n"
            "/strategies - Управление стратегиями\n"
            "/trades - История сделок\n"
            "/logs - Логи системы\n\n"
            
            "⚙️ *Дополнительно:*\n"
            "/menu - Главное меню\n"
            "/help - Эта справка\n\n"
            
            "💜 *Рекомендуем попробовать Modern UX с командой /ux*"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def _unified_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Унифицированное меню"""
        await self._unified_dashboard(update, context)
    
    def get_usage_stats(self) -> Dict:
        """Получить статистику использования"""
        return {
            **self.usage_stats,
            'ux_adoption_rate': (
                self.usage_stats['ux_users'] / max(self.usage_stats['total_users'], 1) * 100
            ),
            'total_user_settings': len(self.user_settings),
            'ab_test_groups': len(self.ab_test_groups)
        }
    
    def send_admin_message(self, message: str):
        """Отправка сообщения админу через notification manager"""
        import asyncio
        
        async def send():
            await self.notification_manager.send_smart_notification(
                notification_type='system_alert',
                title='System Message',
                message=message,
                data={'type': 'admin_message'},
                priority=2,
                ttl_minutes=120
            )
        
        # Запускаем в фоне
        asyncio.create_task(send())
    
    def start(self):
        """Запуск enhanced бота"""
        
        self.logger.info("🚀 Starting Enhanced Telegram Bot...")
        
        try:
            # Запускаем с polling
            self.app.run_polling(drop_pending_updates=True)
            
        except KeyboardInterrupt:
            self.logger.info("💜 Enhanced Bot stopped by user")
        except Exception as e:
            self.logger.error(f"❌ Critical error in Enhanced Bot: {e}")
            raise

# Основная функция запуска
def main():
    """Главная функция для запуска enhanced бота"""
    
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не настроен!")
        return
    
    bot = EnhancedTelegramBot(TELEGRAM_TOKEN)
    
    print("🚀 Enhanced Telegram Bot готов к запуску!")
    print("💜 Особенности:")
    print("   • Два интерфейса: Modern UX + Classic")
    print("   • Smart notifications")
    print("   • A/B тестирование") 
    print("   • Полная обратная совместимость")
    print("   • Персонализация UX")
    print()
    
    bot.start()

if __name__ == "__main__":
    main()