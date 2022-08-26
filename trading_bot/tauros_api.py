import requests
import logging
import json
import time
import hmac
import hashlib
import base64
import simplejson
from decimal import Decimal


class TaurosPrivate:
    def __init__(self, key, secret, prod=True):
        self.key = key
        self.secret = secret
        self.base_url = (
            "https://api.tauros.io" if prod else "https://api.staging.tauros.io"
        )

    def _get_signature(self, path, data, nonce, method="post"):
        request_data = json.dumps(data, separators=(",", ":"))
        message = str(nonce) + method.upper() + path + str(request_data)
        api_sha256 = hashlib.sha256(message.encode()).digest()
        api_hmac = hmac.new(base64.b64decode(self.secret), api_sha256, hashlib.sha512)
        api_signature = base64.b64encode(api_hmac.digest())
        signature = api_signature.decode()
        return signature

    def _request(self, path, data={}, query_params={}, method="post"):
        nonce = str(int(1000 * time.time()))
        signature = self._get_signature(
            path=path,
            data=data,
            nonce=nonce,
            method=method,
        )
        headers = {
            "Authorization": "Bearer {}".format(self.key),
            "Taur-Signature": signature,
            "Taur-Nonce": nonce,
            "Content-Type": "application/json",
        }
        try:
            return requests.request(
                method=method,
                url=self.base_url + path,
                data=json.dumps(data),
                params=query_params,
                headers=headers,
            ).json()
        except simplejson.errors.JSONDecodeError:
            return {"success": False, "msg": "Could not connect to api.tauros.io"}

    def place_order(self, order):
        path = "/api/v1/trading/placeorder/"
        return self._request(path=path, data=order)

    def get_orders(self, market=None):
        path = "/api/v1/trading/myopenorders/"
        params = {}
        if market:
            params["market"] = market
        return self._request(path=path, query_params=params, method="get")

    def close_order(self, order_id):
        path = "/api/v1/trading/closeorder/"
        data = {
            "id": order_id,
        }
        return self._request(path=path, data=data)

    def get_wallet(self, coin):
        path = "/api/v1/data/getbalance/"
        data = {
            "coin": coin,
        }
        return self._request(path=path, query_params=data, method="get")
    
    def close_all_orders(self):
        """
        This function queries all open orders in tauros and closes them.
        """
        open_orders = self.get_orders()
        if not open_orders["success"]:
            logging.error(f'Querying open orders fail. Error: {open_orders["msg"]}')
            return

        orders_ids = [order["order_id"] for order in open_orders["data"]]
        logging.info(f"Open orders: {orders_ids}")
        orders_closed = 0
        for order_id in orders_ids:
            logging.info(f"Closing order with id: {order_id}")
            close_order = self.close_order(order_id=order_id)
            if not close_order["success"]:
                error_msg = close_order["msg"]
                logging.error(f"Close order with id {order_id} failed. Error: {error_msg}")
                continue
            orders_closed += 1
        logging.info(f"{orders_closed} limit orders closed!")


class TaurosPublic:
    def __init__(self, prod=True):
        self.base_url = (
            "https://api.tauros.io/api" if prod else "https://api.staging.tauros.io/api"
        )

    def _request(self, path, params={}):
        try:
            return requests.get(
                url=self.base_url + path,
                params=params,
            ).json()
        except simplejson.errors.JSONDecodeError:
            return {"success": False, "msg": "Could not connect to api.tauros.io"}

    def get_order_book(self, market="BTC-MXN"):
        path = f"/v2/trading/{market}/orderbook/"
        return self._request(path=path)

    def get_ask_price(self, market="btc-mxn", ignore_below=Decimal("200.00")):
        # Getting tauros order book
        tauros_order_book = self.get_order_book(market=market)
        tauros_price = None
        for ask in tauros_order_book["payload"]["asks"]:
            if Decimal(str(ask["value"])) > ignore_below:
                tauros_price = Decimal(str(ask["price"]))
                return tauros_price

    def get_bid_price(self, market="btc-mxn", ignore_below=Decimal("200.00")):
        # Getting tauros order book
        tauros_order_book = self.get_order_book(market=market)
        tauros_price = None
        for bid in tauros_order_book["payload"]["bids"]:
            if Decimal(str(bid["value"])) > ignore_below:
                tauros_price = Decimal(str(bid["price"]))
                return tauros_price
