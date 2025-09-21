#!/usr/bin/env python3
"""
🚨 ЭКСТРЕННОЕ ИСПРАВЛЕНИЕ КОНФЛИКТА ПОЗИЦИЙ

Проблема: OrderManager блокирует все ордера из-за внешней Sell позиции
Решение: Временно отключить строгую проверку конфликтов

Использование:
    python fix_position_conflict.py
"""

import os
import shutil
from datetime import datetime

def fix_order_manager():
    """Исправление OrderManager для разрешения торговли"""

    order_manager_file = "bot/core/order_manager.py"
    backup_file = f"{order_manager_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print(f"🔧 Исправление {order_manager_file}...")

    # Создаем бэкап
    shutil.copy2(order_manager_file, backup_file)
    print(f"💾 Бэкап создан: {backup_file}")

    # Читаем файл
    with open(order_manager_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Заменяем строгую проверку на предупреждение
    old_code = '''if not request.reduce_only and current_side != request.side:
                    return False, f"Конфликт направлений: текущая позиция {current_side}, запрос {request.side}"'''

    new_code = '''if not request.reduce_only and current_side != request.side:
                    # ⚠️ ВРЕМЕННОЕ ИСПРАВЛЕНИЕ: Разрешаем хеджирование внешних позиций
                    self.logger.warning(f"⚠️ Внешняя позиция {current_side}, новый ордер {request.side} - разрешаем хеджирование")
                    # return False, f"Конфликт направлений: текущая позиция {current_side}, запрос {request.side}"'''

    if old_code in content:
        content = content.replace(old_code, new_code)

        # Записываем исправленный файл
        with open(order_manager_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print("✅ OrderManager исправлен!")
        print("🎯 Теперь система будет исполнять ордера несмотря на внешние позиции")
        return True
    else:
        print("❌ Код для замены не найден. Возможно файл уже изменен.")
        return False

def add_config_options():
    """Добавление опций в конфигурацию"""

    config_file = "config.py"

    config_addition = '''
# ============================================================================
# ИСПРАВЛЕНИЕ КОНФЛИКТОВ ПОЗИЦИЙ
# ============================================================================

# Разрешить хеджирование внешних позиций
ALLOW_EXTERNAL_HEDGING = True

# Игнорировать внешние позиции при проверке конфликтов
IGNORE_EXTERNAL_POSITIONS = True

# Логировать предупреждения вместо блокировки ордеров
WARN_ON_POSITION_CONFLICTS = True
'''

    try:
        with open(config_file, 'a', encoding='utf-8') as f:
            f.write(config_addition)
        print("✅ Опции добавлены в config.py")
        return True
    except Exception as e:
        print(f"❌ Ошибка добавления в config: {e}")
        return False

def create_restart_script():
    """Создание скрипта для перезапуска системы"""

    restart_script = '''#!/bin/bash
# Скрипт перезапуска после исправления

echo "🔄 Перезапуск системы после исправления конфликтов позиций..."

# Останавливаем текущий процесс
pkill -f "python main.py"
sleep 3

# Очищаем lock файлы
rm -f .locks/trading_bot_main.lock

# Запускаем заново
echo "🚀 Запуск исправленной системы..."
nohup python main.py > restart.log 2>&1 &

echo "✅ Система перезапущена!"
echo "📝 Логи: tail -f restart.log"
'''

    with open("restart_after_fix.sh", 'w') as f:
        f.write(restart_script)

    os.chmod("restart_after_fix.sh", 0o755)
    print("✅ Скрипт перезапуска создан: restart_after_fix.sh")

def main():
    """Главная функция исправления"""

    print("="*60)
    print("🚨 ЭКСТРЕННОЕ ИСПРАВЛЕНИЕ КОНФЛИКТА ПОЗИЦИЙ")
    print("="*60)
    print()
    print("🔍 Диагностика:")
    print("• Система генерирует сигналы (85,965 записей)")
    print("• OrderManager блокирует ордера из-за внешней Sell позиции")
    print("• Результат: логи есть, торговли нет")
    print()
    print("🛠️ Исправление:")
    print("• Отключить строгую проверку конфликтов")
    print("• Разрешить хеджирование внешних позиций")
    print("• Добавить предупреждения вместо блокировки")
    print()

    # Подтверждение
    response = input("Продолжить исправление? (y/N): ").lower()
    if response != 'y':
        print("❌ Отменено пользователем")
        return

    success = True

    # 1. Исправляем OrderManager
    if not fix_order_manager():
        success = False

    # 2. Добавляем опции в конфиг
    if not add_config_options():
        success = False

    # 3. Создаем скрипт перезапуска
    create_restart_script()

    print()
    print("="*60)
    if success:
        print("✅ ИСПРАВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО!")
        print()
        print("🔄 Следующие шаги:")
        print("1. bash restart_after_fix.sh  # Перезапустить систему")
        print("2. tail -f restart.log        # Мониторить логи")
        print("3. Проверить исполнение ордеров через 2-3 минуты")
        print()
        print("🎯 После перезапуска система должна начать реально торговать!")
    else:
        print("❌ ИСПРАВЛЕНИЕ ЧАСТИЧНО ЗАВЕРШЕНО")
        print("Проверьте ошибки выше и попробуйте вручную")
    print("="*60)

if __name__ == "__main__":
    main()