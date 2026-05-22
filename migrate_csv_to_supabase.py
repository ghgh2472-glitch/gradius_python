"""
migrate_csv_to_supabase.py
Google Sheets 시트를 CSV로 내보낸 뒤 Supabase로 마이그레이션합니다.

=========================================================
사용 방법
=========================================================
1. Google Sheets 열기 → 각 시트 탭 클릭
   → 파일 > 다운로드 > CSV (.csv) 저장
2. 다운로드한 CSV를 아래 폴더에 복사:
       /workspaces/gradius_python/migration_csvs/

   파일명은 반드시 아래와 일치해야 합니다:
     필수: 문의작성.csv, STAFF.csv, 계약건은청구금액적기.csv,
           배정기록.csv, 지급내역.csv
     권장: 고객정보.csv, Roles.csv, Factors.csv, 견적상세.csv
     선택: 출석부.csv, 평가표.csv

3. python migrate_csv_to_supabase.py

=========================================================
주의: 현재 Python ERP(Google Sheets 기반)는 영향 없음
=========================================================
"""

import os
import sys
import csv
import uuid
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Supabase 클라이언트 ──────────────────────────────────
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ .env 파일에 SUPABASE_URL 과 SUPABASE_SERVICE_KEY 를 설정하세요.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

CSV_DIR = Path("migration_csvs")

# ── 유틸리티 함수 ────────────────────────────────────────

def read_csv(filename: str) -> list[dict]:
    """CSV 파일을 dict 리스트로 읽기 (BOM, 공백 처리 포함)"""
    path = CSV_DIR / filename
    if not path.exists():
        print(f"  ⚠️  {filename} 없음 — 건너뜀")
        return []
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean = {k.strip(): (v.strip() if isinstance(v, str) else v)
                     for k, v in row.items() if k and k.strip()}
            rows.append(clean)
    print(f"  📋 {filename}: {len(rows)}행 로드")
    return rows


def safe_int(v, default: int = 0) -> int:
    if v is None or str(v).strip() in ("", "nan", "None", "-"):
        return default
    try:
        return int(float(str(v).replace(",", "").replace("원", "").strip()))
    except Exception:
        return default


def safe_str(v) -> str | None:
    if v is None or str(v).strip() in ("", "nan", "None"):
        return None
    return str(v).strip()


def safe_bool(v, default: bool = True) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() not in ("false", "0", "x", "아니오", "아니요", "미대상", "제외", "n")


def safe_date(v) -> str | None:
    if not v or str(v).strip() in ("", "nan", "None", "-"):
        return None
    s = str(v).strip().replace("/", "-")
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except Exception:
        return None


def safe_datetime(v) -> str | None:
    if not v or str(v).strip() in ("", "nan", "None", "-"):
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(s[: len(fmt) + 2], fmt).isoformat()
        except Exception:
            continue
    return None


def get_or_create(table: str, key_col: str, key_val: str, extra_data: dict = None) -> str | None:
    """key_val로 행을 조회, 없으면 insert. UUID 반환."""
    if not key_val:
        return None
    try:
        res = sb.table(table).select("id").eq(key_col, key_val).execute()
        if res.data:
            return res.data[0]["id"]
        data = {key_col: key_val}
        if extra_data:
            data.update(extra_data)
        ins = sb.table(table).insert(data).execute()
        return ins.data[0]["id"] if ins.data else None
    except Exception as e:
        print(f"    ❌ get_or_create({table}, {key_val}): {e}")
        return None


# ── 1. 고객정보 (customers) ──────────────────────────────

