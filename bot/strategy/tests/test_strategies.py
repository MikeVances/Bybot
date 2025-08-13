#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.core.trader import BotState, load_strategy
import pandas as pd
import numpy as np

def test_strategy():
    """Тестируем работу стратегии"""
    
    # Создаем тестовые данные с достаточным количеством строк (минимум 50 для trend_period)
    base_price = 117000
    base_volume = 1000
    
    # Генерируем 100 строк данных с восходящим трендом (больше чем trend_period=50)
    opens = [base_price + i * 15 for i in range(100)]  # Более сильный тренд
    highs = [price + 50 for price in opens]
    lows = [price - 50 for price in opens]
    closes = [price + 100 for price in opens]
    # Увеличиваем объем в конце для создания сигнала
    volumes = [base_volume + i * 10 for i in range(100)]
    # Делаем последний объем очень большим для срабатывания условия
    volumes[-1] = base_volume * 10  # 10x больше среднего
    
    test_data = {
        '1m': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }),
        '5m': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }),
        '15m': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }),
        '1h': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })
    }
    
    # Создаем состояние бота
    state = BotState()
    
    # Тестируем стратегию strategy_01
    print("Тестируем strategy_01...")
    
    try:
        strategy_class = load_strategy('strategy_01')
        if strategy_class:
            strategy = strategy_class()
            print(f"Стратегия загружена: {strategy.__class__.__name__}")
            print(f"Параметры стратегии: {strategy.__dict__}")
            
            signal = strategy.execute(test_data, state, None)
            print(f"Сигнал от strategy_01: {signal}")
            
            if signal:
                print(f"Тип сигнала: {signal.get('signal')}")
                print(f"Цена входа: {signal.get('entry_price')}")
                print(f"Stop Loss: {signal.get('stop_loss')}")
                print(f"Take Profit: {signal.get('take_profit')}")
            else:
                print("Стратегия вернула None - нет сигнала")
        else:
            print("Не удалось загрузить strategy_01")
    except Exception as e:
        print(f"Ошибка при тестировании strategy_01: {e}")
        import traceback
        traceback.print_exc()
    
    # Тестируем стратегию strategy_05
    print("\nТестируем strategy_05...")
    
    try:
        strategy_class = load_strategy('strategy_05')
        if strategy_class:
            strategy = strategy_class()
            print(f"Стратегия загружена: {strategy.__class__.__name__}")
            
            signal = strategy.execute(test_data, state, None)
            print(f"Сигнал от strategy_05: {signal}")
            
            if signal:
                print(f"Тип сигнала: {signal.get('signal')}")
                print(f"Цена входа: {signal.get('entry_price')}")
                print(f"Stop Loss: {signal.get('stop_loss')}")
                print(f"Take Profit: {signal.get('take_profit')}")
            else:
                print("Стратегия вернула None - нет сигнала")
        else:
            print("Не удалось загрузить strategy_05")
    except Exception as e:
        print(f"Ошибка при тестировании strategy_05: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_strategy() 