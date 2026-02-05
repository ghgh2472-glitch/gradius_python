import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", SCOPES)
client = gspread.authorize(creds)
sh = client.open_by_key(SHEET_ID)

wks = sh.worksheet("견적상세")
print("=== 견적상세 시트 직접 접근 ===")

print("Step 1: get_all_records() 시도")
try:
    records = wks.get_all_records()
    print(f"✅ get_all_records() 성공: {len(records)} 행")
except Exception as e:
    print(f"❌ get_all_records() 실패: {type(e).__name__}")
    print(f"   에러 메시지: {str(e)}")
    print(f"   'duplicates' 포함? {'duplicates' in str(e)}")
    
    print("\nStep 2: raw get_all_values() 시도")
    all_values = wks.get_all_values()
    print(f"✅ get_all_values() 성공: {len(all_values)} 행")
    
    print("\nStep 3: 헤더 확인")
    headers = all_values[0] if len(all_values) > 0 else []
    print(f"헤더: {headers}")
    print(f"헤더 중 '사업자번호' 개수: {headers.count('사업자번호')}")
