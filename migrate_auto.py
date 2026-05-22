"""
migrate_auto.py
Google Sheets → Supabase 완전 자동 마이그레이션

사전 준비 (1회):
  1. Google Sheets 열기
  2. 우상단 [공유] 버튼 → [링크 복사]
     → "링크가 있는 모든 사용자" / "뷰어" 설정
  3. python migrate_auto.py

완료 후 시트를 다시 비공개로 돌려도 됩니다.
현재 Python ERP는 전혀 영향 없음.
"""

import os
import sys
import csv
import io
import requests
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Supabase ──────────────────────────────────────────────
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ .env 파일에 SUPABASE_URL 과 SUPABASE_SERVICE_KEY 를 설정하세요.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
CSV_DIR = Path("migration_csvs")

# 다운로드할 시트 목록: {파일명: 시트탭명}
SHEETS = {
    "고객정보.csv":           "고객정보",
    "Roles.csv":              "Roles",
    "Factors.csv":            "Factors",
    "Guides.csv":             "Guides",
    "STAFF.csv":              "STAFF",
    "문의작성.csv":            "문의작성",
    "견적상세.csv":            "견적상세",
    "견적안.csv":              "견적안",
    "견적품목.csv":            "견적품목",
    "배정기록.csv":            "배정기록",
    "계약건은청구금액적기.csv": "계약건은청구금액적기",
    "지급내역.csv":            "지급내역",
    "출석부.csv":              "출석부",
    "평가표.csv":              "평가표",
}

# ── 1단계: 자동 다운로드 ─────────────────────────────────

def download_all_sheets() -> bool:
    """Google Sheets 공개 CSV 엔드포인트로 전체 시트 다운로드."""
    CSV_DIR.mkdir(exist_ok=True)

    print("  Google Sheets에서 시트 다운로드 중...\n")
    success = 0
    failed = []

    session = requests.Session()

    for filename, sheet_name in SHEETS.items():
        url = (
            f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
            f"/gviz/tq?tqx=out:csv&sheet={requests.utils.quote(sheet_name)}"
        )
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code == 200 and resp.text.strip():
                # 실제 데이터인지 확인 (로그인 페이지 반환 방지)
                first_line = resp.text.strip().splitlines()[0]
                if "<html" in first_line.lower() or "<!doctype" in first_line.lower():
                    print(f"  🔒 {sheet_name}: 비공개 — 건너뜀")
                    failed.append(sheet_name)
                    continue

                out_path = CSV_DIR / filename
                out_path.write_text(resp.text, encoding="utf-8")
                row_count = resp.text.count("\n")
                print(f"  ✅ {sheet_name} → {filename} ({row_count}행)")
                success += 1
            elif resp.status_code == 400:
                print(f"  ⚠️  {sheet_name}: 시트 없음 — 건너뜀")
            else:
                print(f"  ❌ {sheet_name}: HTTP {resp.status_code}")
                failed.append(sheet_name)
        except Exception as e:
            print(f"  ❌ {sheet_name}: {e}")
            failed.append(sheet_name)

    print(f"\n  다운로드 완료: {success}/{len(SHEETS)}개")

    if success == 0:
        print("\n❌ 모든 시트 다운로드 실패.")
        print("   구글시트가 비공개 상태입니다. 아래 설정을 확인하세요:\n")
        print("   1. 구글시트 열기")
        print("   2. 우상단 [공유] 버튼 클릭")
        print("   3. '링크가 있는 모든 사용자' → '뷰어' 선택")
        print("   4. 저장 후 다시 실행: python migrate_auto.py")
        return False

    if failed:
        print(f"  ⚠️  일부 시트 없음 (정상): {failed}")

    return True


# ── 공통 유틸리티 ────────────────────────────────────────

def read_csv(filename: str) -> list[dict]:
    path = CSV_DIR / filename
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean = {k.strip(): (v.strip() if isinstance(v, str) else v)
                     for k, v in row.items() if k and k.strip()}
            rows.append(clean)
    return rows


def si(v, default=0):
    if v is None or str(v).strip() in ("", "nan", "None", "-"):
        return default
    try:
        return int(float(str(v).replace(",", "").replace("원", "").strip()))
    except Exception:
        return default


def ss(v):
    if v is None or str(v).strip() in ("", "nan", "None"):
        return None
    return str(v).strip()


