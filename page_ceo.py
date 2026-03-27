# page_ceo.py — 대표님 전용 페이지
# 세금계산서 발행 현황 + 인력비 미지급 현황을 한눈에 확인하고 즉시 처리
# 정산 페이지(page_settlement.py)와 동일한 team_info/calc_rows 로직 사용
import streamlit as st
import pandas as pd
import data_loader as db
import utils_dashboard as ud
import time
from datetime import datetime, timedelta
from helpers import now_kst, today_kst


# ==============================================================================
# 1. 스타일
# ==============================================================================
def _apply_styles():
    st.markdown(
        '<style>'
        '.ceo-kpi{border-radius:14px;padding:18px 14px;text-align:center;'
        'box-shadow:0 2px 10px rgba(0,0,0,0.08);min-height:110px;}'
        '.ceo-kpi .kpi-label{font-size:13px;font-weight:600;opacity:0.85;margin-bottom:6px;}'
        '.ceo-kpi .kpi-value{font-size:32px;font-weight:800;margin:6px 0;}'
        '.ceo-kpi .kpi-sub{font-size:12px;opacity:0.7;}'
        '.ceo-card{background:white;border:1px solid #e5e7eb;border-radius:10px;'
        'padding:20px;margin-bottom:12px;border-left:4px solid #EF4444;transition:all 0.15s;}'
        '.ceo-card:hover{box-shadow:0 2px 8px rgba(0,0,0,0.12);}'
        '.ceo-card.done{border-left-color:#10B981;background:#F0FDF4;}'
        '.ceo-card .card-title{font-size:18px;font-weight:700;color:#1e293b;margin-bottom:8px;}'
        '.ceo-card .card-detail{font-size:14px;color:#4b5563;line-height:1.9;}'
        '.ceo-card .card-amount{font-size:17px;font-weight:700;color:#DC2626;}'
        '.ceo-section{font-size:20px;font-weight:700;color:#111827;margin-bottom:14px;'
        'padding-left:10px;border-left:4px solid #6366F1;}'
        '[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child button[kind="primary"]{'
        'margin-top:0 !important;}'
        '[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child {'
        'display:flex;align-items:flex-start;padding-top:4px;}'
        '</style>',
        unsafe_allow_html=True,
    )


# ==============================================================================
# 2. 데이터 로드 헬퍼
# ==============================================================================
def _load_all_ceo_data():
    """세금계산서(settlement) + 배정/지급 + STAFF 데이터를 한 번에 로드"""
    dispatch_data = db.get_dispatch()
    settlement_df = dispatch_data.get('settlement', pd.DataFrame())
    dispatch_df = dispatch_data.get('dispatch', pd.DataFrame())
    payment_df = dispatch_data.get('payment', pd.DataFrame())
    staff_df = dispatch_data.get('staff', pd.DataFrame())
    if not settlement_df.empty:
        settlement_df = settlement_df.fillna('').copy()
        settlement_df.columns = [str(c).replace('\n', ' ').strip() for c in settlement_df.columns]
    return settlement_df, dispatch_df, payment_df, staff_df


def _find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    for c in candidates:
        for col in df.columns:
            if c in col:
                return col
    return None


def _parse_tax_rate(label):
    if '3.3' in str(label):
        return 0.033
    if '0.9' in str(label):
        return 0.009
    return 0.0


# ==============================================================================
# 3. 세금계산서 현황 분석
# ==============================================================================
def _get_tax_invoice_stats(settlement_df):
    col_company = col_tax_issued = col_inq_id = None
    for col in settlement_df.columns:
        if col in ('업체', '업체명') and not col_company:
            col_company = col
        if '발행여부' in col or '세금계산서' in col:
            col_tax_issued = col
        if col == '문의ID':
            col_inq_id = col
    if not col_tax_issued or not col_company:
        return 0, 0, pd.DataFrame(), col_tax_issued, col_company, col_inq_id
    issued = settlement_df[
        settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)
    ]
    not_issued = settlement_df[
        ~settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)
    ]
    return len(issued), len(not_issued), not_issued, col_tax_issued, col_company, col_inq_id


# ==============================================================================
# 4. 인력비 현황 분석 — 정산 페이지와 동일한 team_info + calc_rows 로직
# ==============================================================================
def _get_bank_info_from_staff(staff_name, staff_df):
    """STAFF 시트에서 이름으로 은행/계좌 검색 (정산 페이지와 동일 로직)"""
    if staff_df.empty:
        return '', ''
    name_c = None
    for c in ['이름', '인력명', '성명']:
        if c in staff_df.columns:
            name_c = c
            break
    if not name_c:
        return '', ''
    matched = staff_df[staff_df[name_c].astype(str).str.strip() == str(staff_name).strip()]
    if matched.empty:
        return '', ''
    r = matched.iloc[0]
    bank = str(r.get('은행명', r.get('은행', ''))).strip()
    account = str(r.get('계좌번호', r.get('계좌', ''))).strip()
    bank = bank if bank and bank not in ('nan', 'None', '') else ''
    account = account if account and account not in ('nan', 'None', '') else ''
    return bank, account


def _extract_tax_label_from_remark(remark_str):
    """지급내역 비고란에서 공제율 라벨 추출 (예: '3.3% 공제' → '3.3%')"""
    remark = str(remark_str)
    if '3.3%' in remark:
        return '3.3%'
    if '0.9%' in remark:
        return '0.9%'
    if '공제없음' in remark or '공제 없음' in remark:
        return '공제없음'
    return ''


