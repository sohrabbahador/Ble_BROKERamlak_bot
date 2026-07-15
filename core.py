# core.py
import json
import re
import sqlite3
import httpx

# تنظیمات اصلی
TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
MAIN_CHANNEL_URL = "https://ble.ir/BROKER_amlak"
ADMIN_ID = 123456789  # شناسه عددی سهراب بهادر (مدیر)


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
        "photos TEXT)"
    )
    # جدول نشست‌ها
    cur.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "user_id INTEGER PRIMARY KEY, "
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
    # جدول کاربران برای آمار و پیام همگانی
    cur.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "user_id INTEGER PRIMARY KEY, "
        "first_name TEXT)"
    )
    # جدول گوش‌به‌زنگ (آلارم‌ها)
    cur.execute(
        "CREATE TABLE IF NOT EXISTS alerts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER, "
        "kind TEXT, "
        "khab TEXT, "
        "budje_min INTEGER, "
        "budje_max INTEGER, "
        "meter_min INTEGER, "
        "meter_max INTEGER)"
    )
    conn.commit()
    conn.close()


def register_user(user_id, first_name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO users (user_id, first_name) VALUES (?, ?)", (user_id, first_name))
    conn.commit()
    conn.close()


def fa_to_en(text):
    if not text:
        return ""
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def extract_info(text):
    text_en = fa_to_en(text)
    kind = "رهن_اجاره" if any(w in text for w in ["رهن", "اجاره", "رهن_اجاره"]) else "فروش"

    khab = None
    kh_match = re.search(r"(\d+)\s*(?:اتاق\s*)?خواب", text_en)
    if kh_match:
        num = kh_match.group(1)
        num_fa = num.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        khab = f"{num_fa} خواب"
    elif "تک خواب" in text or "یک خواب" in text:
        khab = "۱ خواب"

    price = None
    price_line = ""
    for line in text_en.split("\n"):
        if any(keyword in line for keyword in ["قیمت", "رهن", "ودیعه"]):
            if "متری" not in line:
                price_line = line
                break

    if price_line:
        billions = 0
        millions = 0
        b_match = re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", price_line)
        m_match = re.search(r"(\d+)\s*(?:میلیون|میلیونی)", price_line)
        if b_match:
            billions = int(b_match.group(1)) * 10**9
        if m_match:
            millions = int(m_match.group(1)) * 10**6
        price = billions + millions

    if not price:
        b_match = re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text_en)
        m_match = re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
        if b_match:
            price = int(b_match.group(1)) * 10**9
            if m_match:
                price += int(m_match.group(1)) * 10**6
        elif m_match:
            price = int(m_match.group(1)) * 10**6

    meter_match = re.search(r"متراژ[:\s]*(\d+)", text_en) or re.search(r"(\d+)\s*متر", text_en)
    meter = int(meter_match.group(1)) if meter_match else None

    loc_match = re.search(r"موقعیت[:\s]*(.*)", text) or re.search(r"(جنت‌آباد|تهران|منطقه\s*\d+|ستاری)", text)
    location = loc_match.group(1).strip() if loc_match else "نامشخص"

    return kind, khab, price, meter, location


async def check_alerts_and_notify(text, kind, khab, price, meter, photos):
    """بررسی آلارم‌های ثبت شده کاربران و ارسال نوتیفیکیشن در صورت تطابق ملک جدید"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts")
    alerts = cur.fetchall()
    conn.close()

    for alert in alerts:
        if alert["kind"] and alert["kind"] != kind:
            continue
        if alert["khab"] and alert["khab"] != khab:
            continue
        if alert["budje_min"] is not None and (price is None or price < alert["budje_min"]):
            continue
        if alert["budje_max"] is not None and (price is None or price > alert["budje_max"]):
            continue
        if alert["meter_min"] is not None and (meter is None or meter < alert["meter_min"]):
            continue
        if alert["meter_max"] is not None and (meter is None or meter > alert["meter_max"]):
            continue

        cap = f"🔔 **ملک جدید مطابق با فیلتر شما ثبت شد!**\n\n{text[:300]}..."
        
        # استفاده از ایمپورت پویا برای جلوگیری از Circular Import
        from keyboards.templates import inline_action
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM files ORDER BY id DESC LIMIT 1")
        last_file = cur.fetchone()
        conn.close()
        fid = last_file["id"] if last_file else 1

        if photos:
            await send_pic(alert["user_id"], photos[0], cap, inline_action(fid))
        else:
            await send_msg(alert["user_id"], cap, inline_action(fid))


async def save_file(text, photos_list=None):
    k, kh, p, m, l = extract_info(text)
    photos_json = json.dumps(photos_list if photos_list else [])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO files (text, kind, khab, price, meter, location, photos) VALUES (?,?,?,?,?,?,?)",
        (text, k, kh, p, m, l, photos_json),
    )
    conn.commit()
    conn.close()
    
    await check_alerts_and_notify(text, k, kh, p, m, photos_list)


def set_session(user_id, **kwargs):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO sessions (user_id, page) VALUES (?, 1)", (user_id,))
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
    if bmin is not None and bmax is not None:
        q += " AND price BETWEEN ? AND ?"
        params.extend([bmin, bmax])
    if mmin is not None and mmax is not None:
        q += " AND meter BETWEEN ? AND ?"
        params.extend([mmin, mmax])

    limit = 5
    q += " LIMIT ? OFFSET ?"
    params.extend([limit, (page - 1) * limit])
    cur.execute(q, params)
    res = cur.fetchall()
    conn.close()
    return res


async def send_msg(cid, text, kb=None):
    payload = {
        "chat_id": cid,
        "text": f"{text}\n\n📢 *کانال اصلی:*\n{MAIN_CHANNEL_URL}",
        "parse_mode": "Markdown",
    }
    if kb:
        payload["reply_markup"] = kb
    async with httpx.AsyncClient() as client:
        return await client.post(f"{BASE_URL}/sendMessage", json=payload)


async def send_pic(cid, pid, cap, kb=None):
    payload = {
        "chat_id": cid,
        "photo": pid,
        "caption": f"{cap}\n\n📢 *کانال اصلی:*\n{MAIN_CHANNEL_URL}",
        "parse_mode": "Markdown",
    }
    if kb:
        payload["reply_markup"] = kb
    async with httpx.AsyncClient() as client:
        return await client.post(f"{BASE_URL}/sendPhoto", json=payload)


async def send_media_group(cid, media_list):
    payload = {
        "chat_id": cid,
        "media": media_list
    }
    async with httpx.AsyncClient() as client:
        return await client.post(f"{BASE_URL}/sendMediaGroup", json=payload)