def sb_bool(v, default=True):
    if v is None:
        return default
    return str(v).strip().lower() not in ("false", "0", "x", "아니오", "아니요", "미대상", "제외", "n")


def sd(v):
    if not v or str(v).strip() in ("", "nan", "None", "-"):
        return None
    s = str(v).strip().replace("/", "-")
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except Exception:
        return None


def sdt(v):
    if not v or str(v).strip() in ("", "nan", "None", "-"):
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(s[:len(fmt)+2], fmt).isoformat()
        except Exception:
            continue
    return None


# ── 2단계: 마이그레이션 ──────────────────────────────────

def migrate_customers():
    rows = read_csv("고객정보.csv")
    if not rows:
        print("  ⚠️  고객정보.csv 없음 — 건너뜀")
        return {}
    company_id_map = {}
    ok = 0
    for row in rows:
        name = ss(row.get("업체명") or row.get("회사명") or row.get("고객명"))
        if not name:
            continue
        biz = ss(row.get("사업자번호") or row.get("사업자등록번호"))
        data = {k: v for k, v in {
            "company_name": name,
            "rep_name": ss(row.get("대표자") or row.get("대표자명")),
            "biz_number": biz,
            "biz_type": ss(row.get("업태")),
            "biz_item": ss(row.get("종목")),
            "address": ss(row.get("주소") or row.get("사업장주소")),
            "email": ss(row.get("이메일")),
            "contact_name": ss(row.get("담당자")),
            "phone": ss(row.get("연락처") or row.get("전화번호")),
            "memo": ss(row.get("메모") or row.get("비고")),
            "customer_type": "법인" if biz else "개인",
        }.items() if v is not None}
        try:
            r = sb.table("customers").upsert(data, on_conflict="company_name").execute()
            if r.data:
                company_id_map[name] = r.data[0]["id"]
            ok += 1
        except Exception as e:
            print(f"    ❌ 고객({name}): {e}")
    print(f"  ✅ 고객정보: {ok}건")
    return company_id_map


def migrate_roles():
    rows = read_csv("Roles.csv")
    if not rows:
        print("  ⚠️  Roles.csv 없음 — 건너뜀")
        return {}
    role_id_map = {}
    ok = 0
    for row in rows:
        code = ss(row.get("직군코드") or row.get("role_id") or row.get("코드"))
        name = ss(row.get("직군명") or row.get("역할명") or row.get("role_name"))
        if not code or not name:
            continue
        data = {"role_code": code, "role_name": name,
                "base_price": si(row.get("기본단가") or row.get("단가")),
                "pay_price": si(row.get("지급단가")),
                "leader_bonus": si(row.get("팀장가산"), 10000)}
        try:
            r = sb.table("roles").upsert(data, on_conflict="role_code").execute()
            if r.data:
                rid = r.data[0]["id"]
                role_id_map[code] = rid
                role_id_map[name] = rid
            ok += 1
        except Exception as e:
            print(f"    ❌ 직군({code}): {e}")
    print(f"  ✅ Roles: {ok}건")
    return role_id_map


