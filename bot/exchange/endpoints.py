from enum import Enum


class Position(str, Enum):
    GET_POSITIONS = "/v5/position/list"
    SET_LEVERAGE = "/v5/position/set-leverage"
    SWITCH_MARGIN_MODE = "/v5/position/switch-isolated"
    SET_TP_SL_MODE = "/v5/position/set-tpsl-mode"
    SWITCH_POSITION_MODE = "/v5/position/switch-mode"
    SET_RISK_LIMIT = "/v5/position/set-risk-limit"
    SET_TRADING_STOP = "/v5/position/trading-stop"
    SET_AUTO_ADD_MARGIN = "/v5/position/set-auto-add-margin"
    ADD_MARGIN = "/v5/position/add-margin"
    GET_EXECUTIONS = "/v5/execution/list"
    GET_CLOSED_PNL = "/v5/position/closed-pnl"

    def __str__(self) -> str:
        return self.value


class Trade(str, Enum):
    PLACE_ORDER = "/v5/order/create"
    AMEND_ORDER = "/v5/order/amend"
    CANCEL_ORDER = "/v5/order/cancel"
    GET_OPEN_ORDERS = "/v5/order/realtime"
    CANCEL_ALL_ORDERS = "/v5/order/cancel-all"
    GET_ORDER_HISTORY = "/v5/order/history"
    BATCH_PLACE_ORDER = "/v5/order/create-batch"
    BATCH_AMEND_ORDER = "/v5/order/amend-batch"
    BATCH_CANCEL_ORDER = "/v5/order/cancel-batch"
    GET_BORROW_QUOTA = "/v5/order/spot-borrow-check"
    SET_DCP = "/v5/order/disconnected-cancel-all"

    def __str__(self) -> str:
        return self.value


class Account(str, Enum):
    GET_WALLET_BALANCE = "/v5/account/wallet-balance"
    GET_ACCOUNT_INFO = "/v5/account/info"
    GET_COLLATERAL_INFO = "/v5/account/collateral-info"
    GET_ACCOUNT_RATIO = "/v5/account/account-ratio"

    def __str__(self) -> str:
        return self.value


class Market(str, Enum):
    GET_SERVER_TIME = "/v5/market/time"
    GET_KLINE = "/v5/market/kline"
    GET_MARK_PRICE_KLINE = "/v5/market/mark-price-kline"
    GET_INDEX_PRICE_KLINE = "/v5/market/index-price-kline"
    GET_PREMIUM_INDEX_PRICE_KLINE = "/v5/market/premium-index-price-kline"
    GET_INSTRUMENTS_INFO = "/v5/market/instruments-info"
    GET_ORDERBOOK = "/v5/market/orderbook"
    GET_TICKERS = "/v5/market/tickers"
    GET_FUNDING_RATE_HISTORY = "/v5/market/funding/history"
    GET_PUBLIC_TRADING_HISTORY = "/v5/market/recent-trade"
    GET_OPEN_INTEREST = "/v5/market/open-interest"
    GET_HISTORICAL_VOLATILITY = "/v5/market/historical-volatility"
    GET_INSURANCE = "/v5/market/insurance"
    GET_RISK_LIMIT = "/v5/market/risk-limit"
    GET_OPTION_DELIVERY_PRICE = "/v5/market/delivery-price"
    GET_LONG_SHORT_RATIO = "/v5/market/account-ratio"

    def __str__(self) -> str:
        return self.value 