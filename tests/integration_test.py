# integration_test.py
"""
Скрипт интеграционного тестирования обновленной архитектуры торгового бота
Проверяет совместимость всех компонентов системы
"""

import sys
import os
import logging
import traceback
from datetime import datetime
from typing import Dict, Any

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def test_basic_imports():
    """Тест базовых импортов"""
    logger.info("🔍 Тестирование базовых импортов...")
    
    test_results = {}
    
    # 1. Базовая архитектура
    try:
        from bot.strategy.base import (
            BaseStrategy, VolumeVWAPConfig, MarketRegime, 
            SignalType, ConfluenceFactor, get_version_info
        )
        test_results['base_architecture'] = True
        logger.info("✅ Базовая архитектура импортирована")
    except Exception as e:
        test_results['base_architecture'] = False
        logger.error(f"❌ Ошибка импорта базовой архитектуры: {e}")
    
    # 2. VolumeVWAP стратегия
    try:
        from bot.strategy.implementations.volume_vwap_strategy import (
            VolumeVWAPStrategy, create_volume_vwap_strategy
        )
        test_results['volume_vwap_strategy'] = True
        logger.info("✅ VolumeVWAP стратегия импортирована")
    except Exception as e:
        test_results['volume_vwap_strategy'] = False
        logger.error(f"❌ Ошибка импорта VolumeVWAP стратегии: {e}")
    
    # 3. Утилиты
    try:
        from bot.strategy.utils.indicators import TechnicalIndicators
        from bot.strategy.utils.validators import DataValidator
        from bot.strategy.utils.market_analysis import MarketRegimeAnalyzer
        test_results['utilities'] = True
        logger.info("✅ Утилиты импортированы")
    except Exception as e:
        test_results['utilities'] = False
        logger.error(f"❌ Ошибка импорта утилит: {e}")
    
    # 4. Основные компоненты бота (опционально)
    try:
        # Эти импорты могут не работать если нет остальных модулей
        from bot.config_manager import config
        test_results['bot_core'] = True
        logger.info("✅ Основные компоненты бота доступны")
    except Exception as e:
        test_results['bot_core'] = False
        logger.warning(f"⚠️ Основные компоненты бота недоступны: {e}")
    
    return test_results


def test_strategy_manager():
    """Тест менеджера стратегий"""
    logger.info("🔍 Тестирование менеджера стратегий...")
    
    try:
        # Импортируем из main.py
        from main import StrategyManager
        
        # Создаем менеджер
        strategy_manager = StrategyManager()
        
        # Тестируем инициализацию
        init_success = strategy_manager.initialize_strategies()
        
        if init_success:
            logger.info("✅ Менеджер стратегий инициализирован")
            
            # Получаем информацию о стратегиях
            info = strategy_manager.get_strategy_info()
            logger.info(f"📊 Стратегий: {info['total_strategies']}, Активных: {info['active_strategies']}")
            logger.info(f"📋 Доступные: {info['strategy_names']}")
            logger.info(f"🎯 Активные: {info['active_names']}")
            
            return True
        else:
            logger.error("❌ Не удалось инициализировать менеджер стратегий")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования менеджера стратегий: {e}")
        logger.error(traceback.format_exc())
        return False


