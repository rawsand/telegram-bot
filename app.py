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
    
            # ================= CASE 1 =================
            # Formatted message with filename + link
            extracted_link, detected_show = extract_link_from_formatted_message(text)
    
            if extracted_link and detected_show:
    
                if detected_show == "MC":
                    threading.Thread(
                        target=upload_file,
                        args=(chat_id, extracted_link, MC_HANDLER, None, False, True)
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
    
            # ================= CASE 2 =================
            # Direct link
            elif text.startswith("http"):
    
                try:
                    r = requests.head(text, allow_redirects=True)
                    filename = extract_filename(r.headers, text).lower()
    
                    if "masterchef" in filename:
                        threading.Thread(
                            target=upload_file,
                            args=(chat_id, text, MC_HANDLER, None, False, True)
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

# ================= UPLOAD ENGINE =================

def upload_file(chat_id, url, handler, fixed_name, overwrite, enable_delete):
    try:
        status = send_message(chat_id, "🔍 Checking file...")
        message_id = status.json()["result"]["message_id"]

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0))

            if fixed_name:
                filename = fixed_name
            else:
                filename = extract_filename(r.headers, url)

            dbx = handler.get_client()

            # Only check space if NOT overwrite
            if not overwrite:
                usage = dbx.users_get_space_usage()
                if hasattr(usage.allocation, "allocated"):
                    total_space = usage.allocation.allocated
                else:
                    total_space = usage.allocation.get_individual().allocated
                
                free_space = total_space - usage.used

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

            size_mb = round(total_size / (1024 * 1024), 2) if total_size else "Unknown"

            edit_message(chat_id, message_id,
                         f"⬆ Starting upload...\nFile: {filename}\nSize: {size_mb} MB")
            
            progress_msg = send_message(chat_id, "⬆ Uploading: 0%")
            progress_id = progress_msg.json()["result"]["message_id"]
        
            gap = 20
            next_percent = gap

            def progress_callback(uploaded_bytes, *_):
                nonlocal next_percent
                if not total_size:
                    return

                percent = int((uploaded_bytes / total_size) * 100)

                if percent >= next_percent:
                    edit_message(chat_id, progress_id,
                                 f"-> Uploading: {percent}%")
                    next_percent += gap

            success = handler.upload_stream(
                r.raw,
                f"/{filename}",
                progress_callback=progress_callback,
                total_size=total_size,
                overwrite=overwrite
            )

        edit_message(chat_id, progress_id, "-> Uploading: 100%")
        
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

# ================= DELETE =================

def show_delete_menu(chat_id):
    handler = pending_handlers.get(chat_id, DROPBOXLINK_HANDLER)
    dbx = handler.get_client()

    try:
        result = dbx.files_list_folder(path="")
        entries = result.entries
        print([entry.name for entry in entries])
        # Handle pagination
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            entries.extend(result.entries)

    except Exception as e:
        send_message(chat_id, f"❌ Could not fetch file list.\n{str(e)}")
        return

    if not entries:
        send_message(chat_id, "⚠ No files found in Dropbox root.")
        return

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
    handler = pending_handlers.get(chat_id, DROPBOXLINK_HANDLER)
    dbx = handler.get_client()
    dbx.files_delete_v2(f"/{filename}")
    send_message(chat_id, f"🗑 Deleted {filename}")
    retry_upload(chat_id)

def delete_all_files(chat_id):
    handler = pending_handlers.get(chat_id, DROPBOXLINK_HANDLER)
    dbx = handler.get_client()
    result = dbx.files_list_folder("")
    for entry in result.entries:
        dbx.files_delete_v2(f"/{entry.name}")
    send_message(chat_id, "🗑 All files deleted.")
    retry_upload(chat_id)

def retry_upload(chat_id):
    url = pending_links.get(chat_id)
    handler = pending_handlers.get(chat_id, DROPBOXLINK_HANDLER)
    if url:
        threading.Thread(
            target=upload_file,
            args=(chat_id, url, handler, None, False, True)
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

def extract_filename(headers, url):

    # 1️⃣ Try Content-Disposition header (browser-style filename)
    cd = headers.get("Content-Disposition")
    if cd:
        match = re.findall(r'filename\*?=(?:UTF-8\'\')?"?([^\";]+)"?', cd)
        if match:
            filename = match[0].strip()
            base, ext = os.path.splitext(filename)
            return (base[:50-len(ext)] + ext)[:50]

    # 2️⃣ Try extracting from URL path
    if url:
        clean_url = url.split("?")[0]
        filename_from_url = clean_url.rstrip("/").split("/")[-1]

        if "." in filename_from_url and len(filename_from_url) > 3:
            base, ext = os.path.splitext(filename_from_url.strip())
            return (base[:50-len(ext)] + ext)[:50]

    # 3️⃣ Final fallback
    fallback = f"DirectUpload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    base, ext = os.path.splitext(fallback)
    return (base[:50-len(ext)] + ext)[:50]
    
# ================= MAIN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
