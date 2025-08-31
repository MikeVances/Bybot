# bot/services/ux_config.py
# 💜 UX КОНФИГУРАЦИЯ для современного Telegram бота
# Все UX-настройки в одном месте для удобства кастомизации

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

class ThemeMode(Enum):
    """Темы для интерфейса"""
    LIGHT = "light"
    DARK = "dark" 
    AUTO = "auto"
    PURPLE = "purple"  # Наша фирменная тема! 💜

@dataclass
class UXConfig:
    """Конфигурация UX-настроек"""
    
    # 🎨 ВИЗУАЛЬНАЯ ТЕМА
    theme: ThemeMode = ThemeMode.PURPLE
    accent_color: str = "💜"  # Наш фирменный цвет
    
    # ⚡ ПРОИЗВОДИТЕЛЬНОСТЬ
    dashboard_refresh_seconds: int = 30
    live_data_update_seconds: int = 10
    animation_duration_ms: int = 200
    
    # 🔔 УВЕДОМЛЕНИЯ
    enable_push_notifications: bool = True
    enable_sound_alerts: bool = True
    critical_alert_repeat_minutes: int = 5
    
    # 📱 АДАПТИВНОСТЬ
    mobile_first_design: bool = True
    compact_mode_threshold_width: int = 480
    max_items_per_screen: int = 5
    
    # 🤖 ПЕРСОНАЛИЗАЦИЯ
    enable_ai_suggestions: bool = True
    learning_mode: bool = True
    personalized_dashboard: bool = True
    
    # ⚡ QUICK ACTIONS
    quick_actions_enabled: List[str] = None
    
    def __post_init__(self):
        if self.quick_actions_enabled is None:
            self.quick_actions_enabled = [
                "balance_check",
                "position_status", 
                "ai_recommendation",
                "emergency_stop",
                "profit_summary"
            ]

# 🎨 ЭМОДЗИ И ИКОНКИ
class UXEmojis:
    """Единая система эмодзи для консистентного дизайна"""
    
    # Статусы
    SUCCESS = "✅"
    ERROR = "❌" 
    WARNING = "⚠️"
    INFO = "ℹ️"
    LOADING = "⏳"
    
    # Финансы
    MONEY = "💰"
    PROFIT = "📈"
    LOSS = "📉"
    BALANCE = "⚖️"
    
    # AI и технологии
    AI = "🧠"
    ROBOT = "🤖"
    NEURAL = "🔮"
    ALGORITHM = "⚙️"
    
    # Действия
    PLAY = "▶️"
    STOP = "⏹️"
    PAUSE = "⏸️"
    REFRESH = "🔄"
    SETTINGS = "⚙️"
    
    # Навигация
    BACK = "🔙"
    FORWARD = "➡️"
    UP = "⬆️"
    DOWN = "⬇️"
    
    # Приоритеты
    HIGH = "🚨"
    MEDIUM = "⚡"
    LOW = "💡"
    
    # Наша фирменная тема
    PURPLE_HEART = "💜"
    SPARKLES = "✨"
    ROCKET = "🚀"

# 📊 DASHBOARD WIDGETS
class DashboardWidget:
    """Конфигурация виджетов dashboard"""
    
    def __init__(self, name: str, priority: int, enabled: bool = True, 
                 refresh_rate: int = 30, data_source: str = None):
        self.name = name
        self.priority = priority  # 1 = высший приоритет
        self.enabled = enabled
        self.refresh_rate = refresh_rate  # секунды
        self.data_source = data_source

# Предустановленные виджеты
DEFAULT_WIDGETS = [
    DashboardWidget("balance_summary", 1, True, 30, "api.get_balance"),
    DashboardWidget("positions_overview", 2, True, 10, "api.get_positions"),
    DashboardWidget("ai_insights", 3, True, 60, "neural.get_insights"),
    DashboardWidget("alerts_panel", 4, True, 5, "alerts.get_active"),
    DashboardWidget("performance_metrics", 5, True, 300, "analytics.get_summary"),
    DashboardWidget("market_overview", 6, True, 60, "market.get_conditions")
]

# 🎨 ЦВЕТОВАЯ СХЕМА
class ColorScheme:
    """Фирменная цветовая схема"""
    
    # Основные цвета
    PRIMARY = "#8B5CF6"      # Фиолетовый
    SECONDARY = "#A78BFA"    # Светло-фиолетовый
    ACCENT = "#C084FC"       # Акцентный фиолетовый
    
    # Статусы
    SUCCESS = "#10B981"      # Зелёный
    WARNING = "#F59E0B"      # Оранжевый
    ERROR = "#EF4444"        # Красный
    INFO = "#3B82F6"         # Синий
    
    # Нейтральные
    BACKGROUND = "#1F2937"   # Тёмно-серый
    TEXT = "#F9FAFB"         # Почти белый
    TEXT_SECONDARY = "#9CA3AF"  # Серый
    
    # Градиенты
    GRADIENT_PRIMARY = "linear-gradient(135deg, #8B5CF6 0%, #A78BFA 100%)"
    GRADIENT_SUCCESS = "linear-gradient(135deg, #10B981 0%, #34D399 100%)"

