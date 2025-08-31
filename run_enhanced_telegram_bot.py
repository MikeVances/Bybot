#!/usr/bin/env python3
# run_enhanced_telegram_bot.py
# 💜 ЗАПУСК ENHANCED TELEGRAM БОТА
# Демонстрация новых UX возможностей

import sys
import logging
import asyncio
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from bot.services.telegram_bot_enhanced import EnhancedTelegramBot
    from config import TELEGRAM_TOKEN, ADMIN_CHAT_ID
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что все зависимости установлены:")
    print("pip install python-telegram-bot pandas numpy")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('enhanced_telegram_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Отключаем подробное логирование внешних библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def print_startup_banner():
    """Стильный баннер запуска"""
    print("\n" + "="*60)
    print("🚀 ENHANCED TELEGRAM BOT - UX REVOLUTION")
    print("="*60)
    print("💜 Разработано сеньором с фиолетовыми волосами")
    print("🎯 Фокус: современный UX + user-centric design")
    print()
    print("✨ НОВЫЕ ВОЗМОЖНОСТИ:")
    print("   🎨 Modern UX vs Classic interface")
    print("   📊 Smart Dashboard с live-данными")
    print("   🧠 AI-powered insights")
    print("   ⚡ Quick Actions для power users")
    print("   🔔 Smart Notifications с контекстом")
    print("   📱 Адаптивный дизайн")
    print("   🎯 Персонализация интерфейса")
    print("   🧪 A/B тестирование новых фич")
    print()
    print("🔧 ТЕХНОЛОГИИ:")
    print("   • python-telegram-bot (новейшая версия)")
    print("   • Async/await для производительности")
    print("   • Smart routing и callback management")
    print("   • Context-aware notifications")
    print("   • Real-time data updates")
    print()
    
def check_configuration():
    """Проверка конфигурации"""
    print("🔍 Проверка конфигурации...")
    
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не настроен!")
        print("   Добавьте токен в config.py:")
        print("   TELEGRAM_TOKEN = 'your_bot_token_here'")
        return False
    
    if not ADMIN_CHAT_ID:
        print("⚠️  ADMIN_CHAT_ID не настроен")
        print("   Некоторые функции могут работать ограниченно")
        print("   Добавьте в config.py:")
        print("   ADMIN_CHAT_ID = 'your_chat_id_here'")
    
    print("✅ Конфигурация корректна")
    return True

async def test_components():
    """Тестирование компонентов"""
    print("\n🧪 Тестирование компонентов...")
    
    try:
        # Тестируем импорт AI модулей
        from bot.ai import NeuralIntegration
        print("✅ AI модули: OK")
    except Exception as e:
        print(f"⚠️  AI модули: {e}")
    
    try:
        # Тестируем импорт API модулей
        from bot.exchange.bybit_api_v5 import BybitAPI
        print("✅ API модули: OK")
    except Exception as e:
        print(f"⚠️  API модули: {e}")
    
    try:
        # Тестируем UX компоненты
        from bot.services.ux_config import ux_config, UXEmojis
        from bot.services.smart_notifications import NotificationManager
        print("✅ UX компоненты: OK")
    except Exception as e:
        print(f"❌ UX компоненты: {e}")
        return False
    
    print("✅ Все компоненты готовы к работе")
    return True

def show_usage_tips():
    """Показать советы по использованию"""
    print("\n💡 СОВЕТЫ ПО ИСПОЛЬЗОВАНИЮ:")
    print()
    print("📱 ДЛЯ ПОЛЬЗОВАТЕЛЕЙ:")
    print("   /start - Выбор интерфейса (Modern UX или Classic)")
    print("   /ux - Переключиться на Modern UX")
    print("   /classic - Переключиться на Classic")
    print("   /dashboard - Smart Dashboard")
    print("   /quick - Быстрые действия")
    print()
    print("🔧 ДЛЯ РАЗРАБОТЧИКОВ:")
    print("   • Логи сохраняются в enhanced_telegram_bot.log")
    print("   • A/B тестирование: 70% UX, 30% Classic")
    print("   • Smart notifications с rate limiting")
    print("   • Статистика использования в bot.get_usage_stats()")
    print()
    print("🎨 UX ФИШКИ:")
    print("   • Live-обновления каждые 30 секунд")
    print("   • Контекстные уведомления")
    print("   • Адаптивная клавиатура")
    print("   • Персонализация интерфейса")
    print("   • Быстрые действия одним кликом")
    print()

def main():
    """Основная функция запуска"""
    
    print_startup_banner()
    
    # Проверяем конфигурацию
    if not check_configuration():
        return
    
    # Тестируем компоненты
    if not asyncio.run(test_components()):
        print("❌ Критическая ошибка в компонентах")
        return
    
    show_usage_tips()
    
    print("="*60)
    print("🚀 ЗАПУСК ENHANCED TELEGRAM БОТА...")
    print("💜 Press Ctrl+C to stop")
    print("="*60)
    print()
    
    try:
        # Создаём и запускаем бота
        bot = EnhancedTelegramBot(TELEGRAM_TOKEN)
        
        # Показываем стартовую статистику
        stats = bot.get_usage_stats()
        print(f"📊 Стартовая статистика:")
        print(f"   • Пользователей: {stats['total_users']}")
        print(f"   • UX пользователей: {stats['ux_users']}")
        print(f"   • Classic пользователей: {stats['legacy_users']}")
        print()
        
        # Запускаем бота
        bot.start()
        
    except KeyboardInterrupt:
        print("\n💜 Enhanced Bot остановлен пользователем")
        
        # Показываем финальную статистику
        try:
            final_stats = bot.get_usage_stats()
            print(f"\n📊 Финальная статистика:")
            print(f"   • Всего пользователей: {final_stats['total_users']}")
            print(f"   • UX adoption rate: {final_stats['ux_adoption_rate']:.1f}%")
            print(f"   • Сообщений отправлено: {final_stats['messages_sent']}")
        except:
            pass
            
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.exception("Critical error in main")
    
    print("\n👋 До свидания!")

if __name__ == "__main__":
    main()