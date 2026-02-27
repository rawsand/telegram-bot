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

# Case 1 Dropbox (existing)
APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

# Case 2 Dropbox (separate account)
APP_KEY_CASE2 = os.environ.get("APP_KEY_CASE2")
APP_SECRET_CASE2 = os.environ.get("APP_SECRET_CASE2")
REFRESH_TOKEN_CASE2 = os.environ.get("REFRESH_TOKEN_CASE2")

# GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

handler_case1 = DropboxHandler(APP_KEY, APP_SECRET, REFRESH_TOKEN)
handler_case2 = DropboxHandler(APP_KEY_CASE2, APP_SECRET_CASE2, REFRESH_TOKEN_CASE2)

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

        if not url:
            send_message(chat_id, "❌ No pending link found.")
            return "OK"

        if choice == "DropBoxLink":
            threading.Thread(
                target=process_dropbox_case2,
                args=(chat_id, url)
            ).start()
        else:
            threading.Thread(
                target=update_github_only,
                args=(chat_id, url, choice)
            ).start()

        del pending_links[chat_id]
        return "OK"

    # ===== MESSAGE HANDLING =====
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

# ================= CASE 2 =================

def process_dropbox_case2(chat_id, url):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()

            total_size = int(r.headers.get("Content-Length", 0))
            filename = extract_filename(r.headers)

            dbx = handler_case2.get_client()

            # Check space
            usage = dbx.users_get_space_usage()
            free_space = usage.allocation.get_individual().allocated - usage.used

            if total_size and total_size > free_space:
                edit_message(chat_id, message_id, "❌ Not enough Dropbox space.")
                return

            filename = ensure_unique_filename(dbx, filename)

            edit_message(chat_id, message_id,
                         f"⬆ Starting upload...\nFile: {filename}")

            # ===== PROGRESS SETUP =====
            gap = 50 if total_size and total_size < 700 * 1024 * 1024 else 20

            def progress_callback(uploaded_bytes, next_percent, gap_value):
                if not total_size:
                    return

                percent = int((uploaded_bytes / total_size) * 100)

                if percent >= progress_callback.next_percent:
                    edit_message(chat_id, message_id,
                                 f"⬆ Uploading: {percent}%")
                    progress_callback.next_percent += gap_value

            progress_callback.next_percent = gap

            # ===== UPLOAD =====
            success = handler_case2.upload_stream(
                r.raw,
                f"/{filename}",
                progress_callback=progress_callback,
                total_size=total_size
            )

        if not success:
            edit_message(chat_id, message_id, "❌ Upload failed.")
            return

        link = handler_case2.generate_share_link(f"/{filename}")

        # Update original link in GitHub under DropBoxLink
        update_github_link(url, "DropBoxLink")

        edit_message(
            chat_id,
            message_id,
            f"✅ Upload successful!\n\nDropbox Link:\n{link}"
        )

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ================= GITHUB =================

def update_github_only(chat_id, url, title):
    try:
        update_github_link(url, title)
        send_message(chat_id, "✅ GitHub updated successfully.")
    except Exception as e:
        send_message(chat_id, f"❌ GitHub error: {str(e)}")

def update_github_link(new_link, title=None):
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/links.txt"

    res = requests.get(api_url, headers=headers).json()
    decoded = base64.b64decode(res["content"]).decode()
    lines = decoded.splitlines()

    if title:
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

# ================= FILENAME =================

def extract_filename(headers):
    cd = headers.get("Content-Disposition")
    if cd:
        match = re.findall('filename="?([^"]+)"?', cd)
        if match:
            return match[0]

    content_type = headers.get("Content-Type", "")
    if "mp4" in content_type:
        return "DirectUpload.mp4"

    return "DirectUpload.bin"

def ensure_unique_filename(dbx, filename):
    try:
        dbx.files_get_metadata(f"/{filename}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(filename)
        return f"{name}_{timestamp}{ext}"
    except Exception as e:
        if "not_found" in str(e):
            return filename
        raise e

# ================= MAIN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
