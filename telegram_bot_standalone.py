#!/usr/bin/env python3
"""
Отдельный Telegram бот для управления торговым ботом
Запускается независимо от основного торгового процесса
"""

import logging
import sys
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('telegram_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Главная функция Telegram бота"""
    logger.info('='*60)
    logger.info('🚀 ЗАПУСК TELEGRAM БОТА')
    logger.info('='*60)
    
    try:
        # Импортируем конфигурацию
        from bot.config_manager import config
        
        # Проверяем настройки
        logger.info(f'🔍 TELEGRAM_ENABLED: {getattr(config, "TELEGRAM_ENABLED", False)}')
        token = getattr(config, "TELEGRAM_TOKEN", "НЕ НАСТРОЕН")
        if token != "НЕ НАСТРОЕН":
            logger.info(f'🔍 TELEGRAM_TOKEN: {token[:4]}...{token[-4:]} (скрыт)')
        else:
            logger.info(f'🔍 TELEGRAM_TOKEN: {token}')
        
        if not getattr(config, 'TELEGRAM_ENABLED', False):
            logger.error('❌ TELEGRAM_ENABLED=False, бот не запускается')
            return
        
        # Импортируем и запускаем Telegram бота
        from bot.services.telegram_bot import TelegramBot
        
        logger.info('📱 Инициализируем Telegram бота...')
        telegram_bot = TelegramBot(token=config.TELEGRAM_TOKEN)
        logger.info('✅ Telegram бот инициализирован')
        
        logger.info('📱 Запускаем Telegram бота...')
        telegram_bot.start()
        
    except KeyboardInterrupt:
        logger.info('❌ Telegram бот остановлен пользователем')
    except Exception as e:
        logger.error(f'💥 Критическая ошибка Telegram бота: {e}', exc_info=True)
    finally:
        logger.info('🏁 Telegram бот завершён')
        logger.info('='*60)

if __name__ == "__main__":
    main() 