# ingestion/ingest_sheets.py
import os
import re
import tempfile
from datetime import datetime, date as date_type
from dotenv import load_dotenv

import gspread
from google.oauth2.service_account import Credentials
from dateutil import parser as dateparser
from supabase import create_client

from ingestion.embed_local import embed_passages
from ingestion.row_to_text import row_to_text

# Local dev only: load .env if present (Render จะใช้ env vars อยู่แล้ว)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

GSHEET_ID = os.getenv("GSHEET_ID")
WS_NAME = os.getenv("GSHEET_WORKSHEET", "Sheet1")

# Render-friendly: store JSON in env
GS_JSON_INLINE = os.getenv("GOOGLE_SA_JSON")
# Local-friendly: use file path
GS_JSON_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./service_account.json")


def parse_date(value) -> str | None:
    """
    รองรับ:
    - string: '2 Mar 2026', '2026-03-02', '3/2/2026'
    - datetime/date object
    คืน ISO 'YYYY-MM-DD'
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date_type):
        return value.isoformat()

    s = str(value).strip()

    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass

    try:
        dt = dateparser.parse(s, dayfirst=True)
        return dt.date().isoformat() if dt else None
    except Exception:
        return None


def parse_time(s: str) -> str:
    """
    normalize '9:00 น.' '09:00' '9.00' -> 'HH:MM' if possible, else original stripped
    """
    if not s:
        return ""
    raw = str(s).strip()
    raw = raw.replace("น.", "").replace("น", "").strip()
    raw = raw.replace(".", ":")

    m = re.search(r"(\d{1,2})\s*:\s*(\d{2})", raw)
    if not m:
        return raw.strip()

    hh = int(m.group(1))
    mm = int(m.group(2))
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return f"{hh:02d}:{mm:02d}"
    return raw.strip()


def split_departments(raw: str) -> list[str]:
    """
    "ทอ., กก., บข." -> ["ทอ.", "กก.", "บข."]
    """
    if not raw:
        return []
    parts = [p.strip() for p in str(raw).split(",")]
    return [p for p in parts if p]


def _build_creds() -> Credentials:
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    if GS_JSON_INLINE:
        # Render: write env JSON into a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(GS_JSON_INLINE)
            temp_path = f.name
        return Credentials.from_service_account_file(temp_path, scopes=scopes)

    # Local: use json file path
    return Credentials.from_service_account_file(GS_JSON_PATH, scopes=scopes)


def ingest() -> dict:
    """
    Run ingestion:
    - Read Google Sheets (Thai headers)
    - Convert each row to content
    - Embed (local)
    - Replace doc_chunks for this sheet in Supabase
    Return dict summary.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    if not GSHEET_ID:
        raise RuntimeError("Missing GSHEET_ID")
    if not (GS_JSON_INLINE or os.path.exists(GS_JSON_PATH)):
        raise RuntimeError("Missing GOOGLE_SA_JSON (Render) or GOOGLE_SERVICE_ACCOUNT_JSON file (local)")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1) Upsert documents row for this sheet
    supabase.table("documents").upsert(
        {
            "source": "gsheet",
            "title": f"Meetings Sheet: {WS_NAME}",
            "external_id": GSHEET_ID,
        },
        on_conflict="source,external_id",
    ).execute()

    # fetch document_id
    doc_row = (
        supabase.table("documents")
        .select("id")
        .eq("source", "gsheet")
        .eq("external_id", GSHEET_ID)
        .single()
        .execute()
    )
    document_id = doc_row.data["id"]

    # 2) Read sheet
    creds = _build_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GSHEET_ID)
    ws = sh.worksheet(WS_NAME)

    records = ws.get_all_records()
    if not records:
        # Replace existing with empty (optional)
        supabase.table("doc_chunks").delete().eq("document_id", document_id).execute()
        return {"ok": True, "inserted": 0, "message": "No records found in sheet."}

    # 3) Normalize keys: exact Thai headers
    normalized = []
    for i, r in enumerate(records, start=2):  # header row = 1
        date_raw = (r.get("วันที่") or "").strip()
        topic = (r.get("หัวข้อ") or "").strip()
        depts = (r.get("ฝ่ายที่ต้องเข้าร่วม") or "").strip()
        start_time_raw = (r.get("เวลาเริ่ม") or "").strip()
        zoom = (r.get("ลิงค์ Zoom") or "").strip()
        notes = (r.get("หมายเหตุ") or "").strip()

        normalized.append(
            {
                "row_id": str(i),
                "date": date_raw,
                "topic": topic,
                "departments": depts,
                "start_time": start_time_raw,
                "zoom_link": zoom,
                "notes": notes,
            }
        )

    # 4) Build content + embeddings
    contents = [row_to_text(r) for r in normalized]
    embeddings = embed_passages(contents)

    # 5) Replace all chunks for this document (MVP simplest)
    supabase.table("doc_chunks").delete().eq("document_id", document_id).execute()

    payload = []
    for r, content, emb in zip(normalized, contents, embeddings):
        payload.append(
            {
                "document_id": document_id,
                "row_id": r["row_id"],
                "meeting_date": parse_date(r["date"]),
                "topic": r["topic"],
                "departments": r["departments"],
                "departments_arr": split_departments(r["departments"]),
                "start_time": parse_time(r["start_time"]),
                "zoom_link": r["zoom_link"],
                "notes": r["notes"],
                "content": content,
                "metadata": {
                    "sheet_id": GSHEET_ID,
                    "worksheet": WS_NAME,
                    "row_id": r["row_id"],
                    "raw_date": r["date"],
                    "raw_start_time": r["start_time"],
                },
                "embedding": emb,
            }
        )

    supabase.table("doc_chunks").insert(payload).execute()
    return {"ok": True, "inserted": len(payload)}


if __name__ == "__main__":
    # Local run (recommended):
    # python -m ingestion.ingest_sheets
    result = ingest()
    print(result)