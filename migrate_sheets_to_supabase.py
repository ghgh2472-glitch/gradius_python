"""
migrate_sheets_to_supabase.py
Google Sheets 데이터를 Supabase PostgreSQL로 마이그레이션

실행 전 준비:
  1. .env 에 SUPABASE_URL, SUPABASE_SERVICE_KEY 입력
  2. supabase_schema.sql 을 Supabase SQL Editor 에서 실행
  3. pip install supabase
  4. python migrate_sheets_to_supabase.py

현재 Python ERP는 전혀 건드리지 않습니다 — Sheets는 계속 정상 운영됩니다.
"""

import os
import sys
import json
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Supabase 클라이언트 ──────────────────────────────────────
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ .env 파일에 SUPABASE_URL 과 SUPABASE_SERVICE_KEY 를 설정하세요.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Google Sheets 데이터 로더 (기존 코드 재사용) ──────────────
# Streamlit 없이 data_loader를 사용하기 위한 환경 세팅
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

try:
    import streamlit as st
    # session_state mock (Streamlit 없이 실행 시 필요)
    if not hasattr(st, 'session_state'):
        st.session_state = {}
except Exception:
    pass

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_sheet_client():
    """Google Sheets 클라이언트 (secrets.json 사용)"""
    creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", SCOPES)
    return gspread.authorize(creds)

def load_sheet(client, sheet_name: str) -> list[dict]:
    """시트를 dict 리스트로 로드"""
    try:
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet(sheet_name)
        records = ws.get_all_records(empty2zero=False, head=1)
        print(f"  📋 {sheet_name}: {len(records)}행 로드")
        return records
    except Exception as e:
        print(f"  ⚠️  {sheet_name} 로드 실패: {e}")
        return []

def safe_int(v, default=0) -> int:
    if v is None or v == '' or v == 'nan':
        return default
    try:
        return int(str(v).replace(',', '').replace('원', '').strip())
    except:
        return default

def safe_str(v) -> str | None:
    if v is None or str(v).strip() in ('', 'nan', 'None'):
        return None
    return str(v).strip()

def safe_date(v) -> str | None:
    """YYYY-MM-DD 형식으로 변환"""
    if not v or str(v).strip() in ('', 'nan'):
        return None
    s = str(v).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except:
            continue
    return None

def upsert(table: str, data: list[dict], conflict_col: str = None):
    """Supabase upsert (중복 시 업데이트)"""
    if not data:
        return
    try:
        if conflict_col:
            sb.table(table).upsert(data, on_conflict=conflict_col).execute()
        else:
            sb.table(table).upsert(data).execute()
        print(f"  ✅ {table}: {len(data)}건 저장")
    except Exception as e:
        print(f"  ❌ {table} 저장 실패: {e}")
        traceback.print_exc()

# ──────────────────────────────────────────────────────────────
# 마이그레이션 함수들
# ──────────────────────────────────────────────────────────────

def migrate_customers(client):
    print("\n[1/9] 고객정보 마이그레이션...")
    rows = load_sheet(client, "고객정보")
    data = []
    for r in rows:
        name = safe_str(r.get('업체명'))
        if not name:
            continue
        biz_num = safe_str(r.get('사업자번호'))
        data.append({
            "company_name": name,
            "rep_name":     safe_str(r.get('대표자명')),
            "biz_number":   biz_num,
            "biz_type":     safe_str(r.get('업태')),
            "biz_item":     safe_str(r.get('종목')),
            "address":      safe_str(r.get('주소')),
            "email":        safe_str(r.get('이메일')),
            "contact_name": safe_str(r.get('담당자')),
            "phone":        safe_str(r.get('연락처')),
            "memo":         safe_str(r.get('메모')),
            "customer_type": "법인" if biz_num else "개인",  # 자동 분류
        })
    # 중복 company_name 제거 (마지막 행 기준)
    deduped = {d['company_name']: d for d in data}
    upsert("customers", list(deduped.values()), conflict_col="company_name")

def migrate_roles(client):
    print("\n[2/9] 직군 마이그레이션...")
    rows = load_sheet(client, "Roles")
    data = []
    for r in rows:
        code = safe_str(r.get('role_id') or r.get('직군명'))
        if not code:
            continue
        data.append({
            "role_code":    code,
            "role_name":    safe_str(r.get('직군명')) or code,
            "base_price":   safe_int(r.get('기본단가')),
            "pay_price":    safe_int(r.get('지급단가')),
            "leader_bonus": safe_int(r.get('팀장가산', 10000)),
        })
    upsert("roles", data, conflict_col="role_code")

