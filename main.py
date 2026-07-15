import re
import sqlite3
from fastapi import FastAPI, Request
import requests

# --- تنظیمات کلی ---
TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
MAIN_CHANNEL_URL = "https://ble.ir/BROKER_amlak"

# --- تنظیمات داینامیک دکمه‌ها (به راحتی قابل تغییر و اضافه کردن) ---
CONFIG = {
    "kinds": {
        "🏠 خرید": "فروش", 
        "🔑 رهن و اجاره": "رهن_اجاره"
    },
    "khabs": {
        "۱ خواب": "1خواب", 
        "۲ خواب": "2خواب", 
        "۳ خواب": "3خواب", 
        "۴ خواب و بیشتر": "4خواب"
    },
    "budgets": {
        "۲۰ تا ۳۰ میلیارد": (20 * 10**9, 30 * 10**9),
        "۳۰ تا ۴۰ میلیارد": (30 * 10**9, 40 * 10**9),
        "۴۰ تا ۵۰ میلیارد": (40 * 10**9, 50 * 10**9),
        "۵۰ میلیارد به بالا": (50 * 10**9, 999 * 10**9),
    },
    "meters": {
        "کمتر از ۱۰۰ متر": (0, 100),
        "۱۰۰ تا ۱۵۰ متر": (100, 150),
        "۱۵۰ تا ۲۰۰ متر": (150, 200),
        "بیشتر از ۲۰۰ متر": (200, 999),
    }
}

app = FastAPI()


def get_db():
    conn = sqlite3.connect("broker_final.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    # جدول فایل‌ها
    cur.execute(
        "CREATE TABLE IF NOT EXISTS files ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "text TEXT, "
        "kind TEXT, "
        "khab TEXT, "
        "price INTEGER, "
        "meter INTEGER, "
        "location TEXT, "
        "photo_id TEXT)"
    )
    # جدول جلسات (با اضافه شدن ستون step)
    cur.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "user_id INTEGER PRIMARY KEY, "
        "step TEXT, "
        "kind TEXT, "
        "khab TEXT, "
        "budje_min INTEGER, "
        "budje_max INTEGER, "
        "meter_min INTEGER, "
        "meter_max INTEGER, "
        "page INTEGER)"
    )
    # جدول علاقه‌مندی‌ها
    cur.execute(
        "CREATE TABLE IF NOT EXISTS favorites ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER, "
        "file_id INTEGER)"
    )
    # جدول اعلان‌های هوشمند (Alerts)
    cur.execute(
        "CREATE TABLE IF NOT EXISTS alerts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER, "
        "kind TEXT, "
        "khab TEXT, "
        "b_min INTEGER, "
        "b_max INTEGER, "
        "m_min INTEGER, "
        "m_max INTEGER)"
    )
    conn.commit()
    conn.close()


init_db()


# --- منطق استخراج پیشرفته اطلاعات ---
def extract_info(text):
    # شناسایی نوع معامله
    kind = "رهن_اجاره" if any(w in text for w in ["رهن", "اجاره"]) else "فروش"
    
    # استخراج تعداد خواب (پشتیبانی از "۲ خواب" یا "۲ اتاق خواب")
    kh_match = re.search(r"(\d+)\s*(?:اتاق\s*)?خواب", text)
    khab = f"{kh_match.group(1)}خواب" if kh_match else None
    
    # استخراج قیمت هوشمند (ترکیبی میلیارد و میلیون)
    price = 0
    b_match = re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text)
    m_match = re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text)
    if b_match: 
        price += int(b_match.group(1)) * 10**9
    if m_match: 
        price += int(m_match.group(1)) * 10**6
    if price == 0: 
        price = None

    # استخراج متراژ
    meter_match = re.search(r"(\d+)\s*(?:متر|م)", text)
    meter = int(meter_match.group(1)) if meter_match else None
    
    # استخراج لوکیشن (گسترش یافته)
    loc_match = re.search(r"(جنت‌آباد|تهران|فردیس|کرج|شهرک|منطقه\s*\d+|بلوار\s*[^\s]+)", text)
    location = loc_match.group(0) if loc_match else "نامشخص"
    
    return kind, khab, price, meter, location


