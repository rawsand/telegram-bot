import os
import threading
import time
import requests
import dropbox
from flask import Flask
from dropbox_handler import DropboxHandler

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

handler = DropboxHandler(APP_KEY, APP_SECRET, REFRESH_TOKEN)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

last_update_id = None


@app.route("/")
def home():
    return "Bot is running."


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

    debug_msg = send_message(chat_id, "DEBUG: File received.")
    debug_id = debug_msg["result"]["message_id"]

    try:
        edit_message(chat_id, debug_id, "DEBUG: Getting Telegram file path...")

        file_response = requests.get(
            f"{TELEGRAM_API}/getFile",
            params={"file_id": file_id},
            timeout=60,
        ).json()

        file_path = file_response["result"]["file_path"]

        edit_message(chat_id, debug_id, "DEBUG: File path received.")

        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

        edit_message(chat_id, debug_id, "DEBUG: Starting Telegram download...")

        telegram_response = requests.get(
            download_url,
            stream=True,
            timeout=600,
        )

        edit_message(chat_id, debug_id, "DEBUG: Telegram download connection established.")

        progress_msg = send_message(chat_id, "Starting upload...")
        message_id = progress_msg["result"]["message_id"]

        CHUNK_SIZE = 8 * 1024 * 1024
        uploaded = 0

        edit_message(chat_id, debug_id, "DEBUG: Waiting for first chunk...")

        first_chunk = next(telegram_response.iter_content(CHUNK_SIZE))

        if not first_chunk:
            edit_message(chat_id, debug_id, "DEBUG: No first chunk received!")
            return

        edit_message(chat_id, debug_id, "DEBUG: First chunk received. Starting Dropbox session...")

        dbx = handler.get_client()

        session_start = dbx.files_upload_session_start(first_chunk)
        uploaded += len(first_chunk)

        edit_message(chat_id, debug_id, "DEBUG: Dropbox session started.")

        cursor = dropbox.files.UploadSessionCursor(
            session_id=session_start.session_id,
            offset=uploaded,
        )

        commit = dropbox.files.CommitInfo(
            path="/Latest_Video.mp4",
            mode=dropbox.files.WriteMode("overwrite"),
        )

        # thresholds
        if file_size < 700 * 1024 * 1024:
            thresholds = [50, 100]
        else:
            thresholds = [20, 40, 60, 80, 100]

        sent_thresholds = set()

        for chunk in telegram_response.iter_content(CHUNK_SIZE):
            if not chunk:
                break

            dbx.files_upload_session_append_v2(chunk, cursor)
            uploaded += len(chunk)
            cursor.offset = uploaded

            percent = int((uploaded / file_size) * 100)

            for t in thresholds:
                if percent >= t and t not in sent_thresholds:
                    sent_thresholds.add(t)
                    edit_message(chat_id, message_id, f"Uploading... {t}%")

        edit_message(chat_id, debug_id, "DEBUG: Finishing Dropbox session...")

        dbx.files_upload_session_finish(b"", cursor, commit)

        edit_message(chat_id, debug_id, "DEBUG: Upload finished. Generating link...")

        link = handler.generate_share_link("/Latest_Video.mp4")

        edit_message(
            chat_id,
            message_id,
            f"Upload Successful ✅\n\nDropbox Link:\n{link}"
        )

        edit_message(chat_id, debug_id, "DEBUG: Done.")

    except Exception as e:
        edit_message(chat_id, debug_id, f"DEBUG ERROR: {str(e)}")


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
    print("Bot started in hybrid polling mode...")

    threading.Thread(target=poll_updates).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
