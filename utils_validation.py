"""utils_validation.py
데이터 검증 유틸리티 – 중복 방지, 필수값 확인, 범위 검증 등

기존 calculators.ValidationEngine을 보완하여
정산, 출석, 중복 검사 등 추가 검증 기능을 제공한다.
"""
import re
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd
from utils import safe_int
from helpers import get_logger

logger = get_logger(__name__)


def validate_settlement(data: Dict) -> Tuple[bool, List[str]]:
    """정산 데이터 검증

    Args:
        data: 정산 기록 딕셔너리

    Returns:
        (유효 여부, 오류 메시지 리스트)
    """
    errors: List[str] = []

    if not data.get("문의ID", "").strip():
        errors.append("문의ID는 필수입니다")

    amount = safe_int(data.get("청구금액", 0))
    if amount < 0:
        errors.append("청구금액은 0 이상이어야 합니다")

    paid = safe_int(data.get("지급금액", 0))
    if paid < 0:
        errors.append("지급금액은 0 이상이어야 합니다")

    if paid > amount and amount > 0:
        errors.append("지급금액이 청구금액을 초과할 수 없습니다")

    return len(errors) == 0, errors


def validate_attendance(data: Dict) -> Tuple[bool, List[str]]:
    """출석 기록 검증

    Args:
        data: 출석 기록 딕셔너리

    Returns:
        (유효 여부, 오류 메시지 리스트)
    """
    errors: List[str] = []

    if not data.get("배정ID", "").strip():
        errors.append("배정ID는 필수입니다")

    date_str = data.get("출석일자", "").strip()
    if not date_str:
        errors.append("출석일자는 필수입니다")
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            errors.append("출석일자 형식이 올바르지 않습니다 (YYYY-MM-DD)")

    valid_statuses = {"출석", "결근", "지각", "조퇴", "미기록"}
    status = data.get("상태", "").strip()
    if status and status not in valid_statuses:
        errors.append(f"상태는 {', '.join(valid_statuses)} 중 하나여야 합니다")

    return len(errors) == 0, errors


def validate_phone(phone: str) -> Tuple[bool, str]:
    """전화번호 형식 검증 및 정규화

    Returns:
        (유효 여부, 정규화된 전화번호 또는 오류 메시지)
    """
    if not phone:
        return False, "전화번호를 입력해주세요"

    digits = re.sub(r"[^0-9]", "", phone)

    if len(digits) == 11 and digits.startswith("010"):
        formatted = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        return True, formatted
    elif len(digits) == 10 and digits.startswith("02"):
        formatted = f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        return True, formatted
    elif len(digits) in (10, 11):
        formatted = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        return True, formatted
    else:
        return False, "올바른 전화번호 형식이 아닙니다"


def validate_date_range(start: str, end: str) -> Tuple[bool, str]:
    """날짜 범위 유효성 검증

    Returns:
        (유효 여부, 오류 메시지 또는 빈 문자열)
    """
    try:
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return False, "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)"

    if e < s:
        return False, "종료일이 시작일보다 빠를 수 없습니다"

    return True, ""


def check_duplicate(
    df: pd.DataFrame,
    key_columns: List[str],
    new_record: Dict,
) -> Tuple[bool, str]:
    """중복 레코드 여부를 검사한다.

    Args:
        df: 기존 데이터
        key_columns: 중복 판단 기준 컬럼 목록
        new_record: 새로 추가할 레코드

    Returns:
        (중복 여부, 안내 메시지)
    """
    if df.empty:
        return False, ""

    # 키 컬럼이 모두 존재하는지 확인
    missing = [c for c in key_columns if c not in df.columns]
    if missing:
        return False, ""

    mask = pd.Series([True] * len(df), index=df.index)
    for col in key_columns:
        val = str(new_record.get(col, "")).strip()
        if not val:
            return False, ""
        mask = mask & (df[col].astype(str).str.strip() == val)

    duplicates = df[mask]
    if not duplicates.empty:
        return True, f"중복 데이터가 {len(duplicates)}건 존재합니다 (기준: {', '.join(key_columns)})"

    return False, ""


def validate_business_number(biz_num: str) -> Tuple[bool, str]:
    """사업자등록번호 형식 검증 (10자리 숫자)

    Returns:
        (유효 여부, 정규화된 번호 또는 오류 메시지)
    """
    if not biz_num:
        return False, "사업자등록번호를 입력해주세요"

    digits = re.sub(r"[^0-9]", "", biz_num)
    if len(digits) != 10:
        return False, "사업자등록번호는 10자리 숫자여야 합니다"

    formatted = f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return True, formatted
