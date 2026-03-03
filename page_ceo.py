# page_ceo.py — 대표님 전용 페이지
# 세금계산서 발행 현황 + 인력비 미지급 현황을 한눈에 확인하고 즉시 처리
# 정산 페이지(page_settlement.py)와 동일한 team_info/calc_rows 로직 사용
import streamlit as st
import pandas as pd
import data_loader as db
import utils_dashboard as ud
import time
from datetime import datetime


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
        '</style>',
        unsafe_allow_html=True,
    )


# ==============================================================================
# 2. 데이터 로드 헬퍼
# ==============================================================================
def _load_all_ceo_data():
    """세금계산서(settlement) + 배정/지급 데이터를 한 번에 로드"""
    dispatch_data = db.get_dispatch()
    settlement_df = dispatch_data.get('settlement', pd.DataFrame())
    dispatch_df = dispatch_data.get('dispatch', pd.DataFrame())
    payment_df = dispatch_data.get('payment', pd.DataFrame())
    if not settlement_df.empty:
        settlement_df = settlement_df.fillna('').copy()
        settlement_df.columns = [str(c).replace('\n', ' ').strip() for c in settlement_df.columns]
    return settlement_df, dispatch_df, payment_df


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
def _build_inquiry_payment_data(dispatch_df, payment_df):
    """
    문의ID별로 배정기록을 그룹핑한 뒤, 정산 페이지와 동일하게
    team_info(팀 그룹핑) + calc_rows(급여 계산) 를 구성.
    Returns: list of dicts (각 문의별 급여 데이터)
    """
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
            a_bank = str(arow.get(col_bank, '')).strip() if col_bank else ''
            a_acct = str(arow.get(col_acct, '')).strip() if col_acct else ''
            a_date = str(arow.get(col_date, '')).strip() if col_date else ''
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
            if hasattr(pr, 'get'):
                meal = ud.safe_int(pr.get('식사비', 0))
                transport = ud.safe_int(pr.get('교통비', 0))
                overtime = ud.safe_int(pr.get('야근비', 0))
                etc_cost = ud.safe_int(pr.get('보너스', 0))
                saved_gross = ud.safe_int(pr.get('소계', 0))
                saved_tax = ud.safe_int(pr.get('세금공제', 0))
                saved_net = ud.safe_int(pr.get('최종지급액', 0))
            else:
                meal = transport = overtime = etc_cost = 0
                saved_gross = saved_tax = saved_net = 0

            # 지급상태
            pst = pay_status_map.get(a_aid, '미저장')

            # 금액 결정: 지급내역 저장된 게 있으면 그걸 사용 (정산 페이지와 동일한 값)
            if saved_net > 0:
                gross = saved_gross
                tax = saved_tax
                net = saved_net
            else:
                gross = basic + meal + transport + overtime + etc_cost
                tax = int(gross * 0.033)  # 기본 3.3%
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
                '총액': gross,
                '공제': tax,
                '실수령': net,
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
        settlement_df, dispatch_df, payment_df = _load_all_ceo_data()
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
        _build_inquiry_payment_data(dispatch_df, payment_df)
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

    tab_tax, tab_pay = st.tabs(["📄 세금계산서 발행 관리", "💸 인력비 지급 관리"])

    with tab_tax:
        _render_tax_invoice_tab(settlement_df, not_issued_df, col_tax, col_company, col_inq_id,
                                tax_issued, tax_not_issued)

    with tab_pay:
        _render_payment_tab(venue_data_list, staff_done, staff_total, total_unpaid_amt, dispatch_df)


