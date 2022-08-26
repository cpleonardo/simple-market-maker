from decimal import Decimal
import settings
from trading_bot import bitso_client, okx_client


def get_buy_order_price(max_price, ref_price, spread=None, greedy_mood=True):
    if spread is None:
        spread = settings.MIN_SPREAD
    max_price = max_price * Decimal(1 - spread / 100)
    if ref_price > max_price or not greedy_mood:
        return max_price
    return ref_price + settings.ORDER_PRICE_DELTA


def get_sell_order_price(min_price, ref_price, spread=None, greedy_mood=True):
    if spread is None:
        spread = settings.MIN_SPREAD
    min_price = min_price * Decimal(1 + spread / 100)
    if ref_price < min_price or not greedy_mood:
        return min_price
    return ref_price - settings.ORDER_PRICE_DELTA


def get_order_value(max_balance, price, max_order_value=20_000.00, side="buy"):
    # Setting order value
    MAX_ORDER_VALUE = Decimal(str(max_order_value))

    if side == "buy":
        if max_balance > MAX_ORDER_VALUE:
            return MAX_ORDER_VALUE
        else:
            return max_balance

    order_value = max_balance * price

    if order_value > MAX_ORDER_VALUE:
        return MAX_ORDER_VALUE

    return order_value


def get_external_price(market, ask=True):
    source = settings.PRICE_SOURCE_RULES[market]
    if source == settings.BITSO:
        client = bitso_client
    elif source == settings.OKX:
        client = okx_client
    else:
        raise NotImplementedError(f"Source price rule not defined for {market} market")
    if ask:
        return client.get_ask_price(market=market)
    return client.get_bid_price(market=market)
