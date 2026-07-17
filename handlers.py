from property import handle_user_actions
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

# تمام توابع دقیقاً سر جای خود
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
    if not history or history[-1] != state_name:
        history.append(state_name)
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
    set_session(user_id, kind=kind, page=1, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
    push_history(user_id, "main")
    push_history(user_id, "select_khab")
    click_field = "buy_clicks" if kind == "فروش" else "rent_clicks"
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {click_field: 1}}, upsert=True)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())

async def process_bale_webhook(data: dict):
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            if not db["favorites"].find_one({"user_id": cid, "file_id": file_id}):
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else: await send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
        return

    msg = data.get("message") or data.get("edited_message") or data.get("body")
    if not msg: return
    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    first_name = msg.get("from", {}).get("first_name", "کاربر گرامی")

    if ctype == "channel":
        if "photo" in msg and "موجود" in txt:
            photos = [msg["photo"][-1]["file_id"]]
            await save_file(txt, photos)
        return

    if ctype == "private":
        user_id = cid
        register_user(cid, first_name)
        is_admin = (user_id == ADMIN_ID)
        s = get_session(user_id) or {}

        if is_admin:
            admin_state = db["admin_state"].find_one({"_id": cid}) or {}
            if admin_state.get("waiting_broadcast"):
                if txt == "بازگشت به منو اصلی":
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, "عملیات لغو شد.")
                else:
                    success_count = 0
                    for u in db["users"].find({}, {"user_id": 1}):
                        if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"): success_count += 1
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.")
                return
            if txt == "📊 آمار ربات":
                stats = db["stats"].find_one({"_id": "clicks"}) or {}
                await send_msg(cid, f"📊 **آمار:**\n👤 کل کاربران: {db['users'].count_documents({})}\n🏠 کل املاک: {db['files'].count_documents({})}\n🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n🔑 کلیک رهن: {stats.get('rent_clicks', 0)}")
                return
            elif txt == "👥 لیست کاربران":
                users_list = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in db["users"].find({}, {"user_id": 1, "first_name": 1})])
                await send_msg(cid, f"👥 **کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")
                return
            elif txt == "📢 ارسال پیام همگانی":
                db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": True}}, upsert=True)
                await send_msg(cid, "✍️ متن پیام همگانی را بفرستید:")
                return

        # فراخوانی منطقِ جدا شده
        if txt == "🔙 مرحله قبل": await handle_back_step(cid, user_id, is_admin); return
        
        if any(x in txt for x in ["/start", "بازگشت به منو اصلی", "🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره", "💵", "خواب", "مشاهده همه", "متر"]):
            await handle_user_actions(cid, user_id, txt, s, is_admin, set_session, push_history, 
                                      handle_start_flow, parse_budget_text, kb_custom_budget, 
                                      kb_meter, search_files, show_results, kb_main, send_msg)
        
        elif txt == "⭐ علاقه‌مندی‌ها":
            favs = list(db["favorites"].find({"user_id": user_id}))
            if not favs: await send_msg(cid, "لیست علاقه‌مندی‌های شما خالی است.")
            else:
                for f in favs:
                    if r := db["files"].find_one({"id": f["file_id"]}):
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        await send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else await send_msg(cid, r["text"], inline_action(r["id"]))
        elif "پشتیبانی" in txt:
            await send_msg(cid, "📞 **پشتیبانی بروکر**\n\nبا کلیک روی دکمه‌های زیر تماس بگیرید یا پیام دهید:", {
                "inline_keyboard": [
                    [{"text": "📱 09123692401", "url": "tel:09123692401"}, {"text": "📱 09003692401", "url": "tel:09003692401"}],
                    [{"text": "🟢 پیام در بله 💬", "url": "https://ble.ir/sohrabbahador"}]
                ]
            })
        elif "🔍 جستجوی سریع" in txt: await send_msg(cid, "کافیست نام محله یا ویژگی مورد نظرتان را بنویسید و بفرستید:")
        elif "🔔 تنظیم گوش‌به‌زنگ" in txt:
            if s and s.get("kind"):
                db["alerts"].insert_one({"id": get_next_sequence_value("alert_id"), "user_id": user_id, "kind": s.get("kind"), "khab": s.get("khab"), "budje_min": s.get("budje_min"), "budje_max": s.get("budje_max"), "meter_min": s.get("meter_min"), "meter_max": s.get("meter_max")})
                await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد!")
            else: await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید.")
        else:
            if not is_admin:
                res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
                await show_results(cid, res, is_admin)
