# gemini_client.py — Gemini AI 연동 모듈
"""
Gradius ERP AI 비서를 위한 Gemini API 클라이언트.
핵심 원칙:
  1. 실제 데이터 테이블을 Gemini에 직접 전달 → 어떤 질문이든 답변 가능
  2. 민감정보(주민번호, 계좌, 연락처) 자동 제거 후 전달
  3. Gemini 100만 토큰 컨텍스트 활용 — 전체 ERP 데이터가 ~1% 미만
"""

import streamlit as st
import pandas as pd
import re
from datetime import datetime
from typing import Dict, List, Optional

import ai_helper as ai
import utils_dashboard as ud


def _safe_response_text(response) -> str:
    """Gemini 응답에서 텍스트를 안전하게 추출 (불완전 응답도 처리)"""
    # 1) .text 속성이 정상 작동하면 바로 반환
    try:
        text = response.text
        if text:
            return text
    except Exception:
        pass

    # 2) candidates에서 직접 추출 (finish_reason이 STOP이 아닌 경우)
    try:
        for candidate in response.candidates:
            parts_text = []
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    parts_text.append(part.text)
            if parts_text:
                return "\n".join(parts_text)
    except Exception:
        pass

    return "⚠️ AI 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요."

# ==============================================================================
# 1. 민감정보 마스킹
# ==============================================================================

_SENSITIVE_COLUMNS = {
    '주민등록번호', '주민번호', '계좌번호', '연락처', '전화번호', '휴대폰',
    '이메일', '사업자등록증URL', '사업자등록증', '비밀번호', '암호',
    '은행명', '계좌', '주소',
}

def _sanitize_value(val: str) -> str:
    """주민번호/전화번호/계좌번호 패턴 마스킹"""
    s = str(val)
    # 주민번호 패턴 (000000-0000000)
    s = re.sub(r'\d{6}-\d{7}', '******-*******', s)
    # 전화번호 패턴
    s = re.sub(r'01[016789]-?\d{3,4}-?\d{4}', '010-****-****', s)
    # 계좌번호 (10~16자리 연속 숫자)
    s = re.sub(r'\d{10,16}', '**********', s)
    return s


def _sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """민감 컬럼 제거 + 값 마스킹"""
    if df.empty:
        return df
    safe_df = df.copy()
    for col in safe_df.columns:
        if col in _SENSITIVE_COLUMNS:
            safe_df = safe_df.drop(columns=[col])
        else:
            safe_df[col] = safe_df[col].astype(str).apply(_sanitize_value)
    return safe_df

# ==============================================================================
# 2. Gemini 클라이언트
# ==============================================================================

_MODEL_DEFAULT = "gemini-2.5-flash"
_MODEL_LITE = "gemini-2.5-flash-lite"


def _get_api_key() -> Optional[str]:
    """secrets.toml 또는 st.secrets에서 API key 로드"""
    try:
        # 최상위 레벨
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    try:
        # [gcp_service_account] 섹션 아래에 넣은 경우
        if hasattr(st.secrets, 'gcp_service_account'):
            sa = st.secrets["gcp_service_account"]
            if "GEMINI_API_KEY" in sa:
                return sa["GEMINI_API_KEY"]
    except Exception:
        pass
    return None


def _get_client():
    """google.genai Client 싱글턴"""
    if '_gemini_client' not in st.session_state:
        api_key = _get_api_key()
        if not api_key:
            return None
        from google import genai
        st.session_state['_gemini_client'] = genai.Client(api_key=api_key)
    return st.session_state['_gemini_client']


def is_available() -> bool:
    """Gemini 사용 가능 여부"""
    return _get_api_key() is not None


# ==============================================================================
# 3. 전체 데이터 컨텍스트 빌드 (모든 ERP 데이터를 안전하게 전달)
# ==============================================================================

# 각 시트에서 Gemini에 보낼 컬럼 (민감정보 제외)
_SAFE_COLUMNS = {
    'inq': ['문의ID', '업체명', '행사명', '행사시작일', '행사종료일', '상태', '체결',
            '필요인력', '장소', '현장주소', '특이사항', '작성일', '담당자',
            '행사유형', '복장', '식사', '주차'],
    'settlement': ['문의ID', '현장명', '업체', '파견일자', '책임자', '현장주소',
                   '청구금액', '공급가액', '부가세', '받은금액', '잔액',
                   '진행상황', '입금여부', '세금계산서 발행여부',
                   '지급액', '이익', '법인명', '내용(품목)'],
    'dispatch': ['배정ID', '문의ID', '행사명', '인력명', '직무', '지급단가',
                 '근무일수', '총지급액', '지급상태', '구분', '파견일자',
                 '팀코드', '결제대상'],
    'estimate': ['문의ID', '업체명', '행사명', '공급가액', '부가세', '합계금액',
                 '매입원가', '예상수익', '필요인력', '상태'],
    'staff': ['이름', '직무', '경력', '평점', '가용상태', '선호지역', '메모'],
    'payment': ['문의ID', '인력명', '직무', '지급액', '지급상태', '지급일'],
}


