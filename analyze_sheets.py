# -*- coding: utf-8 -*-
import data_loader as db

print("\n" + "=" * 100)
print("[분석] 시트 컬럼 구조 확인")
print("=" * 100)

# 각 시트의 헤더 확인
sheets_to_check = {
    "문의작성": ["업체명", "행사명", "장소", "문의ID"],
    "견적상세": ["문의ID", "현장주소"],
    "계약건은청구금액적기": ["문의ID", "계약일자", "업체명", "현장명", "현장주소", "책임자"],
}

for sheet_name, expected_cols in sheets_to_check.items():
    print(f"\n[{sheet_name}]")
    print("-" * 100)
    
    try:
        client = db.get_connection()
        if not client:
            print("❌ 연결 실패")
            continue
        
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet(sheet_name)
        
        headers = wks.row_values(1)
        print(f"전체 컬럼 ({len(headers)}개):")
        for i, col in enumerate(headers, 1):
            status = "✅" if col in expected_cols else "  "
            print(f"  {status} {i:2}. {col}")
        
        # 첫 데이터 확인
        all_records = wks.get_all_records()
        if all_records:
            print(f"\n첫 번째 레코드:")
            for key, val in list(all_records[0].items())[:5]:
                print(f"  - {key}: {val}")
    
    except Exception as e:
        print(f"❌ 오류: {e}")

print("\n" + "=" * 100)
