import os
import os
import logging
from datetime import datetime, date
from bson.objectid import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ─── .env লোড ────────────────────────────────────────────────────────────────
load_dotenv()

# ─── Cloudinary Config ────────────────────────────────────────────────────────
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure     = True,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── MongoDB ──────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI পাওয়া যায়নি! .env ফাইল চেক করুন।")

client      = MongoClient(MONGO_URI)
db          = client["mk-love-tele-bot"]
users_col   = db["users"]           # ইউজার তথ্য
gallery_col = db["gallery"]         # ছবি + likes
notes_col   = db["notes"]           # প্রেমের নোট
dates_col   = db["special_dates"]   # বিশেষ দিন
logs_col    = db["activity_logs"]   # লগ

# gallery description-এ text index (search এর জন্য)
try:
    gallery_col.create_index([("description", "text")])
except Exception:
    pass

# ─── Config ───────────────────────────────────────────────────────────────────
USER_PASSWORD  = os.getenv("USER_PASSWORD")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
GALLERY_PAGE   = 5

# ─── Multi-step state memory ──────────────────────────────────────────────────
# { user_id: {"step": "...", ...extra data} }
USER_STATE: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
# Utility Helpers
# ══════════════════════════════════════════════════════════════════════════════

def track_user(user):
    """ইউজার MongoDB তে ট্র্যাক ও আপডেট।"""
    users_col.update_one(
        {"user_id": user.id},
        {
            "$set": {
                "user_id":     user.id,
                "first_name":  user.first_name,
                "last_name":   user.last_name or "",
                "username":    user.username or "N/A",
                "last_active": datetime.now(),
            },
            "$setOnInsert": {
                "is_authenticated": False,
                "is_admin":         False,
                "is_banned":        False,
            },
        },
        upsert=True,
    )


def get_user_doc(uid: int) -> dict:
    return users_col.find_one({"user_id": uid}) or {}


def is_authenticated(uid: int) -> bool:
    d = get_user_doc(uid)
    return d.get("is_authenticated", False) and not d.get("is_banned", False)


def is_admin(uid: int) -> bool:
    d = get_user_doc(uid)
    return d.get("is_admin", False) and not d.get("is_banned", False)


def is_banned(uid: int) -> bool:
    return get_user_doc(uid).get("is_banned", False)


def set_authenticated(uid: int, val: bool = True):
    users_col.update_one({"user_id": uid}, {"$set": {"is_authenticated": val}})


def set_admin(uid: int, val: bool = True):
    users_col.update_one(
        {"user_id": uid},
        {"$set": {"is_admin": val, "is_authenticated": True}},
    )


def set_banned(uid: int, val: bool):
    users_col.update_one({"user_id": uid}, {"$set": {"is_banned": val}})


def log_action(uid: int, username: str, action: str, details: str = ""):
    """Activity log এ entry যোগ।"""
    logs_col.insert_one({
        "user_id":   uid,
        "username":  username,
        "action":    action,
        "details":   details,
        "timestamp": datetime.now(),
    })


def chunk_text(text: str, size: int = 4000):
    """Telegram 4096 char limit এর জন্য ভাগ।"""
    return [text[i: i + size] for i in range(0, len(text), size)]


def clear_state(uid: int):
    USER_STATE.pop(uid, None)


async def _guard(update: Update, need_auth: bool = True, need_admin: bool = False) -> bool:
    """True = pass, False = blocked."""
    uid = update.effective_user.id
    msg = update.message or (update.callback_query and update.callback_query.message)
    if is_banned(uid):
        await msg.reply_text("🚫 আপনাকে এই বোট থেকে নিষিদ্ধ করা হয়েছে।")
        return False
    if need_admin and not is_admin(uid):
        await msg.reply_text("⛔ এই কাজটি করার অনুমতি আপনার নেই।")
        return False
    if need_auth and not is_authenticated(uid):
        await msg.reply_text("🔒 আগে পাসওয়ার্ড দিয়ে বোট আনলক করুন!")
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Menus
# ══════════════════════════════════════════════════════════════════════════════

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "❤️ *প্রধান মেনু*\n\nনিচের অপশনগুলো ব্যবহার করুন:"
    keyboard = [
        [InlineKeyboardButton("🖼️ ফটো গ্যালারি",    callback_data="btn_gallery_0")],
        [InlineKeyboardButton("📸 আমার ছবি",          callback_data="btn_myphotos_0")],
        [InlineKeyboardButton("💌 প্রেমের নোট",        callback_data="btn_notes_0")],
        [InlineKeyboardButton("📅 বিশেষ দিনসমূহ",     callback_data="btn_dates")],
        [InlineKeyboardButton("🔍 গ্যালারি সার্চ",    callback_data="btn_search_prompt")],
        [InlineKeyboardButton("👑 এডমিন প্যানেল",     callback_data="btn_admin_prompt")],
    ]
    msg = update.message or (update.callback_query and update.callback_query.message)
    await msg.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def show_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users  = users_col.count_documents({})
    total_photos = gallery_col.count_documents({})
    total_notes  = notes_col.count_documents({})
    total_dates  = dates_col.count_documents({})

    text = (
        "👑 *এডমিন ড্যাশবোর্ড* 👑\n\n"
        f"👥 মোট ইউজার: `{total_users}` জন\n"
        f"🖼️ মোট ছবি: `{total_photos}` টি\n"
        f"💌 মোট নোট: `{total_notes}` টি\n"
        f"📅 বিশেষ দিন: `{total_dates}` টি\n\n"
        "কন্ট্রোল করুন:"
    )
    keyboard = [
        [InlineKeyboardButton("📊 ইউজার লিস্ট",             callback_data="admin_view_users")],
        [InlineKeyboardButton("🖼️ ছবি ম্যানেজ",            callback_data="admin_manage_photos")],
        [InlineKeyboardButton("💌 নোট ম্যানেজ",             callback_data="admin_manage_notes")],
        [InlineKeyboardButton("📅 বিশেষ দিন ম্যানেজ",       callback_data="admin_manage_dates")],
        [InlineKeyboardButton("📋 Activity Log",             callback_data="admin_view_logs")],
        [InlineKeyboardButton("🚫 ইউজার ব্যান/আনব্যান",     callback_data="admin_ban_menu")],
        [InlineKeyboardButton("🔙 প্রধান মেনু",             callback_data="btn_main_menu")],
    ]
    msg = update.message or (update.callback_query and update.callback_query.message)
    await msg.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Gallery  (pagination + likes)
