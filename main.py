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

# --- ডিফল্ট কিছু ব্যাকআপ ছবি (file_id খালি থাকলে এগুলো দেখাবে) ---
DEFAULT_PHOTOS = [
    "https://images.unsplash.com/photo-1518199266791-5375a83190b7",
    "https://images.unsplash.com/photo-1516589178581-6cd7833ae3b2"
]

# ইউজারদের পাঠানো ছবির File ID গচ্ছিত রাখার মেমোরি লিস্ট
USER_SAVED_PHOTOS = []

# ১. /start কমান্ড ও প্রধান বাটন মেনু
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"হ্যালো {user_name}! ❤️\n\n"
        "আমি আপনার রোমান্টিক ভালোবাসার বোট। 🤖\n\n"
        "📌 *গ্যালারি ফিচার:* আপনি চাইলে বোটে যেকোনো সুন্দর ছবি পাঠাতে পারেন! "
        "আপনার পাঠানো ছবিগুলো বোটের গ্যালারিতে সেভ হয়ে যাবে।"
    )

    keyboard = [
        [InlineKeyboardButton("🖼️ ফটো গ্যালারি দেখুন", callback_data="btn_gallery")],
        [InlineKeyboardButton("💖 লাভ ক্যালকুলেটর", callback_data="btn_calc_info"), InlineKeyboardButton("📜 রোমান্টিক উক্তি", callback_data="btn_quote")],
        [InlineKeyboardButton("💡 সম্পর্কের টিপস", callback_data="btn_tips"), InlineKeyboardButton("😉 ফ্লার্ট লাইন", callback_data="btn_flirt")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

# ২. ছবি সেভ করার হ্যান্ডলার (ইউজার ফটো পাঠালে এটি ট্রিগার হবে)
async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # টেলিগ্রাম ছবিতে একাধিক রেজোলিউশন পাঠায়, আমরা সবচেয়ে হাই-কোয়ালিটি (-1) ছবির File ID নেব
    photo_file_id = update.message.photo[-1].file_id
    
    # লিস্টে সেভ করে রাখা
    USER_SAVED_PHOTOS.append(photo_file_id)
    
    await update.message.reply_text(
        "🎉 *ধন্যবাদ!* আপনার ছবিটি সফলভাবে বোটের মেমোরি গ্যালারিতে সেভ করা হয়েছে। "
        "এখন গ্যালারিতে ক্লিক করলে আপনার ছবিটিও দেখা যাবে! 📸",
        parse_mode="Markdown"
    )

# ৩. গ্যালারি সেন্ড করা (ডিফল্ট ছবি + ইউজারদের পাঠানো ছবি)
async def send_gallery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # মেসেজ নিশ্চিতকরণ
    msg = update.message or update.callback_query.message
    
    # যদি কোনো ইউজার ছবি না পাঠিয়ে থাকে, তবে ডিফল্ট ছবি দেখাবে
    all_photos = USER_SAVED_PHOTOS if len(USER_SAVED_PHOTOS) > 0 else DEFAULT_PHOTOS

    await msg.reply_text(f"🌸 গ্যালারি লোড হচ্ছে... (মোট ছবি: {len(all_photos)} টি)")

    # টেলিগ্রামে একবারে সর্বোচ্চ ১০টি মিডিয়া ফাইল পাঠানো যায়
    photos_to_send = all_photos[-10:]  # সর্বশেষ ১০টি ছবি নেওয়া
    
    media_group = [InputMediaPhoto(media=photo_id) for photo_id in photos_to_send]
    await context.bot.send_media_group(chat_id=chat_id, media=media_group)

# ৪. লাভ ক্যালকুলেটর
async def love_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ৫. বাটন ক্লিক হ্যান্ডলার
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_gallery":
        await send_gallery(update, context)
    elif query.data == "btn_calc_info":
        await query.message.reply_text(
            "💖 লাভ ক্যালকুলেটর ব্যবহার করতে টাইপ করুন:\n\n"
            "`/lovecalculator আপনারনাম + প্রিয়মানুষেরনাম`",
            parse_mode="Markdown"
        )

# ৬. সাধারণ টেক্সট বার্তা হ্যান্ডলার
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.lower()
    
    if "গ্যালারি" in user_text or "gallery" in user_text:
        await send_gallery(update, context)
    elif "ভালোবাসি" in user_text or "love" in user_text:
        await update.message.reply_text("ভালোবাসা সুন্দর! সবসময় প্রিয় মানুষটিকে আগলে রাখুন। ❤️")
    else:
        await update.message.reply_text("আমি ঠিক বুঝতে পারছি না! ফটো পাঠাতে পারেন অথবা /start চাপুন। 🤖")

if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    
    if not TOKEN:
        raise ValueError("BOT_TOKEN পাওয়া যায়নি! Environment Variable চেক করুন।")

    app = ApplicationBuilder().token(TOKEN).build()

    # কমান্ড হ্যান্ডলারসমূহ
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gallery", send_gallery))
    app.add_handler(CommandHandler("lovecalculator", love_calculator))

    # ইউজার কোনো ছবি (Photo) পাঠালে তা সেভ করার হ্যান্ডলার
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))

    # বাটন ও সাধারণ টেক্সট হ্যান্ডলার
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("ছবি সেভ সুবিধা সহ বোট প্রস্তুত...")
    app.run_polling()
