from decimal import Decimal
import requests

BASE_URL = "https://www.okx.com"


def get_price_limit(instrument_id="BTC-USDC", type_of_instrument="SPOT"):
    response = requests.get(
        BASE_URL
        + f"/api/v5/public/price-limit?instId={instrument_id}-{type_of_instrument}",
    )
    return response.json()


def get_instruments(instrument_type="SPOT"):
    response = requests.get(
        BASE_URL + f"/api/v5/public/instruments?instType={instrument_type}"
    )
    return response.json()


def get_ticker(instrument_id="BTC-USDC"):
    response = requests.get(BASE_URL + f"/api/v5/market/ticker?instId={instrument_id}")
    return response.json()


def get_tickers(instrument_type="SPOT"):
    response = requests.get(
        BASE_URL + f"/api/v5/market/tickers?instType={instrument_type}"
    )
    return response.json()


def get_ask_price(market):
    return Decimal(get_ticker(market.upper())["data"][0]["askPx"])


def get_bid_price(market):
    return Decimal(get_ticker(market.upper())["data"][0]["bidPx"])