# ══════════════════════════════════════════════════════════════════════════════

async def send_gallery(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    try:
        uid     = update.effective_user.id
        chat_id = update.effective_chat.id
        msg     = update.message or update.callback_query.message

        skip   = page * GALLERY_PAGE
        photos = list(gallery_col.find().sort("created_at", -1).skip(skip).limit(GALLERY_PAGE))
        total  = gallery_col.count_documents({})

        if not photos:
            await msg.reply_text("🖼️ গ্যালারিতে বর্তমানে কোনো ছবি নেই।")
            return

        for photo in photos:
            db_id      = str(photo["_id"])
            likes      = photo.get("likes", [])
            liked      = uid in likes
            heart_lbl  = f"{'❤️' if liked else '🤍'} {len(likes)}"
            caption    = (
                f"📝 *ডেসক্রিপশন:* {photo.get('description', 'N/A')}\n"
                f"👤 *আপলোড করেছেন:* {photo.get('uploaded_by_name', 'Unknown')}"
            )
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo["file_id"],
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(heart_lbl, callback_data=f"like_{db_id}")
                ]]),
                parse_mode="Markdown",
            )

        nav = _nav_buttons("btn_gallery", page, total)
        total_pages = max(1, ((total - 1) // GALLERY_PAGE) + 1)
        await msg.reply_text(
            f"🌸 *গ্যালারি* — পাতা {page + 1}/{total_pages} (মোট {total} ছবি)",
            reply_markup=InlineKeyboardMarkup([nav]) if nav else None,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"send_gallery: {e}")
        msg = update.message or update.callback_query.message
        await msg.reply_text("⚠️ গ্যালারি লোড করতে সমস্যা হয়েছে।")


async def send_my_photos(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    try:
        uid     = update.effective_user.id
        chat_id = update.effective_chat.id
        msg     = update.message or update.callback_query.message

        skip   = page * GALLERY_PAGE
        photos = list(
            gallery_col.find({"uploaded_by": uid})
            .sort("created_at", -1)
            .skip(skip)
            .limit(GALLERY_PAGE)
        )
        total = gallery_col.count_documents({"uploaded_by": uid})

        if not photos:
            await msg.reply_text("📸 আপনি এখনো কোনো ছবি আপলোড করেননি।")
            return

        for photo in photos:
            db_id   = str(photo["_id"])
            caption = f"📝 *ডেসক্রিপশন:* {photo.get('description', 'N/A')}"
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo["file_id"],
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Delete", callback_data=f"mydelete_{db_id}"),
                    InlineKeyboardButton("✏️ Edit",   callback_data=f"myedit_{db_id}"),
                ]]),
                parse_mode="Markdown",
            )

        nav = _nav_buttons("btn_myphotos", page, total)
        total_pages = max(1, ((total - 1) // GALLERY_PAGE) + 1)
        await msg.reply_text(
            f"📸 *আমার ছবি* — পাতা {page + 1}/{total_pages} (মোট {total} ছবি)",
            reply_markup=InlineKeyboardMarkup([nav]) if nav else None,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"send_my_photos: {e}")
        msg = update.message or update.callback_query.message
        await msg.reply_text("⚠️ ছবি লোড করতে সমস্যা হয়েছে।")


async def search_gallery(update: Update, context: ContextTypes.DEFAULT_TYPE, keyword: str):
    try:
        uid     = update.effective_user.id
        chat_id = update.effective_chat.id
        msg     = update.message or update.callback_query.message

        photos = list(
            gallery_col.find({"description": {"$regex": keyword, "$options": "i"}})
            .sort("created_at", -1)
            .limit(10)
        )

        if not photos:
            await msg.reply_text(f'🔍 "{keyword}" দিয়ে কোনো ছবি পাওয়া যায়নি।')
            return

        await msg.reply_text(
            f'🔍 *"{keyword}"* — {len(photos)} টি ছবি পাওয়া গেছে:',
            parse_mode="Markdown",
        )
        for photo in photos:
            db_id     = str(photo["_id"])
            likes     = photo.get("likes", [])
            liked     = uid in likes
            heart_lbl = f"{'❤️' if liked else '🤍'} {len(likes)}"
            caption   = (
                f"📝 *ডেসক্রিপশন:* {photo.get('description', 'N/A')}\n"
                f"👤 *আপলোড করেছেন:* {photo.get('uploaded_by_name', 'Unknown')}"
            )
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo["file_id"],
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(heart_lbl, callback_data=f"like_{db_id}")
                ]]),
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"search_gallery: {e}")
        msg = update.message or (update.callback_query and update.callback_query.message)
        await msg.reply_text("⚠️ সার্চ করতে সমস্যা হয়েছে।")


def _nav_buttons(prefix: str, page: int, total: int) -> list:
    """Pagination prev/next button list তৈরি।"""
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ আগের পাতা", callback_data=f"{prefix}_{page - 1}"))
    if (page + 1) * GALLERY_PAGE < total:
        nav.append(InlineKeyboardButton("পরের পাতা ➡️", callback_data=f"{prefix}_{page + 1}"))
    return nav


