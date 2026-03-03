import os
from dotenv import load_dotenv
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
print("Loaded GOOGLE_SERVICE_ACCOUNT_JSON =", os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))

GS_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
GSHEET_ID = os.environ["GSHEET_ID"]
WS_NAME = os.environ.get("GSHEET_WORKSHEET", "Sheet1")

scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
creds = Credentials.from_service_account_file(GS_JSON, scopes=scopes)
gc = gspread.authorize(creds)

sh = gc.open_by_key(GSHEET_ID)
ws = sh.worksheet(WS_NAME)

print("OK:", ws.title)
print("Rows:", ws.row_count, "Cols:", ws.col_count)
print("Sample records:", ws.get_all_records()[:2])