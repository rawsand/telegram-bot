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
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    )


def process_url(chat_id, url):
    try:
        msg = send_message(chat_id, "Downloading and uploading...")
        message_id = msg.json().get("result", {}).get("message_id")  # for editing

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0))
            
            # Determine progress gap
            if total_size < 700 * 1024 * 1024:
                gap = 50
            else:
                gap = 20

            # Upload with progress
            uploaded_bytes = 0
            next_percent = gap

            CHUNK_SIZE = 8 * 1024 * 1024
            dropbox_path = "/MasterChef_Latest.mp4"
            dbx = handler.get_client()

            upload_session_start_result = dbx.files_upload_session_start(
                r.raw.read(CHUNK_SIZE)
            )
            uploaded_bytes += CHUNK_SIZE
            cursor = handler.dropbox_cursor(upload_session_start_result, uploaded_bytes)
            commit = handler.dropbox_commit_info(dropbox_path)

            while True:
                chunk = r.raw.read(CHUNK_SIZE)
                if not chunk:
                    break
                dbx.files_upload_session_append_v2(chunk, cursor)
                uploaded_bytes += len(chunk)
                cursor.offset = uploaded_bytes

                if total_size:
                    percent = int(uploaded_bytes / total_size * 100)
                    if percent >= next_percent:
                        edit_message(chat_id, message_id, f"Uploading: {percent}%")
                        next_percent += gap

            dbx.files_upload_session_finish(b"", cursor, commit)

        # Generate Dropbox link
        link = handler.generate_share_link(dropbox_path)
        send_message(chat_id, f"Upload successful ✅\nDropbox link: {link}")

    except Exception as e:
        send_message(chat_id, f"Error: {str(e)}")


def edit_message(chat_id, message_id, text):
    requests.post(
        f"{TELEGRAM_API}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text},
    )
