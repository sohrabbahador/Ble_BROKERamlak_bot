# core.py
import json
import re
import httpx
from config import db, TOKEN, BASE_URL, MAIN_CHANNEL_URL, ADMIN_ID

def init_db():
    db["sessions"].create_index("user_id", unique=True)
    db["users"].create_index("user_id", unique=True)
    
    if db["counters"].count_documents({"_id": "file_id"}) == 0:
        db["counters"].insert_one({"_id": "file_id", "sequence_value": 0})
    if db["counters"].count_documents({"_id": "alert_id"}) == 0:
        db["counters"].insert_one({"_id": "alert_id", "sequence_value": 0})
    if db["counters"].count_documents({"_id": "fav_id"}) == 0:
        db["counters"].insert_one({"_id": "fav_id", "sequence_value": 0})

def get_next_sequence_value(sequence_name):
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

    khab = None
    kh_match = re.search(r"(\d+)\s*(?:اتاق\s*)?خواب", text_en)
    if kh_match:
        num = kh_match.group(1)
        num_fa = num.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        khab = f"{num_fa} خواب"
    elif "تک خواب" in text or "یک خواب" in text:
        khab = "۱ خواب"

    price = None
    if kind == "رهن_اجاره":
        rahn_value = 0
        ejare_value = 0
        b_rahn = re.search(r"(?:رهن|ودیعه).*?(\d+)\s*(?:میلیارد|میلیاردی)", text_en) or re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text_en)
        m_rahn = re.search(r"(?:رهن|ودیعه).*?(\d+)\s*(?:میلیون|میلیونی)", text_en) or re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
        m_ejare = re.search(r"اجاره.*?(\d+)\s*(?:میلیون|میلیونی)", text_en)
        
        if b_rahn: rahn_value += int(b_rahn.group(1)) * 1000000000
        if m_rahn and not m_ejare: rahn_value += int(m_rahn.group(1)) * 1000000
        if m_ejare: ejare_value = int(m_ejare.group(1)) * 1000000
            
        converted_ejare = (ejare_value / (30 * 1000000)) * 1000000000
        price = int(rahn_value + converted_ejare)
    else:
        billions, millions = 0, 0
        b_match = re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text_en)
        m_match = re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
        if b_match: billions = int(b_match.group(1)) * 1000000000
        if m_match: millions = int(m_match.group(1)) * 1000000
        price = billions + millions

    meter_match = re.search(r"متراژ[:\s]*(\d+)", text_en) or re.search(r"(\d+)\s*متر", text_en)
    meter = int(meter_match.group(1)) if meter_match else None

    loc_match = re.search(r"موقعیت[:\s]*(.*)", text) or re.search(r"(جنت‌آباد|تهران|منطقه\s*\d+|ستاری)", text)
    location = loc_match.group(1).strip() if loc_match else "نامشخص"

    return kind, khab, price, meter, location

async def check_alerts_and_notify(text, kind, khab, price, meter, photos):
    alerts = list(db["alerts"].find({}))
    for alert in alerts:
        if alert.get("kind") and alert["kind"] != kind: continue
        if alert.get("khab") and alert["khab"] != khab: continue
        if alert.get("budje_min") is not None and (price is None or price < alert["budje_min"]): continue
        if alert.get("budje_max") is not None and (price is None or price > alert["budje_max"]): continue
        if alert.get("meter_min") is not None and (meter is None or meter < alert["meter_min"]): continue
        if alert.get("meter_max") is not None and (meter is None or meter > alert["meter_max"]): continue

        cap = f"🔔 ملک جدید مطابق با فیلتر شما ثبت شد!\n\n{text[:300]}..."
        from keyboards import inline_action
        last_file = db["files"].find_one(sort=[("id", -1)])
        fid = last_file["id"] if last_file else 1

        if photos: await send_pic(alert["user_id"], photos[0], cap, inline_action(fid))
        else: await send_msg(alert["user_id"], cap, inline_action(fid))

async def save_file(text, photos_list=None):
    k, kh, p, m, l = extract_info(text)
    photos_json = json.dumps(photos_list if photos_list else [])
    file_id = get_next_sequence_value("file_id")
    
    db["files"].insert_one({
        "id": file_id, "text": text, "kind": k, "khab": kh,
        "price": p, "meter": m, "location": l, "photos": photos_json
    })
    await check_alerts_and_notify(text, k, kh, p, m, photos_list)

