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

ADMIN_STATES = {}

def parse_budget_text(text: str) -> int:
    persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(persian_to_english).lower().strip()
    numbers = re.findall(r"\d+\.\d+|\d+", text)
    if not numbers: return 0
    val = float(numbers[0])
    if any(x in text for x in ["میلیارد", "milliard", "b"]): return int(val * 10**9)
    elif any(x in text for x in ["میلیون", "million", "m"]): return int(val * 10**6)
    return int(val * 10**9) if val < 10000 else int(val)

def push_history(user_id, state_name):
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if not history or history[-1] != state_name: history.append(state_name)
    set_session(user_id, history=history)

async def show_results(cid, res, is_admin):
    if not res:
        await send_msg(cid, "❌ متاسفانه ملکی با این مشخصات یافت نشد. فیلترها را تغییر دهید یا مجدداً تلاش کنید.", kb_main(is_admin))
        return
    for r in res:
        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
        photos = json.loads(r["photos"]) if r.get("photos") else []
        if photos: await send_pic(cid, photos[0], cap, inline_action(r["id"]))
        else: await send_msg(cid, cap, inline_action(r["id"]))
    await send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())

async def handle_back_step(cid, user_id, is_admin):
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if len(history) <= 1:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
        await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
        return
    history.pop()
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
        await send_msg(cid, f"تنظیمات بودجه ملک {khab}ه:", kb_custom_budget(khab))
    elif prev_state == "select_meter":
        set_session(user_id, meter_min=None, meter_max=None)
        await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter())

async def handle_start_flow(cid, user_id, kind):
    set_session(user_id, kind=kind, page=1, history=[])
    push_history(user_id, "main"); push_history(user_id, "select_khab")
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {"buy_clicks" if kind == "فروش" else "rent_clicks": 1}}, upsert=True)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())

