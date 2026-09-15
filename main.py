import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# Logging সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- কনফিগারেশন ও ডাটা সেটিং ---
PASSWORD = os.getenv("PASSWORD")  # 👈 এখানে আপনার ইচ্ছামতো সিক্রেট পাসওয়ার্ড দিন

# অথেন্টিকেটেড ইউজার আইডি জমা রাখার সেট (RAM Memory)
AUTHENTICATED_USERS = set()

# ছবির আইডি জমা রাখার মেমোরি লিস্ট
USER_SAVED_PHOTOS = []

DEFAULT_PHOTOS = [
    "https://images.unsplash.com/photo-1518199266791-5375a83190b7",
    "https://images.unsplash.com/photo-1516589178581-6cd7833ae3b2"
]

# ১. হেল্পার ফাংশন: ইউজার অথেন্টিকেটেড কিনা যাচাই করা
def is_authenticated(user_id: int) -> bool:
    return user_id in AUTHENTICATED_USERS

# ২. /start এবং পাসওয়ার্ড চেক
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    if not is_authenticated(user_id):
        await update.message.reply_text(
            f"স্বাগতম {user_name}! 🔒\n\n"
            "এই বোটটি পাসওয়ার্ড দিয়ে সুরক্ষিত। বোটটি ব্যবহার করতে অনুগ্রহ করে সঠিক পাসওয়ার্ডটি টাইপ করে পাঠান:"
        )
        return

    # অথেন্টিকেটেড হলে মেইন মেনু দেখাবে
    await show_main_menu(update, context)

