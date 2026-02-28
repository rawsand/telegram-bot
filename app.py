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

# DropBoxLink (dynamic files + delete logic)
APP_KEY_CASE2 = os.environ.get("APP_KEY_CASE2")
APP_SECRET_CASE2 = os.environ.get("APP_SECRET_CASE2")
REFRESH_TOKEN_CASE2 = os.environ.get("REFRESH_TOKEN_CASE2")

# Fixed overwrite accounts
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
    APP_KEY_CASE2,
    APP_SECRET_CASE2,
    REFRESH_TOKEN_CASE2,
)

# ================= GITHUB =================

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

# ================= MEMORY =================

pending_links = {}
pending_retry_upload = {}

# ================= ROUTES =================

@app.route("/")
def home():
    return "Bot running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    # ===== CALLBACK HANDLING =====
    if "callback_query" in data:
        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        choice = query["data"]

        # DELETE LOGIC
        if choice.startswith("delete_one::"):
            filename = choice.split("::")[1]
            delete_one_file(chat_id, filename)
            return "OK"

        if choice == "delete_all":
            delete_all_files(chat_id)
            return "OK"

        url = pending_links.get(chat_id)
        if not url:
            send_message(chat_id, "❌ No pending link.")
            return "OK"

        # GitHub Only Titles
        if choice in ["Sky", "Willow", "Prime1", "Prime2"]:
            threading.Thread(
                target=update_github_only,
                args=(chat_id, url, choice),
            ).start()

        # Fixed Overwrite Accounts
        elif choice in ["MC", "WOF", "LC"]:
            threading.Thread(
                target=process_fixed_upload,
                args=(chat_id, url, choice),
            ).start()

        # DropBoxLink (dynamic)
        elif choice == "DropBoxLink":
            threading.Thread(
                target=process_dropboxlink_upload,
                args=(chat_id, url),
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
        json={"chat_id": chat_id, "text": text},
    )

def edit_message(chat_id, message_id, text):
    requests.post(
        f"{TELEGRAM_API}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        },
    )

def show_buttons(chat_id):
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Sky", "callback_data": "Sky"},
                {"text": "Willow", "callback_data": "Willow"},
            ],
            [
                {"text": "Prime1", "callback_data": "Prime1"},
                {"text": "Prime2", "callback_data": "Prime2"},
            ],
            [
                {"text": "MC", "callback_data": "MC"},
                {"text": "WOF", "callback_data": "WOF"},
                {"text": "LC", "callback_data": "LC"},
            ],
            [
                {"text": "DropBoxLink", "callback_data": "DropBoxLink"},
            ],
        ]
    }

    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "Select destination:",
            "reply_markup": keyboard,
        },
    )

# ================= FIXED OVERWRITE UPLOAD =================

def process_fixed_upload(chat_id, url, choice):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        handler = {
            "MC": MC_HANDLER,
            "WOF": WOF_HANDLER,
            "LC": LC_HANDLER,
        }[choice]

        fixed_name = {
            "MC": "MasterChef_Latest.mp4",
            "WOF": "WheelOfFortune_Latest.mp4",
            "LC": "LaughterChef_Latest.mp4",
        }[choice]

        upload_file(chat_id, message_id, url, handler, fixed_name, overwrite=True)

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ================= DROPBOXLINK UPLOAD =================

def process_dropboxlink_upload(chat_id, url):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        success = upload_file(
            chat_id,
            message_id,
            url,
            DROPBOXLINK_HANDLER,
            None,
            overwrite=False,
            enable_delete=True,
        )

        if not success:
            pending_retry_upload[chat_id] = url

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ================= CORE UPLOAD ENGINE =================

def upload_file(chat_id, message_id, url, handler, fixed_name=None,
                overwrite=False, enable_delete=False):

    with requests.get(url, stream=True) as r:
        r.raise_for_status()

        total_size = int(r.headers.get("Content-Length", 0))
        filename = fixed_name if fixed_name else extract_filename(r.headers)

        dbx = handler.get_client()

        # SPACE CHECK
        usage = dbx.users_get_space_usage()
        free_space = usage.allocation.get_individual().allocated - usage.used

        if total_size and total_size > free_space:
            if enable_delete:
                show_delete_menu(chat_id)
                edit_message(chat_id, message_id,
                             "❌ Dropbox Full. Delete files below.")
                return False
            else:
                edit_message(chat_id, message_id,
                             "❌ Dropbox Full.")
                return False

        if not overwrite:
            filename = ensure_unique_filename(dbx, filename)

        edit_message(chat_id, message_id,
                     f"⬆ Starting upload...\nFile: {filename}")

        gap = 20
        progress_next = gap

        def progress_callback(uploaded_bytes):
            nonlocal progress_next
            if not total_size:
                return
            percent = int((uploaded_bytes / total_size) * 100)
            if percent >= progress_next:
                edit_message(chat_id, message_id,
                             f"⬆ Uploading: {percent}%")
                progress_next += gap

        success = handler.upload_stream(
            r.raw,
            f"/{filename}",
            progress_callback=progress_callback,
            total_size=total_size,
            overwrite=overwrite,
        )

        if not success:
            edit_message(chat_id, message_id,
                         "❌ Upload failed.")
            return False

        link = handler.generate_share_link(f"/{filename}")

        edit_message(chat_id, message_id,
                     f"✅ Upload successful!\n\n{link}")

        return True

# ================= DELETE LOGIC =================

def show_delete_menu(chat_id):
    dbx = DROPBOXLINK_HANDLER.get_client()
    entries = dbx.files_list_folder("").entries

    keyboard = []
    for entry in entries:
        keyboard.append(
            [{"text": f"Delete {entry.name}",
              "callback_data": f"delete_one::{entry.name}"}]
        )

    keyboard.append([{"text": "Delete ALL Files",
                      "callback_data": "delete_all"}])

    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "Select files to delete:",
            "reply_markup": {"inline_keyboard": keyboard},
        },
    )

def delete_one_file(chat_id, filename):
    dbx = DROPBOXLINK_HANDLER.get_client()
    dbx.files_delete_v2(f"/{filename}")

    retry_upload(chat_id)

def delete_all_files(chat_id):
    dbx = DROPBOXLINK_HANDLER.get_client()
    entries = dbx.files_list_folder("").entries

    for entry in entries:
        dbx.files_delete_v2(entry.path_lower)

    retry_upload(chat_id)

def retry_upload(chat_id):
    url = pending_retry_upload.get(chat_id)
    if not url:
        return

    del pending_retry_upload[chat_id]
    threading.Thread(
        target=process_dropboxlink_upload,
        args=(chat_id, url),
    ).start()

# ================= GITHUB =================

def update_github_only(chat_id, url, title):
    try:
        update_github_link(url, title)
        send_message(chat_id, "✅ GitHub updated.")
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

    updated_content = "\n".join(lines)
    encoded = base64.b64encode(updated_content.encode()).decode()

    requests.put(
        api_url,
        headers=headers,
        json={
            "message": f"Update link for {title}",
            "content": encoded,
            "sha": res["sha"],
        },
    )

# ================= FILENAME =================

def extract_filename(headers):
    cd = headers.get("Content-Disposition")
    if cd:
        match = re.findall('filename="?([^"]+)"?', cd)
        if match:
            return match[0]

    return f"DirectUpload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

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
