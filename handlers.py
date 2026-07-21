import json
import httpx
from archive import (add_to_favorites, get_bot_stats, get_users_list, handle_back_step,
                     handle_membership_flow, handle_start_flow, parse_budget_text,
                     push_history, register_alert, remove_from_favorites,
                     send_welcome_message, show_favorites, show_results, show_support)
from config import ADMIN_ID, MAIN_CHANNEL_URL, TOKEN, db
from core import get_session, register_user, save_file, send_msg, send_pic, set_session
from keyboards import kb_main
from property import handle_user_actions
from .rent_property import handle_rent_flow

async def is_member(user_id):
    try:
        ch_username = MAIN_CHANNEL_URL.split("/")[-1]
        ch_username = f"@{ch_username}" if not ch_username.startswith("@") else ch_username
        api_url = f"https://tapi.bale.ai/bot{TOKEN}/getChatMember"
        async with httpx.AsyncClient() as client:
            resp = await client.post(api_url, json={"chat_id": ch_username, "user_id": user_id}, timeout=10)
            data = resp.json()
            return data.get("ok") and data["result"].get("status") in ["member", "administrator", "creator"]
    except:
        return False

async def process_bale_webhook(data: dict):
    try:
        cb_data, msg_data = data.get("callback_query"), data.get("message") or data.get("edited_message") or data.get("body")
        if cb_data:
            cid, chat_type, txt = cb_data["message"]["chat"]["id"], cb_data["message"]["chat"]["type"], cb_data.get("data", "")
        elif msg_data:
            cid, chat_type, txt = msg_data.get("chat", {}).get("id"), msg_data.get("chat", {}).get("type"), msg_data.get("text", "") or msg_data.get("caption", "")
        else:
            return
            
        if not cid: return
        user_id, is_admin = cid, cid == ADMIN_ID
        
        if chat_type == "channel":
            if msg_data and "photo" in msg_data and "موجود" in txt:
                await save_file(txt, [msg_data["photo"][-1]["file_id"]])
            return
            
        if chat_type == "private":
            if txt == "/start":
                name = msg_data.get("from", {}).get("first_name", "کاربر") if msg_data else "کاربر"
                register_user(cid, name)
                await send_welcome_message(cid, name, user_id, is_admin, MAIN_CHANNEL_URL, kb_main)
                return
            
            if cb_data and txt == "check_membership":
                if await is_member(user_id):
                    await send_msg(cid, "✅ عضویت شما تایید شد. اکنون می‌توانید از تمامی خدمات استفاده کنید.", kb_main(is_admin))
                else:
                    await send_msg(cid, "❌ شما هنوز عضو نشده‌اید! لطفاً ابتدا عضو شوید و سپس دکمه تایید را بزنید.", None)
                return
            
            if await handle_membership_flow(cid, user_id, is_admin, cb_data, txt, MAIN_CHANNEL_URL, kb_main, is_member):
                return
            
            if cb_data and txt.startswith("fav:"):
                await add_to_favorites(cid, user_id, int(txt.split(":")[1]))
                return
            if cb_data and txt.startswith("del_fav:"):
                await remove_from_favorites(cid, user_id, int(txt.split(":")[1]))
                return
                
            s = get_session(user_id) or {}
            
            if is_admin:
                if "📊 آمار ربات" in txt:
                    await send_msg(cid, await get_bot_stats())
                    return
                elif "👥 لیست کاربران" in txt:
                    await send_msg(cid, get_users_list())
                    return
                elif "📢 ارسال همگانی" in txt:
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": True}}, upsert=True)
                    await send_msg(cid, "✍️ متن پیام را بفرستید:")
                    return
                
                admin_state = db["admin_state"].find_one({"_id": cid}) or {}
                if admin_state.get("waiting_broadcast"):
                    if "بازگشت به منو اصلی" in txt:
                        db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                        await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(is_admin))
                    else:
                        success = sum(1 for u in db["users"].find({}, {"user_id": 1}) if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"))
                        db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                        await send_msg(cid, f"✅ پیام به {success} کاربر ارسال شد.")
                    return

            if "🔙 مرحله قبل" in txt:
                await handle_back_step(cid, user_id, is_admin)
            elif "علاقه‌مندی‌ها" in txt:
                await show_favorites(cid, user_id, is_admin)
            elif "پشتیبانی" in txt:
                await show_support(cid)
            elif "گوش‌به‌زنگ" in txt:
                await register_alert(cid, user_id, s)
            else:
                await handle_user_actions(cid, user_id, txt, s, is_admin)

    except Exception as e:
        print(f"Error in process_bale_webhook: {e}")
