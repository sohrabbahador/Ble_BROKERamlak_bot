import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import ADMIN_ID, db

# پیکربندی لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- پنل مدیریت (یکپارچه شده و تمیز) ---

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش پنل مدیریت"""
    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [
        ["📊 آمار ربات", "📢 ارسال پیام همگانی"],
        ["👥 لیست کاربران", "بازگشت به منو اصلی"]
    ]
    await update.message.reply_text("👑 **پنل مدیریت ربات املاک**", 
                                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش متن‌های پنل ادمین با اتصال مستقیم به MongoDB"""
    user_id = update.effective_user.id
    txt = update.message.text
    
    if user_id != ADMIN_ID:
        return

    # ۱. مدیریت ارسال پیام همگانی (وضعیت پایدار در دیتابیس)
    admin_state = db["admin_state"].find_one({"_id": user_id}) or {}
    
    if admin_state.get("waiting_broadcast"):
        if txt == "بازگشت به منو اصلی":
            db["admin_state"].update_one({"_id": user_id}, {"$set": {"waiting_broadcast": False}}, upsert=True)
            await update.message.reply_text("عملیات لغو شد.", reply_markup=ReplyKeyboardRemove())
        else:
            success_count = 0
            for u in db["users"].find({}, {"user_id": 1}):
                try:
                    await context.bot.send_message(chat_id=u["user_id"], text=f"📢 **پیام مدیریت:**\n\n{txt}")
                    success_count += 1
                except: continue
            db["admin_state"].update_one({"_id": user_id}, {"$set": {"waiting_broadcast": False}}, upsert=True)
            await update.message.reply_text(f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.", reply_markup=ReplyKeyboardRemove())
        return

    # ۲. آمار ادمین (اتصال به دیتابیس)
    if txt == "📊 آمار ربات":
        stats = db["stats"].find_one({"_id": "clicks"}) or {}
        await update.message.reply_text(
            f"📊 **آمار:**\n👤 کل کاربران: {db['users'].count_documents({})}\n"
            f"🏠 کل املاک: {db['files'].count_documents({})}\n"
            f"🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n"
            f"🔑 کلیک رهن: {stats.get('mortgage_clicks', 0)}"
        )

    # ۳. لیست کاربران
    elif txt == "👥 لیست کاربران":
        users_list = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in db["users"].find({}, {"user_id": 1, "first_name": 1})])
        await update.message.reply_text(f"👥 **کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")

    # ۴. شروع ارسال پیام
    elif txt == "📢 ارسال پیام همگانی":
        db["admin_state"].update_one({"_id": user_id}, {"$set": {"waiting_broadcast": True}}, upsert=True)
        await update.message.reply_text("✍️ متن پیام همگانی را بفرستید:", reply_markup=ReplyKeyboardMarkup([["بازگشت به منو اصلی"]], resize_keyboard=True))

# --- رهگیری کلیک‌ها ---
async def track_section_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "buy_section":
        await query.message.reply_text("بخش خرید فعال شد.")
    elif query.data == "rent_section":
        await query.message.reply_text("بخش اجاره فعال شد.")
    elif query.data == "mortgage_section":
        await query.message.reply_text("بخش رهن فعال شد.")

# --- ثبت هندلرها ---
def register_extension_handlers(application):
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))
    application.add_handler(CallbackQueryHandler(track_section_click, pattern="^(buy_section|rent_section|mortgage_section)$"))
