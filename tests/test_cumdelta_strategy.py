#!/usr/bin/env python3
"""
Тест для CumDelta Support/Resistance стратегии v2.0
Проверяет функциональность рефакторированной стратегии
"""

import sys
import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

def test_cumdelta_strategy():
    """Тестирование CumDelta стратегии"""
    print("🚀 Тестирование CumDelta Support/Resistance стратегии v2.0")
    print("=" * 60)
    
    try:
        # 1. Импорт стратегии
        from bot.strategy.implementations.cumdelta_sr_strategy import (
            CumDeltaSRStrategy, 
            create_cumdelta_sr_strategy,
            create_conservative_cumdelta_sr,
            create_aggressive_cumdelta_sr
        )
        print("✅ Импорт стратегии успешен")
        
        # 2. Создание тестовых данных
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        base_price = 45000
        prices = base_price + np.cumsum(np.random.normal(0, 50, 100))
        
        test_data = pd.DataFrame({
            'open': prices + np.random.normal(0, 10, 100),
            'high': prices + np.abs(np.random.normal(0, 20, 100)),
            'low': prices - np.abs(np.random.normal(0, 20, 100)),
            'close': prices + np.random.normal(0, 10, 100),
            'volume': np.random.randint(1000, 5000, 100)
        })
        
        # Добавляем дельту для тестирования
        test_data['delta'] = (test_data['close'] - test_data['open']) * test_data['volume'] * np.sign(test_data['close'] - test_data['open'])
        
        print("✅ Тестовые данные созданы")
        
        # 3. Тестирование создания стратегий
        print("\n📊 Тестирование создания стратегий:")
        
        # Стандартная стратегия
        strategy = create_cumdelta_sr_strategy()
        print(f"✅ Стандартная стратегия создана: {strategy.strategy_name}")
        
        # Консервативная стратегия
        conservative = create_conservative_cumdelta_sr()
        print(f"✅ Консервативная стратегия создана: {conservative.strategy_name}")
        
        # Агрессивная стратегия
        aggressive = create_aggressive_cumdelta_sr()
        print(f"✅ Агрессивная стратегия создана: {aggressive.strategy_name}")
        
        # 4. Тестирование расчета индикаторов
        print("\n📈 Тестирование расчета индикаторов:")
        indicators = strategy.calculate_strategy_indicators(test_data)
        print(f"✅ Рассчитано индикаторов: {len(indicators)}")
        
        # Проверяем ключевые индикаторы
        key_indicators = ['cum_delta', 'support_levels', 'resistance_levels', 'trend_slope']
        for indicator in key_indicators:
            if indicator in indicators:
                print(f"✅ {indicator}: присутствует")
            else:
                print(f"⚠️ {indicator}: отсутствует")
        
        # 5. Тестирование расчета силы сигнала
        print("\n💪 Тестирование расчета силы сигнала:")
        buy_strength = strategy.calculate_signal_strength(test_data, indicators, 'BUY')
        sell_strength = strategy.calculate_signal_strength(test_data, indicators, 'SELL')
        print(f"✅ Сила сигнала BUY: {buy_strength:.3f}")
        print(f"✅ Сила сигнала SELL: {sell_strength:.3f}")
        
        # 6. Тестирование confluence факторов
        print("\n🔍 Тестирование confluence факторов:")
        buy_confluence, buy_factors = strategy.check_confluence_factors(test_data, indicators, 'BUY')
        sell_confluence, sell_factors = strategy.check_confluence_factors(test_data, indicators, 'SELL')
        print(f"✅ Confluence BUY: {buy_confluence} факторов: {buy_factors}")
        print(f"✅ Confluence SELL: {sell_confluence} факторов: {sell_factors}")
        
        # 7. Тестирование выполнения стратегии
        print("\n🎯 Тестирование выполнения стратегии:")
        result = strategy.execute(test_data)
        if result:
            print(f"✅ Сигнал сгенерирован: {result['signal']}")
            print(f"📊 Детали: {result.get('comment', 'N/A')}")
        else:
            print("ℹ️ Сигнал не сгенерирован (нормально для тестовых данных)")
        
        # 8. Тестирование информации о стратегии
        print("\n📋 Информация о стратегии:")
        info = strategy.get_strategy_info()
        print(f"✅ Название: {info['strategy_name']}")
        print(f"✅ Версия: {info['version']}")
        print(f"✅ Описание: {info['description']}")
        print(f"✅ Активна: {info['is_active']}")
        
        # 9. Тестирование статистики
        print("\n📊 Статистика стратегии:")
        stats = strategy.get_strategy_statistics()
        print(f"✅ Сигналов сгенерировано: {stats['signals_generated']}")
        print(f"✅ Сигналов выполнено: {stats['signals_executed']}")
        
        print("\n🎉 ВСЕ ТЕСТЫ CUMDELTA СТРАТЕГИИ ПРОЙДЕНЫ УСПЕШНО!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_cumdelta_strategy()
    sys.exit(0 if success else 1) 