# bot/strategy/base/factory_mixin.py
"""
Универсальный миксин для фабричных функций стратегий
Устраняет дублирование кода создания стратегий
"""

from __future__ import annotations

from typing import Dict, Any, Optional, Type, TypeVar, Generic
from abc import ABC, abstractmethod
import inspect

T = TypeVar('T', bound='BaseStrategy')


class StrategyFactoryMixin(Generic[T]):
    """
    Миксин для унификации фабричных функций создания стратегий.

    Устраняет дублирование логики создания стратегий с конфигурациями.
    """

    @classmethod
    def create_strategy(
        cls: Type[T],
        config: Optional[Any] = None,
        **kwargs
    ) -> T:
        """
        Универсальная фабричная функция для создания стратегии.

        Args:
            config: Конфигурация стратегии (опционально)
            **kwargs: Дополнительные параметры конфигурации

        Returns:
            Экземпляр стратегии
        """

        # Получение типа конфигурации из сигнатуры __init__
        config_class = cls._get_config_class()

        # Создание конфигурации если не передана
        if config is None:
            if config_class:
                config = config_class()
            else:
                raise ValueError(f"Не удалось определить тип конфигурации для {cls.__name__}")

        # Обновление конфигурации дополнительными параметрами
        if kwargs:
            config = cls._merge_config_kwargs(config, kwargs)

        return cls(config)

    @classmethod
    def create_preset(
        cls: Type[T],
        preset_name: str,
        **override_kwargs
    ) -> T:
        """
        Создание стратегии по предустановленному пресету.

        Args:
            preset_name: Имя пресета ('conservative', 'aggressive', 'custom')
            **override_kwargs: Параметры для переопределения пресета

        Returns:
            Экземпляр стратегии с настройками пресета
        """

        presets = cls._get_strategy_presets()

        if preset_name not in presets:
            available_presets = list(presets.keys())
            raise ValueError(
                f"Пресет '{preset_name}' не найден для {cls.__name__}. "
                f"Доступные пресеты: {available_presets}"
            )

        preset_config = presets[preset_name]

        # Применение переопределений
        if override_kwargs:
            preset_config = cls._merge_config_kwargs(preset_config, override_kwargs)

        return cls(preset_config)

    @classmethod
    def create_conservative(cls: Type[T], **kwargs) -> T:
        """Быстрое создание консервативной версии стратегии."""
        return cls.create_preset('conservative', **kwargs)

    @classmethod
    def create_aggressive(cls: Type[T], **kwargs) -> T:
        """Быстрое создание агрессивной версии стратегии."""
        return cls.create_preset('aggressive', **kwargs)

    @classmethod
    def create_balanced(cls: Type[T], **kwargs) -> T:
        """Быстрое создание сбалансированной версии стратегии."""
        return cls.create_preset('balanced', **kwargs)

    @classmethod
    def list_presets(cls) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка доступных пресетов и их описаний.

        Returns:
            Dict с пресетами и их конфигурациями
        """
        return cls._get_strategy_presets()

    @classmethod
    def get_default_config(cls) -> Any:
        """Получение конфигурации по умолчанию."""
        config_class = cls._get_config_class()
        if config_class:
            return config_class()
        raise ValueError(f"Не удалось определить тип конфигурации для {cls.__name__}")

    @classmethod
    def _get_config_class(cls) -> Optional[Type]:
        """Автоматическое определение класса конфигурации из сигнатуры __init__."""
        try:
            # Получение сигнатуры конструктора
            init_signature = inspect.signature(cls.__init__)
            parameters = list(init_signature.parameters.values())

            # Поиск параметра config (обычно второй после self)
            for param in parameters:
                if param.name == 'config' and param.annotation != inspect.Parameter.empty:
                    annotation = param.annotation

                    # Если аннотация - строка (из-за from __future__ import annotations),
                    # пытаемся разрешить её в реальный класс
                    if isinstance(annotation, str):
                        try:
                            # Получаем модуль стратегии
                            module = inspect.getmodule(cls)
                            if module and hasattr(module, annotation):
                                return getattr(module, annotation)

                            # Попытка импорта из base config модуля
                            from .. import base
                            if hasattr(base, annotation):
                                return getattr(base, annotation)

                            # Попытка поиска в globals стратегии
                            if annotation in module.__dict__:
                                return module.__dict__[annotation]

                        except Exception:
                            pass
                    else:
                        return annotation

            return None
        except Exception:
            return None

    @classmethod
    def _merge_config_kwargs(cls, config: Any, kwargs: Dict[str, Any]) -> Any:
        """
        Слияние конфигурации с дополнительными параметрами.

        Поддерживает разные типы конфигураций (dataclass, dict, custom).
        """

        if not kwargs:
            return config

        # Случай 1: Конфигурация с методом copy (dataclass с custom copy)
        if hasattr(config, 'copy') and callable(config.copy):
            try:
                return config.copy(**kwargs)
            except Exception:
                pass

        # Случай 2: Конфигурация с методом to_dict/from_dict
        if hasattr(config, 'to_dict') and hasattr(config, 'from_dict'):
            try:
                config_dict = config.to_dict()
                config_dict.update(kwargs)
                return config.from_dict(config_dict)
            except Exception:
                pass

        # Случай 3: Dataclass
        if hasattr(config, '__dataclass_fields__'):
            try:
                # Создание нового экземпляра с обновленными полями
                config_dict = {
                    field.name: getattr(config, field.name)
                    for field in config.__dataclass_fields__.values()
                }
                config_dict.update(kwargs)
                return config.__class__(**config_dict)
            except Exception:
                pass

        # Случай 4: Обычный объект с атрибутами
        try:
            # Создание копии и обновление атрибутов
            import copy
            new_config = copy.deepcopy(config)
            for key, value in kwargs.items():
                if hasattr(new_config, key):
                    setattr(new_config, key, value)
            return new_config
        except Exception:
            pass

        # Fallback: возврат оригинальной конфигурации
        cls._log_config_merge_warning(config, kwargs)
        return config

    @classmethod
    def _get_strategy_presets(cls) -> Dict[str, Any]:
        """
        Получение предустановленных конфигураций для стратегии.

        Может быть переопределен в наследниках для кастомных пресетов.
        """

        config_class = cls._get_config_class()
        if not config_class:
            return {}

        # Базовые пресеты (могут быть переопределены)
        try:
            conservative_config = config_class(
                risk_reward_ratio=2.0,
                signal_strength_threshold=0.7,
                confluence_required=3,
                max_risk_per_trade_pct=0.5,
            )
        except Exception:
            conservative_config = config_class()

        try:
            aggressive_config = config_class(
                risk_reward_ratio=1.2,
                signal_strength_threshold=0.5,
                confluence_required=1,
                max_risk_per_trade_pct=1.5,
            )
        except Exception:
            aggressive_config = config_class()

        try:
            balanced_config = config_class(
                risk_reward_ratio=1.5,
                signal_strength_threshold=0.6,
                confluence_required=2,
                max_risk_per_trade_pct=1.0,
            )
        except Exception:
            balanced_config = config_class()

        presets = {
            'conservative': conservative_config,
            'aggressive': aggressive_config,
            'balanced': balanced_config,
        }

        # Добавление стратегии-специфичных пресетов
        custom_presets = cls._get_custom_presets()
        presets.update(custom_presets)

        return presets

    @classmethod
    def _get_custom_presets(cls) -> Dict[str, Any]:
        """
        Кастомные пресеты для конкретной стратегии.

        Переопределяется в наследниках для добавления специфичных пресетов.
        """
        return {}

    @classmethod
    def _log_config_merge_warning(cls, config: Any, kwargs: Dict[str, Any]) -> None:
        """Логирование предупреждения о невозможности слияния конфигурации."""
        try:
            import logging
            logger = logging.getLogger(cls.__name__)
            logger.warning(
                f"Не удалось объединить конфигурацию {type(config).__name__} "
                f"с параметрами {list(kwargs.keys())}. Используется оригинальная конфигурация."
            )
        except Exception:
            pass  # Игнорируем ошибки логирования


# =========================================================================
# АБСТРАКТНЫЙ КЛАСС ДЛЯ СТРАТЕГИЙ С ПРЕСЕТАМИ
# =========================================================================

class PresetStrategy(StrategyFactoryMixin, ABC):
    """
    Абстрактный базовый класс для стратегий с поддержкой пресетов.

    Наследники должны определить метод _get_custom_presets() для специфичных пресетов.
    """

    @classmethod
    @abstractmethod
    def _get_custom_presets(cls) -> Dict[str, Any]:
        """Определение кастомных пресетов для конкретной стратегии."""
        pass


# =========================================================================
# ДЕКОРАТОР ДЛЯ АВТОМАТИЧЕСКОЙ ИНТЕГРАЦИИ
# =========================================================================

def with_factory_methods(*preset_names: str):
    """
    Декоратор для автоматического добавления фабричных методов.

    Args:
        *preset_names: Имена пресетов для создания быстрых методов

    Usage:
        @with_factory_methods('scalping', 'swing')
        class MyStrategy(BaseStrategy):
            pass

        # Автоматически создаются методы:
        # MyStrategy.create_scalping()
        # MyStrategy.create_swing()
    """

    def decorator(cls):
        # Добавление базового миксина
        if not issubclass(cls, StrategyFactoryMixin):
            # Создание нового класса с миксином
            class_name = cls.__name__
            new_cls = type(class_name, (StrategyFactoryMixin, cls), {})
            new_cls.__module__ = cls.__module__
            cls = new_cls

        # Создание быстрых методов для пресетов
        for preset_name in preset_names:
            method_name = f'create_{preset_name}'

            def make_preset_method(name):
                def preset_method(cls_inner, **kwargs):
                    return cls_inner.create_preset(name, **kwargs)
                return classmethod(preset_method)

            setattr(cls, method_name, make_preset_method(preset_name))

        return cls

    return decorator


# =========================================================================
# УТИЛИТЫ ДЛЯ РАБОТЫ С КОНФИГУРАЦИЯМИ
# =========================================================================

class ConfigUtils:
    """Утилиты для работы с конфигурациями стратегий."""

    @staticmethod
    def compare_configs(config1: Any, config2: Any) -> Dict[str, Any]:
        """
        Сравнение двух конфигураций и выявление различий.

        Returns:
            Dict с различиями между конфигурациями
        """

        differences = {}

        # Получение полей конфигураций
        fields1 = ConfigUtils._get_config_fields(config1)
        fields2 = ConfigUtils._get_config_fields(config2)

        all_fields = set(fields1.keys()) | set(fields2.keys())

        for field in all_fields:
            value1 = fields1.get(field, '<missing>')
            value2 = fields2.get(field, '<missing>')

            if value1 != value2:
                differences[field] = {
                    'config1': value1,
                    'config2': value2,
                }

        return differences

    @staticmethod
    def _get_config_fields(config: Any) -> Dict[str, Any]:
        """Извлечение полей из конфигурации."""

        if hasattr(config, '__dataclass_fields__'):
            # Dataclass
            return {
                field.name: getattr(config, field.name)
                for field in config.__dataclass_fields__.values()
            }
        elif hasattr(config, '__dict__'):
            # Обычный объект
            return {
                key: value for key, value in config.__dict__.items()
                if not key.startswith('_')
            }
        else:
            return {}

    @staticmethod
    def validate_config(config: Any, required_fields: List[str]) -> List[str]:
        """
        Валидация конфигурации на наличие обязательных полей.

        Returns:
            Список отсутствующих обязательных полей
        """

        missing_fields = []
        fields = ConfigUtils._get_config_fields(config)

        for field in required_fields:
            if field not in fields:
                missing_fields.append(field)

        return missing_fields