def _build_inquiry_payment_data(dispatch_df, payment_df, staff_df=None):
    """
    문의ID별로 배정기록을 그룹핑한 뒤, 정산 페이지와 동일하게
    team_info(팀 그룹핑) + calc_rows(급여 계산) 를 구성.
    Returns: list of dicts (각 문의별 급여 데이터)
    """
    if staff_df is None:
        staff_df = pd.DataFrame()
    if dispatch_df.empty:
        return [], 0, 0, 0

    # 취소/후보 상태 제외 (정산 페이지 get_assignments_by_inquiry와 동일)
    _status_col = _find_col(dispatch_df, ["지급상태", "상태"])
    if _status_col:
        _exclude = ['취소', '후보']
        dispatch_df = dispatch_df[~dispatch_df[_status_col].astype(str).str.strip().isin(_exclude)].copy()
        if dispatch_df.empty:
            return [], 0, 0, 0

    # 컬럼 찾기
    col_name = _find_col(dispatch_df, ["인력명", "이름", "성명"])
    col_venue = _find_col(dispatch_df, ["현장명", "행사명"])
    col_rate = _find_col(dispatch_df, ["단가", "지급단가"])
    col_days = _find_col(dispatch_df, ["일수", "근무일수"])
    col_total = _find_col(dispatch_df, ["총지급액"])
    col_assign_id = _find_col(dispatch_df, ["배정ID"])
    col_inq_id = _find_col(dispatch_df, ["문의ID"])
    col_bank = _find_col(dispatch_df, ["은행명", "은행"])
    col_acct = _find_col(dispatch_df, ["계좌번호", "계좌"])
    col_pay_target = _find_col(dispatch_df, ["결제대상"])
    col_team_code = _find_col(dispatch_df, ["팀코드"])
    col_onsite = _find_col(dispatch_df, ["현장참여"])
    col_role = _find_col(dispatch_df, ["역할", "직무"])
    col_date = _find_col(dispatch_df, ["파견일자", "파견기간", "날짜"])

    if not col_name or not col_inq_id:
        return [], 0, 0, 0

    hq_names = [s['이름'] for s in db.HQ_STAFF] if hasattr(db, 'HQ_STAFF') else []

    # 지급상태 맵 (전체 payment)
    pay_status_map = {}  # 배정ID → 지급상태
    pay_record_map = {}  # 배정ID → payment row dict
    if not payment_df.empty:
        _pb = _find_col(payment_df, ["배정ID"])
        _ps = _find_col(payment_df, ["지급상태"])
        if _pb and _ps:
            for _, pr in payment_df.iterrows():
                bid = str(pr.get(_pb, '')).strip()
                if bid:
                    pay_status_map[bid] = str(pr.get(_ps, '')).strip()
                    pay_record_map[bid] = pr

    # 문의ID별 그룹핑
    grouped = dispatch_df.groupby(dispatch_df[col_inq_id].astype(str).str.strip())

    all_venue_data = []
    total_done = 0
    total_all = 0
    total_unpaid_amt = 0

    for inq_id, inq_df in grouped:
        if not inq_id or inq_id in ('nan', 'None', ''):
            continue

        venue_name = str(inq_df.iloc[0].get(col_venue, '')) if col_venue and col_venue in inq_df.columns else inq_id

        # ── team_info 구성 (정산 페이지와 동일) ──
        team_info = {}
        if col_team_code and col_pay_target:
            for _, tr in inq_df.iterrows():
                tc = str(tr.get(col_team_code, '')).strip()
                if not tc:
                    continue
                if tc not in team_info:
                    team_info[tc] = {'members': [], 'leader': None, 'sum_amount': 0,
                                     'per_rate': 0, 'per_days': 0, 'onsite_count': 0,
                                     'member_details': []}
                t_name = str(tr.get(col_name, ''))
                t_rate = int(float(tr.get(col_rate, 0) or 0)) if col_rate else 0
                t_days = int(float(tr.get(col_days, 1) or 1)) if col_days else 1
                # 지급내역 파견일수로 override (정산 시 수정된 값 반영)
                _t_aid = str(tr.get(col_assign_id, '')).strip() if col_assign_id else ''
                _t_pr = pay_record_map.get(_t_aid, {})
                if hasattr(_t_pr, 'get'):
                    _pr_days = ud.safe_int(_t_pr.get('파견일수', 0))
                    if _pr_days > 0:
                        t_days = _pr_days
                is_pay = str(tr.get(col_pay_target, 'Y')).strip().upper() == 'Y'
                is_onsite = str(tr.get(col_onsite, 'Y')).strip().upper() != 'N' if col_onsite else True

                team_info[tc]['members'].append(t_name)
                team_info[tc]['member_details'].append({
                    'name': t_name,
                    'rate': t_rate,
                    'days': t_days,
                    'is_pay': is_pay,
                    'is_onsite': is_onsite,
                })
                if is_onsite:
                    team_info[tc]['sum_amount'] += t_rate * t_days
                    team_info[tc]['onsite_count'] += 1
                team_info[tc]['per_rate'] = t_rate
                team_info[tc]['per_days'] = t_days
                if is_pay:
                    team_info[tc]['leader'] = t_name

        # ── calc_rows 구성 (정산 페이지와 동일) ──
        calc_rows = []
        for _, arow in inq_df.iterrows():
            a_name = str(arow.get(col_name, '')) if col_name else ''
            a_role = str(arow.get(col_role, '')) if col_role else ''
            a_rate = int(float(arow.get(col_rate, 0) or 0)) if col_rate else 0
            a_days = int(float(arow.get(col_days, 1) or 1)) if col_days else 1
            a_aid = str(arow.get(col_assign_id, '')).strip() if col_assign_id else ''
            # 지급내역 파견일수로 override (정산 시 수정된 값 반영)
            _ind_pr = pay_record_map.get(a_aid, {})
            if hasattr(_ind_pr, 'get'):
                _pr_days = ud.safe_int(_ind_pr.get('파견일수', 0))
                if _pr_days > 0:
                    a_days = _pr_days
            a_bank = str(arow.get(col_bank, '')).strip() if col_bank else ''
            a_acct = str(arow.get(col_acct, '')).strip() if col_acct else ''
            a_date = str(arow.get(col_date, '')).strip() if col_date else ''

            # 은행/계좌 폴백: STAFF 시트 → 배정 시트 (정산 페이지와 동일 2단계)
            staff_bank, staff_acct = _get_bank_info_from_staff(a_name, staff_df)
            if not a_bank or a_bank in ('nan', 'None', ''):
                a_bank = staff_bank
            if not a_acct or a_acct in ('nan', 'None', ''):
                a_acct = staff_acct
            tc = str(arow.get(col_team_code, '')).strip() if col_team_code else ''
            is_pay = str(arow.get(col_pay_target, 'Y')).strip().upper() == 'Y' if col_pay_target else True
            is_hq = a_name in hq_names

            # 팀원(결제대상=N)은 메인 목록에서 제외 (팀장에 합산)
            if tc and not is_pay:
                continue

            # 팀장이면 팀 합산 기본급 사용
            if tc and tc in team_info:
                ti = team_info[tc]
                basic = ti['sum_amount']
            else:
                basic = a_rate * a_days

            # 지급내역에서 상세 금액 가져오기 (저장된 경우)
            pr = pay_record_map.get(a_aid, {})
            tax_label = ''  # 공제율 라벨
            if hasattr(pr, 'get'):
                meal = ud.safe_int(pr.get('식사비', 0))
                transport = ud.safe_int(pr.get('교통비', 0))
                overtime = ud.safe_int(pr.get('야근비', 0))
                etc_cost = ud.safe_int(pr.get('보너스', 0))
                saved_gross = ud.safe_int(pr.get('소계', 0))
                saved_tax = ud.safe_int(pr.get('세금공제', 0))
                saved_net = ud.safe_int(pr.get('최종지급액', 0))
                # 비고란에서 공제율 복원
                remark = str(pr.get('비고', ''))
                tax_label = _extract_tax_label_from_remark(remark)
                # 비고란에서 기타항목명 + 메모 복원
                import re as _re
                _etc_match = _re.search(r'\[기타:([^\]]+)\]', remark)
                _etc_label = _etc_match.group(1) if _etc_match else '기타(숙박등)'
                # 메모: | 구분자 뒤 텍스트에서 태그/플래그 제외한 순수 메모
                _memo_text = ''
                if '|' in remark:
                    _after_pipe = remark.split('|', 1)[1].strip()
                    # 태그 제거 후 남은 텍스트
                    _memo_text = _re.sub(r'\[[^\]]*\]', '', _after_pipe).strip()
                if not _memo_text:
                    # | 없이 비고 끝에 메모를 쓴 경우: 공제율/태그 제거 후 남은 텍스트
                    _cleaned = _re.sub(r'\[[^\]]*\]', '', remark)  # 태그 제거
                    _cleaned = _re.sub(r'\d+\.\d+%\s*공제', '', _cleaned)  # 공제율 제거
                    _cleaned = _cleaned.replace('본사인원', '').replace('확인완료', '').strip()
                    if _cleaned and _cleaned not in ('공제', ''):
                        _memo_text = _cleaned
                # 지급내역에 은행/계좌가 있으면 우선 사용 (가장 최신)
                pr_bank = str(pr.get('은행명', '')).strip()
                pr_acct = str(pr.get('계좌번호', '')).strip()
                if pr_bank and pr_bank not in ('nan', 'None', ''):
                    a_bank = pr_bank
                if pr_acct and pr_acct not in ('nan', 'None', ''):
                    a_acct = pr_acct
            else:
                meal = transport = overtime = etc_cost = 0
                saved_gross = saved_tax = saved_net = 0
                _etc_label = '기타(숙박등)'
                _memo_text = ''

            # 지급상태
            pst = pay_status_map.get(a_aid, '미저장')

            # 공제율 결정: 비고란 > 세금공제 역산 > 기본 3.3%
            if not tax_label:
                if saved_gross > 0 and saved_tax > 0:
                    ratio = saved_tax / saved_gross
                    if abs(ratio - 0.033) < 0.005:
                        tax_label = '3.3%'
                    elif abs(ratio - 0.009) < 0.003:
                        tax_label = '0.9%'
                    else:
                        tax_label = '3.3%'
                elif saved_tax == 0 and saved_net > 0:
                    tax_label = '공제없음'
                else:
                    tax_label = '3.3%'  # 미저장 시 기본
            tax_rate = _parse_tax_rate(tax_label)

            # 금액 결정: 지급내역 저장된 게 있으면 그걸 사용 (정산 페이지와 동일한 값)
            if saved_net > 0:
                gross = saved_gross
                tax = saved_tax
                net = saved_net
            else:
                gross = basic + meal + transport + overtime + etc_cost
                tax = int(gross * tax_rate)
                net = gross - tax

            calc_rows.append({
                '이름': a_name,
                '직무': a_role,
                '구분': '본사' if is_hq else '',
                '단가': a_rate,
                '일수': a_days,
                '기본급': basic,
                '식비': meal,
                '교통비': transport,
                '연장': overtime,
                '기타': etc_cost,
                '기타항목명': _etc_label,
                '메모': _memo_text,
                '총액': gross,
                '공제': tax,
                '실수령': net,
                '공제율': tax_label,
                '은행': a_bank,
                '계좌': a_acct,
                '날짜': a_date,
                '배정ID': a_aid,
                '팀코드': tc,
                '지급상태': pst,
                '본사': is_hq,
            })

        # 통계
        for cr in calc_rows:
            total_all += 1
            if cr['지급상태'] in ('완료', '확인완료'):
                total_done += 1
            elif not cr['본사']:
                total_unpaid_amt += cr['실수령']

        if calc_rows:
            all_venue_data.append({
                'inq_id': inq_id,
                'venue': venue_name,
                'team_info': team_info,
                'calc_rows': calc_rows,
            })

    return all_venue_data, total_done, total_all, total_unpaid_amt


# ==============================================================================
# 5. 메인 show 함수
# ==============================================================================
def show(data):
    _apply_styles()
    st.title("🏢 대표님 전용")
    st.caption("세금계산서 발행 & 인력비 지급 — 확인 즉시 처리")

    try:
        settlement_df, dispatch_df, payment_df, staff_df = _load_all_ceo_data()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return

    # ── 세금계산서 ──
    tax_issued, tax_not_issued, not_issued_df, col_tax, col_company, col_inq_id = (
        _get_tax_invoice_stats(settlement_df) if not settlement_df.empty
        else (0, 0, pd.DataFrame(), None, None, None)
    )

    # ── 인력비 (정산 페이지 동일 로직) ──
    venue_data_list, staff_done, staff_total, total_unpaid_amt = (
        _build_inquiry_payment_data(dispatch_df, payment_df, staff_df)
    )
    unpaid_count = sum(
        1 for vd in venue_data_list
        for cr in vd['calc_rows']
        if cr['지급상태'] not in ('완료', '확인완료') and not cr['본사']
    )

    # ── 미수금 ──
    settlement_overview = ud.get_settlement_overview(settlement_df) if not settlement_df.empty else {
        "미수금액": 0, "받은금액": 0, "총청구액": 0, "수금률": 0
    }

    pay_rate = int(staff_done / staff_total * 100) if staff_total > 0 else 0
    action_needed = tax_not_issued + unpaid_count

    # ====================================================================
    # KPI 카드 5개
    # ====================================================================
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        _bg = "#FEF2F2" if tax_not_issued > 0 else "#F0FDF4"
        _clr = "#DC2626" if tax_not_issued > 0 else "#059669"
        st.markdown(
            f'<div class="ceo-kpi" style="background:{_bg};border:1px solid {_clr}33;">'
            f'<div class="kpi-label" style="color:{_clr};">📄 미발행 세금계산서</div>'
            f'<div class="kpi-value" style="color:{_clr};">{tax_not_issued}건</div>'
            f'<div class="kpi-sub">발행완료 {tax_issued}건</div></div>',
            unsafe_allow_html=True,
        )
    with k2:
        _amt = settlement_overview['미수금액']
        _bg2 = "#FFF7ED" if _amt > 0 else "#F0FDF4"
        _clr2 = "#EA580C" if _amt > 0 else "#059669"
        st.markdown(
            f'<div class="ceo-kpi" style="background:{_bg2};border:1px solid {_clr2}33;">'
            f'<div class="kpi-label" style="color:{_clr2};">💳 미수금액</div>'
            f'<div class="kpi-value" style="color:{_clr2};">{_amt:,}원</div>'
            f'<div class="kpi-sub">수금률 {settlement_overview["수금률"]}%</div></div>',
            unsafe_allow_html=True,
        )
    with k3:
        _bg3 = "#FEF2F2" if total_unpaid_amt > 0 else "#F0FDF4"
        _clr3 = "#DC2626" if total_unpaid_amt > 0 else "#059669"
        st.markdown(
            f'<div class="ceo-kpi" style="background:{_bg3};border:1px solid {_clr3}33;">'
            f'<div class="kpi-label" style="color:{_clr3};">💸 미지급 인건비</div>'
            f'<div class="kpi-value" style="color:{_clr3};">{total_unpaid_amt:,}원</div>'
            f'<div class="kpi-sub">외부인력 {unpaid_count}명</div></div>',
            unsafe_allow_html=True,
        )
    with k4:
        _rc = "#059669" if pay_rate >= 80 else "#D97706" if pay_rate >= 50 else "#DC2626"
        st.markdown(
            f'<div class="ceo-kpi" style="background:#EFF6FF;border:1px solid #BFDBFE;">'
            f'<div class="kpi-label" style="color:#2563EB;">📊 지급률</div>'
            f'<div class="kpi-value" style="color:{_rc};">{pay_rate}%</div>'
            f'<div class="kpi-sub">{staff_done}/{staff_total}명 처리</div></div>',
            unsafe_allow_html=True,
        )
    with k5:
        _bg5 = "#FDF4FF" if action_needed > 0 else "#F0FDF4"
        _clr5 = "#9333EA" if action_needed > 0 else "#059669"
        st.markdown(
            f'<div class="ceo-kpi" style="background:{_bg5};border:1px solid {_clr5}33;">'
            f'<div class="kpi-label" style="color:{_clr5};">🔔 처리 필요</div>'
            f'<div class="kpi-value" style="color:{_clr5};">{action_needed}건</div>'
            f'<div class="kpi-sub">세금계산서 {tax_not_issued} + 급여 {unpaid_count}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    tab_tax, tab_pay, tab_deposit, tab_profit = st.tabs(
        ["📄 세금계산서 발행 관리", "💸 인력비 지급 관리", "💰 업체 입금관리", "📊 프로젝트 수익 보고"]
    )

    with tab_tax:
        _render_tax_invoice_tab(settlement_df, not_issued_df, col_tax, col_company, col_inq_id,
                                tax_issued, tax_not_issued, dispatch_df)

    with tab_pay:
        df_inq = data.get('inq', pd.DataFrame())
        _render_payment_tab(venue_data_list, staff_done, staff_total, total_unpaid_amt, dispatch_df, df_inq)

    with tab_deposit:
        _render_deposit_tab(settlement_df, settlement_overview)

    with tab_profit:
        _render_profit_tab(settlement_df, payment_df)


