#!/usr/bin/env python3
"""
🚨 ИНТЕГРАЦИЯ СИСТЕМЫ ОПОВЕЩЕНИЙ О БЛОКИРОВКАХ

Автоматически интегрирует blocking_alerts во все компоненты системы
"""

import os
import re
import shutil
from datetime import datetime
from typing import List, Tuple


def create_backup(file_path: str) -> str:
    """Создание бэкапа файла"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{file_path}.backup_{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def integrate_risk_manager():
    """Интеграция в RiskManager"""
    file_path = "bot/risk.py"

    print(f"🔧 Интегрируем blocking alerts в {file_path}...")

    backup = create_backup(file_path)
    print(f"💾 Backup: {backup}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Добавляем импорт
    import_addition = """
from bot.core.blocking_alerts import report_order_block, BlockType"""

    if "from bot.core.blocking_alerts" not in content:
        # Находим место для добавления импорта
        import_position = content.find("from dataclasses import dataclass")
        if import_position != -1:
            content = content[:import_position] + import_addition + "\n" + content[import_position:]

    # Интегрируем в check_pre_trade_risk
    replacements = [
        # Emergency stop
        (
            'return False, "Активирован аварийный стоп"',
            '''report_order_block(BlockType.EMERGENCY_STOP.value, "BTCUSDT", strategy_name, "Активирован аварийный стоп")
            return False, "Активирован аварийный стоп"'''
        ),
        # Заблокированная стратегия
        (
            'return False, f"Стратегия {strategy_name} заблокирована"',
            '''report_order_block(BlockType.RISK_LIMIT.value, "BTCUSDT", strategy_name, f"Стратегия {strategy_name} заблокирована")
            return False, f"Стратегия {strategy_name} заблокирована"'''
        ),
        # Лимит дневных сделок
        (
            'return False, f"Превышен лимит дневных сделок ({limits.max_daily_trades})"',
            '''report_order_block(BlockType.RISK_LIMIT.value, "BTCUSDT", strategy_name,
                               f"Превышен лимит дневных сделок ({daily_trades_count}/{limits.max_daily_trades})",
                               {"daily_trades": daily_trades_count, "limit": limits.max_daily_trades})
            return False, f"Превышен лимит дневных сделок ({limits.max_daily_trades})"'''
        ),
        # Лимит дневных потерь
        (
            'return False, f"Превышен лимит дневных потерь (${daily_loss:.2f} >= ${max_daily_loss:.2f})"',
            '''report_order_block(BlockType.RISK_LIMIT.value, "BTCUSDT", strategy_name,
                               f"Превышен лимит дневных потерь (${daily_loss:.2f} >= ${max_daily_loss:.2f})",
                               {"daily_loss": daily_loss, "limit": max_daily_loss, "balance": current_balance})
            return False, f"Превышен лимит дневных потерь (${daily_loss:.2f} >= ${max_daily_loss:.2f})"'''
        ),
    ]

    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"✅ Заменено: {old[:50]}...")

    # Записываем обновленный файл
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ {file_path} обновлен с интеграцией blocking alerts")


def integrate_order_manager():
    """Интеграция в OrderManager"""
    file_path = "bot/core/order_manager.py"

    print(f"🔧 Интегрируем blocking alerts в {file_path}...")

    backup = create_backup(file_path)
    print(f"💾 Backup: {backup}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Добавляем импорт
    import_addition = """
