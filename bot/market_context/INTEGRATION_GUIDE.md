# Market Context Engine - Integration Guide

## 🎯 Overview

Market Context Engine предоставляет **профессиональную рыночную аналитику** для торговых стратегий:

- **Session-aware stops** - адаптация под торговые сессии
- **Liquidity-based targets** - таргеты на уровни ликвидности
- **Adaptive R/R** - динамический risk/reward под рынок
- **Market regime detection** - классификация тренда

## 🚀 Quick Start

### Базовое использование:

```python
from bot.market_context import MarketContextEngine

# Создаем engine (можно переиспользовать)
engine = MarketContextEngine()

# Получаем контекст для текущего рынка
context = engine.get_context(
    df=market_data,  # OHLCV DataFrame
    current_price=50000,
    signal_direction='BUY'  # или 'SELL'
)

# Используем контекст
stop_loss = context.get_stop_loss(entry_price=50000, atr=300, side='BUY')
take_profit = context.get_take_profit(entry_price=50000, atr=300, side='BUY')
position_size = context.get_position_size(base_size=0.001)

print(f"Stop: {stop_loss}, Target: {take_profit}, Size: {position_size}")
```

## 📊 Integration with Existing Strategies

### 1. Volume VWAP Strategy Integration

**Файл:** `bot/strategy/modules/volume_vwap_pipeline.py`

#### До (старый код):
```python
# volume_vwap_pipeline.py:335
stop_multiplier = 1.5  # ФИКСИРОВАННЫЙ!
stop_loss = entry_price - (atr * stop_multiplier)
```

#### После (с Market Context):
```python
from bot.market_context import get_engine

class VolumeVwapPositionSizer(PositionSizer):
    def __init__(self, config: Any, round_price_fn):
        self.round_price = round_price_fn
        self.ctx = VolumeContext(...)
        self.market_engine = get_engine()  # ← Добавить

    def plan(self, decision: SignalDecision, df: pd.DataFrame,
             current_price: float) -> PositionPlan:

        if not decision.is_actionable:
            return PositionPlan(side=None)

        # ✅ Получаем market context
        market_ctx = self.market_engine.get_context(
            df=df,
            current_price=current_price,
            signal_direction=decision.signal
        )

        # ✅ Проверяем можно ли торговать
        can_trade, reason = market_ctx.should_trade()
        if not can_trade:
            return PositionPlan(
                side=None,
                metadata={'reject_reason': reason}
            )

        # ✅ Используем адаптивные параметры
        entry_price = self.round_price(current_price)

        # Рассчитываем ATR
        atr_result = TechnicalIndicators.calculate_atr_safe(df, 14)
        atr = atr_result.last_value if atr_result and atr_result.is_valid else current_price * 0.01

        # ✅ Context-aware stop & target
        stop_loss = market_ctx.get_stop_loss(entry_price, atr, decision.signal)
        take_profit = market_ctx.get_take_profit(entry_price, atr, decision.signal)

        # ✅ Adaptive position size
        base_size = self.ctx.trade_amount
        size = market_ctx.get_position_size(base_size)

        # Risk/Reward check
        if decision.signal == 'BUY':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit

        actual_rr = reward / risk if risk > 0 else 0.0

        # Use context's minimum R/R (не фиксированный!)
        min_rr = market_ctx.risk_params.risk_reward_ratio * 0.8  # 80% от рекомендованного
        if actual_rr < min_rr:
            return PositionPlan(
                side=None,
                metadata={
                    'reject_reason': 'R/R below adaptive threshold',
                    'required_rr': min_rr,
                    'actual_rr': actual_rr
                }
            )

        return PositionPlan(
            side='Buy' if decision.signal == 'BUY' else 'Sell',
            size=size,
            entry_price=entry_price,
            stop_loss=self.round_price(stop_loss),
            take_profit=self.round_price(take_profit),
            risk_reward=actual_rr,
            metadata={
                'market_regime': market_ctx.risk_params.market_regime.value,
                'session': market_ctx.session.name.value,
                'confidence': market_ctx.risk_params.confidence,
                'stop_multiplier': market_ctx.risk_params.stop_loss_atr_mult,
                'context': market_ctx.to_dict()
            }
        )
```

### 2. CumDelta Strategy Integration

**Файл:** `bot/strategy/implementations/cumdelta_sr_strategy_v3.py`

