from fastapi import FastAPI, Request
import requests

TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

app = FastAPI()

# -----------------------------
# ارسال پیام
# -----------------------------
def send_message(chat_id, text, keyboard=None):
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if keyboard:
        payload["reply_markup"] = keyboard

    requests.post(f"{BASE_URL}/sendMessage", json=payload)

# -----------------------------
# کیبوردهای ربات
# -----------------------------
def keyboard_start():
    return {
        "keyboard": [
            [{"text": "خرید"}],
            [{"text": "رهن و اجاره"}]
        ],
        "resize_keyboard": True
    }

def keyboard_khab():
    return {
        "keyboard": [
            [{"text": "۲ خواب"}],
            [{"text": "۳ خواب"}]
        ],
        "resize_keyboard": True
    }

def keyboard_budje():
    return {
        "keyboard": [
            [{"text": "۲۰ تا ۲۵ میلیارد"}],
            [{"text": "۲۵ تا ۳۰ میلیارد"}],
            [{"text": "۳۰ تا ۴۰ میلیارد"}],
            [{"text": "۴۰ تا ۵۰ میلیارد"}],
            [{"text": "۵۰ میلیارد به بالا"}]
        ],
        "resize_keyboard": True
    }

# -----------------------------
# پردازش پیام‌ها
# -----------------------------
@app.post("/")
async def bale_webhook(req: Request):
    data = await req.json()

    if "message" not in data:
        return {"ok": True}

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    # مرحله اول
    if text == "/start":
        send_message(chat_id, "سلام منصور عزیز، نوع عملیات را انتخاب کن:", keyboard_start())
        return {"ok": True}

    # مرحله دوم
    if text == "خرید":
        send_message(chat_id, "تعداد خواب را انتخاب کن:", keyboard_khab())
        return {"ok": True}

    if text == "رهن و اجاره":
        send_message(chat_id, "تعداد خواب را انتخاب کن:", keyboard_khab())
        return {"ok": True}

    # مرحله سوم
    if text in ["۲ خواب", "۳ خواب"]:
        send_message(chat_id, "بازه بودجه را انتخاب کن:", keyboard_budje())
        return {"ok": True}

    # مرحله نهایی (فیلتر)
    if text in [
        "۲۰ تا ۲۵ میلیارد",
        "۲۵ تا ۳۰ میلیارد",
        "۳۰ تا ۴۰ میلیارد",
        "۴۰ تا ۵۰ میلیارد",
        "۵۰ میلیارد به بالا"
    ]:
        send_message(chat_id, "در حال جستجو بین فایل‌های کانال...")
        # اینجا بعداً فیلتر هشتگ‌ها را اضافه می‌کنیم
        send_message(chat_id, "هیچ فایلی پیدا نشد یا هنوز دیتابیس اضافه نشده.")
        return {"ok": True}

    return {"ok": True}
