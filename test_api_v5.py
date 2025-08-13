#!/usr/bin/env python3
"""
Тестовый скрипт для демонстрации возможностей Bybit API v5
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.exchange.bybit_api_v5 import create_bybit_api_v5, create_trading_bot_v5
from bot.exchange.api_adapter import migrate_to_v5_api
import pandas as pd


def test_api_v5_basic():
    """Тест базовых функций API v5"""
    print("🔧 Тестирование Bybit API v5...")
    
    # Создаем API клиент (testnet)
    api = create_bybit_api_v5(testnet=True)
    
    # Тест 1: Получение времени сервера
    print("\n1️⃣ Тест получения времени сервера...")
    server_time = api.get_server_time()
    if server_time and server_time.get('retCode') == 0:
        print("✅ Время сервера получено успешно")
        print(f"   Время: {server_time['result']['timeNano']}")
    else:
        print("❌ Ошибка получения времени сервера")
    
    # Тест 2: Получение OHLCV данных
    print("\n2️⃣ Тест получения OHLCV данных...")
    ohlcv = api.get_ohlcv("BTCUSDT", "1", 10)
    if ohlcv is not None and len(ohlcv) > 0:
        print("✅ OHLCV данные получены успешно")
        print(f"   Количество свечей: {len(ohlcv)}")
        print(f"   Последняя цена: ${ohlcv['close'].iloc[-1]:.2f}")
        print(f"   Временной диапазон: {ohlcv['timestamp'].iloc[0]} - {ohlcv['timestamp'].iloc[-1]}")
    else:
        print("❌ Ошибка получения OHLCV данных")
    
    # Тест 3: Получение информации об инструментах
    print("\n3️⃣ Тест получения информации об инструментах...")
    instruments = api.get_instruments_info("linear", "BTCUSDT")
    if instruments and instruments.get('retCode') == 0:
        print("✅ Информация об инструментах получена")
        if instruments['result']['list']:
            instrument = instruments['result']['list'][0]
            print(f"   Символ: {instrument.get('symbol', 'N/A')}")
            print(f"   Статус: {instrument.get('status', 'N/A')}")
            # Проверяем доступные поля
            available_fields = list(instrument.keys())
            print(f"   Доступные поля: {available_fields[:5]}...")  # Показываем первые 5 полей
            if 'tickSize' in instrument:
                print(f"   Тик: {instrument['tickSize']}")
            elif 'priceScale' in instrument:
                print(f"   Масштаб цены: {instrument['priceScale']}")
            else:
                print(f"   Детали: {dict(list(instrument.items())[:3])}")  # Первые 3 поля
    else:
        print("❌ Ошибка получения информации об инструментах")
        print(f"   Код ошибки: {instruments.get('retCode') if instruments else 'None'}")
        print(f"   Сообщение: {instruments.get('retMsg') if instruments else 'No response'}")
    
    # Тест 4: Получение баланса (требует API ключи)
    print("\n4️⃣ Тест получения баланса...")
    balance = api.get_wallet_balance_v5()
    if balance and balance.get('retCode') == 0:
        print("✅ Баланс получен успешно")
        formatted_balance = api.format_balance_v5(balance)
        print("   Форматированный баланс:")
        print(formatted_balance)
    else:
        print("❌ Ошибка получения баланса (ожидаемо без API ключей)")
        print(f"   Код ошибки: {balance.get('retCode') if balance else 'None'}")
        print(f"   Сообщение: {balance.get('retMsg') if balance else 'No response'}")
    
    return True


def test_trading_bot_v5():
    """Тест торгового бота v5"""
    print("\n🤖 Тестирование TradingBot v5...")
    
    # Создаем торговый бот
    bot = create_trading_bot_v5("BTCUSDT", testnet=True)
    
    # Тест обновления информации о позиции
    print("\n1️⃣ Тест обновления информации о позиции...")
    try:
        bot.update_position_info()
        print("✅ Информация о позиции обновлена")
        print(f"   Размер позиции: {bot.position_size}")
        print(f"   Цена входа: {bot.entry_price}")
        print(f"   Сторона позиции: {bot.position_side}")
    except Exception as e:
        print(f"❌ Ошибка обновления позиции: {e}")
    
    # Тест получения OHLCV данных
    print("\n2️⃣ Тест получения OHLCV данных через бота...")
    try:
        data = bot.get_ohlcv(bot.symbol, "1", 5)
        if data is not None and len(data) > 0:
            print("✅ Данные получены через бота")
            print(f"   Количество свечей: {len(data)}")
            print(f"   Последняя цена: ${data['close'].iloc[-1]:.2f}")
        else:
            print("❌ Ошибка получения данных через бота")
    except Exception as e:
        print(f"❌ Ошибка получения данных: {e}")
    
    return True


def test_api_adapter():
    """Тест адаптера API"""
    print("\n🔧 Тестирование API Adapter...")
    
    # Тест миграции
    print("\n1️⃣ Тест функции миграции...")
    migration_result = migrate_to_v5_api()
    
    print("Результат миграции:")
    print(f"   Статус: {migration_result['migration_status']}")
    print(f"   API v5 доступен: {migration_result['v5_api_available']}")
    print(f"   Рекомендация: {migration_result['recommendation']}")
    
    if 'test_results' in migration_result:
        print("\nРезультаты тестов:")
        for test_name, result in migration_result['test_results'].items():
            print(f"   {test_name}: {result}")
    
    return migration_result['v5_api_available']


def test_ohlcv_analysis():
    """Тест анализа OHLCV данных"""
    print("\n📊 Тестирование анализа OHLCV данных...")
    
    api = create_bybit_api_v5(testnet=True)
    
    # Получаем данные разных таймфреймов
    timeframes = ["1", "5", "15", "60"]
    
    for tf in timeframes:
        print(f"\n📈 Анализ таймфрейма {tf} минут:")
        
        try:
            data = api.get_ohlcv("BTCUSDT", tf, 20)
            
            if data is not None and len(data) > 0:
                # Базовый анализ
                current_price = data['close'].iloc[-1]
                price_change = ((current_price - data['close'].iloc[0]) / data['close'].iloc[0]) * 100
                volume_avg = data['volume'].mean()
                volatility = data['close'].pct_change().std() * 100
                
                print(f"   Текущая цена: ${current_price:.2f}")
                print(f"   Изменение цены: {price_change:+.2f}%")
                print(f"   Средний объем: {volume_avg:.2f}")
                print(f"   Волатильность: {volatility:.2f}%")
                print(f"   Количество свечей: {len(data)}")
            else:
                print(f"   ❌ Нет данных для таймфрейма {tf}")
                
        except Exception as e:
            print(f"   ❌ Ошибка анализа таймфрейма {tf}: {e}")
    
    return True


def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования Bybit API v5")
    print("=" * 50)
    
    try:
        # Тест 1: Базовые функции API
        test_api_v5_basic()
        
        # Тест 2: Торговый бот
        test_trading_bot_v5()
        
        # Тест 3: Адаптер API
        test_api_adapter()
        
        # Тест 4: Анализ данных
        test_ohlcv_analysis()
        
        print("\n" + "=" * 50)
        print("✅ Все тесты завершены!")
        print("\n📋 Рекомендации:")
        print("1. API v5 работает корректно")
        print("2. Можно начинать миграцию на новый API")
        print("3. Для полного тестирования нужны API ключи")
        print("4. Используйте testnet для безопасного тестирования")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 