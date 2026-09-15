import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Logging সেটআপ (Render এর কনসোলে বোটের স্ট্যাটাস দেখার জন্য)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# /start কমান্ডের উত্তর
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("হ্যালো! আমি Render-এ সফলভাবে ডিপ্লয় হওয়া একটি টেলিগ্রাম বোট।🤖")

# সাধারণ মেসেজের রিপ্লাই
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"আপনি লিখেছেন: {update.message.text}")

if __name__ == '__main__':
    # Environment Variable থেকে Bot Token নেওয়া
    TOKEN = os.getenv("BOT_TOKEN")
    
    if not TOKEN:
        raise ValueError("BOT_TOKEN পাওয়া যায়নি! Render-এ Environment Variable সেট করুন।")

    app = ApplicationBuilder().token(TOKEN).build()

    # হ্যান্ডলার যুক্ত করা
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("বোট চালু হয়েছে...")
    app.run_polling()