def migrate_customers() -> dict:
    rows = read_csv("고객정보.csv")
    if not rows:
        return {}

    company_id_map: dict[str, str] = {}
    inserted = 0

    for row in rows:
        company_name = safe_str(
            row.get("업체명") or row.get("회사명") or row.get("고객명")
        )
        if not company_name:
            continue

        biz_num = safe_str(row.get("사업자번호") or row.get("사업자등록번호"))
        data = {
            "company_name": company_name,
            "rep_name": safe_str(row.get("대표자") or row.get("대표자명")),
            "biz_number": biz_num,
            "biz_type": safe_str(row.get("업태")),
            "biz_item": safe_str(row.get("종목")),
            "address": safe_str(row.get("주소") or row.get("사업장주소")),
            "email": safe_str(row.get("이메일")),
            "contact_name": safe_str(row.get("담당자")),
            "phone": safe_str(row.get("연락처") or row.get("전화번호")),
            "memo": safe_str(row.get("메모") or row.get("비고")),
            "customer_type": "법인" if biz_num else "개인",
        }
        data = {k: v for k, v in data.items() if v is not None}

        try:
            result = sb.table("customers").upsert(data, on_conflict="company_name").execute()
            if result.data:
                company_id_map[company_name] = result.data[0]["id"]
            inserted += 1
        except Exception as e:
            print(f"    ❌ 고객 저장 실패 ({company_name}): {e}")

    print(f"  ✅ 고객정보: {inserted}건 완료")
    return company_id_map


# ── 2. 직군 (roles) ──────────────────────────────────────

def migrate_roles() -> dict:
    rows = read_csv("Roles.csv")
    if not rows:
        return {}

    role_id_map: dict[str, str] = {}
    inserted = 0

    for row in rows:
        role_code = safe_str(row.get("직군코드") or row.get("role_id") or row.get("코드"))
        role_name = safe_str(row.get("직군명") or row.get("역할명") or row.get("role_name"))
        if not role_code or not role_name:
            continue

        data = {
            "role_code": role_code,
            "role_name": role_name,
            "base_price": safe_int(row.get("기본단가") or row.get("단가")),
            "pay_price": safe_int(row.get("지급단가") or row.get("기본지급")),
            "leader_bonus": safe_int(row.get("팀장가산") or row.get("팀장수당"), 10000),
        }

        try:
            result = sb.table("roles").upsert(data, on_conflict="role_code").execute()
            if result.data:
                rid = result.data[0]["id"]
                role_id_map[role_code] = rid
                role_id_map[role_name] = rid
            inserted += 1
        except Exception as e:
            print(f"    ❌ 직군 저장 실패 ({role_code}): {e}")

    print(f"  ✅ Roles: {inserted}건 완료")
    return role_id_map


# ── 3. 직원 (staff) ──────────────────────────────────────

def migrate_staff() -> dict:
    rows = read_csv("STAFF.csv")
    if not rows:
        return {}

    staff_id_map: dict[str, str] = {}
    inserted = 0

    RECOMMEND_MAP = {
        "우선": "우선투입",
        "우선투입": "우선투입",
        "일반": "일반",
        "보류": "보류",
    }

    for row in rows:
        name = safe_str(row.get("이름") or row.get("성명"))
        if not name:
            continue

        jobs_raw = safe_str(row.get("가능직무") or row.get("직무"))
        certs_raw = safe_str(row.get("자격증") or row.get("보유자격"))
        available_jobs = [j.strip() for j in jobs_raw.split(",") if j.strip()] if jobs_raw else []
        certifications = [c.strip() for c in certs_raw.split(",") if c.strip()] if certs_raw else []

        recommend_raw = safe_str(row.get("추천등급") or row.get("추천")) or "일반"
        recommend = RECOMMEND_MAP.get(recommend_raw, "일반")

        age_val = safe_int(row.get("나이") or row.get("연령")) or None
        height_val = safe_int(row.get("키") or row.get("신장")) or None

        data = {
            "name": name,
            "gender": safe_str(row.get("성별")),
            "age": age_val,
            "height": height_val,
            "total_score": safe_int(row.get("총점")),
            "english_skill": safe_str(row.get("영어") or row.get("영어능력")),
            "driving": safe_str(row.get("운전면허") or row.get("운전")),
            "region": safe_str(row.get("거주지") or row.get("지역")),
            "available_jobs": available_jobs,
            "certifications": certifications,
            "recommend": recommend,
            "phone": safe_str(row.get("연락처") or row.get("전화번호")),
            "attendance_score": safe_int(row.get("근태점수")),
            "performance_score": safe_int(row.get("수행점수")),
            "appearance_score": safe_int(row.get("외모점수")),
            "teamwork_score": safe_int(row.get("팀워크점수")),
            "bank_name": safe_str(row.get("은행명")),
            "account_number": safe_str(row.get("계좌번호")),
            "id_number": safe_str(row.get("주민등록번호") or row.get("주민번호")),
            "memo": safe_str(row.get("총평") or row.get("메모")),
        }
        # None 값 제거 (배열은 유지)
        data = {k: v for k, v in data.items() if v is not None}

        try:
            # staff는 company_name 같은 unique key가 없으므로 이름으로 조회 후 upsert
            existing = sb.table("staff").select("id").eq("name", name).execute()
            if existing.data:
                sid = existing.data[0]["id"]
                sb.table("staff").update(data).eq("id", sid).execute()
            else:
                result = sb.table("staff").insert(data).execute()
                sid = result.data[0]["id"] if result.data else None

            if sid and name not in staff_id_map:
                staff_id_map[name] = sid
            inserted += 1
        except Exception as e:
            print(f"    ❌ 직원 저장 실패 ({name}): {e}")

    print(f"  ✅ STAFF: {inserted}건 완료")
    return staff_id_map


