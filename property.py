# property.py
from archive import search_files, show_results, handle_start_flow, parse_budget_text, push_history
from core import set_session
from keyboards import kb_khab, kb_budget_2khab, kb_budget_3khab, kb_meter_2khab, kb_meter_3khab, kb_main

ADMIN_STATES = {}


# 1. تبدیل متن دکمه متراژ به بازه عددی برای دیتابیس
def get_meter_range(txt):
    m_map = {
        "زیر ۸۰ متر": (0, 80),
        "۸۰ الی ۱۰۰ متر": (80, 100),
        "۱۰۰ الی ۱۲۰ متر": (100, 120),
        "۱۲۰ متر به بالا": (120, 999),
        "۱۰۰ الی ۱۱۲۵ متر": (100, 125),
        "۱۲۵ الی ۱۵۰ متر": (125, 150),
        "۱۵۰ الی ۱۷۰ متر": (150, 170),
        "۱۷۰ متر به بالا": (170, 999)
    }
    return m_map.get(txt, (0, 999))


# 2. تبدیل متون دکمه‌های بودجه به عدد برای جلوگیری از تداخل
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
    except:
        return None, None
    return None, None


# 3. مدیریت عملیات و اکشن‌های کاربر
async def handle_user_actions(cid, user_id, txt, s, is_admin, *args, **kwargs):
    # توجه: پارامترهای اضافی از هندلر (args/kwargs) نادیده گرفته می‌شوند چون توابع را مستقیم import کردیم
    
    # 4. منوی اصلی و بازگشت‌ها
    if txt in ["/start", "بازگشت به منو اصلی"]:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None,
                    budje_max=None, meter_min=None, meter_max=None, history=[])
        push_history(user_id, "main")
        # استفاده از kb_main مستقیم از import
        from core import send_msg
        await send_msg(cid, "به منوی اصلی بازگشتید.", kb_main(is_admin))
        return

    elif txt in ["🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره"]:
        kind_map = {"🏠 خرید": "خرید", "🏠 فروش": "فروش", "🔑 رهن و اجاره": "رهن_اجاره"}
        await handle_start_flow(cid, user_id, kind_map[txt])
        return

    # 5. مدیریت بودجه دستی (حفظ کامل منطق قبلی)
    elif ADMIN_STATES.get(user_id) in ["waiting_min_budget_flow", "waiting_max_budget_flow"]:
        if any(x in txt for x in ["مشاهده همه", "📋 مشاهده همه فایل‌ها", "🔙 مرحله قبل", "بازگشت به منو اصلی"]):
            ADMIN_STATES[user_id] = None
        else:
            budget_val = parse_budget_text(txt)
            khab_val = s.get("khab", "۱ خواب")
            example_val = "10 میلیارد" if khab_val == "۱ خواب" else "15 میلیارد"

            if budget_val == 0:
                from core import send_msg
                await send_msg(cid, f"⚠️ لطفاً یک مبلغ معتبر وارد کنید (مثال؛ {example_val}):")
                return

            state = ADMIN_STATES.pop(user_id, None)
            from core import send_msg
            if state == "waiting_min_budget_flow":
                set_session(user_id, budje_min=budget_val)
                kb = kb_budget_2khab() if khab_val == "۲ خواب" else kb_budget_3khab() if khab_val == "۳ خواب" else kb_budget_2khab()
                await send_msg(cid, f"✅ حداقل بودجه ثبت شد: {budget_val:,} تومان\n*حداکثر بودجه را تعیین کنید*", kb)
                return
            elif state == "waiting_max_budget_flow":
                set_session(user_id, budje_max=budget_val)
                push_history(user_id, "select_budget")
                kb_m = kb_meter_2khab() if khab_val == "۲ خواب" else kb_meter_3khab() if khab_val == "۳ خواب" else kb_meter_2khab()
                await send_msg(cid, f"✅ حداکثر بودجه ثبت شد: {budget_val:,} تومان\nحدود متراژ ملک را انتخاب کنید:", kb_m)
                return

    elif txt in ["💵 حداقل بودجه", "💵 حداکثر بودجه"]:
        is_min = (txt == "💵 حداقل بودجه")
        ADMIN_STATES[user_id] = "waiting_min_budget_flow" if is_min else "waiting_max_budget_flow"
        khab_val = s.get("khab", "۱ خواب")
        ex = "10 میلیارد" if is_min else "20 میلیارد"
        from core import send_msg
        await send_msg(cid, f"✍️ {'حداقل' if is_min else 'حداکثر'} بودجه خود را بنویسید (مثال؛ {ex}):")
        return

    # 6. انتخاب تعداد خواب
    elif "خواب" in txt and "مشاهده" not in txt:
        clean_khab = txt.replace(" ", "")
        final_khab = "۴ خواب و بیشتر" if any(x in clean_khab for x in ["۴", "بیشتر"]) else txt.strip()
        set_session(user_id, khab=final_khab)
        push_history(user_id, "select_khab")
        
        if final_khab == "۲ خواب":
            current_kb = kb_budget_2khab()
        elif final_khab == "۳ خواب":
            current_kb = kb_budget_3khab()
        else:
            current_kb = kb_budget_2khab() 

        from core import send_msg
        await send_msg(cid, f"بودجه مورد نظر برای {final_khab} را تعیین کنید یا همه فایل‌ها را ببینید:", current_kb)
        return

    # 7. مدیریت دکمه‌های بازه بودجه (تبدیل متن دکمه به عدد)
    elif any(val in txt for val in ["میلیارد", "الی"]):
        b_min, b_max = parse_range_budget(txt)
        if b_min is not None:
            set_session(user_id, budje_min=b_min, budje_max=b_max)
        
        khab_val = s.get("khab")
        from core import send_msg
        if khab_val == "۲ خواب":
            await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter_2khab())
        elif khab_val == "۳ خواب":
            await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter_3khab())
        else:
            await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_meter_2khab())
        return

    # 8. مشاهده همه فایل‌ها
    elif "مشاهده همه" in txt or "📋 مشاهده همه فایل‌ها" in txt:
        ADMIN_STATES[user_id] = None
        res = search_files(s.get("kind"), s.get("khab"), None, None, None, None, 1)
        await show_results(cid, res, is_admin)
        return

    # 9. متراژ و نمایش نتایج
    elif "متر" in txt:
        v = get_meter_range(txt)
        set_session(user_id, meter_min=v[0], meter_max=v[1])
        push_history(user_id, "select_meter")
        res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), v[0], v[1], s.get("page", 1))
        await show_results(cid, res, is_admin)
        return
