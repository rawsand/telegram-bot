import os
import re
import base64
import requests
import threading
from datetime import datetime
from flask import Flask, request
from dropbox_handler import DropboxHandler
from dropbox.files import WriteMode
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
pending_handlers = {}

# ================= ROUTES =================

@app.route("/")
def home():
    return "Bot running"

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()

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
            pending_handlers[chat_id] = DROPBOXLINK_HANDLER
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, DROPBOXLINK_HANDLER, None, False, True)
            ).start()

        elif choice == "MC":
            pending_handlers[chat_id] = MC_HANDLER
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, MC_HANDLER, None, False, True)
            ).start()

        elif choice == "WOF":
            pending_handlers[chat_id] = WOF_HANDLER
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, WOF_HANDLER, "WheelOfFortune_Latest.mp4", True, False)
            ).start()

        elif choice == "LC":
            pending_handlers[chat_id] = LC_HANDLER
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, LC_HANDLER, "LaughterChef_Latest.mp4", True, False)
            ).start()

        return "OK"

    if "message" in data:

        chat_id = data["message"]["chat"]["id"]

        if "text" in data["message"]:

            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Send a direct link.")

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

            elif text.startswith("http"):

                try:
                    r = requests.head(text, allow_redirects=True)
                    filename = extract_filename(r.headers, text).lower()

                    if "masterchef" in filename:
                        threading.Thread(
                            target=upload_file,
                            args=(chat_id, text, MC_HANDLER, "MasterChef_Latest.mp4", True, False)
                        ).start()

                    elif "wheel" in filename and "fortune" in filename:
                        threading.Thread(
                            target=upload_file,
                            args=(chat_id, text, WOF_HANDLER, "WheelOfFortune_Latest.mp4", True, False)
                        ).start()

                    elif "laughter" in filename and "chef" in filename:
                        threading.Thread(
                            target=upload_file,
                            args=(chat_id, text, LC_HANDLER, "LaughterChef_Latest.mp4", True, False)
                        ).start()

                    else:
                        pending_links[chat_id] = text
                        show_buttons(chat_id)

                except:
                    pending_links[chat_id] = text
                    show_buttons(chat_id)

        return "OK"

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

# ================= DELETE =================

def show_delete_menu(chat_id):

    handler = pending_handlers.get(chat_id)

    if not handler:
        handler = DROPBOXLINK_HANDLER

    dbx = handler.get_client()

    result = dbx.files_list_folder("")
    entries = result.entries

    keyboard = []

    for entry in entries:

        keyboard.append([{
            "text": f"Delete {entry.name}",
            "callback_data": f"delete_one::{entry.name}"
        }])

    keyboard.append([{
        "text": "Delete ALL Files",
        "callback_data": "delete_all"
    }])

    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "Select files to delete:",
            "reply_markup": {"inline_keyboard": keyboard}
        }
    )

def delete_single_file(chat_id, filename):

    handler = pending_handlers.get(chat_id)
    dbx = handler.get_client()

    dbx.files_delete_v2(f"/{filename}")

    send_message(chat_id, f"🗑 Deleted {filename}")

    retry_upload(chat_id)

def delete_all_files(chat_id):

    handler = pending_handlers.get(chat_id)
    dbx = handler.get_client()

    result = dbx.files_list_folder("")

    for entry in result.entries:
        dbx.files_delete_v2(f"/{entry.name}")

    send_message(chat_id, "🗑 All files deleted.")

    retry_upload(chat_id)

def retry_upload(chat_id):

    url = pending_links.get(chat_id)
    handler = pending_handlers.get(chat_id)

    if url and handler:

        threading.Thread(
            target=upload_file,
            args=(chat_id, url, handler, None, False, True)
        ).start()
