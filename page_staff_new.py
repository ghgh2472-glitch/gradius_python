# page_staff_new.py
"""
👥 인력파견 시스템 v5.0 — 전면 개편
- 탭1: 🎯 인력배정 (고도화 검색 + 견적품목 연동 + 다중배정)
- 탭2: 📋 출석/근무 (견적 연동 시간 + 행사완료 처리)
- 탭3: ⭐ 평가 (STAFF DB 일치: 근태/수행/외모/팀워크)
- 탭4: 💰 지급 (수동 편집, 자동수당/세금 제외)
"""

import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta, date as dt_date
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
        .stButton>button { border-radius: 8px; font-weight: 700; font-size: 13px; }
        .section-title {
            font-size: 18px; font-weight: 900; color: #0f2f3f;
            margin: 16px 0 12px 0; border-left: 5px solid #0f766e;
            padding-left: 12px;
        }
        .role-card {
            background: #f8fafc; border: 1px solid #e2e8f0;
            border-radius: 10px; padding: 12px 16px; margin-bottom: 8px;
        }
        .progress-fill { height: 8px; border-radius: 4px; transition: width 0.3s; }
    </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# Helpers
# ==============================================================================

def _select_contract(df_inq, statuses, key_prefix):
    """배정 가능 계약 선택. 없으면 (None, None)"""
    if df_inq.empty or '상태' not in df_inq.columns:
        return None, None
    contracts = df_inq[df_inq['상태'].isin(statuses)].sort_values('작성일', ascending=False)
    if contracts.empty:
        return None, None
    options = {row['문의ID']: f"{row['업체명']} — {row['행사명']}  [{row['상태']}]"
               for _, row in contracts.iterrows()}
    sel_id = st.selectbox("계약 선택", options.keys(), format_func=lambda x: options[x],
                          key=f"{key_prefix}_contract", label_visibility="collapsed")
    sel = contracts[contracts['문의ID'] == sel_id].iloc[0]
    return sel_id, sel


def _parse_work_time(time_str):
    """근무시간 문자열 → (start_time, end_time). 예: '09:00~18:00', '9시-18시'"""
    default_s = datetime.strptime("09:00", "%H:%M").time()
    default_e = datetime.strptime("18:00", "%H:%M").time()
    if not time_str:
        return default_s, default_e
    m = re.search(r'(\d{1,2})[:\s시]?(\d{0,2}).*?[~\-–—].*?(\d{1,2})[:\s시]?(\d{0,2})', str(time_str))
    if m:
        try:
            sh, sm = int(m.group(1)), int(m.group(2) or 0)
            eh, em = int(m.group(3)), int(m.group(4) or 0)
            return (datetime.strptime(f"{sh:02d}:{sm:02d}", "%H:%M").time(),
                    datetime.strptime(f"{eh:02d}:{em:02d}", "%H:%M").time())
        except ValueError:
            pass
    return default_s, default_e