# ── 4. 문의 (inquiries) ──────────────────────────────────

def migrate_inquiries() -> dict:
    rows = read_csv("문의작성.csv")
    if not rows:
        return {}

    inq_id_map: dict[str, str] = {}
    inserted = 0
    VALID_STATUSES = {
        "접수", "견적", "체결", "배정완료", "진행중", "완료", "정산완료", "미체결", "보류", "취소"
    }

    for row in rows:
        inq_code = safe_str(row.get("문의ID") or row.get("ID"))
        event_name = safe_str(row.get("행사명") or row.get("행사"))
        if not event_name:
            continue

        status_raw = safe_str(row.get("상태") or row.get("진행상태")) or "접수"
        status = status_raw if status_raw in VALID_STATUSES else "접수"

        data = {
            "inquiry_code": inq_code,
            "company_name": safe_str(row.get("업체명") or row.get("업체")),
            "contact_name": safe_str(row.get("담당자")),
            "phone": safe_str(row.get("연락처") or row.get("전화번호")),
            "event_name": event_name,
            "location": safe_str(row.get("장소") or row.get("행사장소")),
            "event_start": safe_date(row.get("행사시작일") or row.get("시작일")),
            "event_end": safe_date(row.get("행사종료일") or row.get("종료일")),
            "event_time": safe_str(row.get("행사시간") or row.get("시간")),
            "service_type": safe_str(row.get("서비스종류") or row.get("서비스")),
            "required_staff": safe_int(row.get("필요인원") or row.get("인원")) or None,
            "expected_pay": safe_int(row.get("예상페이")) or None,
            "status": status,
            "notes": safe_str(row.get("특이사항") or row.get("비고")),
            "memo": safe_str(row.get("메모")),
            "relationship": safe_str(row.get("관계") or row.get("신규기존")),
            "category": safe_str(row.get("구분")),
            "attire": safe_str(row.get("복장")),
            "meal": safe_str(row.get("식사")),
            "parking": safe_str(row.get("주차")),
            "consult_notes": safe_str(row.get("상담내용")),
        }
        data = {k: v for k, v in data.items() if v is not None}

        try:
            if inq_code:
                result = sb.table("inquiries").upsert(data, on_conflict="inquiry_code").execute()
            else:
                result = sb.table("inquiries").insert(data).execute()

            if result.data:
                row_id = result.data[0]["id"]
                if inq_code:
                    inq_id_map[inq_code] = row_id
            inserted += 1
        except Exception as e:
            print(f"    ❌ 문의 저장 실패 ({inq_code}): {e}")

    print(f"  ✅ 문의작성: {inserted}건 완료")
    return inq_id_map


# ── 5. 견적 (estimates) ──────────────────────────────────