def migrate_staff(client):
    print("\n[3/9] 직원 마이그레이션...")
    rows = load_sheet(client, "STAFF")
    data = []
    for r in rows:
        name = safe_str(r.get('이름'))
        if not name:
            continue
        jobs_raw = safe_str(r.get('가능직무'))
        jobs = [j.strip() for j in jobs_raw.split(',')] if jobs_raw else []
        certs_raw = safe_str(r.get('자격증'))
        certs = [c.strip() for c in certs_raw.split(',')] if certs_raw else []
        recommend_val = safe_str(r.get('추천도')) or '일반'
        if recommend_val not in ('우선투입', '일반', '보류'):
            recommend_val = '일반'
        data.append({
            "name":               name,
            "gender":             safe_str(r.get('성별')),
            "age":                safe_int(r.get('나이')) or None,
            "height":             safe_int(r.get('키')) or None,
            "total_score":        safe_int(r.get('총점')),
            "english_skill":      safe_str(r.get('영어')),
            "driving":            safe_str(r.get('운전')),
            "region":             safe_str(r.get('거주지')),
            "available_jobs":     jobs,
            "certifications":     certs,
            "recommend":          recommend_val,
            "phone":              safe_str(r.get('연락처')),
            "attendance_score":   safe_int(r.get('근태점수')),
            "performance_score":  safe_int(r.get('수행점수')),
            "bank_name":          safe_str(r.get('은행명')),
            "account_number":     safe_str(r.get('계좌번호')),
            "memo":               safe_str(r.get('총평')),
        })
    upsert("staff", data)

def migrate_inquiries(client):
    print("\n[4/9] 문의 마이그레이션...")
    rows = load_sheet(client, "문의작성")
    valid_statuses = {'접수','견적','체결','배정완료','진행중','완료','정산완료','미체결','보류','취소'}
    data = []
    for r in rows:
        inq_id = safe_str(r.get('문의ID'))
        if not inq_id:
            continue
        status = safe_str(r.get('상태')) or '접수'
        if status not in valid_statuses:
            status = '접수'
        data.append({
            "inquiry_code":    inq_id,
            "company_name":    safe_str(r.get('업체명')),
            "contact_name":    safe_str(r.get('담당자')),
            "phone":           (safe_str(r.get('연락처')) or '')[:20] or None,
            "event_name":      safe_str(r.get('행사명')) or '미입력',
            "location":        safe_str(r.get('장소')),
            "event_start":     safe_date(r.get('행사시작일')),
            "event_end":       safe_date(r.get('행사종료일')),
            "event_time":      safe_str(r.get('행사시간')),
            "service_type":    safe_str(r.get('서비스종류')),
            "required_staff":  safe_int(r.get('필요인력')) or None,
            "expected_pay":    safe_int(r.get('페이')) or None,
            "status":          status,
            "notes":           safe_str(r.get('특이사항')),
            "memo":            safe_str(r.get('비고')),
            "satisfaction":    safe_int(r.get('만족도')) or None,
            "relationship":    safe_str(r.get('관계')),
            "category":        safe_str(r.get('구분')),
            "attire":          safe_str(r.get('복장')),
            "meal":            safe_str(r.get('식사')),
            "parking":         safe_str(r.get('주차')),
            "consult_notes":   safe_str(r.get('상담내용및 고객성향')),
        })
    upsert("inquiries", data, conflict_col="inquiry_code")

def migrate_estimates(client):
    print("\n[5/9] 견적 마이그레이션...")
    rows = load_sheet(client, "견적상세")
    data = []
    for r in rows:
        est_id = safe_str(r.get('견적ID'))
        if not est_id:
            continue
        # inquiry_id는 inquiry_code로 조회 필요 (후처리)
        inq_code = safe_str(r.get('문의ID'))
        data.append({
            "estimate_code":  est_id,
            "company_name":   safe_str(r.get('업체명')),
            "event_name":     safe_str(r.get('행사명')),
            "site_name":      safe_str(r.get('현장명')),
            "manager":        safe_str(r.get('책임자')),
            "site_address":   safe_str(r.get('현장주소')),
            "supply_price":   safe_int(r.get('공급가액')),
            "vat":            safe_int(r.get('부가세')),
            "total_price":    safe_int(r.get('합계금액')),
            "cost_price":     safe_int(r.get('매입원가')),
            "extra_cost":     safe_int(r.get('부대비용')),
            "attire":         safe_str(r.get('복장')),
            "meal":           safe_str(r.get('식사')),
            "parking":        safe_str(r.get('주차')),
            "notes":          safe_str(r.get('특이사항')),
            "send_status":    safe_str(r.get('발송여부')) or '미발송',
            "send_method":    safe_str(r.get('발송방법')),
            "send_memo":      safe_str(r.get('발송메모')),
            # inquiry_id 는 아래 후처리에서 연결
            "_inq_code":      inq_code,  # 임시 필드 (저장 전 제거)
        })

    # inquiry_code → inquiry.id 매핑
    inq_map = _get_inquiry_id_map()
    for d in data:
        inq_code = d.pop("_inq_code", None)
        if inq_code and inq_code in inq_map:
            d["inquiry_id"] = inq_map[inq_code]

    upsert("estimates", data, conflict_col="estimate_code")

