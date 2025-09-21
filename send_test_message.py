#!/usr/bin/env python3
"""
Отправка тестового сообщения через нового бота
"""

import asyncio
from app.bot import get_bot_instance
from app.services.trading_service import trading_service

async def send_test_message():
    bot = get_bot_instance()

    # Your admin ID
    admin_id = 460406929

    # Get real data
    status = await trading_service.get_trading_status()
    balance = await trading_service.get_account_balance()

    test_message = f"""
🚀 <b>НОВЫЙ БОТ АКТИВЕН!</b>

✅ <b>Интеграция работает:</b>
📊 Стратегий: {status["active_strategies_count"]}
💰 Баланс: ${balance["available_balance"]:,.2f} USDT
🎯 Эквити: ${balance["total_equity"]:,.2f} USDT

🔥 <b>Торговля:</b> {"✅ Разрешена" if status["trading_allowed"] else "❌ Заблокирована"}
🚨 <b>Emergency:</b> {status["emergency_stop"]}

Нажмите /start для нового интерфейса!
"""

    try:
        await bot.bot.send_message(
            chat_id=admin_id,
            text=test_message,
            parse_mode="HTML"
        )
        print("✅ Тестовое сообщение отправлено!")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

if __name__ == "__main__":
    asyncio.run(send_test_message())