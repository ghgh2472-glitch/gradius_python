#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
모든 시트의 헤더 확인
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '/c/Users/Win11/Desktop/gradius_python')

import data_loader as db

# 시트 확인
client = db.get_connection()
if client:
    sh = client.open_by_key(db.SHEET_ID)
    
    # 모든 워크시트 목록 가져오기
    worksheets = sh.worksheets()
    
    print("=" * 80)
    print("현재 모든 시트의 헤더 정보")
    print("=" * 80)
    
    for ws in worksheets:
        try:
            headers = ws.row_values(1)
            if headers:
                print(f"\n[{ws.title}]")
                print(f"헤더 수: {len(headers)}")
                for idx, header in enumerate(headers, 1):
                    print(f"  {idx}. {header}")
        except Exception as e:
            print(f"\n[{ws.title}] - 오류: {e}")
    
    print("\n" + "=" * 80)
else:
    print("연결 실패")
