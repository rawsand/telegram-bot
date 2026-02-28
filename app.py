import os
import requests
import dropbox
from flask import Flask, request
from github import Github
from urllib.parse import urlparse
from dropbox.files import WriteMode
from dropbox.exceptions import ApiError
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

app = Flask(__name__)

# ================= ENV =================

BOT_TOKEN = os.getenv("BOT_TOKEN")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH")
GITHUB_FILE_PATH = os.getenv("GITHUB_FILE_PATH")

MC_APP_KEY = os.getenv("MC_APP_KEY")
MC_APP_SECRET = os.getenv("MC_APP_SECRET")
MC_REFRESH_TOKEN = os.getenv("MC_REFRESH_TOKEN")

WOF_APP_KEY = os.getenv("WOF_APP_KEY")
WOF_APP_SECRET = os.getenv("WOF_APP_SECRET")
WOF_REFRESH_TOKEN = os.getenv("WOF_REFRESH_TOKEN")

LC_APP_KEY = os.getenv("LC_APP_KEY")
LC_APP_SECRET = os.getenv("LC_APP_SECRET")
LC_REFRESH_TOKEN = os.getenv("LC_REFRESH_TOKEN")

APP_KEY_CASE2 = os.getenv("APP_KEY_CASE2")
APP_SECRET_CASE2 = os.getenv("APP_SECRET_CASE2")
REFRESH_TOKEN_CASE2 = os.getenv("REFRESH_TOKEN_CASE2")

# ================= TELEGRAM =================

bot = Bot(BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# ================= DROPBOX =================

def get_dbx(app_key, app_secret, refresh_token):
    return dropbox.Dropbox(
        app_key=app_key,
        app_secret=app_secret,
        oauth2_refresh_token=refresh_token
    )

dbx_mc = lambda: get_dbx(MC_APP_KEY, MC_APP_SECRET, MC_REFRESH_TOKEN)
dbx_wof = lambda: get_dbx(WOF_APP_KEY, WOF_APP_SECRET, WOF_REFRESH_TOKEN)
dbx_lc = lambda: get_dbx(LC_APP_KEY, LC_APP_SECRET, LC_REFRESH_TOKEN)
dbx_link = lambda: get_dbx(APP_KEY_CASE2, APP_SECRET_CASE2, REFRESH_TOKEN_CASE2)

# ================= UTIL =================

def extract_filename(url):
    path = urlparse(url).path
    name = os.path.basename(path)
    if not name or "." not in name:
        name = "video.mp4"
    return name

def update_github(original_link, new_link):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    file = repo.get_contents(GITHUB_FILE_PATH, ref=GITHUB_BRANCH)
    content = file.decoded_content.decode()

    content = content.replace(original_link, new_link)

    repo.update_file(
        GITHUB_FILE_PATH,
        "Update link",
        content,
        file.sha,
        branch=GITHUB_BRANCH
    )

# ================= UPLOAD CORE =================

def upload_stream(dbx, url, dropbox_path, chat_id, message_id, overwrite=False):

    r = requests.get(url, stream=True)
    total = int(r.headers.get("content-length", 0))
    uploaded = 0

    mode = WriteMode.overwrite if overwrite else WriteMode.add
    uploader = dbx.files_upload_session_start(b"")

    session_id = uploader.session_id
    offset = 0
    chunk_size = 4 * 1024 * 1024

    for chunk in r.iter_content(chunk_size):
        if chunk:
            if offset == 0:
                dbx.files_upload_session_append_v2(
                    chunk,
                    dropbox.files.UploadSessionCursor(session_id, offset)
                )
            else:
                dbx.files_upload_session_append_v2(
                    chunk,
                    dropbox.files.UploadSessionCursor(session_id, offset)
                )

            offset += len(chunk)
            uploaded += len(chunk)

            if total:
                percent = int(uploaded * 100 / total)
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"⬆ Uploading... {percent}%"
                )

    commit = dropbox.files.CommitInfo(path=dropbox_path, mode=mode)

    dbx.files_upload_session_finish(
        b"",
        dropbox.files.UploadSessionCursor(session_id, offset),
        commit
    )

