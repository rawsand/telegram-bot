import os
import re
import base64
import requests
import threading
from datetime import datetime
from flask import Flask, request
from dropbox_handler import DropboxHandler

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ================= DROPBOX ACCOUNTS =================

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

# GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

# Handlers
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

    # ================= CALLBACK =================
    if "callback_query" in data:
        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        choice = query["data"]

        url = pending_links.get(chat_id)

        if not url:
            send_message(chat_id, "❌ No pending link found.")
            return "OK"

        # ================= GITHUB ONLY =================
        if choice in ["Sky", "Willow", "Prime1", "Prime2"]:
            threading.Thread(
                target=update_github_only,
                args=(chat_id, url, choice)
            ).start()

        # ================= DROPBOX DIRECT =================
        elif choice in ["MC", "WOF", "LC"]:
            threading.Thread(
                target=process_direct_upload,
                args=(chat_id, url, choice)
            ).start()

        # ================= DROPBOXLINK (CASE2) =================
        elif choice == "DropBoxLink":
            threading.Thread(
                target=process_dropbox_case2,
                args=(chat_id, url)
            ).start()

        # ================= DELETE OPTIONS =================
        elif choice.startswith("DELETE_ONE|"):
            filename = choice.split("|")[1]
            delete_one_file(chat_id, filename)

        elif choice == "DELETE_ALL":
            delete_all_files(chat_id)

        elif choice == "RETRY_UPLOAD":
            threading.Thread(
                target=process_dropbox_case2,
                args=(chat_id, url)
            ).start()

        return "OK"

    # ================= MESSAGE =================
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

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

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

    send_message(chat_id, "Select destination:", keyboard)

# ================= GITHUB =================

def update_github_only(chat_id, url, title):
    try:
        update_github_link(url, title)
        send_message(chat_id, "✅ GitHub updated successfully.")
        del pending_links[chat_id]
    except Exception as e:
        send_message(chat_id, f"❌ GitHub error: {str(e)}")

def update_github_link(new_link, title):
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/links.txt"

    res = requests.get(api_url, headers=headers).json()
    decoded = base64.b64decode(res["content"]).decode()
    lines = decoded.splitlines()

    for i in range(len(lines)):
        if lines[i].strip().lower() == title.strip().lower():
            if i + 1 < len(lines):
                lines[i + 1] = new_link
            break

    updated_content = "\n".join(lines)
    encoded = base64.b64encode(updated_content.encode()).decode()

    requests.put(
        api_url,
        headers=headers,
        json={
            "message": f"Update link for {title}",
            "content": encoded,
            "sha": res["sha"]
        }
    )

# ================= DIRECT DROPBOX =================

def process_direct_upload(chat_id, url, account_type):
    handler = get_handler(account_type)
    upload_to_dropbox(chat_id, url, handler)

def process_dropbox_case2(chat_id, url):
    upload_to_dropbox(chat_id, url, handler_case2, allow_delete=True)

def upload_to_dropbox(chat_id, url, handler, allow_delete=False):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            filename = extract_filename(r.headers)
            dbx = handler.get_client()

            filename = ensure_unique_filename(dbx, filename)

            edit_message(chat_id, message_id, f"⬆ Uploading {filename}")

            success = handler.upload_stream(r.raw, f"/{filename}")

        if not success:
            edit_message(chat_id, message_id, "❌ Upload failed.")
            return

        link = handler.generate_share_link(f"/{filename}")
        edit_message(chat_id, message_id, f"✅ Upload successful\n\n{link}")

        del pending_links[chat_id]

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

def get_handler(account_type):
    if account_type == "MC":
        return handler_mc
    if account_type == "WOF":
        return handler_wof
    if account_type == "LC":
        return handler_lc
    return handler_case2

# ================= DELETE SYSTEM (ONLY FOR DROPBOXLINK) =================

def delete_one_file(chat_id, filename):
    dbx = handler_case2.get_client()
    dbx.files_delete_v2(f"/{filename}")
    send_message(chat_id, f"Deleted {filename}")

def delete_all_files(chat_id):
    dbx = handler_case2.get_client()
    files = dbx.files_list_folder("").entries
    for file in files:
        dbx.files_delete_v2(f"/{file.name}")
    send_message(chat_id, "All files deleted.")

# ================= HELPERS =================

def extract_filename(headers):
    cd = headers.get("Content-Disposition")
    if cd:
        match = re.findall('filename="?([^"]+)"?', cd)
        if match:
            return match[0]
    return "DirectUpload.mp4"

def ensure_unique_filename(dbx, filename):
    try:
        dbx.files_get_metadata(f"/{filename}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(filename)
        return f"{name}_{timestamp}{ext}"
    except:
        return filename

# ================= MAIN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