```python
from bot.market_context import MarketContextEngine

class CumDeltaSRStrategyV3(BaseStrategyV3):
    def __init__(self, config):
        super().__init__(config)
        self.market_engine = MarketContextEngine()

    def execute(self, market_data, state=None, api_client=None, symbol='BTCUSDT'):
        # ... existing logic ...

        # ✅ Get market context
        current_price = market_data['close'].iloc[-1]
        context = self.market_engine.get_context(
            df=market_data,
            current_price=current_price,
            signal_direction='BUY'  # or from signal logic
        )

        # ✅ Check session - avoid rollover if extreme volatility
        if context.session.name.value == 'rollover' and context.risk_params.volatility_regime.value == 'extreme':
            self.logger.warning("Skipping trade: extreme volatility in rollover")
            return None

        # ✅ Use liquidity levels for S/R
        support = context.liquidity.nearest_support_below(current_price, min_strength=0.7)
        resistance = context.liquidity.nearest_target_above(current_price, min_strength=0.7)

        # ... rest of strategy logic ...
```

### 3. Multi-TF Strategy Integration

**Файл:** `bot/strategy/implementations/multitf_volume_strategy_v3.py`

```python
from bot.market_context import get_engine

class MultiTFVolumeStrategyV3(BaseStrategyV3):
    def execute(self, market_data, state=None, api_client=None, symbol='BTCUSDT'):
        # ✅ Get context with primary timeframe data
        primary_df = market_data[self.config.fast_tf.value]
        context = get_engine().get_context(
            df=primary_df,
            current_price=primary_df['close'].iloc[-1],
            signal_direction='BUY'
        )

        # ✅ Adaptive R/R based on trend alignment
        if context.risk_params.market_regime.value == 'strong_uptrend':
            # In strong trend, use higher R/R
            target_rr = context.risk_params.risk_reward_ratio  # Could be 3-4
        else:
            # Sideways/weak trend, use conservative
            target_rr = 1.5

        # ... rest of logic ...
```

## 🔬 Advanced Features

### Feature 1: Session-Specific Strategy Behavior

```python
def execute(self, market_data, state=None, api_client=None, symbol='BTCUSDT'):
    context = get_engine().get_context(df=market_data, current_price=current_price)

    # Different behavior per session
    if context.session.name.value == 'asian':
        # Asian session: tight ranges, quick scalps
        use_tight_stops = True
        max_holding_time = 30  # bars

    elif context.session.name.value == 'ny':
        # NY session: trends, wider stops
        use_tight_stops = False
        max_holding_time = 100

    # ... strategy logic ...
```

### Feature 2: Liquidity-Based Stop Placement

```python
def calculate_stop_loss(self, entry_price, atr, side, context):
    """Place stop BEYOND liquidity levels (LVN)"""

    if side == 'BUY':
        # Find sell-side liquidity (supports) below entry
        liquidity_support = context.liquidity.nearest_support_below(entry_price)

        if liquidity_support:
            # LVN (Low Volume Node) logic:
            # Check if support is weak (low volume)
            support_level = next(
                (lvl for lvl in context.liquidity.sell_side_liquidity if lvl.price == liquidity_support),
                None
            )

            if support_level and support_level.type.value == 'equal_lows':
                # Equal lows = liquidity pool, put stop BELOW it
                stop = liquidity_support * 0.998  # 0.2% below

                # Validate not too far
                if (entry_price - stop) <= atr * 3:
                    return stop

    # Fallback to context's ATR-based stop
    return context.get_stop_loss(entry_price, atr, side)
```

### Feature 3: Confidence-Based Position Sizing

```python
def calculate_position_size(self, base_size, context):
    """Scale position by market confidence"""

    # Base size from config
    size = base_size

    # Scale by context confidence
    size *= context.risk_params.confidence

    # Scale by session liquidity
    if context.session.volume_multiplier < 0.7:
        # Low liquidity session (Asian/Rollover weekend)
        size *= 0.5  # Reduce size

    # Scale by volatility regime
    if context.risk_params.volatility_regime.value == 'extreme':
        size *= 0.6  # Reduce in extreme vol

    return max(size, base_size * 0.3)  # Min 30% of base
```

## 📈 Monitoring & Logging

### Log Market Context in Trades

