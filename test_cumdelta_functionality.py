#!/usr/bin/env python3
"""
Детальный тест функциональности CumDelta SR стратегии
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_test_data():
    """Создание тестовых данных"""
    print("📊 Создание тестовых данных...")
    
    # Создаем тестовые данные
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
    
    # Базовые цены
    base_price = 50000
    prices = []
    volumes = []
    
    for i in range(100):
        # Симуляция движения цены
        if i < 30:
            # Тренд вверх
            price = base_price + i * 100 + np.random.normal(0, 50)
        elif i < 60:
            # Боковое движение
            price = base_price + 3000 + np.random.normal(0, 200)
        else:
            # Тренд вниз
            price = base_price + 3000 - (i - 60) * 80 + np.random.normal(0, 50)
        
        prices.append(price)
        
        # Объем с всплесками
        if i % 10 == 0:
            volume = np.random.uniform(1000, 5000)
        else:
            volume = np.random.uniform(100, 500)
        volumes.append(volume)
    
    # Создаем OHLCV данные
    df = pd.DataFrame({
        'open': prices,
        'high': [p + np.random.uniform(0, 100) for p in prices],
        'low': [p - np.random.uniform(0, 100) for p in prices],
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    # Корректируем high/low
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)
    
    print(f"✅ Создано {len(df)} баров данных")
    return df

def test_cumdelta_indicators():
    """Тест расчета индикаторов"""
    print("\n🔍 Тестирование расчета индикаторов...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        
        # Создание стратегии
        config = CumDeltaConfig(
            delta_window=20,
            min_delta_threshold=100.0,
            support_window=20,
            support_resistance_tolerance=0.002,
            volume_multiplier=1.5
        )
        strategy = CumDeltaSRStrategy(config)
        
        # Создание тестовых данных
        df = create_test_data()
        
        # Тест расчета индикаторов
        indicators = strategy.calculate_strategy_indicators({'1h': df})
        
        if indicators:
            print("✅ Индикаторы рассчитаны успешно")
            
            # Проверка ключевых индикаторов
            key_indicators = [
                'cum_delta', 'delta_momentum', 'delta_strength',
                'support_levels', 'resistance_levels', 'trend_slope',
                'trend_strength', 'volume_ratio'
            ]
            
            for indicator in key_indicators:
                if indicator in indicators:
                    print(f"✅ Индикатор {indicator} присутствует")
                else:
                    print(f"⚠️  Отсутствует индикатор {indicator}")
            
            return True
        else:
            print("❌ Не удалось рассчитать индикаторы")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка расчета индикаторов: {e}")
        return False

def test_cumdelta_signal_strength():
    """Тест расчета силы сигнала"""
    print("\n🔍 Тестирование расчета силы сигнала...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        
        # Создание стратегии
        config = CumDeltaConfig()
        strategy = CumDeltaSRStrategy(config)
        
        # Создание тестовых данных
        df = create_test_data()
        
        # Расчет индикаторов
        indicators = strategy.calculate_strategy_indicators({'1h': df})
        
        if not indicators:
            print("❌ Не удалось получить индикаторы")
            return False
        
        # Тест силы сигнала для BUY
        buy_strength = strategy.calculate_signal_strength({'1h': df}, indicators, 'BUY')
        print(f"✅ Сила сигнала BUY: {buy_strength:.3f}")
        
        # Тест силы сигнала для SELL
        sell_strength = strategy.calculate_signal_strength({'1h': df}, indicators, 'SELL')
        print(f"✅ Сила сигнала SELL: {sell_strength:.3f}")
        
        # Проверка диапазона
        if 0 <= buy_strength <= 1 and 0 <= sell_strength <= 1:
            print("✅ Сила сигнала в правильном диапазоне [0, 1]")
            return True
        else:
            print("❌ Сила сигнала вне диапазона [0, 1]")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка расчета силы сигнала: {e}")
        return False

def test_cumdelta_confluence():
    """Тест confluence факторов"""
    print("\n🔍 Тестирование confluence факторов...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        
        # Создание стратегии
        config = CumDeltaConfig()
        strategy = CumDeltaSRStrategy(config)
        
        # Создание тестовых данных
        df = create_test_data()
        
        # Расчет индикаторов
        indicators = strategy.calculate_strategy_indicators({'1h': df})
        
        if not indicators:
            print("❌ Не удалось получить индикаторы")
            return False
        
        # Тест confluence для BUY
        buy_confluence, buy_factors = strategy.check_confluence_factors({'1h': df}, indicators, 'BUY')
        print(f"✅ Confluence BUY: {buy_confluence} факторов - {buy_factors}")
        
        # Тест confluence для SELL
        sell_confluence, sell_factors = strategy.check_confluence_factors({'1h': df}, indicators, 'SELL')
        print(f"✅ Confluence SELL: {sell_confluence} факторов - {sell_factors}")
        
        # Проверка корректности
        if isinstance(buy_confluence, int) and isinstance(sell_confluence, int):
            print("✅ Confluence факторы рассчитаны корректно")
            return True
        else:
            print("❌ Confluence факторы имеют неправильный тип")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка расчета confluence факторов: {e}")
        return False

def test_cumdelta_execute():
    """Тест выполнения стратегии"""
    print("\n🔍 Тестирование выполнения стратегии...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        
        # Создание стратегии
        config = CumDeltaConfig(
            signal_strength_threshold=0.3,  # Низкий порог для тестирования
            confluence_required=1  # Минимальные требования
        )
        strategy = CumDeltaSRStrategy(config)
        
        # Создание тестовых данных
        df = create_test_data()
        
        # Тест выполнения без позиции
        result = strategy.execute({'1h': df}, state=None, symbol='BTCUSDT')
        
        if result is None:
            print("✅ Стратегия корректно вернула None (нет сигнала)")
        else:
            print(f"✅ Стратегия сгенерировала сигнал: {result.get('signal', 'UNKNOWN')}")
            print(f"   Entry: {result.get('entry_price', 'N/A')}")
            print(f"   SL: {result.get('stop_loss', 'N/A')}")
            print(f"   TP: {result.get('take_profit', 'N/A')}")
            print(f"   Strength: {result.get('signal_strength', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка выполнения стратегии: {e}")
        return False

def test_cumdelta_dynamic_levels():
    """Тест динамических уровней"""
    print("\n🔍 Тестирование динамических уровней...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        
        # Создание стратегии
        config = CumDeltaConfig()
        strategy = CumDeltaSRStrategy(config)
        
        # Создание тестовых данных
        df = create_test_data()
        current_price = df['close'].iloc[-1]
        
        # Тест расчета уровней для BUY
        stop_loss_buy, take_profit_buy = strategy.calculate_dynamic_levels(df, current_price, 'BUY')
        print(f"✅ BUY уровни - SL: {stop_loss_buy:.2f}, TP: {take_profit_buy:.2f}")
        
        # Тест расчета уровней для SELL
        stop_loss_sell, take_profit_sell = strategy.calculate_dynamic_levels(df, current_price, 'SELL')
        print(f"✅ SELL уровни - SL: {stop_loss_sell:.2f}, TP: {take_profit_sell:.2f}")
        
        # Проверка логики уровней
        if (stop_loss_buy < current_price < take_profit_buy and 
            stop_loss_sell > current_price > take_profit_sell):
            print("✅ Логика уровней корректна")
            return True
        else:
            print("❌ Логика уровней некорректна")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка расчета динамических уровней: {e}")
        return False

def test_cumdelta_rr_validation():
    """Тест валидации R:R"""
    print("\n🔍 Тестирование валидации R:R...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        
        # Создание стратегии
        config = CumDeltaConfig()
        strategy = CumDeltaSRStrategy(config)
        
        # Проверка установки min_risk_reward_ratio
        if hasattr(strategy.config, 'min_risk_reward_ratio'):
            print(f"✅ min_risk_reward_ratio установлен: {strategy.config.min_risk_reward_ratio}")
            
            if strategy.config.min_risk_reward_ratio == 0.8:
                print("✅ Значение соответствует скальпингу")
                return True
            else:
                print(f"⚠️  Неожиданное значение: {strategy.config.min_risk_reward_ratio}")
                return False
        else:
            print("❌ min_risk_reward_ratio не установлен")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки R:R: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🚀 Детальное тестирование функциональности CumDelta SR стратегии")
    print("=" * 80)
    
    tests = [
        test_cumdelta_indicators,
        test_cumdelta_signal_strength,
        test_cumdelta_confluence,
        test_cumdelta_dynamic_levels,
        test_cumdelta_rr_validation,
        test_cumdelta_execute
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ Тест {test.__name__} не прошел")
        except Exception as e:
            print(f"❌ Тест {test.__name__} завершился с ошибкой: {e}")
    
    print("\n" + "=" * 80)
    print(f"📊 Результаты функционального тестирования: {passed}/{total} тестов прошли успешно")
    
    if passed == total:
        print("🎉 CumDelta SR стратегия полностью функциональна!")
        return True
    else:
        print("⚠️  Обнаружены проблемы с функциональностью CumDelta SR стратегии")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
