from sqlalchemy.orm import Session
from .models import Trade

def create_trade(db: Session, symbol: str, side: str, qty: float, price: float):
    trade = Trade(symbol=symbol, side=side, qty=qty, price=price)
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade

def get_trades(db: Session, symbol: str = None):
    query = db.query(Trade)
    if symbol:
        query = query.filter(Trade.symbol == symbol)
    return query.all() 