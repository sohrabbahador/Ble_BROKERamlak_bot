import json
import re
from core import get_session, set_session, send_msg, send_pic, get_next_sequence_value
from keyboards import kb_main, kb_next, inline_action, kb_khab, kb_custom_budget, kb_meter

# ۱ این تابع متن‌های حاوی مبالغ فارسی یا انگلیسی را به عدد خالص تبدیل می‌کند
def parse_budget_text(text: str) -> int:
    persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(persian_to_english).lower().strip()
    numbers = re.findall(r"\d+\.\d+|\d+", text)
    if not numbers: return 0
    val = float(numbers[0])
    if any(x in text for x in ["میلیارد", "milliard", "b"]): return int(val * 10**9)
    elif any(x in text for x in ["میلیون", "million", "m"]): return int(val * 10**6)
    return int(val * 10**9) if val < 10000 else int(val)

# ۲ این تابع مرحله فعلی کاربر را در سشن ذخیره می‌کند تا قابلیت بازگشت به مرحله قبل فعال شود
def push_history(user_id, state_name):
    s = get_session(user_id) or {}
    history = s.get("history", [])
    if not history or history[-1] != state_name:
        history.append(state_name)
    set_session(user_id, history=history)

# ۳ این تابع لیست املاک پیدا شده در دیتابیس را دریافت کرده و به صورت کارت‌های گرافیکی به کاربر نمایش می‌دهد
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

# ۴ این تابع منطقِ بازگشت به مرحله قبلی در سشن کاربر را مدیریت می‌کند
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

# ۵ این تابع فرآیندِ شروعِ یک جستجوی جدید را با تنظیم سشن و ثبت آمارِ کلیک استارت می‌زند
async def handle_start_flow(cid, user_id, kind):
    set_session(user_id, kind=kind, page=1, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
    push_history(user_id, "main")
    push_history(user_id, "select_khab")
    click_field = "buy_clicks" if kind == "فروش" else "rent_clicks"
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {click_field: 1}}, upsert=True)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())

# ۶ بخش پشتیبانی
async def show_support(cid, send_msg):
    await send_msg(cid, "📞 **پشتیبانی بروکر**\n\nبا کلیک روی دکمه‌های زیر تماس بگیرید یا پیام دهید:", {
        "inline_keyboard": [
            [{"text": "📱 09123692401", "url": "tel:+989123692401"}, {"text": "📱 09003692401", "url": "tel:+989003692401"}],
            [{"text": "🟢 پیام در بله 💬", "url": "https://ble.ir/sohrabbahador"}]
        ]
    })
# ۷ تابع گوش به زنگ 🔔
async def register_alert(cid, user_id, s):
    if s and s.get("kind"):
        db["alerts"].insert_one({
            "id": get_next_sequence_value("alert_id"), 
            "user_id": user_id, 
            "kind": s.get("kind"), 
            "khab": s.get("khab"), 
            "budje_min": s.get("budje_min"), 
            "budje_max": s.get("budje_max"), 
            "meter_min": s.get("meter_min"), 
            "meter_max": s.get("meter_max")
        })
        await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد!")
    else: 
        await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید.")
        
# ۸ این تابع آمار کلی ربات را استخراج می‌کند
async def get_bot_stats():
    stats = db["stats"].find_one({"_id": "clicks"}) or {}
    return (
        f"📊 **آمار:**\n"
        f"👤 کل کاربران: {db['users'].count_documents({})}\n"
        f"🏠 کل املاک: {db['files'].count_documents({})}\n"
        f"🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n"
        f"🔑 کلیک رهن: {stats.get('rent_clicks', 0)}"
    )

# ۹ این تابع لیست کاربران را به صورت فرمت شده برمی‌گرداند
def get_users_list():
    users = list(db["users"].find({}, {"user_id": 1, "first_name": 1}))
    return "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in users])
