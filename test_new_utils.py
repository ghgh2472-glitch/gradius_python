"""test_new_utils.py
신규 유틸리티 모듈 테스트

실행:
    python test_new_utils.py
    또는
    pytest test_new_utils.py -v
"""
import sys
import os

# 프로젝트 루트 경로를 모듈 검색 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from datetime import datetime


# ======================================================================
# 1. utils_validation 테스트
# ======================================================================
def test_validate_settlement():
    from utils_validation import validate_settlement

    # 유효한 데이터
    ok, errors = validate_settlement({"문의ID": "INQ-001", "청구금액": 1000000, "지급금액": 500000})
    assert ok is True, f"유효한 정산 데이터인데 실패: {errors}"
    assert errors == []

    # 문의ID 누락
    ok, errors = validate_settlement({"문의ID": "", "청구금액": 100})
    assert ok is False
    assert any("문의ID" in e for e in errors)

    # 지급금액 > 청구금액
    ok, errors = validate_settlement({"문의ID": "INQ-001", "청구금액": 1000, "지급금액": 2000})
    assert ok is False
    assert any("초과" in e for e in errors)

    print("✅ validate_settlement 통과")


def test_validate_attendance():
    from utils_validation import validate_attendance

    # 유효한 데이터
    ok, errors = validate_attendance({"배정ID": "A-001", "출석일자": "2026-01-15", "상태": "출석"})
    assert ok is True, f"유효한 출석 데이터인데 실패: {errors}"

    # 배정ID 누락
    ok, errors = validate_attendance({"배정ID": "", "출석일자": "2026-01-15"})
    assert ok is False

    # 잘못된 날짜
    ok, errors = validate_attendance({"배정ID": "A-001", "출석일자": "not-a-date"})
    assert ok is False

    # 잘못된 상태
    ok, errors = validate_attendance({"배정ID": "A-001", "출석일자": "2026-01-15", "상태": "잘못된상태"})
    assert ok is False

    print("✅ validate_attendance 통과")


def test_validate_phone():
    from utils_validation import validate_phone

    ok, result = validate_phone("01012345678")
    assert ok is True
    assert result == "010-1234-5678"

    ok, result = validate_phone("010-1234-5678")
    assert ok is True

    ok, result = validate_phone("12345")
    assert ok is False

    ok, result = validate_phone("")
    assert ok is False

    print("✅ validate_phone 통과")


def test_validate_date_range():
    from utils_validation import validate_date_range

    ok, msg = validate_date_range("2026-01-01", "2026-01-31")
    assert ok is True

    ok, msg = validate_date_range("2026-01-31", "2026-01-01")
    assert ok is False

    ok, msg = validate_date_range("invalid", "2026-01-01")
    assert ok is False

    print("✅ validate_date_range 통과")


def test_check_duplicate():
    from utils_validation import check_duplicate

    df = pd.DataFrame({
        "이름": ["홍길동", "김철수", "이영희"],
        "연락처": ["010-1111-2222", "010-3333-4444", "010-5555-6666"],
    })

    # 중복
    is_dup, msg = check_duplicate(df, ["이름", "연락처"], {"이름": "홍길동", "연락처": "010-1111-2222"})
    assert is_dup is True

    # 중복 아님
    is_dup, msg = check_duplicate(df, ["이름", "연락처"], {"이름": "박지수", "연락처": "010-9999-0000"})
    assert is_dup is False

    # 빈 DataFrame
    is_dup, msg = check_duplicate(pd.DataFrame(), ["이름"], {"이름": "홍길동"})
    assert is_dup is False

    print("✅ check_duplicate 통과")


def test_validate_business_number():
    from utils_validation import validate_business_number

    ok, result = validate_business_number("1234567890")
    assert ok is True
    assert result == "123-45-67890"

    ok, result = validate_business_number("123-45-67890")
    assert ok is True

    ok, result = validate_business_number("12345")
    assert ok is False

    print("✅ validate_business_number 통과")


# ======================================================================
# 2. utils_export 테스트
# ======================================================================
def test_export_to_excel():
    from utils_export import export_to_excel

    df = pd.DataFrame({
        "이름": ["홍길동", "김철수"],
        "금액": [1000000, 2000000],
    })

    result = export_to_excel(df, "테스트", title="테스트 리포트", number_columns=["금액"])
    assert isinstance(result, bytes)
    assert len(result) > 0
    # XLSX 매직 바이트 (PK)
    assert result[:2] == b"PK"

    print("✅ export_to_excel 통과")


def test_export_empty_dataframe():
    from utils_export import export_to_excel

    result = export_to_excel(pd.DataFrame(), "빈데이터")
    assert isinstance(result, bytes)
    assert len(result) > 0

    print("✅ export_empty_dataframe 통과")


def test_export_multiple_sheets():
    from utils_export import export_multiple_sheets

    sheets = {
        "문의": pd.DataFrame({"ID": ["INQ-001"], "업체명": ["테스트"]}),
        "견적": pd.DataFrame({"ID": ["EST-001"], "금액": [500000]}),
    }
    result = export_multiple_sheets(sheets)
    assert isinstance(result, bytes)
    assert result[:2] == b"PK"

    print("✅ export_multiple_sheets 통과")


