"""
Основной модуль стратегий - экспорт реальных стратегий для MVP
"""

# Динамический импорт всех v3 стратегий
try:
    import os
    import importlib
    from pathlib import Path

    # Получаем путь к папке implementations
    implementations_dir = Path(__file__).parent / 'implementations'

    # Динамически найдем все v3 стратегии
    strategy_classes = {}

    # Сканируем папку implementations
    for file_path in implementations_dir.glob('*_strategy_v3.py'):
        module_name = file_path.stem  # имя файла без .py

        try:
            # Импортируем модуль
            module = importlib.import_module(f'.implementations.{module_name}', package='bot.strategy')

            # Ищем класс стратегии в модуле (должен заканчиваться на V3)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    attr_name.endswith('V3') and
                    hasattr(attr, 'strategy_type')):

                    strategy_classes[attr_name] = attr
                    print(f"✅ Загружена стратегия: {attr_name}")

        except ImportError as e:
            print(f"⚠️ Не удалось загрузить {module_name}: {e}")

    # Создаем алиасы для совместимости
    VolumeVWAP = strategy_classes.get('VolumeVWAPStrategyV3')
    CumDeltaSR = strategy_classes.get('CumDeltaSRStrategyV3')
    MultiTFVolume = strategy_classes.get('MultiTFVolumeStrategyV3')
    FibonacciRSI = strategy_classes.get('FibonacciRSIStrategyV3')
    RangeTrading = strategy_classes.get('RangeTradingStrategyV3')

    print(f"🎯 Динамически загружено {len(strategy_classes)} стратегий v3")

except ImportError as e:
    # Fallback на MVP стратегию если импорт не удался
    import logging
    logging.getLogger(__name__).warning(f"Не удалось импортировать стратегии: {e}, используем MVP")
    from .simple_mvp_strategy import SimpleMVPStrategy, VolumeVWAP, CumDeltaSR, MultiTFVolume

# Экспорт основных классов
__all__ = ['VolumeVWAP', 'CumDeltaSR', 'MultiTFVolume', 'FibonacciRSI', 'RangeTrading']