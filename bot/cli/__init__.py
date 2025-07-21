import os
import click
from bot.exchange.bybit_api import BybitAPI
from config import TELEGRAM_TOKEN, ADMIN_USER_ID
import pandas as pd

STRATEGY_STATE_FILE = 'bot/strategy/active_strategy.txt'

def save_active_strategy(strategy_name):
    with open(STRATEGY_STATE_FILE, 'w') as f:
        f.write(strategy_name)

def load_active_strategy():
    if os.path.exists(STRATEGY_STATE_FILE):
        with open(STRATEGY_STATE_FILE, 'r') as f:
            return f.read().strip()
    return None

@click.group()
def cli():
    """Bybit Trading Bot CLI"""
    pass

@cli.command()
@click.option('--symbol', default='BTCUSDT', help='Trading pair')
def check_balance(symbol):
    """Check account balance"""
    api = BybitAPI()
    balance = api.get_wallet_balance_v5()
    click.echo(api.format_balance_v5(balance))

@cli.command()
@click.option('--strategy', required=True, help='Strategy name')
@click.option('--risk', default=1.0, help='Risk percentage')
def run(strategy, risk):
    """Run trading bot (заглушка, используйте TradingBot и загрузчик стратегий)"""
    click.echo(f"Starting {strategy} strategy with {risk}% risk (реализация через TradingBot)")
    # Здесь можно реализовать запуск TradingBot с нужной стратегией

@cli.command()
def backtest():
    """Run backtesting (заглушка)"""
    click.echo("Backtest not implemented in this version.")

@cli.command()
@click.option('--symbol', required=True, help='Trading pair (например, BTCUSDT)')
@click.option('--buy', default=1, help='Плечо для лонга (по умолчанию 1)')
@click.option('--sell', default=1, help='Плечо для шорта (по умолчанию 1)')
def set_leverage(symbol, buy, sell):
    """
    Установить плечо для деривативов (USDT-фьючерсы) на Bybit.
    Пример: bybot set-leverage --symbol BTCUSDT --buy 2 --sell 2
    """
    api = BybitAPI()
    result = api.set_leverage(symbol, buy_leverage=buy, sell_leverage=sell)
    click.echo(f"Set leverage result: {result}")

@cli.command()
@click.option('--symbol', required=True, help='Trading pair (например, BTCUSDT)')
@click.option('--side', required=True, type=click.Choice(['Buy', 'Sell']), help='Buy (лонг) или Sell (шорт)')
@click.option('--qty', required=True, type=float, help='Количество контракта')
@click.option('--order-type', default='Market', type=click.Choice(['Market', 'Limit']), help='Тип ордера')
@click.option('--price', default=None, type=float, help='Цена (для лимитного ордера)')
@click.option('--stop-loss', default=None, type=float, help='Стоп-лосс (опционально)')
@click.option('--take-profit', default=None, type=float, help='Тейк-профит (опционально)')
@click.option('--reduce-only', is_flag=True, help='Только для закрытия позиции')
def open_position(symbol, side, qty, order_type, price, stop_loss, take_profit, reduce_only):
    """
    Открыть позицию (лонг/шорт) на деривативах Bybit.
    Пример:
    bybot open-position --symbol BTCUSDT --side Buy --qty 0.01 --order-type Market --stop-loss 30000 --take-profit 35000
    """
    api = BybitAPI()
    result = api.create_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        qty=qty,
        price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reduce_only=reduce_only
    )
    click.echo(f"Order result: {result}")

@cli.command()
@click.option('--symbol', default=None, help='Торговая пара (например, BTCUSDT), если не указано — все позиции')
def get_positions(symbol):
    """
    Получить текущие открытые позиции по всем инструментам или по конкретному symbol.
    Пример: bybot get-positions --symbol BTCUSDT
    """
    from ..exchange.bybit_api import BybitAPI
    api = BybitAPI()
    result = api.get_positions(symbol)
    click.echo(result)

@cli.command()
@click.option('--symbol', required=True, help='Торговая пара (например, BTCUSDT)')
@click.option('--side', required=True, type=click.Choice(['Buy', 'Sell']), help='Текущая сторона позиции (Buy — лонг, Sell — шорт)')
def close_position(symbol, side):
    """
    Закрыть позицию по рынку (открывает противоположный ордер с reduce_only).
    Пример: bybot close-position --symbol BTCUSDT --side Buy
    """
    from ..exchange.bybit_api import BybitAPI
    api = BybitAPI()
    result = api.close_position(symbol, side)
    click.echo(result)

@cli.command()
@click.argument('strategy_name')
def set_strategy(strategy_name):
    """
    Установить активную стратегию для бота.
    Пример: bybot set-strategy strategy_02
    """
    save_active_strategy(strategy_name)
    click.echo(f"Активная стратегия установлена: {strategy_name}")

@cli.command()
def get_strategy():
    """
    Показать текущую активную стратегию.
    """
    strategy = load_active_strategy()
    if strategy:
        click.echo(f"Текущая активная стратегия: {strategy}")
    else:
        click.echo("Стратегия не выбрана.")

@cli.command()
def export_trades():
    """
    Экспортировать все сделки из базы данных в data/trades.csv
    """
    import csv
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from bot.db.models import Trade
    from bot.db.crud import get_trades

    # Путь к базе данных (по умолчанию bybot.db в корне)
    db_path = 'sqlite:///bybot.db'
    engine = create_engine(db_path)
    Session = sessionmaker(bind=engine)
    session = Session()

    trades = get_trades(session)
    if not trades:
        click.echo('Нет сделок для экспорта.')
        return

    out_path = 'data/trades.csv'
    fieldnames = ['id', 'symbol', 'side', 'qty', 'price', 'timestamp']
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in trades:
            writer.writerow({
                'id': t.id,
                'symbol': t.symbol,
                'side': t.side,
                'qty': t.qty,
                'price': t.price,
                'timestamp': t.timestamp.isoformat() if t.timestamp else ''
            })
    click.echo(f'Экспортировано {len(trades)} сделок в {out_path}')

if __name__ == '__main__':
    cli()