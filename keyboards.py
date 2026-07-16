# keyboards.py
from config import MAIN_CHANNEL_URL

def kb_main(is_admin=False):
    kb = [
        [{"text": "🏠 خرید"}, {"text": "🔑 رهن و اجاره"}],
        [{"text": "🔍 جستجوی سریع"}, {"text": "⭐ علاقه‌مندی‌ها"}],
        [{"text": "🔔 تنظیم گوش‌به‌زنگ"}]
    ]
    if is_admin:
        kb.append([{"text": "📊 آمار ربات"}, {"text": "📢 ارسال پیام همگانی"}])
    return {"keyboard": kb, "resize_keyboard": True}

def kb_khab():
    return {
        "keyboard": [
            [{"text": "۱ خواب"}, {"text": "۲ خواب"}],
            [{"text": "۳ خواب"}, {"text": "۴ خواب و بیشتر"}],
            [{"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def kb_budje_forosh():
    return {
        "keyboard": [
            [{"text": "۲۰ تا ۳۰ میلیارد"}, {"text": "۳۰ تا ۴۰ میلیارد"}],
            [{"text": "۴۰ تا ۵۰ میلیارد"}, {"text": "۵۰ میلیارد به بالا"}],
            [{"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def kb_budje_rahn():
    return {
        "keyboard": [
            [{"text": "کمتر از ۲ میلیارد"}, {"text": "۲ تا ۴ میلیارد"}],
            [{"text": "۴ تا ۶ میلیارد"}, {"text": "۶ میلیارد به بالا"}],
            [{"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def kb_meter():
    return {
        "keyboard": [
            [{"text": "کمتر از ۱۰۰ متر"}, {"text": "۱۰۰ تا ۱۵۰ متر"}],
            [{"text": "۱۵۰ تا ۲۰۰ متر"}, {"text": "بیشتر از ۲۰۰ متر"}],
            [{"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def kb_next():
    return {
        "keyboard": [
            [{"text": "صفحه بعد"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def inline_action(fid):
    share_url = f"https://ble.ir/share/url?url=https://t.me/BrokerBot?start=file_{fid}"
    return {
        "inline_keyboard": [
            [{"text": "🚀 مشاهده در کانال", "url": MAIN_CHANNEL_URL}],
            [{"text": "⭐ افزودن به علاقه‌مندی", "callback_data": f"fav:{fid}"}, {"text": "🔗 اشتراک‌گذاری", "url": share_url}]
        ]
    }
