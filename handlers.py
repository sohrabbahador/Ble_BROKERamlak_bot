# handlers.py
import json
import re
from config import db, ADMIN_ID
from keyboards import (
    kb_main, kb_khab, kb_budje_forosh, kb_budje_rahn, kb_meter, kb_next, inline_action,
    kb_custom_budget_1khab  # <--- ایمپورت منوی اختصاصی ۱ خواب از فایل کیبوردها
)
from core import (
    get_session, set_session, register_user, save_file, search_files,
    send_msg, send_pic, get_next_sequence_value
)

ADMIN_STATES = {}

def parse_budget_text(text: str) -> int:
    """تبدیل متن‌های فارسی/انگلیسی بودجه به عدد صحیح ریاضی (تومان)"""
    # تبدیل ارقام فارسی به انگلیسی
    persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(persian_to_english).lower().strip()
    
    # استخراج تمام اعداد (شامل اعشاری)
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if not numbers:
        return 0
    
    val = float(numbers[0])
    
    if "میلیارد" in text or "milliard" in text or "b" in text:
        return int(val * 10**9)
    elif "میلیون" in text or "million" in text or "m" in text:
        return int(val * 10**6)
    
    # اگر کاربر عدد خالص وارد کرده باشد (با فرض اینکه به تومان است)
    if val < 10000:  # مثلاً کاربر تایپ کرده "25" (به معنی ۲۵ میلیارد)
        return int(val * 10**9)
        
    return int(val)


def push_history(user_id, state_name):
    """ذخیره مرحله فعلی در تاریخچه سشن برای امکان برگشت به عقب"""
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if not history or history[-1] != state_name:
        history.append(state_name)
    set_session(user_id, history=history)


async def handle_back_step(cid, user_id, is_admin):
    """بازگرداندن کاربر به یک مرحله قبل بر اساس تاریخچه سشن"""
    s = get_session(user_id) or {}
    history = s.get("history", [])
    
    if len(history) <= 1:
        # اگر تاریخچه‌ای نبود یا در مرحله اول بود، به منوی اصلی برگردد
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
        await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
        return
    
    # حذف وضعیت فعلی و گرفتن وضعیت قبلی
    history.pop()  # حذف حالت فعلی
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
        kind = s.get("kind")
        khab = s.get("khab")
        if khab == "۱ خواب":
            await send_msg(cid, "تنظیمات بودجه ملک ۱ خوابه:", kb_custom_budget_1khab())
        elif kind == "فروش":
            await send_msg(cid, "بازه بودجه خرید را انتخاب کنید:", kb_budje_forosh())
        else:
            await send_msg(cid, "بازه رهن مورد نظرتان را انتخاب کنید:", kb_budje_rahn())
            
    elif prev_state == "select_meter":
        set_session(user_id, meter_min=None, meter_max=None)
        await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter())


async def handle_buy_start(cid, user_id):
    set_session(user_id, kind="فروش", page=1, history=[])
    push_history(user_id, "main")
    push_history(user_id, "select_khab")
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {"buy_clicks": 1}}, upsert=True)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())


async def handle_rent_start(cid, user_id):
    set_session(user_id, kind="رهن_اجاره", page=1, history=[])
    push_history(user_id, "main")
    push_history(user_id, "select_khab")
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {"rent_clicks": 1}}, upsert=True)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())


def get_buy_budget_ranges():
    return {
        "۲۰ تا ۳۰ میلیارد": (20 * 10**9, 30 * 10**9),
        "۳۰ تا ۴۰ میلیارد": (30 * 10**9, 40 * 10**9),
        "۴۰ تا ۵۰ میلیارد": (40 * 10**9, 50 * 10**9),
        "۵۰ میلیارد به بالا": (50 * 10**9, 999 * 10**9),
    }


def get_rent_budget_ranges():
    return {
        "کمتر از ۲ میلیارد": (0, 2 * 10**9),
        "۲ تا ۴ میلیارد": (2 * 10**9, 4 * 10**9),
        "۴ تا ۶ میلیارد": (4 * 10**9, 6 * 10**9),
        "۶ میلیارد به بالا": (6 * 10**9, 999 * 10**9),
    }