from bot.core.blocking_alerts import report_order_block, report_successful_order, BlockType"""

    if "from bot.core.blocking_alerts" not in content:
        # Находим место для добавления импорта
        import_position = content.find("from bot.core.exceptions import")
        if import_position != -1:
            line_end = content.find('\n', import_position)
            content = content[:line_end] + "\n" + import_addition + content[line_end:]

    # Интегрируем уведомления о блокировках
    replacements = [
        # Emergency stop
        (
            'raise OrderRejectionError("🚨 АВАРИЙНАЯ ОСТАНОВКА: Все ордера заблокированы")',
            '''report_order_block(BlockType.EMERGENCY_STOP.value, symbol, request.strategy_name, "Аварийная остановка активна")
                raise OrderRejectionError("🚨 АВАРИЙНАЯ ОСТАНОВКА: Все ордера заблокированы")'''
        ),
        # Rate limit
        (
            'raise RateLimitError(f"Rate limit для {symbol}: {rate_msg}")',
            '''report_order_block(BlockType.RATE_LIMIT.value, symbol, request.strategy_name, f"Rate limit: {rate_msg}")
                raise RateLimitError(f"Rate limit для {symbol}: {rate_msg}")'''
        ),
        # Дублированный ордер
        (
            'raise OrderRejectionError(f"Дублированный ордер для {symbol}: {dup_msg}")',
            '''report_order_block(BlockType.DUPLICATE_ORDER.value, symbol, request.strategy_name, f"Дублированный ордер: {dup_msg}")
                raise OrderRejectionError(f"Дублированный ордер для {symbol}: {dup_msg}")'''
        ),
        # Конфликт позиций
        (
            'raise PositionConflictError(f"Конфликт позиции для {symbol}: {pos_msg}")',
            '''report_order_block(BlockType.POSITION_CONFLICT.value, symbol, request.strategy_name, f"Конфликт позиции: {pos_msg}")
                raise PositionConflictError(f"Конфликт позиции для {symbol}: {pos_msg}")'''
        ),
    ]

    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"✅ Заменено: {old[:50]}...")

    # Добавляем уведомление об успешном ордере
    success_pattern = r'(self\.logger\.info\(f"✅ Ордер успешно создан для \{symbol\}: \{order_id\}"\))'
    success_replacement = r'''\1

                    # Уведомляем об успешном ордере
                    report_successful_order(symbol, request.strategy_name, order_id)'''

    content = re.sub(success_pattern, success_replacement, content)

    # Записываем обновленный файл
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ {file_path} обновлен с интеграцией blocking alerts")


def integrate_rate_limiter():
    """Интеграция в RateLimiter"""
    file_path = "bot/core/rate_limiter.py"

    print(f"🔧 Интегрируем blocking alerts в {file_path}...")

    backup = create_backup(file_path)
    print(f"💾 Backup: {backup}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Добавляем импорт
    import_addition = """
from bot.core.blocking_alerts import report_order_block, BlockType"""

    if "from bot.core.blocking_alerts" not in content:
        # Находим место для добавления импорта
        import_position = content.find("from bot.core.exceptions import")
        if import_position != -1:
            line_end = content.find('\n', import_position)
            content = content[:line_end] + "\n" + import_addition + content[line_end:]

    # Интегрируем в _activate_emergency_stop
    replacement = (
        'self.logger.critical(\n                f"🚨 EMERGENCY STOP АКТИВИРОВАН: {reason}"\n            )',
        '''self.logger.critical(
                f"🚨 EMERGENCY STOP АКТИВИРОВАН: {reason}"
            )

            # Уведомляем через blocking alerts
            report_order_block(BlockType.EMERGENCY_STOP.value, "GLOBAL", "rate_limiter", reason)'''
    )

    if replacement[0] in content:
        content = content.replace(replacement[0], replacement[1])
        print("✅ Добавлено уведомление в emergency stop")

    # Записываем обновленный файл
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ {file_path} обновлен с интеграцией blocking alerts")


def create_telegram_integration():
    """Создание интеграции с Telegram ботом"""

    integration_code = '''
# Добавить в main.py или в инициализацию Telegram бота

def setup_blocking_alerts_with_telegram():
    """Настройка blocking alerts с интеграцией Telegram"""
    try:
        from bot.services.telegram_bot import telegram_bot
        from bot.core.blocking_alerts import get_blocking_alerts_manager

        # Получаем менеджер блокировок с Telegram ботом
        blocking_manager = get_blocking_alerts_manager(telegram_bot)

        print("✅ Blocking alerts интегрированы с Telegram")
        return blocking_manager

    except Exception as e:
        print(f"❌ Ошибка интеграции blocking alerts с Telegram: {e}")
        # Возвращаем менеджер без Telegram
        from bot.core.blocking_alerts import get_blocking_alerts_manager
        return get_blocking_alerts_manager()

# Вызвать эту функцию при запуске системы
blocking_manager = setup_blocking_alerts_with_telegram()
'''

    with open("telegram_blocking_integration.py", 'w', encoding='utf-8') as f:
        f.write(integration_code)

    print("✅ Создан файл telegram_blocking_integration.py")


def create_startup_diagnostics():
    """Создание startup диагностики"""

    diagnostic_code = '''#!/usr/bin/env python3
"""
🚨 STARTUP ДИАГНОСТИКА СИСТЕМЫ БЛОКИРОВОК

