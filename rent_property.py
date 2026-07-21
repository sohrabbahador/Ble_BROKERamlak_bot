# rent_property.py
# وارد کردن توابع کمکی مورد نیاز از ماژول core و کیبوردها از ماژول keyboards
from core import push_history, search_files, send_msg, set_session, show_results
from keyboards import (
    kb_khab as kb_khab_selection,
)


# تابع مدیریت کامل جریان رهن و اجاره - کاملاً مجزا از خرید
async def handle_rent_flow(cid, user_id, s, txt):
    "" ""

    # ۱. بررسی درخواست بازگشت به منوی اصلی
    if txt == "🏠 منوی اصلی":
        # پاک کردن سشن مربوط به خواب برای شروع مجدد در آینده
        set_session(user_id, khab=None)
        await send_msg(
            cid,
            "به منوی اصلی بازگشتید. چه کمکی از دست من برمی‌آید؟",
            # در اینجا باید kb_main() فراخوانی شود، اما چون در core یا elsewhere هندل می‌شود،
            # فقط پیام می‌فرستیم یا اگر تابع kb_main در دسترس است اینجا قرار می‌دهیم.
        )
        return

    # ۲. بررسی دکمه مشاهده همه فایل‌ها (بدون نیاز به انتخاب خواب)
    if "مشاهده" in txt and "فایل‌ها" in txt:
        # ارسال None برای خواب، بودجه و متراژ تا همه نتایج رهن و اجاره نمایش داده شود
        res = await search_files(
            cid,
            user_id,
            "رهن_اجاره",
            None,  # بدون محدودیت خواب
            None,  # بدون محدودیت بودجه
            None,  # بدون محدودیت متراژ
            s.get("page", 1),
        )
        await show_results(cid, res, False)
        return

    # ۳. بررسی انتخاب تعداد خواب توسط کاربر
    if "خواب" in txt:
        clean_khab = txt.strip()

        # ذخیره تعداد خواب در سشن کاربر و ثبت تاریخچه
        set_session(user_id, khab=clean_khab)
        push_history(user_id, "select_khab")

        # جستجو بر اساس تعداد خواب انتخاب شده
        res = await search_files(
            cid,
            user_id,
            "رهن_اجاره",
            clean_khab,
            None,  # بودجه (غیرفعال)
            None,  # متراژ (غیرفعال)
            s.get("page", 1),
        )

        await show_results(cid, res, False)
        return

    # ۴. مدیریت سایر پیام‌ها یا ورودی‌های نامعتبر
    else:
        await send_msg(
            cid,
            "لطفاً از منوی موجود برای انتخاب تعداد خواب یا مشاهده کلی فایل‌ها استفاده کنید.",
            kb_khab_selection(),
        )
