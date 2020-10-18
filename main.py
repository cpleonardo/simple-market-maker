import bitso
from trading_bot.tauros_api import TaurosPrivate, TaurosPublic
from decimal import Decimal
import logging
import settings
import time
import json
from multiprocessing import Process
from threading import Thread

tauros_key = settings.TAUR_API_KEY
tauros_secret = settings.TAUR_API_SECRET
is_production = settings.ENVIRONMENT == 'prod'

if not tauros_key or not tauros_secret:
    raise ValueError('Tauros credentials not fund')

tauros = TaurosPrivate(key=tauros_key, secret=tauros_secret, prod=is_production)

tauros_public = TaurosPublic(prod=is_production)

bisto_api = bitso.Api()

ORDER_PRICE_DELTA = Decimal('1')

def close_all_orders():
    '''
    This function queries all open orders in tauros and closes them.
    '''
    open_orders = tauros.get_orders(market='btc-mxn')
    if not open_orders['success']:
        logging.error(f'Querying open orders fail. Error: {open_orders["msg"]}')
        return
    # Filtering buy orders
    # buy_open_orders = list(filter(lambda order: order['side'] == 'BUY', open_orders['data']))
    orders_ids = [order['order_id']  for order in open_orders['data']]
    logging.info(f'Open orders: {orders_ids}')
    orders_closed = 0
    for order_id in orders_ids:
        print("Closing order with id: ", order_id)
        close_order = tauros.close_order(order_id=order_id)
        if not close_order['success']:
            print(f'Close order with id {order_id} failed. Error: ', close_order['msg'])
            continue
        orders_closed += 1
    print(f'{orders_closed} limit orders closed!')

def get_buy_order_price(max_price, ref_price):
    max_price = max_price * Decimal(1 - settings.MIN_SPREAD)
    if ref_price > max_price:
        return max_price
    return ref_price + ORDER_PRICE_DELTA

def get_sell_order_price(min_price, ref_price):
    min_price = min_price * Decimal(1 + settings.MIN_SPREAD)
    if ref_price < min_price:
        return min_price
    return ref_price - ORDER_PRICE_DELTA

def get_bitso_bid():
    # Getting bitso order book
    bitso_order_book = bisto_api.order_book('btc_mxn')

    bitso_price = None
    for bid in bitso_order_book.bids:
        bid_value = bid.price * bid.amount
        if bid_value >= Decimal('500.00'):
            bitso_price = bid.price
            print('Bitso bid order price: ', bitso_price)
            return bitso_price


def get_bitso_ask():
    # Getting bitso order book
    bitso_order_book = bisto_api.order_book('btc_mxn')

    bitso_price = None
    for ask in bitso_order_book.asks:
        ask_value = ask.price * ask.amount
        if ask_value >= Decimal('500.00'):
            bitso_price = ask.price
            print('Bitso ask order price: ', bitso_price)
            return bitso_price


def get_tauros_bid():
    # Getting tauros order book
    tauros_order_book = tauros_public.get_order_book()
    tauros_price = None
    for bid in tauros_order_book['data']['bids']:
        if Decimal(str(bid['value'])) > Decimal('200.00'):
            tauros_price = Decimal(str(bid['price']))
            print('Tauros bid order price: ', tauros_price)
            return tauros_price


def get_tauros_ask():
    # Getting tauros order book
    tauros_order_book = tauros_public.get_order_book()
    tauros_price = None
    for ask in tauros_order_book['data']['asks']:
        if Decimal(str(ask['value'])) > Decimal('200.00'):
            tauros_price = Decimal(str(ask['price']))
            print('Tauros ask order price: ', tauros_price)
            return tauros_price


def get_order_value(max_balance, price, side='buy'):
    # Setting order value
    MAX_ORDER_VALUE = Decimal('20000.00')

    if side == 'buy':
        if max_balance > MAX_ORDER_VALUE:
            return MAX_ORDER_VALUE
        else:
            return max_balance

    order_value = max_balance * price

    if order_value > MAX_ORDER_VALUE:
        return MAX_ORDER_VALUE

    return order_value

def sell_bot():
    while True:
        bitso_price = get_bitso_ask()
        tauros_price = get_tauros_ask()

        if not bitso_price or not tauros_price:
            print('Bitso or Tauros query price failed')
            time.sleep(3)
            continue

        btc_wallet = tauros.get_wallet('btc')

        if not btc_wallet['success']:
            print('Tauros available balance failed')
            time.sleep(3)
            continue

        available_btc_balance = Decimal(btc_wallet['data']['balances']['available'])

        if available_btc_balance == 0:
            print('BTC wallet is empty. Imposible to place a sell order.')
            time.sleep(60*5)
            continue

        order_price = get_sell_order_price(
            min_price=bitso_price,
            ref_price=tauros_price,
        )

        order_value = get_order_value(
            max_balance=available_btc_balance,
            price=order_price,
            side='sell'
        )

        order = {
            "market": "BTC-MXN",
            "amount": str(order_value),
            "is_amount_value": True,
            "side": "SELL",
            "type": "LIMIT",
            "price": str(order_price),
        }

        order_placed = tauros.place_order(order=order)

        if not order_placed['success']:
            print('Could not place sell order. Error: ', order_placed['msg'])
            continue

        order_id = order_placed['data']['id']

        time_to_sleep = settings.REFRESH_ORDER_RATE
        print("Order successfully placed: ")
        print(json.dumps(order_placed, indent=4))
        print(f'Sleeping {time_to_sleep} seconds')

        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order['success']:
            print("Order close faild. Error", close_order['msg'])
            close_all_orders()


def buy_bot():
    while True:
        bitso_price = get_bitso_bid()
        tauros_price = get_tauros_bid()

        if not bitso_price or not tauros_price:
            print('Bitso or Tauros query price failed')
            time.sleep(3)
            continue

        mxn_wallet = tauros.get_wallet('mxn')

        if not mxn_wallet['success']:
            print('Tauros available balance failed')
            time.sleep(3)
            continue

        available_mxn_balance = Decimal(mxn_wallet['data']['balances']['available'])

        if available_mxn_balance == 0:
            print('MXN wallet is empty. Imposible to place a buy order.')
            time.sleep(60*5)
            continue

        order_price = get_buy_order_price(
            max_price=bitso_price,
            ref_price=tauros_price,
        )

        order_value = get_order_value(
            max_balance=available_mxn_balance,
            price=order_price,
            side='buy'
        )

        order = {
            "market": "BTC-MXN",
            "amount": str(order_value),
            "is_amount_value": True,
            "side": "BUY",
            "type": "LIMIT",
            "price": str(order_price),
        }

        order_placed = tauros.place_order(order=order)

        if not order_placed['success']:
            print('Could not place buy order. Error: ', order_placed['msg'])
            continue

        order_id = order_placed['data']['id']

        time_to_sleep = settings.REFRESH_ORDER_RATE
        print("Order successfully placed: ")
        print(json.dumps(order_placed, indent=4))
        print(f'Sleeping {time_to_sleep} seconds')

        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order['success']:
            print("Order close faild. Error", close_order['msg'])
            close_all_orders()


if __name__ == '__main__':
    close_all_orders()
    p1 = Process(target=sell_bot)
    p2 = Process(target=buy_bot)
    try:
        p1.start()
        p2.start()
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        close_all_orders()
        p1.terminate()
        p2.terminate()