def _df_to_safe_text(df: pd.DataFrame, sheet_name: str, max_rows: int = 200) -> str:
    """DataFrame을 민감정보 제거 후 텍스트 테이블로 변환"""
    if df.empty:
        return f"[{sheet_name}] 데이터 없음 (0건)"

    # 허용된 컬럼만 선택 (있는 것만)
    safe_cols = _SAFE_COLUMNS.get(sheet_name, [])
    if safe_cols:
        available = [c for c in safe_cols if c in df.columns]
        if not available:
            # 허용 목록에 없으면 민감 컬럼 제외하고 전부
            available = [c for c in df.columns if c not in _SENSITIVE_COLUMNS]
        safe_df = df[available].head(max_rows)
    else:
        safe_df = _sanitize_dataframe(df).head(max_rows)

    # 값 마스킹 (원본 보호를 위해 copy)
    safe_df = safe_df.copy()
    for col in safe_df.columns:
        safe_df[col] = safe_df[col].astype(str).apply(_sanitize_value)

    # 마크다운 테이블로 변환
    total = len(df)
    header = f"[{sheet_name}] 총 {total}건" + (f" (상위 {max_rows}건 표시)" if total > max_rows else "")
    table = safe_df.to_csv(index=False, sep='|')

    return f"{header}\n{table}"


def _build_full_context(data: Dict, df_dispatch: pd.DataFrame,
                        df_settlement: pd.DataFrame) -> str:
    """모든 ERP 데이터를 안전하게 텍스트로 변환"""
    parts = []
    today = datetime.now().strftime('%Y-%m-%d (%A)')
    parts.append(f"=== Gradius ERP 전체 데이터 ({today}) ===\n")

    # 1) 문의 데이터
    df_inq = data.get('inq', pd.DataFrame())
    parts.append(_df_to_safe_text(df_inq, 'inq'))

    # 2) 정산 데이터
    parts.append(_df_to_safe_text(df_settlement, 'settlement'))

    # 3) 배정 데이터
    parts.append(_df_to_safe_text(df_dispatch, 'dispatch'))

    # 4) 견적 데이터
    df_estimate = data.get('estimate', pd.DataFrame())
    parts.append(_df_to_safe_text(df_estimate, 'estimate'))

    # 5) 인력 데이터
    df_staff = data.get('staff', pd.DataFrame())
    parts.append(_df_to_safe_text(df_staff, 'staff'))

    # 6) 지급 데이터
    df_payment = data.get('payment', pd.DataFrame())
    if not df_payment.empty:
        parts.append(_df_to_safe_text(df_payment, 'payment'))

    # 7) AI 분석 결과 보강 (숫자 정확도 위해)
    supplements = []
    try:
        role_stats = ud.get_role_statistics(df_dispatch)
        if not role_stats.empty:
            lines = [f"{r['직군']}: {r['배정횟수']}회" +
                     (f"(₩{int(r['총지급액']):,})" if '총지급액' in r.index and r['총지급액'] > 0 else "")
                     for _, r in role_stats.iterrows()]
            supplements.append(f"[직군별 배정 통계 TOP10] {', '.join(lines)}")
    except Exception:
        pass

    try:
        risks = ai.analyze_risks(df_inq, df_dispatch, df_settlement)
        if risks:
            for r in risks:
                supplements.append(f"[리스크-{r['level']}] {r['type']}: {r['message']} → {r['action']}")
    except Exception:
        pass

    try:
        retention = ai.analyze_customer_retention(df_inq)
        if retention.get('total_customers', 0) > 0:
            supplements.append(f"[고객분석] 총 {retention['total_customers']}사, "
                               f"재계약률 {retention['retention_rate']}%")
    except Exception:
        pass

    if supplements:
        parts.append("\n=== AI 분석 보강 ===")
        parts.extend(supplements)

    return "\n\n".join(parts)


# ==============================================================================
# 4. 시스템 프롬프트
# ==============================================================================

