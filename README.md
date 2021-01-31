# Simple market maker
Simple market maker bot

This bot places limit orders in [tauros](https://tauros.io) crypto exchange querying [Bitso](https://bitso.com) orderbook as reference price.

## Parameters

Working parameters:
* `is_active`: Designates wether the bot is active (`true` or `false`)
* `refresh_rate`: Time in minutes for price updating (e.g. every 3 minutes)


Trading related parameters:
* `market`: Market to place the order (e.g. BTC-MXN)
* `spread`: The minimum spread to take in consideration for order placement (e.g. 3%). Nevative values are allwed.
* `order_vale`: The maximum value that the order can have (e.g. $10,000.00 MXN)
* `side`: Order side (buy or sell)

This parameters can be confirgued locally in the file `robots.json` or in a remote firebase realtime database. View `settings.py` file.


## Business Logic

Rule 1:
Allways look for 1st position in order book

Rule 2:
Increase spread as much as posible until 1st order book positition allows

Rule 3:
Never put an order bellow configured spread

Rule 4:
Use the maximum available funds but never surpase configured order value.

Rule 5:
Ignore tauros orders located at first places if its value is bellow $200.00 MXN

Rule 6:
Ignore bitso orders localed at first places if its value is bellow $500.00 MXN


## Running the bots

### Set environment variables

  1. Copy to `env.example` into `.env`

    cp env.example .env

  2. Edit values in `.env` depending on your preferences

    nano .env

### Create and activate a python virtual envirtonment

You must first install or verify that your computer has `python 3.8`, `pip` and `virtualenv`

    virtualenv -p python3 env && source env/bin/activate
    pip install -r requirements.txt

### Run the bots
Do not forget to configure your bots using the `robots.json` file or in your firebase realtime database.

    python3 main.py


## Email notificacions
If some of your wallets runs out of funds, an email can be sent to notice you. You can follow this [tutorial](https://realpython.com/python-send-email/) for creating a dedicated gmail account.