#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.services.telegram_bot import TelegramBot
from config import TELEGRAM_TOKEN

def test_neural_function():
    """Тестируем функцию нейронки в Telegram боте"""
    
    print("Тестируем функцию нейронки в Telegram боте...")
    
    try:
        # Создаем экземпляр бота
        bot = TelegramBot(TELEGRAM_TOKEN)
        print(f"Telegram бот создан с токеном: {TELEGRAM_TOKEN[:10]}...")
        
        # Тестируем функцию _neural
        print("Тестируем функцию _neural...")
        
        # Создаем мок объекты для тестирования
        class MockUpdate:
            def __init__(self):
                self.effective_chat = MockChat()
                self.callback_query = None
        
        class MockChat:
            def __init__(self):
                self.id = 123456789
        
        class MockContext:
            def __init__(self):
                self.bot = None
        
        # Создаем мок объекты
        mock_update = MockUpdate()
        mock_context = MockContext()
        
        # Импортируем asyncio для тестирования
        import asyncio
        
        async def test_neural():
            try:
                await bot._neural(mock_update, mock_context)
                print("✅ Функция _neural выполнилась без ошибок!")
                return True
            except Exception as e:
                print(f"❌ Ошибка в функции _neural: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # Запускаем тест
        result = asyncio.run(test_neural())
        
        if result:
            print("✅ Функция нейронки работает корректно!")
        else:
            print("❌ Проблемы с функцией нейронки")
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании функции нейронки: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_neural_function() 