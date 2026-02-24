import os
import requests
from flask import Flask, request
from dropbox_handler import DropboxHandler

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

handler = DropboxHandler(APP_KEY, APP_SECRET, REFRESH_TOKEN)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

@app.route("/")
def home():
    return "Bot is running."

def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=60,
    )

def edit_message(chat_id, message_id, text):
    requests.post(
        f"{TELEGRAM_API}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        },
        timeout=60,
    )

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" not in data:
        return "OK"

    message = data["message"]
    chat_id = message["chat"]["id"]

    # Detect video or document
    if "video" in message:
        file_info = message["video"]
    elif "document" in message:
        file_info = message["document"]
    else:
        send_message(chat_id, "Please forward a video file.")
        return "OK"

    file_id = file_info["file_id"]
    file_name = file_info.get("file_name", "uploaded_video.mp4")
    file_size = file_info.get("file_size", 0)

    # 2GB limit check
    if file_size > 2 * 1024 * 1024 * 1024:
        send_message(chat_id, "File exceeds 2GB Telegram limit.")
        return "OK"

    # Initial progress message
    progress_msg = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": "Starting upload..."},
    ).json()

    message_id = progress_msg["result"]["message_id"]

    # Get file path from Telegram
    file_response = requests.get(
        f"{TELEGRAM_API}/getFile",
        params={"file_id": file_id},
        timeout=60,
    ).json()

    file_path = file_response["result"]["file_path"]

    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    response = requests.get(download_url, stream=True, timeout=300)

    thresholds = []
    if file_size < 700 * 1024 * 1024:
        thresholds = [50, 100]
    else:
        thresholds = [20, 40, 60, 80, 100]

    sent_thresholds = set()

    def progress_callback(uploaded, total):
        percent = int((uploaded / total) * 100)
        for t in thresholds:
            if percent >= t and t not in sent_thresholds:
                sent_thresholds.add(t)
                edit_message(
                    chat_id,
                    message_id,
                    f"Uploading... {t}%"
                )

    success = handler.upload_stream(
        response.raw,
        file_size,
        "/Latest_Video.mp4",
        progress_callback
    )

    if not success:
        edit_message(chat_id, message_id, "Upload failed.")
        return "OK"

    link = handler.generate_share_link("/Latest_Video.mp4")

    edit_message(
        chat_id,
        message_id,
        f"Upload Successful ✅\n\nDropbox Link:\n{link}"
    )

    return "OK"
