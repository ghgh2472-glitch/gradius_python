# page_ai_assistant.py — 🤖 AI 비서 에이전트 페이지
"""
Gradius ERP AI 비서 페이지:
  Tab 1: 💬 AI 채팅 — 자연어로 경영 데이터 질문
  Tab 2: 📋 오늘의 브리핑 — AI 경영 브리핑 + 인사이트 카드
  Tab 3: 📈 기간 리포트 — 연도/월별 매출 집계 + 차트
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO

import data_loader as db
import ai_helper as ai
import gemini_client as gc


# ==============================================================================
# 스타일
# ==============================================================================

def _apply_styles():
    st.markdown("""<style>
    /* AI 비서 전용 스타일 */
    .ai-chat-msg {
        padding: 12px 16px;
        border-radius: 12px;
        margin-bottom: 10px;
        font-size: 14px;
        line-height: 1.7;
    }
    .ai-chat-user {
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        color: #1E3A8A;
        margin-left: 40px;
    }
    .ai-chat-bot {
        background: #F0FDF4;
        border: 1px solid #86EFAC;
        color: #166534;
        margin-right: 40px;
    }
    .ai-briefing-card {
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .ai-kpi-card {
        border-radius: 12px;
        padding: 18px;
        text-align: center;
        color: white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    }
    .ai-kpi-label { font-size: 12px; font-weight: 600; opacity: 0.9; margin-bottom: 4px; }
    .ai-kpi-value { font-size: 28px; font-weight: 800; margin: 6px 0; }
    .ai-kpi-sub { font-size: 12px; opacity: 0.8; }
    .quick-btn button {
        border-radius: 20px !important;
        font-size: 13px !important;
        padding: 4px 16px !important;
    }
    .risk-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 700;
        color: white;
    }
    </style>""", unsafe_allow_html=True)


# ==============================================================================
# 메인
# ==============================================================================

def show(data):
    _apply_styles()

    st.title("🤖 AI 비서")
    st.caption("Gemini 기반 경영 데이터 분석 · 자연어 질문 · 인사이트 리포트")

    # 데이터 준비
    df_inq = data.get('inq', pd.DataFrame())
    df_estimate = data.get('estimate', pd.DataFrame())
    try:
        dispatch_data = db.get_dispatch()
        df_dispatch = dispatch_data.get('dispatch', pd.DataFrame())
        df_settlement = dispatch_data.get('settlement', pd.DataFrame())
        df_payment = dispatch_data.get('payment', pd.DataFrame())
    except Exception:
        df_dispatch = pd.DataFrame()
        df_settlement = pd.DataFrame()
        df_payment = pd.DataFrame()

    # Gemini 가용성 체크
    gemini_ok = gc.is_available()
    if not gemini_ok:
        st.warning("⚠️ Gemini API Key가 설정되지 않았습니다. 채팅 기능은 제한됩니다.")

    # 탭
    tab_chat, tab_briefing, tab_report = st.tabs([
        "💬 AI 채팅", "📋 오늘의 브리핑", "📈 기간 리포트"
    ])

    with tab_chat:
        _render_chat_tab(data, df_dispatch, df_settlement, gemini_ok)

    with tab_briefing:
        _render_briefing_tab(data, df_inq, df_dispatch, df_settlement, gemini_ok)

    with tab_report:
        _render_report_tab(df_inq, df_settlement, df_dispatch, df_payment)


# ==============================================================================
# Tab 1: AI 채팅
# ==============================================================================

_QUICK_QUESTIONS = [
    "이번 달 매출 현황 알려줘",
    "미수금 많은 업체 알려줘",
    "다음 주 인력 현황은?",
    "리스크 요약해줘",
    "고객 재계약률 분석해줘",
    "이번 달 vs 지난 달 비교",
]


def _render_chat_tab(data, df_dispatch, df_settlement, gemini_ok):
    st.markdown("##### 💬 무엇이든 물어보세요")
    st.caption("ERP 데이터를 기반으로 AI가 답변합니다. 숫자는 실제 데이터에서 계산됩니다.")

    # 빠른 질문 버튼
    st.markdown("###### 자주 묻는 질문")
    qcols = st.columns(3)
    for i, q in enumerate(_QUICK_QUESTIONS):
        with qcols[i % 3]:
            if st.button(q, key=f"quick_{i}", use_container_width=True):
                st.session_state['_ai_pending_question'] = q

    st.markdown("---")

    # 채팅 히스토리 초기화
    if '_ai_chat_history' not in st.session_state:
        st.session_state['_ai_chat_history'] = []

    # 히스토리 표시
    for msg in st.session_state['_ai_chat_history']:
        if msg['role'] == 'user':
            with st.chat_message("user"):
                st.markdown(msg['content'])
        else:
            with st.chat_message("assistant"):
                st.markdown(msg['content'])

    # 입력
    col_input, col_clear = st.columns([5, 1])
    with col_input:
        user_input = st.chat_input("질문을 입력하세요...", key="ai_chat_input")
    with col_clear:
        if st.button("🗑️ 초기화", key="clear_chat"):
            st.session_state['_ai_chat_history'] = []
            st.rerun()

    # 빠른 질문 또는 직접 입력 처리
    pending = st.session_state.pop('_ai_pending_question', None)
    question = pending or user_input

    if question:
        # 히스토리에 사용자 질문 추가
        st.session_state['_ai_chat_history'].append({"role": "user", "content": question})

        if gemini_ok:
            with st.spinner("🤖 분석 중..."):
                answer = gc.ask(question, data, df_dispatch, df_settlement)
        else:
            answer = _fallback_answer(question, data, df_dispatch, df_settlement)

        st.session_state['_ai_chat_history'].append({"role": "assistant", "content": answer})
        st.rerun()


def _fallback_answer(question: str, data, df_dispatch, df_settlement):
    """Gemini가 없을 때 규칙 기반 답변"""
    df_inq = data.get('inq', pd.DataFrame())
    summary = ai.generate_executive_summary(df_inq, df_dispatch, df_settlement)
    risks = ai.analyze_risks(df_inq, df_dispatch, df_settlement)

    parts = [f"📊 **경영 요약**: {summary}"]
    if risks:
        parts.append("🚨 **리스크**:")
        for r in risks[:3]:
            parts.append(f"  - [{r['level']}] {r['type']}: {r['message']}")

    parts.append("\n💡 *Gemini AI가 연결되면 더 상세한 분석이 가능합니다.*")
    return "\n".join(parts)


# ==============================================================================
# Tab 2: 오늘의 브리핑
# ==============================================================================

def _render_briefing_tab(data, df_inq, df_dispatch, df_settlement, gemini_ok):
    st.markdown("##### 📋 오늘의 경영 브리핑")

    # KPI 카드 영역
    _render_kpi_cards(df_inq, df_settlement, df_dispatch)

    st.markdown("---")

    # 리스크 알림
    _render_risk_alerts(df_inq, df_dispatch, df_settlement)

    st.markdown("---")

    # AI 브리핑
    st.markdown("###### 🤖 AI 분석 브리핑")
    if gemini_ok:
        # 캐시: 같은 세션에서 5분 내 재사용
        cache_key = '_ai_briefing_cache'
        cache_time_key = '_ai_briefing_time'
        cached = st.session_state.get(cache_key)
        cached_time = st.session_state.get(cache_time_key)

        need_refresh = (
            cached is None or
            cached_time is None or
            (datetime.now() - cached_time).total_seconds() > 300
        )

        col_b1, col_b2 = st.columns([4, 1])
        with col_b2:
            if st.button("🔄 새로고침", key="refresh_briefing"):
                need_refresh = True

        if need_refresh:
            with st.spinner("🤖 AI 브리핑 생성 중..."):
                briefing = gc.generate_briefing(data, df_dispatch, df_settlement)
                if briefing:
                    st.session_state[cache_key] = briefing
                    st.session_state[cache_time_key] = datetime.now()
                else:
                    briefing = "브리핑 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
                    st.session_state[cache_key] = briefing
        else:
            briefing = cached

        st.markdown(briefing)
    else:
        # Gemini 없으면 규칙 기반 요약
        summary = ai.generate_executive_summary(df_inq, df_dispatch, df_settlement)
        st.markdown(f"**📊 경영 현황 요약**\n\n{summary}")


def _render_kpi_cards(df_inq, df_settlement, df_dispatch):
    """핵심 KPI 카드 4개"""
    # 총 청구액
    total_supply = 0
    if not df_settlement.empty:
        for col in ['공급가액', '합계금액', '청구금액']:
            if col in df_settlement.columns:
                total_supply = pd.to_numeric(df_settlement[col], errors='coerce').fillna(0).sum()
                break

    # 수금액
    total_paid = 0
    if not df_settlement.empty and '받은금액' in df_settlement.columns:
        total_paid = pd.to_numeric(df_settlement['받은금액'], errors='coerce').fillna(0).sum()

    # 미수금
    total_unpaid = 0
    if not df_settlement.empty:
        for col in ['잔액', '미수금액']:
            if col in df_settlement.columns:
                total_unpaid = pd.to_numeric(df_settlement[col], errors='coerce').fillna(0).sum()
                break

    # 체결률
    conv_rate = 0
    total_inq = len(df_inq)
    if total_inq > 0:
        status_col = None
        for col in ['상태', '체결']:
            if col in df_inq.columns:
                status_col = col
                break
        if status_col:
            confirmed = df_inq[status_col].astype(str).str.strip().isin(
                ['체결', '배정완료', '진행중', '완료', '정산완료']).sum()
            conv_rate = confirmed / total_inq * 100

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="ai-kpi-card" style="background:linear-gradient(135deg,#667eea,#764ba2);">
            <div class="ai-kpi-label">💰 총 청구액</div>
            <div class="ai-kpi-value">₩{int(total_supply):,}</div>
            <div class="ai-kpi-sub">공급가액 기준</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="ai-kpi-card" style="background:linear-gradient(135deg,#30cfd0,#330867);">
            <div class="ai-kpi-label">✅ 수금액</div>
            <div class="ai-kpi-value">₩{int(total_paid):,}</div>
            <div class="ai-kpi-sub">입금 확인분</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="ai-kpi-card" style="background:linear-gradient(135deg,#fa709a,#fee140);">
            <div class="ai-kpi-label">💸 미수금</div>
            <div class="ai-kpi-value">₩{int(total_unpaid):,}</div>
            <div class="ai-kpi-sub">{int(total_unpaid > 0) and '확인 필요' or '없음'}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="ai-kpi-card" style="background:linear-gradient(135deg,#f093fb,#f5576c);">
            <div class="ai-kpi-label">📈 체결률</div>
            <div class="ai-kpi-value">{conv_rate:.0f}%</div>
            <div class="ai-kpi-sub">전체 {total_inq}건 중</div>
        </div>""", unsafe_allow_html=True)


