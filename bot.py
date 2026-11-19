from flask import Flask, request
import requests
import re
import psycopg
from datetime import datetime, date, timedelta
from typing import Dict, Optional, Tuple, List
import os
import json
from pymongo import MongoClient, ReturnDocument

# ==================== سیستم یادآوری ====================
from reminders import (
    configure as configure_reminders,
    process_reminders_from_fields,
    check_due_reminders,
    get_active_reminders,
    mark_followed_up,
    to_jalali_str,
    days_until,
)

# ==================== تنظیمات ====================
# تمام مقادیر محرمانه و شناسه‌های محیط اجرا از متغیرهای محیطی خوانده می‌شوند.
TOKEN = os.getenv("BALE_BOT_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("متغیر BALE_BOT_TOKEN تنظیم نشده است.")

API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("متغیر DATABASE_URL تنظیم نشده است.")

SOURCE_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID", "4739638593"))
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "4941666224"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "4941666224"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "160513400"))

# اتصال به بانک مرکزی بروکر (همان MongoDB ربات اصلی)
MONGODB_URI = (os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip()
if not MONGODB_URI:
    raise RuntimeError("متغیر MONGODB_URI در Environment تنظیم نشده است.")
mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
central_db = mongo_client["broker_database"]
central_files = central_db["files"]

waiting_for_code = False
manual_add_state = {}
WELCOME_PHOTO_ID = ""  # شناسه‌ی عکس پیام آماده‌ی عضویت دستی (خالی = فقط متن)

# ==================== دستیار هوشمند (فقط مدیر) ====================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
AI_MODE = False
AI_HISTORY = []  # تاریخچه‌ی کوتاه و موقت؛ با Restart پاک می‌شود.
AI_MAX_HISTORY_MESSAGES = 12
AI_SYSTEM_INSTRUCTIONS = (
    "تو دستیار هوشمند فارسی‌زبان مدیر کسب‌وکار املاک هستی. "
    "پاسخ‌ها را کوتاه، دقیق و اجرایی بده. "
    "اطلاعاتی را که در اختیار نداری حدس نزن و برای اقدامات واقعی ادعای انجام‌شدن نکن. "
    "به داده‌های خصوصی مالکان، شماره تماس‌ها یا اطلاعات اعضا دسترسی نداری. "
    "اگر اطلاعات فایل‌های موجود در بخش زمینه گفتگو ارائه شد، فقط بر اساس همان اطلاعات پاسخ بده؛ "
    "اگر فایل مناسبی در داده‌های موجود نیست، صریح بگو اطلاعات کافی پیدا نشد و چیزی نساز."
)

def ask_gemini_admin(user_text: str) -> str:
    """ارسال پیام مدیر به Gemini API با تاریخچه‌ی کوتاه."""
    if not GEMINI_API_KEY:
        return "کلید GEMINI_API_KEY در Environment تنظیم نشده است."
    if not user_text or len(user_text) > 3000:
        return "پیام باید حداکثر ۳۰۰۰ نویسه باشد."

    inventory_context = get_ai_inventory_context()
    instructions = AI_SYSTEM_INSTRUCTIONS
    if inventory_context:
        instructions += "\\n\\nفایل‌های موجود ثبت‌شده در بانک اطلاعاتی ربات (اطلاعات عمومی و بدون شماره تماس):\\n" + inventory_context
    else:
        instructions += "\\n\\nدر حال حاضر اطلاعات فایل ملکی در بانک اطلاعاتی دستیار ثبت نشده است. درباره فایل مشخص ادعای موجودی یا قیمت نکن."

    contents = []
    for item in AI_HISTORY[-AI_MAX_HISTORY_MESSAGES:]:
        role = "model" if item.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": item.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    payload = {
        "systemInstruction": {"parts": [{"text": instructions}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.4}
    }
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=60
        )
        if response.status_code in (401, 403):
            return "کلید Gemini معتبر نیست یا دسترسی API برای آن فعال نیست."
        if response.status_code == 429:
            return "سهمیه رایگان Gemini فعلاً به پایان رسیده یا محدودیت درخواست اعمال شده؛ کمی بعد دوباره امتحان کن."
        if response.status_code >= 400:
            print("Gemini API error:", response.status_code, response.text[:500])
            return "ارتباط با Gemini برقرار نشد؛ مدل و دسترسی API را بررسی کن."
        data = response.json()
        candidates = data.get("candidates", [])
        answer = "\\n".join(
            part.get("text", "")
            for part in (candidates[0].get("content", {}).get("parts", []) if candidates else [])
            if part.get("text")
        ).strip()
        if not answer:
            return "پاسخ خالی از Gemini دریافت شد؛ دوباره امتحان کن."
        AI_HISTORY.extend([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": answer}
        ])
        del AI_HISTORY[:-AI_MAX_HISTORY_MESSAGES]
        return answer
    except requests.Timeout:
        return "پاسخ‌گویی بیش از حد طول کشید؛ دوباره امتحان کن."
    except Exception as exc:
        print("Gemini connection error:", str(exc)[:500])
        return "خطا در اتصال به Gemini؛ گزارش اجرا را بررسی کن."

app = Flask(__name__)

