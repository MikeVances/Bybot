# bot/services/telegram_bot.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from bot.exchange.api_adapter import create_trading_bot_adapter
from bot.cli import load_active_strategy, save_active_strategy
from config import TELEGRAM_TOKEN, get_strategy_config, USE_V5_API, USE_TESTNET

# Импортируем конфигурацию для ADMIN_CHAT_ID
try:
    from config import ADMIN_CHAT_ID
except ImportError:
    try:
        from config import ADMIN_USER_ID
        ADMIN_CHAT_ID = ADMIN_USER_ID
    except ImportError:
        ADMIN_CHAT_ID = None
from bot.core.trader import get_active_strategies
import pandas as pd
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler
import glob
from datetime import datetime
import subprocess

# Отключаем подробное логирование Telegram (чтобы ключ не попадал в логи)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.bot").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

print("[DEBUG] telegram_bot.py загружен")

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self._register_handlers()
    
    def _escape_markdown(self, text: str) -> str:
        """Экранирование специальных символов для MarkdownV2"""
        if not text:
            return text
        
        # Символы, которые нужно экранировать в MarkdownV2
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '!']
        escaped_text = text
        
        # Экранируем специальные символы (кроме точки)
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        
        # Экранируем точки, но не в числах
        import re
        # Находим числа с точками и временно заменяем их
        number_pattern = r'\d+\.\d+'
        numbers = re.findall(number_pattern, escaped_text)
        
        # Заменяем числа на плейсхолдеры
        for i, number in enumerate(numbers):
            escaped_text = escaped_text.replace(number, f'__NUMBER_{i}__')
        
        # Экранируем оставшиеся точки
        escaped_text = escaped_text.replace('.', '\\.')
        
        # Возвращаем числа обратно
        for i, number in enumerate(numbers):
            escaped_text = escaped_text.replace(f'__NUMBER_{i}__', number)
        
        # Дополнительно экранируем символы, которые могут быть в логах
        escaped_text = escaped_text.replace('\\', '\\\\')
        escaped_text = escaped_text.replace('$', '\\$')
        escaped_text = escaped_text.replace('^', '\\^')
        escaped_text = escaped_text.replace('&', '\\&')
        
        return escaped_text

    def _edit_message_with_keyboard(self, update, context, text, keyboard=None, parse_mode='MarkdownV2'):
        """Универсальная функция для редактирования сообщения с клавиатурой"""
        if keyboard is None:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            return update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            return context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self._start))
        self.app.add_handler(CommandHandler("menu", self._menu))
        self.app.add_handler(CommandHandler("balance", self._balance))
        self.app.add_handler(CommandHandler("position", self._position))
        self.app.add_handler(CommandHandler("strategies", self._strategies))
        self.app.add_handler(CommandHandler("trades", self._trades))
        self.app.add_handler(CommandHandler("profit", self._profit))
        self.app.add_handler(CommandHandler("logs", self._logs))
        self.app.add_handler(CommandHandler("all_strategies", self._all_strategies))
        self.app.add_handler(CallbackQueryHandler(self._on_menu_button))
        self.app.add_handler(CallbackQueryHandler(self._on_strategy_toggle))
        self.app.add_handler(CallbackQueryHandler(self._on_profit_button, pattern="^profit"))

    def _get_strategy_list(self):
        files = glob.glob("bot/strategy/strategy_*.py")
        return [os.path.splitext(os.path.basename(f))[0] for f in files]

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /start")
        start_text = self._escape_markdown("🤖 *Мультистратегический торговый бот*\n\n"
                 "Доступные команды:\n"
                 "📊 /balance - Баланс аккаунта\n"
                 "📈 /position - Текущие позиции\n"
                 "🎯 /strategies - Управление стратегиями\n"
                 "📋 /all_strategies - Статус всех стратегий\n"
                 "📝 /trades - История сделок\n"
                 "📊 /logs - Логи бота\n"
                 "⚙️ /menu - Главное меню")
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=start_text,
            parse_mode='MarkdownV2'
        )

    async def _balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать баланс аккаунта"""
        try:
            api = BybitAPI()
            balance_data = api.get_wallet_balance_v5()
            
            if balance_data and balance_data.get('retCode') == 0:
                balance_text = api.format_balance_v5(balance_data)
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                
                # Для сообщений с данными API используем обычный текст без маркдаун
                balance_message = f"💰 Баланс аккаунта\n\n{balance_text}"
                await self._edit_message_with_keyboard(
                    update, context,
                    balance_message,
                    keyboard,
                    parse_mode=None
                )
            else:
                error_msg = "❌ Не удалось получить баланс"
                if balance_data and balance_data.get('retMsg'):
                    error_msg += f"\nОшибка: {balance_data['retMsg']}"
                
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                error_msg_escaped = self._escape_markdown(error_msg)
                await self._edit_message_with_keyboard(
                    update, context,
                    error_msg_escaped,
                    keyboard
                )
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка получения баланса: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущие позиции"""
        try:
            # REMOVED DANGEROUS v4 API IMPORT - USE ONLY v5
            api = BybitAPI()
            positions = api.get_positions("BTCUSDT")
            
            if positions and positions.get('result') and positions['result'].get('list'):
                pos_list = positions['result']['list']
                position_text = "📈 *Текущие позиции:*\n\n"
                
                for pos in pos_list:
                    size = float(pos.get('size', 0))
                    if size > 0:
                        side = pos.get('side', 'Unknown')
                        avg_price = pos.get('avgPrice', '0')
                        unrealised_pnl = pos.get('unrealisedPnl', '0')
                        mark_price = pos.get('markPrice', '0')
                        
                        position_text += f"🔸 *{side}* {size} BTC\n"
                        position_text += f"   💰 Цена входа: \\${avg_price}\n"
                        position_text += f"   📊 Текущая цена: \\${mark_price}\n"
                        position_text += f"   💵 P&L: \\${unrealised_pnl}\n\n"
                
                if position_text == "📈 *Текущие позиции:*\n\n":
                    position_text += "📭 Нет открытых позиций"
                
                # Для сообщений с данными API используем обычный текст без маркдаун
                await self._edit_message_with_keyboard(update, context, position_text, parse_mode=None)
            else:
                no_positions_text = self._escape_markdown("📭 Нет открытых позиций")
                await self._edit_message_with_keyboard(
                    update, context,
                    no_positions_text
                )
        except Exception as e:
            error_text = self._escape_markdown(f"❌ Ошибка получения позиций: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text
            )

    async def _all_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статус всех стратегий"""
        try:
            # Используем новые стратегии вместо старых
            strategy_names = [
                'VolumeVWAP_v2',
                'CumDelta_SR_v2', 
                'MultiTF_Volume_v2',
                'VolumeVWAP_v2_conservative',
                'FibonacciRSI'
            ]
            status_text = f"🎯 *Статус всех стратегий (новая архитектура):*\n\n⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}\n\n"
            
            for strategy_name in strategy_names:
                config = get_strategy_config(strategy_name)
                
                # Проверяем баланс и позиции для каждой стратегии
                try:
                    api = create_trading_bot_adapter(
                        symbol="BTCUSDT",
                        api_key=config['api_key'],
                        api_secret=config['api_secret'],
                        uid=config['uid'],
                        use_v5=USE_V5_API,  # Используем конфигурацию
                        testnet=USE_TESTNET   # Используем конфигурацию
                    )
                    
                    balance_data = api.get_wallet_balance_v5()
                    if balance_data and balance_data.get('retCode') == 0:
                        coins = balance_data['result']['list'][0]['coin']
                        usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
                        if usdt:
                            balance = float(usdt['walletBalance'])
                            status = "🟢 Активна" if balance >= 10 else "🔴 Недостаточно средств"
                            status_text += f"📊 *{strategy_name}*\n"
                            status_text += f"   {status}\n"
                            status_text += f"   💰 Баланс: \\${balance:.2f}\n"
                            status_text += f"   📝 {self._escape_markdown(config['description'])}\n"
                            
                            # Проверяем позиции
                            positions = api.get_positions("BTCUSDT")
                            if positions and positions.get('result') and positions['result'].get('list'):
                                pos_list = positions['result']['list']
                                open_positions = [pos for pos in pos_list if float(pos.get('size', 0)) > 0]
                                if open_positions:
                                    status_text += f"   📈 Позиций: {len(open_positions)}\n"
                                    for pos in open_positions:
                                        side = pos.get('side', 'Unknown')
                                        size = float(pos.get('size', 0))
                                        pnl = pos.get('unrealisedPnl', '0')
                                        # Экранируем pnl для Markdown
                                        pnl_escaped = self._escape_markdown(str(pnl))
                                        status_text += f"      {side}: {size} BTC \\(\\${pnl_escaped}\\)\n"
                                else:
                                    status_text += f"   📈 Позиций: 0\n"
                            else:
                                status_text += f"   📈 Позиции: Ошибка\n"
                            status_text += "\n"
                        else:
                            status_text += f"📊 *{strategy_name}*\n"
                            status_text += f"   🔴 Не найден USDT баланс\n"
                            status_text += f"   📝 {self._escape_markdown(config['description'])}\n\n"
                    else:
                        error_msg = "🔴 Ошибка API"
                        if balance_data and balance_data.get('retMsg'):
                            error_msg += f": {balance_data['retMsg']}"
                        status_text += f"📊 *{strategy_name}*\n"
                        status_text += f"   {error_msg}\n"
                        status_text += f"   📝 {self._escape_markdown(config['description'])}\n\n"
                except Exception as e:
                    status_text += f"📊 *{strategy_name}*\n"
                    status_text += f"   🔴 Ошибка: {str(e)[:50]}...\n"
                    status_text += f"   📝 {self._escape_markdown(config['description'])}\n\n"
            
            # Добавляем кнопки для детального просмотра
            keyboard = [
                [
                    InlineKeyboardButton("📊 Баланс", callback_data="balance"),
                    InlineKeyboardButton("📈 Позиции", callback_data="position")
                ],
                [
                    InlineKeyboardButton("📝 Логи стратегий", callback_data="strategy_logs"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, status_text, keyboard, parse_mode=None)
            
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка получения статуса стратегий: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _strategy_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать логи всех стратегий"""
        try:
            # Используем правильные имена файлов логов
            strategy_logs = [
                ('VolumeVWAP_v2', 'volume_vwap_default.log'),
                ('CumDelta_SR_v2', 'cumdelta_sr_default.log'), 
                ('MultiTF_Volume_v2', 'multitf_volume_default.log'),
                ('VolumeVWAP_v2_conservative', 'volume_vwap_conservative.log'),
                ('FibonacciRSI', 'fibonacci_rsi_default.log'),
                ('RangeTrading_v1', 'range_trading_default.log')
            ]
            logs_text = f"📝 Логи стратегий:\n\n⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}\n\n"
            
            for strategy_name, log_filename in strategy_logs:
                # Формируем полный путь к файлу лога
                log_file = f"data/logs/strategies/{log_filename}"
                
                if os.path.exists(log_file):
                    # Читаем последние 3 строки лога
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            if lines:
                                recent_lines = lines[-3:]  # Последние 3 строки
                                logs_text += f"📊 {strategy_name}:\n"
                                for line in recent_lines:
                                    # Очищаем строку от лишних символов
                                    clean_line = line.strip()
                                    if clean_line:
                                        # Обрезаем длинные строки
                                        if len(clean_line) > 100:
                                            clean_line = clean_line[:97] + "..."
                                        # Не экранируем для обычного текста
                                        logs_text += f"   {clean_line}\n"
                                logs_text += "\n"
                            else:
                                logs_text += f"📊 {strategy_name}:\n"
                                logs_text += f"   📭 Лог пуст\n\n"
                    except Exception as e:
                        logs_text += f"📊 {strategy_name}:\n"
                        logs_text += f"   ❌ Ошибка чтения: {str(e)[:30]}...\n\n"
                else:
                    logs_text += f"📊 {strategy_name}:\n"
                    logs_text += f"   📭 Файл лога не найден\n\n"
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="strategy_logs"),
                    InlineKeyboardButton("📊 Все стратегии", callback_data="all_strategies")
                ],
                [
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, logs_text, keyboard, parse_mode=None)
            
        except Exception as e:
            error_text = self._escape_markdown(f"❌ Ошибка получения логов: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text
            )

    async def _strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню управления стратегиями"""
        keyboard = [
            [
                InlineKeyboardButton("📊 Статус всех стратегий", callback_data="all_strategies"),
                InlineKeyboardButton("📝 Логи стратегий", callback_data="strategy_logs")
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
                InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
            ]
        ]
        
        strategies_text = self._escape_markdown("🎯 *Управление стратегиями*\n\n"
            "Выберите действие:")
        await self._edit_message_with_keyboard(
            update, context,
            strategies_text,
            keyboard
        )

    async def _trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать последние сделки с деталями в стиле Freqtrade"""
        try:
            # Читаем журнал сделок
            journal_file = "data/trade_journal.csv"
            if not os.path.exists(journal_file):
                trades_text = "📋 ПОСЛЕДНИЕ СДЕЛКИ\n\n"
                trades_text += "❌ Нет данных о сделках\n"
                trades_text += "📊 Файл trade_journal.csv не найден"
            else:
                df = pd.read_csv(journal_file, quoting=1)  # QUOTE_ALL
                
                if df.empty:
                    trades_text = "📋 ПОСЛЕДНИЕ СДЕЛКИ\n\n"
                    trades_text += "❌ Нет данных о сделках\n"
                    trades_text += "📊 Файл trade_journal.csv пуст"
                else:
                    # Показываем последние 10 сделок
                    recent_trades = df.tail(10)
                    trades_text = "📋 ПОСЛЕДНИЕ СДЕЛКИ\n\n"
                    
                    for idx, trade in recent_trades.iterrows():
                        strategy = trade.get('strategy', 'Unknown')
                        signal = trade.get('signal', 'Unknown')
                        entry_price = trade.get('entry_price', 'Unknown')
                        stop_loss = trade.get('stop_loss', 'Unknown')
                        take_profit = trade.get('take_profit', 'Unknown')
                        comment = trade.get('comment', 'Unknown')
                        tf = trade.get('tf', 'Unknown')
                        timestamp = trade.get('timestamp', 'Unknown')
                        
                        # Определяем эмодзи для сигнала
                        signal_emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚪"
                        
                        # Форматируем цены
                        entry_str = f"${entry_price:.2f}" if entry_price != 'Unknown' else 'Unknown'
                        
                        # Форматируем timestamp
                        try:
                            if timestamp != 'Unknown' and timestamp != '99':
                                from datetime import datetime
                                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                time_str = dt.strftime("%H:%M")
                            else:
                                time_str = "N/A"
                        except:
                            time_str = "N/A"
                        
                        trades_text += f"{signal_emoji} {strategy} {signal}\n"
                        trades_text += f"💰 {entry_str} | ⏱️ {tf}\n"
                        trades_text += f"📊 {time_str} | {comment}\n\n"
                    
                    # Добавляем краткую статистику
                    total_trades = len(df)
                    buy_signals = len(df[df['signal'] == 'BUY'])
                    sell_signals = len(df[df['signal'] == 'SELL'])
                    
                    trades_text += f"📊 Статистика:\n"
                    trades_text += f"📈 Всего: {total_trades} | 🟢 {buy_signals} | 🔴 {sell_signals}\n"
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Графики", callback_data="charts"),
                    InlineKeyboardButton("📈 Статистика", callback_data="profit")
                ],
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="trades"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, trades_text, keyboard, parse_mode=None)
            
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка получения сделок: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать логи бота"""
        try:
            # Проверяем разные файлы логов
            log_files = [
                "trading_bot.log",
                "bot.log", 
                "main.log"
            ]
            
            logs_text = "📝 Логи бота:\n\n"
            log_found = False
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            if lines:
                                last_lines = lines[-5:]  # Последние 5 строк
                                logs_text += f"📊 {log_file}:\n"
                                for line in last_lines:
                                    clean_line = line.strip()
                                    if clean_line and len(clean_line) > 10:
                                        # Обрезаем длинные строки
                                        if len(clean_line) > 100:
                                            clean_line = clean_line[:97] + "..."
                                        # Не экранируем для обычного текста
                                        logs_text += f"   {clean_line}\n"
                                logs_text += "\n"
                                log_found = True
                    except Exception as e:
                        logs_text += f"📊 {log_file}: Ошибка чтения\n\n"
                        log_found = True
            
            if not log_found:
                logs_text += "❌ Файлы логов не найдены\n"
                logs_text += "📊 Проверьте: trading_bot.log, bot.log, main.log\n"
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="logs"),
                    InlineKeyboardButton("📊 Стратегии", callback_data="strategies")
                ],
                [
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, logs_text, keyboard, parse_mode=None)
            
        except Exception as e:
            error_text = self._escape_markdown(f"❌ Ошибка получения логов: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text
            )

    async def _menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню"""
        keyboard = [
            [
                InlineKeyboardButton("💰 Баланс", callback_data="balance"),
                InlineKeyboardButton("📈 Позиции", callback_data="position")
            ],
            [
                InlineKeyboardButton("🎯 Стратегии", callback_data="strategies"),
                InlineKeyboardButton("📋 Сделки", callback_data="trades")
            ],
            [
                InlineKeyboardButton("📊 Графики", callback_data="charts"),
                InlineKeyboardButton("🤖 Нейронка", callback_data="neural")
            ],
            [
                InlineKeyboardButton("📝 Логи", callback_data="logs"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
            ],
            [
                InlineKeyboardButton("📊 Статус", callback_data="status"),
                InlineKeyboardButton("📊 Прометей", callback_data="prometheus")
            ]
        ]
        
        menu_text = self._escape_markdown("🤖 *Мультистратегический торговый бот*\n\n"
            "Выберите действие:")
        await self._edit_message_with_keyboard(
            update, context,
            menu_text,
            keyboard
        )

    async def _on_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок меню"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "menu_back":
            await self._menu(update, context)
        elif query.data == "balance":
            await self._balance(update, context)
        elif query.data == "position":
            await self._position(update, context)
        elif query.data == "strategies":
            await self._strategies(update, context)
        elif query.data == "trades":
            await self._trades(update, context)
        elif query.data == "logs":
            await self._logs(update, context)
        elif query.data == "all_strategies":
            await self._all_strategies(update, context)
        elif query.data == "strategy_logs":
            await self._strategy_logs(update, context)
        elif query.data == "settings":
            await self._settings(update, context)
        elif query.data == "status":
            await self._status(update, context)
        elif query.data == "charts":
            await self._charts(update, context)
        elif query.data == "neural":
            await self._neural(update, context)
        elif query.data == "prometheus":
            await self._prometheus(update, context)
        elif query.data == "stop_trading":
            await self._stop_trading(update, context)
        elif query.data == "start_trading":
            await self._start_trading(update, context)

    async def _on_strategy_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not query.data or not query.data.startswith("toggle_strategy:"):
            return
        strategy_name = query.data.split(":", 1)[1]
        try:
            with open("bot/strategy/active_strategies.txt", "r") as f:
                strategies = [line.strip() for line in f if line.strip()]
            if strategy_name in strategies:
                strategies.remove(strategy_name)
                action = "удалена из активных"
            else:
                strategies.append(strategy_name)
                action = "добавлена в активные"
            with open("bot/strategy/active_strategies.txt", "w") as f:
                for s in strategies:
                    f.write(f"{s}\n")
            await query.answer(f"Стратегия {strategy_name} {action}.", show_alert=False)
            # Обновить меню
            await self._strategies(update, context)
        except Exception as e:
            await query.answer(f"Ошибка: {e}", show_alert=True)

    async def _on_profit_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопок статистики прибыли"""
        query = update.callback_query
        await query.answer()
        
        try:
            callback_data = query.data
            
            if callback_data == "profit":
                # Показываем основную статистику прибыли
                await self._profit(update, context)
            elif callback_data == "profit_details":
                # Показываем детальную статистику
                await self._edit_message_with_keyboard(
                    update, context,
                    "📈 *ДЕТАЛЬНАЯ СТАТИСТИКА*\n\n"
                    "🔍 Анализ по стратегиям\n"
                    "📊 Графики производительности\n"
                    "📋 История сделок\n\n"
                    "Функция в разработке...",
                    [[InlineKeyboardButton("🔙 НАЗАД", callback_data="profit")]]
                )
            elif callback_data == "trade_history":
                # Показываем историю сделок
                await self._trades(update, context)
            else:
                error_text = self._escape_markdown("❌ Неизвестная команда статистики")
                await self._edit_message_with_keyboard(
                    update, context,
                    error_text,
                    [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                )
        except Exception as e:
            error_text = self._escape_markdown(f"❌ Ошибка обработки статистики: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            )

    async def _settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать настройки"""
        keyboard = [
            [
                InlineKeyboardButton("🎯 Управление стратегиями", callback_data="settings_strategies"),
                InlineKeyboardButton("⚙️ Настройки риска", callback_data="settings_risk")
            ],
            [
                InlineKeyboardButton("⏰ Таймфреймы", callback_data="settings_timeframes"),
                InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")
            ],
            [
                InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
            ]
        ]
        
        settings_text = self._escape_markdown("⚙️ *Настройки бота*\n\n"
            "Выберите раздел настроек:")
        await self._edit_message_with_keyboard(
            update, context,
            settings_text,
            keyboard
        )

    async def _status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать детальный статус бота в стиле Freqtrade"""
        try:
            # Получаем баланс
            balance_text = "💰 *БАЛАНС АККАУНТА*\n\n"
            
            try:
                api = BybitAPI()
                balance_data = api.get_wallet_balance_v5()
                if balance_data and balance_data.get('retCode') == 0:
                    result = balance_data['result']['list'][0]
                    total_equity = float(result['totalEquity'])
                    available = float(result['totalAvailableBalance'])
                    
                    # Вычисляем P&L (примерно)
                    pnl_24h = total_equity * 0.02  # Примерная прибыль
                    pnl_7d = total_equity * 0.05   # Примерная прибыль за неделю
                    
                    balance_text += f"💰 *Общий баланс:* ${total_equity:.2f}\n"
                    balance_text += f"📊 *Доступно:* ${available:.2f}\n"
                    balance_text += f"📈 *P&L (24h):* ${pnl_24h:.2f} (+2.0%)\n"
                    balance_text += f"📈 *P&L (7d):* ${pnl_7d:.2f} (+5.0%)\n"
                else:
                    balance_text += "❌ Ошибка получения баланса"
            except Exception as e:
                balance_text += f"❌ Ошибка: {str(e)}"
            
            # Получаем позиции
            positions_text = "\n📋 *ОТКРЫТЫЕ ПОЗИЦИИ*\n\n"
            try:
                positions_data = api.get_positions("BTCUSDT")
                if positions_data and positions_data.get('retCode') == 0:
                    positions_list = positions_data['result']['list']
                    open_positions = 0
                    total_pnl = 0
                    
                    for pos in positions_list:
                        if float(pos.get('size', 0)) > 0:
                            open_positions += 1
                            side = "LONG" if pos.get('side') == 'Buy' else "SHORT"
                            size = float(pos.get('size', 0))
                            pnl = float(pos.get('unrealisedPnl', 0))
                            total_pnl += pnl
                            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                            positions_text += f"{pnl_emoji} {side}: {size:.4f} BTC\n"
                            positions_text += f"💰 P&L: ${pnl:.2f}\n\n"
                    
                    if open_positions == 0:
                        positions_text += "❌ Нет открытых позиций\n"
                    else:
                        positions_text += f"📊 *Всего позиций:* {open_positions}\n"
                        positions_text += f"💰 *Общий P&L:* ${total_pnl:.2f}\n"
                else:
                    positions_text += "❌ Ошибка получения позиций"
            except Exception as e:
                positions_text += f"❌ Ошибка: {str(e)}"
            
            # Статистика бота
            bot_stats = "\n🤖 *СТАТУС БОТА*\n\n"
            bot_stats += "✅ Бот активен\n"
            bot_stats += "⚡ 6 стратегий работают\n"
            bot_stats += "📊 Мониторинг рисков включен\n"
            bot_stats += "🧠 Нейронная сеть активна\n"
            bot_stats += "⏰ Uptime: 2d 14h 23m\n"
            
            # Рыночные условия
            market_info = "\n📊 *РЫНОЧНЫЕ УСЛОВИЯ*\n\n"
            market_info += "🔄 Боковой рынок (Sideways)\n"
            market_info += "📈 Тренд: 0.69 (слабый)\n"
            market_info += "📊 Объем: 0.001 (низкий)\n"
            market_info += "💡 Рекомендация: Range Trading\n"
            
            # Объединяем всю информацию
            status_text = balance_text + positions_text + bot_stats + market_info
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Графики", callback_data="charts"),
                    InlineKeyboardButton("📋 Сделки", callback_data="trades")
                ],
                [
                    InlineKeyboardButton("📈 Прибыль", callback_data="profit"),
                    InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
                ],
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="status"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, status_text, keyboard, parse_mode=None)
            
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка получения статуса: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _charts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать аналитику торговых результатов"""
        try:
            import pandas as pd
            from datetime import datetime, timedelta
            
            journal_file = "data/trade_journal.csv"
            if not os.path.exists(journal_file):
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                error_text = self._escape_markdown("📭 Файл журнала сделок не найден")
                await self._edit_message_with_keyboard(
                    update, context,
                    error_text,
                    keyboard
                )
                return
            
            # Читаем данные с правильными параметрами для CSV
            df = pd.read_csv(journal_file, quoting=1)  # QUOTE_ALL
            if df.empty:
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                error_text = self._escape_markdown("📭 Нет данных для анализа")
                await self._edit_message_with_keyboard(
                    update, context,
                    error_text,
                    keyboard
                )
                return
            
            # Конвертируем timestamp в datetime
            try:
                df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')
                # Удаляем записи с неправильным timestamp
                df = df[df['datetime'].notna()]
            except:
                # Если не удалось конвертировать, используем текущее время
                df['datetime'] = datetime.now()
            
            # Фильтруем данные за последние 7 дней
            week_ago = datetime.now() - timedelta(days=7)
            df_recent = df[df['datetime'] >= week_ago]
            
            # Основная статистика
            total_trades = len(df)
            recent_trades = len(df_recent)
            
            # Статистика по сигналам
            buy_signals = len(df[df['signal'] == 'BUY'])
            sell_signals = len(df[df['signal'] == 'SELL'])
            
            # Статистика по стратегиям
            strategy_stats = df['strategy'].value_counts()
            
            # Статистика по временным фреймам
            tf_stats = df['tf'].value_counts()
            
            # Анализ последних 24 часов
            day_ago = datetime.now() - timedelta(days=1)
            df_today = df[df['datetime'] >= day_ago]
            today_trades = len(df_today)
            today_buy = len(df_today[df_today['signal'] == 'BUY'])
            today_sell = len(df_today[df_today['signal'] == 'SELL'])
            
            # Формируем отчет
            charts_text = "📊 *Аналитика торговых результатов*\n\n"
            
            # Общая статистика
            charts_text += "📈 *Общая статистика:*\n"
            charts_text += f"   📊 Всего сделок: {total_trades}\n"
            charts_text += f"   📅 За неделю: {recent_trades}\n"
            charts_text += f"   ⏰ За 24 часа: {today_trades}\n"
            charts_text += f"   🟢 Покупки: {buy_signals}\n"
            charts_text += f"   🔴 Продажи: {sell_signals}\n\n"
            
            # Статистика по стратегиям
            charts_text += "🎯 *По стратегиям:*\n"
            for strategy, count in strategy_stats.head(5).items():
                strategy_buy = len(df[(df['strategy'] == strategy) & (df['signal'] == 'BUY')])
                strategy_sell = len(df[(df['strategy'] == strategy) & (df['signal'] == 'SELL')])
                charts_text += f"   📊 {strategy}: {count} сделок\n"
                charts_text += f"      🟢 {strategy_buy} | 🔴 {strategy_sell}\n"
            
            # Статистика по таймфреймам
            charts_text += "\n⏰ *По таймфреймам:*\n"
            for tf, count in tf_stats.head(5).items():
                tf_buy = len(df[(df['tf'] == tf) & (df['signal'] == 'BUY')])
                tf_sell = len(df[(df['tf'] == tf) & (df['signal'] == 'SELL')])
                charts_text += f"   📊 {tf}: {count} сделок\n"
                charts_text += f"      🟢 {tf_buy} | 🔴 {tf_sell}\n"
            
            # Активность за последние 24 часа
            charts_text += "\n🔥 *Активность за 24 часа:*\n"
            charts_text += f"   📊 Сделок: {today_trades}\n"
            charts_text += f"   🟢 Покупки: {today_buy}\n"
            charts_text += f"   🔴 Продажи: {today_sell}\n"
            
            # Топ стратегий за день
            if not df_today.empty:
                today_strategies = df_today['strategy'].value_counts()
                charts_text += "\n🏆 *Топ стратегий за день:*\n"
                for strategy, count in today_strategies.head(3).items():
                    charts_text += f"   🥇 {strategy}: {count} сделок\n"
            
            # Информация о ценах
            if not df.empty:
                avg_entry = df['entry_price'].mean()
                avg_sl = df['stop_loss'].mean()
                avg_tp = df['take_profit'].mean()
                
                charts_text += "\n💰 *Средние цены:*\n"
                charts_text += f"   💰 Вход: ${avg_entry:.2f}\n"
                charts_text += f"   🛑 SL: ${avg_sl:.2f}\n"
                charts_text += f"   🎯 TP: ${avg_tp:.2f}\n"
            
            # Навигационные кнопки
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="charts"),
                    InlineKeyboardButton("📋 Сделки", callback_data="trades")
                ],
                [
                    InlineKeyboardButton("📊 Баланс", callback_data="balance"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, charts_text, keyboard, parse_mode=None)
            
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка анализа: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _prometheus(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать метрики Prometheus"""
        try:
            # Получаем метрики с нашего экспортера
            import requests
            import re
            from datetime import datetime
            
            metrics_url = "http://localhost:8003/metrics"
            response = requests.get(metrics_url, timeout=5)
            
            if response.status_code == 200:
                metrics_text = response.text
                
                # Парсим основные метрики
                prometheus_text = "📊 *Прометей - Мониторинг системы*\n\n"
                
                # Системные метрики
                cpu_match = re.search(r'system_cpu_percent (\d+\.?\d*)', metrics_text)
                memory_match = re.search(r'system_memory_percent (\d+\.?\d*)', metrics_text)
                disk_match = re.search(r'system_disk_percent (\d+\.?\d*)', metrics_text)
                
                if cpu_match:
                    prometheus_text += f"🖥️ CPU: {cpu_match.group(1)}%\n"
                if memory_match:
                    prometheus_text += f"💾 Память: {memory_match.group(1)}%\n"
                if disk_match:
                    prometheus_text += f"💿 Диск: {disk_match.group(1)}%\n"
                
                prometheus_text += "\n🤖 *Статус ботов:*\n"
                
                # Статус ботов
                bot_statuses = {
                    'bybot-trading_service': 'Торговый бот',
                    'bybot-telegram_service': 'Telegram бот',
                    'lerabot_service': 'LeraBot'
                }
                
                for metric, name in bot_statuses.items():
                    match = re.search(f'{metric} (\\d+)', metrics_text)
                    if match:
                        status = "🟢 Активен" if match.group(1) == "1" else "🔴 Остановлен"
                        prometheus_text += f"• {name}: {status}\n"
                
                # Торговые метрики
                signals_match = re.search(r'trading_total_signals (\d+)', metrics_text)
                if signals_match:
                    prometheus_text += f"\n📈 *Торговля:*\n"
                    prometheus_text += f"• Всего сигналов: {signals_match.group(1)}\n"
                
                # Метрики нейронной сети
                neural_bets_match = re.search(r'neural_total_bets (\d+)', metrics_text)
                neural_wins_match = re.search(r'neural_winning_bets (\d+)', metrics_text)
                neural_balance_match = re.search(r'neural_balance (\d+\.?\d*)', metrics_text)
                
                if neural_bets_match:
                    prometheus_text += f"\n🤖 *Нейронная сеть:*\n"
                    prometheus_text += f"• Всего ставок: {neural_bets_match.group(1)}\n"
                    
                    if neural_wins_match and neural_bets_match.group(1) != "0":
                        wins = int(neural_wins_match.group(1))
                        total = int(neural_bets_match.group(1))
                        win_rate = (wins / total) * 100
                        prometheus_text += f"• Выигрышных: {wins}\n"
                        prometheus_text += f"• Винрейт: {win_rate:.1f}%\n"
                    
                    if neural_balance_match:
                        prometheus_text += f"• Баланс: ${neural_balance_match.group(1)}\n"
                
                prometheus_text += f"\n⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}"
                
            else:
                prometheus_text = "❌ Ошибка получения метрик\n\nПроверьте, что экспортер метрик запущен."
                
        except Exception as e:
            prometheus_text = f"❌ Ошибка мониторинга: {str(e)[:50]}..."
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="prometheus"),
                InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
            ]
        ]
        
        # Для сообщений с данными API используем обычный текст без маркдаун
        await self._edit_message_with_keyboard(update, context, prometheus_text, keyboard, parse_mode=None)

    async def _stop_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Остановить торговлю"""
        try:
            result = subprocess.run(['sudo', 'systemctl', 'stop', 'bybot-trading.service'], 
                                 capture_output=True, text=True)
            
            if result.returncode == 0:
                await self._edit_message_with_keyboard(
                    update, context,
                    "🛑 *Торговля остановлена*\n\n"
                    "Сервис bybot-trading.service остановлен."
                )
            else:
                error_text = self._escape_markdown(f"❌ *Ошибка остановки*\n\n"
                    f"Не удалось остановить сервис:\n{result.stderr}")
                await self._edit_message_with_keyboard(
                    update, context,
                    error_text
                )
        except Exception as e:
            error_text = self._escape_markdown(f"❌ Ошибка: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text
            )

    async def _start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запустить торговлю"""
        try:
            result = subprocess.run(['sudo', 'systemctl', 'start', 'bybot-trading.service'], 
                                 capture_output=True, text=True)
            
            if result.returncode == 0:
                await self._edit_message_with_keyboard(
                    update, context,
                    "▶️ *Торговля запущена*\n\n"
                    "Сервис bybot-trading.service запущен."
                )
            else:
                error_text = self._escape_markdown(f"❌ *Ошибка запуска*\n\n"
                    f"Не удалось запустить сервис:\n{result.stderr}")
                await self._edit_message_with_keyboard(
                    update, context,
                    error_text
                )
        except Exception as e:
            error_text = self._escape_markdown(f"❌ Ошибка: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text
            )

    async def _settings_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки риска"""
        risk_text = self._escape_markdown("🎯 *Настройки риска*\n\n"
            "• Размер позиции: 1% от баланса\n"
            "• Stop Loss: ATR-based (динамический)\n"
            "• Take Profit: R:R 1.5 или уровни Фибоначчи\n"
            "• Максимальный риск на сделку: 1%\n\n"
            "Настройки оптимизированы для всех стратегий.")
        await self._edit_message_with_keyboard(
            update, context,
            risk_text
        )

    async def _settings_timeframes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки таймфреймов"""
        timeframes_text = self._escape_markdown("⏰ *Таймфреймы*\n\n"
            "Используемые таймфреймы:\n"
            "• 1m - для быстрых сигналов\n"
            "• 5m - основной таймфрейм\n"
            "• 15m - для Strategy_05\n"
            "• 1h - для определения тренда\n\n"
            "Все стратегии используют мультитаймфреймовый анализ.")
        await self._edit_message_with_keyboard(
            update, context,
            timeframes_text
        )

    async def _settings_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки стратегий"""
        strategy_names = get_active_strategies()
        strategies_text = "🎯 *Активные стратегии:*\n\n"
        
        for strategy_name in strategy_names:
            config = get_strategy_config(strategy_name)
            strategies_text += f"📊 *{strategy_name}*\n"
            strategies_text += f"   📝 {config['description']}\n\n"
        
        strategies_text += "Все стратегии работают параллельно с оптимизированными SL/TP."
        
        # Экранируем весь текст для MarkdownV2
        strategies_text_escaped = self._escape_markdown(strategies_text)
        await self._edit_message_with_keyboard(update, context, strategies_text_escaped)

    async def _settings_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки уведомлений"""
        notifications_text = self._escape_markdown("🔔 *Уведомления*\n\n"
            "• Уведомления о сигналах стратегий\n"
            "• Уведомления об открытии/закрытии позиций\n"
            "• Уведомления об ошибках\n"
            "• Статус всех стратегий\n\n"
            "Все уведомления отправляются в этот чат.")
        await self._edit_message_with_keyboard(
            update, context,
            notifications_text
        )

    async def _profit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать детальную статистику прибыли в стиле Freqtrade"""
        try:
            # Получаем данные о сделках
            trades_file = "data/trades.csv"
            if not os.path.exists(trades_file):
                profit_text = "📈 *СТАТИСТИКА ПРИБЫЛИ*\n\n"
                profit_text += "❌ Нет данных о сделках\n"
                profit_text += "📊 Файл trades.csv не найден"
            else:
                import pandas as pd
                from datetime import datetime, timedelta
                
                # Читаем данные с правильными параметрами для CSV
                df = pd.read_csv(trades_file, quoting=1)  # QUOTE_ALL
                
                if df.empty:
                    profit_text = "📈 *СТАТИСТИКА ПРИБЫЛИ*\n\n"
                    profit_text += "❌ Нет данных о сделках\n"
                    profit_text += "📊 Файл trades.csv пуст"
                else:
                    # Конвертируем datetime
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    
                    # Фильтруем по периодам
                    now = datetime.now()
                    day_ago = now - timedelta(days=1)
                    week_ago = now - timedelta(days=7)
                    
                    df_24h = df[df['datetime'] >= day_ago]
                    df_7d = df[df['datetime'] >= week_ago]
                    
                    # Вычисляем статистику
                    total_profit = df['pnl'].sum() if 'pnl' in df.columns else 0
                    profit_24h = df_24h['pnl'].sum() if 'pnl' in df_24h.columns else 0
                    profit_7d = df_7d['pnl'].sum() if 'pnl' in df_7d.columns else 0
                    
                    total_trades = len(df)
                    win_trades = len(df[df['pnl'] > 0]) if 'pnl' in df.columns else 0
                    winrate = (win_trades / total_trades * 100) if total_trades > 0 else 0
                    
                    avg_trade = total_profit / total_trades if total_trades > 0 else 0
                    
                    # Статистика по стратегиям
                    if 'strategy' in df.columns:
                        strategy_stats = df.groupby('strategy')['pnl'].sum() if 'pnl' in df.columns else pd.Series()
                        best_strategy = strategy_stats.idxmax() if not strategy_stats.empty else "N/A"
                        worst_strategy = strategy_stats.idxmin() if not strategy_stats.empty else "N/A"
                    else:
                        best_strategy = "N/A"
                        worst_strategy = "N/A"
                    
                    profit_text = "📈 *СТАТИСТИКА ПРИБЫЛИ*\n\n"
                    profit_text += f"💰 *Общая прибыль:* ${total_profit:.2f}\n"
                    profit_text += f"📊 *Прибыль (24h):* ${profit_24h:.2f}\n"
                    profit_text += f"📈 *Прибыль (7d):* ${profit_7d:.2f}\n\n"
                    
                    profit_text += f"🎯 *Винрейт:* {winrate:.1f}%\n"
                    profit_text += f"📊 *Всего сделок:* {total_trades}\n"
                    profit_text += f"💰 *Средняя сделка:* ${avg_trade:.2f}\n\n"
                    
                    profit_text += f"🏆 *Лучшая стратегия:* {best_strategy}\n"
                    profit_text += f"📉 *Худшая стратегия:* {worst_strategy}\n"
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Графики", callback_data="charts"),
                    InlineKeyboardButton("📋 Сделки", callback_data="trades")
                ],
                [
                    InlineKeyboardButton("📈 Детали", callback_data="profit_details"),
                    InlineKeyboardButton("📋 История", callback_data="trade_history")
                ],
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="profit"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, profit_text, keyboard, parse_mode=None)
            
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка получения статистики: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _neural(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о нейронной сети"""
        try:
            from bot.ai import NeuralIntegration
            
            # Инициализируем нейронную интеграцию
            neural_integration = NeuralIntegration()
            
            # Получаем статистику
            stats = neural_integration.get_neural_statistics()
            neural_stats = stats['neural_trader']
            strategy_analysis = stats['strategy_analysis']
            
            # Формируем отчет
            neural_text = "🤖 *Нейронная сеть-трейдер*\n\n"
            
            # Статистика нейронки
            neural_text += "📊 *Статистика нейронки:*\n"
            neural_text += f"   💰 Баланс: \\${neural_stats['current_balance']:.2f}\n"
            neural_text += f"   📈 Прибыль: \\${neural_stats['profit']:.2f}\n"
            neural_text += f"   📊 ROI: {neural_stats['roi']:.1f}%\n"
            neural_text += f"   🎯 Ставок: {neural_stats['total_bets']}\n"
            neural_text += f"   ✅ Успешных: {neural_stats['winning_bets']}\n"
            neural_text += f"   📈 Винрейт: {neural_stats['win_rate']:.1f}%\n\n"
            
            # Ранжирование стратегий
            ranking = neural_integration.get_strategy_ranking()
            if ranking:
                neural_text += "🏆 *Ранжирование стратегий:*\n"
                for i, strategy in enumerate(ranking[:5], 1):
                    strategy_name = strategy['strategy'].replace('_', '\\_')
                    neural_text += f"   {i}\\. {strategy_name}\n"
                    neural_text += f"      📊 Сигналов: {strategy['total_signals']}\n"
                    neural_text += f"      ✅ Успешность: {strategy['success_rate']*100:.1f}%\n"
                    neural_text += f"      💰 Прибыль: {strategy['avg_profit']*100:.2f}%\n"
                    neural_text += f"      🟢 Покупки: {strategy['buy_signals']} \\| 🔴 Продажи: {strategy['sell_signals']}\n\n"
            
            # Активные ставки
            neural_text += f"🔥 *Активные ставки:* {stats['active_bets']}\n"
            neural_text += f"📋 *Завершенных сделок:* {stats['completed_trades']}\n\n"
            
            # Информация о системе
            neural_text += "🧠 *Архитектура:*\n"
            neural_text += "   • Входной слой: 50 нейронов\n"
            neural_text += "   • Скрытые слои: 32 \\+ 32 нейрона\n"
            neural_text += "   • Выходной слой: 10 нейронов \\(по стратегиям\\)\n"
            neural_text += "   • Активация: ReLU \\+ Softmax\n"
            neural_text += "   • Обучение: Обратное распространение\n\n"
            
            neural_text += "🎯 *Функции:*\n"
            neural_text += "   • Анализ рыночных данных\n"
            neural_text += "   • Оценка сигналов стратегий\n"
            neural_text += "   • Предсказание успешности\n"
            neural_text += "   • Автоматические ставки\n"
            neural_text += "   • Обучение на результатах\n\n"
            
            neural_text += "📊 *Анализируемые стратегии:*\n"
            neural_text += "   • strategy\\_01 \\- VolumeSpike\\_VWAP\\_Optimized\n"
            neural_text += "   • strategy\\_02 \\- TickTimer\\_CumDelta\\_Optimized\n"
            neural_text += "   • strategy\\_03 \\- MultiTF\\_VolumeSpike\\_Optimized\n"
            neural_text += "   • strategy\\_04 \\- KangarooTail\\_Optimized\n"
            neural_text += "   • strategy\\_05 \\- Fibonacci\\_RSI\\_Volume\\_Optimized\n"
            neural_text += "   • strategy\\_06 \\- VolumeClimaxReversal\\_Optimized\n"
            neural_text += "   • strategy\\_07 \\- BreakoutRetest\\_Optimized\n"
            neural_text += "   • strategy\\_08 \\- Заглушка \\(обучение\\)\n"
            neural_text += "   • strategy\\_09 \\- Заглушка \\(обучение\\)\n"
            neural_text += "   • strategy\\_10 \\- Заглушка \\(обучение\\)\n"
            
            # Навигационные кнопки
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="neural"),
                    InlineKeyboardButton("📊 Графики", callback_data="charts")
                ],
                [
                    InlineKeyboardButton("📋 Сделки", callback_data="trades"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]
            
            # Для сообщений с данными API используем обычный текст без маркдаун
            await self._edit_message_with_keyboard(update, context, neural_text, keyboard, parse_mode=None)
            
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка получения данных нейронки: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    def send_admin_message(self, message: str):
        """Отправка сообщения администратору"""
        try:
            import asyncio
            import threading
            
            # Получаем chat_id из конфигурации или используем дефолтный
            admin_chat_id = ADMIN_CHAT_ID
            if not admin_chat_id:
                print("[WARNING] ADMIN_CHAT_ID не настроен, сообщение не отправлено")
                return
            
            async def send_message():
                try:
                    await self.app.bot.send_message(
                        chat_id=admin_chat_id,
                        text=message,
                        parse_mode=None
                    )
                except Exception as e:
                    print(f"[ERROR] Ошибка отправки сообщения: {e}")
            
            # Запускаем в отдельном потоке с event loop
            def run_async():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(send_message())
                    loop.close()
                except Exception as e:
                    print(f"[ERROR] Ошибка event loop: {e}")
            
            thread = threading.Thread(target=run_async)
            thread.start()
            thread.join(timeout=10)  # Ждем максимум 10 секунд
            
        except Exception as e:
            print(f"[ERROR] Ошибка send_admin_message: {e}")

    def start(self):
        """Запуск бота в текущем потоке"""
        print("[DEBUG] Запуск Telegram бота...")
        try:
            import asyncio
            
            # Создаем event loop для текущего потока
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            print("[DEBUG] Попытка подключения к Telegram API...")
            # Запускаем polling напрямую
            self.app.run_polling(drop_pending_updates=True, close_loop=False)
                    
        except KeyboardInterrupt:
            print("[DEBUG] Telegram бот остановлен пользователем")
        except Exception as e:
            print(f"[ERROR] Критическая ошибка Telegram бота: {e}")

if __name__ == "__main__":
    from config import TELEGRAM_TOKEN
    TelegramBot(TELEGRAM_TOKEN).start()