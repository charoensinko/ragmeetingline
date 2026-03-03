# app/main.py
import os

# ปิด TF logs
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from linebot.v3.webhook import WebhookParser
from linebot.v3.webhooks.models import MessageEvent, TextMessageContent

from app.rag import ask
from app.line_client import reply_text

from ingestion.ingest_sheets import ingest

app = FastAPI()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

if not LINE_CHANNEL_SECRET:
    raise RuntimeError("Missing LINE_CHANNEL_SECRET (Render Environment Variables)")
if not LINE_ADMIN_TOKEN:
    # ไม่บังคับก็ได้ แต่แนะนำให้ตั้งเสมอ
    print("WARNING: ADMIN_TOKEN is not set. /admin/ingest will be unusable.")

parser = WebhookParser(LINE_CHANNEL_SECRET)

# เก็บสถานะ ingestion ล่าสุดแบบง่าย ๆ
_last_ingest_status = {
    "running": False,
    "last_result": None,
    "last_error": None,
}


def _require_admin(request: Request):
    token = request.headers.get("X-ADMIN-TOKEN", "")
    if not LINE_ADMIN_TOKEN or token != LINE_ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _run_ingest_job():
    global _last_ingest_status
    _last_ingest_status["running"] = True
    _last_ingest_status["last_error"] = None
    try:
        res = ingest()
        _last_ingest_status["last_result"] = res
    except Exception as e:
        _last_ingest_status["last_error"] = str(e)
    finally:
        _last_ingest_status["running"] = False


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/admin/ingest/status")
def ingest_status(request: Request):
    _require_admin(request)
    return {"ok": True, **_last_ingest_status}


@app.post("/admin/ingest")
def ingest_trigger(request: Request, background_tasks: BackgroundTasks):
    """
    Trigger ingestion in background to avoid blocking.
    Security: header X-ADMIN-TOKEN must match ADMIN_TOKEN
    """
    _require_admin(request)

    if _last_ingest_status["running"]:
        return {"ok": True, "message": "Ingestion already running.", **_last_ingest_status}

    background_tasks.add_task(_run_ingest_job)
    return {"ok": True, "message": "Ingestion started."}


@app.post("/ask")
async def ask_api(payload: dict):
    q = (payload.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Missing query")
    return {"answer": ask(q)}


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    try:
        events = parser.parse(body.decode("utf-8"), signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            user_text = (event.message.text or "").strip()
            if not user_text:
                continue
            answer = ask(user_text)
            reply_text(event.reply_token, answer)

    return {"ok": True}