def set_session(user_id, **kwargs):
    db["sessions"].update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "page": 1}},
        upsert=True
    )
    if kwargs:
        db["sessions"].update_one({"user_id": user_id}, {"$set": kwargs})

def get_session(user_id):
    return db["sessions"].find_one({"user_id": user_id})

def search_files(kind, khab, bmin, bmax, mmin, mmax, page, cid=None, user_id=None):
    # ۱. تلاش اول: جستجوی کاملاً دقیق با تمام فیلترها
    query = {"kind": kind}
    if khab: query["khab"] = khab
    
    price_filter = {}
    if bmin is not None: price_filter["$gte"] = bmin
    if bmax is not None: price_filter["$lte"] = bmax
    if price_filter: query["price"] = price_filter

    meter_filter = {}
    if mmin is not None: meter_filter["$gte"] = mmin
    if mmax is not None: meter_filter["$lte"] = mmax
    if meter_filter: query["meter"] = meter_filter

    limit = 5
    skip = (page - 1) * limit
    results = list(db["files"].find(query).skip(skip).limit(limit))
    if results:
        return results

    # ۲. تلاش دوم: اگر با قیمت یا متراژ دقیق نتیجه‌ای پیدا نشد، فیلتر قیمت و متراژ را بردار و فقط روی نوع معامله و تعداد خواب تمرکز کن
    fallback_query = {"kind": kind}
    if khab: fallback_query["khab"] = khab
    results = list(db["files"].find(fallback_query).skip(skip).limit(limit))
    if results:
        return results

    # ۳. تلاش سوم: اگر باز هم نتیجه‌ای نبود، فقط بر اساس نوع معامله جستجو کن تا کاربر دست خالی نماند
    return list(db["files"].find({"kind": kind}).skip(skip).limit(limit))

async def send_msg(cid, text, kb=None):
    payload = {"chat_id": cid, "text": f"{text}", "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    async with httpx.AsyncClient() as client:
        return await client.post(f"{BASE_URL}/sendMessage", json=payload)

async def send_pic(cid, pid, cap, kb=None):
    payload = {"chat_id": cid, "photo": pid, "caption": f"{cap}", "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    async with httpx.AsyncClient() as client:
        return await client.post(f"{BASE_URL}/sendPhoto", json=payload)

async def send_media_group(cid, media_list):
    payload = {"chat_id": cid, "media": media_list}
    async with httpx.AsyncClient() as client:
        return await client.post(f"{BASE_URL}/sendMediaGroup", json=payload)

def push_history(user_id, step_name):
    db["sessions"].update_one(
        {"user_id": user_id},
        {"$push": {"history": {"$each": [step_name], "$slice": -10}}},
        upsert=True
    )

async def show_results(cid, res, is_fav=False):
    if not res:
        await send_msg(cid, "❌ هیچ ملکی با این مشخصات یافت نشد.")
        return
    for item in res:
        photos = json.loads(item.get("photos", "[]"))
        cap = item.get("text", "")
        fid = item.get("id")
        from keyboards import inline_action
        kb = inline_action(fid)
        if photos: await send_pic(cid, photos[0], cap, kb)
        else: await send_msg(cid, cap, kb)

async def handle_start_flow(cid, user_id, kind):
    set_session(user_id, kind=kind, page=1, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
    push_history(user_id, "main")
    click_field = "buy_clicks" if kind == "خرید" else "rent_clicks"
    db["stats"].update_one({"_id": "clicks"}, {"$inc": {click_field: 1}}, upsert=True)
    push_history(user_id, "select_khab")
    
    from keyboards import kb_khab
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())

def parse_budget_text(text):
    text_en = fa_to_en(text)
    billions, millions = 0, 0
    b_match = re.search(r"(\d+)\s*(?:میلیارد|میلیاردی)", text_en)
    m_match = re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
    if b_match: billions = int(b_match.group(1)) * 1000000000
    if m_match: millions = int(m_match.group(1)) * 1000000
    total = billions + millions
    return total if total > 0 else None
