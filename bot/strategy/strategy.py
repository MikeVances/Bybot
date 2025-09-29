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
                    import logging
                    logging.debug(f"✅ Загружена стратегия: {attr_name}")

        except ImportError as e:
            import logging
            logging.warning(f"⚠️ Не удалось загрузить {module_name}: {e}")

    # Создаем алиасы для совместимости
    VolumeVWAP = strategy_classes.get('VolumeVWAPStrategyV3')
    CumDeltaSR = strategy_classes.get('CumDeltaSRStrategyV3')
    MultiTFVolume = strategy_classes.get('MultiTFVolumeStrategyV3')
    FibonacciRSI = strategy_classes.get('FibonacciRSIStrategyV3')
    RangeTrading = strategy_classes.get('RangeTradingStrategyV3')

    import logging
    logging.info(f"🎯 Динамически загружено {len(strategy_classes)} стратегий v3")

except ImportError as e:
    # Fallback на MVP стратегию если импорт не удался
    import logging
    logging.getLogger(__name__).warning(f"Не удалось импортировать стратегии: {e}, используем MVP")
    from .simple_mvp_strategy import SimpleMVPStrategy, VolumeVWAP, CumDeltaSR, MultiTFVolume

# Фабричные функции для обратной совместимости с v2 API
def create_volume_vwap_strategy(config=None):
    """Создание Volume VWAP стратегии (обратная совместимость)"""
    if VolumeVWAP:
        return VolumeVWAP.create_strategy(config or {})
    return None

def create_cumdelta_sr_strategy(config=None):
    """Создание CumDelta SR стратегии (обратная совместимость)"""
    if CumDeltaSR:
        return CumDeltaSR.create_strategy(config or {})
    return None

def create_multitf_volume_strategy(config=None):
    """Создание MultiTF Volume стратегии (обратная совместимость)"""
    if MultiTFVolume:
        return MultiTFVolume.create_strategy(config or {})
    return None

def create_fibonacci_rsi_strategy(config=None):
    """Создание Fibonacci RSI стратегии (обратная совместимость)"""
    if FibonacciRSI:
        return FibonacciRSI.create_strategy(config or {})
    return None

def create_range_trading_strategy(config=None):
    """Создание Range Trading стратегии (обратная совместимость)"""
    if RangeTrading:
        return RangeTrading.create_strategy(config or {})
    return None

# Экспорт основных классов и функций
__all__ = [
    'VolumeVWAP', 'CumDeltaSR', 'MultiTFVolume', 'FibonacciRSI', 'RangeTrading',
    'create_volume_vwap_strategy', 'create_cumdelta_sr_strategy',
    'create_multitf_volume_strategy', 'create_fibonacci_rsi_strategy',
    'create_range_trading_strategy'
]