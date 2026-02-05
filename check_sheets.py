import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = '13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

credentials = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', SCOPES)
client = gspread.authorize(credentials)
sh = client.open_by_key(SHEET_ID)

# STAFF 시트 헤더
try:
    wks = sh.worksheet('STAFF')
    headers = wks.row_values(1)
    print('=== STAFF 시트 헤더 ===')
    for i, h in enumerate(headers, 1):
        print(f'{i}. {h}')
    print(f'\n총 {len(headers)}개 컬럼')
    print(f'총 {len(wks.col_values(1))-1}명 데이터')
except Exception as e:
    print(f'STAFF 오류: {e}')

# 인건비 시트 헤더
try:
    wks = sh.worksheet('인건비')
    headers = wks.row_values(1)
    print('\n=== 인건비 시트 헤더 ===')
    for i, h in enumerate(headers, 1):
        print(f'{i}. {h}')
except Exception as e:
    print(f'\n인건비 오류: {e}')

# 모든 시트
print('\n=== 현재 스프레드시트의 모든 시트 ===')
for ws in sh.worksheets():
    print(f'- {ws.title}')