def migrate_estimates(inq_id_map: dict) -> dict:
    rows = read_csv("견적상세.csv")
    if not rows:
        return {}

    est_id_map: dict[str, str] = {}
    inserted = 0
    skipped = 0

    for row in rows:
        est_code = safe_str(row.get("견적ID") or row.get("ID"))
        inq_code = safe_str(row.get("문의ID"))
        inquiry_uuid = inq_id_map.get(inq_code) if inq_code else None

        supply = safe_int(row.get("공급가액"))
        cost = safe_int(row.get("매입원가"))
        extra = safe_int(row.get("부대비용"))

        # expected_profit 은 GENERATED ALWAYS AS — 절대 포함하지 않음
        data = {
            "estimate_code": est_code,
            "inquiry_id": inquiry_uuid,
            "company_name": safe_str(row.get("업체명") or row.get("업체")),
            "event_name": safe_str(row.get("행사명")),
            "site_name": safe_str(row.get("현장명")),
            "manager": safe_str(row.get("책임자")),
            "site_address": safe_str(row.get("현장주소")),
            "supply_price": supply,
            "vat": safe_int(row.get("부가세")),
            "total_price": safe_int(row.get("합계금액") or row.get("합계")),
            "cost_price": cost,
            "extra_cost": extra,
            "attire": safe_str(row.get("복장")),
            "meal": safe_str(row.get("식사")),
            "parking": safe_str(row.get("주차")),
            "notes": safe_str(row.get("특이사항") or row.get("비고")),
            "send_status": safe_str(row.get("발송여부")) or "미발송",
            "sent_at": safe_datetime(row.get("발송일시")),
            "send_method": safe_str(row.get("발송방법")),
            "send_memo": safe_str(row.get("발송메모")),
        }

        # 수익률 계산
        if supply and supply > 0:
            try:
                data["profit_rate"] = round((supply - cost - extra) / supply * 100, 2)
            except Exception:
                pass

        data = {k: v for k, v in data.items() if v is not None}

        try:
            if est_code:
                result = sb.table("estimates").upsert(data, on_conflict="estimate_code").execute()
            else:
                result = sb.table("estimates").insert(data).execute()

            if result.data:
                key = est_code or inq_code or ""
                est_id_map[key] = result.data[0]["id"]
            inserted += 1
        except Exception as e:
            print(f"    ❌ 견적 저장 실패 ({est_code}): {e}")

    print(f"  ✅ 견적상세: {inserted}건 완료 ({skipped}건 FK 없어 건너뜀)")
    return est_id_map


# ── 6. 정산 (settlements) ────────────────────────────────

def migrate_settlements(inq_id_map: dict):
    rows = read_csv("계약건은청구금액적기.csv")
    if not rows:
        return

    inserted = 0
    skipped = 0

    VALID_PROGRESS = {"계약체결", "행사준비", "행사종료", "정산완료"}
    VALID_DEPOSIT = {"입금완료", "부분입금", "미입금"}
    PROGRESS_MAP = {
        "완료": "행사종료",
        "배정완료": "계약체결",
        "진행중": "행사준비",
        "체결": "계약체결",
    }

    for row in rows:
        inq_code = safe_str(row.get("문의ID"))
        inquiry_uuid = inq_id_map.get(inq_code) if inq_code else None

        if not inquiry_uuid:
            skipped += 1
            continue

        progress_raw = safe_str(row.get("진행상황") or row.get("진행상태")) or "계약체결"
        progress = PROGRESS_MAP.get(progress_raw, progress_raw)
        if progress not in VALID_PROGRESS:
            progress = "계약체결"

        deposit_raw = safe_str(row.get("입금여부") or row.get("입금상태")) or "미입금"
        deposit = deposit_raw if deposit_raw in VALID_DEPOSIT else "미입금"

        tax_invoice_raw = safe_str(row.get("세금계산서 발행여부") or row.get("세금계산서"))
        tax_invoice = tax_invoice_raw in ("O", "o", "발행", "Y", "y", "True", "true", "완료")

        # balance, profit 는 GENERATED ALWAYS AS — 절대 포함하지 않음
        data = {
            "inquiry_id": inquiry_uuid,
            "site_name": safe_str(row.get("현장명")),
            "company_name": safe_str(row.get("업체") or row.get("업체명")),
            "dispatch_period": safe_str(row.get("파견일자") or row.get("파견기간")),
            "manager": safe_str(row.get("책임자")),
            "site_address": safe_str(row.get("현장주소")),
            "invoice_amount": safe_int(row.get("청구금액")),
            "supply_price": safe_int(row.get("공급가액")),
            "vat": safe_int(row.get("부가세")),
            "received_amount": safe_int(row.get("받은금액")),
            "progress": progress,
            "deposit_status": deposit,
            "tax_invoice_issued": tax_invoice,
            "payout_amount": safe_int(row.get("지급액")),
            "invoice_calc_amount": safe_int(row.get("계산서금액")),
            "withholding_tax": safe_int(row.get("3.3%") or row.get("원천세")),
            "category": safe_str(row.get("구분")),
            "biz_number": safe_str(row.get("사업자번호")),
            "rep_name": safe_str(row.get("대표자")),
            "email": safe_str(row.get("이메일")),
            "corp_name": safe_str(row.get("법인명")),
            "item_description": safe_str(
                row.get("내용(품목)") or row.get("내용") or row.get("품목")
            ),
            "contact_phone": safe_str(row.get("연락처")),
            "invoice_request": safe_str(row.get("발행요청사항")),
            "biz_reg_url": safe_str(row.get("사업자등록증URL")),
        }
        data = {k: v for k, v in data.items() if v is not None}

        try:
            sb.table("settlements").upsert(data, on_conflict="inquiry_id").execute()
            inserted += 1
        except Exception as e:
            print(f"    ❌ 정산 저장 실패 ({inq_code}): {e}")

    print(f"  ✅ 계약건은청구금액적기: {inserted}건 완료 ({skipped}건 FK 없어 건너뜀)")


