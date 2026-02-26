import os
import re
import requests
import threading
from flask import Flask, request
from dropbox_handler import DropboxHandler

app = Flask(__name__)

# ================= ENV VARIABLES =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

MC_APP_KEY = os.environ.get("MC_APP_KEY")
MC_APP_SECRET = os.environ.get("MC_APP_SECRET")
MC_REFRESH_TOKEN = os.environ.get("MC_REFRESH_TOKEN")

WOF_APP_KEY = os.environ.get("WOF_APP_KEY")
WOF_APP_SECRET = os.environ.get("WOF_APP_SECRET")
WOF_REFRESH_TOKEN = os.environ.get("WOF_REFRESH_TOKEN")

FIFTY_APP_KEY = os.environ.get("FIFTY_APP_KEY")
FIFTY_APP_SECRET = os.environ.get("FIFTY_APP_SECRET")
FIFTY_REFRESH_TOKEN = os.environ.get("FIFTY_REFRESH_TOKEN")

LC_APP_KEY = os.environ.get("LC_APP_KEY")
LC_APP_SECRET = os.environ.get("LC_APP_SECRET")
LC_REFRESH_TOKEN = os.environ.get("LC_REFRESH_TOKEN")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # username/repo

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ================= DROPBOX HANDLERS =================
mc_handler = DropboxHandler(MC_APP_KEY, MC_APP_SECRET, MC_REFRESH_TOKEN)
wof_handler = DropboxHandler(WOF_APP_KEY, WOF_APP_SECRET, WOF_REFRESH_TOKEN)
fifty_handler = DropboxHandler(FIFTY_APP_KEY, FIFTY_APP_SECRET, FIFTY_REFRESH_TOKEN)
lc_handler = DropboxHandler(LC_APP_KEY, LC_APP_SECRET, LC_REFRESH_TOKEN)

# ================= ROUTES =================
@app.route("/")
def home():
    return "Bot is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]

        if "text" in data["message"]:
            text = data["message"]["text"]

            if text == "/start":
                send_message(chat_id, "Forward the full message containing file name and download link.")
            else:
                threading.Thread(target=process_case_logic, args=(chat_id, text)).start()

    return "OK"

# ================= TELEGRAM FUNCTIONS =================
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

# ================= MAIN LOGIC =================
def process_case_logic(chat_id, text):
    try:
        file_match = re.search(r"File\s*Name\s*:\s*(.+\.mp4)", text, re.IGNORECASE)
        link_match = re.search(r"https?://\S+", text)

        if not file_match or not link_match:
            send_message(chat_id, "❌ Could not detect file name or link.")
            return

        file_name = file_match.group(1).strip()
        download_url = link_match.group(0).strip()

        lower_name = file_name.lower()

        # ===== CATEGORY MATCHING =====
        if "masterchef" in lower_name:
            handler = mc_handler
            dropbox_path = "/MasterChef_Latest.mp4"
            category_title = "Master Chef"

        elif "wheel" in lower_name:
            handler = wof_handler
            dropbox_path = "/WheelOfFortune_Latest.mp4"
            category_title = "Wheel of Fortune"

        elif "the_50" in lower_name or "the50" in lower_name or " 50" in lower_name:
            handler = fifty_handler
            dropbox_path = "/The50_Latest.mp4"
            category_title = "The 50"

        elif "laughter" in lower_name:
            handler = lc_handler
            dropbox_path = "/LaughterChef_Latest.mp4"
            category_title = "Laughter Chef"

        else:
            send_message(chat_id, "❌ Category not matched.")
            return

        msg = send_message(chat_id, "Starting upload...")
        message_id = msg.json()["result"]["message_id"]

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*"
        }

        with requests.get(download_url, stream=True, headers=headers) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0))

            def progress_callback(uploaded_bytes, next_percent, gap):
                if not total_size:
                    return

                percent = int(uploaded_bytes / total_size * 100)
                if percent >= progress_callback.next_percent:
                    edit_message(chat_id, message_id, f"Uploading: {percent}%")
                    progress_callback.next_percent += gap

            progress_callback.next_percent = 20 if total_size >= 700*1024*1024 else 50

            success = handler.upload_stream(
                r.raw,
                dropbox_path,
                progress_callback=progress_callback,
                total_size=total_size
            )

        if not success:
            send_message(chat_id, "❌ Upload failed.")
            return

        dropbox_link = handler.generate_share_link(dropbox_path)

        update_github_links(category_title, download_url)

        send_message(chat_id, f"✅ Upload successful!\nDropbox Link:\n{dropbox_link}")

    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

# ================= GITHUB UPDATE =================
def update_github_links(category_title, new_original_link):
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/links.txt"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}

        res = requests.get(url, headers=headers)
        data = res.json()

        import base64
        decoded = base64.b64decode(data["content"]).decode()

        lines = decoded.split("\n")
        updated_lines = []
        inside_block = False

        for line in lines:
            if category_title in line:
                inside_block = True
                updated_lines.append(line)
                continue

            if inside_block and line.startswith("http"):
                updated_lines.append(new_original_link)
                inside_block = False
            else:
                updated_lines.append(line)

        updated_content = "\n".join(updated_lines)
        encoded = base64.b64encode(updated_content.encode()).decode()

        requests.put(
            url,
            headers=headers,
            json={
                "message": f"Updated link for {category_title}",
                "content": encoded,
                "sha": data["sha"],
            },
        )
    except:
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
