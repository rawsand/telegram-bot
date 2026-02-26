import os
import re
import requests
import threading
from flask import Flask, request
from dropbox_handler import DropboxHandler

app = Flask(__name__)

# ========== ENV VARIABLES ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Dropbox Accounts
MC_APP_KEY = os.environ.get("MC_APP_KEY")
MC_APP_SECRET = os.environ.get("MC_APP_SECRET")
MC_REFRESH_TOKEN = os.environ.get("MC_REFRESH_TOKEN")

WOF_APP_KEY = os.environ.get("WOF_APP_KEY")
WOF_APP_SECRET = os.environ.get("WOF_APP_SECRET")
WOF_REFRESH_TOKEN = os.environ.get("WOF_REFRESH_TOKEN")

# GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # username/repo

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Dropbox Handlers
dropbox_accounts = {
    "masterchef": DropboxHandler(MC_APP_KEY, MC_APP_SECRET, MC_REFRESH_TOKEN),
    "wheel": DropboxHandler(WOF_APP_KEY, WOF_APP_SECRET, WOF_REFRESH_TOKEN),
}

# ====================================

@app.route("/")
def home():
    return "Bot is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]

        filename, url = extract_filename_and_url(text)

        if filename and url:
            threading.Thread(
                target=process_case_logic,
                args=(chat_id, filename, url)
            ).start()
        else:
            send_message(chat_id, "❌ Could not detect file name or link.")

    return "OK"

# ====================================

def extract_filename_and_url(text):
    filename_match = re.search(r'([A-Za-z0-9_\-,\.]+\.mp4)', text, re.IGNORECASE)
    url_match = re.search(r'(https?://[^\s]+)', text)

    if not filename_match or not url_match:
        return None, None

    return filename_match.group(1).strip(), url_match.group(1).strip()

# ====================================

def detect_category(filename):
    name = filename.lower()

    if "masterchef" in name:
        return "masterchef", "/MasterChef_Latest.mp4"

    if "wheel_of_fortune" in name or "wheel" in name:
        return "wheel", "/WheelOfFortune_Latest.mp4"

    return None, None

# ====================================

def send_message(chat_id, text):
    return requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    )

def edit_message(chat_id, message_id, text):
    requests.post(
        f"{TELEGRAM_API}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text},
    )

# ====================================

def process_case_logic(chat_id, filename, url):
    try:
        category, dropbox_path = detect_category(filename)

        if not category:
            send_message(chat_id, "❌ Could not detect category.")
            return

        handler = dropbox_accounts.get(category)

        msg = send_message(chat_id, "Starting upload...")
        message_id = msg.json()["result"]["message_id"]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0))

            def progress_callback(uploaded_bytes):
                if total_size == 0:
                    return

                percent = int(uploaded_bytes * 100 / total_size)

                gap = 50 if total_size < 700 * 1024 * 1024 else 20

                if percent >= progress_callback.next_update:
                    edit_message(chat_id, message_id, f"Uploading: {percent}%")
                    progress_callback.next_update += gap

            progress_callback.next_update = 50 if total_size < 700 * 1024 * 1024 else 20

            success = handler.upload_stream(
                r.raw,
                dropbox_path,
                total_size=total_size,
                progress_callback=progress_callback
            )

        if not success:
            send_message(chat_id, "❌ Upload failed.")
            return

        dropbox_link = handler.generate_share_link(dropbox_path)

        update_github_links(filename, url)

        send_message(
            chat_id,
            f"✅ Upload successful!\nDropbox link:\n{dropbox_link}"
        )

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ====================================

def update_github_links(filename, original_link):
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/links.txt"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}"
    }

    response = requests.get(api_url, headers=headers)
    content = response.json()

    import base64
    file_content = base64.b64decode(content["content"]).decode()

    updated_content = file_content.replace(original_link, original_link)

    data = {
        "message": f"Update link for {filename}",
        "content": base64.b64encode(updated_content.encode()).decode(),
        "sha": content["sha"]
    }

    requests.put(api_url, headers=headers, json=data)

# ====================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
