# page_dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import utils_dashboard as ud
import data_loader as db
from streamlit_calendar import calendar
from datetime import datetime, timedelta

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
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 메인 대시보드
# ==============================================================================
def show(data):
    apply_styles()
    st.title("🚀 Gradius 경영 대시보드")
    st.caption("실시간 사업 현황 통합 분석")
    
    df_inq = data['inq']
    
    # 배정 데이터와 정산 데이터 로드 (캐시됨)
    dispatch_data = db.load_dispatch_data()
    df_dispatch = dispatch_data.get('dispatch', pd.DataFrame())
    df_settlement = dispatch_data.get('settlement', pd.DataFrame())
    
    # 1. KPI 계산
    kpi = ud.calculate_kpi(df_inq)
    settlement_overview = ud.get_settlement_overview(df_settlement)
    unpaid_df = ud.get_unpaid_list(df_inq)
    pending_df = ud.get_pending_list(df_inq)
    
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
    briefing_colors = ["#FEF2F2", "#FFF7ED", "#F0FDF4"]
    briefing_borders = ["#EF4444", "#F97316", "#10B981"]
    
    for idx, item in enumerate(smart_briefing):
        color_idx = idx % len(briefing_colors)
        st.markdown(f"""
        <div style="background-color: {briefing_colors[color_idx]}; border-left: 4px solid {briefing_borders[color_idx]}; 
                    padding: 12px 15px; margin-bottom: 10px; border-radius: 6px; font-size: 13px; line-height: 1.6;">
            {item}
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 3. KPI 카드 (고도화된 디자인)
    st.subheader("📊 핵심 KPI")
    col_s, col_p, col_u, col_r = st.columns(4)
    
    with col_s:
        st.markdown(f"""
        <div class="metric-card sales">
            <div class="metric-label">💰 총 청구액</div>
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
    
    st.markdown("---")
    
    # 4. 탭 구성
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 분석", "🔥 긴급", "👥 인력", "💼 고객", "💰 정산", "📅 캘린더", "📋 리포트"
    ])
    
    # [Tab 1] 분석 차트
    with tab1:
        col_chart, col_ranking = st.columns([2, 1])
        
        with col_chart:
            st.markdown('<div class="section-title">📈 월별 매출 추이</div>', unsafe_allow_html=True)
            trend_df = ud.get_monthly_trend(df_inq)
            if not trend_df.empty:
                fig = px.bar(trend_df, x='Month', y='Sales', 
                           text_auto='.2s', color_discrete_sequence=['#667eea'])
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10), height=300,
                    showlegend=False, hovermode='x unified'
                )
                fig.update_yaxes(rangemode="tozero")
                fig.update_traces(marker_line=dict(width=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("📊 매출 데이터가 없습니다.")
        
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
        st.markdown('<div class="section-title">🚨 D-7 이내 투입 현장 (상세정보)</div>', unsafe_allow_html=True)
        
        upcoming_detail = ud.get_upcoming_dispatch_info(df_dispatch, df_inq, days=7)
        if not upcoming_detail.empty:
            for _, row in upcoming_detail.iterrows():
                d_day = int(row['D-Day'])
                if d_day == 0:
                    badge = "🔴 당일"
                    badge_color = "#DC2626"
                    priority = "가장 긴급"
                elif d_day <= 2:
                    badge = f"🟠 D-{d_day}"
                    badge_color = "#F97316"
                    priority = "긴급"
                else:
                    badge = f"🟡 D-{d_day}"
                    badge_color = "#EAB308"
                    priority = "확인필요"
                
                location = row['장소'] if pd.notna(row['장소']) and str(row['장소']).strip() else "장소정보없음"
                staff_count = int(row['배정인원'])
                
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
                    <div style="color: #6B7280; font-size: 13px;">
                        👥 <b>배정인원</b>: {staff_count}명
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ 급한 현장 없음 (앞으로 7일)")
        
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
        st.markdown('<div class="section-title">👥 가장 많이 파견된 인원 (Top 10)</div>', unsafe_allow_html=True)
        
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
            paid_count = len(df_settlement[df_settlement.iloc[:, 0].astype(str).str.contains('완료', na=False)]) if not df_settlement.empty else 0
            st.metric("✅ 입금완료", paid_count)
        with col_info3:
            partial_count = len(df_settlement[df_settlement.iloc[:, 0].astype(str).str.contains('부분', na=False)]) if not df_settlement.empty else 0
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
        st.markdown('<div class="section-title">📆 전체 행사 일정표</div>', unsafe_allow_html=True)
        st.caption("📌 행사 일정을 한 눈에 확인하세요. (클릭으로 날짜 선택 가능)")
        
        events = ud.get_calendar_events(df_inq)
        
        cal_options = {
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek"
            },
            "initialView": "dayGridMonth",
            "navLinks": True,
            "selectable": True,
            "height": "auto",
            "locale": "ko"
        }
        
        # 일정이 있든 없든 캘린더는 항상 표시
        calendar(events=events if events else [], options=cal_options)
        
        # 일정이 없을 때 안내 메시지
        if not events:
            st.info("📅 현재 등록된 행사 일정이 없습니다. 문의 시스템에 행사 일정을 추가하면 자동으로 나타납니다.")
        else:
            # 일정이 있을 때 요약 정보 표시
            st.markdown("---")
            st.markdown('<div class="section-title">📋 등록된 일정 목록</div>', unsafe_allow_html=True)
            
            # 일정을 표로 표시
            upcoming_events = ud.get_upcoming_events(df_inq, days=90)
            if not upcoming_events.empty:
                st.dataframe(
                    upcoming_events[[col for col in upcoming_events.columns if col != 'D-Day']],
                    use_container_width=True,
                    hide_index=True
                )

    
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
                    file_name=f"일일보고서_{datetime.now().strftime('%Y%m%d')}.txt",
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
                    file_name=f"주간리포트_{datetime.now().strftime('%Y%m%d')}.txt",
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
                    file_name=f"월간분석_{datetime.now().strftime('%Y%m')}.txt",
                    mime="text/plain"
                )