def migrate_settlements(client):
    print("\n[6/9] 청구/정산 마이그레이션...")
    rows = load_sheet(client, "계약건은청구금액적기")
    valid_progress = {'계약체결', '행사준비', '행사종료', '정산완료'}
    valid_deposit  = {'입금완료', '부분입금', '미입금'}
    inq_map = _get_inquiry_id_map()
    data = []
    for r in rows:
        inq_code = safe_str(r.get('문의ID'))
        if not inq_code or inq_code not in inq_map:
            continue
        progress = safe_str(r.get('진행상황')) or '계약체결'
        if progress not in valid_progress:
            progress = '계약체결'
        dep_status = safe_str(r.get('입금여부')) or '미입금'
        if dep_status not in valid_deposit:
            dep_status = '미입금'
        tax_inv = safe_str(r.get('세금계산서발행여부'))
        data.append({
            "inquiry_id":          inq_map[inq_code],
            "site_name":           safe_str(r.get('현장명')),
            "company_name":        safe_str(r.get('업체')),
            "dispatch_period":     safe_str(r.get('파견일자')),
            "manager":             safe_str(r.get('책임자')),
            "site_address":        safe_str(r.get('현장주소')),
            "invoice_amount":      safe_int(r.get('청구금액')),
            "supply_price":        safe_int(r.get('공급가액')),
            "vat":                 safe_int(r.get('부가세')),
            "received_amount":     safe_int(r.get('받은금액')),
            "progress":            progress,
            "deposit_status":      dep_status,
            "tax_invoice_issued":  tax_inv == '발행완료',
            "payout_amount":       safe_int(r.get('지급액')),
            "invoice_calc_amount": safe_int(r.get('계산서금액')),
            "withholding_tax":     safe_int(r.get('3.3%')),
            "category":            safe_str(r.get('구분')),
            "biz_number":          safe_str(r.get('사업자번호')),
            "rep_name":            safe_str(r.get('대표자')),
            "email":               safe_str(r.get('이메일')),
            "corp_name":           safe_str(r.get('법인명')),
            "item_description":    safe_str(r.get('내용(품목)')),
            "contact_phone":       safe_str(r.get('연락처')),
            "invoice_request":     safe_str(r.get('발행요청사항')),
            "biz_reg_url":         safe_str(r.get('사업자등록증URL')),
        })
    upsert("settlements", data, conflict_col="inquiry_id")

def migrate_assignments(client):
    print("\n[7/9] 배정기록 마이그레이션...")
    rows = load_sheet(client, "배정기록")
    valid_status = {'후보', '배정중', '확정', '취소'}
    inq_map = _get_inquiry_id_map()
    data = []
    for r in rows:
        assign_code = safe_str(r.get('배정ID'))
        inq_code    = safe_str(r.get('문의ID'))
        if not assign_code:
            continue
        status = safe_str(r.get('지급상태')) or '후보'
        if status not in valid_status:
            status = '후보'
        # 근무일자: "2026-02-18,2026-02-20" → DATE 배열
        dates_raw = safe_str(r.get('근무일자'))
        work_dates = []
        if dates_raw:
            for d in dates_raw.split(','):
                dt = safe_date(d.strip())
                if dt:
                    work_dates.append(dt)
        row = {
            "assignment_code": assign_code,
            "event_name":      safe_str(r.get('행사명')),
            "staff_name":      safe_str(r.get('인력명')),
            "staff_type":      safe_str(r.get('구분')) or '본사',
            "job_type":        safe_str(r.get('직무')),
            "phone":           safe_str(r.get('연락처')),
            "bank_name":       safe_str(r.get('은행명')),
            "account_number":  safe_str(r.get('계좌번호')),
            "pay_rate":        safe_int(r.get('지급단가')),
            "work_days":       safe_int(r.get('근무일수')),
            "status":          status,
            "work_dates":      work_dates if work_dates else None,
            "team_code":       safe_str(r.get('팀코드')),
            "is_payable":      str(r.get('결제대상', 'Y')).upper() == 'Y',
            "is_present":      str(r.get('현장참여', 'Y')).upper() == 'Y',
            "start_date":      safe_date(r.get('투입시작일')),
            "end_date":        safe_date(r.get('투입종료일')),
            "memo":            safe_str(r.get('메모')),
        }
        if inq_code and inq_code in inq_map:
            row["inquiry_id"] = inq_map[inq_code]
        data.append(row)
    upsert("assignments", data, conflict_col="assignment_code")

