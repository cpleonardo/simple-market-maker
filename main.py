from trading_bot.tauros_api import TaurosPrivate, TaurosPublic
from trading_bot import notifications, bitso_client
from decimal import Decimal
import requests
import logging
import settings
import time
import json
from multiprocessing import Process

logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)

tauros_key = settings.TAUR_API_KEY
tauros_secret = settings.TAUR_API_SECRET
is_production = settings.ENVIRONMENT == "prod"
FIREBASE_BASE_URL = f"https://{settings.FIREBASE_PROJECT_ID}.firebaseio.com"

if not tauros_key or not tauros_secret:
    raise ValueError("Tauros credentials not fund")

tauros = TaurosPrivate(key=tauros_key, secret=tauros_secret, prod=is_production)

tauros_public = TaurosPublic(prod=is_production)


def close_all_orders():
    """
    This function queries all open orders in tauros and closes them.
    """
    open_orders = tauros.get_orders()
    if not open_orders["success"]:
        logging.error(f'Querying open orders fail. Error: {open_orders["msg"]}')
        return

    orders_ids = [order["order_id"] for order in open_orders["data"]]
    logging.info(f"Open orders: {orders_ids}")
    orders_closed = 0
    for order_id in orders_ids:
        logging.info(f"Closing order with id: {order_id}")
        close_order = tauros.close_order(order_id=order_id)
        if not close_order["success"]:
            error_msg = close_order["msg"]
            logging.error(f"Close order with id {order_id} failed. Error: {error_msg}")
            continue
        orders_closed += 1
    logging.info(f"{orders_closed} limit orders closed!")


def get_buy_order_price(max_price, ref_price, spread=None):
    if spread is None:
        spread = settings.MIN_SPREAD
    max_price = max_price * Decimal(1 - spread / 100)
    if ref_price > max_price:
        return max_price
    return ref_price + settings.ORDER_PRICE_DELTA


def get_sell_order_price(min_price, ref_price, spread=None):
    if spread is None:
        spread = settings.MIN_SPREAD
    min_price = min_price * Decimal(1 + spread / 100)
    if ref_price < min_price:
        return min_price
    return ref_price - settings.ORDER_PRICE_DELTA


def send_not_enough_balance_notification(
    left_coin_balance=None, right_coin_balance=None
):
    if right_coin_balance is None:
        right_coin_wallet = tauros.get_wallet("mxn")
        right_coin_balance = right_coin_wallet["data"]["balances"]["available"]

    if left_coin_balance is None:
        left_coin_wallet = tauros.get_wallet("btc")
        left_coin_balance = left_coin_wallet["data"]["balances"]["available"]

    notifications.send_funds_status_email(
        left_coin_balance=left_coin_balance,
        right_coin_balance=right_coin_balance,
        market="BTC-MXN",
    )


def get_order_value(max_balance, price, max_order_value=200_00.00, side="buy"):
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


def sell_bot(config_id, remote=False):
    config = {}
    while True:
        if remote:
            response = requests.get(f"{FIREBASE_BASE_URL}/{config_id}.json")
            config = response.json()
        else:
            with open("./robots.json") as robots:
                robots_list = json.load(robots)
                config = robots_list[config_id]
        market = config["market"]
        spread = config["spread"]
        time_to_sleep = config.get("refresh_rate") * 60 or settings.REFRESH_ORDER_RATE

        if not config.get("is_active"):
            logging.info(
                f"{market} bot is not active. Sleeping {time_to_sleep} seconds"
            )
            time.sleep(time_to_sleep)
            continue

        left_coin, right_coin = market.split("-")
        bitso_price = bitso_client.get_ask_price(market=market)
        tauros_price = tauros_public.get_ask_price(market=market)

        if not bitso_price or not tauros_price:
            logging.error("Bitso or Tauros query price failed")
            time.sleep(3)
            continue

        left_coin_wallet = tauros.get_wallet(left_coin)

        if not left_coin_wallet["success"]:
            logging.error(f"Tauros {left_coin} wallet query failed")
            logging.error(left_coin_wallet["msg"])
            time.sleep(3)
            continue

        left_coin_balance = Decimal(left_coin_wallet["data"]["balances"]["available"])

        if left_coin_balance == 0:
            logging.error(
                f"{left_coin} wallet is empty. Imposible to place a buy order. Sending email . . ."
            )
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
            max_order_value=config.get("order_value") or 20_000.00,
            side="sell",
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

        if not order_placed["success"]:
            error_msg = f"Could not place sell order in {market} market. Error: {order_placed['msg']}"
            logging.error(error_msg)
            messages = (
                "The minimum order",
                "has not enough {}".format(left_coin.upper()),
                "'amount' field must be greater",
            )
            try:
                for message in messages:
                    if message in order_placed["msg"][0]:
                        send_not_enough_balance_notification()
                        logging.error("Not enough funds email sent...")
                        time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            except:
                pass
            continue

        order_id = order_placed["data"]["id"]

        time_to_sleep = config.get("refresh_rate") * 60 or settings.REFRESH_ORDER_RATE

        logging.info(f"Market: {market}")
        logging.info("Side: SELL")
        logging.info(f"Tauros ask order price: {tauros_price}")
        logging.info(f"Bitso ask order price: {bitso_price}")
        logging.info("Sell order successfully placed: ")
        order_data = order_placed["data"]
        real_spread = (bitso_price - Decimal(order_data["price"])) / bitso_price
        real_spread = abs(round(real_spread * 100, 2))
        logging.info(
            f"DT: {order_data['created_at']} | Price: {order_data['price']} | Spread: {real_spread}% | Amount: {order_data['amount']} | Status: {order_data['status']}"
        )
        logging.info(f"Sleeping {time_to_sleep} seconds")
        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order["success"]:
            logging.info("Order close faild. Error", close_order["msg"])
            close_all_orders()


