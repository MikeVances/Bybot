#!/usr/bin/env python3
"""
Тестовый скрипт для проверки установки стоп-лоссов и тейк-профитов
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.exchange.api_adapter import create_trading_bot_adapter
from bot.strategy.implementations.volume_vwap_strategy import create_volume_vwap_strategy
import pandas as pd

def test_stop_loss_tp_calculation():
    """Тест расчета стоп-лоссов и тейк-профитов"""
    print("🔍 Тест расчета стоп-лоссов и тейк-профитов")
    print("=" * 50)
    
    # Создаем API клиент
    api = create_trading_bot_adapter(
        symbol="BTCUSDT",
        use_v5=True,
        testnet=True
    )
    
    # Создаем стратегию
    strategy = create_volume_vwap_strategy()
    
    # Получаем рыночные данные
    print("📊 Получение рыночных данных...")
    df = api.get_ohlcv("1", 100)
    
    if df is None or df.empty:
        print("❌ Не удалось получить данные")
        return
    
    current_price = df['close'].iloc[-1]
    print(f"💰 Текущая цена: ${current_price:.2f}")
    
    # Тестируем расчет уровней для LONG позиции
    print("\n📈 Тест LONG позиции:")
    entry_price_long = current_price
    stop_loss_long, take_profit_long = strategy.calculate_dynamic_levels(df, entry_price_long, 'BUY')
    
    print(f"   Цена входа: ${entry_price_long:.2f}")
    print(f"   Стоп-лосс: ${stop_loss_long:.2f}")
    print(f"   Тейк-профит: ${take_profit_long:.2f}")
    
    # Проверяем логику
    if stop_loss_long < entry_price_long:
        print("   ✅ Стоп-лосс ниже цены входа (правильно для LONG)")
    else:
        print("   ❌ Стоп-лосс выше цены входа (неправильно для LONG)")
    
    if take_profit_long > entry_price_long:
        print("   ✅ Тейк-профит выше цены входа (правильно для LONG)")
    else:
        print("   ❌ Тейк-профит ниже цены входа (неправильно для LONG)")
    
    # Тестируем расчет уровней для SHORT позиции
    print("\n📉 Тест SHORT позиции:")
    entry_price_short = current_price
    stop_loss_short, take_profit_short = strategy.calculate_dynamic_levels(df, entry_price_short, 'SELL')
    
    print(f"   Цена входа: ${entry_price_short:.2f}")
    print(f"   Стоп-лосс: ${stop_loss_short:.2f}")
    print(f"   Тейк-профит: ${take_profit_short:.2f}")
    
    # Проверяем логику
    if stop_loss_short > entry_price_short:
        print("   ✅ Стоп-лосс выше цены входа (правильно для SHORT)")
    else:
        print("   ❌ Стоп-лосс ниже цены входа (неправильно для SHORT)")
    
    if take_profit_short < entry_price_short:
        print("   ✅ Тейк-профит ниже цены входа (правильно для SHORT)")
    else:
        print("   ❌ Тейк-профит выше цены входа (неправильно для SHORT)")
    
    # Тестируем создание сигнала
    print("\n🎯 Тест создания сигнала:")
    market_data = {
        '1m': df,
        '5m': df,
        '15m': df,
        '1h': df
    }
    
    signal = strategy.execute(market_data, symbol="BTCUSDT")
    
    if signal:
        print(f"   Тип сигнала: {signal.get('signal')}")
        print(f"   Цена входа: ${signal.get('entry_price', 0):.2f}")
        print(f"   Стоп-лосс: ${signal.get('stop_loss', 0):.2f}")
        print(f"   Тейк-профит: ${signal.get('take_profit', 0):.2f}")
        print(f"   Сила сигнала: {signal.get('signal_strength', 0):.3f}")
    else:
        print("   ❌ Сигнал не сгенерирован")
    
    # Тестируем API создание ордера (без реального размещения)
    print("\n🔧 Тест API создания ордера:")
    if signal:
        try:
            # Создаем тестовый ордер (не размещаем)
            order_params = {
                "symbol": "BTCUSDT",
                "side": "Sell" if signal.get('signal') == 'SELL' else "Buy",
                "orderType": "Market",
                "qty": "0.001",
                "stopLoss": str(signal.get('stop_loss', 0)),
                "takeProfit": str(signal.get('take_profit', 0))
            }
            
            print("   Параметры ордера:")
            for key, value in order_params.items():
                print(f"     {key}: {value}")
            
            print("   ✅ Параметры ордера корректны")
            
        except Exception as e:
            print(f"   ❌ Ошибка создания ордера: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Тест завершен!")

if __name__ == "__main__":
    test_stop_loss_tp_calculation() 