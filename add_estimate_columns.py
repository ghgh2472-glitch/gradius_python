#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
견적상세 시트에 새로운 컬럼 추가 (메타데이터용)
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
    try:
        wks = sh.worksheet("견적상세")
        
        # 현재 헤더 읽기
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        
        print(f"[INFO] 현재 헤더 수: {len(headers_clean)}")
        print(f"[INFO] 현재 헤더: {headers_clean}")
        
        # 필요한 새 헤더 추가
        new_headers_to_add = []
        for new_header in ["현장명", "책임자", "현장주소"]:
            if new_header not in headers_clean:
                new_headers_to_add.append(new_header)
        
        if new_headers_to_add:
            print(f"[INFO] 추가할 헤더: {new_headers_to_add}")
            
            # 새 헤더를 마지막 위치에 추가
            new_headers = headers + new_headers_to_add
            wks.update('A1', [new_headers], value_input_option='RAW')
            
            print("[SUCCESS] 헤더 추가 완료!")
            print(f"[INFO] 새 헤더: {new_headers}")
        else:
            print("[INFO] 추가할 헤더가 없습니다")
            
    except Exception as e:
        print(f"[ERROR] {e}")
else:
    print("[ERROR] Connection failed")
