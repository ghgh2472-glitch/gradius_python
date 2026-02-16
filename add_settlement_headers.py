#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
계약건은청구금액적기 시트에 사업자번호, 대표자, 이메일, 법인명 헤더 추가
(이미 존재하는 경우 스킵)
"""
import data_loader as db

client = db.get_connection()
if not client:
    print("[ERROR] 연결 실패")
    exit(1)

sh = client.open_by_key(db.SHEET_ID)

try:
    wks = sh.worksheet("계약건은청구금액적기")
    headers = wks.row_values(1)
    headers_clean = [str(h).strip() for h in headers]
    
    print(f"[현재 헤더] ({len(headers_clean)}개):")
    for i, h in enumerate(headers_clean, 1):
        print(f"  {i}. '{h}'")
    
    # 추가할 헤더 목록
    new_headers = ["사업자번호", "대표자", "이메일", "법인명"]
    added = []
    
    for nh in new_headers:
        if nh not in headers_clean:
            headers_clean.append(nh)
            added.append(nh)
            print(f"  [+] '{nh}' 추가")
        else:
            print(f"  [=] '{nh}' 이미 존재 (위치: {headers_clean.index(nh)+1})")
    
    if added:
        wks.update('A1', [headers_clean], value_input_option='RAW')
        print(f"\n[SUCCESS] 헤더 {len(added)}개 추가 완료: {added}")
    else:
        print("\n[INFO] 추가할 헤더가 없습니다 - 모두 이미 존재합니다.")
    
    # 최종 헤더 확인
    final_headers = wks.row_values(1)
    print(f"\n[최종 헤더] ({len(final_headers)}개):")
    for i, h in enumerate(final_headers, 1):
        print(f"  {i}. '{h}'")

except Exception as e:
    print(f"[ERROR] {e}")
