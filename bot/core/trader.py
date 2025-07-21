import logging
from decimal import Decimal
from bot.exchange.bybit_api import TradingBot
from bot.state import BotState
import importlib
import time
import pandas as pd
import os
import csv
from datetime import datetime

# Настройка логов
logging.basicConfig(filename='bot.log', level=logging.INFO)

def load_strategy(strategy_name):
    try:
        module = importlib.import_module(f"bot.strategy.{strategy_name}")
        class_name = "".join([part.capitalize() for part in strategy_name.split('_')])
        return getattr(module, class_name)()
    except Exception as e:
        logging.error(f"Ошибка загрузки стратегии: {e}", exc_info=True)
        raise

def get_active_strategies():
    try:
        with open("bot/strategy/active_strategies.txt") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return ["strategy_01"]  # стратегия по умолчанию

def log_trade_journal(strategy_name, signal, all_market_data):
    filename = "data/trade_journal.csv"
    fieldnames = [
        'timestamp', 'strategy', 'signal', 'entry_price', 'stop_loss', 'take_profit', 'comment',
        'tf', 'open', 'high', 'low', 'close', 'volume'
    ]
    # Для каждого таймфрейма логируем последнюю свечу
    for tf, df in all_market_data.items():
        if len(df) == 0:
            continue
        last = df.iloc[-1]
        row = {
            'timestamp': signal.get('timestamp', datetime.utcnow().isoformat()),
            'strategy': strategy_name,
            'signal': signal.get('signal', ''),
            'entry_price': signal.get('entry_price', ''),
            'stop_loss': signal.get('stop_loss', ''),
            'take_profit': signal.get('take_profit', ''),
            'comment': signal.get('comment', ''),
            'tf': tf,
            'open': last['open'],
            'high': last['high'],
            'low': last['low'],
            'close': last['close'],
            'volume': last['volume']
        }
        with open(filename, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(row)

def run_trading():
    api = TradingBot(symbol="BTCUSDT")
    state = BotState()
    
    logging.info("Торговый бот запущен")
    
    while True:
        try:
            # Получаем баланс
            balance_data = api.get_wallet_balance_v5()
            if balance_data and balance_data.get('retCode') == 0:
                coins = balance_data['result']['list'][0]['coin']
                usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
                if usdt:
                    balance = float(usdt['walletBalance'])
                else:
                    balance = 0
            else:
                balance = 0

            if balance < 10:  # Минимум для торговли
                logging.warning("Недостаточно средств на балансе")
                time.sleep(60)
                continue

            # Универсальный сбор данных по таймфреймам
            all_market_data = {
                '1m': api.get_ohlcv(interval="1", limit=100),
                '5m': api.get_ohlcv(interval="5", limit=100),
                '1h': api.get_ohlcv(interval="60", limit=100)
            }
            for tf, df in all_market_data.items():
                all_market_data[tf] = df.apply(pd.to_numeric, errors='coerce')

            # Мультистратегия: перебираем все активные стратегии
            strategy_names = get_active_strategies()
            in_position = getattr(state, 'position', None) in ('LONG', 'SHORT')
            signal = None
            if not in_position:
                for name in strategy_names:
                    strategy = load_strategy(name)
                    # Для обратной совместимости: если стратегия принимает только 1 DataFrame, передаём '5m'
                    try:
                        signal = strategy.execute(all_market_data, state=state, bybit_api=api)
                    except TypeError:
                        signal = strategy.execute(all_market_data['5m'], state=state, bybit_api=api)
                    logging.info(f"Стратегия {name}: сигнал = {signal}")
                    if signal and signal.get('signal') in ('BUY', 'SELL'):
                        log_trade_journal(name, signal, all_market_data)
                        # Открываем позицию только по первому сигналу
                        break
            else:
                for name in strategy_names:
                    strategy = load_strategy(name)
                    try:
                        signal = strategy.execute(all_market_data, state=state, bybit_api=api)
                    except TypeError:
                        signal = strategy.execute(all_market_data['5m'], state=state, bybit_api=api)
                    logging.info(f"Стратегия {name}: сигнал = {signal}")
                    if signal and signal.get('signal', '').startswith('EXIT'):
                        log_trade_journal(name, signal, all_market_data)
                        # Закрываем позицию по первому сигналу на выход
                        break
            # Далее обработка signal как раньше
            
            if signal:
                positions_resp = api.get_positions(symbol="BTCUSDT")
                has_open_position = False
                if positions_resp and positions_resp.get('result') and positions_resp['result'].get('list'):
                    for pos in positions_resp['result']['list']:
                        # Открытая позиция: size > 0
                        try:
                            if float(pos.get('size', 0)) > 0:
                                has_open_position = True
                                break
                        except Exception:
                            continue
                if not has_open_position:
                    entry_price = float(signal['entry_price'])
                    stop_loss = float(signal['stop_loss'])
                    take_profit = float(signal['take_profit'])
                    # Расчет объема
                    risk_amount = balance * 0.01  # 1% от депозита
                    qty = risk_amount / (entry_price - stop_loss)
                    qty = float(Decimal(str(qty)).quantize(Decimal('0.001')))  # Округление
                    # Открытие ордера
                    api.create_order(
                        symbol="BTCUSDT",
                        side=signal['signal'],
                        order_type="Market",
                        qty=qty,
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )
                    logging.info(f"Открыта позиция: {signal}")
            
            time.sleep(5)
            
        except Exception as e:
            logging.error(f"Критическая ошибка: {e}", exc_info=True)
            time.sleep(30)

if __name__ == "__main__":
    run_trading()