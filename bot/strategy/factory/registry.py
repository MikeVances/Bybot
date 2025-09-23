"""Простой реестр стратегий для фабрики новой архитектуры."""

from typing import Dict, Optional, Type


class StrategyRegistry:
    """Хранилище соответствий стратегий и их конфигураций."""

    _strategy_classes: Dict[str, str] = {
        'volume_vwap': 'bot.strategy.implementations.volume_vwap_strategy:VolumeVWAPStrategy',
        'cumdelta_sr': 'bot.strategy.implementations.cumdelta_sr_strategy:CumDeltaSRStrategy',
        'multitf_volume': 'bot.strategy.implementations.multitf_volume_strategy:MultiTFVolumeStrategy',
        'fibonacci_rsi': 'bot.strategy.implementations.fibonacci_rsi_strategy:FibonacciRSIStrategy',
        'range_trading': 'bot.strategy.implementations.range_trading_strategy:RangeTradingStrategy',
    }

    _config_classes: Dict[str, str] = {
        'volume_vwap': 'bot.strategy.base.config:VolumeVWAPConfig',
        'cumdelta_sr': 'bot.strategy.base.config:CumDeltaConfig',
        'multitf_volume': 'bot.strategy.base.config:MultiTFConfig',
        'fibonacci_rsi': 'bot.strategy.base.config:BaseStrategyConfig',
        'range_trading': 'bot.strategy.base.config:BaseStrategyConfig',
    }

    @classmethod
    def register_strategy(cls, name: str, dotted_path: str) -> None:
        cls._strategy_classes[name] = dotted_path

    @classmethod
    def register_config(cls, name: str, dotted_path: str) -> None:
        cls._config_classes[name] = dotted_path

    @classmethod
    def _resolve(cls, dotted_path: str) -> Optional[Type]:
        try:
            module_path, attr = dotted_path.split(":", 1)
            module = __import__(module_path, fromlist=[attr])
            return getattr(module, attr)
        except (ValueError, ImportError, AttributeError):
            return None

    @classmethod
    def get_strategy(cls, name: str) -> Optional[Type]:
        dotted_path = cls._strategy_classes.get(name)
        if not dotted_path:
            return None
        return cls._resolve(dotted_path)

    @classmethod
    def get_config_class(cls, name: str) -> Optional[Type]:
        base_name = name
        if name.endswith('_strategy'):
            base_name = name.replace('_strategy', '')
        dotted_path = cls._config_classes.get(base_name)
        if not dotted_path:
            return None
        return cls._resolve(dotted_path)

    @classmethod
    def list_strategies(cls) -> Dict[str, str]:
        return dict(cls._strategy_classes)