def _render_risk_alerts(df_inq, df_dispatch, df_settlement):
    """리스크 알림 카드"""
    risks = ai.analyze_risks(df_inq, df_dispatch, df_settlement)
    if not risks:
        st.success("✅ 현재 긴급 리스크가 없습니다.")
        return

    st.markdown(f"###### 🚨 리스크 현황 ({len(risks)}건)")
    for risk in risks:
        level_color = "#DC2626" if risk['level'] == "높음" else "#F59E0B" if risk['level'] == "보통" else "#10B981"
        st.markdown(f"""<div style="background:#FFF;border:1px solid #E5E7EB;border-left:4px solid {level_color};
            border-radius:8px;padding:12px;margin-bottom:8px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span style="font-weight:700;">{risk['type']}</span>
                <span class="risk-badge" style="background:{level_color};">{risk['level']}</span>
            </div>
            <div style="font-size:13px;color:#374151;">{risk['message']}</div>
            <div style="font-size:12px;color:#6B7280;margin-top:4px;">💡 {risk['action']}</div>
        </div>""", unsafe_allow_html=True)


# ==============================================================================
# Tab 3: 기간 리포트
# ==============================================================================

def _render_report_tab(df_inq, df_settlement, df_dispatch, df_payment):
    st.markdown("##### 📈 기간별 리포트")

    # 필터 영역
    fc1, fc2, fc3 = st.columns(3)
    current_year = datetime.now().year
    with fc1:
        year = st.selectbox("연도", range(current_year, current_year - 5, -1),
                            key="report_year")
    with fc2:
        period = st.selectbox("집계 단위", ["월별", "분기별", "연간"],
                              key="report_period")
    with fc3:
        target = st.selectbox("데이터", ["매출(정산)", "문의 건수", "배정 인원"],
                              key="report_target")

    st.markdown("---")

    # 데이터에 따라 분석
    if target == "매출(정산)":
        _report_revenue(df_settlement, year, period)
    elif target == "문의 건수":
        _report_inquiries(df_inq, year, period)
    else:
        _report_dispatch(df_dispatch, year, period)