```python
context = get_engine().get_context(...)

self.logger.info(
    f"Trade setup: {context.to_dict()}"
)

# In trade execution
trade_metadata = {
    'session': context.session.name.value,
    'market_regime': context.risk_params.market_regime.value,
    'volatility_regime': context.risk_params.volatility_regime.value,
    'confidence': context.risk_params.confidence,
    'stop_multiplier': context.risk_params.stop_loss_atr_mult,
    'rr_ratio': context.risk_params.risk_reward_ratio,
    'strongest_liquidity': [
        {'price': lvl.price, 'type': lvl.type.value, 'strength': lvl.strength}
        for lvl in context.liquidity.get_strongest_levels(3)
    ]
}
```

### Telegram Bot Integration

```python
from bot.market_context import get_engine

def show_market_context(df, current_price):
    engine = get_engine()
    context = engine.get_context(df, current_price)

    message = f"""
🔍 Market Context:
├─ Session: {context.session.name.value.upper()}
├─ Regime: {context.risk_params.market_regime.value}
├─ Volatility: {context.risk_params.volatility_regime.value}
├─ R/R Ratio: {context.risk_params.risk_reward_ratio:.1f}
├─ Stop Mult: {context.risk_params.stop_loss_atr_mult:.2f}x ATR
└─ Confidence: {context.risk_params.confidence * 100:.0f}%

💧 Liquidity:
├─ Buy side: {len(context.liquidity.buy_side_liquidity)} levels
└─ Sell side: {len(context.liquidity.sell_side_liquidity)} levels

Top Levels:
"""
    for lvl in context.liquidity.get_strongest_levels(3):
        message += f"├─ ${lvl.price:.0f} ({lvl.type.value}, {lvl.strength:.2f})\n"

    return message
```

## 🧪 Testing

### Run Unit Tests

```bash
cd /home/mikevance/bots/bybot
source .venv/bin/activate
pytest tests/market_context/ -v
```

### Example Test in Strategy

```python
def test_volume_vwap_with_market_context():
    # Create test data
    df = create_test_dataframe(...)

    # Create strategy with context engine
    strategy = VolumeVWAPStrategyV3(config)

    # Execute
    result = strategy.execute(df, current_price=50000)

    # Verify context was used
    assert 'market_regime' in result['metadata']
    assert 'session' in result['metadata']
```

## 🎯 Migration Checklist

- [ ] Import `MarketContextEngine` or `get_engine()`
- [ ] Get context in `execute()` or `plan()` methods
- [ ] Replace fixed `stop_multiplier` with `context.risk_params.stop_loss_atr_mult`
- [ ] Replace fixed R/R with `context.risk_params.risk_reward_ratio`
- [ ] Use `context.get_stop_loss()` and `context.get_take_profit()`
- [ ] Add `context.should_trade()` check
- [ ] Scale position size with `context.get_position_size()`
- [ ] Log context in metadata for debugging
- [ ] Add unit tests with mocked context

## 📚 API Reference

### MarketContext

| Method | Description | Returns |
|--------|-------------|---------|
| `get_stop_loss(entry, atr, side)` | Calculate stop loss | float |
| `get_take_profit(entry, atr, side)` | Calculate take profit (liquidity-aware) | float |
| `get_position_size(base_size)` | Adaptive position sizing | float |
| `should_trade()` | Check if trading allowed | (bool, str) |
| `to_dict()` | Serializable context | Dict |

### MarketContextEngine

| Method | Description | Returns |
|--------|-------------|---------|
| `get_context(df, price, direction)` | Get market context | MarketContext |
| `get_session_stats(df)` | Current session statistics | Dict |
| `get_liquidity_map(df, price)` | Detailed liquidity analysis | Dict |

## 🚨 Performance Notes

- **Caching:** Context is cached for 60 seconds by default
- **Thread-safe:** Can be used across multiple strategies
- **Lightweight:** ~5-10ms overhead per context call
- **Memory:** ~10MB for full engine instance

## ❓ FAQ

**Q: Do I need to modify existing configs?**
A: No! Market Context Engine uses existing ATR calculations and adds intelligence on top.

**Q: What if I want different behavior per strategy?**
A: You can pass custom `SessionManager`, `LiquidityAnalyzer`, or `RiskCalculator` to engine.

**Q: How to disable for specific strategies?**
A: Simply don't use the engine - old code still works.

**Q: Can I customize session definitions?**
A: Yes! Create custom `SESSIONS` dict and pass to `SessionManager()`.

---

**Next Steps:**
1. Review integration examples above
2. Test with one strategy (recommend Volume VWAP)
3. Monitor logs for context metadata
4. Gradually rollout to other strategies
5. Collect metrics and optimize parameters
