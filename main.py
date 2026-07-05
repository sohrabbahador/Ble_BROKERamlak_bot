from fastapi import FastAPI, Request
import requests
import sqlite3
import re

TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

app = FastAPI()

# دیتابیس
conn = sqlite3.connect("files.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    kind TEXT,
    khab TEXT,
    price INTEGER,
    photo_id TEXT
)
""")
conn.commit()

# استخراج اطلاعات
def extract_info(text):
    kind = "رهن_اجاره" if ("رهن" in text or "اجاره" in text) else "فروش"
    khab_match = re.search(r"(\d+)\s*خواب", text)
    khab = f"{khab_match.group(1)}خواب" if khab_match else None
    price_match = re.search(r"(\d+)\s*میلیارد", text)
    price = int(price_match.group(1)) if price_match else None
    return kind, khab, price

def save_file(text, photo_id=None):
    kind, khab, price = extract_info(text)
    cur.execute("INSERT INTO files (text, kind, khab, price, photo_id) VALUES (?, ?, ?, ?, ?)",
                (text, kind, khab, price, photo_id))
    conn.commit()

# جستجو خرید (بدون متراژ)
def search_buy(khab, bmin, bmax):
    q = "SELECT text, photo_id FROM files WHERE kind='فروش'"
    params = []
    if khab:
        q += " AND khab=?"
        params.append(khab)
    if bmin is not None and bmax is not None:
        q += " AND price BETWEEN ? AND ?"
        params.extend([bmin, bmax])
    cur.execute(q, params)
    return cur.fetchall()

# ارسال پیام
def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {"keyboard": keyboard, "resize_keyboard": True}
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_photo(chat_id, photo_id, caption, keyboard=None):
    payload = {"chat_id": chat_id, "photo": photo_id, "caption": caption}
    if keyboard:
        payload["reply_markup"] = {"keyboard": keyboard, "resize_keyboard": True}
    requests.post(f"{BASE_URL}/sendPhoto", json=payload)

# کیبوردها
WELCOME_KEYBOARD = [["خرید 🏡"], ["رهن‌واجاره 🏢"], ["جستجوی سریع 🔍"]]
KHAB_KEYBOARD = [["۲ خواب"], ["۳ خواب"]]
BUDJE_KEYBOARD = [["۲۰ تا ۳۰ میلیارد"], ["۳۰ تا ۴۰ میلیارد"], ["۴۰ تا ۵۰ میلیارد"], ["۵۰ میلیارد به بالا"]]

@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    # پیام کانال
    if "message" in data and data["message"]["chat"]["type"] == "channel":
        msg = data["message"]
        text = msg.get("caption", "")
        if "موجود" in text:
            photo_id = msg["photo"][0]["file_id"]
            save_file(text, photo_id)
        return {"ok": True}

    # پیام کاربر
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        # خوش‌آمدگویی
        if text == "/start":
            send_message(chat_id, "سلام 👋\nبه بازوی املاک خوش آمدید ✨", WELCOME_KEYBOARD)
            return {"ok": True}

        # خرید
        if text == "خرید 🏡":
            send_message(chat_id, "تعداد خواب را انتخاب کنید:", KHAB_KEYBOARD)
            return {"ok": True}

        # انتخاب خواب
        if text in ["۲ خواب", "۳ خواب"]:
            khab = text.replace(" خواب", "")
            msg["khab"] = khab
            send_message(chat_id, "بودجه را انتخاب کنید:", BUDJE_KEYBOARD)
            return {"ok": True}

        # انتخاب بودجه
        if "میلیارد" in text:
            khab = msg.get("khab", "۲")
            parts = text.replace("میلیارد", "").split("تا")
            if len(parts) == 2:
                bmin, bmax = int(parts[0].strip()), int(parts[1].strip())
            else:
                bmin, bmax = 50, 999
            results = search_buy(f"{khab}خواب", bmin, bmax)
            if not results:
                send_message(chat_id, "❌ هیچ فایل مطابق پیدا نشد.")
            else:
                for ftext, photo_id in results:
                    send_photo(chat_id, photo_id, ftext, [["تماس با مشاور 📞"]])
            return {"ok": True}

        # تماس
        if text == "تماس با مشاور 📞":
            send_message(chat_id, "📞 تماس مستقیم:\n09123692401")
            return {"ok": True}

    return {"ok": True}
