# keyboards.py
from config import MAIN_CHANNEL_URL

def kb_main(is_admin=False):
    kb = [
    [{"text": "🏠 خرید"}, {"text": "🔑 رهن و اجاره"}],
    [{"text": "🔍 جستجوی سریع"}, {"text": "⭐ علاقه‌مندی‌ها"}],
    [{"text": "🔔 تنظیم گوش‌به‌زنگ"}, {"text": "📞 پشتیبانی"}]
    ]
    
    if is_admin:
        kb.append([{"text": "📊 آمار ربات"}, {"text": "👥 لیست کاربران"}])
        kb.append([{"text": "📢 ارسال پیام همگانی"}, {"text": "بازگشت به منو اصلی"}])
    return {"keyboard": kb, "resize_keyboard": True}

def kb_khab():
    return {
        "keyboard": [
            [{"text": "۱ خواب"}, {"text": "۲ خواب"}],
            [{"text": "۳ خواب"}, {"text": "۴ خواب و بیشتر"}],
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }


def kb_budget_2khab():
    return {
        "keyboard": [
            [{"text": "۱۵ الی ۲۰ میلیارد"}, {"text": "۲۰ الی ۲۵ میلیارد"}],
            [{"text": "۲۵ الی ۳۰ میلیارد"}, {"text": "۳۰ الی ۳۵ میلیارد"}],
            [{"text": "۳۵ الی ۴۰ میلیارد"}, {"text": "۴۰ الی ۵۰ میلیارد"}],
            [{"text": "۵۰ الی ۶۰ میلیارد"}, {"text": "۶۰ میلیارد به بالا"}],
            [{"text": "📋 مشاهده همه فایل‌ها"}],
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }


def kb_budget_3khab():
    return {
        "keyboard": [
            [{"text": "۲۵ الی ۳۰ میلیارد"}, {"text": "۳۰ الی ۳۵ میلیارد"}],
            [{"text": "۳۵ الی ۴۰ میلیارد"}, {"text": "۴۰ الی ۵۰ میلیارد"}],
            [{"text": "۵۰ الی ۶۰ میلیارد"}, {"text": "۶۰ میلیارد به بالا"}],
            [{"text": "📋 مشاهده همه فایل‌ها"}],
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }


def kb_meter_2khab():
    return {
        "keyboard": [
            [{"text": "زیر ۸۰ متر"}, {"text": "۸۰ الی ۱۰۰ متر"}],
            [{"text": "۱۰۰ الی ۱۲۰ متر"}, {"text": "۱۲۰ متر به بالا"}],
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }


def kb_meter_3khab():
    return {
        "keyboard": [
            [{"text": "۱۰۰ الی ۱۲۵ متر"}, {"text": "۱۲۵ الی ۱۵۰ متر"}],
            [{"text": "۱۵۰ الی ۱۷۰ متر"}, {"text": "۱۷۰ متر به بالا"}],
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

 def inline_action(fid):
    share_url = f"https://ble.ir/share/url?url=https://t.me/BrokerBot?start=file_{fid}"
    return {
        "inline_keyboard": [
            [
                {"text": "🚀 خرید و فروش", "url": "https://ble.ir/broker_amlak"},
                {"text": "🚀 رهن و اجاره", "url": "https://ble.ir/BROKER_amlak2"}
            ],
            [
                {"text": "⭐ افزودن به علاقه‌مندی", "callback_data": f"fav:{fid}"}, 
                {"text": "🔗 اشتراک‌گذاری", "url": share_url}
            ]
        ]
    }

