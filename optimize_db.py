from config import db

def optimize_database():
    print("در حال پاکسازی فایل‌های تکراری از دیتابیس...")
    
    # ۱. حذف رکوردهای تکراری بر اساس متن یکسان
    pipeline = [
        {"$group": {"_id": "$text", "dups": {"$push": "$_id"}, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}}
    ]

    deleted_count = 0
    for doc in db["files"].aggregate(pipeline):
        # نگهداری اولین رکورد و حذف بقیه موارد تکراری
        ids_to_delete = doc["dups"][1:]
        result = db["files"].delete_many({"_id": {"$in": ids_to_delete}})
        deleted_count += result.deleted_count

    print(f"✅ تعداد {deleted_count} فایل تکراری با موفقیت حذف شد.")

    print("در حال بروزرسانی و ساخت ایندکس‌های سرعتی...")
    
    # ۲. اعمال ایندکس‌های ترکیبی جدید برای کاهش فشار روی دیتابیس
    db["sessions"].create_index("user_id", unique=True)
    db["users"].create_index("user_id", unique=True)
    db["files"].create_index([("kind", 1), ("khab", 1), ("price", 1), ("meter", 1)])
    db["files"].create_index("id", unique=True)
    
    print("✅ ایندکس‌های دیتابیس با موفقیت بهینه‌سازی شدند.")

if __name__ == "__main__":
    optimize_database()