def _parse_date_safe(date_str):
    """날짜 문자열 → date 객체. 실패 시 None"""
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d', '%m/%d', '%m.%d'):
        try:
            d = datetime.strptime(str(date_str).strip(), fmt)
            if d.year < 2000:
                d = d.replace(year=datetime.now().year)
            return d.date()
        except ValueError:
            continue
    m = re.search(r'(\d{1,2})[.\-/](\d{1,2})', str(date_str))
    if m:
        try:
            return dt_date(datetime.now().year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return None


def _get_role_status(est_items, assignments_df):
    """견적품목과 배정기록에서 직군별 배정 현황 계산"""
    role_status = []
    if est_items.empty:
        return role_status
    for _, item in est_items.iterrows():
        role_name = str(item.get('직군명', ''))
        needed = int(item.get('인원수', 0) or 0)
        assigned_count = 0
        if not assignments_df.empty:
            role_col = '직무' if '직무' in assignments_df.columns else '역할'
            if role_col in assignments_df.columns:
                assigned_count = len(assignments_df[
                    assignments_df[role_col].astype(str).str.contains(role_name, na=False)])
        role_status.append({
            'role': role_name, 'needed': needed, 'assigned': assigned_count,
            'pay_rate': int(item.get('매입단가', 0) or 0),
            'days': int(item.get('일수', 0) or 0),
            'time': str(item.get('근무시간', '')),
        })
    return role_status


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


def _search_staff(df_staff, search_q, gender_f, age_filter, rec_filter,
                  role_filter, region_filter, min_height, min_score,
                  english_f, driving_f):
    """STAFF DB 고도화 검색 — 모든 필터 직접 적용"""
    result = df_staff.copy()

    # 1. 텍스트 검색 (이름 / 지역 / 직무 OR 검색)
    if search_q:
        sq = search_q.strip()
        mask = result['이름'].astype(str).str.contains(sq, na=False, case=False)
        for col in ['이동가능지역', '가능직무', '거주지']:
            if col in result.columns:
                mask = mask | result[col].astype(str).str.contains(sq, na=False, case=False)
        result = result[mask]

    # 2. 성별
    if gender_f and gender_f != "전체" and '성별' in result.columns:
        result = result[result['성별'].astype(str).str.strip() == gender_f]

    # 3. 연령대
    if age_filter and '연령대' in result.columns:
        result = result[result['연령대'].astype(str).isin(age_filter)]

    # 4. 추천도
    if rec_filter and '추천도' in result.columns:
        result = result[result['추천도'].astype(str).isin(rec_filter)]

    # 5. 가능직무
    if role_filter and '가능직무' in result.columns:
        kws = [k.strip() for k in role_filter.split(',') if k.strip()]
        mask = pd.Series([False] * len(result), index=result.index)
        for kw in kws:
            mask = mask | result['가능직무'].astype(str).str.contains(kw, na=False, case=False)
        result = result[mask]

    # 6. 이동가능지역
    if region_filter:
        r_col = '이동가능지역' if '이동가능지역' in result.columns else '거주지' if '거주지' in result.columns else None
        if r_col:
            kws = [k.strip() for k in region_filter.split(',') if k.strip()]
            mask = pd.Series([False] * len(result), index=result.index)
            for kw in kws:
                mask = mask | result[r_col].astype(str).str.contains(kw, na=False, case=False)
            result = result[mask]

    # 7. 키
    if min_height and min_height > 0 and '키' in result.columns:
        result['_키n'] = pd.to_numeric(
            result['키'].astype(str).str.extract(r'(\d+)', expand=False), errors='coerce').fillna(0)
        result = result[result['_키n'] >= min_height]

    # 8. 총점
    if min_score and min_score > 0 and '총점' in result.columns:
        result['_점수n'] = pd.to_numeric(result['총점'], errors='coerce').fillna(0)
        result = result[result['_점수n'] >= min_score]

    # 9. 영어
    if english_f == "가능" and '영어' in result.columns:
        result = result[result['영어'].astype(str).str.contains('가능|O|Yes|Native', na=False, case=False)]

    # 10. 운전
    if driving_f == "가능" and '운전' in result.columns:
        result = result[result['운전'].astype(str).str.contains('가능|O|Yes|1종|2종', na=False, case=False)]

    # 정렬: 추천도 → 총점
    rec_map = {'우선투입': 1, '일반': 2, '보류': 3}
    if '추천도' in result.columns:
        result['_rec'] = result['추천도'].map(rec_map).fillna(9)
    else:
        result['_rec'] = 9
    if '총점' in result.columns:
        result['_scr'] = pd.to_numeric(result['총점'], errors='coerce').fillna(0)
    else:
        result['_scr'] = 0
    result = result.sort_values(['_rec', '_scr'], ascending=[True, False])

    return result.head(20)


# ==============================================================================
# 1. 탭1: 인력배정 (좌우분할 UI)
# ==============================================================================

def tab_assignment(data):
    """인력배정 — 좌: 검색/추가 | 우: 배정현황 실시간 표시"""
    df_inq = data.get('inq', pd.DataFrame())
    df_staff = data.get('staff', pd.DataFrame())

    sel_id, sel = _select_contract(df_inq, ['체결', '배정완료', '진행중'], "assign")
    if sel_id is None:
        st.info("📌 체결된 계약이 없습니다. 계약 체결 후 인력배정이 가능합니다.")
        return

    ci = st.columns(4)
    ci[0].metric("업체", sel.get('업체명', ''))
    ci[1].metric("행사", sel.get('행사명', ''))
    ci[2].metric("장소", sel.get('장소', '-'))
    ci[3].metric("상태", sel.get('상태', ''))

    # ── 배정 스킵 (위약금/취소 케이스) ──
    current_status = str(sel.get('상태', '')).strip()
    if current_status == '체결':
        with st.expander("⏭️ 배정 불필요 (위약금/취소 등)", expanded=False):
            st.warning("⚠️ 인력 배정 없이 정산으로 바로 넘어갑니다.")
            skip_memo = st.text_input("사유 메모 (선택)", placeholder="예: 고객 취소, 위약금 50%", key="skip_memo")
            if st.button("✅ 배정 스킵 → 완료 상태로 전환", type="secondary", key="skip_assignment"):
                # 바로 '완료' 상태로 전환
                db.update_status(sel_id, sc.STATUS_FLOW[5])  # '완료'
                st.cache_data.clear()
                st.success(f"✅ '{sel.get('행사명', '')}'이(가) 완료 상태로 전환되었습니다.")
                if skip_memo:
                    st.info(f"📝 메모: {skip_memo}")
                st.rerun()

    # ── 필요 직군 현황 ──
    st.markdown('<div class="section-title">📊 필요인력 현황</div>', unsafe_allow_html=True)
    est_items = db.load_estimate_items(sel_id)
    assignments_df = db.get_assignments_by_inquiry(sel_id)
    role_status = _get_role_status(est_items, assignments_df)

    if not role_status:
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
                    <div style="font-size:12px;color:#64748b;">₩{rs['pay_rate']:,}/일 · {rs['days']}일 · {rs['time']}</div>
                    <div style="background:#E5E7EB;border-radius:4px;margin:6px 0;height:8px;">
                        <div class="progress-fill" style="width:{min(pct,100):.0f}%;background:{bar_color};"></div>
                    </div>
                    <div style="font-size:13px;font-weight:600;">{rs['assigned']}/{rs['needed']}명 {'✅' if pct >= 100 else ''}</div>
                </div>
                """, unsafe_allow_html=True)

    # ================================================================
    # 좌우 분할 레이아웃
    # ================================================================
    col_left, col_right = st.columns([1.3, 1])

    # ── 왼쪽: 검색 & 추가 ──
    with col_left:
        st.markdown('<div class="section-title">🎯 인력 배정</div>', unsafe_allow_html=True)
        if 'assign_cart' not in st.session_state:
            st.session_state.assign_cart = []
        if 'team_members' not in st.session_state:
            st.session_state.team_members = []

        # ══════════════════════════════════════════════════════════════
        # 배정 유형 선택: 개별 / 팀
        # ══════════════════════════════════════════════════════════════
        assign_type = st.radio("배정 유형", ["개별 배정", "👥 팀 배정"], horizontal=True, key="assign_type")
        
        st.divider()

        # 직군 선택 (공통)
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

        role_info = next((rs for rs in role_status if rs['role'] == sel_role), None)
        default_rate = role_info['pay_rate'] if role_info else 100000
        default_days = role_info['days'] if role_info else 1

        # ══════════════════════════════════════════════════════════════
        # 팀 배정 모드
        # ══════════════════════════════════════════════════════════════
        if assign_type == "👥 팀 배정":
            st.markdown("##### 👤 팀장 선택 (STAFF에서 검색)")
            
            # 팀장 검색
            leader_search = st.text_input("🔍 팀장 이름 검색", placeholder="예: 강정호", key="leader_search")
            
            if leader_search:
                mask = df_staff['이름'].astype(str).str.contains(leader_search, na=False, case=False)
                leaders = df_staff[mask].head(10)
                
                if not leaders.empty:
                    leader_options = {
                        idx: f"{row.get('이름', '')} | {row.get('성별', '-')} | {row.get('가능직무', '-')}"
                        for idx, row in leaders.iterrows()
                    }
                    sel_leader_idx = st.selectbox(
                        "팀장 선택", list(leader_options.keys()),
                        format_func=lambda x: leader_options[x],
                        key="sel_leader"
                    )
                    selected_leader = leaders.loc[sel_leader_idx]
                    st.success(f"✅ 팀장: **{selected_leader.get('이름', '')}**")
                else:
                    st.warning("검색 결과가 없습니다.")
                    selected_leader = None
            else:
                selected_leader = None
            
            st.markdown("##### 👥 팀원 추가 (수기 입력)")
            st.caption("팀원은 STAFF에 없어도 됩니다. 이름만 입력하세요.")
            
            # 팀원 추가 입력
            col_add, col_btn = st.columns([3, 1])
            with col_add:
                new_member = st.text_input("팀원 이름", placeholder="예: 김철수", key="new_member", label_visibility="collapsed")
            with col_btn:
                if st.button("➕ 추가", key="add_member"):
                    if new_member.strip():
                        st.session_state.team_members.append(new_member.strip())
                        st.rerun()
            
            # 현재 팀원 목록 표시
            if st.session_state.team_members:
                st.markdown(f"**현재 팀원:** {len(st.session_state.team_members)}명")
                for i, member in enumerate(st.session_state.team_members):
                    mc1, mc2 = st.columns([4, 1])
                    mc1.write(f"• {member}")
                    if mc2.button("🗑️", key=f"del_member_{i}"):
                        st.session_state.team_members.pop(i)
                        st.rerun()
            
            st.divider()
            
            # 팀 단가 설정
            col_rate, col_days = st.columns(2)
            with col_rate:
                team_rate = st.number_input("인당 단가 (원/일)", value=default_rate, step=10000, key="team_rate")
            with col_days:
                team_days = st.number_input("근무일수", value=default_days, min_value=1, key="team_days")
            
            # 팀 합계 계산
            team_size = 1 + len(st.session_state.team_members)  # 팀장 + 팀원
            team_total = team_rate * team_days * team_size
            
            st.info(f"""
            📊 **팀 합계**
            - 팀 인원: {team_size}명 (팀장 1 + 팀원 {len(st.session_state.team_members)})
            - 총 지급액: **{team_total:,}원** → 팀장 계좌로 지급
            """)
            
            # 팀 배정 추가 버튼
            if st.button("✅ 팀 배정 추가", type="primary", use_container_width=True, key="add_team"):
                if selected_leader is None:
                    st.error("팀장을 선택해주세요.")
                else:
                    # 팀코드 생성
                    from uuid import uuid4
                    team_code = f"T-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:4]}"
                    leader_name = selected_leader.get('이름', '')
                    
                    # 팀장 추가 (결제대상 = Y)
                    st.session_state.assign_cart.append({
                        '인력명': leader_name, '구분': '팀장',
                        '직무': sel_role, '지급단가': int(team_rate),
                        '근무일수': int(team_days), '총지급액': int(team_rate * team_days),
                        '팀코드': team_code, '결제대상': 'Y',
                    })
                    
                    # 팀원 추가 (결제대상 = N)
                    for member in st.session_state.team_members:
                        st.session_state.assign_cart.append({
                            '인력명': member, '구분': '팀원',
                            '직무': sel_role, '지급단가': int(team_rate),
                            '근무일수': int(team_days), '총지급액': int(team_rate * team_days),
                            '팀코드': team_code, '결제대상': 'N',
                        })
                    
                    # 팀원 목록 초기화
                    st.session_state.team_members = []
                    st.success(f"✅ {leader_name}팀 ({team_size}명) 배정 추가!")
                    st.rerun()

        # ══════════════════════════════════════════════════════════════
        # 개별 배정 모드 (기존)
        # ══════════════════════════════════════════════════════════════
        else:
            # ── 본사 인력 ──
            st.markdown("##### 🏢 본사 인원 배정")
            hq_cols = st.columns(min(len(db.HQ_STAFF) + 1, 5))
            for i, hq in enumerate(db.HQ_STAFF):
                with hq_cols[i % len(hq_cols)]:
                    if st.button(f"➕ {hq['이름']}", key=f"hq_{hq['이름']}", use_container_width=True):
                        st.session_state.assign_cart.append({
                            '인력명': hq['이름'], '구분': '본사',
                            '직무': sel_role if sel_role else hq['직무'],
                            '지급단가': 0, '근무일수': default_days, '총지급액': 0,
                            '팀코드': '', '결제대상': 'Y',
                        })
                        st.rerun()

            # ── 외부 인력 검색 ──
            st.markdown("##### 👥 외부 인력 검색")
            col_name, col_gender = st.columns([3, 1])
            with col_name:
                search_q = st.text_input("🔍 이름 / 지역 / 직무 검색", placeholder="예: 김, 서울, 경호",
                                         key="staff_search")
            with col_gender:
                gender_f = st.radio("성별", ["전체", "M", "F"], horizontal=True, key="gender_f")

            with st.expander("🔧 상세 필터", expanded=False):
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    age_filter = st.multiselect("연령대", ["20대", "30대", "40대", "50대↑"], key="age_f")
                    rec_filter = st.multiselect("추천도", ["우선투입", "일반", "보류"], key="rec_f")
                with fc2:
                    role_filter = st.text_input("가능직무", placeholder="예: 경호, 안내", key="role_f")
                    region_filter = st.text_input("이동가능지역", placeholder="예: 서울, 경기", key="region_f")
                with fc3:
                    min_height = st.number_input("최소 키(cm)", min_value=0, value=0, step=5, key="height_f")
                    min_score = st.number_input("최소 총점", min_value=0, value=0, step=10, key="score_f")
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        english_f = st.selectbox("영어", ["무관", "가능"], key="eng_f")
                    with ec2:
                        driving_f = st.selectbox("운전", ["무관", "가능"], key="drv_f")

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
                        g_val = gender_f if gender_f != "전체" else None
                        result = SmartAssignment.ai_recommend(
                            staff_df=df_staff, dispatch_df=df_dispatch,
                            job_type=sel_role, location=location.split()[0] if location else None,
                            gender=g_val, top_n=20)
                    else:
                        result = _search_staff(
                            df_staff, search_q, gender_f, age_filter, rec_filter,
                            role_filter, region_filter, min_height, min_score,
                            english_f, driving_f)

                    st.session_state.search_results = result
                    st.session_state.search_done = True

            # 검색 결과 (컴팩트)
            if st.session_state.get('search_done') and not st.session_state.get('search_results', pd.DataFrame()).empty:
                results = st.session_state.search_results
                st.markdown(f"**{len(results)}명 검색됨**")

                selected_indices = []
                for idx, row in results.reset_index(drop=True).iterrows():
                    name = row.get('이름', 'N/A')
                    gender = row.get('성별', '-')
                    age = row.get('나이', '-')
                    region = row.get('이동가능지역', row.get('거주지', '-'))
                    role = row.get('가능직무', '-')
                    height = row.get('키', '-')
                    score = row.get('총점', '-')
                    recommend = row.get('추천도', '-')
                    ai_score = row.get('AI점수', '')
                    ai_txt = f" · AI:{ai_score}" if ai_score != '' else ''

                    label = (f"{name}  |  {gender}/{age}  |  📍{region}  |  🔧{role}  "
                             f"|  📏{height}cm  |  ⭐{score}  |  {recommend}{ai_txt}")

                    if st.checkbox(label, key=f"staff_sel_{idx}"):
                        selected_indices.append(idx)

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
                                '팀코드': '', '결제대상': 'Y',
                            })
                        st.rerun()

    # ── 오른쪽: 배정 현황 실시간 ──
    with col_right:
        # 배정 카트
        cart = st.session_state.get('assign_cart', [])
        if cart:
            st.markdown(f'<div class="section-title">🛒 배정 대기 ({len(cart)}명)</div>', unsafe_allow_html=True)
            cart_df = pd.DataFrame(cart)
            st.dataframe(cart_df, use_container_width=True, hide_index=True, height=min(200, 35 * len(cart) + 38))

            # 개별 삭제
            for ci_idx in range(len(cart)):
                item = cart[ci_idx]
                dc1, dc2 = st.columns([3, 1])
                with dc2:
                    if st.button(f"🗑️", key=f"del_cart_{ci_idx}", help=f"{item['인력명']} 제거"):
                        st.session_state.assign_cart.pop(ci_idx)
                        st.rerun()

            col_act1, col_act2 = st.columns(2)
            with col_act1:
                if st.button("💾 배정 확정", type="primary", use_container_width=True, key="confirm_cart"):
                    success_count = 0
                    with st.spinner("배정 정보를 저장 중..."):
                        for item in cart:
                            assignment_dict = {
                                "배정ID": "", "문의ID": sel_id,
                                "행사명": sel.get('행사명', ''),
                                "인력명": item['인력명'], "구분": item['구분'],
                                "직무": item['직무'], "연락처": "",
                                "지급단가": item['지급단가'], "근무일수": item['근무일수'],
                                "총지급액": item['총지급액'], "지급상태": "배정중",
                                "배정일시": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "팀코드": item.get('팀코드', ''),
                                "결제대상": item.get('결제대상', 'Y'),
                            }
                            if db.save_assignment_record(assignment_dict):
                                success_count += 1
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
                if st.button("🗑️ 전체 비우기", use_container_width=True, key="clear_cart"):
                    st.session_state.assign_cart = []
                    st.rerun()
        else:
            st.markdown('<div class="section-title">🛒 배정 대기</div>', unsafe_allow_html=True)
            st.info("👈 왼쪽에서 인력을 검색하고 추가하세요")

        # ── 배정된 인력 ──
        st.markdown('<div class="section-title">📋 배정된 인력</div>', unsafe_allow_html=True)
        if st.button("🔄 새로고침", key="refresh_assignments"):
            st.cache_data.clear()
            st.rerun()

        assignments_df = db.get_assignments_by_inquiry(sel_id)
        if not assignments_df.empty:
            # 팀코드가 있으면 표시
            display_cols = ['인력명', '구분', '팀코드', '직무', '지급단가', '근무일수', '총지급액', '지급상태', '결제대상']
            avail = [c for c in display_cols if c in assignments_df.columns]
            st.dataframe(assignments_df[avail], use_container_width=True, hide_index=True,
                         height=min(300, 35 * len(assignments_df) + 38))
            
            # 팀별 요약 표시
            if '팀코드' in assignments_df.columns:
                team_df = assignments_df[assignments_df['팀코드'].astype(str).str.strip() != '']
                if not team_df.empty:
                    st.markdown("##### 👥 팀 배정 요약")
                    for team_code in team_df['팀코드'].unique():
                        team_members = team_df[team_df['팀코드'] == team_code]
                        leader = team_members[team_members['구분'].astype(str) == '팀장']
                        leader_name = leader['인력명'].iloc[0] if not leader.empty else '?'
                        member_count = len(team_members)
                        team_total = team_members['총지급액'].astype(int).sum() if '총지급액' in team_members.columns else 0
                        st.info(f"👤 **{leader_name}팀** ({member_count}명) — 합계: {team_total:,}원 → 팀장 지급")

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
                        st.success("✅ 확정!")
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


# ==============================================================================
# 2. 탭2: 출석/근무 관리
# ==============================================================================

def tab_attendance(data):
    """출석부 — 견적 연동 시간/날짜 + 스케줄표 + 행사완료 처리"""
    df_inq = data.get('inq', pd.DataFrame())
    sel_id, sel = _select_contract(df_inq, ['배정완료', '진행중', '완료'], "att")
    if sel_id is None:
        st.info("📌 배정완료/진행중 상태의 계약이 필요합니다.")
        return

    assignments_df = db.get_assignments_by_inquiry(sel_id)
    if assignments_df.empty:
        st.info("이 계약에 배정된 인력이 없습니다.")
        return

    name_col = '인력명' if '인력명' in assignments_df.columns else '이름'
    rate_col = '지급단가' if '지급단가' in assignments_df.columns else '단가'
    current_status = str(sel.get('상태', ''))

    st.markdown(f"**{sel.get('행사명', '')}** — 배정 인력 {len(assignments_df)}명 · 상태: {current_status}")

    # ── 행사완료 처리 ──
    if current_status == '진행중':
        if st.button("🏁 행사 완료 처리", type="primary", key="complete_event"):
            db.update_status(sel_id, sc.STATUS_FLOW[5])  # '완료'
            st.cache_data.clear()
            st.balloons()
            st.success("✅ 행사가 완료 처리되었습니다. 이제 정산을 진행하세요.")
            st.rerun()
    elif current_status == '완료':
        st.success("✅ 행사 완료 — 정산 페이지에서 후속 처리를 진행하세요.")

    st.divider()

    # ── 다일 행사 스케줄표 (일차별 인원 배분) ──
    start_date = _parse_date_safe(sel.get('행사시작일', ''))
    end_date = _parse_date_safe(sel.get('행사종료일', ''))
    
    if start_date and end_date and (end_date - start_date).days >= 1:
        num_days = (end_date - start_date).days + 1
        st.markdown(f'<div class="section-title">📅 일자별 스케줄표 ({num_days}일 행사)</div>', unsafe_allow_html=True)
        st.caption("💡 각 인력의 일자별 투입 여부를 체크하세요. 일차별로 다른 인원을 배정할 수 있습니다.")
        
        # 날짜 목록 생성
        date_list = [start_date + timedelta(days=d) for d in range(num_days)]
        date_labels = [f"{d.month}/{d.day}({['월','화','수','목','금','토','일'][d.weekday()]})" for d in date_list]
        
        # 스케줄 키 초기화
        sched_key = f"schedule_{sel_id}"
        if sched_key not in st.session_state:
            # 기본값: 전 인원 전일 투입
            st.session_state[sched_key] = {
                str(row.get(name_col, '')): [True] * num_days
                for _, row in assignments_df.iterrows()
            }
        
        schedule_data = st.session_state[sched_key]
        
        # 그리드 헤더
        header_cols = st.columns([2] + [1] * min(num_days, 7))
        with header_cols[0]:
            st.markdown("**인력명**")
        for di, dl in enumerate(date_labels[:7]):
            with header_cols[di + 1]:
                st.markdown(f"**{dl}**")
        
        # 7일 이상일 경우 페이지 나누기
        page_size = 7
        if num_days > page_size:
            sched_page = st.radio(
                "주차 선택",
                [f"{i*page_size+1}~{min((i+1)*page_size, num_days)}일차" for i in range((num_days + page_size - 1) // page_size)],
                horizontal=True, key="sched_page"
            )
            page_idx = [f"{i*page_size+1}~{min((i+1)*page_size, num_days)}일차" for i in range((num_days + page_size - 1) // page_size)].index(sched_page)
            day_start = page_idx * page_size
            day_end = min(day_start + page_size, num_days)
        else:
            day_start = 0
            day_end = num_days
        
        visible_dates = date_labels[day_start:day_end]
        visible_count = len(visible_dates)
        
        # 인력별 일자 체크박스
        daily_counts = [0] * visible_count
        for _, row in assignments_df.iterrows():
            staff_name = str(row.get(name_col, ''))
            role = str(row.get('직무', row.get('역할', '')))
            
            if staff_name not in schedule_data:
                schedule_data[staff_name] = [True] * num_days
            
            row_cols = st.columns([2] + [1] * visible_count)
            with row_cols[0]:
                st.markdown(f"👤 **{staff_name}** <span style='color:#6B7280;font-size:12px;'>({role})</span>", unsafe_allow_html=True)
            
            for di in range(visible_count):
                actual_di = day_start + di
                with row_cols[di + 1]:
                    checked = st.checkbox(
                        "✓", value=schedule_data[staff_name][actual_di],
                        key=f"sched_{sel_id}_{staff_name}_{actual_di}",
                        label_visibility="collapsed"
                    )
                    schedule_data[staff_name][actual_di] = checked
                    if checked:
                        daily_counts[di] += 1
        
        # 일자별 인원 요약
        st.markdown("---")
        summary_cols = st.columns([2] + [1] * visible_count)
        with summary_cols[0]:
            st.markdown("**일자별 인원**")
        for di in range(visible_count):
            with summary_cols[di + 1]:
                st.markdown(f"**{daily_counts[di]}명**")
        
        # 스케줄 저장
        st.session_state[sched_key] = schedule_data
        
        st.divider()

    # ── 출석 날짜: 문의 기준 (행사시작일~행사종료일) ──
    if not start_date:
        start_date = _parse_date_safe(sel.get('행사시작일', ''))
    if not end_date:
        end_date = _parse_date_safe(sel.get('행사종료일', ''))
    today = datetime.now().date()

    if start_date and end_date:
        default_date = max(start_date, min(today, end_date))
        att_date = st.date_input("출석 날짜", value=default_date,
                                 min_value=start_date, max_value=end_date, key="att_date")
        st.caption(f"📅 행사 기간: {start_date} ~ {end_date}")
    elif start_date:
        att_date = st.date_input("출석 날짜", value=max(start_date, today), key="att_date")
        st.caption(f"📅 시작일: {start_date}")
    else:
        att_date = st.date_input("출석 날짜", value=today, key="att_date")

    # ── 출퇴근 시간: 견적품목 근무시간 기준 + 수동 입력 ──
    est_items = db.load_estimate_items(sel_id)
    work_time_str = ''
    if not est_items.empty:
        work_time_str = str(est_items.iloc[0].get('근무시간', ''))

    default_start, default_end = _parse_work_time(work_time_str)
    col_t1, col_t2 = st.columns(2)
    start_time = col_t1.time_input("출근", value=default_start, key="att_start")
    end_time = col_t2.time_input("퇴근", value=default_end, key="att_end")

    if work_time_str:
        st.caption(f"⏰ 견적 기준 근무시간: {work_time_str} (수동 변경 가능)")

    start_dt = datetime.combine(today, start_time)
    end_dt = datetime.combine(today, end_time)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    worked_hours = (end_dt - start_dt).total_seconds() / 3600
    st.caption(f"근무시간: {worked_hours:.1f}시간")

    # ── 개인별 출석 ──
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
            if current_status == '배정완료':
                try:
                    db.update_status(sel_id, sc.STATUS_FLOW[4])  # '진행중'
                except Exception:
                    pass
            st.cache_data.clear()
            st.balloons()
            st.success(f"✅ {saved}명 출석 기록 완료!")


# ==============================================================================
# 3. 탭3: 평가 (STAFF DB 일치: 근태/수행/외모/팀워크)
# ==============================================================================

def tab_evaluation(data):
    """평가 — STAFF DB 평가항목과 일치 (근태/수행/외모/팀워크) + 캐시 최적화"""
    df_inq = data.get('inq', pd.DataFrame())
    sel_id, sel = _select_contract(df_inq, ['진행중', '완료'], "eval")
    if sel_id is None:
        st.info("📌 진행중 또는 완료 상태의 계약이 필요합니다.")
        return

    # 배정 인력 캐시 (selectbox 변경 시 재로딩 방지)
    cache_key = f"_eval_assignments_{sel_id}"
    if cache_key not in st.session_state or st.session_state.get('_eval_last_id') != sel_id:
        st.session_state[cache_key] = db.get_assignments_by_inquiry(sel_id)
        st.session_state['_eval_last_id'] = sel_id
    
    assignments_df = st.session_state[cache_key]
    if assignments_df.empty:
        st.info("배정된 인력이 없습니다.")
        return

    name_col = '인력명' if '인력명' in assignments_df.columns else '이름'
    eval_labels = [f"{row.get(name_col, 'N/A')} — {row.get('직무', row.get('역할', ''))}"
                   for _, row in assignments_df.iterrows()]
    sel_idx = st.selectbox("평가 대상", range(len(eval_labels)),
                            format_func=lambda x: eval_labels[x], key="eval_target")
    target = assignments_df.iloc[sel_idx]

    st.markdown(f"**{target.get(name_col, '')}** 평가")

    # STAFF DB와 일치하는 4개 평가항목 — form으로 감싸서 불필요한 rerun 방지
    st.caption("💡 평가 항목은 STAFF 인력 DB와 동일합니다. 슬라이더 조정 후 '평가 저장'을 누르세요.")
    
    with st.form(key=f"eval_form_{sel_id}_{sel_idx}"):
        col1, col2 = st.columns(2)
        s1 = col1.slider("근태", 1, 5, 3, key="e_s1", help="출퇴근 시간 준수, 결근율")
        s2 = col2.slider("수행", 1, 5, 3, key="e_s2", help="업무 수행 능력, 전문성")
        col3, col4 = st.columns(2)
        s3 = col3.slider("외모", 1, 5, 3, key="e_s3", help="복장, 단정함, 서비스 이미지")
        s4 = col4.slider("팀워크", 1, 5, 3, key="e_s4", help="협업, 의사소통, 현장 적응")

        total = round((s1 + s2 + s3 + s4) / 4, 1)
        grade = "A" if total >= 4.5 else "B" if total >= 3.5 else "C" if total >= 2.5 else "D"

        cr1, cr2 = st.columns(2)
        cr1.metric("총점", f"{total}")
        cr2.metric("등급", grade)

        total_comment = st.text_area("총평", key="e_comment", placeholder="종합 평가 내용을 입력하세요")
        recommend = st.checkbox("재추천 (다음에도 배정 추천)", value=total >= 3.5, key="e_rec")

        submitted = st.form_submit_button("✅ 평가 저장", type="primary", use_container_width=True)
    
    if submitted:
        eval_dict = {
            '배정ID': target.get('배정ID', ''),
            '인력명': target.get(name_col, ''),
            '현장명': sel.get('행사명', ''),
            '근태': s1, '수행': s2, '외모': s3, '팀워크': s4,
            '총점': total, '평가등급': grade,
            '평가자': '', '평가일시': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '강점': total_comment,
            '재추천': 'Yes' if recommend else 'No', '비고': '',
        }
        with st.spinner("평가를 저장 중..."):
            if db.save_evaluation(eval_dict):
                st.cache_data.clear()
                st.balloons()
                st.success("✅ 평가 저장 완료!")
            else:
                st.error("❌ 평가 저장 실패")


# ==============================================================================
# 4. 탭4: 지급 (수동 편집, 자동수당/세금 제외)
# ==============================================================================

def tab_payment(data):
    """지급 — 기본급만 자동, 추가수당/세금 없음, 수동 편집 가능"""
    df_inq = data.get('inq', pd.DataFrame())
    sel_id, sel = _select_contract(df_inq, ['진행중', '완료'], "pay")
    if sel_id is None:
        st.info("📌 진행중 또는 완료 상태의 계약이 필요합니다.")
        return

    assignments_df = db.get_assignments_by_inquiry(sel_id)
    if assignments_df.empty:
        st.info("배정된 인력이 없습니다.")
        return

    name_col = '인력명' if '인력명' in assignments_df.columns else '이름'
    rate_col = '지급단가' if '지급단가' in assignments_df.columns else '단가'
    days_col = '근무일수' if '근무일수' in assignments_df.columns else '일수'

    st.markdown(f"**{sel.get('행사명', '')}** — 급여 관리")
    st.caption("💡 기본급(단가×일수)만 자동 계산됩니다. 추가수당/세금공제는 정산 단계에서 처리합니다.")

    # 지급 데이터 구성 — 기본급만, 추가수당/세금 없음
    pay_data = []
    for _, row in assignments_df.iterrows():
        name = row.get(name_col, '')
        category = row.get('구분', '외부')
        base_rate = int(row.get(rate_col, 0) or 0)
        days = int(row.get(days_col, 0) or 0)
        basic_pay = base_rate * days

        pay_data.append({
            '인력명': name,
            '구분': category,
            '지급단가': base_rate,
            '근무일수': days,
            '기본급': basic_pay,
            '최종지급액': basic_pay if category != '본사' else 0,
            '배정ID': row.get('배정ID', ''),
        })

    pay_df = pd.DataFrame(pay_data)
    ext_pay = pay_df[pay_df['구분'] != '본사']

    c1, c2 = st.columns(2)
    c1.metric("외부 인력", f"{len(ext_pay)}명")
    c2.metric("총 기본급", f"₩{int(ext_pay['기본급'].sum()):,}")

    # 편집 가능한 테이블
    edit_cols = ['인력명', '구분', '지급단가', '근무일수', '기본급', '최종지급액']
    edited_df = st.data_editor(
        pay_df[edit_cols],
        disabled=['인력명', '구분'],
        use_container_width=True, hide_index=True, key="pay_editor",
        column_config={
            '지급단가': st.column_config.NumberColumn("지급단가(원/일)", format="%d"),
            '근무일수': st.column_config.NumberColumn("근무일수"),
            '기본급': st.column_config.NumberColumn("기본급", format="%d"),
            '최종지급액': st.column_config.NumberColumn("최종지급액", format="%d"),
        }
    )

    col_p1, col_p2 = st.columns(2)
    pay_date = col_p1.date_input("지급일", value=datetime.now().date(), key="pay_date")
    pay_status = col_p2.selectbox("지급상태", ["대기", "확정", "완료"], key="pay_status_sel")

    if st.button("💾 지급 내역 저장", type="primary", use_container_width=True, key="save_pay"):
        saved = 0
        with st.spinner("지급 내역 저장 중..."):
            for i, prow in edited_df.iterrows():
                if prow['구분'] == '본사':
                    continue
                period = f"{sel.get('행사시작일', '')}~{sel.get('행사종료일', '')}"
                payment_dict = {
                    '배정ID': pay_df.iloc[i]['배정ID'],
                    '인력명': prow['인력명'],
                    '현장명': sel.get('행사명', ''),
                    '파견기간': period,
                    '파견일수': int(prow['근무일수']),
                    '기본급': int(prow['기본급']),
                    '야근비': 0, '식사비': 0, '교통비': 0, '보너스': 0,
                    '소계': int(prow['최종지급액']),
                    '세금공제': 0,
                    '최종지급액': int(prow['최종지급액']),
                    '지급상태': pay_status,
                    '지급일': pay_date.strftime('%Y-%m-%d'),
                    '지급담당자': '', '비고': '',
                }
                if db.save_payment_record(payment_dict):
                    saved += 1

        if saved > 0:
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
    st.title("👥 인력파견 시스템 v5.0")

    st.markdown("""
    <div style="background: linear-gradient(135deg, #EFF6FF, #F0FDF4); border: 1px solid #BFDBFE;
                border-radius: 12px; padding: 12px 18px; margin-bottom: 14px;">
        <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; flex-wrap: wrap;">
            <span style="background:#DBEAFE;color:#1E40AF;padding:4px 10px;border-radius:8px;font-weight:600;">1️⃣ 인력배정</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#D1FAE5;color:#065F46;padding:4px 10px;border-radius:8px;font-weight:600;">2️⃣ 출석/근무</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#FEF3C7;color:#92400E;padding:4px 10px;border-radius:8px;font-weight:600;">3️⃣ 행사완료</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#EDE9FE;color:#5B21B6;padding:4px 10px;border-radius:8px;font-weight:600;">4️⃣ 평가</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#FEE2E2;color:#991B1B;padding:4px 10px;border-radius:8px;font-weight:600;">5️⃣ 지급</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#F3F4F6;color:#374151;padding:4px 10px;border-radius:8px;font-weight:600;">💰 정산</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 대시보드 메트릭 ──
    dispatch_df = db.load_dispatch_sheet()
    if dispatch_df is None:
        dispatch_df = pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 총 배정", f"{len(dispatch_df)}명")

    if not dispatch_df.empty:
        total_col = '총지급액' if '총지급액' in dispatch_df.columns else None
        if total_col:
            total = pd.to_numeric(dispatch_df[total_col], errors='coerce').fillna(0).sum()
        else:
            rate_c = '지급단가' if '지급단가' in dispatch_df.columns else '단가' if '단가' in dispatch_df.columns else None
            days_c = '근무일수' if '근무일수' in dispatch_df.columns else '일수' if '일수' in dispatch_df.columns else None
            if rate_c and days_c:
                r = pd.to_numeric(dispatch_df[rate_c], errors='coerce').fillna(0)
                d = pd.to_numeric(dispatch_df[days_c], errors='coerce').fillna(0)
                total = (r * d).sum()
            else:
                total = 0
        c2.metric("💰 예상 급여", f"₩{int(total):,}")
    else:
        c2.metric("💰 예상 급여", "₩0")

    cat_col = '구분' if not dispatch_df.empty and '구분' in dispatch_df.columns else None
    hq_count = len(dispatch_df[dispatch_df[cat_col].astype(str) == '본사']) if cat_col else 0
    ext_count = len(dispatch_df) - hq_count
    c3.metric("🏢 본사 투입", f"{hq_count}명")
    c4.metric("👥 외부 인력", f"{ext_count}명")

    tab1, tab2, tab3, tab4 = st.tabs(["🎯 인력배정", "📋 출석/근무", "⭐ 평가", "💰 지급"])
    with tab1:
        tab_assignment(data)
    with tab2:
        tab_attendance(data)
    with tab3:
        tab_evaluation(data)
    with tab4:
        tab_payment(data)
