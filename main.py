# main.py
from fastapi import FastAPI, Request
from config import db
from core import init_db
from handlers import process_bale_webhook

app = FastAPI()

@app.on_event("startup")
def startup_event():
    # راه‌اندازی ایندکس‌ها و کانترهای دیتابیس MongoDB در زمان شروع به کار ربات
    init_db()

@app.get("/")
def home():
    return {"status": "running", "message": "Broker Bot is active!"}

@app.post("/")
async def webhook(req: Request):
    try:
        data = await req.json()
        # ارجاع پیام دریافتی به هندلر اصلی جهت پردازش منطق ربات بله
        await process_bale_webhook(data)
    except Exception as e:
        # مدیریت خطاهای احتمالی در زمان دریافت ریکوئست‌های نامعتبر
        return {"ok": False, "error": str(e)}
    return {"ok": True}
