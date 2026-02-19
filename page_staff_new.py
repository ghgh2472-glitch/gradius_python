# page_staff_new.py
"""
👥 인력파견 시스템 v5.1 — 후보군 기반 3단계 배정 플로우
- 탭1: 🎯 인력배정 (3단계: 후보등록 → 직군배정 → 확정&일정관리)
  - Step1: 후보 등록 (검색→후보풀 서버저장, 새로고침 안전)
  - Step2: 직군별 배정 (후보→직군 할당, 진행률 시각화)
  - Step3: 확정 & 일정관리 (일괄확정 + 장기건 일정 추후입력)
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

def _col(df, *candidates):
    """DataFrame에서 사용 가능한 첫 번째 컬럼명 반환.
    load_dispatch_sheet() 정규화로 인해 컬럼명이 바뀔 수 있어
    여러 후보를 시도합니다. (예: '인력명' or '이름')"""
    if df is None or (hasattr(df, 'empty') and df.empty):
        return candidates[0] if candidates else None
    for c in candidates:
        if c in df.columns:
            return c
    return candidates[0] if candidates else None

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
    """견적품목과 배정기록에서 직군별 배정 현황 계산 ([지원] 품목 제외)
    인일(man-day) 기반 진행률 포함"""
    role_status = []
    if est_items.empty:
        return role_status
    for _, item in est_items.iterrows():
        # [지원] 품목은 인력이 아니므로 제외
        item_name = str(item.get('품목', item.get('직군명', '')))
        if item_name.startswith('[지원]'):
            continue
        role_name = str(item.get('직군명', item_name))
        if not role_name or role_name == 'nan':
            continue
        needed = int(item.get('인원수', item.get('수량', 0)) or 0)
        est_days = int(item.get('일수', 0) or 0)
        needed_mandays = needed * est_days  # 필요 인일

        assigned_count = 0
        actual_mandays = 0
        if not assignments_df.empty:
            role_col = '직무' if '직무' in assignments_df.columns else '역할'
            days_col = '근무일수' if '근무일수' in assignments_df.columns else '일수'
            if role_col in assignments_df.columns:
                role_rows = assignments_df[
                    assignments_df[role_col].astype(str).str.contains(role_name, na=False)]
                assigned_count = len(role_rows)
                if days_col in role_rows.columns:
                    actual_mandays = int(pd.to_numeric(
                        role_rows[days_col], errors='coerce').fillna(0).sum())
        role_status.append({
            'role': role_name, 'needed': needed, 'assigned': assigned_count,
            'pay_rate': int(item.get('매입단가', 0) or 0),
            'days': est_days,
            'time': str(item.get('근무시간', '')),
            'needed_mandays': needed_mandays,
            'actual_mandays': actual_mandays,
        })
    return role_status


def _lookup_staff_brief(df_staff, name):
    """STAFF DF에서 이름으로 간략 정보 조회 (읽기 전용)
    반환: {'성별','나이','연락처','총점','가능직무'} or None"""
    if df_staff is None or df_staff.empty or not name:
        return None
    name_col = None
    for c in df_staff.columns:
        if c.strip() in ('이름', '성명'):
            name_col = c
            break
    if not name_col:
        return None
    match = df_staff[df_staff[name_col].astype(str).str.strip() == str(name).strip()]
    if match.empty:
        return None
    r = match.iloc[0]
    return {
        '성별': str(r.get('성별', '-')).strip() or '-',
        '나이': str(r.get('나이', '-')).strip() or '-',
        '연락처': str(r.get('연락처', '')).strip() or '',
        '총점': str(r.get('총점', '-')).strip() or '-',
        '가능직무': str(r.get('가능직무', '-')).strip() or '-',
    }


def _get_support_items(est_items):
    """견적품목에서 [지원] 품목만 추출"""
    support = []
    if est_items.empty:
        return support
    for _, item in est_items.iterrows():
        item_name = str(item.get('품목', item.get('직군명', '')))
        if item_name.startswith('[지원]'):
            support.append({
                'name': item_name.replace('[지원] ', '').replace('[지원]', ''),
                'qty': int(item.get('수량', item.get('인원수', 0)) or 0),
                'days': int(item.get('일수', 0) or 0),
                'note': str(item.get('비고', '')),
            })
    return support


def _auto_update_status(inquiry_id, role_status):
    """필요 인원 대비 배정 현황 체크 → 자동 상태 전환"""
    try:
        db.invalidate_dispatch_only()  # 배정기록 최신화 (문의 상태 변경은 호출자가 invalidate_data() 처리)
        assignments_df = db.get_assignments_by_inquiry(inquiry_id)
        # 취소된 배정은 제외
        if not assignments_df.empty and '지급상태' in assignments_df.columns:
            active = assignments_df[~assignments_df['지급상태'].astype(str).str.contains('취소', na=False)]
        else:
            active = assignments_df
        if role_status:
            total_needed = sum(rs['needed'] for rs in role_status)
            total_assigned = len(active) if not active.empty else 0
            if total_needed > 0 and total_assigned >= total_needed:
                db.update_status(inquiry_id, sc.STATUS_FLOW[3])  # '배정완료'
                # ✅ 정산 시트 진행상황도 '행사준비'로 자동 전환
                db.update_settlement_progress(inquiry_id, '행사준비')
        elif not active.empty:
            db.update_status(inquiry_id, sc.STATUS_FLOW[3])
            db.update_settlement_progress(inquiry_id, '행사준비')
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
# 1. 탭1: 인력배정 v5.1 — 3단계 플로우
#    Step 1: 후보 등록 (검색→후보풀 서버저장)
#    Step 2: 직군별 배정 (후보→직군 배정)
#    Step 3: 배정 확정 & 일정관리 (확정 + 장기건 일괄입력)
# ==============================================================================

def tab_assignment(data):
    """인력배정 v5.1 — 후보군 기반 3단계 배정"""
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

    # ── 장기건 감지 ──
    raw_start = str(sel.get('행사시작일', '')).strip()
    raw_end = str(sel.get('행사종료일', '')).strip()
    start_d = _parse_date_safe(raw_start.split('/')[0].strip() if '/' in raw_start else raw_start)
    end_d = _parse_date_safe(raw_end.split('/')[-1].strip() if '/' in raw_end else raw_end)
    is_long_term = (start_d and end_d and (end_d - start_d).days >= 5)

    if is_long_term:
        num_days = (end_d - start_d).days + 1
        st.info(f"📅 장기건 ({num_days}일) — 배정 확정 후 일정을 추후 일괄입력할 수 있습니다.")

    # ── 필요 직군 현황 (인일 기반) ──
    st.markdown('<div class="section-title">📊 필요인력 현황</div>', unsafe_allow_html=True)
    est_items = db.load_estimate_items(sel_id)
    assignments_df = db.get_assignments_by_inquiry(sel_id)
    role_status = _get_role_status(est_items, assignments_df)

    # 지원품목
    support_items = _get_support_items(est_items)
    if not role_status:
        st.caption("💡 견적서에 품목이 없어 자유 배정 모드입니다.")

    if role_status:
        # 전체 인일 합계
        total_needed_md = sum(rs['needed_mandays'] for rs in role_status)
        total_actual_md = sum(rs['actual_mandays'] for rs in role_status)
        md_pct = (total_actual_md / total_needed_md * 100) if total_needed_md > 0 else 0

        cols = st.columns(min(len(role_status) + 1, 5))
        for i, rs in enumerate(role_status):
            # 인일 기준 진행률
            md_p = (rs['actual_mandays'] / rs['needed_mandays'] * 100) if rs['needed_mandays'] > 0 else 0
            with cols[i % (len(role_status) + 1)]:
                with st.container():
                    rc1, rc2 = st.columns([2, 1])
                    with rc1:
                        st.markdown(f"**{rs['role']}**")
                        st.caption(f"₩{rs['pay_rate']:,}/일 · {rs['days']}일 · {rs['time']}")
                    with rc2:
                        over_tag = " 초과OK" if rs['assigned'] > rs['needed'] else ""
                        st.markdown(f"**{rs['assigned']}/{rs['needed']}명**{over_tag}")
                    st.progress(min(md_p / 100.0, 1.0))
                    md_icon = '✅' if md_p >= 100 else ''
                    st.caption(f"인일: {rs['actual_mandays']}/{rs['needed_mandays']} {md_icon}")

        # 전체 인일 요약 (마지막 컬럼)
        with cols[len(role_status) % (len(role_status) + 1)]:
            with st.container():
                st.markdown("**📊 전체**")
                total_persons = sum(rs['assigned'] for rs in role_status)
                total_needed_p = sum(rs['needed'] for rs in role_status)
                st.caption(f"인원: {total_persons}/{total_needed_p}명")
                st.progress(min(md_pct / 100.0, 1.0))
                md_all_icon = '✅' if md_pct >= 100 else ''
                st.caption(f"**인일: {total_actual_md}/{total_needed_md}** {md_all_icon}")

        # 일자별 미니 상태 (날짜가 있을 때)
        if start_d and end_d:
            event_dates_top = []
            d = start_d
            while d <= end_d:
                event_dates_top.append(d)
                d += timedelta(days=1)
            if event_dates_top and len(event_dates_top) <= 30:
                st.caption("📅 일자별 충원 상태 (배정중+확정 인원 기준)")
                day_cols = st.columns(min(len(event_dates_top), 10))
                total_needed_p = sum(rs['needed'] for rs in role_status)
                for di, dd in enumerate(event_dates_top[:10]):
                    wd = '월화수목금토일'[dd.weekday()]
                    with day_cols[di]:
                        st.caption(f"{dd.strftime('%m/%d')}{wd}")
                if len(event_dates_top) > 10:
                    st.caption(f"⋯ +{len(event_dates_top) - 10}일 더")

    if support_items:
        with st.expander(f"📦 지원품목 ({len(support_items)}건) — 수량 확인", expanded=False):
            sup_cols = st.columns(min(len(support_items), 4))
            for si, sup in enumerate(support_items):
                with sup_cols[si % len(sup_cols)]:
                    _checked = st.checkbox(f"✅ {sup['name']} x{sup['qty']}개",
                                           key=f"sup_check_{si}", value=False)
                    if _checked:
                        st.caption(f"✔ 준비 완료")
                    else:
                        st.caption(f"{sup['days']}일분 · {sup['note']}")

    # ================================================================
    # 3단계 서브탭
    # ================================================================
    step1, step2, step3 = st.tabs([
        "① 후보 등록",
        "② 직군별 배정",
        "③ 확정 & 일정관리"
    ])

    with step1:
        _step1_candidate_pool(sel_id, sel, df_staff, role_status, est_items)

    with step2:
        _step2_role_assignment(sel_id, sel, role_status, start_d, end_d, df_inq, df_staff)

    with step3:
        _step3_confirm_and_schedule(sel_id, sel, role_status, is_long_term, start_d, end_d)


# ──────────────────────────────────────────────────────────
# Step 1: 후보 등록 (검색 → 후보풀 서버 저장)
# ──────────────────────────────────────────────────────────

def _step1_candidate_pool(sel_id, sel, df_staff, role_status, est_items):
    """후보 인력 검색 및 후보풀 등록"""

    col_left, col_right = st.columns([1.3, 1])

    # ── 왼쪽: 검색 ──
    with col_left:
        st.markdown('<div class="section-title">🔍 인력 검색 → 후보풀 등록</div>', unsafe_allow_html=True)
        st.caption("💡 인력을 검색하고 후보풀에 등록하세요. 후보풀은 서버에 저장되어 새로고침해도 유지됩니다.")

        if 'assign_cart' not in st.session_state:
            st.session_state.assign_cart = []
        if 'team_members' not in st.session_state:
            st.session_state.team_members = []

        # ══ 배정 유형 선택: 개별 / 팀 ══
        assign_type = st.radio("배정 유형", ["개별 배정", "👥 팀 배정"], horizontal=True, key="assign_type")
        st.divider()

        if assign_type == "👥 팀 배정":
            _render_team_assignment_ui(df_staff, role_status)
        else:
            _render_individual_assignment_ui(sel, df_staff, role_status)

    # ── 오른쪽: 후보풀 (로컬 대기 + 서버 저장됨) ──
    with col_right:
        _render_candidate_pool_panel(sel_id, sel, df_staff, role_status)


def _render_candidate_pool_panel(sel_id, sel, df_staff, role_status):
    """오른쪽 패널: 후보풀 + 확정 인력"""
    st.markdown('<div class="section-title">👥 후보풀</div>', unsafe_allow_html=True)

    # 로컬 대기 카트 (아직 서버 미저장)
    cart = st.session_state.get('assign_cart', [])
    if cart:
        st.markdown(f"##### 🕐 등록 대기 ({len(cart)}명)")
        cart_df = pd.DataFrame(cart)
        display_cart_cols = ['인력명', '구분', '팀코드']
        avail_cart = [c for c in display_cart_cols if c in cart_df.columns]
        st.dataframe(cart_df[avail_cart], use_container_width=True, hide_index=True,
                     height=min(180, 35 * len(cart) + 38))

        # 팀별 요약 (카트에 팀 배정이 있을 때)
        if '팀코드' in cart_df.columns:
            team_cart = cart_df[cart_df['팀코드'].astype(str).str.strip() != '']
            if not team_cart.empty:
                for tc in team_cart['팀코드'].unique():
                    tc_df = team_cart[team_cart['팀코드'] == tc]
                    leader = tc_df[tc_df['구분'] == '팀장']
                    leader_name = leader['인력명'].iloc[0] if not leader.empty else '?'
                    total = int(tc_df['총지급액'].sum()) if '총지급액' in tc_df.columns else 0
                    st.caption(f"👥 {leader_name}팀 ({len(tc_df)}명) — ₩{total:,}")

        for ci_idx in range(len(cart)):
            item = cart[ci_idx]
            dc1, dc2 = st.columns([3, 1])
            with dc1:
                st.caption(f"{item['인력명']} ({item['구분']})")
            with dc2:
                if st.button(f"🗑️", key=f"del_cart_{ci_idx}", help=f"{item['인력명']} 제거"):
                    st.session_state.assign_cart.pop(ci_idx)
                    st.rerun()

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            if st.button("💾 후보풀에 등록", type="primary", use_container_width=True, key="save_pool"):
                with st.spinner("후보 등록 중..."):
                    event_name = sel.get('행사명', '')
                    ok, fail = db.save_candidates_batch(sel_id, event_name, cart)
                if ok > 0:
                    st.session_state.assign_cart = []
                    db.invalidate_dispatch_only()
                    st.success(f"✅ {ok}명 후보 등록 완료!")
                    st.rerun()
                else:
                    st.error("❌ 등록 실패")
        with col_a2:
            if st.button("🗑️ 전체 비우기", use_container_width=True, key="clear_cart"):
                st.session_state.assign_cart = []
                st.rerun()

    # 서버 저장된 후보 목록
    st.markdown("##### 📋 등록된 후보 목록")
    if st.button("🔄 새로고침", key="refresh_candidates"):
        db.invalidate_dispatch_only()
        st.rerun()

    candidates_df = db.get_candidates_by_inquiry(sel_id)
    if not candidates_df.empty:
        name_col = _col(candidates_df, '인력명', '이름')
        status_col = _col(candidates_df, '지급상태', '상태')
        role_col = _col(candidates_df, '직무', '역할')

        for idx, row in candidates_df.iterrows():
            cname = row.get(name_col, 'N/A')
            cstatus = str(row.get(status_col, '후보'))
            crole = row.get(role_col, '')
            ctype = row.get('구분', '외부')
            badge_icon = "🏢" if ctype == '본사' else "👤"
            status_badge = "🟡 후보" if '후보' in cstatus else "🔵 배정중"
            role_text = f" → {crole}" if crole and str(crole) != 'nan' and str(crole).strip() else ""

            # STAFF 정보 조회
            sinfo = _lookup_staff_brief(df_staff, cname)
            info_line = ""
            if sinfo:
                phone_display = sinfo['연락처'] if sinfo['연락처'] else '-'
                info_line = f"{sinfo['성별']}/{sinfo['나이']} · 📱{phone_display} · ⭐{sinfo['총점']}"

            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"{badge_icon} **{cname}** {status_badge}{role_text}")
                if info_line:
                    st.caption(f"  {info_line}")
            with c2:
                if '후보' in cstatus:
                    if st.button("❌", key=f"rm_cand_{idx}", help=f"{cname} 제거"):
                        aid = row.get('배정ID', '')
                        if aid:
                            db.remove_candidate(aid)
                            db.invalidate_dispatch_only()
                            st.rerun()

        st.caption(f"총 {len(candidates_df)}명 후보 등록됨")
    else:
        st.info("👈 왼쪽에서 인력을 검색하고 후보풀에 등록하세요")

    # 기존 확정 인력
    all_assignments = db.get_assignments_by_inquiry(sel_id)
    if not all_assignments.empty:
        status_col = _col(all_assignments, '지급상태', '상태')
        confirmed = all_assignments[
            all_assignments[status_col].astype(str).str.contains('확정', na=False)]
        if not confirmed.empty:
            name_col = _col(confirmed, '인력명', '이름')
            st.markdown(f"##### ✅ 확정 인력 ({len(confirmed)}명)")
            display_cols = ['인력명', '이름', '직무', '역할', '팀코드', '지급단가', '단가', '근무일수', '일수']
            avail = [c for c in display_cols if c in confirmed.columns]
            st.dataframe(confirmed[avail], use_container_width=True, hide_index=True,
                         height=min(200, 35 * len(confirmed) + 38))

            # 팀별 요약 표시
            if '팀코드' in confirmed.columns:
                team_confirmed = confirmed[confirmed['팀코드'].astype(str).str.strip() != '']
                if not team_confirmed.empty:
                    st.markdown("##### 👥 팀 배정 요약")
                    for tc in team_confirmed['팀코드'].unique():
                        tc_members = team_confirmed[team_confirmed['팀코드'] == tc]
                        leader = tc_members[tc_members['구분'].astype(str) == '팀장'] if '구분' in tc_members.columns else pd.DataFrame()
                        leader_name = leader['인력명'].iloc[0] if not leader.empty and '인력명' in leader.columns else '?'
                        tc_total = int(pd.to_numeric(tc_members.get('총지급액', 0), errors='coerce').sum())
                        st.info(f"👤 **{leader_name}팀** ({len(tc_members)}명) — 합계: ₩{tc_total:,} → 팀장 지급")


def _render_team_assignment_ui(df_staff, role_status):
    """팀 배정 모드 UI — 팀장 검색 + 팀원 수기 입력"""

    # 직군 선택 (공통)
    role_options = [rs['role'] for rs in role_status] if role_status else []
    role_options.append("기타 (직접입력)")
    col_role, col_custom = st.columns([2, 1])
    with col_role:
        sel_role = st.selectbox("배정 직군", role_options, key="team_assign_role")
    with col_custom:
        if sel_role == "기타 (직접입력)":
            sel_role = st.text_input("직군명 입력", key="team_custom_role")
        else:
            st.empty()

    role_info = next((rs for rs in role_status if rs['role'] == sel_role), None)
    default_rate = role_info['pay_rate'] if role_info else 100000
    default_days = role_info['days'] if role_info else 1

    st.markdown("##### 👤 팀장 선택 (STAFF에서 검색)")
    leader_search = st.text_input("🔍 팀장 이름 검색", placeholder="예: 강정호", key="leader_search")

    selected_leader = None
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
                format_func=lambda x: leader_options[x], key="sel_leader")
            selected_leader = leaders.loc[sel_leader_idx]
            st.success(f"✅ 팀장: **{selected_leader.get('이름', '')}**")
        else:
            st.warning("검색 결과가 없습니다.")

    st.markdown("##### 👥 팀원 추가 (수기 입력)")
    st.caption("팀원은 STAFF에 없어도 됩니다. 이름만 입력하세요.")

    col_add, col_btn = st.columns([3, 1])
    with col_add:
        new_member = st.text_input("팀원 이름", placeholder="예: 김철수", key="new_member", label_visibility="collapsed")
    with col_btn:
        if st.button("➕ 추가", key="add_member"):
            if new_member.strip():
                st.session_state.team_members.append(new_member.strip())
                st.rerun()

    if st.session_state.team_members:
        st.markdown(f"**현재 팀원:** {len(st.session_state.team_members)}명")
        for i, member in enumerate(st.session_state.team_members):
            mc1, mc2 = st.columns([4, 1])
            mc1.write(f"• {member}")
            if mc2.button("🗑️", key=f"del_member_{i}"):
                st.session_state.team_members.pop(i)
                st.rerun()

    st.divider()

    col_rate, col_days = st.columns(2)
    with col_rate:
        team_rate = st.number_input("인당 단가 (원/일)", value=default_rate, step=10000, key="team_rate")
    with col_days:
        team_days = st.number_input("근무일수", value=default_days, min_value=1, key="team_days")

    team_size = 1 + len(st.session_state.team_members)
    team_total = team_rate * team_days * team_size

    st.info(f"""
    📊 **팀 합계**
    - 팀 인원: {team_size}명 (팀장 1 + 팀원 {len(st.session_state.team_members)})
    - 총 지급액: **{team_total:,}원** → 팀장 계좌로 지급
    """)

    if st.button("✅ 팀 배정 추가", type="primary", use_container_width=True, key="add_team"):
        if selected_leader is None:
            st.error("팀장을 선택해주세요.")
        else:
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

            st.session_state.team_members = []
            st.success(f"✅ {leader_name}팀 ({team_size}명) 배정 추가!")
            st.rerun()


def _render_individual_assignment_ui(sel, df_staff, role_status):
    """개별 배정 모드 UI — 본사 인원 + 외부 인력 검색"""

    # ── 본사 인력 ──
    st.markdown("##### 🏢 본사 인원")
    hq_cols = st.columns(min(len(db.HQ_STAFF) + 1, 5))
    for i, hq in enumerate(db.HQ_STAFF):
        with hq_cols[i % len(hq_cols)]:
            if st.button(f"➕ {hq['이름']}", key=f"hq_{hq['이름']}", use_container_width=True):
                st.session_state.assign_cart.append({
                    '인력명': hq['이름'], '구분': '본사',
                    '직무': hq['직무'], '지급단가': 0, '근무일수': 1, '총지급액': 0,
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
                dispatch_data = db.get_dispatch()
                df_dispatch = dispatch_data.get('dispatch', pd.DataFrame())
                location = str(sel.get('장소', ''))
                g_val = gender_f if gender_f != "전체" else None
                # 필요 직군 중 미충원 1순위 자동 선택
                auto_role = None
                for rs in (role_status or []):
                    if rs['assigned'] < rs['needed']:
                        auto_role = rs['role']
                        break
                result = SmartAssignment.ai_recommend(
                    staff_df=df_staff, dispatch_df=df_dispatch,
                    job_type=auto_role, location=location.split()[0] if location else None,
                    gender=g_val, top_n=20)
            else:
                result = _search_staff(
                    df_staff, search_q, gender_f, age_filter, rec_filter,
                    role_filter, region_filter, min_height, min_score,
                    english_f, driving_f)

            st.session_state.search_results = result
            st.session_state.search_done = True

    # 검색 결과
    if st.session_state.get('search_done') and not st.session_state.get('search_results', pd.DataFrame()).empty:
        results = st.session_state.search_results
        st.markdown(f"**{len(results)}명 검색됨** — 체크하여 후보풀에 추가")

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
            if st.button(f"✅ 선택한 {len(selected_indices)}명 후보풀에 추가",
                         type="primary", use_container_width=True, key="add_to_pool"):
                for si in selected_indices:
                    row = results.iloc[si]
                    st.session_state.assign_cart.append({
                        '인력명': row.get('이름', ''), '구분': '외부',
                        '직무': '', '지급단가': 0, '근무일수': 0, '총지급액': 0,
                    })
                st.rerun()

    # ── 신규 인력 직접 입력 ──
    st.markdown("##### ✍️ 신규 인력 직접 입력")
    st.caption("💡 인력풀에 없는 신규 인력을 등록하고 바로 후보풀에 추가합니다.")
    with st.expander("➕ 신규 인력 입력", expanded=False):
        nc1, nc2, nc3 = st.columns([1.5, 1, 0.8])
        with nc1:
            new_name = st.text_input("이름 *", placeholder="홍길동", key="new_staff_name")
        with nc2:
            new_phone = st.text_input("연락처", placeholder="010-0000-0000", key="new_staff_phone")
        with nc3:
            new_gender = st.selectbox("성별", ["M", "F"], key="new_staff_gender")

        nc4, nc5, nc6 = st.columns([1.5, 1, 0.8])
        with nc4:
            new_job = st.text_input("가능직무", placeholder="경호, 안내", key="new_staff_job")
        with nc5:
            new_region = st.text_input("지역", placeholder="서울, 경기", key="new_staff_region")
        with nc6:
            new_age = st.number_input("나이", min_value=18, max_value=70, value=30, key="new_staff_age")

        _save_to_staff = st.checkbox("STAFF 시트에도 등록", value=True, key="save_new_to_staff")

        if st.button("✅ 후보풀에 추가", type="primary", use_container_width=True, key="add_new_staff_btn"):
            if not new_name.strip():
                st.warning("이름을 입력해주세요.")
            else:
                st.session_state.assign_cart.append({
                    '인력명': new_name.strip(), '구분': '외부',
                    '직무': new_job if new_job else '', '지급단가': 0, '근무일수': 0, '총지급액': 0,
                })
                if _save_to_staff:
                    staff_data = {
                        '이름': new_name.strip(), '연락처': new_phone.strip() if new_phone else '',
                        '성별': new_gender, '나이': str(new_age),
                        '가능직무': new_job, '이동가능지역': new_region.strip() if new_region else '',
                        '추천도': '일반',
                    }
                    if db.add_new_staff(staff_data):
                        st.success(f"✅ {new_name} — 후보 추가 + STAFF 등록 완료!")
                    else:
                        st.warning(f"⚠️ {new_name} — 후보 추가됨 (STAFF 등록 실패)")
                else:
                    st.success(f"✅ {new_name} — 후보풀에 추가!")
                st.rerun()


# ──────────────────────────────────────────────────────────
# Step 2: 직군별 배정 (후보풀 → 직군 할당)
#   좌: 일자별 배정 매트릭스  /  우: 후보 & 배정 UI
# ──────────────────────────────────────────────────────────

def _step2_role_assignment(sel_id, sel, role_status, start_d=None, end_d=None, df_inq=None, df_staff=None):
    """후보풀에서 직군별로 인력 배정 — 좌우 분할 + 인일 기반 + 충돌 감지"""

    candidates_df = db.get_candidates_by_inquiry(sel_id, include_assigned=True)
    if candidates_df.empty:
        st.info("📌 먼저 ① 후보 등록 탭에서 인력을 후보풀에 등록하세요.")
        return

    name_col = _col(candidates_df, '인력명', '이름')
    status_col = _col(candidates_df, '지급상태', '상태')
    role_col_name = _col(candidates_df, '직무', '역할')

    unassigned = candidates_df[candidates_df[status_col].astype(str).str.strip() == '후보']
    assigned = candidates_df[candidates_df[status_col].astype(str).str.strip() == '배정중']

    # ── 일자 목록 ──
    event_dates = []
    if start_d and end_d and start_d <= end_d:
        d = start_d
        while d <= end_d:
            event_dates.append(d)
            d += timedelta(days=1)

    # ── 일정 충돌 데이터 준비 ──
    conflict_map = {}
    if event_dates and df_inq is not None and not df_inq.empty:
        try:
            dispatch_df = db.load_dispatch_sheet()
            if not dispatch_df.empty:
                d_name_col = _col(dispatch_df, '인력명', '이름')
                d_status_col = _col(dispatch_df, '지급상태', '상태')
                d_inq_col = _col(dispatch_df, '문의ID')
                active_dispatch = dispatch_df[
                    (~dispatch_df[d_status_col].astype(str).str.contains('취소', na=False)) &
                    (dispatch_df[d_inq_col].astype(str) != str(sel_id))
                ]
                if not active_dispatch.empty:
                    other_inq_ids = active_dispatch[d_inq_col].unique()
                    inq_dates = {}
                    for oid in other_inq_ids:
                        oid_str = str(oid).strip()
                        match = df_inq[df_inq['문의ID'].astype(str).str.strip() == oid_str]
                        if not match.empty:
                            row = match.iloc[0]
                            rs = str(row.get('행사시작일', '')).strip()
                            re_ = str(row.get('행사종료일', '')).strip()
                            os = _parse_date_safe(rs.split('/')[0].strip() if '/' in rs else rs)
                            oe = _parse_date_safe(re_.split('/')[-1].strip() if '/' in re_ else re_)
                            if os and oe:
                                inq_dates[oid_str] = (os, oe, row.get('행사명', ''))
                    for _, cand in candidates_df.iterrows():
                        cname = cand.get(name_col, '')
                        if not cname:
                            continue
                        person_dispatches = active_dispatch[
                            active_dispatch[d_name_col].astype(str).str.strip() == str(cname).strip()
                        ]
                        if person_dispatches.empty:
                            continue
                        for _, pd_row in person_dispatches.iterrows():
                            pd_inq = str(pd_row.get(d_inq_col, '')).strip()
                            if pd_inq in inq_dates:
                                os, oe, ev_name = inq_dates[pd_inq]
                                overlap = [dd for dd in event_dates if os <= dd <= oe]
                                if overlap:
                                    if cname not in conflict_map:
                                        conflict_map[cname] = []
                                    conflict_map[cname].append({
                                        '행사명': ev_name,
                                        '기간': f"{os.strftime('%m/%d')}~{oe.strftime('%m/%d')}",
                                        '겹치는날짜': overlap,
                                    })
        except Exception as e:
            print(f"[Conflict] Error: {e}")

    # ── 헤더 ──
    st.markdown('<div class="section-title">🎯 직군별 인력 배정</div>', unsafe_allow_html=True)

    hdr1, hdr2 = st.columns([3, 1])
    with hdr1:
        st.caption("💡 좌측에서 일자별 배정 현황을 확인하고, 우측에서 후보를 배정하세요.")
    with hdr2:
        if st.button("🔄 새로고침", key="refresh_role_assign", use_container_width=True):
            db.invalidate_dispatch_only()
            st.rerun()

    # ── 충돌 경고 ──
    if conflict_map:
        with st.expander(f"⚠️ 일정 충돌: {len(conflict_map)}명", expanded=False):
            for cname, conflicts in conflict_map.items():
                for cf in conflicts:
                    overlap_strs = [dd.strftime('%m/%d') for dd in cf['겹치는날짜']]
                    st.warning(
                        f"⚠️ **{cname}** — 「{cf['행사명']}」({cf['기간']})과 "
                        f"**{len(cf['겹치는날짜'])}일** 겹침: {', '.join(overlap_strs)}"
                    )

    # ================================================================
    # 좌우 분할 레이아웃
    # ================================================================
    col_left, col_right = st.columns([1.2, 1])

    # ──────────────────────────────────────────
    # 좌측: 일자별 배정 현황 매트릭스 + 인라인 편집
    # ──────────────────────────────────────────
    with col_left:
        st.markdown("##### 📅 일자별 배정 현황")

        if not event_dates:
            st.caption("행사 날짜 정보가 없어 매트릭스를 표시할 수 없습니다.")
        elif len(event_dates) > 60:
            st.caption(f"행사 기간이 {len(event_dates)}일로 너무 깁니다. 매트릭스 생략.")
        else:
            total_needed_per_day = sum(rs['needed'] for rs in role_status) if role_status else 0

            # 페이징
            dates_per_page = 7
            total_pages = max(1, (len(event_dates) + dates_per_page - 1) // dates_per_page)
            if total_pages > 1:
                page = st.number_input(
                    "주차 선택", min_value=1, max_value=total_pages, value=1,
                    key="matrix_page_main") - 1
            else:
                page = 0
            page_dates = event_dates[page * dates_per_page: (page + 1) * dates_per_page]

            # 헤더 행
            hcols = st.columns([2.5] + [1] * len(page_dates) + [0.8, 0.8])
            hcols[0].markdown("**인력**")
            for di, dd in enumerate(page_dates):
                wd = '월화수목금토일'[dd.weekday()]
                is_we = dd.weekday() >= 5
                hcols[di + 1].caption(f"**{dd.strftime('%m/%d')}**\n{'🔴' if is_we else ''}{wd}")
            hcols[-2].markdown("**일수**")
            hcols[-1].markdown("**관리**")

            # 배정된 인력 행 (배정중) — 인라인 편집 지원
            day_counts = {dd.isoformat(): 0 for dd in page_dates}

            # 편집 모드 키: edit_assign_{assign_id}
            editing_id = st.session_state.get('_editing_assign_id', None)

            if not assigned.empty:
                for aidx, arow in assigned.iterrows():
                    a_name = arow.get(name_col, '')
                    a_role = arow.get(role_col_name, '')
                    a_days = int(arow.get('근무일수', arow.get('일수', 0)) or 0)
                    a_type = arow.get('구분', '외부')
                    a_pay = int(arow.get('지급단가', arow.get('단가', 0)) or 0)
                    a_assign_id = str(arow.get('배정ID', '')).strip()
                    is_editing = (editing_id == a_assign_id)

                    # 근무일자 컬럼 파싱 (저장된 실제 날짜)
                    raw_work_dates = str(arow.get('근무일자', '')).strip()
                    if raw_work_dates and raw_work_dates != 'nan':
                        a_work_dates_set = set(raw_work_dates.split(','))
                    else:
                        a_work_dates_set = None  # 레거시: 순서 기반 폴백

                    acols = st.columns([2.5] + [1] * len(page_dates) + [0.8, 0.8])
                    badge = "🏢" if a_type == '본사' else "👤"
                    conflict_tag = ""
                    if a_name in conflict_map:
                        conflict_tag = " ⚠️"
                    acols[0].caption(f"{badge}{a_name}{conflict_tag}\n({a_role})")

                    person_days = 0
                    for di, dd in enumerate(page_dates):
                        d_iso = dd.isoformat()
                        # 근무일자 컬럼이 있으면 정확한 날짜 매칭, 없으면 순서 기반 폴백
                        if a_work_dates_set is not None:
                            works_this_day = d_iso in a_work_dates_set
                        else:
                            day_idx = event_dates.index(dd) if dd in event_dates else -1
                            works_this_day = day_idx < a_days if a_days > 0 and day_idx >= 0 else False
                        with acols[di + 1]:
                            if works_this_day:
                                st.markdown("✅")
                                day_counts[d_iso] = day_counts.get(d_iso, 0) + 1
                                person_days += 1
                            else:
                                st.markdown("·")
                    acols[-2].caption(f"**{person_days}**")

                    # 관리 버튼: ✏️ 수정 / ❌ 배정취소
                    with acols[-1]:
                        if not is_editing:
                            eb1, eb2 = st.columns(2)
                            with eb1:
                                if st.button("✏️", key=f"edit_{a_assign_id}", help=f"{a_name} 수정"):
                                    st.session_state['_editing_assign_id'] = a_assign_id
                                    st.rerun()
                            with eb2:
                                if st.button("↩️", key=f"unassign_{a_assign_id}", help=f"{a_name} 후보로 되돌리기"):
                                    with st.spinner("되돌리는 중..."):
                                        if db.unassign_from_role(a_assign_id):
                                            st.toast(f"↩️ {a_name} → 후보로 되돌림", icon="↩️")
                                            db.invalidate_dispatch_only()
                                            st.rerun()
                                        else:
                                            st.error("❌ 실패")

                    # 인라인 편집 폼
                    if is_editing:
                        with st.container():
                            st.caption(f"✏️ **{a_name}** 수정 중")
                            ec1, ec2, ec3 = st.columns(3)
                            with ec1:
                                # 직군 선택 — 기존 role_status에서 가져오기
                                role_options = [rs['role'] for rs in role_status] if role_status else []
                                if a_role and a_role not in role_options:
                                    role_options.insert(0, a_role)
                                edit_role_idx = role_options.index(a_role) if a_role in role_options else 0
                                edit_role = st.selectbox("직무", role_options, index=edit_role_idx,
                                                         key=f"edit_role_{a_assign_id}")
                            with ec2:
                                edit_pay = st.number_input("단가", value=a_pay, step=10000,
                                                           key=f"edit_pay_{a_assign_id}")
                            with ec3:
                                edit_days = st.number_input("일수", value=a_days, min_value=1,
                                                            key=f"edit_days_{a_assign_id}")
                            eb1, eb2 = st.columns(2)
                            with eb1:
                                if st.button("💾 저장", type="primary", use_container_width=True,
                                             key=f"save_edit_{a_assign_id}"):
                                    kwargs = {}
                                    if edit_role != a_role:
                                        kwargs['직무'] = edit_role
                                    if edit_pay != a_pay:
                                        kwargs['지급단가'] = edit_pay
                                    if edit_days != a_days:
                                        kwargs['근무일수'] = edit_days
                                    if kwargs:
                                        with st.spinner("저장 중..."):
                                            if db.update_assignment(a_assign_id, **kwargs):
                                                st.toast(f"✅ {a_name} 수정 완료", icon="✅")
                                                st.session_state.pop('_editing_assign_id', None)
                                                db.invalidate_dispatch_only()
                                                st.rerun()
                                            else:
                                                st.error("❌ 저장 실패")
                                    else:
                                        st.session_state.pop('_editing_assign_id', None)
                                        st.rerun()
                            with eb2:
                                if st.button("취소", use_container_width=True,
                                             key=f"cancel_edit_{a_assign_id}"):
                                    st.session_state.pop('_editing_assign_id', None)
                                    st.rerun()

            # 일자별 합계 행
            scols = st.columns([2.5] + [1] * len(page_dates) + [0.8, 0.8])
            scols[0].markdown("**필요/현재**")
            short_days = 0
            for di, dd in enumerate(page_dates):
                cnt = day_counts.get(dd.isoformat(), 0)
                if cnt >= total_needed_per_day:
                    icon = "🟢"
                elif cnt > 0:
                    icon = "🟡"
                else:
                    icon = "🔴"
                    short_days += 1
                scols[di + 1].caption(f"{icon}**{cnt}/{total_needed_per_day}**")
            total_mandays_page = sum(day_counts.values())
            scols[-2].caption(f"**{total_mandays_page}**")

            if total_pages > 1:
                st.caption(f"📄 {page + 1}/{total_pages} 페이지 (총 {len(event_dates)}일)")

            # 인일 요약
            st.divider()
            total_md_needed = sum(rs['needed_mandays'] for rs in role_status) if role_status else 0
            total_md_actual = sum(rs['actual_mandays'] for rs in role_status) if role_status else 0
            md_pct = (total_md_actual / total_md_needed * 100) if total_md_needed > 0 else 0
            md_icon = "✅" if md_pct >= 100 else ""

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("전체 인일", f"{total_md_actual}/{total_md_needed} {md_icon}")
            with m2:
                st.metric("배정 인원", f"{len(assigned)}명")
            with m3:
                st.metric("미배정 후보", f"{len(unassigned)}명")
            st.progress(min(md_pct / 100.0, 1.0))

    # ──────────────────────────────────────────
    # 우측: 후보 & 직군별 배정 UI (배치 저장 + 진행 표시)
    # ──────────────────────────────────────────
    with col_right:
        # ── 미배정 후보 목록 (상세정보 포함) ──
        st.markdown(f"##### 👥 미배정 후보 ({len(unassigned)}명)")
        if unassigned.empty:
            st.success("✅ 모든 후보가 직군에 배정되었습니다.")
        else:
            for idx, row in unassigned.iterrows():
                cname = row.get(name_col, 'N/A')
                ctype = row.get('구분', '외부')
                badge = "🏢" if ctype == '본사' else "👤"
                conflict_tag = ""
                if cname in conflict_map:
                    total_overlap = sum(len(c['겹치는날짜']) for c in conflict_map[cname])
                    conflict_tag = f" ⚠️{total_overlap}일충돌"
                # STAFF 정보 조회
                sinfo = _lookup_staff_brief(df_staff, cname)
                if sinfo:
                    phone_display = sinfo['연락처'] if sinfo['연락처'] else '-'
                    info_txt = f" {sinfo['성별']}/{sinfo['나이']} · 📱{phone_display} · ⭐{sinfo['총점']}"
                else:
                    info_txt = ""
                st.markdown(f"{badge} **{cname}**{info_txt}{conflict_tag}")

        st.divider()

        # ── 직군별 배정 UI (batch_assign_to_role + st.status) ──
        if role_status:
            for ri, rs in enumerate(role_status):
                role_name = rs['role']
                needed = rs['needed']
                pay_rate = rs['pay_rate']
                days = rs['days']

                role_assigned = assigned[
                    assigned[role_col_name].astype(str).str.contains(role_name, na=False)
                ] if not assigned.empty else pd.DataFrame()
                current_count = len(role_assigned)

                # 인일 기반 진행률
                md_p = (rs['actual_mandays'] / rs['needed_mandays'] * 100) if rs['needed_mandays'] > 0 else 0
                md_icon = '✅' if md_p >= 100 else ''

                with st.container():
                    rc1, rc2 = st.columns([2, 1])
                    with rc1:
                        st.markdown(f"**{role_name}** · ₩{pay_rate:,}/일 · {days}일")
                    with rc2:
                        over_tag = " 초과OK" if current_count > needed else ""
                        st.markdown(f"**{current_count}/{needed}명**{over_tag}")
                    st.progress(min(md_p / 100.0, 1.0))
                    st.caption(f"인일: {rs['actual_mandays']}/{rs['needed_mandays']} {md_icon}")

                # 이미 배정된 인력
                if not role_assigned.empty:
                    for _, rr in role_assigned.iterrows():
                        rr_name = rr.get(name_col, '')
                        rr_days = int(rr.get('근무일수', rr.get('일수', 0)) or 0)
                        ct = ""
                        if rr_name in conflict_map:
                            ct = f" ⚠️충돌"
                        st.caption(f"  ✔ {rr_name} ({rr_days}일){ct}")

                # 미배정 후보를 이 직군에 배정 (인원 초과 허용)
                has_manday_shortage = rs['actual_mandays'] < rs['needed_mandays']
                if not unassigned.empty and has_manday_shortage:
                    with st.expander(f"➕ {role_name}에 인력 배정", expanded=(ri == 0)):
                        candidate_names = [r.get(name_col, 'N/A') for _, r in unassigned.iterrows()]
                        candidate_ids = [r.get('배정ID', '') for _, r in unassigned.iterrows()]

                        selected_candidates = st.multiselect(
                            f"{role_name} 배정할 후보",
                            range(len(candidate_names)),
                            format_func=lambda x: f"{candidate_names[x]}{' ⚠️' if candidate_names[x] in conflict_map else ''}",
                            key=f"role_select_{ri}",
                        )

                        # ── 선택된 후보별 일자 체크 매트릭스 ──
                        if selected_candidates and event_dates and len(event_dates) <= 60:
                            st.markdown("**📅 근무일 체크**")
                            dates_pp = 7
                            tp = max(1, (len(event_dates) + dates_pp - 1) // dates_pp)
                            if tp > 1:
                                pg = st.number_input("주차", min_value=1, max_value=tp, value=1,
                                                     key=f"mp_{ri}") - 1
                            else:
                                pg = 0
                            pg_dates = event_dates[pg * dates_pp: (pg + 1) * dates_pp]

                            # 헤더
                            hc = st.columns([2] + [1] * len(pg_dates) + [0.7])
                            hc[0].caption("**이름**")
                            for di, dd in enumerate(pg_dates):
                                wd = '월화수목금토일'[dd.weekday()]
                                hc[di + 1].caption(f"{dd.strftime('%m/%d')}\n{wd}")
                            hc[-1].caption("**일**")

                            # 후보별 행
                            for ci in selected_candidates:
                                cname = candidate_names[ci]
                                cc = st.columns([2] + [1] * len(pg_dates) + [0.7])
                                lbl = f"⚠️{cname}" if cname in conflict_map else cname
                                cc[0].caption(lbl)

                                checked_days = 0
                                checked_dates_list = []
                                for di, dd in enumerate(pg_dates):
                                    d_iso = dd.isoformat()
                                    key = f"dc_{ri}_{ci}_{d_iso}"
                                    is_conflict = False
                                    if cname in conflict_map:
                                        for cf in conflict_map[cname]:
                                            if dd in cf['겹치는날짜']:
                                                is_conflict = True
                                                break
                                    with cc[di + 1]:
                                        chk = st.checkbox("✓", value=not is_conflict,
                                                          key=key, label_visibility="collapsed")
                                    if chk:
                                        checked_days += 1
                                        checked_dates_list.append(d_iso)
                                cc[-1].markdown(f"**{checked_days}**")
                                st.session_state[f"matrix_days_{ri}_{ci}"] = checked_days
                                st.session_state[f"matrix_dates_{ri}_{ci}"] = checked_dates_list

                        # 단가 + 근무일수
                        pc1, pc2 = st.columns(2)
                        with pc1:
                            assign_pay = st.number_input(
                                "단가(원/일)", value=pay_rate, step=10000, key=f"role_pay_{ri}")
                        with pc2:
                            if selected_candidates and event_dates and len(event_dates) <= 60:
                                auto_days = max(
                                    (st.session_state.get(f"matrix_days_{ri}_{ci}", days)
                                     for ci in selected_candidates), default=days)
                                assign_days = st.number_input(
                                    "근무일수(자동)", value=auto_days, min_value=1, key=f"role_days_{ri}")
                            else:
                                assign_days = st.number_input(
                                    "근무일수", value=days, min_value=1, key=f"role_days_{ri}")

                        if selected_candidates and st.button(
                                f"🎯 {len(selected_candidates)}명 → {role_name}",
                                type="primary", use_container_width=True, key=f"assign_role_{ri}"):
                            # 배치 배정: 1 API call로 N명 처리
                            batch_items = []
                            for ci in selected_candidates:
                                c_days = st.session_state.get(f"matrix_days_{ri}_{ci}", assign_days)
                                # 체크된 실제 날짜 목록 (쉼표구분 ISO)
                                c_dates = st.session_state.get(f"matrix_dates_{ri}_{ci}", [])
                                # 페이지에서만 체크했으므로, 전체 event_dates에서도 수집
                                # (현재 페이지 외 날짜는 전체 선택으로 보완)
                                all_checked = []
                                for dd in event_dates:
                                    d_iso = dd.isoformat()
                                    dk = f"dc_{ri}_{ci}_{d_iso}"
                                    if dk in st.session_state:
                                        if st.session_state[dk]:
                                            all_checked.append(d_iso)
                                    else:
                                        # 체크박스가 렌더되지 않은 날짜 → 기본 근무(충돌 없으면)
                                        cname = candidate_names[ci]
                                        is_cf = False
                                        if cname in conflict_map:
                                            for cf in conflict_map[cname]:
                                                if dd in cf['겹치는날짜']:
                                                    is_cf = True
                                                    break
                                        if not is_cf:
                                            all_checked.append(d_iso)
                                work_dates_str = ','.join(sorted(all_checked)) if all_checked else ''
                                final_days = len(all_checked) if all_checked else c_days
                                batch_items.append({
                                    'assign_id': candidate_ids[ci],
                                    'role': role_name,
                                    'pay_rate': assign_pay,
                                    'work_days': final_days,
                                    'work_dates': work_dates_str,
                                })
                            with st.status(f"🎯 {role_name} 배정 처리 중...", expanded=True) as status:
                                st.write(f"📋 {len(batch_items)}명 배정 데이터 준비 완료")
                                st.write("💾 Google Sheets에 일괄 저장 중...")
                                ok, fail = db.batch_assign_to_role(batch_items)
                                if ok > 0:
                                    status.update(label=f"✅ {ok}명 배정 완료!", state="complete")
                                    st.toast(f"✅ {ok}명 → {role_name} 배정 완료!", icon="🎯")
                                    db.invalidate_dispatch_only()
                                    import time; time.sleep(0.5)
                                    st.rerun()
                                else:
                                    status.update(label="❌ 배정 실패", state="error")
                                    st.error("❌ 배정 실패 — 데이터를 확인하세요.")
                elif not unassigned.empty:
                    st.caption(f"  ✅ {role_name} 인일 충족")

        else:
            # 자유 배정 모드 (batch)
            st.markdown("##### 자유 배정 모드")
            if not unassigned.empty:
                free_role = st.text_input("직군명", placeholder="예: 경호", key="free_role")
                free_pay = st.number_input("단가", value=100000, step=10000, key="free_pay")
                free_days = st.number_input("일수", value=1, min_value=1, key="free_days")
                candidate_names = [r.get(name_col, 'N/A') for _, r in unassigned.iterrows()]
                candidate_ids = [r.get('배정ID', '') for _, r in unassigned.iterrows()]
                selected = st.multiselect("후보 선택", range(len(candidate_names)),
                                           format_func=lambda x: candidate_names[x], key="free_select")
                if selected and free_role and st.button(
                        f"🎯 {len(selected)}명 → {free_role}",
                        type="primary", use_container_width=True, key="assign_free"):
                    # 자유배정: 근무일자도 함께 저장 (앞쪽 N일)
                    free_work_dates = ','.join(
                        dd.isoformat() for dd in event_dates[:free_days]
                    ) if event_dates else ''
                    batch_items = [{'assign_id': candidate_ids[ci], 'role': free_role,
                                    'pay_rate': free_pay, 'work_days': free_days,
                                    'work_dates': free_work_dates} for ci in selected]
                    with st.status(f"🎯 자유배정 처리 중...", expanded=True) as status:
                        st.write(f"📋 {len(batch_items)}명 배정 데이터 준비 완료")
                        st.write("💾 Google Sheets에 일괄 저장 중...")
                        ok, fail = db.batch_assign_to_role(batch_items)
                        if ok > 0:
                            status.update(label=f"✅ {ok}명 배정 완료!", state="complete")
                            st.toast(f"✅ {ok}명 → {free_role} 배정!", icon="🎯")
                            db.invalidate_dispatch_only()
                            import time; time.sleep(0.5)
                            st.rerun()
                        else:
                            status.update(label="❌ 배정 실패", state="error")

        # ── 배정 현황 요약 ──
        if not assigned.empty:
            st.divider()
            st.markdown("##### 📊 배정 요약")
            summary_data = []
            for _, row in assigned.iterrows():
                r_col_val = row.get(role_col_name, 'N/A')
                rate_val = int(row.get('지급단가', row.get('단가', 0)) or 0)
                days_val = int(row.get('근무일수', row.get('일수', 0)) or 0)
                r_name = row.get(name_col, '')
                ct = ""
                if r_name in conflict_map:
                    ct = f"⚠️"
                summary_data.append({
                    '인력': f"{ct}{r_name}",
                    '직무': r_col_val,
                    '단가': f"₩{rate_val:,}",
                    '일수': days_val,
                    '총액': f"₩{rate_val * days_val:,}",
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────────────────
# Step 3: 배정 확정 & 일정관리
# ──────────────────────────────────────────────────────────

def _step3_confirm_and_schedule(sel_id, sel, role_status, is_long_term, start_d, end_d):
    """배정 확정 + 장기건 일정 일괄입력"""

    st.markdown('<div class="section-title">✅ 배정 확정 & 일정관리</div>', unsafe_allow_html=True)

    if st.button("🔄 새로고침", key="refresh_confirm"):
        db.invalidate_dispatch_only()
        st.rerun()

    # 배정중 인력 (확정 대상)
    all_df = db.get_assignments_by_inquiry(sel_id)
    if all_df.empty:
        st.info("📌 아직 배정된 인력이 없습니다. ② 직군별 배정 탭에서 배정을 진행하세요.")
        return

    name_col = _col(all_df, '인력명', '이름')
    status_col = _col(all_df, '지급상태', '상태')
    role_col = _col(all_df, '직무', '역할')

    # 상태별 분리
    pending = all_df[all_df[status_col].astype(str).str.strip() == '배정중']
    confirmed = all_df[all_df[status_col].astype(str).str.contains('확정', na=False)]
    candidates_only = all_df[all_df[status_col].astype(str).str.strip() == '후보']

    # ── 배정중 인력 확정 ──
    if not pending.empty:
        st.markdown(f"##### 📋 배정 확정 대기 ({len(pending)}명)")
        st.caption("직군에 배정된 인력을 최종 확정합니다.")

        # 확인 테이블
        confirm_data = []
        for _, row in pending.iterrows():
            r_name = row.get(name_col, '')
            r_role = row.get(role_col, '')
            r_rate = int(row.get('지급단가', row.get('단가', 0)) or 0)
            r_days = int(row.get('근무일수', row.get('일수', 0)) or 0)
            confirm_data.append({
                '인력명': r_name, '구분': row.get('구분', ''), '직무': r_role,
                '단가': f"₩{r_rate:,}", '일수': r_days,
                '총액': f"₩{r_rate * r_days:,}",
                '배정ID': row.get('배정ID', '')
            })

        confirm_df = pd.DataFrame(confirm_data)
        disp_cols = ['인력명', '구분', '직무', '단가', '일수', '총액']
        st.dataframe(confirm_df[disp_cols], use_container_width=True, hide_index=True)

        # 선택적 확정
        select_all = st.checkbox("전체 선택", value=True, key="sel_all_confirm")
        selected_ids = []
        if not select_all:
            for idx, row in confirm_df.iterrows():
                if st.checkbox(f"{row['인력명']} — {row['직무']}", value=True,
                               key=f"confirm_sel_{idx}"):
                    selected_ids.append(row['배정ID'])
        else:
            selected_ids = confirm_df['배정ID'].tolist()

        # 확정 방식 선택
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if is_long_term:
                confirm_type = st.radio(
                    "확정 방식", ["일반 확정", "장기건 확정 (일정 추후입력)"],
                    index=1, key="confirm_type", horizontal=True)
            else:
                confirm_type = "일반 확정"

        with col_c2:
            pass

        if selected_ids:
            btn_label = f"✅ {len(selected_ids)}명 배정 확정"
            if '장기건' in confirm_type:
                btn_label += " (일정 추후입력)"

            if st.button(btn_label, type="primary", use_container_width=True, key="do_confirm"):
                is_lt = '장기건' in confirm_type
                with st.spinner("배정 확정 중..."):
                    ok, fail = db.batch_confirm_assignments(selected_ids, long_term=is_lt)
                if ok > 0:
                    _auto_update_status(sel_id, role_status)
                    db.invalidate_data()  # 문의 상태도 변경되므로 전체 캐시 초기화
                    st.balloons()
                    msg = f"✅ {ok}명 배정 확정 완료!"
                    if is_lt:
                        msg += " 아래에서 일정을 일괄입력할 수 있습니다."
                    st.success(msg)
                    st.rerun()
                else:
                    st.error("❌ 확정 실패")
    elif candidates_only.empty:
        pass  # 모두 확정 완료
    else:
        st.info("📌 ② 직군별 배정 탭에서 후보를 직군에 배정하세요.")

    # ── 확정된 인력 현황 ──
    if not confirmed.empty:
        st.divider()
        st.markdown(f"##### ✅ 확정된 인력 ({len(confirmed)}명)")
        display_cols = ['인력명', '이름', '구분', '직무', '역할', '지급단가', '단가', '근무일수', '일수', '총지급액', '지급상태', '상태']
        avail = [c for c in display_cols if c in confirmed.columns]
        st.dataframe(confirmed[avail], use_container_width=True, hide_index=True)

        # 개별 관리
        st.markdown("##### 🔧 배정 관리")
        manage_labels = [f"{row.get(name_col, 'N/A')} — {row.get(role_col, '-')}"
                         for _, row in confirmed.iterrows()]
        sel_manage = st.selectbox("대상", range(len(manage_labels)),
                                   format_func=lambda x: manage_labels[x], key="manage_confirmed")
        sel_row = confirmed.iloc[sel_manage]
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            pass
        with mc2:
            if st.button("❌ 취소", key="cancel_confirmed", use_container_width=True):
                aid = sel_row.get('배정ID', '')
                if aid and db.update_assignment_status(aid, '취소'):
                    db.invalidate_dispatch_only()
                    st.success("취소 완료")
                    st.rerun()
        with mc3:
            total_c = len(confirmed)
            hq_c = len(confirmed[confirmed['구분'].astype(str) == '본사']) if '구분' in confirmed.columns else 0
            st.metric("현황", f"외부 {total_c - hq_c} + 본사 {hq_c}")

    # ── 장기건 일정 일괄입력 ──
    # 확정(일정미입력) 상태인 인력이 있으면 표시
    schedule_pending = all_df[
        all_df[status_col].astype(str).str.contains('일정미입력', na=False)
    ] if not all_df.empty else pd.DataFrame()

    if not schedule_pending.empty:
        st.divider()
        st.markdown(f'<div class="section-title">📅 장기건 일정 일괄입력 ({len(schedule_pending)}명)</div>',
                    unsafe_allow_html=True)
        st.caption("💡 확정된 인력의 근무일수, 단가, 총지급액을 일괄로 입력하세요. "
                   "이후 출석/근무 탭에서 일자별 스케줄를 관리할 수 있습니다.")

        schedule_data = []
        for idx, row in schedule_pending.iterrows():
            r_name = row.get(name_col, '')
            r_role = row.get(role_col, '')
            r_aid = row.get('배정ID', '')
            current_rate = int(row.get('지급단가', row.get('단가', 0)) or 0)
            current_days = int(row.get('근무일수', row.get('일수', 0)) or 0)

            st.markdown(f"**{r_name}** ({r_role})")
            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                s_rate = st.number_input("단가", value=current_rate, step=10000,
                                          key=f"sched_rate_{idx}")
            with sc2:
                s_days = st.number_input("일수", value=current_days if current_days > 0 else 1,
                                          min_value=1, key=f"sched_days_{idx}")
            with sc3:
                s_total = s_rate * s_days
                st.metric("총액", f"₩{s_total:,}")

            schedule_data.append({
                '배정ID': r_aid, '지급단가': s_rate,
                '근무일수': s_days, '총지급액': s_total
            })

        # 전체 합계
        grand_total = sum(s['총지급액'] for s in schedule_data)
        st.markdown(f"**총 예상 지급액: ₩{grand_total:,}**")

        if st.button("💾 일정 일괄 저장", type="primary", use_container_width=True, key="save_batch_schedule"):
            with st.spinner("일정 저장 중..."):
                ok, fail = db.batch_update_schedule(schedule_data)
            if ok > 0:
                db.invalidate_dispatch_only()
                st.balloons()
                st.success(f"✅ {ok}명 일정 입력 완료! 이제 출석/근무 탭에서 상세 스케줄을 관리하세요.")
                st.rerun()
            else:
                st.error("❌ 저장 실패")


# ==============================================================================
# 2. 탭2: 출석/근무
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

    name_col = _col(assignments_df, '인력명', '이름') or '인력명'
    rate_col = _col(assignments_df, '지급단가', '단가') or '지급단가'
    current_status = str(sel.get('상태', ''))

    st.markdown(f"**{sel.get('행사명', '')}** — 배정 인력 {len(assignments_df)}명 · 상태: {current_status}")

    # ── 행사완료 처리 ──
    if current_status == '진행중':
        if st.button("🏁 행사 완료 처리", type="primary", key="complete_event"):
            db.update_status(sel_id, sc.STATUS_FLOW[5])  # '완료'
            db.invalidate_data()
            st.balloons()
            st.success("✅ 행사가 완료 처리되었습니다. 이제 정산을 진행하세요.")
            st.rerun()
    elif current_status == '완료':
        st.success("✅ 행사 완료 — 정산 페이지에서 후속 처리를 진행하세요.")

    st.divider()

    # ── 다일 행사 스케줄표 (일차별 인원 배분) ──
    raw_start = str(sel.get('행사시작일', '')).strip()
    raw_end = str(sel.get('행사종료일', '')).strip()
    if '/' in raw_start:
        _parts = [p.strip() for p in raw_start.split('/') if p.strip()]
        start_date = _parse_date_safe(_parts[0]) if _parts else None
    else:
        start_date = _parse_date_safe(raw_start)
    if '/' in raw_end:
        _parts = [p.strip() for p in raw_end.split('/') if p.strip()]
        end_date = _parse_date_safe(_parts[-1]) if _parts else None
    else:
        end_date = _parse_date_safe(raw_end)
    
    if start_date and end_date and (end_date - start_date).days >= 1:
        num_days = (end_date - start_date).days + 1
        st.markdown(f'<div class="section-title">📅 일자별 스케줄표 ({num_days}일 행사)</div>', unsafe_allow_html=True)
        st.caption("💡 각 인력의 일자별 투입 여부를 체크하세요.")
        
        date_list = [start_date + timedelta(days=d) for d in range(num_days)]
        date_labels = [f"{d.month}/{d.day}({['월','화','수','목','금','토','일'][d.weekday()]})" for d in date_list]
        
        sched_key = f"schedule_{sel_id}"
        if sched_key not in st.session_state:
            st.session_state[sched_key] = {
                str(row.get(name_col, '')): [True] * num_days
                for _, row in assignments_df.iterrows()
            }
        
        schedule_data = st.session_state[sched_key]
        
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
        
        header_cols = st.columns([2] + [1] * visible_count)
        with header_cols[0]:
            st.markdown("**인력명**")
        for di, dl in enumerate(visible_dates):
            with header_cols[di + 1]:
                st.markdown(f"**{dl}**")
        
        daily_counts = [0] * visible_count
        for row_idx, (_, row) in enumerate(assignments_df.iterrows()):
            staff_name = str(row.get(name_col, ''))
            role = str(row.get('직무', row.get('역할', '')))
            assign_id = str(row.get('배정ID', row_idx))
            
            sched_name_key = f"{staff_name}_{assign_id}"
            if sched_name_key not in schedule_data:
                schedule_data[sched_name_key] = [True] * num_days
            
            row_cols = st.columns([2] + [1] * visible_count)
            with row_cols[0]:
                st.markdown(f"👤 **{staff_name}** <span style='color:#6B7280;font-size:12px;'>({role})</span>", unsafe_allow_html=True)
            
            for di in range(visible_count):
                actual_di = day_start + di
                with row_cols[di + 1]:
                    checked = st.checkbox(
                        "✓", value=schedule_data[sched_name_key][actual_di],
                        key=f"sched_{sel_id}_{staff_name}_{assign_id}_{actual_di}",
                        label_visibility="collapsed"
                    )
                    schedule_data[sched_name_key][actual_di] = checked
                    if checked:
                        daily_counts[di] += 1
        
        st.markdown("---")
        summary_cols = st.columns([2] + [1] * visible_count)
        with summary_cols[0]:
            st.markdown("**일자별 인원**")
        for di in range(visible_count):
            with summary_cols[di + 1]:
                st.markdown(f"**{daily_counts[di]}명**")
        
        st.session_state[sched_key] = schedule_data
        st.divider()

    # ── 출석 날짜 ──
    today = datetime.now().date()
    if start_date and end_date:
        default_date = max(start_date, min(today, end_date))
        att_date = st.date_input("출석 날짜", value=default_date,
                                 min_value=start_date, max_value=end_date, key="att_date")
        st.caption(f"📅 행사 기간: {start_date} ~ {end_date}")
    elif start_date:
        att_date = st.date_input("출석 날짜", value=max(start_date, today), key="att_date")
    else:
        att_date = st.date_input("출석 날짜", value=today, key="att_date")

    # ── 출퇴근 시간 ──
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
            db.invalidate_data()
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
                db.invalidate_data()
                st.balloons()
                st.success("✅ 평가 저장 완료!")
            else:
                st.error("❌ 평가 저장 실패")


# ==============================================================================
# 4. 탭4: 지급 (수동 편집, 자동수당/세금 제외)
# ==============================================================================

def tab_payment(data):
    """지급 — 통합 테이블 + 변동내역 + 이체관리 + 엑셀 다운"""
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
    st.caption("💡 단가·일수를 수정하면 기본급→공제→실수령이 자동 계산. `+`로 충원 인원 추가. 메모로 변경사유 기록.")

    # 공제율 일괄 기본값
    TAX_OPTIONS = ["3.3%", "0.9%", "공제없음"]
    tax_opt_col, _ = st.columns([1.5, 1.5])
    with tax_opt_col:
        tax_choice = st.radio(
            "💰 기본 공제 방식",
            ["3.3% 공제 (사업소득세)", "0.9% 공제 (일용직)", "공제 없음 (0%)"],
            key=f"pay_tax_choice_{sel_id}",
            horizontal=True,
        )
    if "3.3%" in tax_choice:
        default_tax_label = "3.3%"
    elif "0.9%" in tax_choice:
        default_tax_label = "0.9%"
    else:
        default_tax_label = "공제없음"

    def _parse_tax_rate(label):
        if '3.3' in str(label): return 0.033
        if '0.9' in str(label): return 0.009
        return 0.0

    hq_names = [s['이름'] for s in db.HQ_STAFF] if hasattr(db, 'HQ_STAFF') else []

    # 원본 데이터 + 편집용 DataFrame
    orig_data = {}
    pay_data = []
    for _, row in assignments_df.iterrows():
        name = row.get(name_col, '')
        category = row.get('구분', '외부')
        base_rate = int(row.get(rate_col, 0) or 0)
        days = int(row.get(days_col, 0) or 0)
        is_hq = name in hq_names or category == '본사'
        orig_data[name] = {'단가': base_rate, '일수': days}

        pay_data.append({
            '이체': False,
            '인력명': name,
            '구분': '본사' if is_hq else category,
            '공제율': default_tax_label,
            '별도': True if is_hq else False,
            '지급단가': base_rate,
            '근무일수': days,
            '기본급': base_rate * days,
            '공제': 0,
            '실수령': base_rate * days,
            '메모': '',
            '배정ID': row.get('배정ID', ''),
        })

    pay_df = pd.DataFrame(pay_data)

    edited_df = st.data_editor(
        pay_df.drop(columns=['배정ID']),
        disabled=['인력명', '구분', '기본급', '공제', '실수령'],
        use_container_width=True, hide_index=True, key="pay_editor",
        num_rows="dynamic",
        column_config={
            '이체': st.column_config.CheckboxColumn("이체✓", width=50, help="이체 완료 체크"),
            '인력명': st.column_config.TextColumn("이름", width=75),
            '구분': st.column_config.TextColumn("구분", width=50),
            '공제율': st.column_config.SelectboxColumn("공제율", width=80, options=TAX_OPTIONS),
            '별도': st.column_config.CheckboxColumn("별도", width=45, help="별도정산 → 합계 제외"),
            '지급단가': st.column_config.NumberColumn("단가", width=85, format="%d", min_value=0, step=10000),
            '근무일수': st.column_config.NumberColumn("일수", width=50, min_value=0, step=1),
            '기본급': st.column_config.NumberColumn("기본급", width=85, format="%d"),
            '공제': st.column_config.NumberColumn("공제", width=70, format="%d"),
            '실수령': st.column_config.NumberColumn("실수령", width=85, format="%d"),
            '메모': st.column_config.TextColumn("메모", width=130),
        }
    )

    # 자동 계산 + 변동 감지
    calc_rows = []
    for i, prow in edited_df.iterrows():
        rate = int(prow.get('지급단가', 0) or 0)
        days = int(prow.get('근무일수', 0) or 0)
        is_sep = bool(prow.get('별도', False))
        tax_r = _parse_tax_rate(prow.get('공제율', default_tax_label))
        basic = rate * days
        tax = int(basic * tax_r) if not is_sep else 0
        net = basic - tax
        name = str(prow.get('인력명', '')).strip()

        changes = []
        if name in orig_data:
            o = orig_data[name]
            if rate != o['단가']: changes.append(f"단가 {o['단가']:,}→{rate:,}")
            if days != o['일수']: changes.append(f"일수 {o['일수']}→{days}")
        elif name and name != '':
            changes.append("신규 충원")

        calc_rows.append({
            'name': name, 'sep': is_sep, 'paid': bool(prow.get('이체', False)),
            'basic': basic, 'tax': tax, 'net': net, 'changes': changes,
            'memo': str(prow.get('메모', '')), 'tax_label': str(prow.get('공제율', default_tax_label)),
            'days': days,
        })

    # 변동내역 배지
    changed = [(r['name'], r['changes']) for r in calc_rows if r['changes']]
    if changed:
        badges = " ".join(
            f'<span style="background:#FEF3C7;color:#92400E;padding:3px 8px;border-radius:6px;font-size:12px;margin:2px;">'
            f'⚡ {n}: {", ".join(c)}</span>' for n, c in changed
        )
        st.markdown(f'<div style="background:#FFFBEB;border:1px solid #F59E0B;border-radius:8px;padding:8px 12px;margin:6px 0;">'
                     f'<b style="font-size:12px;">📋 변동내역</b><br/>{badges}</div>', unsafe_allow_html=True)

    # 요약 메트릭 (별도정산 제외)
    normal = [r for r in calc_rows if not r['sep']]
    paid_count = sum(1 for r in calc_rows if r['paid'])
    total_basic = sum(r['basic'] for r in normal)
    total_tax = sum(r['tax'] for r in normal)

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("지급 대상", f"{len(normal)}명")
    mc2.metric("총 기본급", f"₩{total_basic:,}")
    mc3.metric("공제→실수령", f"₩{total_basic - total_tax:,}")
    mc4.metric("이체 진행", f"{paid_count}/{len(calc_rows)}명")
    sep_count = len(calc_rows) - len(normal)
    if sep_count > 0:
        st.caption(f"🔸 별도정산 {sep_count}명은 위 합계에 미포함")

    col_p1, col_p2 = st.columns(2)
    pay_date = col_p1.date_input("지급일", value=datetime.now().date(), key="pay_date")
    pay_status = col_p2.selectbox("지급상태", ["대기", "확정", "완료"], key="pay_status_sel")

    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        if st.button("💾 지급 내역 저장", type="primary", use_container_width=True, key="save_pay"):
            saved = 0
            skipped = 0
            with st.spinner("저장 중..."):
                for i, cr in enumerate(calc_rows):
                    if cr['sep']:
                        skipped += 1
                        continue
                    if cr['basic'] <= 0:
                        continue
                    period = f"{sel.get('행사시작일', '')}~{sel.get('행사종료일', '')}"
                    a_id = pay_df.iloc[i]['배정ID'] if i < len(pay_df) else ''
                    payment_dict = {
                        '배정ID': a_id,
                        '인력명': cr['name'],
                        '현장명': sel.get('행사명', ''),
                        '파견기간': period,
                        '파견일수': cr['days'],
                        '기본급': cr['basic'],
                        '야근비': 0, '식사비': 0, '교통비': 0, '보너스': 0,
                        '소계': cr['basic'],
                        '세금공제': cr['tax'],
                        '최종지급액': cr['net'],
                        '지급상태': pay_status,
                        '지급일': pay_date.strftime('%Y-%m-%d'),
                        '지급담당자': '',
                        '비고': f"{cr['tax_label']} 공제" + (f" | {cr['memo']}" if cr['memo'] else ""),
                    }
                    if db.save_payment_record(payment_dict):
                        saved += 1
            if saved > 0:
                db.invalidate_data()
                st.balloons()
                msg = f"✅ {saved}명 저장!"
                if skipped > 0: msg += f" ({skipped}명 별도정산 제외)"
                st.success(msg)
            else:
                st.error("❌ 저장 실패")

    with btn_c2:
        # 은행이체 엑셀 다운로드
        import io as _io
        xfer_rows = []
        for cr in calc_rows:
            if cr['sep'] or cr['net'] <= 0:
                continue
            xfer_rows.append({'이름': cr['name'], '이체금액': cr['net'], '메모': cr['memo'] or f"{sel.get('행사명','')} 급여"})
        if xfer_rows:
            buf = _io.BytesIO()
            pd.DataFrame(xfer_rows).to_excel(buf, index=False, sheet_name='이체목록')
            buf.seek(0)
            st.download_button("📥 이체용 엑셀", data=buf.getvalue(),
                              file_name=f"이체_{sel.get('행사명','')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              use_container_width=True, key=f"dl_xls_{sel_id}")
        else:
            st.button("📥 이체용 엑셀", disabled=True, use_container_width=True, key=f"dl_xls_{sel_id}")


# ==============================================================================
# 5. 메인 페이지
# ==============================================================================

def show(data):
    apply_styles()
    st.title("👥 인력파견 시스템 v5.1")

    st.markdown("""
    <div style="background: linear-gradient(135deg, #EFF6FF, #F0FDF4); border: 1px solid #BFDBFE;
                border-radius: 12px; padding: 12px 18px; margin-bottom: 14px;">
        <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; flex-wrap: wrap;">
            <span style="background:#DBEAFE;color:#1E40AF;padding:4px 10px;border-radius:8px;font-weight:600;">①후보등록</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#C7D2FE;color:#3730A3;padding:4px 10px;border-radius:8px;font-weight:600;">②직군배정</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#D1FAE5;color:#065F46;padding:4px 10px;border-radius:8px;font-weight:600;">③배정확정</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#FEF3C7;color:#92400E;padding:4px 10px;border-radius:8px;font-weight:600;">📋출석/근무</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#EDE9FE;color:#5B21B6;padding:4px 10px;border-radius:8px;font-weight:600;">⭐평가</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#FEE2E2;color:#991B1B;padding:4px 10px;border-radius:8px;font-weight:600;">💰지급</span>
            <span style="color:#9CA3AF;">→</span>
            <span style="background:#F3F4F6;color:#374151;padding:4px 10px;border-radius:8px;font-weight:600;">💰정산</span>
        </div>
        <div style="font-size:11px;color:#6B7280;margin-top:6px;">
            💡 장기건: ③에서 '일정 추후입력'으로 확정 → 일괄입력 가능
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