def _find_date_col(df, candidates=None):
    """날짜 컬럼 찾기"""
    if candidates is None:
        candidates = ['파견일자', '행사시작일', '계약일', '작성일', '등록일', '일시', '날짜']
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _prepare_time_series(df, date_col, value_col, year, period):
    """시계열 데이터 집계"""
    tmp = df.copy()
    tmp['_date'] = pd.to_datetime(tmp[date_col], errors='coerce')
    tmp = tmp.dropna(subset=['_date'])
    tmp = tmp[tmp['_date'].dt.year == year]

    if tmp.empty:
        return pd.DataFrame()

    if value_col:
        tmp['_val'] = pd.to_numeric(tmp[value_col], errors='coerce').fillna(0)
    else:
        tmp['_val'] = 1  # 건수 카운트

    if period == "월별":
        tmp['_period'] = tmp['_date'].dt.month.apply(lambda m: f"{m}월")
        order = [f"{m}월" for m in range(1, 13)]
    elif period == "분기별":
        tmp['_period'] = tmp['_date'].dt.quarter.apply(lambda q: f"Q{q}")
        order = ["Q1", "Q2", "Q3", "Q4"]
    else:
        tmp['_period'] = f"{year}년"
        order = [f"{year}년"]

    result = tmp.groupby('_period')['_val'].sum().reset_index()
    result.columns = ['기간', '값']
    # 정렬
    result['_sort'] = result['기간'].apply(lambda x: order.index(x) if x in order else 99)
    result = result.sort_values('_sort').drop(columns=['_sort'])
    return result


