#!/usr/bin/env python3
"""
Тест CumDelta SR стратегии на предмет адаптации к системе
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_cumdelta_strategy_imports():
    """Тест импортов CumDelta стратегии"""
    print("🔍 Тестирование импортов CumDelta стратегии...")
    
    try:
        # Тест импорта базовых компонентов
        from bot.strategy.base import CumDeltaConfig, BaseStrategy
        print("✅ CumDeltaConfig и BaseStrategy импортированы успешно")
        
        # Тест импорта стратегии
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        print("✅ CumDeltaSRStrategy импортирована успешно")
        
        # Тест импорта фабричных функций
        from bot.strategy.implementations.cumdelta_sr_strategy import (
            create_cumdelta_sr_strategy,
            create_conservative_cumdelta_sr,
            create_aggressive_cumdelta_sr
        )
        print("✅ Фабричные функции импортированы успешно")
        
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

def test_cumdelta_config():
    """Тест конфигурации CumDelta"""
    print("\n🔍 Тестирование конфигурации CumDelta...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        
        # Создание базовой конфигурации
        config = CumDeltaConfig()
        print(f"✅ Базовая конфигурация создана: {config.strategy_name}")
        
        # Проверка обязательных параметров
        required_params = [
            'delta_window', 'min_delta_threshold', 'support_window',
            'support_resistance_tolerance', 'volume_multiplier'
        ]
        
        for param in required_params:
            if hasattr(config, param):
                print(f"✅ Параметр {param}: {getattr(config, param)}")
            else:
                print(f"❌ Отсутствует параметр {param}")
                return False
        
        # Тест валидации
        config.validate()
        print("✅ Валидация конфигурации прошла успешно")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return False

def test_cumdelta_strategy_creation():
    """Тест создания CumDelta стратегии"""
    print("\n🔍 Тестирование создания CumDelta стратегии...")
    
    try:
        from bot.strategy.base import CumDeltaConfig
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        
        # Создание конфигурации
        config = CumDeltaConfig(
            delta_window=20,
            min_delta_threshold=100.0,
            support_window=20,
            support_resistance_tolerance=0.002,
            volume_multiplier=1.5
        )
        
        # Создание стратегии
        strategy = CumDeltaSRStrategy(config)
        print(f"✅ Стратегия создана: {strategy.config.strategy_name}")
        
        # Проверка наследования
        from bot.strategy.base import BaseStrategy
        if isinstance(strategy, BaseStrategy):
            print("✅ Стратегия правильно наследует BaseStrategy")
        else:
            print("❌ Стратегия не наследует BaseStrategy")
            return False
        
        # Проверка методов
        required_methods = [
            'calculate_strategy_indicators',
            'calculate_signal_strength',
            'check_confluence_factors',
            'execute'
        ]
        
        for method in required_methods:
            if hasattr(strategy, method):
                print(f"✅ Метод {method} присутствует")
            else:
                print(f"❌ Отсутствует метод {method}")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания стратегии: {e}")
        return False

def test_cumdelta_factory_functions():
    """Тест фабричных функций"""
    print("\n🔍 Тестирование фабричных функций...")
    
    try:
        from bot.strategy.implementations.cumdelta_sr_strategy import (
            create_cumdelta_sr_strategy,
            create_conservative_cumdelta_sr,
            create_aggressive_cumdelta_sr
        )
        
        # Тест базовой фабричной функции
        strategy1 = create_cumdelta_sr_strategy()
        print(f"✅ Базовая стратегия создана: {strategy1.config.strategy_name}")
        
        # Тест консервативной стратегии
        strategy2 = create_conservative_cumdelta_sr()
        print(f"✅ Консервативная стратегия создана: {strategy2.config.strategy_name}")
        print(f"   min_delta_threshold: {strategy2.config.min_delta_threshold}")
        print(f"   confluence_required: {strategy2.config.confluence_required}")
        
        # Тест агрессивной стратегии
        strategy3 = create_aggressive_cumdelta_sr()
        print(f"✅ Агрессивная стратегия создана: {strategy3.config.strategy_name}")
        print(f"   min_delta_threshold: {strategy3.config.min_delta_threshold}")
        print(f"   confluence_required: {strategy3.config.confluence_required}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка фабричных функций: {e}")
        return False

def test_cumdelta_integration():
    """Тест интеграции с системой"""
    print("\n🔍 Тестирование интеграции с системой...")
    
    try:
        from bot.strategy.implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
        from bot.strategy.base import CumDeltaConfig
        
        # Создание стратегии
        config = CumDeltaConfig()
        strategy = CumDeltaSRStrategy(config)
        
        # Проверка интеграции с базовой архитектурой
        if hasattr(strategy, 'current_market_regime'):
            print("✅ Интеграция с рыночным режимом")
        else:
            print("❌ Отсутствует интеграция с рыночным режимом")
        
        if hasattr(strategy, 'is_active'):
            print("✅ Интеграция с системой активности")
        else:
            print("❌ Отсутствует интеграция с системой активности")
        
        # Проверка методов базовой архитектуры
        base_methods = [
            'get_primary_dataframe',
            'calculate_base_indicators',
            'calculate_dynamic_levels',
            'create_signal',
            'is_in_position'
        ]
        
        for method in base_methods:
            if hasattr(strategy, method):
                print(f"✅ Базовый метод {method} доступен")
            else:
                print(f"❌ Отсутствует базовый метод {method}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка интеграции: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🚀 Тестирование CumDelta SR стратегии на предмет адаптации к системе")
    print("=" * 70)
    
    tests = [
        test_cumdelta_strategy_imports,
        test_cumdelta_config,
        test_cumdelta_strategy_creation,
        test_cumdelta_factory_functions,
        test_cumdelta_integration
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
    
    print("\n" + "=" * 70)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов прошли успешно")
    
    if passed == total:
        print("🎉 CumDelta SR стратегия полностью адаптирована к системе!")
        return True
    else:
        print("⚠️  Обнаружены проблемы с адаптацией CumDelta SR стратегии")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
