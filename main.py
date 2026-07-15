# main.py
import json
from fastapi import FastAPI, Request

# ایمپورت کردن توابع هسته از فایل core.py
from core import (
    ADMIN_ID,
    MAIN_CHANNEL_URL,
    get_db,
    get_session,
    init_db,
    register_user,
    save_file,
    search_files,
    send_msg,
    send_pic,
    set_session,
    send_media_group,
)

app = FastAPI()

# دیکشنری برای پیگیری موقت حالت ادمین برای ارسال پیام همگانی
ADMIN_STATES = {}

# ==========================================
# بخش اول: قالب‌های کیبورد (Keyboards)
# ==========================================

def kb_main(is_admin=False):
    kb = [
        [{"text": "🏠 خرید"}, {"text": "🔑 رهن و اجاره"}],
        [{"text": "🔍 جستجوی سریع"}, {"text": "⭐ علاقه‌مندی‌ها"}],
        [{"text": "🔔 تنظیم گوش‌به‌زنگ"}]
    ]
    if is_admin:
        kb.append([{"text": "📊 آمار ربات"}, {"text": "📢 ارسال پیام همگانی"}])
    return {
        "keyboard": kb,
        "resize_keyboard": True,
    }


def kb_khab():
    return {
        "keyboard": [
            [{"text": "۱ خواب"}, {"text": "۲ خواب"}],
            [{"text": "۳ خواب"}, {"text": "۴ خواب و بیشتر"}],
            [{"text": "بازگشت به منو اصلی"}],
        ],
        "resize_keyboard": True,
    }


def kb_budje_forosh():
    return {
        "keyboard": [
            [{"text": "۲۰ تا ۳۰ میلیارد"}, {"text": "۳۰ تا ۴۰ میلیارد"}],
            [{"text": "۴۰ تا ۵۰ میلیارد"}, {"text": "۵۰ میلیارد به بالا"}],
            [{"text": "بازگشت به منو اصلی"}],
        ],
        "resize_keyboard": True,
    }


def kb_budje_rahn():
    return {
        "keyboard": [
            [{"text": "کمتر از ۲ میلیارد"}, {"text": "۲ تا ۴ میلیارد"}],
            [{"text": "۴ تا ۶ میلیارد"}, {"text": "۶ میلیارد به بالا"}],
            [{"text": "بازگشت به منو اصلی"}],
        ],
        "resize_keyboard": True,
    }


def kb_meter():
    return {
        "keyboard": [
            [{"text": "کمتر از ۱۰۰ متر"}, {"text": "۱۰۰ تا ۱۵۰ متر"}],
            [{"text": "۱۵۰ تا ۲۰۰ متر"}, {"text": "بیشتر از ۲۰۰ متر"}],
            [{"text": "بازگشت به منو اصلی"}],
        ],
        "resize_keyboard": True,
    }


def kb_next():
    return {
        "keyboard": [[{"text": "صفحه بعد"}, {"text": "بازگشت به منو اصلی"}]],
        "resize_keyboard": True,
    }


def inline_action(fid):
    # لینک مستقیم اشتراک گذاری با بله
    share_url = f"https://ble.ir/share/url?url=https://t.me/BrokerBot?start=file_{fid}"
    return {
        "inline_keyboard": [
            [{"text": "🚀 مشاهده در کانال", "url": MAIN_CHANNEL_URL}],
            [
                {"text": "⭐ افزودن به علاقه‌مندی", "callback_data": f"fav:{fid}"},
                {"text": "🔗 اشتراک‌گذاری", "url": share_url}
            ],
        ]
    }

# ==========================================
# بخش دوم: هندلرهای خرید و رهن (Handlers)
# ==========================================

async def handle_buy_start(cid, user_id):
    set_session(user_id, kind="فروش", page=1)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())


def get_buy_budget_ranges():
    return {
        "۲۰ تا ۳۰ میلیارد": (20 * 10**9, 30 * 10**9),
        "۳۰ تا ۴۰ میلیارد": (30 * 10**9, 40 * 10**9),
        "۴۰ تا ۵۰ میلیارد": (40 * 10**9, 50 * 10**9),
        "۵۰ میلیارد به بالا": (50 * 10**9, 999 * 10**9),
    }


async def handle_rent_start(cid, user_id):
    set_session(user_id, kind="رهن_اجاره", page=1)
    await send_msg(cid, "تعداد اتاق خواب مورد نظرتان را انتخاب کنید:", kb_khab())


def get_rent_budget_ranges():
    return {
        "کمتر از ۲ میلیارد": (0, 2 * 10**9),
        "۲ تا ۴ میلیارد": (2 * 10**9, 4 * 10**9),
        "۴ تا ۶ میلیارد": (4 * 10**9, 6 * 10**9),
        "۶ میلیارد به بالا": (6 * 10**9, 999 * 10**9),
    }

