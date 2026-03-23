# gemini_client.py — Gemini AI 연동 모듈
"""
Gradius ERP AI 비서를 위한 Gemini API 클라이언트.
핵심 원칙:
  1. 숫자 계산은 pandas (ai_helper), Gemini는 자연어 설명만
  2. 민감정보(주민번호, 계좌, 연락처) 절대 외부 전송 안 함
  3. 기존 ai_helper 함수를 '도구'로 재활용
"""

import streamlit as st
import pandas as pd
import re
from datetime import datetime
from typing import Dict, List, Optional

import ai_helper as ai
import utils_dashboard as ud

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
# 3. 질문 분류 및 데이터 컨텍스트 빌드
# ==============================================================================

_QUESTION_CATEGORIES = {
    "매출": ["매출", "수익", "이익", "공급가", "청구", "정산", "수금", "금액", "돈", "입금",
            "얼마", "매출액", "수입", "실적"],
    "미수금": ["미수", "잔액", "미입금", "안 들어온", "안들어온", "독촉", "미지급", "안받은"],
    "인력": ["인력", "인원", "배정", "스태프", "직원", "부족", "필요",
            "직무", "역할", "직군", "직급", "나간", "나갔", "투입", "파견",
            "주차", "안내", "보안", "진행", "기술", "요원", "도우미",
            "몇 번", "몇번", "많이", "가장", "순위", "통계"],
    "고객": ["업체", "고객", "거래", "이탈", "재계약", "충성", "거래처", "회사"],
    "일정": ["일정", "현장", "행사", "D-day", "디데이", "이번 주", "다음 주", "임박",
            "이번주", "다음주", "예정", "스케줄", "언제"],
    "리스크": ["리스크", "위험", "경고", "주의", "긴급", "문제", "이슈"],
    "견적": ["견적", "단가", "추천가", "적정가", "가격", "비용"],
    "비교": ["비교", "대비", "추이", "변화", "증감", "지난달", "전월", "전년",
            "작년", "올해", "vs"],
}


def _classify_question(question: str) -> List[str]:
    """질문을 카테고리로 분류 (복수 가능)"""
    categories = []
    q = question.lower()
    for cat, keywords in _QUESTION_CATEGORIES.items():
        if any(kw in q for kw in keywords):
            categories.append(cat)
    return categories if categories else ["일반"]