# ==============================================================================
# 6. 세금계산서 탭 상세
# ==============================================================================
def _render_tax_invoice_tab(settlement_df, not_issued_df, col_tax, col_company, col_inq_id,
                            tax_issued, tax_not_issued, dispatch_df=None):
    st.markdown('<div class="ceo-section">📄 세금계산서 발행 현황</div>', unsafe_allow_html=True)

    if settlement_df.empty:
        st.warning("⚠️ 정산 데이터가 없습니다.")
        return
    if not col_tax or not col_company:
        st.warning("⚠️ 세금계산서 발행여부 또는 업체 컬럼을 찾을 수 없습니다.")
        return

    # ── 배정기록에서 문의ID별 투입인력 요약 맵 구성 ──
    _staff_summary_map = {}  # 문의ID → "행사스탭 5명 3일, 안내원 2명 2일"
    if dispatch_df is not None and not dispatch_df.empty:
        _d_inq = _find_col(dispatch_df, ['문의ID'])
        _d_job = _find_col(dispatch_df, ['직무', '역할'])
        _d_days = _find_col(dispatch_df, ['근무일수', '일수'])
        _d_status = _find_col(dispatch_df, ['지급상태', '상태'])
        if _d_inq and _d_job:
            _d_active = dispatch_df.copy()
            if _d_status:
                _d_active = _d_active[~_d_active[_d_status].astype(str).str.strip().isin(['취소', '후보'])]
            for _inq_id, _grp in _d_active.groupby(_d_active[_d_inq].astype(str).str.strip()):
                if not _inq_id or _inq_id in ('nan', 'None', ''):
                    continue
                _job_summary = []
                for _job, _jgrp in _grp.groupby(_grp[_d_job].astype(str).str.strip()):
                    if not _job or _job in ('nan', 'None', ''):
                        _job = '기타'
                    _cnt = len(_jgrp)
                    _days_val = ''
                    if _d_days:
                        _days_vals = _jgrp[_d_days].dropna().astype(str).str.strip()
                        _days_vals = _days_vals[_days_vals != ''].unique()
                        if len(_days_vals) > 0:
                            try:
                                _d = int(float(_days_vals[0]))
                                if _d > 0:
                                    _days_val = f' {_d}일'
                            except:
                                pass
                    _job_summary.append(f"{_job} {_cnt}명{_days_val}")
                _staff_summary_map[_inq_id] = ', '.join(_job_summary)

    # ── 발행완료 이력 (상단 배치) ──
    issued_df = settlement_df[
        settlement_df[col_tax].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)
    ] if col_tax else pd.DataFrame()
    if not issued_df.empty:
        with st.expander(f"✅ 발행완료 이력 ({len(issued_df)}건)", expanded=False):
            _styled_rows = []
            for _, _ir in issued_df.iterrows():
                _c = str(_ir.get(col_company, '')).strip() if col_company else ''
                _s = str(_ir.get('현장명', '')).strip()
                _d = str(_ir.get('파견일자', '')).strip()
                _d = _d if _d not in ('nan', 'None', '') else ''
                _sup = pd.to_numeric(_ir.get('공급가액', 0), errors='coerce')
                _sup = 0 if pd.isna(_sup) else int(_sup)
                _vat = pd.to_numeric(_ir.get('부가세', 0), errors='coerce')
                _vat = 0 if pd.isna(_vat) else int(_vat)
                _total = _sup + _vat
                _biz = str(_ir.get('사업자번호', '')).strip()
                _biz = _biz if _biz not in ('nan', 'None', '') else '-'
                _styled_rows.append(
                    f'<tr>'
                    f'<td style="font-weight:700;">{_c}</td>'
                    f'<td>{_s}</td>'
                    f'<td>{_d}</td>'
                    f'<td style="text-align:right;font-weight:600;">₩{_total:,}</td>'
                    f'<td>{_biz}</td>'
                    f'<td><span style="background:#D1FAE5;color:#065F46;padding:2px 8px;'
                    f'border-radius:10px;font-size:12px;font-weight:600;">✅ 발행완료</span></td>'
                    f'</tr>'
                )
            st.markdown(
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                f'<thead><tr style="background:#F9FAFB;border-bottom:2px solid #E5E7EB;">'
                f'<th style="padding:10px 8px;text-align:left;">업체명</th>'
                f'<th style="padding:10px 8px;text-align:left;">현장명</th>'
                f'<th style="padding:10px 8px;text-align:left;">파견일자</th>'
                f'<th style="padding:10px 8px;text-align:right;">청구금액</th>'
                f'<th style="padding:10px 8px;text-align:left;">사업자번호</th>'
                f'<th style="padding:10px 8px;text-align:left;">상태</th>'
                f'</tr></thead><tbody>'
                + ''.join(
                    f'<tr style="border-bottom:1px solid #F3F4F6;{"background:#F9FAFB;" if i % 2 == 1 else ""}">'
                    + r[4:]  # strip the existing <tr>
                    for i, r in enumerate(_styled_rows)
                )
                + f'</tbody></table></div>',
                unsafe_allow_html=True,
            )
            import io as _io_tax
            _tax_buf = _io_tax.BytesIO()
            export_cols = [c for c in [col_inq_id, col_company, '현장명', '파견일자', '청구금액',
                                        '공급가액', '부가세', '사업자번호', '대표자', '이메일',
                                        '법인명', '사업장주소', col_tax]
                           if c and c in issued_df.columns]
            issued_df[export_cols].to_excel(_tax_buf, index=False, sheet_name='발행완료')
            _tax_buf.seek(0)
            st.download_button(
                f"📥 발행완료 엑셀 다운로드 ({len(issued_df)}건)",
                data=_tax_buf.getvalue(),
                file_name=f"세금계산서_발행완료_{now_kst().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="ceo_tax_history_dl",
            )

    st.link_button(
        "🏛️ 홈택스 세금계산서 발행 바로가기",
        "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index_pp.xml&menuCd=index3",
        use_container_width=True, type="primary",
    )
    st.caption("💡 홈택스에서 전자세금계산서를 발행한 뒤 아래에서 '발행완료' 버튼을 눌러주세요.")
    st.markdown("")

    with st.expander(f"📋 전체 업체 현황 ({tax_issued + tax_not_issued}건)", expanded=False):
        display_cols = [c for c in [col_inq_id, col_company, '현장명', '청구금액', '공급가액', '부가세',
                                     col_tax, '사업자번호', '이메일']
                        if c and c in settlement_df.columns]
        if display_cols:
            st.dataframe(settlement_df[display_cols], use_container_width=True, hide_index=True)

    if not_issued_df.empty:
        st.success("🎉 모든 업체의 세금계산서가 발행되었습니다!")
        return

    st.markdown(f"### 🚨 미발행 업체 ({tax_not_issued}건) — 즉시 처리 필요")

    if tax_not_issued > 1:
        if st.button(f"✅ 전체 {tax_not_issued}건 일괄 발행완료 처리", type="primary",
                     key="ceo_tax_bulk", use_container_width=True):
            try:
                _client = db.get_connection()
                if _client:
                    _sh = _client.open_by_key(db.SHEET_ID)
                    _wks = _sh.worksheet("계약건은청구금액적기")
                    _headers = [str(h).replace('\n', ' ').strip() for h in _wks.row_values(1)]
                    if col_tax in _headers:
                        tax_col_idx = _headers.index(col_tax) + 1
                        all_records = _wks.get_all_values()
                        from gspread.cell import Cell
                        cells = []
                        inq_ids = set(not_issued_df['문의ID'].astype(str).str.strip()) if '문의ID' in not_issued_df.columns else set()
                        for r_idx in range(1, len(all_records)):
                            if str(all_records[r_idx][0]).strip() in inq_ids:
                                cells.append(Cell(row=r_idx + 1, col=tax_col_idx, value="발행완료"))
                        if cells:
                            _wks.update_cells(cells, value_input_option='RAW')
                    db.invalidate_data()
                    st.success(f"✅ {tax_not_issued}건 일괄 발행완료!")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"일괄 처리 실패: {e}")
        st.markdown("")

    for idx, row in not_issued_df.iterrows():
        company = str(row.get(col_company, '미등록')).strip()
        site_name = str(row.get('현장명', '')).strip()
        biz_num = str(row.get('사업자번호', '')).strip()
        email_val = str(row.get('이메일', '')).strip()
        ceo_name = str(row.get('대표자', '')).strip()
        corp_name = str(row.get('법인명', '')).strip()
        phone_val = str(row.get('연락처', '')).strip()
        paid_val = str(row.get('받은금액', '')).strip()
        # 행사정보 (파견일자, 현장주소)
        event_date_val = str(row.get('파견일자', '')).strip()
        if not event_date_val or event_date_val in ('nan', 'None', ''):
            event_date_val = ''
        venue_addr_val = str(row.get('현장주소', '')).strip()
        if not venue_addr_val or venue_addr_val in ('nan', 'None', ''):
            venue_addr_val = ''
        # 사업장주소
        address_val = str(row.get('사업장주소', '')).strip()
        if not address_val or address_val in ('nan', 'None', ''):
            address_val = ''

        def _fmt(v):
            try:
                n = int(float(str(v).replace(',', '').strip()))
                return f"₩{n:,}" if n > 0 else ''
            except Exception:
                return str(v).strip() if str(v).strip() not in ('', 'nan', 'None', '0') else ''

        amount_str = _fmt(row.get('청구금액', ''))
        supply_str = _fmt(row.get('공급가액', ''))
        tax_str = _fmt(row.get('부가세', ''))

        if not supply_str and amount_str:
            try:
                total_amt = int(float(str(row.get('청구금액', 0)).replace(',', '').strip()))
                calc_supply = int(total_amt / 1.1)
                supply_str = f"₩{calc_supply:,} (추정)"
                tax_str = f"₩{total_amt - calc_supply:,} (추정)"
            except Exception:
                pass

        # 받은금액 포맷
        paid_str = _fmt(paid_val)

        # 잔액 계산
        try:
            _inv_num = int(float(str(row.get('청구금액', 0)).replace(',', '').strip()) or 0)
            _paid_num = int(float(str(paid_val).replace(',', '').strip()) or 0) if paid_val and paid_val not in ('nan', 'None', '') else 0
            _balance_num = max(0, _inv_num - _paid_num)
            balance_str = f"₩{_balance_num:,}" if _balance_num > 0 else ''
        except Exception:
            _balance_num = 0
            balance_str = ''

        # 투입인력 요약
        _inq_id_val = str(row.get('문의ID', '')).strip() if '문의ID' in row.index else ''
        staff_summary = _staff_summary_map.get(_inq_id_val, '')

        col_left, col_right = st.columns([4, 1])
        with col_left:
            biz_lines = []
            if biz_num and biz_num not in ('nan', 'None', ''):
                biz_lines.append(f"🏢 사업자번호: <b>{biz_num}</b>")
            if corp_name and corp_name not in ('nan', 'None', ''):
                biz_lines.append(f"🏗️ 법인명: <b>{corp_name}</b>")
            if ceo_name and ceo_name not in ('nan', 'None', ''):
                biz_lines.append(f"👤 대표자: {ceo_name}")
            if email_val and email_val not in ('nan', 'None', ''):
                biz_lines.append(f"📧 이메일: <b>{email_val}</b>")
            if phone_val and phone_val not in ('nan', 'None', ''):
                biz_lines.append(f"📞 연락처: <b>{phone_val}</b>")
            if address_val and address_val not in ('nan', 'None', ''):
                biz_lines.append(f"🏠 사업장주소: <b>{address_val}</b>")
            else:
                biz_lines.append("🏠 사업장주소: <span style='color:#DC2626;'>미입력</span>")

            item_val = str(row.get('내용(품목)', '')).strip()
            item_line = ''
            if item_val and item_val not in ('nan', 'None', ''):
                item_line = f'📋 내용(품목): <b>{item_val}</b><br/>'

            money_parts = []
            if supply_str:
                money_parts.append(f"💰 공급가액: <b>{supply_str}</b>")
            if tax_str:
                money_parts.append(f"💰 부가세: <b>{tax_str}</b>")
            if amount_str:
                money_parts.append(f"💰 청구금액(합계): <b>{amount_str}</b>")
            if paid_str:
                money_parts.append(f"✅ 받은금액: <b>{paid_str}</b>")
            if balance_str:
                money_parts.append(f"🔴 잔액: <b style='color:#DC2626;'>{balance_str}</b>")

            missing = []
            if not biz_num or biz_num in ('nan', 'None', ''):
                missing.append("사업자번호")
            if not email_val or email_val in ('nan', 'None', ''):
                missing.append("이메일")
            missing_html = ''
            if missing:
                missing_html = (
                    f'<div style="background:#FEF3C7;border-radius:6px;padding:6px 10px;'
                    f'margin-top:8px;font-size:13px;color:#92400E;">'
                    f'⚠️ 미입력: {", ".join(missing)}</div>'
                )

            biz_block = "<br/>".join(biz_lines) if biz_lines else ""
            money_block = "<br/>".join(money_parts) if money_parts else ""

            # 행사정보 블록
            event_lines = []
            if event_date_val:
                event_lines.append(f"📅 파견일자: <b>{event_date_val}</b>")
            if venue_addr_val:
                event_lines.append(f"📍 현장주소: <b>{venue_addr_val}</b>")
            if staff_summary:
                event_lines.append(f"👥 투입인력: <b>{staff_summary}</b>")
            event_block = "<br/>".join(event_lines) if event_lines else ""

            title = f"<b style='font-size:18px;'>{company}</b>"
            if site_name:
                title += f" <span style='color:#6b7280;font-size:14px;'>({site_name})</span>"

            st.markdown(
                f'<div class="ceo-card">'
                f'<div class="card-title">{title}</div>'
                f'<div class="card-detail">'
                f'{item_line}'
                f'{event_block}{"<br/>" if event_block else ""}'
                f'{biz_block}{"<br/>" if biz_block else ""}'
                f'<span style="color:#C2410C;font-weight:600;">{money_block}</span>'
                f'</div>{missing_html}</div>',
                unsafe_allow_html=True,
            )

        with col_right:
            st.markdown("<div style='padding-top:12px;'></div>", unsafe_allow_html=True)
            if st.button("✅ 발행완료", key=f"ceo_tax_{idx}", use_container_width=True, type="primary"):
                try:
                    _client = db.get_connection()
                    if _client:
                        _sh = _client.open_by_key(db.SHEET_ID)
                        _wks = _sh.worksheet("계약건은청구금액적기")
                        _headers = [str(h).replace('\n', ' ').strip() for h in _wks.row_values(1)]
                        if col_tax in _headers:
                            tax_col_idx = _headers.index(col_tax) + 1
                            all_records = _wks.get_all_values()
                            _inq_id = str(row.get('문의ID', '')).strip()
                            for r_idx in range(1, len(all_records)):
                                if str(all_records[r_idx][0]).strip() == _inq_id:
                                    _wks.update_cell(r_idx + 1, tax_col_idx, "발행완료")
                                    break
                        db.invalidate_data()
                        st.success(f"✅ {company} 발행완료!")
                        time.sleep(1)
                        st.rerun()
                except Exception as e:
                    st.error(f"저장 실패: {e}")
            st.link_button(
                "🏛️ 홈택스",
                "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index_pp.xml&menuCd=index3",
                use_container_width=True,
            )


