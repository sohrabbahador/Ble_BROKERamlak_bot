from fastapi import FastAPI, Request
import requests
import sqlite3
import re

TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
MAIN_CHANNEL_URL = "https://ble.ir/BROKER_amlak"

app = FastAPI()


@app.get("/")
def home(): 
    return {"ok": True}


def get_db():
    conn = sqlite3.connect("broker_final.db", check_same_thread=False)
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
        "location TEXT, "
        "photo_id TEXT)"
    )
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
    cur.execute(
        "CREATE TABLE IF NOT EXISTS favorites ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER, "
        "file_id INTEGER)"
    )
    conn.commit()
    conn.close()


init_db()


# --- تبدیل هوشمند اعداد فارسی/عربی به انگلیسی ---
def fa_to_en(text):
    if not text:
        return ""
    translation_table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return text.translate(translation_table)


# --- استخراج هوشمند اطلاعات پست‌ها بر اساس نمونه‌های ارسالی شما ---
def extract_info(text):
    text_en = fa_to_en(text)
    
    # ۱. تشخیص نوع معامله (خرید/فروش یا رهن/اجاره)
    kind = "رهن_اجاره" if any(w in text for w in ["رهن", "اجاره", "رهن_اجاره"]) else "فروش"
    
    # ۲. استخراج تعداد خواب (پشتیبانی از: ۳ خواب، ۲ اتاق خواب، تک خواب و تبدیل به فرمت دکمه‌ها مثل "۳ خواب")
    khab = None
    kh_match = re.search(r"(\d+)\s*(?:اتاق\s*)?خواب", text_en)
    if kh_match:
        num = kh_match.group(1)
        # تبدیل مجدد به فارسی جهت انطباق با متن دکمه‌های ربات
        num_fa = num.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        khab = f"{num_fa} خواب"
    elif "تک خواب" in text or "یک خواب" in text:
        khab = "۱ خواب"
        
    # ۳. استخراج قیمت کل (فیلتر کردن عبارت "قیمت:" یا "رهن کامل:")
    price = None
    # تلاش برای پیدا کردن سطر قیمت کل و جلوگیری از استخراج اشتباه "متری"
    price_line = ""
    for line in text_en.split("\n"):
        if any(keyword in line for keyword in ["قیمت", "رهن", "ودیعه"]):
            if "متری" not in line: # نادیده گرفتن قیمت متری
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
        
    # اگر در لاین اختصاصی پیدا نشد، یک جستجوی کلی انجام بده
    if not price:
        b_match = re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text_en)
        m_match = re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
        if b_match:
            price = int(b_match.group(1)) * 10**9
            if m_match:
                price += int(m_match.group(1)) * 10**6
        elif m_match:
            price = int(m_match.group(1)) * 10**6

    # ۴. استخراج متراژ
    meter_match = re.search(r"متراژ[:\s]*(\d+)", text_en) or re.search(r"(\d+)\s*متر", text_en)
    meter = int(meter_match.group(1)) if meter_match else None
    
    # ۵. استخراج محدوده/لوکیشن
    loc_match = re.search(r"موقعیت[:\s]*(.*)", text) or re.search(r"(جنت‌آباد|تهران|منطقه\s*\d+|ستاری)", text)
    location = loc_match.group(1).strip() if loc_match else "نامشخص"
    
    return kind, khab, price, meter, location


def save_file(text, photo_id=None):
    k, kh, p, m, l = extract_info(text)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO files (text, kind, khab, price, meter, location, photo_id) VALUES (?,?,?,?,?,?,?)", 
        (text, k, kh, p, m, l, photo_id)
    )
    conn.commit()
    conn.close()


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


# --- طراحی دکمه‌های متنی کیبورد بله ---
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
            [{"text": "۱ خواب"}, {"text": "۲ خواب"}], 
            [{"text": "۳ خواب"}, {"text": "۴ خواب و بیشتر"}],
            [{"text": "بازگشت به منو اصلی"}]
        ], 
        "resize_keyboard": True
    }


# بازه‌های خرید (میلیاردی بزرگ)
def kb_budje_forosh(): 
    return {
        "keyboard": [
            [{"text": "۲۰ تا ۳۰ میلیارد"}, {"text": "۳۰ تا ۴۰ میلیارد"}], 
            [{"text": "۴۰ تا ۵۰ میلیارد"}, {"text": "۵۰ میلیارد به بالا"}],
            [{"text": "بازگشت به منو اصلی"}]
        ], 
        "resize_keyboard": True
    }


