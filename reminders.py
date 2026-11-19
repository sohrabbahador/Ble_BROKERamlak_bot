"""
سیستم یادآوری مستقل ربات بروکر
نسخه نهایی پایدار - ارسال شبانه ساعت ۹ تهران
- الف: ۳۵ روز مانده به پایان اجاره‌نامه (لیست یکجا + نام مالک بولد)
- ب: یک روز مانده به یادآوری دستی (پیام مجزا + دکمه پیگیری)
- تشخیص تغییر/حذف فیلدها و پاکسازی خودکار رکوردهای قبلی
- محاسبه دقیق با تقویم جلالی
- جلوگیری از ثبت/ارسال آلارم تاریخ‌گذشته
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import re
import psycopg
import os
import jdatetime
import pytz

DATABASE_URL = os.getenv("DATABASE_URL")
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

_send_message_func = None
_admin_id = None


# ==================== کمکی زمان ====================
def now_tehran_naive() -> datetime:
    """الان به وقت تهران (بدون tzinfo برای ذخیره در DB)"""
    return datetime.now(TEHRAN_TZ).replace(tzinfo=None)


def today_tehran() -> datetime:
    """امروز ساعت ۰۰:۰۰ به وقت تهران"""
    n = now_tehran_naive()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def subtract_jalali_days(gregorian_dt: datetime, days: int) -> datetime:
    """کم کردن تعداد روز با تقویم جلالی (دقیق‌تر از timedelta میلادی)"""
    jdt = jdatetime.datetime.fromgregorian(datetime=gregorian_dt)
    j_target = jdt - jdatetime.timedelta(days=days)
    return j_target.togregorian().replace(hour=0, minute=0, second=0, microsecond=0)


# ==================== دیتابیس ====================
def get_db():
    return psycopg.connect(DATABASE_URL)


def init_reminders_table():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id                  SERIAL PRIMARY KEY,
            property_code       TEXT NOT NULL,
            reminder_text       TEXT,
            reminder_at         TIMESTAMP,
            reminder_type       TEXT DEFAULT 'manual',
            owner_name          TEXT,
            notified            BOOLEAN DEFAULT FALSE,
            followed_up         BOOLEAN DEFAULT FALSE,
            source_message_id   BIGINT,
            created_at          TIMESTAMP DEFAULT NOW(),
            last_checked        TIMESTAMP
        )
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_reminders_code_type
        ON reminders (property_code, reminder_type)
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_reminders_due
        ON reminders (reminder_at)
        WHERE notified = FALSE AND reminder_at IS NOT NULL
    """)

    for col, definition in [
        ("followed_up", "BOOLEAN DEFAULT FALSE"),
        ("owner_name", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE reminders ADD COLUMN IF NOT EXISTS {col} {definition}")
        except Exception:
            pass

    # پاکسازی یک‌باره رکوردهای قدیمی سیستم قبلی
    try:
        c.execute("""
            DELETE FROM reminders
            WHERE reminder_type NOT IN ('lease_end_35d', 'manual')
               OR reminder_type IS NULL
        """)
        if c.rowcount > 0:
            print(f"🧹 {c.rowcount} رکورد قدیمی پاک شد")
    except Exception:
        pass

    conn.commit()
    conn.close()


def save_or_update_reminder(
    property_code: str,
    reminder_text: Optional[str] = None,
    reminder_at: Optional[datetime] = None,
    reminder_type: str = "manual",
    owner_name: Optional[str] = None,
    source_message_id: Optional[int] = None,
    force_notified: bool = False,
) -> Optional[int]:
    """
    ذخیره یا به‌روزرسانی.
    اگر force_notified=True باشد (تاریخ گذشته)، از ابتدا notified=True ثبت می‌شود
    تا آلارم الکی ارسال نشود.
    """
    if not property_code or property_code == "—":
        return None

    conn = get_db()
    c = conn.cursor()
    now = now_tehran_naive()

    c.execute("""
        SELECT id, notified, reminder_at
        FROM reminders
        WHERE property_code = %s AND reminder_type = %s
        ORDER BY id DESC LIMIT 1
    """, (property_code, reminder_type))

    row = c.fetchone()
    reminder_id = None

    if row:
        rid, already_notified, old_at = row
        reminder_id = rid

        time_changed = False
        if reminder_at is not None and old_at is not None:
            time_changed = (
                reminder_at.replace(microsecond=0) != old_at.replace(microsecond=0)
            )
        elif reminder_at is not None and old_at is None:
            time_changed = True

        if time_changed:
            notified_val = True if force_notified else False
            c.execute("""
                UPDATE reminders SET
                    reminder_text = %s,
                    reminder_at = %s,
                    owner_name = COALESCE(%s, owner_name),
                    source_message_id = COALESCE(%s, source_message_id),
                    notified = %s,
                    followed_up = FALSE,
                    last_checked = %s
                WHERE id = %s
            """, (reminder_text, reminder_at, owner_name, source_message_id,
                  notified_val, now, rid))
        else:
            c.execute("""
                UPDATE reminders SET
                    reminder_text = COALESCE(%s, reminder_text),
                    reminder_at = COALESCE(%s, reminder_at),
                    owner_name = COALESCE(%s, owner_name),
                    source_message_id = COALESCE(%s, source_message_id),
                    last_checked = %s
                WHERE id = %s
            """, (reminder_text, reminder_at, owner_name, source_message_id, now, rid))
    else:
        notified_val = True if force_notified else False
        c.execute("""
            INSERT INTO reminders
                (property_code, reminder_text, reminder_at, reminder_type,
                 owner_name, notified, followed_up, source_message_id, created_at, last_checked)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s)
            RETURNING id
        """, (
            property_code,
            reminder_text,
            reminder_at,
            reminder_type,
            owner_name,
            notified_val,
            source_message_id,
            now, now
        ))
        reminder_id = c.fetchone()[0]

    conn.commit()
    conn.close()
    return reminder_id


def delete_reminder(property_code: str, reminder_type: str) -> bool:
    if not property_code or property_code == "—":
        return False
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        DELETE FROM reminders
        WHERE property_code = %s AND reminder_type = %s
    """, (property_code, reminder_type))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def mark_followed_up(reminder_id: int) -> bool:
    """حذف کامل رکورد بعد از پیگیری"""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_due_reminders(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    if now is None:
        now = now_tehran_naive()

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, property_code, reminder_text, reminder_at, reminder_type, owner_name
        FROM reminders
        WHERE notified = FALSE
          AND (followed_up = FALSE OR followed_up IS NULL)
          AND reminder_at IS NOT NULL
          AND reminder_at <= %s
          AND reminder_type IN ('lease_end_35d', 'manual')
        ORDER BY reminder_type, reminder_at ASC
    """, (now,))
    rows = c.fetchall()

    results = []
    for rid, code, text, r_at, rtype, owner in rows:
        results.append({
            "id": rid,
            "property_code": code,
            "reminder_text": text,
            "reminder_at": r_at,
            "reminder_type": rtype,
            "owner_name": owner,
        })
        c.execute("""
            UPDATE reminders
            SET notified = TRUE, last_checked = %s
            WHERE id = %s
        """, (now, rid))

    conn.commit()
    conn.close()
    return results


def get_active_reminders(limit: int = 30, reminder_type: str = None) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()

    # پاکسازی رکوردهای قدیمی
    try:
        c.execute("""
            DELETE FROM reminders
            WHERE reminder_type NOT IN ('lease_end_35d', 'manual')
               OR reminder_type IS NULL
        """)
        if c.rowcount > 0:
            print(f"🧹 {c.rowcount} رکورد قدیمی پاک شد")
            conn.commit()
    except Exception as e:
        print("cleanup error:", e)

    if reminder_type:
        c.execute("""
            SELECT id, property_code, reminder_text, reminder_at, reminder_type,
                   notified, followed_up, created_at, owner_name
            FROM reminders
            WHERE reminder_type = %s
            ORDER BY reminder_at ASC NULLS LAST
            LIMIT %s
        """, (reminder_type, limit))
    else:
        c.execute("""
            SELECT id, property_code, reminder_text, reminder_at, reminder_type,
                   notified, followed_up, created_at, owner_name
            FROM reminders
            WHERE reminder_type IN ('lease_end_35d', 'manual')
            ORDER BY reminder_at ASC NULLS LAST
            LIMIT %s
        """, (limit,))

    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "property_code": r[1],
            "reminder_text": r[2],
            "reminder_at": r[3],
            "reminder_type": r[4],
            "notified": r[5],
            "followed_up": r[6],
            "created_at": r[7],
            "owner_name": r[8],
        }
        for r in rows
    ]