async def process_bale_webhook(data: dict):
    if "callback_query" in data:
        cb = data["callback_query"]; cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            if not db["favorites"].find_one({"user_id": cid, "file_id": file_id}):
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else: await send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
        return

    msg = data.get("message") or data.get("edited_message") or data.get("body")
    if not msg: return
    chat = msg.get("chat", {}); txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type"); user_id = cid; is_admin = (user_id == ADMIN_ID)
    if ctype == "private": register_user(cid, msg.get("from", {}).get("first_name", "کاربر گرامی"))
    if ctype == "channel":
        if "photo" in msg and "موجود" in txt: await save_file(txt, [msg["photo"][-1]["file_id"]])
        return

    s = get_session(user_id) or {}
    if txt == "🔙 مرحله قبل": await handle_back_step(cid, user_id, is_admin); return
    if is_admin and ADMIN_STATES.get(user_id) == "waiting_broadcast":
        if txt != "بازگشت به منو اصلی":
            count = sum(1 for u in db["users"].find({}, {"user_id": 1}) if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"))
            await send_msg(cid, f"✅ پیام به {count} کاربر ارسال شد.", kb_main(is_admin))
        ADMIN_STATES[user_id] = None; return

    if ADMIN_STATES.get(user_id) in ["waiting_min_budget", "waiting_max_budget"]:
        if txt in ["🔙 مرحله قبل", "بازگشت به منو اصلی"]: ADMIN_STATES[user_id] = None
        else:
            budget = parse_budget_text(txt)
            if budget == 0: await send_msg(cid, "⚠️ مبلغ معتبر وارد کنید:"); return
            state = ADMIN_STATES.pop(user_id)
            if state == "waiting_min_budget":
                set_session(user_id, budje_min=budget); await send_msg(cid, f"✅ حداقل {budget:,} ثبت شد.", kb_custom_budget(s.get("khab")))
            else:
                set_session(user_id, budje_max=budget); push_history(user_id, "select_budget")
                await send_msg(cid, f"✅ حداکثر {budget:,} ثبت شد.", kb_meter())
            return

    if txt in ["/start", "بازگشت به منو اصلی"]:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
        push_history(user_id, "main"); welcome = f"سلام {msg.get('from', {}).get('first_name')} عزیز 👑 منوی مدیریت:" if is_admin else "سلام، به ربات خوش آمدید."
        await send_msg(cid, welcome, kb_main(is_admin))
    elif txt == "🏠 خرید": await handle_start_flow(cid, user_id, "فروش")
    elif txt == "🔑 رهن و اجاره": await handle_start_flow(cid, user_id, "رهن_اجاره")
    elif "خواب" in txt and "مشاهده" not in txt:
        khab = "۴ خواب و بیشتر" if ("۴" in txt or "بیشتر" in txt) else txt.strip()
        set_session(user_id, khab=khab); push_history(user_id, "select_khab")
        await send_msg(cid, f"بودجه برای {khab} را تعیین کنید:", kb_custom_budget(khab))
    elif txt in ["💵 حداقل بودجه", "💵 حداکثر بودجه"]:
        ADMIN_STATES[user_id] = "waiting_min_budget" if "حداقل" in txt else "waiting_max_budget"
        await send_msg(cid, f"✍️ {txt} را بنویسید:")
    elif "متر" in txt:
        m_map = {"کمتر از ۱۰۰ متر": (0, 100), "۱۰۰ تا ۱۵۰ متر": (100, 150), "۱۵۰ تا ۲۰۰ متر": (150, 200), "بیشتر از ۲۰۰ متر": (200, 999)}
        v = m_map.get(txt, (0, 999))
        set_session(user_id, meter_min=v[0], meter_max=v[1]); push_history(user_id, "select_meter")
        s = get_session(user_id) or {}
        res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), v[0], v[1], 1)
        await show_results(cid, res, is_admin)
    elif "مشاهده همه" in txt:
        res = search_files(s.get("kind"), s.get("khab"), None, None, None, None, 1); await show_results(cid, res, is_admin)
    elif txt == "صفحه بعد":
        next_p = (s.get("page") or 1) + 1; set_session(user_id, page=next_p)
        res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), s.get("meter_min"), s.get("meter_max"), next_p)
        if not res: await send_msg(cid, "🏁 انتهای لیست.", kb_main(is_admin))
        else: await show_results(cid, res, is_admin)
    elif txt == "⭐ علاقه‌مندی‌ها":
        favs = list(db["favorites"].find({"user_id": user_id}))
        if not favs: await send_msg(cid, "خالی است.")
        else:
            for f in favs:
                if r := db["files"].find_one({"id": f["file_id"]}):
                    cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                    photos = json.loads(r["photos"]) if r.get("photos") else []
                    await (send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else send_msg(cid, r["text"], inline_action(r["id"])))
    elif txt == "🔔 تنظیم گوش‌به‌زنگ":
        if s.get("kind"):
            db["alerts"].insert_one({"id": get_next_sequence_value("alert_id"), "user_id": user_id, "kind": s.get("kind"), "khab": s.get("khab"), "budje_min": s.get("budje_min"), "budje_max": s.get("budje_max"), "meter_min": s.get("meter_min"), "meter_max": s.get("meter_max")})
            await send_msg(cid, "✅ ثبت شد!")
        else: await send_msg(cid, "⚠️ ابتدا جستجو را کامل کنید.")
    elif is_admin and txt == "📊 آمار ربات":
        stats = db["stats"].find_one({"_id": "clicks"}) or {}
        await send_msg(cid, f"📊 **آمار:**\n👤 کاربران: {db['users'].count_documents({})}\n🏠 املاک: {db['files'].count_documents({})}\n🔍 خرید: {stats.get('buy_clicks', 0)}\n🔑 رهن: {stats.get('rent_clicks', 0)}")
    elif is_admin and txt == "👥 لیست کاربران":
        lst = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in db["users"].find({}, {"user_id": 1, "first_name": 1})])
        await send_msg(cid, f"👥 **کاربران:**\n\n{lst}" if lst else "کاربری یافت نشد.")
    elif is_admin and txt == "📢 ارسال پیام همگانی":
        ADMIN_STATES[user_id] = "waiting_broadcast"; await send_msg(cid, "✍️ متن پیام:", {"keyboard": [[{"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True})
    elif "پشتیبانی" in txt:
        await send_msg(cid, "📞 **پشتیبانی:**", {"inline_keyboard": [[{"text": "📱 09123692401", "url": "tel:09123692401"}]]})
    else:
        res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
        if not res: await send_msg(cid, "❌ یافت نشد.", kb_main(is_admin))
        else:
            for r in res:
                cap = f"🔍 **نتیجه**\n\n{r['text'][:300]}..."
                photos = json.loads(r["photos"]) if r.get("photos") else []
                await (send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else send_msg(cid, cap, inline_action(r["id"])))
