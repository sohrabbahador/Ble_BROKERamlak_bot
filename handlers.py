import json
import httpx
from config import db, ADMIN_ID, TOKEN, MAIN_CHANNEL_URL
from keyboards import kb_main, kb_khab, kb_meter, kb_next, inline_action, kb_custom_budget
from core import (
    get_session, set_session, register_user, save_file, search_files,
    send_msg, send_pic
)
from archive import (
    parse_budget_text, push_history, show_results, show_support, 
    handle_back_step, handle_start_flow, register_alert, 
    get_bot_stats, get_users_list
)
from property import handle_user_actions

async def is_member(user_id):
    """بررسی عضویت کاربر در کانال با استفاده از لینک موجود در کانفیگ"""
    try:
        # استخراج نام کانال از لینک (مثلاً BROKER_amlak)
        channel_username = MAIN_CHANNEL_URL.split("/")[-1]
        if not channel_username.startswith("@"):
            channel_username = "@" + channel_username
            
        api_url = f"https://tapi.bale.ai/bot{TOKEN}/getChatMember"
        async with httpx.AsyncClient() as client:
            # ارسال درخواست به API بله
            resp = await client.post(api_url, json={"chat_id": channel_username, "user_id": user_id}, timeout=10)
            data = resp.json()
            if data.get("ok"):
                status = data["result"].get("status")
                # کاربر باید یا عضو باشد یا ادمین/سازنده
                return status in ["member", "administrator", "creator"]
            else:
                print(f"Bale API Error for user {user_id}: {data.get('description')}")
                return False
    except Exception as e:
        print(f"Connection Error in is_member: {e}")
        return False

async def process_bale_webhook(data: dict):
    try:
        cb_data = data.get("callback_query")
        msg_data = data.get("message") or data.get("edited_message") or data.get("body")
        
        if cb_data:
            cid = cb_data["message"]["chat"]["id"]
            txt = cb_data.get("data", "") 
        elif msg_data:
            cid = msg_data.get("chat", {}).get("id")
            txt = msg_data.get("text", "") or msg_data.get("caption", "")
        else: return

        if not cid: return
        is_admin = (cid == ADMIN_ID)

        # --- ۱. هندل کردن تایید عضویت (Callback) ---
        if cb_data and txt == "بررسی عضویت":
            if await is_member(cid):
                await send_msg(cid, "✅ تایید شد! حالا می‌توانید از تمامی امکانات ربات استفاده کنید.")
            else:
                await send_msg(cid, "❌ هنوز عضو کانال نشدید. لطفاً ابتدا عضو شوید:", {
                    "inline_keyboard": [[{"text": "📢 عضویت در کانال", "url": MAIN_CHANNEL_URL}], 
                                        [{"text": "✅ عضو شدم (تایید)", "callback_data": "بررسی عضویت"}]]
                })
            return

        # --- ۲. دستور استارت (همیشه آزاد) ---
        if txt == "/start":
            name = msg_data.get("from", {}).get("first_name", "کاربر") if msg_data else "کاربر"
            register_user(cid, name)
            await send_msg(cid, "به خدمات ملکی هوشمند بروکر املاک خوش آمدید 💐 ! برای شروع، یکی از گزینه‌ها را انتخاب کنید:", kb_main(is_admin))
            return

        # --- ۳. قفل سخت‌گیرانه (برای هر کلیدی به جز استارت) ---
        if not is_admin:
            member_ok = await is_member(cid)
            if not member_ok:
                await send_msg(cid, "⚠️ **دسترسی محدود است!**\nلطفاً روی لینک عضو شوید، سپس به اینجا بازگردید و دکمه تایید را بزنید :", {
                    "inline_keyboard": [
                        [{"text": "📢 عضویت در کانال", "url": MAIN_CHANNEL_URL}],
                        [{"text": "✅ عضو شدم (تایید)", "callback_data": "بررسی عضویت"}]
                    ]
                })
                return

        # --- ۴. پردازش دستورات (فقط برای اعضا یا ادمین) ---
        s = get_session(cid) or {}
        
        if is_admin:
            # بخش مدیریت ادمین
            if txt == "📊 آمار ربات": await send_msg(cid, await get_bot_stats()); return
            elif txt == "👥 لیست کاربران": await send_msg(cid, get_users_list()); return
            elif txt == "📢 ارسال پیام همگانی":
                db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": True}}, upsert=True)
                await send_msg(cid, "✍️ متن پیام را بفرستید:"); return
            
            admin_state = db["admin_state"].find_one({"_id": cid}) or {}
            if admin_state.get("waiting_broadcast"):
                if txt == "بازگشت به منو اصلی":
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, "لغو شد."); return
                else:
                    success = 0
                    for u in db["users"].find({}, {"user_id": 1}):
                        if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"): success += 1
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, f"✅ پیام به {success} کاربر ارسال شد."); return

        # دستورات عمومی
        if txt == "🔙 مرحله قبل": await handle_back_step(cid, cid, is_admin); return
        elif "پشتیبانی" in txt: await show_support(cid, send_msg); return
        elif "جستجوی سریع" in txt: await send_msg(cid, "نام محله یا ویژگی را بفرستید:"); return
        elif "🔔 تنظیم گوش‌به‌زنگ" in txt: await register_alert(cid, cid, s); return
        
        # هندلر اصلی املاک
        elif txt in ["🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره", "🏠 منوی اصلی"] or any(x in txt for x in ["متر", "خواب", "میلیون", "میلیارد"]):
            await handle_user_actions(cid, cid, txt, s, is_admin, set_session, push_history, 
                                      handle_start_flow, parse_budget_text, kb_custom_budget, 
                                      kb_meter, search_files, show_results, kb_main, send_msg)
        else:
            if not is_admin:
                res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
                await show_results(cid, res, is_admin)

    except Exception as e:
        print(f"Critical Error: {e}")