def migrate_staff():
    rows = read_csv("STAFF.csv")
    if not rows:
        print("  ⚠️  STAFF.csv 없음 — 건너뜀")
        return {}
    staff_id_map = {}
    ok = 0
    RM = {"우선": "우선투입", "우선투입": "우선투입", "일반": "일반", "보류": "보류"}
    for row in rows:
        name = ss(row.get("이름") or row.get("성명"))
        if not name:
            continue
        jobs_raw = ss(row.get("가능직무") or row.get("직무"))
        certs_raw = ss(row.get("자격증") or row.get("보유자격"))
        data = {k: v for k, v in {
            "name": name,
            "gender": ss(row.get("성별")),
            "age": si(row.get("나이") or row.get("연령")) or None,
            "height": si(row.get("키") or row.get("신장")) or None,
            "total_score": si(row.get("총점")),
            "english_skill": ss(row.get("영어") or row.get("영어능력")),
            "driving": ss(row.get("운전면허") or row.get("운전")),
            "region": ss(row.get("거주지") or row.get("지역")),
            "available_jobs": [j.strip() for j in jobs_raw.split(",") if j.strip()] if jobs_raw else [],
            "certifications": [c.strip() for c in certs_raw.split(",") if c.strip()] if certs_raw else [],
            "recommend": RM.get(ss(row.get("추천등급") or row.get("추천")) or "", "일반"),
            "phone": ss(row.get("연락처") or row.get("전화번호")),
            "attendance_score": si(row.get("근태점수")),
            "performance_score": si(row.get("수행점수")),
            "appearance_score": si(row.get("외모점수")),
            "teamwork_score": si(row.get("팀워크점수")),
            "bank_name": ss(row.get("은행명")),
            "account_number": ss(row.get("계좌번호")),
            "id_number": ss(row.get("주민등록번호") or row.get("주민번호")),
            "memo": ss(row.get("총평") or row.get("메모")),
        }.items() if v is not None}
        try:
            existing = sb.table("staff").select("id").eq("name", name).execute()
            if existing.data:
                sid = existing.data[0]["id"]
                sb.table("staff").update(data).eq("id", sid).execute()
            else:
                r = sb.table("staff").insert(data).execute()
                sid = r.data[0]["id"] if r.data else None
            if sid and name not in staff_id_map:
                staff_id_map[name] = sid
            ok += 1
        except Exception as e:
            print(f"    ❌ 직원({name}): {e}")
    print(f"  ✅ STAFF: {ok}건")
    return staff_id_map


def migrate_inquiries():
    rows = read_csv("문의작성.csv")
    if not rows:
        print("  ❌ 문의작성.csv 없음 — 핵심 데이터 누락!")
        return {}
    inq_id_map = {}
    ok = 0
    VALID = {"접수", "견적", "체결", "배정완료", "진행중", "완료", "정산완료", "미체결", "보류", "취소"}
    for row in rows:
        code = ss(row.get("문의ID") or row.get("ID"))
        event = ss(row.get("행사명") or row.get("행사"))
        if not event:
            continue
        status_raw = ss(row.get("상태") or row.get("진행상태")) or "접수"
        data = {k: v for k, v in {
            "inquiry_code": code,
            "company_name": ss(row.get("업체명") or row.get("업체")),
            "contact_name": ss(row.get("담당자")),
            "phone": ss(row.get("연락처") or row.get("전화번호")),
            "event_name": event,
            "location": ss(row.get("장소") or row.get("행사장소")),
            "event_start": sd(row.get("행사시작일") or row.get("시작일")),
            "event_end": sd(row.get("행사종료일") or row.get("종료일")),
            "event_time": ss(row.get("행사시간") or row.get("시간")),
            "service_type": ss(row.get("서비스종류") or row.get("서비스")),
            "required_staff": si(row.get("필요인원") or row.get("인원")) or None,
            "expected_pay": si(row.get("예상페이")) or None,
            "status": status_raw if status_raw in VALID else "접수",
            "notes": ss(row.get("특이사항") or row.get("비고")),
            "memo": ss(row.get("메모")),
            "relationship": ss(row.get("관계") or row.get("신규기존")),
            "category": ss(row.get("구분")),
            "attire": ss(row.get("복장")),
            "meal": ss(row.get("식사")),
            "parking": ss(row.get("주차")),
            "consult_notes": ss(row.get("상담내용")),
        }.items() if v is not None}
        try:
            if code:
                r = sb.table("inquiries").upsert(data, on_conflict="inquiry_code").execute()
            else:
                r = sb.table("inquiries").insert(data).execute()
            if r.data:
                inq_id_map[code] = r.data[0]["id"]
            ok += 1
        except Exception as e:
            print(f"    ❌ 문의({code}): {e}")
    print(f"  ✅ 문의작성: {ok}건")
    return inq_id_map