# ================= DROPBOX FULL HANDLER =================

def handle_full(dbx, chat_id):
    entries = dbx.files_list_folder("").entries
    buttons = []

    for file in entries[:5]:
        buttons.append([InlineKeyboardButton(
            f"Delete {file.name}",
            callback_data=f"delete_one|{file.path_lower}"
        )])

    buttons.append([InlineKeyboardButton("Delete ALL", callback_data="delete_all")])

    bot.send_message(
        chat_id,
        "❌ Dropbox Full. Delete files below.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ================= COMMAND =================

def start(update, context):
    keyboard = [
        [
            InlineKeyboardButton("Sky Willow Prime1", callback_data="prime1"),
            InlineKeyboardButton("Sky Willow Prime2", callback_data="prime2")
        ],
        [
            InlineKeyboardButton("DropBoxLink", callback_data="dropboxlink")
        ],
        [
            InlineKeyboardButton("MC", callback_data="mc"),
            InlineKeyboardButton("WOF", callback_data="wof"),
            InlineKeyboardButton("LC", callback_data="lc")
        ]
    ]
    update.message.reply_text(
        "Select option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

dispatcher.add_handler(CommandHandler("start", start))

# ================= CALLBACK =================

def button(update, context):
    query = update.callback_query
    query.answer()

    context.user_data["option"] = query.data
    query.edit_message_text("Send URL now...")

dispatcher.add_handler(CallbackQueryHandler(button))

# ================= MESSAGE =================

def handle_message(update, context):

    url = update.message.text
    option = context.user_data.get("option")

    msg = update.message.reply_text("🔍 Checking file...")

    try:

        if option in ["mc", "wof", "lc"]:

            fixed_names = {
                "mc": "MasterChef_Latest.mp4",
                "wof": "WheelOfFortune_Latest.mp4",
                "lc": "LaughterChef_Latest.mp4"
            }

            dbx_map = {
                "mc": dbx_mc(),
                "wof": dbx_wof(),
                "lc": dbx_lc()
            }

            dbx = dbx_map[option]
            filename = fixed_names[option]
            path = f"/{filename}"

            upload_stream(dbx, url, path,
                          update.message.chat_id,
                          msg.message_id,
                          overwrite=True)

            update_github(url, url)
            bot.edit_message_text("✅ Uploaded & Overwritten",
                                  update.message.chat_id,
                                  msg.message_id)

        elif option == "dropboxlink":

            dbx = dbx_link()
            filename = extract_filename(url)
            path = f"/{filename}"

            try:
                upload_stream(dbx, url, path,
                              update.message.chat_id,
                              msg.message_id)

                update_github(url, url)
                bot.edit_message_text("✅ Uploaded Successfully",
                                      update.message.chat_id,
                                      msg.message_id)

            except ApiError:
                handle_full(dbx, update.message.chat_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)}",
                              update.message.chat_id,
                              msg.message_id)

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# ================= DELETE HANDLER =================

def delete_handler(update, context):
    query = update.callback_query
    query.answer()

    dbx = dbx_link()

    data = query.data

    if data.startswith("delete_one"):
        path = data.split("|")[1]
        dbx.files_delete_v2(path)

    elif data == "delete_all":
        entries = dbx.files_list_folder("").entries
        for file in entries:
            dbx.files_delete_v2(file.path_lower)

    query.edit_message_text("🗑 Deleted. Retry upload.")

dispatcher.add_handler(CallbackQueryHandler(delete_handler, pattern="delete_"))

# ================= FLASK =================

@app.route("/", methods=["POST"])
def webhook():
    dispatcher.process_update(
        dropbox.Dropbox._json_decoder(request.get_json(force=True))
    )
    return "OK"

if __name__ == "__main__":
    app.run()
