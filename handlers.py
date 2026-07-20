import json
import httpx
from archive import (add_to_favorites, get_bot_stats, get_users_list, handle_back_step,
                     handle_membership_flow, handle_start_flow, parse_budget_text,
                     push_history, register_alert, remove_from_favorites,
                     send_welcome_message, show_favorites, show_results, show_support)
from config import ADMIN_ID, MAIN_CHANNEL_URL, TOKEN, db
from core import get_session, register_user, save_file, send_msg, send_pic, set_session
from keyboards import inline_action, kb_custom_budget, kb_khab, kb_main, kb_meter, kb_next
from property import handle_user_actions

# --- بررسی عضویت کاربر در کانال ---
async def is_member(user_id):
    try:
        channel_username = MAIN_CHANNEL_URL.split("/")[-1]
        channel_username = f"@{channel_username}" if not channel_username.startswith("@") else channel_username
        api_url = f"https://tapi.bale.ai/bot{TOKEN}/getChatMember"
        async with httpx.AsyncClient() as client:
            resp = await client.post(api_url, json={"chat_id": channel_username, "user_id": user_id}, timeout=10)
            data = resp.json()
            return data.get("ok") and data["result"].get("status") in ["member", "administrator", "creator"]
    except:
        return False

# --- پردازش اصلی پیام‌های دریافتی از وب‌هوک ---
async def process_bale_webhook(data: dict):
    try:
        cb_data = data.get("callback_query")
        msg_data = data.get("message") or data.get("edited_message") or data.get("body")
        
        if cb_data:
            cid, chat_type, txt = cb_data["message"]["chat"]["id"], cb_data["message"]["chat"]["type"], cb_data.get("data", "")
        elif msg_data:
            cid, chat_type, txt = msg_data.get("chat", {}).get("id"), msg_data.get("chat", {}).get("type"), msg_data.get("text", "") or msg_data.get("caption", "")
        else:
            return
            
        if not cid:
            return
            
        user_id, is_admin = cid, cid == ADMIN_ID
        
        # --- مدیریت پیام‌های ارسالی در کانال ---
        if chat_type == "channel":
            if msg_data and "photo" in msg_data and "موجود" in txt:
                await save_file(txt, [msg_data["photo"][-1]["file_id"]])
            return
            
        # --- مدیریت تعاملات در چت خصوصی ---
        if chat_type == "private":
            if txt == "/start":
                name = msg_data.get("from", {}).get("first_name", "کاربر") if msg_data else "کاربر"
                register_user(cid, name)
                await send_welcome_message(cid, name, is_admin, send_msg, MAIN_CHANNEL_URL, kb_main)
                return
            
            # --- تایید عضویت کاربر ---
            if cb_data and txt == "check_membership":
                if await is_member(user_id):
                    await send_msg(cid, "✅ عضویت شما تایید شد. اکنون می‌توانید از تمامی خدمات استفاده کنید.", kb_main(is_admin))
                else:
                    await send_msg(cid, "❌ شما هنوز عضو نشده‌اید! لطفاً ابتدا عضو شوید و سپس دکمه تایید را بزنید.", None)
                return
            
            # --- سد دفاعی (بررسی اجباری بودن عضویت) ---
            if await handle_membership_flow(cid, user_id, is_admin, cb_data, txt, send_msg, MAIN_CHANNEL_URL, kb_main, is_member):
                return
            
            # --- مدیریت علاقه‌مندی‌ها ---
            if cb_data and txt.startswith("fav:"):
                await add_to_favorites(cid, user_id, int(txt.split(":")[1]), send_msg)
                return
            if cb_data and txt.startswith("del_fav:"):
                await remove_from_favorites(cid, user_id, int(txt.split(":")[1]), send_msg)
                return
                
            s = get_session(user_id) or {}
            
            # --- بخش پنل مدیریت ---
            if is_admin:
                if "📊 آمار ربات" in txt:
                    await send_msg(cid, await get_bot_stats())
                elif "👥 لیست کاربران" in txt:
                    await send_msg(cid, get_users_list())
                elif "📢 ارسال پیام همگانی" in txt:
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": True}}, upsert=True)
                    await send_msg(cid, "✍️ متن پیام را بفرستید:")
                    return
                
                admin_state = db["admin_state"].find_one({"_id": cid}) or {}
                if admin_state.get("waiting_broadcast"):
                    if "بازگشت به منو اصلی" in txt:
                        db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                        await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
                    else:
                        success = 0
                        for u in db["users"].find({}, {"user_id": 1}):
                            if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"):
                                success += 1
                        db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                        await send_msg(cid, f"✅ پیام به {success} کاربر ارسال شد.")
                    return
            
            # --- پردازش دستورات عمومی و منوی کاربری ---
            if "🔙 مرحله قبل" in txt:
                await handle_back_step(cid, user_id, is_admin)
            elif "علاقه‌مندی‌ها" in txt:
                await show_favorites(cid, user_id, send_msg, is_admin)
            elif "پشتیبانی" in txt:
                await show_support(cid, send_msg)
            elif "جستجوی سریع" in txt:
                await send_msg(cid, "نام محله یا ویژگی را بفرستید:")
            elif "گوش‌به‌زنگ" in txt:
                await register_alert(cid, user_id, s)
            elif any(kw in txt for kw in ["خرید", "فروش", "رهن", "اجاره", "منوی اصلی", "بودجه", "حداقل", "حداکثر"]) or any(x in txt for x in ["متر", "خواب", "میلیون", "میلیارد"]):
                await handle_user_actions(cid, user_id, txt, s, is_admin, set_session, push_history, handle_start_flow, parse_budget_text, kb_custom_budget, kb_meter, kb_khab, show_results, kb_main, send_msg)
            
            # --- جستجوی فایل‌ها در دیتابیس ---
            else:
                res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
                await show_results(cid, res, is_admin)
    except Exception as e:
        print(f"Error: {e}")
