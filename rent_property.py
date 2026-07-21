# rent_property.py
from utils import set_session, push_history, send_msg
from keyboards import (
    kb_khab_selection,  # فرض می‌کنم کیبورد انتخاب خواب مشترک است
)
from database import search_files  # توابع دیتابیس را ایمپورت کن
from results import show_results  # تابع نمایش نتایج را ایمپورت کن


async def handle_rent_flow(cid, user_id, s, txt):
    """مدیریت کامل جریان رهن و اجاره - کاملاً مجزا از خرید"""

    # ۱. مرحله انتخاب تعداد خواب
    if "خواب" in txt and "مشاهده" not in txt:
        clean_khab = txt.strip()

        # ذخیره تعداد خواب در سشن کاربر
        set_session(user_id, khab=clean_khab)
        push_history(user_id, "select_khab")

        # میان‌بر: در رهن و اجاره، بعد از انتخاب خواب، مستقیم نتایج را نمایش می‌دهیم
        # بودجه و متراژ در این مسیر حذف شده‌اند
        res = await search_files(
            cid,
            user_id,
            "رهن_اجاره",
            clean_khab,
            None,  # بودجه (غیرفعال)
            None,  # بودجه (غیرفعال)
            s.get("page", 1),
        )

        await show_results(cid, res, False)
        return

    # ۲. اگر کاربر دکمه مشاهده فایل‌ها را زد (بدون اینکه خواب را انتخاب کرده باشد یا برای تکرار)
    elif "مشاهده" in txt:
        khab_val = s.get("khab")
        if not khab_val:
            # اگر هنوز خواب را انتخاب نکرده، دوباره از او بخواه
            await send_msg(
                cid,
                "لطفاً ابتدا تعداد خواب مورد نظر خود را انتخاب کنید:",
                kb_khab_selection,
            )
            return

        res = await search_files(
            cid, user_id, "رهن_اجاره", khab_val, None, None, s.get("page", 1)
        )
        await show_results(cid, res, False)
        return

    # ۳. مدیریت سایر پیام‌ها یا بازگشت‌ها در بخش رهن
    else:
        # اگر کاربر متنی فرستاد که در دسته‌بندی‌های بالا نبود
        await send_msg(
            cid,
            "لطفاً از منوی موجود برای انتخاب تعداد خواب یا مشاهده فایل‌ها استفاده کنید.",
        )
