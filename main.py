import bitso
from trading_bot.tauros_api import TaurosPrivate, TaurosPublic
from trading_bot import notifications
from decimal import Decimal
import logging
import settings
import time
import json

from threading import Thread

logging.basicConfig(filename='logs.log', level=logging.ERROR)

tauros_key = settings.TAUR_API_KEY
tauros_secret = settings.TAUR_API_SECRET
is_production = settings.ENVIRONMENT == 'prod'

if not tauros_key or not tauros_secret:
    raise ValueError('Tauros credentials not fund')

tauros = TaurosPrivate(key=tauros_key, secret=tauros_secret, prod=is_production)

tauros_public = TaurosPublic(prod=is_production)

bisto_api = bitso.Api()

def close_all_orders():
    '''
    This function queries all open orders in tauros and closes them.
    '''
    open_orders = tauros.get_orders(market='btc-mxn')
    if not open_orders['success']:
        logging.error(f'Querying open orders fail. Error: {open_orders["msg"]}')
        return

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

def get_buy_order_price(max_price, ref_price, spread=None):
    if spread is None:
        spread =  settings.MIN_SPREAD
    max_price = max_price * Decimal(1 - spread)
    if ref_price > max_price:
        return max_price
    return ref_price + settings.ORDER_PRICE_DELTA

def get_sell_order_price(min_price, ref_price, spread=None):
    if spread is None:
        spread =  settings.MIN_SPREAD
    min_price = min_price * Decimal(1 + spread)
    if ref_price < min_price:
        return min_price
    return ref_price - settings.ORDER_PRICE_DELTA

def send_not_enough_balance_notification(left_coin_balance=None, right_coin_balance=None):
    if right_coin_balance is None:
        right_coin_wallet = tauros.get_wallet('mxn')
        right_coin_balance = right_coin_wallet['data']['balances']['available']

    if left_coin_balance is None:
        left_coin_wallet = tauros.get_wallet('btc')
        left_coin_balance = left_coin_wallet['data']['balances']['available']

    notifications.send_funds_status_email(
        left_coin_balance=left_coin_balance,
        right_coin_balance=right_coin_balance,
        market='BTC-MXN',
    )

def get_bitso_bid(market='btc-mxn'):
    # Getting bitso order book
    bitso_order_book = bisto_api.order_book(market.replace('-', '_'))

    bitso_price = None
    for bid in bitso_order_book.bids:
        bid_value = bid.price * bid.amount
        if bid_value >= Decimal('500.00'):
            bitso_price = bid.price
            return bitso_price


def get_bitso_ask(market='btc-mxn'):
    # Getting bitso order book
    bitso_order_book = bisto_api.order_book(market.replace('-', '_'))

    bitso_price = None
    for ask in bitso_order_book.asks:
        ask_value = ask.price * ask.amount
        if ask_value >= Decimal('500.00'):
            bitso_price = ask.price
            return bitso_price


def get_tauros_bid(market='btc-mxn'):
    # Getting tauros order book
    tauros_order_book = tauros_public.get_order_book(market=market)
    tauros_price = None
    for bid in tauros_order_book['data']['bids']:
        if Decimal(str(bid['value'])) > Decimal('200.00'):
            tauros_price = Decimal(str(bid['price']))
            return tauros_price


def get_tauros_ask(market='btc-mxn'):
    # Getting tauros order book
    tauros_order_book = tauros_public.get_order_book(market=market)
    tauros_price = None
    for ask in tauros_order_book['data']['asks']:
        if Decimal(str(ask['value'])) > Decimal('200.00'):
            tauros_price = Decimal(str(ask['price']))
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

