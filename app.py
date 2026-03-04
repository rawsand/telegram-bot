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

# ========= QUEUE STATE =========
upload_state = {}  # { chat_id: {"is_uploading": bool, "queue": []} }

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
            send_message(chat_id, "❌ No pending link.")
            return "OK"

        if choice == "MC":
            enqueue_upload(chat_id, url, "MC")

        elif choice == "WOF":
            enqueue_upload(chat_id, url, "WOF")

        elif choice == "LC":
            enqueue_upload(chat_id, url, "LC")

        elif choice == "DropBoxLink":
            enqueue_upload(chat_id, url, "DROPBOXLINK")

        return "OK"

    # ===== MESSAGE HANDLING =====
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]

        if "text" in data["message"]:
            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Send a direct link.")

            elif text.startswith("http"):
                enqueue_upload(chat_id, text, "AUTO")

            else:
                extracted_link, detected_show = extract_link_from_formatted_message(text)

                if extracted_link and detected_show:
                    enqueue_upload(chat_id, extracted_link, detected_show)

    return "OK"

# ================= QUEUE SYSTEM =================

def enqueue_upload(chat_id, url, mode):
    if chat_id not in upload_state:
        upload_state[chat_id] = {"is_uploading": False, "queue": []}

    state = upload_state[chat_id]

    job = {"url": url, "mode": mode}
    state["queue"].append(job)

    if state["is_uploading"]:
        position = len(state["queue"])
        send_message(chat_id,
                     f"⏳ Upload in progress.\nAdded to queue (Position: {position})")
    else:
        process_next_upload(chat_id)

def process_next_upload(chat_id):
    state = upload_state[chat_id]

    if not state["queue"]:
        state["is_uploading"] = False
        return

    state["is_uploading"] = True
    job = state["queue"].pop(0)

    threading.Thread(
        target=handle_upload_job,
        args=(chat_id, job)
    ).start()

# ================= MAIN UPLOAD LOGIC =================

def handle_upload_job(chat_id, job):
    try:
        url = job["url"]
        mode = job["mode"]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()

            filename = extract_filename(r.headers)
            send_message(chat_id, f"📂 Detected File:\n{filename}")

            detected_show = None

            if mode == "AUTO":
                detected_show = detect_show_from_filename(filename)
            else:
                detected_show = mode

            if detected_show == "MC":
                handler = MC_HANDLER
                fixed_name = "MasterChef_Latest.mp4"
                overwrite = True
                enable_delete = False

            elif detected_show == "WOF":
                handler = WOF_HANDLER
                fixed_name = "WheelOfFortune_Latest.mp4"
                overwrite = True
                enable_delete = False

            elif detected_show == "LC":
                handler = LC_HANDLER
                fixed_name = "LaughterChef_Latest.mp4"
                overwrite = True
                enable_delete = False

            else:
                # fallback to buttons
                pending_links[chat_id] = url
                show_buttons(chat_id)
                process_next_upload(chat_id)
                return

            status = send_message(chat_id, "⬆ Starting upload...")
            message_id = status.json()["result"]["message_id"]

            total_size = int(r.headers.get("Content-Length", 0))

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
                f"/{fixed_name}",
                progress_callback=progress_callback,
                total_size=total_size,
                overwrite=overwrite
            )

        if not success:
            edit_message(chat_id, message_id, "❌ Upload failed.")
            process_next_upload(chat_id)
            return

        link = handler.generate_share_link(f"/{fixed_name}")
        update_github_link(url, fixed_name.split("_")[0])

        edit_message(chat_id, message_id,
                     f"✅ Upload successful!\n\n{link}")

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

    process_next_upload(chat_id)

# ================= DETECTION =================

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

# ================= GITHUB =================

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

    return f"DirectUpload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

# ================= MAIN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
