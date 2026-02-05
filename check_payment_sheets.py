"""
인건비 시트와 지급내역 시트 비교 및 구조 확인
"""
import data_loader as db

# 시트 확인
print("=" * 80)
print("📊 지급 관련 시트 확인")
print("=" * 80)

# 1. 인건비 시트 확인
print("\n[1] 인건비 시트:")
print("-" * 80)
try:
    df_salary = db.load_sheet('인건비')
    if df_salary is None or df_salary.empty:
        print("   ❌ 시트 비어있음 (헤더 없음)")
    else:
        print(f"   ✅ 행 수: {len(df_salary)}")
        print(f"   ✅ 컬럼 수: {len(df_salary.columns)}")
        print(f"   ✅ 컬럼명:")
        for i, col in enumerate(df_salary.columns, 1):
            print(f"      {i}. {col}")
except Exception as e:
    print(f"   ❌ 에러: {e}")

# 2. 지급내역 시트 확인
print("\n[2] 지급내역 시트:")
print("-" * 80)
try:
    df_payment = db.load_sheet('지급내역')
    if df_payment is None or df_payment.empty:
        print("   ❌ 시트 비어있음")
    else:
        print(f"   ✅ 행 수: {len(df_payment)}")
        print(f"   ✅ 컬럼 수: {len(df_payment.columns)}")
        print(f"   ✅ 컬럼명:")
        for i, col in enumerate(df_payment.columns, 1):
            print(f"      {i}. {col}")
except Exception as e:
    print(f"   ❌ 에러: {e}")

# 3. 스프레드시트 전체 시트 목록
print("\n[3] 스프레드시트 전체 시트 목록:")
print("-" * 80)
try:
    all_sheets = db.get_sheet_names()
    if all_sheets:
        for i, sheet in enumerate(all_sheets, 1):
            print(f"   {i:2}. {sheet}")
        print(f"\n   총 {len(all_sheets)}개 시트")
except Exception as e:
    print(f"   ❌ 에러: {e}")

# 4. 추천
print("\n[4] 📋 추천 방안:")
print("-" * 80)
print("   인건비 시트의 상태: 비어있음")
print("   지급내역 시트의 상태: 생성됨")
print()
print("   ✅ 권장사항:")
print("   - 현재 지급내역 시트를 계속 사용")
print("   - 또는 지급내역 시트의 컬럼을 인건비 시트로 복사")
print("   - 인건비 시트: 인력별 급여 정보 (StaffID, 이름, 기본시급, 추가급)")
print("   - 지급내역 시트: 배정별 지급 기록 (배정ID, 인력명, 일수, 총급여, 지급일자)")
print()