# ------------------ دیتابیس (PostgreSQL) ------------------
def get_db():
    return psycopg.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            username TEXT,
            registered_at TEXT,
            invite_link TEXT,
            link_sent_at TEXT,
            joined_channel INTEGER DEFAULT 0,
            join_date TEXT,
            status TEXT DEFAULT 'registered'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            day TEXT PRIMARY KEY,
            new_joins INTEGER DEFAULT 0,
            new_registers INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS message_map (
            property_code TEXT PRIMARY KEY,
            target_message_id BIGINT NOT NULL,
            has_media INTEGER DEFAULT 0,
            source_message_id BIGINT,
            last_updated TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS manual_members (
            id SERIAL PRIMARY KEY,
            full_name TEXT,
            phone TEXT UNIQUE,
            invite_link TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS property_inventory (
            property_code TEXT PRIMARY KEY,
            fields_json TEXT NOT NULL,
            is_available BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_property_inventory_available ON property_inventory (is_available)")
    conn.commit()
    conn.close()

init_db()

# ------------------ توابع API ------------------
def api(method: str, data: dict = None):
    try:
        r = requests.post(API_URL + method, json=data, timeout=20)
        return r.json()
    except Exception as e:
        print(f"API Error ({method}): {e}")
        return None

def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = reply_markup
    return api("sendMessage", data)

def answer_callback(callback_query_id, text=None, show_alert=False):
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
        data["show_alert"] = show_alert
    return api("answerCallbackQuery", data)

def get_chat_member_status(user_id: int) -> Optional[str]:
    result = api("getChatMember", {
        "chat_id": CHANNEL_ID,
        "user_id": user_id
    })
    if result and result.get("ok"):
        return result["result"].get("status")
    return None

def create_one_time_invite_link(user_id: int) -> Optional[str]:
    expire_date = int((datetime.now() + timedelta(days=3)).timestamp())
    result = api("createChatInviteLink", {
        "chat_id": CHANNEL_ID,
        "name": f"u{user_id}_{int(datetime.now().timestamp())}",
        "member_limit": 1,
        "expire_date": expire_date,
        "creates_join_request": False
    })
    if result and result.get("ok"):
        return result["result"]["invite_link"]
    print("خطا در ساخت لینک:", result)
    return None

def create_manual_invite_link() -> Optional[str]:
    expire_date = int((datetime.now() + timedelta(days=3)).timestamp())
    result = api("createChatInviteLink", {
        "chat_id": CHANNEL_ID,
        "name": f"manual_{int(datetime.now().timestamp())}",
        "member_limit": 1,
        "expire_date": expire_date,
        "creates_join_request": False
    })
    if result and result.get("ok"):
        return result["result"]["invite_link"]
    print("خطا در ساخت لینک دستی:", result)
    return None

def save_manual_member(full_name: str, phone: str, invite_link: str) -> bool:
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO manual_members (full_name, phone, invite_link, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (phone) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                invite_link = EXCLUDED.invite_link,
                created_at = EXCLUDED.created_at
        """, (full_name, phone, invite_link, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("خطا در ذخیره عضو دستی:", e)
        return False

def find_user_by_phone(phone: str):
    try:
        last10 = phone[-10:]
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT user_id, full_name, phone, joined_channel
            FROM users
            WHERE RIGHT(regexp_replace(COALESCE(phone, ''), '\\D', '', 'g'), 10) = %s
            LIMIT 1
        """, (last10,))
        row = c.fetchone()
        conn.close()
        return row
    except Exception as e:
        print("خطا در جستجوی کاربر با شماره:", e)
        return None

def find_manual_member(phone: str):
    try:
        last10 = phone[-10:]
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT full_name, phone
            FROM manual_members
            WHERE RIGHT(regexp_replace(COALESCE(phone, ''), '\\D', '', 'g'), 10) = %s
            LIMIT 1
        """, (last10,))
        row = c.fetchone()
        conn.close()
        return row
    except Exception as e:
        print("خطا در جستجوی عضو دستی با شماره:", e)
        return None

# ------------------ مدیریت mapping بر اساس کد ملک ------------------
def save_message_map(property_code: str, target_msg_id: int, has_media: bool = False, source_msg_id: int = None):
    if not property_code or property_code == "—":
        return
    property_code = property_code.strip()
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""
        INSERT INTO message_map (property_code, target_message_id, has_media, source_message_id, last_updated)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (property_code) DO UPDATE SET
            target_message_id = EXCLUDED.target_message_id,
            has_media = EXCLUDED.has_media,
            source_message_id = EXCLUDED.source_message_id,
            last_updated = EXCLUDED.last_updated
    """, (property_code, target_msg_id, 1 if has_media else 0, source_msg_id, now))
    conn.commit()
    conn.close()

def get_message_map(property_code: str) -> Optional[Tuple[int, bool]]:
    if not property_code or property_code == "—":
        return None
    property_code = property_code.strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT target_message_id, has_media 
        FROM message_map 
        WHERE TRIM(property_code) = %s 
           OR property_code = %s
    """, (property_code, property_code))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], bool(row[1])
    return None

def delete_message_map(property_code: str):
    if not property_code or property_code == "—":
        return
    property_code = property_code.strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM message_map WHERE TRIM(property_code) = %s OR property_code = %s", (property_code, property_code))
    conn.commit()
    conn.close()

# ==================== پردازش فایل‌های ملکی ====================
def parse_fields(text: str) -> Dict[str, str]:
    fields = {}
    if "——— بخش خصوصی" in text:
        text = text.split("——— بخش خصوصی")[0]
    
    pattern = r"^([^:\n]+):\s*(.+)$"
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("———"):
            continue
        match = re.match(pattern, line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            fields[key] = value
    return fields

def build_public_message(fields: Dict[str, str]) -> Optional[str]:
    status = fields.get("وضعیت", "").strip()
    if "موجود" not in status:
        return None
    
    code = fields.get("کد", "—")
    region = fields.get("منطقه", "منطقه ۵تهران")
    location = fields.get("موقعیت", "—")
    metraj = fields.get("متراژ", "—")
    khab = fields.get("تعداد خواب", "—")
    tabaghe = fields.get("طبقه", "—")
    tedad_tabaghe = fields.get("تعداد طبقه", "—")
    tedad_vahed = fields.get("تعداد واحد در هر طبقه", "—")
    
    amenities = []
    for key, name in [("آسانسور", "آسانسور"), ("پارکینگ", "پارکینگ"),
                      ("انباری", "انباری"), ("تراس", "تراس")]:
        val = fields.get(key, "")
        if "✅" in val or "دارد" in val:
            amenities.append(f"✅{name}")
    amenities_str = "".join(amenities)
    
    rahn = fields.get("رهن کامل", "—")
    tabdil = fields.get("قابلیت تبدیل", "—")
    tozihat = fields.get("توضیحات", "—")
    tel1 = fields.get("تلفن1", "09123692401")
    tel2 = fields.get("تلفن2", "09003692401")
    
    msg = f"""#رهن_اجاره «{region}»
کد {code}

📍موقعیت: *{location}*

📋 *مشخصات ملک*؛
📏 متراژ: * {metraj} متر | {khab} خواب *
🏢 طبقه:* {tabaghe} (ساختمان {tedad_tabaghe} طبقه)*
👥 تعداد واحد: *{tedad_vahed} واحد در هر طبقه*
{amenities_str}

💰 شرایط :
  🟢رهن کامل ؛* {rahn}*
🔄 قابلیت تبدیل: *{tabdil}*

🌟 *توضیحات*:[{tozihat}]

 وضعیت: ✅* موجود* است 

📞 *مشاهده تصاویر بیشتر ، اطلاعات تکمیلی و بازدید*
📱 {tel1}
📱 {tel2}

⚖️ *صفحه خرید و فروش و اطلاعات ملکی:*👇
🆔 *@BROKER_amlak*
"""
    return msg.strip()

def process_message(message: dict, is_edit: bool = False):
    chat = message.get("chat", {})
    if chat.get("id") != SOURCE_CHAT_ID:
        return
    
    text = message.get("text") or message.get("caption") or ""
    if not text:
        return
    
    source_msg_id = message.get("message_id")
    fields = parse_fields(text)
    property_code = fields.get("کد", "—").strip()
    public_text = build_public_message(fields)
    photos = message.get("photo")
    save_property_inventory(fields, is_available=(public_text is not None), photos=photos, source_message_id=source_msg_id)
    has_photo = bool(photos)

    if not property_code or property_code == "—":
        print("کد ملک یافت نشد، پیام نادیده گرفته شد")
        return

    # ========== سیستم یادآوری ==========
    process_reminders_from_fields(fields, property_code, source_msg_id, full_text=text)

    mapped = get_message_map(property_code)

    if public_text is None:
        if mapped:
            target_msg_id, _ = mapped
            result = api("deleteMessage", {
                "chat_id": TARGET_CHAT_ID,
                "message_id": target_msg_id
            })
            print(f"پیام کد {property_code} حذف شد (دیگر موجود نیست):", result)
            delete_message_map(property_code)
        return

    if mapped:
        target_msg_id, was_media = mapped
        print(f"پیام قبلی برای کد {property_code} پیدا شد → در حال ویرایش...")

        success = False

        if was_media or has_photo:
            result = api("editMessageCaption", {
                "chat_id": TARGET_CHAT_ID,
                "message_id": target_msg_id,
                "caption": public_text,
                "parse_mode": "Markdown"
            })
            if result and result.get("ok"):
                print(f"✅ کپشن کد {property_code} ویرایش شد")
                save_message_map(property_code, target_msg_id, has_media=True, source_msg_id=source_msg_id)
                save_inventory_display_reference(property_code, target_msg_id)
                success = True
            else:
                if has_photo:
                    photo = max(photos, key=lambda p: p.get("file_size", 0))
                    media = {
                        "type": "photo",
                        "media": photo["file_id"],
                        "caption": public_text,
                        "parse_mode": "Markdown"
                    }
                    result = api("editMessageMedia", {
                        "chat_id": TARGET_CHAT_ID,
                        "message_id": target_msg_id,
                        "media": media
                    })
                    if result and result.get("ok"):
                        print(f"✅ مدیا کد {property_code} ویرایش شد")
                        save_message_map(property_code, target_msg_id, has_media=True, source_msg_id=source_msg_id)
                        save_inventory_display_reference(property_code, target_msg_id)
                        success = True
        else:
            result = api("editMessageText", {
                "chat_id": TARGET_CHAT_ID,
                "message_id": target_msg_id,
                "text": public_text,
                "parse_mode": "Markdown"
            })
            if result and result.get("ok"):
                print(f"✅ متن کد {property_code} ویرایش شد")
                save_message_map(property_code, target_msg_id, has_media=False, source_msg_id=source_msg_id)
                save_inventory_display_reference(property_code, target_msg_id)
                success = True

        if success:
            return

        print(f"⚠️ ویرایش کد {property_code} شکست خورد، حذف و ارسال مجدد...")
        api("deleteMessage", {"chat_id": TARGET_CHAT_ID, "message_id": target_msg_id})
        delete_message_map(property_code)

    print(f"ارسال پیام جدید برای کد {property_code}")

    if has_photo:
        photo = max(photos, key=lambda p: p.get("file_size", 0))
        result = api("sendPhoto", {
            "chat_id": TARGET_CHAT_ID,
            "photo": photo["file_id"],
            "caption": public_text,
            "parse_mode": "Markdown"
        })
        print("نتیجه عکس:", result)
        if result and result.get("ok"):
            target_msg_id = result["result"]["message_id"]
            save_message_map(property_code, target_msg_id, has_media=True, source_msg_id=source_msg_id)
            save_inventory_display_reference(property_code, target_msg_id)
    else:
        result = api("sendMessage", {
            "chat_id": TARGET_CHAT_ID,
            "text": public_text,
            "parse_mode": "Markdown"
        })
        print("نتیجه متن:", result)
        if result and result.get("ok"):
            target_msg_id = result["result"]["message_id"]
            save_message_map(property_code, target_msg_id, has_media=False, source_msg_id=source_msg_id)
            save_inventory_display_reference(property_code, target_msg_id)

# ==================== مدیریت کاربران و آمار ====================
def save_or_update_user(user_id: int, full_name: str = None, phone: str = None,
                        username: str = None, invite_link: str = None,
                        status: str = None, joined: bool = False):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    today = date.today().isoformat()

    c.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
    exists = c.fetchone()

    if not exists:
        c.execute("""
            INSERT INTO users (user_id, full_name, phone, username, registered_at, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, full_name or "", phone or "", username, now, status or "registered"))
        c.execute("""
            INSERT INTO daily_stats (day, new_joins, new_registers)
            VALUES (%s, 0, 0)
            ON CONFLICT (day) DO NOTHING
        """, (today,))
        c.execute("UPDATE daily_stats SET new_registers = new_registers + 1 WHERE day = %s", (today,))
    else:
        updates = []
        params = []
        if full_name is not None:
            updates.append("full_name = %s")
            params.append(full_name)
        if phone is not None:
            updates.append("phone = %s")
            params.append(phone)
        if username is not None:
            updates.append("username = %s")
            params.append(username)
        if invite_link is not None:
            updates.append("invite_link = %s")
            params.append(invite_link)
            updates.append("link_sent_at = %s")
            params.append(now)
        if status is not None:
            updates.append("status = %s")
            params.append(status)
        if joined:
            updates.append("joined_channel = 1")
            updates.append("join_date = %s")
            params.append(today)
            updates.append("status = 'joined'")

        if updates:
            params.append(user_id)
            c.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s", params)

    conn.commit()
    conn.close()

def mark_joined(user_id: int):
    conn = get_db()
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute("SELECT joined_channel FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()
    already_joined = row and row[0] == 1

    c.execute("""
        UPDATE users 
        SET joined_channel = 1, join_date = %s, status = 'joined' 
        WHERE user_id = %s
    """, (today, user_id))

    if not already_joined:
        c.execute("""
            INSERT INTO daily_stats (day, new_joins, new_registers)
            VALUES (%s, 0, 0)
            ON CONFLICT (day) DO NOTHING
        """, (today,))
        c.execute("UPDATE daily_stats SET new_joins = new_joins + 1 WHERE day = %s", (today,))

    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    keys = ["user_id", "full_name", "phone", "username", "registered_at",
            "invite_link", "link_sent_at", "joined_channel", "join_date", "status"]
    return dict(zip(keys, row))

def get_pending_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT user_id, full_name, phone, username, registered_at
        FROM users
        WHERE status = 'pending' AND (joined_channel = 0 OR joined_channel IS NULL)
        ORDER BY registered_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def get_link_sent_not_joined():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT user_id, full_name, phone, username, link_sent_at
        FROM users
        WHERE status = 'link_sent' AND (joined_channel = 0 OR joined_channel IS NULL)
        ORDER BY link_sent_at DESC NULLS LAST
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = get_db()
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute("SELECT COUNT(*) FROM users")
    total_registered = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE joined_channel = 1")
    total_joined = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE status = 'pending' AND (joined_channel = 0 OR joined_channel IS NULL)")
    pending = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE status = 'link_sent' AND (joined_channel = 0 OR joined_channel IS NULL)")
    link_sent_not_joined = c.fetchone()[0]

    c.execute("SELECT new_joins, new_registers FROM daily_stats WHERE day = %s", (today,))
    row = c.fetchone()
    today_joins = row[0] if row else 0
    today_registers = row[1] if row else 0

    c.execute("""
        SELECT full_name, phone, username, join_date
        FROM users WHERE joined_channel = 1
        ORDER BY join_date DESC LIMIT 8
    """)
    recent_joins = c.fetchall()

    conn.close()
    return {
        "total_registered": total_registered,
        "total_joined": total_joined,
        "pending": pending,
        "link_sent_not_joined": link_sent_not_joined,
        "today_joins": today_joins,
        "today_registers": today_registers,
        "recent_joins": recent_joins
    }

def get_available_files():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT TRIM(property_code) FROM message_map ORDER BY 1")
    rows = c.fetchall()
    conn.close()
    codes = [r[0] for r in rows if r[0]]
    return len(codes), codes


def _fa_digits_to_en(value):
    return str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _public_ai_text(value):
    """حذف خطوط تماس و شماره موبایل پیش از ارسال متن فایل به مدل."""
    lines = []
    for line in str(value or "").splitlines():
        if re.search(r"(تلفن|موبایل|شماره\s*تماس|تماس\s*با|نام\s*مالک|آدرس\s*دقیق)", line, re.I):
            continue
        line = re.sub(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)", "[شماره حذف شد]", line)
        line = re.sub(r"(?<!\d)0\d{10}(?!\d)", "[شماره حذف شد]", line)
        lines.append(line)
    return "\n".join(lines).strip()


def save_property_inventory(fields: Dict[str, str], is_available: bool = True, photos=None, source_message_id=None):
    """همگام‌سازی فایل اجاره با مجموعه مرکزی broker_database.files."""
    code = (fields.get("کد") or "").strip()
    if not code or code == "—":
        return

    public_text = build_public_message(fields) if is_available else None

    # فقط رکورد متعلق به همین ربات اجاره تغییر می‌کند.
    own_filter = {"source": "rent_bale", "property_code": code}
    if not is_available or not public_text:
        central_files.update_many(
            own_filter,
            {"$set": {"is_available": False, "updated_at": datetime.utcnow()}}
        )
        return

    private_keys = {
        "تلفن", "تلفن1", "تلفن2", "شماره تماس", "موبایل",
        "شماره موبایل", "شماره مالک", "نام مالک",
        "نام و نام خانوادگی مالک", "آدرس دقیق"
    }
    public_fields = {
        str(k).strip(): str(v).strip()
        for k, v in fields.items()
        if str(k).strip() not in private_keys and str(v).strip()
    }

    def number_from(value):
        digits = re.findall(r"\d+", _fa_digits_to_en(value))
        return int(digits[0]) if digits else None

    khab = fields.get("تعداد خواب") or fields.get("خواب")
    meter = number_from(fields.get("متراژ"))
    price = number_from(fields.get("رهن کامل") or fields.get("ودیعه") or fields.get("قیمت"))
    location = fields.get("موقعیت") or fields.get("منطقه") or "نامشخص"
    photo_ids = [
        item["file_id"] for item in (photos or [])
        if isinstance(item, dict) and item.get("file_id")
    ]

    document = {
        "property_code": code,
        "text": public_text,
        "kind": "رهن_اجاره",
        "khab": khab,
        "price": price,
        "meter": meter,
        "location": location,
        "photos": json.dumps(photo_ids, ensure_ascii=False),
        "public_fields": public_fields,
        "source": "rent_bale",
        "source_chat_id": SOURCE_CHAT_ID,
        "source_message_id": source_message_id,
        "is_available": True,
        "updated_at": datetime.utcnow()
    }

    existing = central_files.find_one(own_filter, {"_id": 1, "id": 1})
    if existing:
        central_files.update_one({"_id": existing["_id"]}, {"$set": document})
    else:
        counter = central_db["counters"].find_one_and_update(
            {"_id": "file_id"},
            {"$inc": {"sequence_value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        document["id"] = counter.get("sequence_value", 1)
        central_files.insert_one(document)


def save_inventory_display_reference(property_code: str, display_message_id: int):
    """ثبت شناسه پیام منتشرشده؛ فقط برای رکوردهای همین ربات اجاره."""
    if not property_code or not display_message_id:
        return
    central_files.update_one(
        {"source": "rent_bale", "property_code": str(property_code).strip()},
        {"$set": {
            "display_chat_id": TARGET_CHAT_ID,
            "display_message_id": display_message_id,
            "updated_at": datetime.utcnow()
        }}
    )


def get_ai_inventory_context(limit: int = 35) -> str:
    """خواندن فایل‌های فعال از بانک مرکزی؛ شماره‌ها و اطلاعات خصوصی حذف می‌شوند."""
    rows = list(
        central_files.find(
            {
                "is_available": {"$ne": False},
                "$or": [{"source": "rent_bale"}, {"kind": "رهن_اجاره"}]
            },
            {"_id": 0, "id": 1, "property_code": 1, "text": 1,
             "kind": 1, "khab": 1, "price": 1, "meter": 1,
             "location": 1, "public_fields": 1}
        ).sort("id", -1).limit(limit)
    )
    chunks = []
    for item in rows:
        code = item.get("property_code") or ""
        public_fields = item.get("public_fields") or {}
        if public_fields:
            summary = " | ".join(
                f"{k}: {v}" for k, v in public_fields.items()
                if not re.search(r"(تلفن|موبایل|شماره|مالک|آدرس\s*دقیق)", str(k), re.I)
            )
        else:
            summary = " | ".join(
                f"{k}: {item.get(k)}" for k in ("kind", "khab", "price", "meter", "location")
                if item.get(k) not in (None, "")
            )
            summary += " | " + _public_ai_text(item.get("text", ""))
        chunks.append(f"کد {code or item.get('id', '—')}: {summary}")
    return "\n".join(chunks)[:14000]

def process_send_link(target_id: int, admin_chat_id: int = ADMIN_ID) -> str:
    user_data = get_user(target_id)
    if not user_data:
        return "❌ کاربری با این آیدی یافت نشد."

    if user_data.get("joined_channel") == 1:
        return "⚠️ این کاربر قبلاً عضو کانال شده است."

    current_status = get_chat_member_status(target_id)
    if current_status in ["member", "administrator", "creator"]:
        mark_joined(target_id)
        return "⚠️ این کاربر هم‌اکنون عضو کانال است. وضعیت به‌روز شد."

    invite_link = create_one_time_invite_link(target_id)
    if not invite_link:
        return "❌ خطا در ساخت لینک. دوباره تلاش کنید."

    save_or_update_user(target_id, invite_link=invite_link, status="link_sent")

    send_message(target_id,
        f"✅ درخواست شما تأیید شد.\n\n"
        f"🔗 *لینک عضویت یک‌بارمصرف شما*:\n"
        f"{invite_link}\n\n"
        f"⚠️ این لینک فقط یک بار قابل استفاده است و تا ۳ روز اعتبار دارد.\n"
        f"بعد از عضویت، لینک باطل می‌شود."
    )

    return (
        f"✅ لینک یک‌بارمصرف ارسال شد\n"
        f"نام: {user_data['full_name']}\n"
        f"شماره: {user_data['phone']}\n"
        f"آیدی: {target_id}"
    )

# ==================== وب‌هوک ====================
@app.route("/", methods=["GET"])
def home():
    return "ربات فعال است ✅", 200


@app.route("/check_reminders", methods=["GET", "POST"])
def check_reminders_endpoint():
    due = check_due_reminders()
    return {
        "ok": True,
        "checked_at": datetime.now().isoformat(),
        "sent_count": len(due),
        "items": [i["property_code"] for i in due]
    }, 200


@app.route("/webhook", methods=["POST"])
def webhook():
    global waiting_for_code, AI_MODE
    update = request.get_json()
    if not update:
        return "ok", 200

    if "callback_query" in update:
        cq = update["callback_query"]
        cq_id = cq.get("id")
        from_user = cq.get("from", {})
        data = cq.get("data", "")
        admin_id = from_user.get("id")

        if admin_id != ADMIN_ID:
            answer_callback(cq_id, "شما دسترسی ندارید.", show_alert=True)
            return "ok", 200

        if data.startswith("sendlink_"):
            try:
                target_id = int(data.split("_")[1])
            except:
                answer_callback(cq_id, "خطا در شناسایی کاربر", show_alert=True)
                return "ok", 200

            result_msg = process_send_link(target_id)
            answer_callback(cq_id, "انجام شد ✅")
            send_message(ADMIN_ID, result_msg)

            try:
                api("editMessageReplyMarkup", {
                    "chat_id": cq["message"]["chat"]["id"],
                    "message_id": cq["message"]["message_id"],
                    "reply_markup": {"inline_keyboard": []}
                })
            except:
                pass

        if data.startswith("done_reminder_"):
            try:
                reminder_id = int(data.split("_")[2])
                success = mark_followed_up(reminder_id)
                if success:
                    answer_callback(cq_id, "✅ پیگیری شد و حذف گردید")
                    try:
                        api("editMessageReplyMarkup", {
                            "chat_id": cq["message"]["chat"]["id"],
                            "message_id": cq["message"]["message_id"],
                            "reply_markup": {"inline_keyboard": []}
                        })
                    except Exception:
                        pass
                else:
                    answer_callback(cq_id, "خطا در ثبت", show_alert=True)
            except Exception as e:
                print("Error done_reminder:", e)
                answer_callback(cq_id, "خطا", show_alert=True)
            return "ok", 200

        return "ok", 200

    if "chat_member" in update:
        cm = update["chat_member"]
        new_status = cm.get("new_chat_member", {}).get("status")
        old_status = cm.get("old_chat_member", {}).get("status")
        user = cm.get("new_chat_member", {}).get("user", {})
        user_id = user.get("id")

        if new_status == "member" and old_status in ["left", "kicked", "restricted", None]:
            user_data = get_user(user_id)
            if user_data and user_data.get("joined_channel") != 1:
                mark_joined(user_id)
                name = f"{user.get('first_name', '')} {user.get('last_name') or ''}".strip()
                send_message(ADMIN_ID,
                    f"✅ *عضویت نهایی ثبت شد*\n"
                    f"نام: {name}\n"
                    f"آیدی: {user_id}\n"
                    f"یوزرنیم: @{user.get('username') or 'ندارد'}"
                )

        if new_status in ["left", "kicked"] and old_status in ["member", "administrator", "restricted"]:
            conn = get_db()
            c = conn.cursor()
            c.execute("""
                UPDATE users 
                SET joined_channel = 0, status = 'pending'
                WHERE user_id = %s
            """, (user_id,))
            conn.commit()
            conn.close()

        return "ok", 200

    # دریافت پیام‌های کانال فایلینگ و ویرایش آن‌ها نیز فعال است.
    is_edit = any(key in update for key in ("edited_message", "edited_channel_post"))
    message = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
    )
    if not message:
        return "ok", 200

    chat = message.get("chat", {})
    chat_type = chat.get("type")
    user = message.get("from", {})
    user_id = user.get("id")
    text = (message.get("text") or "").strip()
    contact = message.get("contact")

    if chat_type == "private" and user_id == ADMIN_ID:

        admin_keyboard = {
            "keyboard": [
                [{"text": "📊 آمار کامل"}, {"text": "⏳ در انتظار تأیید"}],
                [{"text": "🔔 یادآوری"}, {"text": "📅 پایان اجاره‌نامه"}],
                [{"text": "📁 فایل‌های موجود"}, {"text": "🔍 جستجوی کد"}],
                [{"text": "🤖 دستیار هوشمند"}],
                [{"text": "➕ افزودن دستی عضو"}],
            ],
            "resize_keyboard": True
        }

        if text in ["🤖 دستیار هوشمند", "/ai"]:
            if not GEMINI_API_KEY:
                send_message(ADMIN_ID, "کلید GEMINI_API_KEY در Environment تنظیم نشده است.", reply_markup=admin_keyboard)
                return "ok", 200
            AI_MODE = True
            send_message(
                ADMIN_ID,
                "🤖 دستیار هوشمند فعال شد. پیام خودت را بفرست. برای خروج /ai_off را بزن.",
                reply_markup=admin_keyboard
            )
            return "ok", 200

        if text in ["/ai_off", "⏹ خروج از دستیار"]:
            AI_MODE = False
            AI_HISTORY.clear()
            send_message(ADMIN_ID, "حالت دستیار خاموش شد و تاریخچه‌ی موقت پاک شد.", reply_markup=admin_keyboard)
            return "ok", 200

        if text.startswith("/") or text in [
            "📊 آمار کامل", "⏳ در انتظار تأیید", "🔔 یادآوری",
            "📅 پایان اجاره‌نامه", "📁 فایل‌های موجود", "🔍 جستجوی کد"
        ]:
            manual_add_state.clear()

        if text in ["/start"]:
            send_message(ADMIN_ID,
                "سلام ادمین 👋\nاز دکمه‌های زیر استفاده کنید:",
                reply_markup=admin_keyboard
            )
            return "ok", 200

        admin_photos = message.get("photo")
        if admin_photos:
            best_photo = max(admin_photos, key=lambda p: p.get("file_size", 0))
            send_message(ADMIN_ID,
                f"🖼 شناسه‌ی این عکس:\n\n{best_photo['file_id']}",
                reply_markup=admin_keyboard,
                parse_mode=None
            )
            return "ok", 200

        if text == "📊 آمار کامل" or text == "/stats":
            s = get_stats()
            msg = (
                f"📊 *آمار حرفه‌ای ربات*\n\n"
                f"📅 امروز:\n"
                f"• ثبت‌نام جدید: *{s['today_registers']}*\n"
                f"• عضویت نهایی: *{s['today_joins']}*\n\n"
                f"📈 کلی:\n"
                f"• کل ثبت‌نام‌شده‌ها: *{s['total_registered']}*\n"
                f"• کل اعضای کانال (از طریق ربات): *{s['total_joined']}*\n"
                f"• در انتظار تأیید لینک: *{s['pending']}*\n"
                f"• لینک گرفته ولی هنوز عضو نشده: *{s['link_sent_not_joined']}*\n\n"
                f"🆕 آخرین عضویت‌ها:\n"
            )
            for r in s["recent_joins"]:
                msg += f"• {r[0]} | {r[1]} | @{r[2] or '—'}\n"

            link_users = get_link_sent_not_joined()
            if link_users:
                msg += f"\n📌 *لینک گرفته ولی هنوز عضو نشده‌اند ({len(link_users)} نفر):*\n"
                for u in link_users:
                    msg += f"• {u[1]} | {u[2]} | {u[0]}\n"

            send_message(ADMIN_ID, msg, reply_markup=admin_keyboard)

            for u in link_users:
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "🔄 ارسال مجدد لینک", "callback_data": f"sendlink_{u[0]}"}
                    ]]
                }
                send_message(ADMIN_ID,
                    f"👤 {u[1]}\n📱 {u[2]}\n🆔 {u[0]}",
                    reply_markup=keyboard
                )

            return "ok", 200

        if text == "⏳ در انتظار تأیید" or text == "/pending":
            pending = get_pending_users()
            if not pending:
                send_message(ADMIN_ID, "✅ هیچ کاربری در انتظار تأیید لینک نیست.", reply_markup=admin_keyboard)
                return "ok", 200

            for p in pending:
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "✅ ارسال لینک یک‌بارمصرف", "callback_data": f"sendlink_{p[0]}"}
                    ]]
                }
                msg = (
                    f"👤 {p[1]}\n"
                    f"📱 {p[2]}\n"
                    f"🆔 {p[0]}\n"
                    f"یوزرنیم: @{p[3] or 'ندارد'}"
                )
                send_message(ADMIN_ID, msg, reply_markup=keyboard)
            return "ok", 200

        if text == "🔔 یادآوری" or text == "/reminders":
            rows = get_active_reminders(limit=30, reminder_type="manual")
            if not rows:
                send_message(ADMIN_ID, "هیچ یادآوری فعالی ثبت نشده است.", reply_markup=admin_keyboard)
                return "ok", 200

            msg = f"🔔 *یادآوری‌ها*\n\nتعداد: *{len(rows)}*\n\n"
            for r in rows:
                status = "✅ ارسال‌شده" if r["notified"] else "⏳ در انتظار"
                if r.get("followed_up"):
                    status = "✔️ پیگیری‌شده"

                time_str = to_jalali_str(r["reminder_at"]) if r.get("reminder_at") else "—"
                owner = r.get("owner_name") or "—"
                text_preview = (r.get("reminder_text") or "—")[:60]
                if len(r.get("reminder_text") or "") > 60:
                    text_preview += "…"

                remain = days_until(r.get("reminder_at"))
                if remain is None:
                    remain_str = ""
                elif remain > 0:
                    remain_str = f" ({remain} روز مانده)"
                    if remain < 3:
                        remain_str = f" 🔴 ({remain} روز مانده)"
                elif remain == 0:
                    remain_str = " 🔴 (امروز)"
                else:
                    remain_str = " (گذشته)"

                msg += (
                    f"• {r['property_code']}\n"
                    f"  مالک: *{owner}*\n"
                    f"  {text_preview}\n"
                    f"  تاریخ اعلام: {time_str}{remain_str}\n"
                    f"  وضعیت: {status}\n\n"
                )
            send_message(ADMIN_ID, msg, reply_markup=admin_keyboard)
            return "ok", 200

        if text == "📅 پایان اجاره‌نامه":
            rows = get_active_reminders(limit=30, reminder_type="lease_end_35d")
            if not rows:
                send_message(ADMIN_ID, "هیچ یادآوری پایان اجاره‌نامه‌ای ثبت نشده است.", reply_markup=admin_keyboard)
                return "ok", 200

            msg = f"📅 *پایان اجاره‌نامه*\n\nتعداد: *{len(rows)}*\n\n"
            for r in rows:
                status = "✅ ارسال‌شده" if r["notified"] else "⏳ در انتظار"
                if r.get("followed_up"):
                    status = "✔️ پیگیری‌شده"

                time_str = to_jalali_str(r["reminder_at"]) if r.get("reminder_at") else "—"
                owner = r.get("owner_name") or "—"

                lease_end_display = "—"
                rt = r.get("reminder_text") or ""
                if "(" in rt and ")" in rt:
                    lease_end_display = rt.split("(")[-1].rstrip(")")

                remain = days_until(r.get("reminder_at"))
                if remain is None:
                    remain_str = ""
                elif remain > 0:
                    remain_str = f" ({remain} روز مانده)"
                    if remain < 3:
                        remain_str = f" 🔴 ({remain} روز مانده)"
                elif remain == 0:
                    remain_str = " 🔴 (امروز)"
                else:
                    remain_str = " (گذشته)"

                msg += (
                    f"• {r['property_code']} — *{owner}*\n"
                    f"  پایان اجاره: {lease_end_display}\n"
                    f"  اعلام: {time_str}{remain_str}\n"
                    f"  وضعیت: {status}\n\n"
                )
            send_message(ADMIN_ID, msg, reply_markup=admin_keyboard)
            return "ok", 200

        if text == "📁 فایل‌های موجود":
            count, codes = get_available_files()
            if count == 0:
                msg = "هیچ فایل موجودی ثبت نشده است."
            else:
                msg = f"📊 *فایل‌های موجود*\n\nتعداد: *{count}*\n\nکدها:\n"
                for code in codes:
                    msg += f"• {code}\n"
            send_message(ADMIN_ID, msg, reply_markup=admin_keyboard)
            return "ok", 200

        if text == "🔍 جستجوی کد":
            waiting_for_code = True
            send_message(ADMIN_ID,
                "کد ملک را فقط به صورت عدد ارسال کنید:\nمثال: 137",
                reply_markup=admin_keyboard
            )
            return "ok", 200

        if text == "➕ افزودن دستی عضو":
            waiting_for_code = False
            manual_add_state.clear()
            manual_add_state["step"] = "name"
            send_message(ADMIN_ID,
                "👤 نام و نام خانوادگی فرد را وارد کنید:\n(برای انصراف یکی از دکمه‌های منو را بزنید)",
                reply_markup=admin_keyboard
            )
            return "ok", 200

        if manual_add_state.get("step") == "name" and text:
            manual_add_state["name"] = text
            manual_add_state["step"] = "phone"
            send_message(ADMIN_ID, "📱 شماره تماس را وارد کنید:", reply_markup=admin_keyboard)
            return "ok", 200

        if manual_add_state.get("step") == "phone" and text:
            phone = text.translate(
                str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
            ).replace(" ", "")
            if not phone.isdigit() or not (10 <= len(phone) <= 13):
                send_message(ADMIN_ID,
                    "❌ شماره معتبر نیست. فقط عدد وارد کنید (مثال: 09123456789):",
                    reply_markup=admin_keyboard
                )
                return "ok", 200

            name = manual_add_state.get("name")
            manual_add_state.clear()

            # بررسی اینکه این شماره قبلاً در ربات ثبت شده یا عضو کانال است
            existing = find_user_by_phone(phone)
            if existing:
                ex_id, ex_name, ex_phone, ex_joined = existing
                live_status = get_chat_member_status(ex_id)
                if live_status in ["member", "administrator", "creator"]:
                    if ex_joined != 1:
                        mark_joined(ex_id)
                    send_message(ADMIN_ID,
                        f"⚠️ این فرد قبلاً عضو کانال است.\n\n"
                        f"👤 {ex_name}\n"
                        f"📱 {ex_phone}\n\n"
                        f"لینک جدید ساخته نشد.",
                        reply_markup=admin_keyboard,
                        parse_mode=None
                    )
                    return "ok", 200

                send_message(ADMIN_ID,
                    f"ℹ️ این فرد قبلاً در ربات ثبت‌نام کرده ولی هنوز عضو کانال نیست.\n\n"
                    f"👤 {ex_name}\n"
                    f"📱 {ex_phone}\n\n"
                    f"برای ارسال لینک مستقیم به خودش، دکمه‌ی زیر را بزنید 👇",
                    reply_markup={
                        "inline_keyboard": [[
                            {"text": "✅ ارسال لینک یک‌بارمصرف", "callback_data": f"sendlink_{ex_id}"}
                        ]]
                    },
                    parse_mode=None
                )
                return "ok", 200

            prev_manual = find_manual_member(phone)
            prev_note = ""
            if prev_manual:
                prev_note = "\n⚠️ قبلاً هم برای این شماره لینک ساخته شده بود (ممکن است عضو شده باشد)."

            invite_link = create_manual_invite_link()
            if not invite_link:
                send_message(ADMIN_ID, "❌ خطا در ساخت لینک. دوباره تلاش کنید.", reply_markup=admin_keyboard)
                return "ok", 200

            saved = save_manual_member(name, phone, invite_link)
            save_note = "💾 اطلاعات ذخیره شد" if saved else "⚠️ ذخیره‌ی اطلاعات در دیتابیس ناموفق بود"

            send_message(ADMIN_ID,
                f"✅ لینک عضویت یک‌بارمصرف ساخته شد\n\n"
                f"👤 نام: {name}\n"
                f"📱 شماره: {phone}\n"
                f"{save_note}{prev_note}\n\n"
                f"👇 پیام زیر را برای همین فرد فوروارد کنید",
                reply_markup=admin_keyboard,
                parse_mode=None
            )

            welcome_text = (
                f"سلام {name} عزیز 🌹\n\n"
                f"من دستیار سهراب بهادر «بروکر املاک» هستم.\n"
                f"صفحه اختصاصی رهن و اجاره آپارتمان‌های منطقه ۵ تهران\n"
                f"✨ فایل‌های واقعی با مشخصات دقیق ✨\n\n"
                f"برای عضویت روی لینک زیر بزنید 👇\n"
                f"🔗 {invite_link}\n\n"
                f"⚠️ لینک اختصاصی و یک‌بارمصرف است (۳ روز اعتبار).\n\n"
                f"📞 09123692401\n"
                f"📞 09003692401\n"
                f"🌐 https://www.BROKER-amlak.ir"
            )

            photo_sent = False
            if WELCOME_PHOTO_ID:
                photo_result = api("sendPhoto", {
                    "chat_id": ADMIN_ID,
                    "photo": WELCOME_PHOTO_ID,
                    "caption": welcome_text
                })
                photo_sent = bool(photo_result and photo_result.get("ok"))

            if not photo_sent:
                send_message(ADMIN_ID, welcome_text, parse_mode=None)
            return "ok", 200

        if waiting_for_code and text.isdigit():
            waiting_for_code = False
            code = text.strip()

            mapped = get_message_map(code)
            exists = "✅ موجود" if mapped else "❌ موجود نیست"

            rows = get_active_reminders(limit=20)
            related = [r for r in rows if str(r["property_code"]).strip() == code]

            msg = f"🔍 *جستجوی کد {code}*\n\nوضعیت فایل: {exists}\n"
            if related:
                msg += "\nیادآوری‌های مرتبط:\n"
                for r in related:
                    rtype = "۳۵روزه" if r["reminder_type"] == "lease_end_35d" else "یادآوری"
                    time_str = to_jalali_str(r["reminder_at"]) if r.get("reminder_at") else "—"
                    msg += f"• {rtype} → {time_str}\n"
            else:
                msg += "\nهیچ یادآوری مرتبطی یافت نشد."

            send_message(ADMIN_ID, msg, reply_markup=admin_keyboard)
            return "ok", 200

        if text.startswith("/sendlink "):
            try:
                target_id = int(text.split()[1])
            except:
                send_message(ADMIN_ID, "❌ فرمت اشتباه است.\nمثال:\n/sendlink 123456789", reply_markup=admin_keyboard)
                return "ok", 200

            result_msg = process_send_link(target_id)
            send_message(ADMIN_ID, result_msg, reply_markup=admin_keyboard)
            return "ok", 200

        # پیام آزاد مدیر در حالت دستیار هوشمند؛ فرمان‌ها و فرم‌های قبلی اولویت دارند.
        if AI_MODE and text and not text.startswith("/") and not manual_add_state.get("step") and not waiting_for_code:
            send_message(ADMIN_ID, "⏳ دارم پاسخ را آماده می‌کنم...")
            ai_answer = ask_gemini_admin(text)
            send_message(ADMIN_ID, ai_answer, reply_markup=admin_keyboard, parse_mode=None)
            return "ok", 200

        if text.startswith("/"):
            send_message(ADMIN_ID,
                "دستورات ادمین:\n"
                "/stats → آمار کامل\n"
                "/pending → لیست در انتظار + دکمه\n"
                "/reminders → یادآوری‌های فعال\n"
                "/sendlink USER_ID → ارسال لینک",
                reply_markup=admin_keyboard
            )
            return "ok", 200

    if chat_type == "private":

        if text == "/start":
            user_data = get_user(user_id)
            if user_data and user_data.get("phone"):
                current_status = get_chat_member_status(user_id)
                if current_status in ["member", "administrator", "creator"]:
                    if user_data.get("joined_channel") != 1:
                        mark_joined(user_id)
                    send_message(user_id, "شما قبلاً عضو کانال شده‌اید ✅")
                else:
                    # کاربر خارج شده یا لینک قبلی منقضی شده → درخواست مجدد
                    save_or_update_user(user_id, status="pending")
                    send_message(user_id,
                        "درخواست عضویت مجدد شما برای ادمین ارسال شد.\n"
                        "پس از تأیید، لینک یک‌بارمصرف جدید برایتان ارسال خواهد شد."
                    )
                    keyboard = {
                        "inline_keyboard": [[
                            {"text": "✅ ارسال لینک یک‌بارمصرف", "callback_data": f"sendlink_{user_id}"}
                        ]]
                    }
                    full_name = user_data.get("full_name") or ""
                    phone = user_data.get("phone") or ""
                    send_message(ADMIN_ID,
                        f"📝 *درخواست عضویت مجدد*\n\n"
                        f"👤 نام: {full_name}\n"
                        f"📱 شماره: {phone}\n"
                        f"🆔 آیدی: {user_id}\n"
                        f"یوزرنیم: @{user.get('username') or 'ندارد'}",
                        reply_markup=keyboard
                    )
            else:
                send_message(user_id,
                    " 👋خوش آمدید.\n\n"
                    "برای دریافت لینک عضویت کانال، لطفاً نام و نام خانوادگی خود را ارسال کنید:"
                )
            return "ok", 200

        if contact:
            phone = contact.get("phone_number")
            if contact.get("user_id") != user_id:
                send_message(user_id, "❌ لطفاً فقط شماره متعلق به خودتان را ارسال کنید.")
                return "ok", 200

            user_data = get_user(user_id)
            full_name = user_data["full_name"] if user_data else f"{user.get('first_name', '')} {user.get('last_name') or ''}".strip()

            save_or_update_user(
                user_id,
                full_name=full_name,
                phone=phone,
                username=user.get("username"),
                status="pending"
            )

            send_message(user_id,
                f"✅ مشخصات شما با موفقیت ثبت شد.\n\n"
                f"نام: *{full_name}*\n"
                f"شماره: {phone}\n\n"
                f"درخواست شما برای ادمین ارسال شد.\n"
                f"پس از تأیید، لینک عضویت یک‌بارمصرف برایتان ارسال خواهد شد."
            )

            keyboard = {
                "inline_keyboard": [[
                    {"text": "✅ ارسال لینک یک‌بارمصرف", "callback_data": f"sendlink_{user_id}"}
                ]]
            }
            send_message(ADMIN_ID,
                f"📝 *درخواست جدید عضویت*\n\n"
                f"👤 نام: {full_name}\n"
                f"📱 شماره: {phone}\n"
                f"🆔 آیدی: {user_id}\n"
                f"یوزرنیم: @{user.get('username') or 'ندارد'}",
                reply_markup=keyboard
            )
            return "ok", 200

        if text and text != "/start":
            user_data = get_user(user_id)
            if user_data and user_data.get("phone"):
                send_message(user_id, "مشخصات شما قبلاً ثبت شده است.")
                return "ok", 200

            save_or_update_user(user_id, full_name=text, username=user.get("username"), status="registered")

            keyboard = {
                "keyboard": [[{
                    "text": "📱 ارسال شماره تلفن",
                    "request_contact": True
                }]],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            send_message(user_id,
                f"ممنون *{text}* 🌟\n\n"
                "لطفاً با کلیک روی دکمه ارسال شماره تلفن خود را به راحتی ارسال کنید:",
                reply_markup=keyboard
            )
            return "ok", 200

        return "ok", 200

    process_message(message, is_edit=is_edit)
    return "ok", 200


# ==================== راه‌اندازی سیستم‌ها ====================
configure_reminders(send_message_func=send_message, admin_id=ADMIN_ID)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