def _render_chart_and_table(agg_df, value_label, year, period, is_currency=True):
    """차트 + 테이블 + 다운로드 공통 렌더"""
    if agg_df.empty:
        st.info(f"📭 {year}년 데이터가 없습니다.")
        return

    import plotly.express as px

    # 차트
    fig = px.bar(
        agg_df, x='기간', y='값',
        text='값',
        color_discrete_sequence=['#667EEA'],
    )
    if is_currency:
        fig.update_traces(texttemplate='₩%{text:,.0f}', textposition='outside')
    else:
        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig.update_layout(
        title=f"{year}년 {period} {value_label}",
        xaxis_title="",
        yaxis_title=value_label,
        yaxis_tickformat=',.0f',
        height=400,
        margin=dict(t=50, b=30),
        plot_bgcolor='rgba(0,0,0,0)',
    )
    st.plotly_chart(fig, use_container_width=True)

    # 요약
    total = agg_df['값'].sum()
    avg = agg_df['값'].mean()
    max_row = agg_df.loc[agg_df['값'].idxmax()]

    sc1, sc2, sc3 = st.columns(3)
    if is_currency:
        sc1.metric(f"합계", f"₩{int(total):,}")
        sc2.metric(f"평균", f"₩{int(avg):,}")
        sc3.metric(f"최고 ({max_row['기간']})", f"₩{int(max_row['값']):,}")
    else:
        sc1.metric(f"합계", f"{int(total):,}")
        sc2.metric(f"평균", f"{int(avg):,}")
        sc3.metric(f"최고 ({max_row['기간']})", f"{int(max_row['값']):,}")

    # 테이블
    with st.expander("📊 상세 데이터 보기"):
        display_df = agg_df.copy()
        if is_currency:
            display_df['값'] = display_df['값'].apply(lambda v: f"₩{int(v):,}")
        display_df.columns = ['기간', value_label]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Excel 다운로드
    _render_excel_download(agg_df, value_label, year, period)


def _render_excel_download(agg_df, value_label, year, period):
    """Excel 다운로드 버튼"""
    try:
        buf = BytesIO()
        export_df = agg_df.copy()
        export_df.columns = ['기간', value_label]
        export_df.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        st.download_button(
            label="📥 Excel 다운로드",
            data=buf,
            file_name=f"gradius_{year}_{period}_{value_label}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_{year}_{period}_{value_label}"
        )
    except Exception:
        pass


def _report_revenue(df_settlement, year, period):
    """매출 리포트"""
    if df_settlement.empty:
        st.info("📭 정산 데이터가 없습니다.")
        return

    date_col = _find_date_col(df_settlement, ['파견일자', '계약일', '작성일', '등록일'])
    if not date_col:
        st.warning("날짜 컬럼을 찾을 수 없습니다.")
        return

    value_col = None
    for col in ['공급가액', '합계금액', '청구금액']:
        if col in df_settlement.columns:
            value_col = col
            break
    if not value_col:
        st.warning("금액 컬럼을 찾을 수 없습니다.")
        return

    agg = _prepare_time_series(df_settlement, date_col, value_col, year, period)
    _render_chart_and_table(agg, "매출액", year, period, is_currency=True)


def _report_inquiries(df_inq, year, period):
    """문의 건수 리포트"""
    if df_inq.empty:
        st.info("📭 문의 데이터가 없습니다.")
        return

    date_col = _find_date_col(df_inq, ['작성일', '문의날짜', '등록일', '행사시작일'])
    if not date_col:
        st.warning("날짜 컬럼을 찾을 수 없습니다.")
        return

    agg = _prepare_time_series(df_inq, date_col, None, year, period)
    _render_chart_and_table(agg, "문의 건수", year, period, is_currency=False)


def _report_dispatch(df_dispatch, year, period):
    """배정 인원 리포트"""
    if df_dispatch.empty:
        st.info("📭 배정 데이터가 없습니다.")
        return

    date_col = _find_date_col(df_dispatch, ['파견일자', '배정일', '날짜', '행사시작일'])
    if not date_col:
        st.warning("날짜 컬럼을 찾을 수 없습니다.")
        return

    agg = _prepare_time_series(df_dispatch, date_col, None, year, period)
    _render_chart_and_table(agg, "배정 인원", year, period, is_currency=False)
