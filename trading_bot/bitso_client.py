import bitso
from decimal import Decimal


bisto_api = bitso.Api()


def get_bid_price(market="btc-mxn", ignore_below=Decimal("500.00")):
    # Getting bitso order book
    bitso_order_book = bisto_api.order_book(market.replace("-", "_"))

    bitso_price = None
    for bid in bitso_order_book.bids:
        bid_value = bid.price * bid.amount
        if bid_value >= ignore_below:
            bitso_price = bid.price
            return bitso_price


def get_ask_price(market="btc-mxn", ignore_below=Decimal("500.00")):
    # Getting bitso order book
    bitso_order_book = bisto_api.order_book(market.replace("-", "_"))

    bitso_price = None
    for ask in bitso_order_book.asks:
        ask_value = ask.price * ask.amount
        if ask_value >= ignore_below:
            bitso_price = ask.price
            return bitso_price
