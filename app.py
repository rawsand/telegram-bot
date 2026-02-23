import os
import requests
import threading
from flask import Flask, request
from dropbox_handler import DropboxHandler

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

handler = DropboxHandler(APP_KEY, APP_SECRET, REFRESH_TOKEN)


@app.route("/")
def home():
    return "Bot is running"


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]

        if "text" in data["message"]:
            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Send me a direct downloadable file URL.")

            elif text.startswith("http"):
                # Run in background thread
                threading.Thread(target=process_url, args=(chat_id, text)).start()

    return "OK"  # VERY IMPORTANT (instant response)


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    )


def process_url(chat_id, url):
    try:
        send_message(chat_id, "Downloading and uploading...")

        dropbox_path = "/MasterChef_Latest.mp4"

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            success = handler.upload_stream(r.raw, dropbox_path)

        if not success:
            send_message(chat_id, "Upload failed.")
            return

        link = handler.generate_share_link(dropbox_path)
        send_message(chat_id, f"Upload successful:\n{link}")

    except Exception as e:
        send_message(chat_id, f"Error: {str(e)}")
