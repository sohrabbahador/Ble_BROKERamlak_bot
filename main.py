from fastapi import FastAPI, Request
from bale import Bot, types

TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
bot = Bot(TOKEN)

app = FastAPI()

# -----------------------------
# دیتابیس ساده (در حافظه)
# -----------------------------
files_db = []   # هر پست کانال اینجا ذخیره می‌شود

def extract_tags(text):
    return [w for w in text.split() if w.startswith("#")]

# -----------------------------
# کیبوردهای ربات
# -----------------------------
def keyboard_start():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="خرید")],
            [types.KeyboardButton(text="رهن و اجاره")]
        ],
        resize_keyboard=True
    )

def keyboard_khab():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="۲ خواب")],
            [types.KeyboardButton(text="۳ خواب")]
        ],
        resize_keyboard=True
    )

def keyboard_budje():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="۲۰ تا ۲۵ میلیارد")],
            [types.KeyboardButton(text="۲۵ تا ۳۰ میلیارد")],
            [types.KeyboardButton(text="۳۰ تا ۴۰ میلیارد")],
            [types.KeyboardButton(text="۴۰ تا ۵۰ میلیارد")],
            [types.KeyboardButton(text="۵۰ میلیارد به بالا")]
        ],
        resize_keyboard=True
    )

# -----------------------------
# وبهوک بله
# -----------------------------
@app.post("/")
async def webhook(req: Request):
    data = await req.json()
    update = types.Update(**data)

    # -----------------------------
    # ذخیره پست‌های کانال
    # -----------------------------
    if update.message and update.message.chat.type == "channel":
        text = update.message.text or ""
        tags = extract_tags(text)

        files_db.append({
            "text": text,
            "tags": tags
        })

        return {"ok": True}

    # -----------------------------
    # پیام‌های بازو
    # -----------------------------
    if update.message and update.message.chat.type == "private":
        chat_id = update.message.chat.id
        text = update.message.text

        # مرحله اول
        if text == "/start":
            bot.send_message(chat_id, "نوع عملیات را انتخاب کن:", reply_markup=keyboard_start())
            return {"ok": True}

        # مرحله دوم
        if text == "خرید":
            bot.send_message(chat_id, "تعداد خواب را انتخاب کن:", reply_markup=keyboard_khab())
            return {"ok": True}

        if text == "رهن و اجاره":
            bot.send_message(chat_id, "تعداد خواب را انتخاب کن:", reply_markup=keyboard_khab())
            return {"ok": True}

        # مرحله سوم
        if text in ["۲ خواب", "۳ خواب"]:
            # اگر خرید بود → بودجه‌ها
            bot.send_message(chat_id, "بازه بودجه را انتخاب کن:", reply_markup=keyboard_budje())
            return {"ok": True}

        # مرحله نهایی خرید → فیلتر کامل
        if text in [
            "۲۰ تا ۲۵ میلیارد",
            "۲۵ تا ۳۰ میلیارد",
            "۳۰ تا ۴۰ میلیارد",
            "۴۰ تا ۵۰ میلیارد",
            "۵۰ میلیارد به بالا"
        ]:
            bot.send_message(chat_id, "در حال جستجو بین فایل‌های خرید...")

            # تبدیل بودجه به هشتگ
            budje_tag = {
                "۲۰ تا ۲۵ میلیارد": "#۲۰میلیارد",
                "۲۵ تا ۳۰ میلیارد": "#۳۰میلیارد",
                "۳۰ تا ۴۰ میلیارد": "#۳۰میلیارد",
                "۴۰ تا ۵۰ میلیارد": "#۴۰میلیارد",
                "۵۰ میلیارد به بالا": "#۵۰میلیارد_به_بالا"
            }[text]

            results = []
            for f in files_db:
                if "#فروش" in f["tags"] and budje_tag in f["tags"]:
                    results.append(f["text"])

            if not results:
                bot.send_message(chat_id, "هیچ فایل مطابق پیدا نشد.")
            else:
                for r in results:
                    bot.send_message(chat_id, r)

            return {"ok": True}

    return {"ok": True}