# ==============================================================================
# 6. 세금계산서 탭 상세
# ==============================================================================
def _render_tax_invoice_tab(settlement_df, not_issued_df, col_tax, col_company, col_inq_id,
                            tax_issued, tax_not_issued):
    st.markdown('<div class="ceo-section">📄 세금계산서 발행 현황</div>', unsafe_allow_html=True)

    if settlement_df.empty:
        st.warning("⚠️ 정산 데이터가 없습니다.")
        return
    if not col_tax or not col_company:
        st.warning("⚠️ 세금계산서 발행여부 또는 업체 컬럼을 찾을 수 없습니다.")
        return

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

        col_left, col_right = st.columns([4, 1])
        with col_left:
            biz_lines = []
            if biz_num and biz_num not in ('nan', 'None', ''):
                biz_lines.append(f"🏢 사업자번호: <b>{biz_num}</b>")
            if ceo_name and ceo_name not in ('nan', 'None', ''):
                biz_lines.append(f"👤 대표자: {ceo_name}")
            if email_val and email_val not in ('nan', 'None', ''):
                biz_lines.append(f"📧 이메일: <b>{email_val}</b>")

            item_val = str(row.get('내용(품목)', '')).strip()
            item_line = ''
            if item_val and item_val not in ('nan', 'None', ''):
                item_line = f'📦 품목: <b>{item_val}</b><br/>'

            money_parts = []
            if supply_str:
                money_parts.append(f"공급가액: <b>{supply_str}</b>")
            if tax_str:
                money_parts.append(f"부가세: <b>{tax_str}</b>")
            if amount_str:
                money_parts.append(f"합계: <b>{amount_str}</b>")

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

            biz_block = " · ".join(biz_lines) if biz_lines else ""
            money_block = " | ".join(money_parts) if money_parts else ""
            title = f"<b style='font-size:18px;'>{company}</b>"
            if site_name:
                title += f" <span style='color:#6b7280;font-size:14px;'>({site_name})</span>"

            st.markdown(
                f'<div class="ceo-card">'
                f'<div class="card-title">{title}</div>'
                f'<div class="card-detail">'
                f'{item_line}'
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
def _render_payment_tab(venue_data_list, staff_done, staff_total, total_unpaid_amt, dispatch_df):
    st.markdown('<div class="ceo-section">💸 인력비 지급 현황</div>', unsafe_allow_html=True)

    if not venue_data_list:
        if dispatch_df.empty:
            st.info("📋 배정 기록이 없습니다.")
        else:
            st.success("🎉 모든 인력 급여가 지급 완료되었습니다!")
            _show_done_summary(staff_done, staff_total)
        return

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
        st.markdown(f"#### 📍 {venue} ({len(venue_unpaid)}명 · ₩{venue_total:,})")

        # 현장 일괄 입금완료
        venue_pending = [cr for cr in venue_unpaid if cr['지급상태'] == '대기']
        if len(venue_pending) > 1:
            if st.button(f"💰 {venue} 전체 {len(venue_pending)}명 일괄 입금완료",
                         key=f"ceo_bulk_{inq_id}", type="primary"):
                _now = datetime.now().strftime('%Y-%m-%d')
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
            status_txt = " [대기]" if leader_cr['지급상태'] == '대기' else " [미저장]"
            bank_info = (f"💳 {leader_cr['은행']} {leader_cr['계좌']}"
                         if leader_cr['은행'] and leader_cr['은행'] not in ('nan', 'None', '')
                         else "❗ 계좌 미등록")

            with st.expander(
                f"{status_badge} 👥 {leader}팀{status_txt} ({total_n}명, 현장{onsite_n}명{onsite_tag}) "
                f"— ₩{leader_cr['실수령']:,} {bank_info}"
            ):
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
                        f"| 기타(숙박등) | ₩{leader_cr['기타']:,} |\n"
                        f"| **총액** | **₩{leader_cr['총액']:,}** |\n"
                        f"| 공제 | -₩{leader_cr['공제']:,} |\n"
                        f"| **실수령 → {leader} 계좌** | **₩{leader_cr['실수령']:,}** |"
                    )
                with c2:
                    if leader_cr['은행'] and leader_cr['은행'] not in ('nan', 'None', ''):
                        st.info(f"🏦 {leader_cr['은행']}\n\n📋 {leader_cr['계좌']}\n\n👤 수령인: **{leader}**")
                    else:
                        st.warning(f"❗ {leader} 계좌 미등록")

                    # 입금완료 버튼
                    if leader_cr['지급상태'] == '대기':
                        if st.button("💰 팀 입금완료", key=f"ceo_team_{tc}_{inq_id}", type="primary",
                                     use_container_width=True):
                            _now = datetime.now().strftime('%Y-%m-%d')
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
                        st.caption("📝 정산 페이지에서\n지급기록 먼저 저장")

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
                bank_display = (f"💳 {bank} {acct}"
                                if bank and bank not in ('nan', 'None', '')
                                else "❗ 계좌 미등록")
                status_badge = "⏳" if pst == '대기' else "📝"
                status_txt = " [대기]" if pst == '대기' else " [미저장]"

                with st.expander(
                    f"{status_badge} 👤 {name}{status_txt} ({cr['직무']}) "
                    f"— ₩{net:,} {bank_display}"
                ):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(
                            f"| 항목 | 금액 |\n|------|------|\n"
                            f"| 기본급 ({cr['단가']:,} × {cr['일수']}일) | ₩{cr['기본급']:,} |\n"
                            f"| 식비 | ₩{cr['식비']:,} |\n"
                            f"| 교통비 | ₩{cr['교통비']:,} |\n"
                            f"| 연장 | ₩{cr['연장']:,} |\n"
                            f"| 기타(숙박등) | ₩{cr['기타']:,} |\n"
                            f"| **총액** | **₩{cr['총액']:,}** |\n"
                            f"| 공제 | -₩{cr['공제']:,} |\n"
                            f"| **실수령** | **₩{net:,}** |"
                        )
                    with c2:
                        if bank and bank not in ('nan', 'None', ''):
                            st.info(f"🏦 {bank}\n\n📋 {acct}")
                        else:
                            st.warning("❗ 계좌 미등록")

                        if pst == '대기' and aid:
                            if st.button("💰 입금완료", key=f"ceo_ind_{aid}_{inq_id}", type="primary",
                                         use_container_width=True):
                                _now = datetime.now().strftime('%Y-%m-%d')
                                db.update_payment_status(aid, '완료', _now)
                                db.invalidate_payment_cache()
                                db.invalidate_dispatch_only()
                                st.success(f"✅ {name} 입금완료!")
                                time.sleep(1)
                                st.rerun()
                        elif pst == '미저장':
                            st.caption("📝 정산 페이지에서\n지급기록 먼저 저장")

        st.markdown("---")

    # 현장별 요약
    with st.expander("📊 현장별 미지급 요약", expanded=False):
        summary_rows = []
        for vd in venue_data_list:
            unpaid = [cr for cr in vd['calc_rows']
                      if cr['지급상태'] not in ('완료', '확인완료') and not cr['본사']]
            if unpaid:
                summary_rows.append({
                    '현장명': vd['venue'],
                    '인원': len(unpaid),
                    '미지급합계': sum(cr['실수령'] for cr in unpaid),
                })
        if summary_rows:
            sdf = pd.DataFrame(summary_rows).sort_values('미지급합계', ascending=False).reset_index(drop=True)
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