def _build_data_context(categories: List[str], data: Dict,
                        df_dispatch: pd.DataFrame,
                        df_settlement: pd.DataFrame) -> str:
    """카테고리에 맞는 안전한 데이터 요약 생성 (Gemini에 전달할 부분)"""
    df_inq = data.get('inq', pd.DataFrame())
    df_estimate = data.get('estimate', pd.DataFrame())
    context_parts = []
    today = datetime.now().strftime('%Y-%m-%d')
    context_parts.append(f"[오늘 날짜: {today}]")

    # --- 기본 현황 (항상 포함) ---
    context_parts.append(f"[전체 문의 건수: {len(df_inq)}건]")
    if not df_inq.empty:
        status_col = None
        for col in ['상태', '체결']:
            if col in df_inq.columns:
                status_col = col
                break
        if status_col:
            counts = df_inq[status_col].astype(str).str.strip().value_counts().to_dict()
            context_parts.append(f"[상태별 건수: {counts}]")

    # --- 카테고리별 데이터 수집 ---
    if "매출" in categories or "비교" in categories:
        summary = ai.generate_executive_summary(df_inq, df_dispatch, df_settlement)
        context_parts.append(f"[경영 요약: {summary}]")
        predictions = ai.predict_monthly_revenue(df_settlement, months_ahead=3)
        if predictions:
            pred_text = ", ".join(f"{p['month']}: ₩{p['predicted']:,}({p['confidence']})" for p in predictions)
            context_parts.append(f"[매출 예측: {pred_text}]")

    if "미수금" in categories:
        if not df_settlement.empty:
            for col in ['잔액', '미수금액']:
                if col in df_settlement.columns:
                    unpaid = pd.to_numeric(df_settlement[col], errors='coerce').fillna(0)
                    unpaid_rows = df_settlement[unpaid > 0]
                    if not unpaid_rows.empty:
                        company_col = None
                        for c in ['업체', '업체명', '현장명']:
                            if c in unpaid_rows.columns:
                                company_col = c
                                break
                        if company_col:
                            details = []
                            for _, r in unpaid_rows.head(10).iterrows():
                                details.append(f"{r[company_col]}: ₩{int(unpaid[r.name]):,}")
                            context_parts.append(f"[미수금 목록: {'; '.join(details)}]")
                        context_parts.append(f"[총 미수금: ₩{int(unpaid.sum()):,}, {len(unpaid_rows)}건]")
                    break

    if "인력" in categories:
        demand = ai.predict_staff_demand(df_inq, weeks_ahead=4)
        if demand:
            demand_text = ", ".join(f"{d['week']}: {d['estimated_staff']}명({d['events']}건)" for d in demand)
            context_parts.append(f"[인력 수요 예측: {demand_text}]")
        context_parts.append(f"[배정 건수: {len(df_dispatch)}건]")

        # 직군별 배정 통계 (대시보드에서 쓰는 것과 동일)
        try:
            role_stats = ud.get_role_statistics(df_dispatch)
            if not role_stats.empty:
                role_lines = []
                for _, row in role_stats.iterrows():
                    line = f"{row['직군']}: {row['배정횟수']}회"
                    if '총지급액' in row.index and row['총지급액'] > 0:
                        line += f"(₩{int(row['총지급액']):,})"
                    role_lines.append(line)
                context_parts.append(f"[직군별 배정 통계(Top10): {', '.join(role_lines)}]")
        except Exception:
            pass

        # 현장별 배정 현황
        if not df_dispatch.empty:
            for ecol in ['행사명', '현장명']:
                if ecol in df_dispatch.columns:
                    event_counts = df_dispatch[ecol].astype(str).str.strip().value_counts().head(5)
                    if not event_counts.empty:
                        ev_text = ", ".join(f"{n}: {c}명" for n, c in event_counts.items())
                        context_parts.append(f"[현장별 배정 현황(Top5): {ev_text}]")
                    break

    if "고객" in categories:
        retention = ai.analyze_customer_retention(df_inq)
        if retention['total_customers'] > 0:
            context_parts.append(f"[고객 분석: 총 {retention['total_customers']}사, "
                                 f"재계약률 {retention['retention_rate']}%]")
            if retention['top_loyal']:
                loyal_text = ", ".join(f"{c['company']}({c['count']}회)" for c in retention['top_loyal'])
                context_parts.append(f"[충성 고객: {loyal_text}]")
            if retention['at_risk']:
                risk_text = ", ".join(f"{c['company']}({c['days_since']}일전)" for c in retention['at_risk'])
                context_parts.append(f"[이탈위험 고객: {risk_text}]")

    if "일정" in categories:
        demand = ai.predict_staff_demand(df_inq, weeks_ahead=2)
        if demand:
            for d in demand:
                context_parts.append(f"[{d['week']} 예정: {d['events']}건, 필요인력 {d['estimated_staff']}명]")

    if "리스크" in categories:
        risks = ai.analyze_risks(df_inq, df_dispatch, df_settlement)
        if risks:
            for r in risks:
                context_parts.append(f"[리스크({r['level']}): {r['type']} - {r['message']} → {r['action']}]")

    if "견적" in categories:
        price = ai.suggest_estimate_price(df_estimate, num_staff=5, num_days=1)
        if price['recommended_supply'] > 0:
            context_parts.append(f"[견적 참고: 5인1일 기준 추천 ₩{price['recommended_supply']:,}, "
                                 f"범위 ₩{price['min_price']:,}~₩{price['max_price']:,}, "
                                 f"마진 {price['avg_margin']}%]")

    if "일반" in categories:
        summary = ai.generate_executive_summary(df_inq, df_dispatch, df_settlement)
        context_parts.append(f"[경영 요약: {summary}]")
        risks = ai.analyze_risks(df_inq, df_dispatch, df_settlement)
        if risks:
            high = [r for r in risks if r['level'] == '높음']
            if high:
                context_parts.append(f"[긴급 리스크: {high[0]['type']} - {high[0]['message']}]")
        # 일반 질문에도 기본 직군 통계 포함
        try:
            role_stats = ud.get_role_statistics(df_dispatch)
            if not role_stats.empty:
                role_lines = [f"{row['직군']}: {row['배정횟수']}회" for _, row in role_stats.head(5).iterrows()]
                context_parts.append(f"[직군별 배정 통계(Top5): {', '.join(role_lines)}]")
        except Exception:
            pass

    return "\n".join(context_parts)


