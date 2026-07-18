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
    get_bot_stats, get_users_list, handle_membership_flow, send_welcome_message,
    add_to_favorites, show_favorites, remove_from_favorites
)
from property import handle_user_actions

async def is_member(user_id):
    """بررسی عضویت کاربر در کانال"""
    try:
        channel_username = MAIN_CHANNEL_URL.split("/")[-1]
        if not channel_username.startswith("@"): channel_username = "@" + channel_username
        api_url = f"https://tapi.bale.ai/bot{TOKEN}/getChatMember"
        async with httpx.AsyncClient() as client:
            resp = await client.post(api_url, json={"chat_id": channel_username, "user_id": user_id}, timeout=10)
            data = resp.json()
            if data.get("ok"): return data["result"].get("status") in ["member", "administrator", "creator"]
            return False
    except: return False

async def process_bale_webhook(data: dict):
    try:
        cb_data = data.get("callback_query")
        msg_data = data.get("message") or data.get("edited_message") or data.get("body")
        if cb_data:
            cid = cb_data["message"]["chat"]["id"]
            chat_type = cb_data["message"]["chat"]["type"]
            txt = cb_data.get("data", "")
        elif msg_data:
            chat = msg_data.get("chat", {})
            cid = chat.get("id")
            chat_type = chat.get("type")
            txt = msg_data.get("text", "") or msg_data.get("caption", "")
        else: return

        if not cid: return
        user_id = cid
        is_admin = (user_id == ADMIN_ID)

        if chat_type == "channel":
            if "photo" in msg_data and "موجود" in txt:
                photos = [msg_data["photo"][-1]["file_id"]]
                await save_file(txt, photos)
            return

        if chat_type == "private":
            # استارت آزاد (ابتدا خوش‌آمدگویی ارسال می‌شود)
            if txt == "/start":
                name = msg_data.get("from", {}).get("first_name", "کاربر") if msg_data else "کاربر"
                register_user(cid, name)
                await send_welcome_message(cid, name, is_admin, send_msg, MAIN_CHANNEL_URL, kb_main)
                return

            # سد دفاعی عضویت (بعد از استارت، روی دکمه‌ها اعمال می‌شود)
            if await handle_membership_flow(cid, user_id, is_admin, cb_data, txt, send_msg, MAIN_CHANNEL_URL, kb_main, is_member):
                return
                
            # مدیریت دکمه‌های شیشه‌ای (علاقه‌مندی‌ها و حذف)
            if cb_data and txt.startswith("fav:"):
                prop_id = int(txt.split(":")[1])
                await add_to_favorites(cid, user_id, prop_id, send_msg)
                return
            if cb_data and txt.startswith("del_fav:"):
                prop_id = int(txt.split(":")[1])
                await remove_from_favorites(cid, user_id, prop_id, send_msg)
                return

            s = get_session(user_id) or {}
            if is_admin:
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

            if txt == "🔙 مرحله قبل": await handle_back_step(cid, user_id, is_admin)
            elif txt == "⭐ علاقه‌مندی‌ها": await show_favorites(cid, user_id, send_msg, is_admin)
            elif "پشتیبانی" in txt: await show_support(cid, send_msg)
            elif "جستجوی سریع" in txt: await send_msg(cid, "نام محله یا ویژگی را بفرستید:")
            elif "🔔 تنظیم گوش‌به‌زنگ" in txt: await register_alert(cid, user_id, s)
            elif txt in ["🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره", "🏠 منوی اصلی"] or any(x in txt for x in ["متر", "خواب", "میلیون", "میلیارد"]):
                await handle_user_actions(cid, user_id, txt, s, is_admin, set_session, push_history, 
                                          handle_start_flow, parse_budget_text, kb_custom_budget, 
                                          kb_meter, search_files, show_results, kb_main, send_msg)
            else:
                if any(word in txt for word in ["عضو شدم", "تایید عضویت", "عضویت در کانال"]):
                    return
                
                # جستجوی عادی برای ملک‌ها
                res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
                await show_results(cid, res, is_admin)
    except Exception as e: print(f"Error: {e}")