_SYSTEM_PROMPT = """당신은 "Gradius ERP AI 비서"입니다.
인력파견 전문 회사 Gradius의 **전체 경영 데이터**를 제공받고 있습니다.

핵심 규칙:
1. 제공된 데이터 테이블에서 직접 수치를 읽어 답변하세요. 데이터에 없는 숫자를 만들어내지 마세요.
2. 금액은 항상 ₩와 천단위 쉼표를 사용하세요 (예: ₩15,000,000).
3. 답변은 간결하고 실무적으로 작성하세요.
4. 경영 판단에 도움이 되는 조언이나 액션 아이템을 포함하세요.
5. 확실하지 않으면 "데이터 기준으로는 확인이 어렵습니다"라고 솔직히 말하세요.
6. 데이터를 나열할 때는 표(마크다운 테이블) 형태로 정리하세요.
7. 여러 테이블을 조합해서 분석할 수 있습니다 (문의ID 등으로 연결).

비즈니스 컨텍스트:
- 업종: 인력파견 (행사/이벤트 스태프, 안내, 보안, 주차 등)
- 워크플로: 문의접수 → 견적 → 계약체결 → 인력배정 → 행사진행 → 정산
- 상태값: 접수, 견적, 체결, 배정완료, 진행중, 완료, 정산완료 / 미체결, 보류, 취소
- 정산 시트의 '잔액'이 양수이면 미수금(아직 안 받은 금액)

제공되는 데이터:
- inq: 문의/계약 전체 목록
- settlement: 정산 데이터 (매출, 입금, 미수금)
- dispatch: 인력 배정 상세 (누가 어디로 갔는지)
- estimate: 견적 데이터
- staff: 인력 풀
- payment: 지급 내역
- AI 분석 보강: 직군별 통계, 리스크, 고객 분석
"""

# ==============================================================================
# 5. 메인 질문 처리
# ==============================================================================

def ask(question: str, data: Dict, df_dispatch: pd.DataFrame,
        df_settlement: pd.DataFrame, model: str = None) -> str:
    """사용자 질문 → 전체 데이터 컨텍스트 → Gemini 응답"""
    client = _get_client()
    if not client:
        return "⚠️ Gemini API Key가 설정되지 않았습니다. 관리자에게 문의하세요."

    # 전체 데이터를 텍스트로 변환 (키워드 분류 없이 모든 데이터 전달)
    data_context = _build_full_context(data, df_dispatch, df_settlement)

    user_prompt = f"""아래는 현재 Gradius ERP 전체 데이터입니다:

{data_context}

사용자 질문: {question}

위 데이터를 분석하여 정확하게 답변해주세요. 수치는 데이터에서 직접 계산하세요."""

    use_model = model or _MODEL_DEFAULT
    try:
        response = client.models.generate_content(
            model=use_model,
            contents=user_prompt,
            config={
                "system_instruction": _SYSTEM_PROMPT,
                "temperature": 0.3,
                "max_output_tokens": 8192,
            }
        )
        return _safe_response_text(response)
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            if use_model != _MODEL_LITE:
                try:
                    response = client.models.generate_content(
                        model=_MODEL_LITE,
                        contents=user_prompt,
                        config={
                            "system_instruction": _SYSTEM_PROMPT,
                            "temperature": 0.3,
                            "max_output_tokens": 8192,
                        }
                    )
                    return _safe_response_text(response)
                except Exception:
                    pass
            return "⚠️ API 호출 한도에 도달했습니다. 잠시 후 다시 시도해주세요."
        return f"⚠️ AI 응답 생성 중 오류: {error_msg}"


def generate_briefing(data: Dict, df_dispatch: pd.DataFrame,
                      df_settlement: pd.DataFrame) -> str:
    """오늘의 경영 브리핑 생성"""
    client = _get_client()
    if not client:
        return None

    data_context = _build_full_context(data, df_dispatch, df_settlement)

    prompt = f"""아래는 오늘의 Gradius ERP 전체 데이터입니다:

{data_context}

위 데이터를 기반으로 대표님께 보고하는 '오늘의 경영 브리핑'을 작성해주세요.
포맷:
1. 핵심 요약 (2~3문장)
2. 주요 지표 (금액, 건수 중심)
3. 주의 필요 사항 (미수금, 리스크 등)
4. 오늘의 추천 액션 (구체적으로 2~3개)

친근하지만 전문적인 톤으로, 한국어로 작성하세요."""

    try:
        response = client.models.generate_content(
            model=_MODEL_DEFAULT,
            contents=prompt,
            config={
                "system_instruction": _SYSTEM_PROMPT,
                "temperature": 0.4,
                "max_output_tokens": 8192,
            }
        )
        return _safe_response_text(response)
    except Exception:
        try:
            response = client.models.generate_content(
                model=_MODEL_LITE,
                contents=prompt,
                config={
                    "system_instruction": _SYSTEM_PROMPT,
                    "temperature": 0.4,
                    "max_output_tokens": 8192,
                }
            )
            return _safe_response_text(response)
        except Exception:
            return None
