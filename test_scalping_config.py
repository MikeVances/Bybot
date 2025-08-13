#!/usr/bin/env python3
"""
Тест конфигурации для скальпинга с частыми небольшими прибылями
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.exchange.api_adapter import create_trading_bot_adapter
from bot.strategy.implementations.volume_vwap_strategy import create_volume_vwap_strategy
from bot.strategy.base import VolumeVWAPConfig
import pandas as pd

def test_scalping_config():
    """Тест конфигурации для скальпинга"""
    print("🎯 Тест конфигурации для скальпинга")
    print("=" * 50)
    
    # Создаем API клиент
    api = create_trading_bot_adapter(
        symbol="BTCUSDT",
        use_v5=True,
        testnet=True
    )
    
    # Создаем конфигурацию для скальпинга
    scalping_config = VolumeVWAPConfig(
        # Уменьшаем стоп-лосс для быстрых выходов
        stop_loss_atr_multiplier=0.8,  # Было 1.5
        
        # Уменьшаем R:R для частых небольших прибылей
        risk_reward_ratio=1.2,  # Было 1.5
        
        # Более чувствительные фильтры
        signal_strength_threshold=0.5,  # Было 0.6
        confluence_required=1,  # Было 2
        
        # Адаптивные параметры
        adaptive_parameters=True,
        market_regime_adaptation=True
    )
    
    print("📋 Конфигурация для скальпинга:")
    print(f"   Стоп-лосс ATR множитель: {scalping_config.stop_loss_atr_multiplier}")
    print(f"   Risk/Reward соотношение: {scalping_config.risk_reward_ratio}")
    print(f"   Порог силы сигнала: {scalping_config.signal_strength_threshold}")
    print(f"   Требуемые confluence факторы: {scalping_config.confluence_required}")
    
    # Создаем стратегию с новой конфигурацией
    strategy = create_volume_vwap_strategy(scalping_config)
    
    # Получаем рыночные данные
    print("\n📊 Получение рыночных данных...")
    df = api.get_ohlcv("1", 100)
    
    if df is None or df.empty:
        print("❌ Не удалось получить данные")
        return
    
    current_price = df['close'].iloc[-1]
    print(f"💰 Текущая цена: ${current_price:.2f}")
    
    # Тестируем расчет уровней для SHORT позиции с новой конфигурацией
    print("\n📉 Тест SHORT позиции (скальпинг):")
    entry_price_short = current_price
    stop_loss_short, take_profit_short = strategy.calculate_dynamic_levels(df, entry_price_short, 'SELL')
    
    print(f"   Цена входа: ${entry_price_short:.2f}")
    print(f"   Стоп-лосс: ${stop_loss_short:.2f}")
    print(f"   Тейк-профит: ${take_profit_short:.2f}")
    
    # Рассчитываем R:R
    risk = stop_loss_short - entry_price_short
    reward = entry_price_short - take_profit_short
    rr_ratio = reward / risk if risk > 0 else 0
    
    print(f"   Риск: ${risk:.2f}")
    print(f"   Прибыль: ${reward:.2f}")
    print(f"   R:R соотношение: {rr_ratio:.3f}")
    
    # Проверяем логику
    if stop_loss_short > entry_price_short:
        print("   ✅ Стоп-лосс выше цены входа (правильно для SHORT)")
    else:
        print("   ❌ Стоп-лосс ниже цены входа (неправильно для SHORT)")
    
    if take_profit_short < entry_price_short:
        print("   ✅ Тейк-профит ниже цены входа (правильно для SHORT)")
    else:
        print("   ❌ Тейк-профит выше цены входа (неправильно для SHORT)")
    
    if rr_ratio >= 1.0:
        print("   ✅ R:R соотношение приемлемо для скальпинга")
    else:
        print(f"   ⚠️ R:R соотношение низкое ({rr_ratio:.3f}), но это нормально для скальпинга")
    
    # Тестируем создание сигнала
    print("\n🎯 Тест создания сигнала (скальпинг):")
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
        
        # Рассчитываем R:R для сигнала
        sl = signal.get('stop_loss', 0)
        tp = signal.get('take_profit', 0)
        entry = signal.get('entry_price', 0)
        
        if entry > 0 and sl > 0 and tp > 0:
            if signal.get('signal') == 'SELL':
                risk = sl - entry
                reward = entry - tp
            else:
                risk = entry - sl
                reward = tp - entry
            
            rr = reward / risk if risk > 0 else 0
            print(f"   R:R для сигнала: {rr:.3f}")
    else:
        print("   ❌ Сигнал не сгенерирован")
    
    print("\n" + "=" * 50)
    print("✅ Тест скальпинг конфигурации завершен!")
    print("\n💡 Выводы:")
    print("   - Уменьшенный стоп-лосс позволяет быстрые выходы")
    print("   - Низкий R:R фокусируется на частых небольших прибылях")
    print("   - Это типичная настройка для скальпинга")

if __name__ == "__main__":
    test_scalping_config() 