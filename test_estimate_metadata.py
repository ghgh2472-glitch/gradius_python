#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
견적상세 메타데이터 저장 테스트
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '/c/Users/Win11/Desktop/gradius_python')

import data_loader as db
from datetime import datetime

def test_estimate_with_metadata():
    """메타데이터와 함께 견적 저장 테스트"""
    
    est_data = {
        "문의ID": "META_TEST_001",
        "업체명": "테스트 업체",
        "행사명": "테스트 행사",
        "공급가액": 500000,
        "부가세": 50000,
        "합계금액": 550000,
        "매입원가": 300000,
        "부대비용": 20000
    }
    
    metadata = {
        "현장명": "서울시 강남구 테스트",
        "책임자": "홍길동",
        "현장주소": "서울시 강남구 테헤란로 123"
    }
    
    print("[TEST] 견적 메타데이터 저장 테스트 시작...")
    print(f"[DATA] 견적 데이터: {est_data}")
    print(f"[META] 메타데이터: {metadata}")
    
    result = db.save_estimate_details(est_data, metadata=metadata)
    
    if result:
        print("[SUCCESS] 견적 메타데이터 저장 성공!")
    else:
        print("[FAILED] 견적 메타데이터 저장 실패!")
    
    return result

if __name__ == "__main__":
    test_estimate_with_metadata()
