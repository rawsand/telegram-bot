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
                threading.Thread(target=process_url, args=(chat_id, text)).start()

    return "OK"


def send_message(chat_id, text):
    resp = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    )
    return resp


def edit_message(chat_id, message_id, text):
    requests.post(
        f"{TELEGRAM_API}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text},
    )


def process_url(chat_id, url):
    try:
        msg = send_message(chat_id, "Downloading and uploading...")
        message_id = msg.json().get("result", {}).get("message_id")

        dropbox_path = "/MasterChef_Latest.mp4"

        def progress_callback(percent):
            edit_message(chat_id, message_id, f"Uploading: {percent}%")

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            handler.upload_stream(r.raw, dropbox_path, progress_callback=progress_callback)

        # Generate shareable link
        link = handler.generate_share_link(dropbox_path)
        send_message(chat_id, f"Upload successful ✅\nDropbox link: {link}")

    except Exception as e:
        send_message(chat_id, f"Error: {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
