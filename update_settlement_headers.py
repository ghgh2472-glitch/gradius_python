#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
계약건은청구금액적기 시트의 헤더 수정
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '/c/Users/Win11/Desktop/gradius_python')

import data_loader as db

# 시트 수정
client = db.get_connection()
if client:
    sh = client.open_by_key(db.SHEET_ID)
    try:
        wks = sh.worksheet("계약건은청구금액적기")
        
        # 현재 헤더 읽기
        current_headers = wks.row_values(1)
        print("[BEFORE] 현재 헤더:")
        for idx, header in enumerate(current_headers[:10], 1):
            print(f"  {idx}. {header}")
        
        # 새 헤더 생성
        # 변경: 문의ID, 현장명, 업체(신규), 파견일자(신규), 책임자, 현장주소, 계약일자, 청구금액, ...
        new_headers = [
            '문의ID',
            '현장명',
            '업체',           # 신규 추가
            '파견일자',       # 신규 추가
            '책임자',
            '현장주소',
            '계약일자'
        ]
        
        # 기존 헤더의 8번째 이후 항목들 추가
        if len(current_headers) > 7:
            new_headers.extend(current_headers[7:])
        
        print("\n[AFTER] 새 헤더:")
        for idx, header in enumerate(new_headers[:10], 1):
            print(f"  {idx}. {header}")
        
        # 헤더 업데이트
        wks.update('A1', [new_headers], value_input_option='RAW')
        
        print("\n[SUCCESS] 헤더 수정 완료!")
        
    except Exception as e:
        print(f"[ERROR] {e}")
else:
    print("[ERROR] 연결 실패")
