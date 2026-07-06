from fastapi import FastAPI, Request
import requests, sqlite3, re

TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
MAIN_CHANNEL_URL = "https://ble.ir/BROKER_amlak"

app = FastAPI()

@app.get("/")
def home(): return {"ok": True}

def get_db():
    conn = sqlite3.connect("broker_final.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, kind TEXT, khab TEXT, price INTEGER, meter INTEGER, location TEXT, photo_id TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS sessions (user_id INTEGER PRIMARY KEY, kind TEXT, khab TEXT, budje_min INTEGER, budje_max INTEGER, meter_min INTEGER, meter_max INTEGER, page INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS favorites (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, file_id INTEGER)")
    conn.commit(); conn.close()

init_db()

def extract_info(text):
    kind = "رهن_اجاره" if any(w in text for w in ["رهن", "اجاره"]) else "فروش"
    kh_match = re.search(r"(\d+)\s*(خواب|خوابه)", text)
    khab = f"{kh_match.group(1)}خواب" if kh_match else None
    price = None
    b_match = re.search(r"(\d+)\s*(میلیارد|میلیاردی)", text)
    if b_match: price = int(b_match.group(1)) * 10**9
    elif (m_match := re.search(r"(\d+)\s*(میلیون|میلیونی)", text)): price = int(m_match.group(1)) * 10**6
    meter_match = re.search(r"(\d+)\s*(متر|م)", text)
    meter = int(meter_match.group(1)) if meter_match else None
    loc_match = re.search(r"(جنت‌آباد|تهران|فردیس|کرج|شهرک|منطقه\s*\d+)", text)
    location = loc_match.group(0) if loc_match else "نامشخص"
    return kind, khab, price, meter, location

def save_file(text, photo_id=None):
    k, kh, p, m, l = extract_info(text)
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO files (text, kind, khab, price, meter, location, photo_id) VALUES (?,?,?,?,?,?,?)", (text, k, kh, p, m, l, photo_id))
    conn.commit(); conn.close()

def set_session(user_id, **kwargs):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO sessions (user_id, page) VALUES (?, 1)", (user_id,))
    for key, value in kwargs.items(): cur.execute(f"UPDATE sessions SET {key}=? WHERE user_id=?", (value, user_id))
    conn.commit(); conn.close()

