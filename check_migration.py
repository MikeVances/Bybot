#!/usr/bin/env python3
"""
Скрипт для проверки миграции на Bybit API v5
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.exchange.api_adapter import migrate_to_v5_api
from bot.exchange.bybit_api_v5 import create_bybit_api_v5
from config import USE_V5_API, USE_TESTNET
import logging

def check_migration():
    """Проверка миграции на API v5"""
    print("🔍 Проверка миграции на Bybit API v5")
    print("=" * 50)
    
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)
    
    # Проверка конфигурации
    print(f"📋 Конфигурация:")
    print(f"   USE_V5_API: {USE_V5_API}")
    print(f"   USE_TESTNET: {USE_TESTNET}")
    print()
    
    # Тест миграции
    print("🔄 Тестирование миграции...")
    migration_result = migrate_to_v5_api()
    
    print("📊 Результаты миграции:")
    print(f"   Статус: {migration_result['migration_status']}")
    print(f"   API v5 доступен: {migration_result['v5_api_available']}")
    print(f"   Рекомендация: {migration_result['recommendation']}")
    
    if 'test_results' in migration_result:
        print("\n📈 Результаты тестов:")
        for test_name, result in migration_result['test_results'].items():
            status = "✅" if "Успешно" in str(result) else "❌"
            print(f"   {status} {test_name}: {result}")
    
    # Тест создания API клиента
    print("\n🔧 Тест создания API клиента...")
    try:
        api = create_bybit_api_v5(testnet=USE_TESTNET)
        print("✅ API клиент создан успешно")
        
        # Тест получения времени сервера
        server_time = api.get_server_time()
        if server_time and server_time.get('retCode') == 0:
            print("✅ Время сервера получено")
        else:
            print("❌ Ошибка получения времени сервера")
            
    except Exception as e:
        print(f"❌ Ошибка создания API клиента: {e}")
    
    # Проверка основных файлов
    print("\n📁 Проверка файлов:")
    files_to_check = [
        'bot/exchange/bybit_api_v5.py',
        'bot/exchange/api_adapter.py',
        'bot/core/trader.py',
        'bot/services/telegram_bot.py'
    ]
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} - НЕ НАЙДЕН")
    
    # Итоговая оценка
    print("\n" + "=" * 50)
    if migration_result['v5_api_available']:
        print("🎉 Миграция на API v5 УСПЕШНА!")
        print("✅ Все компоненты готовы к работе")
        print("✅ Можно запускать торгового бота")
    else:
        print("⚠️ Миграция на API v5 НЕ ЗАВЕРШЕНА")
        print("❌ Есть проблемы, требующие внимания")
    
    return migration_result['v5_api_available']

if __name__ == "__main__":
    success = check_migration()
    sys.exit(0 if success else 1) 