# RAG LINE Meeting Bot (MVP)

## 0) Prepare
- Create Supabase project
- Create LINE Messaging API channel
- Create Google Service Account + enable Google Sheets API
- Share the Google Sheet to the service account email (Viewer is OK)

## 1) Install
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

## 2) Setup env
Copy .env.example -> .env แล้วกรอกค่าให้ครบ
วาง service_account.json ตาม path ใน GOOGLE_SERVICE_ACCOUNT_JSON

## 3) Setup Supabase SQL
Run in Supabase SQL Editor:
- sql/schema.sql
- sql/rpc.sql

## 4) Ingest Google Sheets -> Supabase
python ingestion/ingest_sheets.py

## 5) Run API
uvicorn app.main:app --host 0.0.0.0 --port 8000

Test:
POST http://localhost:8000/ask
{"query":"วันนี้ฝ่ายไหนต้องเข้าร่วมประชุมบ้าง"}
{"query":"ฝ่าย กต. ต้องเข้าร่วม workshop วันไหน"}
{"query":"วันนี้เริ่มประชุมกี่โมง ขอ link zoom ด้วย"}

## 6) LINE Webhook
Expose public url with ngrok/cloudflare tunnel
Set LINE Webhook URL:
https://<public-url>/webhook