def test_strategy_execution():
    """Тест выполнения стратегий"""
    logger.info("🔍 Тестирование выполнения стратегий...")
    
    try:
        # Создаем тестовые данные
        import pandas as pd
        import numpy as np
        from datetime import datetime, timedelta
        
        # Генерируем простые тестовые данные
        dates = pd.date_range(start=datetime.now() - timedelta(days=1), periods=100, freq='5min')
        
        np.random.seed(42)
        base_price = 45000
        prices = base_price + np.cumsum(np.random.normal(0, 50, 100))
        
        test_data = pd.DataFrame({
            'timestamp': dates,
            'open': prices + np.random.normal(0, 10, 100),
            'high': prices + np.abs(np.random.normal(0, 20, 100)),
            'low': prices - np.abs(np.random.normal(0, 20, 100)),
            'close': prices,
            'volume': np.random.normal(1000000, 200000, 100)
        })
        
        test_data.set_index('timestamp', inplace=True)
        
        # Создаем стратегию
        from bot.strategy.implementations.volume_vwap_strategy import create_volume_vwap_strategy
        
        strategy = create_volume_vwap_strategy()
        
        # Тестируем расчет индикаторов
        indicators = strategy.calculate_strategy_indicators(test_data)
        
        if indicators:
            logger.info(f"✅ Индикаторы рассчитаны: {len(indicators)} штук")
            
            # Тестируем выполнение стратегии
            mock_state = {'position': None, 'balance': 10000}
            
            signal = strategy.execute(test_data, mock_state, symbol='BTCUSDT')
            
            if signal:
                logger.info(f"✅ Стратегия сгенерировала сигнал: {signal['signal']}")
                logger.info(f"📊 Сила сигнала: {signal['signal_strength']:.3f}")
                logger.info(f"🎯 Confluence факторов: {len(signal['confluence_factors'])}")
                return True
            else:
                logger.info("ℹ️ Стратегия не сгенерировала сигнал (нормально для тестовых данных)")
                return True
        else:
            logger.error("❌ Не удалось рассчитать индикаторы")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования выполнения стратегий: {e}")
        logger.error(traceback.format_exc())
        return False


def test_data_validation():
    """Тест валидации данных"""
    logger.info("🔍 Тестирование валидации данных...")
    
    try:
        from bot.strategy.utils.validators import DataValidator, ValidationLevel
        
        # Создаем валидатор (используем статические методы)
        validator = DataValidator
        
        # Создаем тестовые данные
        import pandas as pd
        import numpy as np
        
        # Создаем больше данных для валидации
        dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')
        np.random.seed(42)
        base_price = 45000
        prices = base_price + np.cumsum(np.random.normal(0, 50, 60))
        
        test_data = pd.DataFrame({
            'open': prices + np.random.normal(0, 10, 60),
            'high': prices + np.abs(np.random.normal(0, 20, 60)),
            'low': prices - np.abs(np.random.normal(0, 20, 60)),
            'close': prices,
            'volume': np.random.normal(1000000, 200000, 60)
        }, index=dates)
        
        # Тестируем валидацию
        result = validator.validate_basic_data(test_data)
        
        if result.is_valid:
            logger.info(f"✅ Данные валидны, качество: {result.quality.value}")
            return True
        else:
            logger.info(f"⚠️ Данные невалидны: {result.errors}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования валидации: {e}")
        return False


def test_market_analysis():
    """Тест анализа рынка"""
    logger.info("🔍 Тестирование анализа рынка...")
    
    try:
        from bot.strategy.utils.market_analysis import MarketRegimeAnalyzer
        
        # Создаем анализатор
        analyzer = MarketRegimeAnalyzer()
        
        # Создаем тестовые данные
        import pandas as pd
        import numpy as np
        
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
        prices = 45000 + np.cumsum(np.random.normal(0, 100, 50))
        
        test_data = pd.DataFrame({
            'open': prices + np.random.normal(0, 50, 50),
            'high': prices + np.abs(np.random.normal(0, 100, 50)),
            'low': prices - np.abs(np.random.normal(0, 100, 50)),
            'close': prices,
            'volume': np.random.normal(1000000, 300000, 50)
        }, index=dates)
        
        # Анализируем рынок
        analysis = analyzer.analyze_market_condition(test_data)
        
        logger.info(f"✅ Режим рынка: {analysis.regime.value}")
        logger.info(f"📈 Направление тренда: {analysis.trend_direction}")
        logger.info(f"💪 Сила тренда: {analysis.trend_strength:.2f}")
        logger.info(f"🎯 Уверенность: {analysis.confidence:.2f}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования анализа рынка: {e}")
        return False


