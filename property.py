# property.py

ADMIN_STATES = {}

def get_meter_range(txt):
    m_map = {
        "کمتر از ۸۰ متر": (0, 80), 
        "۸۰ تا ۱۰۰ متر": (80, 100), 
        "۱۰۰ تا ۱۳۰ متر": (100, 130), 
        "بیشتر از ۱۳۰ متر": (130, 999)
    }
    return m_map.get(txt, (0, 999))

async def handle_user_actions(cid, user_id, txt, s, is_admin, set_session, push_history, 
                              handle_start_flow, parse_budget_text, kb_custom_budget, 
                              kb_meter, search_files, show_results, kb_main, send_msg):
    
    # 1. هدایت کلیدهای منوی اصلی
    if txt in ["/start", "بازگشت به منو اصلی"]:
        set_session(user_id, page=1, kind=None, khab=None, budje_min=None, 
                    budje_max=None, meter_min=None, meter_max=None, history=[])
        push_history(user_id, "main")

    elif txt in ["🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره"]:
        kind_map = {"🏠 خرید": "خرید", "🏠 فروش": "فروش", "🔑 رهن و اجاره": "رهن_اجاره"}
        await handle_start_flow(cid, user_id, kind_map[txt])

    # 2. دریافت مبالغ عددی بودجه
    elif ADMIN_STATES.get(user_id) in ["waiting_min_budget_flow", "waiting_max_budget_flow"]:
        if any(x in txt for x in ["مشاهده همه", "🔙 مرحله قبل", "بازگشت به منو اصلی", "💵 حداقل بودجه", "💵 حداکثر بودجه"]):
            ADMIN_STATES[user_id] = None
        else:
            budget_val = parse_budget_text(txt)
            khab_val = s.get("khab", "۱ خواب")
            example_val = "10 میلیارد" if khab_val == '۱ خواب' else "15 میلیارد"

            if budget_val == 0:
                await send_msg(cid, f"⚠️ لطفاً یک مبلغ معتبر وارد کنید (مثال؛ {example_val}):")
                return

            state = ADMIN_STATES.pop(user_id)
            if state == "waiting_min_budget_flow":
                set_session(user_id, budje_min=budget_val)
                await send_msg(cid, f"✅ حداقل بودجه ثبت شد: {budget_val:,} تومان\nحداکثر بودجه را تعیین کنید یا مستقیماً متراژ را انتخاب کنید.", kb_custom_budget(khab_val))
            else:
                set_session(user_id, budje_max=budget_val)
                push_history(user_id, "select_budget")
                await send_msg(cid, f"✅ حداکثر بودجه ثبت شد: {budget_val:,} تومان\nحدود متراژ ملک را انتخاب کنید:", kb_meter())
            return

    # 3. ورود بودجه دلخواه
    elif txt in ["💵 حداقل بودجه", "💵 حداکثر بودجه"]:
        is_min = (txt == "💵 حداقل بودجه")
        ADMIN_STATES[user_id] = "waiting_min_budget_flow" if is_min else "waiting_max_budget_flow"
        khab_val = s.get("khab", "۱ خواب")
        ex = "10 میلیارد" if is_min else "20 میلیارد"
        await send_msg(cid, f"✍️ {'حداقل' if is_min else 'حداکثر'} بودجه خود را بنویسید (مثال؛ {ex}):")

    # 4. فرآیند انتخاب خواب
    elif "خواب" in txt and "مشاهده" not in txt:
        clean_khab = txt.replace(" ", "")
        final_khab = "۴ خواب و بیشتر" if any(x in clean_khab for x in ["۴", "بیشتر"]) else txt.strip()
        set_session(user_id, khab=final_khab)
        push_history(user_id, "select_khab")
        await send_msg(cid, f"بودجه مورد نظر برای {final_khab} را تعیین کنید یا همه فایل‌ها را ببینید:", kb_custom_budget(final_khab))

    # 5. دکمه‌های «مشاهده همه»
    elif "مشاهده همه" in txt:
        ADMIN_STATES[user_id] = None
        res = search_files(s.get("kind"), s.get("khab"), None, None, None, None, 1)
        await show_results(cid, res, is_admin)

    # 6. دریافت متراژ و نمایش نتایج
    elif "متر" in txt:
        v = get_meter_range(txt)
        set_session(user_id, meter_min=v[0], meter_max=v[1])
        push_history(user_id, "select_meter")
        s_up = s # استفاده از سشن فعلی
        res = search_files(s_up.get("kind"), s_up.get("khab"), s_up.get("budje_min"), s_up.get("budje_max"), s_up.get("meter_min"), s_up.get("meter_max"), s_up.get("page", 1))
        await show_results(cid, res, is_admin)