def migrate_payouts(client):
    print("\n[8/9] 지급내역 마이그레이션...")
    rows = load_sheet(client, "지급내역")
    valid_status = {'대기', '완료', '확인완료', '미지급'}
    inq_map = _get_inquiry_id_map()
    data = []
    for r in rows:
        payout_code = safe_str(r.get('지급ID'))
        if not payout_code:
            continue
        inq_code = safe_str(r.get('문의ID'))
        status = safe_str(r.get('지급상태')) or '대기'
        if status not in valid_status:
            status = '대기'

        # 택시비(교통비)는 3.3% 공제 제외 — 별도 컬럼으로 저장
        transport = safe_int(r.get('교통비'))
        meal      = safe_int(r.get('식사비'))
        base      = safe_int(r.get('기본급'))
        overtime  = safe_int(r.get('야근비'))
        bonus     = safe_int(r.get('보너스'))
        subtotal  = base + overtime + meal + bonus  # transport 제외
        tax       = safe_int(r.get('세금공제')) or int(subtotal * 0.033)
        final_pay = subtotal - tax + transport       # 교통비는 공제 없이 합산

        row = {
            "payout_code":     payout_code,
            "staff_name":      safe_str(r.get('인력명')),
            "site_name":       safe_str(r.get('현장명')),
            "dispatch_period": safe_str(r.get('파견기간')),
            "dispatch_days":   safe_int(r.get('파견일수')),
            "base_pay":        base,
            "overtime_pay":    overtime,
            "meal_pay":        meal,
            "transport_pay":   transport,  # 3.3% 공제 제외 컬럼
            "bonus":           bonus,
            "subtotal":        subtotal,
            "tax_deduction":   tax,
            "final_pay":       final_pay,
            "status":          status,
            "paid_at":         safe_date(r.get('지급일')),
            "paid_by":         safe_str(r.get('지급담당자')),
            "bank_name":       safe_str(r.get('은행명')),
            "account_number":  safe_str(r.get('계좌번호')),
            "notes":           safe_str(r.get('비고')),
        }
        if inq_code and inq_code in inq_map:
            row["inquiry_id"] = inq_map[inq_code]
        data.append(row)
    upsert("payouts", data, conflict_col="payout_code")

def migrate_attendances(client):
    print("\n[9/9] 출석부 마이그레이션...")
    rows = load_sheet(client, "출석부")
    valid_status = {'출석', '지각', '결근', '조퇴', '외출'}
    inq_map = _get_inquiry_id_map()
    data = []
    for r in rows:
        rec_code = safe_str(r.get('기록ID'))
        if not rec_code:
            continue
        inq_code = safe_str(r.get('문의ID'))
        status = safe_str(r.get('출석상태')) or '출석'
        if status not in valid_status:
            status = '출석'
        row = {
            "record_code":  rec_code,
            "staff_name":   safe_str(r.get('인력명')),
            "work_date":    safe_date(r.get('출석날짜')),
            "clock_in":     safe_str(r.get('출근시간')),
            "clock_out":    safe_str(r.get('퇴근시간')),
            "daily_pay":    safe_int(r.get('일급여')),
            "status":       status,
            "reason":       safe_str(r.get('사유')),
            "notes":        safe_str(r.get('비고')),
        }
        if inq_code and inq_code in inq_map:
            row["inquiry_id"] = inq_map[inq_code]
        data.append(row)
    upsert("attendances", data, conflict_col="record_code")

# ── 헬퍼: inquiry_code → UUID 매핑 캐시 ────────────────────
_inq_id_cache = None

def _get_inquiry_id_map() -> dict:
    global _inq_id_cache
    if _inq_id_cache is None:
        resp = sb.table("inquiries").select("id,inquiry_code").execute()
        _inq_id_cache = {r["inquiry_code"]: r["id"] for r in resp.data if r.get("inquiry_code")}
    return _inq_id_cache

# ──────────────────────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Gradius ERP — Google Sheets → Supabase 마이그레이션")
    print("=" * 55)
    print("⚠️  현재 운영 중인 Python ERP는 영향 없음\n")

    try:
        gc = get_sheet_client()
        print("✅ Google Sheets 연결 성공\n")
    except Exception as e:
        print(f"❌ Google Sheets 연결 실패: {e}")
        sys.exit(1)

    # 의존성 순서대로 실행 (FK 오류 방지)
    migrate_customers(gc)
    migrate_roles(gc)
    migrate_staff(gc)
    migrate_inquiries(gc)
    migrate_estimates(gc)
    migrate_settlements(gc)
    migrate_assignments(gc)
    migrate_payouts(gc)
    migrate_attendances(gc)

    print("\n" + "=" * 55)
    print("  마이그레이션 완료!")
    print("  python test_supabase_conn.py 로 결과를 확인하세요.")
    print("=" * 55)
