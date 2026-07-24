# rent_property.py
# وارد کردن توابع کمکی مورد نیاز از ماژول core و کیبوردها از ماژول keyboards
from core import push_history, search_files, send_msg, set_session, show_results
from keyboards import (
    kb_khab as kb_khab_selection,
    kb_main,
)
from config import ADMIN_ID


# تابع مدیریت کامل جریان رهن و اجاره - کاملاً مجزا از خرید
async def handle_rent_flow(cid, user_id, s, txt):
    """مدیریت جریان رهن و اجاره با پیش‌گیری از تداخل با خرید"""

    # ثبت وضعیت کاربر در سشن برای جلوگیری از تداخل با مسیر خرید در main.py
    set_session(user_id, flow="rent")

    # ۱. بررسی درخواست بازگشت به منوی اصلی (اصلاح شده با ارسال کیبورد اصلی و ریست کامل سشن)
    if txt in ["🏠 منوی اصلی", "منوی اصلی", "بازگشت به منو اصلی"]:
        set_session(user_id, khab=None, flow=None, page=1, budje_min=None, budje_max=None)
        is_admin = (user_id == ADMIN_ID)
        await send_msg(
            cid,
            "به منوی اصلی بازگشتید.",
            kb_main(is_admin)
        )
        return

    # ۲. بررسی دکمه مشاهده همه فایل‌ها (بدون نیاز به انتخاب خواب)
    elif "مشاهده همه" in txt or ("مشاهده" in txt and "فایل" in txt):
        # ارسال پیام با کلید شیشه‌ای لینک کانال رهن و اجاره
        inline_kb = {
            "inline_keyboard": [
                [{"text": "📢 ورود به کانال رهن و اجاره", "url": "https://ble.ir/BROKER_amlak2"}]
            ]
        }
        await send_msg(cid, "📢 برای مشاهده تمامی فایل‌های رهن و اجاره، روی دکمه زیر کلیک کنید:", inline_kb)
        return

    # ۳. بررسی انتخاب تعداد خواب توسط کاربر
    elif "خواب" in txt:
        clean_khab = txt.strip()

        # ذخیره تعداد خواب در سشن کاربر، تثبیت فلو روی رهن و ثبت تاریخچه
        set_session(user_id, khab=clean_khab, flow="rent")
        push_history(user_id, "select_khab")

        # جستجو بر اساس تعداد خواب انتخاب شده
        res = search_files(
            kind="رهن_اجاره",
            khab=clean_khab,
            bmin=None,
            bmax=None,
            mmin=None,
            mmax=None,
            page=s.get("page", 1),
            cid=cid,
            user_id=user_id
        )

        if not res:
            # حل مشکل: اگر فایلی نبود، به جای نمایش مسیر خرید، این پیام نمایش داده شود
            await send_msg(
                cid,
                f"❌ متأسفانه ملکی با مشخصات «{clean_khab}» در بخش رهن و اجاره یافت نشد.",
                kb_khab_selection(),
            )
        else:
            await show_results(cid, res, False)
        return

    # ۴. مدیریت سایر پیام‌ها یا ورودی‌های نامعتبر
    else:
        await send_msg(
            cid,
            "لطفاً از منوی موجود برای انتخاب تعداد خواب یا مشاهده کلی فایل‌ها استفاده کنید.",
            kb_khab_selection(),
        )
