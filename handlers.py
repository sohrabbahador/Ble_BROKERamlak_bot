# handlers.py
import httpx
from config import ADMIN_ID, MAIN_CHANNEL_URL, TOKEN, db
from core import (
    get_session, 
    register_user, 
    save_file, 
    send_msg,
    set_session
)
from archive import (
    add_to_favorites,
    get_bot_stats,
    get_users_list,
    handle_back_step,
    handle_membership_flow,
    register_alert,
    remove_from_favorites,
    send_welcome_message,
    show_favorites,
    show_support
)
from keyboards import kb_main
from property import handle_user_actions
from rent_property import handle_rent_flow


async def is_member(user_id):
    try:
        u = f"@{MAIN_CHANNEL_URL.split('/')[-1].lstrip('@')}"
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"https://tapi.bale.ai/bot{TOKEN}/getChatMember",
                json={"chat_id": u, "user_id": user_id},
                timeout=10,
            )
            return r.json().get("ok") and r.json()["result"].get("status") in [
                "member",
                "administrator",
                "creator",
            ]
    except:
        return False


async def process_bale_webhook(d: dict):
    try:
        cb, msg = (
            d.get("callback_query"),
            d.get("message") or d.get("edited_message") or d.get("body"),
        )
        if cb:
            cid, ct, txt = (
                cb["message"]["chat"]["id"],
                cb["message"]["chat"]["type"],
                cb.get("data", ""),
            )
        elif msg:
            cid, ct, txt = (
                msg.get("chat", {}).get("id"),
                msg.get("chat", {}).get("type"),
                msg.get("text", "") or msg.get("caption", ""),
            )
        else:
            return
        if not cid:
            return
        uid, adm = cid, cid == ADMIN_ID

        if ct == "channel":
            if msg and "photo" in msg and "موجود" in txt:
                await save_file(txt, [msg["photo"][-1]["file_id"]])
            return

        if ct == "private":
            if txt == "/start":
                name = (
                    (msg.get("from", {}) if msg else {})
                    .get("first_name", "کاربر")
                )
                register_user(cid, name)
                await send_welcome_message(
                    cid, name, uid, adm, MAIN_CHANNEL_URL, kb_main
                )
                return

        if cb and txt == "check_membership":
            ok = await is_member(uid)
            await send_msg(
                cid,
                "✅ عضویت شما تایید شد. اکنون می‌توانید از تمامی خدمات استفاده کنید." if ok else "❌ شما هنوز عضو نشده‌اید! لطفاً ابتدا عضو شوید و سپس دکمه تایید را بزنید.",
                kb_main(adm) if ok else None,
            )
            return

        if await handle_membership_flow(
            cid, uid, adm, cb, txt, MAIN_CHANNEL_URL, kb_main, is_member
        ):
            return

        if cb and txt.startswith("fav:"):
            await add_to_favorites(cid, uid, int(txt.split(":")[1]))
            return
        if cb and txt.startswith("del_fav:"):
            await remove_from_favorites(cid, uid, int(txt.split(":")[1]))
            return

        s = get_session(uid) or {}

        if adm:
            if "📊 آمار ربات" in txt:
                await send_msg(cid, get_bot_stats())
                return
            elif "👥 لیست کاربران" in txt:
                await send_msg(cid, get_users_list())
                return
            elif "📢 ارسال همگانی" in txt:
                db["admin_state"].update_one(
                    {"_id": cid},
                    {"$set": {"waiting_broadcast": True}},
                    upsert=True,
                )
                await send_msg(cid, "✍️ متن پیام را بفرستید:")
                return

        state_adm = db["admin_state"].find_one({"_id": cid}) or {}
        if state_adm.get("waiting_broadcast"):
            if "بازگشت به منو اصلی" in txt:
                db["admin_state"].update_one(
                    {"_id": cid},
                    {"$set": {"waiting_broadcast": False}},
                    upsert=True,
                )
                await send_msg(cid, "به منوی اصلی بازگشتید:", kb_main(adm))
            else:
                sc = sum(
                    1
                    for u in db["users"].find({}, {"user_id": 1})
                    if await send_msg(
                        u["user_id"], f"📢 **پیام مدیریت:**\n\n{txt}"
                    )
                )
                db["admin_state"].update_one(
                    {"_id": cid},
                    {"$set": {"waiting_broadcast": False}},
                    upsert=True,
                )
                await send_msg(cid, f"✅ پیام به {sc} کاربر ارسال شد.")
            return

        if "🔙 مرحله قبل" in txt:
            await handle_back_step(cid, uid, adm)
        elif "علاقه‌مندی‌ها" in txt:
            await show_favorites(cid, uid, adm)
        elif "پشتیبانی" in txt:
            await show_support(cid)
        elif "گوش‌به‌زنگ" in txt:
            await register_alert(cid, uid, s)
        elif txt == "🔑 رهن و اجاره" or s.get("flow") == "rent":
            if txt == "🔑 رهن و اجاره":
                set_session(uid, flow="rent")
            await handle_rent_flow(cid, uid, s, txt)
        elif txt == "🏠 خرید" or s.get("flow") == "buy":
            if txt == "🏠 خرید":
                set_session(uid, flow="buy")
                from core import handle_start_flow
                await handle_start_flow(cid, uid, "خرید")
                return
            await handle_user_actions(cid, uid, txt, s, adm)
        else:
            if s.get("flow") == "rent":
                await handle_rent_flow(cid, uid, s, txt)
            else:
                await handle_user_actions(cid, uid, txt, s, adm)

    except Exception as e:
        print(f"Error in process_bale_webhook: {e}")
