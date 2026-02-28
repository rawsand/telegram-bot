import os
import re
import base64
import requests
import threading
from datetime import datetime
from flask import Flask, request
import dropbox
from dropbox.files import WriteMode

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ========= DROPBOX ENV =========

DROPBOX_ACCOUNTS = {
    "DropBoxLink": {
        "app_key": os.environ.get("APP_KEY_CASE2"),
        "app_secret": os.environ.get("APP_SECRET_CASE2"),
        "refresh_token": os.environ.get("REFRESH_TOKEN_CASE2"),
        "fixed_filename": None,
        "overwrite": False
    },
    "MC": {
        "app_key": os.environ.get("MC_APP_KEY"),
        "app_secret": os.environ.get("MC_APP_SECRET"),
        "refresh_token": os.environ.get("MC_REFRESH_TOKEN"),
        "fixed_filename": "MasterChef_Latest.mp4",
        "overwrite": True
    },
    "WOF": {
        "app_key": os.environ.get("WOF_APP_KEY"),
        "app_secret": os.environ.get("WOF_APP_SECRET"),
        "refresh_token": os.environ.get("WOF_REFRESH_TOKEN"),
        "fixed_filename": "WheelOfFortune_Latest.mp4",
        "overwrite": True
    },
    "LC": {
        "app_key": os.environ.get("LC_APP_KEY"),
        "app_secret": os.environ.get("LC_APP_SECRET"),
        "refresh_token": os.environ.get("LC_REFRESH_TOKEN"),
        "fixed_filename": "LaughterChef_Latest.mp4",
        "overwrite": True
    }
}

# ========= GITHUB =========

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

pending_links = {}

# ==========================================================
# ======================= ROUTES ===========================
# ==========================================================

@app.route("/")
def home():
    return "Bot Running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "callback_query" in data:
        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        choice = query["data"]

        url = pending_links.get(chat_id)
        if not url:
            send_message(chat_id, "❌ No pending link.")
            return "OK"

        if choice in ["Sky", "Willow", "Prime1", "Prime2"]:
            threading.Thread(
                target=update_github_only,
                args=(chat_id, url, choice)
            ).start()

        elif choice in DROPBOX_ACCOUNTS:
            threading.Thread(
                target=process_dropbox_upload,
                args=(chat_id, url, choice)
            ).start()

        del pending_links[chat_id]
        return "OK"

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]

        if "text" in data["message"]:
            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Send direct link.")
            elif text.startswith("http"):
                pending_links[chat_id] = text
                show_buttons(chat_id)

    return "OK"

# ==========================================================
# ================= TELEGRAM HELPERS =======================
# ==========================================================

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
            [{"text": "Sky", "callback_data": "Sky"},
             {"text": "Willow", "callback_data": "Willow"}],
            [{"text": "Prime1", "callback_data": "Prime1"},
             {"text": "Prime2", "callback_data": "Prime2"}],
            [{"text": "DropBoxLink", "callback_data": "DropBoxLink"}],
            [{"text": "MC", "callback_data": "MC"},
             {"text": "WOF", "callback_data": "WOF"},
             {"text": "LC", "callback_data": "LC"}]
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

# ==========================================================
# ================= DROPBOX UPLOAD =========================
# ==========================================================

def get_dropbox_client(account_key):
    acc = DROPBOX_ACCOUNTS[account_key]

    return dropbox.Dropbox(
        oauth2_refresh_token=acc["refresh_token"],
        app_key=acc["app_key"],
        app_secret=acc["app_secret"]
    )

def process_dropbox_upload(chat_id, url, account_key):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        dbx = get_dropbox_client(account_key)
        acc_config = DROPBOX_ACCOUNTS[account_key]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()

            total_size = int(r.headers.get("Content-Length", 0))

            if acc_config["fixed_filename"]:
                filename = acc_config["fixed_filename"]
            else:
                filename = extract_filename(r.headers)

            path = f"/{filename}"

            # Space check
            usage = dbx.users_get_space_usage()
            free = usage.allocation.get_individual().allocated - usage.used

            if total_size and total_size > free:
                edit_message(chat_id, message_id,
                             "❌ Dropbox Full. Delete files and retry.")
                return

            edit_message(chat_id, message_id,
                         f"⬆ Starting upload...\n{filename}")

            chunk_size = 8 * 1024 * 1024
            uploaded = 0

            session_start = dbx.files_upload_session_start(
                r.raw.read(chunk_size)
            )

            cursor = dropbox.files.UploadSessionCursor(
                session_id=session_start.session_id,
                offset=chunk_size
            )

            commit = dropbox.files.CommitInfo(
                path=path,
                mode=WriteMode.overwrite if acc_config["overwrite"]
                else WriteMode.add
            )

            uploaded = chunk_size

            while True:
                chunk = r.raw.read(chunk_size)
                if not chunk:
                    break

                dbx.files_upload_session_append_v2(chunk, cursor)
                cursor.offset += len(chunk)
                uploaded += len(chunk)

                if total_size:
                    percent = int((uploaded / total_size) * 100)
                    edit_message(chat_id, message_id,
                                 f"⬆ Uploading: {percent}%")

            dbx.files_upload_session_finish(b"", cursor, commit)

        link = dbx.sharing_create_shared_link_with_settings(path).url
        link = link.replace("?dl=0", "?dl=1")

        if account_key == "DropBoxLink":
            update_github_link(url, "DropBoxLink")

        edit_message(chat_id, message_id,
                     f"✅ Upload Complete!\n\n{link}")

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ==========================================================
# ================= GITHUB ================================
# ==========================================================

def update_github_only(chat_id, url, title):
    try:
        update_github_link(url, title)
        send_message(chat_id, "✅ GitHub updated.")
    except Exception as e:
        send_message(chat_id, f"❌ GitHub error: {str(e)}")

def update_github_link(new_link, title):
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/links.txt"

    res = requests.get(api, headers=headers).json()
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
        api,
        headers=headers,
        json={
            "message": f"Update link for {title}",
            "content": encoded,
            "sha": res["sha"]
        }
    )

# ==========================================================
# ================= FILENAME ===============================
# ==========================================================

def extract_filename(headers):
    cd = headers.get("Content-Disposition")
    if cd:
        match = re.findall('filename="?([^"]+)"?', cd)
        if match:
            return match[0]

    return "DirectUpload.mp4"

# ==========================================================
# ================= MAIN ===================================
# ==========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