def migrate_estimates(inq_id_map):
    rows = read_csv("견적상세.csv")
    if not rows:
        print("  ⚠️  견적상세.csv 없음 — 건너뜀")
        return {}
    ok = skip = 0
    est_id_map = {}
    for row in rows:
        code = ss(row.get("견적ID") or row.get("ID"))
        inq_code = ss(row.get("문의ID"))
        inq_uuid = inq_id_map.get(inq_code)
        supply = si(row.get("공급가액"))
        cost = si(row.get("매입원가"))
        extra = si(row.get("부대비용"))
        data = {k: v for k, v in {
            "estimate_code": code,
            "inquiry_id": inq_uuid,
            "company_name": ss(row.get("업체명") or row.get("업체")),
            "event_name": ss(row.get("행사명")),
            "site_name": ss(row.get("현장명")),
            "manager": ss(row.get("책임자")),
            "site_address": ss(row.get("현장주소")),
            "supply_price": supply,
            "vat": si(row.get("부가세")),
            "total_price": si(row.get("합계금액") or row.get("합계")),
            "cost_price": cost,
            "extra_cost": extra,
            "profit_rate": round((supply - cost - extra) / supply * 100, 2) if supply > 0 else None,
            "attire": ss(row.get("복장")),
            "meal": ss(row.get("식사")),
            "parking": ss(row.get("주차")),
            "notes": ss(row.get("특이사항") or row.get("비고")),
            "send_status": ss(row.get("발송여부")) or "미발송",
            "sent_at": sdt(row.get("발송일시")),
            "send_method": ss(row.get("발송방법")),
            "send_memo": ss(row.get("발송메모")),
        }.items() if v is not None}
        try:
            if code:
                r = sb.table("estimates").upsert(data, on_conflict="estimate_code").execute()
            else:
                r = sb.table("estimates").insert(data).execute()
            if r.data:
                est_id_map[code or inq_code or ""] = r.data[0]["id"]
            ok += 1
        except Exception as e:
            print(f"    ❌ 견적({code}): {e}")
    print(f"  ✅ 견적상세: {ok}건 ({skip}건 건너뜀)")
    return est_id_map


def migrate_settlements(inq_id_map):
    rows = read_csv("계약건은청구금액적기.csv")
    if not rows:
        print("  ⚠️  계약건은청구금액적기.csv 없음 — 건너뜀")
        return
    ok = skip = 0
    VPRG = {"계약체결", "행사준비", "행사종료", "정산완료"}
    VDEP = {"입금완료", "부분입금", "미입금"}
    PMAP = {"완료": "행사종료", "배정완료": "계약체결", "진행중": "행사준비", "체결": "계약체결"}
    for row in rows:
        inq_code = ss(row.get("문의ID"))
        inq_uuid = inq_id_map.get(inq_code)
        if not inq_uuid:
            skip += 1
            continue
        prg_raw = ss(row.get("진행상황") or row.get("진행상태")) or "계약체결"
        prg = PMAP.get(prg_raw, prg_raw)
        if prg not in VPRG:
            prg = "계약체결"
        dep_raw = ss(row.get("입금여부") or row.get("입금상태")) or "미입금"
        dep = dep_raw if dep_raw in VDEP else "미입금"
        ti_raw = ss(row.get("세금계산서 발행여부") or row.get("세금계산서"))
        ti = ti_raw in ("O", "o", "발행", "Y", "y", "True", "true", "완료")
        # balance, profit 은 GENERATED ALWAYS AS → 포함 금지
        data = {k: v for k, v in {
            "inquiry_id": inq_uuid,
            "site_name": ss(row.get("현장명")),
            "company_name": ss(row.get("업체") or row.get("업체명")),
            "dispatch_period": ss(row.get("파견일자") or row.get("파견기간")),
            "manager": ss(row.get("책임자")),
            "site_address": ss(row.get("현장주소")),
            "invoice_amount": si(row.get("청구금액")),
            "supply_price": si(row.get("공급가액")),
            "vat": si(row.get("부가세")),
            "received_amount": si(row.get("받은금액")),
            "progress": prg,
            "deposit_status": dep,
            "tax_invoice_issued": ti,
            "payout_amount": si(row.get("지급액")),
            "invoice_calc_amount": si(row.get("계산서금액")),
            "withholding_tax": si(row.get("3.3%") or row.get("원천세")),
            "category": ss(row.get("구분")),
            "biz_number": ss(row.get("사업자번호")),
            "rep_name": ss(row.get("대표자")),
            "email": ss(row.get("이메일")),
            "corp_name": ss(row.get("법인명")),
            "item_description": ss(row.get("내용(품목)") or row.get("내용") or row.get("품목")),
            "contact_phone": ss(row.get("연락처")),
            "invoice_request": ss(row.get("발행요청사항")),
            "biz_reg_url": ss(row.get("사업자등록증URL")),
        }.items() if v is not None}
        try:
            sb.table("settlements").upsert(data, on_conflict="inquiry_id").execute()
            ok += 1
        except Exception as e:
            print(f"    ❌ 정산({inq_code}): {e}")
    print(f"  ✅ 계약건은청구금액적기: {ok}건 ({skip}건 FK 없어 건너뜀)")


