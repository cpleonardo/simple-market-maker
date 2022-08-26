# settings.py
import os
from os.path import join, dirname
from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

ENVIRONMENT = os.environ.get("ENVIRONMENT")
TAUR_API_KEY = os.environ.get("TAUR_API_KEY")
TAUR_API_SECRET = os.environ.get("TAUR_API_SECRET")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
EMAIL_PASSWORD = os.environ.get("SENDER_EMAIL_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

NOTIFICATIONS_ENABLED = os.environ.get("NOTIFICATIONS_ENABLED") == "1"

REFRESH_ORDER_RATE = 60 * 3  # In seconds

NOT_FUNDS_AWAITING_TIME = 10  # In minutes

MIN_SPREAD = 0.015  # means 1.5 %

ORDER_PRICE_DELTA = 1  # Order price will be 1 MXN upper/lower than the best one

USE_FIREBASE = os.environ.get("USE_FIREBASE") == "1"

FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID")

BITSO = "BITSO"
OKX = "OKX"

PRICE_SOURCE_RULES = {
    "btc-mxn": BITSO,
    "ltc-mxn": BITSO,
    "eth-mxn": BITSO,
    "bch-mxn": BITSO,
    "btc-usdc": OKX,
}