# ==================== پارس تاریخ شمسی قوی ====================
def parse_jalali_datetime(text: str) -> Optional[datetime]:
    if not text:
        return None

    text = text.strip()

    patterns = [
        r'(\d{1,2}):(\d{2})(?:\s+(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2}))',
        r'(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?',
        r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?',
    ]

    for i, pat in enumerate(patterns):
        m = re.search(pat, text)
        if not m:
            continue
        try:
            g = m.groups()

            if i == 0:
                hour = int(g[0])
                minute = int(g[1])
                jy, jm, jd = int(g[2]), int(g[3]), int(g[4])
                second = 0
            elif i == 1:
                jy, jm, jd = int(g[0]), int(g[1]), int(g[2])
                hour = int(g[3]) if g[3] else 0
                minute = int(g[4]) if g[4] else 0
                second = int(g[5]) if g[5] else 0
            else:
                jd, jm, jy = int(g[0]), int(g[1]), int(g[2])
                hour = int(g[3]) if g[3] else 0
                minute = int(g[4]) if g[4] else 0
                second = int(g[5]) if g[5] else 0

            if not (1300 <= jy <= 1500 and 1 <= jm <= 12 and 1 <= jd <= 31):
                continue
            if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                continue

            jdt = jdatetime.datetime(jy, jm, jd, hour, minute, second)
            return jdt.togregorian()
        except Exception:
            continue

    return None


