# config.py
from pymongo import MongoClient

# --- تنظیمات ربات بله ---
TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
MAIN_CHANNEL_URL = "https://ble.ir/BROKER_amlak"
ADMIN_ID = 160513400  # شناسه عددی سهراب بهادر (مدیر)

# --- اتصال به دیتابیس ابری MongoDB ---
MONGO_URI = "mongodb+srv://sohrabbahador2_db_user:48whO2iH0lCDGzeK@cluster0.tbsddnd.mongodb.net/?appName=Cluster0"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["broker_database"]  # نام دیتابیس پیش‌فرض
