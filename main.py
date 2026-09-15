import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ডেটাবেজ/লিস্ট (উক্তি, টিপস ও ফ্লার্ট লাইন)
LOVE_QUOTES = [
    "ভালোবাসা মানে কাউকে কাছে পাওয়ার ইচ্ছা নয়, বরং কারো শান্তিতে থাকার কারণ হওয়া। ❤️",
    "তুমি আমার সেই কবিতা, যা প্রতিদিন পড়তে ইচ্ছে করে। 📖💖",
    "পৃথিবীর সবচেয়ে সুন্দর অনুভূতি হলো কারো প্রিয় মানুষ হওয়া। 🌸",
    "প্রেম হলো একটি আত্মাকে দুটি দেহে বসবাস করার সুন্দর রূপ। ✨"
]

LOVE_TIPS = [
    "💡 পরামর্শ: সঙ্গীর কথার গুরুত্ব দিন এবং ভালো শ্রোতা হন।",
    "💡 পরামর্শ: প্রতিদিন অন্তত একবার তার খবরাখবর নিন এবং যত্ন দেখান।",
    "💡 পরামর্শ: সম্পর্কে ছোট ছোট ভুল ক্ষমার চোখে দেখতে শিখুন।",
    "💡 পরামর্শ: মাঝে মাঝে কোনো কারণ ছাড়াই তাকে চমকে (Surprise) দিন।"
]

FLIRT_LINES = [
    "তুমি কি কোনো জাদু জানো? কারণ আমি যতবার তোমার দিকে তাকাই, চারপাশের বাকি সবকিছু গায়েব হয়ে যায়! 😉✨",
    "আমার কাছে একটা ম্যাপ আছে, কিন্তু আমি তোমার চোখে হারিয়ে গিয়েছি! 🗺️❤️",
    "তোমার হাসিটা দেখতে এতটা সুন্দর কেন? আমার দিনটাই সুন্দর হয়ে যায়! 🙈"
]

# ১. /start কমান্ড ও মেইন মেনু
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"হ্যালো {user_name}! ❤️\n\n"
        "আমি আপনার ভালোবাসার বিশেষ সহকারী বোট। নিচে দেওয়া বাটন বা কমান্ড ব্যবহার করে সেবা উপভোগ করুন:"
    )

    # ইনলাইন বাটন মেনু
    keyboard = [
        [InlineKeyboardButton("💖 লাভ ক্যালকুলেটর", callback_data="btn_calc_info")],
        [InlineKeyboardButton("📜 রোমান্টিক উক্তি", callback_data="btn_quote"), InlineKeyboardButton("💡 সম্পর্কের টিপস", callback_data="btn_tips")],
        [InlineKeyboardButton("😉 ফ্লার্ট লাইন", callback_data="btn_flirt")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup)

# ২. লাভ ক্যালকুলেটর (/lovecalculator নাম১ + নাম২)
async def love_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ইউজার যদি প্যারামিটার দিয়ে থাকে (যেমন: /lovecalculator রহিম + রহিমা)
    if not context.args or "+" not in " ".join(context.args):
        await update.message.reply_text(
            "⚠️ ব্যবহারের নিয়ম:\n`/lovecalculator নাম১ + নাম২`\n\n"
            "উদাহরণ:\n`/lovecalculator শাকিব + বুশরা`",
            parse_mode="Markdown"
        )
        return

    full_text = " ".join(context.args)
    names = full_text.split("+")
    name1 = names[0].strip()
    name2 = names[1].strip()

    # নামের ওপর ভিত্তি করে একটি নির্দিষ্ট পার্সেন্টেজ হিসাব (যেন প্রতিবার একই ইনপুটে একই ফলাফল আসে)
    combined = (name1.lower() + name2.lower()).encode('utf-8')
    score = sum(combined) % 101

    if score > 80:
        comment = "স্বর্গীয় জুটি! আপনাদের ভালোবাসা চিরস্থায়ী হোক। 👩‍❤️‍👨💖"
    elif score > 50:
        comment = "বেশ ভালো সম্পর্ক! একটু যত্ন নিলেই সেরা জুটি হবেন। ❤️"
    else:
        comment = "সম্পর্কে আরও বোঝাপড়া ও সময় দেওয়া প্রয়োজন! 💔"

    response = (
        f"💌 *লাভ ক্যালকুলেটর রেজাল্ট* 💌\n\n"
        f"👤 *প্রথম নাম:* {name1}\n"
        f"👤 *দ্বিতীয় নাম:* {name2}\n\n"
        f"🔥 *ভালোবাসার হার:* `{score}%`\n"
        f"📝 *মতামত:* {comment}"
    )
    await update.message.reply_text(response, parse_mode="Markdown")

# ৩. রোমান্টিক উক্তি
async def love_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quote = random.choice(LOVE_QUOTES)
    if update.message:
        await update.message.reply_text(quote)
    elif update.callback_query:
        await update.callback_query.message.reply_text(quote)

# ৪. সম্পর্কের টিপস
async def love_tips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tip = random.choice(LOVE_TIPS)
    if update.message:
        await update.message.reply_text(tip)
    elif update.callback_query:
        await update.callback_query.message.reply_text(tip)

# ৫. ফ্লার্ট মেসেজ
async def flirt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    line = random.choice(FLIRT_LINES)
    if update.message:
        await update.message.reply_text(line)
    elif update.callback_query:
        await update.callback_query.message.reply_text(line)

# ৬. বাটন ক্লিক হ্যান্ডলার
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_quote":
        await love_quote(update, context)
    elif query.data == "btn_tips":
        await love_tips(update, context)
    elif query.data == "btn_flirt":
        await flirt(update, context)
    elif query.data == "btn_calc_info":
        await query.message.reply_text(
            "💖 লাভ ক্যালকুলেটর ব্যবহার করতে এভাবে মেসেজ পাঠান:\n\n"
            "`/lovecalculator আপনারনাম + প্রিয়মানুষেরনাম`",
            parse_mode="Markdown"
        )

# ৭. সাধারণ টেক্সট মেসেজের উত্তর
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.lower()
    
    if "ভালোবাসি" in user_text or "love" in user_text:
        await update.message.reply_text("ভালোবাসা সুন্দর! সবসময় প্রিয় মানুষটিকে আগলে রাখুন। ❤️")
    elif "কেমন আছো" in user_text:
        await update.message.reply_text("আমি ভালো আছি! আপনার রোমান্টিক মুহূর্তগুলো সুন্দর করতে আমি প্রস্তুত। ✨")
    else:
        await update.message.reply_text("আমি বুজতে পারিনি! মেনু দেখতে /start চাপুন অথবা বাটন ব্যবহার করুন। 🤖")

if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    
    if not TOKEN:
        raise ValueError("BOT_TOKEN পাওয়া যায়নি! Environment Variable চেক করুন।")

    app = ApplicationBuilder().token(TOKEN).build()

    # কমান্ড হ্যান্ডলার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lovecalculator", love_calculator))
    app.add_handler(CommandHandler("lovequote", love_quote))
    app.add_handler(CommandHandler("lovetips", love_tips))
    app.add_handler(CommandHandler("flirt", flirt))

    # ইনলাইন বাটন ও সাধারণ টেক্সট হ্যান্ডলার
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("ভালোবাসার বোট সফলতা সহকারে চালু হয়েছে...")
    app.run_polling()