# ── 7. 배정 (assignments) ────────────────────────────────

def migrate_assignments(inq_id_map: dict, staff_id_map: dict) -> dict:
    rows = read_csv("배정기록.csv")
    if not rows:
        return {}

    assign_id_map: dict[str, str] = {}
    inserted = 0
    skipped = 0

    VALID_STATUS = {"후보", "배정중", "확정", "취소"}

    for row in rows:
        assign_code = safe_str(row.get("배정ID") or row.get("ID"))
        inq_code = safe_str(row.get("문의ID"))
        inquiry_uuid = inq_id_map.get(inq_code) if inq_code else None

        if not inquiry_uuid:
            skipped += 1
            continue

        staff_name = safe_str(row.get("이름") or row.get("성명"))
        staff_uuid = staff_id_map.get(staff_name) if staff_name else None

        status_raw = (
            safe_str(row.get("배정상태") or row.get("지급상태") or row.get("상태")) or "후보"
        )
        status = status_raw if status_raw in VALID_STATUS else "후보"

        staff_type_raw = safe_str(row.get("구분") or row.get("소속")) or "본사"
        staff_type = staff_type_raw if staff_type_raw in ("본사", "외부") else "본사"

        # total_pay 는 GENERATED ALWAYS AS — 절대 포함하지 않음
        data = {
            "assignment_code": assign_code,
            "inquiry_id": inquiry_uuid,
            "event_name": safe_str(row.get("행사명")),
            "staff_id": staff_uuid,
            "staff_name": staff_name,
            "staff_type": staff_type,
            "job_type": safe_str(row.get("직무")),
            "phone": safe_str(row.get("연락처") or row.get("전화번호")),
            "id_number": safe_str(row.get("주민번호") or row.get("주민등록번호")),
            "bank_name": safe_str(row.get("은행명")),
            "account_number": safe_str(row.get("계좌번호")),
            "pay_rate": safe_int(row.get("지급단가") or row.get("단가")),
            "work_days": safe_int(row.get("근무일수") or row.get("일수")),
            "status": status,
            "assigned_at": safe_datetime(row.get("배정일시")),
            "team_code": safe_str(row.get("팀코드")),
            "is_payable": safe_bool(row.get("결제대상"), True),
            "is_present": safe_bool(row.get("현장참여"), True),
            "start_date": safe_date(row.get("근무시작일") or row.get("시작일")),
            "end_date": safe_date(row.get("근무종료일") or row.get("종료일")),
            "memo": safe_str(row.get("메모") or row.get("비고")),
        }
        data = {k: v for k, v in data.items() if v is not None}

        try:
            if assign_code:
                result = sb.table("assignments").upsert(data, on_conflict="assignment_code").execute()
            else:
                result = sb.table("assignments").insert(data).execute()

            if result.data:
                akey = assign_code or f"{inq_code}_{staff_name}"
                assign_id_map[akey] = result.data[0]["id"]
            inserted += 1
        except Exception as e:
            print(f"    ❌ 배정 저장 실패 ({assign_code}): {e}")

    print(f"  ✅ 배정기록: {inserted}건 완료 ({skipped}건 FK 없어 건너뜀)")
    return assign_id_map