# ══════════════════════════════════════════════════════════════════════════════
# Notes
# ══════════════════════════════════════════════════════════════════════════════

CATEGORY_LABELS = {
    "love_letter": "💌 প্রেমপত্র",
    "note":        "📝 নোট",
    "memory":      "🌸 স্মৃতি",
}


async def send_notes(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    try:
        msg   = update.message or update.callback_query.message
        skip  = page * GALLERY_PAGE
        notes = list(
            notes_col.find()
            .sort([("is_pinned", -1), ("created_at", -1)])
            .skip(skip)
            .limit(GALLERY_PAGE)
        )
        total = notes_col.count_documents({})

        if not total:
            await msg.reply_text("💌 এখনো কোনো নোট লেখা হয়নি।")
            return

        for note in notes:
            category = CATEGORY_LABELS.get(note.get("category", "note"), "📝 নোট")
            pinned   = "📌 " if note.get("is_pinned") else ""
            created  = note.get("created_at", datetime.now()).strftime("%d %b %Y")
            text = (
                f"{pinned}{category}\n\n"
                f"✍️ *{note.get('title', 'শিরোনাম নেই')}*\n\n"
                f"{note.get('content', '')}\n\n"
                f"🗓️ _{created}_"
            )
            await msg.reply_text(text, parse_mode="Markdown")

        nav = _nav_buttons("btn_notes", page, total)
        total_pages = max(1, ((total - 1) // GALLERY_PAGE) + 1)
        await msg.reply_text(
            f"💌 *প্রেমের নোট* — পাতা {page + 1}/{total_pages} (মোট {total} টি)",
            reply_markup=InlineKeyboardMarkup([nav]) if nav else None,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"send_notes: {e}")
        msg = update.message or update.callback_query.message
        await msg.reply_text("⚠️ নোট লোড করতে সমস্যা হয়েছে।")


async def admin_manage_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg   = update.callback_query.message
        notes = list(notes_col.find().sort([("is_pinned", -1), ("created_at", -1)]))

        if not notes:
            await msg.reply_text("💌 এখনো কোনো নোট নেই।")
        else:
            await msg.reply_text("💌 *সকল নোট (এডমিন ভিউ):*", parse_mode="Markdown")
            for note in notes:
                nid      = str(note["_id"])
                pinned   = "📌 " if note.get("is_pinned") else ""
                category = CATEGORY_LABELS.get(note.get("category", "note"), "📝")
                title    = note.get("title", "শিরোনাম নেই")
                await msg.reply_text(
                    f"{pinned}{category} — *{title}*",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "📌 আনপিন" if note.get("is_pinned") else "📌 পিন",
                            callback_data=f"note_pin_{nid}",
                        ),
                        InlineKeyboardButton("✏️ Edit",   callback_data=f"note_edit_{nid}"),
                        InlineKeyboardButton("❌ Delete", callback_data=f"note_del_{nid}"),
                    ]]),
                    parse_mode="Markdown",
                )

        await msg.reply_text(
            "➕ নতুন নোট লিখতে:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💌 নতুন নোট লিখুন", callback_data="note_new")
            ]]),
        )
    except Exception as e:
        logger.error(f"admin_manage_notes: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Special Dates
# ══════════════════════════════════════════════════════════════════════════════

async def send_special_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg       = update.message or update.callback_query.message
        today     = date.today()
        all_dates = list(dates_col.find().sort("date", 1))

        if not all_dates:
            await msg.reply_text("📅 এখনো কোনো বিশেষ দিন যোগ করা হয়নি।")
            return

        text = "📅 *বিশেষ দিনসমূহ:*\n\n"
        for d in all_dates:
            raw = d.get("date", "")
            try:
                event_date = datetime.strptime(raw, "%Y-%m-%d").date()
                if d.get("repeat_yearly"):
                    ev = event_date.replace(year=today.year)
                    if ev < today:
                        ev = event_date.replace(year=today.year + 1)
                else:
                    ev = event_date
                days_left = (ev - today).days
                if days_left > 0:
                    countdown = f"⏳ {days_left} দিন বাকি"
                elif days_left == 0:
                    countdown = "🎉 আজকেই!"
                else:
                    countdown = "✅ শেষ হয়েছে"
                repeat = "🔁 প্রতি বছর" if d.get("repeat_yearly") else "1️⃣ একবার"
                text += f"🗓️ *{d.get('title')}*\n📆 {raw} | {repeat} | {countdown}\n\n"
            except Exception:
                text += f"🗓️ *{d.get('title')}* — {raw}\n\n"

        await msg.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"send_special_dates: {e}")
        msg = update.message or update.callback_query.message
        await msg.reply_text("⚠️ বিশেষ দিন লোড করতে সমস্যা হয়েছে।")


