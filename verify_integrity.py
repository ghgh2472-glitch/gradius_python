#!/usr/bin/env python3
"""
verify_integrity.py — 코드 무결성 검증 도구
커밋 전에 핵심 기능이 누락되지 않았는지 자동으로 확인합니다.
사용법: python verify_integrity.py [--strict] [--quiet]
"""
import re, sys, os

# ──────────────────────────────────────────────────
# 1. 파일별 최소 라인 수 (현재 기준 70% 하한선)
#    이보다 줄어들면 대량 삭제가 일어난 것으로 간주
# ──────────────────────────────────────────────────
MIN_LINES = {
    "page_staff_new.py":  1600,   # 현재 2338
    "page_settlement.py": 1600,   # 현재 2311
    "data_loader.py":     2200,   # 현재 3100+
    "page_estimate.py":   2000,   # 현재 2400+
    "page_contract.py":    280,   # 현재 425
    "page_ceo.py":         300,   # 현재 400+
    "page_inquiry.py":     220,   # 현재 338
    "utils_dashboard.py":  800,   # 현재 1157
}

# ──────────────────────────────────────────────────
# 2. 파일별 반드시 존재해야 하는 핵심 함수 목록
# ──────────────────────────────────────────────────
REQUIRED_FUNCTIONS = {
    "page_staff_new.py": [
        "show",                        # 메인 진입점
        "_render_team_assignment_ui",   # 팀 배정 UI
        "tab_attendance",              # 출석 탭
        "tab_evaluation",              # 평가 탭
        "tab_payment",                 # 지급 탭
        "_team_prefix",                # 팀 코드 처리
        "_strip_date_tag",             # 날짜 태그 제거
    ],
    "page_settlement.py": [
        "show",                        # 메인 진입점
        "show_settlement_detail",      # 정산 상세
        "show_tax_invoice_management", # 세금계산서
        "_get_bank_info",              # 은행정보 조회
        "_save_bank_to_staff",         # 은행정보 저장
        "_batch_save_bank_to_staff",   # 은행정보 배치 저장
        "_parse_tax_rate",             # 공제율 파싱
    ],
    "data_loader.py": [
        "get_connection",              # DB 연결
        "load_all_data",               # 전체 로드
        "get_dispatch",                # 배정/정산 로드
        "invalidate_data",             # 전체 캐시 무효화
        "invalidate_main_only",        # 메인만 무효화
        "invalidate_dispatch_only",    # 배정/정산만 무효화
        "invalidate_payment_cache",    # 지급내역 캐시 무효화
        "update_status",               # 상태 변경
        "save_payment_record",         # 지급 기록 저장
        "batch_save_payment_records",  # 지급 배치 저장
        "save_settlement_record",      # 정산 기록 저장
        "ensure_inquiry_headers",      # 헤더 보장
        "ensure_payment_headers",      # 지급내역 헤더 보장
        "get_assignments_by_inquiry",  # 배정 조회
    ],
    "page_estimate.py": [
        "show",                        # 메인 진입점
        "_show_send_status_section",   # 발송 상태 섹션
        "_load_existing_items",        # 기존 품목 로드
        "_collect_metadata",           # 메타데이터 수집
        "_restore_metadata",           # 메타데이터 복원
    ],
    "page_ceo.py": [
        "show",                        # 메인 진입점
        "_render_tax_invoice_tab",     # 세금계산서 탭
        "_render_payment_tab",         # 인력비 탭
        "_get_tax_invoice_stats",      # 세금계산서 통계
        "_get_unpaid_staff_stats",     # 미지급 통계
    ],
    "utils_dashboard.py": [
        "get_settlement_overview",     # 정산 요약
        "get_operating_profit",        # 영업이익
        "calculate_kpi",               # KPI 계산
        "get_unpaid_companies",        # 미수금 업체
    ],
}

# ──────────────────────────────────────────────────
# 3. 모듈 임포트 검증 (app.py가 참조하는 모듈)
# ──────────────────────────────────────────────────
REQUIRED_FILES = [
    "app.py", "page_ceo.py", "page_dashboard.py", "page_inquiry.py", "page_estimate.py",
    "page_contract.py", "page_staff_new.py", "page_settlement.py",
    "page_search.py", "page_customer.py", "page_guide.py",
    "data_loader.py", "utils_dashboard.py", "status_config.py",
]


