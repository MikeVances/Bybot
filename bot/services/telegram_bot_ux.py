# bot/services/telegram_bot_ux.py
# 💜 РЕВОЛЮЦИОННЫЙ UX ДЛЯ TELEGRAM БОТА
# Создано сеньором-разработчиком с фиолетовыми волосами
# Фокус: user-centric design + современные Telegram фичи

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from datetime import datetime
import asyncio
from typing import Dict, List, Optional
import json

# Импорты проекта
from bot.exchange.api_adapter import create_trading_bot_adapter
from config import TELEGRAM_TOKEN, get_strategy_config, USE_V5_API, USE_TESTNET

try:
    from config import ADMIN_CHAT_ID
except ImportError:
    ADMIN_CHAT_ID = None

class TelegramBotUX:
    """
    🚀 Революционный UX-дизайн для Telegram бота
    
    Принципы:
    - User-first design
    - Минимум кликов до результата
    - Визуальная иерархия информации
    - Современные Telegram фичи
    - Адаптивные интерфейсы
    """
    
    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).build()
        
        # UX-состояние пользователей
        self.user_states = {}  # {user_id: state_data}
        
        # Регистрируем обработчики
        self._register_handlers()
        
        # Настройка логирования (без утечки токена)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)
        
        print("🚀 UX Bot инициализирован")
    
    def _register_handlers(self):
        """Регистрация всех обработчиков"""
        # Основные команды
        self.app.add_handler(CommandHandler("start", self._start))
        self.app.add_handler(CommandHandler("dashboard", self._dashboard))
        self.app.add_handler(CommandHandler("quick", self._quick_actions))
        
        # Callback query handlers
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))
    
    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """💜 Стильный и современный стартовый экран"""
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "Трейдер"
        
        # Персонализированное приветствие
        welcome_text = (
            f"🚀 *Привет, {first_name}!*\n\n"
            f"💜 *Добро пожаловать в будущее трейдинга*\n\n"
            f"Я твой персональный AI-помощник для торговли. "
            f"Готов показать тебе всю мощь автоматизации!\n\n"
            f"🎯 *Что умею:*\n"
            f"• 🧠 AI-анализ рынков в реальном времени\n"
            f"• ⚡ Мгновенные уведомления о сигналах\n"
            f"• 📊 Красивая аналитика твоих результатов\n"
            f"• 🛡️ Продвинутый риск-менеджмент\n"
            f"• 💰 Отслеживание прибыли 24/7"
        )
        
        # Создаем стильную клавиатуру с эмодзи и логикой
        keyboard = [
            [
                InlineKeyboardButton("🚀 DASHBOARD", callback_data="dashboard_main"),
                InlineKeyboardButton("⚡ QUICK ACTIONS", callback_data="quick_actions")
            ],
            [
                InlineKeyboardButton("🧠 AI STATUS", callback_data="ai_status"),
                InlineKeyboardButton("💰 P&L LIVE", callback_data="pnl_live")
            ],
            [
                InlineKeyboardButton("📊 ANALYTICS", callback_data="analytics_main"),
                InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings_main")
            ],
            [
                InlineKeyboardButton("🆘 HELP", callback_data="help_main")
            ]
        ]
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Сохраняем пользователя в наше UX-состояние
        self.user_states[user_id] = {
            'last_active': datetime.now(),
            'current_screen': 'start',
            'preferences': {}
        }
    
    async def _dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """📊 Умный dashboard с live-данными"""
        await self._show_smart_dashboard(update, context)
    
    async def _quick_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """⚡ Быстрые действия для опытных пользователей"""
        keyboard = [
            [
                InlineKeyboardButton("🚫 STOP ALL", callback_data="emergency_stop"),
                InlineKeyboardButton("▶️ START ALL", callback_data="emergency_start")
            ],
            [
                InlineKeyboardButton("💰 BALANCE", callback_data="quick_balance"),
                InlineKeyboardButton("📈 POSITIONS", callback_data="quick_positions")
            ],
            [
                InlineKeyboardButton("🧠 AI RECOMMEND", callback_data="ai_recommend"),
                InlineKeyboardButton("📱 MOBILE VIEW", web_app=WebAppInfo("https://your-webapp.com/mobile"))
            ]
        ]
        
        quick_text = (
            "⚡ *QUICK ACTIONS*\n\n"
            "Быстрый доступ к основным функциям для опытных пользователей"
        )
        
        await update.message.reply_text(
            quick_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _show_smart_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """📊 Умный dashboard с приоритизацией информации"""
        
        try:
            # Получаем критически важные данные
            critical_data = await self._get_critical_data()
            
            # Формируем dashboard с визуальной иерархией
            dashboard_text = self._format_smart_dashboard(critical_data)
            
            # Адаптивная клавиатура на основе данных
            keyboard = self._create_adaptive_keyboard(critical_data)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    dashboard_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    dashboard_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                
        except Exception as e:
            error_text = f"🚨 *Dashboard Error*\n\nНе удалось загрузить данные: `{str(e)[:100]}...`"
            
            keyboard = [
                [InlineKeyboardButton("🔄 RETRY", callback_data="dashboard_main")],
                [InlineKeyboardButton("🆘 SUPPORT", callback_data="support")]
            ]
            
            await update.callback_query.edit_message_text(
                error_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _get_critical_data(self) -> Dict:
        """Получаем только критически важные данные для dashboard"""
        try:
            # Здесь будет интеграция с вашими сервисами
            from bot.exchange.bybit_api_v5 import BybitAPI
            
            api = BybitAPI()
            
            # Параллельный сбор данных для ускорения
            tasks = [
                self._get_balance_summary(api),
                self._get_positions_summary(api),
                self._get_ai_status(),
                self._get_alerts_count()
            ]
            
            balance, positions, ai_status, alerts = await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                'balance': balance if not isinstance(balance, Exception) else None,
                'positions': positions if not isinstance(positions, Exception) else None,
                'ai_status': ai_status if not isinstance(ai_status, Exception) else None,
                'alerts': alerts if not isinstance(alerts, Exception) else 0,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            print(f"Error getting critical data: {e}")
            return {'error': str(e), 'timestamp': datetime.now()}
    
    async def _get_balance_summary(self, api) -> Dict:
        """Краткая сводка по балансу"""
        try:
            data = api.get_wallet_balance_v5()
            if data and data.get('retCode') == 0:
                result = data['result']['list'][0]
                return {
                    'total': float(result['totalEquity']),
                    'available': float(result['totalAvailableBalance']),
                    'pnl_24h': 0.0  # Будет вычислено позже
                }
            return None
        except Exception as e:
            print(f"Balance error: {e}")
            return None
    
    async def _get_positions_summary(self, api) -> Dict:
        """Краткая сводка по позициям"""
        try:
            data = api.get_positions("BTCUSDT")
            if data and data.get('retCode') == 0:
                positions = data['result']['list']
                open_positions = [pos for pos in positions if float(pos.get('size', 0)) > 0]
                
                total_pnl = sum(float(pos.get('unrealisedPnl', 0)) for pos in open_positions)
                
                return {
                    'count': len(open_positions),
                    'total_pnl': total_pnl,
                    'positions': open_positions[:3]  # Только топ-3 для dashboard
                }
            return {'count': 0, 'total_pnl': 0.0, 'positions': []}
        except Exception as e:
            print(f"Positions error: {e}")
            return {'count': 0, 'total_pnl': 0.0, 'positions': []}
    
    async def _get_ai_status(self) -> Dict:
        """Статус AI-системы"""
        try:
            from bot.ai import NeuralIntegration
            neural = NeuralIntegration()
            stats = neural.get_neural_statistics()
            
            return {
                'active': True,
                'win_rate': stats['neural_trader']['win_rate'],
                'confidence': 85.5,  # Средняя уверенность модели
                'last_recommendation': 'BUY Signal on Strategy_02'
            }
        except Exception as e:
            return {
                'active': False,
                'error': str(e)
            }
    
    async def _get_alerts_count(self) -> int:
        """Количество непрочитанных алертов"""
        # Здесь будет логика подсчёта алертов
        return 3
    
    def _format_smart_dashboard(self, data: Dict) -> str:
        """Форматирование dashboard с приоритизацией информации"""
        
        if 'error' in data:
            return f"🚨 *DASHBOARD ERROR*\n\n`{data['error']}`"
        
        # Заголовок с временем обновления
        time_str = data['timestamp'].strftime("%H:%M:%S")
        dashboard_text = f"📊 *SMART DASHBOARD*\n🕐 *Updated: {time_str}*\n\n"
        
        # 1. КРИТИЧЕСКАЯ ИНФОРМАЦИЯ (статусы, алерты)
        if data.get('alerts', 0) > 0:
            dashboard_text += f"🚨 *{data['alerts']} NEW ALERTS*\n\n"
        
        # 2. ФИНАНСОВЫЕ ПОКАЗАТЕЛИ (приоритет #1)
        balance = data.get('balance')
        if balance:
            dashboard_text += f"💰 *BALANCE: ${balance['total']:,.2f}*\n"
            dashboard_text += f"📈 *Available: ${balance['available']:,.2f}*\n"
            
            # Цветовая индикация P&L
            pnl = balance.get('pnl_24h', 0)
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            dashboard_text += f"{pnl_emoji} *24h P&L: ${pnl:+.2f}*\n\n"
        
        # 3. ПОЗИЦИИ (приоритет #2)
        positions = data.get('positions', {})
        if positions['count'] > 0:
            pnl_emoji = "🟢" if positions['total_pnl'] >= 0 else "🔴"
            dashboard_text += f"📊 *{positions['count']} OPEN POSITIONS*\n"
            dashboard_text += f"{pnl_emoji} *Total P&L: ${positions['total_pnl']:+.2f}*\n\n"
            
            # Показываем топ-3 позиции
            for i, pos in enumerate(positions['positions'][:2], 1):
                side = pos.get('side', 'Unknown')
                size = float(pos.get('size', 0))
                pnl = float(pos.get('unrealisedPnl', 0))
                pnl_sign = "+" if pnl >= 0 else ""
                dashboard_text += f"  {i}. {side} {size:.4f} BTC ({pnl_sign}${pnl:.2f})\n"
        else:
            dashboard_text += "📭 *No Open Positions*\n\n"
        
        # 4. AI STATUS (приоритет #3)
        ai_status = data.get('ai_status', {})
        if ai_status.get('active'):
            win_rate = ai_status.get('win_rate', 0)
            confidence = ai_status.get('confidence', 0)
            
            status_emoji = "🟢" if win_rate > 60 else "🟡" if win_rate > 40 else "🔴"
            dashboard_text += f"🧠 *AI STATUS:* {status_emoji}\n"
            dashboard_text += f"🎯 *Win Rate: {win_rate:.1f}%*\n"
            dashboard_text += f"💡 *Confidence: {confidence:.1f}%*\n"
        else:
            dashboard_text += f"🧠 *AI STATUS:* 🔴 OFFLINE\n"
        
        return dashboard_text
    
    def _create_adaptive_keyboard(self, data: Dict) -> List[List[InlineKeyboardButton]]:
        """Создаём адаптивную клавиатуру на основе данных"""
        
        keyboard = []
        
        # Ряд 1: Критические действия (если есть алерты или проблемы)
        if data.get('alerts', 0) > 0:
            keyboard.append([
                InlineKeyboardButton(f"🚨 VIEW {data['alerts']} ALERTS", callback_data="view_alerts")
            ])
        
        # Ряд 2: Основные действия
        row2 = []
        if data.get('positions', {})['count'] > 0:
            row2.append(InlineKeyboardButton("📊 POSITIONS", callback_data="positions_detail"))
        else:
            row2.append(InlineKeyboardButton("🚀 START TRADING", callback_data="start_trading"))
            
        row2.append(InlineKeyboardButton("💰 BALANCE", callback_data="balance_detail"))
        keyboard.append(row2)
        
        # Ряд 3: AI и аналитика
        keyboard.append([
            InlineKeyboardButton("🧠 AI INSIGHTS", callback_data="ai_insights"),
            InlineKeyboardButton("📈 ANALYTICS", callback_data="analytics_main")
        ])
        
        # Ряд 4: Навигация и настройки
        keyboard.append([
            InlineKeyboardButton("🔄 REFRESH", callback_data="dashboard_main"),
            InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings_main")
        ])
        
        return keyboard
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Роутер для всех callback queries"""
        query = update.callback_query
        await query.answer()  # Убираем "loading" индикатор
        
        callback_data = query.data
        
        # Роутинг по типу callback
        if callback_data == "dashboard_main":
            await self._show_smart_dashboard(update, context)
        elif callback_data == "quick_actions":
            await self._show_quick_actions(update, context)
        elif callback_data == "ai_status":
            await self._show_ai_status(update, context)
        elif callback_data == "pnl_live":
            await self._show_pnl_live(update, context)
        elif callback_data == "analytics_main":
            await self._show_analytics(update, context)
        elif callback_data == "positions_detail":
            await self._show_positions_detail(update, context)
        elif callback_data == "balance_detail":
            await self._show_balance_detail(update, context)
        elif callback_data == "emergency_stop":
            await self._emergency_stop(update, context)
        elif callback_data == "emergency_start":
            await self._emergency_start(update, context)
        elif callback_data == "ai_insights":
            await self._show_ai_insights(update, context)
        else:
            await query.edit_message_text(
                f"🚧 *Feature In Development*\n\n`{callback_data}` coming soon!",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _show_quick_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """⚡ Показать меню быстрых действий"""
        keyboard = [
            [
                InlineKeyboardButton("🚫 EMERGENCY STOP", callback_data="emergency_stop"),
                InlineKeyboardButton("▶️ START TRADING", callback_data="emergency_start")
            ],
            [
                InlineKeyboardButton("💰 QUICK BALANCE", callback_data="balance_detail"),
                InlineKeyboardButton("📈 QUICK POSITIONS", callback_data="positions_detail")
            ],
            [
                InlineKeyboardButton("🧠 AI RECOMMEND", callback_data="ai_insights"),
                InlineKeyboardButton("📊 LIVE STATS", callback_data="analytics_main")
            ],
            [
                InlineKeyboardButton("🔙 BACK", callback_data="dashboard_main")
            ]
        ]
        
        text = (
            "⚡ *QUICK ACTIONS*\n\n"
            "Мгновенный доступ к основным функциям:"
        )
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🚫 Emergency stop всех торговых операций"""
        # Здесь будет логика экстренной остановки
        
        keyboard = [
            [InlineKeyboardButton("✅ CONFIRM STOP", callback_data="confirm_stop")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="quick_actions")]
        ]
        
        text = (
            "🚨 *EMERGENCY STOP*\n\n"
            "⚠️ *ВНИМАНИЕ!* Это остановит:\n"
            "• Все активные стратегии\n"
            "• AI-анализ\n"
            "• Автоматическую торговлю\n\n"
            "❗ Открытые позиции останутся открытыми"
        )
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _show_ai_insights(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🧠 Показать AI-инсайты"""
        try:
            # Получаем данные от нейронной сети
            ai_data = await self._get_ai_insights()
            
            text = self._format_ai_insights(ai_data)
            
            keyboard = [
                [
                    InlineKeyboardButton("🎯 PREDICTIONS", callback_data="ai_predictions"),
                    InlineKeyboardButton("📊 MODEL STATS", callback_data="ai_model_stats")
                ],
                [
                    InlineKeyboardButton("🔄 REFRESH", callback_data="ai_insights"),
                    InlineKeyboardButton("🔙 BACK", callback_data="dashboard_main")
                ]
            ]
            
            await update.callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            error_text = f"🚨 *AI Insights Error*\n\n`{str(e)[:150]}...`"
            
            keyboard = [[InlineKeyboardButton("🔙 BACK", callback_data="dashboard_main")]]
            
            await update.callback_query.edit_message_text(
                error_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _get_ai_insights(self) -> Dict:
        """Получаем инсайты от AI"""
        try:
            from bot.ai import NeuralIntegration
            
            neural = NeuralIntegration()
            stats = neural.get_neural_statistics()
            ranking = neural.get_strategy_ranking()
            
            return {
                'neural_stats': stats['neural_trader'],
                'strategy_ranking': ranking[:5],  # Топ-5 стратегий
                'recent_performance': stats.get('recent_performance', {}),
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            print(f"AI Insights error: {e}")
            raise e
    
    def _format_ai_insights(self, data: Dict) -> str:
        """Форматирование AI-инсайтов"""
        time_str = data['timestamp'].strftime("%H:%M:%S")
        
        text = f"🧠 *AI INSIGHTS*\n🕐 *Updated: {time_str}*\n\n"
        
        # Статистика нейронной сети
        neural_stats = data['neural_stats']
        text += f"🎯 *Neural Network Performance:*\n"
        text += f"💰 Balance: ${neural_stats['current_balance']:.2f}\n"
        text += f"📈 ROI: {neural_stats['roi']:+.1f}%\n"
        text += f"🏆 Win Rate: {neural_stats['win_rate']:.1f}%\n"
        text += f"📊 Total Bets: {neural_stats['total_bets']}\n\n"
        
        # Топ стратегий
        ranking = data['strategy_ranking']
        if ranking:
            text += f"🏆 *Top Performing Strategies:*\n"
            for i, strategy in enumerate(ranking[:3], 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                text += f"{emoji} {strategy['strategy']}\n"
                text += f"   📊 {strategy['success_rate']*100:.1f}% success\n"
                text += f"   💰 {strategy['total_signals']} signals\n"
        
        # Последняя активность
        recent = data.get('recent_performance', {})
        if recent:
            text += f"\n⚡ *Recent Activity:*\n"
            text += f"📈 Win Rate: {recent.get('win_rate', 0)*100:.1f}%\n"
            text += f"💰 Avg Profit: ${recent.get('avg_profit', 0):.2f}\n"
        
        return text
    
    def start(self):
        """Запуск UX-бота"""
        print("🚀 Запуск UX Telegram бота...")
        try:
            self.app.run_polling(drop_pending_updates=True)
        except KeyboardInterrupt:
            print("💜 UX Bot остановлен пользователем")
        except Exception as e:
            print(f"❌ Критическая ошибка UX бота: {e}")

if __name__ == "__main__":
    bot = TelegramBotUX(TELEGRAM_TOKEN)
    bot.start()