# handlers.py
import json
import re
from config import db, ADMIN_ID
from keyboards import (
    kb_main, kb_khab, kb_budje_forosh, kb_budje_rahn, kb_meter, kb_next, inline_action, kb_custom_budget_1khab
)
from core import (
    get_session, set_session, register_user, save_file, search_files,
    send_msg, send_pic, get_next_sequence_value
)

ADMIN_STATES = {}

def parse_budget_text(text: str) -> int:
    """تبدیل متن‌های بودجه به عدد صحیح ریاضی (تومان)"""
    persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(persian_to_english).lower().strip()
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if not numbers:
        return 0
    val = float(numbers[0])
    if "میلیارد" in text or "milliard" in text or "b" in text:
        return int(val * 10**9)
    elif "میلیون" in text or "million" in text or "m" in text:
        return int(val * 10**6)
    return int(val * 10**9) if val < 10000 else int(val)


def push_history(user_id, state_name):
    """ذخیره مرحله فعلی در تاریخچه سشن"""
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if not history or history[-1] != state_name:
        history.append(state_name)
    set_session(user_id, history=history)


async def show_results(cid, res, is_admin):
    """تابع کمکی یکپارچه برای نمایش نتایج جستجو و دکمه صفحه بعد (حذف کدهای تکراری)"""
    if not res:
        await send_msg(cid, "❌ متاسفانه ملکی با این مشخصات یافت نشد. فیلترها را تغییر دهید یا مجدداً تلاش کنید.", kb_main(is_admin))
        return
    for r in res:
        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
        photos = json.loads(r["photos"]) if r.get("photos") else []
        if photos:
            await send_pic(cid, photos[0], cap, inline_action(r["id"]))
        else:
            await send_msg(cid, cap, inline_action(r["id"]))
    await send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())


async def handle_back_step(cid, user_id, is_admin):
    """مدیریت بازگشت به عقب بر اساس تاریخچه مسیر طی شده"""
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if len(history) <= 1:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
        await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
        return
    
    history.pop()  # حذف گام فعلی
    prev_state = history[-1]
    set_session(user_id, history=history)
    
    if prev_state == "main":
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None)
        await send_msg(cid, "نوع عملیات مورد نظرتان را انتخاب کنید:", kb_main(is_admin))
    elif prev_state == "select_khab":
        set_session(user_id, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None)
        await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())
    elif prev_state == "select_budget":
        set_session(user_id, budje_min=None, budje_max=None, meter_min=None, meter_max=None)
        if s.get("khab") == "۱ خواب":
            await send_msg(cid, "تنظیمات بودجه ملک ۱ خوابه:", kb_custom_budget_1khab())
        else:
            kb = kb_budje_forosh() if s.get("kind") == "فروش" else kb_budje_rahn()
            await send_msg(cid, "بازه بودجه مورد نظرتان را انتخاب کنید:", kb)
    elif prev_state == "select_meter":
        set_session(user_id, meter_min=None, meter_max=None)
        await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter())


async def handle_start_flow(cid, user_id, kind):
    """شروع فرآیند جستجو (خرید یا رهن)"""
    set_session(user_id, kind=kind, page=1, history=[])
    push_history(user_id, "main")
    push_history(user_id, "select_khab")
    click_field = "buy_clicks" if kind == "فروش" else "rent_clicks"
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {click_field: 1}}, upsert=True)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())


