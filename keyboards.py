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

def kb_custom_budget(khab_type: str):
    """تولید منوی بودجه داینامیک و متناسب با تعداد خواب انتخاب شده"""
    suffix = "خواب‌ها"
    if khab_type == "۴ خواب و بیشتر":
        suffix = "۴خواب‌ها به بالا"
    else:
        suffix = f"{khab_type}ها"

    return {
        "keyboard": [
            [{"text": "💵 حداقل بودجه"}, {"text": "💵 حداکثر بودجه"}],
            [{"text": f"📋 مشاهده همه {suffix}"}],
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def kb_meter():
    return {
        "keyboard": [
            [{"text": "کمتر از ۱۰۰ متر"}, {"text": "۱۰۰ تا ۱۵۰ متر"}],
            [{"text": "۱۵۰ تا ۲۰۰ متر"}, {"text": "بیشتر از ۲۰۰ متر"}],
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
        ],
        "resize_keyboard": True
    }

def kb_next():
    return {
        "keyboard": [
            [{"text": "🔙 مرحله قبل"}, {"text": "بازگشت به منو اصلی"}]
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
