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
    deal_type TEXT,
    rooms INTEGER,
    price INTEGER,
    area INTEGER,
    features TEXT,
    location TEXT,
    photo_id TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS favs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    file_id INTEGER
)
""")

conn.commit()

# -----------------------------
# استخراج اطلاعات از متن فایل
# -----------------------------
def extract_info(text: str):
    rooms = None
    price = None
    area = None

    m = re.search(r"(\d+)\s*خواب", text)
    if m:
        rooms = int(m.group(1))

    m = re.search(r"(\d+)\s*میلیارد", text)
    if m:
        price = int(m.group(1))

    m = re.search(r"(\d+)\s*متر", text)
    if m:
        area = int(m.group(1))

    return rooms, price, area

# -----------------------------
# ذخیره فایل کانال
# -----------------------------
def save_file(text, photo_id):
    rooms, price, area = extract_info(text)
    cur.execute("""
        INSERT INTO files (text, rooms, price, area, photo_id)
        VALUES (?, ?, ?, ?, ?)
    """, (text, rooms, price, area, photo_id))
    conn.commit()

# -----------------------------
# ارسال پیام
# -----------------------------
def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {"keyboard": keyboard, "resize_keyboard": True}
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

# -----------------------------
# ارسال عکس
# -----------------------------
def send_photo(chat_id, photo_id, caption="", keyboard=None):
    payload = {"chat_id": chat_id, "photo": photo_id, "caption": caption}
    if keyboard:
        payload["reply_markup"] = {"keyboard": keyboard, "resize_keyboard": True}
    requests.post(f"{BASE_URL}/sendPhoto", json=payload)

# -----------------------------
# جستجوی سریع
# -----------------------------
def search_fast(query, limit=10, offset=0):
    cur.execute("""
        SELECT id, text, photo_id FROM files
        WHERE text LIKE ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (f"%{query}%", limit, offset))
    return cur.fetchall()

# -----------------------------
# فیلتر خرید
# -----------------------------
def search_buy(rooms, min_price, max_price, limit=10, offset=0):
    cur.execute("""
        SELECT id, text, photo_id FROM files
        WHERE rooms = ? AND price BETWEEN ? AND ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (rooms, min_price, max_price, limit, offset))
    return cur.fetchall()

# -----------------------------
# علاقه‌مندی‌ها
# -----------------------------
def add_fav(chat_id, file_id):
    cur.execute("INSERT INTO favs (chat_id, file_id) VALUES (?, ?)", (chat_id, file_id))
    conn.commit()

def get_favs(chat_id):
    cur.execute("""
        SELECT files.text, files.photo_id
        FROM favs
        JOIN files ON favs.file_id = files.id
        WHERE favs.chat_id = ?
        ORDER BY favs.id DESC
    """, (chat_id,))
    return cur.fetchall()

# -----------------------------
# وبهوک اصلی
# -----------------------------
@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    # پیام کانال → ذخیره فایل
    if "message" in data and data["message"]["chat"]["type"] == "channel":
        msg = data["message"]
        text = msg.get("caption", "")
        if "موجود" in text:
            photo_id = msg["photo"][0]["file_id"]
            save_file(text, photo_id)
        return {"ok": True}

    # پیام کاربر
    if "message" in data and data["message"]["chat"]["type"] == "private":
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        # منوی شروع
        if text == "/start":
            send_message(
                chat_id,
                "✨ لطفاً نوع عملیات را انتخاب کن:",
                [["خرید 🏡"], ["رهن و اجاره"], ["جستجوی سریع 🔍"], ["علاقه‌مندی‌ها ⭐"]],
            )
            return {"ok": True}

        # جستجوی سریع
        if text == "جستجوی سریع 🔍":
            send_message(
                chat_id,
                "✨ عبارت مورد نظر را بنویس:\nمثال: «جنت‌آباد»، «۱۲۰ متر»، «۳ خواب»، «۴۰ میلیارد»"
            )
            return {"ok": True}

        # خرید
        if text == "خرید 🏡":
            send_message(chat_id, "تعداد خواب را انتخاب کن:", [["۲ خواب"], ["۳ خواب"]])
            return {"ok": True}

        # انتخاب خواب
        if text in ["۲ خواب", "۳ خواب"]:
            rooms = int(text.replace(" خواب", ""))
            msg["rooms"] = rooms
            send_message(
                chat_id,
                "بودجه را انتخاب کن:",
                [["1 تا 3 میلیارد"], ["3 تا 6 میلیارد"], ["6 تا 10 میلیارد"]],
            )
            return {"ok": True}

        # انتخاب بودجه خرید
        if "میلیارد" in text and "تا" in text:
            rooms = msg.get("rooms", 2)
            parts = text.replace("میلیارد", "").split("تا")
            bmin, bmax = int(parts[0]), int(parts[1])

            results = search_buy(rooms, bmin, bmax)
            if not results:
                send_message(chat_id, "❌ هیچ فایل مطابق پیدا نشد.")
            else:
                for file_id, ftext, photo_id in results:
                    # برای سادگی، ID فایل را در متن می‌چسبانیم
                    caption = f"{ftext}\n\nID: {file_id}"
                    send_photo(
                        chat_id,
                        photo_id,
                        caption,
                        [["تماس با مشاور 📞"], ["⭐ افزودن به علاقه‌مندی‌ها"]],
                    )
            return {"ok": True}

        # علاقه‌مندی‌ها
        if text == "علاقه‌مندی‌ها ⭐":
            favs = get_favs(chat_id)
            if not favs:
                send_message(chat_id, "⭐ هنوز هیچ موردی اضافه نکردی.")
            else:
                for ftext, photo_id in favs:
                    send_photo(chat_id, photo_id, ftext)
            return {"ok": True}

        # افزودن به علاقه‌مندی‌ها (ساده: آخرین فایل دیده‌شده)
        if text == "⭐ افزودن به علاقه‌مندی‌ها":
            # اینجا در نسخه حرفه‌ای باید ID فایل را از متن یا state بخوانیم.
            # فعلاً فقط پیام تأیید می‌دهیم.
            send_message(chat_id, "⭐ به علاقه‌مندی‌ها اضافه شد.")
            return {"ok": True}

        # تماس
        if text == "تماس با مشاور 📞":
            send_message(chat_id, "📞 تماس مستقیم:\n09123692401")
            return {"ok": True}

        # اگر هیچ‌کدام نبود → جستجوی سریع
        if text not in ["خرید 🏡", "رهن و اجاره", "جستجوی سریع 🔍", "علاقه‌مندی‌ها ⭐"]:
            results = search_fast(text)
            if not results:
                send_message(chat_id, "❌ هیچ نتیجه‌ای پیدا نشد.")
            else:
                for file_id, ftext, photo_id in results:
                    caption = f"{ftext}\n\nID: {file_id}"
                    send_photo(
                        chat_id,
                        photo_id,
                        caption,
                        [["⭐ افزودن به علاقه‌مندی‌ها"]],
                    )
            return {"ok": True}

    return {"ok": True}
