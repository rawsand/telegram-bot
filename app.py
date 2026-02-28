import os
import re
import base64
import requests
import threading
from datetime import datetime
from flask import Flask, request
from dropbox_handler import DropboxHandler
from dropbox.files import WriteMode

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# -------- Dropbox Accounts --------
APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

APP_KEY_CASE2 = os.environ.get("APP_KEY_CASE2")
APP_SECRET_CASE2 = os.environ.get("APP_SECRET_CASE2")
REFRESH_TOKEN_CASE2 = os.environ.get("REFRESH_TOKEN_CASE2")

MC_APP_KEY = os.environ.get("MC_APP_KEY")
MC_APP_SECRET = os.environ.get("MC_APP_SECRET")
MC_REFRESH_TOKEN = os.environ.get("MC_REFRESH_TOKEN")

WOF_APP_KEY = os.environ.get("WOF_APP_KEY")
WOF_APP_SECRET = os.environ.get("WOF_APP_SECRET")
WOF_REFRESH_TOKEN = os.environ.get("WOF_REFRESH_TOKEN")

LC_APP_KEY = os.environ.get("LC_APP_KEY")
LC_APP_SECRET = os.environ.get("LC_APP_SECRET")
LC_REFRESH_TOKEN = os.environ.get("LC_REFRESH_TOKEN")

# -------- GitHub --------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

# -------- Handlers --------
handler_case2 = DropboxHandler(APP_KEY_CASE2, APP_SECRET_CASE2, REFRESH_TOKEN_CASE2)
handler_mc = DropboxHandler(MC_APP_KEY, MC_APP_SECRET, MC_REFRESH_TOKEN)
handler_wof = DropboxHandler(WOF_APP_KEY, WOF_APP_SECRET, WOF_REFRESH_TOKEN)
handler_lc = DropboxHandler(LC_APP_KEY, LC_APP_SECRET, LC_REFRESH_TOKEN)

pending_links = {}

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
        if not url:
            send_message(chat_id, "❌ No pending link found.")
            return "OK"

        if choice in ["Sky", "Willow", "Prime1", "Prime2"]:
            threading.Thread(target=update_github_only, args=(chat_id, url, choice)).start()

        elif choice == "DropBoxLink":
            threading.Thread(target=process_dropboxlink_upload, args=(chat_id, url)).start()

        elif choice in ["MC", "WOF", "LC"]:
            threading.Thread(target=process_fixed_account_upload, args=(chat_id, url, choice)).start()

        del pending_links[chat_id]
        return "OK"

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]

        if "text" in data["message"]:
            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Send a direct link.")
            elif text.startswith("http"):
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
                {"text": "DropBoxLink", "callback_data": "DropBoxLink"}
            ],
            [
                {"text": "MC", "callback_data": "MC"},
                {"text": "WOF", "callback_data": "WOF"},
                {"text": "LC", "callback_data": "LC"}
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

# ================= DROPBOXLINK (Dynamic filename) =================

def process_dropboxlink_upload(chat_id, url):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()

            filename = extract_filename(r.headers)

            success = handler_case2.upload_stream(
                r.raw,
                f"/{filename}",
                overwrite=False
            )

        if not success:
            edit_message(chat_id, message_id, "❌ Upload failed.")
            return

        link = handler_case2.generate_share_link(f"/{filename}")
        update_github_link(url, "DropBoxLink")

        edit_message(chat_id, message_id, f"✅ Upload successful!\n\n{link}")

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ================= FIXED ACCOUNT UPLOAD =================

def process_fixed_account_upload(chat_id, url, account_type):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        if account_type == "MC":
            handler = handler_mc
            filename = "MasterChef_Latest.mp4"
        elif account_type == "WOF":
            handler = handler_wof
            filename = "WheelOfFortune_Latest.mp4"
        else:
            handler = handler_lc
            filename = "LaughterChef_Latest.mp4"

        with requests.get(url, stream=True) as r:
            r.raise_for_status()

            success = handler.upload_stream(
                r.raw,
                f"/{filename}",
                overwrite=True
            )

        if not success:
            edit_message(chat_id, message_id, "❌ Upload failed.")
            return

        link = handler.generate_share_link(f"/{filename}")

        edit_message(chat_id, message_id, f"✅ Upload successful!\n\n{link}")

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ================= GITHUB =================

def update_github_only(chat_id, url, title):
    try:
        update_github_link(url, title)
        send_message(chat_id, "✅ GitHub updated successfully.")
    except Exception as e:
        send_message(chat_id, f"❌ GitHub error: {str(e)}")

def update_github_link(new_link, title):
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/links.txt"

    res = requests.get(api_url, headers=headers).json()
    decoded = base64.b64decode(res["content"]).decode()
    lines = decoded.splitlines()

    for i in range(len(lines)):
        if lines[i].strip().lower() == title.lower():
            if i + 1 < len(lines):
                lines[i + 1] = new_link
            break

    updated = "\n".join(lines)
    encoded = base64.b64encode(updated.encode()).decode()

    requests.put(
        api_url,
        headers=headers,
        json={
            "message": f"Update link for {title}",
            "content": encoded,
            "sha": res["sha"]
        }
    )

# ================= FILENAME =================

def extract_filename(headers):
    cd = headers.get("Content-Disposition")
    if cd:
        match = re.findall('filename="?([^"]+)"?', cd)
        if match:
            return match[0]
    return "DirectUpload.mp4"

# ================= MAIN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
