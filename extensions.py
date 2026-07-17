from config import db
from core import send_msg

# --- پردازش دستورات ادمین ---
async def handle_admin_commands(cid, txt):
    """پردازش دستورات ادمین به صورت مستقیم"""
    
    # ۱. مدیریت ارسال پیام همگانی (وضعیت پایدار در دیتابیس)
    admin_state = db["admin_state"].find_one({"_id": cid}) or {}
    
    if admin_state.get("waiting_broadcast"):
        if txt == "بازگشت به منو اصلی":
            db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
            await send_msg(cid, "عملیات لغو شد.")
        else:
            success_count = 0
            for u in db["users"].find({}, {"user_id": 1}):
                if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"):
                    success_count += 1
            db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
            await send_msg(cid, f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.")
        return True # پردازش شد

    # ۲. آمار ربات
    if txt == "📊 آمار ربات":
        stats = db["stats"].find_one({"_id": "clicks"}) or {}
        await send_msg(cid, f"📊 **آمار:**\n👤 کل کاربران: {db['users'].count_documents({})}\n"
                           f"🏠 کل املاک: {db['files'].count_documents({})}\n"
                           f"🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n"
                           f"🔑 کلیک رهن: {stats.get('rent_clicks', 0)}")
        return True

    # ۳. لیست کاربران
    elif txt == "👥 لیست کاربران":
        users_list = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in db["users"].find({}, {"user_id": 1, "first_name": 1})])
        await send_msg(cid, f"👥 **کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")
        return True

    # ۴. شروع ارسال پیام همگانی
    elif txt == "📢 ارسال پیام همگانی":
        db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": True}}, upsert=True)
        await send_msg(cid, "✍️ متن پیام همگانی را بفرستید:")
        return True

    return False # دستوری شناسایی نشد
