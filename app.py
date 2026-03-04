import os
import re
import base64
import requests
import threading
from datetime import datetime
from flask import Flask, request
from dropbox_handler import DropboxHandler
from message_parser import extract_link_from_formatted_message

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ========= DROPBOX ACCOUNTS =========
MC_HANDLER = DropboxHandler(
    os.environ.get("MC_APP_KEY"),
    os.environ.get("MC_APP_SECRET"),
    os.environ.get("MC_REFRESH_TOKEN"),
)

WOF_HANDLER = DropboxHandler(
    os.environ.get("WOF_APP_KEY"),
    os.environ.get("WOF_APP_SECRET"),
    os.environ.get("WOF_REFRESH_TOKEN"),
)

LC_HANDLER = DropboxHandler(
    os.environ.get("LC_APP_KEY"),
    os.environ.get("LC_APP_SECRET"),
    os.environ.get("LC_REFRESH_TOKEN"),
)

DROPBOXLINK_HANDLER = DropboxHandler(
    os.environ.get("APP_KEY_CASE2"),
    os.environ.get("APP_SECRET_CASE2"),
    os.environ.get("REFRESH_TOKEN_CASE2"),
)

# ========= GITHUB =========
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

pending_links = {}

# ================= ROUTES =================

@app.route("/")
def home():
    return "Bot running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    # ===== BUTTON CALLBACK =====
    if "callback_query" in data:
        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        choice = query["data"]

        url = pending_links.get(chat_id)

        if choice.startswith("delete_one::"):
            filename = choice.split("::")[1]
            delete_single_file(chat_id, filename)
            return "OK"

        if choice == "delete_all":
            delete_all_files(chat_id)
            return "OK"

        if not url:
            send_message(chat_id, "❌ No pending link.")
            return "OK"

        if choice in ["Sky", "Willow", "Prime1", "Prime2"]:
            threading.Thread(
                target=update_github_only,
                args=(chat_id, url, choice)
            ).start()

        elif choice == "DropBoxLink":
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, DROPBOXLINK_HANDLER, None, False, True)
            ).start()

        elif choice == "MC":
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, MC_HANDLER, "MasterChef_Latest.mp4", True, False)
            ).start()

        elif choice == "WOF":
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, WOF_HANDLER, "WheelOfFortune_Latest.mp4", True, False)
            ).start()

        elif choice == "LC":
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, LC_HANDLER, "LaughterChef_Latest.mp4", True, False)
            ).start()

        return "OK"

    # ===== MESSAGE HANDLING =====
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]

        if "text" in data["message"]:
            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Send a direct link.")

            elif text.startswith("http"):
                # NEW: Process direct link in background
                threading.Thread(
                    target=process_direct_link,
                    args=(chat_id, text)
                ).start()

            else:
                # Formatted message case (unchanged)
                extracted_link, detected_show = extract_link_from_formatted_message(text)

                if extracted_link and detected_show:

                    if detected_show == "MC":
                        threading.Thread(
                            target=upload_file,
                            args=(chat_id, extracted_link, MC_HANDLER, "MasterChef_Latest.mp4", True, False)
                        ).start()

                    elif detected_show == "WOF":
                        threading.Thread(
                            target=upload_file,
                            args=(chat_id, extracted_link, WOF_HANDLER, "WheelOfFortune_Latest.mp4", True, False)
                        ).start()

                    elif detected_show == "LC":
                        threading.Thread(
                            target=upload_file,
                            args=(chat_id, extracted_link, LC_HANDLER, "LaughterChef_Latest.mp4", True, False)
                        ).start()

    return "OK"

# ================= DIRECT LINK PROCESSOR =================

