"""
Основной модуль стратегий - экспорт реальных стратегий для MVP
"""

# Импорт существующих профессиональных стратегий
try:
    from .implementations.volume_vwap_strategy import VolumeVWAPStrategy
    from .implementations.cumdelta_sr_strategy import CumDeltaSRStrategy
    from .implementations.multitf_volume_strategy import MultiTFVolumeStrategy

    # Алиасы для совместимости с конфигом
    VolumeVWAP = VolumeVWAPStrategy
    CumDeltaSR = CumDeltaSRStrategy
    MultiTFVolume = MultiTFVolumeStrategy

except ImportError as e:
    # Fallback на MVP стратегию если импорт не удался
    import logging
    logging.getLogger(__name__).warning(f"Не удалось импортировать стратегии: {e}, используем MVP")
    from .simple_mvp_strategy import SimpleMVPStrategy, VolumeVWAP, CumDeltaSR, MultiTFVolume

# Экспорт основных классов
__all__ = ['VolumeVWAP', 'CumDeltaSR', 'MultiTFVolume']