# ── 8. 지급 (payouts) ────────────────────────────────────

def migrate_payouts(inq_id_map: dict, assign_id_map: dict):
    rows = read_csv("지급내역.csv")
    if not rows:
        return

    inserted = 0
    VALID_STATUS = {"대기", "완료", "확인완료", "미지급"}

    for row in rows:
        payout_code = safe_str(row.get("지급ID") or row.get("ID"))
        inq_code = safe_str(row.get("문의ID"))
        inquiry_uuid = inq_id_map.get(inq_code) if inq_code else None

        status_raw = safe_str(row.get("지급상태") or row.get("상태")) or "대기"
        status = status_raw if status_raw in VALID_STATUS else "대기"

        data = {
            "payout_code": payout_code,
            "inquiry_id": inquiry_uuid,
            "staff_name": safe_str(row.get("이름") or row.get("성명")),
            "site_name": safe_str(row.get("현장명")),
            "dispatch_period": safe_str(row.get("파견기간") or row.get("파견일자")),
            "dispatch_days": safe_int(row.get("파견일수") or row.get("일수")),
            "base_pay": safe_int(row.get("기본급") or row.get("기본페이")),
            "overtime_pay": safe_int(row.get("야근비") or row.get("초과수당")),
            "meal_pay": safe_int(row.get("식사비") or row.get("식대")),
            "transport_pay": safe_int(row.get("교통비") or row.get("택시비")),
            "bonus": safe_int(row.get("보너스")),
            "subtotal": safe_int(row.get("소계")),
            "tax_deduction": safe_int(row.get("세금공제") or row.get("3.3%") or row.get("원천세")),
            "final_pay": safe_int(row.get("최종지급액") or row.get("실지급액")),
            "status": status,
            "paid_at": safe_date(row.get("지급일") or row.get("지급일시")),
            "paid_by": safe_str(row.get("지급자")),
            "bank_name": safe_str(row.get("은행명")),
            "account_number": safe_str(row.get("계좌번호")),
            "id_number": safe_str(row.get("주민번호") or row.get("주민등록번호")),
            "notes": safe_str(row.get("메모") or row.get("비고")),
        }
        data = {k: v for k, v in data.items() if v is not None}

        try:
            if payout_code:
                sb.table("payouts").upsert(data, on_conflict="payout_code").execute()
            else:
                sb.table("payouts").insert(data).execute()
            inserted += 1
        except Exception as e:
            print(f"    ❌ 지급 저장 실패 ({payout_code}): {e}")

    print(f"  ✅ 지급내역: {inserted}건 완료")


# ── 9. 출석부 (attendances) ─────────────────────────────