async def admin_manage_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg       = update.callback_query.message
        all_dates = list(dates_col.find().sort("date", 1))

        if all_dates:
            await msg.reply_text("📅 *বর্তমান বিশেষ দিনসমূহ:*", parse_mode="Markdown")
            for d in all_dates:
                did = str(d["_id"])
                await msg.reply_text(
                    f"🗓️ *{d.get('title')}* — {d.get('date')}\n"
                    f"💌 {d.get('message', 'বার্তা নেই')}\n"
                    f"🔁 {'প্রতি বছর' if d.get('repeat_yearly') else 'একবার'} | "
                    f"⏰ {d.get('reminder_days_before', 1)} দিন আগে reminder",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Delete", callback_data=f"date_del_{did}")
                    ]]),
                    parse_mode="Markdown",
                )

        await msg.reply_text(
            "➕ নতুন বিশেষ দিন যোগ করুন:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📅 নতুন দিন যোগ করুন", callback_data="date_new")
            ]]),
        )
    except Exception as e:
        logger.error(f"admin_manage_dates: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Scheduler — Special Date Reminder (প্রতিদিন সকাল ৯টায়)
# ══════════════════════════════════════════════════════════════════════════════

async def check_special_dates(app):
    try:
        today     = date.today()
        all_dates = list(dates_col.find())

        for d in all_dates:
            raw = d.get("date", "")
            try:
                event_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except Exception:
                continue

            if d.get("repeat_yearly"):
                ev = event_date.replace(year=today.year)
                if ev < today:
                    ev = event_date.replace(year=today.year + 1)
            else:
                ev = event_date

            days_left     = (ev - today).days
            remind_before = d.get("reminder_days_before", 1)

            if days_left not in (0, remind_before):
                continue

            label = "🎉 আজকেই!" if days_left == 0 else f"⏳ {days_left} দিন পরে!"
            reminder_text = (
                f"📅 *বিশেষ দিনের Reminder!*\n\n"
                f"🗓️ *{d.get('title')}*\n"
                f"📆 তারিখ: {raw} — {label}\n\n"
                f"💌 {d.get('message', '')}"
            )
            # সব authenticated ইউজারকে পাঠাও
            active_users = users_col.find({
                "is_authenticated": True,
                "is_banned": {"$ne": True},
            })
            for u in active_users:
                try:
                    await app.bot.send_message(
                        chat_id=u["user_id"],
                        text=reminder_text,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"check_special_dates scheduler: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Command Handlers
# ══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        track_user(user)
        if is_banned(user.id):
            await update.message.reply_text("🚫 আপনাকে এই বোট থেকে নিষিদ্ধ করা হয়েছে।")
            return
        if not is_authenticated(user.id):
            await update.message.reply_text(
                f"স্বাগতম *{user.first_name}*! 🔒\n\n"
                "এই বোটটি ব্যবহার করতে পাসওয়ার্ডটি টাইপ করে পাঠান:",
                parse_mode="Markdown",
            )
            return
        log_action(user.id, user.username or "N/A", "login")
        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"start: {e}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        track_user(update.effective_user)
        text = (
            "🤖 *বোট ব্যবহারের নির্দেশিকা*\n\n"
            "📌 *কমান্ডসমূহ:*\n"
            "/start — বোট শুরু করুন\n"
            "/help — সাহায্য দেখুন\n"
            "/myPhotos — আপনার আপলোড করা ছবি\n"
            "/notes — প্রেমের নোট দেখুন\n"
            "/dates — বিশেষ দিনসমূহ\n"
            "/search [কীওয়ার্ড] — গ্যালারি সার্চ\n"
            "/adminPanel — এডমিন প্যানেল\n\n"
            "📌 *ফিচারসমূহ:*\n"
            "• ছবি পাঠালে গ্যালারিতে সেভ হয়\n"
            "• ছবিতে ❤️ Heart দেওয়া যায়\n"
            "• নিজের ছবি Delete ও Edit করা যায়\n"
            "• এডমিনের প্রেমের নোট/চিঠি পড়া যায়\n"
            "• বার্ষিকী/জন্মদিনের reminder পাঠানো হয়"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"help_cmd: {e}")


async def my_photos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        track_user(update.effective_user)
        if not await _guard(update):
            return
        await send_my_photos(update, context, page=0)
    except Exception as e:
        logger.error(f"my_photos_cmd: {e}")


async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        track_user(update.effective_user)
        if not await _guard(update):
            return
        await send_notes(update, context, page=0)
    except Exception as e:
        logger.error(f"notes_cmd: {e}")


async def dates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        track_user(update.effective_user)
        if not await _guard(update):
            return
        await send_special_dates(update, context)
    except Exception as e:
        logger.error(f"dates_cmd: {e}")


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        track_user(update.effective_user)
        if not await _guard(update):
            return
        keyword = " ".join(context.args).strip() if context.args else ""
        if not keyword:
            await update.message.reply_text(
                "🔍 ব্যবহার: /search [কীওয়ার্ড]\nযেমন: /search প্রথম দেখা"
            )
            return
        await search_gallery(update, context, keyword)
    except Exception as e:
        logger.error(f"search_cmd: {e}")


async def admin_panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        track_user(user)
        if is_banned(user.id):
            msg = update.message or update.callback_query.message
            await msg.reply_text("🚫 আপনাকে এই বোট থেকে নিষিদ্ধ করা হয়েছে।")
            return
        if not is_admin(user.id):
            msg = update.message or update.callback_query.message
            await msg.reply_text("🔐 এডমিন পাসওয়ার্ডটি প্রবেশ করান:")
            context.user_data["awaiting_admin_pass"] = True
            return
        await show_admin_dashboard(update, context)
    except Exception as e:
        logger.error(f"admin_panel_cmd: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Photo Upload
# ══════════════════════════════════════════════════════════════════════════════

async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        track_user(user)
        if not await _guard(update):
            return

        photo_file_id = update.message.photo[-1].file_id
        description   = update.message.caption or "কোনো ডেসক্রিপশন দেওয়া হয়নি।"

        # Telegram থেকে file info নেওয়া
        file_info    = await context.bot.get_file(photo_file_id)
        telegram_url = file_info.file_path   # Telegram CDN URL

        # ── Cloudinary তে upload ──────────────────────────────────────────
        cloudinary_url = None
        try:
            # Telegram URL থেকে সরাসরি Cloudinary তে upload
            upload_result  = cloudinary.uploader.upload(
                telegram_url,
                folder        = "love-telebot",
                resource_type = "image",
            )
            cloudinary_url = upload_result.get("secure_url")
            logger.info(f"Cloudinary upload success: {cloudinary_url}")
        except Exception as cld_err:
            # Cloudinary fail হলেও বোট চলবে — শুধু log করব
            logger.warning(f"Cloudinary upload failed: {cld_err}")

        result = gallery_col.insert_one({
            "file_id":          photo_file_id,
            "telegram_url":     telegram_url,        # Telegram CDN URL
            "cloudinary_url":   cloudinary_url,      # Cloudinary permanent URL (None হলে upload হয়নি)
            "description":      description,
            "uploaded_by":      user.id,
            "uploaded_by_name": user.first_name,
            "created_at":       datetime.now(),
            "likes":            [],
        })
        log_action(user.id, user.username or "N/A", "photo_uploaded", str(result.inserted_id))

        # Success message — Cloudinary status সহ
        cloud_status = "☁️ Cloudinary: ✅ সেভ হয়েছে" if cloudinary_url else "☁️ Cloudinary: ⚠️ সেভ হয়নি (Telegram URL ব্যবহার হবে)"
        await update.message.reply_text(
            f"🎉 *ছবি সফলভাবে গ্যালারিতে যোগ হয়েছে!*\n\n"
            f"📝 *ডেসক্রিপশন:* {description}\n"
            f"{cloud_status}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"handle_photo_upload: {e}")
        await update.message.reply_text("⚠️ ছবি সেভ করতে সমস্যা হয়েছে।")


# ══════════════════════════════════════════════════════════════════════════════
# Text Message Handler  (state-machine)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user    = update.effective_user
        uid     = user.id
        text_in = update.message.text.strip()
        track_user(user)

        if is_banned(uid):
            await update.message.reply_text("🚫 আপনাকে এই বোট থেকে নিষিদ্ধ করা হয়েছে।")
            return

        state = USER_STATE.get(uid, {})
        step  = state.get("step")

        # ──── State machine ────────────────────────────────────────────────

        # ১. ছবির description edit
        if step == "edit_photo_desc":
            owner_id = state["owner_id"]
            if is_admin(uid) or uid == owner_id:
                gallery_col.update_one(
                    {"_id": ObjectId(state["photo_id"])},
                    {"$set": {"description": text_in}},
                )
                log_action(uid, user.username or "N/A", "photo_desc_edited", state["photo_id"])
                await update.message.reply_text("✅ ডেসক্রিপশন সফলভাবে পরিবর্তন করা হয়েছে!")
            else:
                await update.message.reply_text("❌ এই ছবির ডেসক্রিপশন পরিবর্তনের অনুমতি নেই।")
            clear_state(uid)
            return

        # ২. নোট — শিরোনাম
        if step == "note_title":
            USER_STATE[uid]["title"] = text_in
            USER_STATE[uid]["step"]  = "note_content"
            await update.message.reply_text("📝 এবার নোটের মূল বার্তাটি লিখুন:")
            return

        # ৩. নোট — বার্তা
        if step == "note_content":
            USER_STATE[uid]["content"] = text_in
            USER_STATE[uid]["step"]    = "note_category"
            await update.message.reply_text(
                "📂 নোটের ধরন বেছে নিন:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💌 প্রেমপত্র", callback_data="note_cat_love_letter")],
                    [InlineKeyboardButton("📝 নোট",        callback_data="note_cat_note")],
                    [InlineKeyboardButton("🌸 স্মৃতি",     callback_data="note_cat_memory")],
                ]),
            )
            return

        # ৪. নোট edit — নতুন content
        if step == "note_edit_content":
            notes_col.update_one(
                {"_id": ObjectId(state["note_id"])},
                {"$set": {"content": text_in, "updated_at": datetime.now()}},
            )
            log_action(uid, user.username or "N/A", "note_edited", state["note_id"])
            await update.message.reply_text("✅ নোট সফলভাবে আপডেট হয়েছে!")
            clear_state(uid)
            return

        # ৫. বিশেষ দিন — শিরোনাম
        if step == "date_title":
            USER_STATE[uid]["title"] = text_in
            USER_STATE[uid]["step"]  = "date_date"
            await update.message.reply_text(
                "📆 তারিখটি লিখুন (YYYY-MM-DD ফরমেটে):\nযেমন: 2026-10-05"
            )
            return

        # ৬. বিশেষ দিন — তারিখ
        if step == "date_date":
            try:
                datetime.strptime(text_in, "%Y-%m-%d")
                USER_STATE[uid]["date"] = text_in
                USER_STATE[uid]["step"] = "date_message"
                await update.message.reply_text("💌 এই দিনের জন্য একটি বিশেষ বার্তা লিখুন:")
            except ValueError:
                await update.message.reply_text(
                    "❌ তারিখের ফরমেট ভুল!\nYYYY-MM-DD ফরমেটে লিখুন। যেমন: 2026-10-05"
                )
            return

        # ৭. বিশেষ দিন — বার্তা
        if step == "date_message":
            USER_STATE[uid]["message"] = text_in
            USER_STATE[uid]["step"]    = "date_repeat"
            await update.message.reply_text(
                "🔁 এই দিনটি কি প্রতি বছর মনে করিয়ে দেবে?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 হ্যাঁ, প্রতি বছর", callback_data="date_repeat_yes")],
                    [InlineKeyboardButton("1️⃣ না, শুধু একবার",   callback_data="date_repeat_no")],
                ]),
            )
            return

        # ৮. বিশেষ দিন — reminder দিন সংখ্যা (শেষ ধাপ)
        if step == "date_reminder_days":
            try:
                days = int(text_in)
                if days < 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: 3")
                return
            result = dates_col.insert_one({
                "title":                state.get("title", "বিশেষ দিন"),
                "date":                 state.get("date"),
                "message":              state.get("message", ""),
                "repeat_yearly":        state.get("repeat_yearly", False),
                "reminder_days_before": days,
                "created_by":           uid,
                "created_at":           datetime.now(),
                "last_reminded":        None,
            })
            log_action(uid, user.username or "N/A", "date_created", str(result.inserted_id))
            clear_state(uid)
            await update.message.reply_text(
                f"✅ *বিশেষ দিন সেভ হয়েছে!*\n\n"
                f"🗓️ *{state.get('title')}* — {state.get('date')}\n"
                f"⏰ {days} দিন আগে reminder আসবে।",
                parse_mode="Markdown",
            )
            return

        # ৯. গ্যালারি সার্চ (inline prompt থেকে)
        if step == "search_keyword":
            clear_state(uid)
            await search_gallery(update, context, text_in)
            return

        # ──── Normal password flow ─────────────────────────────────────────

        if context.user_data.get("awaiting_admin_pass"):
            if text_in == ADMIN_PASSWORD:
                set_admin(uid, True)
                context.user_data["awaiting_admin_pass"] = False
                log_action(uid, user.username or "N/A", "admin_login")
                await update.message.reply_text("🎉 এডমিন পাসওয়ার্ড সঠিক! স্বাগতম।")
                await show_admin_dashboard(update, context)
            else:
                await update.message.reply_text("❌ ভুল পাসওয়ার্ড! আবার চেষ্টা করুন:")
            return

        if not is_authenticated(uid):
            if text_in == USER_PASSWORD:
                set_authenticated(uid, True)
                log_action(uid, user.username or "N/A", "login")
                await update.message.reply_text("🎉 পাসওয়ার্ড সঠিক! স্বাগতম।")
                await show_main_menu(update, context)
            else:
                await update.message.reply_text("❌ ভুল পাসওয়ার্ড! সঠিক পাসওয়ার্ড দিন:")
            return

        # ──── Keyword shortcuts ────────────────────────────────────────────
        clean = text_in.lower()
        if any(g in clean for g in ["assalamu alaikum", "আসসালামু আলাইকুম", "সালাম"]):
            await update.message.reply_text("ওয়ালাইকুমুস সালাম ওয়া রহমাতুল্লাহ! 🌸")
        elif "গ্যালারি" in clean or "gallery" in clean:
            await send_gallery(update, context, page=0)
        elif "নোট" in clean or "চিঠি" in clean:
            await send_notes(update, context, page=0)
        else:
            await update.message.reply_text("বুঝতে পারিনি! /help প্রেস করুন।")

    except Exception as e:
        logger.error(f"handle_text_message: {e}")
        await update.message.reply_text("⚠️ একটি সমস্যা হয়েছে।")


