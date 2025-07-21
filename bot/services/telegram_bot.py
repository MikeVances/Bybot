# bot/services/telegram_bot.py
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from bot.exchange.bybit_api import TradingBot
from bot.cli import load_active_strategy, save_active_strategy
from config import TELEGRAM_TOKEN
import pandas as pd
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler
import glob

# Отключаем подробное логирование Telegram (чтобы ключ не попадал в логи)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.bot").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

print("[DEBUG] telegram_bot.py загружен")

class TelegramBot:
    def __init__(self, token):
        print("[DEBUG] TelegramBot __init__")
        self.trading_bot = TradingBot(symbol="BTCUSDT")
        self.app = ApplicationBuilder().token(token).build()
        self._register_handlers()
        
    # def _is_admin(self, update: Update):
    #     return update.effective_user.id == ADMIN_USER_ID

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self._start))
        self.app.add_handler(CommandHandler("menu", self._menu))
        self.app.add_handler(CommandHandler("balance", self._balance))
        self.app.add_handler(CommandHandler("position", self._position))
        self.app.add_handler(CommandHandler("strategies", self._strategies))
        self.app.add_handler(CommandHandler("trades", self._trades))
        self.app.add_handler(CommandHandler("logs", self._logs))
        self.app.add_handler(CallbackQueryHandler(self._on_menu_button))
        self.app.add_handler(CallbackQueryHandler(self._on_strategy_toggle))

    def _get_strategy_list(self):
        files = glob.glob("bot/strategy/strategy_*.py")
        return [os.path.splitext(os.path.basename(f))[0] for f in files]

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /start")
        # if not self._is_admin(update):
        #     return
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Торговый бот активирован!\n"
                 "Доступные команды:\n"
                 "/balance - Проверить баланс\n"
                 "/position - Показать позицию\n"
                 "/strategy - Текущая стратегия\n"
                 "/set_strategy <имя> - Сменить стратегию\n"
                 "/get_strategy - Показать стратегию\n"
                 "/trades - Последние сделки"
        )

    async def _balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /balance")
        # if not self._is_admin(update):
        #     return
        balance = self.trading_bot.get_wallet_balance_v5()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.trading_bot.format_balance_v5(balance)
        )

    async def _position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /position")
        # if not self._is_admin(update):
        #     return
        self.trading_bot.update_position_info()
        msg = f"Позиция: {self.trading_bot.position_size} {self.trading_bot.position_side} по {self.trading_bot.entry_price}"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)

    async def _strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /strategy")
        # if not self._is_admin(update):
        #     return
        strategy = load_active_strategy()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Текущая стратегия: {strategy}")

    async def _strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        strategy = self._get_strategy_list()
        keyboard = [[InlineKeyboardButton(s, callback_data=f"set_strategy:{s}")]
                    for s in strategy]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите стратегию:",
            reply_markup=reply_markup
        )

    async def _set_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /set_strategy")
        # if not self._is_admin(update):
        #     return
        if not context.args:
            await self._strategy(update, context)
            return
        strategy_name = context.args[0]
        save_active_strategy(strategy_name)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Стратегия установлена: {strategy_name}")

    async def _on_strategy_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not query.data:
            return
        if query.data.startswith("set_strategy:"):
            strategy_name = query.data.split(":", 1)[1]
            save_active_strategy(strategy_name)
            await query.answer()
            await query.edit_message_text(f"Стратегия установлена: {strategy_name}")

    async def _get_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /get_strategy")
        # if not self._is_admin(update):
        #     return
        strategy = load_active_strategy()
        if strategy:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Текущая стратегия: {strategy}")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Стратегия не выбрана.")

    async def _trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[DEBUG] Получена команда /trades")
        # if not self._is_admin(update):
        #     return
        file_path = 'data/trades.csv'
        if not os.path.exists(file_path):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Нет сделок.")
            return
        try:
            df = pd.read_csv(file_path)
        except pd.errors.EmptyDataError:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Нет сделок.")
            return
        if df.empty:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Нет сделок.")
            return
        last_trades = df.tail(5)
        msg = "Последние сделки:\n"
        # Универсальный вывод: если нет нужных столбцов, просто выводим строку
        for _, row in last_trades.iterrows():
            if 'datetime' in row and 'symbol' in row and 'side' in row and 'qty' in row and 'entry_price' in row and 'exit_price' in row and 'pnl' in row:
                msg += f"{row['datetime']} {row['symbol']} {row['side']} {row['qty']} по {row['entry_price']} → {row['exit_price']} PNL: {row['pnl']}\n"
            else:
                msg += str(row.to_dict()) + "\n"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)

    async def _strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список активных стратегий"""
        try:
            with open("bot/strategy/active_strategies.txt") as f:
                strategies = [line.strip() for line in f if line.strip()]
        except Exception:
            strategies = []
        if strategies:
            msg = "Активные стратегии:\n" + "\n".join(strategies)
        else:
            msg = "Нет активных стратегий."
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)

    async def _add_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить стратегию в список активных"""
        if not context.args:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Укажите имя стратегии для добавления.")
            return
        strategy_name = context.args[0]
        try:
            with open("bot/strategy/active_strategies.txt", "a+") as f:
                f.seek(0)
                strategies = [line.strip() for line in f if line.strip()]
                if strategy_name in strategies:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Стратегия {strategy_name} уже в списке.")
                    return
                f.write(f"{strategy_name}\n")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Стратегия {strategy_name} добавлена.")
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ошибка: {e}")

    async def _remove_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить стратегию из списка активных"""
        if not context.args:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Укажите имя стратегии для удаления.")
            return
        strategy_name = context.args[0]
        try:
            with open("bot/strategy/active_strategies.txt", "r") as f:
                strategies = [line.strip() for line in f if line.strip()]
            if strategy_name not in strategies:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Стратегия {strategy_name} не найдена в списке.")
                return
            strategies.remove(strategy_name)
            with open("bot/strategy/active_strategies.txt", "w") as f:
                for s in strategies:
                    f.write(f"{s}\n")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Стратегия {strategy_name} удалена.")
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ошибка: {e}")

    async def _menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("💰 Баланс", callback_data="menu_balance"),
             InlineKeyboardButton("📈 Позиция", callback_data="menu_position")],
            [InlineKeyboardButton("🧩 Стратегии", callback_data="menu_strategies")],
            [InlineKeyboardButton("📊 Сделки", callback_data="menu_trades")],
            [InlineKeyboardButton("📝 Логи", callback_data="menu_logs")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*Главное меню*\nВыберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _on_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not query.data:
            return
        if query.data == "menu_balance":
            await self._balance(update, context)
        elif query.data == "menu_position":
            await self._position(update, context)
        elif query.data == "menu_strategies":
            await self._strategies(update, context)
        elif query.data == "menu_trades":
            await self._trades(update, context)
        elif query.data == "menu_logs":
            await self._logs(update, context)
        await query.answer()

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

    async def _logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        log_path = "bot.log"
        import os
        if not os.path.exists(log_path):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Лог-файл не найден.")
            return
        with open(log_path, "r") as f:
            lines = f.readlines()[-30:]
        log_text = "".join(lines)
        if len(log_text) > 4000:
            log_text = log_text[-4000:]
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Последние строки лога:\n\n{log_text}")

    def start(self):
        print("[DEBUG] Бот стартует, polling включён")
        self.app.run_polling()

if __name__ == "__main__":
    from config import TELEGRAM_TOKEN
    TelegramBot(TELEGRAM_TOKEN).start()