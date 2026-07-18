import json
import re
import httpx
from config import db, ADMIN_ID, TOKEN, MAIN_CHANNEL_URL
from keyboards import kb_main, kb_khab, kb_meter, kb_next, inline_action, kb_custom_budget
from core import (
    get_session, set_session, register_user, save_file, search_files,
    send_msg, send_pic, get_next_sequence_value
)
from archive import (
    parse_budget_text, push_history, show_results, show_support, 
    handle_back_step, handle_start_flow, register_alert, 
    get_bot_stats, get_users_list
)
from property import handle_user_actions

# تابع بررسی عضویت
async def is_member(user_id):
    try:
        channel_id = "@" + MAIN_CHANNEL_URL.split("/")[-1]
        api_url = f"https://tapi.bale.ai/bot{TOKEN}/getChatMember"
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json={"chat_id": channel_id, "user_id": user_id})
            data = response.json()
            return data.get("ok") and data["result"]["status"] in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Error checking membership: {e}")
        return False

async def process_bale_webhook(data: dict):
    cb_data = data.get("callback_query")
    msg_data = data.get("message") or data.get("edited_message") or data.get("body")
    
    if cb_data:
        cid = cb_data["message"]["chat"]["id"]
        txt = cb_data.get("data", "") 
    elif msg_data:
        chat = msg_data.get("chat", {})
        cid = chat.get("id")
        txt = msg_data.get("text", "") or msg_data.get("caption", "")
    else:
        return

    if not cid: return
    user_id = cid
    is_admin = (user_id == ADMIN_ID)

    # --- پردازش دکمه‌های شیشه‌ای ---
    if cb_data:
        d_val = cb_data.get("data", "")
        
        if d_val == "بررسی عضویت":
            if await is_member(user_id):
                await send_msg(cid, "✅ عضویت شما تایید شد. حالا می‌توانید از تمامی خدمات ربات استفاده کنید.")
            else:
                await send_msg(cid, "❌ شما هنوز عضو کانال نشده‌اید. لطفا ابتدا عضو شوید:", {
                    "inline_keyboard": [
                        [{"text": "📢 عضویت در کانال", "url": MAIN_CHANNEL_URL}],
                        [{"text": "✅ عضو شدم (تایید)", "callback_data": "بررسی عضویت"}]
                    ]
                })
            return

        if d_val.startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            if not db["favorites"].find_one({"user_id": cid, "file_id": file_id}):
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این ملک به لیست علاقه‌مندی‌های شما اضافه شد.")
            else: 
                await send_msg(cid, "⚠️ این ملک قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
            return

    # --- پردازش پیام‌های متنی ---
    if not msg_data: return 
    
    chat_type = msg_data.get("chat", {}).get("type")
    if chat_type == "channel":
        if "photo" in msg_data and "موجود" in txt:
            photos = [msg_data["photo"][-1]["file_id"]]
            await save_file(txt, photos)
        return

    if chat_type == "private":
        register_user(cid, msg_data.get("from", {}).get("first_name", "کاربر گرامی"))
        s = get_session(user_id) or {}

        # ۱. بخش مدیریت ادمین
        if is_admin:
            admin_state = db["admin_state"].find_one({"_id": cid}) or {}
            if admin_state.get("waiting_broadcast"):
                if txt == "بازگشت به منو اصلی":
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, "❌ عملیات ارسال پیام لغو شد.")
                else:
                    success_count = 0
                    for u in db["users"].find({}, {"user_id": 1}):
                        if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"): 
                            success_count += 1
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.")
                return
            
            if txt == "📊 آمار ربات":
                stats = await get_bot_stats()
                await send_msg(cid, stats)
                return
            elif txt == "👥 لیست کاربران":
                users_list = get_users_list()
                await send_msg(cid, f"👥 **لیست کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")
                return
            elif txt == "📢 ارسال پیام همگانی":
                db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": True}}, upsert=True)
                await send_msg(cid, "✍️ لطفاً متن پیام همگانی خود را بنویسید و بفرستید:")
                return

        # ۲. استارت آزاد (بدون چک عضویت)
        if txt == "/start":
            await send_msg(cid, "به ربات املاک بروکر خوش آمدید. برای شروع، یکی از گزینه‌های زیر را انتخاب کنید:", kb_main(is_admin))
            return

        # ۳. گیت‌وی عضویت (برای تمام دکمه‌ها و درخواست‌های دیگر غیر-ادمین)
        if not is_admin and not await is_member(user_id):
            await send_msg(cid, 
                "⚠️ **برای دسترسی به این بخش، لطفاً ابتدا در کانال ما عضو شوید:**\n\n"
                "تا زمانی که عضو نشوید، امکان مشاهده املاک و استفاده از منوها وجود ندارد.", 
                {
                    "inline_keyboard": [
                        [{"text": "📢 عضویت در کانال", "url": MAIN_CHANNEL_URL}],
                        [{"text": "✅ عضو شدم (تایید)", "callback_data": "بررسی عضویت"}]
                    ]
                }
            )
            return

        # ۴. پردازش عملیات کاربر (فقط اگر ادمین باشد یا عضو کانال شده باشد)
        if txt == "🔙 مرحله قبل": 
            await handle_back_step(cid, user_id, is_admin)
            return
        
        if txt == "⭐ علاقه‌مندی‌ها":
            favs = list(db["favorites"].find({"user_id": user_id}))
            if not favs: 
                await send_msg(cid, "لیست علاقه‌مندی‌های شما در حال حاضر خالی است.")
            else:
                for f in favs:
                    if r := db["files"].find_one({"id": f["file_id"]}):
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        if photos: await send_pic(cid, photos[0], cap, inline_action(r["id"]))
                        else: await send_msg(cid, r["text"], inline_action(r["id"]))
            return

        elif "پشتیبانی" in txt: 
            await show_support(cid, send_msg)
        elif "جستجوی سریع" in txt: 
            await send_msg(cid, "کافیست نام محله، منطقه یا ویژگی مورد نظرتان را بنویسید و بفرستید:")
        elif "🔔 تنظیم گوش‌به‌زنگ" in txt: 
            await register_alert(cid, user_id, s)
        elif txt in ["🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره", "🏠 منوی اصلی"] or any(x in txt for x in ["متر", "خواب", "میلیون", "میلیارد"]):
            await handle_user_actions(cid, user_id, txt, s, is_admin, set_session, push_history, 
                                      handle_start_flow, parse_budget_text, kb_custom_budget, 
                                      kb_meter, search_files, show_results, kb_main, send_msg)
        else:
            # جستجوی متنی در دیتابیس برای کاربر
            if not is_admin:
                res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
                await show_results(cid, res, is_admin)
