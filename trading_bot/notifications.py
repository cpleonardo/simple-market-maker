import smtplib, ssl
from email.message import EmailMessage
import settings

port = 465  # For SSL

# Create a secure SSL context
context = ssl.create_default_context()

def send_email(message):
    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        server.login(settings.SENDER_EMAIL, settings.EMAIL_PASSWORD)
        server.sendmail(
            settings.SENDER_EMAIL, settings.RECEIVER_EMAIL, message
        )

def send_funds_status_email(left_coin_balance, right_coin_balance, market):
    if not settings.NOTIFICATIONS_ENABLED:
        return
    left_coin, right_coin = market.split('-')
    msg = EmailMessage()
    msg.set_content(
        f'Reporte del estado de sus balances en tauros.io en el mercado {market} \n'
        f'• {left_coin_balance} {left_coin} \n'
        f'• {right_coin_balance} {right_coin}'
    )
    msg['Subject'] = f'{left_coin_balance} {left_coin}, {right_coin_balance} {right_coin}'
    msg['From'] = 'Tauros trading bot'
    msg['To'] = 'Marco Montero'
    send_email(msg.as_string())