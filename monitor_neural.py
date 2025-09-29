#!/usr/bin/env python3
"""
Скрипт мониторинга нейромодуля в реальном времени
Использование: python monitor_neural.py
"""

import sys
import os
import time
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '.')

def check_neural_files():
    """Проверка файлов нейромодуля"""
    files = {
        'config': 'bot/strategy/active_strategies.txt',
        'state': 'data/neural_state.json',
        'bets': 'data/neural_bets.json',
        'logs': 'full_system.log',
        'main_log': 'trading_bot.log'  # Альтернативный лог файл
    }

    status = {}
    for name, path in files.items():
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
            status[name] = {
                'exists': True,
                'modified': datetime.fromtimestamp(mtime).strftime('%H:%M:%S'),
                'size': size
            }
        else:
            status[name] = {'exists': False}

    return status

def check_neural_logs():
    """Проверка логов нейромодуля"""
    # Проверяем оба возможных лог файла
    log_files = ['full_system.log', 'trading_bot.log']

    for log_file in log_files:
        try:
            if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
                with open(log_file, 'r') as f:
                    lines = f.readlines()

                neural_lines = [line for line in lines[-100:] if '🧠' in line or 'neural' in line.lower()]
                if neural_lines:
                    return neural_lines[-5:]
        except:
            continue

    return []

def check_neural_integration():
    """Проверка интеграции нейромодуля"""
    try:
        from bot.ai.neural_integration import NeuralIntegration
        neural = NeuralIntegration()
        neural.reload_active_strategies()

        stats = neural.get_neural_statistics()
        return {
            'loaded': True,
            'strategies': len(neural.strategy_mapping),
            'active_bets': len(neural.active_bets),
            'completed_trades': len(neural.completed_trades),
            'neural_trader_status': stats.get('neural_trader', {}).get('total_bets', 0)
        }
    except Exception as e:
        return {'loaded': False, 'error': str(e)}

def print_status():
    """Вывод статуса нейромодуля"""
    print("\n" + "="*60)
    print(f"🧠 МОНИТОРИНГ НЕЙРОМОДУЛЯ - {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)

    # Проверка файлов
    files = check_neural_files()
    print("\n📁 ФАЙЛЫ:")
    for name, info in files.items():
        if info['exists']:
            print(f"   ✅ {name}: изменен {info['modified']}, размер {info['size']} байт")
        else:
            print(f"   ❌ {name}: НЕ НАЙДЕН")

    # Проверка интеграции
    integration = check_neural_integration()
    print("\n🔧 ИНТЕГРАЦИЯ:")
    if integration['loaded']:
        print(f"   ✅ Модуль загружен")
        print(f"   📊 Стратегий: {integration['strategies']}")
        print(f"   💰 Активных ставок: {integration['active_bets']}")
        print(f"   📈 Завершенных сделок: {integration['completed_trades']}")
        print(f"   🎯 Всего нейронных ставок: {integration['neural_trader_status']}")
    else:
        print(f"   ❌ Ошибка загрузки: {integration.get('error', 'Неизвестная ошибка')}")

    # Проверка логов
    logs = check_neural_logs()
    print("\n📋 ПОСЛЕДНИЕ ЛОГИ:")
    if logs:
        for log in logs:
            print(f"   📝 {log.strip()}")
    else:
        print("   ⚠️ Нет записей о нейромодуле в логах")

    # Рекомендации
    print("\n💡 СПОСОБЫ ПРОВЕРКИ:")
    print("   1. Запустите систему и посмотрите логи: grep '🧠' full_system.log")
    print("   2. В Telegram боте нажмите: 🤖 Нейронка")
    print("   3. Проверьте метрики: curl localhost:8000/metrics | grep neural")
    print("   4. Мониторьте файл состояния: watch -n 5 'cat data/neural_state.json'")

def main():
    """Основная функция мониторинга"""
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        print("🔄 Режим мониторинга (Ctrl+C для выхода)")
        try:
            while True:
                print_status()
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n👋 Мониторинг остановлен")
    else:
        print_status()
        print("\n💡 Для непрерывного мониторинга используйте: python monitor_neural.py --watch")

if __name__ == "__main__":
    main()