import os
import re
import requests
from flask import Flask, request
from dropbox_handler import DropboxHandler
from github import Github
from io import BytesIO

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPO")
FILE_PATH = os.getenv("GITHUB_FILE_PATH")
BRANCH = os.getenv("GITHUB_BRANCH")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Dropbox handlers per category
DROPBOX_ACCOUNTS = {
    "masterchef": DropboxHandler(
        os.getenv("MC_APP_KEY"),
        os.getenv("MC_APP_SECRET"),
        os.getenv("MC_REFRESH_TOKEN"),
    ),
    "wheeloffortune": DropboxHandler(
        os.getenv("WOF_APP_KEY"),
        os.getenv("WOF_APP_SECRET"),
        os.getenv("WOF_REFRESH_TOKEN"),
    ),
    "the50": DropboxHandler(
        os.getenv("T50_APP_KEY"),
        os.getenv("T50_APP_SECRET"),
        os.getenv("T50_REFRESH_TOKEN"),
    ),
    "laughterchef": DropboxHandler(
        os.getenv("LC_APP_KEY"),
        os.getenv("LC_APP_SECRET"),
        os.getenv("LC_REFRESH_TOKEN"),
    ),
}


def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })


def extract_filename_and_url(text):
    filename_match = re.search(r"File.*?:\s*(.+)", text)
    url_match = re.search(r"https?://[^\s]+", text)

    if not filename_match or not url_match:
        return None, None

    filename = filename_match.group(1).strip()
    url = url_match.group(0).strip()

    return filename, url


def detect_category(filename):
    name = filename.lower()

    if "masterchef" in name:
        return "masterchef", "/MasterChef_Latest.mp4", "# Master Chef"
    elif "wheel" in name:
        return "wheeloffortune", "/WheelOfFortune_Latest.mp4", "# Wheel of Fortune"
    elif "50" in name:
        return "the50", "/The50_Latest.mp4", "# The 50"
    elif "laughter" in name:
        return "laughterchef", "/LaughterChef_Latest.mp4", "# Laughter Chef"
    else:
        return None, None, None


def update_github_link(category_header, new_link):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    file = repo.get_contents(FILE_PATH, ref=BRANCH)
    content = file.decoded_content.decode()

    lines = content.splitlines()
    updated = []
    inside_block = False

    for line in lines:
        if line.strip() == category_header:
            inside_block = True
            updated.append(line)
            continue

        if inside_block and line.startswith("http"):
            updated.append(new_link)
            inside_block = False
            continue

        updated.append(line)

    new_content = "\n".join(updated)

    repo.update_file(
        FILE_PATH,
        f"Update link for {category_header}",
        new_content,
        file.sha,
        branch=BRANCH
    )


def stream_download_to_dropbox(url, handler, dropbox_path, chat_id):
    send_message(chat_id, "⬇️ Downloading file...")

    response = requests.get(url, stream=True)
    if response.status_code != 200:
        return False, None

    buffer = BytesIO()

    total_downloaded = 0
    for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
        if chunk:
            buffer.write(chunk)
            total_downloaded += len(chunk)

    buffer.seek(0)

    send_message(chat_id, "☁️ Uploading to Dropbox...")

    success = handler.upload_stream(
        buffer,
        dropbox_path,
        total_size=total_downloaded
    )

    if not success:
        return False, None

    link = handler.generate_share_link(dropbox_path)
    return True, link


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if "message" not in data:
        return "OK"

    message = data["message"]
    chat_id = message["chat"]["id"]

    if "text" not in message:
        send_message(chat_id, "Send a forwarded message with File Name + Download link.")
        return "OK"

    text = message["text"]

    filename, url = extract_filename_and_url(text)

    if not filename or not url:
        send_message(chat_id, "❌ Could not detect file name or link.")
        return "OK"

    category_key, dropbox_path, header = detect_category(filename)

    if not category_key:
        send_message(chat_id, "❌ Category not matched.")
        return "OK"

    handler = DROPBOX_ACCOUNTS[category_key]

    send_message(chat_id, f"📁 Category: {header}")

    success, dropbox_link = stream_download_to_dropbox(
        url, handler, dropbox_path, chat_id
    )

    if not success:
        send_message(chat_id, "❌ Upload failed.")
        return "OK"

    send_message(chat_id, "🔗 Dropbox upload completed.")

    try:
        update_github_link(header, url)
        send_message(chat_id, "✅ GitHub updated successfully.")
    except Exception as e:
        send_message(chat_id, "⚠️ GitHub update failed (Dropbox file kept).")

    send_message(chat_id, f"🎉 Done!\nDropbox Link:\n{dropbox_link}")

    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
