# page_ceo.py — 대표님 전용 페이지
# 세금계산서 발행 현황 + 인력비 미지급 현황을 한눈에 확인하고 즉시 처리
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
    st.markdown("""
    <style>
        .ceo-kpi {
            border-radius: 14px; padding: 18px 14px; text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08); min-height: 110px;
        }
        .ceo-kpi .kpi-label { font-size: 13px; font-weight: 600; opacity: 0.85; margin-bottom: 6px; }
        .ceo-kpi .kpi-value { font-size: 32px; font-weight: 800; margin: 6px 0; }
        .ceo-kpi .kpi-sub { font-size: 12px; opacity: 0.7; }
        .ceo-card {
            background: white; border: 1px solid #e5e7eb; border-radius: 10px;
            padding: 20px; margin-bottom: 12px;
            border-left: 4px solid #EF4444; transition: all 0.15s;
        }
        .ceo-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
        .ceo-card.done { border-left-color: #10B981; background: #F0FDF4; }
        .ceo-card .card-title { font-size: 18px; font-weight: 700; color: #1e293b; margin-bottom: 8px; }
        .ceo-card .card-detail { font-size: 14px; color: #4b5563; line-height: 1.9; }
        .ceo-card .card-amount { font-size: 17px; font-weight: 700; color: #DC2626; }
        .ceo-section { font-size: 20px; font-weight: 700; color: #111827; margin-bottom: 14px;
                       padding-left: 10px; border-left: 4px solid #6366F1; }
    </style>
    """, unsafe_allow_html=True)


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
    """컬럼 탐색 (utils_dashboard.find_col 과 동일 로직)"""
    for c in candidates:
        if c in df.columns:
            return c
    for c in candidates:
        for col in df.columns:
            if c in col:
                return col
    return None


# ==============================================================================
# 3. 세금계산서 현황 분석
# ==============================================================================
def _get_tax_invoice_stats(settlement_df):
    """세금계산서 발행 현황 집계 → (발행완료수, 미발행수, 미발행DF, col_tax_issued, col_company)"""
    col_company = None
    col_tax_issued = None
    col_inq_id = None

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
# 4. 인력비 미지급 현황 분석
# ==============================================================================
def _get_unpaid_staff_stats(dispatch_df, payment_df):
    """미지급 인력 통계: (미지급DF, 완료수, 미지급수, 총액, 본사HQ목록)"""
    if dispatch_df.empty:
        return pd.DataFrame(), 0, 0, 0, []

    col_name = _find_col(dispatch_df, ["인력명", "이름", "성명"])
    col_venue = _find_col(dispatch_df, ["현장명", "행사명"])
    col_pay_amt = _find_col(dispatch_df, ["총지급액", "지급액"])
    col_date = _find_col(dispatch_df, ["파견일자", "파견기간", "날짜"])
    col_assign_id = _find_col(dispatch_df, ["배정ID"])
    col_bank = _find_col(dispatch_df, ["은행명", "은행"])
    col_acct = _find_col(dispatch_df, ["계좌번호", "계좌"])
    col_pay_target = _find_col(dispatch_df, ["결제대상"])

    if not col_name or not col_pay_amt:
        return pd.DataFrame(), 0, 0, 0, []

    pay_df = dispatch_df.copy()

    # 팀원(결제대상=N)은 팀장 계좌로 일괄지급되므로 개별 미지급 목록에서 제외
    if col_pay_target and col_pay_target in pay_df.columns:
        pay_df = pay_df[pay_df[col_pay_target].astype(str).str.strip().str.upper() != 'N'].copy()

    pay_df['_지급액'] = pay_df[col_pay_amt].apply(ud.safe_int)

    # 지급내역(payment_df)에 기록된 최종지급액이 있으면 우선 사용 (팀장 합산금액 반영)
    if not payment_df.empty and col_assign_id:
        _pay_amt_col = _find_col(payment_df, ["최종지급액", "소계"])
        _pay_bid_col = _find_col(payment_df, ["배정ID"])
        if _pay_amt_col and _pay_bid_col:
            _pay_amt_map = {}
            for _, _pr in payment_df.iterrows():
                _pbid = str(_pr.get(_pay_bid_col, '')).strip()
                _pamt = ud.safe_int(_pr.get(_pay_amt_col, 0))
                if _pbid and _pamt > 0:
                    _pay_amt_map[_pbid] = _pamt
            if _pay_amt_map:
                def _override_amt(row):
                    _bid = str(row.get(col_assign_id, '')).strip()
                    return _pay_amt_map.get(_bid, row['_지급액'])
                pay_df['_지급액'] = pay_df.apply(_override_amt, axis=1)

    pay_df = pay_df[pay_df['_지급액'] > 0].copy()

    if pay_df.empty:
        return pd.DataFrame(), 0, 0, 0, []

    # 본사 인원 목록
    hq_names = [s['이름'] for s in db.HQ_STAFF] if hasattr(db, 'HQ_STAFF') else []

    # 지급내역 시트 기준 상태 판정 (Single Source of Truth)
    completed_ids = set()
    hq_confirmed_ids = set()
    pending_ids = set()

    if not payment_df.empty:
        col_paid_bid = _find_col(payment_df, ["배정ID"])
        col_paid_status = _find_col(payment_df, ["지급상태"])
        if col_paid_bid and col_paid_status:
            for _, pr in payment_df.iterrows():
                bid = str(pr.get(col_paid_bid, '')).strip()
                pst = str(pr.get(col_paid_status, '')).strip()
                if pst == '완료':
                    completed_ids.add(bid)
                elif pst == '확인완료':
                    hq_confirmed_ids.add(bid)
                    completed_ids.add(bid)
                elif pst == '대기':
                    pending_ids.add(bid)

    def _status(row):
        bid = str(row.get(col_assign_id, '')).strip() if col_assign_id and col_assign_id in pay_df.columns else ''
        if bid in completed_ids:
            return '확인완료' if bid in hq_confirmed_ids else '완료'
        elif bid in pending_ids:
            return '대기'
        return '미저장'

    pay_df['_상태'] = pay_df.apply(_status, axis=1)
    pay_df['_본사'] = pay_df[col_name].astype(str).str.strip().isin(hq_names) if col_name else False

    # 미지급 = 완료/확인완료가 아닌 건 (외부인력만)
    unpaid_ext = pay_df[(~pay_df['_상태'].isin(['완료', '확인완료'])) & (~pay_df['_본사'])].copy()

    done_ext = len(pay_df[(~pay_df['_본사']) & (pay_df['_상태'] == '완료')])
    done_hq = len(pay_df[(pay_df['_본사']) & (pay_df['_상태'] == '확인완료')])
    total_done = done_ext + done_hq
    total_all = len(pay_df)
    total_unpaid_amt = int(unpaid_ext['_지급액'].sum())

    # 메타 컬럼 정보 기록
    unpaid_ext.attrs['col_name'] = col_name
    unpaid_ext.attrs['col_venue'] = col_venue
    unpaid_ext.attrs['col_date'] = col_date
    unpaid_ext.attrs['col_assign_id'] = col_assign_id
    unpaid_ext.attrs['col_bank'] = col_bank
    unpaid_ext.attrs['col_acct'] = col_acct

    return unpaid_ext, total_done, total_all, total_unpaid_amt, hq_names


