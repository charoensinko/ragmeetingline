import os
from app.supabase_client import get_supabase
from app.openrouter_client import chat_completion
from app.prompts import SYSTEM_PROMPT
from app.utils import (
    extract_dept_keyword,
    extract_date_filter_iso,
    extract_date_range_iso,
    extract_relative_label,
    detect_meeting_intent,
    extract_weekday_date_iso,
)

from ingestion.embed_local import embed_query  # local embedding
import re

TOP_K = int(os.environ.get("TOP_K", "5"))
SIM_THRESHOLD = float(os.environ.get("SIM_THRESHOLD", "0.35"))


def build_context(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        lines.append(
            f"- row_id={r.get('row_id')} | วันที่={r.get('meeting_date')} | หัวข้อ={r.get('topic')} | "
            f"ฝ่าย={r.get('departments')} | เวลาเริ่ม={r.get('start_time')} | "
            f"Zoom={r.get('zoom_link')} | หมายเหตุ={r.get('notes')}"
        )
    return "\n".join(lines)


def answer_from_rows(query: str, rows: list[dict]) -> str:
    context = build_context(rows)
    user_prompt = f"""คำถาม: {query}

CONTEXT:
{context}

โปรดสรุปคำตอบให้ชัดเจน:
- ถ้ามีหลายรายการ ให้จัดเป็นรายการเรียงตามวันและเวลา
- แสดงเวลาเริ่ม + หัวข้อ + (ถ้ามี) Zoom link
- ถ้าผู้ใช้ถามว่า "ฝ่ายไหนต้องเข้าร่วม" ให้สรุปรายชื่อฝ่ายด้วย
"""
    ans = chat_completion(SYSTEM_PROMPT, user_prompt)

    # ✅ post-process: ตัดบรรทัด "อ้างอิง: ..." ทิ้ง (กันกรณี LLM ใส่มาเอง)
    ans = re.sub(r"\n?อ้างอิง:.*$", "", ans, flags=re.DOTALL).strip()

    return ans


def no_meeting_message(query: str, label: str, date_iso: str | None, dept_filter: str | None) -> str:
    intent = detect_meeting_intent(query)

    base = label if label else (f"วันที่ {date_iso}" if date_iso else "ช่วงที่ถาม")
    scope = f"ฝ่าย {dept_filter} " if dept_filter else ""

    if intent["mentions_workshop"] and not intent["mentions_meeting"]:
        noun = "Workshop"
    elif intent["mentions_meeting"] and not intent["mentions_workshop"]:
        noun = "ประชุม"
    else:
        noun = "ประชุม/Workshop"

    if intent["wants_zoom"]:
        return f"{base}{scope}ไม่มี{noun} จึงไม่มีลิงก์ Zoom\n\nอ้างอิง: (ตารางประชุม)"
    return f"{base}{scope}ไม่มี{noun}\n\nอ้างอิง: (ตารางประชุม)"


def ask(query: str) -> str:
    supabase = get_supabase()

    dept_filter = extract_dept_keyword(query)

    # 0) จับ label เฉพาะ (วันนี้/พรุ่งนี้/มะรืน) และ (วันจันทร์นี้ ฯลฯ)
    rel_label = extract_relative_label(query)
    weekday_info = extract_weekday_date_iso(query)  # (iso, label) หรือ None

    # 1) ช่วงสัปดาห์ (สัปดาห์นี้/อาทิตย์นี้/สัปดาห์หน้า/อาทิตย์หน้า)
    date_range = extract_date_range_iso(query)
    if date_range:
        start_date, end_date, range_label = date_range
        q = (
            supabase.table("doc_chunks")
            .select("row_id,meeting_date,topic,departments,start_time,zoom_link,notes")
            .gte("meeting_date", start_date)
            .lte("meeting_date", end_date)
        )
        if dept_filter:
            q = q.contains("departments_arr", [dept_filter])

        resp = q.order("meeting_date", desc=False).order("start_time", desc=False).execute()
        rows = resp.data or []
        if not rows:
            return no_meeting_message(query, range_label, None, dept_filter)
        return answer_from_rows(query, rows)

    # 2) วันเดียว (วันนี้/พรุ่งนี้/มะรืน/วันจันทร์นี้/วันที่ระบุ)
    date_filter = extract_date_filter_iso(query)
    if date_filter:
        # label สำหรับตอบกรณีไม่พบ
        label = rel_label or (weekday_info[1] if weekday_info else None)

        q = (
            supabase.table("doc_chunks")
            .select("row_id,meeting_date,topic,departments,start_time,zoom_link,notes")
            .eq("meeting_date", date_filter)
        )
        if dept_filter:
            q = q.contains("departments_arr", [dept_filter])

        resp = q.order("start_time", desc=False).execute()
        rows = resp.data or []
        if not rows:
            return no_meeting_message(query, label, date_filter, dept_filter)
        return answer_from_rows(query, rows)

    # 3) ไม่ระบุวัน/ช่วง → RAG fallback
    q_emb = embed_query(query)
    resp = supabase.rpc(
        "match_meetings",
        {
            "query_embedding": q_emb,
            "match_count": TOP_K,
            "date_filter": None,
            "dept_filter": dept_filter,
        },
    ).execute()

    rows = resp.data or []
    top_score = float(rows[0].get("score", 0)) if rows else 0.0

    if (not rows) or (top_score < SIM_THRESHOLD):
        user_prompt = f"""คำถาม: {query}

CONTEXT:
(ไม่พบข้อมูลที่มั่นใจได้ในตาราง หรือข้อมูลไม่พอ)

โปรดตอบตามกติกา"""
        return chat_completion(SYSTEM_PROMPT, user_prompt)

    return answer_from_rows(query, rows)