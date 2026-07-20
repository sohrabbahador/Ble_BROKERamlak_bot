# core.py
import json
import re
import httpx
from config import db, TOKEN, BASE_URL, MAIN_CHANNEL_URL, ADMIN_ID

def init_db():
    """ایجاد ایندکس‌های یکتا برای حفظ ساختار کلیدهای اصلی مشابه با دیتابیس قبلی"""
    db["sessions"].create_index("user_id", unique=True)
    db["users"].create_index("user_id", unique=True)
    
    # شبیه‌سازی ساختار AUTOINCREMENT دیتابیس برای آیدی فایل‌ها، آلارم‌ها و علاقه‌مندی‌ها
    if db["counters"].count_documents({"_id": "file_id"}) == 0:
        db["counters"].insert_one({"_id": "file_id", "sequence_value": 0})
    if db["counters"].count_documents({"_id": "alert_id"}) == 0:
        db["counters"].insert_one({"_id": "alert_id", "sequence_value": 0})
    if db["counters"].count_documents({"_id": "fav_id"}) == 0:
        db["counters"].insert_one({"_id": "fav_id", "sequence_value": 0})


def get_next_sequence_value(sequence_name):
    """ایجاد شناسه عددی افزایشی خودکار مشابه با SQLite AUTOINCREMENT"""
    sequence_document = db["counters"].find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"sequence_value": 1}},
        return_document=True
    )
    return sequence_document["sequence_value"]


def register_user(user_id, first_name):
    db["users"].update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "first_name": first_name}},
        upsert=True
    )


def fa_to_en(text):
    if not text:
        return ""
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def extract_info(text):
    text_en = fa_to_en(text)
    kind = "رهن_اجاره" if any(w in text for w in ["رهن", "اجاره", "رهن_اجاره"]) else "فروش"

    # ۱. استخراج تعداد اتاق خواب
    khab = None
    kh_match = re.search(r"(\d+)\s*(?:اتاق\s*)?خواب", text_en)
    if kh_match:
        num = kh_match.group(1)
        num_fa = num.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        khab = f"{num_fa} خواب"
    elif "تک خواب" in text or "یک خواب" in text:
        khab = "۱ خواب"

    # ۲. استخراج قیمت و تبدیل رهن/اجاره (هر ۳۰ میلیون اجاره = ۱ میلیارد رهن)
    price = None
    if kind == "رهن_اجاره":
        rahn_value = 0
        ejare_value = 0
        
        b_rahn = re.search(r"(?:رهن|ودیعه).*?(\d+)\s*(?:میلیارد|میلیاردی)", text_en) or re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text_en)
        m_rahn = re.search(r"(?:رهن|ودیعه).*?(\d+)\s*(?:میلیون|میلیونی)", text_en) or re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
        m_ejare = re.search(r"اجاره.*?(\d+)\s*(?:میلیون|میلیونی)", text_en)
        
        if b_rahn:
            rahn_value += int(b_rahn.group(1)) * 10**9
        if m_rahn and not m_ejare:
            rahn_value += int(m_rahn.group(1)) * 10**6
            
        if m_ejare:
            ejare_value = int(m_ejare.group(1)) * 10**6
            
        converted_ejare = (ejare_value / (30 * 10**6)) * 10**9
        price = int(rahn_value + converted_ejare)
    else:
        billions = 0
        millions = 0
        b_match = re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text_en)
        m_match = re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
        if b_match:
            billions = int(b_match.group(1)) * 10**9
        if m_match:
            millions = int(m_match.group(1)) * 10**6
        price = billions + millions

    # ۳. استخراج متراژ
    meter_match = re.search(r"متراژ[:\s]*(\d+)", text_en) or re.search(r"(\d+)\s*متر", text_en)
    meter = int(meter_match.group(1)) if meter_match else None

    # ۴. استخراج موقعیت جغرافیایی
    loc_match = re.search(r"موقعیت[:\s]*(.*)", text) or re.search(r"(جنت‌آباد|تهران|منطقه\s*\d+|ستاری)", text)
    location = loc_match.group(1).strip() if loc_match else "نامشخص"

    return kind, khab, price, meter, location


async def check_alerts_and_notify(text, kind, khab, price, meter, photos):
    """بررسی آلارم‌های ثبت شده کاربران و ارسال نوتیفیکیشن در صورت تطابق ملک جدید"""
    alerts = list(db["alerts"].find({}))

    for alert in alerts:
        if alert.get("kind") and alert["kind"] != kind:
            continue
        if alert.get("khab") and alert["khab"] != khab:
            continue
        if alert.get("budje_min") is not None and (price is None or price < alert["budje_min"]):
            continue
        if alert.get("budje_max") is not None and (price is None or price > alert["budje_max"]):
            continue
        if alert.get("meter_min") is not None and (meter is None or meter < alert["meter_min"]):
            continue
        if alert.get("meter_max") is not None and (meter is None or meter > alert["meter_max"]):
            continue

        cap = f"🔔 **ملک جدید مطابق با فیلتر شما ثبت شد!**\n\n{text[:300]}..."
        
        # برای جلوگیری از ایمپورت چرخه‌ای، دکمه شیشه‌ای را از فایل کیبورد می‌خوانیم
        from keyboards import inline_action
        
        last_file = db["files"].find_one(sort=[("id", -1)])
        fid = last_file["id"] if last_file else 1

        if photos:
            await send_pic(alert["user_id"], photos[0], cap, inline_action(fid))
        else:
            await send_msg(alert["user_id"], cap, inline_action(fid))


async def save_file(text, photos_list=None):
    k, kh, p, m, l = extract_info(text)
    photos_json = json.dumps(photos_list if photos_list else [])
    
    file_id = get_next_sequence_value("file_id")
    
    db["files"].insert_one({
        "id": file_id,
        "text": text,
        "kind": k,
        "khab": kh,
        "price": p,
        "meter": m,
        "location": l,
        "photos": photos_json
    })
    
    await check_alerts_and_notify(text, k, kh, p, m, photos_list)


def set_session(user_id, **kwargs):
    db["sessions"].update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "page": 1}},
        upsert=True
    )
    if kwargs:
        db["sessions"].update_one(
            {"user_id": user_id},
            {"$set": kwargs}
        )


def get_session(user_id):
    return db["sessions"].find_one({"user_id": user_id})


def search_files(kind, khab, bmin, bmax, mmin, mmax, page):
    # شروع کوئری با نوع ملک (که اجباری است)
    query = {"kind": kind}

    # فیلتر تعداد خواب (اگر انتخاب شده باشد)
    if khab:
        query["khab"] = khab

    # فیلتر بودجه (به صورت منعطف)
    price_filter = {}
    if bmin is not None:
        price_filter["$gte"] = bmin
    if bmax is not None:
        price_filter["$lte"] = bmax

    if price_filter:  # اگر حداقل یا حداکثر بودجه مقدار داشت، به کوئری اضافه شود
        query["price"] = price_filter

    # فیلتر متراژ (به صورت منعطف)
    meter_filter = {}
    if mmin is not None:
        meter_filter["$gte"] = mmin
    if mmax is not None:
        meter_filter["$lte"] = mmax

    if meter_filter:  # اگر حداقل یا حداکثر متراژ مقدار داشت، به کوئری اضافه شود
        query["meter"] = meter_filter

    limit = 5
    skip = (page - 1) * limit

    res = list(db["files"].find(query).skip(skip).limit(limit))
    return res


async def send_msg(cid, text, kb=None):
    payload = {
        "chat_id": cid,
        "text": f"{text}",
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
        "caption": f"{cap}",
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