def migrate_assignments(inq_id_map, staff_id_map):
    rows = read_csv("배정기록.csv")
    if not rows:
        print("  ⚠️  배정기록.csv 없음 — 건너뜀")
        return {}
    assign_id_map = {}
    ok = skip = 0
    VSTS = {"후보", "배정중", "확정", "취소"}
    for row in rows:
        code = ss(row.get("배정ID") or row.get("ID"))
        inq_code = ss(row.get("문의ID"))
        inq_uuid = inq_id_map.get(inq_code)
        if not inq_uuid:
            skip += 1
            continue
        staff_name = ss(row.get("이름") or row.get("성명"))
        sts_raw = ss(row.get("배정상태") or row.get("지급상태") or row.get("상태")) or "후보"
        stype_raw = ss(row.get("구분") or row.get("소속")) or "본사"
        # total_pay 는 GENERATED ALWAYS AS → 포함 금지
        data = {k: v for k, v in {
            "assignment_code": code,
            "inquiry_id": inq_uuid,
            "event_name": ss(row.get("행사명")),
            "staff_id": staff_id_map.get(staff_name) if staff_name else None,
            "staff_name": staff_name,
            "staff_type": stype_raw if stype_raw in ("본사", "외부") else "본사",
            "job_type": ss(row.get("직무")),
            "phone": ss(row.get("연락처") or row.get("전화번호")),
            "id_number": ss(row.get("주민번호") or row.get("주민등록번호")),
            "bank_name": ss(row.get("은행명")),
            "account_number": ss(row.get("계좌번호")),
            "pay_rate": si(row.get("지급단가") or row.get("단가")),
            "work_days": si(row.get("근무일수") or row.get("일수")),
            "status": sts_raw if sts_raw in VSTS else "후보",
            "assigned_at": sdt(row.get("배정일시")),
            "team_code": ss(row.get("팀코드")),
            "is_payable": sb_bool(row.get("결제대상"), True),
            "is_present": sb_bool(row.get("현장참여"), True),
            "start_date": sd(row.get("근무시작일") or row.get("시작일")),
            "end_date": sd(row.get("근무종료일") or row.get("종료일")),
            "memo": ss(row.get("메모") or row.get("비고")),
        }.items() if v is not None}
        try:
            if code:
                r = sb.table("assignments").upsert(data, on_conflict="assignment_code").execute()
            else:
                r = sb.table("assignments").insert(data).execute()
            if r.data:
                assign_id_map[code or f"{inq_code}_{staff_name}"] = r.data[0]["id"]
            ok += 1
        except Exception as e:
            print(f"    ❌ 배정({code}): {e}")
    print(f"  ✅ 배정기록: {ok}건 ({skip}건 FK 없어 건너뜀)")
    return assign_id_map


def migrate_payouts(inq_id_map, assign_id_map):
    rows = read_csv("지급내역.csv")
    if not rows:
        print("  ⚠️  지급내역.csv 없음 — 건너뜀")
        return
    ok = 0
    VSTS = {"대기", "완료", "확인완료", "미지급"}
    for row in rows:
        code = ss(row.get("지급ID") or row.get("ID"))
        inq_code = ss(row.get("문의ID"))
        sts_raw = ss(row.get("지급상태") or row.get("상태")) or "대기"
        data = {k: v for k, v in {
            "payout_code": code,
            "inquiry_id": inq_id_map.get(inq_code),
            "staff_name": ss(row.get("이름") or row.get("성명")),
            "site_name": ss(row.get("현장명")),
            "dispatch_period": ss(row.get("파견기간") or row.get("파견일자")),
            "dispatch_days": si(row.get("파견일수") or row.get("일수")),
            "base_pay": si(row.get("기본급") or row.get("기본페이")),
            "overtime_pay": si(row.get("야근비") or row.get("초과수당")),
            "meal_pay": si(row.get("식사비") or row.get("식대")),
            "transport_pay": si(row.get("교통비") or row.get("택시비")),
            "bonus": si(row.get("보너스")),
            "subtotal": si(row.get("소계")),
            "tax_deduction": si(row.get("세금공제") or row.get("3.3%") or row.get("원천세")),
            "final_pay": si(row.get("최종지급액") or row.get("실지급액")),
            "status": sts_raw if sts_raw in VSTS else "대기",
            "paid_at": sd(row.get("지급일") or row.get("지급일시")),
            "paid_by": ss(row.get("지급자")),
            "bank_name": ss(row.get("은행명")),
            "account_number": ss(row.get("계좌번호")),
            "id_number": ss(row.get("주민번호") or row.get("주민등록번호")),
            "notes": ss(row.get("메모") or row.get("비고")),
        }.items() if v is not None}
        try:
            if code:
                sb.table("payouts").upsert(data, on_conflict="payout_code").execute()
            else:
                sb.table("payouts").insert(data).execute()
            ok += 1
        except Exception as e:
            print(f"    ❌ 지급({code}): {e}")
    print(f"  ✅ 지급내역: {ok}건")


