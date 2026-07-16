ADMIN_STATES = {}

# --- بخش پردازش پیام‌های ادمین در webhook ---

if ctype == "channel":
    if "photo" in msg and "موجود" in txt:
        photos = [msg["photo"][-1]["file_id"]]
        await save_file(txt, photos)
        return

if ctype == "private":
    user_id = cid
    is_admin = (user_id == ADMIN_ID)

    if txt in ["/start", "بازگشت به منو اصلی"]:
        welcome = f"سلام {first_name} عزیز 👑 منوی مدیریت:" if is_admin else f"سلام {first_name} عزیز، به خدمات ملکی هوشمند « بروکر املاک » خوش آمدید. 🏠"
        await send_msg(cid, welcome, kb_main(is_admin))

    # پنل ادمین - ارسال پیام همگانی
    if is_admin and ADMIN_STATES.get(user_id) == "waiting_broadcast":
        ADMIN_STATES[user_id] = None
        if txt != "بازگشت به منو اصلی":
            success_count = sum(1 for u in db["users"].find({}, {"user_id": 1}) if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"))
            await send_msg(cid, f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.", kb_main(is_admin))
        else:
            await send_msg(cid, "عملیات لغو شد.", kb_main(is_admin))
        return

    # آمار ادمین
    elif is_admin and txt == "📊 آمار ربات":
        stats = db["stats"].find_one({"_id": "clicks"}) or {}
        await send_msg(cid, f"📊 **آمار:**\n👤 کل کاربران: {db['users'].count_documents({})}\n🏠 کل املاک: {db['files'].count_documents({})}\n🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n🔑 کلیک رهن: {stats.get('rent_clicks', 0)}")

    elif is_admin and txt == "👥 لیست کاربران":
        users_list = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in db["users"].find({}, {"user_id": 1, "first_name": 1})])
        await send_msg(cid, f"👥 **کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")

    elif is_admin and txt == "📢 ارسال پیام همگانی":
        ADMIN_STATES[user_id] = "waiting_broadcast"
        await send_msg(cid, "✍️ متن پیام همگانی را بفرستید:", {"keyboard": [[{"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True})
