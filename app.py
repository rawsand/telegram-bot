import os
from flask import Flask
from dropbox_handler import DropboxHandler

app = Flask(__name__)

APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

handler = DropboxHandler(APP_KEY, APP_SECRET, REFRESH_TOKEN)

@app.route("/")
def home():
    return "Bot is running."

@app.route("/test-upload")
def test_upload():
    test_content = b"Hello from Render production test"
    path = "/MasterChef_Latest.mp4"

    success = handler.upload_file(test_content, path)

    if not success:
        return "Upload failed"

    link = handler.generate_share_link(path)
    return f"Upload successful. Link: {link}"
