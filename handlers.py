async def process_bale_webhook(data: dict):
    """پردازشگر اصلی پیام‌های بله"""
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            if not db["favorites"].find_one({"user_id": cid, "file_id": file_id}):
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else:
                await send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
        return

    msg = data.get("message") or data.get("edited_message") or data.get("body")
    if not msg: return

    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    first_name = msg.get("from", {}).get("first_name", "کاربر گرامی")

    if ctype == "private": register_user(cid, first_name)
    if ctype == "channel":
        if "photo" in msg and "موجود" in txt:
            photos = [msg["photo"][-1]["file_id"]]
            await save_file(txt, photos)
        return

    if ctype == "private":
        user_id = cid
        is_admin = (user_id == ADMIN_ID)
        s = get_session(user_id) or {}
        kind = s.get("kind")

        # --- گارد جداسازی رهن و اجاره (اضافه شده) ---
        if kind == "رهن_اجاره":
            # اینجا کدهای اختصاصی رهن و اجاره شما قرار می‌گیرد
            # برای مثال بازگشت به منو اصلی:
            if txt in ["/start", "بازگشت به منو اصلی"]:
                set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
                await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
                return
            # ... بقیه منطق رهن و اجاره (ودیعه/اجاره) اینجا اضافه می‌شود ...
            return 
        # --- پایان گارد ---

        # دکمه بازگشت به عقب (کد اصلی شما ادامه پیدا می‌کند)
        if txt == "🔙 مرحله قبل":
            ADMIN_STATES[user_id] = None
            await handle_back_step(cid, user_id, is_admin)
            return

        if txt == "بازگشت به منو اصلی":
            ADMIN_STATES[user_id] = None

        # پنل ادمین - ارسال پیام همگانی
        if is_admin and ADMIN_STATES.get(user_id) == "waiting_broadcast":
            ADMIN_STATES[user_id] = None
            if txt != "بازگشت به منو اصلی":
                success_count = sum(1 for u in db["users"].find({}, {"user_id": 1}) if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"))
                await send_msg(cid, f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.", kb_main(is_admin))
            else:
                await send_msg(cid, "عملیات لغو شد.", kb_main(is_admin))
            return

        # دریافت مبالغ عددی بودجه با گارد امنیتی
        if ADMIN_STATES.get(user_id) in ["waiting_min_budget", "waiting_max_budget"]:
            if "مشاهده همه" in txt or txt in ["🔙 مرحله قبل", "بازگشت به منو اصلی", "💵 حداقل بودجه", "💵 حداکثر بودجه"]:
                ADMIN_STATES[user_id] = None
            else:
                budget_val = parse_budget_text(txt)
                khab_val = s.get("khab", "۱ خواب")
                example_val = "10 میلیارد" if khab_val == "۱ خواب" else "15 میلیارد"
                
                if budget_val == 0:
                    await send_msg(cid, f"⚠️ لطفاً یک مبلغ معتبر وارد کنید (مثال؛ {example_val}):")
                    return
                
                state = ADMIN_STATES[user_id]
                ADMIN_STATES[user_id] = None
                if state == "waiting_min_budget":
                    set_session(user_id, budje_min=budget_val)
                    await send_msg(cid, f"✅ حداقل بودجه ثبت شد: {budget_val:,} تومان\nحداکثر بودجه را تعیین کنید یا مستقیماً متراژ را انتخاب کنید.", kb_custom_budget(khab_val))
                else:
                    set_session(user_id, budje_max=budget_val)
                    await send_msg(cid, f"✅ حداکثر بودجه ثبت شد: {budget_val:,} تومان\nحدود متراژ ملک را انتخاب کنید:", kb_meter())
                    push_history(user_id, "select_budget")
                return

        # هدایت کلیدهای منوی اصلی
        if txt in ["/start", "بازگشت به منو اصلی"]:
            set_session(user_id, page=1, kind=None, khab=None, budje_min=None, budje_max=None, meter_min=None, meter_max=None, history=[])
            push_history(user_id, "main")
            welcome = f"سلام {first_name} عزیز 👑 منوی مدیریت:" if is_admin else f"سلام {first_name} عزیز، به ربات هوشمند خوش آمدید. 🏠"
            await send_msg(cid, welcome, kb_main(is_admin))

        elif txt == "🏠 خرید": await handle_start_flow(cid, user_id, "فروش")
        elif txt == "🔑 رهن و اجاره": await handle_start_flow(cid, user_id, "رهن_اجاره")
        elif "پشتیبانی" in txt:
            await send_msg(cid, "📞 **پشتیبانی بروکر**\n\nبا کلیک روی دکمه‌های زیر تماس بگیرید یا پیام دهید:", {
                "inline_keyboard": [
                    [{"text": "📱 09123692401", "url": "tel:09123692401"}, {"text": "📱 09003692401", "url": "tel:09003692401"}],
                    [{"text": "🟢 پیام در بله 💬", "url": "https://ble.ir/sohrabbahador"}]
                ]
            })

        elif "خواب" in txt and "مشاهده" not in txt:
            clean_khab = txt.replace(" ", "")
            final_khab = "۴ خواب و بیشتر" if ("۴" in clean_khab or "بیشتر" in clean_khab) else txt.strip()
            set_session(user_id, khab=final_khab)
            push_history(user_id, "select_khab")
            await send_msg(cid, f"بودجه مورد نظر برای {final_khab} را تعیین کنید یا همه فایل‌ها را ببینید:", kb_custom_budget(final_khab))

        elif txt == "💵 حداقل بودجه":
            ADMIN_STATES[user_id] = "waiting_min_budget"
            khab_val = s.get("khab", "۱ خواب")
            example_val = "10 میلیارد" if khab_val == "۱ خواب" else "15 میلیارد"
            await send_msg(cid, f"✍️ حداقل بودجه خود را بنویسید و ارسال کنید:\n(مثال؛ {example_val}):")
            
        elif txt == "💵 حداکثر بودجه":
            ADMIN_STATES[user_id] = "waiting_max_budget"
            khab_val = s.get("khab", "۱ خواب")
            example_val = "20 میلیارد" if khab_val == "۱ خواب" else "100 میلیارد"
            await send_msg(cid, f"✍️ حداکثر بودجه خود را بفرستید:\n(مثال؛ {example_val}):")

        elif "📋 مشاهده همه" in txt or "مشاهده همه" in txt:
            ADMIN_STATES[user_id] = None
            khab_val = s.get("khab", "۱ خواب")
            res = search_files(s.get("kind"), khab_val, None, None, None, None, 1)
            await show_results(cid, res, is_admin)

        elif "متر" in txt:
            m_map = {"کمتر از ۱۰۰ متر": (0, 100), "۱۰۰ تا ۱۵۰ متر": (100, 150), "۱۵۰ تا ۲۰۰ متر": (150, 200), "بیشتر از ۲۰۰ متر": (200, 999)}
            v = m_map.get(txt, (0, 999))
            set_session(user_id, meter_min=v[0], meter_max=v[1])
            push_history(user_id, "select_meter")
            s = get_session(user_id) or {}
            res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), s.get("meter_min"), s.get("meter_max"), s.get("page", 1))
            await show_results(cid, res, is_admin)

        elif txt == "صفحه بعد":
            next_page = (s.get("page") or 1) + 1
            set_session(user_id, page=next_page)
            s = get_session(user_id) or {}
            res = search_files(s.get("kind"), s.get("khab"), s.get("budje_min"), s.get("budje_max"), s.get("meter_min"), s.get("meter_max"), s.get("page", 1))
            if not res:
                await send_msg(cid, "🏁 به انتهای لیست فایل‌های موجود رسیدید.", kb_main(is_admin))
            else:
                await show_results(cid, res, is_admin)

        elif txt == "⭐ علاقه‌مندی‌ها":
            favs = list(db["favorites"].find({"user_id": user_id}))
            if not favs:
                await send_msg(cid, "لیست علاقه‌مندی‌های شما خالی است.")
            else:
                for f in favs:
                    if r := db["files"].find_one({"id": f["file_id"]}):
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        await send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else await send_msg(cid, r["text"], inline_action(r["id"]))

        elif "🔍 جستجوی سریع" in txt:
            await send_msg(cid, "کافیست نام محله یا ویژگی مورد نظرتان را بنویسید و بفرستید:")
        
        elif txt == "🔔 تنظیم گوش‌به‌زنگ":
            if s and s.get("kind"):
                db["alerts"].insert_one({
                    "id": get_next_sequence_value("alert_id"), "user_id": user_id, "kind": s.get("kind"), "khab": s.get("khab"),
                    "budje_min": s.get("budje_min"), "budje_max": s.get("budje_max"), "meter_min": s.get("meter_min"), "meter_max": s.get("meter_max")
                })
                await send_msg(cid, "✅ فیلترهای جستجوی شما در بخش گوش‌به‌زنگ ثبت شد!")
            else:
                await send_msg(cid, "⚠️ ابتدا باید یکبار از طریق دکمه‌های منو جستجوی ملک را کامل کنید.")

        elif is_admin and txt == "📊 آمار ربات":
            stats = db["stats"].find_one({"_id": "clicks"}) or {}
            await send_msg(cid, f"📊 **آمار:**\n👤 کل کاربران: {db['users'].count_documents({})}\n🏠 کل املاک: {db['files'].count_documents({})}\n🔍 کلیک خرید: {stats.get('buy_clicks', 0)}\n🔑 کلیک رهن: {stats.get('rent_clicks', 0)}")
        
        elif is_admin and txt == "👥 لیست کاربران":
            users_list = "\n".join([f"• `{u['user_id']}` ({u.get('first_name', 'بدون نام')})" for u in db["users"].find({}, {"user_id": 1, "first_name": 1})])
            await send_msg(cid, f"👥 **کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")
        
        elif is_admin and txt == "📢 ارسال پیام همگانی":
            ADMIN_STATES[user_id] = "waiting_broadcast"
            await send_msg(cid, "✍️ متن پیام همگانی را بفرستید:", {"keyboard": [[{"text": "بازگشت به منو اصلی"}]], "resize_keyboard": True})

        else:
            res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
            if not res:
                await send_msg(cid, "❌ موردی با این مشخصات یافت نشد.", kb_main(is_admin))
            else:
                for r in res:
                    cap = f"🔍 **نتیجه جستجو**\n\n{r['text'][:300]}..."
                    photos = json.loads(r["photos"]) if r.get("photos") else []
                    await send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else await send_msg(cid, cap, inline_action(r["id"]))