def get_session(user_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE user_id=?", (user_id,))
    res = cur.fetchone(); conn.close()
    return res

def search_files(kind, khab, bmin, bmax, mmin, mmax, page):
    conn = get_db(); cur = conn.cursor()
    q, params = "SELECT * FROM files WHERE kind=?", [kind]
    if khab: q += " AND khab=?"; params.append(khab)
    if kind == "فروش" and bmin and bmax: q += " AND price BETWEEN ? AND ?"; params.extend([bmin, bmax])
    if mmin and mmax: q += " AND meter BETWEEN ? AND ?"; params.extend([mmin, mmax])
    limit = 5; q += " LIMIT ? OFFSET ?"; params.extend([limit, (page-1)*limit])
    cur.execute(q, params); res = cur.fetchall(); conn.close()
    return res

def send_msg(cid, text, kb=None):
    payload = {"chat_id": cid, "text": f"{text}\n\n📢 *کانال اصلی:*\n{MAIN_CHANNEL_URL}", "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    return requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_pic(cid, pid, cap, kb=None):
    payload = {"chat_id": cid, "photo": pid, "caption": f"{cap}\n\n📢 *کانال اصلی:*\n{MAIN_CHANNEL_URL}", "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    return requests.post(f"{BASE_URL}/sendPhoto", json=payload)

def kb_main(): return {"keyboard": [[{"text": "🏠 خرید"}, {"text": "🔑 رهن و اجاره"}], [{"text": "🔍 جستجوی سریع"}, {"text": "⭐ علاقه‌مندی‌ها"}]], "resize_keyboard": True}

def kb_khab(): return {"keyboard": [[{"text": "۱ خواب"}, {"text": "۲ خواب"}], [{"text": "۳ خواب"}, {"text": "۴ خواب و بیشتر"}]], "resize_keyboard": True}
def kb_budje(): return {"keyboard": [[{"text": "۲۰ تا ۳۰ میلیارد"}, {"text": "۳۰ تا ۴۰ میلیارد"}], [{"text": "۴۰ تا ۵۰ میلیارد"}, {"text": "۵۰ میلیارد به بالا"}]], "resize_keyboard": True}
def kb_meter(): return {"keyboard": [[{"text": "کمتر از ۱۰۰ متر"}, {"text": "۱۰۰ تا ۱۵۰ متر"}], [{"text": "۱۵۰ تا ۲۰۰ متر"}, {"text": "بیشتر از ۲۰۰ متر"}]], "resize_keyboard": True}
def kb_next(): return {"keyboard": [[{"text": "صفحه بعد"}, {"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True}
def inline_action(fid): return {"inline_keyboard": [[{"text": "🚀 مشاهده در کانال", "url": MAIN_CHANNEL_URL}], [{"text": "⭐ افزودن به علاقه‌مندی", "callback_data": f"fav:{fid}"}]]}

@app.post("/")
async def webhook(req: Request):
    data = await req.json()
    if "callback_query" in data:
        cb = data["callback_query"]; cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO favorites (user_id, file_id) VALUES (?,?)", (cid, d_val.split(":")[1]))
            conn.commit(); conn.close()
            send_msg(cid, "✅ اضافه شد به علاقه‌مندی‌ها.")
        return {"ok": True}
    msg = data.get("message") or data.get("body")
    if not msg: return {"ok": True}
    chat = msg.get("chat", {}); txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    if ctype == "channel":
        pid = msg["photo"][-1]["file_id"] if "photo" in msg else None
        if "موجود" in txt: save_file(txt, pid)
        return {"ok": True}
    if ctype == "private":
        user_id = cid; s = get_session(user_id)
        if txt == "/start" or txt == "بازگشت به منو اصلی":
            set_session(user_id, page=1); send_msg(cid, "نوع عملیات را انتخاب کنید:", kb_main())
        elif txt == "🏠 خرید":
            set_session(user_id, kind="فروش", page=1); send_msg(cid, "تعداد خواب:", kb_khab())
        elif txt == "🔑 رهن و اجاره":
            set_session(user_id, kind="رهن_اجاره", page=1); send_msg(cid, "تعداد خواب:", kb_khab())
        elif "خواب" in txt:
            set_session(user_id, khab=txt.replace(" ", "")); s = get_session(user_id)
            send_msg(cid, "بودجه را انتخاب کنید:" if s["kind"]=="فروش" else "متراژ را انتخاب کنید:", kb_budje() if s["kind"]=="فروش" else kb_meter())
        elif any(w in txt for w in ["میلیارد", "میلیونی"]):
            b_map = {"۲۰ تا ۳۰ میلیارد": (20, 30), "۳۰ تا ۴۰ میلیارد": (30, 40), "۴۰ تا ۵۰ میلیارد": (40, 50), "۵۰ میلیارد به بالا": (50, 999)}
            v = b_map.get(txt, (0, 999)); set_session(user_id, budje_min=v[0]*10**9, budje_max=v[1]*10**9)
            send_msg(cid, "متراژ را انتخاب کنید:", kb_meter())
        elif "متر" in txt:
            m_map = {"کمتر از ۱۰۰ متر": (0, 100), "۱۰۰ تا ۱۵۰ متر": (100, 150), "۱۵۰ تا ۲۰۰ متر": (150, 200), "بیشتر از ۲۰۰ متر": (200, 999)}
            v = m_map.get(txt, (0, 999)); set_session(user_id, meter_min=v[0], meter_max=v[1])
            s = get_session(user_id); res = search_files(s["kind"], s["khab"], s["budje_min"], s["budje_max"], s["meter_min"], s["meter_max"], s["page"])
            if not res: send_msg(cid, "❌ موردی یافت نشد.", kb_main())
            else:
                for r in res:
                    cap = f"🏠 **پیشنهاد ویژه**\n\n{r['text'][:200]}..."
                    if r["photo_id"]: send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else: send_msg(cid, cap, inline_action(r["id"]))
                send_msg(cid, "📄 برای موارد بیشتر:", kb_next())
        elif txt == "صفحه بعد":
            set_session(user_id, page=s["page"]+1); s = get_session(user_id)
            res = search_files(s["kind"], s["khab"], s["budje_min"], s["budje_max"], s["meter_min"], s["meter_max"], s["page"])
            if not res: send_msg(cid, "پایان لیست.", kb_main())
            else:
                for r in res:
                    cap = f"🏠 **پیشنهاد ویژه**\n\n{r['text'][:200]}..."
                    if r["photo_id"]: send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else: send_msg(cid, cap, inline_action(r["id"]))
                send_msg(cid, "📄 برای موارد بیشتر:", kb_next())
        elif txt == "⭐ علاقه‌مندی‌ها":
            conn = get_db(); cur = conn.cursor(); cur.execute("SELECT file_id FROM favorites WHERE user_id=?", (user_id,))
            favs = cur.fetchall(); conn.close()
            if not favs: send_msg(cid, "لیست شما خالی است.")
            else:
                conn = get_db(); cur = conn.cursor()
                for f in favs:
                    cur.execute("SELECT * FROM files WHERE id=?", (f["file_id"],))
                    r = cur.fetchone()
                    if r:
                        cap = f"⭐ **علاقه‌مندی**\n\n{r['text'][:200]}..."
                        if r["photo_id"]: send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                        else: send_msg(cid, cap, inline_action(r["id"]))
                conn.close()
        elif "🔍 جستجوی سریع" in txt: send_msg(cid, "نام محله یا متراژ را بفرستید.")
        else:
            conn = get_db(); cur = conn.cursor(); cur.execute("SELECT * FROM files WHERE text LIKE ? LIMIT 5", (f"%{txt}%",))
            res = cur.fetchall(); conn.close()
            if not res: send_msg(cid, "موردی یافت نشد.", kb_main())
            else:
                for r in res:
                    cap = f"🔍 **نتیجه جستجو**\n\n{r['text'][:200]}..."
                    if r["photo_id"]: send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else: send_msg(cid, cap, inline_action(r["id"]))
    return {"ok": True}
