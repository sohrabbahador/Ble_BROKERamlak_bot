import json
import re
from config import db
from core import get_next_sequence_value, get_session, send_msg, send_pic, set_session
from keyboards import inline_action, kb_khab, kb_main, kb_budget_2khab, kb_budget_3khab, kb_meter_2khab, kb_meter_3khab

# تعریف دکمه صفحه بعد (جایگزین kb_next که در keyboards نبود)
def kb_next():
    return {"keyboard": [[{"text": "صفحه بعد ➡️"}, {"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True}

# --- متغیر سراسری برای ذخیره کاربران هشدار دیده ---
warned_users = set()

# ۱. تبدیل متن‌های حاوی مبالغ به عدد خالص
def parse_budget_text(text: str) -> int:
    persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(persian_to_english).lower().strip()
    numbers = re.findall(r"\d+\.\d+|\d+", text)
    if not numbers: return 0
    val = float(numbers[0])
    if any(x in text for x in ["میلیارد", "milliard", "b"]): return int(val * 10**9)
    elif any(x in text for x in ["میلیون", "million", "m"]): return int(val * 10**6)
    return int(val * 10**9) if val < 10000 else int(val)

# ۲. مدیریت تاریخچه مراحل در سشن
def push_history(user_id, state_name):
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if not history or history[-1] != state_name: history.append(state_name)
    set_session(user_id, history=history)

# ۳. نمایش لیست املاک پیدا شده
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

# ۴. مدیریت بازگشت به مرحله قبلی
async def handle_back_step(cid, user_id, is_admin):
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if len(history) <= 1:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
        await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
        return

    history.pop()
    prev_state = history[-1] if history else "main"
    set_session(user_id, history=history)

    if prev_state == "main":
        await send_msg(cid, "نوع عملیات مورد نظرتان را انتخاب کنید:", kb_main(is_admin))
    elif prev_state == "select_khab":
        set_session(user_id, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None)
        await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())
    elif prev_state == "select_budget":
        khab = s.get("khab", "۱ خواب")
        kb = kb_budget_2khab() if khab == "۲ خواب" else kb_budget_3khab() if khab == "۳ خواب" else kb_budget_2khab()
        await send_msg(cid, f"تنظیمات بودجه ملک {khab}ه:", kb)
    elif prev_state == "select_meter":
        khab = s.get("khab", "۱ خواب")
        kb_m = kb_meter_2khab() if khab == "۲ خواب" else kb_meter_3khab() if khab == "۳ خواب" else kb_meter_2khab()
        await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_m)

# ۵. شروع جستجوی جدید
async def handle_start_flow(cid, user_id, kind):
    set_session(user_id, kind=kind, page=1, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
    push_history(user_id, "main")
    click_field = "buy_clicks" if kind == "خرید" else "rent_clicks"
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {click_field: 1}}, upsert=True)
    push_history(user_id, "select_khab")
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())

# ۶. نمایش پشتیبانی
async def show_support(cid):
    await send_msg(cid, "📞 **پشتیبانی بروکر**\n\nبا کلیک روی دکمه‌های زیر تماس بگیرید یا پیام دهید:", {
        "inline_keyboard": [
            [{"text": "📱 09123692401", "url": "tel:+989123692401"}, {"text": "📱 09003692401", "url": "tel:+989003692401"}],
            [{"text": "🟢 پیام در بله 💬", "url": "https://ble.ir/sohrabbahador"}]
        ]
    })

# ۷. ثبت در بخش گوش‌به‌زنگ
async def register_alert(cid, user_id, s):
    if s and s.get("kind"):
        db["alerts"].insert_one({
            "id": get_next_sequence_value("alert_id"), "user_id": user_id, "kind": s.get("kind"),
            "khab": s.get("khab"), "budje_min": s.get("budje_min"), "budje_max": s.get("budje_max"),
            "meter_min": s.get("meter_min"), "meter_max": s.get("meter_max"),
        })
        await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد!")
    else:
        await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید.")

# ۸. دریافت آمار کلی ربات
async def get_bot_stats():
    stats = db["stats"].find_one({"_id": "clicks"}) or {}
    return (
        f"📊 **آمار:**\n"
        f"👤 کل کاربران: {db['users'].count_documents({})}\n"
        f"🏠 کل املاک: {db['files'].count_documents({})}\n"
        f"🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n"
        f"🔑 کلیک رهن: {stats.get('rent_clicks', 0)}"
    )

# ۹. دریافت لیست کاربران
def get_users_list():
    users = list(db["users"].find({}, {"user_id": 1, "first_name": 1}))
    return "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in users])

# ۱۰. مدیریت عضویت
async def handle_membership_flow(cid, user_id, is_admin, cb_data, txt, MAIN_CHANNEL_URL, kb_main, is_member_func):
    global warned_users
    if is_admin or await is_member_func(user_id):
        if user_id in warned_users: warned_users.remove(user_id)
        return False

    inline_kb = {"inline_keyboard": [[{"text": "🚀 عضویت در کانال بروکر", "url": MAIN_CHANNEL_URL}], [{"text": "✅ عضو شدم", "callback_data": "check_membership"}]]}
    message = "❌ **هنوز عضو نشدید!**\nلطفاً ابتدا عضو شوید و سپس برگردید." if user_id in warned_users else f"🔔 *برای استفاده از منوی خدمات، لطفاً ابتدا عضو کانال شوید*.\n\n🚀 {MAIN_CHANNEL_URL}\n\n🔄 *پس از عضویت، برگردید و ادامه دهید.*"
    if user_id not in warned_users: warned_users.add(user_id)
    
    await send_msg(cid, message, inline_kb)
    await send_msg(cid, "🔹 لطفاً پس از عضویت، دکمه تایید را بزنید.", kb_main(is_admin))
    return True

# ۱۱. ارسال پیام خوش‌آمدگویی
async def send_welcome_message(cid, name, is_admin, MAIN_CHANNEL_URL, kb_main):
    welcome_text = f"💐 **به خدمات ملکی هوشمند «بروکر املاک» خوش آمدید** 💐\n\n🚀 کانال اصلی:\n{MAIN_CHANNEL_URL}"
    await send_msg(cid, welcome_text, kb_main(is_admin))

# ۱۲. توابع علاقه‌مندی‌ها
async def add_to_favorites(cid, user_id, prop_id):
    await send_msg(cid, "⚠️ بخش علاقه‌مندی‌ها در حال به‌روزرسانی است و به‌زودی در دسترس قرار می‌گیرد.")

async def show_favorites(cid, user_id, is_admin):
    await send_msg(cid, "⚠️ بخش علاقه‌مندی‌ها در حال به‌روزرسانی است و به‌زودی در دسترس قرار می‌گیرد.")

async def remove_from_favorites(cid, user_id, prop_id):
    await send_msg(cid, "⚠️ بخش علاقه‌مندی‌ها در حال به‌روزرسانی است و به‌زودی در دسترس قرار می‌گیرد.")
