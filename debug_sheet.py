import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", SCOPES)
client = gspread.authorize(creds)
sh = client.open_by_key(SHEET_ID)

# 견적상세 시트 확인
wks = sh.worksheet("견적상세")
print("=== 견적상세 시트 ===")
print("Row 1 (Headers):")
headers = wks.row_values(1)
print(headers)
print("\nFirst 5 rows:")
all_values = wks.get_all_values()
for i, row in enumerate(all_values[:6]):
    print(f"Row {i}:", row)

print("\n=== 각 컬럼별 데이터 ===")
for col_idx, header in enumerate(headers):
    col_data = [row[col_idx] if col_idx < len(row) else '' for row in all_values[1:6]]
    print(f"{col_idx+1}. {header}: {col_data}")
