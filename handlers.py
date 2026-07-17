import json
import re
from config import db, ADMIN_ID
from keyboards import (
    kb_main, kb_khab, kb_meter, kb_next, inline_action, kb_custom_budget
)
from core import (
    get_session, set_session, register_user, save_file, search_files,
    send_msg, send_pic, get_next_sequence_value
)

def parse_budget_text(text: str) -> int:
    """تبدیل متن‌های بودجه به عدد صحیح ریاضی (تومان) با پشتیبانی کامل از عدد فارسی و انگلیسی"""
    persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(persian_to_english).lower().strip()

    numbers = re.findall(r"\d+\.\d+|\d+", text)
    if not numbers:
        return 0
    val = float(numbers[0])

    if any(x in text for x in ["میلیارد", "milliard", "b"]):
        return int(val * 10**9)
    elif any(x in text for x in ["میلیون", "million", "m"]):
        return int(val * 10**6)

    return int(val * 10**9) if val < 10000 else int(val)


def push_history(user_id, state_name):
    """ذخیره مرحله فعلی در تاریخچه سشن برای بازگشت به عقب صحیح"""
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if not history or history[-1] != state_name:
        history.append(state_name)
    set_session(user_id, history=history)


async def show_results(cid, res, is_admin):
    """نمایش نتایج جستجو به همراه دکمه شیشه‌ای علاقه‌مندی و دکمه صفحه بعد"""
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
    """مدیریت بازگشت گام‌به‌گام به عقب بر اساس دکمه (🔙 مرحله قبل)"""
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if len(history) <= 1:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
        await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
        return

    history.pop()  # حذف مرحله فعلی از تاریخچه
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
        khab = s.get("khab")
        if khab:
            await send_msg(cid, f"تنظیمات بودجه ملک {khab}ه:", kb_custom_budget(khab))
        else:
            await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())
    elif prev_state == "select_meter":
        set_session(user_id, meter_min=None, meter_max=None)
        await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter())


async def handle_start_flow(cid, user_id, kind):
    """شروع فرآیند جستجوی ملک با ریست کامل سشن برای جلوگیری از تداخل مسیرها"""
    set_session(user_id, kind=kind, page=1, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
    push_history(user_id, "main")
    push_history(user_id, "select_khab")

    click_field = "buy_clicks" if kind == "فروش" else "rent_clicks"
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {click_field: 1}}, upsert=True)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())


async def process_bale_webhook(data: dict):
    """پردازشگر اصلی پیام‌های بله"""
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
    if not msg:
        return

    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    first_name = msg.get("from", {}).get("first_name", "کاربر گرامی")

    if ctype == "private":
        register_user(cid, first_name)
    if ctype == "channel":
        if "photo" in msg and "موجود" in txt:
            photos = [msg["photo"][-1]["file_id"]]
            await save_file(txt, photos)
        return

    if ctype == "private":
        user_id = cid
        is_admin = (user_id == ADMIN_ID)
        s = get_session(user_id) or {}

        # --- اتصال به پنل مدیریت در اکستنشن ---
        from extensions import handle_admin_commands
        if is_admin:
            if await handle_admin_commands(cid, txt):
                return
        # -------------------------------------

        # دکمه بازگشت به عقب
        if txt == "🔙 مرحله قبل":
            await handle_back_step(cid, user_id, is_admin)
            return

        # هدایت کلیدهای منوی اصلی
        if txt in ["/start", "بازگشت به منو اصلی"]:
            set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
            push_history(user_id, "main")
            welcome = f"سلام {first_name} عزیز، به ربات هوشمند خوش آمدید. 🏠"
            await send_msg(cid, welcome, kb_main(is_admin))

        elif txt == "🏠 خرید":
            await handle_start_flow(cid, user_id, "فروش")

        elif txt == "🔑 رهن و اجاره":
            await handle_start_flow(cid, user_id, "رهن_اجاره")

        elif "پشتیبانی" in txt:
            await send_msg(cid, "📞 **پشتیبانی بروکر**\n\nبا کلیک روی دکمه‌های زیر تماس بگیرید یا پیام دهید:", {
                "inline_keyboard": [
                    [{"text": "📱 09123692401", "url": "tel:09123692401"}, {"text": "📱 09003692401", "url": "tel:09003692401"}],
                    [{"text": "🟢 پیام در بله 💬", "url": "https://ble.ir/sohrabbahador"}]
                ]
            })

        # فرآیند انتخاب خواب
        elif "خواب" in txt and "مشاهده" not in txt:
            clean_khab = txt.replace(" ", "")
            final_khab = "۴ خواب و بیشتر" if ("۴" in clean_khab or "بیشتر" in clean_khab) else txt.strip()
            set_session(user_id, khab=final_khab)
            push_history(user_id, "select_khab")
            await send_msg(cid, f"بودجه مورد نظر برای {final_khab} را تعیین کنید یا همه فایل‌ها را ببینید:", kb_custom_budget(final_khab))

        # ورود بودجه دلخواه
        elif txt == "💵 حداقل بودجه":
            khab_val = s.get("khab", "۱ خواب")
            example_val = "10 میلیارد" if khab_val == "۱ خواب" else "15 میلیارد"
            await send_msg(cid, f"✍️ حداقل بودجه خود را بنویسید و ارسال کنید:\n(مثال؛ {example_val}):")

        elif txt == "💵 حداکثر بودجه":
            khab_val = s.get("khab", "۱ خواب")
            example_val = "20 میلیارد" if khab_val == "۱ خواب" else "100 میلیارد"
            await send_msg(cid, f"✍️ حداکثر بودجه خود را بفرستید:\n(مثال؛ {example_val}):")

        # دکمه‌های «مشاهده همه»
        elif "📋 مشاهده همه" in txt or "مشاهده همه" in txt:
            khab_val = s.get("khab", "۱ خواب")
            res = search_files(s.get("kind"), khab_val, None, None, None, None, 1)
            await show_results(cid, res, is_admin)

        # دریافت متراژ و نمایش نتایج
        elif "متر" in txt:
            m_map = {"کمتر از ۱۰۰ متر": (0, 100), "۱۰۰ تا ۱۵۰ متر": (100, 150), "۱۵۰ تا ۲۰۰ متر": (150, 200), "بیشتر از ۲۰۰ متر": (200, 999)}
            v = m_map.get(txt, (0, 999))
            set_session(user_id, meter_min=v[0], meter_max=v[1])
            push_history(user_id, "select_meter")
            s_updated = get_session(user_id) or {}
            res = search_files(s_updated.get("kind"), s_updated.get("khab"), s_updated.get("budje_min"), s_updated.get("budje_max"), s_updated.get("meter_min"), s_updated.get("meter_max"), s_updated.get("page", 1))
            await show_results(cid, res, is_admin)

        # علاقه‌مندی‌ها
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

        elif "🔔 تنظیم گوش‌به‌زنگ" in txt:
            if s and s.get("kind"):
                db["alerts"].insert_one({
                    "id": get_next_sequence_value("alert_id"), "user_id": user_id, "kind": s.get("kind"), "khab": s.get("khab"),
                    "budje_min": s.get("budje_min"), "budje_max": s.get("budje_max"), "meter_min": s.get("meter_min"), "meter_max": s.get("meter_max")
                })
                await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد!")
            else:
                await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید.")

        # جستجوی متنی آزاد سراسری
        else:
            res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
            await show_results(cid, res, is_admin)
