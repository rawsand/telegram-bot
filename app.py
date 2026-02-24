import os
import time
import requests
from dropbox_handler import DropboxHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

handler = DropboxHandler(APP_KEY, APP_SECRET, REFRESH_TOKEN)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

last_update_id = None


def send_message(chat_id, text):
    return requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=60,
    ).json()


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


def process_video(chat_id, file_id, file_name, file_size):

    progress_msg = send_message(chat_id, "Starting upload...")
    message_id = progress_msg["result"]["message_id"]

    if file_size > 2 * 1024 * 1024 * 1024:
        edit_message(chat_id, message_id, "File exceeds 2GB limit.")
        return

    # Get file path
    file_response = requests.get(
        f"{TELEGRAM_API}/getFile",
        params={"file_id": file_id},
        timeout=60,
    ).json()

    file_path = file_response["result"]["file_path"]

    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    response = requests.get(download_url, stream=True, timeout=600)

    # Progress thresholds
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
                edit_message(chat_id, message_id, f"Uploading... {t}%")

    success = handler.upload_stream(
        response.raw,
        file_size,
        "/Latest_Video.mp4",
        progress_callback
    )

    if not success:
        edit_message(chat_id, message_id, "Upload failed.")
        return

    link = handler.generate_share_link("/Latest_Video.mp4")

    edit_message(
        chat_id,
        message_id,
        f"Upload Successful ✅\n\nDropbox Link:\n{link}"
    )


def poll_updates():
    global last_update_id

    while True:
        try:
            params = {"timeout": 30}
            if last_update_id:
                params["offset"] = last_update_id + 1

            response = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params=params,
                timeout=60,
            ).json()

            if "result" in response:
                for update in response["result"]:
                    last_update_id = update["update_id"]

                    if "message" not in update:
                        continue

                    message = update["message"]
                    chat_id = message["chat"]["id"]

                    if "video" in message:
                        file_info = message["video"]
                    elif "document" in message:
                        file_info = message["document"]
                    else:
                        continue

                    file_id = file_info["file_id"]
                    file_name = file_info.get("file_name", "uploaded_video.mp4")
                    file_size = file_info.get("file_size", 0)

                    process_video(chat_id, file_id, file_name, file_size)

        except Exception as e:
            print("Polling error:", e)

        time.sleep(1)


if __name__ == "__main__":
    print("Bot started in polling mode...")
    poll_updates()