# ══════════════════════════════════════════════════════════════════════════════
# Callback Handler
# ══════════════════════════════════════════════════════════════════════════════

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query   = update.callback_query
        uid     = query.from_user.id
        uname   = query.from_user.username or "N/A"
        data    = query.data
        await query.answer()

        if is_banned(uid):
            await query.message.reply_text("🚫 আপনাকে এই বোট থেকে নিষিদ্ধ করা হয়েছে।")
            return

        # ── Navigation ────────────────────────────────────────────────────
        if data == "btn_main_menu":
            await show_main_menu(update, context)
            return

        if data == "btn_admin_prompt":
            await admin_panel_cmd(update, context)
            return

        if data == "btn_dates":
            if not await _guard(update):
                return
            await send_special_dates(update, context)
            return

        if data == "btn_search_prompt":
            if not await _guard(update):
                return
            USER_STATE[uid] = {"step": "search_keyword"}
            await query.message.reply_text("🔍 সার্চ করতে চান এমন কীওয়ার্ড লিখুন:")
            return

        if data.startswith("btn_gallery_"):
            if not await _guard(update):
                return
            await send_gallery(update, context, page=int(data.split("_")[-1]))
            return

        if data.startswith("btn_myphotos_"):
            if not await _guard(update):
                return
            await send_my_photos(update, context, page=int(data.split("_")[-1]))
            return

        if data.startswith("btn_notes_"):
            if not await _guard(update):
                return
            await send_notes(update, context, page=int(data.split("_")[-1]))
            return

        # ── Like / Heart ──────────────────────────────────────────────────
        if data.startswith("like_"):
            if not await _guard(update):
                return
            photo_id = data[5:]
            photo    = gallery_col.find_one({"_id": ObjectId(photo_id)})
            if not photo:
                await query.message.reply_text("⚠️ ছবিটি পাওয়া যায়নি।")
                return
            likes = photo.get("likes", [])
            if uid in likes:
                gallery_col.update_one({"_id": ObjectId(photo_id)}, {"$pull": {"likes": uid}})
                await query.answer("💔 Like সরানো হয়েছে।", show_alert=False)
            else:
                gallery_col.update_one({"_id": ObjectId(photo_id)}, {"$addToSet": {"likes": uid}})
                log_action(uid, uname, "photo_liked", photo_id)
                await query.answer("❤️ Like দেওয়া হয়েছে!", show_alert=False)

            updated   = gallery_col.find_one({"_id": ObjectId(photo_id)})
            new_likes = updated.get("likes", [])
            heart_lbl = f"{'❤️' if uid in new_likes else '🤍'} {len(new_likes)}"
            try:
                await query.message.edit_reply_markup(
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(heart_lbl, callback_data=f"like_{photo_id}")
                    ]])
                )
            except Exception:
                pass
            return

        # ── User own photo: Delete ────────────────────────────────────────
        if data.startswith("mydelete_"):
            photo_id = data[9:]
            photo    = gallery_col.find_one({"_id": ObjectId(photo_id)})
            if not photo:
                await query.message.reply_text("⚠️ ছবিটি পাওয়া যায়নি।")
                return
            if photo.get("uploaded_by") != uid:
                await query.message.reply_text("❌ এটি আপনার ছবি নয়।")
                return
            gallery_col.delete_one({"_id": ObjectId(photo_id)})
            log_action(uid, uname, "photo_deleted", photo_id)
            await query.message.edit_caption(
                caption="🗑️ *আপনার ছবিটি মুছে ফেলা হয়েছে!*",
                parse_mode="Markdown",
            )
            return

        # ── User own photo: Edit ──────────────────────────────────────────
        if data.startswith("myedit_"):
            photo_id = data[7:]
            photo    = gallery_col.find_one({"_id": ObjectId(photo_id)})
            if not photo:
                await query.message.reply_text("⚠️ ছবিটি পাওয়া যায়নি।")
                return
            if photo.get("uploaded_by") != uid:
                await query.message.reply_text("❌ এটি আপনার ছবি নয়।")
                return
            USER_STATE[uid] = {"step": "edit_photo_desc", "photo_id": photo_id, "owner_id": uid}
            await query.message.reply_text("✏️ নতুন ডেসক্রিপশনটি লিখে পাঠান:")
            return

        # ── Admin only below this line ────────────────────────────────────
        if not is_admin(uid):
            await query.message.reply_text("⛔ এই কাজটি করার অনুমতি আপনার নেই।")
            return

        # ── Admin: user list ──────────────────────────────────────────────
        if data == "admin_view_users":
            users = list(users_col.find())
            if not users:
                await query.message.reply_text("কোনো ইউজার পাওয়া যায়নি।")
                return
            text = "👥 *ইউজার তালিকা:*\n\n"
            for u in users:
                status = "🚫 Ban" if u.get("is_banned") else ("👑 Admin" if u.get("is_admin") else "✅ User")
                text += (
                    f"• *{u.get('first_name')}* (@{u.get('username')}) "
                    f"— ID: `{u.get('user_id')}` [{status}]\n"
                )
            for chunk in chunk_text(text):
                await query.message.reply_text(chunk, parse_mode="Markdown")
            return

        # ── Admin: manage photos ──────────────────────────────────────────
        if data == "admin_manage_photos":
            photos = list(gallery_col.find().sort("created_at", -1))
            if not photos:
                await query.message.reply_text("কোনো ছবি পাওয়া যায়নি।")
                return
            await query.message.reply_text("🖼️ সকল ছবি (এডমিন ভিউ):")
            for photo in photos:
                db_id   = str(photo["_id"])
                caption = (
                    f"📝 {photo.get('description', 'N/A')}\n"
                    f"👤 {photo.get('uploaded_by_name', 'Unknown')} | "
                    f"❤️ {len(photo.get('likes', []))}"
                )
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo["file_id"],
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Delete", callback_data=f"del_{db_id}"),
                        InlineKeyboardButton("✏️ Edit",   callback_data=f"edit_{db_id}"),
                    ]]),
                )
            return

        # ── Admin: manage notes ───────────────────────────────────────────
        if data == "admin_manage_notes":
            await admin_manage_notes(update, context)
            return

        # ── Admin: manage dates ───────────────────────────────────────────
        if data == "admin_manage_dates":
            await admin_manage_dates(update, context)
            return

        # ── Admin: activity log ───────────────────────────────────────────
        if data == "admin_view_logs":
            logs = list(logs_col.find().sort("timestamp", -1).limit(30))
            if not logs:
                await query.message.reply_text("📋 কোনো লগ নেই।")
                return
            text = "📋 *সর্বশেষ ৩০টি Activity:*\n\n"
            for log in logs:
                ts = log.get("timestamp", datetime.now()).strftime("%d/%m %H:%M")
                text += f"• `{ts}` @{log.get('username')} — *{log.get('action')}* {log.get('details', '')}\n"
            for chunk in chunk_text(text):
                await query.message.reply_text(chunk, parse_mode="Markdown")
            return

        # ── Admin: ban menu ───────────────────────────────────────────────
        if data == "admin_ban_menu":
            regular_users = list(users_col.find({"is_admin": {"$ne": True}}))
            if not regular_users:
                await query.message.reply_text("কোনো সাধারণ ইউজার নেই।")
                return
            await query.message.reply_text("🚫 *ব্যান / আনব্যান মেনু:*", parse_mode="Markdown")
            for u in regular_users:
                target_id = u.get("user_id")
                fname     = u.get("first_name", "Unknown")
                uname_u   = u.get("username", "N/A")
                banned    = u.get("is_banned", False)
                btn_lbl   = f"{'✅ আনব্যান' if banned else '🚫 ব্যান'} — {fname}"
                btn_data  = f"unban_{target_id}" if banned else f"ban_{target_id}"
                status    = "🚫 নিষিদ্ধ" if banned else "✅ সক্রিয়"
                await query.message.reply_text(
                    f"{status}: *{fname}* (@{uname_u}) — ID: `{target_id}`",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(btn_lbl, callback_data=btn_data)
                    ]]),
                    parse_mode="Markdown",
                )
            return

        if data.startswith("ban_"):
            target_id = int(data[4:])
            set_banned(target_id, True)
            log_action(uid, uname, "user_banned", str(target_id))
            await query.message.reply_text(
                f"🚫 ইউজার `{target_id}` কে ব্যান করা হয়েছে।",
                parse_mode="Markdown",
            )
            return

        if data.startswith("unban_"):
            target_id = int(data[6:])
            set_banned(target_id, False)
            log_action(uid, uname, "user_unbanned", str(target_id))
            await query.message.reply_text(
                f"✅ ইউজার `{target_id}` এর ব্যান তুলে নেওয়া হয়েছে।",
                parse_mode="Markdown",
            )
            return

        # ── Admin: photo delete ───────────────────────────────────────────
        if data.startswith("del_"):
            photo_id = data[4:]
            gallery_col.delete_one({"_id": ObjectId(photo_id)})
            log_action(uid, uname, "admin_photo_deleted", photo_id)
            await query.message.edit_caption(
                caption="🗑️ *এই ছবিটি ডিলিট করা হয়েছে!*",
                parse_mode="Markdown",
            )
            return

        # ── Admin: photo edit desc ────────────────────────────────────────
        if data.startswith("edit_"):
            photo_id = data[5:]
            photo    = gallery_col.find_one({"_id": ObjectId(photo_id)})
            if not photo:
                await query.message.reply_text("⚠️ ছবিটি পাওয়া যায়নি।")
                return
            USER_STATE[uid] = {
                "step":     "edit_photo_desc",
                "photo_id": photo_id,
                "owner_id": photo.get("uploaded_by"),
            }
            await query.message.reply_text("✏️ নতুন ডেসক্রিপশনটি লিখে পাঠান:")
            return

        # ── Notes callbacks ───────────────────────────────────────────────
        if data == "note_new":
            USER_STATE[uid] = {"step": "note_title"}
            await query.message.reply_text("✍️ নোটের শিরোনামটি লিখুন:")
            return

        if data.startswith("note_cat_"):
            category = data[9:]   # love_letter / note / memory
            st = USER_STATE.get(uid, {})
            if st.get("step") != "note_category":
                return
            result = notes_col.insert_one({
                "title":      st.get("title", "শিরোনাম নেই"),
                "content":    st.get("content", ""),
                "category":   category,
                "created_by": uid,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "is_pinned":  False,
            })
            log_action(uid, uname, "note_created", str(result.inserted_id))
            clear_state(uid)
            await query.message.reply_text(
                f"✅ নোট সফলভাবে সেভ হয়েছে!\n"
                f"📂 ধরন: {CATEGORY_LABELS.get(category, category)}"
            )
            return

        if data.startswith("note_pin_"):
            note_id = data[9:]
            note    = notes_col.find_one({"_id": ObjectId(note_id)})
            if not note:
                await query.message.reply_text("⚠️ নোটটি পাওয়া যায়নি।")
                return
            new_pin = not note.get("is_pinned", False)
            notes_col.update_one({"_id": ObjectId(note_id)}, {"$set": {"is_pinned": new_pin}})
            status = "📌 পিন করা হয়েছে" if new_pin else "📌 আনপিন করা হয়েছে"
            await query.message.reply_text(f"✅ নোটটি {status}!")
            return

        if data.startswith("note_edit_"):
            note_id = data[10:]
            USER_STATE[uid] = {"step": "note_edit_content", "note_id": note_id}
            await query.message.reply_text("✏️ নোটের নতুন বার্তাটি লিখুন:")
            return

        if data.startswith("note_del_"):
            note_id = data[9:]
            notes_col.delete_one({"_id": ObjectId(note_id)})
            log_action(uid, uname, "note_deleted", note_id)
            await query.message.reply_text("🗑️ নোটটি ডিলিট করা হয়েছে!")
            return

        # ── Special dates callbacks ───────────────────────────────────────
        if data == "date_new":
            USER_STATE[uid] = {"step": "date_title"}
            await query.message.reply_text("📅 বিশেষ দিনের শিরোনামটি লিখুন:\nযেমন: আমাদের বার্ষিকী 💑")
            return

        if data.startswith("date_repeat_"):
            repeat = data == "date_repeat_yes"
            st     = USER_STATE.get(uid, {})
            if st.get("step") != "date_repeat":
                return

            # reminder কত দিন আগে?
            USER_STATE[uid]["repeat_yearly"] = repeat
            USER_STATE[uid]["step"]          = "date_reminder_days"
            await query.message.reply_text(
                "⏰ কত দিন আগে reminder পাঠাবে?\n"
                "একটি সংখ্যা লিখুন (যেমন: 3):"
            )
            return

        if data.startswith("date_del_"):
            date_id = data[9:]
            dates_col.delete_one({"_id": ObjectId(date_id)})
            log_action(uid, uname, "date_deleted", date_id)
            await query.message.reply_text("🗑️ বিশেষ দিনটি ডিলিট করা হয়েছে!")
            return

    except Exception as e:
        logger.error(f"button_click: {e}")
        try:
            await update.callback_query.message.reply_text("⚠️ একটি সমস্যা হয়েছে।")
        except Exception:
            pass





# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN পাওয়া যায়নি! .env ফাইল চেক করুন।")

    app = ApplicationBuilder().token(TOKEN).build()

    # ── Scheduler setup ────────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Asia/Dhaka")
    scheduler.add_job(
        check_special_dates,
        trigger="cron",
        hour=9,
        minute=0,
        args=[app],
    )
    scheduler.start()

    # ── Handlers ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("help",       help_cmd))
    app.add_handler(CommandHandler("myPhotos",   my_photos_cmd))
    app.add_handler(CommandHandler("notes",      notes_cmd))
    app.add_handler(CommandHandler("dates",      dates_cmd))
    app.add_handler(CommandHandler("search",     search_cmd))
    app.add_handler(CommandHandler("adminPanel", admin_panel_cmd))

    app.add_handler(MessageHandler(filters.PHOTO,                   handle_photo_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(button_click))

    print("✅ বোট চালু হয়েছে!")
    print("   ফিচার: গ্যালারি, নোট, বিশেষ দিন, সার্চ, likes, ban/unban, activity log")
    app.run_polling()
