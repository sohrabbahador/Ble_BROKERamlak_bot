from fastapi import FastAPI, Request
import requests
import sqlite3
import re

TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

app = FastAPI()

# -----------------------------
# دیتابیس
# -----------------------------
conn = sqlite3.connect("files.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    kind TEXT,
    khab TEXT,
    price INTEGER,
    amenities TEXT,
    location TEXT,
    photo_id TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS sessions (
    user_id INTEGER PRIMARY KEY,
    kind TEXT,
    khab TEXT,
    budje_min INTEGER,
    budje_max INTEGER,
    page INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_id INTEGER
)
""")

conn.commit()

# -----------------------------
# استخراج اطلاعات فایل
# -----------------------------
def extract_info(text):
    kind = "رهن_اجاره" if ("رهن" in text or "اجاره" in text) else "فروش"

    khab_match = re.search(r"(\d+)\s*خواب", text)
    khab = f"{khab_match.group(1)}خواب" if khab_match else None

    price_match = re.search(r"(\d+)\s*میلیارد", text)
    price = int(price_match.group(1)) if price_match else None

    amenities = []
    for item in ["آسانسور", "پارکینگ", "انباری", "بالکن", "نوساز"]:
        if item in text:
            amenities.append(item)
    amenities = ",".join(amenities)

    loc_match = re.search(r"(جنت‌آباد جنوبی|جنت آباد|تهران|فردیس|کرج|فلکه\s*\w+|شهرک\s*\w+)", text)
    location = loc_match.group(1) if loc_match else None

    return kind, khab, price, amenities, location

# -----------------------------
# ذخیره فایل کانال
# -----------------------------
def save_file(text, photo_id=None):
    kind, khab, price, amenities, location = extract_info(text)
    cur.execute("""
        INSERT INTO files (text, kind, khab, price, amenities, location, photo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (text, kind, khab, price, amenities, location, photo_id))
    conn.commit()

# -----------------------------
# مدیریت session
# -----------------------------
def set_session(user_id, **kwargs):
    cur.execute("SELECT user_id FROM sessions WHERE user_id=?", (user_id,))
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            INSERT INTO sessions (user_id, kind, khab, budje_min, budje_max, page)
            VALUES (?, NULL, NULL, NULL, NULL, 1)
        """, (user_id,))

    for key, value in kwargs.items():
        cur.execute(f"UPDATE sessions SET {key}=? WHERE user_id=?", (value, user_id))

    conn.commit()

def get_session(user_id):
    cur.execute("""
        SELECT kind, khab, budje_min, budje_max, page
        FROM sessions WHERE user_id=?
    """, (user_id,))
    return cur.fetchone()

# -----------------------------
# فیلتر خرید (بدون متراژ)
# -----------------------------
def search_buy(khab, bmin, bmax, page):
    q = "SELECT id, text, photo_id FROM files WHERE kind='فروش'"
    params = []

    if khab:
        q += " AND khab=?"
        params.append(khab)

    if bmin is not None and bmax is not None:
        q += " AND price BETWEEN ? AND ?"
        params.append(bmin)
        params.append(bmax)

    limit = 5
    offset = (page - 1) * limit
    q += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(q, params)
    return cur.fetchall()

# -----------------------------
# فیلتر رهن و اجاره
# -----------------------------
def search_rent(khab, page):
    q = "SELECT id, text, photo_id FROM files WHERE kind='رهن_اجاره'"
    params = []

    if khab:
        q += " AND khab=?"
        params.append(khab)

    limit = 5
    offset = (page - 1) * limit
    q += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(q, params)
    return cur.fetchall()

# -----------------------------
# علاقه‌مندی‌ها
# -----------------------------
def add_favorite(user_id, file_id):
    cur.execute("SELECT id FROM favorites WHERE user_id=? AND file_id=?", (user_id, file_id))
    if not cur.fetchone():
        cur.execute("INSERT INTO favorites (user_id, file_id) VALUES (?, ?)", (user_id, file_id))
        conn.commit()

def list_favorites(user_id):
    cur.execute("""
        SELECT f.file_id, files.text, files.photo_id
        FROM favorites f
        JOIN files ON f.file_id = files.id
        WHERE f.user_id=?
    """, (user_id,))
    return cur.fetchall()

# -----------------------------
# جستجوی سریع
# -----------------------------
def quick_search(query):
    cur.execute("SELECT id, text, photo_id FROM files WHERE text LIKE ?", (f"%{query}%",))
    return cur.fetchall()

# -----------------------------
# ارسال پیام / عکس
# -----------------------------
def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = keyboard
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_photo(chat_id, photo_id, caption, keyboard=None):
    payload = {"chat_id": chat_id, "photo": photo_id, "caption": caption}
    if keyboard:
        payload["reply_markup"] = keyboard
    requests.post(f"{BASE_URL}/sendPhoto", json=payload)

# -----------------------------
# کیبوردها
# -----------------------------
def kb_start():
    return {
        "keyboard": [
            [{"text": "خرید"}],
            [{"text": "رهن و اجاره"}],
            [{"text": "🔍 جستجوی سریع"}],
            [{"text": "⭐ علاقه‌مندی‌ها"}]
        ],
        "resize_keyboard": True
    }

def kb_khab():
    return {
        "keyboard": [
            [{"text": "۲ خواب"}],
            [{"text": "۳ خواب"}]
        ],
        "resize_keyboard": True
    }

def kb_budje_sale():
    return {
        "keyboard": [
            [{"text": "۲۰ تا ۳۰ میلیارد"}],
            [{"text": "۳۰ تا ۴۰ میلیارد"}],
            [{"text": "۴۰ تا ۵۰ میلیارد"}],
            [{"text": "۵۰ میلیارد به بالا"}]
        ],
        "resize_keyboard": True
    }

def kb_next_page():
    return {
        "keyboard": [
            [{"text": "صفحه بعد"}],
            [{"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def inline_main(file_id):
    return {
        "inline_keyboard": [
            [
                {"text": "📞 تماس", "callback_data": f"contact:{file_id}"},
                {"text": "ℹ️ جزئیات", "callback_data": f"detail:{file_id}"}
            ],
            [
                {"text": "⭐ افزودن به علاقه‌مندی‌ها", "callback_data": f"favadd:{file_id}"}
            ]
        ]
    }

# -----------------------------
# وبهوک
# -----------------------------
@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    # پیام کانال
    if "message" in data and data["message"]["chat"]["type"] == "channel":
        msg = data["message"]
        text = msg.get("text", "") or msg.get("caption", "")
        photo_id = msg["photo"][-1]["file_id"] if "photo" in msg else None

        if "موجود" in text:
            save_file(text, photo_id)

        return {"ok": True}

    # کال‌بک
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        user_id = cq["from"]["id"]
        data_cb = cq["data"]

        if data_cb.startswith("contact:"):
            send_message(chat_id, "📞 تماس مستقیم:\n09123692401")

        elif data_cb.startswith("detail:"):
            file_id = int(data_cb.split(":")[1])
            cur.execute("SELECT text FROM files WHERE id=?", (file_id,))
            row = cur.fetchone()
            if row:
                send_message(chat_id, f"ℹ️ جزئیات:\n\n{row[0]}")

        elif data_cb.startswith("favadd:"):
            file_id = int(data_cb.split(":")[1])
            add_favorite(user_id, file_id)
            send_message(chat_id, "⭐ به علاقه‌مندی‌ها اضافه شد.")

        return {"ok": True}

    # پیام خصوصی
    if "message" in data and data["message"]["chat"]["type"] == "private":
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        user_id = chat_id
        text = msg.get("text", "")

        # شروع
        if text == "/start":
            send_message(chat_id, "سلام 👋\nبه بازوی املاک خوش آمدید ✨", kb_start())
            return {"ok": True}

        # علاقه‌مندی‌ها
        if text == "⭐ علاقه‌مندی‌ها":
            favs = list_favorites(user_id)
            if not favs:
                send_message(chat_id, "⭐ هیچ فایل علاقه‌مندی نداری.")
            else:
                send_message(chat_id, "⭐ فایل‌های علاقه‌مندی:")
                for fid, ftext, photo_id in favs:
                    caption = f"🏡 فایل:\n\n{ftext}"
                    kb_inline = inline_main(fid)
                    if photo_id:
                        send_photo(chat_id, photo_id, caption, kb_inline)
                    else:
                        send_message(chat_id, caption, kb_inline)
            return {"ok": True}

        # جستجوی سریع
        if text == "🔍 جستجوی سریع":
            send_message(chat_id,
                "✨ عبارت مورد نظر را بنویس:\nمثال:\n«جنت‌آباد جنوبی»\n«۱۲۰ متر»\n«۳ خواب»\n«۴۰ میلیارد»"
            )
            set_session(user_id, kind=None, khab=None, budje_min=None, budje_max=None, page=1)
            return {"ok": True}

        # حالت جستجوی سریع
        kind, khab, bmin, bmax, page = get_session(user_id)
        if kind is None and khab is None and bmin is None and text not in ["خرید", "رهن و اجاره", "۲ خواب", "۳ خواب"]:
            results = quick_search(text)
            if not results:
                send_message(chat_id, "❌ هیچ موردی پیدا نشد.")
            else:
                send_message(chat_id, "🔎 نتایج:")
                for fid, ftext, photo_id in results:
                    caption = f"🏙️ فایل:\n\n{ftext}"
                    kb_inline = inline_main(fid)
                    if photo_id:
                        send_photo(chat_id, photo_id, caption, kb_inline)
                    else:
                        send_message(chat_id, caption, kb_inline)
            return {"ok": True}

        # نوع معامله
        if text in ["خرید", "رهن و اجاره"]:
            kind_tag = "فروش" if text == "خرید" else "رهن_اجاره"
            set_session(user_id, kind=kind_tag, page=1)
            send_message(chat_id, "🏡 تعداد خواب را انتخاب کن:", kb_khab())
            return {"ok": True}

        # خواب
        if text in ["۲ خواب", "۳ خواب"]:
            khab_tag = "۲خواب" if text == "۲ خواب" else "۳خواب"
            set_session(user_id, khab=khab_tag)

            kind, *_ = get_session(user_id)
            if kind == "فروش":
                send_message(chat_id, "💰 بودجه را انتخاب کن:", kb_budje_sale())
            elif kind == "رهن_اجاره":
                send_message(chat_id, "⏳ در حال جستجوی فایل‌های رهن و اجاره...")
                kind, khab, bmin, bmax, page = get_session(user_id)
                results = search_rent(khab, page)

                if not results:
                    send_message(chat_id, "❌ هیچ فایل رهن و اجاره مطابق پیدا نشد.", kb_next_page())
                else:
                    for fid, ftext, photo_id in results:
                        caption = f"🏢 فایل رهن‌واجاره:\n\n{ftext}"
                        kb_inline = inline_main(fid)
                        if photo_id:
                            send_photo(chat_id, photo_id, caption, kb_inline)
                        else:
                            send_message(chat_id, caption, kb_inline)

                    send_message(chat_id, "📄 برای دیدن فایل‌های بیشتر، «صفحه بعد» را بزن.", kb_next_page())
            return {"ok": True}

        # بودجه خرید
        budje_map_sale = {
            "۲۰ تا ۳۰ میلیارد": (20, 30),
            "۳۰ تا ۴۰ میلیارد": (30, 40),
            "۴۰ تا ۵۰ میلیارد": (40, 50),
            "۵۰ میلیارد به بالا": (50, 999)
        }

        if text in budje_map_sale:
            bmin, bmax = budje_map_sale[text]
            set_session(user_id, budje_min=bmin, budje_max=bmax)

            kind, khab, bmin, bmax, page = get_session(user_id)
            send_message(chat_id, "⏳ در حال جستجو...")

            results = search_buy(khab, bmin, bmax, page)

            if not results:
                send_message(chat_id, "❌ هیچ فایل مطابق پیدا نشد.", kb_next_page())
            else:
                for fid, ftext, photo_id in results:
                    caption = f"🏡 فایل:\n\n{ftext}"
                    kb_inline = inline_main(fid)
                    if photo_id:
                        send_photo(chat_id, photo_id, caption, kb_inline)
                    else:
                        send_message(chat_id, caption, kb_inline)

                send_message(chat_id, "📄 برای دیدن فایل‌های بیشتر، «صفحه بعد» را بزن.", kb_next_page())
            return {"ok": True}

        # صفحه بعد
        if text == "صفحه بعد":
            kind, khab, bmin, bmax, page = get_session(user_id)
            page += 1
            set_session(user_id, page=page)

            if kind == "فروش":
                results = search_buy(khab, bmin, bmax, page)
            elif kind == "رهن_اجاره":
                results = search_rent(khab, page)
            else:
                results = []

            if not results:
                send_message(chat_id, "❌ فایل بیشتری وجود ندارد.", kb_next_page())
            else:
                for fid, ftext, photo_id in results:
                    caption = f"🏡 فایل:\n\n{ftext}"
                    kb_inline = inline_main(fid)
                    if photo_id:
                        send_photo(chat_id, photo_id, caption, kb_inline)
                    else:
                        send_message(chat_id, caption, kb_inline)

                send_message(chat_id, "📄 ادامه بده:", kb_next_page())
            return {"ok": True}

        # بازگشت
        if text == "بازگشت به منو اصلی":
            send_message(chat_id, "منوی اصلی:", kb_start())
            return {"ok": True}

    return {"ok": True}