def to_jalali_str(dt: datetime, with_time: bool = False) -> str:
    if not dt:
        return "—"
    try:
        jdt = jdatetime.datetime.fromgregorian(datetime=dt)
        if jdt.year < 1300 or jdt.year > 1500:
            return "—"
        if with_time and (jdt.hour or jdt.minute):
            return jdt.strftime("%Y/%m/%d %H:%M")
        return jdt.strftime("%Y/%m/%d")
    except Exception:
        return "—"


def days_until(dt: datetime) -> Optional[int]:
    """تعداد روز باقی‌مانده تا تاریخ (منفی = گذشته)"""
    if not dt:
        return None
    try:
        today = today_tehran()
        delta = dt.replace(hour=0, minute=0, second=0, microsecond=0) - today
        return delta.days
    except Exception:
        return None


# ==================== استخراج فیلدهای بخش خصوصی ====================
def _parse_private_section(full_text: str) -> Dict[str, str]:
    private = {}
    if not full_text:
        return private

    marker = "——— بخش خصوصی"
    if marker not in full_text:
        for alt in ["--- بخش خصوصی", "———بخش خصوصی", "بخش خصوصی"]:
            if alt in full_text:
                marker = alt
                break
        else:
            return private

    part = full_text.split(marker, 1)[1]
    pattern = r"^([^:\n]+):\s*(.*)$"
    for line in part.splitlines():
        line = line.strip()
        if not line or line.startswith("———") or line.startswith("---"):
            continue
        m = re.match(pattern, line)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip()
            private[key] = value
    return private


def extract_reminder_fields(fields: dict, full_text: str = None) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[datetime], Optional[str]
]:
    private = _parse_private_section(full_text or "")

    owner_name = None
    for key in ["نام مالک", "نام‌مالک", "مالک", "owner"]:
        if key in private and private[key].strip():
            owner_name = private[key].strip()
            break
        if key in fields and fields[key].strip():
            owner_name = fields[key].strip()
            break

    lease_end_raw = None
    for key in [
        "تاریخ پایان اجاره‌نامه", "تاریخ پایان اجاره نامه",
        "تاریخ پایان اجاره", "تاریخ پایان قرارداد",
        "پایان اجاره‌نامه", "پایان اجاره نامه",
    ]:
        if key in private and private[key].strip():
            lease_end_raw = private[key].strip()
            break
        if key in fields and fields[key].strip():
            lease_end_raw = fields[key].strip()
            break

    reminder_raw = None
    reminder_text = None
    for key in ["یادآوری", "یادآوری ", "یاد اوری", "آلارم", "reminder"]:
        if key in private and private[key].strip():
            reminder_raw = private[key].strip()
            break
        if key in fields and fields[key].strip():
            reminder_raw = fields[key].strip()
            break

    if not reminder_raw and full_text:
        for line in full_text.splitlines():
            line = line.strip()
            if line.startswith(("یادآوری", "یاد آوری", "آلارم")):
                if ":" in line:
                    reminder_raw = line.split(":", 1)[1].strip()
                else:
                    reminder_raw = line
                break

    reminder_date = None
    if reminder_raw:
        reminder_date = parse_jalali_datetime(reminder_raw)
        reminder_text = reminder_raw

    return owner_name, lease_end_raw, reminder_text, reminder_date, reminder_raw


# ==================== سرویس اصلی ====================
def configure(send_message_func, admin_id: int):
    global _send_message_func, _admin_id
    _send_message_func = send_message_func
    _admin_id = admin_id
    init_reminders_table()


