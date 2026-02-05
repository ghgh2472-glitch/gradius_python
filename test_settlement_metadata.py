#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
계약건은청구금액적기 시트 저장 테스트 (업데이트된 헤더)
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '/c/Users/Win11/Desktop/gradius_python')

import data_loader as db

def test_settlement_with_new_headers():
    """업데이트된 헤더에 맞게 계약 기록 저장"""
    
    settlement_data = {
        "문의ID": "NEW_TEST_001",
        "업체명": "테스트 업체",
        "행사명": "테스트 행사",
        "사업자번호": "123-45-67890",
        "대표자": "테스트 대표",
        "이메일": "test@test.com",
        "계약일": "2026-02-02",
        "공급가액": 600000,
        "부가세": 60000,
        "합계금액": 660000,
        "상태": "계약체결"
    }
    
    site_info = {
        "현장명": "서울시 강남구 테스트",
        "책임자": "김진영",
        "현장주소": "서울시 강남구 테헤란로 123",
        "파견일자": "2026-02-02 ~ 2026-02-03"
    }
    
    print("[TEST] 업데이트된 헤더로 계약 저장 테스트")
    print(f"[DATA] Settlement: {settlement_data}")
    print(f"[SITE] Site Info: {site_info}")
    
    result = db.save_settlement_record(settlement_data, site_info=site_info)
    
    if result:
        print("[SUCCESS] 계약 저장 성공!")
    else:
        print("[FAILED] 계약 저장 실패!")
    
    return result

if __name__ == "__main__":
    test_settlement_with_new_headers()
