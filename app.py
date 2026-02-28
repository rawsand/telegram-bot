import os
import requests
import threading
import dropbox
from flask import Flask, request
from dropbox.files import WriteMode

# ==============================
# CONFIG
# ==============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DROPBOX_MC_TOKEN = os.environ.get("DROPBOX_MC_TOKEN")
DROPBOX_WOF_TOKEN = os.environ.get("DROPBOX_WOF_TOKEN")
DROPBOX_LC_TOKEN = os.environ.get("DROPBOX_LC_TOKEN")
DROPBOX_LINK_TOKEN = os.environ.get("DROPBOX_LINK_TOKEN")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

# ==============================
# DROPBOX HANDLERS
# ==============================

dbx_mc = dropbox.Dropbox(DROPBOX_MC_TOKEN)
dbx_wof = dropbox.Dropbox(DROPBOX_WOF_TOKEN)
dbx_lc = dropbox.Dropbox(DROPBOX_LC_TOKEN)
dbx_link = dropbox.Dropbox(DROPBOX_LINK_TOKEN)

# ==============================
# FIXED FILE NAMES
# ==============================

FIXED_FILES = {
    "mc": "MasterChef_Latest.mp4",
    "wof": "WheelOfFortune_Latest.mp4",
    "lc": "LaughterChef_Latest.mp4",
}

# ==============================
# RUNTIME STORAGE
# ==============================

pending_links = {}
retry_upload_data = {}

# ==============================
# TELEGRAM HELPERS
# ==============================

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{BASE_URL}/sendMessage", json=payload)


def edit_message(chat_id, message_id, text):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    }
    requests.post(f"{BASE_URL}/editMessageText", json=payload)


# ==============================
# DROPBOX UTILITIES
# ==============================

def get_free_space(dbx):
    usage = dbx.users_get_space_usage()
    allocated = usage.allocation.get_individual().allocated
    used = usage.used
    return allocated - used


def list_files(dbx):
    try:
        result = dbx.files_list_folder("")
        return result.entries
    except:
        return []


def delete_file(dbx, path):
    try:
        dbx.files_delete_v2(path)
        return True
    except:
        return False


def upload_stream(dbx, url, dropbox_filename, overwrite=False):
    r = requests.get(url, stream=True)

    mode = WriteMode.overwrite if overwrite else WriteMode.add

    dbx.files_upload(
        r.content,
        f"/{dropbox_filename}",
        mode=mode
    )


# ==============================
# DELETE MENU
# ==============================

def show_delete_menu(chat_id):
    files = list_files(dbx_link)

    if not files:
        send_message(chat_id, "No files found.")
        return

    keyboard = []

    for f in files:
        keyboard.append([{
            "text": f.name,
            "callback_data": f"delete_one|{f.path_display}"
        }])

    keyboard.append([{
        "text": "🗑 Delete ALL",
        "callback_data": "delete_all"
    }])

    send_message(chat_id, "Delete files below:", {
        "inline_keyboard": keyboard
    })


# ==============================
# RETRY UPLOAD
# ==============================

def retry_upload(chat_id):
    data = retry_upload_data.get(chat_id)

    if not data:
        send_message(chat_id, "❌ No retry data found.")
        return

    url = data["url"]

    threading.Thread(
        target=upload_file,
        args=(chat_id, url, "dropboxlink")
    ).start()


# ==============================
# MAIN UPLOAD LOGIC
# ==============================

def upload_file(chat_id, url, upload_type):

    send_message(chat_id, "🔍 Checking file...")

    if upload_type in FIXED_FILES:

        filename = FIXED_FILES[upload_type]

        if upload_type == "mc":
            dbx = dbx_mc
        elif upload_type == "wof":
            dbx = dbx_wof
        else:
            dbx = dbx_lc

        try:
            upload_stream(dbx, url, filename, overwrite=True)
            send_message(chat_id, "✅ Overwritten Successfully.")
        except Exception as e:
            send_message(chat_id, f"❌ Error: {str(e)}")

        return

    # ==============================
    # DROPBOXLINK LOGIC
    # ==============================

    if upload_type == "dropboxlink":

        files = list_files(dbx_link)

        if len(files) >= 5:
            retry_upload_data[chat_id] = {"url": url}
            send_message(chat_id, "❌ Dropbox Full. Delete files below.")
            show_delete_menu(chat_id)
            return

        filename = url.split("/")[-1].split("?")[0]

        try:
            upload_stream(dbx_link, url, filename)
            retry_upload_data.pop(chat_id, None)
            send_message(chat_id, "✅ Uploaded to DropBoxLink.")
        except Exception as e:
            send_message(chat_id, f"❌ Error: {str(e)}")


# ==============================
# TELEGRAM WEBHOOK
# ==============================

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    # ==========================
    # MESSAGE
    # ==========================

    if "message" in data:

        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text")

        if text and text.lower() in ["mc", "wof", "lc", "dropboxlink"]:
            pending_links[chat_id] = text.lower()
            send_message(chat_id, "Send the direct video link.")
            return "OK"

        if chat_id in pending_links:
            upload_type = pending_links.pop(chat_id)
            url = text
            threading.Thread(
                target=upload_file,
                args=(chat_id, url, upload_type)
            ).start()
            return "OK"

    # ==========================
    # CALLBACK QUERY
    # ==========================

    if "callback_query" in data:

        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        callback_data = query["data"]

        if callback_data.startswith("delete_one|"):
            path = callback_data.split("|")[1]
            delete_file(dbx_link, path)
            retry_upload(chat_id)

        elif callback_data == "delete_all":
            files = list_files(dbx_link)
            for f in files:
                delete_file(dbx_link, f.path_display)
            retry_upload(chat_id)

        requests.post(f"{BASE_URL}/answerCallbackQuery", json={
            "callback_query_id": query["id"]
        })

    return "OK"


# ==============================
# START
# ==============================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
