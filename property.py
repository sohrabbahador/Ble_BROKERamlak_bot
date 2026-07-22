# property.py
import json
from config import db
from core import send_msg

ADMIN_STATES = {}


def get_meter_range(txt):
    m_map = {
        "زیر ۸۰ متر": (0, 80), "۸۰ الی ۱۰۰ متر": (80, 100),
        "۱۰۰ الی ۱۲۰ متر": (100, 120), "۱۲۵ متر به بالا": (125, 999),
        "۱۰۰ الی ۱۲۵ متر": (100, 125), "۱۲۵ الی ۱۵۰ متر": (125, 150),
        "۱۵۰ الی ۱۷۰ متر": (150, 170), "۱۷۰ متر به بالا": (170, 999)
    }
    return m_map.get(txt, (0, 999))

def parse_range_budget(txt):
    try:
        if " الی " in txt and "میلیارد" in txt:
            parts = txt.replace("میلیارد", "").split(" الی ")
            min_val = int(parts[0].strip().replace(",", "")) * 1_000_000_000
            max_val = int(parts[1].strip().replace(",", "")) * 1_000_000_000
            return min_val, max_val
        elif "به بالا" in txt:
            val = int(txt.replace(" میلیارد به بالا", "").strip().replace(",", "")) * 1_000_000_000
            return val, 999_999_999_999
    except: return None, None
    return None, None

async def handle_user_actions(cid, user_id, txt, s, is_admin, *args, **kwargs):
    from core import search_files, show_results, handle_start_flow, parse_budget_text, push_history, set_session
    from keyboards import kb_main, kb_budget_2khab, kb_budget_3khab, kb_meter_2khab, kb_meter_3khab


    # ۱. مدیریت کامل بازگشت و منوی اصلی (با پشتیبانی کامل از نام دقیق "بازگشت به منوی اصلی" و سایر حالت‌ها)
    if any(item in txt for item in ["بازگشت به منوی اصلی", "منوی اصلی", "/start"]):
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, flow=None)
        push_history(user_id, "main")
        await send_msg(cid, "به منوی اصلی بازگشتید.", kb_main(is_admin))
        return

    # ۲. انتخاب نوع معامله
    elif txt in ["🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره"]:
        kind_map = {"🏠 خرید": "فروش", "🏠 فروش": "فروش", "🔑 رهن و اجاره": "رهن_اجاره"}
        selected_kind = kind_map[txt]
        set_session(user_id, kind=selected_kind)
        await handle_start_flow(cid, user_id, selected_kind)
        return

    # ۳. انتخاب تعداد خواب
    elif "خواب" in txt and "مشاهده" not in txt:
        if s.get("flow") == "rent":
            return
            
        clean_khab = txt.strip()
        # حفظ یا تعیین پیش‌فرض kind در صورت خالی بودن
        current_kind = s.get("kind") or "فروش"
        set_session(user_id, khab=clean_khab, flow="buy", kind=current_kind)
        push_history(user_id, "select_khab")
        kb = kb_budget_2khab() if clean_khab == "۲ خواب" else kb_budget_3khab() if clean_khab == "۳ خواب" else kb_budget_2khab()
        await send_msg(cid, f"✅ {clean_khab} انتخاب شد. حالا بودجه را تعیین کنید:", kb)
        return

    # ۴. مدیریت بودجه
    elif any(val in txt for val in ["میلیارد", "الی"]) and "متر" not in txt:
        b_min, b_max = parse_range_budget(txt)
        if b_min is not None:
            set_session(user_id, budje_min=b_min, budje_max=b_max)
            khab_val = s.get("khab", "۲ خواب")
            kb_m = kb_meter_2khab() if khab_val == "۲ خواب" else kb_meter_3khab() if khab_val == "۳ خواب" else kb_meter_2khab()
            await send_msg(cid, f"✅ بودجه ثبت شد.\nحالا حدود متراژ را انتخاب کنید:", kb_m)
        return

    # ۵. مشاهده همه (اصلاح‌شده برای جستجوی دقیق بدون خطای عدم یافتن ملک)
    elif "مشاهده همه" in txt or "📋 مشاهده همه فایل‌ها" in txt or ("مشاهده" in txt and "فایل" in txt):
        current_kind = s.get("kind") or "فروش"
        res = search_files(
            kind=current_kind,
            khab=s.get("khab"),
            bmin=s.get("budje_min"),
            bmax=s.get("budje_max"),
            mmin=s.get("meter_min"),
            mmax=s.get("meter_max"),
            page=1,
            cid=cid,
            user_id=user_id
        )
        if not res:
            # جستجوی پشتیبان بدون فیلتر تعداد خواب/بودجه در صورت خالی بودن نتیجه اولیه
            res = search_files(kind=current_kind, page=1, cid=cid, user_id=user_id)
            
        if not res:
            await send_msg(cid, "❌ در حال حاضر هیچ ملکی با این مشخصات یافت نشد.")
        else:
            await show_results(cid, res, is_admin)
        return

    # ۶. جستجوی نهایی با متراژ
    elif "متر" in txt:
        v = get_meter_range(txt)
        set_session(user_id, meter_min=v[0], meter_max=v[1])
        push_history(user_id, "select_meter")
        
        current_kind = s.get("kind") or "فروش"
        res = search_files(
            kind=current_kind,
            khab=s.get("khab"),
            bmin=s.get("budje_min"),
            bmax=s.get("budje_max"),
            mmin=v[0],
            mmax=v[1],
            page=s.get("page", 1),
            cid=cid,
            user_id=user_id
        )
        if not res:
            await send_msg(cid, "❌ در حال حاضر هیچ ملکی با این مشخصات یافت نشد.")
        else:
            await show_results(cid, res, is_admin)
        return

    # ۷. جستجوی متنی آزاد (منطقه / کلیدواژه مثل جنت‌آباد)
    else:
        current_kind = s.get("kind") or "فروش"
        res = search_files(
            kind=current_kind,
            query=txt.strip(),
            page=1,
            cid=cid,
            user_id=user_id
        )
        if not res:
            await send_msg(cid, "❌ در حال حاضر هیچ ملکی با این مشخصات یافت نشد.")
        else:
            await show_results(cid, res, is_admin)
        return
