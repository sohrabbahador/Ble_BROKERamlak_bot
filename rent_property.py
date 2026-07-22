# rent_property.py
# وارد کردن توابع کمکی مورد نیاز از ماژول core و کیبوردها از ماژول keyboards
from core import push_history, search_files, send_msg, set_session, show_results
from keyboards import (
    kb_khab as kb_khab_selection,
)


# تابع مدیریت کامل جریان رهن و اجاره - کاملاً مجزا از خرید
async def handle_rent_flow(cid, user_id, s, txt):
    """مدیریت جریان رهن و اجاره با پیش‌گیری از تداخل با خرید"""

    # ثبت وضعیت کاربر در سشن برای جلوگیری از تداخل با مسیر خرید در main.py
    set_session(user_id, flow="rent")

    # ۱. بررسی درخواست بازگشت به منوی اصلی
    if txt == "🏠 منوی اصلی" or txt == "بازگشت به منو اصلی":
        # پاک کردن سشن مربوط به خواب و وضعیت جریان برای شروع مجدد
        set_session(user_id, khab=None, flow=None)
        await send_msg(
            cid,
            "به منوی اصلی بازگشتید.",
        )
        return

    # ۲. بررسی دکمه مشاهده همه فایل‌ها (بدون نیاز به انتخاب خواب)
    elif "مشاهده همه" in txt or "مشاهده" in txt and "فایل" in txt:
        res = search_files(
            kind="رهن_اجاره",
            khab=None,
            bmin=None,
            bmax=None,
            mmin=None,
            mmax=None,
            page=s.get("page", 1),
            cid=cid,
            user_id=user_id
        )

        if not res:
            await send_msg(
                cid,
                "❌ در حال حاضر هیچ ملکی در بخش رهن و اجاره یافت نشد.",
                kb_khab_selection(),
            )
        else:
            show_results(cid, res, False)
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
            show_results(cid, res, False)
        return

    # ۴. مدیریت سایر پیام‌ها یا ورودی‌های نامعتبر
    else:
        await send_msg(
            cid,
            "لطفاً از منوی موجود برای انتخاب تعداد خواب یا مشاهده کلی فایل‌ها استفاده کنید.",
            kb_khab_selection(),
        )