def check_file_exists(base_dir):
    """필수 파일 존재 확인"""
    errors = []
    for f in REQUIRED_FILES:
        if not os.path.exists(os.path.join(base_dir, f)):
            errors.append(f"❌ 필수 파일 누락: {f}")
    return errors


def check_line_counts(base_dir):
    """파일별 최소 라인 수 확인 (대량 삭제 감지)"""
    errors = []
    warnings = []
    for fname, min_count in MIN_LINES.items():
        fpath = os.path.join(base_dir, fname)
        if not os.path.exists(fpath):
            continue  # 파일 존재 검사는 별도
        with open(fpath, 'r', encoding='utf-8') as f:
            lines = sum(1 for _ in f)
        if lines < min_count:
            delta = min_count - lines
            errors.append(
                f"❌ {fname}: {lines}줄 (최소 {min_count}줄 필요, {delta}줄 부족) "
                f"→ 대량 삭제 의심!"
            )
        elif lines < min_count * 1.15:  # 15% 여유 이내면 경고
            warnings.append(f"⚠️  {fname}: {lines}줄 (최소 기준에 근접)")
    return errors, warnings


def check_required_functions(base_dir):
    """핵심 함수 존재 확인"""
    errors = []
    for fname, funcs in REQUIRED_FUNCTIONS.items():
        fpath = os.path.join(base_dir, fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for func_name in funcs:
            # def func_name( 패턴 검색
            pattern = rf'def\s+{re.escape(func_name)}\s*\('
            if not re.search(pattern, content):
                errors.append(f"❌ {fname}: 핵심 함수 '{func_name}()' 누락!")
    return errors


# ──────────────────────────────────────────────────
# 핵심 키워드 검증 (특정 기능이 전체 제거된 것을 감지)
# ──────────────────────────────────────────────────
REQUIRED_KEYWORDS = {
    "page_estimate.py": [
        ("w_date_text", "날짜 직접입력 기능"),
        ("_date_input_mode", "날짜 달력/직접입력 모드 토글"),
        ("additional_costs", "부대비용 기능"),
        ("_bak_w_client", "탭 전환 백업/복원 로직"),
        ("final_date_", "견적서 발행탭 날짜 편집 필드"),
        ("save_estimate_items", "견적품목 저장 호출"),
        ("load_additional_costs", "부대비용 로드 호출"),
    ],
    "data_loader.py": [
        ("save_estimate_items", "견적품목 저장 함수"),
        ("load_estimate_items", "견적품목 로드 함수"),
        ("load_additional_costs", "부대비용 로드 함수"),
        ("additional_costs_df", "부대비용 DF 파라미터"),
        ("\'\uad6c\ubd84\'", "견적품목 구분 컬럼"),        ("ensure_payment_headers", "지급내역 헤더 마이그레이션"),
        ("은행명", "지급내역 은행명 컬럼"),
        ("계좌번호", "지급내역 계좌번호 컬럼"),
    ],
    "page_settlement.py": [
        ("_batch_save_bank_to_staff", "은행정보 배치 저장 기능"),
        ("invalidate_payment_cache", "정밀 캐시 초기화"),
        ("주민등록번호", "주민등록번호 필드"),    ],
    "utils_dashboard.py": [
        ("후보", "후보군 제외 로직"),
        ("취소", "취소 제외 로직"),
        ("extendedProps", "캘린더 이벤트 상세 데이터"),
    ],
}


def check_required_keywords(base_dir):
    """핵심 키워드 존재 확인 (기능 전체 제거 감지)"""
    errors = []
    for fname, keywords in REQUIRED_KEYWORDS.items():
        fpath = os.path.join(base_dir, fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for keyword, desc in keywords:
            if keyword not in content:
                errors.append(f"\u274c {fname}: \u2018{keyword}\u2019 \ub204\ub77d \u2192 {desc} \uc81c\uac70\ub428!")
    return errors


def check_syntax(base_dir):
    """Python 구문 오류 확인"""
    import py_compile
    errors = []
    py_files = [f for f in os.listdir(base_dir)
                if f.endswith('.py') and not f.startswith('__')]
    for fname in sorted(py_files):
        fpath = os.path.join(base_dir, fname)
        try:
            py_compile.compile(fpath, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"❌ {fname}: 구문 오류 — {e}")
    return errors


def check_cross_references(base_dir):
    """주요 모듈 간 크로스 레퍼런스 확인"""
    errors = []
    # data_loader에서 정의된 함수가 호출 파일에서 쓰이는지 확인
    dl_path = os.path.join(base_dir, "data_loader.py")
    if not os.path.exists(dl_path):
        return errors
    
    with open(dl_path, 'r', encoding='utf-8') as f:
        dl_content = f.read()
    
    # data_loader의 public 함수 목록 추출
    dl_funcs = set(re.findall(r'^def\s+([a-zA-Z_]\w*)\s*\(', dl_content, re.MULTILINE))
    dl_funcs -= {f for f in dl_funcs if f.startswith('_')}  # private 제외
    
    # 호출자 파일에서 db.func_name() 호출 패턴 확인
    callers = ["page_ceo.py", "page_settlement.py", "page_staff_new.py", "page_estimate.py",
               "page_contract.py", "page_inquiry.py"]
    for caller in callers:
        cpath = os.path.join(base_dir, caller)
        if not os.path.exists(cpath):
            continue
        with open(cpath, 'r', encoding='utf-8') as f:
            caller_content = f.read()
        # db.xxx() 호출 찾기
        called = set(re.findall(r'db\.([a-zA-Z_]\w*)\s*\(', caller_content))
        missing = called - dl_funcs
        for m in missing:
            errors.append(f"❌ {caller}: db.{m}() 호출하지만 data_loader에 정의 없음")
    
    return errors


def main():
    strict = '--strict' in sys.argv
    quiet = '--quiet' in sys.argv
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    all_errors = []
    all_warnings = []
    
    if not quiet:
        print("=" * 60)
        print("🔍 Gradius 코드 무결성 검증")
        print("=" * 60)
    
    # 1. 파일 존재
    if not quiet:
        print("\n📁 [1/6] 필수 파일 존재 확인...")
    errs = check_file_exists(base_dir)
    all_errors.extend(errs)
    if not quiet and not errs:
        print("   ✅ 모든 필수 파일 존재")
    
    # 2. 라인 수
    if not quiet:
        print("\n📏 [2/6] 파일 크기 검증 (대량 삭제 감지)...")
    errs, warns = check_line_counts(base_dir)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    if not quiet and not errs:
        print("   ✅ 모든 파일 최소 라인 기준 충족")
    
    # 3. 핵심 함수
    if not quiet:
        print("\n🔧 [3/6] 핵심 함수 존재 확인...")
    errs = check_required_functions(base_dir)
    all_errors.extend(errs)
    if not quiet and not errs:
        print("   ✅ 모든 핵심 함수 존재")
    
    # 4. 구문 검사
    if not quiet:
        print("\n📝 [4/6] Python 구문 검증...")
    errs = check_syntax(base_dir)
    all_errors.extend(errs)
    if not quiet and not errs:
        print("   ✅ 모든 파일 구문 정상")
    
    # 5. 핵심 키워드
    if not quiet:
        print("\n🔑 [5/6] 핵심 키워드 존재 확인 (기능 누락 감지)...")
    errs = check_required_keywords(base_dir)
    all_errors.extend(errs)
    if not quiet and not errs:
        print("   ✅ 모든 핵심 키워드 존재")

    # 6. 크로스 레퍼런스
    if not quiet:
        print("\n🔗 [6/6] 모듈 간 크로스 레퍼런스 확인...")
    errs = check_cross_references(base_dir)
    all_errors.extend(errs)
    if not quiet and not errs:
        print("   ✅ 모든 크로스 레퍼런스 정상")
    
    # 결과 출력
    if not quiet:
        print("\n" + "=" * 60)
    
    if all_warnings and not quiet:
        print("\n⚠️  경고:")
        for w in all_warnings:
            print(f"   {w}")
    
    if all_errors:
        if not quiet:
            print(f"\n🚨 오류 {len(all_errors)}건 발견:")
        for e in all_errors:
            print(f"   {e}")
        if not quiet:
            print(f"\n❌ 검증 실패 — 커밋을 중단합니다!")
        sys.exit(1)
    else:
        if not quiet:
            print(f"\n✅ 모든 검증 통과! 커밋해도 안전합니다.")
        sys.exit(0)


if __name__ == "__main__":
    main()