# ==========================================
# بخش سوم: وب‌هووک و مسیریابی ربات (FastAPI Webhook)
# ==========================================

@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def home():
    return {"ok": True}


@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    # مدیریت عملیات علاقه‌مندی‌ها
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            db = get_db()
            
            # بررسی وضعیت تکراری بودن در لیست علاقه‌مندی‌ها با مونگو
            exists = db["favorites"].find_one({"user_id": cid, "file_id": file_id})
            if not exists:
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else:
                await send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
        return {"ok": True}

    msg = data.get("message") or data.get("body")
    if not msg:
        return {"ok": True}

    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    user_info = msg.get("from", {})
    first_name = user_info.get("first_name", "کاربر گرامی")

    # ثبت کاربر در دیتابیس برای آمار و همگانی
    if ctype == "private":
        register_user(cid, first_name)

    # مانیتورینگ کانال (ذخیره فایل‌ها به همراه کل آلبوم عکس)
    if ctype == "channel":
        photos = []
        if "photo" in msg:
            photos.append(msg["photo"][-1]["file_id"])
        if "media_group_id" in msg:
            photos.append(msg["photo"][-1]["file_id"] if "photo" in msg else None)

        if "موجود" in txt:
            await save_file(txt, [p for p in photos if p])
        return {"ok": True}

    # چت خصوصی کاربر
    if ctype == "private":
        user_id = cid
        is_admin = (user_id == ADMIN_ID)
        s = get_session(user_id)

        # مدیریت حالت پیام همگانی ادمین
        if is_admin and ADMIN_STATES.get(user_id) == "waiting_broadcast":
            if txt == "بازگشت به منو اصلی":
                ADMIN_STATES[user_id] = None
            else:
                ADMIN_STATES[user_id] = None
                db = get_db()
                all_users = list(db["users"].find({}, {"user_id": 1}))
                
                success_count = 0
                for u in all_users:
                    try:
                        await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}")
                        success_count += 1
                    except:
                        pass
                await send_msg(cid, f"✅ پیام همگانی با موفقیت به {success_count} کاربر ارسال شد.", kb_main(is_admin))
                return {"ok": True}

        if txt == "/start" or txt == "بازگشت به منو اصلی":
            set_session(
                user_id,
                page=1,
                kind=None,
                khab=None,
                budje_min=None,
                budje_max=None,
                meter_min=None,
                meter_max=None,
            )
            welcome_text = f"سلام {first_name} عزیز، به ربات هوشمند بروکر خوش آمدید. 🏠\n\nنوع عملیات مورد نظرتان را انتخاب کنید:"
            if is_admin:
                welcome_text = f"سلام سهراب عزیز، خوش آمدید. 👑\nمنوی مدیریت برای شما فعال است:"
            await send_msg(cid, welcome_text, kb_main(is_admin))

        elif txt == "🏠 خرید":
            await handle_buy_start(cid, user_id)

        elif txt == "🔑 رهن و اجاره":
            await handle_rent_start(cid, user_id)

        elif "خواب" in txt:
            clean_khab = txt.replace(" ", "")
            if "۴" in clean_khab or "بیشتر" in clean_khab:
                final_khab = "۴ خواب و بیشتر"
            else:
                final_khab = txt.strip()
            set_session(user_id, khab=final_khab)
            s = get_session(user_id)
            if s and s.get("kind") == "فروش":
                await send_msg(cid, "بازه بودجه خرید را انتخاب کنید:", kb_budje_forosh())
            else:
                await send_msg(cid, "بازه رهن مورد نظرتان را انتخاب کنید:", kb_budje_rahn())

        elif any(w in txt for w in ["میلیارد", "میلیونی"]):
            b_map = {}
            b_map.update(get_buy_budget_ranges())
            b_map.update(get_rent_budget_ranges())

            v = b_map.get(txt, (0, 999 * 10**9))
            set_session(user_id, budje_min=v[0], budje_max=v[1])
            await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter())

        elif "متر" in txt:
            m_map = {
                "کمتر از ۱۰۰ متر": (0, 100),
                "۱۰۰ تا ۱۵۰ متر": (100, 150),
                "۱۵۰ تا ۲۰۰ متر": (150, 200),
                "بیشتر از ۲۰۰ متر": (200, 999),
            }
            v = m_map.get(txt, (0, 999))
            set_session(user_id, meter_min=v[0], meter_max=v[1])

            s = get_session(user_id)
            if s:
                res = search_files(
                    s.get("kind"),
                    s.get("khab"),
                    s.get("budje_min"),
                    s.get("budje_max"),
                    s.get("meter_min"),
                    s.get("meter_max"),
                    s.get("page", 1),
                )
                if not res:
                    await send_msg(
                        cid,
                        "❌ متاسفانه ملکی با این مشخصات یافت نشد. فیلترها را تغییر دهید یا مجدداً تلاش کنید.",
                        kb_main(is_admin),
                    )
                else:
                    for r in res:
                        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        if photos:
                            await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                        else:
                            await send_msg(cid, cap, inline_action(r["id"]))
                    await send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())
            else:
                await send_msg(cid, "خطایی رخ داد. لطفاً مجدداً جستجو را آغاز کنید.", kb_main(is_admin))

        elif txt == "صفحه بعد":
            s = get_session(user_id)
            if s:
                next_page = (s.get("page") or 1) + 1
                set_session(user_id, page=next_page)
                s = get_session(user_id)
                res = search_files(
                    s.get("kind"),
                    s.get("khab"),
                    s.get("budje_min"),
                    s.get("budje_max"),
                    s.get("meter_min"),
                    s.get("meter_max"),
                    s.get("page", 1),
                )
                if not res:
                    await send_msg(cid, "🏁 به انتهای لیست فایل‌های موجود رسیدید.", kb_main(is_admin))
                else:
                    for r in res:
                        cap = f"🏠 **پیشنهاد ویژه بروکر**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        if photos:
                            await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                        else:
                            await send_msg(cid, cap, inline_action(r["id"]))
                    await send_msg(cid, "📄 برای مشاهده گزینه‌های بیشتر:", kb_next())
            else:
                await send_msg(cid, "نشست کاربری شما یافت نشد. بازگشت به منو اصلی...", kb_main(is_admin))

        elif txt == "⭐ علاقه‌مندی‌ها":
            db = get_db()
            favs = list(db["favorites"].find({"user_id": user_id}))

            if not favs:
                await send_msg(cid, "لیست علاقه‌مندی‌های شما در حال حاضر خالی است.")
            else:
                await send_msg(cid, "⭐ **لیست فایل‌های مورد علاقه شما:**")
                for f in favs:
                    r = db["files"].find_one({"id": f["file_id"]})
                    if r:
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        if photos:
                            await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                        else:
                            await send_msg(cid, r["text"], inline_action(r["id"]))

        elif "🔍 جستجوی سریع" in txt:
            await send_msg(
                cid,
                "کافیست نام محله (مثلاً جنت‌آباد) یا ویژگی مورد نظرتان را بنویسید و بفرستید تا سریعاً جستجو کنم:",
            )

        elif txt == "🔔 تنظیم گوش‌به‌زنگ":
            s = get_session(user_id)
            if s and s.get("kind"):
                db = get_db()
                
                # دریافت آیدی خودکار افزایشی با ساختار core.py برای آلارم
                from core import get_next_sequence_value
                alert_id = get_next_sequence_value("alert_id")
                
                db["alerts"].insert_one({
                    "id": alert_id,
                    "user_id": user_id,
                    "kind": s.get("kind"),
                    "khab": s.get("khab"),
                    "budje_min": s.get("budje_min"),
                    "budje_max": s.get("budje_max"),
                    "meter_min": s.get("meter_min"),
                    "meter_max": s.get("meter_max")
                })
                await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد! به محض اضافه شدن فایل جدید همسو با سلیقه‌تان، بلافاصله به شما اطلاع می‌دهیم.")
            else:
                await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید تا فیلترهای دلخواه شما شناسایی و ثبت شوند.")

        elif is_admin and txt == "📊 آمار ربات":
            db = get_db()
            u_count = db["users"].count_documents({})
            f_count = db["files"].count_documents({})
            await send_msg(cid, f"📊 **آمار سیستم هوشمند بروکر:**\n\n👤 کل کاربران عضو: {u_count} نفر\n🏠 کل املاک ثبت‌شده: {f_count} ملک")

        elif is_admin and txt == "📢 ارسال پیام همگانی":
            ADMIN_STATES[user_id] = "waiting_broadcast"
            await send_msg(cid, "✍️ لطفاً متنی که می‌خواهید برای تمام کاربران ارسال شود را بنویسید و بفرستید:\n(برای لغو، دکمه بازگشت به منو اصلی را بزنید.)", {"keyboard": [[{"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True})

        else:
            db = get_db()
            # شبیه‌سازی دقیق فیلتر متنی LIKE در دیتابیس MongoDB با استفاده از رگولار اکسپرشن
            res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
            if not res:
                await send_msg(
                    cid,
                    "❌ موردی با این مشخصات یافت نشد. جستجوی متنی دیگری انجام دهید یا از دکمه‌های منو استفاده کنید.",
                    kb_main(is_admin),
                )
            else:
                for r in res:
                    cap = f"🔍 **نتیجه جستجوی سریع**\n\n{r['text'][:300]}..."
                    photos = json.loads(r["photos"]) if r.get("photos") else []
                    if photos:
                        await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                    else:
                        await send_msg(cid, cap, inline_action(r["id"]))

    return {"ok": True}
