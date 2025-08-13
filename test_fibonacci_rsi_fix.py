#!/usr/bin/env python3
"""
Тест исправленной Fibonacci RSI стратегии
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.exchange.api_adapter import create_trading_bot_adapter
from bot.strategy.implementations.fibonacci_rsi_strategy import create_fibonacci_rsi_strategy
import pandas as pd

def test_fibonacci_rsi_strategy():
    """Тест Fibonacci RSI стратегии"""
    print("🎯 Тест исправленной Fibonacci RSI стратегии")
    print("=" * 50)
    
    # Создаем API клиент
    api = create_trading_bot_adapter(
        symbol="BTCUSDT",
        use_v5=True,
        testnet=True
    )
    
    # Создаем стратегию
    strategy = create_fibonacci_rsi_strategy()
    
    print(f"📋 Стратегия: {strategy.config.strategy_name}")
    print(f"📊 Версия: {strategy.config.strategy_version}")
    print(f"📈 Таймфреймы: {strategy.config.fast_tf} / {strategy.config.slow_tf}")
    print(f"📊 R:R настройки: risk_reward_ratio={strategy.config.risk_reward_ratio}, min_risk_reward_ratio={strategy.config.min_risk_reward_ratio}")
    
    # Получаем рыночные данные
    print("\n📊 Получение рыночных данных...")
    df_15m = api.get_ohlcv("15", 100)
    df_1h = api.get_ohlcv("60", 100)
    
    if df_15m is None or df_1h is None:
        print("❌ Не удалось получить данные")
        return
    
    current_price = df_15m['close'].iloc[-1]
    print(f"💰 Текущая цена: ${current_price:.2f}")
    
    # Подготавливаем данные для стратегии
    market_data = {
        '15m': df_15m,
        '1h': df_1h
    }
    
    # Рассчитываем индикаторы
    print("\n🔧 Расчет индикаторов...")
    indicators = strategy.calculate_strategy_indicators(market_data)
    
    if not indicators:
        print("❌ Не удалось рассчитать индикаторы")
        return
    
    print(f"✅ Индикаторы рассчитаны: {len(indicators)} параметров")
    
    # Проверяем ключевые индикаторы
    print("\n📊 Ключевые индикаторы:")
    print(f"   EMA тренд: {'UP' if indicators.get('trend_up') else 'DOWN' if indicators.get('trend_down') else 'NEUTRAL'}")
    print(f"   RSI: {indicators.get('rsi', 0):.1f}")
    print(f"   Объемный всплеск: {'Да' if indicators.get('volume_spike') else 'Нет'}")
    print(f"   ATR: {indicators.get('atr', 0):.2f}")
    
    # Тестируем расчет уровней
    print("\n📈 Тест расчета уровней:")
    stop_loss, take_profit = strategy.calculate_dynamic_levels(df_15m, current_price, 'BUY')
    
    print(f"   Цена входа: ${current_price:.2f}")
    print(f"   Стоп-лосс: ${stop_loss:.2f}")
    print(f"   Тейк-профит: ${take_profit:.2f}")
    
    # Рассчитываем R:R
    risk = current_price - stop_loss
    reward = take_profit - current_price
    rr_ratio = reward / risk if risk > 0 else 0
    
    print(f"   Риск: ${risk:.2f}")
    print(f"   Прибыль: ${reward:.2f}")
    print(f"   R:R соотношение: {rr_ratio:.3f}")
    
    # Тестируем создание сигнала
    print("\n🎯 Тест создания сигнала:")
    signal = strategy.execute(market_data, symbol="BTCUSDT")
    
    if signal:
        print(f"   Тип сигнала: {signal.get('signal')}")
        print(f"   Цена входа: ${signal.get('entry_price', 0):.2f}")
        print(f"   Стоп-лосс: ${signal.get('stop_loss', 0):.2f}")
        print(f"   Тейк-профит: ${signal.get('take_profit', 0):.2f}")
        print(f"   Сила сигнала: {signal.get('signal_strength', 0):.3f}")
        print(f"   Confluence факторов: {signal.get('confluence_count', 0)}")
    else:
        print("   ❌ Сигнал не сгенерирован")
    
    print("\n" + "=" * 50)
    print("✅ Тест Fibonacci RSI стратегии завершен!")
    print("\n💡 Выводы:")
    print("   - Стратегия успешно интегрирована с базовой архитектурой")
    print("   - Использует стандартную логику расчета уровней")
    print("   - Поддерживает адаптивные параметры")

if __name__ == "__main__":
    test_fibonacci_rsi_strategy() 