# ======================================================================
# 3. utils_audit 테스트
# ======================================================================
def test_audit_logger():
    from utils_audit import AuditLogger

    AuditLogger.clear()

    AuditLogger.log("CREATE", "문의", "INQ-001", {"업체명": "테스트회사"}, user="admin")
    AuditLogger.log("UPDATE", "문의", "INQ-001", {"상태": "접수→견적"}, user="admin")
    AuditLogger.log("CREATE", "견적", "EST-001", {"금액": 1000000})

    recent = AuditLogger.get_recent(10)
    assert len(recent) == 3, f"Expected 3, got {len(recent)}"
    assert recent.iloc[0]["action"] == "CREATE"  # 최신 순이므로 마지막 추가한 것이 첫 번째

    # 엔티티별 조회
    entity_log = AuditLogger.get_by_entity("문의", "INQ-001")
    assert len(entity_log) == 2

    AuditLogger.clear()
    assert len(AuditLogger.get_recent()) == 0

    print("✅ audit_logger 통과")


# ======================================================================
# 4. utils_search 테스트
# ======================================================================
def test_search_dataframe():
    from utils_search import search_dataframe

    df = pd.DataFrame({
        "이름": ["홍길동", "김철수", "이영희"],
        "업체명": ["A회사", "B회사", "A회사"],
        "연락처": ["010-1111-2222", "010-3333-4444", "010-5555-6666"],
    })

    result = search_dataframe(df, "홍길동")
    assert len(result) == 1

    result = search_dataframe(df, "A회사")
    assert len(result) == 2

    result = search_dataframe(df, "존재하지않는")
    assert len(result) == 0

    # 특정 컬럼 검색
    result = search_dataframe(df, "A회사", columns=["업체명"])
    assert len(result) == 2

    # 빈 키워드
    result = search_dataframe(df, "")
    assert len(result) == 3

    print("✅ search_dataframe 통과")


def test_filter_by_status():
    from utils_search import filter_by_status

    df = pd.DataFrame({
        "이름": ["A", "B", "C"],
        "상태": ["접수", "견적", "접수"],
    })

    result = filter_by_status(df, "접수")
    assert len(result) == 2

    result = filter_by_status(df, "전체")
    assert len(result) == 3

    result = filter_by_status(df, "")
    assert len(result) == 3

    print("✅ filter_by_status 통과")


def test_filter_by_date_range():
    from utils_search import filter_by_date_range

    df = pd.DataFrame({
        "이름": ["A", "B", "C"],
        "날짜": ["2026-01-10", "2026-01-20", "2026-02-05"],
    })

    result = filter_by_date_range(df, "2026-01-01", "2026-01-31")
    assert len(result) == 2

    result = filter_by_date_range(df, "2026-02-01", "2026-02-28")
    assert len(result) == 1

    print("✅ filter_by_date_range 통과")


def test_get_unique_values():
    from utils_search import get_unique_values

    df = pd.DataFrame({
        "상태": ["접수", "견적", "접수", "체결"],
    })

    values = get_unique_values(df, "상태", include_all=True)
    assert values[0] == "전체"
    assert len(values) == 4  # 전체 + 3개 고유값

    values = get_unique_values(df, "상태", include_all=False)
    assert "전체" not in values
    assert len(values) == 3

    print("✅ get_unique_values 통과")


# ======================================================================
# 5. calculators.ValidationEngine 정산 검증 테스트
# ======================================================================
def test_validation_engine_settlement():
    from calculators import ValidationEngine

    ok, errors = ValidationEngine.validate_settlement({"문의ID": "INQ-001", "청구금액": 1000, "지급금액": 500})
    assert ok is True

    ok, errors = ValidationEngine.validate_settlement({"문의ID": "", "청구금액": -1})
    assert ok is False
    assert len(errors) >= 2

    print("✅ ValidationEngine.validate_settlement 통과")


# ======================================================================
# 6. workflow_automation 완성된 check_workflow_status 테스트
# ======================================================================
def test_check_workflow_status():
    from workflow_automation import check_workflow_status

    # 문의만 있는 경우
    data = {
        'inq': pd.DataFrame({'문의ID': ['INQ-001', 'INQ-002']}),
        'dispatch': pd.DataFrame(),
        'attendance': pd.DataFrame(),
        'payroll': pd.DataFrame(),
    }
    result = check_workflow_status('INQ-001', data)
    assert result['문의'] is True
    assert result['배정'] is False
    assert result['진행률'] == 0.25

    # 배정까지 완료
    data['dispatch'] = pd.DataFrame({'문의ID': ['INQ-001'], '배정ID': ['A-001'], '상태': ['배정중']})
    result = check_workflow_status('INQ-001', data)
    assert result['배정'] is True
    assert result['진행률'] == 0.5

    # 출석까지 완료
    data['attendance'] = pd.DataFrame({'배정ID': ['A-001'], '상태': ['출석']})
    result = check_workflow_status('INQ-001', data)
    assert result['출석'] is True
    assert result['진행률'] == 0.75

    # 지급까지 완료
    data['payroll'] = pd.DataFrame({'배정ID': ['A-001'], '지급상태': ['지급완료']})
    result = check_workflow_status('INQ-001', data)
    assert result['지급'] is True
    assert result['진행률'] == 1.0

    print("✅ check_workflow_status 통과")


# ======================================================================
# 실행
# ======================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🧪 신규 유틸리티 테스트 시작")
    print("=" * 60)

    tests = [
        # validation
        test_validate_settlement,
        test_validate_attendance,
        test_validate_phone,
        test_validate_date_range,
        test_check_duplicate,
        test_validate_business_number,
        # export
        test_export_to_excel,
        test_export_empty_dataframe,
        test_export_multiple_sheets,
        # audit
        test_audit_logger,
        # search
        test_search_dataframe,
        test_filter_by_status,
        test_filter_by_date_range,
        test_get_unique_values,
        # calculators
        test_validation_engine_settlement,
        # workflow
        test_check_workflow_status,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ {test_fn.__name__} 실패: {e}")
            failed += 1

    print("=" * 60)
    print(f"🎉 결과: {passed} 통과 / {failed} 실패 (총 {len(tests)}건)")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
