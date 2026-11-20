import os
import json
import re
import httpx
from config import db, TOKEN, BASE_URL, MAIN_CHANNEL_URL, ADMIN_ID


# ==================== دستیار هوشمند فروش (فقط مدیر) ====================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()
AI_HISTORY = []
AI_MAX_HISTORY_MESSAGES = 12

def _public_ai_text(value):
    """حذف خطوط حاوی اطلاعات تماس و مالک پیش از ارسال به مدل."""
    lines = []
    for line in str(value or "").splitlines():
        if re.search(r"(تلفن|موبایل|شماره\\s*تماس|تماس\\s*با|نام\\s*مالک|آدرس\\s*دقیق)", line, re.I):
            continue
        line = re.sub(r"(?<!\\d)(?:\\+?98|0)?9\\d{9}(?!\\d)", "[شماره حذف شد]", line)
        line = re.sub(r"(?<!\\d)0\\d{10}(?!\\d)", "[شماره حذف شد]", line)
        lines.append(line)
    return "\\n".join(lines).strip()

def get_ai_sale_inventory_context(limit=35):
    """فقط فایل‌های فعال فروش متعلق به همین ربات."""
    rows = list(db["files"].find(
        {"source": "sale_bale", "kind": "فروش",
         "$or": [{"is_available": True}, {"is_available": {"$exists": False}}]},
        {"_id": 0, "id": 1, "text": 1, "khab": 1, "price": 1,
         "meter": 1, "location": 1}
    ).sort("id", -1).limit(limit))
    chunks = []
    for item in rows:
        summary = _public_ai_text(item.get("text", ""))
        extras = " | ".join(
            f"{k}: {item.get(k)}" for k in ("khab", "price", "meter", "location")
            if item.get(k) not in (None, "")
        )
        chunks.append(f"کد {item.get('id', '—')}: {extras} | {summary}")
    return "\\n".join(chunks)[:14000]

async def ask_gemini_admin(user_text: str) -> str:
    if not GEMINI_API_KEY:
        return "کلید GEMINI_API_KEY در Environment تنظیم نشده است."
    if not user_text or len(user_text) > 3000:
        return "پیام باید حداکثر ۳۰۰۰ نویسه باشد."
    inventory = get_ai_sale_inventory_context()
    instructions = (
        "تو دستیار هوشمند فارسی‌زبان مدیر بخش فروش املاک هستی. "
        "پاسخ‌ها کوتاه، دقیق و اجرایی باشند. اطلاعات را حدس نزن و ادعای انجام اقدام واقعی نکن. "
        "فقط درباره فایل‌های فروش ارائه‌شده پاسخ موجودی بده؛ فایل اجاره را نادیده بگیر. "
        "اطلاعات تماس، نام مالک و آدرس دقیق محرمانه‌اند و نباید افشا شوند. "
        "اگر فایل مناسب در فهرست نیست، صریح بگو اطلاعات کافی پیدا نشد."
    )
    if inventory:
        instructions += "\\n\\nفایل‌های فعال فروش:\\n" + inventory
    else:
        instructions += "\\n\\nدر حال حاضر فایل فعال فروشی در بانک اطلاعاتی ثبت نشده؛ درباره موجودی یا قیمت ادعایی نکن."

    contents = []
    for item in AI_HISTORY[-AI_MAX_HISTORY_MESSAGES:]:
        role = "model" if item.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": item.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    payload = {
        "systemInstruction": {"parts": [{"text": instructions}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.4}
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=payload
            )
        if response.status_code in (401, 403):
            return "کلید Gemini معتبر نیست یا دسترسی API برای آن فعال نیست."
        if response.status_code == 429:
            return "سهمیه رایگان Gemini فعلاً به پایان رسیده یا محدودیت درخواست اعمال شده؛ کمی بعد دوباره امتحان کن."
        if response.status_code >= 400:
            print("Gemini API error:", response.status_code, response.text[:500])
            return "ارتباط با Gemini برقرار نشد؛ مدل و دسترسی API را بررسی کن."
        data = response.json()
        candidates = data.get("candidates", [])
        answer = "\\n".join(
            part.get("text", "")
            for part in (candidates[0].get("content", {}).get("parts", []) if candidates else [])
            if part.get("text")
        ).strip()
        if not answer:
            return "پاسخ خالی از Gemini دریافت شد؛ دوباره امتحان کن."
        AI_HISTORY.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}])
        del AI_HISTORY[:-AI_MAX_HISTORY_MESSAGES]
        return answer
    except httpx.TimeoutException:
        return "پاسخ‌گویی بیش از حد طول کشید؛ دوباره امتحان کن."
    except Exception as exc:
        print("Gemini connection error:", str(exc)[:500])
        return "خطا در اتصال به Gemini؛ گزارش اجرا را بررسی کن."

# حافظه موقت برای جلوگیری از ارسال‌های هم‌زمان و لحظه‌ای
_recent_processed_texts = {}

def init_db():
    db["sessions"].create_index("user_id", unique=True)
    db["users"].create_index("user_id", unique=True)
    # ایندکس‌گذاری برای افزایش چشمگیر سرعت جستجوی املاک و فیلترها
    db["files"].create_index([("kind", 1), ("khab", 1), ("price", 1), ("meter", 1)])
    # ایندکس یکتا برای جلوگیری از ثبت تکراری متون در حالت هم‌زمانی
    try:
        db["files"].create_index("text", unique=True)
    except Exception:
        pass
    
    if db["counters"].count_documents({"_id": "file_id"}) == 0:
        db["counters"].insert_one({"_id": "file_id", "sequence_value": 0})
    if db["counters"].count_documents({"_id": "alert_id"}) == 0:
        db["counters"].insert_one({"_id": "alert_id", "sequence_value": 0})
    if db["counters"].count_documents({"_id": "fav_id"}) == 0:
        db["counters"].insert_one({"_id": "fav_id", "sequence_value": 0})
    if db["settings"].count_documents({"_id": "bot_status"}) == 0:
        db["settings"].insert_one({"_id": "bot_status", "maintenance": False})

