# page_staff_new.py
"""
👥 인력파견 시스템 v4.0 — 전면 리디자인
- 탭1: 🎯 인력배정 (견적품목 연동 + 다중배정 + 본사인원)
- 탭2: 📋 출석부 (일괄 출석 체크)
- 탭3: ⭐ 평가 (평가표 시트 실제 저장)
- 탭4: 💰 지급 (지급내역 시트 실제 저장)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from uuid import uuid4
import data_loader as db
import status_config as sc

# ==============================================================================
# 0. 스타일
# ==============================================================================

def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 1400px; padding-top: 1rem; }
        .stTabs [data-baseweb="tab-list"] button {
            font-size: 15px; font-weight: 700; padding: 10px 20px;
        }
        .stButton>button {
            border-radius: 8px; font-weight: 700;
            font-size: 13px;
        }
        .section-title {
            font-size: 18px; font-weight: 900; color: #0f2f3f;
            margin: 16px 0 12px 0; border-left: 5px solid #0f766e;
            padding-left: 12px;
        }
        .role-card {
            background: #f8fafc; border: 1px solid #e2e8f0;
            border-radius: 10px; padding: 12px 16px; margin-bottom: 8px;
        }
        .progress-fill {
            height: 8px; border-radius: 4px;
            transition: width 0.3s;
        }
        .hq-badge {
            background: #EDE9FE; color: #5B21B6;
            padding: 3px 10px; border-radius: 12px;
            font-size: 11px; font-weight: 700;
        }
        .ext-badge {
            background: #DBEAFE; color: #1E40AF;
            padding: 3px 10px; border-radius: 12px;
            font-size: 11px; font-weight: 700;
        }
    </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# 1. 탭1: 인력배정
# ==============================================================================

def tab_assignment(data):
    """인력배정 — 견적품목 기반 + 본사인원 + 다중배정"""

    df_inq = data.get('inq', pd.DataFrame())
    df_staff = data.get('staff', pd.DataFrame())

    # 배정 가능 계약 필터 (체결 / 배정완료 / 진행중)
    assignable = ['체결', '배정완료', '진행중']
    if df_inq.empty or '상태' not in df_inq.columns:
        st.warning("⚠️ 배정 가능한 계약이 없습니다.")
        return
    contracts = df_inq[df_inq['상태'].isin(assignable)].sort_values('작성일', ascending=False)
    if contracts.empty:
        st.info("📌 체결된 계약이 없습니다. 계약 체결 후 인력배정이 가능합니다.")
        return

    # ── Step 1: 계약 선택 ──
    st.markdown('<div class="section-title">📋 계약 선택</div>', unsafe_allow_html=True)
    options = {row['문의ID']: f"{row['업체명']} — {row['행사명']}  [{row['상태']}]"
               for _, row in contracts.iterrows()}
    sel_id = st.selectbox("계약", options.keys(), format_func=lambda x: options[x],
                          label_visibility="collapsed")
    sel = contracts[contracts['문의ID'] == sel_id].iloc[0]

    col_info = st.columns(4)
    col_info[0].metric("업체", sel.get('업체명', ''))
    col_info[1].metric("행사", sel.get('행사명', ''))
    col_info[2].metric("장소", sel.get('장소', '-'))
    col_info[3].metric("상태", sel.get('상태', ''))

    # ── Step 2: 필요 직군 현황 (견적품목 연동) ──
    st.markdown('<div class="section-title">📊 필요인력 현황</div>', unsafe_allow_html=True)

    est_items = db.load_estimate_items(sel_id)
    assignments_df = db.get_assignments_by_inquiry(sel_id)

    # 직군별 배정 현황 계산
    role_status = []
    if not est_items.empty:
        for _, item in est_items.iterrows():
            role_name = str(item.get('직군명', ''))
            needed = int(item.get('인원수', 0) or 0)
            # 해당 직군으로 배정된 인원 수
            assigned_count = 0
            if not assignments_df.empty:
                role_col = '직무' if '직무' in assignments_df.columns else '역할'
                if role_col in assignments_df.columns:
                    assigned_count = len(assignments_df[
                        assignments_df[role_col].astype(str).str.contains(role_name, na=False)
                    ])
            role_status.append({
                'role': role_name,
                'needed': needed,
                'assigned': assigned_count,
                'pay_rate': int(item.get('매입단가', 0) or 0),
                'days': int(item.get('일수', 0) or 0),
                'time': str(item.get('근무시간', '')),
            })
    else:
        st.caption("💡 견적서에 품목이 없어 자유 배정 모드입니다.")

    if role_status:
        cols = st.columns(min(len(role_status), 4))
        for i, rs in enumerate(role_status):
            pct = (rs['assigned'] / rs['needed'] * 100) if rs['needed'] > 0 else 0
            bar_color = "#10B981" if pct >= 100 else "#F59E0B" if pct > 0 else "#E5E7EB"
            with cols[i % len(cols)]:
                st.markdown(f"""
                <div class="role-card">
                    <div style="font-weight:700;font-size:14px;">{rs['role']}</div>
                    <div style="font-size:12px;color:#64748b;">단가 ₩{rs['pay_rate']:,} · {rs['days']}일 · {rs['time']}</div>
                    <div style="background:#E5E7EB;border-radius:4px;margin:6px 0;height:8px;">
                        <div class="progress-fill" style="width:{min(pct,100):.0f}%;background:{bar_color};"></div>
                    </div>
                    <div style="font-size:13px;font-weight:600;">
                        {rs['assigned']}/{rs['needed']}명
                        {'✅' if pct >= 100 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # ── Step 3: 인력 배정 ──
    st.markdown('<div class="section-title">🎯 인력 배정</div>', unsafe_allow_html=True)

    # 세션 초기화
    if 'assign_cart' not in st.session_state:
        st.session_state.assign_cart = []

    # 직군 선택
    role_options = [rs['role'] for rs in role_status] if role_status else []
    role_options.append("기타 (직접입력)")

    col_role, col_custom = st.columns([2, 1])
    with col_role:
        sel_role = st.selectbox("배정 직군", role_options, key="assign_role")
    with col_custom:
        if sel_role == "기타 (직접입력)":
            sel_role = st.text_input("직군명 입력", key="custom_role")
        else:
            st.empty()

    # 급여 자동 세팅
    role_info = next((rs for rs in role_status if rs['role'] == sel_role), None)
    default_rate = role_info['pay_rate'] if role_info else 100000
    default_days = role_info['days'] if role_info else 1

    # ── 본사 인원 배정 ──
    st.markdown("##### 🏢 본사 인원 배정")
    hq_cols = st.columns(len(db.HQ_STAFF) + 1)
    for i, hq in enumerate(db.HQ_STAFF):
        with hq_cols[i]:
            if st.button(f"➕ {hq['이름']}", key=f"hq_{hq['이름']}", use_container_width=True):
                st.session_state.assign_cart.append({
                    '인력명': hq['이름'],
                    '구분': '본사',
                    '직무': sel_role if sel_role else hq['직무'],
                    '지급단가': 0,
                    '근무일수': default_days,
                    '총지급액': 0,
                })
                st.rerun()

    # ── 외부 인력 검색 & 다중 선택 ──
    st.markdown("##### 👥 외부 인력 검색")
    col_search, col_filter = st.columns([2, 1])
    with col_search:
        search_q = st.text_input("이름 또는 지역 검색", placeholder="예: 김, 서울",
                                 key="staff_search", label_visibility="collapsed")
    with col_filter:
        gender_f = st.selectbox("성별", ["전체", "M", "F"], key="gender_f", label_visibility="collapsed")

    # AI 추천 또는 검색
    col_ai, col_manual = st.columns(2)
    do_ai = col_ai.button("🤖 AI 추천", use_container_width=True, type="primary", key="ai_btn")
    do_search = col_manual.button("🔍 검색", use_container_width=True, key="search_btn")

    if do_ai or do_search:
        with st.spinner("인력을 검색 중..."):
            if do_ai:
                from smart_assignment import SmartAssignment
                dispatch_data = db.load_dispatch_data()
                df_dispatch = dispatch_data.get('dispatch', pd.DataFrame())
                location = str(sel.get('장소', ''))
                result = SmartAssignment.ai_recommend(
                    staff_df=df_staff, dispatch_df=df_dispatch,
                    job_type=sel_role, location=location.split()[0] if location else None,
                    gender=gender_f if gender_f != "전체" else None,
                    top_n=15
                )
            else:
                result = df_staff.copy()
                if search_q:
                    mask = result['이름'].astype(str).str.contains(search_q, na=False)
                    if '이동가능지역' in result.columns:
                        mask = mask | result['이동가능지역'].astype(str).str.contains(search_q, na=False)
                    result = result[mask]
                if gender_f != "전체" and '성별' in result.columns:
                    result = result[result['성별'].astype(str) == gender_f]
                if '총점' in result.columns:
                    result['총점_n'] = pd.to_numeric(result['총점'], errors='coerce').fillna(0)
                    result = result.sort_values('총점_n', ascending=False)
                result = result.head(15)

            st.session_state.search_results = result
            st.session_state.search_done = True

    # 검색 결과 표시 + 체크박스
    if st.session_state.get('search_done') and not st.session_state.get('search_results', pd.DataFrame()).empty:
        results = st.session_state.search_results
        st.markdown(f"**{len(results)}명 검색됨**")

        selected_indices = []
        for idx, row in results.reset_index(drop=True).iterrows():
            name = row.get('이름', 'N/A')
            age = row.get('나이', '-')
            region = row.get('이동가능지역', '-')
            score = row.get('총점', '-')
            recommend = row.get('추천도', '-')
            ai_score = row.get('AI점수', '')
            ai_txt = f"  |  AI:{ai_score}" if ai_score != '' else ''
            label = f"{name}  |  {row.get('성별','-')}/{age}세  |  {region}  |  ⭐{score}  |  추천:{recommend}{ai_txt}"

            if st.checkbox(label, key=f"staff_sel_{idx}"):
                selected_indices.append(idx)

        # 선택한 인력 일괄 추가
        if selected_indices:
            pay_rate = st.number_input("지급단가 (원/일)", value=default_rate, step=10000, key="batch_rate")
            work_days = st.number_input("근무일수", value=default_days, min_value=1, key="batch_days")

            if st.button(f"✅ 선택한 {len(selected_indices)}명 배정 추가", type="primary",
                         use_container_width=True, key="add_selected"):
                for si in selected_indices:
                    row = results.iloc[si]
                    st.session_state.assign_cart.append({
                        '인력명': row.get('이름', ''),
                        '구분': '외부',
                        '직무': sel_role,
                        '지급단가': int(pay_rate),
                        '근무일수': int(work_days),
                        '총지급액': int(pay_rate) * int(work_days),
                    })
                st.rerun()

    # ── 배정 카트 ──
    cart = st.session_state.assign_cart
    if cart:
        st.markdown(f'<div class="section-title">🛒 배정 대기 ({len(cart)}명)</div>', unsafe_allow_html=True)
        cart_df = pd.DataFrame(cart)
        st.dataframe(cart_df, use_container_width=True, hide_index=True)

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("💾 배정 확정 (시트 저장)", type="primary", use_container_width=True, key="confirm_cart"):
                success_count = 0
                with st.spinner("배정 정보를 저장 중..."):
                    for item in cart:
                        assignment_dict = {
                            "배정ID": "",
                            "문의ID": sel_id,
                            "행사명": sel.get('행사명', ''),
                            "인력명": item['인력명'],
                            "구분": item['구분'],
                            "직무": item['직무'],
                            "연락처": "",
                            "지급단가": item['지급단가'],
                            "근무일수": item['근무일수'],
                            "총지급액": item['총지급액'],
                            "지급상태": "배정중",
                            "배정일시": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        }
                        if db.save_assignment_record(assignment_dict):
                            success_count += 1

                if success_count > 0:
                    _auto_update_status(sel_id, role_status)
                    st.session_state.assign_cart = []
                    st.cache_data.clear()
                    st.balloons()
                    st.success(f"✅ {success_count}명 배정 완료!")
                    st.rerun()
                else:
                    st.error("❌ 배정 저장 실패")

        with col_act2:
            if st.button("🗑️ 카트 비우기", use_container_width=True, key="clear_cart"):
                st.session_state.assign_cart = []
                st.rerun()

    # ── 이미 배정된 인력 ──
    st.markdown('<div class="section-title">📋 배정된 인력</div>', unsafe_allow_html=True)

    if st.button("🔄 새로고침", key="refresh_assignments"):
        st.cache_data.clear()
        st.rerun()

    assignments_df = db.get_assignments_by_inquiry(sel_id)
    if not assignments_df.empty:
        display_cols = ['인력명', '구분', '직무', '지급단가', '근무일수', '총지급액', '지급상태', '배정일시']
        rename_map = {'이름': '인력명', '역할': '직무', '단가': '지급단가', '일수': '근무일수', '상태': '지급상태'}
        for old, new in rename_map.items():
            if old in assignments_df.columns and new not in assignments_df.columns:
                assignments_df = assignments_df.rename(columns={old: new})
        avail = [c for c in display_cols if c in assignments_df.columns]

        st.dataframe(assignments_df[avail], use_container_width=True, hide_index=True)

        # 배정 관리
        st.markdown("##### 🔧 배정 관리")
        name_col = '인력명' if '인력명' in assignments_df.columns else '이름'
        assign_labels = [f"{row.get(name_col, 'N/A')} — {row.get('직무', row.get('역할', '-'))}"
                         for _, row in assignments_df.iterrows()]

        sel_assign_idx = st.selectbox("대상", range(len(assign_labels)),
                                       format_func=lambda x: assign_labels[x], key="manage_assign")
        sel_assign = assignments_df.iloc[sel_assign_idx]

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            if st.button("📊 확정", key="confirm_one", use_container_width=True):
                aid = sel_assign.get('배정ID', '')
                if aid and db.update_assignment_status(aid, '확정'):
                    _auto_update_status(sel_id, role_status)
                    st.cache_data.clear()
                    st.success(f"✅ 확정 완료!")
                    st.rerun()
        with col_m2:
            if st.button("❌ 취소", key="cancel_one", use_container_width=True):
                aid = sel_assign.get('배정ID', '')
                if aid and db.update_assignment_status(aid, '취소'):
                    st.cache_data.clear()
                    st.success("취소 완료")
                    st.rerun()
        with col_m3:
            total_assigned = len(assignments_df)
            total_hq = len(assignments_df[assignments_df['구분'].astype(str) == '본사']) if '구분' in assignments_df.columns else 0
            st.metric("현황", f"외부 {total_assigned - total_hq} + 본사 {total_hq}")
    else:
        st.info("👉 아직 배정된 인력이 없습니다.")


def _auto_update_status(inquiry_id, role_status):
    """필요 인원 대비 배정 현황 체크 → 자동 상태 전환"""
    try:
        st.cache_data.clear()
        assignments_df = db.get_assignments_by_inquiry(inquiry_id)
        if role_status:
            total_needed = sum(rs['needed'] for rs in role_status)
            total_assigned = len(assignments_df) if not assignments_df.empty else 0
            if total_needed > 0 and total_assigned >= total_needed:
                db.update_status(inquiry_id, sc.STATUS_FLOW[3])  # '배정완료'
        elif not assignments_df.empty:
            db.update_status(inquiry_id, sc.STATUS_FLOW[3])
    except Exception:
        pass


# ==============================================================================
# 2. 탭2: 출석부
# ==============================================================================

def tab_attendance(data):
    """출석부 — 배정 인력 일일 출석 체크"""
    df_inq = data.get('inq', pd.DataFrame())
    att_statuses = ['배정완료', '진행중']
    if df_inq.empty or '상태' not in df_inq.columns:
        st.warning("⚠️ 출석 기록 가능한 계약이 없습니다.")
        return

    contracts = df_inq[df_inq['상태'].isin(att_statuses)].sort_values('작성일', ascending=False)
    if contracts.empty:
        st.info("📌 배정완료 또는 진행중 상태의 계약이 필요합니다.")
        return

    options = {row['문의ID']: f"{row['업체명']} — {row['행사명']}"
               for _, row in contracts.iterrows()}
    sel_id = st.selectbox("계약", options.keys(), format_func=lambda x: options[x], key="att_contract")
    sel = contracts[contracts['문의ID'] == sel_id].iloc[0]

    assignments_df = db.get_assignments_by_inquiry(sel_id)
    if assignments_df.empty:
        st.info("이 계약에 배정된 인력이 없습니다.")
        return

    name_col = '인력명' if '인력명' in assignments_df.columns else '이름'
    rate_col = '지급단가' if '지급단가' in assignments_df.columns else '단가'

    st.markdown(f"**{sel.get('행사명', '')}** — 배정 인력 {len(assignments_df)}명")

    att_date = st.date_input("출석 날짜", value=datetime.now().date(), key="att_date")
    col_t1, col_t2 = st.columns(2)
    start_time = col_t1.time_input("출근", value=datetime.strptime("09:00", "%H:%M").time(), key="att_start")
    end_time = col_t2.time_input("퇴근", value=datetime.strptime("18:00", "%H:%M").time(), key="att_end")

    start_dt = datetime.combine(datetime.today(), start_time)
    end_dt = datetime.combine(datetime.today(), end_time)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    worked_hours = (end_dt - start_dt).total_seconds() / 3600
    st.caption(f"근무시간: {worked_hours:.1f}시간")

    st.markdown("##### 개인별 출석")
    att_records = []
    for idx, row in assignments_df.iterrows():
        name = row.get(name_col, 'N/A')
        assign_id = row.get('배정ID', '')
        category = row.get('구분', '외부')
        hourly_rate = int(row.get(rate_col, 0) or 0)
        daily_wage = int(worked_hours * (hourly_rate / 8)) if hourly_rate > 0 else 0
        badge = "🏢" if category == '본사' else "👤"

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"{badge} **{name}** — ₩{daily_wage:,}")
        with col2:
            status = st.selectbox("상태", ["출근", "지각", "조퇴", "결근"], key=f"att_st_{idx}")
        with col3:
            reason = st.text_input("사유", key=f"att_rs_{idx}", label_visibility="collapsed", placeholder="사유")

        att_records.append({
            '배정ID': assign_id, '문의ID': sel_id, '인력명': name,
            '출석날짜': att_date.strftime('%Y-%m-%d'),
            '출근시간': start_time.strftime('%H:%M'),
            '퇴근시간': end_time.strftime('%H:%M'),
            '근무시간': worked_hours, '일급여': daily_wage,
            '출석상태': status, '사유': reason,
            '비고': f'구분:{category}',
            '기록일시': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })

    if st.button("✅ 출석 일괄 저장", type="primary", use_container_width=True, key="save_att_batch"):
        saved = 0
        with st.spinner("출석 기록 저장 중..."):
            for rec in att_records:
                if db.save_attendance_record(rec):
                    saved += 1
        if saved > 0:
            try:
                if sel.get('상태', '') == '배정완료':
                    db.update_status(sel_id, sc.STATUS_FLOW[4])  # '진행중'
            except Exception:
                pass
            st.cache_data.clear()
            st.balloons()
            st.success(f"✅ {saved}명 출석 기록 완료!")


