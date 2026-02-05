# test_conn.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# 사용자님의 시트 ID (확실하게 박아넣음)
SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def test():
    print("---------------------------------------------------")
    print("🕵️‍♂️ 구글 시트 연결 테스트를 시작합니다...")
    print("---------------------------------------------------")

    # 1. 키 파일 존재 확인
    if not os.path.exists("secrets.json"):
        print("❌ [실패] secrets.json 파일이 없습니다!")
        return

    print("✅ secrets.json 파일 발견!")

    try:
        # 2. 인증 시도
        creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", SCOPES)
        client = gspread.authorize(creds)
        print("✅ 인증 성공! (키 파일 내용이 올바릅니다)")
    except Exception as e:
        print(f"❌ [실패] 인증 오류: {e}")
        print("👉 힌트: secrets.json의 'type'이 'service_account'인지 확인하세요.")
        return

    try:
        # 3. 시트 접근 시도
        sh = client.open_by_key(SHEET_ID)
        print(f"✅ 시트 접속 성공! 제목: {sh.title}")
        
        # 4. 워크시트 목록 확인
        print("\n[현재 시트 목록]")
        worksheets = sh.worksheets()
        target_found = False
        for ws in worksheets:
            print(f" - {ws.title}")
            if ws.title == "문의작성":
                target_found = True
        
        print("---------------------------------------------------")
        if target_found:
            print("🎉 [완벽] '문의작성' 시트를 찾았습니다! 이제 프로그램이 잘 될 겁니다.")
        else:
            print("⚠️ [주의] '문의작성' 시트가 안 보입니다. 탭 이름을 확인해주세요.")
            
    except Exception as e:
        print(f"❌ [실패] 시트 열기 오류: {e}")
        print("👉 힌트: secrets.json 안의 'client_email' 주소를 시트에 '공유(편집자)' 했는지 확인하세요.")

if __name__ == "__main__":
    test()