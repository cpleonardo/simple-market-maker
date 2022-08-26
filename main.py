from trading_bot.tauros_api import TaurosPrivate, TaurosPublic
from trading_bot import notifications, price_source
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
    exit("Tauros credentials not fund. Unable to launch bots.")

tauros = TaurosPrivate(key=tauros_key, secret=tauros_secret, prod=is_production)

tauros_public = TaurosPublic(prod=is_production)


def notify_not_enough_balance(left_coin_balance=None, right_coin_balance=None):
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
        greedy_mood = config.get("greedy_mood", True)

        if not config.get("is_active"):
            logging.info(
                f"{market} bot is not active. Sleeping {time_to_sleep} seconds"
            )
            time.sleep(time_to_sleep)
            continue

        left_coin, _ = market.split("-")
        external_price = price_source.get_external_price(market=market, ask=True)
        tauros_price = tauros_public.get_ask_price(market=market)

        if not external_price or not tauros_price:
            logging.error("Bitso or Tauros query price failed")
            time.sleep(3)
            continue

        left_coin_wallet = tauros.get_wallet(left_coin)

        if not left_coin_wallet["success"]:
            error_msg = left_coin_wallet["msg"]
            logging.error(f"Tauros {left_coin} wallet query failed. Error: {error_msg}")
            time.sleep(3)
            continue

        left_coin_balance = Decimal(left_coin_wallet["data"]["balances"]["available"])

        if left_coin_balance == 0:
            logging.error(
                f"{left_coin} wallet is empty. Imposible to place a buy order. Sending email . . ."
            )
            notify_not_enough_balance(left_coin_balance=0)
            time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            continue

        order_price = price_source.get_sell_order_price(
            min_price=external_price,
            ref_price=tauros_price,
            spread=spread,
            greedy_mood=greedy_mood,
        )
        if not greedy_mood:
            tauros_bid_price = tauros_public.get_bid_price(
                market=market, ignore_below=0
            )
            if order_price <= tauros_bid_price:
                # TODO: Remove magic number
                order_price = tauros_bid_price + Decimal("0.01")

        order_value = price_source.get_order_value(
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
            logging.error(
                f"Could not place sell order in {market} market. Error: {order_placed['msg']}"
            )
            messages = (
                "The minimum order",
                "has not enough {}".format(left_coin.upper()),
                "'amount' field must be greater",
            )
            try:
                for message in messages:
                    if message in order_placed["msg"][0]:
                        notify_not_enough_balance()
                        logging.error("Not enough funds email sent...")
                        time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            except:
                pass
            continue

        order_id = order_placed["data"]["id"]

        time_to_sleep = config.get("refresh_rate") * 60 or settings.REFRESH_ORDER_RATE

        logging.info(f"Market: {market}. Side: SELL")
        logging.info(f"Tauros ask order price: {tauros_price}")
        logging.info(f"External ask order price: {external_price}")
        logging.info("Sell order successfully placed: ")
        order_data = order_placed["data"]
        real_spread = (external_price - Decimal(order_data["price"])) / external_price
        real_spread = abs(round(real_spread * 100, 2))
        order_data["spread"] = str(real_spread) + "%"
        logging.info(order_data)
        logging.info(f"Sleeping {time_to_sleep} seconds")
        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order["success"]:
            logging.info(f"Order close faild. Error: {close_order['msg']}")
            # Making a second attempt if nonce invalid
            if "Provided nonce it is not valid." == close_order["msg"]:
                logging.info("Making a sencond attempt")
                close_order = tauros.close_order(order_id)


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
        greedy_mood = config.get("greedy_mood", True)

        if not config.get("is_active"):
            logging.info(
                f"{market} bot is not active. Sleeping {time_to_sleep} seconds"
            )
            time.sleep(time_to_sleep)
            continue

        _, right_coin = market.split("-")
        external_price = price_source.get_external_price(market=market, ask=False)
        tauros_price = tauros_public.get_bid_price(market=market)

        if not external_price or not tauros_price:
            TRY_AGAIN_IN = 3
            logging.error(
                f"External or Tauros query price failed for BUY bot in {market}. Trying again in: {TRY_AGAIN_IN}s"
            )
            time.sleep(TRY_AGAIN_IN)
            continue

        right_coin_wallet = tauros.get_wallet(right_coin)

        if not right_coin_wallet["success"]:
            error_msg = right_coin_wallet["msg"]
            logging.error(
                f"Tauros {right_coin} wallet query failed. Error: {error_msg}"
            )
            time.sleep(3)
            continue

        right_coin_balance = Decimal(right_coin_wallet["data"]["balances"]["available"])

        if right_coin_balance == 0:
            logging.error(
                f"{right_coin} wallet is empty. Imposible to place a buy order. Sending email . . ."
            )
            notify_not_enough_balance(right_coin_balance=0)
            time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            continue

        order_price = price_source.get_buy_order_price(
            max_price=external_price,
            ref_price=tauros_price,
            spread=spread,
            greedy_mood=greedy_mood,
        )
        if not greedy_mood:
            tauros_ask_price = tauros_public.get_ask_price(
                market=market, ignore_below=0
            )
            if order_price >= tauros_ask_price:
                # TODO: Remove magic number
                order_price = tauros_ask_price - Decimal("0.01")

        order_value = price_source.get_order_value(
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
                        notify_not_enough_balance()
                        logging.error("Not enough funds email sent...")
                        time.sleep(settings.NOT_FUNDS_AWAITING_TIME * 60)
            except:
                pass
            continue

        order_id = order_placed["data"]["id"]

        logging.info(f"Market: {market}. Side: BUY")
        logging.info(f"Tauros bid order price: {tauros_price}")
        logging.info(f"External bid order price: {external_price}")
        logging.info("Buy order successfully placed: ")
        order_data = order_placed["data"]
        real_spread = (external_price - Decimal(order_data["price"])) / external_price
        real_spread = abs(round(real_spread * 100, 2))
        order_data["spread"] = str(real_spread) + "%"
        logging.info(order_data)
        logging.info(f"Sleeping {time_to_sleep} seconds")
        time.sleep(time_to_sleep)

        close_order = tauros.close_order(order_id)
        if not close_order["success"]:
            logging.info(f"Order close faild. Error: {close_order['msg']}")
            # Making a second attempt if nonce invalid
            if "Provided nonce it is not valid." == close_order["msg"]:
                logging.info("Making a sencond attempt")
                close_order = tauros.close_order(order_id)


if __name__ == "__main__":
    logging.info(f"Environment: {'PRODUCTION' if is_production else 'STAGING'}")
    tauros.close_all_orders()
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
        tauros.close_all_orders()
        for process in processes:
            process.terminate()
