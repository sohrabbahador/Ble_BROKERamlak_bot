# main.py
from fastapi import FastAPI, Request
import uvicorn
import os
from config import db
from core import init_db
from handlers import process_bale_webhook

app = FastAPI()

@app.on_event("startup")
def startup_event():
    # راه‌اندازی اولیه دیتابیس
    init_db()

@app.get("/")
def home():
    return {"status": "running", "message": "Broker Bot is active!"}

@app.post("/")
async def webhook(req: Request):
    try:
        # دریافت و پردازش پیام ارسالی از بله
        data = await req.json()
        await process_bale_webhook(data)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}

# بخش جدید و حیاتی برای رفع خطای Render
if __name__ == "__main__":
    # خواندن پورت از محیط Render یا استفاده از ۸۰۸۰ به صورت پیش‌فرض
    port = int(os.environ.get("PORT", 8080))
    # اجرای برنامه با uvicorn روی پورت مشخص شده
    uvicorn.run(app, host="0.0.0.0", port=port)