def process_direct_link(chat_id, url):
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()

            filename = extract_filename(r.headers)

            # Send filename message (NEVER edited later)
            send_message(chat_id, f"📂 Detected File:\n{filename}")

            detected_show = detect_show_from_filename(filename)

            # Auto detect and upload
            if detected_show == "MC":
                upload_file(chat_id, url, MC_HANDLER,
                            "MasterChef_Latest.mp4", True, False)

            elif detected_show == "WOF":
                upload_file(chat_id, url, WOF_HANDLER,
                            "WheelOfFortune_Latest.mp4", True, False)

            elif detected_show == "LC":
                upload_file(chat_id, url, LC_HANDLER,
                            "LaughterChef_Latest.mp4", True, False)

            else:
                # Fallback to buttons
                pending_links[chat_id] = url
                show_buttons(chat_id)

    except Exception as e:
        send_message(chat_id, f"❌ Error reading link: {str(e)}")

# ================= SHOW DETECTION =================

def detect_show_from_filename(filename):
    name = filename.lower()

    if "master" in name and "chef" in name:
        return "MC"
    elif "wheel" in name and "fortune" in name:
        return "WOF"
    elif "laughter" in name and "chef" in name:
        return "LC"

    return None

# ================= TELEGRAM =================

def send_message(chat_id, text):
    return requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

def edit_message(chat_id, message_id, text):
    requests.post(
        f"{TELEGRAM_API}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
    )

def show_buttons(chat_id):
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Sky", "callback_data": "Sky"},
                {"text": "Willow", "callback_data": "Willow"}
            ],
            [
                {"text": "Prime1", "callback_data": "Prime1"},
                {"text": "Prime2", "callback_data": "Prime2"}
            ],
            [
                {"text": "MC", "callback_data": "MC"},
                {"text": "WOF", "callback_data": "WOF"},
                {"text": "LC", "callback_data": "LC"}
            ],
            [
                {"text": "DropBoxLink", "callback_data": "DropBoxLink"}
            ]
        ]
    }

    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "Select destination:",
            "reply_markup": keyboard
        }
    )

# ================= UPLOAD ENGINE =================

def upload_file(chat_id, url, handler, fixed_name, overwrite, enable_delete):
    try:
        status = send_message(chat_id, "⬆ Starting upload...")
        message_id = status.json()["result"]["message_id"]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0))

            filename = fixed_name if fixed_name else extract_filename(r.headers)
            dbx = handler.get_client()

            if not overwrite:
                usage = dbx.users_get_space_usage()
                free_space = usage.allocation.get_individual().allocated - usage.used

                if total_size and total_size > free_space:
                    if enable_delete:
                        show_delete_menu(chat_id)
                        edit_message(chat_id, message_id,
                                     "❌ Dropbox Full. Delete files below.")
                        return
                    else:
                        edit_message(chat_id, message_id,
                                     "❌ Dropbox Full.")
                        return

            gap = 20
            next_percent = gap

            def progress_callback(uploaded_bytes, *_):
                nonlocal next_percent
                if not total_size:
                    return

                percent = int((uploaded_bytes / total_size) * 100)

                if percent >= next_percent:
                    edit_message(chat_id, message_id,
                                 f"⬆ Uploading: {percent}%")
                    next_percent += gap

            success = handler.upload_stream(
                r.raw,
                f"/{filename}",
                progress_callback=progress_callback,
                total_size=total_size,
                overwrite=overwrite
            )

        if not success:
            edit_message(chat_id, message_id, "❌ Upload failed.")
            return

        link = handler.generate_share_link(f"/{filename}")

        if fixed_name:
            update_github_link(url, fixed_name.split("_")[0])
        else:
            update_github_link(url, "DropBoxLink")

        edit_message(chat_id, message_id,
                     f"✅ Upload successful!\n\n{link}")

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ================= DELETE (UNCHANGED) =================
# Your delete logic remains exactly the same as before
# (keep your existing delete functions here without modification)

# ================= GITHUB (UNCHANGED) =================
# keep your existing GitHub functions here

# ================= FILENAME =================

def extract_filename(headers):
    cd = headers.get("Content-Disposition")
    if cd:
        match = re.findall('filename="?([^"]+)"?', cd)
        if match:
            return match[0]

    return f"DirectUpload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

# ================= MAIN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
