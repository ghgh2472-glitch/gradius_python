# test_assignment_flow.py
# 배정 프로세스 전체 흐름 테스트

import sys
sys.path.insert(0, 'c:\\Users\\Win11\\Desktop\\gradius_python')

import data_loader as db
from datetime import datetime
import pandas as pd

print("=" * 70)
print("배정 프로세스 통합 테스트")
print("=" * 70)

# Step 1: 현재 배정기록 확인
print("\n[Step 1] 현재 배정기록 확인")
print("-" * 70)
db.load_all_data.clear()
db.load_dispatch_sheet.clear()
df_dispatch = db.load_dispatch_sheet()
print(f"배정기록: {len(df_dispatch)}행")
if not df_dispatch.empty:
    print(df_dispatch[['배정ID', '문의ID', '이름', '역할', '일수', '단가']].head())

# Step 2: 새 배정 저장
print("\n[Step 2] 새 배정 저장")
print("-" * 70)
new_assignment = {
    '문의ID': 'TEST-20260202-FINAL',
    '이름': 'Kim Ji Won',
    '역할': 'Assistant Guide',
    '일수': 3,
    '단가': 90000,
    '총지급액': 270000,
    '배정일시': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    '상태': 'active'
}

result = db.save_assignment_record(new_assignment)
print(f"저장 결과: {result}")

# Step 3: 저장 후 배정기록 재로드
print("\n[Step 3] 저장 후 배정기록 재로드 (캐시 초기화)")
print("-" * 70)
db.load_dispatch_sheet.clear()
df_dispatch_new = db.load_dispatch_sheet()
print(f"배정기록: {len(df_dispatch_new)}행")

# Step 4: 새 배정 레코드 확인
print("\n[Step 4] 새 배정 레코드 확인")
print("-" * 70)
test_record = df_dispatch_new[df_dispatch_new['문의ID'].astype(str).str.contains('TEST-20260202-FINAL')]
if not test_record.empty:
    print("✅ 새 배정 레코드 발견!")
    print(test_record[['배정ID', '문의ID', '이름', '역할', '일수', '단가']].to_string())
else:
    print("❌ 새 배정 레코드를 찾을 수 없습니다")

# Step 5: 특정 문의ID의 모든 배정 확인
print("\n[Step 5] 특정 문의ID의 배정 인원 추출")
print("-" * 70)
inquiry_id = 'TEST-20260202-FINAL'
assignments = df_dispatch_new[
    (df_dispatch_new['문의ID'].astype(str).str.strip() == inquiry_id) &
    (~df_dispatch_new['상태'].astype(str).str.strip().isin(['취소', '삭제']))
].copy()

print(f"문의ID '{inquiry_id}' 배정 인원: {len(assignments)}명")
if not assignments.empty:
    print(assignments[['이름', '역할', '일수', '단가', '총지급액']].to_string())
    
    # 출석부용 데이터
    print("\n[출석부 생성용 데이터]")
    attendance_data = []
    for idx, row in assignments.iterrows():
        attendance_data.append({
            'name': row.get('이름', ''),
            'role': row.get('역할', ''),
            'phone': row.get('연락처', ''),
            'days': row.get('일수', 1)
        })
    
    for i, staff in enumerate(attendance_data, 1):
        print(f"  {i}. {staff['name']} ({staff['role']}) - {staff['days']}일")

# Step 6: 급여 합계 계산
print("\n[Step 6] 급여 합계 계산")
print("-" * 70)
total_payroll = assignments['총지급액'].astype(str).str.replace(',', '').astype(float).sum()
print(f"전체 급여 합계: {total_payroll:,.0f}원")

print("\n" + "=" * 70)
print("테스트 완료")
print("=" * 70)
