#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.services.telegram_bot import TelegramBot
from config import TELEGRAM_TOKEN

def test_telegram_bot():
    """Тестируем работу Telegram бота"""
    
    print("Тестируем Telegram бота...")
    
    try:
        # Создаем экземпляр бота
        bot = TelegramBot(TELEGRAM_TOKEN)
        print(f"Telegram бот создан с токеном: {TELEGRAM_TOKEN[:10]}...")
        
        # Проверяем, что бот может подключиться к API
        print("Проверяем подключение к Telegram API...")
        
        # Получаем информацию о боте
        import asyncio
        from telegram import Bot
        
        async def test_connection():
            try:
                telegram_bot = Bot(token=TELEGRAM_TOKEN)
                me = await telegram_bot.get_me()
                print(f"✅ Бот подключен: @{me.username}")
                print(f"   ID: {me.id}")
                print(f"   Имя: {me.first_name}")
                return True
            except Exception as e:
                print(f"❌ Ошибка подключения к Telegram API: {e}")
                return False
        
        # Запускаем тест
        result = asyncio.run(test_connection())
        
        if result:
            print("✅ Telegram бот работает корректно!")
        else:
            print("❌ Проблемы с Telegram ботом")
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании Telegram бота: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_telegram_bot() 