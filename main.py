from fastapi import FastAPI, Request
import requests
import sqlite3

TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

app = FastAPI()

# -----------------------------
# دیتابیس SQLite
# -----------------------------
conn = sqlite3.connect("files.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    tags TEXT
)
""")
conn.commit()

def extract_tags(text):
    return [w for w in text.split() if w.startswith("#")]

def save_file(text):
    tags = " ".join(extract_tags(text))
    cur.execute("INSERT INTO files (text, tags) VALUES (?, ?)", (text, tags))
    conn.commit()

def search_files(kind, khab=None, budje=None):
    q = "SELECT text FROM files WHERE tags LIKE ?"
    params = [f"%#{kind}%"]

    if khab:
        q += " AND tags LIKE ?"
        params.append(f"%#{khab}%")

    if budje:
        q += " AND tags LIKE ?"
        params.append(f"%{budje}%")

    cur.execute(q, params)
    return [row[0] for row in cur.fetchall()]

# -----------------------------
# ارسال پیام
# -----------------------------
def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = keyboard
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

# -----------------------------
# کیبوردها
# -----------------------------
def kb_start():
    return {
        "keyboard": [
            [{"text": "خرید"}],
            [{"text": "رهن و اجاره"}]
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

def kb_budje():
    return {
        "keyboard": [
            [{"text": "۲۰ تا ۲۵ میلیارد"}],
            [{"text": "۲۵ تا ۳۰ میلیارد"}],
            [{"text": "۳۰ تا ۴۰ میلیارد"}],
            [{"text": "۴۰ تا ۵۰ میلیارد"}],
            [{"text": "۵۰ میلیارد به بالا"}]
        ],
        "resize_keyboard": True
    }

# -----------------------------
# وبهوک
# -----------------------------
@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    # ذخیره پست‌های کانال
    if "message" in data and data["message"]["chat"]["type"] == "channel":
        text = data["message"].get("text", "")
        if "#موجود" in text:
            save_file(text)
        return {"ok": True}

    # پیام‌های بازو
    if "message" in data and data["message"]["chat"]["type"] == "private":
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # شروع
        if text == "/start":
            send_message(chat_id, "نوع عملیات را انتخاب کن:", kb_start())
            return {"ok": True}

        # انتخاب نوع معامله
        if text == "خرید":
            send_message(chat_id, "تعداد خواب را انتخاب کن:", kb_khab())
            return {"ok": True}

        if text == "رهن و اجاره":
            send_message(chat_id, "تعداد خواب را انتخاب کن:", kb_khab())
            return {"ok": True}

        # انتخاب خواب
        if text in ["۲ خواب", "۳ خواب"]:
            send_message(chat_id, "بازه بودجه را انتخاب کن:", kb_budje())
            return {"ok": True}

        # انتخاب بودجه → فیلتر
        budje_map = {
            "۲۰ تا ۲۵ میلیارد": "#۲۰میلیارد",
            "۲۵ تا ۳۰ میلیارد": "#۳۰میلیارد",
            "۳۰ تا ۴۰ میلیارد": "#۳۰میلیارد",
            "۴۰ تا ۵۰ میلیارد": "#۴۰میلیارد",
            "۵۰ میلیارد به بالا": "#۵۰میلیارد_به_بالا"
        }

        if text in budje_map:
            budje_tag = budje_map[text]
            send_message(chat_id, "در حال جستجو...")

            results = search_files("فروش", "۲خواب", budje_tag)

            if not results:
                send_message(chat_id, "هیچ فایل مطابق پیدا نشد.")
            else:
                for r in results:
                    send_message(chat_id, r)

            return {"ok": True}

    return {"ok": True}
