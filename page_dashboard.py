# page_dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import utils_dashboard as ud
import data_loader as db
from streamlit_calendar import calendar
from datetime import datetime, timedelta
from helpers import now_kst, today_kst
import status_config as sc

# ==============================================================================
# 1. 스타일링
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px; padding: 20px; text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15); color: white;
        }
        .metric-card.sales { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .metric-card.profit { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .metric-card.unpaid { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
        .metric-card.payment-rate { background: linear-gradient(135deg, #30cfd0 0%, #330867 100%); }
        
        .metric-label { font-size: 13px; font-weight: 600; opacity: 0.9; margin-bottom: 8px; }
        .metric-value { font-size: 32px; font-weight: 800; margin: 10px 0; }
        .metric-unit { font-size: 14px; opacity: 0.85; }
        
        .ai-box {
            background-color: #F0FDF4; border: 2px solid #86efac; border-radius: 12px;
            padding: 16px; margin-bottom: 20px; color: #166534; font-size: 14px;
            line-height: 1.8; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        .ranking-table {
            background: white; border-radius: 10px; padding: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        .alert-card {
            background-color: #FEF2F2; border-left: 4px solid #EF4444; padding: 12px;
            margin-bottom: 8px; border-radius: 4px; display: flex; align-items: center;
        }
        .alert-badge { 
            background: #EF4444; color: white; padding: 4px 10px; border-radius: 12px; 
            font-size: 11px; font-weight: bold; margin-right: 12px; min-width: 45px;
        }
        
        .section-title {
            font-size: 18px; font-weight: 700; color: #111827; margin-bottom: 15px;
            padding-left: 8px; border-left: 4px solid #3B82F6;
        }
        
        /* Pipeline Board Styles */
        .pipeline-stage {
            border-radius: 12px; padding: 16px; text-align: center;
            min-height: 110px; position: relative; transition: transform 0.2s;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .pipeline-stage:hover { transform: translateY(-3px); box-shadow: 0 4px 16px rgba(0,0,0,0.15); }
        .pipeline-count { font-size: 36px; font-weight: 800; margin: 4px 0; }
        .pipeline-label { font-size: 13px; font-weight: 600; opacity: 0.9; }
        .pipeline-arrow { display: flex; align-items: center; justify-content: center;
                         font-size: 18px; color: #9CA3AF; padding-top: 30px; }
        .pipeline-exit { border-radius: 10px; padding: 10px; text-align: center;
                        border: 1px dashed #D1D5DB; min-height: 70px; }
        .pipeline-exit-count { font-size: 22px; font-weight: 700; margin: 2px 0; }
        .pipeline-exit-label { font-size: 11px; font-weight: 600; }
        /* 캘린더 컴포넌트 탭 내부 렌더링 수정 */
        iframe[title="streamlit_calendar.calendar"] {
            min-height: 700px !important;
            height: 700px !important;
        }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 메인 대시보드
# ==============================================================================
def show(data):
    apply_styles()
    st.title("🚀 Gradius 경영 대시보드")
    st.caption("실시간 사업 현황 통합 분석")

    # ── 하루 1회 자동 상태 전환 (배정완료/진행중 → 완료) ──────────────────
    _today_str = today_kst().strftime("%Y-%m-%d")
    if st.session_state.get("_auto_fix_date") != _today_str:
        fixed = db.auto_fix_status_by_date()
        st.session_state["_auto_fix_date"] = _today_str
        if fixed:
            st.toast(f"✅ 행사 종료 {fixed}건이 자동으로 '완료' 처리되었습니다.", icon="🎯")
            data = db.load_all_data()   # 갱신된 데이터로 교체
    # ────────────────────────────────────────────────────────────────────────

    df_inq = data['inq']
    
    # 배정 데이터와 정산 데이터 로드 (세션 캐시)
    dispatch_data = db.get_dispatch()
    df_dispatch = dispatch_data.get('dispatch', pd.DataFrame())
    df_settlement = dispatch_data.get('settlement', pd.DataFrame())
    df_payment = dispatch_data.get('payment', pd.DataFrame())
    
    # 1. KPI 계산
    kpi = ud.calculate_kpi(df_inq)
    settlement_overview = ud.get_settlement_overview(df_settlement)
    unpaid_df = ud.get_unpaid_list(df_inq)
    pending_df = ud.get_pending_list(df_inq)
    operating_profit = ud.get_operating_profit(df_settlement, df_dispatch, df_payment)
    conversion = ud.get_estimate_conversion_rate(df_inq)
    stale_estimates = ud.get_stale_estimates(df_inq)
    role_stats = ud.get_role_statistics(df_dispatch)
    team_stats = ud.get_team_dispatch_stats(df_dispatch)
    
    # 2. AI 브리핑
    insight = ud.generate_ai_insight(kpi, len(unpaid_df), len(pending_df))
    st.markdown(f"""<div class="ai-box">
    <b>🤖 AI Executive Summary</b><br/>
    {insight}
    </div>""", unsafe_allow_html=True)
    
    # 3. 스마트 브리핑 (AI 추천)
    st.markdown("---")
    st.markdown('<div class="section-title">📌 오늘의 확인 사항</div>', unsafe_allow_html=True)
    
    smart_briefing = ud.generate_smart_briefing(df_inq, df_dispatch, df_settlement)
    briefing_colors = ["#FEF2F2", "#FFF7ED", "#F0FDF4", "#EFF6FF", "#FDF4FF"]
    briefing_borders = ["#EF4444", "#F97316", "#10B981", "#3B82F6", "#A855F7"]
    
    # 견적 미체결 경과일 알림 추가 + 계약대기 청구예정액 매핑용 견적금액 조회
    _est_amt_map = {}
    _df_est = data.get('estimate', pd.DataFrame())
    if not _df_est.empty:
        _eid_col = ud.find_col(_df_est, ['문의ID', 'ID'])
        _amt_col = ud.find_col(_df_est, ['합계금액', '공급가액'])
        if _eid_col and _amt_col:
            for _, _er in _df_est.iterrows():
                _eid = str(_er.get(_eid_col, '')).strip()
                _amt = ud.safe_int(_er.get(_amt_col, 0))
                if _eid and _amt > 0:
                    _est_amt_map[_eid] = _amt

    if not stale_estimates.empty:
        count = len(stale_estimates)
        top_names = ", ".join(stale_estimates['업체명'].head(3).tolist()) if '업체명' in stale_estimates.columns else ""
        detail_rows = []
        for _, r in stale_estimates.head(10).iterrows():
            _inq_id = str(r.get('문의ID', '')).strip()
            _amt_val = _est_amt_map.get(_inq_id, 0)
            detail_rows.append({
                '업체명': r.get('업체명', ''),
                '행사명': r.get('행사명', ''),
                '연락처': r.get('연락처', '-') if '연락처' in stale_estimates.columns else '-',
                '청구예정액': f'₩{_amt_val:,}' if _amt_val > 0 else '-',
                '경과일': f"{int(r.get('경과일', 0))}일",
            })
        smart_briefing.append({
            'type': 'stale',
            'title': f'🧮 견적 미체결 {count}건',
            'html': f"🧮 <b>견적 후 미체결 {count}건 확인 필요</b><br/>"
                    f"견적 발송 후 7일 이상 체결되지 않은 건이 있습니다"
                    + (f": <b>{top_names}</b>" if top_names else ""),
            'detail_rows': detail_rows,
        })
    
    # 영업이익 알림
    if operating_profit['공급가액'] > 0:
        if operating_profit['이익률'] < 15:
            smart_briefing.append({
                'type': 'profit',
                'title': f"📉 이익률 주의 ({operating_profit['이익률']}%)",
                'html': f"📉 <b>이익률 주의 ({operating_profit['이익률']}%)</b><br/>"
                        f"공급가액 {operating_profit['공급가액']:,}원 대비 지급액 {operating_profit['지급액']:,}원 → 이익률이 낮습니다",
                'detail_rows': [],
            })
    
    # 팀 배정 현황 요약
    if team_stats['팀배정건수'] > 0:
        smart_briefing.append({
            'type': 'team',
            'title': '👥 팀 배정 현황',
            'html': f"👥 <b>팀 배정 현황</b><br/>"
                    f"현재 {team_stats['팀수']}개 팀, 팀장 {team_stats.get('팀장수', 0)}명 + 팀원 {team_stats.get('팀원수', 0)}명 투입 중",
            'detail_rows': [],
        })
    
    # ── 확인사항 렌더링 (요약카드 방식) ──
    _type_nav_map = {
        'unpaid': '대표님',
        'upcoming': '인원',
        'pending': '계약',
        'stale': '계약',
        'profit': '정산',
        'team': '인원',
    }
    
    for idx, item in enumerate(smart_briefing):
        color_idx = idx % len(briefing_colors)
        bg_color = briefing_colors[color_idx]
        border_color = briefing_borders[color_idx]
        
        # 구조화된 dict인지 확인 (하위 호환)
        if isinstance(item, dict):
            html = item.get('html', '')
            detail_rows = item.get('detail_rows', [])
            item_type = item.get('type', '')
            nav_target = _type_nav_map.get(item_type)
        else:
            html = item
            detail_rows = []
            item_type = ''
            nav_target = None
        
        # 요약 바
        st.markdown(f"""
        <div style="background-color: {bg_color}; border-left: 4px solid {border_color}; 
                    padding: 12px 15px; margin-bottom: 4px; border-radius: 6px; font-size: 13px; line-height: 1.6;">
            {html}
        </div>
        """, unsafe_allow_html=True)
        
        # 상세 카드 (접이식)
        if detail_rows:
            # pending 타입: 청구예정액 채우기 + D-Day 색상
            if item_type == 'pending':
                for _pr in detail_rows:
                    _pid = _pr.pop('_inq_id', '')
                    _pamt = _est_amt_map.get(_pid, 0)
                    _pr['청구예정액'] = f'₩{_pamt:,}' if _pamt > 0 else '-'
                    # D-Day 색상
                    _dd = _pr.get('D-Day', '-')
                    if _dd == '★오늘' or _dd.startswith('D+'):
                        _pr['D-Day'] = f"<span style='color:#DC2626;font-weight:700;'>{_dd}</span>"
                    elif _dd.startswith('D-'):
                        _dd_num = int(_dd.replace('D-', ''))
                        if _dd_num <= 7:
                            _pr['D-Day'] = f"<span style='color:#DC2626;font-weight:700;'>{_dd}</span>"
                        elif _dd_num <= 14:
                            _pr['D-Day'] = f"<span style='color:#EA580C;font-weight:700;'>{_dd}</span>"
                        else:
                            _pr['D-Day'] = f"<span style='color:#059669;'>{_dd}</span>"

            with st.expander("📋 상세보기", expanded=False):
                # 테이블 헤더 구성 (_로 시작하는 내부 키 제외)
                cols = [c for c in detail_rows[0].keys() if not c.startswith('_')]
                header_html = "".join(
                    f"<th style='padding:10px 14px; background:#e2e8f0; font-size:14px; font-weight:700; "
                    f"border-bottom:2px solid #cbd5e1; color:#1e293b;'>{c}</th>" for c in cols
                )
                rows_html = ""
                for ri, r in enumerate(detail_rows):
                    _bg = '#f8fafc' if ri % 2 == 0 else '#ffffff'
                    cells = "".join(
                        f"<td style='padding:9px 14px; font-size:14px; border-bottom:1px solid #e2e8f0; "
                        f"color:#334155;'>{r.get(c, '')}</td>" for c in cols
                    )
                    rows_html += f"<tr style='background:{_bg};'>{cells}</tr>"
                
                st.markdown(f"""
                <table style="width:100%; border-collapse:collapse; margin:6px 0; border-radius:8px; overflow:hidden; border:1px solid #e2e8f0;">
                    <thead><tr>{header_html}</tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
                """, unsafe_allow_html=True)
                
                # 해당 페이지로 이동 버튼
                if nav_target:
                    _nav_labels = {
                        'unpaid': '💰 업체 입금관리로 이동',
                        'upcoming': '👥 인력배정 현황으로 이동',
                        'pending': '� 계약 관리 및 승인으로 이동',
                        'stale': '📋 계약 관리 및 승인으로 이동',
                        'profit': '🧾 정산관리로 이동',
                        'team': '👥 인력배정으로 이동',
                    }
                    btn_label = _nav_labels.get(item_type, f'{nav_target} 페이지로 이동')
                    if st.button(btn_label, key=f"_brief_nav_{idx}", use_container_width=True):
                        st.session_state['_nav_target'] = nav_target
                        st.rerun()
    
    st.markdown("---")
    
    # 3. KPI 카드 (고도화된 디자인) — 2행 구성
    st.subheader("📊 핵심 KPI")
    col_supply, col_s, col_p, col_u, col_r = st.columns(5)
    
    with col_supply:
        st.markdown(f"""
        <div class="metric-card sales">
            <div class="metric-label">📦 공급가액</div>
            <div class="metric-value">{settlement_overview['공급가액']:,}</div>
            <div class="metric-unit">원</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_s:
        st.markdown(f"""
        <div class="metric-card sales">
            <div class="metric-label">💰 총청구액 (공급가+VAT)</div>
            <div class="metric-value">{settlement_overview['총청구액']:,}</div>
            <div class="metric-unit">원</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_p:
        st.markdown(f"""
        <div class="metric-card profit">
            <div class="metric-label">✅ 수금액</div>
            <div class="metric-value">{settlement_overview['받은금액']:,}</div>
            <div class="metric-unit">원</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_u:
        st.markdown(f"""
        <div class="metric-card unpaid">
            <div class="metric-label">⚠️ 미수금액</div>
            <div class="metric-value">{settlement_overview['미수금액']:,}</div>
            <div class="metric-unit">원</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_r:
        st.markdown(f"""
        <div class="metric-card payment-rate">
            <div class="metric-label">📈 수금률</div>
            <div class="metric-value">{settlement_overview['수금률']}%</div>
            <div class="metric-unit">집행률</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("")
    
    # ── KPI 2행: 영업이익 + 견적전환율 ──
    profit_color = "#059669" if operating_profit['영업이익'] >= 0 else "#DC2626"
    col_op, col_pay, col_margin, col_conv = st.columns(4)
    
    with col_op:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #059669 0%, #047857 100%);
                    border-radius: 12px; padding: 20px; text-align: center;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15); color: white;">
            <div style="font-size: 13px; font-weight: 600; opacity: 0.9; margin-bottom: 8px;">💎 영업이익</div>
            <div style="font-size: 28px; font-weight: 800; margin: 10px 0;">{operating_profit['영업이익']:,}</div>
            <div style="font-size: 14px; opacity: 0.85;">원 (이익률 {operating_profit['이익률']}%)</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_pay:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%);
                    border-radius: 12px; padding: 20px; text-align: center;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15); color: white;">
            <div style="font-size: 13px; font-weight: 600; opacity: 0.9; margin-bottom: 8px;">💸 총 지급액</div>
            <div style="font-size: 28px; font-weight: 800; margin: 10px 0;">{operating_profit['지급액']:,}</div>
            <div style="font-size: 14px; opacity: 0.85;">원</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_margin:
        margin_bg = "#059669" if operating_profit['이익률'] >= 30 else "#F59E0B" if operating_profit['이익률'] >= 15 else "#DC2626"
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {margin_bg} 0%, {margin_bg}DD 100%);
                    border-radius: 12px; padding: 20px; text-align: center;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15); color: white;">
            <div style="font-size: 13px; font-weight: 600; opacity: 0.9; margin-bottom: 8px;">📊 이익률</div>
            <div style="font-size: 28px; font-weight: 800; margin: 10px 0;">{operating_profit['이익률']}%</div>
            <div style="font-size: 14px; opacity: 0.85;">{'양호' if operating_profit['이익률'] >= 30 else '주의' if operating_profit['이익률'] >= 15 else '위험'}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_conv:
        conv_bg = "#2563EB" if conversion['전체전환율'] >= 60 else "#F59E0B" if conversion['전체전환율'] >= 30 else "#DC2626"
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {conv_bg} 0%, {conv_bg}DD 100%);
                    border-radius: 12px; padding: 20px; text-align: center;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15); color: white;">
            <div style="font-size: 13px; font-weight: 600; opacity: 0.9; margin-bottom: 8px;">🎯 견적→체결 전환율</div>
            <div style="font-size: 28px; font-weight: 800; margin: 10px 0;">{conversion['전체전환율']}%</div>
            <div style="font-size: 14px; opacity: 0.85;">{conversion['체결건수']}/{conversion['견적건수']}건 (대기 {conversion['대기건수']}건)</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # =========================================================================
    # 4. 파이프라인 보드 (전체 진행 현황)
    # =========================================================================
    st.subheader("🔄 파이프라인 보드")
    st.caption("문의 → 정산완료까지 전체 진행 현황을 한 눈에 확인하세요")
    
    # 상태 컬럼 탐지
    col_status = ud.find_col(df_inq, ["체결", "상태", "진행상태"])
    
    if col_status:
        status_series = df_inq[col_status].astype(str).str.strip()
        
        # 각 상태별 건수 집계
        stage_counts = {}
        for s in sc.STATUS_FLOW:
            stage_counts[s] = int((status_series == s).sum())
        exit_counts = {}
        for s in sc.STATUS_EXIT:
            exit_counts[s] = int((status_series == s).sum())
        
        # 메인 파이프라인 (7 stages + 6 arrows = 13 columns)
        cols = st.columns([3, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3])
        for i, status_name in enumerate(sc.STATUS_FLOW):
            cfg = sc.STATUS_CONFIG[status_name]
            col_idx = i * 2
            with cols[col_idx]:
                count = stage_counts[status_name]
                st.markdown(f"""
                <div class="pipeline-stage" style="background:{cfg['bg']};border:2px solid {cfg['color']};">
                    <div class="pipeline-label" style="color:{cfg['color']};">{cfg['icon']} {status_name}</div>
                    <div class="pipeline-count" style="color:{cfg['color']};">{count}</div>
                    <div style="font-size:11px;color:{cfg['color']};opacity:0.7;">{cfg['desc'][:8]}</div>
                </div>
                """, unsafe_allow_html=True)
                # 클릭 버튼
                if count > 0:
                    if st.button(f"상세보기", key=f"pipe_{status_name}", use_container_width=True):
                        st.session_state['pipeline_detail_status'] = status_name
            if i < len(sc.STATUS_FLOW) - 1:
                with cols[col_idx + 1]:
                    st.markdown('<div class="pipeline-arrow">→</div>', unsafe_allow_html=True)
        
        # 이탈 상태 (파이프라인 아래 독립 섹션)
        exit_total = sum(exit_counts.values())
        if exit_total > 0:
            st.markdown("")
            st.markdown("##### 🚫 이탈 현황")
            exit_cols = st.columns([1, 1, 1, 3])
            for i, status_name in enumerate(sc.STATUS_EXIT):
                cfg = sc.STATUS_CONFIG[status_name]
                count = exit_counts[status_name]
                with exit_cols[i]:
                    st.markdown(f"""
                    <div class="pipeline-exit" style="background:{cfg['bg']};border-color:{cfg['color']};">
                        <div class="pipeline-exit-label" style="color:{cfg['color']};">{cfg['icon']} {status_name}</div>
                        <div class="pipeline-exit-count" style="color:{cfg['color']};">{count}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if count > 0:
                        if st.button("상세", key=f"pipe_exit_{status_name}"):
                            st.session_state['pipeline_detail_status'] = status_name
            with exit_cols[3]:
                st.markdown(f"""
                <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;padding:12px;font-size:13px;color:#991B1B;">
                    ⚠️ 이탈 합계 <b>{exit_total}건</b> (미체결 {exit_counts.get('미체결',0)} / 보류 {exit_counts.get('보류',0)} / 취소 {exit_counts.get('취소',0)})
                </div>
                """, unsafe_allow_html=True)
        
        # ── 파이프라인 상세 패널 ──
        _pipe_sel = st.session_state.get('pipeline_detail_status', '')
        if _pipe_sel:
            _pipe_cfg = sc.STATUS_CONFIG.get(_pipe_sel, {})
            _pipe_icon = _pipe_cfg.get('icon', '📋')
            st.markdown(f"""
            <div style="background:{_pipe_cfg.get('bg','#f9fafb')};border:2px solid {_pipe_cfg.get('color','#6B7280')};
                        border-radius:12px;padding:16px;margin:12px 0;">
                <div style="font-size:18px;font-weight:800;color:{_pipe_cfg.get('color','#111')};margin-bottom:10px;">
                    {_pipe_icon} {_pipe_sel} 상태 상세 목록
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            _pipe_df = df_inq[status_series == _pipe_sel].copy()
            if not _pipe_df.empty:
                col_id = ud.find_col(df_inq, ["문의ID", "ID", "No", "번호"])
                col_company = ud.find_col(df_inq, ["업체", "업체명", "회사명", "고객사"])
                col_service = ud.find_col(df_inq, ["서비스", "서비스종류", "행사명"])
                col_contact = ud.find_col(df_inq, ["연락처", "담당자연락처", "전화"])
                col_manager = ud.find_col(df_inq, ["담당자", "담당자명"])
                col_date = ud.find_col(df_inq, ["행사시작일", "일시", "시작일"])
                col_date_end = ud.find_col(df_inq, ["행사종료일", "종료일"])
                col_location = ud.find_col(df_inq, ["장소", "행사장소"])
                col_svc_type = ud.find_col(df_inq, ["서비스종류", "서비스"])
                col_headcount = ud.find_col(df_inq, ["필요인력", "요청인원", "인원"])
                col_time = ud.find_col(df_inq, ["행사시간", "시간"])
                col_pay = ud.find_col(df_inq, ["페이", "예산"])
                col_note = ud.find_col(df_inq, ["특이사항"])
                col_status_val = ud.find_col(df_inq, ["상태"])

                # ── 완료 상태: 정산/지급 현황 맵 사전 구성 ────────────────────
                _settle_status_map = {}
                _pay_done_map = {}
                if _pipe_sel == '완료':
                    if not df_settlement.empty and '문의ID' in df_settlement.columns:
                        def _n(v):  # 콤마 포함 숫자 문자열 안전 변환
                            try: return float(str(v).replace(',', '').strip() or 0)
                            except: return 0.0
                        for _, _sr in df_settlement.iterrows():
                            _sid = str(_sr.get('문의ID', '')).strip()
                            if not _sid:
                                continue
                            _s_supply = _n(_sr.get('공급가액', 0))
                            _s_tax    = _n(_sr.get('부가세', 0))
                            _s_paid   = _n(_sr.get('받은금액', 0))
                            _s_bal    = _n(_sr.get('잔액', 0))
                            if _s_bal <= 0:
                                _s_bal = max(0, _s_supply + _s_tax - _s_paid)
                            _s_dep  = str(_sr.get('입금여부', '')).strip()
                            _s_prog = str(_sr.get('진행상황', '')).strip()
                            _settle_status_map[_sid] = {
                                'deposit_ok': (_s_bal <= 0 and _s_paid > 0) or _s_dep == '입금완료',
                                'paid':     int(_s_paid),
                                'balance':  int(_s_bal),
                                'total':    int(_s_supply + _s_tax),
                                'progress': _s_prog,  # 진행상황 저장 (이미 정산완료 필터용)
                            }
                    if not df_payment.empty and '문의ID' in df_payment.columns and '지급상태' in df_payment.columns:
                        for _, _prow in df_payment.iterrows():
                            _prow_id = str(_prow.get('문의ID', '')).strip()
                            _prow_st = str(_prow.get('지급상태', '')).strip()
                            if not _prow_id:
                                continue
                            if _prow_id not in _pay_done_map:
                                _pay_done_map[_prow_id] = {'done': 0, 'total': 0}
                            _pay_done_map[_prow_id]['total'] += 1
                            if _prow_st in ('완료', '확인완료'):
                                _pay_done_map[_prow_id]['done'] += 1
                    # 배정기록 외부인력 카운트 맵: 지급내역 교차검증용
                    # 외부인력(팀장/팀원/외부)이 있는데 지급내역이 0건이면 미완료로 판정
                    _ext_count_map = {}  # 문의ID → 외부인력 수
                    if not df_dispatch.empty and '문의ID' in df_dispatch.columns:
                        _has_gubun = '구분' in df_dispatch.columns
                        for _, _drow in df_dispatch.iterrows():
                            _drow_id = str(_drow.get('문의ID', '')).strip()
                            if not _drow_id:
                                continue
                            if _has_gubun and str(_drow.get('구분', '')).strip() == '본사':
                                continue  # 본사 인원 제외
                            _ext_count_map[_drow_id] = _ext_count_map.get(_drow_id, 0) + 1
                # ──────────────────────────────────────────────────────────────

                # ── 완료 상태: 전체 정산완료 버튼 ────────────────────────────────
                if _pipe_sel == '완료':
                    # _pipe_df 에 실제로 표시되는 ID만 대상으로 한정
                    _pipe_ids = set(
                        str(_pr2.get(col_id, '')).strip()
                        for _, _pr2 in _pipe_df.iterrows()
                        if col_id
                    )
                    _ready_inq_ids = [
                        _sid for _sid, _si in _settle_status_map.items()
                        if _sid in _pipe_ids
                        and _si.get('progress', '') != '정산완료'  # 이미 정산완료된 항목 제외
                        and _si['deposit_ok']
                        and _si.get('paid', 0) > 0  # 실제 입금액이 0이면 제외
                        and (lambda _p=_pay_done_map.get(_sid, {'done': 0, 'total': 0}),
                                  _ec=_ext_count_map.get(_sid, 0):
                             _p['done'] == _p['total'] and (_p['total'] > 0 or _ec == 0))()
                    ]
                    # ── 디버그 expander ──
                    with st.expander("🔍 전체정산 버튼 디버그", expanded=False):
                        st.write(f"**파이프라인 ID 수**: {len(_pipe_ids)}")
                        st.write(f"**settle_map IDs**: {len(_settle_status_map)}개 → {list(_settle_status_map.keys())[:10]}")
                        st.write(f"**pay_map IDs**: {len(_pay_done_map)}개")
                        st.write(f"**pipe_ids ∩ settle_map**: {_pipe_ids & set(_settle_status_map.keys())}")
                        for _dbg_id in list(_pipe_ids)[:10]:
                            _dbg_s = _settle_status_map.get(_dbg_id, {})
                            _dbg_p = _pay_done_map.get(_dbg_id, {})
                            st.write(f"  `{_dbg_id}`: dep_ok={_dbg_s.get('deposit_ok')}, "
                                     f"paid={_dbg_s.get('paid', 0)}, "
                                     f"progress={_dbg_s.get('progress')!r}, "
                                     f"pay={_dbg_p.get('done')}/{_dbg_p.get('total')}")
                        st.write(f"**_ready_inq_ids**: {_ready_inq_ids}")
                    # ────────────────────
                    if _ready_inq_ids:
                        _bulk_col, _ = st.columns([2, 3])
                        with _bulk_col:
                            if st.button(
                                f"✅ 조건충족 전체 {len(_ready_inq_ids)}건 정산완료",
                                type="primary", key="_bulk_finalize",
                                use_container_width=True,
                            ):
                                _bulk = db.batch_finalize_settlements(_ready_inq_ids)
                                if _bulk.get('confirmed'):
                                    st.success(f"{len(_bulk['confirmed'])}건 정산완료 처리!")
                                    st.rerun()
                                else:
                                    st.warning("재검증 결과 조건 미충족")
                # ──────────────────────────────────────────────────────────────

                for _pi, _pr in _pipe_df.iterrows():
                    _p_id = str(_pr.get(col_id, '')) if col_id else ''
                    _p_company = str(_pr.get(col_company, '')) if col_company else ''
                    _p_event = str(_pr.get(col_service, '')) if col_service else ''
                    _p_contact = str(_pr.get(col_contact, '')) if col_contact else '-'
                    _p_manager = str(_pr.get(col_manager, '')) if col_manager else '-'
                    _p_date = str(_pr.get(col_date, '')) if col_date else '-'
                    _p_date_end = str(_pr.get(col_date_end, '')) if col_date_end else ''
                    _p_location = str(_pr.get(col_location, '')) if col_location else '-'
                    _p_svc_type = str(_pr.get(col_svc_type, '')) if col_svc_type else '-'
                    _p_headcount = str(_pr.get(col_headcount, '')) if col_headcount else '-'
                    _p_time = str(_pr.get(col_time, '')) if col_time else '-'
                    _p_pay = str(_pr.get(col_pay, '')) if col_pay else '-'
                    _p_note = str(_pr.get(col_note, '')) if col_note else ''
                    
                    # nan 처리
                    for _var_name in ['_p_date_end', '_p_svc_type', '_p_headcount', '_p_time', '_p_pay', '_p_note']:
                        _val = locals()[_var_name]
                        if _val in ('nan', 'None', ''): locals()[_var_name] = '-'
                    
                    _date_display = _p_date
                    if _p_date_end and _p_date_end not in ('-', 'nan', 'None', ''):
                        _date_display = f"{_p_date} ~ {_p_date_end}"
                    
                    # 견적 금액 확인
                    _est_data = data.get('estimate', pd.DataFrame())
                    _est_amount = 0
                    if not _est_data.empty and '문의ID' in _est_data.columns:
                        _est_match = _est_data[_est_data['문의ID'].astype(str).str.strip() == _p_id]
                        if not _est_match.empty:
                            _est_amount = ud.safe_int(_est_match.iloc[0].get('합계금액', 0))
                    
                    with st.container(border=True):
                        _dc1, _dc2, _dc3 = st.columns([2.5, 2.5, 1])
                        with _dc1:
                            st.markdown(f"**🏢 {_p_company}** — {_p_event}")
                            st.caption(f"📋 {_p_id}")
                            st.markdown(f"📅 {_date_display}  |  ⏰ {_p_time}")
                            st.markdown(f"📍 {_p_location}")
                        with _dc2:
                            st.markdown(f"👤 {_p_manager}  |  📞 {_p_contact}")
                            st.markdown(f"🔧 서비스: {_p_svc_type}  |  👥 인원: {_p_headcount}")
                            st.markdown(f"💵 페이: {_p_pay}")
                            if _p_note and _p_note != '-':
                                st.caption(f"📝 {_p_note}")
                        with _dc3:
                            # 배정 인원 확인 (필요인원 대비 비율 표시)
                            _p_staff_detail = ud.get_dispatch_detail_for_event(df_dispatch, _p_event)
                            _p_staff_count = len(_p_staff_detail) if not _p_staff_detail.empty else 0
                            _p_need = ud.safe_int(_p_headcount) if _p_headcount and _p_headcount != '-' else 0
                            
                            if _p_need > 0:
                                if _p_staff_count >= _p_need:
                                    st.markdown(f"""<div style="background:#DCFCE7;color:#166534;padding:8px;border-radius:8px;text-align:center;font-weight:bold;">
                                        ✅ 배정완료<br/>{_p_staff_count}/{_p_need}명
                                    </div>""", unsafe_allow_html=True)
                                elif _p_staff_count == 0:
                                    st.markdown(f"""<div style="background:#FEE2E2;color:#991B1B;padding:8px;border-radius:8px;text-align:center;font-weight:bold;">
                                        🔴 배정필요<br/>0/{_p_need}명
                                    </div>""", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"""<div style="background:#FEF3C7;color:#92400E;padding:8px;border-radius:8px;text-align:center;font-weight:bold;">
                                        ⚠️ 배정중<br/>{_p_staff_count}/{_p_need}명
                                    </div>""", unsafe_allow_html=True)
                            else:
                                st.markdown(f"""<div style="background:#F3F4F6;color:#374151;padding:8px;border-radius:8px;text-align:center;font-weight:bold;">
                                    👥 {_p_staff_count}명 배정
                                </div>""", unsafe_allow_html=True)
                            if _est_amount > 0:
                                st.metric("견적액", f"{_est_amount:,}원")
                        # ── 완료 상태: 정산/지급 현황 표시 ───────────────────
                        if _pipe_sel == '완료':
                            st.divider()
                            _sinfo = _settle_status_map.get(_p_id, {})
                            _pinfo = _pay_done_map.get(_p_id, {'done': 0, 'total': 0})
                            _pd = _pinfo.get('done', 0)
                            _pt = _pinfo.get('total', 0)
                            _dep_ok = _sinfo.get('deposit_ok', False)
                            _paid_ok = _sinfo.get('paid', 0) > 0  # 실제 입금액 > 0
                            # 외부인력이 있는데 지급내역이 0건이면 지급미완료로 판정
                            _ec = _ext_count_map.get(_p_id, 0)
                            _pay_ok = (_pd == _pt) and (_pt > 0 or _ec == 0)
                            _fs1, _fs2, _fs3 = st.columns([2, 2, 1.3])
                            with _fs1:
                                if _dep_ok:
                                    st.success(f"💰 업체 입금완료  ₩{_sinfo.get('paid', 0):,}")
                                elif _sinfo:
                                    if _sinfo.get('paid', 0) > 0:
                                        st.warning(f"💰 부분입금  잔액 ₩{_sinfo.get('balance', 0):,}")
                                    else:
                                        st.error(f"💰 미입금  청구 ₩{_sinfo.get('total', 0):,}")
                                else:
                                    st.info("💰 정산 데이터 없음")
                            with _fs2:
                                if _pt == 0 and _ec == 0:
                                    # 외부인력 없음 = 본사 인원만 진행
                                    st.success("💼 본사 인원 전용  지급 불필요")
                                elif _pt == 0 and _ec > 0:
                                    # 외부인력이 있는데 지급내역이 0건 = 인사담당자 미컨펌
                                    st.warning(f"💸 지급 대기  외부 {_ec}명  (인사담당자 확인 필요)")
                                elif _pay_ok:
                                    st.success(f"💸 인건비 전원 지급완료  {_pd}명")
                                else:
                                    _unpaid_names = []
                                    if (not df_payment.empty
                                            and '문의ID' in df_payment.columns
                                            and '인력명' in df_payment.columns
                                            and '지급상태' in df_payment.columns):
                                        _pm = (
                                            (df_payment['문의ID'].astype(str).str.strip() == _p_id)
                                            & (~df_payment['지급상태'].astype(str).str.strip()
                                               .isin(['완료', '확인완료']))
                                        )
                                        if _pm.any():
                                            _unpaid_names = df_payment[_pm]['인력명'].astype(str).tolist()
                                    _n_txt = ', '.join(_unpaid_names[:3]) + ('...' if len(_unpaid_names) > 3 else '')
                                    st.warning(f"💸 인건비 {_pd}/{_pt}명  미지급: {_n_txt}" if _n_txt else f"💸 인건비 {_pd}/{_pt}명")
                            with _fs3:
                                if _dep_ok and _paid_ok and _pay_ok:
                                    if st.button("✅ 정산완료", key=f"_fin_{_p_id}",
                                                 type="primary", use_container_width=True):
                                        _fin = db.batch_finalize_settlements([_p_id])
                                        if _fin.get('confirmed'):
                                            st.success("정산완료 처리!")
                                            st.rerun()
                                        else:
                                            st.warning("조건 재확인 필요")
                                else:
                                    _miss = []
                                    if not _dep_ok:   _miss.append("입금미완료")
                                    if not _paid_ok:  _miss.append("받은금액=0")
                                    if not _pay_ok:   _miss.append("지급미완료")
                                    st.button("🔒 조건미충족", key=f"_fin_{_p_id}",
                                              disabled=True, use_container_width=True,
                                              help=" · ".join(_miss))
                        # ─────────────────────────────────────────────────────

                st.caption(f"총 {len(_pipe_df)}건")
            else:
                st.info("해당 상태의 건이 없습니다.")
            
            if st.button("✖ 상세 패널 닫기", key="close_pipe_detail"):
                st.session_state.pop('pipeline_detail_status', None)
                st.rerun()
        
        # 진행률 바 (체결 이후 건수 / 전체 건수)
        total = len(df_inq)
        if total > 0:
            confirmed = sum(stage_counts[s] for s in sc.CONFIRMED_STATUSES if s in stage_counts)
            completed = stage_counts.get("정산완료", 0)
            in_progress_pct = round(confirmed / total * 100, 1) if total > 0 else 0
            completed_pct = round(completed / total * 100, 1) if total > 0 else 0
            
            st.markdown("")
            prog_cols = st.columns(3)
            with prog_cols[0]:
                st.metric("📋 전체 건수", f"{total}건")
            with prog_cols[1]:
                st.metric("✅ 확정(체결 이후)", f"{confirmed}건", f"{in_progress_pct}%")
            with prog_cols[2]:
                st.metric("💰 정산완료", f"{completed}건", f"{completed_pct}%")
    else:
        st.warning("상태 컬럼을 찾을 수 없습니다.")
    
    st.markdown("---")
    
    # =========================================================================
    # 5. 상태 변경 관리
    # =========================================================================
    with st.expander("🔧 상태 변경 관리 (클릭하여 펼치기)"):
        st.caption("문의건의 상태를 직접 변경할 수 있습니다")
        
        if col_status and not df_inq.empty:
            # 문의 ID 컬럼 찾기
            col_id = ud.find_col(df_inq, ["문의ID", "ID", "No", "번호"])
            col_company = ud.find_col(df_inq, ["업체", "업체명", "회사명", "고객사"])
            col_service = ud.find_col(df_inq, ["서비스", "서비스종류", "행사명"])
            
            if col_id:
                # 검색 & 필터
                filter_col1, filter_col2 = st.columns(2)
                with filter_col1:
                    selected_status_filter = st.selectbox(
                        "상태 필터",
                        ["전체"] + sc.ALL_STATUS,
                        key="pipeline_status_filter"
                    )
                with filter_col2:
                    search_keyword = st.text_input("🔍 업체명/ID 검색", key="pipeline_search")
                
                # 필터된 데이터
                filtered_df = df_inq.copy()
                if selected_status_filter != "전체":
                    filtered_df = filtered_df[filtered_df[col_status].astype(str).str.strip() == selected_status_filter]
                if search_keyword:
                    mask = pd.Series([False]*len(filtered_df), index=filtered_df.index)
                    if col_id:
                        mask |= filtered_df[col_id].astype(str).str.contains(search_keyword, na=False, case=False)
                    if col_company:
                        mask |= filtered_df[col_company].astype(str).str.contains(search_keyword, na=False, case=False)
                    filtered_df = filtered_df[mask]
                
                if filtered_df.empty:
                    st.info("조건에 맞는 문의건이 없습니다.")
                else:
                    st.markdown(f"**{len(filtered_df)}건** 검색됨")
                    
                    # 상태 변경할 건 선택
                    display_options = []
                    for _, row in filtered_df.head(30).iterrows():
                        inq_id = str(row.get(col_id, ''))
                        company = str(row.get(col_company, '')) if col_company else ''
                        cur_status = str(row.get(col_status, ''))
                        cfg = sc.STATUS_CONFIG.get(cur_status, {"icon": "❓"})
                        label = f"{cfg['icon']} [{cur_status}] {inq_id}"
                        if company:
                            label += f" - {company}"
                        display_options.append(label)
                    
                    if display_options:
                        selected = st.selectbox(
                            "변경할 문의 선택 (최근 30건)",
                            display_options,
                            key="pipeline_select_inq"
                        )
                        
                        if selected:
                            # 선택된 항목에서 ID 추출
                            sel_idx = display_options.index(selected)
                            sel_row = filtered_df.head(30).iloc[sel_idx]
                            sel_id = str(sel_row.get(col_id, ''))
                            cur_status_val = str(sel_row.get(col_status, '')).strip()
                            
                            # 현재 상태 표시
                            st.markdown(f"**현재 상태**: {sc.get_status_badge_html(cur_status_val)}", unsafe_allow_html=True)
                            
                            # 전환 가능 상태
                            next_statuses = sc.get_next_statuses(cur_status_val)
                            
                            if next_statuses:
                                # 진행률 표시
                                progress = sc.get_status_progress(cur_status_val)
                                st.progress(progress / 100, text=f"진행률: {progress}%")
                                
                                change_col1, change_col2 = st.columns([2, 1])
                                with change_col1:
                                    new_status = st.selectbox(
                                        "변경할 상태 선택",
                                        next_statuses,
                                        format_func=lambda x: f"{sc.get_status_icon(x)} {x} — {sc.STATUS_CONFIG.get(x, {}).get('desc', '')}",
                                        key="pipeline_new_status"
                                    )
                                with change_col2:
                                    st.markdown("<br>", unsafe_allow_html=True)
                                    if st.button("✅ 상태 변경", type="primary", key="pipeline_change_btn"):
                                        try:
                                            db.update_status(sel_id, new_status)
                                            st.success(f"'{sel_id}' → {sc.get_status_icon(new_status)} {new_status} 변경 완료!")
                                            db.invalidate_data()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"변경 실패: {e}")
                            else:
                                st.info(f"'{cur_status_val}'는 최종 상태입니다. 더 이상 전환할 수 없습니다.")
            else:
                st.warning("문의 ID 컬럼을 찾을 수 없습니다.")
        else:
            st.warning("문의 데이터가 없습니다.")
    
    st.markdown("---")
    
    # 6. 탭 구성
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
        "📊 분석", "🔥 긴급", "👥 인력", "💼 고객", "💰 정산", "📅 캘린더", "📋 리포트", "🤖 AI 분석", "💎 수익분석", "💸 미지급 인건비"
    ])
    
    # [Tab 1] 분석 차트
    with tab1:
        col_chart, col_ranking = st.columns([2, 1])
        
        with col_chart:
            st.markdown('<div class="section-title">📈 월별 매출 추이</div>', unsafe_allow_html=True)
            
            # 연도 선택기
            current_year = now_kst().year
            year_options = ["전체"] + [str(y) for y in range(current_year, current_year - 5, -1)]
            sel_year_str = st.selectbox("📅 연도 필터", year_options, key="trend_year_filter")
            sel_year = int(sel_year_str) if sel_year_str != "전체" else None
            
            # 정산/견적 데이터 전달하여 실제 매출 표시
            df_est_for_trend = data.get('estimate', pd.DataFrame())
            trend_df = ud.get_monthly_trend(df_inq, df_settlement=df_settlement, df_estimate=df_est_for_trend, selected_year=sel_year)
            if not trend_df.empty:
                # 만원 단위로 변환하여 직관적 표시
                trend_df['Sales_만원'] = trend_df['Sales'] / 10000
                trend_df['Sales_label'] = trend_df['Sales'].apply(
                    lambda v: f"{int(v/10000):,}만" if v >= 10000 else f"{int(v):,}"
                )
                fig = px.bar(trend_df, x='Month', y='Sales', 
                           text='Sales_label', color_discrete_sequence=['#667eea'])
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10), height=300,
                    showlegend=False, hovermode='x unified',
                    xaxis_title="월", yaxis_title="매출액(원)"
                )
                fig.update_yaxes(rangemode="tozero", tickformat=",")
                fig.update_traces(marker_line=dict(width=0), textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
                
                # 요약 통계
                total_sales = int(trend_df['Sales'].sum())
                avg_sales = int(trend_df['Sales'].mean())
                st.caption(f"총 매출: {total_sales:,}원 | 월평균: {avg_sales:,}원 | {len(trend_df)}개월")
            else:
                st.info("📊 매출 데이터가 없습니다. 견적/정산 데이터가 쌓이면 표시됩니다.")
        
        with col_ranking:
            st.markdown('<div class="section-title">🏆 Top 고객사</div>', unsafe_allow_html=True)
            top_clients = ud.get_top_customers(df_inq, top_n=5)
            if not top_clients.empty:
                # 컬러풀한 표로 표현
                st.dataframe(
                    top_clients,
                    column_config={
                        "순위": st.column_config.NumberColumn("No.", format="%d"),
                        "고객사": st.column_config.TextColumn("고객사"),
                        "체결건수": st.column_config.ProgressColumn("건수", min_value=0, max_value=int(top_clients['체결건수'].max()))
                    },
                    use_container_width=True,
                    hide_index=True,
                    height=300
                )
            else:
                st.info("👥 고객 데이터 없음")
        
        st.markdown("---")
        
        # 수금률 파이 차트
        st.markdown('<div class="section-title">💳 수금 현황 (비율)</div>', unsafe_allow_html=True)
        col_pie1, col_pie2 = st.columns(2)
        
        with col_pie1:
            paid_data = [
                settlement_overview['받은금액'],
                settlement_overview['미수금액']
            ]
            fig_pie = go.Figure(data=[go.Pie(
                labels=['수금완료', '미수금'], 
                values=paid_data,
                marker=dict(colors=['#10b981', '#ef4444']),
                hole=.3
            )])
            fig_pie.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=280)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col_pie2:
            status_breakdown = ud.get_payment_status_breakdown(df_settlement)
            if status_breakdown:
                fig_status = go.Figure(data=[go.Pie(
                    labels=list(status_breakdown.keys()),
                    values=list(status_breakdown.values()),
                    marker=dict(colors=['#10b981', '#f59e0b', '#ef4444']),
                    hole=.3
                )])
                fig_status.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=280)
                st.plotly_chart(fig_status, use_container_width=True)
            else:
                st.info("정산 상태 데이터 없음")
    
    # [Tab 2] 긴급 현장
    with tab2:
        st.markdown('<div class="section-title">🚨 D-14 이내 투입 현장 (상세정보)</div>', unsafe_allow_html=True)
        
        upcoming_detail = ud.get_upcoming_dispatch_info(df_dispatch, df_inq, days=14)
        if not upcoming_detail.empty:
            for _, row in upcoming_detail.iterrows():
                d_day = int(row['D-Day'])
                if d_day == 0:
                    badge = "🔴 당일"
                    badge_color = "#DC2626"
                    priority = "가장 긴급"
                elif d_day <= 3:
                    badge = f"🟠 D-{d_day}"
                    badge_color = "#F97316"
                    priority = "긴급"
                elif d_day <= 7:
                    badge = f"🟡 D-{d_day}"
                    badge_color = "#EAB308"
                    priority = "주의"
                else:
                    badge = f"🔵 D-{d_day}"
                    badge_color = "#3B82F6"
                    priority = "확인필요"
                
                location = row['장소'] if pd.notna(row['장소']) and str(row['장소']).strip() else "장소정보없음"
                staff_count = int(row['배정인원'])
                
                # 배정 인력 상세
                staff_detail = ud.get_dispatch_detail_for_event(df_dispatch, row['행사명'])
                staff_names = ", ".join(staff_detail['인력명'].tolist()) if not staff_detail.empty else "배정전"
                
                # 문의상 필요인력 확인
                _need_col = ud.find_col(df_inq, ["필요인력", "인원"])
                _evt_col_inq = ud.find_col(df_inq, ["행사명"])
                need_count = 0
                if _need_col and _evt_col_inq:
                    _matched_inq = df_inq[df_inq[_evt_col_inq].astype(str).str.strip() == str(row['행사명']).strip()]
                    if not _matched_inq.empty:
                        need_count = ud.safe_int(_matched_inq.iloc[0].get(_need_col, 0))
                
                if need_count > 0:
                    assign_pct = min(100, int(staff_count / need_count * 100))
                    if assign_pct >= 100:
                        assign_text = f"✅ {staff_count}/{need_count}명 배정완료"
                        assign_badge_color = "#10B981"
                    elif staff_count == 0:
                        assign_text = f"🔴 0/{need_count}명 배정필요"
                        assign_badge_color = "#EF4444"
                    else:
                        assign_text = f"⚠️ {staff_count}/{need_count}명 배정중"
                        assign_badge_color = "#F59E0B"
                else:
                    assign_text = f"{staff_count}명 배정"
                    assign_badge_color = "#6B7280"
                
                st.markdown(f"""
                <div style="background: white; border: 1px solid #E5E7EB; border-left: 4px solid {badge_color};
                            border-radius: 8px; padding: 14px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.08);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                        <div style="flex: 1;">
                            <span style="background: {badge_color}; color: white; padding: 4px 8px; border-radius: 4px; 
                                        font-weight: bold; font-size: 11px; margin-right: 8px;">{badge}</span>
                            <span style="background: #F3F4F6; color: #374151; padding: 4px 8px; border-radius: 4px; 
                                        font-size: 11px;">{priority}</span>
                        </div>
                    </div>
                    <div style="margin-bottom: 8px;">
                        <b style="font-size: 15px; color: #111827;">{row['업체']} - {row['행사명']}</b>
                    </div>
                    <div style="color: #6B7280; font-size: 13px; margin-bottom: 6px;">
                        📍 <b>장소</b>: {location}
                    </div>
                    <div style="color: #6B7280; font-size: 13px; margin-bottom: 6px;">
                        📅 <b>일정</b>: {row['일정']}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: #6B7280; font-size: 13px;">
                            👥 <b>배정인력</b>: {staff_names}
                        </span>
                        <span style="background: {assign_badge_color}; color: white; padding: 3px 10px; border-radius: 12px;
                                    font-size: 11px; font-weight: bold;">{assign_text}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ 급한 현장 없음 (앞으로 2주)")
        
        st.markdown("---")
        
        # ── 견적 후 미체결 경과 건 ──
        st.markdown('<div class="section-title">🧮 견적 후 미체결 확인 필요 (7일+)</div>', unsafe_allow_html=True)
        if not stale_estimates.empty:
            st.warning(f"⚠️ 견적 발송 후 7일 이상 체결되지 않은 건이 **{len(stale_estimates)}건** 있습니다.")
            for _, row in stale_estimates.iterrows():
                days = int(row.get('경과일', 0))
                company = row.get('업체명', '-')
                event = row.get('행사명', '-')
                inq_id = row.get('문의ID', '-')
                urgency_color = "#DC2626" if days >= 14 else "#F97316" if days >= 7 else "#EAB308"
                st.markdown(f"""
                <div style="background: white; border: 1px solid #E5E7EB; border-left: 4px solid {urgency_color};
                            border-radius: 8px; padding: 12px; margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <b>{company}</b> — {event}
                            <span style="color:#9CA3AF; font-size:11px; margin-left:8px;">({inq_id})</span>
                        </div>
                        <span style="background:{urgency_color}; color:white; padding:3px 10px; border-radius:12px;
                                    font-size:11px; font-weight:bold;">📅 {days}일 경과</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ 모든 견적건이 정상 처리 중입니다.")
        
        st.markdown("---")
        st.markdown('<div class="section-title">💸 미수금 Top 5 업체</div>', unsafe_allow_html=True)
        
        unpaid_cos = ud.get_unpaid_companies(df_settlement, top_n=5)
        if not unpaid_cos.empty:
            st.dataframe(
                unpaid_cos,
                column_config={
                    "순위": st.column_config.NumberColumn("No.", format="%d"),
                    "업체": st.column_config.TextColumn("업체명"),
                    "미수금액": st.column_config.ProgressColumn(
                        "미수금", format="%d원",
                        min_value=0, max_value=int(unpaid_cos['미수금액'].max())
                    ),
                    "건수": st.column_config.NumberColumn("건수", format="%d건"),
                },
                use_container_width=True,
                hide_index=True
            )
            
            # 미수금 합계
            total_unpaid = unpaid_cos['미수금액'].sum()
            st.markdown(f"""
            <div style="background: #FEF2F2; border-left: 4px solid #EF4444; padding: 12px; border-radius: 6px; margin-top: 10px;">
                <b>🚨 Top 5 미수금 합계: ₩{total_unpaid:,}</b>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.success("🎉 미수금 업체 없음!")
        
        st.markdown("---")
        st.markdown('<div class="section-title">⚠️ 전체 미수금 현황</div>', unsafe_allow_html=True)
        
        if not unpaid_df.empty:
            st.dataframe(
                unpaid_df.head(10),
                column_config={
                    "미수금액": st.column_config.ProgressColumn(
                        "미수금", format="%d원",
                        min_value=0, max_value=int(unpaid_df['미수금액'].max())
                    ),
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("🎉 미수금 없음!")
    
    # [Tab 3] 인력 현황
    with tab3:
        st.markdown('<div class="section-title">👥 배정 인력 현황</div>', unsafe_allow_html=True)
        
        # 현재 현장별 배정 현황
        if not df_dispatch.empty:
            col_dispatch_event = ud.find_col(df_dispatch, ["행사명"])
            if col_dispatch_event:
                events_list = df_dispatch[col_dispatch_event].unique().tolist()
                
                st.markdown(f"**현재 배정된 전체 인원: {len(df_dispatch)}명 / {len(events_list)}개 현장**")
                st.markdown("---")
                
                for evt_name in events_list:
                    detail_df = ud.get_dispatch_detail_for_event(df_dispatch, evt_name)
                    staff_count = len(detail_df)
                    staff_names = ", ".join(detail_df['인력명'].tolist()) if not detail_df.empty else "미배정"
                    
                    # 문의상 필요인력 확인
                    need_col = ud.find_col(df_inq, ["필요인력", "인원"])
                    evt_col = ud.find_col(df_inq, ["행사명"])
                    need_count = 0
                    if need_col and evt_col:
                        matched_inq = df_inq[df_inq[evt_col].astype(str).str.strip() == str(evt_name).strip()]
                        if not matched_inq.empty:
                            need_count = ud.safe_int(matched_inq.iloc[0].get(need_col, 0))
                    
                    if need_count > 0:
                        fill_pct = min(100, int(staff_count / need_count * 100))
                        if fill_pct >= 100:
                            fill_color = "#10B981"
                            fill_label = "배정완료"
                        elif staff_count == 0:
                            fill_color = "#EF4444"
                            fill_label = "배정필요"
                        else:
                            fill_color = "#F59E0B"
                            fill_label = "배정중"
                        fill_text = f"{staff_count}/{need_count}명 {fill_label}"
                    else:
                        fill_pct = 100
                        fill_color = "#6B7280"
                        fill_text = f"{staff_count}명 배정"
                    
                    with st.container(border=True):
                        st.markdown(f"""
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                            <b style="font-size:14px;">🎪 {evt_name}</b>
                            <span style="background:{fill_color}; color:white; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:bold;">{fill_text}</span>
                        </div>
                        <div style="background:#E5E7EB; border-radius:4px; height:8px; margin-bottom:8px;">
                            <div style="background:{fill_color}; width:{fill_pct}%; height:100%; border-radius:4px;"></div>
                        </div>
                        <div style="font-size:12px; color:#6B7280;">👤 {staff_names}</div>
                        """, unsafe_allow_html=True)
        else:
            st.info("👥 배정 데이터가 없습니다.")
        
        st.markdown("---")
        
        # ── 직군별 배정 통계 ──
        st.markdown('<div class="section-title">🔧 직군별 배정 통계 (Top 10)</div>', unsafe_allow_html=True)
        if not role_stats.empty:
            rs_col1, rs_col2 = st.columns([2, 1])
            with rs_col1:
                fig_role = px.bar(
                    role_stats, x='배정횟수', y='직군',
                    orientation='h', color='배정횟수',
                    color_continuous_scale='Viridis', text='배정횟수'
                )
                fig_role.update_layout(
                    margin=dict(l=100, r=10, t=10, b=10), height=350,
                    showlegend=False, xaxis_title="배정 횟수", yaxis_title=""
                )
                fig_role.update_traces(textposition='outside')
                st.plotly_chart(fig_role, use_container_width=True)
            with rs_col2:
                config = {"순위": st.column_config.NumberColumn("No.", format="%d"),
                          "직군": st.column_config.TextColumn("직군"),
                          "배정횟수": st.column_config.ProgressColumn("배정횟수", min_value=0, max_value=int(role_stats['배정횟수'].max()))}
                if '총지급액' in role_stats.columns:
                    config["총지급액"] = st.column_config.NumberColumn("총지급액", format="₩%d")
                st.dataframe(role_stats, column_config=config, use_container_width=True, hide_index=True, height=350)
        else:
            st.info("🔧 직군 데이터가 없습니다.")
        
        st.markdown("---")
        
        # ── 팀 배정 현황 ──
        st.markdown('<div class="section-title">🤝 팀 배정 현황</div>', unsafe_allow_html=True)
        ts_c1, ts_c2, ts_c3, ts_c4 = st.columns(4)
        ts_c1.metric("🏢 팀 배정", f"{team_stats['팀배정건수']}명")
        ts_c2.metric("👤 개별 배정", f"{team_stats['개별배정건수']}명")
        ts_c3.metric("🏷️ 팀 수", f"{team_stats['팀수']}개")
        ts_c4.metric("👥 팀원", f"{team_stats.get('팀원수', 0)}명")
        
        if team_stats['팀배정건수'] > 0 and not df_dispatch.empty:
            col_team = ud.find_col(df_dispatch, ["팀코드"])
            if col_team:
                team_df = df_dispatch[df_dispatch[col_team].astype(str).str.strip().ne('') & df_dispatch[col_team].astype(str).str.strip().ne('nan')]
                if not team_df.empty:
                    col_name = ud.find_col(team_df, ["인력명", "직원명"])
                    col_pay_target = ud.find_col(team_df, ["결제대상"])
                    col_event = ud.find_col(team_df, ["행사명"])
                    display = []
                    if col_name and col_event:
                        for tc in team_df[col_team].unique():
                            team_rows = team_df[team_df[col_team] == tc]
                            leader = ""
                            members = []
                            for _, r in team_rows.iterrows():
                                name = str(r.get(col_name, ''))
                                if col_pay_target and str(r.get(col_pay_target, '')).strip() == 'Y':
                                    leader = name
                                else:
                                    members.append(name)
                            event = str(team_rows.iloc[0].get(col_event, '')) if col_event else ''
                            display.append({"팀코드": tc, "행사": event, "팀장": leader, "팀원": ", ".join(members), "인원": len(team_rows)})
                        if display:
                            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown('<div class="section-title">🏆 가장 많이 파견된 인원 (Top 10)</div>', unsafe_allow_html=True)
        
        top_staff = ud.get_most_dispatched_staff(df_dispatch, top_n=10)
        if not top_staff.empty:
            # 컬러풀한 바 차트
            fig_staff = px.bar(
                top_staff,
                x='파견횟수',
                y='직원명',
                orientation='h',
                color='파견횟수',
                color_continuous_scale='Blues',
                text='파견횟수'
            )
            fig_staff.update_layout(
                margin=dict(l=100, r=10, t=10, b=10),
                height=350,
                showlegend=False,
                xaxis_title="파견 횟수",
                yaxis_title=""
            )
            fig_staff.update_traces(textposition='outside')
            st.plotly_chart(fig_staff, use_container_width=True)
            
            # 테이블로도 표현
            st.dataframe(
                top_staff,
                column_config={
                    "순위": st.column_config.NumberColumn("순위", format="%d"),
                    "직원명": st.column_config.TextColumn("직원명"),
                    "파견횟수": st.column_config.ProgressColumn("파견횟수", min_value=0, max_value=int(top_staff['파견횟수'].max()))
                },
                use_container_width=True,
                hide_index=True,
                height=300
            )
        else:
            st.info("👥 배정 데이터가 없습니다.")
    
    # [Tab 4] 고객 현황
    with tab4:
        st.markdown('<div class="section-title">💼 체결된 고객사 (Top 10)</div>', unsafe_allow_html=True)
        
        top_customers = ud.get_top_customers(df_inq, top_n=10)
        if not top_customers.empty:
            # 파이 차트
            fig_cust = px.pie(
                top_customers,
                values='체결건수',
                names='고객사',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_cust.update_layout(
                margin=dict(l=10, r=10, t=10, b=10),
                height=350
            )
            st.plotly_chart(fig_cust, use_container_width=True)
            
            # 테이블
            st.dataframe(
                top_customers,
                column_config={
                    "순위": st.column_config.NumberColumn("순위", format="%d"),
                    "고객사": st.column_config.TextColumn("고객사"),
                    "체결건수": st.column_config.ProgressColumn("건수", min_value=0, max_value=int(top_customers['체결건수'].max()))
                },
                use_container_width=True,
                hide_index=True,
                height=300
            )
        else:
            st.info("💼 고객 데이터가 없습니다.")
    
    # [Tab 5] 정산 현황
    with tab5:
        st.markdown('<div class="section-title">💳 전체 정산 현황</div>', unsafe_allow_html=True)
        
        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            st.metric("📋 총 계약건수", len(df_settlement) if not df_settlement.empty else 0)
        with col_info2:
            # 입금여부 컬럼 우선 사용
            _col_progress = ud.find_col(df_settlement, ["입금여부", "진행상황", "상태", "입금상태"]) if not df_settlement.empty else None
            paid_count = len(df_settlement[df_settlement[_col_progress].astype(str).str.contains('완료', na=False)]) if _col_progress else 0
            st.metric("✅ 입금완료", paid_count)
        with col_info3:
            partial_count = len(df_settlement[df_settlement[_col_progress].astype(str).str.contains('부분', na=False)]) if _col_progress else 0
            st.metric("🔄 부분입금", partial_count)
        
        st.markdown("---")
        
        if not df_settlement.empty:
            st.dataframe(
                df_settlement.head(15),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("📊 정산 데이터가 없습니다.")
    
    # [Tab 6] 캘린더
    with tab6:
        # 불필요한 여백 제거 (radio/caption 위 여백 + iframe 주변 여백)
        st.markdown("""
        <style>
            /* 캘린더 탭 내부 여백 최소화 */
            [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"]:has(iframe[title="streamlit_calendar.calendar"]) {
                margin-top: -0.5rem;
                padding-top: 0;
            }
            /* radio 버튼 아래 여백 */
            [data-testid="stRadio"] { margin-bottom: -0.5rem; }
        </style>
        """, unsafe_allow_html=True)
        
        # 캘린더 필터 옵션
        cal_filter = st.radio("표시 범위", ["체결 건만", "전체"], horizontal=True, key="cal_range_filter")
        
        if cal_filter == "체결 건만":
            st.caption("📌 체결된 행사만 달력에 표시됩니다.")
            confirmed_statuses = sc.CONFIRMED_STATUSES
            if col_status:
                cal_df = df_inq[df_inq[col_status].astype(str).str.strip().isin(confirmed_statuses)]
            else:
                cal_df = df_inq
        else:
            st.caption("📌 전체 문의 건이 달력에 표시됩니다.")
            cal_df = df_inq

        events = ud.get_calendar_events(cal_df, df_dispatch)
        
        # 이벤트 건수 + 구글 캘린더 동기화 버튼
        _gcal_c1, _gcal_c2 = st.columns([3, 1])
        with _gcal_c1:
            if events:
                st.caption(f"📅 {len(events)}개 일정")
            else:
                st.caption("📅 표시할 일정이 없습니다.")
        with _gcal_c2:
            if events and st.button("🔄 구글 캘린더 동기화", key="gcal_sync_btn", use_container_width=True):
                try:
                    import google_calendar as gcal
                    available, msg = gcal.is_calendar_available()
                    if available:
                        with st.spinner("구글 캘린더에 동기화 중..."):
                            result = gcal.sync_all_events(events)
                        if result['success']:
                            st.success(f"✅ {result['synced']}건 동기화 완료!")
                        else:
                            st.warning(f"⚠️ {result['message']}")
                    else:
                        st.error(f"❌ {msg}")
                        st.info("💡 Google Cloud Console에서 Calendar API 활성화 후,\n서비스 계정을 캘린더에 공유해주세요.")
                except Exception as _ge:
                    st.error(f"동기화 오류: {_ge}")
        
        cal_options = {
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,listMonth"
            },
            "initialView": "dayGridMonth",
            "navLinks": True,
            "selectable": True,
            "contentHeight": 600,
            "locale": "ko",
            "dayMaxEvents": 3,
            "eventDisplay": "block",
        }
        
        # 범례 (한 줄 압축)
        st.markdown("""
        <div style="display:flex;gap:12px;margin:0 0 4px 0;font-size:11px;color:#6B7280;">
            <span>🟦체결/배정</span> <span>🟩완료/정산</span> <span>🟧접수/미정</span> <span>🟥취소</span>
        </div>
        """, unsafe_allow_html=True)
        
        try:
            calendar_css = """
                .fc {
                    min-height: 600px !important;
                    height: auto !important;
                }
                .fc .fc-scrollgrid {
                    min-height: 500px !important;
                }
                .fc .fc-scrollgrid-section-body > td {
                    height: 500px !important;
                }
                .fc .fc-daygrid-body {
                    min-height: 480px !important;
                }
                .fc .fc-toolbar { font-size: 14px; }
                .fc .fc-button { font-size: 13px; }
                .fc-h-event { cursor: pointer; }
                .fc td, .fc th { border-color: #e5e7eb; }
            """
            cal_result = calendar(
                events=events if events else [], 
                options=cal_options, 
                custom_css=calendar_css,
                callbacks=["dateClick", "eventClick"],
                key="main_calendar"
            )
        except Exception as e:
            st.warning(f"캘린더 렌더링 오류: {e}")
            st.info("대안으로 리스트 뷰를 표시합니다.")
            if events:
                for ev in events[:20]:
                    st.markdown(f"📅 **{ev.get('start', '')}** — {ev.get('title', '')}")
        
        if not events:
            st.info("📅 표시할 행사 일정이 없습니다. 문의접수에서 행사시작일을 입력해주세요.")
        
        # --- 캘린더 이벤트 클릭 시 상세카드 ---
        try:
            if cal_result and isinstance(cal_result, dict) and 'eventClick' in cal_result:
                clicked = cal_result['eventClick'].get('event', {})
                ep = clicked.get('extendedProps', {})
                c_evt = ep.get('event_name', '')
                c_client = ep.get('client_name', '')
                c_status = ep.get('status', '')
                c_need = int(ep.get('need', 0) or 0)
                c_assigned = int(ep.get('assigned', 0) or 0)
                c_names = ep.get('names', '') or '배정전'
                c_loc = ep.get('location', '') or '장소미입력'
                c_time = ep.get('time', '') or ''
                c_start = clicked.get('start', '')[:10] if clicked.get('start') else ''
                c_end_raw = clicked.get('end', '')
                c_end = c_end_raw[:10] if c_end_raw else c_start
                c_date_str = c_start + (f" ~ {c_end}" if c_end and c_end != c_start else '')
                
                # 배정 상세 (상태 포함)
                staff_detail = ud.get_dispatch_detail_for_event(df_dispatch, c_evt)
                if not staff_detail.empty:
                    staff_lines = []
                    for _, sr in staff_detail.iterrows():
                        sname = sr.get('인력명', '')
                        srole = sr.get('직무', '') if '직무' in sr.index else ''
                        sstatus = sr.get('상태', '') if '상태' in sr.index else ''
                        tag = f"<span style='background:#E5E7EB;padding:1px 6px;border-radius:4px;font-size:10px;'>{sstatus}</span>" if sstatus else ''
                        role_tag = f"<span style='color:#6B7280;font-size:11px;'>({srole})</span>" if srole else ''
                        staff_lines.append(f"{sname} {role_tag} {tag}")
                    staff_html = "<br/>".join(staff_lines)
                else:
                    staff_html = "🙅 배정된 인력이 없습니다."
                
                # 배정 상태 색상
                if c_need > 0 and c_assigned >= c_need:
                    assign_color = "#10B981"; assign_text = f"✅ {c_assigned}/{c_need}명 배정완료"
                elif c_assigned > 0:
                    assign_color = "#F59E0B"; assign_text = f"⚠️ {c_assigned}/{c_need}명 배정중"
                else:
                    assign_color = "#EF4444"; assign_text = f"❌ 0/{c_need}명 배정필요" if c_need > 0 else "미배정"
                
                st_cfg = sc.STATUS_CONFIG.get(c_status, {})
                st_icon = st_cfg.get('icon', '❓')
                st_bg = st_cfg.get('bg', '#f3f4f6')
                st_clr = st_cfg.get('color', '#6B7280')
                
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#F0F9FF,#EFF6FF);border:1px solid #BFDBFE;
                            border-left:5px solid #3B82F6;border-radius:10px;padding:18px 20px;
                            margin:12px 0 8px 0;box-shadow:0 3px 8px rgba(59,130,246,0.12);">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        <div>
                            <span style="font-size:16px;font-weight:700;color:#1E3A5F;">📌 {c_client} — {c_evt}</span>
                            <span style="background:{st_bg};color:{st_clr};padding:3px 8px;border-radius:6px;
                                        font-size:11px;font-weight:600;margin-left:8px;">{st_icon} {c_status}</span>
                        </div>
                        <span style="background:{assign_color};color:white;padding:4px 12px;border-radius:12px;
                                    font-size:12px;font-weight:600;">👥 {assign_text}</span>
                    </div>
                    <div style="display:flex;gap:24px;color:#4B5563;font-size:13px;margin-bottom:10px;">
                        <span>📅 {c_date_str}</span>
                        <span>📍 {c_loc}</span>
                        {f'<span>⏰ {c_time}</span>' if c_time else ''}
                    </div>
                    <div style="background:white;border-radius:6px;padding:10px 14px;border:1px solid #E5E7EB;">
                        <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:6px;">👤 배정 인력</div>
                        <div style="font-size:12px;color:#4B5563;line-height:1.8;">{staff_html}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            pass  # 클릭 이벤트 없음 — 정상
        
        st.markdown("---")
        st.markdown('<div class="section-title">📋 전체 현장 목록 (배정현황 포함)</div>', unsafe_allow_html=True)

        # 체결/미체결 필터
        filt_c1, filt_c2, filt_c3 = st.columns([1, 1, 2])
        with filt_c1:
            evt_filter = st.selectbox("📌 상태 필터", ["전체", "체결 건만", "미체결 건만"], key="evt_list_filter")
        with filt_c2:
            evt_search = st.text_input("🔎 검색", key="evt_list_search", placeholder="업체명/행사명")
        
        all_events = ud.get_all_events_with_status(df_inq, df_dispatch)
        if not all_events.empty:
            # 상태 필터 적용
            if evt_filter == "체결 건만" and '상태' in all_events.columns:
                all_events = all_events[all_events['상태'].astype(str).str.strip().isin(confirmed_statuses)]
            elif evt_filter == "미체결 건만" and '상태' in all_events.columns:
                non_confirmed = sc.STATUS_EXIT + [sc.STATUS_FLOW[0], sc.STATUS_FLOW[1]]  # 접수, 견적, 미체결, 보류, 취소
                all_events = all_events[all_events['상태'].astype(str).str.strip().isin(non_confirmed)]
            
            # 검색 필터
            if evt_search:
                q = evt_search.lower()
                mask = all_events.apply(lambda r: any(q in str(v).lower() for v in r.values), axis=1)
                all_events = all_events[mask]

            st.caption(f"총 {len(all_events)}건")

            for _, ev_row in all_events.iterrows():
                d_day = int(ev_row.get('D-Day', 0))
                evt_name = ev_row.get('행사명', '')
                evt_status = str(ev_row.get('상태', ''))
                assigned = int(ev_row.get('배정인원', 0))
                needed = int(ev_row.get('필요인원', 0))
                location = ev_row.get('장소', '')
                if not location or str(location).strip() == '' or pd.isna(location):
                    location = '장소미입력'
                
                # D-Day 색상
                if d_day < 0:
                    badge = "⏰ 종료"
                    badge_color = "#9CA3AF"
                elif d_day == 0:
                    badge = "🔴 당일"
                    badge_color = "#DC2626"
                elif d_day <= 3:
                    badge = f"🟠 D-{d_day}"
                    badge_color = "#F97316"
                elif d_day <= 7:
                    badge = f"🟡 D-{d_day}"
                    badge_color = "#EAB308"
                else:
                    badge = f"🟢 D-{d_day}"
                    badge_color = "#10B981"
                
                # 배정 현황
                if needed > 0:
                    fill_pct = min(100, int(assigned / needed * 100))
                    assign_text = f"{assigned}/{needed}명"
                else:
                    fill_pct = 100 if assigned > 0 else 0
                    assign_text = f"{assigned}명" if assigned > 0 else "미배정"
                
                assign_color = "#10B981" if fill_pct >= 100 else "#F59E0B" if fill_pct >= 50 else "#EF4444"
                
                # 배정 인력 이름
                staff_detail = ud.get_dispatch_detail_for_event(df_dispatch, evt_name)
                staff_names = ", ".join(staff_detail['인력명'].tolist()) if not staff_detail.empty else "배정전"
                
                start_dt = str(ev_row.get('시작일', ''))
                end_dt = str(ev_row.get('종료일', '')) if '종료일' in ev_row.index else ''
                date_str = f"{start_dt}" + (f" ~ {end_dt}" if end_dt and end_dt != start_dt else "")
                
                # 상태 뱃지
                evt_status = str(ev_row.get(col_status, ''))
                evt_st_cfg = sc.STATUS_CONFIG.get(evt_status, {})
                st_icon = evt_st_cfg.get('icon', '❓')
                st_bg = evt_st_cfg.get('bg', '#f3f4f6')
                st_clr = evt_st_cfg.get('color', '#6B7280')
                
                st.markdown(f"""
                <div style="background: white; border: 1px solid #E5E7EB; border-left: 4px solid {badge_color};
                            border-radius: 8px; padding: 14px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.06);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <div>
                            <span style="background: {badge_color}; color: white; padding: 3px 8px; border-radius: 4px;
                                        font-weight: bold; font-size: 11px; margin-right: 6px;">{badge}</span>
                            <b style="font-size: 14px; color: #111827;">{ev_row.get('업체', '')} - {evt_name}</b>
                            <span style="background: {st_bg}; color: {st_clr}; padding: 2px 7px; border-radius: 4px;
                                        font-size: 10px; font-weight: bold; margin-left: 6px;">{st_icon} {evt_status}</span>
                        </div>
                        <span style="background: {assign_color}; color: white; padding: 3px 10px; border-radius: 12px;
                                    font-size: 11px; font-weight: bold;">👥 {assign_text}</span>
                    </div>
                    <div style="color: #6B7280; font-size: 12px; margin-bottom: 4px;">
                        📍 {location}  |  📅 {date_str}
                    </div>
                    <div style="color: #6B7280; font-size: 12px;">
                        👤 <b>배정인력</b>: {staff_names}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("📅 등록된 행사가 없습니다.")
        
        # --- 미체결 처리 ---
        st.markdown("---")
        st.subheader("🚫 미체결 / 보류 / 취소 처리")
        non_confirmed_statuses = [sc.STATUS_FLOW[0], sc.STATUS_FLOW[1]]  # 접수, 견적
        cancelable_df = df_inq[df_inq[col_status].isin(non_confirmed_statuses)] if col_status in df_inq.columns else pd.DataFrame()
        
        if cancelable_df.empty:
            st.info("미체결 처리 가능한 건이 없습니다. (접수/견적 상태만 가능)")
        else:
            col_sel, col_reason, col_btn = st.columns([2, 2, 1])
            cancel_options = [f"{r.get('업체', '')} - {r.get('행사명', '')} ({r.get(col_status, '')})" for _, r in cancelable_df.iterrows()]
            with col_sel:
                sel_cancel = st.selectbox("대상 선택", cancel_options, key="dash_cancel_sel")
            with col_reason:
                cancel_action = st.selectbox("처리 유형", ["미체결", "보류", "취소"], key="dash_cancel_action")
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("처리 실행", type="primary", key="dash_cancel_btn"):
                    sel_idx = cancel_options.index(sel_cancel)
                    target_row = cancelable_df.iloc[sel_idx]
                    cid_val = str(target_row.get('관리번호', ''))
                    if cid_val:
                        import time as _time
                        db.update_status(cid_val, cancel_action)
                        st.success(f"✅ '{sel_cancel}' → {cancel_action} 처리 완료")
                        _time.sleep(1)
                        st.rerun()
                    else:
                        st.error("관리번호를 찾을 수 없습니다.")

    # [Tab 7] 자동화 리포트
    with tab7:
        st.markdown('<div class="section-title">📋 자동화 리포트</div>', unsafe_allow_html=True)
        
        report_type = st.radio("리포트 유형 선택", ["일일 보고서", "주간 성과", "월간 분석"], horizontal=True)
        
        col_download, col_copy = st.columns([1, 1])
        
        if report_type == "일일 보고서":
            report = ud.generate_daily_report(df_inq, df_dispatch, df_settlement)
            report_text = ud.format_report_text(report)
            
            st.subheader("📅 일일 보고서")
            
            # 섹션별 표시
            for section in report['섹션']:
                with st.container(border=True):
                    st.markdown(f"### {section['제목']}")
                    if isinstance(section['데이터'], list):
                        for item in section['데이터']:
                            st.markdown(f"• {item}")
                    elif isinstance(section['데이터'], dict):
                        for key, value in section['데이터'].items():
                            st.markdown(f"**{key}**: {value}")
            
            with col_download:
                st.download_button(
                    label="📥 텍스트로 다운로드",
                    data=report_text.encode('utf-8'),
                    file_name=f"일일보고서_{now_kst().strftime('%Y%m%d')}.txt",
                    mime="text/plain"
                )
        
        elif report_type == "주간 성과":
            report = ud.generate_weekly_report(df_inq, df_dispatch, df_settlement)
            report_text = ud.format_report_text(report)
            
            st.subheader("📊 주간 성과 리포트")
            st.caption(f"기간: {report['주간']}")
            
            # 섹션별 표시
            for section in report['섹션']:
                with st.container(border=True):
                    st.markdown(f"### {section['제목']}")
                    if isinstance(section['데이터'], list):
                        for item in section['데이터']:
                            st.markdown(f"• {item}")
                    elif isinstance(section['데이터'], dict):
                        for key, value in section['데이터'].items():
                            if isinstance(value, list):
                                st.markdown(f"**{key}**")
                                for item in value:
                                    st.markdown(f"  - {item}")
                            else:
                                st.markdown(f"**{key}**: {value}")
            
            with col_download:
                st.download_button(
                    label="📥 텍스트로 다운로드",
                    data=report_text.encode('utf-8'),
                    file_name=f"주간리포트_{now_kst().strftime('%Y%m%d')}.txt",
                    mime="text/plain"
                )
        
        else:  # 월간 분석
            report = ud.generate_monthly_report(df_inq, df_dispatch, df_settlement)
            report_text = ud.format_report_text(report)
            
            st.subheader("📈 월간 분석 리포트")
            st.caption(f"생성일: {report['생성일']}")
            
            # 섹션별 표시
            for section in report['섹션']:
                with st.container(border=True):
                    st.markdown(f"### {section['제목']}")
                    if isinstance(section['데이터'], list):
                        for item in section['데이터']:
                            st.markdown(f"• {item}")
                    elif isinstance(section['데이터'], dict):
                        for key, value in section['데이터'].items():
                            if isinstance(value, list):
                                st.markdown(f"**{key}**")
                                for item in value:
                                    st.markdown(f"  - {item}")
                            else:
                                st.markdown(f"**{key}**: {value}")
            
            with col_download:
                st.download_button(
                    label="📥 텍스트로 다운로드",
                    data=report_text.encode('utf-8'),
                    file_name=f"월간분석_{now_kst().strftime('%Y%m')}.txt",
                    mime="text/plain"
                )

    # [Tab 8] AI 분석
    with tab8:
        import ai_helper as ai
        
        st.markdown('<div class="section-title">🤖 AI 경영 분석</div>', unsafe_allow_html=True)
        st.caption("데이터 기반 AI 분석으로 경영 인사이트를 제공합니다")
        
        # AI 종합 요약
        exec_summary = ai.generate_executive_summary(df_inq, df_dispatch, df_settlement)
        st.markdown(f"""
        <div class="ai-box">
            <b>🤖 AI 경영 요약</b><br/>
            {exec_summary}
        </div>
        """, unsafe_allow_html=True)
        
        ai_tab1, ai_tab2, ai_tab3, ai_tab4 = st.tabs([
            "📈 매출 예측", "🚨 리스크 분석", "👥 인력 수요", "💼 고객 분석"
        ])
        
        with ai_tab1:
            st.markdown("##### 📈 향후 3개월 매출 예측")
            predictions = ai.predict_monthly_revenue(df_settlement, months_ahead=3)
            if predictions:
                for pred in predictions:
                    trend_icon = "📈" if "+" in pred['trend'] else "📉" if "-" in pred['trend'] else "➡️"
                    confidence_color = "#10B981" if pred['confidence'] == "높음" else "#F59E0B" if pred['confidence'] == "보통" else "#EF4444"
                    st.markdown(f"""
                    <div style="background:white;border:1px solid #E5E7EB;border-radius:8px;padding:14px;margin-bottom:8px;
                                display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <b>{pred['month']}</b>
                            <span style="color:#6B7280;font-size:12px;margin-left:8px;">{trend_icon} {pred['trend']}</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:12px;">
                            <span style="font-size:18px;font-weight:800;">₩{pred['predicted']:,}</span>
                            <span style="background:{confidence_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">
                                신뢰도: {pred['confidence']}
                            </span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("💡 매출 예측을 위해 더 많은 정산 데이터가 필요합니다.")
        
        with ai_tab2:
            st.markdown("##### 🚨 사업 리스크 분석")
            risks = ai.analyze_risks(df_inq, df_dispatch, df_settlement)
            if risks:
                for risk in risks:
                    level_color = "#DC2626" if risk['level'] == "높음" else "#F59E0B" if risk['level'] == "보통" else "#10B981"
                    st.markdown(f"""
                    <div style="background:#FFF;border:1px solid #E5E7EB;border-left:4px solid {level_color};
                                border-radius:8px;padding:12px;margin-bottom:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="font-weight:700;">{risk['type']}</span>
                            <span style="background:{level_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">
                                {risk['level']}
                            </span>
                        </div>
                        <div style="font-size:13px;color:#374151;">{risk['message']}</div>
                        <div style="font-size:12px;color:#6B7280;margin-top:4px;">💡 {risk['action']}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("✅ 현재 식별된 리스크가 없습니다!")
        
        with ai_tab3:
            st.markdown("##### 👥 향후 4주 인력 수요 예측")
            demand = ai.predict_staff_demand(df_inq, weeks_ahead=4)
            if demand:
                demand_df = pd.DataFrame(demand)
                if not demand_df.empty and demand_df['estimated_staff'].sum() > 0:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=demand_df['week'], 
                        y=demand_df['estimated_staff'],
                        text=demand_df['estimated_staff'],
                        textposition='outside',
                        marker_color='#667eea',
                        name='필요인력'
                    ))
                    fig.add_trace(go.Scatter(
                        x=demand_df['week'],
                        y=demand_df['events'],
                        mode='lines+markers+text',
                        text=demand_df['events'],
                        textposition='top center',
                        marker_color='#f5576c',
                        name='행사건수',
                        yaxis='y2'
                    ))
                    fig.update_layout(
                        margin=dict(l=10, r=10, t=30, b=10),
                        height=300,
                        yaxis=dict(title='필요인력(명)'),
                        yaxis2=dict(title='행사건수', overlaying='y', side='right'),
                        showlegend=True,
                        legend=dict(orientation='h', y=-0.15)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    total_demand = demand_df['estimated_staff'].sum()
                    st.info(f"📊 향후 4주간 총 예상 필요인력: **{total_demand}명** / 행사 {demand_df['events'].sum()}건")
                else:
                    st.info("💡 확정된 행사가 아직 없습니다.")
            else:
                st.info("💡 수요 예측을 위한 데이터가 부족합니다.")
        
        with ai_tab4:
            st.markdown("##### 💼 고객 분석")
            retention = ai.analyze_customer_retention(df_inq)
            
            if retention['total_customers'] > 0:
                rc1, rc2, rc3 = st.columns(3)
                rc1.metric("전체 고객사", f"{retention['total_customers']}사")
                rc2.metric("재계약률", f"{retention['retention_rate']}%")
                rc3.metric("이탈 위험", f"{len(retention['at_risk'])}사")
                
                if retention['top_loyal']:
                    st.markdown("**🏆 충성 고객 Top 5**")
                    for i, cust in enumerate(retention['top_loyal'], 1):
                        st.markdown(f"{i}. **{cust['company']}** — {cust['count']}회 거래")
                
                if retention['at_risk']:
                    st.markdown("**⚠️ 이탈 위험 고객 (90일+ 미거래)**")
                    for cust in retention['at_risk'][:5]:
                        st.markdown(f"- {cust['company']} ({cust['days_since']}일 전)")
            else:
                st.info("💡 고객 분석을 위한 데이터가 필요합니다.")

    # [Tab 9] 수익 분석
    with tab9:
        st.markdown('<div class="section-title">💎 수익성 분석 (영업이익)</div>', unsafe_allow_html=True)
        st.caption("공급가액 - 지급액 = 영업이익")
        
        # ── 핵심 수익 지표 ──
        pr_c1, pr_c2, pr_c3, pr_c4 = st.columns(4)
        pr_c1.metric("📦 공급가액", f"₩{operating_profit['공급가액']:,}")
        pr_c2.metric("💸 총 지급액", f"₩{operating_profit['지급액']:,}")
        
        profit_delta = f"{operating_profit['이익률']}%" if operating_profit['이익률'] != 0 else "0%"
        pr_c3.metric("💎 영업이익", f"₩{operating_profit['영업이익']:,}", delta=profit_delta)
        pr_c4.metric("📊 이익률", f"{operating_profit['이익률']}%")
        
        st.markdown("---")
        
        # ── 공급가액 vs 지급액 비교 차트 ──
        st.markdown("##### 📊 공급가액 vs 지급액 비교")
        fig_profit = go.Figure()
        fig_profit.add_trace(go.Bar(
            x=['공급가액', '지급액', '영업이익'],
            y=[operating_profit['공급가액'], operating_profit['지급액'], operating_profit['영업이익']],
            marker_color=['#3B82F6', '#EF4444', '#10B981' if operating_profit['영업이익'] >= 0 else '#DC2626'],
            text=[f"₩{operating_profit['공급가액']:,}", f"₩{operating_profit['지급액']:,}", f"₩{operating_profit['영업이익']:,}"],
            textposition='outside'
        ))
        fig_profit.update_layout(
            margin=dict(l=10, r=10, t=30, b=10), height=350,
            showlegend=False, yaxis_title="금액(원)", yaxis_tickformat=","
        )
        st.plotly_chart(fig_profit, use_container_width=True)
        
        st.markdown("---")
        
        # ── 견적 → 체결 전환 분석 ──
        st.markdown("##### 🎯 견적 → 체결 전환율 분석")
        conv_c1, conv_c2, conv_c3, conv_c4 = st.columns(4)
        conv_c1.metric("📋 견적 발송", f"{conversion['견적건수']}건")
        conv_c2.metric("📝 체결 완료", f"{conversion['체결건수']}건")
        conv_c3.metric("🎯 전환율", f"{conversion['전체전환율']}%")
        conv_c4.metric("⏳ 대기 중", f"{conversion['대기건수']}건")
        
        if conversion['견적건수'] > 0:
            fig_conv = go.Figure(data=[go.Pie(
                labels=['체결', '대기중', '미체결'],
                values=[
                    conversion['체결건수'],
                    conversion['대기건수'],
                    max(0, conversion['견적건수'] - conversion['체결건수'] - conversion['대기건수'])
                ],
                marker=dict(colors=['#10B981', '#F59E0B', '#EF4444']),
                hole=.4,
                textinfo='label+percent'
            )])
            fig_conv.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
            st.plotly_chart(fig_conv, use_container_width=True)
        
        # ── 미체결 경과 건 상세 ──
        if not stale_estimates.empty:
            st.markdown("---")
            st.markdown("##### ⏰ 견적 후 미체결 경과 건")
            st.warning(f"견적 발송 후 7일 이상 미체결 건이 {len(stale_estimates)}건 있습니다. 확인 필요!")
            st.dataframe(stale_estimates, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # ── 직군별 수익성 ──
        if not role_stats.empty and '총지급액' in role_stats.columns:
            st.markdown("##### 🔧 직군별 지급액 분포")
            fig_role_cost = px.pie(
                role_stats[role_stats['총지급액'] > 0],
                values='총지급액', names='직군',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_role_cost.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=350)
            st.plotly_chart(fig_role_cost, use_container_width=True)
        
        # ── 정산 건별 이익 상세 ──
        if not df_settlement.empty:
            st.markdown("---")
            st.markdown("##### 📋 건별 이익 현황")
            
            col_supply_s = ud.find_col(df_settlement, ["공급가액"])
            col_payment_s = ud.find_col(df_settlement, ["지급액"])
            col_profit_s = ud.find_col(df_settlement, ["이익"])
            col_client_s = ud.find_col(df_settlement, ["업체", "업체명"])
            col_event_s = ud.find_col(df_settlement, ["현장명", "행사명"])
            
            profit_cols = []
            if col_client_s: profit_cols.append(col_client_s)
            if col_event_s: profit_cols.append(col_event_s)
            if col_supply_s: profit_cols.append(col_supply_s)
            if col_payment_s: profit_cols.append(col_payment_s)
            if col_profit_s: profit_cols.append(col_profit_s)
            
            if len(profit_cols) >= 3:
                profit_df = df_settlement[profit_cols].copy()
                # 숫자 변환
                for nc in [col_supply_s, col_payment_s, col_profit_s]:
                    if nc and nc in profit_df.columns:
                        profit_df[nc] = profit_df[nc].apply(ud.safe_int)
                
                # 이익 컬럼이 없으면 계산
                if not col_profit_s and col_supply_s and col_payment_s:
                    profit_df['이익'] = profit_df[col_supply_s] - profit_df[col_payment_s]
                
                # 비어있지 않은 행만
                if col_supply_s:
                    profit_df = profit_df[profit_df[col_supply_s] > 0]
                
                if not profit_df.empty:
                    st.dataframe(profit_df, use_container_width=True, hide_index=True)
                else:
                    st.info("건별 이익 데이터가 없습니다.")
            else:
                st.info("정산 시트에 공급가액/지급액 컬럼이 필요합니다.")

    # [Tab 10] 미지급 인건비
    with tab10:
        st.markdown('<div class="section-title">💸 미지급 인건비 현황</div>', unsafe_allow_html=True)
        
        # 배정기록에서 미지급 건 추출 (지급내역 시트 기준으로 통일 판정)
        if not df_dispatch.empty:
            col_name = ud.find_col(df_dispatch, ["인력명", "이름", "성명"])
            col_venue = ud.find_col(df_dispatch, ["현장명", "행사명"])
            col_pay_amt = ud.find_col(df_dispatch, ["총지급액", "지급액"])
            col_date = ud.find_col(df_dispatch, ["파견일자", "파견기간", "날짜"])
            col_assign_id = ud.find_col(df_dispatch, ["배정ID"])
            col_pay_target = ud.find_col(df_dispatch, ["결제대상"])
            
            if col_name and col_pay_amt:
                _pay_df = df_dispatch.copy()

                # 팀원(결제대상=N)은 팀장 계좌로 일괄지급되므로 개별 미지급 목록에서 제외
                if col_pay_target and col_pay_target in _pay_df.columns:
                    _pay_df = _pay_df[_pay_df[col_pay_target].astype(str).str.strip().str.upper() != 'N'].copy()

                _pay_df['_지급액'] = _pay_df[col_pay_amt].apply(ud.safe_int)
                
                # 지급액 > 0인 건만 대상
                _pay_df = _pay_df[_pay_df['_지급액'] > 0].copy()
                
                if not _pay_df.empty:
                    # ── 지급내역 시트를 기준(Single Source of Truth)으로 판정 ──
                    # 완료 = 지급내역에서 배정ID의 지급상태가 '완료' 또는 '확인완료'
                    _completed_ids = set()   # 지급 완료된 배정ID
                    _pending_ids = set()     # 대기 중인 배정ID
                    _hq_confirmed_ids = set()  # 본사 확인완료 배정ID
                    
                    if not df_payment.empty:
                        col_paid_bid = ud.find_col(df_payment, ["배정ID"])
                        col_paid_status = ud.find_col(df_payment, ["지급상태"])
                        if col_paid_bid and col_paid_status:
                            for _, _pr in df_payment.iterrows():
                                _p_bid = str(_pr.get(col_paid_bid, '')).strip()
                                _p_st = str(_pr.get(col_paid_status, '')).strip()
                                if _p_st == '완료':
                                    _completed_ids.add(_p_bid)
                                elif _p_st == '확인완료':
                                    _hq_confirmed_ids.add(_p_bid)
                                    _completed_ids.add(_p_bid)  # 본사확인도 완료로 간주
                                elif _p_st == '대기':
                                    _pending_ids.add(_p_bid)
                    
                    # 본사인원 목록
                    _hq_names = [s['이름'] for s in db.HQ_STAFF] if hasattr(db, 'HQ_STAFF') else []
                    
                    # 각 행에 지급 상태 매핑
                    def _get_pay_status(row):
                        _bid = str(row.get(col_assign_id, '')).strip() if col_assign_id and col_assign_id in _pay_df.columns else ''
                        _name = str(row.get(col_name, '')).strip()
                        _is_hq = _name in _hq_names
                        if _bid in _completed_ids:
                            return '확인완료' if _bid in _hq_confirmed_ids else '완료'
                        elif _bid in _pending_ids:
                            return '대기'
                        else:
                            return '미저장'
                    
                    _pay_df['_상태'] = _pay_df.apply(_get_pay_status, axis=1)
                    _pay_df['_본사'] = _pay_df[col_name].astype(str).str.strip().isin(_hq_names) if col_name else False
                    
                    # 미지급 = 완료/확인완료가 아닌 모든 건
                    _unpaid_df = _pay_df[~_pay_df['_상태'].isin(['완료', '확인완료'])].copy()
                    
                    # 외부 인력만 (본사인원 제외한 순수 미지급)
                    _unpaid_ext = _unpaid_df[~_unpaid_df['_본사']].copy()
                    _unpaid_hq = _unpaid_df[_unpaid_df['_본사']].copy()
                    
                    # 완료 건수
                    _done_ext = len(_pay_df[(~_pay_df['_본사']) & (_pay_df['_상태'].isin(['완료']))])
                    _done_hq = len(_pay_df[(_pay_df['_본사']) & (_pay_df['_상태'].isin(['확인완료']))])
                    _total_ext = len(_pay_df[~_pay_df['_본사']])
                    _total_hq = len(_pay_df[_pay_df['_본사']])
                    
                    # KPI 카드
                    total_unpaid_pay = int(_unpaid_ext['_지급액'].sum())
                    total_unpaid_cnt = len(_unpaid_ext)
                    
                    kp1, kp2, kp3, kp4 = st.columns(4)
                    with kp1:
                        st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #FEF2F2, #FEE2E2); border-radius: 12px; padding: 16px; text-align: center; border: 1px solid #FECACA;">
                            <div style="font-size: 11px; color: #DC2626;">💸 미지급 총액</div>
                            <div style="font-size: 22px; font-weight: 800; color: #B91C1C;">{total_unpaid_pay:,}원</div>
                            <div style="font-size: 10px; color: #9CA3AF;">외부인력 기준 (본사 제외)</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with kp2:
                        st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #FFF7ED, #FFEDD5); border-radius: 12px; padding: 16px; text-align: center; border: 1px solid #FED7AA;">
                            <div style="font-size: 11px; color: #EA580C;">👤 미지급 인원</div>
                            <div style="font-size: 22px; font-weight: 800; color: #C2410C;">{total_unpaid_cnt}명</div>
                            <div style="font-size: 10px; color: #9CA3AF;">외부 {total_unpaid_cnt} | 본사 {len(_unpaid_hq)}명 미확인</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with kp3:
                        st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #F0FDF4, #DCFCE7); border-radius: 12px; padding: 16px; text-align: center; border: 1px solid #BBF7D0;">
                            <div style="font-size: 11px; color: #059669;">✅ 지급/확인 완료</div>
                            <div style="font-size: 22px; font-weight: 800; color: #047857;">{_done_ext + _done_hq}명</div>
                            <div style="font-size: 10px; color: #9CA3AF;">외부 {_done_ext}명 지급 | 본사 {_done_hq}명 확인</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with kp4:
                        _total_all = _total_ext + _total_hq
                        _done_all = _done_ext + _done_hq
                        pay_rate = int(_done_all / _total_all * 100) if _total_all > 0 else 0
                        rate_color = "#059669" if pay_rate >= 80 else "#D97706" if pay_rate >= 50 else "#DC2626"
                        st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #EFF6FF, #DBEAFE); border-radius: 12px; padding: 16px; text-align: center; border: 1px solid #BFDBFE;">
                            <div style="font-size: 11px; color: #2563EB;">📊 지급률</div>
                            <div style="font-size: 22px; font-weight: 800; color: {rate_color};">{pay_rate}%</div>
                            <div style="font-size: 10px; color: #9CA3AF;">{_done_all}/{_total_all}명 처리</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("---")
                    
                    # 미지급 목록
                    if not _unpaid_ext.empty:
                        st.markdown("##### 🚨 미지급 인력 목록")
                        
                        # 표시용 DataFrame 구성
                        display_cols_map = {}
                        if col_name: display_cols_map['인력명'] = col_name
                        if col_venue: display_cols_map['현장명'] = col_venue
                        if col_date: display_cols_map['파견일자'] = col_date
                        display_cols_map['지급액'] = '_지급액'
                        display_cols_map['상태'] = '_상태'
                        
                        valid_cols = {k: v for k, v in display_cols_map.items() if v in _unpaid_ext.columns}
                        _disp_df = _unpaid_ext[list(valid_cols.values())].copy()
                        _disp_df.columns = list(valid_cols.keys())
                        _disp_df = _disp_df.sort_values('지급액', ascending=False).reset_index(drop=True)
                        
                        col_config = {
                            "지급액": st.column_config.NumberColumn("💰 지급액", format="%d원"),
                            "상태": st.column_config.TextColumn("📋 상태", help="미저장=지급기록 미생성, 대기=기록 생성됨"),
                        }
                        
                        st.dataframe(_disp_df, use_container_width=True, hide_index=True, column_config=col_config)
                        
                        st.markdown(f"""
                        <div style="background: #FEF2F2; border-left: 4px solid #EF4444; padding: 12px; border-radius: 6px; margin-top: 10px;">
                            <b>🚨 미지급 합계: ₩{total_unpaid_pay:,}</b> ({total_unpaid_cnt}명)
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # 현장별 미지급 요약
                        if col_venue and col_venue in _unpaid_ext.columns:
                            st.markdown("##### 📍 현장별 미지급 요약")
                            _venue_summary = _unpaid_ext.groupby(_unpaid_ext[col_venue].astype(str).str.strip()).agg(
                                인원=('_지급액', 'count'),
                                미지급합계=('_지급액', 'sum'),
                            ).reset_index()
                            _venue_summary.columns = ['현장명', '인원', '미지급합계']
                            _venue_summary = _venue_summary.sort_values('미지급합계', ascending=False).reset_index(drop=True)
                            st.dataframe(
                                _venue_summary, use_container_width=True, hide_index=True,
                                column_config={
                                    "미지급합계": st.column_config.NumberColumn("💰 미지급합계", format="%d원"),
                                }
                            )
                    else:
                        st.success("🎉 외부인력 미지급 없음! 모든 급여가 지급 완료되었습니다.")
                    
                    # 본사인원 미확인 안내
                    if not _unpaid_hq.empty:
                        st.markdown("##### 🏢 본사인원 미확인")
                        st.caption("본사인원은 별도정산 대상이며, 확인 처리만 필요합니다.")
                        _hq_disp = []
                        for _, _hr in _unpaid_hq.iterrows():
                            _hq_disp.append({
                                '이름': str(_hr.get(col_name, '')),
                                '현장명': str(_hr.get(col_venue, '')) if col_venue else '',
                                '상태': str(_hr.get('_상태', '미저장')),
                            })
                        if _hq_disp:
                            st.dataframe(pd.DataFrame(_hq_disp), use_container_width=True, hide_index=True)
                    elif _total_hq > 0:
                        st.info(f"🏢 본사인원 {_done_hq}/{_total_hq}명 전원 확인 완료")
                else:
                    st.info("💡 지급 대상 배정 기록이 없습니다.")
            else:
                st.warning("⚠️ 배정기록에 인력명/지급액 컬럼이 필요합니다.")
        else:
            st.info("📋 배정 기록이 없습니다.")