def is_maintenance():
    doc = db["settings"].find_one({"_id": "bot_status"})
    return bool(doc and doc.get("maintenance", False))

def set_maintenance(enabled: bool):
    db["settings"].update_one(
        {"_id": "bot_status"},
        {"$set": {"maintenance": enabled}},
        upsert=True
    )

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
        m_match = re.search(r"میلیارد[^\d]*(\d+)\s*(?:میلیون|میلیونی)", text_en) or re.search(r"(\d+)\s*(?:میلیون|میلیونی)", text_en)
        
        if b_match: billions = int(b_match.group(1)) * 1000000000
        if m_match: 
            val = int(m_match.group(1))
            if val < 1000:
                millions = val * 1000000
            else:
                millions = val
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

async def save_file(text, photos_list=None, source_chat_id=None, source_message_id=None):
    """ثبت/به‌روزرسانی فایل فروش؛ هر پیام کانال فقط یک رکورد مستقل دارد."""
    import time
    global _recent_processed_texts

    text = (text or "").strip()
    if not text:
        return

    current_time = time.time()
    _recent_processed_texts = {
        t: tm for t, tm in _recent_processed_texts.items()
        if current_time - tm < 10
    }

    # جلوگیری از پردازش تکراری webhook؛ برای پیام‌های دارای شناسه، خود رکورد معیار اصلی است.
    dedupe_key = f"{source_chat_id}:{source_message_id}:{text}" if source_message_id else text
    if dedupe_key in _recent_processed_texts:
        return
    _recent_processed_texts[dedupe_key] = current_time

    k, kh, p, m, l = extract_info(text)
    # این ربات، ربات فروش است؛ نوع فایل را صریحاً فروش نگه می‌داریم.
    k = "فروش"
    photos_json = json.dumps(photos_list if photos_list else [], ensure_ascii=False)

    record = {
        "text": text,
        "kind": k,
        "khab": kh,
        "price": p,
        "meter": m,
        "location": l,
        "photos": photos_json,
        "source": "sale_bale",
        "is_available": True,
        "updated_at": current_time,
    }
    if source_chat_id is not None:
        record["source_chat_id"] = source_chat_id
    if source_message_id is not None:
        record["source_message_id"] = source_message_id

    try:
        if source_chat_id is not None and source_message_id is not None:
            existing = db["files"].find_one({
                "source": "sale_bale",
                "source_chat_id": source_chat_id,
                "source_message_id": source_message_id,
            })
            if existing:
                db["files"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": record}
                )
                return

        # سازگاری با فایل‌های قدیمی فروش که قبل از ثبت شناسه پیام ذخیره شده‌اند.
        existing = db["files"].find_one({"text": text, "kind": "فروش"})
        if existing:
            db["files"].update_one(
                {"_id": existing["_id"]},
                {"$set": {**record, "id": existing.get("id")}}
            )
        else:
            record["id"] = get_next_sequence_value("file_id")
            db["files"].insert_one(record)

        await check_alerts_and_notify(text, k, kh, p, m, photos_list)
    except Exception as e:
        print(f"Error saving sale file: {e}")


def remove_file_by_content(text, source_chat_id=None, source_message_id=None):
    """ناموجود کردن فقط همان فایل فروش؛ هیچ رکوردی از رهن و اجاره حذف نمی‌شود."""
    try:
        query = {"kind": "فروش", "source": "sale_bale"}
        if source_chat_id is not None and source_message_id is not None:
            query.update({
                "source_chat_id": source_chat_id,
                "source_message_id": source_message_id,
            })
        else:
            # مسیر سازگاری قدیمی فقط با تطبیق دقیق متن؛ حذف بر اساس مکان/متراژ ممنوع است.
            query["text"] = (text or "").strip()

        db["files"].update_many(
            query,
            {"$set": {"is_available": False, "updated_at": __import__("time").time()}}
        )
    except Exception as e:
        print(f"Error marking sale file unavailable: {e}")


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

def search_files(kind, khab=None, bmin=None, bmax=None, mmin=None, mmax=None, page=1, cid=None, user_id=None):
    # فقط فایل‌های موجود نمایش داده شوند؛ رکوردهای قدیمیِ بدون فیلد وضعیت حفظ می‌شوند.
    query = {
        "kind": kind,
        "$or": [{"is_available": True}, {"is_available": {"$exists": False}}],
    }
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
    return list(db["files"].find(query).skip(skip).limit(limit))

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
    
    # جلوگیری از ارسال تکراری فایل‌ها با استفاده از شناسه یکتا (id)
    seen_ids = set()
    unique_res = []
    for item in res:
        fid = item.get("id")
        if fid not in seen_ids:
            seen_ids.add(fid)
            unique_res.append(item)

    for item in unique_res:
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

def search_files_by_keyword(keyword, page=1):
    limit = 5
    skip = (page - 1) * limit
    
    # تبدیل فاصله و نیم‌فاصله به الگوی منعطف برای تمام کلمات و اعداد
    normalized_keyword = re.sub(r'[\s‌]+', r'[\\s‌]*', keyword.strip())
    
    query = {
        "text": {"$regex": normalized_keyword, "$options": "i"},
        "$or": [{"is_available": True}, {"is_available": {"$exists": False}}],
    }
    return list(db["files"].find(query).skip(skip).limit(limit))
