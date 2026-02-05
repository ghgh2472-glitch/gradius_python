# -*- coding: utf-8 -*-
import pandas as pd
import data_loader as db

print("\n" + "=" * 100)
print("[DEBUG] STAFF 검색 필터링 문제 진단")
print("=" * 100)

# load_all_data() 함수를 사용
data = db.load_all_data()

df_staff = data.get('staff', pd.DataFrame())

if df_staff is None or df_staff.empty:
    print("[ERROR] STAFF 데이터가 로드되지 않음!")
    exit(1)

print(f"\n[OK] STAFF 로드 성공: {len(df_staff)}명, {len(df_staff.columns)}개 컬럼")

# 컬럼명 출력
print("\n[컬럼명 목록]")
for i, col in enumerate(df_staff.columns, 1):
    print(f"  {i:2}. {col}")

# 샘플 데이터 확인
print("\n[샘플 데이터 - 처음 3명]")
sample_cols = ['이름', '성별', '나이', '이동가능지역', '가능직무', '총점', '추천도']
for col in sample_cols:
    if col in df_staff.columns:
        vals = df_staff[col].head(3).tolist()
        print(f"  {col}: {vals}")

# 필터 테스트
print("\n[필터 테스트]")

# 1. 나이 필터만
print("\n  1) 나이 30~45세 필터:")
test_df = df_staff[df_staff['나이'] >= 30]
test_df = test_df[test_df['나이'] <= 45]
print(f"     결과: {len(test_df)}명")

# 2. 지역 필터
print("\n  2) 지역에 '서울' 포함:")
test_df = df_staff[df_staff['이동가능지역'].astype(str).str.contains('서울', na=False)]
print(f"     결과: {len(test_df)}명")

# 3. 직무 필터
print("\n  3) 직무에 '진행자' 포함:")
test_df = df_staff[df_staff['가능직무'].astype(str).str.contains('진행자', na=False)]
print(f"     결과: {len(test_df)}명")

# 4. 성별 필터
print("\n  4) 성별 = M:")
test_df = df_staff[df_staff['성별'] == 'M']
print(f"     결과: {len(test_df)}명")

# 5. 종합 필터
print("\n  5) 종합 필터 (25~50세 + 여성 + 서울):")
test_df = df_staff[df_staff['성별'] == 'F']
test_df = test_df[test_df['나이'] >= 25]
test_df = test_df[test_df['나이'] <= 50]
test_df = test_df[test_df['이동가능지역'].astype(str).str.contains('서울', na=False)]
print(f"     결과: {len(test_df)}명")
if len(test_df) > 0:
    for _, row in test_df.head(3).iterrows():
        print(f"       - {row['이름']} ({row['성별']}, {row['나이']}세, {row['이동가능지역']})")

print("\n" + "=" * 100)
