"""
Тест для Fibonacci RSI Volume Strategy
Проверяет функциональность стратегии, вдохновленной выступлением Сергея на SoloConf
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Добавляем корневую директорию в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.strategy.implementations.fibonacci_rsi_strategy import (
    FibonacciRSIStrategy,
    FibonacciRSIConfig,
    create_fibonacci_rsi_strategy,
    create_conservative_fibonacci_rsi,
    create_aggressive_fibonacci_rsi
)


class MockState:
    """Мок-объект для состояния позиции"""
    def __init__(self):
        self.in_position = False
        self.position_side = None
        self.entry_price = None
        self.entry_time = None
        self.stop_loss = None
        self.take_profit = None
        self.position_size = 0.0
        self.unrealized_pnl = 0.0


def create_mock_market_data():
    """Создание мок-данных рынка для тестирования"""
    
    # Создаем временные метки
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    
    # Генерируем данные для 15m таймфрейма
    timestamps_15m = pd.date_range(start=start_time, end=end_time, freq='15T')
    data_15m = []
    
    base_price = 45000.0
    for i, ts in enumerate(timestamps_15m):
        # Создаем реалистичные данные с трендом
        trend_factor = 1 + (i / len(timestamps_15m)) * 0.02  # Небольшой восходящий тренд
        noise = np.random.normal(0, 100)
        
        open_price = base_price * trend_factor + noise
        high_price = open_price + np.random.uniform(50, 200)
        low_price = open_price - np.random.uniform(50, 200)
        close_price = open_price + np.random.uniform(-100, 100)
        volume = np.random.uniform(1000, 5000)
        
        data_15m.append({
            'timestamp': ts,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })
    
    # Генерируем данные для 1h таймфрейма
    timestamps_1h = pd.date_range(start=start_time, end=end_time, freq='1H')
    data_1h = []
    
    for i, ts in enumerate(timestamps_1h):
        trend_factor = 1 + (i / len(timestamps_1h)) * 0.02
        noise = np.random.normal(0, 200)
        
        open_price = base_price * trend_factor + noise
        high_price = open_price + np.random.uniform(100, 400)
        low_price = open_price - np.random.uniform(100, 400)
        close_price = open_price + np.random.uniform(-200, 200)
        volume = np.random.uniform(2000, 10000)
        
        data_1h.append({
            'timestamp': ts,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })
    
    # Создаем DataFrame
    df_15m = pd.DataFrame(data_15m)
    df_1h = pd.DataFrame(data_1h)
    
    return {
        '15m': df_15m,
        '1h': df_1h
    }


def test_fibonacci_rsi_strategy_creation():
    """Тест создания стратегии"""
    print("🧪 Тестирование создания Fibonacci RSI стратегии...")
    
    try:
        # Создаем стандартную стратегию
        strategy = create_fibonacci_rsi_strategy()
        assert strategy is not None
        assert isinstance(strategy, FibonacciRSIStrategy)
        print("✅ Стандартная стратегия создана успешно")
        
        # Создаем консервативную стратегию
        conservative = create_conservative_fibonacci_rsi()
        assert conservative is not None
        assert isinstance(conservative, FibonacciRSIStrategy)
        print("✅ Консервативная стратегия создана успешно")
        
        # Создаем агрессивную стратегию
        aggressive = create_aggressive_fibonacci_rsi()
        assert aggressive is not None
        assert isinstance(aggressive, FibonacciRSIStrategy)
        print("✅ Агрессивная стратегия создана успешно")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания стратегии: {e}")
        return False


def test_fibonacci_rsi_config():
    """Тест конфигурации стратегии"""
    print("🧪 Тестирование конфигурации Fibonacci RSI...")
    
    try:
        config = FibonacciRSIConfig()
        
        # Проверяем параметры
        assert config.fast_tf == '15m'
        assert config.slow_tf == '1h'
        assert config.ema_short == 20
        assert config.ema_long == 50
        assert config.rsi_period == 14
        assert config.volume_multiplier == 1.5
        assert config.atr_period == 14
        assert config.fib_lookback == 50
        
        print("✅ Конфигурация корректна")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return False


def test_fibonacci_rsi_indicators():
    """Тест расчета индикаторов"""
    print("🧪 Тестирование расчета индикаторов...")
    
    try:
        strategy = create_fibonacci_rsi_strategy()
        market_data = create_mock_market_data()
        
        # Рассчитываем индикаторы
        indicators = strategy.calculate_strategy_indicators(market_data)
        
        # Проверяем наличие ключевых индикаторов
        assert 'ema_short' in indicators
        assert 'ema_long' in indicators
        assert 'rsi' in indicators
        assert 'volume_spike' in indicators
        assert 'atr' in indicators
        assert 'fib_levels' in indicators
        assert 'trend_up' in indicators
        assert 'trend_down' in indicators
        
        print(f"✅ Индикаторы рассчитаны: RSI={indicators.get('rsi', 0):.1f}, "
              f"EMA_short={indicators.get('ema_short', 0):.1f}, "
              f"Volume_ratio={indicators.get('volume_ratio', 0):.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка расчета индикаторов: {e}")
        return False


def test_fibonacci_rsi_signal_strength():
    """Тест расчета силы сигнала"""
    print("🧪 Тестирование расчета силы сигнала...")
    
    try:
        strategy = create_fibonacci_rsi_strategy()
        market_data = create_mock_market_data()
        indicators = strategy.calculate_strategy_indicators(market_data)
        
        # Тестируем силу сигнала для BUY
        buy_strength = strategy.calculate_signal_strength(market_data, indicators, 'BUY')
        assert 0 <= buy_strength <= 1
        
        # Тестируем силу сигнала для SELL
        sell_strength = strategy.calculate_signal_strength(market_data, indicators, 'SELL')
        assert 0 <= sell_strength <= 1
        
        print(f"✅ Сила сигнала: BUY={buy_strength:.2f}, SELL={sell_strength:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка расчета силы сигнала: {e}")
        return False


def test_fibonacci_rsi_confluence_factors():
    """Тест confluence факторов"""
    print("🧪 Тестирование confluence факторов...")
    
    try:
        strategy = create_fibonacci_rsi_strategy()
        market_data = create_mock_market_data()
        indicators = strategy.calculate_strategy_indicators(market_data)
        
        # Тестируем confluence для BUY
        buy_count, buy_factors = strategy.check_confluence_factors(market_data, indicators, 'BUY')
        assert buy_count >= 0
        assert isinstance(buy_factors, list)
        
        # Тестируем confluence для SELL
        sell_count, sell_factors = strategy.check_confluence_factors(market_data, indicators, 'SELL')
        assert sell_count >= 0
        assert isinstance(sell_factors, list)
        
        print(f"✅ Confluence факторы: BUY={buy_count} ({buy_factors}), SELL={sell_count} ({sell_factors})")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка confluence факторов: {e}")
        return False


def test_fibonacci_rsi_execution():
    """Тест выполнения стратегии"""
    print("🧪 Тестирование выполнения стратегии...")
    
    try:
        strategy = create_fibonacci_rsi_strategy()
        market_data = create_mock_market_data()
        state = MockState()
        
        # Тестируем выполнение без позиции
        signal = strategy.execute(market_data, state)
        
        # Сигнал может быть None (нет условий для входа)
        if signal is not None:
            assert 'signal' in signal
            assert 'entry_price' in signal
            assert 'stop_loss' in signal
            assert 'take_profit' in signal
            assert 'strategy' in signal
            print(f"✅ Сигнал сгенерирован: {signal['signal']} по цене {signal['entry_price']}")
        else:
            print("✅ Сигнал не сгенерирован (нормально для текущих условий)")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка выполнения стратегии: {e}")
        return False


def test_fibonacci_rsi_variants():
    """Тест различных вариантов стратегии"""
    print("🧪 Тестирование вариантов стратегии...")
    
    try:
        # Тестируем консервативную стратегию
        conservative = create_conservative_fibonacci_rsi()
        assert conservative.config.rsi_overbought == 75.0
        assert conservative.config.rsi_oversold == 25.0
        assert conservative.config.volume_multiplier == 2.0
        assert conservative.config.signal_strength_threshold == 0.7
        print("✅ Консервативная стратегия настроена корректно")
        
        # Тестируем агрессивную стратегию
        aggressive = create_aggressive_fibonacci_rsi()
        assert aggressive.config.rsi_overbought == 65.0
        assert aggressive.config.rsi_oversold == 35.0
        assert aggressive.config.volume_multiplier == 1.2
        assert aggressive.config.signal_strength_threshold == 0.5
        print("✅ Агрессивная стратегия настроена корректно")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка вариантов стратегии: {e}")
        return False


def test_fibonacci_rsi_fibonacci_levels():
    """Тест расчета уровней Фибоначчи"""
    print("🧪 Тестирование уровней Фибоначчи...")
    
    try:
        strategy = create_fibonacci_rsi_strategy()
        market_data = create_mock_market_data()
        indicators = strategy.calculate_strategy_indicators(market_data)
        
        # Проверяем наличие уровней Фибоначчи
        if 'fib_levels' in indicators:
            fib_levels = indicators['fib_levels']
            assert isinstance(fib_levels, dict)
            
            # Проверяем наличие ключевых уровней
            expected_levels = ['fib_382', 'fib_500', 'fib_618', 'fib_786']
            for level in expected_levels:
                if level in fib_levels:
                    assert isinstance(fib_levels[level], (int, float))
            
            print(f"✅ Уровни Фибоначчи рассчитаны: {list(fib_levels.keys())}")
        else:
            print("⚠️ Уровни Фибоначчи не рассчитаны (недостаточно данных)")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка уровней Фибоначчи: {e}")
        return False


def run_all_tests():
    """Запуск всех тестов"""
    print("🚀 Запуск тестов Fibonacci RSI Strategy")
    print("=" * 50)
    
    tests = [
        test_fibonacci_rsi_strategy_creation,
        test_fibonacci_rsi_config,
        test_fibonacci_rsi_indicators,
        test_fibonacci_rsi_signal_strength,
        test_fibonacci_rsi_confluence_factors,
        test_fibonacci_rsi_execution,
        test_fibonacci_rsi_variants,
        test_fibonacci_rsi_fibonacci_levels
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте {test.__name__}: {e}")
            print()
    
    print("=" * 50)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов прошли")
    
    if passed == total:
        print("🎉 Все тесты прошли успешно!")
        return True
    else:
        print("⚠️ Некоторые тесты не прошли")
        return False


if __name__ == "__main__":
    run_all_tests() 