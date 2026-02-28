import os
import requests
import dropbox
from dropbox.files import WriteMode
from dropbox.exceptions import ApiError
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ===============================
# DROPBOX INITIALIZATION (OAUTH)
# ===============================

def get_dropbox(app_key, app_secret, refresh_token):
    return dropbox.Dropbox(
        app_key=app_key,
        app_secret=app_secret,
        oauth2_refresh_token=refresh_token
    )

dbx_mc = get_dropbox(
    os.getenv("MC_APP_KEY"),
    os.getenv("MC_APP_SECRET"),
    os.getenv("MC_REFRESH_TOKEN")
)

dbx_wof = get_dropbox(
    os.getenv("WOF_APP_KEY"),
    os.getenv("WOF_APP_SECRET"),
    os.getenv("WOF_REFRESH_TOKEN")
)

dbx_lc = get_dropbox(
    os.getenv("LC_APP_KEY"),
    os.getenv("LC_APP_SECRET"),
    os.getenv("LC_REFRESH_TOKEN")
)

dbx_link = get_dropbox(
    os.getenv("LINK_APP_KEY"),
    os.getenv("LINK_APP_SECRET"),
    os.getenv("LINK_REFRESH_TOKEN")
)

# ===============================
# FILE NAME HELPERS
# ===============================

def extract_filename(url):
    name = url.split("/")[-1].split("?")[0]
    if "." not in name:
        name += ".mp4"
    return name

# ===============================
# UPLOAD FUNCTION
# ===============================

def upload_file(dbx, url, dropbox_path, overwrite=False):
    response = requests.get(url, stream=True)
    response.raise_for_status()

    mode = WriteMode.overwrite if overwrite else WriteMode.add

    dbx.files_upload(
        response.content,
        dropbox_path,
        mode=mode
    )

# ===============================
# TELEGRAM HANDLERS
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send direct video link.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    context.user_data["url"] = url

    keyboard = [
        [
            InlineKeyboardButton("Sky", callback_data="sky"),
            InlineKeyboardButton("Willow", callback_data="willow")
        ],
        [
            InlineKeyboardButton("Prime1", callback_data="prime1"),
            InlineKeyboardButton("Prime2", callback_data="prime2")
        ],
        [
            InlineKeyboardButton("DropBoxLink", callback_data="link")
        ],
        [
            InlineKeyboardButton("MC", callback_data="mc"),
            InlineKeyboardButton("WOF", callback_data="wof"),
            InlineKeyboardButton("LC", callback_data="lc")
        ]
    ]

    await update.message.reply_text(
        "Select Option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===============================
# CALLBACK HANDLER
# ===============================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get("url")
    choice = query.data

    await query.edit_message_text("🔍 Checking file...")

    try:

        # ===============================
        # MC / WOF / LC (Overwrite Mode)
        # ===============================

        if choice == "mc":
            upload_file(
                dbx_mc,
                url,
                "/MasterChef_Latest.mp4",
                overwrite=True
            )

        elif choice == "wof":
            upload_file(
                dbx_wof,
                url,
                "/WheelOfFortune_Latest.mp4",
                overwrite=True
            )

        elif choice == "lc":
            upload_file(
                dbx_lc,
                url,
                "/LaughterChef_Latest.mp4",
                overwrite=True
            )

        # ===============================
        # DropBoxLink (Storage Account)
        # ===============================

        elif choice == "link":
            filename = extract_filename(url)
            dropbox_path = f"/{filename}"

            try:
                upload_file(
                    dbx_link,
                    url,
                    dropbox_path,
                    overwrite=False
                )

            except ApiError as e:
                if "insufficient_space" in str(e):
                    files = dbx_link.files_list_folder("").entries

                    if not files:
                        await query.edit_message_text("❌ Dropbox Full.")
                        return

                    buttons = []

                    for f in files[:5]:
                        buttons.append([
                            InlineKeyboardButton(
                                f"Delete {f.name}",
                                callback_data=f"del_{f.name}"
                            )
                        ])

                    buttons.append([
                        InlineKeyboardButton(
                            "Delete ALL",
                            callback_data="del_all"
                        )
                    ])

                    await query.edit_message_text(
                        "❌ Dropbox Full. Delete files below.",
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                    return
                else:
                    raise e

        # ===============================
        # SKY / WILLOW / PRIME1 / PRIME2
        # ===============================

        elif choice in ["sky", "willow", "prime1", "prime2"]:
            await query.edit_message_text(
                f"✅ Link updated for {choice.upper()}"
            )
            return

        await query.edit_message_text("✅ Upload Successful.")

    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

# ===============================
# DELETE HANDLER
# ===============================

async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        if data == "del_all":
            files = dbx_link.files_list_folder("").entries
            for f in files:
                dbx_link.files_delete_v2(f.path_lower)

        elif data.startswith("del_"):
            name = data.replace("del_", "")
            dbx_link.files_delete_v2(f"/{name}")

        # AUTO RETRY
        url = context.user_data.get("url")
        filename = extract_filename(url)
        dropbox_path = f"/{filename}"

        upload_file(dbx_link, url, dropbox_path)

        await query.edit_message_text("✅ Deleted & Upload Successful.")

    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

# ===============================
# MAIN
# ===============================

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
app.add_handler(CallbackQueryHandler(handle_delete, pattern="^del_"))
app.add_handler(CallbackQueryHandler(handle_callback))

app.run_polling()
