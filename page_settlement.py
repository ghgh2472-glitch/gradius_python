# page_settlement.py
import streamlit as st
import pandas as pd
import data_loader as db
import status_config as sc
from utils_settlement import SettlementBrain
import time
from datetime import datetime
from PIL import Image

# ... (스타일링 함수 기존 동일) ...
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 95% !important; padding-top: 1rem; }
        .metric-card { background-color: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .metric-label { font-size: 14px; color: #6b7280; font-weight: 600; margin-bottom: 5px; }
        .metric-val { font-size: 24px; font-weight: 800; color: #111827; }
        .profit-val { color: #16a34a; }
        .cost-val { color: #dc2626; }
    </style>
    """, unsafe_allow_html=True)

def show(data):
    apply_styles()
    st.title("💰 정산 및 급여 관리 (Settlement)")

    # 탭 생성: 전체 현황 vs 개별 정산 vs 세금계산서
    tab_overview, tab_detail, tab_tax = st.tabs([
        "📊 전체 정산 현황", 
        "🔍 계약별 상세 정산",
        "📄 세금계산서 관리"
    ])
    
    with tab_overview:
        show_settlement_overview()
    
    with tab_detail:
        show_settlement_detail(data)
    
    with tab_tax:
        show_tax_invoice_management()


def show_settlement_overview():
    """전체 정산 현황"""
    st.markdown('<div class="section-title">📊 전체 정산 현황</div>', unsafe_allow_html=True)
    
    try:
        dispatch_data = db.get_dispatch()
        settlement_df = dispatch_data.get('settlement', pd.DataFrame())
    except Exception as e:
        st.error(f"정산 데이터 로드 실패: {e}")
        return
    
    if settlement_df.empty:
        st.warning("⚠️ 정산 데이터가 없습니다.")
        return
    
    # 데이터 정리
    settlement_df = settlement_df.fillna('').copy()
    
    # 통계 계산
    has_supply = '공급가액' in settlement_df.columns
    has_tax = '부가세' in settlement_df.columns
    has_paid = '받은금액' in settlement_df.columns
    has_balance = '잔액' in settlement_df.columns
    
    if has_supply:
        total_supply = pd.to_numeric(settlement_df['공급가액'], errors='coerce').sum()
    else:
        total_supply = 0
        
    if has_tax:
        total_tax = pd.to_numeric(settlement_df['부가세'], errors='coerce').sum()
    else:
        total_tax = 0
        
    total_invoice = total_supply + total_tax
    
    if has_paid:
        total_paid = pd.to_numeric(settlement_df['받은금액'], errors='coerce').sum()
    else:
        total_paid = 0
        
    if has_balance:
        total_balance = pd.to_numeric(settlement_df['잔액'], errors='coerce').sum()
    else:
        total_balance = total_invoice - total_paid
    
    # 통계 표시
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📌 총 청구액", f"₩{int(total_invoice):,}")
    with col2:
        st.metric("💵 받은 금액", f"₩{int(total_paid):,}")
    with col3:
        st.metric("📊 미수금액", f"₩{int(total_balance):,}")
    with col4:
        if total_invoice > 0:
            collection_rate = (total_paid / total_invoice) * 100
        else:
            collection_rate = 0
        st.metric("📈 수금률", f"{collection_rate:.1f}%")
    
    # 입금 기록 입력 섹션
    st.markdown("### ✍️ 입금 기록 입력")
    st.info("💡 행사를 선택하고 입금받은 금액을 입력하면 자동으로 계산됩니다.")
    
    col_input1, col_input2, col_input3 = st.columns([2, 1, 1])
    
    with col_input1:
        # 문의ID와 함께 업체/행사명 표시
        settlement_df['label'] = settlement_df.get('문의ID', '') + ' - ' + settlement_df.get('업체', '') + ' (' + settlement_df.get('현장명', '') + ')'
        selected_label = st.selectbox(
            "행사 선택",
            settlement_df['label'].unique(),
            key="settlement_payment_select"
        )
        selected_row = settlement_df[settlement_df['label'] == selected_label].iloc[0]
    
    with col_input2:
        # 현재 청구금액
        invoice_amount = pd.to_numeric(selected_row.get('공급가액', 0), errors='coerce')
        invoice_amount = 0 if pd.isna(invoice_amount) else invoice_amount
        invoice_tax = pd.to_numeric(selected_row.get('부가세', 0), errors='coerce')
        invoice_tax = 0 if pd.isna(invoice_tax) else invoice_tax
        total_invoice_amt = invoice_amount + invoice_tax
        st.metric("총청구액", f"₩{int(total_invoice_amt):,}")
    
    with col_input3:
        # 현재 받은금액
        current_paid = pd.to_numeric(selected_row.get('받은금액', 0), errors='coerce')
        current_paid = 0 if pd.isna(current_paid) else current_paid
        st.metric("현재받음", f"₩{int(current_paid):,}")
    
    # 50% 계약금 / 잔액 빠른 입력 버튼
    remaining_for_btns = total_invoice_amt - current_paid
    qc1, qc2, qc3 = st.columns(3)
    with qc1:
        if st.button(f"💰 50% 계약금 (₩{int(total_invoice_amt * 0.5):,})", key="fill_50", use_container_width=True):
            st.session_state['_payment_fill'] = int(total_invoice_amt * 0.5)
            st.rerun()
    with qc2:
        if st.button(f"💰 잔금 (₩{int(max(0, remaining_for_btns)):,})", key="fill_remain", use_container_width=True):
            st.session_state['_payment_fill'] = int(max(0, remaining_for_btns))
            st.rerun()
    with qc3:
        if st.button(f"💰 전액 (₩{int(total_invoice_amt):,})", key="fill_full", use_container_width=True):
            st.session_state['_payment_fill'] = int(total_invoice_amt)
            st.rerun()

    # 입금금액 입력 (버튼으로 채운 값 적용)
    if '_payment_fill' in st.session_state:
        st.session_state['payment_input_amt'] = st.session_state.pop('_payment_fill')

    col_amt1, col_amt2, col_amt3 = st.columns([2, 1, 1])
    
    with col_amt1:
        new_paid_amount = st.number_input(
            "입금 금액 (이번 입금분)",
            min_value=0,
            step=10000,
            key="payment_input_amt"
        )
    
    with col_amt2:
        st.metric("누적금액", f"₩{int(current_paid + new_paid_amount):,}")
    
    with col_amt3:
        remaining = total_invoice_amt - (current_paid + new_paid_amount)
        st.metric("남은액", f"₩{int(max(0, remaining)):,}")
    
    # 저장 버튼
    col_btn1, col_btn2 = st.columns([1, 3])
    
    with col_btn1:
        if st.button("💾 입금 저장", use_container_width=True, key="save_payment_btn"):
            if new_paid_amount > 0:
                total_new_paid = current_paid + new_paid_amount
                save_payment_record(
                    selected_row['문의ID'],
                    total_new_paid,
                    total_invoice_amt
                )
                st.success(f"✅ 입금이 저장되었습니다!\n- 합계: ₩{int(total_new_paid):,}")
                st.balloons()
                # 캐시만 무효화 (rerun 제거 — 데이터 증발 방지)
                db.invalidate_data()
            else:
                st.error("❌ 입금 금액을 입력해주세요.")
    
    # 입금완료 / 미수금 / 전체 서브탭
    st.markdown("### 📋 전체 계약 정산 현황")
    
    display_cols = ['문의ID', '업체', '현장명', '공급가액', '부가세', '받은금액', '잔액', '진행상황']
    available_cols = [c for c in display_cols if c in settlement_df.columns]
    
    if available_cols:
        full_edit_df = settlement_df[available_cols].copy()
        for nc in ['공급가액', '부가세', '받은금액', '잔액']:
            if nc in full_edit_df.columns:
                full_edit_df[nc] = pd.to_numeric(full_edit_df[nc], errors='coerce').fillna(0).astype(int)
        
        # 잔액이 없으면 자동 계산
        if '잔액' in full_edit_df.columns and '공급가액' in full_edit_df.columns and '부가세' in full_edit_df.columns and '받은금액' in full_edit_df.columns:
            mask_no_bal = full_edit_df['잔액'] == 0
            full_edit_df.loc[mask_no_bal, '잔액'] = (full_edit_df.loc[mask_no_bal, '공급가액'] + full_edit_df.loc[mask_no_bal, '부가세'] - full_edit_df.loc[mask_no_bal, '받은금액']).clip(lower=0)
        
        # 서브탭: 전체 / 입금완료 / 미수금(부분입금+미입금)
        sub_all, sub_paid, sub_unpaid = st.tabs(["📋 전체", "✅ 입금완료", "🚨 미수금 업체"])
        
        def _render_settlement_table(df_view, key_suffix):
            """정산 테이블 렌더링 (받은금액 수정 시 잔액 자동 계산)"""
            if df_view.empty:
                st.info("해당 조건의 데이터가 없습니다.")
                return
            
            editable_cols = {}
            for c in available_cols:
                if c == '받은금액':
                    editable_cols[c] = st.column_config.NumberColumn(c, min_value=0, step=10000, format="%d")
                elif c == '잔액':
                    editable_cols[c] = st.column_config.NumberColumn(c, min_value=0, format="%d", disabled=True, help="받은금액 수정 시 자동 계산됩니다")
                elif c == '진행상황':
                    editable_cols[c] = st.column_config.SelectboxColumn(c, options=["미입금", "부분입금", "입금완료"])
                else:
                    editable_cols[c] = st.column_config.Column(c, disabled=True)
            
            edited = st.data_editor(
                df_view.reset_index(drop=True),
                column_config=editable_cols,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                key=f"settlement_editor_{key_suffix}"
            )
            
            if st.button("💾 변경사항 저장", key=f"save_manual_edit_{key_suffix}"):
                _save_count = 0
                for idx in range(len(edited)):
                    orig = df_view.reset_index(drop=True).iloc[idx]
                    curr = edited.iloc[idx]
                    
                    # 받은금액이 변경되면 잔액 자동 재계산
                    paid_changed = ('받은금액' in orig.index and int(orig['받은금액']) != int(curr['받은금액']))
                    status_changed = ('진행상황' in orig.index and str(orig['진행상황']) != str(curr['진행상황']))
                    
                    if paid_changed or status_changed:
                        inq_id_edit = str(curr.get('문의ID', '')).strip()
                        if inq_id_edit:
                            _paid_v = int(curr.get('받은금액', 0))
                            # 잔액 자동 계산: 공급가액 + 부가세 - 받은금액
                            _supply = int(curr.get('공급가액', 0))
                            _tax = int(curr.get('부가세', 0))
                            _bal_v = max(0, _supply + _tax - _paid_v)
                            # 진행상황 자동 결정
                            if paid_changed:
                                if _bal_v <= 0:
                                    _status_v = "입금완료"
                                elif _paid_v > 0:
                                    _status_v = "부분입금"
                                else:
                                    _status_v = "미입금"
                            else:
                                _status_v = str(curr.get('진행상황', ''))
                            _direct_save_settlement(inq_id_edit, _paid_v, _bal_v, _status_v)
                            _save_count += 1
                if _save_count > 0:
                    st.success(f"✅ {_save_count}건 저장 완료! (잔액 자동 계산 적용)")
                    db.invalidate_data()
                else:
                    st.info("변경된 데이터가 없습니다.")
        
        with sub_all:
            st.caption(f"💡 받은금액을 수정하면 잔액이 자동으로 재계산됩니다. (총 {len(full_edit_df)}건)")
            _render_settlement_table(full_edit_df, "all")
        
        with sub_paid:
            if '진행상황' in full_edit_df.columns:
                paid_df = full_edit_df[full_edit_df['진행상황'].astype(str).str.contains('완료', na=False)]
            elif '잔액' in full_edit_df.columns:
                paid_df = full_edit_df[full_edit_df['잔액'] <= 0]
            else:
                paid_df = pd.DataFrame()
            st.caption(f"✅ 입금 완료된 업체 ({len(paid_df)}건)")
            if not paid_df.empty:
                st.metric("입금완료 합계", f"₩{int(paid_df['받은금액'].sum()):,}")
            _render_settlement_table(paid_df, "paid")
        
        with sub_unpaid:
            if '진행상황' in full_edit_df.columns:
                unpaid_filter = full_edit_df[~full_edit_df['진행상황'].astype(str).str.contains('완료', na=False)]
            elif '잔액' in full_edit_df.columns:
                unpaid_filter = full_edit_df[full_edit_df['잔액'] > 0]
            else:
                unpaid_filter = full_edit_df
            st.caption(f"🚨 미수금 업체 ({len(unpaid_filter)}건)")
            if not unpaid_filter.empty and '잔액' in unpaid_filter.columns:
                uc1, uc2 = st.columns(2)
                uc1.metric("미수금 합계", f"₩{int(unpaid_filter['잔액'].sum()):,}")
                uc2.metric("부분입금 건수", f"{len(unpaid_filter[unpaid_filter['받은금액'] > 0])}건")
            _render_settlement_table(unpaid_filter, "unpaid")
    else:
        st.warning("⚠️ 표시할 컬럼이 없습니다")


def update_payment_and_profit(inquiry_id, total_payment, supply_amount=None):
    """지급액과 이익을 계약건은청구금액적기 시트에 업데이트
    
    Args:
        inquiry_id: 문의ID
        total_payment: 총 지급액 (인력 급여 합계)
        supply_amount: 공급가액 (None이면 시트에서 읽어옴)
    """
    try:
        client = db.get_connection()
        if not client:
            return False
        
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("계약건은청구금액적기")
        headers = wks.row_values(1)
        all_records = wks.get_all_records()
        
        target_row = None
        current_record = None
        for idx, record in enumerate(all_records, start=2):
            if str(record.get('문의ID', '')).strip() == str(inquiry_id).strip():
                target_row = idx
                current_record = record
                break
        
        if not target_row:
            return False
        
        # 컬럼 인덱스 찾기
        col_map = {}
        for i, h in enumerate(headers, 1):
            h_clean = str(h).strip()
            if h_clean == '지급액':
                col_map['지급액'] = i
            elif h_clean == '이익':
                col_map['이익'] = i
            elif h_clean == '공급가액':
                col_map['공급가액'] = i
        
        # 공급가액이 없으면 현재 레코드에서 읽기
        if supply_amount is None and current_record:
            try:
                supply_amount = int(float(current_record.get('공급가액', 0) or 0))
            except:
                supply_amount = 0
        
        # 지급액 업데이트
        if '지급액' in col_map:
            wks.update_cell(target_row, col_map['지급액'], int(total_payment))
        
        # 이익 자동 계산 (공급가액 - 지급액)
        if '이익' in col_map and supply_amount is not None:
            profit = int(supply_amount) - int(total_payment)
            wks.update_cell(target_row, col_map['이익'], profit)
        
        return True
    except Exception as e:
        print(f"지급액/이익 업데이트 실패: {e}")
        return False


def _direct_save_settlement(inquiry_id, paid, balance, status):
    """받은금액/잔액/입금여부를 직접 저장 (data_editor 연동)"""
    try:
        client = db.get_connection()
        if not client:
            return False
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("계약건은청구금액적기")
        headers = wks.row_values(1)
        all_records = wks.get_all_records()
        target_row = None
        for idx, record in enumerate(all_records, start=2):
            if str(record.get('문의ID', '')).strip() == str(inquiry_id).strip():
                target_row = idx
                break
        if not target_row:
            return False
        col_map = {}
        for i, h in enumerate(headers, 1):
            if '받은금액' in str(h):
                col_map['받은금액'] = i
            elif h == '잔액':
                col_map['잔액'] = i
            elif h == '입금여부':
                col_map['입금여부'] = i
            elif h == '진행상황':
                col_map['진행상황'] = i
        if '받은금액' in col_map:
            wks.update_cell(target_row, col_map['받은금액'], int(paid))
        if '잔액' in col_map:
            wks.update_cell(target_row, col_map['잔액'], int(balance))
        # 입금여부 컬럼 업데이트 (분리된 상태 관리)
        if '입금여부' in col_map and status:
            wks.update_cell(target_row, col_map['입금여부'], status)
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False


def save_payment_record(inquiry_id, total_paid, total_invoice):
    """입금 기록을 Google Sheets에 저장 (입금여부 컬럼 활용)"""
    try:
        # NaN 값 처리
        total_paid = 0 if pd.isna(total_paid) else float(total_paid)
        total_invoice = 0 if pd.isna(total_invoice) else float(total_invoice)
        
        client = db.get_connection()
        if not client:
            st.error("❌ Google Sheets 연결 실패")
            return False
        
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("계약건은청구금액적기")
        
        # 해당 행 찾기
        all_records = wks.get_all_records()
        target_row = None
        for idx, record in enumerate(all_records, start=2):  # 2부터 시작 (헤더는 1)
            if record.get('문의ID') == inquiry_id:
                target_row = idx
                break
        
        if not target_row:
            st.error(f"❌ 문의ID '{inquiry_id}'를 찾을 수 없습니다.")
            return False
        
        # 컬럼 인덱스 매핑
        headers = wks.row_values(1)
        col_map = {}
        for idx, header in enumerate(headers, start=1):
            h = str(header).strip()
            if '받은금액' in h:
                col_map['받은금액'] = idx
            elif h == '잔액':
                col_map['잔액'] = idx
            elif h == '입금여부':
                col_map['입금여부'] = idx
        
        # 받은금액 업데이트
        if '받은금액' in col_map:
            wks.update_cell(target_row, col_map['받은금액'], int(total_paid))
        
        # 잔액 업데이트
        remaining = int(total_invoice - total_paid)
        if '잔액' in col_map:
            wks.update_cell(target_row, col_map['잔액'], remaining)
        
        # 입금여부 컬럼 업데이트 (진행상황 대신)
        if '입금여부' in col_map:
            if remaining <= 0:
                status = "입금완료"
            elif total_paid > 0:
                status = "부분입금"
            else:
                status = "미입금"
            wks.update_cell(target_row, col_map['입금여부'], status)
        
        return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False


def show_settlement_detail(data):
    """계약별 상세 정산"""
    st.markdown('<div class="section-title">🔍 계약별 상세 정산</div>', unsafe_allow_html=True)
    
    df_inq = data.get('inq', pd.DataFrame())
    brain = SettlementBrain(df_inq)

    # 필터링 — 상태 컬럼에서 정산 대상 필터링 (체결 이후 건)
    status_col = '상태' if '상태' in df_inq.columns else '체결' if '체결' in df_inq.columns else None
    if not status_col:
        st.warning("상태 컬럼을 찾을 수 없습니다.")
        return
    mask = df_inq[status_col].astype(str).str.strip().isin(sc.CONFIRMED_STATUSES)
    targets = df_inq[mask]
    # 정렬 컬럼 존재 여부 확인 (문의날짜가 없으면 첫 컬럼으로 정렬)
    sort_col = '문의날짜' if '문의날짜' in targets.columns else '일시' if '일시' in targets.columns else targets.columns[0]
    targets = targets.sort_values(sort_col, ascending=False)

    if targets.empty:
        st.info("📌 정산할 프로젝트가 없습니다. (인력 배정 완료 필요)")
        return

    # 프로젝트 선택
    c_sel, c_blank = st.columns([1.5, 2.5])
    with c_sel:
        targets['label'] = targets['업체명'] + " (" + targets['행사명'] + ")"
        sel_p = st.selectbox("📂 프로젝트 선택", targets['label'].unique())
        row = targets[targets['label'] == sel_p].iloc[0]

    # --------------------------------------------------------------------------
    # 손익 요약 (견적상세 데이터 우선, fallback으로 특이사항 파싱)
    # --------------------------------------------------------------------------
    df_est = data.get('estimate', pd.DataFrame())
    inq_id = str(row.get('문의ID', '')).strip()

    # 견적상세에서 데이터 조회
    est_row = None
    if not df_est.empty and '문의ID' in df_est.columns:
        matches = df_est[df_est['문의ID'].astype(str).str.strip() == inq_id]
        if not matches.empty:
            est_row = matches.iloc[0]

    def _safe_int(v):
        try:
            n = pd.to_numeric(v, errors='coerce')
            return 0 if pd.isna(n) else int(n)
        except:
            return 0

    if est_row is not None:
        summary = {
            '매출': _safe_int(est_row.get('공급가액', 0)),
            '매입': _safe_int(est_row.get('매입원가', 0)),
            '수익': _safe_int(est_row.get('예상수익', 0)),
            '수익률': 0.0,
        }
        if summary['수익'] == 0:
            summary['수익'] = summary['매출'] - summary['매입']
        if summary['매출'] > 0:
            summary['수익률'] = (summary['수익'] / summary['매출'] * 100)
    else:
        summary = brain.get_financial_summary(row)

    st.markdown("##### 📊 손익 요약")
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.markdown(f"""<div class="metric-card"><div class="metric-label">총 매출 (공급가액)</div><div class="metric-val">{summary['매출']:,}</div></div>""", unsafe_allow_html=True)
    with m2: st.markdown(f"""<div class="metric-card"><div class="metric-label">총 인건비 (매입원가)</div><div class="metric-val cost-val">{summary['매입']:,}</div></div>""", unsafe_allow_html=True)
    with m3: st.markdown(f"""<div class="metric-card"><div class="metric-label">순수익</div><div class="metric-val profit-val">+{summary['수익']:,}</div></div>""", unsafe_allow_html=True)
    with m4: st.markdown(f"""<div class="metric-card"><div class="metric-label">수익률</div><div class="metric-val">{summary['수익률']:.1f}%</div></div>""", unsafe_allow_html=True)

    st.divider()

    # --------------------------------------------------------------------------
    # 정산 탭
    # --------------------------------------------------------------------------
    tab_c, tab_s = st.tabs(["🏢 업체 정산", "👷 인력 급여 정산"])

    with tab_c:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("거래명세서 발행")
            # 견적품목 데이터로 세부 항목 조회
            invoice_supply = summary['매출']
            invoice_items = None
            try:
                # 견적품목 시트에서 직접 조회 (data 딕셔너리에 미포함이므로 직접 로드)
                matched_items = db.load_estimate_items(inq_id)
                if not matched_items.empty:
                    invoice_items = matched_items.to_dict('records')
            except Exception:
                pass
            # 견적품목이 없으면 견적상세에서 항목 생성
            if not invoice_items and est_row is not None:
                try:
                    _items = []
                    for _col_prefix in ['직종', '직군']:
                        # 견적상세에 직종1_명칭, 직종1_인원, 직종1_단가 형식 확인
                        for _i in range(1, 6):
                            _name_key = f"{_col_prefix}{_i}_명칭" if f"{_col_prefix}{_i}_명칭" in est_row.index else f"{_col_prefix}{_i}" if f"{_col_prefix}{_i}" in est_row.index else None
                            if _name_key and str(est_row.get(_name_key, '')).strip():
                                _qty = int(float(est_row.get(f"{_col_prefix}{_i}_인원", 1) or 1))
                                _unit = int(float(est_row.get(f"{_col_prefix}{_i}_단가", 0) or 0))
                                _days = int(float(est_row.get(f"{_col_prefix}{_i}_일수", 1) or 1))
                                _item = {
                                    '품목명': str(est_row.get(_name_key, '')),
                                    '수량': _qty,
                                    '단가': _unit,
                                    '일수': _days,
                                    '금액': _qty * _unit * _days
                                }
                                _items.append(_item)
                    if _items:
                        invoice_items = _items
                except Exception:
                    pass
            # 행사일 표시
            event_date = str(row.get('행사시작일', row.get('일시', '-')))
            end_date = str(row.get('행사종료일', ''))
            if end_date and end_date.strip() and end_date != event_date:
                event_date = f"{event_date} ~ {end_date}"
            html = brain.get_invoice_html(row['업체명'], row['행사명'], event_date, invoice_supply, items=invoice_items)
            st.components.v1.html(html, height=550, scrolling=True)
        with c2:
            st.subheader("입금 관리")
            cur_status = str(row.get(status_col, '')).strip()
            st.markdown(f"현재 상태: {sc.get_status_badge_html(cur_status)}", unsafe_allow_html=True)
            
            inq_id_for_update = str(row.get('문의ID', '')).strip()
            if cur_status in ['배정완료', '진행중']:
                if st.button("✅ 현장 완료 처리"):
                    db.update_status(inq_id_for_update, sc.STATUS_FLOW[5])  # '완료'
                    st.success("현장 완료 처리됨!"); db.invalidate_data(); time.sleep(1); st.rerun()
            elif cur_status == '완료':
                st.success("✅ 현장 완료 — 아래 인력 급여 탭에서 지급 후 정산 완료 처리하세요.")

    with tab_s:
        # 공제 방식 선택
        tax_opt_col, _ = st.columns([1, 2])
        with tax_opt_col:
            tax_choice = st.radio(
                "💰 공제 방식 선택",
                ["3.3% 공제 (사업소득세)", "0.9% 공제 (일용직)"],
                key=f"tax_choice_{inq_id}",
                horizontal=True
            )
        sel_tax_rate = 0.033 if "3.3%" in tax_choice else 0.009

        # 배정기록 시트에서 직접 인력 데이터 조회
        inq_id = str(row.get('문의ID', '')).strip()
        assignment_df = pd.DataFrame()
        if inq_id:
            try:
                assignment_df = db.get_assignments_by_inquiry(inq_id)
            except Exception:
                pass

        # STAFF 시트에서 은행/계좌 정보 로드
        df_staff = data.get('staff', pd.DataFrame())
        
        def _get_bank_info(staff_name, staff_df):
            """STAFF 시트에서 이름으로 은행/계좌 검색"""
            if staff_df.empty:
                return None, None
            name_c = None
            for c in ['이름', '인력명', '성명']:
                if c in staff_df.columns:
                    name_c = c
                    break
            if not name_c:
                return None, None
            matched = staff_df[staff_df[name_c].astype(str).str.strip() == str(staff_name).strip()]
            if matched.empty:
                return None, None
            r = matched.iloc[0]
            bank = str(r.get('은행명', r.get('은행', ''))).strip()
            account = str(r.get('계좌번호', r.get('계좌', ''))).strip()
            bank = bank if bank and bank not in ('nan', 'None', '') else None
            account = account if account and account not in ('nan', 'None', '') else None
            return bank, account

        def _save_bank_to_staff(staff_name, bank_name, account_num, staff_df):
            """STAFF 시트에 은행/계좌 정보를 직접 업데이트"""
            try:
                client = db.get_connection()
                if not client:
                    return False
                sh = client.open_by_key(db.SHEET_ID)
                wks = sh.worksheet("STAFF")
                headers = [str(h).strip() for h in wks.row_values(1)]
                
                # 이름 컬럼 찾기
                name_col_idx = None
                for nc in ['이름', '인력명', '성명']:
                    if nc in headers:
                        name_col_idx = headers.index(nc) + 1
                        break
                if not name_col_idx:
                    return False
                
                # 은행/계좌 컬럼 찾기
                bank_col_idx = None
                acct_col_idx = None
                for i, h in enumerate(headers, 1):
                    if h in ('은행명', '은행') and not bank_col_idx:
                        bank_col_idx = i
                    if h in ('계좌번호', '계좌') and not acct_col_idx:
                        acct_col_idx = i
                
                if not bank_col_idx or not acct_col_idx:
                    return False
                
                # 이름으로 행 찾기
                all_vals = wks.get_all_values()
                target_row = None
                for ri in range(1, len(all_vals)):
                    if str(all_vals[ri][name_col_idx - 1]).strip() == str(staff_name).strip():
                        target_row = ri + 1  # 1-based
                        break
                
                if not target_row:
                    return False
                
                from gspread.cell import Cell
                cells = [
                    Cell(row=target_row, col=bank_col_idx, value=str(bank_name).strip()),
                    Cell(row=target_row, col=acct_col_idx, value=str(account_num).strip()),
                ]
                wks.update_cells(cells, value_input_option='RAW')
                return True
            except Exception as e:
                print(f"계좌정보 저장 실패: {e}")
                return False
        
        if not assignment_df.empty:
            name_col = '이름' if '이름' in assignment_df.columns else '인력명' if '인력명' in assignment_df.columns else None
            role_col = '역할' if '역할' in assignment_df.columns else '직무' if '직무' in assignment_df.columns else None
            rate_col = '단가' if '단가' in assignment_df.columns else '지급단가' if '지급단가' in assignment_df.columns else None
            days_col = '일수' if '일수' in assignment_df.columns else '근무일수' if '근무일수' in assignment_df.columns else None
            total_col = '총지급액' if '총지급액' in assignment_df.columns else None
            assign_type_col = '구분' if '구분' in assignment_df.columns else None
            
            # 본사인원 필터
            hq_names = [s['이름'] for s in db.HQ_STAFF] if hasattr(db, 'HQ_STAFF') else []
            
            st.subheader(f"👷 인력 급여 편집 ({len(assignment_df)}명)")
            st.caption("💡 단가·일수·식비·교통비를 직접 수정할 수 있습니다. **출근 체크 해제 = 노쇼(지급 0원)**")
            
            # ── 편집용 DataFrame 구축 ──
            edit_rows = []
            for i, arow in assignment_df.iterrows():
                a_name = str(arow.get(name_col, 'N/A')) if name_col else 'N/A'
                a_role = str(arow.get(role_col, '')) if role_col else ''
                a_rate = int(float(arow.get(rate_col, 0) or 0)) if rate_col else 0
                a_days = int(float(arow.get(days_col, 1) or 1)) if days_col else 1
                a_type = str(arow.get(assign_type_col, '')) if assign_type_col else ''
                is_hq = a_name in hq_names
                
                bank, account = _get_bank_info(a_name, df_staff)
                
                edit_rows.append({
                    '출근': True,
                    '이름': a_name,
                    '직무': a_role,
                    '구분': '본사' if is_hq else a_type,
                    '단가': a_rate,
                    '일수': a_days,
                    '식비': 0,
                    '교통비': 0,
                    '은행': bank or '',
                    '계좌번호': account or '',
                })
            
            initial_df = pd.DataFrame(edit_rows)
            
            # ── data_editor ──
            edited_df = st.data_editor(
                initial_df,
                column_config={
                    '출근': st.column_config.CheckboxColumn('출근', default=True, help="노쇼 시 체크 해제 → 지급 0원"),
                    '이름': st.column_config.TextColumn('이름', disabled=True),
                    '직무': st.column_config.TextColumn('직무', disabled=True),
                    '구분': st.column_config.TextColumn('구분', disabled=True),
                    '단가': st.column_config.NumberColumn('단가', min_value=0, step=10000, format="%d"),
                    '일수': st.column_config.NumberColumn('일수', min_value=0, step=1),
                    '식비': st.column_config.NumberColumn('식비', min_value=0, step=5000, format="%d"),
                    '교통비': st.column_config.NumberColumn('교통비', min_value=0, step=5000, format="%d"),
                    '은행': st.column_config.TextColumn('은행', help="미등록 시 직접 입력"),
                    '계좌번호': st.column_config.TextColumn('계좌번호', help="미등록 시 직접 입력"),
                },
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                key=f"salary_editor_{inq_id}"
            )
            
            # ── 계산 결과 ──
            result_rows = []
            for i, erow in edited_df.iterrows():
                e_rate = int(erow.get('단가', 0) or 0)
                e_days = int(erow.get('일수', 0) or 0)
                e_meal = int(erow.get('식비', 0) or 0)
                e_trans = int(erow.get('교통비', 0) or 0)
                
                if erow['출근']:
                    gross = e_rate * e_days + e_meal + e_trans
                else:
                    gross = 0
                
                is_hq = erow.get('구분', '') == '본사'
                tax_amt = int(gross * sel_tax_rate) if not is_hq else 0
                net = gross - tax_amt
                
                result_rows.append({
                    '이름': erow['이름'],
                    '상태': '✅ 출근' if erow['출근'] else '❌ 노쇼',
                    '구분': erow.get('구분', ''),
                    '기본급': e_rate * e_days if erow['출근'] else 0,
                    '식비': e_meal if erow['출근'] else 0,
                    '교통비': e_trans if erow['출근'] else 0,
                    '총액': gross,
                    '공제': tax_amt,
                    '실수령액': net,
                    '_gross': gross,
                    '_is_hq': is_hq,
                })
            
            # ── 💰 지급 요약 메트릭 ──
            st.markdown("##### 💰 지급 요약")
            total_gross = sum(r['_gross'] for r in result_rows)
            total_gross_excl_hq = sum(r['_gross'] for r in result_rows if not r['_is_hq'])
            total_tax = int(total_gross_excl_hq * sel_tax_rate)
            total_net = total_gross - total_tax
            attended = sum(1 for r in result_rows if '출근' in r['상태'])
            noshow = sum(1 for r in result_rows if '노쇼' in r['상태'])
            
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("출근", f"{attended}명", delta=f"-{noshow}명 노쇼" if noshow > 0 else None, delta_color="inverse" if noshow > 0 else "off")
            mc2.metric("총 지급액", f"₩{total_gross:,}")
            mc3.metric("공제 합계", f"-₩{total_tax:,}")
            mc4.metric("실수령 합계", f"₩{total_net:,}")
            
            # ── 결과 테이블 ──
            display_result = pd.DataFrame(result_rows).drop(columns=['_gross', '_is_hq'])
            # 금액 포맷팅
            for fc in ['기본급', '식비', '교통비', '총액', '공제', '실수령액']:
                if fc in display_result.columns:
                    display_result[fc] = display_result[fc].apply(lambda x: f"{int(x):,}")
            st.dataframe(display_result, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # ── 저장 버튼들 ──
            btn_c1, btn_c2 = st.columns(2)
            
            with btn_c1:
                if st.button("🏦 계좌정보 → STAFF 시트 저장", key=f"save_bank_{inq_id}", use_container_width=True):
                    save_count = 0
                    for i, erow in edited_df.iterrows():
                        bank_val = str(erow.get('은행', '')).strip()
                        acct_val = str(erow.get('계좌번호', '')).strip()
                        if bank_val and acct_val:
                            orig_bank, orig_acct = _get_bank_info(erow['이름'], df_staff)
                            if bank_val != (orig_bank or '') or acct_val != (orig_acct or ''):
                                if _save_bank_to_staff(erow['이름'], bank_val, acct_val, df_staff):
                                    save_count += 1
                    if save_count > 0:
                        st.success(f"✅ {save_count}명의 계좌정보가 STAFF 시트에 저장되었습니다!")
                        db.invalidate_data()
                    else:
                        st.info("변경된 계좌정보가 없습니다.")
            
            with btn_c2:
                if st.button("💾 지급기록 일괄 저장", key=f"save_pay_all_{inq_id}", type="primary", use_container_width=True):
                    save_count = 0
                    for i, erow in edited_df.iterrows():
                        is_hq = erow.get('구분', '') == '본사'
                        if not erow['출근'] or is_hq:
                            continue  # 노쇼 또는 본사인원은 스킵
                        e_rate = int(erow.get('단가', 0) or 0)
                        e_days = int(erow.get('일수', 0) or 0)
                        e_meal = int(erow.get('식비', 0) or 0)
                        e_trans = int(erow.get('교통비', 0) or 0)
                        gross = e_rate * e_days + e_meal + e_trans
                        tax_amt = int(gross * sel_tax_rate)
                        a_assign_id = str(assignment_df.iloc[i].get('배정ID', '')) if i < len(assignment_df) else ''
                        payment_dict = {
                            '배정ID': a_assign_id,
                            '인력명': erow['이름'],
                            '현장명': row['행사명'],
                            '파견기간': str(row.get('행사시작일', '')),
                            '파견일수': e_days,
                            '기본급': e_rate * e_days,
                            '야근비': 0,
                            '식사비': e_meal,
                            '교통비': e_trans,
                            '보너스': 0,
                            '소계': gross,
                            '세금공제': tax_amt,
                            '최종지급액': gross - tax_amt,
                            '지급상태': '완료',
                            '지급일': datetime.now().strftime('%Y-%m-%d'),
                            '지급담당자': '',
                            '비고': f"정산페이지 ({sel_tax_rate*100:.1f}% 공제)",
                        }
                        if db.save_payment_record(payment_dict):
                            save_count += 1
                    if save_count > 0:
                        st.success(f"✅ {save_count}명의 지급기록이 저장되었습니다!")
                        db.invalidate_data()
                    else:
                        st.warning("저장할 지급기록이 없습니다.")
            
            st.divider()
            
            # ── 개별 급여명세서 미리보기 ──
            st.subheader("📄 개별 급여명세서")
            for i, erow in edited_df.iterrows():
                e_name = erow['이름']
                e_role = erow.get('직무', '')
                e_rate = int(erow.get('단가', 0) or 0)
                e_days = int(erow.get('일수', 0) or 0)
                e_meal = int(erow.get('식비', 0) or 0)
                e_trans = int(erow.get('교통비', 0) or 0)
                is_hq = erow.get('구분', '') == '본사'
                is_attend = bool(erow.get('출근', True))
                
                if is_attend:
                    gross = e_rate * e_days + e_meal + e_trans
                else:
                    gross = 0
                
                badge = "🏢" if is_hq else ("👤" if is_attend else "🚫")
                status_txt = " [본사]" if is_hq else ("" if is_attend else " [노쇼]")
                bank_val = str(erow.get('은행', '')).strip()
                acct_val = str(erow.get('계좌번호', '')).strip()
                bank_info = f"💳 {bank_val} {acct_val}" if bank_val and acct_val else "❗ 계좌정보 미등록"
                
                with st.expander(f"{badge} {e_name}{status_txt} ({e_role}) — {gross:,}원 | {bank_info}"):
                    if not is_attend:
                        st.warning("❌ 노쇼 — 지급 대상 아님")
                        continue
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        html_p = brain.get_payslip_html(e_name, row['행사명'], e_rate, e_days, gross, tax_rate=sel_tax_rate, meal=e_meal, transport=e_trans)
                        st.components.v1.html(html_p, height=400)
                    with c2:
                        if bank_val and acct_val:
                            st.info(f"🏦 {bank_val}\n\n📋 {acct_val}")
                        else:
                            st.warning("계좌정보 미등록 — 위 테이블에서 입력 후 '계좌정보 → STAFF 시트 저장' 버튼을 눌러주세요")
                        if is_hq:
                            st.caption("ℹ️ 본사 인원 — 별도 정산")
        else:
            # 배정기록 없으면 기존 특이사항 텍스트 파싱 fallback
            note_text = str(row.get('특이사항', ''))
            staff_data = brain.parse_dispatch_data(note_text)
            
            if not staff_data:
                st.warning("⚠️ 배정된 인원 데이터를 찾을 수 없습니다.")
                st.caption("인력배정 → 배정 확정을 먼저 진행해주세요.")
            else:
                st.subheader(f"지급 대상자 ({len(staff_data)}명) — 특이사항 파싱")
                for i, s in enumerate(staff_data):
                    with st.expander(f"{s['이름']} ({s['지급단가']:,}원 x {s['일수']}일 = {s['총지급액']:,}원)"):
                        c1, c2 = st.columns([2, 1])
                        with c1:
                            html_p = brain.get_payslip_html(s['이름'], row['행사명'], s['지급단가'], s['일수'], s['총지급액'], tax_rate=sel_tax_rate)
                            st.components.v1.html(html_p, height=400)
                        with c2:
                            if st.checkbox("이체 완료", key=f"pay_{i}"):
                                st.success("지급 완료됨")

        # 정산 완료 버튼
        if cur_status == '완료':
            st.divider()
            
            # 배정기록에서 총 지급액 계산
            total_payment = 0
            if not assignment_df.empty:
                total_col = '총지급액' if '총지급액' in assignment_df.columns else None
                if total_col:
                    total_payment = int(assignment_df[total_col].astype(float).sum())
            
            st.info(f"💰 총 지급액: **{total_payment:,}원** | 예상 이익: **{summary['매출'] - total_payment:,}원**")
            
            if st.button("🏁 최종 정산 완료 (프로젝트 종료)", type="primary"):
                # 지급액 / 이익 업데이트
                update_payment_and_profit(inq_id_for_update, total_payment, summary['매출'])
                # 상태 업데이트
                db.update_status(inq_id_for_update, sc.STATUS_FLOW[6])  # '정산완료'
                db.invalidate_data()
                st.balloons(); st.success("모든 정산이 완료되었습니다!"); st.rerun()


def show_tax_invoice_management():
    """세금계산서 발행 현황 관리"""
    st.markdown('<div class="section-title">📄 세금계산서 발행 관리</div>', unsafe_allow_html=True)
    st.caption("거래처별 세금계산서 발행 현황을 관리하고, 사업자등록증에서 정보를 자동 추출하세요.")
    
    try:
        dispatch_data = db.get_dispatch()
        settlement_df = dispatch_data.get('settlement', pd.DataFrame())
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return
    
    if settlement_df.empty:
        st.warning("⚠️ 정산 데이터가 없습니다.")
        return
    
    settlement_df = settlement_df.fillna('').copy()
    # 헤더 줄바꿈 정리
    settlement_df.columns = [str(c).replace('\n', ' ').strip() for c in settlement_df.columns]
    
    # ── 컬럼 자동 매핑 ──
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
    
    # 1️⃣ 발행 현황 요약
    st.markdown("### 📊 발행 현황 요약")
    
    if col_tax_issued and col_company:
        issued = settlement_df[settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)]
        not_issued = settlement_df[~settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)]
        total_count = len(settlement_df)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ 발행 완료", len(issued))
        c2.metric("⏳ 미발행", len(not_issued))
        rate = int((len(issued) / total_count * 100) if total_count > 0 else 0)
        c3.metric("📈 발행률", f"{rate}%")
    
    st.markdown("---")
    
    # 2️⃣ 업체별 세금계산서 발행 현황 테이블
    st.markdown("### 📋 업체별 발행 현황")
    
    if col_company:
        display_cols = [c for c in [col_inq_id, col_company, '현장명', '청구금액', '공급가액', '부가세',
                                     col_tax_issued, '사업자번호', '대표자', '이메일', '내용(품목)', '발행요청사항']
                        if c and c in settlement_df.columns]
        if display_cols:
            st.dataframe(settlement_df[display_cols], use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # 3️⃣ 미발행 업체
    st.markdown("### 🚨 미발행 업체 (즉시 처리 필요)")
    
    if col_tax_issued and col_company:
        not_issued_df = settlement_df[
            ~settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)
        ].copy()
        
        if not not_issued_df.empty:
            for idx, row in not_issued_df.iterrows():
                company = row.get(col_company, '미등록')
                biz_num = str(row.get('사업자번호', '')).strip()
                email_val = str(row.get('이메일', '')).strip()
                amount = str(row.get('청구금액', '')).strip()
                
                col_left, col_right = st.columns([3, 1])
                with col_left:
                    info_parts = [f"<b>{company}</b>"]
                    if biz_num:
                        info_parts.append(f"사업자: {biz_num}")
                    if email_val:
                        info_parts.append(f"이메일: {email_val}")
                    if amount:
                        info_parts.append(f"청구금액: {amount}")
                    
                    st.markdown(f"""
                    <div style="background-color:#FEF2F2;border-left:4px solid #DC2626;
                                padding:12px;border-radius:4px;margin-bottom:8px;">
                        {'<br/>'.join(info_parts)}
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_right:
                    if st.button("✅ 발행 완료", key=f"tax_done_{idx}"):
                        try:
                            _client = db.get_connection()
                            if _client:
                                _sh = _client.open_by_key(db.SHEET_ID)
                                _wks = _sh.worksheet("계약건은청구금액적기")
                                _headers = [str(h).replace('\n', ' ').strip() for h in _wks.row_values(1)]
                                if col_tax_issued in _headers:
                                    _tax_col_idx = _headers.index(col_tax_issued) + 1
                                    _all_records = _wks.get_all_values()
                                    # 문의ID로 행 찾기
                                    _inq_id = str(row.get('문의ID', '')).strip()
                                    for _r_idx in range(1, len(_all_records)):
                                        if str(_all_records[_r_idx][0]).strip() == _inq_id:
                                            _wks.update_cell(_r_idx + 1, _tax_col_idx, "발행완료")
                                            break
                                db.invalidate_data()
                                st.success(f"✅ {company} 세금계산서 발행 완료 처리됨")
                                time.sleep(1)
                                st.rerun()
                        except Exception as _e:
                            st.error(f"저장 실패: {_e}")
        else:
            st.success("🎉 모든 업체의 세금계산서가 발행되었습니다!")
    
    st.markdown("---")
    
    # 4️⃣ 세금계산서 정보 등록/수정
    st.markdown("### 📝 세금계산서 발행 정보 등록")
    st.info("💡 업체를 선택하여 사업자등록번호, 발행 이메일, 품목 등의 정보를 등록/수정합니다.")
    
    if col_company:
        company_list = ['-- 업체 선택 --'] + settlement_df[col_company].unique().tolist()
        selected_company = st.selectbox(
            "정보를 등록할 업체 선택",
            company_list,
            help="정보를 등록/수정할 업체를 먼저 선택하세요"
        )
        
        if selected_company != '-- 업체 선택 --':
            selected_row = settlement_df[settlement_df[col_company] == selected_company].iloc[0]
            _inq_id = str(selected_row.get('문의ID', '')).strip()
            
            # ── 사업자등록증 이미지 업로드 (상단에 배치) ──
            uploaded_file = st.file_uploader(
                f"📸 {selected_company}의 사업자등록증 이미지 업로드",
                type=["jpg", "jpeg", "png", "gif"],
                help="이미지를 보면서 좌측 폼에 직접 입력합니다",
                key=f"file_{selected_company}"
            )
            
            # ── 좌우 2컬럼 레이아웃 ──
            col_form, col_image = st.columns([1.2, 1])
            
            # ────────────────────────────────────
            # 좌측: 세금계산서 발행 정보 입력 폼
            # ────────────────────────────────────
            with col_form:
                st.markdown("#### 📋 세금계산서 발행 정보")
                
                def _pick_val(sheet_key):
                    """시트 저장값이 있으면 반환, 없으면 빈값"""
                    saved = str(selected_row.get(sheet_key, '')).strip()
                    if saved and saved not in ('nan', 'None', '-', ''):
                        return saved
                    return ''
                
                with st.form(key=f"tax_edit_{selected_company}"):
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        edit_biz_num = st.text_input("사업자등록번호", 
                            value=_pick_val('사업자번호'),
                            placeholder="000-00-00000")
                        edit_ceo = st.text_input("대표자명", 
                            value=_pick_val('대표자'),
                            placeholder="홍길동")
                        edit_company_name = st.text_input("법인명", 
                            value=_pick_val('법인명'),
                            placeholder="(주)그래디우스")
                    with fc2:
                        edit_email = st.text_input("세금계산서 발행 이메일", 
                            value=_pick_val('이메일'),
                            placeholder="tax@company.com")
                        edit_contact = st.text_input("연락처", 
                            value=_pick_val('연락처'),
                            placeholder="010-0000-0000")
                        edit_content = st.text_input("내용(품목)", 
                            value=_pick_val('내용(품목)'),
                            placeholder="인력파견 등")
                    
                    edit_note = st.text_area("발행관련 요청사항", 
                        value=_pick_val('발행요청사항'),
                        placeholder="계산서 발행일 지정, 분할 발행 등", height=80)
                    
                    fc_btn1, fc_btn2 = st.columns(2)
                    with fc_btn1:
                        submit_edit = st.form_submit_button("💾 정보 저장", type="primary", use_container_width=True)
                    with fc_btn2:
                        st.form_submit_button("❌ 취소", use_container_width=True)
                    
                    if submit_edit:
                        try:
                            _client = db.get_connection()
                            if _client:
                                _sh = _client.open_by_key(db.SHEET_ID)
                                _wks = _sh.worksheet("계약건은청구금액적기")
                                _headers = [str(h).replace('\n', ' ').strip() for h in _wks.row_values(1)]
                                
                                _all_vals = _wks.get_all_values()
                                _target_row = None
                                for _ri in range(1, len(_all_vals)):
                                    if str(_all_vals[_ri][0]).strip() == _inq_id:
                                        _target_row = _ri + 1
                                        break
                                
                                if _target_row:
                                    from gspread.cell import Cell
                                    _cells = []
                                    _update_map = {
                                        '사업자번호': edit_biz_num,
                                        '대표자': edit_ceo,
                                        '법인명': edit_company_name,
                                        '이메일': edit_email,
                                        '연락처': edit_contact,
                                        '내용(품목)': edit_content,
                                        '발행요청사항': edit_note,
                                    }
                                    for _hdr, _val in _update_map.items():
                                        if _hdr in _headers:
                                            _ci = _headers.index(_hdr) + 1
                                            _cells.append(Cell(row=_target_row, col=_ci, value=str(_val).strip()))
                                    
                                    if _cells:
                                        _wks.update_cells(_cells, value_input_option='RAW')
                                        db.invalidate_data()
                                        st.success(f"✅ {selected_company}의 세금계산서 정보가 저장되었습니다!")
                                        st.balloons()
                                        time.sleep(1)
                                        st.rerun()
                                else:
                                    st.error(f"❌ 문의ID '{_inq_id}'에 해당하는 행을 찾을 수 없습니다.")
                        except Exception as _e:
                            st.error(f"❌ 저장 실패: {_e}")
                
                # ── 현재 저장 정보 요약 ──
                with st.expander(f"📌 {selected_company} 현재 저장된 정보", expanded=False):
                    ci1, ci2 = st.columns(2)
                    ci1.markdown(f"**업체명**: {selected_company}")
                    ci1.markdown(f"**사업자번호**: {selected_row.get('사업자번호', '-')}")
                    ci1.markdown(f"**대표자**: {selected_row.get('대표자', '-')}")
                    ci1.markdown(f"**법인명**: {selected_row.get('법인명', '-')}")
                    ci2.markdown(f"**이메일**: {selected_row.get('이메일', '-')}")
                    ci2.markdown(f"**연락처**: {selected_row.get('연락처', '-')}")
                    ci2.markdown(f"**청구금액**: {selected_row.get('청구금액', '-')}")
                    ci2.markdown(f"**내용(품목)**: {selected_row.get('내용(품목)', '-')}")
            
            # ────────────────────────────────────
            # 우측: 사업자등록증 이미지 표시
            # ────────────────────────────────────
            with col_image:
                if uploaded_file is not None:
                    st.markdown("#### 📸 사업자등록증")
                    uploaded_file.seek(0)
                    image = Image.open(uploaded_file)
                    st.image(image, use_container_width=True, caption=f"{selected_company} 사업자등록증")
                    st.caption("💡 이미지를 보면서 좌측 폼에 직접 입력하세요")
                    
                    # 이미지 로컬 저장 버튼
                    if st.button("💾 이미지 저장", key=f"save_img_{selected_company}", use_container_width=True):
                        try:
                            img_url = _save_biz_image(uploaded_file, selected_company, _inq_id)
                            if img_url:
                                # 시트에 URL/경로 저장
                                _client = db.get_connection()
                                if _client:
                                    _sh = _client.open_by_key(db.SHEET_ID)
                                    _wks = _sh.worksheet("계약건은청구금액적기")
                                    _headers = [str(h).replace('\n', ' ').strip() for h in _wks.row_values(1)]
                                    if '사업자등록증URL' in _headers:
                                        _url_ci = _headers.index('사업자등록증URL') + 1
                                        _all_vals = _wks.get_all_values()
                                        for _ri in range(1, len(_all_vals)):
                                            if str(_all_vals[_ri][0]).strip() == _inq_id:
                                                _wks.update_cell(_ri + 1, _url_ci, img_url)
                                                break
                                    db.invalidate_data()
                                st.success("✅ 이미지 저장 완료!")
                            else:
                                st.error("❌ 이미지 저장에 실패했습니다.")
                        except Exception as img_err:
                            st.error(f"❌ 이미지 저장 오류: {img_err}")
                else:
                    st.markdown("#### 📸 사업자등록증")
                    # 기존 저장된 이미지가 있으면 표시 (base64 / 로컬파일 / URL)
                    biz_url = str(selected_row.get('사업자등록증URL', '')).strip()
                    biz_b64 = str(selected_row.get('사업자등록증데이터', '')).strip()
                    if biz_b64 and biz_b64 not in ('nan', 'None', ''):
                        # base64 인코딩된 이미지 (계약에서 업로드)
                        try:
                            import base64 as _b64
                            _img_bytes = _b64.b64decode(biz_b64)
                            st.image(_img_bytes, use_container_width=True, caption="저장된 사업자등록증 (계약 업로드)")
                        except Exception:
                            st.caption("저장된 이미지를 표시할 수 없습니다.")
                    elif biz_url and biz_url not in ('nan', 'None', '', '-'):
                        if biz_url.startswith('http'):
                            st.markdown(f"[🔗 저장된 사업자등록증 보기]({biz_url})")
                        elif os.path.exists(biz_url):
                            try:
                                st.image(biz_url, use_container_width=True, caption="저장된 사업자등록증")
                            except Exception:
                                st.caption(f"📁 저장 경로: {biz_url}")
                        else:
                            st.caption(f"📁 저장 경로: {biz_url}")
                    else:
                        st.markdown("""
                        <div style="border:2px dashed #cbd5e1; border-radius:12px; padding:40px 20px; text-align:center; color:#94a3b8;">
                            <div style="font-size:48px;">📸</div>
                            <div style="margin-top:10px;">사업자등록증 이미지를 업로드하면<br>여기에 표시됩니다</div>
                            <div style="margin-top:8px; font-size:12px;">이미지를 보면서 좌측 폼에 직접 입력할 수 있습니다</div>
                        </div>
                        """, unsafe_allow_html=True)
        
        else:
            st.info("⬆️ 위에서 업체를 선택해주세요")


def _save_biz_image(uploaded_file, company_name, inq_id):
    """사업자등록증 이미지를 로컬에 저장하고 경로 반환
    
    저장 위치: biz_images/ 폴더 (자동 생성)
    파일명: 사업자등록증_업체명_문의ID.png
    
    참고: 서비스 계정은 Google Drive 스토리지 할당량이 없어
    직접 업로드가 불가합니다. 로컬 저장으로 대체합니다.
    """
    try:
        import io
        
        # 저장 폴더 생성
        save_dir = os.path.join(os.path.dirname(__file__) or '.', 'biz_images')
        os.makedirs(save_dir, exist_ok=True)
        
        # 안전한 파일명
        safe_name = company_name.replace('/', '_').replace('\\', '_').replace(' ', '_')
        safe_id = inq_id.replace('/', '_').replace('\\', '_')
        filename = f"사업자등록증_{safe_name}_{safe_id}.png"
        filepath = os.path.join(save_dir, filename)
        
        # 이미지 저장
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        img.save(filepath, format='PNG')
        uploaded_file.seek(0)
        
        print(f"사업자등록증 이미지 저장: {filepath}")
        return filepath
    
    except Exception as e:
        print(f"이미지 저장 실패: {e}")
        return None