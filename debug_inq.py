import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", SCOPES)
client = gspread.authorize(creds)
sh = client.open_by_key(SHEET_ID)

# 문의작성 시트 확인
wks = sh.worksheet("문의작성")
print("=== 문의작성 시트 (상태='견적' 행만) ===")
headers = wks.row_values(1)
print("Headers:", headers)
print("\nData rows:")
all_values = wks.get_all_values()
for i, row in enumerate(all_values[1:]):
    if len(row) > 13 and '견적' in row[13]:  # 14번째 컬럼(상태)이 '견적'인 행
        print(f"Row {i+1}: ID={row[0]}, 업체={row[2]}, 행사={row[3]}, 상태={row[13]}")