# ==============================================================================
# 4. 시스템 프롬프트
# ==============================================================================

_SYSTEM_PROMPT = """당신은 "Gradius ERP AI 비서"입니다.
인력파견 전문 회사 Gradius의 경영 데이터를 기반으로 질문에 답합니다.

핵심 규칙:
1. 제공된 [데이터]만 사용하여 답변하세요. 데이터에 없는 숫자를 만들어내지 마세요.
2. 금액은 항상 ₩와 천단위 쉼표를 사용하세요 (예: ₩15,000,000).
3. 답변은 간결하고 실무적으로 작성하세요.
4. 경영 판단에 도움이 되는 조언이나 액션 아이템을 포함하세요.
5. 확실하지 않은 내용은 "데이터 기준으로는 확인이 어렵습니다"라고 솔직히 말하세요.

비즈니스 컨텍스트:
- 업종: 인력파견 (행사/이벤트 스태프, 안내, 보안 등)
- 워크플로: 문의접수 → 견적 → 계약체결 → 인력배정 → 행사진행 → 정산
- 상태값: 접수, 견적, 체결, 배정완료, 진행중, 완료, 정산완료 / 미체결, 보류, 취소
"""

# ==============================================================================
# 5. 메인 질문 처리
# ==============================================================================

def ask(question: str, data: Dict, df_dispatch: pd.DataFrame,
        df_settlement: pd.DataFrame, model: str = None) -> str:
    """사용자 질문 → 데이터 분석 → Gemini 응답

    Args:
        question: 사용자 질문
        data: get_data() 반환 딕셔너리
        df_dispatch: 배정 DataFrame
        df_settlement: 정산 DataFrame
        model: 사용할 모델 (기본: gemini-2.5-flash)

    Returns:
        AI 응답 텍스트
    """
    client = _get_client()
    if not client:
        return "⚠️ Gemini API Key가 설정되지 않았습니다. 관리자에게 문의하세요."

    # 1) 질문 분류
    categories = _classify_question(question)

    # 2) 안전한 데이터 컨텍스트 빌드
    data_context = _build_data_context(categories, data, df_dispatch, df_settlement)

    # 3) 프롬프트 조합
    user_prompt = f"""아래는 현재 Gradius ERP 데이터 요약입니다:

{data_context}

사용자 질문: {question}

위 데이터를 기반으로 답변해주세요."""

    # 4) Gemini 호출
    use_model = model or _MODEL_DEFAULT
    try:
        response = client.models.generate_content(
            model=use_model,
            contents=user_prompt,
            config={
                "system_instruction": _SYSTEM_PROMPT,
                "temperature": 0.3,
                "max_output_tokens": 1024,
            }
        )
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            # lite 모델로 폴백
            if use_model != _MODEL_LITE:
                try:
                    response = client.models.generate_content(
                        model=_MODEL_LITE,
                        contents=user_prompt,
                        config={
                            "system_instruction": _SYSTEM_PROMPT,
                            "temperature": 0.3,
                            "max_output_tokens": 1024,
                        }
                    )
                    return response.text
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

    # 모든 카테고리 데이터 수집
    all_categories = ["매출", "미수금", "인력", "리스크", "일정"]
    data_context = _build_data_context(all_categories, data, df_dispatch, df_settlement)

    prompt = f"""아래는 오늘의 Gradius ERP 데이터 요약입니다:

{data_context}

위 데이터를 기반으로 대표님께 보고하는 '오늘의 경영 브리핑'을 작성해주세요.
포맷:
1. 핵심 요약 (2~3문장)
2. 주요 지표 (금액, 건수 중심)
3. 주의 필요 사항
4. 오늘의 추천 액션 (구체적으로 2~3개)

친근하지만 전문적인 톤으로, 한국어로 작성하세요."""

    try:
        response = client.models.generate_content(
            model=_MODEL_DEFAULT,
            contents=prompt,
            config={
                "system_instruction": _SYSTEM_PROMPT,
                "temperature": 0.4,
                "max_output_tokens": 1500,
            }
        )
        return response.text
    except Exception:
        try:
            response = client.models.generate_content(
                model=_MODEL_LITE,
                contents=prompt,
                config={
                    "system_instruction": _SYSTEM_PROMPT,
                    "temperature": 0.4,
                    "max_output_tokens": 1500,
                }
            )
            return response.text
        except Exception:
            return None