# ==============================================================================
# 3. 탭3: 평가
# ==============================================================================

def tab_evaluation(data):
    """평가 — 평가표 시트 실제 저장"""
    df_inq = data.get('inq', pd.DataFrame())
    eval_statuses = ['진행중', '완료']
    if df_inq.empty or '상태' not in df_inq.columns:
        st.warning("⚠️ 평가 가능한 계약이 없습니다.")
        return

    contracts = df_inq[df_inq['상태'].isin(eval_statuses)].sort_values('작성일', ascending=False)
    if contracts.empty:
        st.info("📌 진행중 또는 완료 상태의 계약이 필요합니다.")
        return

    options = {row['문의ID']: f"{row['업체명']} — {row['행사명']}"
               for _, row in contracts.iterrows()}
    sel_id = st.selectbox("계약", options.keys(), format_func=lambda x: options[x], key="eval_contract")
    sel = contracts[contracts['문의ID'] == sel_id].iloc[0]

    assignments_df = db.get_assignments_by_inquiry(sel_id)
    if assignments_df.empty:
        st.info("배정된 인력이 없습니다.")
        return

    name_col = '인력명' if '인력명' in assignments_df.columns else '이름'
    eval_labels = [f"{row.get(name_col, 'N/A')} — {row.get('직무', row.get('역할', ''))}"
                   for _, row in assignments_df.iterrows()]
    sel_idx = st.selectbox("평가 대상", range(len(eval_labels)),
                            format_func=lambda x: eval_labels[x], key="eval_target")
    target = assignments_df.iloc[sel_idx]

    st.markdown(f"**{target.get(name_col, '')}**")

    col1, col2, col3 = st.columns(3)
    s1 = col1.slider("근태", 1, 5, 3, key="e_s1")
    s2 = col2.slider("수행력", 1, 5, 3, key="e_s2")
    s3 = col3.slider("태도", 1, 5, 3, key="e_s3")
    col4, col5 = st.columns(2)
    s4 = col4.slider("의사소통", 1, 5, 3, key="e_s4")
    s5 = col5.slider("현장적응", 1, 5, 3, key="e_s5")

    total = round((s1 + s2 + s3 + s4 + s5) / 5, 1)
    grade = "A" if total >= 4.5 else "B" if total >= 3.5 else "C" if total >= 2.5 else "D"

    cr1, cr2, cr3 = st.columns(3)
    cr1.metric("총점", f"{total}")
    cr2.metric("등급", grade)
    cr3.metric("보너스", f"{'+10%' if grade=='A' else '+5%' if grade=='B' else '0%' if grade=='C' else '-5%'}")

    strengths = st.text_area("강점", key="e_str")
    improvements = st.text_area("개선점", key="e_imp")
    recommend = st.checkbox("재추천", value=total >= 3.5, key="e_rec")

    if st.button("✅ 평가 저장", type="primary", use_container_width=True, key="save_eval"):
        eval_dict = {
            '배정ID': target.get('배정ID', ''),
            '인력명': target.get(name_col, ''),
            '현장명': sel.get('행사명', ''),
            '근태': s1, '수행력': s2, '태도': s3, '의사소통': s4, '현장적응': s5,
            '총점': total, '평가등급': grade,
            '평가자': '', '평가일시': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '강점': strengths, '개선점': improvements,
            '재추천': 'Yes' if recommend else 'No', '비고': '',
        }
        with st.spinner("평가를 저장 중..."):
            if db.save_evaluation(eval_dict):
                st.cache_data.clear()
                st.balloons()
                st.success(f"✅ 평가 저장 완료!")
            else:
                st.error("❌ 평가 저장 실패")