def buy_bot(config_id, remote=False):
    config = {}
    while True:
        if remote:
            response = requests.get(f"{FIREBASE_BASE_URL}/{config_id}.json")
            config = response.json()
            if not config:
                logging.error(
                    "Imposible to place order. Could get config from firebase. Error:",
                    response.text,
                )
                return
        else:
            with open("./robots.json") as robots:
                robots_list = json.load(robots)
                config = robots_list[config_id]
        market = config["market"]
        spread = config["spread"]
        time_to_sleep = config.get("refresh_rate") * 60 or settings.REFRESH_ORDER_RATE

        if not config.get("is_active"):
            logging.info(
                f"{market} bot is not active. Sleeping {time_to_sleep} seconds"
            )
            time.sleep(time_to_sleep)
            continue

        left_coin, right_coin = market.split("-")
        bitso_price = bitso_client.get_bid_price(market=market)
        tauros_price = tauros_public.get_bid_price(market=market)

        if not bitso_price or not tauros_price:
            TRY_AGAIN_IN = 3
            logging.error(
                f"Bitso or Tauros query price failed. Trying again in: {TRY_AGAIN_IN}s"
            )
            time.sleep(TRY_AGAIN_IN)
            continue

        right_coin_wallet = tauros.get_wallet(right_coin)

        if not right_coin_wallet["success"]:
            logging.error(f"Tauros {right_coin} wallet query failed")
            logging.error(right_coin_wallet["msg"])
            time.sleep(3)
            continue

        right_coin_balance = Decimal(right_coin_wallet["data"]["balances"]["available"])

        if right_coin_balance == 0:
            logging.error(
                f"{right_coin} wallet is empty. Imposible to place a buy order. Sending email . . ."
            )
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
            max_order_value=config.get("order_value") or 20_000.00,
            side="buy",
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

        if not order_placed["success"]:
            error_msg = f"Could not place buy order in {market} market. Error: {order_placed['msg']}"
            logging.error(error_msg)
            messages = (
                "The minimum order",
                "has not enough {}".format(right_coin.upper()),
                "'amount' field must be greater",
            )
            try:
                for message in messages:
                    if message in order_placed["msg"][0]:
                        send_not_enough_balance_notification()
                        logging.error("Not enough funds email sent...")
                        time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            except:
                pass
            continue

        order_id = order_placed["data"]["id"]

        logging.info(f"Market: {market}")
        logging.info("Side: BUY")
        logging.info(f"Tauros bid order price: {tauros_price}")
        logging.info(f"Bitso bid order price: {bitso_price}")
        logging.info("Buy order successfully placed: ")
        order_data = order_placed["data"]
        real_spread = (bitso_price - Decimal(order_data["price"])) / bitso_price
        real_spread = abs(round(real_spread * 100, 2))
        logging.info(
            f"DT: {order_data['created_at']} | Price: {order_data['price']} | Spread: {real_spread}% | Amount: {order_data['amount']} | Status: {order_data['status']}"
        )
        logging.info(f"Sleeping {time_to_sleep} seconds")
        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order["success"]:
            logging.error("Order close failed")
            logging.error(close_order["msg"])


if __name__ == "__main__":
    logging.info(f"Environment: {'PRODUCTION' if is_production else 'STAGING'}")
    close_all_orders()
    processes = []

    if not settings.USE_FIREBASE:
        logging.info("Using robots.json file...")
        with open("./robots.json") as bots_config:
            robots_config = json.load(bots_config)
        for index, bot_config in enumerate(robots_config):
            processes.append(
                Process(
                    target=buy_bot if bot_config["side"] == "buy" else sell_bot,
                    args=(index, False),
                )
            )
    else:
        LIMIT = 50
        logging.info(f"Using firebase with up to {LIMIT} bots")
        for i in range(0, LIMIT - 1):
            response = requests.get(f"{FIREBASE_BASE_URL}/{i}.json")
            robot = response.json()
            if not robot:
                break
            processes.append(
                Process(
                    target=buy_bot if robot["side"] == "buy" else sell_bot,
                    args=(i, True),
                )
            )
    if not processes:
        exit("No bots config defined")
    try:
        for process in processes:
            time.sleep(0.1)
            process.start()
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        close_all_orders()
        for process in processes:
            process.terminate()