# بازه‌های رهن و اجاره (میلیاردی کوچک و متناسب)
def kb_budje_rahn(): 
    return {
        "keyboard": [
            [{"text": "کمتر از ۲ میلیارد"}, {"text": "۲ تا ۴ میلیارد"}], 
            [{"text": "۴ تا ۶ میلیارد"}, {"text": "۶ میلیارد به بالا"}],
            [{"text": "بازگشت به منو اصلی"}]
        ], 
        "resize_keyboard": True
    }


def kb_meter(): 
    return {
        "keyboard": [
            [{"text": "کمتر از ۱۰۰ متر"}, {"text": "۱۰۰ تا ۱۵۰ متر"}], 
            [{"text": "۱۵۰ تا ۲۰۰ متر"}, {"text": "بیشتر از ۲۰۰ متر"}],
            [{"text": "بازگشت به منو اصلی"}]
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
            [{"text": "🚀 مشاهده در کانال", "url": MAIN_CHANNEL_URL}], 
            [{"text": "⭐ افزودن به علاقه‌مندی", "callback_data": f"fav:{fid}"}]
        ]
    }


@app.post("/")
async def webhook(req: Request):
    data = await req.json()
    
    # مدیریت لایک و علاقه‌مندی‌ها (Inline)
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = d_val.split(":")[1]
            conn = get_db()
            cur = conn.cursor()
            # بررسی تکراری نبودن
            cur.execute("SELECT * FROM favorites WHERE user_id=? AND file_id=?", (cid, file_id))
            if not cur.fetchone():
                cur.execute("INSERT INTO favorites (user_id, file_id) VALUES (?,?)", (cid, file_id))
                conn.commit()
                send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else:
                send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
            conn.close()
        return {"ok": True}
        
    msg = data.get("message") or data.get("body")
    if not msg: 
        return {"ok": True}
        
    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    
    # دریافت و ذخیره فایل از کانال شما
    if ctype == "channel":
        pid = msg["photo"][-1]["file_id"] if "photo" in msg else None
        if "موجود" in txt: 
            save_file(txt, pid)
        return {"ok": True}
        
    # پردازش چت خصوصی با کاربر
    if ctype == "private":
        user_id = cid
        s = get_session(user_id)
        
        # هندل کردن شروع مجدد و برگشت
        if txt == "/start" or txt == "بازگشت به منو اصلی":
            set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None)
            send_msg(cid, "سلام سهراب بهادر عزیز، به ربات هوشمند بروکر خوش آمدید. 🏠\n\nنوع عملیات مورد نظرتان را انتخاب کنید:", kb_main())
            
        elif txt == "🏠 خرید":
            set_session(user_id, kind="فروش", page=1)
            send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())
            
        elif txt == "🔑 رهن و اجاره":
            set_session(user_id, kind="رهن_اجاره", page=1)
            send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())
            
        elif "خواب" in txt:
            # یکپارچه‌سازی متون ورودی
            clean_khab = txt.replace(" ", "")
            if "۴" in clean_khab or "بیشتر" in clean_khab:
                clean_khab = "4خواب" # فرمت دیتابیس
            set_session(user_id, khab=txt.strip())
            s = get_session(user_id)
            
            # تغییر داینامیک کیبورد بودجه بر اساس نوع معامله (فروش یا رهن)
            if s and s["kind"] == "فروش":
                send_msg(cid, "بازه بودجه خرید را انتخاب کنید:", kb_budje_forosh())
            else:
                send_msg(cid, "بازه رهن مورد نظرتان را انتخاب کنید:", kb_budje_rahn())
                
        elif any(w in txt for w in ["میلیارد", "میلیونی"]):
            # نقشه‌ریزی مبالغ برای خرید یا رهن به صورت منعطف
            b_map = {
                # دکمه‌های خرید
                "۲۰ تا ۳۰ میلیارد": (20 * 10**9, 30 * 10**9), 
                "۳۰ تا ۴۰ میلیارد": (30 * 10**9, 40 * 10**9), 
                "۴۰ تا ۵۰ میلیارد": (40 * 10**9, 50 * 10**9), 
                "۵۰ میلیارد به بالا": (50 * 10**9, 999 * 10**9),
                # دکمه‌های رهن و اجاره
                "کمتر از ۲ میلیارد": (0, 2 * 10**9),
                "۲ تا ۴ میلیارد": (2 * 10**9, 4 * 10**9),
                "۴ تا ۶ میلیارد": (4 * 10**9, 6 * 10**9),
                "۶ میلیارد به بالا": (6 * 10**9, 999 * 10**9)
            }
            v = b_map.get(txt, (0, 999 * 10**9))
            set_session(user_id, budje_min=v[0], budje_max=v[1])
            send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter())
            
        elif "متر" in txt:
            m_map = {
                "کمتر از ۱۰۰ متر": (0, 100), 
                "۱۰۰ تا ۱۵۰ متر": (100, 150), 
                "۱۵۰ تا ۲۰۰ متر": (150, 200), 
                "بیشتر از ۲۰۰ متر": (200, 999)
            }
            v = m_map.get(txt, (0, 999))
            set_session(user_id, meter_min=v[0], meter_max=v[1])
            
            s = get_session(user_id)
            if s:
                res = search_files(s["kind"], s["khab"], s["budje_min"], s["budje_max"], s["meter_min"], s["meter_max"], s["page"])
                if not res: 
                    send_msg(cid, "❌ متاسفانه ملکی با این مشخصات یافت نشد. فیلترها را تغییر دهید یا مجدداً تلاش کنید.", kb_main())
                else:
                    for r in res:
                        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
                        if r["photo_id"]: 
                            send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                        else: 
                            send_msg(cid, cap, inline_action(r["id"]))
                    send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())
            else:
                send_msg(cid, "خطایی رخ داد. لطفاً مجدداً جستجو را آغاز کنید.", kb_main())
                
        elif txt == "صفحه بعد":
            s = get_session(user_id)
            if s:
                next_page = (s["page"] or 1) + 1
                set_session(user_id, page=next_page)
                s = get_session(user_id)
                res = search_files(s["kind"], s["khab"], s["budje_min"], s["budje_max"], s["meter_min"], s["meter_max"], s["page"])
                if not res: 
                    send_msg(cid, "🏁 به انتهای لیست فایل‌های موجود رسیدید.", kb_main())
                else:
                    for r in res:
                        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
                        if r["photo_id"]: 
                            send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                        else: 
                            send_msg(cid, cap, inline_action(r["id"]))
                    send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())
            else:
                send_msg(cid, "نشست کاربری شما یافت نشد. بازگشت به منو اصلی...", kb_main())
                
        elif txt == "⭐ علاقه‌مندی‌ها":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT file_id FROM favorites WHERE user_id=?", (user_id,))
            favs = cur.fetchall()
            conn.close()
            
            if not favs: 
                send_msg(cid, "لیست علاقه‌مندی‌های شما در حال حاضر خالی است.")
            else:
                conn = get_db()
                cur = conn.cursor()
                send_msg(cid, "⭐ **لیست فایل‌های مورد علاقه شما:**")
                for f in favs:
                    cur.execute("SELECT * FROM files WHERE id=?", (f["file_id"],))
                    r = cur.fetchone()
                    if r:
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        if r["photo_id"]: 
                            send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                        else: 
                            send_msg(cid, r["text"], inline_action(r["id"]))
                conn.close()
                
        elif "🔍 جستجوی سریع" in txt: 
            send_msg(cid, "کافیست نام محله (مثلاً جنت‌آباد) یا ویژگی مورد نظرتان را بنویسید و بفرستید تا سریعاً جستجو کنم:")
            
        else:
            # جستجوی متنی آزاد در دیتابیس
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM files WHERE text LIKE ? LIMIT 5", (f"%{txt}%",))
            res = cur.fetchall()
            conn.close()
            if not res: 
                send_msg(cid, "❌ موردی با این مشخصات یافت نشد. جستجوی متنی دیگری انجام دهید یا از دکمه‌های منو استفاده کنید.", kb_main())
            else:
                for r in res:
                    cap = f"🔍 **نتیجه جستجوی سریع**\n\n{r['text'][:300]}..."
                    if r["photo_id"]: 
                        send_pic(cid, r["photo_id"], cap, inline_action(r["id"]))
                    else: 
                        send_msg(cid, cap, inline_action(r["id"]))
                        
    return {"ok": True}