Проверяет все потенциальные блокировки при запуске
"""

def startup_blocking_diagnostics():
    """Диагностика блокировок при запуске"""
    print("🔍 Проверка потенциальных блокировок при запуске...")

    issues = []
    warnings = []

    try:
        # 1. Проверка emergency stops
        from bot.core.rate_limiter import get_rate_limiter
        rate_limiter = get_rate_limiter()

        global_status = rate_limiter.get_global_status()
        if global_status.get('emergency_stop_active'):
            issues.append(f"🚨 Rate Limiter Emergency Stop: {global_status.get('emergency_reason')}")

        # 2. Проверка risk manager
        from bot.risk import RiskManager
        risk_manager = RiskManager()

        if risk_manager.emergency_stop:
            issues.append("🚨 Risk Manager Emergency Stop активен")

        if risk_manager.blocked_strategies:
            warnings.append(f"⚠️ Заблокированные стратегии: {list(risk_manager.blocked_strategies)}")

        # 3. Проверка позиций
        from bot.exchange.bybit_api_v5 import BybitAPIV5
        from config import get_api_credentials

        api_key, api_secret = get_api_credentials()
        api = BybitAPIV5(api_key, api_secret, testnet=True)

        positions = api.get_positions('BTCUSDT')
        if positions.get('retCode') == 0:
            active_positions = [p for p in positions.get('result', {}).get('list', [])
                             if float(p.get('size', 0)) != 0]

            if active_positions:
                warnings.append(f"⚠️ Обнаружены внешние позиции: {len(active_positions)}")
                for pos in active_positions:
                    warnings.append(f"   - {pos.get('symbol')} {pos.get('side')} {pos.get('size')}")

        # 4. Проверка баланса
        balance = api.get_wallet_balance_v5()
        if balance.get('retCode') == 0:
            # Можно добавить проверки минимального баланса
            pass

        # 5. Вывод результатов
        if issues:
            print("🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ:")
            for issue in issues:
                print(f"   {issue}")

        if warnings:
            print("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
            for warning in warnings:
                print(f"   {warning}")

        if not issues and not warnings:
            print("✅ Блокировок не обнаружено - система готова к торговле")

        return len(issues) == 0

    except Exception as e:
        print(f"❌ Ошибка диагностики: {e}")
        return False

if __name__ == "__main__":
    startup_blocking_diagnostics()
'''

    with open("startup_diagnostics.py", 'w', encoding='utf-8') as f:
        f.write(diagnostic_code)

    print("✅ Создан файл startup_diagnostics.py")


def main():
    """Главная функция интеграции"""
    print("="*60)
    print("🚨 ИНТЕГРАЦИЯ СИСТЕМЫ ОПОВЕЩЕНИЙ О БЛОКИРОВКАХ")
    print("="*60)
    print()

    print("📋 План интеграции:")
    print("1. RiskManager - все критические проверки")
    print("2. OrderManager - блокировки ордеров")
    print("3. RateLimiter - emergency stops")
    print("4. Telegram интеграция")
    print("5. Startup диагностика")
    print()

    response = input("Продолжить интеграцию? (y/N): ").lower()
    if response != 'y':
        print("❌ Отменено пользователем")
        return

    try:
        # 1. Интегрируем RiskManager
        integrate_risk_manager()

        # 2. Интегрируем OrderManager
        integrate_order_manager()

        # 3. Интегрируем RateLimiter
        integrate_rate_limiter()

        # 4. Создаем Telegram интеграцию
        create_telegram_integration()

        # 5. Создаем startup диагностику
        create_startup_diagnostics()

        print()
        print("="*60)
        print("✅ ИНТЕГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("="*60)
        print()
        print("🔄 Следующие шаги:")
        print("1. Перезапустить систему")
        print("2. Проверить что уведомления работают")
        print("3. Запустить startup_diagnostics.py для проверки")
        print("4. Интегрировать telegram_blocking_integration.py в main.py")
        print()
        print("🎯 Теперь все блокировки будут ГРОМКО озвучены!")

    except Exception as e:
        print(f"❌ Ошибка интеграции: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()