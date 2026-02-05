import gspread
from google.oauth2.service_account import Credentials
import os

# 1. 인증 설정
key_path = r"C:\Users\Win11\Desktop\gradius_python\service_account.json"

if not os.path.exists(key_path):
    print(f"❌ 오류: 열쇠 파일이 없습니다! 경로를 확인하세요: {key_path}")
else:
    print(f"✅ 열쇠 파일 확인됨")
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        # 열쇠로 로봇 소환
        creds = Credentials.from_service_account_file(key_path, scopes=scopes)
        
        # 🔥 [중요] 로봇이 자기 이름을 말합니다.
        print(f"\n🤖 로봇 이메일: {creds.service_account_email}")
        print("👉 위 이메일 주소가 엑셀 파일에 '공유(초대)' 되어 있나요? (확인 필수!)\n")

        client = gspread.authorize(creds)

        # 2. 구글 시트 열기
        sheet_id = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
        
        print("⏳ 접속 시도 중...")
        sh = client.open_by_key(sheet_id)
        
        print(f"🎉 대성공! [{sh.title}] 파일에 접속했습니다.")
        
        # 데이터 읽어보기
        worksheet = sh.get_worksheet(0) 
        val = worksheet.acell('E8').value
        print(f"📢 E8 셀의 값: {val}")

    except Exception as e:
        print("\n🚨 [비상] 에러가 발생했습니다! 아래 내용을 복사해서 알려주세요.")
        print("------------------------------------------------------")
        print(repr(e))  # 에러의 속살을 그대로 보여줌
        print("------------------------------------------------------")