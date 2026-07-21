ADMIN_STATES = {}

def get_meter_range(txt):
    m_map = {
        "زیر ۸۰ متر": (0, 80), "۸۰ الی ۱۰۰ متر": (80, 100),
        "۱۰۰ الی ۱۲۰ متر": (100, 120), "۱۲۰ متر به بالا": (120, 999),
        "۱۰۰ الی ۱۱۲۵ متر": (100, 125), "۱۲۵ الی ۱۵۰ متر": (125, 150),
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
    from core import send_msg, set_session
    from archive import search_files, show_results, handle_start_flow, parse_budget_text, push_history
    from keyboards import kb_main, kb_budget_2khab, kb_budget_3khab, kb_meter_2khab, kb_meter_3khab

    if txt in ["/start", "بازگشت به منو اصلی"]:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
        push_history(user_id, "main")
        await send_msg(cid, "به منوی اصلی بازگشتید.", kb_main(is_admin))
    elif txt in ["🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره"]:
        kind_map = {"🏠 خرید": "خرید", "🏠 فروش": "فروش", "🔑 رهن و اجاره": "رهن_اجاره"}
        await handle_start_flow(cid, user_id, kind_map[txt])
    elif ADMIN_STATES.get(user_id) in ["waiting_min_budget_flow", "waiting_max_budget_flow"]:
        if any(x in txt for x in ["مشاهده همه", "📋 مشاهده همه فایل‌ها", "🔙 مرحله قبل", "بازگشت به منو اصلی"]):
            ADMIN_STATES[user_id] = None
        else:
            budget_val = parse_budget_text(txt)
            khab_val = s.get("khab", "۱ خواب")
            if budget_val == 0:
                await send_msg(cid, "⚠️ مبلغ نامعتبر است. لطفاً دوباره وارد کنید.")
                return
            state = ADMIN_STATES.pop(user_id, None)
            if state == "waiting_min_budget_flow":
                set_session(user_id, budje_min=budget_val)
                kb = kb_budget_2khab() if khab_val == "۲ خواب" else kb_budget_3khab() if khab_val == "۳ خواب" else kb_budget_2khab()
                await send_msg(cid, f"✅ حداقل بودجه ثبت شد: {budget_val:,} تومان\nحالا حداکثر بودجه را تعیین کنید:", kb)
            elif state == "waiting_max_budget_flow":
                set_session(user_id, budje_max=budget_val)
                push_history(user_id, "select_budget")
                kb_m = kb_meter_2khab() if khab_val == "۲ خواب" else kb_meter_3khab() if khab_val == "۳ خواب" else kb_meter_2khab()
                await send_msg(cid, f"✅ حداکثر بودجه ثبت شد: {budget_val:,} تومان\nحدود متراژ ملک را انتخاب کنید:", kb_m)
    elif txt in ["💵 حداقل بودجه", "💵 حداکثر بودجه"]:
        is_min = (txt == "💵 حداقل بودجه")
        ADMIN_STATES[user_id] = "waiting_min_budget_flow" if is_min else "waiting_max_budget_flow"
        await send_msg(cid, f"✍️ {'حداقل' if is_min else 'حداکثر'} بودجه را بنویسید:")
    elif "خواب" in txt and "مشاهده" not in txt:
        clean_khab = txt.strip()
        set_session(user_id, khab=clean_khab)
        push_history(user_id, "select_khab")
        kb = kb_budget_2khab() if clean_khab == "۲ خواب" else kb_budget_3khab() if clean_khab == "۳ خواب" else kb_budget_2khab()
        await send_msg(cid, f"✅ {clean_khab} انتخاب شد. حالا بودجه را تعیین کنید:", kb)
    elif any(val in txt for val in ["میلیارد", "الی"]):
        b_min, b_max = parse_range_budget(txt)
        if b_min is not None: set_session(user_id, budje_min=b_min, budje_max=b_max)
        khab_val = s.get("khab")
        kb_m = kb_meter_2khab() if khab_val == "۲ خواب" else kb_meter_3khab() if khab_val == "۳ خواب" else kb_meter_2khab()
        await send_msg(cid, "حدود متراژ ملک را انتخاب کنید:", kb_m)
    elif "مشاهده همه" in txt or "📋 مشاهده همه فایل‌ها" in txt:
        ADMIN_STATES[user_id] = None
        res = search_files(s.get("kind"), s.get("khab"), None, None, None, None, 1)
        await show_results(cid, res, is_admin)
    elif "متر" in txt:
        v = get_meter_range(txt)
        set_session(user_id, meter_min=v[0], meter_max=v[1])
        push_history(user_id, "select_meter")
        res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), v[0], v[1], s.get("page", 1))
        await show_results(cid, res, is_admin)

from core import send_msg, send_pic, get_session, register_user, save_file, set_session
from archive import (
    add_to_favorites, get_bot_stats, get_users_list, handle_back_step,
    handle_membership_flow, handle_start_flow, parse_budget_text,
    push_history, register_alert, remove_from_favorites,
    send_welcome_message, show_favorites, show_results, show_support
)
from config import ADMIN_ID, MAIN_CHANNEL_URL, TOKEN, db
from keyboards import kb_main 
from property import handle_user_actions