# ==============================================================================
# 4. 탭4: 지급
# ==============================================================================

def tab_payment(data):
    """지급 — 출석 기반 급여 계산 + 지급내역 시트 저장"""
    df_inq = data.get('inq', pd.DataFrame())
    pay_statuses = ['진행중', '완료']
    if df_inq.empty or '상태' not in df_inq.columns:
        st.warning("⚠️ 지급 가능한 계약이 없습니다.")
        return

    contracts = df_inq[df_inq['상태'].isin(pay_statuses)].sort_values('작성일', ascending=False)
    if contracts.empty:
        st.info("📌 진행중 또는 완료 상태의 계약이 필요합니다.")
        return

    options = {row['문의ID']: f"{row['업체명']} — {row['행사명']}"
               for _, row in contracts.iterrows()}
    sel_id = st.selectbox("계약", options.keys(), format_func=lambda x: options[x], key="pay_contract")
    sel = contracts[contracts['문의ID'] == sel_id].iloc[0]

    assignments_df = db.get_assignments_by_inquiry(sel_id)
    if assignments_df.empty:
        st.info("배정된 인력이 없습니다.")
        return

    name_col = '인력명' if '인력명' in assignments_df.columns else '이름'
    rate_col = '지급단가' if '지급단가' in assignments_df.columns else '단가'
    days_col = '근무일수' if '근무일수' in assignments_df.columns else '일수'

    st.markdown(f"**{sel.get('행사명', '')}** — 급여 명세")

    pay_data = []
    for _, row in assignments_df.iterrows():
        name = row.get(name_col, '')
        category = row.get('구분', '외부')
        base_rate = int(row.get(rate_col, 0) or 0)
        days = int(row.get(days_col, 0) or 0)
        basic_pay = base_rate * days

        if category == '본사':
            pay_data.append({
                '인력명': name, '구분': '본사', '기본급': 0,
                '야근비': 0, '식사비': 0, '교통비': 0, '보너스': 0,
                '소계': 0, '세금공제': 0, '최종지급액': 0,
                '배정ID': row.get('배정ID', ''),
            })
        else:
            meal = 30000
            transport = 20000
            bonus = int(basic_pay * 0.05)
            subtotal = basic_pay + meal + transport + bonus
            tax = int(subtotal * 0.033)
            final = subtotal - tax
            pay_data.append({
                '인력명': name, '구분': '외부', '기본급': basic_pay,
                '야근비': 0, '식사비': meal, '교통비': transport, '보너스': bonus,
                '소계': subtotal, '세금공제': tax, '최종지급액': final,
                '배정ID': row.get('배정ID', ''),
            })

    pay_df = pd.DataFrame(pay_data)
    ext_pay = pay_df[pay_df['구분'] == '외부']

    c1, c2, c3 = st.columns(3)
    c1.metric("외부 인력", f"{len(ext_pay)}명")
    c2.metric("총 지급액", f"₩{int(ext_pay['최종지급액'].sum()):,}")
    c3.metric("세금공제", f"₩{int(ext_pay['세금공제'].sum()):,}")

    st.dataframe(
        pay_df[['인력명', '구분', '기본급', '식사비', '교통비', '보너스', '세금공제', '최종지급액']],
        use_container_width=True, hide_index=True
    )

    col_p1, col_p2 = st.columns(2)
    pay_date = col_p1.date_input("지급일", value=datetime.now().date(), key="pay_date")
    pay_status = col_p2.selectbox("지급상태", ["대기", "확정", "완료"], key="pay_status_sel")

    if st.button("💾 지급 내역 저장", type="primary", use_container_width=True, key="save_pay"):
        saved = 0
        with st.spinner("지급 내역 저장 중..."):
            for _, prow in pay_df.iterrows():
                if prow['구분'] == '본사':
                    continue
                period = f"{sel.get('행사시작일', '')}~{sel.get('행사종료일', '')}"
                pdays = 0
                match = assignments_df[assignments_df['배정ID'] == prow['배정ID']]
                if not match.empty:
                    pdays = int(match[days_col].iloc[0] or 0)
                payment_dict = {
                    '배정ID': prow['배정ID'], '인력명': prow['인력명'],
                    '현장명': sel.get('행사명', ''), '파견기간': period,
                    '파견일수': pdays, '기본급': prow['기본급'],
                    '야근비': prow['야근비'], '식사비': prow['식사비'],
                    '교통비': prow['교통비'], '보너스': prow['보너스'],
                    '소계': prow['소계'], '세금공제': prow['세금공제'],
                    '최종지급액': prow['최종지급액'],
                    '지급상태': pay_status,
                    '지급일': pay_date.strftime('%Y-%m-%d'),
                    '지급담당자': '', '비고': '',
                }
                if db.save_payment_record(payment_dict):
                    saved += 1

        if saved > 0:
            if pay_status == '완료':
                try:
                    db.update_status(sel_id, sc.STATUS_FLOW[6])  # '정산완료'
                except Exception:
                    pass
            st.cache_data.clear()
            st.balloons()
            st.success(f"✅ {saved}명 지급 내역 저장 완료!")
        else:
            st.error("❌ 저장 실패")