def migrate_attendances(inq_id_map: dict):
    rows = read_csv("출석부.csv")
    if not rows:
        return

    inserted = 0
    VALID_STATUS = {"출석", "지각", "결근", "조퇴", "외출"}

    for row in rows:
        record_code = safe_str(row.get("기록ID") or row.get("ID"))
        inq_code = safe_str(row.get("문의ID"))
        inquiry_uuid = inq_id_map.get(inq_code) if inq_code else None
        work_date = safe_date(row.get("근무일자") or row.get("일자"))

        if not work_date:
            continue

        status_raw = safe_str(row.get("출결상태") or row.get("상태")) or "출석"
        status = status_raw if status_raw in VALID_STATUS else "출석"

        data = {
            "record_code": record_code,
            "inquiry_id": inquiry_uuid,
            "staff_name": safe_str(row.get("이름") or row.get("성명")),
            "work_date": work_date,
            "clock_in": safe_str(row.get("출근시간") or row.get("출근")),
            "clock_out": safe_str(row.get("퇴근시간") or row.get("퇴근")),
            "daily_pay": safe_int(row.get("일급") or row.get("일당")),
            "status": status,
            "reason": safe_str(row.get("사유")),
            "notes": safe_str(row.get("메모") or row.get("비고")),
        }
        data = {k: v for k, v in data.items() if v is not None}

        try:
            if record_code:
                sb.table("attendances").upsert(data, on_conflict="record_code").execute()
            else:
                sb.table("attendances").insert(data).execute()
            inserted += 1
        except Exception as e:
            print(f"    ❌ 출석 저장 실패: {e}")

    print(f"  ✅ 출석부: {inserted}건 완료")


# ── MAIN ─────────────────────────────────────────────────

def main():
    print("=" * 57)
    print("  Gradius ERP — CSV → Supabase 마이그레이션")
    print("=" * 57)

    if not CSV_DIR.exists():
        CSV_DIR.mkdir()
        print(f"\n📁 migration_csvs/ 폴더를 생성했습니다.")
        print("\n  Google Sheets에서 각 시트를 다음 순서로 CSV 저장:")
        for f in [
            "  1. 고객정보.csv      ← '고객정보' 탭",
            "  2. Roles.csv         ← 'Roles' 탭",
            "  3. STAFF.csv         ← 'STAFF' 탭",
            "  4. 문의작성.csv       ← '문의작성' 탭",
            "  5. 견적상세.csv       ← '견적상세' 탭",
            "  6. 배정기록.csv       ← '배정기록' 탭",
            "  7. 계약건은청구금액적기.csv  ← '계약건은청구금액적기' 탭",
            "  8. 지급내역.csv       ← '지급내역' 탭",
            "  9. 출석부.csv         ← '출석부' 탭 (선택)",
        ]:
            print(f)
        print("\n  저장 위치: /workspaces/gradius_python/migration_csvs/")
        print("\n  완료 후 다시 실행하세요: python migrate_csv_to_supabase.py")
        return

    csv_files = list(CSV_DIR.glob("*.csv"))
    if not csv_files:
        print(f"\n❌ migration_csvs/ 폴더가 비어있습니다.")
        print("  Google Sheets에서 CSV를 다운로드하여 폴더에 넣어주세요.")
        return

    print(f"\n  발견된 CSV: {[f.name for f in csv_files]}\n")

    # FK 의존 순서대로 실행
    print("[1/9] 고객정보 이전 중...")
    company_id_map = migrate_customers()

    print("\n[2/9] 직군(Roles) 이전 중...")
    role_id_map = migrate_roles()

    print("\n[3/9] 직원(STAFF) 이전 중...")
    staff_id_map = migrate_staff()

    print("\n[4/9] 문의작성 이전 중...")
    inq_id_map = migrate_inquiries()

    print("\n[5/9] 견적상세 이전 중...")
    est_id_map = migrate_estimates(inq_id_map)

    print("\n[6/9] 정산(계약건은청구금액적기) 이전 중...")
    migrate_settlements(inq_id_map)

    print("\n[7/9] 배정기록 이전 중...")
    assign_id_map = migrate_assignments(inq_id_map, staff_id_map)

    print("\n[8/9] 지급내역 이전 중...")
    migrate_payouts(inq_id_map, assign_id_map)

    print("\n[9/9] 출석부 이전 중...")
    migrate_attendances(inq_id_map)

    print("\n" + "=" * 57)
    print("  ✅ 마이그레이션 완료!")
    print(f"     문의: {len(inq_id_map)}건  |  직원: {len(staff_id_map)}건")
    print("=" * 57)
    print("\n  Supabase 대시보드에서 데이터를 확인하세요:")
    print("  https://supabase.com/dashboard/project/mpdpwmouxzhmostimafd/editor")


if __name__ == "__main__":
    main()