def _send(text: str, reply_markup=None):
    if not _send_message_func or not _admin_id:
        print("⚠️ سیستم یادآوری هنوز configure نشده")
        return
    _send_message_func(_admin_id, text, reply_markup=reply_markup)


def send_lease_end_batch(items: List[Dict[str, Any]]):
    if not items:
        return

    lines = ["📢 *۳۵ روز مانده به پایان اجاره‌نامه*\n"]
    for it in items:
        code = it["property_code"]
        owner = it.get("owner_name") or "—"
        lines.append(f"• {code} — *{owner}*")

    lines.append("\n— سیستم یادآوری")
    _send("\n".join(lines))


def send_manual_reminder(item: Dict[str, Any]):
    code = item["property_code"]
    text = item.get("reminder_text") or "—"
    r_at = item.get("reminder_at")
    rid = item.get("id")

    msg = (
        f"⏰ *یادآوری فردا*\n\n"
        f"🏠 کد: {code}\n"
        f"📝 متن: {text}\n"
        f"📅 تاریخ: {to_jalali_str(r_at)}"
    )

    reply_markup = None
    if rid:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ پیگیری کردم", "callback_data": f"done_reminder_{rid}"}
            ]]
        }

    _send(msg, reply_markup=reply_markup)


def process_reminders_from_fields(
    fields: dict,
    property_code: str,
    source_msg_id: Optional[int] = None,
    full_text: str = None,
):
    if not property_code or property_code == "—":
        return

    owner_name, lease_end_raw, reminder_text, reminder_date, _ = extract_reminder_fields(
        fields, full_text
    )

    today = today_tehran()

    # پاکسازی رکوردهای قدیمی سیستم قبلی برای این کد
    for old_type in ("one_month_before", "due", "auto"):
        if delete_reminder(property_code, old_type):
            print(f"🗑️ رکورد قدیمی ({old_type}) کد {property_code} حذف شد")

    # ---------- الف: ۳۵ روز مانده به پایان اجاره‌نامه ----------
    if lease_end_raw:
        end_date = parse_jalali_datetime(lease_end_raw)
        if end_date:
            # محاسبه دقیق با تقویم جلالی
            target = subtract_jalali_days(end_date, 35)

            # اگر تاریخ اعلام از قبل گذشته → ثبت ولی بدون آلارم
            force_notified = target < today

            auto_text = f"۳۵ روز مانده به پایان اجاره‌نامه ({lease_end_raw})"
            save_or_update_reminder(
                property_code=property_code,
                reminder_text=auto_text,
                reminder_at=target,
                reminder_type="lease_end_35d",
                owner_name=owner_name,
                source_message_id=source_msg_id,
                force_notified=force_notified,
            )
            status = " (تاریخ گذشته - بدون آلارم)" if force_notified else ""
            print(f"✅ یادآوری ۳۵روزه برای کد {property_code} → {to_jalali_str(target)}{status}")
        else:
            if delete_reminder(property_code, "lease_end_35d"):
                print(f"🗑️ یادآوری ۳۵روزه کد {property_code} حذف شد (تاریخ نامعتبر)")
    else:
        if delete_reminder(property_code, "lease_end_35d"):
            print(f"🗑️ یادآوری ۳۵روزه کد {property_code} حذف شد (فیلد خالی)")

    # ---------- ب: یادآوری دستی (یک روز مانده) ----------
    if reminder_text and reminder_date:
        target = subtract_jalali_days(reminder_date, 1)

        force_notified = target < today

        save_or_update_reminder(
            property_code=property_code,
            reminder_text=reminder_text,
            reminder_at=target,
            reminder_type="manual",
            owner_name=owner_name,
            source_message_id=source_msg_id,
            force_notified=force_notified,
        )
        status = " (تاریخ گذشته - بدون آلارم)" if force_notified else ""
        print(f"✅ یادآوری دستی برای کد {property_code} → {to_jalali_str(target)}{status}")
    else:
        if delete_reminder(property_code, "manual"):
            print(f"🗑️ یادآوری دستی کد {property_code} حذف شد")


def check_due_reminders() -> List[Dict[str, Any]]:
    due_list = get_due_reminders()
    if not due_list:
        return []

    lease_items = [i for i in due_list if i["reminder_type"] == "lease_end_35d"]
    manual_items = [i for i in due_list if i["reminder_type"] == "manual"]

    if lease_items:
        send_lease_end_batch(lease_items)
        print(f"📢 لیست ۳۵روزه ارسال شد ({len(lease_items)} مورد)")

    for item in manual_items:
        send_manual_reminder(item)
        print(f"⏰ یادآوری دستی ارسال شد → کد {item['property_code']}")

    return due_list
