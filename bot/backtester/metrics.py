import pandas as pd

def calculate_sharpe(returns, risk_free_rate=0.0):
    mean_return = returns.mean()
    std_return = returns.std()
    if std_return == 0:
        return 0
    return (mean_return - risk_free_rate) / std_return

def calculate_drawdown(equity_curve):
    roll_max = equity_curve.cummax()
    drawdown = (equity_curve - roll_max) / roll_max
    return drawdown.min() 