# settings.py
import os
from os.path import join, dirname
from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

ENVIRONMENT = os.environ.get("ENVIRONMENT")
TAUR_API_KEY = os.environ.get("TAUR_API_KEY")
TAUR_API_SECRET = os.environ.get("TAUR_API_SECRET")

REFRESH_ORDER_RATE = 3 # In minutes

MIN_SPREAD = 0.009 # means 0.9 %