"""test_inquiry_save.py
문의 등록 기능 테스트
"""
from datetime import datetime
import uuid
import data_loader as db

# 테스트 데이터 준비
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
new_id = str(uuid.uuid4())[:8]

test_row = [
    new_id,                     # 문의ID
    now_str,                    # 작성일
    "테스트 회사",              # 업체명
    "담당자",                   # 담당자
    "010-1234-5678",            # 연락처
    "테스트 행사",              # 행사명
    "서울시 강남구",            # 장소
    "2026-02-10",               # 시작일
    "2026-02-11",               # 종료일
    "09:00-18:00",              # 시간
    "보안요원",                 # 서비스종류
    "5",                        # 요청인원
    "150000",                   # 페이
    "접수",                     # 상태
    "테스트 특이사항",          # 특이사항
    ""                          # 비고
]

print("=" * 60)
print("📝 문의 등록 테스트")
print("=" * 60)
print(f"\n📌 테스트 데이터:")
print(f"   문의ID: {new_id}")
print(f"   업체명: 테스트 회사")
print(f"   행사명: 테스트 행사")
print(f"   연락처: 010-1234-5678")

print(f"\n🔄 저장 중...")
result, msg = db.append_row("inq", test_row)

print(f"\n📊 결과:")
print(f"   성공: {result}")
print(f"   메시지: {msg}")

if result:
    print(f"\n✅ 문의 등록 성공!")
else:
    print(f"\n❌ 문의 등록 실패!")
    print(f"\n💡 확인사항:")
    print(f"   1. secrets.json이 프로젝트 루트에 있는지 확인")
    print(f"   2. Google Service Account 이메일이 시트에 공유되었는지 확인")
    print(f"   3. '문의작성' 시트가 존재하는지 확인")