def test_technical_indicators():
    """Тест технических индикаторов"""
    logger.info("🔍 Тестирование технических индикаторов...")
    
    try:
        from bot.strategy.utils.indicators import TechnicalIndicators
        
        # Создаем тестовые данные
        import pandas as pd
        import numpy as np
        
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
        prices = 45000 + np.cumsum(np.random.normal(0, 100, 50))
        
        test_data = pd.DataFrame({
            'open': prices + np.random.normal(0, 50, 50),
            'high': prices + np.abs(np.random.normal(0, 100, 50)),
            'low': prices - np.abs(np.random.normal(0, 100, 50)),
            'close': prices,
            'volume': np.random.normal(1000000, 300000, 50)
        }, index=dates)
        
        # Тестируем различные индикаторы
        indicators_tested = 0
        
        # RSI
        rsi_result = TechnicalIndicators.calculate_rsi(test_data)
        if rsi_result.is_valid:
            indicators_tested += 1
            logger.info(f"✅ RSI: {rsi_result.last_value:.2f}")
        
        # VWAP
        vwap_result = TechnicalIndicators.calculate_vwap(test_data)
        if vwap_result.is_valid:
            indicators_tested += 1
            logger.info(f"✅ VWAP: {vwap_result.last_value:.2f}")
        
        # ATR
        atr_result = TechnicalIndicators.calculate_atr_safe(test_data)
        if atr_result.is_valid:
            indicators_tested += 1
            logger.info(f"✅ ATR: {atr_result.value:.2f}")
        
        # Bollinger Bands
        bb_result = TechnicalIndicators.calculate_bollinger_bands(test_data)
        if bb_result.is_valid:
            indicators_tested += 1
            logger.info(f"✅ Bollinger Bands: позиция {bb_result.value['position'].iloc[-1]:.2f}")
        
        logger.info(f"✅ Протестировано индикаторов: {indicators_tested}/4")
        return indicators_tested >= 3
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования индикаторов: {e}")
        return False


def run_comprehensive_integration_test():
    """Запуск комплексного интеграционного тестирования"""
    logger.info("🚀 Начало комплексного интеграционного тестирования")
    logger.info("=" * 80)
    
    test_results = {}
    
    # Тесты
    tests = [
        ("Базовые импорты", test_basic_imports),
        ("Менеджер стратегий", test_strategy_manager),
        ("Выполнение стратегий", test_strategy_execution),
        ("Валидация данных", test_data_validation),
        ("Анализ рынка", test_market_analysis),
        ("Технические индикаторы", test_technical_indicators)
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n--- Тест: {test_name} ---")
        try:
            if test_name == "Базовые импорты":
                # Этот тест возвращает словарь
                result_dict = test_func()
                result = all(result_dict.values())
                test_results[test_name] = result_dict
            else:
                result = test_func()
                test_results[test_name] = result
            
            if result:
                logger.info(f"✅ {test_name}: ПРОЙДЕН")
                passed_tests += 1
            else:
                logger.error(f"❌ {test_name}: ПРОВАЛЕН")
                
        except Exception as e:
            logger.error(f"💥 {test_name}: ОШИБКА - {e}")
            test_results[test_name] = False
    
    # Итоговый отчет
    logger.info("\n" + "=" * 80)
    logger.info("📋 ИТОГОВЫЙ ОТЧЕТ ИНТЕГРАЦИОННОГО ТЕСТИРОВАНИЯ")
    logger.info("=" * 80)
    
    for test_name, result in test_results.items():
        if isinstance(result, dict):
            # Для теста импортов показываем детали
            logger.info(f"{test_name}:")
            for subtest, subresult in result.items():
                status = "✅" if subresult else "❌"
                logger.info(f"  {status} {subtest}")
        else:
            status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
            logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n📊 ИТОГО: {passed_tests}/{total_tests} тестов пройдено")
    
    if passed_tests == total_tests:
        logger.info("🎉 ВСЕ ИНТЕГРАЦИОННЫЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        logger.info("🚀 Система готова к запуску!")
        return True
    else:
        logger.warning(f"⚠️ {total_tests - passed_tests} тестов провалено")
        logger.warning("🔧 Требуется исправление ошибок перед запуском")
        return False


if __name__ == "__main__":
    try:
        success = run_comprehensive_integration_test()
        
        if success:
            print("\n" + "="*60)
            print("🎉 ИНТЕГРАЦИОННОЕ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО!")
            print("🚀 Можно запускать торгового бота: python main.py")
            print("="*60)
            sys.exit(0)
        else:
            print("\n" + "="*60)
            print("❌ ИНТЕГРАЦИОННОЕ ТЕСТИРОВАНИЕ ПРОВАЛЕНО!")
            print("🔧 Исправьте ошибки перед запуском бота")
            print("="*60)
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\n❌ Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n💥 Критическая ошибка тестирования: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)