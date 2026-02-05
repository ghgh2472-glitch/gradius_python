#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
견적상세 시트의 현재 상태 확인
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
        print("[SHEET] 견적상세")
        print(f"[ROWS] {wks.row_count}")
        headers = wks.row_values(1)
        print(f"[HEADERS] {headers}")
        
        # 처음 5행 출력
        all_vals = wks.get_all_values()[:6]
        for idx, row in enumerate(all_vals, 1):
            print(f"[ROW {idx}] {row}")
    except Exception as e:
        print(f"[ERROR] {e}")
else:
    print("[ERROR] Connection failed")