async def process_bale_webhook(data: dict):
    """پردازشگر اصلی رویدادهای ربات"""
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            if not db["favorites"].find_one({"user_id": cid, "file_id": file_id}):
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else:
                await send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
        return

    msg = data.get("message") or data.get("edited_message") or data.get("body")
    if not msg: return

    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    first_name = msg.get("from", {}).get("first_name", "کاربر گرامی")

    if ctype == "private": register_user(cid, first_name)
    if ctype == "channel":
        if "photo" in msg and "موجود" in txt:
            photos = [msg["photo"][-1]["file_id"]]
            await save_file(txt, photos)
        return

    if ctype == "private":
        user_id = cid
        is_admin = (user_id == ADMIN_ID)
        s = get_session(user_id) or {}

        # ۱. دکمه مرحله قبل
        if txt == "🔙 مرحله قبل":
            await handle_back_step(cid, user_id, is_admin)
            return

        # ۲. بخش ادمین - ارسال پیام همگانی
        if is_admin and ADMIN_STATES.get(user_id) == "waiting_broadcast":
            ADMIN_STATES[user_id] = None
            if txt != "بازگشت به منو اصلی":
                success_count = sum(1 for u in db["users"].find({}, {"user_id": 1}) if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"))
                await send_msg(cid, f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.", kb_main(is_admin))
            else:
                await send_msg(cid, "عملیات لغو شد.", kb_main(is_admin))
            return

        # ۳. دریافت مبالغ دلخواه برای ۱ خواب
        if ADMIN_STATES.get(user_id) in ["waiting_min_budget", "waiting_max_budget"]:
            budget_val = parse_budget_text(txt)
            if budget_val == 0:
                await send_msg(cid, "⚠️ لطفاً یک مبلغ معتبر وارد کنید (مثال: ۲.۵ میلیارد یا ۳۰۰ میلیون):")
                return
            state = ADMIN_STATES[user_id]
            ADMIN_STATES[user_id] = None
            if state == "waiting_min_budget":
                set_session(user_id, budje_min=budget_val)
                await send_msg(cid, f"✅ حداقل بودجه ثبت شد: {budget_val:,} تومان\nسقف بودجه را تعیین کنید یا مستقیماً متراژ را انتخاب کنید.", kb_custom_budget_1khab())
            else:
                set_session(user_id, budje_max=budget_val)
                await send_msg(cid, f"✅ حداکثر بودجه ثبت شد: {budget_val:,} تومان\nحدود متراژ ملک را انتخاب کنید:", kb_meter())
                push_history(user_id, "select_budget")
            return

        # ۴. هدایت کلیدهای منوی اصلی
        if txt in ["/start", "بازگشت به منو اصلی"]:
            set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
            push_history(user_id, "main")
            welcome = f"سلام {first_name} عزیز 👑 منوی مدیریت:" if is_admin else f"سلام {first_name} عزیز، به ربات هوشمند خوش آمدید. 🏠"
            await send_msg(cid, welcome, kb_main(is_admin))

        elif txt == "🏠 خرید": await handle_start_flow(cid, user_id, "فروش")
        elif txt == "🔑 رهن و اجاره": await handle_start_flow(cid, user_id, "رهن_اجاره")
        elif "پشتیبانی" in txt:
            await send_msg(cid, "📞 **پشتیبانی بروکر**\n\nبا کلیک روی دکمه‌های زیر تماس بگیرید یا پیام دهید:", {
                "inline_keyboard": [
                    [{"text": "📱 09123692401", "url": "tel:09123692401"}, {"text": "📱 09003692401", "url": "tel:09003692401"}],
                    [{"text": "🟢 پیام در بله 💬", "url": "https://ble.ir/sohrabbahador"}]
                ]
            })

        # ۵. فرآیند انتخاب خواب
        elif "خواب" in txt:
            clean_khab = txt.replace(" ", "")
            final_khab = "۴ خواب و بیشتر" if ("۴" in clean_khab or "بیشتر" in clean_khab) else txt.strip()
            set_session(user_id, khab=final_khab)
            push_history(user_id, "select_khab")
            if final_khab == "۱ خواب":
                await send_msg(cid, "بودجه مورد نظر برای ۱ خواب را تعیین کنید یا همه فایل‌ها را ببینید:", kb_custom_budget_1khab())
            else:
                kb = kb_budje_forosh() if s.get("kind") == "فروش" else kb_budje_rahn()
                await send_msg(cid, "بازه بودجه مورد نظر را انتخاب کنید:", kb)

        # دکمه‌های اختصاصی ۱ خواب
        elif txt == "💵 حداقل بودجه":
            ADMIN_STATES[user_id] = "waiting_min_budget"
            await send_msg(cid, "✍️ حداقل بودجه خود را بفرستید (مثال: ۲.۵ میلیارد):")
        elif txt == "💵 حداکثر بودجه":
            ADMIN_STATES[user_id] = "waiting_max_budget"
            await send_msg(cid, "✍️ حداکثر بودجه خود را بفرستید (مثال: ۵ میلیارد):")
        elif txt == "📋 مشاهده همه ۱خواب‌ها":
            res = search_files(s.get("kind"), "۱ خواب", None, None, None, None, 1)
            await show_results(cid, res, is_admin)

        # ۶. فیلتر بودجه و متراژ
        elif any(w in txt for w in ["میلیارد", "میلیونی"]):
            b_map = {**get_buy_budget_ranges(), **get_rent_budget_ranges()}
            v = b_map.get(txt, (0, 999 * 10**9))
            set_session(user_id, budje_min=v[0], budje_max=v[1])
            push_history(user_id, "select_budget")
            await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter())

        elif "متر" in txt:
            m_map = {"کمتر از ۱۰۰ متر": (0, 100), "۱۰۰ تا ۱۵۰ متر": (100, 150), "۱۵۰ تا ۲۰۰ متر": (150, 200), "بیشتر از ۲۰۰ متر": (200, 999)}
            v = m_map.get(txt, (0, 999))
            set_session(user_id, meter_min=v[0], meter_max=v[1])
            push_history(user_id, "select_meter")
            s = get_session(user_id) or {}
            res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), s.get("meter_min"), s.get("meter_max"), s.get("page", 1))
            await show_results(cid, res, is_admin)

        elif txt == "صفحه بعد":
            next_page = (s.get("page") or 1) + 1
            set_session(user_id, page=next_page)
            s = get_session(user_id) or {}
            res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), s.get("meter_min"), s.get("meter_max"), s.get("page", 1))
            if not res:
                await send_msg(cid, "🏁 به انتهای لیست فایل‌های موجود رسیدید.", kb_main(is_admin))
            else:
                await show_results(cid, res, is_admin)

        # سایر دکمه‌های فرعی
        elif txt == "⭐ علاقه‌مندی‌ها":
            favs = list(db["favorites"].find({"user_id": user_id}))
            if not favs:
                await send_msg(cid, "لیست علاقه‌مندی‌های شما خالی است.")
            else:
                for f in favs:
                    if r := db["files"].find_one({"id": f["file_id"]}):
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        await send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else await send_msg(cid, r["text"], inline_action(r["id"]))

        elif "🔍 جستجوی سریع" in txt:
            await send_msg(cid, "کافیست نام محله یا ویژگی مورد نظرتان را بنویسید و بفرستید:")
        elif txt == "🔔 تنظیم گوش‌به‌زنگ":
            if s and s.get("kind"):
                db["alerts"].insert_one({
                    "id": get_next_sequence_value("alert_id"), "user_id": user_id, "kind": s.get("kind"), "khab": s.get("khab"),
                    "budje_min": s.get("budje_min"), "budje_max": s.get("budje_max"), "meter_min": s.get("meter_min"), "meter_max": s.get("meter_max")
                })
                await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد!")
            else:
                await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید.")

        # امکانات آماری ادمین
        elif is_admin and txt == "📊 آمار ربات":
            stats = db["stats"].find_one({"_id": "clicks"}) or {}
            await send_msg(cid, f"📊 **آمار:**\n👤 کل کاربران: {db['users'].count_documents({})}\n🏠 کل املاک: {db['files'].count_documents({})}\n🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n🔑 کلیک رهن: {stats.get('rent_clicks', 0)}")
        elif is_admin and txt == "👥 لیست کاربران":
            users_list = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in db["users"].find({}, {"user_id": 1, "first_name": 1})])
            await send_msg(cid, f"👥 **کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")
        elif is_admin and txt == "📢 ارسال پیام همگانی":
            ADMIN_STATES[user_id] = "waiting_broadcast"
            await send_msg(cid, "✍️ متن پیام همگانی را بفرستید:", {"keyboard": [[{"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True})

        # جستجوی متنی آزاد
        else:
            res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
            if not res:
                await send_msg(cid, "❌ موردی با این مشخصات یافت نشد.", kb_main(is_admin))
            else:
                for r in res:
                    cap = f"🔍 **نتیجه جستجو**\n\n{r['text'][:300]}..."
                    photos = json.loads(r["photos"]) if r.get("photos") else []
                    await send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else await send_msg(cid, cap, inline_action(r["id"]))
