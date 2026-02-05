#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gspread
from oauth2client.service_account import ServiceAccountCredentials

scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scopes)
client = gspread.authorize(creds)

SHEET_ID = '13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI'
sh = client.open_by_key(SHEET_ID)

# 계약 관련 시트 찾기
for ws in sh.worksheets():
    title = ws.title
    if '계약' in title:
        print(f"\n=== {title} ===")
        print(f"Total rows: {ws.row_count}, Total cols: {ws.col_count}")
        
        headers = ws.row_values(1)
        print(f"\nHeaders ({len(headers)} cols):")
        for i, h in enumerate(headers, 1):
            print(f"  Col {i}: {h}")
        
        # 첫 데이터 행
        if ws.row_count > 1:
            first_data = ws.row_values(2)
            print(f"\nSample Data Row 2 (first {min(5, len(first_data))} values):")
            for i, v in enumerate(first_data[:5], 1):
                print(f"  Col {i}: {v}")
