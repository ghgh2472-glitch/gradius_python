#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
계약건은 청구금액적기 시트 저장 테스트
"""
import sys
sys.path.insert(0, '/c/Users/Win11/Desktop/gradius_python')

import data_loader as db
from datetime import datetime

def test_settlement_save():
    """Settlement record save 테스트"""
    
    # 테스트 데이터
    settlement_data = {
        "문의ID": "TEST_001",
        "업체명": "테스트 업체",
        "행사명": "테스트 행사",
        "사업자번호": "123-45-67890",
        "대표자": "테스트 대표",
        "이메일": "test@example.com",
        "계약일": datetime.now().strftime("%Y-%m-%d"),
        "공급가액": 1000000,
        "부가세": 100000,
        "합계금액": 1100000,
        "상태": "계약체결"
    }
    
    print("🧪 Settlement 저장 테스트 시작...")
    print(f"📋 테스트 데이터: {settlement_data}")
    
    result = db.save_settlement_record(settlement_data)
    
    if result:
        print("✅ Settlement 저장 성공!")
    else:
        print("❌ Settlement 저장 실패!")
    
    return result

if __name__ == "__main__":
    test_settlement_save()
