# extensions.py
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import ADMIN_ID  # دریافت مستقیم شناسه ادمین از فایل تنظیمات

# پیکربندی لاگ برای عیب‌یابی
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# دیتابیس فرضی در حافظه (می‌توانید در آینده این بخش را به توابع دیتابیس اصلی در core.py متصل کنید)
db_mock = {
    "users": set(),          # شناسه کاربران عضو شده
    "stats": {
        "new_users_today": set(),
        "buy_clicks": 0,
        "rent_clicks": 0,
        "mortgage_clicks": 0
    }
}

# ----------------- بخش ۴: بهینه‌سازی سرعت (مکانیزم کش سبک) -----------------
def log_activity(activity_type: str, user_id: int):
    """ثبت فعالیت‌ها با سرعت بالا در حافظه موقت"""
    db_mock["users"].add(user_id)
    if activity_type == "new_user":
        db_mock["stats"]["new_users_today"].add(user_id)
    elif activity_type == "buy":
        db_mock["stats"]["buy_clicks"] += 1
    elif activity_type == "rent":
        db_mock["stats"]["rent_clicks"] += 1
    elif activity_type == "mortgage":
        db_mock["stats"]["mortgage_clicks"] += 1

# ----------------- بخش ۱: مدیریت و ارسال پیام انبوه -----------------

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش پنل مدیریت"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    total_users = len(db_mock["users"])
    keyboard = [
        [InlineKeyboardButton("📊 گزارش آمار امروز", callback_data="get_report")],
        [InlineKeyboardButton("✉️ ارسال پیام انبوه", callback_data="start_broadcast")],
        [InlineKeyboardButton("👥 لیست شناسه کاربران", callback_data="list_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"👑 **پنل مدیریت ربات املاک**\n\nتعداد کل کاربران ثبت شده: {total_users}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های پنل ادمین"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "list_users":
        users_list = "\n".join([f"• `{uid}`" for uid in db_mock["users"]]) or "کاربری یافت نشد."
        await query.message.reply_text(f"👥 **لیست کاربران:**\n\n{users_list}", parse_mode="Markdown")
        
    elif query.data == "start_broadcast":
        context.user_data["waiting_for_broadcast"] = True
        await query.message.reply_text("✍️ لطفاً پیامی که می‌خواهید به همه کاربران ارسال شود را بنویسید:")

    elif query.data == "get_report":
        # بخش ۲: گزارش روزانه تفکیکی
        stats = db_mock["stats"]
        report_text = (
            f"📊 **گزارش آماری امروز ({datetime.now().strftime('%Y-%m-%d')})**\n\n"
            f"🆕 کاربران جدید امروز: {len(stats['new_users_today'])}\n"
            f"🔍 بازدید بخش خرید: {stats['buy_clicks']} بار\n"
            f"🔑 بازدید بخش رهن: {stats['mortgage_clicks']} بار\n"
            f"🏠 بازدید بخش اجاره: {stats['rent_clicks']} بار\n"
        )
        await query.message.reply_text(report_text, parse_mode="Markdown")

async def send_broadcast_job(context: ContextTypes.DEFAULT_TYPE):
    """ارسال ناهمگام پیام انبوه بدون کند کردن ربات برای سایر کاربران"""
    data = context.job.data
    message_text = data["text"]
    success = 0
    failed = 0
    
    for user_id in list(db_mock["users"]):
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text)
            success += 1
        except Exception:
            failed += 1
            
    await context.bot.send_message(
        chat_id=ADMIN_ID, 
        text=f"📢 **ارسال انبوه به پایان رسید.**\n\n✅ موفق: {success}\n❌ ناموفق (بلاک شده یا غیرفعال): {failed}"
    )

async def receive_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن پیام انبوه از ادمین و صف‌بندی ارسال"""
    if update.effective_user.id != ADMIN_ID or not context.user_data.get("waiting_for_broadcast"):
        return False
    
    context.user_data["waiting_for_broadcast"] = False
    broadcast_text = update.message.text
    
    # اجرای ارسال در پس‌زمینه (Job Queue)
    context.job_queue.run_once(send_broadcast_job, when=1, data={"text": broadcast_text})
    await update.message.reply_text("⏳ پیام در صف ارسال انبوه قرار گرفت. نتیجه پس از اتمام گزارش می‌شود.")
    return True

# ----------------- بخش رهگیری بازدیدها -----------------

async def track_section_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رهگیری کلیک‌های بخش‌های مختلف"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if query.data == "buy_section":
        log_activity("buy", user_id)
        await query.message.reply_text("بخش خرید فعال شد.")
    elif query.data == "rent_section":
        log_activity("rent", user_id)
        await query.message.reply_text("بخش اجاره فعال شد.")
    elif query.data == "mortgage_section":
        log_activity("mortgage", user_id)
        await query.message.reply_text("بخش رهن فعال شد.")

# ----------------- بارگذاری هندلرها -----------------

def register_extension_handlers(application):
    """اتصال تمامی هندلرهای تلگرام به کلاس Application اصلی در main.py"""
    # ادمین
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(CallbackQueryHandler(handle_admin_buttons, pattern="^(list_users|start_broadcast|get_report)$"))
    
    # رهگیری بخش‌ها
    application.add_handler(CallbackQueryHandler(track_section_click, pattern="^(buy_section|rent_section|mortgage_section)$"))
    
    # مدیریت پیام‌های متنی متفرقه
    async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await receive_broadcast_text(update, context):
            return
        
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