# ==============================================================================
# 5. 메인 페이지
# ==============================================================================

def show(data):
    apply_styles()
    st.title("👥 인력파견 시스템 v4.0")

    st.markdown("""
    <div style="background: linear-gradient(135deg, #EFF6FF, #F0FDF4); border: 1px solid #BFDBFE;
                border-radius: 12px; padding: 12px 18px; margin-bottom: 14px;">
        <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; flex-wrap: wrap;">
            <span style="background:#DBEAFE;color:#1E40AF;padding:4px 10px;border-radius:8px;font-weight:600;">1️⃣ 인력배정</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#D1FAE5;color:#065F46;padding:4px 10px;border-radius:8px;font-weight:600;">2️⃣ 출석부</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#EDE9FE;color:#5B21B6;padding:4px 10px;border-radius:8px;font-weight:600;">3️⃣ 평가</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#FEF3C7;color:#92400E;padding:4px 10px;border-radius:8px;font-weight:600;">4️⃣ 지급</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    dispatch_df = db.load_dispatch_sheet()
    if dispatch_df is None:
        dispatch_df = pd.DataFrame()

    c1, c2, c3 = st.columns(3)
    c1.metric("📋 총 배정", f"{len(dispatch_df)}명")
    if not dispatch_df.empty and '총지급액' in dispatch_df.columns:
        total = pd.to_numeric(dispatch_df['총지급액'], errors='coerce').sum()
        c2.metric("💰 예상 급여", f"₩{int(total):,}")
    else:
        c2.metric("💰 예상 급여", "₩0")
    hq_count = len(dispatch_df[dispatch_df['구분'].astype(str) == '본사']) if not dispatch_df.empty and '구분' in dispatch_df.columns else 0
    c3.metric("🏢 본사 투입", f"{hq_count}명")

    tab1, tab2, tab3, tab4 = st.tabs(["🎯 인력배정", "📋 출석부", "⭐ 평가", "💰 지급"])
    with tab1:
        tab_assignment(data)
    with tab2:
        tab_attendance(data)
    with tab3:
        tab_evaluation(data)
    with tab4:
        tab_payment(data)
