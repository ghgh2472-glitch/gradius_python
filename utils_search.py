"""utils_search.py
통합 검색/필터 유틸리티

여러 페이지에서 공통으로 사용하는 검색·필터 헬퍼 함수 모음.
"""
from datetime import datetime
from typing import List, Optional

import pandas as pd
from helpers import get_logger

logger = get_logger(__name__)


def search_dataframe(
    df: pd.DataFrame,
    keyword: str,
    columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """DataFrame 전체(또는 지정 컬럼)에서 키워드를 검색한다.

    Args:
        df: 대상 데이터프레임
        keyword: 검색어
        columns: 검색 대상 컬럼 (None이면 전체 컬럼)

    Returns:
        매칭된 행으로 구성된 DataFrame
    """
    if df.empty or not keyword:
        return df

    keyword = keyword.strip()
    if not keyword:
        return df

    target_cols = columns if columns else df.columns.tolist()
    target_cols = [c for c in target_cols if c in df.columns]

    if not target_cols:
        return df

    mask = pd.Series([False] * len(df), index=df.index)
    for col in target_cols:
        mask = mask | df[col].astype(str).str.contains(keyword, case=False, na=False)

    result = df[mask]
    logger.info(f"Search '{keyword}': {len(result)}/{len(df)} matches")
    return result


def filter_by_status(
    df: pd.DataFrame,
    status: str,
    status_column: str = "상태",
) -> pd.DataFrame:
    """상태 값으로 DataFrame을 필터링한다.

    Args:
        df: 대상 데이터프레임
        status: 필터링할 상태 값 (빈 문자열이면 전체)
        status_column: 상태 컬럼 이름

    Returns:
        필터링된 DataFrame
    """
    if df.empty or not status or status == "전체":
        return df

    if status_column not in df.columns:
        return df

    return df[df[status_column].astype(str).str.strip() == status]


def filter_by_date_range(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    date_column: str = "날짜",
) -> pd.DataFrame:
    """날짜 범위로 DataFrame을 필터링한다.

    Args:
        df: 대상 데이터프레임
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (YYYY-MM-DD)
        date_column: 날짜 컬럼 이름

    Returns:
        필터링된 DataFrame
    """
    if df.empty:
        return df

    if date_column not in df.columns:
        return df

    dates = df[date_column].astype(str).str[:10]  # YYYY-MM-DD 부분만
    mask = pd.Series([True] * len(df), index=df.index)

    if start_date:
        mask = mask & (dates >= start_date)
    if end_date:
        mask = mask & (dates <= end_date)

    return df[mask]


def get_unique_values(
    df: pd.DataFrame,
    column: str,
    include_all: bool = True,
) -> List[str]:
    """컬럼의 고유 값 목록을 반환한다 (필터 드롭다운용).

    Args:
        df: 데이터프레임
        column: 컬럼 이름
        include_all: True이면 맨 앞에 '전체' 옵션 추가

    Returns:
        고유 값 리스트
    """
    if df.empty or column not in df.columns:
        return ["전체"] if include_all else []

    values = (
        df[column]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    values.sort()

    if include_all:
        values.insert(0, "전체")

    return values