async def process_bale_webhook(data: dict):
    """پردازشگر اصلی پیام‌ها و رویدادهای دریافتی از پیام‌رسان بله"""
    
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            exists = db["favorites"].find_one({"user_id": cid, "file_id": file_id})
            if not exists:
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else:
                await send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
        return

    msg = (
        data.get("message") 
        or data.get("edited_message") 
        or data.get("channel_post") 
        or data.get("edited_channel_post") 
        or data.get("body")
    )
    if not msg:
        return

    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    user_info = msg.get("from", {})
    first_name = user_info.get("first_name", "کاربر گرامی")

    if ctype == "private":
        register_user(cid, first_name)

    if ctype == "channel":
        photos = []
        if "photo" in msg:
            photos.append(msg["photo"][-1]["file_id"])
        if "media_group_id" in msg and "photo" in msg:
            photos.append(msg["photo"][-1]["file_id"])
        if "موجود" in txt:
            await save_file(txt, [p for p in photos if p])
        return

    if ctype == "private":
        user_id = cid
        is_admin = (user_id == ADMIN_ID)
        s = get_session(user_id) or {}

        # مدیریت دکمه بازگشت به مرحله قبل
        if txt == "🔙 مرحله قبل":
            await handle_back_step(cid, user_id, is_admin)
            return

        if is_admin and ADMIN_STATES.get(user_id) == "waiting_broadcast":
            if txt == "بازگشت به منو اصلی":
                ADMIN_STATES[user_id] = None
                await send_msg(cid, "عملیات ارسال پیام همگانی لغو شد.", kb_main(is_admin))
            else:
                ADMIN_STATES[user_id] = None
                all_users = list(db["users"].find({}, {"user_id": 1}))
                success_count = 0
                for u in all_users:
                    try:
                        await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}")
                        success_count += 1
                    except:
                        pass
                await send_msg(cid, f"✅ پیام همگانی با موفقیت به {success_count} کاربر ارسال شد.", kb_main(is_admin))
                return

        # دریافت عدد تایپی کاربر برای حداقل/حداکثر بودجه ۱ خواب
        if ADMIN_STATES.get(user_id) in ["waiting_min_budget", "waiting_max_budget"]:
            budget_val = parse_budget_text(txt)
            if budget_val == 0:
                await send_msg(cid, "⚠️ لطفاً یک مبلغ معتبر وارد کنید (مثال: ۲.۵ میلیارد یا ۳۰۰ میلیون):")
                return
            
            state = ADMIN_STATES[user_id]
            ADMIN_STATES[user_id] = None # ریست کردن وضعیت ادمین/کاربر
            
            if state == "waiting_min_budget":
                set_session(user_id, budje_min=budget_val)
                await send_msg(cid, f"✅ حداقل بودجه ثبت شد: {budget_val:,} تومان\nاکنون سقف بودجه خود را تعیین کنید یا مستقیماً متراژ را انتخاب کنید.", kb_custom_budget_1khab())
            else:
                set_session(user_id, budje_max=budget_val)
                await send_msg(cid, f"✅ حداکثر بودجه ثبت شد: {budget_val:,} تومان\nاکنون حدود متراژ ملک را انتخاب کنید:", kb_meter())
                push_history(user_id, "select_budget")
            return

        if txt in ["/start", "بازگشت به منو اصلی"]:
            set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
            push_history(user_id, "main")
            welcome_text = f"سلام {first_name} عزیز، به ربات هوشمند بروکر خوش آمدید. 🏠\n\nنوع عملیات مورد نظرتان را انتخاب کنید:"
            if is_admin:
                welcome_text = f"سلام سهراب عزیز، خوش آمدید. 👑\nمنوی مدیریت برای شما فعال است:"
            await send_msg(cid, welcome_text, kb_main(is_admin))

        elif txt == "🏠 خرید":
            await handle_buy_start(cid, user_id)

        elif txt == "🔑 رهن و اجاره":
            await handle_rent_start(cid, user_id)

        # پردازش دکمه پشتیبانی به صورت شیشه‌ای و برقراری تماس خودکار
        elif "پشتیبانی" in txt:
            support_text = (
                "📞 **پشتیبانی بروکر**\n\n"
                "جهت سپردن ملک، هماهنگی بازدید یا مشاوره، با کلیک روی دکمه‌های زیر می‌توانید مستقیماً با ما تماس بگیرید یا در بله پیام دهید:"
            )
            
            support_keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "📱 09123692401", "url": "tel:09123692401"},
                        {"text": "📱 09003692401", "url": "tel:09003692401"}
                    ],
                    [
                        {"text": "🟢 پیام در بله  💬", "url": "https://ble.ir/sohrabbahador"}
                    ]
                ]
            }
            await send_msg(cid, support_text, support_keyboard)

        elif "خواب" in txt:
            clean_khab = txt.replace(" ", "")
            final_khab = "۴ خواب و بیشتر" if ("۴" in clean_khab or "بیشتر" in clean_khab) else txt.strip()
            set_session(user_id, khab=final_khab)
            push_history(user_id, "select_khab")
            
            if final_khab == "۱ خواب":
                # انشعاب اختصاصی ۱ خواب
                await send_msg(cid, "بودجه مورد نظر خود برای فایل ۱ خوابه را تعیین کنید یا همه فایل‌ها را ببینید:", kb_custom_budget_1khab())
            else:
                s = get_session(user_id) or {}
                if s.get("kind") == "فروش":
                    await send_msg(cid, "بازه بودجه خرید را انتخاب کنید:", kb_budje_forosh())
                else:
                    await send_msg(cid, "بازه رهن مورد نظرتان را انتخاب کنید:", kb_budje_rahn())

        # سناریوی اختصاصی کلیدهای بخش ۱ خواب
        elif txt == "💵 حداقل بودجه":
            ADMIN_STATES[user_id] = "waiting_min_budget"
            await send_msg(cid, "✍️ حداقل بودجه خود را بنویسید و ارسال کنید:\n(مثال: ۲.۵ میلیارد یا ۳۰۰ میلیون)")

        elif txt == "💵 حداکثر بودجه":
            ADMIN_STATES[user_id] = "waiting_max_budget"
            await send_msg(cid, "✍️ حداکثر بودجه خود را بنویسید و ارسال کنید:\n(مثال: ۵ میلیارد یا ۸۰۰ میلیون)")

        elif txt == "📋 مشاهده همه ۱خواب‌ها":
            s = get_session(user_id) or {}
            res = search_files(s.get("kind"), "۱ خواب", None, None, None, None, 1)
            if not res:
                await send_msg(cid, "❌ متاسفانه هیچ فایل ۱ خوابه‌ای یافت نشد.", kb_main(is_admin))
            else:
                for r in res:
                    cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
                    photos = json.loads(r["photos"]) if r.get("photos") else []
                    if photos:
                        await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                    else:
                        await send_msg(cid, cap, inline_action(r["id"]))
                await send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())

        elif any(w in txt for w in ["میلیارد", "میلیونی"]):
            b_map = {}
            b_map.update(get_buy_budget_ranges())
            b_map.update(get_rent_budget_ranges())
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
            if s:
                res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), s.get("meter_min"), s.get("meter_max"), s.get("page", 1))
                if not res:
                    await send_msg(cid, "❌ متاسفانه ملکی با این مشخصات یافت نشد. فیلترها را تغییر دهید یا مجدداً تلاش کنید.", kb_main(is_admin))
                else:
                    for r in res:
                        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        if photos:
                            await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                        else:
                            await send_msg(cid, cap, inline_action(r["id"]))
                    await send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())
            else:
                await send_msg(cid, "خطایی رخ داد. لطفاً مجدداً جستجو را آغاز کنید.", kb_main(is_admin))

        elif txt == "صفحه بعد":
            s = get_session(user_id) or {}
            if s:
                next_page = (s.get("page") or 1) + 1
                set_session(user_id, page=next_page)
                s = get_session(user_id) or {}
                res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), s.get("meter_min"), s.get("meter_max"), s.get("page", 1))
                if not res:
                    await send_msg(cid, "🏁 به انتهای لیست فایل‌های موجود رسیدید.", kb_main(is_admin))
                else:
                    for r in res:
                        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        if photos:
                            await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                        else:
                            await send_msg(cid, cap, inline_action(r["id"]))
                    await send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())
            else:
                await send_msg(cid, "نشست کاربری شما یافت نشد. بازگشت به منو اصلی...", kb_main(is_admin))

        elif txt == "⭐ علاقه‌مندی‌ها":
            favs = list(db["favorites"].find({"user_id": user_id}))
            if not favs:
                await send_msg(cid, "لیست علاقه‌مندی‌های شما در حال حاضر خالی است.")
            else:
                await send_msg(cid, "⭐ **لیست فایل‌های مورد علاقه شما:**")
                for f in favs:
                    r = db["files"].find_one({"id": f["file_id"]})
                    if r:
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        if photos:
                            await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                        else:
                            await send_msg(cid, r["text"], inline_action(r["id"]))

        elif "🔍 جستجوی سریع" in txt:
            await send_msg(cid, "کافیست نام محله (مثلاً جنت‌آباد) یا ویژگی مورد نظرتان را بنویسید و بفرستید تا سریعاً جستجو کنم:")

        elif txt == "🔔 تنظیم گوش‌به‌زنگ":
            s = get_session(user_id) or {}
            if s and s.get("kind"):
                alert_id = get_next_sequence_value("alert_id")
                db["alerts"].insert_one({
                    "id": alert_id, "user_id": user_id, "kind": s.get("kind"), "khab": s.get("khab"),
                    "budje_min": s.get("budje_min"), "budje_max": s.get("budje_max"),
                    "meter_min": s.get("meter_min"), "meter_max": s.get("meter_max")
                })
                await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد! به محض اضافه شدن فایل جدید همسو با سلیقه‌تان، بلافاصله به شما اطلاع می‌دهیم.")
            else:
                await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید تا فیلترهای دلخواه شما شناسایی و ثبت شوند.")

        elif is_admin and txt == "📊 آمار ربات":
            stats_doc = db["stats"].find_one({"_id": "clicks"}) or {}
            buy_cnt = stats_doc.get("buy_clicks", 0)
            rent_cnt = stats_doc.get("rent_clicks", 0)
            
            await send_msg(
                cid, 
                f"📊 **آمار سیستم هوشمند بروکر:**\n\n"
                f"👤 کل کاربران عضو: {db['users'].count_documents({})} نفر\n"
                f"🏠 کل املاک ثبت‌شده: {db['files'].count_documents({})} ملک\n\n"
                f"🔍 میزان بازدید بخش خرید: {buy_cnt} بار\n"
                f"🔑 میزان بازدید بخش رهن و اجاره: {rent_cnt} بار"
            )

        elif is_admin and txt == "👥 لیست کاربران":
            users = list(db["users"].find({}, {"user_id": 1, "first_name": 1}))
            if not users:
                await send_msg(cid, "کاربری در دیتابیس یافت نشد.")
            else:
                users_list = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in users])
                await send_msg(cid, f"👥 **لیست کاربران عضو ربات:**\n\n{users_list}")

        elif is_admin and txt == "📢 ارسال پیام همگانی":
            ADMIN_STATES[user_id] = "waiting_broadcast"
            await send_msg(cid, "✍️ لطفاً متنی که می‌خواهید برای تمام کاربران ارسال شود را بنویسید و بفرستید:\n(برای لغو، دکمه بازگشت به منو اصلی را بزنید.)", {"keyboard": [[{"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True})

        else:
            res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
            if not res:
                await send_msg(cid, "❌ موردی با این مشخصات یافت نشد. جستجوی متنی دیگری انجام دهید یا از دکمه‌های منو استفاده کنید.", kb_main(is_admin))
            else:
                for r in res:
                    cap = f"🔍 **نتیجه جستجوی سریع**\n\n{r['text'][:300]}..."
                    photos = json.loads(r["photos"]) if r.get("photos") else []
                    if photos:
                        await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                    else:
                        await send_msg(cid, cap, inline_action(r["id"]))
