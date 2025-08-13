"""

# -----------------------------------------------------------------------------
# bot/strategy/factory/strategy_factory.py - Фабрика стратегий
# -----------------------------------------------------------------------------

FACTORY_FILE_STRUCTURE = """
from typing import Dict, Any, Type, Optional
import logging
from ..base import BaseStrategy, BaseStrategyConfig
from ..implementations import (
    VolumeVWAPStrategy,
    CumDeltaSRStrategy, 
    MultiTFVolumeStrategy
)
from .registry import StrategyRegistry

class StrategyFactory:
    '''Фабрика для создания стратегий'''
    
    logger = logging.getLogger(__name__)
    
    @staticmethod
    def create_strategy(strategy_name: str, config: BaseStrategyConfig) -> BaseStrategy:
        '''Создание стратегии по имени и конфигурации'''
        
        strategy_class = StrategyRegistry.get_strategy(strategy_name)
        if strategy_class is None:
            available = StrategyRegistry.list_strategies()
            raise ValueError(f"Стратегия '{strategy_name}' не найдена. Доступные: {available}")
        
        try:
            strategy = strategy_class(config)
            StrategyFactory.logger.info(f"Создана стратегия: {strategy_name}")
            return strategy
        except Exception as e:
            StrategyFactory.logger.error(f"Ошибка создания стратегии {strategy_name}: {e}")
            raise
    
    @staticmethod
    def create_from_dict(config_dict: Dict[str, Any]) -> BaseStrategy:
        '''Создание стратегии из словаря конфигурации'''
        
        strategy_name = config_dict.pop('strategy_name')
        config_class = StrategyRegistry.get_config_class(strategy_name)
        
        if config_class is None:
            raise ValueError(f"Конфигурация для стратегии '{strategy_name}' не найдена")
        
        config = config_class.from_dict(config_dict)
        return StrategyFactory.create_strategy(strategy_name, config)
    
    @staticmethod
    def create_preset(preset_name: str, **overrides) -> BaseStrategy:
        '''Создание стратегии из предустановки'''
        
        presets = {
            'conservative_vwap': {
                'strategy_name': 'volume_vwap',
                'volume_multiplier': 4.0,
                'signal_strength_threshold': 0.8,
                'risk_reward_ratio': 1.2
            },
            'aggressive_delta': {
                'strategy_name': 'cumdelta_sr',
                'min_delta_threshold': 50.0,
                'signal_strength_threshold': 0.5,
                'risk_reward_ratio': 2.0
            },
            'mtf_scalping': {
                'strategy_name': 'multitf_volume',
                'fast_tf': '1m',
                'slow_tf': '5m',
                'volume_multiplier': 3.0
            }
        }
        
        if preset_name not in presets:
            available = list(presets.keys())
            raise ValueError(f"Пресет '{preset_name}' не найден. Доступные: {available}")
        
        config_dict = presets[preset_name].copy()
        config_dict.update(overrides)
        
        return StrategyFactory.create_from_dict(config_dict)