# ==============================================================================
# 7. 인력비 지급 탭 — 팀 결제 명세서 + 개별 급여명세서
# ==============================================================================
def _render_payment_tab(venue_data_list, staff_done, staff_total, total_unpaid_amt, dispatch_df, df_inq=None):
    st.markdown('<div class="ceo-section">💸 인력비 지급 현황</div>', unsafe_allow_html=True)

    # ── 지급완료 이력 (상단 배치) ──
    all_done_for_history = []
    for vd in venue_data_list:
        for cr in vd['calc_rows']:
            if cr['지급상태'] in ('완료', '확인완료') and not cr['본사']:
                all_done_for_history.append({
                    '현장명': vd['venue'],
                    '이름': cr['이름'],
                    '직무': cr['직무'],
                    '총액': cr['총액'],
                    '공제': cr['공제'],
                    '실수령': cr['실수령'],
                    '은행': cr.get('은행', ''),
                    '계좌': cr.get('계좌', ''),
                    '공제율': cr.get('공제율', ''),
                })
    if all_done_for_history:
        with st.expander(f"✅ 지급완료 이력 ({len(all_done_for_history)}명)", expanded=False):
            _pay_rows_html = []
            for i, _dr in enumerate(all_done_for_history):
                _bg = 'background:#F9FAFB;' if i % 2 == 1 else ''
                _pay_rows_html.append(
                    f'<tr style="border-bottom:1px solid #F3F4F6;{_bg}">'
                    f'<td style="padding:8px;font-weight:600;">{_dr["현장명"]}</td>'
                    f'<td style="padding:8px;">{_dr["이름"]}</td>'
                    f'<td style="padding:8px;">{_dr["직무"]}</td>'
                    f'<td style="padding:8px;text-align:right;">₩{_dr["총액"]:,}</td>'
                    f'<td style="padding:8px;text-align:right;color:#DC2626;">-₩{_dr["공제"]:,}</td>'
                    f'<td style="padding:8px;text-align:right;font-weight:700;color:#059669;">₩{_dr["실수령"]:,}</td>'
                    f'<td style="padding:8px;">{_dr["은행"]} {_dr["계좌"]}</td>'
                    f'<td style="padding:8px;"><span style="background:#D1FAE5;color:#065F46;padding:2px 8px;'
                    f'border-radius:10px;font-size:12px;font-weight:600;">✅ 완료</span></td>'
                    f'</tr>'
                )
            st.markdown(
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                f'<thead><tr style="background:#F9FAFB;border-bottom:2px solid #E5E7EB;">'
                f'<th style="padding:8px;text-align:left;">현장명</th>'
                f'<th style="padding:8px;text-align:left;">이름</th>'
                f'<th style="padding:8px;text-align:left;">직무</th>'
                f'<th style="padding:8px;text-align:right;">총액</th>'
                f'<th style="padding:8px;text-align:right;">공제</th>'
                f'<th style="padding:8px;text-align:right;">실수령</th>'
                f'<th style="padding:8px;text-align:left;">계좌</th>'
                f'<th style="padding:8px;text-align:left;">상태</th>'
                f'</tr></thead><tbody>'
                + ''.join(_pay_rows_html)
                + f'</tbody></table></div>',
                unsafe_allow_html=True,
            )
            import io as _io_pay
            _pay_buf = _io_pay.BytesIO()
            pd.DataFrame(all_done_for_history).to_excel(_pay_buf, index=False, sheet_name='지급완료')
            _pay_buf.seek(0)
            st.download_button(
                f"📥 지급완료 엑셀 다운로드 ({len(all_done_for_history)}명)",
                data=_pay_buf.getvalue(),
                file_name=f"인력비_지급완료_{now_kst().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="ceo_pay_history_dl",
            )

    if not venue_data_list:
        if dispatch_df.empty:
            st.info("📋 배정 기록이 없습니다.")
        else:
            st.success("🎉 모든 인력 급여가 지급 완료되었습니다!")
            _show_done_summary(staff_done, staff_total)
        return

    # ── 행사종료일 → 입금마감일 맵 구성 ──
    _end_date_map = {}  # inq_id → 행사종료일 datetime
    if df_inq is not None and not df_inq.empty:
        _col_inq_id = _find_col(df_inq, ['문의ID', 'ID'])
        _col_end = _find_col(df_inq, ['행사종료일', '종료일'])
        if not _col_end:
            _col_end = _find_col(df_inq, ['행사시작일', '시작일', '행사일시'])
        if _col_inq_id and _col_end:
            for _, _r in df_inq.iterrows():
                _iid = str(_r.get(_col_inq_id, '')).strip()
                _dval = str(_r.get(_col_end, '')).strip()
                if _iid and _dval:
                    try:
                        # '~' 구분 날짜는 뒷부분(종료일) 사용
                        if '~' in _dval:
                            _dval = _dval.split('~')[-1].strip()
                        _end_dt = datetime.strptime(_dval[:10], '%Y-%m-%d')
                        _end_date_map[_iid] = _end_dt
                    except:
                        pass

    _today = today_kst()
    _DEADLINE_DAYS = 13  # 행사종료 후 13일 이내 입금

    # 각 venue에 마감일 정보 부여
    for vd in venue_data_list:
        _end_dt = _end_date_map.get(vd['inq_id'])
        if _end_dt:
            _deadline = _end_dt + timedelta(days=_DEADLINE_DAYS)
            _dday = (_deadline - _today).days
            vd['_end_date'] = _end_dt
            vd['_deadline'] = _deadline
            vd['_dday'] = _dday
        else:
            vd['_end_date'] = None
            vd['_deadline'] = None
            vd['_dday'] = 9999  # 날짜 없으면 맨 뒤로

    # ★ 입금마감일 가까운 순으로 정렬
    venue_data_list = sorted(venue_data_list, key=lambda v: v['_dday'])

    # 전체 미지급 건 수
    all_unpaid = []
    all_pending = []
    for vd in venue_data_list:
        for cr in vd['calc_rows']:
            if cr['지급상태'] not in ('완료', '확인완료') and not cr['본사']:
                all_unpaid.append(cr)
            if cr['지급상태'] == '대기' and not cr['본사']:
                all_pending.append(cr)

    if not all_unpaid and not all_pending:
        st.success("🎉 모든 외부인력 급여가 지급 완료되었습니다!")
        _show_done_summary(staff_done, staff_total)
        return

    st.markdown(f"**미지급 합계: ₩{total_unpaid_amt:,}** ({len(all_unpaid)}명)")
    st.caption("💡 행사종료 후 13일 이내 입금 기준 | 마감 임박순 정렬")
    st.markdown("")

    # ── 현장별 렌더링 ──
    for vd in venue_data_list:
        venue = vd['venue']
        team_info = vd['team_info']
        calc_rows = vd['calc_rows']
        inq_id = vd['inq_id']

        # 이 현장의 미지급 건만
        venue_unpaid = [cr for cr in calc_rows
                        if cr['지급상태'] not in ('완료', '확인완료') and not cr['본사']]
        if not venue_unpaid:
            continue

        venue_total = sum(cr['실수령'] for cr in venue_unpaid)

        # ── 마감일 D-Day 라벨 ──
        _vd_dday = vd.get('_dday', 9999)
        _vd_deadline = vd.get('_deadline')
        if _vd_deadline and _vd_dday != 9999:
            _dl_str = _vd_deadline.strftime('%m/%d')
            if _vd_dday < 0:
                _dday_badge = f'🔴 마감 {abs(_vd_dday)}일 초과!'
                _dday_color = '#DC2626'
            elif _vd_dday == 0:
                _dday_badge = '🔴 오늘 마감!'
                _dday_color = '#DC2626'
            elif _vd_dday <= 3:
                _dday_badge = f'🟠 D-{_vd_dday} ({_dl_str}까지)'
                _dday_color = '#EA580C'
            elif _vd_dday <= 7:
                _dday_badge = f'🟡 D-{_vd_dday} ({_dl_str}까지)'
                _dday_color = '#D97706'
            elif _vd_dday <= 14:
                _dday_badge = f'🟢 D-{_vd_dday} ({_dl_str}까지)'
                _dday_color = '#059669'
            else:
                _dday_badge = f'D-{_vd_dday} ({_dl_str}까지)'
                _dday_color = '#6B7280'
        else:
            _dday_badge = ''
            _dday_color = '#6B7280'

        # 현장 제목 + 이체 엑셀 다운로드 (미지급만)
        _venue_title_col, _venue_dl_col = st.columns([3, 1])
        with _venue_title_col:
            if _dday_badge:
                st.markdown(
                    f"#### 📍 {venue} ({len(venue_unpaid)}명 · ₩{venue_total:,})"
                    f"  \n"
                    f"<span style='font-size:16px;font-weight:700;color:{_dday_color};'>"
                    f"📅 {_dday_badge}</span>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"#### 📍 {venue} ({len(venue_unpaid)}명 · ₩{venue_total:,})")
        with _venue_dl_col:
            import io as _io
            _venue_transfer = []
            for _vcr in venue_unpaid:
                if _vcr['실수령'] <= 0:
                    continue
                _venue_transfer.append({
                    '이름': _vcr['이름'],
                    '은행': _vcr.get('은행', ''),
                    '계좌번호': _vcr.get('계좌', ''),
                    '이체금액': _vcr['실수령'],
                    '메모': _vcr.get('메모', '') or f"{venue} 급여",
                })
            if _venue_transfer:
                _vbuf = _io.BytesIO()
                pd.DataFrame(_venue_transfer).to_excel(_vbuf, index=False, sheet_name='이체목록')
                _vbuf.seek(0)
                st.download_button(
                    f"📥 이체 엑셀 ({len(_venue_transfer)}명)",
                    data=_vbuf.getvalue(),
                    file_name=f"이체_{venue}_{now_kst().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key=f"ceo_dl_venue_{inq_id}",
                )

        # 현장 일괄 입금완료
        venue_pending = [cr for cr in venue_unpaid if cr['지급상태'] == '대기']
        if len(venue_pending) > 1:
            if st.button(f"💰 {venue} 전체 {len(venue_pending)}명 일괄 입금완료",
                         key=f"ceo_bulk_{inq_id}", type="primary"):
                _now = now_kst().strftime('%Y-%m-%d')
                updates = []
                for cr in venue_pending:
                    if cr['배정ID']:
                        updates.append({'배정ID': cr['배정ID'], '지급상태': '완료', '지급일': _now})
                # 팀원도 함께 완료 처리
                for tc, ti in team_info.items():
                    leader_cr = next((cr for cr in venue_pending if cr['팀코드'] == tc), None)
                    if leader_cr:
                        for md in ti.get('member_details', []):
                            if not md['is_pay']:
                                # 팀원의 배정ID 찾기
                                m_aid = _find_member_aid(dispatch_df, inq_id, md['name'])
                                if m_aid:
                                    updates.append({'배정ID': m_aid, '지급상태': '완료', '지급일': _now})
                if updates:
                    result = db.batch_update_payment_status(updates)
                    db.invalidate_payment_cache()
                    db.invalidate_dispatch_only()
                    st.success(f"✅ {result.get('success', 0)}명 입금완료!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("⚠️ 일괄 처리 가능한 건이 없습니다.")

        # ── 팀 결제 명세서 ──
        for tc, ti in team_info.items():
            leader = ti['leader'] or '?'
            leader_cr = next((cr for cr in calc_rows if cr['이름'] == leader and cr['팀코드'] == tc), None)
            if not leader_cr:
                continue
            if leader_cr['지급상태'] in ('완료', '확인완료'):
                continue  # 이미 완료된 팀은 숨김

            members = ti['members']
            per_r = ti['per_rate']
            per_d = ti['per_days']
            onsite_n = ti['onsite_count']
            total_n = len(members)
            sum_amt = ti['sum_amount']

            # 팀장 참여 여부
            leader_detail = next((md for md in ti['member_details'] if md['name'] == leader), None)
            leader_onsite = leader_detail['is_onsite'] if leader_detail else True

            onsite_tag = "" if leader_onsite else " 🚫불참"
            status_badge = "⏳" if leader_cr['지급상태'] == '대기' else "📝"
            status_txt = " [대기]" if leader_cr['지급상태'] == '대기' else " [인사컨펌필요]"
            leader_tax_label = leader_cr.get('공제율', '3.3%')
            bank_info = (f"💳 {leader_cr['은행']} {leader_cr['계좌']}"
                         if leader_cr['은행'] and leader_cr['은행'] not in ('nan', 'None', '')
                         else "❗ 계좌 미등록")

            # 팀원 이름 목록 (expander 제목용)
            member_names = [md['name'] for md in ti['member_details'] if md['name'] != leader]
            member_list_txt = f" ({', '.join(member_names)})"

            # ── 팀 카드: 외부 버튼 + expander ──
            _team_exp_col, _team_btn_col = st.columns([8, 2])
            with _team_exp_col:
              with st.expander(
                f"{status_badge} 👥 {leader}팀{status_txt} ({total_n}명, 현장{onsite_n}명{onsite_tag}) "
                f"— 총 ₩{leader_cr['총액']:,} → 실수령 ₩{leader_cr['실수령']:,} [{leader_tax_label}공제 -₩{leader_cr['공제']:,}] {bank_info}"
              ):
                if leader_cr.get('메모'):
                    st.info(f"📝 메모: {leader_cr['메모']}")
                # 팀원 결제분 포함 안내
                st.info(
                    f"ℹ️ **{leader}**에게 팀원 {len(member_names)}명분{member_list_txt} 합산 지급"
                )
                # 팀 구성원 상세
                st.markdown("**👥 팀 구성원**")
                member_html = ''
                for md in ti['member_details']:
                    m_name = md['name']
                    is_leader = m_name == leader
                    m_onsite = md['is_onsite']

                    if is_leader and not m_onsite:
                        m_icon = "🚫"
                        m_label = f"<b>{m_name}</b> (팀장·불참) — 결제 수령인"
                        m_amt = "본인분 제외"
                        m_color = "#DC2626"
                    elif is_leader:
                        m_icon = "👑"
                        m_label = f"<b>{m_name}</b> (팀장·현장참여) — 결제 수령인"
                        m_amt = f"₩{md['rate']:,} × {md['days']}일 = ₩{md['rate'] * md['days']:,}"
                        m_color = "#7C3AED"
                    else:
                        m_icon = "👤"
                        m_label = f"{m_name} (팀원)"
                        m_amt = f"₩{md['rate']:,} × {md['days']}일 = ₩{md['rate'] * md['days']:,}"
                        m_color = "#374151"

                    member_html += (
                        f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                        f'border-bottom:1px solid #f3f4f6;">'
                        f'<span style="color:{m_color};font-size:14px;">{m_icon} {m_label}</span>'
                        f'<span style="font-weight:600;color:{m_color};font-size:14px;">{m_amt}</span>'
                        f'</div>'
                    )
                st.markdown(
                    f'<div style="background:#F9FAFB;border-radius:8px;padding:12px 16px;">'
                    f'{member_html}</div>',
                    unsafe_allow_html=True,
                )

                # 산출 내역
                st.markdown("")
                if not leader_onsite:
                    st.warning(
                        f"🚫 **팀장 현장 불참** — 팀장 본인 몫(₩{per_r:,}×{per_d}일=₩{per_r * per_d:,}) 제외\n\n"
                        f"팀원 {onsite_n}명분만 지급: ₩{per_r:,} × {per_d}일 × {onsite_n}명 = **₩{sum_amt:,}**"
                    )
                else:
                    st.info(f"인당 ₩{per_r:,} × {per_d}일 × {total_n}명 = **₩{sum_amt:,}**")

                # 상세 금액 테이블
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(
                        f"| 항목 | 금액 |\n|------|------|\n"
                        f"| 팀 합산 기본급 | ₩{sum_amt:,} |\n"
                        f"| 식비 | ₩{leader_cr['식비']:,} |\n"
                        f"| 교통비 | ₩{leader_cr['교통비']:,} |\n"
                        f"| 연장 | ₩{leader_cr['연장']:,} |\n"
                        f"| {leader_cr.get('기타항목명', '기타(숙박등)')} | ₩{leader_cr['기타']:,} |\n"
                        f"| **총액** | **₩{leader_cr['총액']:,}** |\n"
                        f"| 공제({leader_tax_label}) | -₩{leader_cr['공제']:,} |\n"
                        f"| **실수령 → {leader} 계좌** | **₩{leader_cr['실수령']:,}** |"
                    )
                with c2:
                    if leader_cr['은행'] and leader_cr['은행'] not in ('nan', 'None', ''):
                        st.info(f"🏦 {leader_cr['은행']}\n\n📋 {leader_cr['계좌']}\n\n👤 수령인: **{leader}**")
                    else:
                        st.warning(f"❗ {leader} 계좌 미등록")
            # ── 팀 외부 입금완료 버튼 ──
            with _team_btn_col:
                if leader_cr['지급상태'] == '대기':
                    if st.button("💰 입금완료", key=f"ceo_team_{tc}_{inq_id}", type="primary",
                                 use_container_width=True):
                        _now = now_kst().strftime('%Y-%m-%d')
                        team_updates = []
                        if leader_cr['배정ID']:
                            team_updates.append({'배정ID': leader_cr['배정ID'], '지급상태': '완료', '지급일': _now})
                        # 팀원도 완료 처리
                        for md in ti['member_details']:
                            if md['name'] == leader:
                                continue
                            m_aid = _find_member_aid(dispatch_df, inq_id, md['name'])
                            if m_aid:
                                team_updates.append({'배정ID': m_aid, '지급상태': '완료', '지급일': _now})
                        if team_updates:
                            db.batch_update_payment_status(team_updates)
                        db.invalidate_payment_cache()
                        db.invalidate_dispatch_only()
                        st.success(f"✅ {leader}팀 입금완료!")
                        time.sleep(1)
                        st.rerun()
                elif leader_cr['지급상태'] == '미저장':
                    st.markdown("<span style='font-size:15px; font-weight:700; color:#b45309;'>📝 인사담당자의 컨펌이 필요합니다</span>", unsafe_allow_html=True)

        # ── 개별 급여명세서 (팀장 이외) ──
        individual = [cr for cr in venue_unpaid if not cr['팀코드']]
        if individual:
            for cr in individual:
                name = cr['이름']
                net = cr['실수령']
                pst = cr['지급상태']
                aid = cr['배정ID']
                bank = cr['은행']
                acct = cr['계좌']
                ind_tax_label = cr.get('공제율', '3.3%')
                bank_display = (f"💳 {bank} {acct}"
                                if bank and bank not in ('nan', 'None', '')
                                else "❗ 계좌 미등록")
                status_badge = "⏳" if pst == '대기' else "📝"
                status_txt = " [대기]" if pst == '대기' else " [인사컨펌필요]"

                # ── 개별 카드: 외부 버튼 + expander ──
                _ind_exp_col, _ind_btn_col = st.columns([8, 2])
                with _ind_exp_col:
                  with st.expander(
                    f"{status_badge} 👤 {name}{status_txt} ({cr['직무']}) "
                    f"— 총 ₩{cr['총액']:,} → 실수령 ₩{net:,} [{ind_tax_label}공제 -₩{cr['공제']:,}] {bank_display}"
                  ):
                    if cr.get('메모'):
                        st.info(f"📝 메모: {cr['메모']}")
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(
                            f"| 항목 | 금액 |\n|------|------|\n"
                            f"| 기본급 ({cr['단가']:,} × {cr['일수']}일) | ₩{cr['기본급']:,} |\n"
                            f"| 식비 | ₩{cr['식비']:,} |\n"
                            f"| 교통비 | ₩{cr['교통비']:,} |\n"
                            f"| 연장 | ₩{cr['연장']:,} |\n"
                            f"| {cr.get('기타항목명', '기타(숙박등)')} | ₩{cr['기타']:,} |\n"
                            f"| **총액** | **₩{cr['총액']:,}** |\n"
                            f"| 공제({ind_tax_label}) | -₩{cr['공제']:,} |\n"
                            f"| **실수령** | **₩{net:,}** |"
                        )
                    with c2:
                        if bank and bank not in ('nan', 'None', ''):
                            st.info(f"🏦 {bank}\n\n📋 {acct}")
                        else:
                            st.warning("❗ 계좌 미등록")
                # ── 개별 외부 입금완료 버튼 ──
                with _ind_btn_col:
                    if pst == '대기' and aid:
                        if st.button("💰 입금완료", key=f"ceo_ind_{aid}_{inq_id}", type="primary",
                                     use_container_width=True):
                            _now = now_kst().strftime('%Y-%m-%d')
                            db.update_payment_status(aid, '완료', _now)
                            db.invalidate_payment_cache()
                            db.invalidate_dispatch_only()
                            st.success(f"✅ {name} 입금완료!")
                            time.sleep(1)
                            st.rerun()
                    elif pst == '미저장':
                        st.markdown("<span style='font-size:15px; font-weight:700; color:#b45309;'>📝 인사담당자의 컨펌이 필요합니다</span>", unsafe_allow_html=True)

        st.markdown("---")

    # 현장별 요약
    with st.expander("📊 현장별 미지급 요약", expanded=False):
        summary_rows = []
        for vd in venue_data_list:
            unpaid = [cr for cr in vd['calc_rows']
                      if cr['지급상태'] not in ('완료', '확인완료') and not cr['본사']]
            if unpaid:
                _dl = vd.get('_deadline')
                _dd = vd.get('_dday', 9999)
                if _dl and _dd != 9999:
                    if _dd < 0:
                        _dl_label = f"🔴 {abs(_dd)}일 초과"
                    elif _dd <= 3:
                        _dl_label = f"🟠 D-{_dd}"
                    elif _dd <= 7:
                        _dl_label = f"🟡 D-{_dd}"
                    else:
                        _dl_label = f"🟢 D-{_dd}"
                    _dl_date = _dl.strftime('%m/%d')
                else:
                    _dl_label = '-'
                    _dl_date = '-'
                summary_rows.append({
                    '현장명': vd['venue'],
                    '입금마감': _dl_date,
                    'D-Day': _dl_label,
                    '인원': len(unpaid),
                    '미지급합계': sum(cr['실수령'] for cr in unpaid),
                })
        if summary_rows:
            sdf = pd.DataFrame(summary_rows).reset_index(drop=True)
            st.dataframe(sdf, use_container_width=True, hide_index=True,
                         column_config={"미지급합계": st.column_config.NumberColumn("💰 미지급합계", format="%d원")})


def _find_member_aid(dispatch_df, inq_id, member_name):
    """배정기록에서 팀원의 배정ID 찾기"""
    col_name = _find_col(dispatch_df, ["인력명", "이름", "성명"])
    col_inq = _find_col(dispatch_df, ["문의ID"])
    col_aid = _find_col(dispatch_df, ["배정ID"])
    if not col_name or not col_inq or not col_aid:
        return ''
    matched = dispatch_df[
        (dispatch_df[col_inq].astype(str).str.strip() == str(inq_id).strip()) &
        (dispatch_df[col_name].astype(str).str.strip() == str(member_name).strip())
    ]
    if not matched.empty:
        return str(matched.iloc[0].get(col_aid, '')).strip()
    return ''


def _show_done_summary(staff_done, staff_total):
    st.markdown(
        '<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:12px;'
        'padding:20px;text-align:center;margin-top:10px;">'
        '<div style="font-size:40px;">✅</div>'
        f'<div style="font-size:18px;font-weight:700;color:#047857;margin:8px 0;">전원 처리 완료</div>'
        f'<div style="font-size:13px;color:#059669;">{staff_done}/{staff_total}명 지급/확인 완료</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ==============================================================================
# 8. 업체 입금관리 탭
# ==============================================================================
def _render_deposit_tab(settlement_df, overview):
    """업체정산 현황 및 입금관리 — CEO 전용 입금 추적"""
    from page_settlement import save_payment_record

    st.markdown('<div class="ceo-section">💰 업체 입금 현황</div>', unsafe_allow_html=True)

    if settlement_df.empty:
        st.warning("정산 데이터가 없습니다.")
        return

    # ── 통계 메트릭 (4열) ──
    total_invoice = overview.get('총청구액', 0)
    total_paid = overview.get('받은금액', 0)
    total_balance = overview.get('미수금액', 0)
    collect_rate = overview.get('수금률', 0)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("📌 총 청구액", f"₩{total_invoice:,}")
    with m2:
        st.metric("💵 받은 금액", f"₩{total_paid:,}")
    with m3:
        _bal_color = "inverse" if total_balance > 0 else "off"
        st.metric("🚨 미수금", f"₩{total_balance:,}", delta=f"-₩{total_balance:,}" if total_balance > 0 else "완납", delta_color=_bal_color)
    with m4:
        st.metric("📈 수금률", f"{collect_rate}%")

    st.markdown("---")

    # ── 행별 데이터 준비 ──
    df = settlement_df.copy()
    col_inq = _find_col(df, ['문의ID'])
    col_company = _find_col(df, ['업체', '업체명'])
    col_site = _find_col(df, ['현장명', '행사명'])
    col_date = _find_col(df, ['파견일자', '행사일자', '행사시작일'])
    col_addr = _find_col(df, ['현장주소', '장소', '행사장소'])
    col_supply = _find_col(df, ['공급가액'])
    col_tax = _find_col(df, ['부가세'])
    col_paid_c = _find_col(df, ['받은금액'])
    col_progress = _find_col(df, ['진행상황'])

    if not col_inq or not col_company:
        st.warning("필수 컬럼(문의ID, 업체)이 없습니다.")
        return

    # 수치 변환
    df['_supply'] = pd.to_numeric(df[col_supply], errors='coerce').fillna(0).astype(int) if col_supply else 0
    df['_tax'] = pd.to_numeric(df[col_tax], errors='coerce').fillna(0).astype(int) if col_tax else 0
    df['_invoice'] = df['_supply'] + df['_tax']
    df['_paid'] = pd.to_numeric(df[col_paid_c], errors='coerce').fillna(0).astype(int) if col_paid_c else 0
    df['_balance'] = (df['_invoice'] - df['_paid']).clip(lower=0)
    df['_progress'] = df[col_progress].astype(str).str.strip() if col_progress else ''

    # 세금계산서 발행여부 컨럼 찾기
    col_tax_issued = None
    for col in df.columns:
        if '발행여부' in col or '세금계산서' in col:
            col_tax_issued = col
            break

    # ── 입금완료 이력 (상단 배치) ──
    df_completed = df[(df['_balance'] <= 0) & (df['_paid'] > 0)]
    if not df_completed.empty:
        with st.expander(f"✅ 입금완료 이력 ({len(df_completed)}건)", expanded=False):
            _dep_rows_html = []
            for i, (_, _dr) in enumerate(df_completed.iterrows()):
                _dc = str(_dr.get(col_company, '')).strip() if col_company else ''
                _ds = str(_dr.get(col_site, '')).strip() if col_site else ''
                _dd = str(_dr.get(col_date, '')).strip() if col_date else ''
                _dd = _dd if _dd not in ('nan', 'None', '') else ''
                _dinv = int(_dr['_invoice'])
                _dpaid = int(_dr['_paid'])
                _dprog = str(_dr.get('_progress', '')).strip()
                _bg = 'background:#F9FAFB;' if i % 2 == 1 else ''
                _dep_rows_html.append(
                    f'<tr style="border-bottom:1px solid #F3F4F6;{_bg}">'
                    f'<td style="padding:8px;font-weight:600;">{_dc}</td>'
                    f'<td style="padding:8px;">{_ds}</td>'
                    f'<td style="padding:8px;">{_dd}</td>'
                    f'<td style="padding:8px;text-align:right;">₩{_dinv:,}</td>'
                    f'<td style="padding:8px;text-align:right;font-weight:700;color:#059669;">₩{_dpaid:,}</td>'
                    f'<td style="padding:8px;">{_dprog}</td>'
                    f'<td style="padding:8px;"><span style="background:#D1FAE5;color:#065F46;padding:2px 8px;'
                    f'border-radius:10px;font-size:12px;font-weight:600;">✅ 완납</span></td>'
                    f'</tr>'
                )
            st.markdown(
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                f'<thead><tr style="background:#F9FAFB;border-bottom:2px solid #E5E7EB;">'
                f'<th style="padding:8px;text-align:left;">업체명</th>'
                f'<th style="padding:8px;text-align:left;">현장명</th>'
                f'<th style="padding:8px;text-align:left;">파견일자</th>'
                f'<th style="padding:8px;text-align:right;">청구금액</th>'
                f'<th style="padding:8px;text-align:right;">받은금액</th>'
                f'<th style="padding:8px;text-align:left;">진행상황</th>'
                f'<th style="padding:8px;text-align:left;">상태</th>'
                f'</tr></thead><tbody>'
                + ''.join(_dep_rows_html)
                + f'</tbody></table></div>',
                unsafe_allow_html=True,
            )
            import io as _io_dep
            _dep_buf = _io_dep.BytesIO()
            export_cols = [c for c in [col_inq, col_company, col_site, col_date,
                                        col_supply, col_tax, col_paid_c, col_progress]
                           if c and c in df_completed.columns]
            if export_cols:
                df_completed[export_cols].to_excel(_dep_buf, index=False, sheet_name='입금완료')
            else:
                df_completed.to_excel(_dep_buf, index=False, sheet_name='입금완료')
            _dep_buf.seek(0)
            st.download_button(
                f"📥 입금완료 엑셀 다운로드 ({len(df_completed)}건)",
                data=_dep_buf.getvalue(),
                file_name=f"업체입금_완료_{now_kst().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="ceo_deposit_history_dl",
            )

    # ── 필터 ──
    filter_col, _ = st.columns([4, 6])
    with filter_col:
        deposit_filter = st.radio(
            "필터", ["🚨 미수금", "🔶 부분입금", "✅ 입금완료", "📋 전체"],
            key="ceo_deposit_filter", horizontal=True, label_visibility="collapsed"
        )

    if deposit_filter == "🚨 미수금":
        df_view = df[df['_balance'] > 0].sort_values('_balance', ascending=False)
    elif deposit_filter == "🔶 부분입금":
        df_view = df[(df['_balance'] > 0) & (df['_paid'] > 0)].sort_values('_balance', ascending=False)
    elif deposit_filter == "✅ 입금완료":
        df_view = df[(df['_balance'] <= 0) & (df['_paid'] > 0)].sort_values('_paid', ascending=False)
    else:
        df_view = df.sort_values('_balance', ascending=False)

    if df_view.empty:
        st.info("해당 조건의 건이 없습니다.")
        return

    st.caption(f"총 {len(df_view)}건")

    # ── 카드 리스트 ──
    for _, row in df_view.iterrows():
        inq_id = str(row[col_inq]).strip()
        company = str(row[col_company]).strip()
        site = str(row[col_site]).strip() if col_site else ''
        event_date = str(row[col_date]).strip() if col_date and col_date in row.index else ''
        event_addr = str(row[col_addr]).strip() if col_addr and col_addr in row.index else ''
        invoice = int(row['_invoice'])
        paid = int(row['_paid'])
        balance = int(row['_balance'])
        progress = str(row.get('_progress', ''))

        # 상태 결정
        if balance <= 0 and paid > 0:
            card_cls = "done"
            badge = "✅ 입금완료"
            badge_bg = "#D1FAE5"
            badge_clr = "#065F46"
        elif paid > 0:
            card_cls = ""
            badge = "🔶 부분입금"
            badge_bg = "#FEF3C7"
            badge_clr = "#92400E"
        else:
            card_cls = ""
            badge = "🔴 미입금"
            badge_bg = "#FEE2E2"
            badge_clr = "#991B1B"

        # 프로그레스 바 (수금률)
        pct = int(paid / invoice * 100) if invoice > 0 else 0
        bar_color = "#10B981" if pct >= 100 else "#F59E0B" if pct > 0 else "#EF4444"

        # expander 제목 구성: 업체 — 행사명 | 날짜 | 장소 | 금액 | 세금계산서상태
        _title_parts = [f"{badge}  **{company}**"]
        if site:
            _title_parts.append(f"— {site}")
        _detail_parts = []
        if event_date and event_date not in ('nan', 'None', ''):
            _detail_parts.append(f"📅{event_date}")
        if event_addr and event_addr not in ('nan', 'None', ''):
            _detail_parts.append(f"📍{event_addr}")
        _detail_parts.append(f"청구 ₩{invoice:,}")
        _detail_parts.append(f"받음 ₩{paid:,}")
        _detail_parts.append(f"잔액 ₩{balance:,}")
        # 세금계산서 발행 상태 배지
        if col_tax_issued:
            _tax_val = str(row.get(col_tax_issued, '')).strip()
            if _tax_val and any(k in _tax_val for k in ('발행', '완료', 'O', 'Yes', 'yes')):
                _detail_parts.append("✅계산서 발행완료")
            else:
                _detail_parts.append("⚠️계산서 미발행")
        _expander_title = f"{' '.join(_title_parts)}  |  {'  |  '.join(_detail_parts)}"

        with st.expander(_expander_title):
            # 상단: 프로그레스 바
            st.markdown(
                f'<div style="background:#E5E7EB;border-radius:8px;height:10px;margin-bottom:12px;">'
                f'<div style="background:{bar_color};border-radius:8px;height:100%;width:{min(pct, 100)}%;"></div>'
                f'</div>'
                f'<div style="text-align:right;font-size:12px;color:#6B7280;margin-top:-8px;">'
                f'수금률 {pct}%</div>',
                unsafe_allow_html=True,
            )

            # 상세 금액
            ic1, ic2, ic3 = st.columns(3)
            with ic1:
                st.markdown(f"**공급가액** ₩{int(row['_supply']):,}")
                if int(row['_tax']) > 0:
                    st.caption(f"부가세 ₩{int(row['_tax']):,}")
            with ic2:
                st.markdown(f"**받은금액** ₩{paid:,}")
            with ic3:
                if balance > 0:
                    st.markdown(f"**잔액** <span style='color:#DC2626;font-weight:700;'>₩{balance:,}</span>",
                                unsafe_allow_html=True)
                else:
                    st.markdown("**잔액** ₩0 ✅")

            # 진행상황 표시
            if progress and progress not in ('nan', 'None', ''):
                st.caption(f"📋 진행상황: {progress}")

            # ── 입금 기록 입력 (잔액 있을 때만) ──
            if balance > 0:
                st.markdown("---")
                st.markdown("**💳 입금 기록**")

                # 빠른 입력 버튼
                qc1, qc2, qc3 = st.columns(3)
                fill_key = f"_ceo_dep_fill_{inq_id}"
                with qc1:
                    half = int(invoice * 0.5)
                    if st.button(f"50% ₩{half:,}", key=f"ceo_dep_50_{inq_id}", use_container_width=True):
                        st.session_state[fill_key] = half
                        st.rerun()
                with qc2:
                    if st.button(f"잔금 ₩{balance:,}", key=f"ceo_dep_rem_{inq_id}", use_container_width=True):
                        st.session_state[fill_key] = balance
                        st.rerun()
                with qc3:
                    if st.button(f"전액 ₩{invoice:,}", key=f"ceo_dep_full_{inq_id}", use_container_width=True):
                        st.session_state[fill_key] = invoice
                        st.rerun()

                # 입금 금액 입력
                amt_key = f"ceo_dep_amt_{inq_id}"
                if fill_key in st.session_state:
                    st.session_state[amt_key] = st.session_state.pop(fill_key)

                ac1, ac2, ac3 = st.columns([2, 1, 1])
                with ac1:
                    new_amount = st.number_input(
                        "입금액", min_value=0, step=10000,
                        key=amt_key, label_visibility="collapsed"
                    )
                with ac2:
                    new_total = paid + new_amount
                    st.metric("누적", f"₩{new_total:,}")
                with ac3:
                    new_remain = max(0, invoice - new_total)
                    st.metric("잔액", f"₩{new_remain:,}")

                if st.button("💾 입금 저장", key=f"ceo_dep_save_{inq_id}", type="primary", use_container_width=True):
                    if new_amount > 0:
                        result = save_payment_record(inq_id, new_total, invoice)
                        if result:
                            st.success(f"✅ {company} 입금 ₩{new_amount:,} 저장!")
                            db.invalidate_data()
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.warning("입금 금액을 입력하세요.")


# ==============================================================================
# 9. 프로젝트 수익 보고 탭
# ==============================================================================
def _render_profit_tab(settlement_df, payment_df):
    """행사종료 프로젝트별 수익(공급가액 - Σ지급내역.소계) 보고"""
    st.markdown('<div class="ceo-section">📊 프로젝트별 최종 수익 보고</div>', unsafe_allow_html=True)
    st.caption("행사종료 건만 표시 · 수익 = 공급가액 - 인력비 지급원가(소계 합산)")

    if settlement_df.empty:
        st.warning("⚠️ 정산 데이터가 없습니다.")
        return

    df = settlement_df.copy()
    col_inq = _find_col(df, ['문의ID'])
    col_company = _find_col(df, ['업체', '업체명'])
    col_site = _find_col(df, ['현장명', '행사명'])
    col_supply = _find_col(df, ['공급가액'])
    col_progress = _find_col(df, ['진행상황'])

    if not col_inq or not col_supply or not col_progress:
        st.warning("⚠️ 필수 컬럼(문의ID, 공급가액, 진행상황)이 없습니다.")
        return

    # 행사종료 필터
    df['_progress'] = df[col_progress].astype(str).str.strip()
    df_done = df[df['_progress'] == '행사종료'].copy()

    if df_done.empty:
        st.info("행사종료된 프로젝트가 아직 없습니다.")
        return

    df_done['_supply'] = pd.to_numeric(df_done[col_supply], errors='coerce').fillna(0).astype(int)

    # ── payment_df에서 문의ID별 소계 합산 ──
    cost_map = {}  # 문의ID → 소계합산
    staff_map = {}  # 문의ID → [{이름, 소계}, ...]
    if not payment_df.empty:
        p_inq = _find_col(payment_df, ['문의ID'])
        p_subtotal = _find_col(payment_df, ['소계'])
        p_name = _find_col(payment_df, ['인력명', '이름'])
        if p_inq and p_subtotal:
            for _, pr in payment_df.iterrows():
                inq_id = str(pr.get(p_inq, '')).strip()
                if not inq_id or inq_id in ('nan', 'None', ''):
                    continue
                sub = int(pd.to_numeric(pr.get(p_subtotal, 0), errors='coerce') or 0)
                cost_map[inq_id] = cost_map.get(inq_id, 0) + sub
                name = str(pr.get(p_name, '')) if p_name else ''
                if inq_id not in staff_map:
                    staff_map[inq_id] = []
                staff_map[inq_id].append({'이름': name, '소계': sub})

    # ── 프로젝트별 수익 계산 ──
    profit_rows = []
    for _, row in df_done.iterrows():
        inq_id = str(row[col_inq]).strip()
        company = str(row[col_company]).strip() if col_company else ''
        site = str(row[col_site]).strip() if col_site else ''
        supply = int(row['_supply'])
        cost = cost_map.get(inq_id, 0)
        profit = supply - cost
        margin = round(profit / supply * 100, 1) if supply > 0 else 0.0
        profit_rows.append({
            'inq_id': inq_id,
            'company': company,
            'site': site,
            'supply': supply,
            'cost': cost,
            'profit': profit,
            'margin': margin,
            'staffs': staff_map.get(inq_id, []),
        })

    # 수익 내림차순 정렬
    profit_rows.sort(key=lambda x: x['profit'], reverse=True)

    # ── KPI 요약 ──
    total_supply = sum(p['supply'] for p in profit_rows)
    total_cost = sum(p['cost'] for p in profit_rows)
    total_profit = total_supply - total_cost
    avg_margin = round(total_profit / total_supply * 100, 1) if total_supply > 0 else 0.0
    count = len(profit_rows)
    loss_count = sum(1 for p in profit_rows if p['profit'] < 0)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        _bg = "#F0FDF4" if total_profit >= 0 else "#FEF2F2"
        _clr = "#059669" if total_profit >= 0 else "#DC2626"
        st.markdown(
            f'<div class="ceo-kpi" style="background:{_bg};border:1px solid {_clr}33;">'
            f'<div class="kpi-label" style="color:{_clr};">💰 총 수익</div>'
            f'<div class="kpi-value" style="color:{_clr};">₩{total_profit:,}</div>'
            f'<div class="kpi-sub">매출 ₩{total_supply:,}</div></div>',
            unsafe_allow_html=True,
        )
    with m2:
        _rc = "#059669" if avg_margin >= 30 else "#D97706" if avg_margin >= 10 else "#DC2626"
        st.markdown(
            f'<div class="ceo-kpi" style="background:#EFF6FF;border:1px solid #BFDBFE;">'
            f'<div class="kpi-label" style="color:#2563EB;">📈 평균 수익률</div>'
            f'<div class="kpi-value" style="color:{_rc};">{avg_margin}%</div>'
            f'<div class="kpi-sub">목표 30% 이상</div></div>',
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f'<div class="ceo-kpi" style="background:#F0FDF4;border:1px solid #BBF7D0;">'
            f'<div class="kpi-label" style="color:#059669;">✅ 완료 건수</div>'
            f'<div class="kpi-value" style="color:#059669;">{count}건</div>'
            f'<div class="kpi-sub">행사종료 프로젝트</div></div>',
            unsafe_allow_html=True,
        )
    with m4:
        _lclr = "#DC2626" if loss_count > 0 else "#059669"
        st.markdown(
            f'<div class="ceo-kpi" style="background:{"#FEF2F2" if loss_count > 0 else "#F0FDF4"};'
            f'border:1px solid {_lclr}33;">'
            f'<div class="kpi-label" style="color:{_lclr};">⚠️ 적자 프로젝트</div>'
            f'<div class="kpi-value" style="color:{_lclr};">{loss_count}건</div>'
            f'<div class="kpi-sub">수익 < 0</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── 필터 ──
    fc, _ = st.columns([3, 7])
    with fc:
        profit_filter = st.radio(
            "필터", ["📋 전체", "💚 흑자", "🔴 적자"],
            key="ceo_profit_filter", horizontal=True, label_visibility="collapsed"
        )

    if profit_filter == "💚 흑자":
        view_rows = [p for p in profit_rows if p['profit'] >= 0]
    elif profit_filter == "🔴 적자":
        view_rows = [p for p in profit_rows if p['profit'] < 0]
    else:
        view_rows = profit_rows

    if not view_rows:
        st.info("해당 조건의 프로젝트가 없습니다.")
        return

    st.caption(f"총 {len(view_rows)}건")

    # ── 프로젝트 카드 리스트 ──
    for p in view_rows:
        profit_val = p['profit']
        margin_val = p['margin']

        if profit_val >= 0:
            badge = "💚 흑자"
            badge_bg = "#D1FAE5"
            badge_clr = "#065F46"
            card_border = "#10B981"
        else:
            badge = "🔴 적자"
            badge_bg = "#FEE2E2"
            badge_clr = "#991B1B"
            card_border = "#EF4444"

        # 수익률 바
        bar_pct = max(0, min(100, int(margin_val)))
        bar_color = "#10B981" if margin_val >= 30 else "#F59E0B" if margin_val >= 10 else "#EF4444"

        with st.expander(
            f"{badge}  **{p['company']}** — {p['site']}  |  수익 ₩{profit_val:,}  |  수익률 {margin_val}%"
        ):
            # 수익률 프로그레스 바
            st.markdown(
                f'<div style="background:#E5E7EB;border-radius:8px;height:10px;margin-bottom:12px;">'
                f'<div style="background:{bar_color};border-radius:8px;height:100%;'
                f'width:{bar_pct}%;"></div></div>'
                f'<div style="text-align:right;font-size:12px;color:#6B7280;margin-top:-8px;">'
                f'수익률 {margin_val}%</div>',
                unsafe_allow_html=True,
            )

            # 금액 상세
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                st.markdown(f"**공급가액 (매출)**")
                st.markdown(f"### ₩{p['supply']:,}")
            with ac2:
                st.markdown(f"**지급원가**")
                st.markdown(f"### ₩{p['cost']:,}")
            with ac3:
                clr = "#059669" if profit_val >= 0 else "#DC2626"
                st.markdown(f"**수익**")
                st.markdown(
                    f"<h3 style='color:{clr};'>₩{profit_val:,}</h3>",
                    unsafe_allow_html=True,
                )

            # 인력별 지급 내역
            staffs = p['staffs']
            if staffs:
                st.markdown("---")
                st.markdown(f"**👥 인력별 지급 내역** ({len(staffs)}명)")
                staff_data = []
                for s in sorted(staffs, key=lambda x: x['소계'], reverse=True):
                    staff_data.append({
                        '인력명': s['이름'],
                        '소계(지급원가)': f"₩{s['소계']:,}",
                    })
                st.dataframe(
                    pd.DataFrame(staff_data),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("💡 지급내역 데이터가 아직 없습니다.")
