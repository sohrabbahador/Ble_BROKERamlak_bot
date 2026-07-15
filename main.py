import re
import sqlite3
from fastapi import FastAPI, Request
import requests

# --- تنظیمات ---
TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
CHANNEL_URL = "https://ble.ir/BROKER_amlak"

app = FastAPI()


def get_db():
    conn = sqlite3.connect("broker_luxury.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS files ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "text TEXT, "
        "kind TEXT, "
        "khab TEXT, "
        "price INTEGER, "
        "meter INTEGER, "
        "photo_id TEXT)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "user_id INTEGER PRIMARY KEY, "
        "step TEXT, "
        "kind TEXT, "
        "khab TEXT, "
        "b_min INTEGER, "
        "b_max INTEGER)"
    )
    conn.commit()
    conn.close()


init_db()


# --- توابع ارسال ---
def send_bale(method, payload):
    return requests.post(f"{BASE_URL}/{method}", json=payload)


def edit_msg(cid, mid, text, kb=None):
    payload = {"chat_id": cid, "message_id": mid, "text": text, "parse_mode": "Markdown"}
    if kb: 
        payload["reply_markup"] = kb
    return send_bale("editMessageText", payload)


def send_msg(cid, text, kb=None):
    payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    if kb: 
        payload["reply_markup"] = kb
    return send_bale("sendMessage", payload)


# --- طراحی دکمه‌های شیک ---
def main_kb():
    return {
        "keyboard": [
            [{"text": "🏠 جستجوی ملک"}, {"text": "🔔 اعلان هوشمند"}], 
            [{"text": "⭐ علاقه‌مندی‌ها"}]
        ], 
        "resize_keyboard": True
    }


def inline_kb(btns, prefix):
    keyboard = []
    for i in range(0, len(btns), 2):
        row = [{"text": btns[i][0], "callback_data": f"{prefix}:{btns[i][1]}"}]
        if i + 1 < len(btns):
            row.append({"text": btns[i + 1][0], "callback_data": f"{prefix}:{btns[i + 1][1]}"})
        keyboard.append(row)
    return {"inline_keyboard": keyboard}


@app.post("/")
async def webhook(req: Request):
    data = await req.json()
    
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        mid = cb["message"]["message_id"]
        d_val = cb["data"]
        
        if d_val.startswith("set_k:"):  # انتخاب نوع معامله
            kind = d_val.split(":")[1]
            conn = get_db()
            conn.execute("UPDATE sessions SET step='khab', kind=? WHERE user_id=?", (kind, cid))
            conn.commit()
            conn.close()
            btns = [("۱ خواب", "1"), ("۲ خواب", "2"), ("۳ خواب", "3"), ("۴+ خواب", "4")]
            edit_msg(
                cid, 
                mid, 
                "✨ عالیه. حالا لطفاً تعداد خواب مورد نظرتون رو انتخاب کنید:", 
                inline_kb(btns, "set_kh")
            )
            
        elif d_val.startswith("set_kh:"):  # انتخاب تعداد خواب
            khab = d_val.split(":")[1] + "خواب"
            conn = get_db()
            conn.execute("UPDATE sessions SET step='budget', khab=? WHERE user_id=?", (khab, cid))
            conn.commit()
            conn.close()
            btns = [
                ("۲۰ تا ۳۰ میلیارد", "20_30"), 
                ("۳۰ تا ۴۰ میلیارد", "30_40"), 
                ("۴۰ تا ۵۰ میلیارد", "40_50"), 
                ("۵۰+ میلیارد", "50_999")
            ]
            edit_msg(
                cid, 
                mid, 
                "💰 برای اینکه بهترین گزینه‌ها رو پیدا کنم، بازه بودجه‌تون رو بگید:", 
                inline_kb(btns, "set_b")
            )

        elif d_val.startswith("set_b:"):  # نمایش نتایج
            b_range = d_val.split(":")[1].split("_")
            b_min, b_max = int(b_range[0]) * 10**9, int(b_range[1]) * 10**9
            
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM sessions WHERE user_id=?", (cid,))
            s = cur.fetchone()
            
            cur.execute(
                "SELECT * FROM files WHERE kind=? AND khab=? AND price BETWEEN ? AND ? LIMIT 5", 
                (s["kind"], s["khab"], b_min, b_max)
            )
            results = cur.fetchall()
            conn.close()
            
            edit_msg(cid, mid, "🔍 در حال بررسی آخرین فایل‌ها برای شما...")
            
            if not results:
                send_msg(
                    cid, 
                    "❌ متاسفانه در حال حاضر ملکی با این مشخصات نداریم.\n\n"
                    "اما می‌توانید از بخش «اعلان هوشمند» درخواست ثبت کنید تا به محض موجود شدن، به شما خبر دهیم.", 
                    main_kb()
                )
            else:
                send_msg(cid, "💎 **پیشنهادهای ویژه برای شما:**")
                for r in results:
                    cap = f"🏠 **ملک پیشنهادی**\n\n{r['text'][:300]}..."
                    if r["photo_id"]: 
                        send_bale("sendPhoto", {"chat_id": cid, "photo": r["photo_id"], "caption": cap})
                    else: 
                        send_msg(cid, cap)
                send_msg(cid, "امیدوارم مورد پسندتون باشه! برای جستجوی مجدد از منوی اصلی استفاده کنید.", main_kb())
        
        return {"ok": True}

    msg = data.get("message", {})
    txt = msg.get("text", "")
    cid = msg.get("chat", {}).get("id")
    
    if txt == "/start" or txt == "بازگشت":
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO sessions (user_id, step) VALUES (?, 'start')", (cid,))
        conn.commit()
        conn.close()
        welcome_text = (
            f"سلام سهراب بهادر عزیز، به **بروکر املاک** خوش آمدید. 🏠\n\n"
            f"من اینجا هستم تا سریع‌ترین راه رو برای پیدا کردن ملک رویایی‌تون براتون باز کنم.\n\n"
            f"📢 کانال ما برای مشاهده لحظه‌ای ملک‌ها:\n{CHANNEL_URL}"
        )
        send_msg(cid, welcome_text, main_kb())

    elif txt == "🏠 جستجوی ملک":
        btns = [("🏠 خرید آپارتمان", "فروش"), ("🔑 رهن و اجاره", "رهن_اجاره")]
        send_msg(cid, "ابتدا بفرمایید قصد **خرید** دارید یا **اجاره**؟", inline_kb(btns, "set_k"))

    elif txt == "🔔 اعلان هوشمند":
        send_msg(
            cid, 
            "🔔 **سرویس اعلان هوشمند**\n\n"
            "در این بخش می‌توانید مشخصات ملک مورد نظرتون رو ثبت کنید تا به محض اینکه ملکی با این ویژگی‌ها "
            "وارد سیستم شد، فوراً به شما خبر بدیم."
        )

    return {"ok": True}