# মেইন মেনু দেখানোর ফাংশন
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"হ্যালো {user_name}! ❤️\n\n"
        "আমি আপনার সিকিউর রোমান্টিক বোট। নিচের বাটনগুলো ব্যবহার করুন অথবা আমাকে যেকোনো ছবি পাঠান গ্যালারিতে যোগ করতে। 📸"
    )

    keyboard = [
        [InlineKeyboardButton("🖼️ ফটো গ্যালারি দেখুন", callback_data="btn_gallery")],
        [InlineKeyboardButton("💖 লাভ ক্যালকুলেটর", callback_data="btn_calc_info"), InlineKeyboardButton("📜 রোমান্টিক উক্তি", callback_data="btn_quote")],
        [InlineKeyboardButton("💡 সম্পর্কের টিপস", callback_data="btn_tips"), InlineKeyboardButton("😉 ফ্লার্ট লাইন", callback_data="btn_flirt")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup)

# ৩. টেক্সট ও পাসওয়ার্ড প্রসেসিং হ্যান্ডলার
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    clean_text = user_text.lower()

    # ক) পাসওয়ার্ড যাচাই করা
    if not is_authenticated(user_id):
        if user_text == PASSWORD:
            AUTHENTICATED_USERS.add(user_id)
            await update.message.reply_text("🎉 অভিনন্দন! পাসওয়ার্ড সঠিক হয়েছে। আপনার অ্যাক্সেস আনলক করা হলো।")
            await show_main_menu(update, context)
        else:
            await update.message.reply_text("❌ ভুল পাসওয়ার্ড! অনুগ্রহ করে সঠিক পাসওয়ার্ডটি আবার চেষ্টা করুন:")
        return

    # খ) অটো-রিপ্লাই ফিচার (সালাম ও কথোপকথন)
    if any(greeting in clean_text for greeting in ["assalamu alaikum", "assalamaualaikum", "আসসালামু আলাইকুম", "সালাম", "salam"]):
        await update.message.reply_text("ওয়ালাইকুমুস সালাম ওয়া রহমাতুল্লাহি ওয়া বারাকাতুহ! 🌸 আপনাকে সাহায্য করতে পেরে আনন্দিত।")
    
    elif any(ask in clean_text for ask in ["কেমন আছেন", "কেমন আছো", "kemon acho", "how are you"]):
        await update.message.reply_text("আলহামদুলিল্লাহ, আমি খুব ভালো আছি! ❤️ আপনি কেমন আছেন?")

    elif any(fine in clean_text for fine in ["ভালো", "valo", "fine", "alhamdulillah"]):
        await update.message.reply_text("শুনে খুব ভালো লাগলো! আলহামদুলিল্লাহ। 😇")

    elif "গ্যালারি" in clean_text or "gallery" in clean_text:
        await send_gallery(update, context)

    elif "ভালোবাসি" in clean_text or "love" in clean_text:
        await update.message.reply_text("ভালোবাসা এক সুন্দর অনুভূতি! প্রিয় মানুষটিকে সবসময় সম্মান ও যত্ন দিন। ❤️")

    else:
        await update.message.reply_text("আমি আপনার কথাটি বুঝতে পারিনি। মোটু মেনু দেখতে /start প্রেস করুন অথবা বাটন নির্বাচন করুন। 🤖")

# ৪. ছবি হ্যান্ডলার (পাসওয়ার্ড প্রটেক্টেড)
async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authenticated(user_id):
        await update.message.reply_text("🔒 ছবি সেভ করার জন্য আগে সঠিক পাসওয়ার্ড দিয়ে বোটটি আনলক করুন!")
        return

    photo_file_id = update.message.photo[-1].file_id
    USER_SAVED_PHOTOS.append(photo_file_id)
    
    await update.message.reply_text("🎉 ধন্যবাদ! আপনার ছবিটি সফলভাবে বোটের গ্যালারিতে যুক্ত হয়েছে। 📸")

# ৫. গ্যালারি সেন্ড করা
async def send_gallery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg = update.message or update.callback_query.message
    
    all_photos = USER_SAVED_PHOTOS if len(USER_SAVED_PHOTOS) > 0 else DEFAULT_PHOTOS

    await msg.reply_text(f"🌸 গ্যালারি লোড হচ্ছে... (মোট ছবি: {len(all_photos)} টি)")

    photos_to_send = all_photos[-10:]  # সর্বশেষ ১০টি ছবি
    media_group = [InputMediaPhoto(media=photo_id) for photo_id in photos_to_send]
    await context.bot.send_media_group(chat_id=chat_id, media=media_group)

# ৬. লাভ ক্যালকুলেটর
async def love_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await update.message.reply_text("🔒 আগে পাসওয়ার্ড দিন!")
        return

    if not context.args or "+" not in " ".join(context.args):
        await update.message.reply_text(
            "⚠️ ব্যবহারের নিয়ম:\n`/lovecalculator নাম১ + নাম২`\n\n"
            "উদাহরণ:\n`/lovecalculator শাকিব + বুশরা`",
            parse_mode="Markdown"
        )
        return

    full_text = " ".join(context.args)
    names = full_text.split("+")
    name1, name2 = names[0].strip(), names[1].strip()

    combined = (name1.lower() + name2.lower()).encode('utf-8')
    score = sum(combined) % 101

    comment = "স্বর্গীয় জুটি! 👩‍❤️‍👨💖" if score > 75 else "সুন্দর সম্পর্ক! ❤️"

    response = (
        f"💌 *লাভ ক্যালকুলেটর রেজাল্ট* 💌\n\n"
        f"👤 *প্রথম নাম:* {name1}\n"
        f"👤 *দ্বিতীয় নাম:* {name2}\n\n"
        f"🔥 *ভালোবাসার হার:* `{score}%`\n"
        f"📝 *মতামত:* {comment}"
    )
    await update.message.reply_text(response, parse_mode="Markdown")

# ৭. বাটন ক্লিক হ্যান্ডলার
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if not is_authenticated(user_id):
        await query.message.reply_text("🔒 অনুগ্রহ করে প্রথমে পাসওয়ার্ড লিখে পাঠান!")
        return

    if query.data == "btn_gallery":
        await send_gallery(update, context)
    elif query.data == "btn_quote":
        await query.message.reply_text("❤️ 'ভালোবাসা হলো দুটি দেহের মাঝে বাস করা একটিমাত্র আত্মা।'")
    elif query.data == "btn_tips":
        await query.message.reply_text("💡 টিপস: সম্পর্কে সততা এবং যোগাযোগের কোনো বিকল্প নেই।")
    elif query.data == "btn_flirt":
        await query.message.reply_text("😉 'তুমি কি কোনো জাদু জানো? তোমাকে দেখলেই চারপাশ উজ্জ্বল হয়ে ওঠে!'")
    elif query.data == "btn_calc_info":
        await query.message.reply_text(
            "💖 লাভ ক্যালকুলেটর ব্যবহার করতে টাইপ করুন:\n\n"
            "`/lovecalculator আপনারনাম + প্রিয়মানুষেরনাম`",
            parse_mode="Markdown"
        )

if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    
    if not TOKEN:
        raise ValueError("BOT_TOKEN পাওয়া যায়নি! Environment Variable চেক করুন।")

    app = ApplicationBuilder().token(TOKEN).build()

    # হ্যান্ডলারসমূহ
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lovecalculator", love_calculator))

    # পাসওয়ার্ড ও কনভারসেশন মেসেজ
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # ছবি হ্যান্ডলার
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))

    # ইনলাইন বাটন হ্যান্ডলার
    app.add_handler(CallbackQueryHandler(button_click))

    print("পাসওয়ার্ড সিকিউরড বোট প্রস্তুত...")
    app.run_polling()
