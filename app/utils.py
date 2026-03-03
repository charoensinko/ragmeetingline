import os
import re
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

TZ = os.environ.get("TIMEZONE", "Asia/Bangkok")

THAI_WEEKDAYS = {
    "จันทร์": 0,
    "อังคาร": 1,
    "พุธ": 2,
    "พฤหัสบดี": 3,
    "พฤหัส": 3,
    "ศุกร์": 4,
    "เสาร์": 5,
    "อาทิตย์": 6,
}

def now_local() -> datetime:
    return datetime.now(ZoneInfo(TZ))

def today_date_iso() -> str:
    return now_local().date().isoformat()

def extract_dept_keyword(text: str) -> str | None:
    m = re.search(r"ฝ่าย\s*([A-Za-zก-๙\.]+)", (text or ""))
    return m.group(1).strip() if m else None

def extract_relative_label(text: str) -> str | None:
    t = (text or "")
    if "มะรืน" in t:
        return "มะรืน"
    if "พรุ่งนี้" in t:
        return "พรุ่งนี้"
    if "วันนี้" in t:
        return "วันนี้"
    return None

def detect_meeting_intent(text: str) -> dict:
    t = (text or "").lower()
    raw = text or ""

    wants_zoom = ("zoom" in t) or ("ลิงค์ zoom" in raw) or ("ลิงก์ zoom" in raw) or ("ขอ link" in t) or ("ขอลิงก์" in raw) or ("ขอลิงค์" in raw)
    wants_time = ("กี่โมง" in raw) or ("เวลา" in raw) or ("เริ่ม" in raw)
    wants_topic = ("หัวข้อ" in raw) or ("เรื่องอะไร" in raw) or ("topic" in t)

    mentions_workshop = ("workshop" in t) or ("เวิร์กชอป" in raw)
    mentions_meeting = ("ประชุม" in raw) or ("meeting" in t)

    if not mentions_meeting and not mentions_workshop and (wants_time or wants_topic or wants_zoom):
        mentions_meeting = True

    return {
        "wants_zoom": wants_zoom,
        "wants_time": wants_time,
        "wants_topic": wants_topic,
        "mentions_workshop": mentions_workshop,
        "mentions_meeting": mentions_meeting,
    }

# -------- Date parsing helpers --------

def extract_date_filter_iso(text: str) -> str | None:
    """
    คืน ISO date 'YYYY-MM-DD' สำหรับคำถามแบบ 'วันเดียว'
    - วันนี้ / พรุ่งนี้ / มะรืน
    - วันที่รูปแบบ: 2 Mar 2026
    - วันในสัปดาห์: วันจันทร์นี้/วันอังคารนี้/.../วันอาทิตย์นี้
    """
    t = (text or "").strip()
    base = now_local().date()

    if "มะรืน" in t:
        return (base + timedelta(days=2)).isoformat()
    if "พรุ่งนี้" in t:
        return (base + timedelta(days=1)).isoformat()
    if "วันนี้" in t:
        return base.isoformat()

    # weekday phrases e.g. "วันจันทร์นี้"
    wd = extract_weekday_date_iso(t)
    if wd:
        return wd[0]  # iso date

    # Explicit date like "2 Mar 2026" / "2 March 2026"
    m = re.search(
        r"\b(\d{1,2})\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
        r"January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{4})\b",
        t,
        re.IGNORECASE,
    )
    if m:
        day = int(m.group(1))
        mon = m.group(2)
        year = int(m.group(3))
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                dt = datetime.strptime(f"{day} {mon} {year}", fmt)
                return dt.date().isoformat()
            except ValueError:
                pass

    return None

def extract_date_range_iso(text: str) -> tuple[str, str, str] | None:
    """
    คืน (start_iso, end_iso, label) แบบ inclusive สำหรับช่วงสัปดาห์:
    - สัปดาห์นี้ / อาทิตย์นี้
    - สัปดาห์หน้า / อาทิตย์หน้า
    นิยามสัปดาห์: จันทร์–อาทิตย์
    """
    t = (text or "").strip()

    is_this_week = ("สัปดาห์นี้" in t) or ("อาทิตย์นี้" in t)
    is_next_week = ("สัปดาห์หน้า" in t) or ("อาทิตย์หน้า" in t)

    if not is_this_week and not is_next_week:
        return None

    d = now_local().date()
    start_this = d - timedelta(days=d.weekday())   # Monday
    start = start_this + timedelta(days=7) if is_next_week else start_this
    end = start + timedelta(days=6)

    label = "สัปดาห์หน้า" if is_next_week else ("สัปดาห์นี้" if "สัปดาห์นี้" in t else "อาทิตย์นี้")
    if is_next_week and "อาทิตย์หน้า" in t:
        label = "อาทิตย์หน้า"

    return (start.isoformat(), end.isoformat(), label)

def extract_weekday_date_iso(text: str) -> tuple[str, str] | None:
    """
    รองรับ: วันจันทร์นี้/วันอังคารนี้/.../วันอาทิตย์นี้
    กติกา:
    - เลือก "ครั้งถัดไป" ของวันนั้นที่ >= วันนี้
      เช่น วันนี้วันพุธ ถ้าถาม "วันจันทร์นี้" -> จะเป็นวันจันทร์ของสัปดาห์หน้า (เพราะจันทร์สัปดาห์นี้ผ่านแล้ว)
    คืน (date_iso, label)
    """
    t = (text or "")

    # ต้องมีคำว่า "วัน" และลงท้ายด้วย "นี้" เพื่อกันจับมั่ว
    m = re.search(r"วัน(จันทร์|อังคาร|พุธ|พฤหัสบดี|พฤหัส|ศุกร์|เสาร์|อาทิตย์)นี้", t)
    if not m:
        return None

    wd_name = m.group(1)
    target_wd = THAI_WEEKDAYS[wd_name]

    today = now_local().date()
    today_wd = today.weekday()

    delta = (target_wd - today_wd) % 7
    # ถ้าเป็นวันเดียวกัน "วัน...นี้" ให้ตีความเป็นวันนี้
    target_date = today + timedelta(days=delta)

    label = f"วัน{wd_name}นี้"
    return (target_date.isoformat(), label)