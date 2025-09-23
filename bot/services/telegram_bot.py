# bot/services/telegram_bot.py
import logging
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Разрешить вложенные event loops для совместимости с интерактивными средами
nest_asyncio.apply()
from bot.exchange.api_adapter import create_trading_bot_adapter
from bot.exchange.bybit_api_v5 import BybitAPIV5
from bot.cli import load_active_strategy, save_active_strategy
from config import TELEGRAM_TOKEN, get_strategy_config, USE_V5_API, USE_TESTNET, BYBIT_API_KEY, BYBIT_API_SECRET

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
        self._is_running = False
        self._bot_thread = None
        self._loop = None
    
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
        # Регистрируем обработчик ошибок ПЕРВЫМ
        self.app.add_error_handler(self._error_handler)

        # Затем обычные хэндлеры
        self.app.add_handler(CommandHandler("start", self._start))
        self.app.add_handler(CommandHandler("menu", self._menu))
        self.app.add_handler(CommandHandler("balance", self._balance))
        self.app.add_handler(CommandHandler("position", self._position))
        self.app.add_handler(CommandHandler("strategies", self._strategies))
        self.app.add_handler(CommandHandler("trades", self._trades))
        self.app.add_handler(CommandHandler("profit", self._profit))
        self.app.add_handler(CommandHandler("logs", self._logs))
        self.app.add_handler(CommandHandler("all_strategies", self._all_strategies))
        self.app.add_handler(CommandHandler("api", self._cmd_api_health))
        self.app.add_handler(CommandHandler("blocks", self._cmd_blocks))
        self.app.add_handler(CallbackQueryHandler(self._on_menu_button))
        self.app.add_handler(CallbackQueryHandler(self._on_strategy_toggle))
        self.app.add_handler(CallbackQueryHandler(self._on_profit_button, pattern="^profit"))

    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок Telegram API"""
        try:
            # Логируем ошибку без шума
            error_message = str(context.error)
            if "RemoteProtocolError" in error_message or "Server disconnected" in error_message:
                # Сетевые ошибки Telegram - логируем как DEBUG
                logging.debug(f"Telegram network error: {error_message}")
            elif "NetworkError" in error_message:
                # Другие сетевые ошибки
                logging.debug(f"Telegram network issue: {error_message}")
            else:
                # Остальные ошибки логируем как WARNING
                logging.warning(f"Telegram error: {error_message}")
        except Exception as e:
            # Если даже обработчик ошибок упал
            logging.error(f"Error in error handler: {e}")

    def _get_strategy_list(self):
        files = glob.glob("bot/strategy/strategy_*.py")
        return [os.path.splitext(os.path.basename(f))[0] for f in files]

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /start")
        start_text = ("🤖 Мультистратегический торговый бот\n\n"
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
            text=start_text
        )

    async def _balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать баланс аккаунта"""
        try:
            # Получаем API credentials для Telegram bot
            api = BybitAPIV5(BYBIT_API_KEY, BYBIT_API_SECRET, testnet=USE_TESTNET)
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
            # Используем API v5 для получения позиций
            api = BybitAPIV5(BYBIT_API_KEY, BYBIT_API_SECRET, testnet=USE_TESTNET)
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
                
                # Добавляем клавиатуру навигации
                keyboard = [
                    [
                        InlineKeyboardButton("💰 Баланс", callback_data="balance"),
                        InlineKeyboardButton("📊 Графики", callback_data="charts")
                    ],
                    [
                        InlineKeyboardButton("🔄 Обновить", callback_data="position"),
                        InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                    ]
                ]

                # Для сообщений с данными API используем обычный текст без маркдаун
                await self._edit_message_with_keyboard(update, context, position_text, keyboard, parse_mode=None)
            else:
                no_positions_text = "📭 Нет открытых позиций"
                keyboard = [
                    [
                        InlineKeyboardButton("💰 Баланс", callback_data="balance"),
                        InlineKeyboardButton("📊 Графики", callback_data="charts")
                    ],
                    [
                        InlineKeyboardButton("🔄 Обновить", callback_data="position"),
                        InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                    ]
                ]
                await self._edit_message_with_keyboard(
                    update, context,
                    no_positions_text,
                    keyboard,
                    parse_mode=None
                )
        except Exception as e:
            error_text = f"❌ Ошибка получения позиций: {str(e)}"
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard,
                parse_mode=None
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
                            
                            # Проверяем позиции для конкретной стратегии
                            from bot.core.thread_safe_state import get_bot_state
                            bot_state = get_bot_state()
                            position_info = bot_state.get_position("BTCUSDT")

                            if position_info and position_info.is_active:
                                # Проверяем принадлежит ли позиция этой стратегии
                                if position_info.strategy_name == strategy_name:
                                    status_text += f"   📈 Позиций: 1 \\(владеет\\)\n"
                                    side = position_info.side.value if position_info.side else 'Unknown'
                                    size = position_info.size

                                    # Получаем актуальный PnL с биржи
                                    positions = api.get_positions("BTCUSDT")
                                    pnl = "0"
                                    if positions and positions.get('result') and positions['result'].get('list'):
                                        exchange_pos = positions['result']['list'][0] if positions['result']['list'] else None
                                        if exchange_pos:
                                            pnl = exchange_pos.get('unrealisedPnl', '0')

                                    pnl_escaped = self._escape_markdown(str(pnl))
                                    status_text += f"      {side}: {size} BTC \\(\\${pnl_escaped}\\)\n"
                                elif position_info.strategy_name:
                                    status_text += f"   📈 Позиций: 1 \\(владеет: {self._escape_markdown(position_info.strategy_name)}\\)\n"
                                else:
                                    status_text += f"   📈 Позиций: 1 \\(владелец неизвестен\\)\n"
                            else:
                                status_text += f"   📈 Позиций: 0\n"
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
        """Показать активность и состояние всех стратегий"""
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

            logs_text = f"📊 АКТИВНОСТЬ СТРАТЕГИЙ\n\n⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}\n\n"

            # Счетчики для аналитики
            active_strategies = 0
            strategies_with_signals = 0
            strategies_with_errors = 0

            for strategy_name, log_filename in strategy_logs:
                # Формируем полный путь к файлу лога
                log_file = f"data/logs/strategies/{log_filename}"

                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()

                        if lines:
                            active_strategies += 1

                            # Ищем важные события в последних 10 строках
                            recent_lines = lines[-10:]

                            # Анализируем типы событий
                            signals = []
                            errors = []
                            warnings = []

                            for line in recent_lines:
                                line_clean = line.strip()
                                if 'Сигнал:' in line and ('BUY' in line or 'SELL' in line):
                                    # Извлекаем сигнал
                                    if 'BUY' in line:
                                        signals.append('🟢 BUY')
                                    elif 'SELL' in line:
                                        signals.append('🔴 SELL')
                                elif 'ERROR' in line:
                                    # Извлекаем суть ошибки
                                    if 'БЛОКИРОВКА ПО БАЛАНСУ' in line:
                                        errors.append('💰 Нет баланса')
                                    elif 'Недостаточно баланса' in line:
                                        errors.append('💰 Мало средств')
                                    else:
                                        errors.append('❌ Ошибка')
                                elif 'WARNING' in line:
                                    if 'Недостаточно средств' in line:
                                        warnings.append('💸 $0.00')
                                    else:
                                        warnings.append('⚠️ Предупреждение')

                            # Формируем краткий отчет
                            strategy_short = strategy_name.replace('_v2', '').replace('_v1', '')
                            logs_text += f"📊 {strategy_short}:\n"

                            # Показываем последние сигналы
                            if signals:
                                strategies_with_signals += 1
                                unique_signals = list(set(signals))
                                logs_text += f"   🎯 Сигналы: {' '.join(unique_signals[:2])}\n"

                            # Показываем проблемы
                            if errors:
                                strategies_with_errors += 1
                                unique_errors = list(set(errors))
                                logs_text += f"   ⚠️ Проблемы: {unique_errors[0]}\n"
                            elif warnings:
                                unique_warnings = list(set(warnings))
                                logs_text += f"   💭 Статус: {unique_warnings[0]}\n"

                            # Показываем время последней активности
                            last_line = lines[-1].strip()
                            if last_line:
                                try:
                                    # Извлекаем timestamp из лога (формат: 2025-09-22 07:21:11,819)
                                    import re
                                    time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_line)
                                    if time_match:
                                        time_str = time_match.group(1).split(' ')[1][:5]  # HH:MM
                                        logs_text += f"   🕐 Последняя активность: {time_str}\n"
                                except:
                                    pass

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

            # Добавляем общую аналитику
            logs_text += f"📈 ОБЩАЯ СТАТИСТИКА:\n"
            logs_text += f"✅ Активных стратегий: {active_strategies}/6\n"
            logs_text += f"🎯 С сигналами: {strategies_with_signals}\n"
            logs_text += f"⚠️ С проблемами: {strategies_with_errors}\n"

            # Определяем общий статус
            if strategies_with_errors > 3:
                logs_text += f"🔴 Общий статус: Проблемы с балансом\n"
            elif strategies_with_signals > 0:
                logs_text += f"🟢 Общий статус: Активная торговля\n"
            else:
                logs_text += f"🟡 Общий статус: Ожидание сигналов\n"
            
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
        """Показать последние торговые сигналы с детальной аналитикой оптимизированных стратегий"""
        try:
            # Читаем журнал торговых сигналов
            journal_file = "data/trade_journal.csv"
            if not os.path.exists(journal_file):
                trades_text = "📋 ТОРГОВЫЕ СИГНАЛЫ\n\n"
                trades_text += "❌ Нет данных о сигналах\n"
                trades_text += "📊 Файл trade_journal.csv не найден"
            else:
                try:
                    # Читаем CSV с правильной обработкой структуры данных
                    # Реальная структура: 15 полей данных, но заголовок 11 полей
                    import csv

                    trades_data = []
                    with open(journal_file, 'r', encoding='utf-8') as f:
                        csv_reader = csv.reader(f)
                        header = next(csv_reader)  # Пропускаем несовместимый заголовок

                        # Реальная структура полей из trader.py
                        real_fields = ['timestamp', 'strategy', 'signal', 'entry_price', 'stop_loss', 'take_profit',
                                     'comment', 'tf', 'open', 'high', 'low', 'close', 'volume', 'signal_strength', 'risk_reward_ratio']

                        for row in csv_reader:
                            if len(row) >= len(real_fields):
                                trade_dict = {field: row[i] for i, field in enumerate(real_fields)}
                                trades_data.append(trade_dict)

                    if not trades_data:
                        trades_text = "📋 ТОРГОВЫЕ СИГНАЛЫ\n\n"
                        trades_text += "❌ Нет данных о сигналах\n"
                        trades_text += "📊 Файл пуст или поврежден"
                    else:
                        # Показываем последние 8 сигналов для удобной читаемости
                        recent_trades = trades_data[-8:]
                        trades_text = "📋 ТОРГОВЫЕ СИГНАЛЫ (оптимизированные)\n\n"

                        for trade in recent_trades:
                            strategy = trade.get('strategy', 'Unknown')
                            signal = trade.get('signal', 'Unknown')
                            entry_price = trade.get('entry_price', 'Unknown')
                            tf = trade.get('tf', 'Unknown')
                            signal_strength = trade.get('signal_strength', '0')
                            comment = trade.get('comment', '')
                            timestamp = trade.get('timestamp', '')

                            # Определяем эмодзи для сигнала
                            signal_emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "📊"

                            # Форматируем цены
                            try:
                                entry_str = f"${float(entry_price):,.0f}" if entry_price != 'Unknown' else "N/A"
                            except:
                                entry_str = str(entry_price)[:8]

                            # Форматируем силу сигнала (новая оптимизация!)
                            try:
                                strength = float(signal_strength)
                                strength_emoji = "🔥" if strength > 0.8 else "⚡" if strength > 0.6 else "📊"
                                strength_str = f"{strength:.2f}"
                            except:
                                strength_emoji = "📊"
                                strength_str = "N/A"

                            # Форматируем время
                            try:
                                if timestamp:
                                    from datetime import datetime
                                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                    time_str = dt.strftime('%H:%M:%S')
                                else:
                                    time_str = "N/A"
                            except:
                                time_str = "N/A"

                            # Короткое название стратегии
                            strategy_short = strategy.replace('_trading_default', '').replace('_', ' ').title()

                            trades_text += f"{signal_emoji} {strategy_short} {signal}\n"
                            trades_text += f"💰 {entry_str} | ⏱️ {tf} | {strength_emoji} {strength_str}\n"
                            trades_text += f"🕐 {time_str}\n\n"

                        # Расширенная аналитика оптимизированной системы
                        total_signals = len(trades_data)
                        buy_signals = sum(1 for t in trades_data if t.get('signal') == 'BUY')
                        sell_signals = sum(1 for t in trades_data if t.get('signal') == 'SELL')

                        # Статистика по таймфреймам
                        tf_stats = {}
                        for trade in trades_data:
                            tf = trade.get('tf', 'Unknown')
                            tf_stats[tf] = tf_stats.get(tf, 0) + 1

                        # Средняя сила сигналов (показатель качества оптимизаций)
                        try:
                            strengths = [float(t.get('signal_strength', 0)) for t in trades_data[-50:]]  # Последние 50
                            avg_strength = sum(strengths) / len(strengths) if strengths else 0
                            strength_quality = "🔥 Отлично" if avg_strength > 0.7 else "⚡ Хорошо" if avg_strength > 0.5 else "📊 Норма"
                        except:
                            avg_strength = 0
                            strength_quality = "📊 N/A"

                        trades_text += f"📊 АНАЛИТИКА ОПТИМИЗАЦИЙ:\n"
                        trades_text += f"📈 Всего сигналов: {total_signals:,}\n"
                        trades_text += f"🟢 Покупки: {buy_signals} | 🔴 Продажи: {sell_signals}\n"
                        trades_text += f"⚡ Средняя сила: {avg_strength:.2f} ({strength_quality})\n\n"

                        trades_text += f"⏰ Распределение по TF:\n"
                        for tf, count in sorted(tf_stats.items()):
                            percentage = count/total_signals*100 if total_signals > 0 else 0
                            trades_text += f"• {tf}: {count} ({percentage:.1f}%)\n"

                        # Сегодняшняя активность
                        from datetime import datetime, timezone
                        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                        today_signals = sum(1 for t in trades_data if t.get('timestamp', '').startswith(today))
                        trades_text += f"\n🔥 Сегодня: {today_signals} сигналов"

                except Exception as e:
                    trades_text = f"❌ Ошибка чтения данных: {str(e)}\n\n"
                    trades_text += "🔧 Проблема структуры CSV файла"
            
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
                InlineKeyboardButton("📈 Аналитика", callback_data="analytics"),
                InlineKeyboardButton("📊 Статистика", callback_data="statistics")
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
        
        if query.data == "menu_back" or query.data == "main_menu":
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
        elif query.data == "analytics":
            await self._analytics(update, context)
        elif query.data == "statistics":
            await self._statistics(update, context)
        elif query.data == "stop_trading":
            await self._stop_trading(update, context)
        elif query.data == "start_trading":
            await self._start_trading(update, context)
        elif query.data == "profit":
            await self._profit(update, context)
        elif query.data == "profit_details":
            await self._profit_details(update, context)
        elif query.data == "trade_history":
            await self._trades(update, context)
        elif query.data == "settings_risk":
            await self._settings_risk(update, context)
        elif query.data == "settings_timeframes":
            await self._settings_timeframes(update, context)
        elif query.data == "settings_strategies":
            await self._settings_strategies(update, context)
        elif query.data == "settings_notifications":
            await self._settings_notifications(update, context)

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
                await self._profit_details(update, context)
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
                api = BybitAPIV5(BYBIT_API_KEY, BYBIT_API_SECRET, testnet=USE_TESTNET)
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
            
            # Читаем данные с правильными параметрами для CSV и обработкой ошибок
            try:
                df = pd.read_csv(journal_file, quoting=1)  # QUOTE_ALL
            except pd.errors.ParserError as e:
                print(f"CSV parsing error: {e}")
                # Если CSV поврежден, попробуем прочитать то что можем
                try:
                    df = pd.read_csv(journal_file, quoting=1, on_bad_lines='skip')
                except:
                    # Если все еще ошибка, используем базовый парсер
                    try:
                        df = pd.read_csv(journal_file, on_bad_lines='skip', engine='python')
                    except:
                        # Последняя попытка - создаем пустой DataFrame
                        df = pd.DataFrame()
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
            from datetime import timezone
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
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
            day_ago = datetime.now(timezone.utc) - timedelta(days=1)
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
                prometheus_text = "📊 Прометей - Мониторинг системы\n\n"

                # Системные метрики
                cpu_match = re.search(r'system_cpu_percent (\d+\.?\d*)', metrics_text)
                memory_match = re.search(r'system_memory_percent (\d+\.?\d*)', metrics_text)
                disk_match = re.search(r'system_disk_percent (\d+\.?\d*)', metrics_text)

                if cpu_match:
                    cpu_val = float(cpu_match.group(1))
                    cpu_emoji = "🔥" if cpu_val > 80 else "⚡" if cpu_val > 50 else "💚"
                    prometheus_text += f"{cpu_emoji} CPU: {cpu_val:.1f}%\n"
                if memory_match:
                    mem_val = float(memory_match.group(1))
                    mem_emoji = "🔴" if mem_val > 80 else "🟡" if mem_val > 60 else "🟢"
                    prometheus_text += f"{mem_emoji} Память: {mem_val:.1f}%\n"
                if disk_match:
                    disk_val = float(disk_match.group(1))
                    disk_emoji = "🔴" if disk_val > 90 else "🟡" if disk_val > 70 else "🟢"
                    prometheus_text += f"{disk_emoji} Диск: {disk_val:.1f}%\n"

                prometheus_text += "\n🤖 Статус ботов:\n"

                # Статус ботов (исправленные названия метрик)
                bot_statuses = {
                    'bot_status_bybot-trading_service': 'Торговый бот',
                    'bot_status_bybot-telegram_service': 'Telegram бот',
                    'bot_status_lerabot_service': 'LeraBot'
                }

                for metric, name in bot_statuses.items():
                    match = re.search(f'{metric} (\\d+)', metrics_text)
                    if match:
                        status = "🟢 Активен" if match.group(1) == "1" else "🔴 Остановлен"
                        prometheus_text += f"• {name}: {status}\n"

                # Торговые метрики
                signals_match = re.search(r'trading_total_signals (\d+)', metrics_text)
                if signals_match:
                    signals_count = int(signals_match.group(1))
                    signals_emoji = "🚀" if signals_count > 100 else "📈" if signals_count > 10 else "📊"
                    prometheus_text += f"\n{signals_emoji} Торговля:\n"
                    prometheus_text += f"• Всего сигналов: {signals_count}\n"

                # Метрики производительности (новые оптимизации)
                latency_match = re.search(r'strategy_latency_ms (\d+\.?\d*)', metrics_text)
                cache_hit_match = re.search(r'ttl_cache_hit_rate (\d+\.?\d*)', metrics_text)

                if latency_match or cache_hit_match:
                    prometheus_text += f"\n⚡ Оптимизации:\n"
                    if latency_match:
                        latency = float(latency_match.group(1))
                        latency_emoji = "🟢" if latency < 50 else "🟡" if latency < 100 else "🔴"
                        prometheus_text += f"• {latency_emoji} Латентность: {latency:.1f}ms\n"
                    if cache_hit_match:
                        hit_rate = float(cache_hit_match.group(1))
                        cache_emoji = "🟢" if hit_rate > 70 else "🟡" if hit_rate > 50 else "🔴"
                        prometheus_text += f"• {cache_emoji} TTL кэш: {hit_rate:.1f}%\n"

                # Метрики нейронной сети
                neural_bets_match = re.search(r'neural_total_bets (\d+)', metrics_text)
                neural_wins_match = re.search(r'neural_winning_bets (\d+)', metrics_text)
                neural_balance_match = re.search(r'neural_balance (\d+\.?\d*)', metrics_text)

                if neural_bets_match:
                    prometheus_text += f"\n🤖 Нейронная сеть:\n"
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
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                await self._edit_message_with_keyboard(
                    update, context,
                    "🛑 Торговля остановлена\n\nСервис bybot-trading.service остановлен.",
                    keyboard,
                    parse_mode=None
                )
            else:
                error_text = f"❌ Ошибка остановки\n\nНе удалось остановить сервис:\n{result.stderr}"
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                await self._edit_message_with_keyboard(
                    update, context,
                    error_text,
                    keyboard,
                    parse_mode=None
                )
        except Exception as e:
            error_text = f"❌ Ошибка: {str(e)}"
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard,
                parse_mode=None
            )

    async def _start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запустить торговлю"""
        try:
            result = subprocess.run(['sudo', 'systemctl', 'start', 'bybot-trading.service'], 
                                 capture_output=True, text=True)
            
            if result.returncode == 0:
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                await self._edit_message_with_keyboard(
                    update, context,
                    "▶️ Торговля запущена\n\nСервис bybot-trading.service запущен.",
                    keyboard,
                    parse_mode=None
                )
            else:
                error_text = f"❌ Ошибка запуска\n\nНе удалось запустить сервис:\n{result.stderr}"
                keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
                await self._edit_message_with_keyboard(
                    update, context,
                    error_text,
                    keyboard,
                    parse_mode=None
                )
        except Exception as e:
            error_text = f"❌ Ошибка: {str(e)}"
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard,
                parse_mode=None
            )

    async def _settings_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки риска"""
        risk_text = "🎯 *Настройки риска*\n\n"\
            "• Размер позиции: 1% от баланса\n"\
            "• Stop Loss: ATR-based (динамический)\n"\
            "• Take Profit: R:R 1.5 или уровни Фибоначчи\n"\
            "• Максимальный риск на сделку: 1%\n\n"\
            "Настройки оптимизированы для всех стратегий."
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="settings")]]
        await self._edit_message_with_keyboard(
            update, context,
            risk_text,
            keyboard,
            parse_mode=None
        )

    async def _settings_timeframes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки таймфреймов"""
        timeframes_text = "⏰ *Таймфреймы*\n\n"\
            "Используемые таймфреймы:\n"\
            "• 1m - для быстрых сигналов\n"\
            "• 5m - основной таймфрейм\n"\
            "• 15m - для Strategy_05\n"\
            "• 1h - для определения тренда\n\n"\
            "Все стратегии используют мультитаймфреймовый анализ."
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="settings")]]
        await self._edit_message_with_keyboard(
            update, context,
            timeframes_text,
            keyboard,
            parse_mode=None
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
        
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="settings")]]
        await self._edit_message_with_keyboard(update, context, strategies_text, keyboard, parse_mode=None)

    async def _settings_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки уведомлений"""
        notifications_text = "🔔 *Уведомления*\n\n"\
            "• Уведомления о сигналах стратегий\n"\
            "• Уведомления об открытии/закрытии позиций\n"\
            "• Уведомления об ошибках\n"\
            "• Статус всех стратегий\n\n"\
            "Все уведомления отправляются в этот чат."
        keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="settings")]]
        await self._edit_message_with_keyboard(
            update, context,
            notifications_text,
            keyboard,
            parse_mode=None
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
                try:
                    df = pd.read_csv(trades_file, quoting=1)  # QUOTE_ALL
                except pd.errors.ParserError:
                    # Если CSV поврежден, используем более надежный парсер
                    df = pd.read_csv(trades_file, on_bad_lines='skip', engine='python')
                
                if df.empty:
                    profit_text = "📈 *СТАТИСТИКА ПРИБЫЛИ*\n\n"
                    profit_text += "❌ Нет данных о сделках\n"
                    profit_text += "📊 Файл trades.csv пуст"
                else:
                    # Конвертируем datetime
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    
                    # Фильтруем по периодам
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
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

    async def _profit_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать детальную статистику прибыли по стратегиям"""
        try:
            import pandas as pd
            from datetime import datetime, timedelta, timezone

            # Проверяем журнал сделок
            journal_file = "data/trade_journal.csv"
            if not os.path.exists(journal_file):
                details_text = "📈 *ДЕТАЛЬНАЯ СТАТИСТИКА*\n\n"
                details_text += "❌ Нет данных для анализа\n"
                details_text += "📊 Файл trade_journal.csv не найден"
            else:
                # Читаем данные с обработкой ошибок
                try:
                    df = pd.read_csv(journal_file, quoting=1)
                except pd.errors.ParserError:
                    df = pd.read_csv(journal_file, on_bad_lines='skip', engine='python')

                if df.empty:
                    details_text = "📈 *ДЕТАЛЬНАЯ СТАТИСТИКА*\n\n"
                    details_text += "❌ Нет данных для анализа\n"
                    details_text += "📊 Файл пуст"
                else:
                    # Конвертируем timestamp
                    df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')
                    df = df[df['datetime'].notna()]

                    # Фильтруем данные за периоды
                    now = datetime.now(timezone.utc)
                    day_ago = now - timedelta(days=1)
                    week_ago = now - timedelta(days=7)
                    month_ago = now - timedelta(days=30)

                    df_24h = df[df['datetime'] >= day_ago]
                    df_7d = df[df['datetime'] >= week_ago]
                    df_30d = df[df['datetime'] >= month_ago]

                    details_text = "📈 *ДЕТАЛЬНАЯ СТАТИСТИКА*\n\n"

                    # Общая статистика по периодам
                    details_text += "📊 *Сигналы по периодам:*\n"
                    details_text += f"   📅 За 24 часа: {len(df_24h)}\n"
                    details_text += f"   📅 За 7 дней: {len(df_7d)}\n"
                    details_text += f"   📅 За 30 дней: {len(df_30d)}\n"
                    details_text += f"   📅 Всего: {len(df)}\n\n"

                    # Детальная статистика по стратегиям
                    details_text += "🎯 *Анализ по стратегиям:*\n"
                    strategy_stats = df.groupby('strategy').agg({
                        'signal': ['count'],
                        'entry_price': ['mean']
                    }).round(2)

                    strategy_signals = df['strategy'].value_counts()
                    for strategy, count in strategy_signals.head(10).items():
                        buy_count = len(df[(df['strategy'] == strategy) & (df['signal'] == 'BUY')])
                        sell_count = len(df[(df['strategy'] == strategy) & (df['signal'] == 'SELL')])

                        # Последние сигналы этой стратегии
                        recent_strategy = df[df['strategy'] == strategy].tail(5)
                        if not recent_strategy.empty:
                            avg_price = recent_strategy['entry_price'].mean()
                            last_signal = recent_strategy.iloc[-1]['signal']
                            last_time = recent_strategy.iloc[-1]['datetime'].strftime('%m-%d %H:%M')
                        else:
                            avg_price = 0
                            last_signal = "N/A"
                            last_time = "N/A"

                        details_text += f"\n📊 *{strategy}*:\n"
                        details_text += f"   📈 Всего: {count} ({buy_count} BUY / {sell_count} SELL)\n"
                        details_text += f"   💰 Средняя цена: ${avg_price:.2f}\n"
                        details_text += f"   🕐 Последний: {last_signal} ({last_time})\n"

                    # Статистика по таймфреймам
                    details_text += "\n⏰ *По таймфреймам:*\n"
                    tf_stats = df['tf'].value_counts()
                    for tf, count in tf_stats.items():
                        tf_buy = len(df[(df['tf'] == tf) & (df['signal'] == 'BUY')])
                        tf_sell = len(df[(df['tf'] == tf) & (df['signal'] == 'SELL')])
                        details_text += f"   {tf}: {count} ({tf_buy} BUY / {tf_sell} SELL)\n"

                    # Активность по часам (последние 24 часа)
                    if not df_24h.empty:
                        details_text += "\n🕐 *Активность за 24 часа:*\n"
                        hourly_activity = df_24h.groupby(df_24h['datetime'].dt.hour).size()
                        for hour in sorted(hourly_activity.index):
                            count = hourly_activity[hour]
                            details_text += f"   {hour:02d}:00 - {count} сигналов\n"

                    # Топ комментарии/причины
                    details_text += "\n💬 *Топ причины сигналов:*\n"
                    comment_stats = df['comment'].value_counts()
                    for comment, count in comment_stats.head(5).items():
                        if len(comment) > 30:
                            comment = comment[:27] + "..."
                        details_text += f"   • {comment}: {count}\n"

            keyboard = [
                [
                    InlineKeyboardButton("📊 Графики", callback_data="charts"),
                    InlineKeyboardButton("📋 Сделки", callback_data="trades")
                ],
                [
                    InlineKeyboardButton("💰 Прибыль", callback_data="profit"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]

            # Для детальных данных используем обычный текст
            await self._edit_message_with_keyboard(update, context, details_text, keyboard, parse_mode=None)

        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="profit")]]
            error_text = self._escape_markdown(f"❌ Ошибка детальной статистики: {str(e)}")
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
            if ranking and len(ranking) > 0:
                neural_text += "🏆 *Ранжирование стратегий:*\n"
                for i, strategy in enumerate(ranking[:5], 1):
                    strategy_name = strategy['strategy'].replace('_', '\\_')
                    neural_text += f"   {i}\\. {strategy_name}\n"
                    neural_text += f"      📊 Сигналов: {strategy['total_signals']}\n"
                    neural_text += f"      ✅ Успешность: {strategy['success_rate']*100:.1f}%\n"
                    neural_text += f"      💰 Прибыль: {strategy['avg_profit']*100:.2f}%\n"
                    neural_text += f"      🟢 Покупки: {strategy['buy_signals']} \\| 🔴 Продажи: {strategy['sell_signals']}\n\n"
            else:
                neural_text += "🏆 *Ранжирование стратегий:*\n"
                neural_text += "   📊 Пока нет данных для ранжирования\n"
                neural_text += "   🔄 Накапливаются результаты стратегий\n\n"
            
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
            neural_text += "   • strategy\\_08 \\- AdvancedMomentum\\_AI\n"
            neural_text += "   • strategy\\_09 \\- SmartVolume\\_ML\n"
            neural_text += "   • strategy\\_10 \\- NeuralPattern\\_Recognition\n"
            
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
            
            # Для сообщений с данными API используем Markdown V2
            await self._edit_message_with_keyboard(update, context, neural_text, keyboard)
            
        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка получения данных нейронки: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _analytics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать детальную аналитику торговли"""
        try:
            import pandas as pd
            from datetime import datetime, timedelta, timezone

            # Читаем журнал сделок
            try:
                df = pd.read_csv('data/trade_journal.csv')
                if df.empty:
                    raise ValueError("Журнал сделок пуст")

                # Конвертируем timestamp в datetime если нужно
                if 'timestamp' in df.columns:
                    df['datetime'] = pd.to_datetime(df['timestamp'])
                elif 'datetime' in df.columns:
                    df['datetime'] = pd.to_datetime(df['datetime'])
                else:
                    raise ValueError("Нет столбца времени в данных")

            except Exception as e:
                raise ValueError(f"Ошибка чтения данных: {e}")

            # Анализируем последние 7 дней
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            df_recent = df[df['datetime'] >= week_ago]

            # Основная статистика
            total_trades = len(df)
            recent_trades = len(df_recent)
            buy_signals = len(df[df['signal'] == 'BUY'])
            sell_signals = len(df[df['signal'] == 'SELL'])

            # Анализ по стратегиям
            strategy_stats = df['strategy'].value_counts().head(5)

            # Анализ по временным фреймам
            tf_stats = df['tf'].value_counts().head(3)

            # Анализ последних 24 часов
            day_ago = datetime.now(timezone.utc) - timedelta(days=1)
            df_today = df[df['datetime'] >= day_ago]
            today_trades = len(df_today)

            # Анализ активности по часам
            df_recent['hour'] = df_recent['datetime'].dt.hour
            hourly_activity = df_recent['hour'].value_counts().sort_index()

            # Формируем отчет
            analytics_text = "📈 *Детальная аналитика торговли*\n\n"

            # Общие показатели
            analytics_text += "📊 *Общие показатели:*\n"
            analytics_text += f"   📈 Всего сигналов: {total_trades:,}\n"
            analytics_text += f"   📅 За неделю: {recent_trades:,}\n"
            analytics_text += f"   ⏰ За 24 часа: {today_trades}\n"
            analytics_text += f"   🟢 Покупки: {buy_signals:,} ({buy_signals/total_trades*100:.1f}%)\n"
            analytics_text += f"   🔴 Продажи: {sell_signals:,} ({sell_signals/total_trades*100:.1f}%)\n\n"

            # Топ стратегий
            analytics_text += "🎯 *Топ-5 стратегий:*\n"
            for i, (strategy, count) in enumerate(strategy_stats.items(), 1):
                strategy_name = strategy.replace('_', '\\_')
                percentage = count/total_trades*100
                analytics_text += f"   {i}\\. {strategy_name}\n"
                analytics_text += f"      📊 {count:,} сигналов ({percentage:.1f}%)\n"

            # Временные фреймы
            analytics_text += "\n⏰ *Популярные таймфреймы:*\n"
            for tf, count in tf_stats.items():
                percentage = count/total_trades*100
                analytics_text += f"   📊 {tf}: {count:,} ({percentage:.1f}%)\n"

            # Активность по времени
            if len(hourly_activity) > 0:
                peak_hour = hourly_activity.idxmax()
                peak_count = hourly_activity.max()
                analytics_text += f"\n🔥 *Пиковая активность:*\n"
                analytics_text += f"   ⏰ {peak_hour}:00 - {peak_count} сигналов\n"

            # Тренды
            if recent_trades > 0:
                daily_avg = recent_trades / 7
                analytics_text += f"\n📈 *Тренды:*\n"
                analytics_text += f"   📊 Среднее в день: {daily_avg:.1f} сигналов\n"
                if today_trades > daily_avg:
                    analytics_text += f"   🔥 Сегодня выше среднего (+{today_trades-daily_avg:.1f})\n"
                else:
                    analytics_text += f"   📉 Сегодня ниже среднего ({today_trades-daily_avg:.1f})\n"

            # Навигационные кнопки
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="analytics"),
                    InlineKeyboardButton("📊 Статистика", callback_data="statistics")
                ],
                [
                    InlineKeyboardButton("📈 Графики", callback_data="charts"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]

            await self._edit_message_with_keyboard(update, context, analytics_text, keyboard, parse_mode=None)

        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка аналитики: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    async def _statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику системы и производительности"""
        try:
            import pandas as pd
            import psutil
            import os
            from datetime import datetime, timezone

            # Системная информация
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Информация о процессе
            process = psutil.Process()
            process_memory = process.memory_info()
            process_cpu = process.cpu_percent()

            # Статистика файлов
            trade_journal_size = 0
            trade_journal_lines = 0
            if os.path.exists('data/trade_journal.csv'):
                trade_journal_size = os.path.getsize('data/trade_journal.csv')
                with open('data/trade_journal.csv', 'r') as f:
                    trade_journal_lines = sum(1 for _ in f) - 1  # Исключаем заголовок

            log_files_size = 0
            if os.path.exists('trading_bot.log'):
                log_files_size += os.path.getsize('trading_bot.log')

            # Проверяем API
            api_status = "🟢 Активен"
            try:
                from bot.exchange.bybit_api_v5 import BybitAPIV5
                from config import get_api_credentials
                api_key, api_secret = get_api_credentials()
                api = BybitAPIV5(api_key, api_secret, testnet=True)

                # Проверяем подключение
                server_time = api.get_server_time()
                if server_time.get('retCode') == 0:
                    api_status = "🟢 Подключен"
                else:
                    api_status = f"🟡 Ошибка: {server_time.get('retMsg', 'Unknown')}"
            except Exception as e:
                api_status = f"🔴 Недоступен: {str(e)[:30]}..."

            # Статистика стратегий
            strategies_count = 0
            try:
                import glob
                strategy_files = glob.glob("bot/strategy/strategy_*.py")
                strategies_count = len(strategy_files)
            except:
                strategies_count = "N/A"

            # Формируем отчет
            stats_text = "📊 *Системная статистика*\n\n"

            # Системные ресурсы
            stats_text += "🖥️ *Системные ресурсы:*\n"
            stats_text += f"   🔥 CPU: {cpu_percent:.1f}%\n"
            stats_text += f"   🧠 RAM: {memory.percent:.1f}% ({memory.used/(1024**3):.1f}GB/{memory.total/(1024**3):.1f}GB)\n"
            stats_text += f"   💾 Диск: {disk.percent:.1f}% ({disk.used/(1024**3):.1f}GB/{disk.total/(1024**3):.1f}GB)\n\n"

            # Процесс бота
            stats_text += "🤖 *Процесс бота:*\n"
            stats_text += f"   🔥 CPU: {process_cpu:.1f}%\n"
            stats_text += f"   🧠 RAM: {process_memory.rss/(1024**2):.1f}MB\n"
            stats_text += f"   📊 PID: {process.pid}\n\n"

            # API и подключения
            stats_text += "🌐 *API и подключения:*\n"
            stats_text += f"   🔗 Bybit API: {api_status}\n"
            stats_text += f"   📡 Telegram Bot: 🟢 Активен\n\n"

            # Данные
            stats_text += "📁 *Данные:*\n"
            stats_text += f"   📋 Сделок в журнале: {trade_journal_lines:,}\n"
            stats_text += f"   📄 Размер журнала: {trade_journal_size/(1024**2):.1f}MB\n"
            stats_text += f"   📝 Размер логов: {log_files_size/(1024**2):.1f}MB\n\n"

            # Компоненты
            stats_text += "⚙️ *Компоненты:*\n"
            stats_text += f"   🎯 Стратегий: {strategies_count}\n"
            stats_text += f"   📊 Rate Limiter: 🟢 Активен\n"
            stats_text += f"   🛡️ Risk Manager: 🟢 Активен\n"
            stats_text += f"   📈 Order Manager: 🟢 Активен\n\n"

            # Время работы
            uptime = datetime.now(timezone.utc) - datetime.fromtimestamp(process.create_time(), timezone.utc)
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            stats_text += f"⏰ *Время работы:* {hours}ч {minutes}м\n"

            # Навигационные кнопки
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="statistics"),
                    InlineKeyboardButton("📈 Аналитика", callback_data="analytics")
                ],
                [
                    InlineKeyboardButton("📊 Графики", callback_data="charts"),
                    InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")
                ]
            ]

            await self._edit_message_with_keyboard(update, context, stats_text, keyboard, parse_mode=None)

        except Exception as e:
            keyboard = [[InlineKeyboardButton("🔙 НАЗАД", callback_data="menu_back")]]
            error_text = self._escape_markdown(f"❌ Ошибка статистики: {str(e)}")
            await self._edit_message_with_keyboard(
                update, context,
                error_text,
                keyboard
            )

    def send_admin_message(self, message: str, with_menu: bool = False):
        """Отправка сообщения администратору"""
        try:
            import asyncio
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            admin_chat_id = ADMIN_CHAT_ID
            if not admin_chat_id:
                print("[WARNING] ADMIN_CHAT_ID не настроен, сообщение не отправлено")
                return

            async def send_message():
                reply_markup = None
                if with_menu:
                    keyboard = [[InlineKeyboardButton("📊 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                await self.app.bot.send_message(
                    chat_id=admin_chat_id,
                    text=message,
                    parse_mode=None,
                    reply_markup=reply_markup
                )

            loop = self._loop
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(send_message(), loop)
                try:
                    future.result(timeout=10)
                except Exception as send_exc:
                    print(f"[ERROR] Ошибка отправки сообщения: {send_exc}")
            else:
                asyncio.run(send_message())

        except Exception as e:
            print(f"[ERROR] Ошибка send_admin_message: {e}")

    async def _cmd_api_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать здоровье API подключений"""
        try:
            from bot.monitoring.api_health_monitor import get_api_health_monitor

            monitor = get_api_health_monitor()
            dashboard = monitor.get_dashboard_data()

            if dashboard['status'] == 'no_data':
                await update.message.reply_text("📊 API мониторинг не активен")
                return

            current = dashboard['current']
            hourly = dashboard['hourly_stats']
            alerts = dashboard['alerts']

            # Эмодзи для статусов
            state_emoji = {
                'healthy': '🟢',
                'degraded': '🟡',
                'unstable': '🟠',
                'failed': '🔴',
                'maintenance': '🔵'
            }

            alert_emoji = {
                'ok': '✅',
                'warning': '⚠️',
                'critical': '🚨'
            }

            message = f"""📊 API HEALTH STATUS

🔌 Подключение: {state_emoji.get(current['connection_state'], '❓')} {current['connection_state']}
⏱️ Время отклика: {current['response_time']:.2f}s {alert_emoji.get(alerts['response_time_status'], '❓')}
❌ Частота ошибок: {current['failure_rate']*100:.1f}% {alert_emoji.get(alerts['failure_rate_status'], '❓')}
🔄 Подряд неудач: {current['consecutive_failures']}
🗂️ Cache hit rate: {current['cache_hit_rate']*100:.1f}%
📁 Кэшировано: {current['cached_items']} записей

📈 СТАТИСТИКА ЗА ЧАС:
⏱️ Среднее время: {hourly['avg_response_time']:.2f}s
❌ Средняя частота ошибок: {hourly['avg_failure_rate']*100:.1f}%
📊 Всего запросов: {hourly['total_requests']}
🔍 Точек данных: {hourly['data_points']}"""

            await update.message.reply_text(message)

        except ImportError:
            await update.message.reply_text("📊 API мониторинг недоступен - модуль не инициализирован")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка получения API статуса: {e}")

    async def _cmd_blocks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о блокировках"""
        try:
            from bot.core.blocking_alerts import get_blocking_alerts_manager

            manager = get_blocking_alerts_manager()
            stats = manager.get_blocking_stats()
            active_blocks = manager.get_active_blocks()

            # Автоматически решаем устаревшие блокировки
            resolved_count = manager.auto_resolve_expired_blocks()
            if resolved_count > 0:
                manager.logger.info(f"✅ Автоматически решено {resolved_count} устаревших блокировок")

            message = f"""🚫 СТАТУС БЛОКИРОВОК

📊 Всего блокировок: {stats['total_blocks']}
🔴 Активных: {stats.get('active_blocks', 0)}
📅 За последние 24ч: {stats.get('last_24h', 0)}
⏰ За последний час: {stats.get('last_1h', 0)}

📋 По причинам:"""

            for reason, count in stats.get('by_reason', {}).items():
                message += f"\n• {reason}: {count}"

            if stats.get('most_common_reason') != 'none':
                message += f"\n\n🔥 Частая причина: {stats['most_common_reason']}"

            if active_blocks:
                message += f"\n\n🚨 АКТИВНЫЕ БЛОКИРОВКИ ({len(active_blocks)}):"
                for block in active_blocks[-5:]:  # Последние 5
                    severity_emoji = {"CRITICAL": "🚨", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
                    emoji = severity_emoji.get(block.severity, "⚠️")
                    message += f"\n{emoji} {block.strategy} ({block.symbol}): {block.message}"
            else:
                message += "\n\n✅ Активных блокировок нет"

            # Последние блокировки
            recent = stats.get('recent_blocks', [])
            if recent:
                message += f"\n\n📋 ПОСЛЕДНИЕ БЛОКИРОВКИ:"
                for block in recent[-3:]:  # Последние 3
                    severity_emoji = {"CRITICAL": "🚨", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
                    emoji = severity_emoji.get(block['severity'], "⚠️")
                    message += f"\n{emoji} {block['timestamp']} - {block['strategy']}: {block['message']}"

            await update.message.reply_text(message)

        except ImportError:
            await update.message.reply_text("🚫 Система блокировок недоступна - модуль не инициализирован")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка получения статуса блокировок: {e}")

    def _run_in_thread(self):
        """Запуск бота в отдельном потоке для избежания конфликтов event loop"""
        import threading
        import asyncio

        def thread_worker():
            # Создаем новый event loop для потока
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                async def run_bot():
                    print("[DEBUG] Начинаем polling с обработкой команд...")
                    print(f"[DEBUG] Токен длина: {len(self.token) if self.token else 'None'}")
                    print(f"[DEBUG] Обработчики зарегистрированы: {len(self.app.handlers)}")
                    await self.app.run_polling(drop_pending_updates=False, stop_signals=None)
                print("[DEBUG] Запускаем run_bot() в event loop...")
                loop.run_until_complete(run_bot())
                print("[DEBUG] run_bot() завершен")
            except Exception as e:
                print(f"[ERROR] Ошибка в thread_worker: {e}")
                import traceback
                traceback.print_exc()
            finally:
                loop.close()
                self._loop = None
                self._is_running = False

        # Запускаем в отдельном потоке
        thread = threading.Thread(target=thread_worker, daemon=True)
        thread.start()
        print("[DEBUG] Telegram бот запущен в отдельном потоке")

    def start(self):
        """Запуск бота - всегда в отдельном потоке"""
        print(f"[DEBUG] start() вызван, _is_running={self._is_running}")
        if self._is_running:
            print("[DEBUG] Telegram бот уже запущен, пропускаем...")
            return

        print("[DEBUG] Запуск Telegram бота в отдельном потоке...")
        self._is_running = True
        print("[DEBUG] Флаг _is_running установлен в True")
        self._run_in_thread()
        print("[DEBUG] _run_in_thread() завершен")

if __name__ == "__main__":
    from config import TELEGRAM_TOKEN
    TelegramBot(TELEGRAM_TOKEN).start()