def sell_bot(config):
    market = config['market']
    spread = config['spread']
    left_coin, right_coin = market.split('-')

    while True:
        bitso_price = get_bitso_ask(market=market)
        tauros_price = get_tauros_ask(market=market)

        if not bitso_price or not tauros_price:
            logging.error('Bitso or Tauros query price failed')
            time.sleep(3)
            continue

        left_coin_wallet = tauros.get_wallet(left_coin)

        if not left_coin_wallet['success']:
            logging.error(f'Tauros {left_coin} wallet query failed')
            logging.error(left_coin_wallet['msg'])
            time.sleep(3)
            continue

        left_coin_balance = Decimal(
            left_coin_wallet['data']['balances']['available']
        )

        if left_coin_balance == 0:
            logging.error(f'{left_coin} wallet is empty. Imposible to place a buy order. Sending email . . .')
            send_not_enough_balance_notification(left_coin_balance=0)
            time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            continue

        order_price = get_sell_order_price(
            min_price=bitso_price,
            ref_price=tauros_price,
            spread=spread,
        )

        order_value = get_order_value(
            max_balance=left_coin_balance,
            price=order_price,
            side='sell'
        )

        order = {
            "market": market,
            "amount": str(order_value),
            "is_amount_value": True,
            "side": "SELL",
            "type": "LIMIT",
            "price": str(order_price),
        }

        order_placed = tauros.place_order(order=order)

        if not order_placed['success']:
            logging.error(f"Could not place sell order in {market} market. Error: {order_placed['msg']}")
            messages = (
                'The minimum order',
                'has not enough {}'.format(left_coin.upper()),
                "'amount' field must be greater",
            )
            try:
                for message in messages:
                    if message in order_placed['msg'][0]:
                        send_not_enough_balance_notification()
                        logging.error("Not enough funds email sent...")
                        time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            except:
                pass
            continue

        order_id = order_placed['data']['id']

        time_to_sleep = settings.REFRESH_ORDER_RATE
        print('=======================================================')
        print("Market: ", market)
        print('Side: SELL')
        print('Tauros ask order price: ', tauros_price)
        print('Bitso ask order price: ', bitso_price)
        print("Sell order successfully placed: ")
        order_data = order_placed['data']
        real_spread = (bitso_price - Decimal(order_data['price'])) / bitso_price
        real_spread = abs(round(real_spread * 100, 2))
        print(
            f"Price: {order_data['price']} | Spread: {real_spread}% | Amount: {order_data['amount']} | Value: {order_data['value']}"
        )

        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order['success']:
            print("Order close faild. Error", close_order['msg'])
            close_all_orders()


def buy_bot(config):
    market = config['market']
    spread = config['spread']
    left_coin, right_coin = market.split('-')

    while True:
        bitso_price = get_bitso_bid(market=market)
        tauros_price = get_tauros_bid(market=market)

        if not bitso_price or not tauros_price:
            logging.error('Bitso or Tauros query price failed')
            time.sleep(3)
            continue

        right_coin_wallet = tauros.get_wallet(right_coin)

        if not right_coin_wallet['success']:
            logging.error(f'Tauros {right_coin} wallet query failed')
            logging.error(right_coin_wallet['msg'])
            time.sleep(3)
            continue

        right_coin_balance = Decimal(
            right_coin_wallet['data']['balances']['available']
        )

        if right_coin_balance == 0:
            logging.error(f'{right_coin} wallet is empty. Imposible to place a buy order. Sending email . . .')
            send_not_enough_balance_notification(right_coin_balance=0)
            time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            continue

        order_price = get_buy_order_price(
            max_price=bitso_price,
            ref_price=tauros_price,
            spread=spread,
        )

        order_value = get_order_value(
            max_balance=right_coin_balance,
            price=order_price,
            side='buy'
        )

        order = {
            "market": market,
            "amount": str(order_value),
            "is_amount_value": True,
            "side": "BUY",
            "type": "LIMIT",
            "price": str(order_price),
        }

        order_placed = tauros.place_order(order=order)

        if not order_placed['success']:
            logging.error(f"Could not place buy order in {market} market. Error: {order_placed['msg']}")
            messages = (
                'The minimum order',
                'has not enough {}'.format(right_coin.upper()),
                "'amount' field must be greater",
            )
            try:
                for message in messages:
                    if message in order_placed['msg'][0]:
                        send_not_enough_balance_notification()
                        logging.error("Not enough funds email sent...")
                        time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            except:
                pass
            continue

        order_id = order_placed['data']['id']

        time_to_sleep = settings.REFRESH_ORDER_RATE
        print('=======================================================')
        print("Market: ", market)
        print('Side: BUY')
        print('Tauros bid order price: ', tauros_price)
        print('Bitso bid order price: ', bitso_price)
        print("Buy order successfully placed: ")
        order_data = order_placed['data']
        real_spread = (bitso_price - Decimal(order_data['price'])) / bitso_price
        real_spread = abs(round(real_spread * 100, 2))
        print(
            f"Price: {order_data['price']} | Spread: {real_spread}% | Amount: {order_data['amount']} | Value: {order_data['value']}"
        )
        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order['success']:
            logging.error('Order close failed')
            logging.error(close_order['msg'])


if __name__ == '__main__':
    close_all_orders()
    from multiprocessing import Process
    with open('./robots.json') as robots:
        robots_list = json.load(robots)
        processes = []
        for robot in robots_list:
            processes.append(
                Process(
                    target=buy_bot if robot['side'] == 'buy' else sell_bot,
                    args=(robot,)
                )
            )
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join()
        except KeyboardInterrupt:
            close_all_orders()
            for process in processes:
                process.terminate()