# 🔔 ТИПЫ УВЕДОМЛЕНИЙ
class NotificationType(Enum):
    """Типы уведомлений с приоритетами"""
    
    CRITICAL = ("🚨", 1, True)   # Критические (всегда показывать)
    HIGH = ("⚡", 2, True)       # Высокий приоритет
    MEDIUM = ("📊", 3, False)   # Средний приоритет
    LOW = ("💡", 4, False)      # Низкий приоритет
    INFO = ("ℹ️", 5, False)     # Информационные
    
    def __init__(self, emoji: str, priority: int, always_show: bool):
        self.emoji = emoji
        self.priority = priority
        self.always_show = always_show

# 📱 RESPONSIVE BREAKPOINTS
class ResponsiveBreakpoints:
    """Точки адаптивности для разных устройств"""
    
    MOBILE = 480
    TABLET = 768
    DESKTOP = 1024
    
    @staticmethod
    def get_device_type(width: int) -> str:
        """Определяем тип устройства по ширине экрана"""
        if width <= ResponsiveBreakpoints.MOBILE:
            return "mobile"
        elif width <= ResponsiveBreakpoints.TABLET:
            return "tablet"
        else:
            return "desktop"

# ⚡ БЫСТРЫЕ ДЕЙСТВИЯ
QUICK_ACTIONS_CONFIG = {
    "balance_check": {
        "emoji": "💰",
        "title": "Balance",
        "description": "Check current balance",
        "callback": "quick_balance",
        "priority": 1
    },
    "position_status": {
        "emoji": "📊",
        "title": "Positions", 
        "description": "View open positions",
        "callback": "quick_positions",
        "priority": 2
    },
    "ai_recommendation": {
        "emoji": "🧠",
        "title": "AI Insights",
        "description": "Get AI recommendations", 
        "callback": "ai_recommend",
        "priority": 3
    },
    "emergency_stop": {
        "emoji": "🚫",
        "title": "Emergency Stop",
        "description": "Stop all trading",
        "callback": "emergency_stop", 
        "priority": 4,
        "confirmation_required": True
    },
    "profit_summary": {
        "emoji": "📈",
        "title": "P&L",
        "description": "View profit/loss summary",
        "callback": "pnl_summary",
        "priority": 5
    }
}

# 🎯 ПЕРСОНАЛИЗАЦИЯ
class PersonalizationSettings:
    """Настройки персонализации под пользователя"""
    
    def __init__(self):
        self.preferred_timeframes = ["5m", "15m", "1h"]
        self.favorite_strategies = []
        self.dashboard_layout = "compact"  # compact, detailed, custom
        self.notification_preferences = {
            "trade_signals": True,
            "balance_changes": True,  
            "ai_insights": True,
            "system_alerts": True,
            "performance_reports": False
        }
        self.language = "ru"  # ru, en
        self.timezone = "UTC+3"

# 🚀 ЭКСПЕРИМЕНТАЛЬНЫЕ ФИЧИ
class ExperimentalFeatures:
    """Бета-фичи для тестирования"""
    
    VOICE_COMMANDS = False          # Голосовые команды
    AR_VISUALIZATION = False        # AR-визуализация данных
    PREDICTIVE_ALERTS = True        # Предиктивные алерты
    SOCIAL_TRADING = False          # Социальная торговля
    ADVANCED_ANALYTICS = True       # Продвинутая аналитика
    MINI_APPS = True               # Telegram Mini Apps
    WEB_APP_INTEGRATION = True      # Интеграция с Web App

# Создаём глобальный экземпляр конфигурации
ux_config = UXConfig()

# 🎨 HELPER FUNCTIONS
def get_status_emoji(status: str) -> str:
    """Получить эмодзи для статуса"""
    status_map = {
        "active": UXEmojis.SUCCESS,
        "inactive": UXEmojis.ERROR,
        "warning": UXEmojis.WARNING,
        "loading": UXEmojis.LOADING,
        "profit": UXEmojis.PROFIT,
        "loss": UXEmojis.LOSS
    }
    return status_map.get(status.lower(), UXEmojis.INFO)

def format_money(amount: float, currency: str = "USD") -> str:
    """Форматирование денежных сумм"""
    if abs(amount) >= 1000000:
        return f"${amount/1000000:.1f}M"
    elif abs(amount) >= 1000:
        return f"${amount/1000:.1f}K"
    else:
        return f"${amount:.2f}"

def get_priority_color(priority: int) -> str:
    """Получить цвет для приоритета"""
    colors = {
        1: ColorScheme.ERROR,     # Критический
        2: ColorScheme.WARNING,   # Высокий
        3: ColorScheme.INFO,      # Средний
        4: ColorScheme.SUCCESS,   # Низкий
        5: ColorScheme.TEXT_SECONDARY  # Информационный
    }
    return colors.get(priority, ColorScheme.TEXT)

# Экспорт основных настроек
__all__ = [
    'UXConfig', 'ux_config', 'UXEmojis', 'ColorScheme',
    'NotificationType', 'ResponsiveBreakpoints', 
    'QUICK_ACTIONS_CONFIG', 'PersonalizationSettings',
    'ExperimentalFeatures', 'get_status_emoji', 
    'format_money', 'get_priority_color'
]