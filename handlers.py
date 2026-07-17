from property import handle_user_actions
import json
import re
from config import db, ADMIN_ID
from keyboards import (
    kb_main, kb_khab, kb_meter, kb_next, inline_action, kb_custom_budget
)
from core import (
    get_session, set_session, register_user, save_file, search_files,
    send_msg, send_pic, get_next_sequence_value
)
# ایمپورت تمامی توابع از آرشیو
from archive import (
    parse_budget_text, push_history, show_results, show_support, 
    handle_back_step, handle_start_flow, register_alert, 
    get_bot_stats, get_users_list
)

async def process_bale_webhook(data: dict):
    if "callback_query" in data:
        cb = data["callback_query"]
        cid = cb["message"]["chat"]["id"]
        if (d_val := cb.get("data", "")).startswith("fav:"):
            file_id = int(d_val.split(":")[1])
            if not db["favorites"].find_one({"user_id": cid, "file_id": file_id}):
                db["favorites"].insert_one({"user_id": cid, "file_id": file_id})
                await send_msg(cid, "✅ این فایل به لیست علاقه‌مندی‌های شما اضافه شد.")
            else: await send_msg(cid, "⚠️ این فایل قبلاً در لیست علاقه‌مندی‌های شما ثبت شده است.")
        return

    msg = data.get("message") or data.get("edited_message") or data.get("body")
    if not msg: return
    chat = msg.get("chat", {})
    txt = msg.get("text", "") or msg.get("caption", "")
    cid, ctype = chat.get("id"), chat.get("type")
    first_name = msg.get("from", {}).get("first_name", "کاربر گرامی")

    if ctype == "channel":
        if "photo" in msg and "موجود" in txt:
            photos = [msg["photo"][-1]["file_id"]]
            await save_file(txt, photos)
        return

    if ctype == "private":
        user_id = cid
        register_user(cid, first_name)
        is_admin = (user_id == ADMIN_ID)
        s = get_session(user_id) or {}

        if is_admin:
            admin_state = db["admin_state"].find_one({"_id": cid}) or {}
            if admin_state.get("waiting_broadcast"):
                if txt == "بازگشت به منو اصلی":
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, "عملیات لغو شد.")
                else:
                    success_count = 0
                    for u in db["users"].find({}, {"user_id": 1}):
                        if await send_msg(u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"): success_count += 1
                    db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": False}}, upsert=True)
                    await send_msg(cid, f"✅ پیام با موفقیت به {success_count} کاربر ارسال شد.")
                return
            if txt == "📊 آمار ربات":
                await send_msg(cid, await get_bot_stats())
                return
            elif txt == "👥 لیست کاربران":
                users_list = get_users_list()
                await send_msg(cid, f"👥 **کاربران:**\n\n{users_list}" if users_list else "کاربری یافت نشد.")
                return
            elif txt == "📢 ارسال پیام همگانی":
                db["admin_state"].update_one({"_id": cid}, {"$set": {"waiting_broadcast": True}}, upsert=True)
                await send_msg(cid, "✍️ متن پیام همگانی را بفرستید:")
                return

        if txt == "🔙 مرحله قبل": await handle_back_step(cid, user_id, is_admin); return
        
        if any(x in txt for x in ["/start", "بازگشت به منو اصلی", "🏠 خرید", "🏠 فروش", "🔑 رهن و اجاره", "💵", "خواب", "مشاهده همه", "متر"]):
            await handle_user_actions(cid, user_id, txt, s, is_admin, set_session, push_history, 
                                      handle_start_flow, parse_budget_text, kb_custom_budget, 
                                      kb_meter, search_files, show_results, kb_main, send_msg)
        
        elif txt == "⭐ علاقه‌مندی‌ها":
            favs = list(db["favorites"].find({"user_id": user_id}))
            if not favs: await send_msg(cid, "لیست علاقه‌مندی‌های شما خالی است.")
            else:
                for f in favs:
                    if r := db["files"].find_one({"id": f["file_id"]}):
                        cap = f"⭐ **ملک نشان شده**\n\n{r['text'][:300]}..."
                        photos = json.loads(r["photos"]) if r.get("photos") else []
                        await send_pic(cid, photos[0], cap, inline_action(r["id"])) if photos else await send_msg(cid, r["text"], inline_action(r["id"]))
        elif "پشتیبانی" in txt:
            await show_support(cid, send_msg)
        elif "🔍 جستجوی سریع" in txt: await send_msg(cid, "کافیست نام محله یا ویژگی مورد نظرتان را بنویسید و بفرستید:")
        elif "🔔 تنظیم گوش‌به‌زنگ" in txt:
            await register_alert(cid, user_id, s)
        else:
            if not is_admin:
                res = list(db["files"].find({"text": {"$regex": txt, "$options": "i"}}).limit(5))
                await show_results(cid, res, is_admin)
