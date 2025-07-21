import threading
import logging
from bot.core import run_trading
from bot.services.telegram_bot import TelegramBot
from bot.config_manager import config

logging.basicConfig(
    filename='main.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def start_trading():
    logging.info('Торговый поток стартовал')
    try:
        run_trading()
    except Exception as e:
        logging.error(f'Торговый поток завершился с ошибкой: {e}')
    finally:
        logging.info('Торговый поток завершён')

def start_telegram():
    logging.info('Поток Telegram-бота стартовал')
    try:
        tg_bot = TelegramBot(config.TELEGRAM_TOKEN)
        tg_bot.start()
    except Exception as e:
        logging.error(f'Поток Telegram-бота завершился с ошибкой: {e}')
    finally:
        logging.info('Поток Telegram-бота завершён')

if __name__ == "__main__":
    threads = []

    trading_thread = threading.Thread(target=start_trading, daemon=True)
    threads.append(trading_thread)
    trading_thread.start()

    if getattr(config, 'TELEGRAM_ENABLED', False):
        telegram_thread = threading.Thread(target=start_telegram, daemon=True)
        threads.append(telegram_thread)
        telegram_thread.start()

    logging.info('Главный процесс: все потоки запущены')
    for t in threads:
        t.join()
    logging.info('Главный процесс завершён: все потоки остановлены')
        