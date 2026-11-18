# config.py
import os
from pymongo import MongoClient

# --- تنظیمات ربات بله ---
# این مقادیر باید در Environment سرویس Render تعریف شوند.
TOKEN = os.getenv("BALE_BOT_TOKEN") or os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("متغیر BALE_BOT_TOKEN در Environment تنظیم نشده است.")

BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
MAIN_CHANNEL_URL = "https://ble.ir/BROKER_amlak"
ADMIN_ID = 160513400  # شناسه عددی مدیر

# --- اتصال به دیتابیس ابری MongoDB ---
MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("متغیر MONGODB_URI در Environment تنظیم نشده است.")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["broker_database"]