def migrate_attendances(inq_id_map):
    rows = read_csv("출석부.csv")
    if not rows:
        return
    ok = 0
    VSTS = {"출석", "지각", "결근", "조퇴", "외출"}
    for row in rows:
        code = ss(row.get("기록ID") or row.get("ID"))
        work_date = sd(row.get("근무일자") or row.get("일자"))
        if not work_date:
            continue
        inq_code = ss(row.get("문의ID"))
        sts_raw = ss(row.get("출결상태") or row.get("상태")) or "출석"
        data = {k: v for k, v in {
            "record_code": code,
            "inquiry_id": inq_id_map.get(inq_code),
            "staff_name": ss(row.get("이름") or row.get("성명")),
            "work_date": work_date,
            "clock_in": ss(row.get("출근시간") or row.get("출근")),
            "clock_out": ss(row.get("퇴근시간") or row.get("퇴근")),
            "daily_pay": si(row.get("일급") or row.get("일당")),
            "status": sts_raw if sts_raw in VSTS else "출석",
            "reason": ss(row.get("사유")),
            "notes": ss(row.get("메모") or row.get("비고")),
        }.items() if v is not None}
        try:
            if code:
                sb.table("attendances").upsert(data, on_conflict="record_code").execute()
            else:
                sb.table("attendances").insert(data).execute()
            ok += 1
        except Exception as e:
            print(f"    ❌ 출석: {e}")
    print(f"  ✅ 출석부: {ok}건")


# ── MAIN ─────────────────────────────────────────────────

def main():
    print("=" * 57)
    print("  Gradius ERP — 자동 마이그레이션 (Sheets → Supabase)")
    print("=" * 57)

    # 1단계: 자동 다운로드
    print("\n[1단계] Google Sheets 자동 다운로드")
    print("-" * 40)
    ok = download_all_sheets()
    if not ok:
        sys.exit(1)

    # 2단계: Supabase 이전 (FK 의존 순서 고정)
    print("\n[2단계] Supabase 데이터 이전")
    print("-" * 40)

    print("  고객정보 이전 중...")
    company_id_map = migrate_customers()

    print("  직군(Roles) 이전 중...")
    role_id_map = migrate_roles()

    print("  직원(STAFF) 이전 중...")
    staff_id_map = migrate_staff()

    print("  문의작성 이전 중...")
    inq_id_map = migrate_inquiries()

    print("  견적상세 이전 중...")
    est_id_map = migrate_estimates(inq_id_map)

    print("  정산(계약건은청구금액적기) 이전 중...")
    migrate_settlements(inq_id_map)

    print("  배정기록 이전 중...")
    assign_id_map = migrate_assignments(inq_id_map, staff_id_map)

    print("  지급내역 이전 중...")
    migrate_payouts(inq_id_map, assign_id_map)

    print("  출석부 이전 중...")
    migrate_attendances(inq_id_map)

    print("\n" + "=" * 57)
    print("  ✅ 완료!")
    print(f"     문의 {len(inq_id_map)}건 | 직원 {len(staff_id_map)}건 이전됨")
    print("=" * 57)
    print("\n  확인: https://supabase.com/dashboard/project/mpdpwmouxzhmostimafd/editor")


if __name__ == "__main__":
    main()
