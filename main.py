from fastapi import FastAPI, Request
import requests
import sqlite3
import re

TOKEN = "296563931:Noek97TDpcSv15596h1wEG1cVjtdCGJyNg8"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
MAIN_CHANNEL_URL = "https://ble.ir/BROKER_amlak"

app = FastAPI()

# ---------------------- HEALTH CHECK ----------------------
@app.get("/")
def home():
    return {"ok": True}

# ---------------------- Database ----------------------

def get_db():
    conn = sqlite3.connect("broker_final.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            kind TEXT,
            khab TEXT,
            price INTEGER,
            meter INTEGER,
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
            meter_min INTEGER,
            meter_max INTEGER,
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
    conn.close()

init_db()

# ---------------------- Extract Info ----------------------

def extract_info(text):
    kind = "رهن_اجاره" if any(w in text for w in ["رهن", "اجاره"]) else "فروش"

    kh_match = re.search(r"(\d+)\s*(خواب|خوابه)", text)
    khab = f"{kh_match.group(1)}خواب" if kh_match else None

    price = None
    b_match = re.search(r"(\d+)\s*(میلیارد|میلیاردی)", text)
    if b_match:
        price = int(b_match.group(1)) * 1_000_000_000
    else:
        m_match = re.search(r"(\d+)\s*(میلیون|میلیونی)", text)
        if m_match:
            price = int(m_match.group(1)) * 1_000_000

    meter_match = re.search(r"(\d+)\s*(متر|م)", text)
    meter = int(meter_match.group(1)) if meter_match else None

    loc_match = re.search(r"(جنت‌آباد|تهران|فردیس|کرج|شهرک|منطقه\s*\d+)", text)
    location = loc_match.group(0) if loc_match else "نامشخص"

    return kind, khab, price, meter, location

# ---------------------- Save File ----------------------

def save_file(text, photo_id=None):
    kind, khab, price, meter, loc = extract_info(text)
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO files (text, kind, khab, price, meter, location, photo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (text, kind, khab, price, meter, loc, photo_id))

    conn.commit()
    conn.close()

# ---------------------- Sessions ----------------------

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

# ---------------------- Search ----------------------

def search_files(kind, khab, bmin, bmax, mmin, mmax, page):
    conn = get_db()
    cur = conn.cursor()

    q = "SELECT * FROM files WHERE kind=?"
    params = [kind]

    if khab:
        q += " AND khab=?"
        params.append(khab)

    if kind == "فروش" and bmin and bmax:
        q += " AND price BETWEEN ? AND ?"
        params.extend([bmin, bmax])

    if mmin and mmax:
        q += " AND meter BETWEEN ? AND ?"
        params.extend([mmin, mmax])

    limit = 5
    offset = (page - 1) * limit

    q += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(q, params)
    res = cur.fetchall()

    conn.close()
    return res

# ---------------------- Send Messages ----------------------

def send_msg(chat_id, text, kb=None):
    footer = f"\n\n📢 *مشاهده لیست کامل در کانال اصلی:*\n{MAIN_CHANNEL_URL}"
    payload = {
        "chat_id": chat_id,
        "text": f"{text}{footer}",
        "parse_mode": "Markdown"
    }
    if kb:
        payload["reply_markup"] = kb

    return requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_pic(chat_id, photo_id, caption, kb=None):
    footer = f"\n\n📢 *مشاهده در کانال اصلی:*\n{MAIN_CHANNEL_URL}"
    payload = {
        "chat_id": chat_id,
        "photo": photo_id,
        "caption": f"{caption}{footer}",
        "parse_mode": "Markdown"
    }
    if kb:
        payload["reply_markup"] = kb

    return requests.post(f"{BASE_URL}/sendPhoto", json=payload)

# ---------------------- Keyboards ----------------------

def kb_main():
    return {
        "keyboard": [
            [{"text": "🏠 خرید"}, {"text": "🔑 رهن و اجاره"}],
            [{"text": "🔍 جستجوی سریع"}, {"text": "⭐ علاقه‌مندی‌ها"}]
        ],
        "resize_keyboard": True
    }

def kb_khab():
    return {
        "keyboard": [
            [{"text": "۲ خواب"}, {"text": "۳ خواب"}],
            [{"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def kb_budje():
    return {
        "keyboard": [
            [{"text": "۲۰ تا ۳۰ میلیارد"}, {"text": "۳۰ تا ۴۰ میلیارد"}],
            [{"text": "۴۰ تا ۵۰ میلیارد"}, {"text": "۵۰ میلیارد به بالا"}]
        ],
        "resize_keyboard": True
    }

def kb_meter():
    return {
        "keyboard": [
            [{"text": "کمتر از 100 متر"}, {"text": "100 تا 150 متر"}],
            [{"text": "150 تا 200 متر"}, {"text": "بیشتر از 200 متر"}]
        ],
        "resize_keyboard": True
    }

def kb_next():
    return {
        "keyboard": [
            [{"text": "صفحه بعد"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def inline_action(fid):
    return {
        "inline_keyboard": [
            [{"text": "🚀 مشاهده در کانال اصلی", "url": MAIN_CHANNEL_URL}],
            [{"text": "⭐ افزودن به علاقه‌مندی", "callback_data": f"fav:{fid}"}]
        ]
    }

# ---------------------- Webhook (اصلاح‌شده و سازگار با بله) ----------------------

@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    # پیام خصوصی یا کانال همیشه داخل message است
    msg = data.get("message") or data.get("body") or data.get("data")
    if not msg:
        return {"ok": True}

    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid = chat.get("id")
    ctype = chat.get("type")

    # پیام کانال
    if ctype == "channel":
        pid = msg["photo"][-1]["file_id"] if "photo" in msg else None
        if "موجود" in txt:
            save_file(txt, pid)
        return {"ok": True}

    # پیام خصوصی
    if ctype == "private":
        user_id = cid

        if txt == "/start" or txt == "بازگشت به منو اصلی":
            set_session(user_id, page=1)
            send_msg(cid,
                     "سلام جناب بهادر عزیز به ربات هوشمند **BROKER Amlak** خوش آمدید.\n"
                     "لطفاً نوع عملیات را انتخاب کنید:",
                     kb_main())
            return {"ok": True}

        elif txt in ["🏠 خرید", "🔑 رهن و اجاره"]:
            kind = "فروش" if "خرید" in txt else "رهن_اجاره"
            set_session(user_id, kind=kind, page=1)
            send_msg(cid, "تعداد خواب مورد نظر را انتخاب کنید:", kb_khab())
            return {"ok": True}

        elif txt in ["۲ خواب", "۳ خواب"]:
            set_session(user_id, khab=txt.replace(" ", ""))
            s = get_session(user_id)

            if s["kind"] == "فروش":
                send_msg(cid, "💰 بازه بودجه را انتخاب کنید:", kb_budje())
            else:
                send_msg(cid, "📏 متراژ مورد نظر را انتخاب کنید:", kb_meter())
            return {"ok": True}

        elif txt in ["۲۰ تا ۳۰ میلیارد", "۳۰ تا ۴۰ میلیارد", "۴۰ تا ۵۰ میلیارد", "۵۰ میلیارد به بالا"]:
            b_map = {
                "۲۰ تا ۳۰ میلیارد": (20, 30),
                "۳۰ تا ۴۰ میلیارد": (30, 40),
                "۴۰ تا ۵۰ میلیارد": (40, 50),
                "۵۰ میلیارد به بالا": (50, 999)
            }
            bmin, bmax = b_map[txt]

            set_session(user_id, budje_min=bmin, budje_max=bmax)
            send_msg(cid, "📏 متراژ مورد نظر را انتخاب کنید:", kb_meter())
            return {"ok": True}

        elif txt in ["کمتر از 100 متر", "100 تا 150 متر", "150 تا 200 متر", "بیشتر از 200 متر"]:
            m_map = {
                "کمتر از 100 متر": (0, 100),
                "100 تا 150 متر": (100, 150),
                "150 تا 200 متر": (150, 200),
                "بیشتر از 200 متر": (200, 999)
            }
            mmin, mmax = m_map.get(txt, (0, 999))

            set_session(user_id, meter_min=mmin, meter_max=mmax)
            s = get_session(user_id)

            results = search_files(
                s["kind"], s["khab"],
                s["budje_min"], s["budje_max"],
                s["meter_min"], s["meter_max"],
                s["page"]
            )

            if not results:
                send_msg(cid, "❌ متاسفانه موردی پیدا نشد.", kb_main())
            else:
                for r in results:
                    cap = f"🏠 **پیشنهاد ویژه**\n\n{r['text'][:200]}..."
                    if r["photo_id"]:
                        send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else:
                        send_msg(cid, cap, inline_action(r["id"]))

                send_msg(cid, "📄 صفحه بعد:", kb_next())
            return {"ok": True}

        elif txt == "صفحه بعد":
            s = get_session(user_id)
            set_session(user_id, page=s["page"] + 1)
            s = get_session(user_id)

            results = search_files(
                s["kind"], s["khab"],
                s["budje_min"], s["budje_max"],
                s["meter_min"], s["meter_max"],
                s["page"]
            )

            if not results:
                send_msg(cid, "پایان لیست.", kb_main())
            else:
                for r in results:
                    cap = f"🏠 **پیشنهاد ویژه**\n\n{r['text'][:200]}..."
                    if r["photo_id"]:
                        send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else:
                        send_msg(cid, cap, inline_action(r["id"]))

                send_msg(cid, "📄 صفحه بعد:", kb_next())
            return {"ok": True}

        elif "جستجوی سریع" in txt:
            send_msg(cid, "🔍 نام محله یا متراژ را بفرستید.")
            return {"ok": True}

        else:
            conn = get_db()
            cur = conn.cursor()

            cur.execute("SELECT * FROM files WHERE text LIKE ? LIMIT 5", (f"%{txt}%",))
            rows = cur.fetchall()

            if not rows:
                send_msg(cid, "موردی یافت نشد.", kb_main())
            else:
                for r in rows:
                    cap = f"🏠 **فایل پیشنهادی**\n\n{r['text'][:150]}..."
                    if r["photo_id"]:
                        send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else:
                        send_msg(cid, cap, inline_action(r["id"]))

            conn.close()
            return {"ok": True}

    return {"ok": True}