def check_alerts(file_id, kind, khab, price, meter):
    """بررسی اینکه آیا این ملک با اعلان‌های کاربران مطابقت دارد یا خیر"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts")
    alerts = cur.fetchall()
    conn.close()
    
    for a in alerts:
        match = True
        if a["kind"] and a["kind"] != kind: 
            match = False
        if a["khab"] and a["khab"] != khab: 
            match = False
        if a["b_min"] and (price is None or price < a["b_min"]): 
            match = False
        if a["b_max"] and (price is None or price > a["b_max"]): 
            match = False
        if a["m_min"] and (meter is None or meter < a["m_min"]): 
            match = False
        if a["m_max"] and (meter is None or meter > a["m_max"]): 
            match = False
        
        if match:
            send_msg(a["user_id"], f"🔔 **اعلان هوشمند!**\nملک جدیدی مطابق با معیارهای شما یافت شد:\n\n🆔 {file_id}")


def save_file(text, photo_id=None):
    k, kh, p, m, l = extract_info(text)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO files (text, kind, khab, price, meter, location, photo_id) VALUES (?,?,?,?,?,?,?)", 
        (text, k, kh, p, m, l, photo_id)
    )
    f_id = cur.lastrowid
    conn.commit()
    conn.close()
    check_alerts(f_id, k, kh, p, m)  # بررسی اعلان‌ها بلافاصله بعد از ذخیره


def set_session(user_id, **kwargs):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO sessions (user_id, step) VALUES (?, 'start')", (user_id,))
    for key, value in kwargs.items():
        cur.execute(f"UPDATE sessions SET {key}=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()


def get_session(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE user_id=?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res


def search_files(kind, khab, bmin, bmax, mmin, mmax, page):
    conn = get_db()
    cur = conn.cursor()
    q, params = "SELECT * FROM files WHERE kind=?", [kind]
    if khab: 
        q += " AND khab=?"
        params.append(khab)
    if bmin and bmax: 
        q += " AND price BETWEEN ? AND ?"
        params.extend([bmin, bmax])
    if mmin and mmax: 
        q += " AND meter BETWEEN ? AND ?"
        params.extend([mmin, mmax])
    
    limit = 5
    q += " LIMIT ? OFFSET ?"
    params.extend([limit, (page - 1) * limit])
    
    cur.execute(q, params)
    res = cur.fetchall()
    conn.close()
    return res


# --- توابع کمکی ارسال پیام و کیبورد ---
def send_msg(cid, text, kb=None):
    payload = {
        "chat_id": cid, 
        "text": f"{text}\n\n📢 *کانال اصلی:*\n{MAIN_CHANNEL_URL}", 
        "parse_mode": "Markdown"
    }
    if kb: 
        payload["reply_markup"] = kb
    return requests.post(f"{BASE_URL}/sendMessage", json=payload)


def send_pic(cid, pid, cap, kb=None):
    payload = {
        "chat_id": cid, 
        "photo": pid, 
        "caption": f"{cap}\n\n📢 *کانال اصلی:*\n{MAIN_CHANNEL_URL}", 
        "parse_mode": "Markdown"
    }
    if kb: 
        payload["reply_markup"] = kb
    return requests.post(f"{BASE_URL}/sendPhoto", json=payload)


def kb_main(): 
    return {
        "keyboard": [
            [{"text": "🏠 خرید"}, {"text": "🔑 رهن و اجاره"}], 
            [{"text": "🔔 اعلان هوشمند"}, {"text": "⭐ علاقه‌مندی‌ها"}]
        ], 
        "resize_keyboard": True
    }


def kb_khab(): 
    return {
        "keyboard": [[{"text": k} for k in CONFIG["khabs"].keys()]], 
        "resize_keyboard": True
    }


def kb_budje(): 
    return {
        "keyboard": [[{"text": k} for k in CONFIG["budgets"].keys()]], 
        "resize_keyboard": True
    }


def kb_meter(): 
    return {
        "keyboard": [[{"text": k} for k in CONFIG["meters"].keys()]], 
        "resize_keyboard": True
    }


def kb_next(): 
    return {
        "keyboard": [[{"text": "صفحه بعد"}, {"text": "بازگشت به منو اصلی"}]], 
        "resize_keyboard": True
    }


def inline_action(fid): 
    return {
        "inline_keyboard": [
            [{"text": "🚀 مشاهده در کانال", "url": MAIN_CHANNEL_URL}], 
            [{"text": "⭐ افزودن به علاقه‌مندی", "callback_data": f"fav:{fid}"}]
        ]
    }


@app.post("/")
async def webhook(req: Request):
    data = await req.json()
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO favorites (user_id, file_id) VALUES (?,?)", (cid, d_val.split(":")[1]))
            conn.commit()
            conn.close()
            send_msg(cid, "✅ اضافه شد به علاقه‌مندی‌ها.")
        return {"ok": True}

    msg = data.get("message") or data.get("body")
    if not msg: 
        return {"ok": True}
    
    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid = chat.get("id")
    ctype = chat.get("type")
    
    if ctype == "channel":
        pid = msg["photo"][-1]["file_id"] if "photo" in msg else None
        if "موجود" in txt: 
            save_file(txt, pid)
        return {"ok": True}

    if ctype == "private":
        user_id = cid
        s = get_session(user_id)
        
        if txt == "/start" or txt == "بازگشت به منو اصلی":
            set_session(user_id, step="start", page=1)
            send_msg(cid, "خوش آمدید. نوع عملیات را انتخاب کنید:", kb_main())
            
        elif txt == "🔔 اعلان هوشمند":
            set_session(user_id, step="alert_start")
            send_msg(cid, "برای ایجاد اعلان، ابتدا نوع ملک را انتخاب کنید:", kb_main())

        elif s["step"] == "start" and txt in CONFIG["kinds"]:
            kind = CONFIG["kinds"][txt]
            set_session(user_id, step="choose_khab", kind=kind)
            send_msg(cid, "تعداد خواب را انتخاب کنید:", kb_khab())

        elif s["step"] == "choose_khab" and txt in CONFIG["khabs"]:
            khab = CONFIG["khabs"][txt]
            set_session(user_id, step="choose_budget" if s["kind"] == "فروش" else "choose_meter", khab=khab)
            kb = kb_budje() if s["kind"] == "فروش" else kb_meter()
            send_msg(cid, "بودجه/متراژ را انتخاب کنید:", kb)

        elif s["step"] == "choose_budget" and txt in CONFIG["budgets"]:
            b_min, b_max = CONFIG["budgets"][txt]
            set_session(user_id, step="choose_meter", budje_min=b_min, budje_max=b_max)
            send_msg(cid, "حالا متراژ را انتخاب کنید:", kb_meter())

        elif (s["step"] == "choose_meter" or s["step"] == "choose_budget") and txt in CONFIG["meters"]:
            m_min, m_max = CONFIG["meters"][txt]
            set_session(user_id, step="results", meter_min=m_min, meter_max=m_max)
            
            # نمایش نتایج
            res = search_files(s["kind"], s["khab"], s.get("budje_min"), s.get("budje_max"), m_min, m_max, 1)
            if not res:
                send_msg(cid, "❌ متاسفانه موردی یافت نشد.", kb_main())
            else:
                for r in res:
                    cap = f"🏠 **پیشنهاد ویژه**\n\n{r['text'][:200]}..."
                    if r["photo_id"]: 
                        send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else: 
                        send_msg(cid, cap, inline_action(r["id"]))
                send_msg(cid, "📄 برای مشاهده موارد بیشتر:", kb_next())
        
        elif txt == "صفحه بعد":
            new_page = (s["page"] or 1) + 1
            set_session(user_id, page=new_page)
            s = get_session(user_id)
            res = search_files(s["kind"], s["khab"], s["budje_min"], s["budje_max"], s["meter_min"], s["meter_max"], new_page)
            if not res: 
                send_msg(cid, "پایان لیست.", kb_main())
            else:
                for r in res:
                    cap = f"🏠 **پیشنهاد ویژه**\n\n{r['text'][:200]}..."
                    if r["photo_id"]: 
                        send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else: 
                        send_msg(cid, cap, inline_action(r["id"]))
                send_msg(cid, "📄 برای موارد بیشتر:", kb_next())

        elif txt == "⭐ علاقه‌مندی‌ها":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT file_id FROM favorites WHERE user_id=?", (user_id,))
            favs = cur.fetchall()
            conn.close()
            if not favs: 
                send_msg(cid, "لیست علاقه‌مندی‌های شما خالی است.")
            return {"ok": True}
