from fastapi import FastAPI, Request
import httpx

app = FastAPI()

BOT_TOKEN = "1163386061:P7CDH8D1hGtiZ1OB1-5jXuOClUgRK1y3TeU"

files_db = []
user_state = {}

def extract_tags(text):
    return [w for w in text.split() if w.startswith('#')]

class FileItem:
    def __init__(self, text, tags):
        self.text = text
        self.tags = tags

    @property
    def is_mojood(self):
        return "#موجود" in self.tags

    @property
    def type_op(self):
        if "#فروش" in self.tags:
            return "خرید"
        if "#رهن‌واجاره" in self.tags:
            return "رهن‌واجاره"
        return None

    @property
    def khab(self):
        if "#۲خواب" in self.tags:
            return 2
        if "#۳خواب" in self.tags:
            return 3
        return None

    @property
    def budget_group(self):
        if "#۲۰میلیارد" in self.tags:
            return "20-25"
        if "#۲۵میلیارد" in self.tags:
            return "25-30"
        if "#۳۰میلیارد" in self.tags:
            return "30-40"
        if "#۴۰میلیارد" in self.tags:
            return "40-50"
        if "#۵۰میلیارد" in self.tags:
            return "50+"
        return None

async def send_message(chat_id, text):
    url = f"https://tapi.bale.ai/bot{BOT_TOKEN}/sendMessage"
    await httpx.AsyncClient().post(url, json={"chat_id": chat_id, "text": text})

async def send_buttons(chat_id, buttons):
    keyboard = [[{"text": b}] for b in buttons]
    url = f"https://tapi.bale.ai/bot{BOT_TOKEN}/sendMessage"
    await httpx.AsyncClient().post(url, json={
        "chat_id": chat_id,
        "text": "انتخاب کن:",
        "reply_markup": {"keyboard": keyboard, "resize_keyboard": True}
    })

async def show_files(chat_id, type_op=None, khab=None, budget=None):
    results = []
    for f in files_db:
        if not f.is_mojood:
            continue
        if type_op and f.type_op != type_op:
            continue
        if khab and f.khab != khab:
            continue
        if budget and f.budget_group != budget:
            continue
        results.append(f)

    if not results:
        await send_message(chat_id, "فایلی با این فیلتر پیدا نشد.")
        return

    for f in results[:20]:
        await send_message(chat_id, f.text)

@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    if "message" in data and "chat" in data["message"] and data["message"]["chat"]["type"] == "channel":
        text = data["message"].get("text", "")
        tags = extract_tags(text)
        item = FileItem(text, tags)
        if item.is_mojood:
            files_db.append(item)
        return {"ok": True}

    if "message" in data:
        msg = data["message"].get("text", "")
        chat_id = data["message"]["chat"]["id"]

        state = user_state.get(chat_id, {"step": 1})

        if state["step"] == 1:
            if msg == "خرید":
                state["type"] = "خرید"
            elif msg == "رهن و اجاره":
                state["type"] = "رهن‌واجاره"
            elif msg == "فایل‌های موجود":
                await show_files(chat_id)
                return {"ok": True}

            state["step"] = 2
            user_state[chat_id] = state
            await send_buttons(chat_id, ["۲ خواب", "۳ خواب"])
            return {"ok": True}

        if state["step"] == 2:
            if msg == "۲ خواب":
                state["khab"] = 2
            elif msg == "۳ خواب":
                state["khab"] = 3

            if state["type"] == "خرید":
                state["step"] = 3
                user_state[chat_id] = state
                await send_buttons(chat_id, ["۲۰ تا ۲۵", "۲۵ تا ۳۰", "۳۰ تا ۴۰", "۴۰ تا ۵۰", "۵۰ به بالا"])
                return {"ok": True}
            else:
                await show_files(chat_id, type_op=state["type"], khab=state["khab"])
                return {"ok": True}

        if state["step"] == 3:
            budget_map = {
                "۲۰ تا ۲۵": "20-25",
                "۲۵ تا ۳۰": "25-30",
                "۳۰ تا ۴۰": "30-40",
                "۴۰ تا ۵۰": "40-50",
                "۵۰ به بالا": "50+"
            }
            state["budget"] = budget_map.get(msg)
            user_state[chat_id] = state
            await show_files(chat_id, type_op=state["type"], khab=state["khab"], budget=state["budget"])
            return {"ok": True}

    return {"ok": True}