# ==============================================================================
# 5. 메인 show 함수
# ==============================================================================
def show(data):
    _apply_styles()
    st.title("🏢 대표님 전용")
    st.caption("세금계산서 발행 & 인력비 지급 — 확인 즉시 처리")

    # ── 데이터 로드 ──
    try:
        settlement_df, dispatch_df, payment_df = _load_all_ceo_data()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return

    # ── 세금계산서 stats ──
    tax_issued, tax_not_issued, not_issued_df, col_tax, col_company, col_inq_id = (
        _get_tax_invoice_stats(settlement_df) if not settlement_df.empty else (0, 0, pd.DataFrame(), None, None, None)
    )

    # ── 인력비 stats ──
    unpaid_ext, staff_done, staff_total, total_unpaid_amt, hq_names = (
        _get_unpaid_staff_stats(dispatch_df, payment_df)
    )

    # ── 미수금 ──
    settlement_overview = ud.get_settlement_overview(settlement_df) if not settlement_df.empty else {
        "미수금액": 0, "받은금액": 0, "총청구액": 0, "수금률": 0
    }

    pay_rate = int(staff_done / staff_total * 100) if staff_total > 0 else 0
    action_needed = tax_not_issued + len(unpaid_ext)

    # ====================================================================
    # KPI 카드 5개
    # ====================================================================
    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:
        _bg = "#FEF2F2" if tax_not_issued > 0 else "#F0FDF4"
        _clr = "#DC2626" if tax_not_issued > 0 else "#059669"
        st.markdown(f"""
        <div class="ceo-kpi" style="background:{_bg};border:1px solid {_clr}33;">
            <div class="kpi-label" style="color:{_clr};">📄 미발행 세금계산서</div>
            <div class="kpi-value" style="color:{_clr};">{tax_not_issued}건</div>
            <div class="kpi-sub">발행완료 {tax_issued}건</div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        _amt = settlement_overview['미수금액']
        _bg2 = "#FFF7ED" if _amt > 0 else "#F0FDF4"
        _clr2 = "#EA580C" if _amt > 0 else "#059669"
        st.markdown(f"""
        <div class="ceo-kpi" style="background:{_bg2};border:1px solid {_clr2}33;">
            <div class="kpi-label" style="color:{_clr2};">💳 미수금액</div>
            <div class="kpi-value" style="color:{_clr2};">{_amt:,}원</div>
            <div class="kpi-sub">수금률 {settlement_overview['수금률']}%</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        _bg3 = "#FEF2F2" if total_unpaid_amt > 0 else "#F0FDF4"
        _clr3 = "#DC2626" if total_unpaid_amt > 0 else "#059669"
        st.markdown(f"""
        <div class="ceo-kpi" style="background:{_bg3};border:1px solid {_clr3}33;">
            <div class="kpi-label" style="color:{_clr3};">💸 미지급 인건비</div>
            <div class="kpi-value" style="color:{_clr3};">{total_unpaid_amt:,}원</div>
            <div class="kpi-sub">외부인력 {len(unpaid_ext)}명</div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        _rc = "#059669" if pay_rate >= 80 else "#D97706" if pay_rate >= 50 else "#DC2626"
        st.markdown(f"""
        <div class="ceo-kpi" style="background:#EFF6FF;border:1px solid #BFDBFE;">
            <div class="kpi-label" style="color:#2563EB;">📊 지급률</div>
            <div class="kpi-value" style="color:{_rc};">{pay_rate}%</div>
            <div class="kpi-sub">{staff_done}/{staff_total}명 처리</div>
        </div>
        """, unsafe_allow_html=True)

    with k5:
        _bg5 = "#FDF4FF" if action_needed > 0 else "#F0FDF4"
        _clr5 = "#9333EA" if action_needed > 0 else "#059669"
        st.markdown(f"""
        <div class="ceo-kpi" style="background:{_bg5};border:1px solid {_clr5}33;">
            <div class="kpi-label" style="color:{_clr5};">🔔 처리 필요</div>
            <div class="kpi-value" style="color:{_clr5};">{action_needed}건</div>
            <div class="kpi-sub">세금계산서 {tax_not_issued} + 급여 {len(unpaid_ext)}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ====================================================================
    # 탭: 세금계산서 | 인력비
    # ====================================================================
    tab_tax, tab_pay = st.tabs(["📄 세금계산서 발행 관리", "💸 인력비 지급 관리"])

    # ====================================================================
    # TAB 1 — 세금계산서 발행 관리
    # ====================================================================
    with tab_tax:
        _render_tax_invoice_tab(settlement_df, not_issued_df, col_tax, col_company, col_inq_id,
                                tax_issued, tax_not_issued)

    # ====================================================================
    # TAB 2 — 인력비 지급 관리
    # ====================================================================
    with tab_pay:
        _render_payment_tab(unpaid_ext, dispatch_df, payment_df, hq_names,
                            staff_done, staff_total, total_unpaid_amt)


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

    # 홈택스 바로가기
    st.link_button(
        "🏛️ 홈택스 세금계산서 발행 바로가기",
        "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index_pp.xml&menuCd=index3",
        use_container_width=True,
        type="primary",
    )
    st.caption("💡 홈택스에서 전자세금계산서를 발행한 뒤 아래에서 '발행완료' 버튼을 눌러주세요.")
    st.markdown("")

    # ── 전체 업체 현황 테이블 ──
    with st.expander(f"📋 전체 업체 현황 ({tax_issued + tax_not_issued}건)", expanded=False):
        display_cols = [c for c in [col_inq_id, col_company, '현장명', '청구금액', '공급가액', '부가세',
                                     col_tax, '사업자번호', '이메일']
                        if c and c in settlement_df.columns]
        if display_cols:
            st.dataframe(settlement_df[display_cols], use_container_width=True, hide_index=True)

    # ── 미발행 목록 (액션 카드) ──
    if not_issued_df.empty:
        st.success("🎉 모든 업체의 세금계산서가 발행되었습니다!")
        return

    st.markdown(f"### 🚨 미발행 업체 ({tax_not_issued}건) — 즉시 처리 필요")

    # 일괄 발행완료 버튼
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
                        not_issued_inq_ids = set(not_issued_df['문의ID'].astype(str).str.strip()) if '문의ID' in not_issued_df.columns else set()
                        for r_idx in range(1, len(all_records)):
                            row_inq = str(all_records[r_idx][0]).strip()
                            if row_inq in not_issued_inq_ids:
                                cells.append(Cell(row=r_idx + 1, col=tax_col_idx, value="발행완료"))
                        if cells:
                            _wks.update_cells(cells, value_input_option='RAW')
                    db.invalidate_data()
                    st.success(f"✅ {tax_not_issued}건 세금계산서 일괄 발행완료 처리됨!")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"일괄 처리 실패: {e}")
        st.markdown("")

    # 개별 카드
    for idx, row in not_issued_df.iterrows():
        company = str(row.get(col_company, '미등록')).strip()
        site_name = str(row.get('현장명', '')).strip()
        biz_num = str(row.get('사업자번호', '')).strip()
        email_val = str(row.get('이메일', '')).strip()
        ceo_name = str(row.get('대표자', '')).strip()

        # 금액
        def _fmt(v):
            try:
                n = int(float(str(v).replace(',', '').strip()))
                return f"₩{n:,}" if n > 0 else ''
            except:
                return str(v).strip() if str(v).strip() not in ('', 'nan', 'None', '0') else ''

        amount_str = _fmt(row.get('청구금액', ''))
        supply_str = _fmt(row.get('공급가액', ''))
        tax_str = _fmt(row.get('부가세', ''))

        # 자동 계산
        if not supply_str and amount_str:
            try:
                total_amt = int(float(str(row.get('청구금액', 0)).replace(',', '').strip()))
                calc_supply = int(total_amt / 1.1)
                calc_tax = total_amt - calc_supply
                supply_str = f"₩{calc_supply:,} (추정)"
                tax_str = f"₩{calc_tax:,} (추정)"
            except:
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

            # 품목 정보
            item_val = str(row.get('내용(품목)', '')).strip()
            item_line = ''
            if item_val and item_val not in ('nan', 'None', ''):
                item_line = f'📦 품목: <b>{item_val}</b><br/>'

            money_lines = []
            if supply_str:
                money_lines.append(f"공급가액: <b>{supply_str}</b>")
            if tax_str:
                money_lines.append(f"부가세: <b>{tax_str}</b>")
            if amount_str:
                money_lines.append(f"합계: <b>{amount_str}</b>")

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
            money_block = " | ".join(money_lines) if money_lines else ""
            title = f"<b style='font-size:18px;'>{company}</b>"
            if site_name:
                title += f" <span style='color:#6b7280;font-size:14px;'>({site_name})</span>"

            card_html = (
                f'<div class="ceo-card">'
                f'<div class="card-title">{title}</div>'
                f'<div class="card-detail">'
                f'{item_line}'
                f'{biz_block}{"<br/>" if biz_block else ""}'
                f'<span style="color:#C2410C;font-weight:600;">{money_block}</span>'
                f'</div>'
                f'{missing_html}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

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
# 7. 인력비 지급 탭 상세
# ==============================================================================
def _render_payment_tab(unpaid_ext, dispatch_df, payment_df, hq_names,
                        staff_done, staff_total, total_unpaid_amt):
    st.markdown('<div class="ceo-section">💸 인력비 미지급 현황</div>', unsafe_allow_html=True)

    if dispatch_df.empty:
        st.info("📋 배정 기록이 없습니다.")
        return

    if unpaid_ext.empty:
        st.success("🎉 모든 외부인력 급여가 지급 완료되었습니다!")
        _show_done_summary(staff_done, staff_total)
        return

    # 컬럼 메타
    col_name = unpaid_ext.attrs.get('col_name')
    col_venue = unpaid_ext.attrs.get('col_venue')
    col_date = unpaid_ext.attrs.get('col_date')
    col_assign_id = unpaid_ext.attrs.get('col_assign_id')
    col_bank = unpaid_ext.attrs.get('col_bank')
    col_acct = unpaid_ext.attrs.get('col_acct')

    # ── 현장별 그룹핑 ──
    if col_venue and col_venue in unpaid_ext.columns:
        venue_groups = unpaid_ext.groupby(unpaid_ext[col_venue].astype(str).str.strip())
    else:
        venue_groups = [("전체", unpaid_ext)]

    st.markdown(f"**미지급 합계: ₩{total_unpaid_amt:,}** ({len(unpaid_ext)}명)")
    st.markdown("")

    for venue_name, venue_df in venue_groups:
        venue_total = int(venue_df['_지급액'].sum())
        venue_cnt = len(venue_df)

        st.markdown(f"#### 📍 {venue_name} ({venue_cnt}명 · ₩{venue_total:,})")

        # 현장 단위 일괄 입금완료
        if venue_cnt > 1:
            if st.button(f"💰 {venue_name} 전체 {venue_cnt}명 일괄 입금완료",
                         key=f"ceo_bulk_pay_{venue_name}", type="primary"):
                _now = datetime.now().strftime('%Y-%m-%d')
                updates = []
                for _, row in venue_df.iterrows():
                    aid = str(row.get(col_assign_id, '')).strip() if col_assign_id and col_assign_id in venue_df.columns else ''
                    status = str(row.get('_상태', ''))
                    if aid and status == '대기':
                        updates.append({'배정ID': aid, '지급상태': '완료', '지급일': _now})
                if updates:
                    result = db.batch_update_payment_status(updates)
                    db.invalidate_payment_cache()
                    db.invalidate_dispatch_only()
                    st.success(f"✅ {result.get('success', 0)}명 입금완료 처리됨!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("⚠️ 일괄 처리 가능한 건이 없습니다. (지급기록 저장이 필요할 수 있습니다)")

        # 개별 카드
        for row_idx, row in venue_df.iterrows():
            name = str(row.get(col_name, '')) if col_name else ''
            amt = int(row.get('_지급액', 0))
            status = str(row.get('_상태', ''))
            aid = str(row.get(col_assign_id, '')).strip() if col_assign_id and col_assign_id in venue_df.columns else ''
            date_val = str(row.get(col_date, '')) if col_date and col_date in venue_df.columns else ''

            # 은행/계좌 정보
            bank = str(row.get(col_bank, '')).strip() if col_bank and col_bank in venue_df.columns else ''
            acct = str(row.get(col_acct, '')).strip() if col_acct and col_acct in venue_df.columns else ''
            bank_display = f"🏦 {bank} {acct}" if bank and bank not in ('nan', 'None', '') else "❗ 계좌 미등록"

            status_badge = "⏳ 대기" if status == '대기' else "📝 미저장"

            col_l, col_r = st.columns([4, 1])
            with col_l:
                date_info = f' · 📅 {date_val}' if date_val and date_val not in ('nan', 'None', '') else ''
                pay_card_html = (
                    f'<div class="ceo-card">'
                    f'<div class="card-title">👤 {name} '
                    f'<span style="font-size:13px;color:#6b7280;">({status_badge})</span></div>'
                    f'<div class="card-detail">'
                    f'{bank_display}<br/>'
                    f'💰 지급액: <b style="color:#DC2626;font-size:16px;">₩{amt:,}</b>'
                    f'{date_info}'
                    f'</div></div>'
                )
                st.markdown(pay_card_html, unsafe_allow_html=True)

            with col_r:
                st.markdown("<div style='padding-top:12px;'></div>", unsafe_allow_html=True)
                if status == '대기' and aid:
                    if st.button("💰 입금완료", key=f"ceo_pay_{row_idx}", use_container_width=True, type="primary"):
                        _now = datetime.now().strftime('%Y-%m-%d')
                        db.update_payment_status(aid, '완료', _now)
                        db.invalidate_payment_cache()
                        db.invalidate_dispatch_only()
                        st.success(f"✅ {name} 입금완료!")
                        time.sleep(1)
                        st.rerun()
                elif status == '미저장':
                    st.caption("📝 정산 페이지에서\n지급기록 먼저 저장")

        st.markdown("---")

    # 현장별 요약
    if col_venue and col_venue in unpaid_ext.columns:
        with st.expander("📊 현장별 미지급 요약", expanded=False):
            summary = unpaid_ext.groupby(unpaid_ext[col_venue].astype(str).str.strip()).agg(
                인원=('_지급액', 'count'),
                미지급합계=('_지급액', 'sum'),
            ).reset_index()
            summary.columns = ['현장명', '인원', '미지급합계']
            summary = summary.sort_values('미지급합계', ascending=False).reset_index(drop=True)
            st.dataframe(summary, use_container_width=True, hide_index=True,
                         column_config={"미지급합계": st.column_config.NumberColumn("💰 미지급합계", format="%d원")})


def _show_done_summary(staff_done, staff_total):
    """전원 처리 완료 시 요약"""
    st.markdown(f"""
    <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:12px;padding:20px;text-align:center;margin-top:10px;">
        <div style="font-size:40px;">✅</div>
        <div style="font-size:18px;font-weight:700;color:#047857;margin:8px 0;">전원 처리 완료</div>
        <div style="font-size:13px;color:#059669;">{staff_done}/{staff_total}명 지급/확인 완료</div>
    </div>
    """, unsafe_allow_html=True)
