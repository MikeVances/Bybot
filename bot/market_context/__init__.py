"""
Market Context Engine - Centralized market intelligence for trading strategies

Provides:
- Session awareness (Asian, London, NY, Rollover)
- Liquidity pool identification (Equal Highs/Lows, Order Blocks)
- Adaptive risk parameters (ATR multipliers, R/R ratios)
- Time-based filtering (avoid low liquidity periods)

Architecture:
    MarketContextEngine (orchestrator)
        ├── SessionManager - Trading session analysis
        ├── LiquidityAnalyzer - Order flow and liquidity pools
        ├── RiskParameterCalculator - Adaptive risk/reward
        └── TimeFilter - Trade timing optimization

Usage:
    from bot.market_context import MarketContextEngine

    engine = MarketContextEngine()
    context = engine.get_context(df, current_price, datetime.now())

    # Use context in strategies
    stop_loss = entry - (atr * context.session.stop_multiplier)
    take_profit = context.liquidity.nearest_target_above(entry)
"""

from .engine import MarketContextEngine, MarketContext
from .session_manager import SessionManager, TradingSession
from .liquidity_analyzer import LiquidityAnalyzer, LiquidityPools
from .risk_calculator import AdaptiveRiskCalculator, RiskParameters

__all__ = [
    'MarketContextEngine',
    'MarketContext',
    'SessionManager',
    'TradingSession',
    'LiquidityAnalyzer',
    'LiquidityPools',
    'AdaptiveRiskCalculator',
    'RiskParameters',
]

__version__ = '1.0.0'
