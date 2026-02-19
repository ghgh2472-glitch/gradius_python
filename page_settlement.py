# page_settlement.py
import streamlit as st
import pandas as pd
import os
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
        /* radio-as-tabs */
        div[data-testid="stRadio"] > div[role="radiogroup"] {
            gap: 0; display: flex; flex-wrap: wrap;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label {
            background: #f0f2f6; border: 1px solid #d1d5db; padding: 8px 20px;
            cursor: pointer; font-weight: 700; font-size: 14px;
            border-radius: 0; margin: 0 -1px 0 0;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label:first-child { border-radius: 8px 0 0 8px; }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label:last-child { border-radius: 0 8px 8px 0; }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label[data-checked="true"] {
            background: #0f766e; color: white; border-color: #0f766e;
        }
    </style>
    """, unsafe_allow_html=True)

def show(data):
    apply_styles()
    st.title("💰 정산 및 급여 관리 (Settlement)")

    # 탭 생성: 전체 현황 vs 개별 정산 vs 세금계산서
    _stl_tabs = ["📊 전체 정산 현황", "🔍 계약별 상세 정산", "📄 세금계산서 관리"]
    _active = st.radio("settlement", _stl_tabs, key="_settlement_tab", horizontal=True, label_visibility="collapsed")
    st.markdown("---")

    if _active == _stl_tabs[0]:
        show_settlement_overview()
    elif _active == _stl_tabs[1]:
        show_settlement_detail(data)
    elif _active == _stl_tabs[2]:
        show_tax_invoice_management()


def _auto_check_event_completion(settlement_df):
    """파견일자가 지난 '행사준비' 건 → '행사종료'로 자동 전환
    
    Returns:
        int: 자동 전환된 건수
    """
    if '파견일자' not in settlement_df.columns or '진행상황' not in settlement_df.columns:
        return 0
    if '문의ID' not in settlement_df.columns:
        return 0
    
    today = datetime.now().date()
    updated = 0
    
    for _, row in settlement_df.iterrows():
        progress = str(row.get('진행상황', '')).strip()
        if progress != '행사준비':
            continue
        
        date_str = str(row.get('파견일자', '')).strip()
        if not date_str:
            continue
        
        # 파견일자 파싱 (다양한 형식 지원)
        event_date = None
        import re
        # "2026-02-20 ~ 2026-02-22" 같은 범위에선 마지막 날짜 사용
        range_match = re.search(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2})\s*[~\-]\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})', date_str)
        if range_match:
            date_str = range_match.group(2)  # 종료일
        
        for fmt in ('%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d'):
            try:
                event_date = datetime.strptime(date_str.strip(), fmt).date()
                break
            except ValueError:
                continue
        
        if event_date and event_date < today:
            inq_id = str(row.get('문의ID', '')).strip()
            if inq_id and db.update_settlement_progress(inq_id, '행사종료'):
                updated += 1
    
    return updated


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
    
    # ✅ 행사종료 자동 체크 (파견일자 경과 + 진행상황=행사준비 → 행사종료)
    auto_completed = _auto_check_event_completion(settlement_df)
    if auto_completed > 0:
        st.toast(f"📅 {auto_completed}건 행사종료 자동 전환", icon="✅")
        db.invalidate_data()
        st.rerun()
    
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
    
    display_cols = ['문의ID', '업체', '현장명', '청구금액', '공급가액', '부가세', '받은금액', '잔액',
                     '입금여부', '세금계산서 발행여부', '지급액', '이익', '진행상황']
    available_cols = [c for c in display_cols if c in settlement_df.columns]
    
    if available_cols:
        full_edit_df = settlement_df[available_cols].copy()
        for nc in ['청구금액', '공급가액', '부가세', '받은금액', '잔액', '지급액', '이익']:
            if nc in full_edit_df.columns:
                full_edit_df[nc] = pd.to_numeric(full_edit_df[nc], errors='coerce').fillna(0).astype(int)
        
        # 청구금액이 0이면 공급가액+부가세로 채움
        if '청구금액' in full_edit_df.columns and '공급가액' in full_edit_df.columns and '부가세' in full_edit_df.columns:
            mask_no_inv = full_edit_df['청구금액'] == 0
            full_edit_df.loc[mask_no_inv, '청구금액'] = full_edit_df.loc[mask_no_inv, '공급가액'] + full_edit_df.loc[mask_no_inv, '부가세']
        
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
                    editable_cols[c] = st.column_config.NumberColumn("💵받은금액", min_value=0, step=10000, format="%d")
                elif c == '잔액':
                    editable_cols[c] = st.column_config.NumberColumn("잔액", min_value=0, format="%d", disabled=True, help="받은금액 수정 시 자동 계산")
                elif c == '청구금액':
                    editable_cols[c] = st.column_config.NumberColumn("💰청구금액", format="%d", disabled=True)
                elif c == '공급가액':
                    editable_cols[c] = st.column_config.NumberColumn("공급가액", format="%d", disabled=True)
                elif c == '부가세':
                    editable_cols[c] = st.column_config.NumberColumn("부가세", format="%d", disabled=True)
                elif c == '입금여부':
                    editable_cols[c] = st.column_config.SelectboxColumn("🏦입금", options=["", "미입금", "부분입금", "입금완료"], width="small", help="받은금액 수정 시 자동 변경")
                elif c == '세금계산서 발행여부':
                    editable_cols[c] = st.column_config.SelectboxColumn("🧾계산서", options=["", "미발행", "발행요청", "발행완료"], width="small")
                elif c == '지급액':
                    editable_cols[c] = st.column_config.NumberColumn("💸지급액", min_value=0, step=10000, format="%d", help="인력 급여 합계")
                elif c == '이익':
                    editable_cols[c] = st.column_config.NumberColumn("📈이익", format="%d", disabled=True, help="공급가액 - 지급액 (자동 계산)")
                elif c == '진행상황':
                    editable_cols[c] = st.column_config.SelectboxColumn("📌진행", options=["계약체결", "행사준비", "행사종료", "정산완료"], help="프로젝트 단계")
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
                    
                    # 변경 감지: 각 편집 가능 필드 체크
                    paid_changed = ('받은금액' in orig.index and int(orig['받은금액']) != int(curr['받은금액']))
                    status_changed = ('진행상황' in orig.index and str(orig['진행상황']) != str(curr['진행상황']))
                    deposit_changed = ('입금여부' in orig.index and str(orig['입금여부']) != str(curr.get('입금여부', '')))
                    tax_inv_changed = ('세금계산서 발행여부' in orig.index and str(orig['세금계산서 발행여부']) != str(curr.get('세금계산서 발행여부', '')))
                    payout_changed = ('지급액' in orig.index and int(orig['지급액']) != int(curr.get('지급액', 0)))
                    
                    any_changed = paid_changed or status_changed or deposit_changed or tax_inv_changed or payout_changed
                    
                    if any_changed:
                        inq_id_edit = str(curr.get('문의ID', '')).strip()
                        if inq_id_edit:
                            _paid_v = int(curr.get('받은금액', 0))
                            _supply = int(curr.get('공급가액', 0))
                            _tax = int(curr.get('부가세', 0))
                            _bal_v = max(0, _supply + _tax - _paid_v)
                            
                            # 입금여부 자동 결정 (받은금액 변경 시)
                            if paid_changed:
                                if _bal_v <= 0:
                                    _deposit_v = "입금완료"
                                elif _paid_v > 0:
                                    _deposit_v = "부분입금"
                                else:
                                    _deposit_v = "미입금"
                            else:
                                _deposit_v = str(curr.get('입금여부', ''))
                            # 진행상황은 사용자가 직접 선택 (입금여부와 독립)
                            _status_v = str(curr.get('진행상황', ''))
                            
                            _tax_inv_v = str(curr.get('세금계산서 발행여부', ''))
                            _payout_v = int(curr.get('지급액', 0))
                            # 이익 자동 계산: 공급가액 - 지급액
                            _profit_v = _supply - _payout_v if _payout_v > 0 else 0
                            
                            # ✅ 정산완료 자동 전환: 입금완료 + 지급완료 → 정산완료
                            if _deposit_v == "입금완료" and _payout_v > 0 and _status_v != "정산완료":
                                _status_v = "정산완료"
                            
                            _direct_save_settlement(
                                inq_id_edit, _paid_v, _bal_v, _status_v,
                                deposit=_deposit_v, tax_invoice=_tax_inv_v,
                                payout=_payout_v, profit=_profit_v
                            )
                            _save_count += 1
                if _save_count > 0:
                    st.success(f"✅ {_save_count}건 저장 완료! (잔액·입금여부·이익 자동 계산 적용)")
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


def _direct_save_settlement(inquiry_id, paid, balance, status,
                            deposit='', tax_invoice='', payout=0, profit=0):
    """정산 필드를 직접 저장 (data_editor 연동)
    
    Args:
        inquiry_id: 문의ID
        paid: 받은금액
        balance: 잔액
        status: 진행상황
        deposit: 입금여부 (미입금/부분입금/입금완료)
        tax_invoice: 세금계산서 발행여부 (미발행/발행요청/발행완료)
        payout: 지급액
        profit: 이익
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
        for idx, record in enumerate(all_records, start=2):
            if str(record.get('문의ID', '')).strip() == str(inquiry_id).strip():
                target_row = idx
                break
        if not target_row:
            return False
        
        # 헤더 → 컬럼인덱스 매핑
        col_map = {}
        header_targets = ['받은금액', '잔액', '진행상황', '입금여부', '세금계산서 발행여부', '지급액', '이익']
        for i, h in enumerate(headers, 1):
            h_clean = str(h).strip()
            if h_clean in header_targets:
                col_map[h_clean] = i
            elif '받은금액' in h_clean:
                col_map['받은금액'] = i
        
        # 일괄 업데이트 (Cell 객체 사용으로 API 호출 최소화)
        from gspread.cell import Cell
        cells = []
        if '받은금액' in col_map:
            cells.append(Cell(row=target_row, col=col_map['받은금액'], value=int(paid)))
        if '잔액' in col_map:
            cells.append(Cell(row=target_row, col=col_map['잔액'], value=int(balance)))
        if '진행상황' in col_map and status:
            cells.append(Cell(row=target_row, col=col_map['진행상황'], value=str(status)))
        if '입금여부' in col_map and deposit:
            cells.append(Cell(row=target_row, col=col_map['입금여부'], value=str(deposit)))
        if '세금계산서 발행여부' in col_map and tax_invoice:
            cells.append(Cell(row=target_row, col=col_map['세금계산서 발행여부'], value=str(tax_invoice)))
        if '지급액' in col_map and payout:
            cells.append(Cell(row=target_row, col=col_map['지급액'], value=int(payout)))
        if '이익' in col_map:
            cells.append(Cell(row=target_row, col=col_map['이익'], value=int(profit)))
        
        if cells:
            wks.update_cells(cells, value_input_option='RAW')
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False


def save_payment_record(inquiry_id, total_paid, total_invoice):
    """입금 기록을 Google Sheets에 저장"""
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
        
        # 받은금액 컬럼 찾기
        headers = wks.row_values(1)
        paid_col_idx = None
        for idx, header in enumerate(headers, start=1):
            if '받은금액' in str(header):
                paid_col_idx = idx
                break
        
        if not paid_col_idx:
            st.error("❌ '받은금액' 컬럼을 찾을 수 없습니다.")
            return False
        
        # 받은금액 업데이트
        wks.update_cell(target_row, paid_col_idx, int(total_paid))
        
        # 잔액 컬럼 찾기 및 업데이트
        balance_col_idx = None
        for idx, header in enumerate(headers, start=1):
            if header == '잔액':
                balance_col_idx = idx
                break
        
        if balance_col_idx:
            remaining = int(total_invoice - total_paid)
            wks.update_cell(target_row, balance_col_idx, remaining)
        
        # 진행상황 + 입금여부 컬럼 찾기 및 업데이트
        col_indices = {}
        for idx, header in enumerate(headers, start=1):
            h = str(header).strip()
            if h == '진행상황':
                col_indices['진행상황'] = idx
            elif h == '입금여부':
                col_indices['입금여부'] = idx
        
        remaining_amt = total_invoice - total_paid
        if remaining_amt <= 0:
            auto_deposit = "입금완료"
        elif total_paid > 0:
            auto_deposit = "부분입금"
        else:
            auto_deposit = "미입금"
        
        from gspread.cell import Cell
        extra_cells = []
        # 입금여부만 자동 변경 (진행상황은 프로젝트 단계이므로 건드리지 않음)
        if '입금여부' in col_indices:
            extra_cells.append(Cell(row=target_row, col=col_indices['입금여부'], value=auto_deposit))
        
        # ✅ 정산완료 자동 전환: 입금완료 + 기존 지급액 > 0 → 정산완료
        if auto_deposit == "입금완료" and '진행상황' in col_indices:
            # 기존 레코드에서 지급액 확인
            existing_payout = 0
            for rec in all_records:
                if str(rec.get('문의ID', '')).strip() == str(inquiry_id).strip():
                    try:
                        existing_payout = int(float(rec.get('지급액', 0) or 0))
                    except:
                        pass
                    break
            if existing_payout > 0:
                extra_cells.append(Cell(row=target_row, col=col_indices['진행상황'], value='정산완료'))
        
        if extra_cells:
            wks.update_cells(extra_cells, value_input_option='RAW')
        
        return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False


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
        
        # ✅ 정산완료 자동 전환: 지급 완료 + 입금완료 → 정산완료
        if current_record and int(total_payment) > 0:
            deposit_status = str(current_record.get('입금여부', '')).strip()
            if deposit_status == '입금완료':
                # 진행상황 컬럼 찾기
                for i, h in enumerate(headers, 1):
                    if str(h).strip() == '진행상황':
                        wks.update_cell(target_row, i, '정산완료')
                        break
        
        return True
    except Exception as e:
        print(f"지급액/이익 업데이트 실패: {e}")
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
    _detail_tabs = ["🏢 업체 정산", "👷 인력 급여 정산"]
    _active_detail = st.radio("detail", _detail_tabs, key=f"_detail_tab_{inq_id}", horizontal=True, label_visibility="collapsed")

    if _active_detail == _detail_tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("거래명세서 발행")
            # 견적품목 데이터로 세부 항목 조회
            invoice_supply = summary['매출']
            invoice_items = None
            try:
                # 견적품목 시트에서 직접 조회
                matched_items = db.load_estimate_items(inq_id)
                if not matched_items.empty:
                    # 견적품목 시트 컬럼 → 거래명세서 형식으로 변환
                    _items = []
                    for _, _r in matched_items.iterrows():
                        _name = str(_r.get('직군명', '')).strip()
                        if str(_r.get('팀장여부', '')).strip() == '팀장':
                            _name += ' [팀장]'
                        _qty = int(float(_r.get('수량', 0) or 0))
                        _days = int(float(_r.get('일수', 1) or 1))
                        _sell = int(float(_r.get('매출단가', 0) or 0))
                        _amt = _qty * _sell * _days
                        if _name and _sell > 0:
                            _items.append({
                                '품목명': _name,
                                '수량': _qty,
                                '단가': _sell,
                                '일수': _days,
                                '금액': _amt
                            })
                    if _items:
                        invoice_items = _items
                        # 품목 합산이 공급가액보다 정확하면 품목 합산 사용
                        items_total = sum(it['금액'] for it in _items)
                        if items_total > 0:
                            invoice_supply = items_total
            except Exception:
                pass
            # 견적품목이 없으면 견적상세에서 항목 생성
            if not invoice_items and est_row is not None:
                try:
                    _items = []
                    for _col_prefix in ['직종', '직군']:
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
                        items_total = sum(it['금액'] for it in _items)
                        if items_total > 0:
                            invoice_supply = items_total
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

    if _active_detail == _detail_tabs[1]:
        # 공제 방식 선택 (일괄 기본값)
        tax_opt_col, sep_info_col = st.columns([1.5, 1.5])
        with tax_opt_col:
            tax_choice = st.radio(
                "💰 기본 공제 방식",
                ["3.3% 공제 (사업소득세)", "0.9% 공제 (일용직)", "공제 없음 (0%)"],
                key=f"tax_choice_{inq_id}",
                horizontal=True,
                help="일괄 기본값입니다. 개인별로 다르게 설정 가능합니다."
            )
        if "3.3%" in tax_choice:
            sel_tax_rate = 0.033
            default_tax_label = "3.3%"
        elif "0.9%" in tax_choice:
            sel_tax_rate = 0.009
            default_tax_label = "0.9%"
        else:
            sel_tax_rate = 0.0
            default_tax_label = "공제없음"

        with sep_info_col:
            st.info("💡 개인별 공제율은 아래 테이블 '공제율' 컬럼에서 변경하세요.\n\n🏢 본사인력은 '별도정산' 체크로 지급합계에서 제외됩니다.")

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
            
            # ── 헬퍼 ──
            TAX_OPTIONS = ["3.3%", "0.9%", "공제없음"]

            def _parse_tax_rate(label):
                if '3.3' in str(label): return 0.033
                if '0.9' in str(label): return 0.009
                return 0.0

            # ── 원본 데이터 수집 (변동내역 비교용) ──
            orig_data = {}  # {이름: {단가, 일수}}

            # ── 팀 그룹핑: 결제대상='N'인 팀원은 팀장 합산 ──
            team_code_col = '팀코드' if '팀코드' in assignment_df.columns else None
            pay_target_col = '결제대상' if '결제대상' in assignment_df.columns else None

            team_info = {}  # {팀코드: {'members': [...], 'leader': ..., 'sum_amount': int, ...}}
            if team_code_col and pay_target_col:
                for _, _tr in assignment_df.iterrows():
                    _tc = str(_tr.get(team_code_col, '')).strip()
                    if not _tc:
                        continue
                    if _tc not in team_info:
                        team_info[_tc] = {'members': [], 'leader': None, 'sum_amount': 0, 'per_rate': 0, 'per_days': 0}
                    _t_name = str(_tr.get(name_col, '')) if name_col else ''
                    _t_rate = int(float(_tr.get(rate_col, 0) or 0)) if rate_col else 0
                    _t_days = int(float(_tr.get(days_col, 1) or 1)) if days_col else 1
                    _is_pay = str(_tr.get(pay_target_col, 'Y')).strip().upper() == 'Y'
                    team_info[_tc]['members'].append(_t_name)
                    team_info[_tc]['sum_amount'] += _t_rate * _t_days
                    team_info[_tc]['per_rate'] = _t_rate
                    team_info[_tc]['per_days'] = _t_days
                    if _is_pay:
                        team_info[_tc]['leader'] = _t_name

            edit_rows = []
            for i, arow in assignment_df.iterrows():
                a_name = str(arow.get(name_col, 'N/A')) if name_col else 'N/A'
                a_role = str(arow.get(role_col, '')) if role_col else ''
                a_rate = int(float(arow.get(rate_col, 0) or 0)) if rate_col else 0
                a_days = int(float(arow.get(days_col, 1) or 1)) if days_col else 1
                a_type = str(arow.get(assign_type_col, '')) if assign_type_col else ''
                is_hq = a_name in hq_names
                _tc = str(arow.get(team_code_col, '')).strip() if team_code_col else ''
                _is_pay = str(arow.get(pay_target_col, 'Y')).strip().upper() == 'Y' if pay_target_col else True

                # 팀원(결제대상=N)은 정산 테이블에서 제외
                if _tc and not _is_pay:
                    continue

                orig_data[a_name] = {'단가': a_rate, '일수': a_days}

                bank, account = _get_bank_info(a_name, df_staff)

                # 팀장이면 팀 전체 합산
                if _tc and _tc in team_info:
                    ti = team_info[_tc]
                    display_basic = ti['sum_amount']
                    member_names = [m for m in ti['members'] if m != a_name]
                    member_count = len(member_names)
                    per_rate = ti.get('per_rate', a_rate)
                    per_days = ti.get('per_days', a_days)
                    team_note = (f"팀원{member_count}명분 포함 | "
                                f"인당 ₩{per_rate:,}×{per_days}일×{len(ti['members'])}명"
                                f"=₩{display_basic:,}")
                else:
                    display_basic = a_rate * a_days
                    team_note = ''

                edit_rows.append({
                    '이체': False,
                    '이름': a_name,
                    '직무': a_role,
                    '구분': '본사' if is_hq else a_type,
                    '팀': team_note,
                    '공제율': default_tax_label,
                    '별도': True if is_hq else False,
                    '단가': a_rate,
                    '일수': a_days,
                    '식비': 0,
                    '교통비': 0,
                    '연장': 0,
                    '기타(숙박등)': 0,
                    '기본급': display_basic,
                    '공제': 0,
                    '실수령': display_basic,
                    '메모': '',
                    '_은행': bank or '',
                    '_계좌': account or '',
                    '_팀코드': _tc,
                })

            initial_df = pd.DataFrame(edit_rows)

            # ── 세션 상태 기반 영구 저장 (새로고침/탭 이동 시에도 수정값 유지) ──
            editor_key = f"salary_editor_{inq_id}"
            persist_key = f"_salary_persist_{inq_id}"

            # 영구 저장된 편집 데이터가 있으면 initial_df에 반영
            if persist_key in st.session_state and st.session_state[persist_key]:
                persisted = st.session_state[persist_key]
                for row_idx_str, changes in persisted.get('edited_rows', {}).items():
                    row_idx = int(row_idx_str)
                    if row_idx < len(initial_df):
                        for col, val in changes.items():
                            if col in initial_df.columns:
                                initial_df.at[row_idx, col] = val
                # 추가된 행 처리
                for added_row in persisted.get('added_rows', []):
                    new_row = {
                        '이체': added_row.get('이체', False),
                        '이름': added_row.get('이름', ''),
                        '직무': added_row.get('직무', ''),
                        '구분': added_row.get('구분', ''),
                        '공제율': added_row.get('공제율', default_tax_label),
                        '별도': added_row.get('별도', False),
                        '단가': added_row.get('단가', 0),
                        '일수': added_row.get('일수', 0),
                        '식비': added_row.get('식비', 0),
                        '교통비': added_row.get('교통비', 0),
                        '연장': added_row.get('연장', 0),
                        '기타(숙박등)': added_row.get('기타(숙박등)', 0),
                        '기본급': 0, '공제': 0, '실수령': 0,
                        '메모': added_row.get('메모', ''),
                        '_은행': '', '_계좌': '',
                    }
                    initial_df = pd.concat([initial_df, pd.DataFrame([new_row])], ignore_index=True)

            # 모든 행의 기본급·공제·실수령 재계산
            for idx in range(len(initial_df)):
                _r_rate = int(float(initial_df.at[idx, '단가'] or 0))
                _r_days = int(float(initial_df.at[idx, '일수'] or 0))
                _r_meal = int(float(initial_df.at[idx, '식비'] or 0))
                _r_trans = int(float(initial_df.at[idx, '교통비'] or 0))
                _r_overtime = int(float(initial_df.at[idx, '연장'] or 0))
                _r_etc = int(float(initial_df.at[idx, '기타(숙박등)'] or 0))
                _r_is_sep = bool(initial_df.at[idx, '별도'])
                _r_tax_label = str(initial_df.at[idx, '공제율'])
                _r_person_rate = _parse_tax_rate(_r_tax_label)
                # 팀장이면 팀 합산 기본급 사용
                _r_tc = str(initial_df.at[idx, '_팀코드']) if '_팀코드' in initial_df.columns else ''
                if _r_tc and _r_tc in team_info:
                    _r_basic = team_info[_r_tc]['sum_amount']
                else:
                    _r_basic = _r_rate * _r_days
                _r_gross = _r_basic + _r_meal + _r_trans + _r_overtime + _r_etc
                _r_tax = int(_r_gross * _r_person_rate) if not _r_is_sep else 0
                _r_net = _r_gross - _r_tax
                initial_df.at[idx, '기본급'] = _r_basic
                initial_df.at[idx, '공제'] = _r_tax
                initial_df.at[idx, '실수령'] = _r_net

            # 편집 시 자동 영구 저장 콜백
            def _on_salary_change():
                if editor_key in st.session_state:
                    widget_state = st.session_state[editor_key]
                    # 기존 persist에 새 변경사항 병합
                    if persist_key not in st.session_state:
                        st.session_state[persist_key] = {'edited_rows': {}, 'added_rows': []}
                    persisted = st.session_state[persist_key]
                    # edited_rows 병합 (같은 행의 같은 컬럼은 새 값으로 덮어쓰기)
                    for row_idx_str, changes in widget_state.get('edited_rows', {}).items():
                        if row_idx_str not in persisted['edited_rows']:
                            persisted['edited_rows'][row_idx_str] = {}
                        persisted['edited_rows'][row_idx_str].update(changes)
                    # added_rows 추가
                    new_added = widget_state.get('added_rows', [])
                    if new_added:
                        persisted['added_rows'].extend(new_added)

            # ── 인력 급여 통합 테이블 ──
            display_count = len(initial_df)
            team_member_count = len(assignment_df) - display_count if team_info else 0
            team_label = f" (팀원 {team_member_count}명 → 팀장 합산)" if team_member_count > 0 else ""
            st.subheader(f"👷 인력 급여 관리 ({display_count}명{team_label})")
            st.caption("💡 단가·일수·수당을 수정하면 기본급→공제→실수령이 **자동 계산**됩니다. 행 하단 `+`로 충원 인원 추가 가능.")

            # 팀 일괄결제 안내
            if team_info:
                team_html = ""
                for _tc, _ti in team_info.items():
                    _leader = _ti['leader'] or '?'
                    _members = [m for m in _ti['members'] if m != _leader]
                    _per_r = _ti.get('per_rate', 0)
                    _per_d = _ti.get('per_days', 0)
                    _n = len(_ti['members'])
                    team_html += (f'<div style="background:#EDE9FE;border-radius:8px;padding:6px 10px;margin:3px 0;">'
                                 f'<b>👥 {_leader}팀</b> ({_n}명) → <b>{_leader}</b> 계좌로 일괄지급<br/>'
                                 f'<span style="font-size:12px;color:#5B21B6;">'
                                 f'  산출: 인당 ₩{_per_r:,} × {_per_d}일 × {_n}명 = <b>₩{_ti["sum_amount"]:,}</b>'
                                 f'</span><br/>'
                                 f'<span style="font-size:11px;color:#7C3AED;">팀원: {", ".join(_members) if _members else "(팀장만)"}</span>'
                                 f'</div>')
                st.markdown(f'<div style="background:#F5F3FF;border:1px solid #A78BFA;border-radius:8px;'
                            f'padding:8px 12px;margin:6px 0;"><b style="font-size:13px;">💰 팀 일괄결제 내역</b>'
                            f'{team_html}</div>', unsafe_allow_html=True)

            edited_df = st.data_editor(
                initial_df.drop(columns=['_은행', '_계좌', '_팀코드']),
                column_config={
                    '이체': st.column_config.CheckboxColumn('이체✓', width=50, help="이체 완료 체크"),
                    '이름': st.column_config.TextColumn('이름', width=75, disabled=True),
                    '직무': st.column_config.TextColumn('직무', width=65, disabled=True),
                    '구분': st.column_config.TextColumn('구분', width=50, disabled=True),
                    '팀': st.column_config.TextColumn('팀', width=140, disabled=True, help="팀 배정 시 팀원 정보"),
                    '공제율': st.column_config.SelectboxColumn('공제율', width=80, options=TAX_OPTIONS, help="개인별 공제율"),
                    '별도': st.column_config.CheckboxColumn('별도', width=45, help="✅ 별도정산 → 합계 제외"),
                    '단가': st.column_config.NumberColumn('단가', width=85, min_value=0, step=10000, format="%d"),
                    '일수': st.column_config.NumberColumn('일수', width=50, min_value=0, step=1),
                    '식비': st.column_config.NumberColumn('식비', width=70, min_value=0, step=5000, format="%d"),
                    '교통비': st.column_config.NumberColumn('교통비', width=70, min_value=0, step=5000, format="%d"),
                    '연장': st.column_config.NumberColumn('연장', width=70, min_value=0, step=5000, format="%d", help="연장근무 수당"),
                    '기타(숙박등)': st.column_config.NumberColumn('기타(숙박등)', width=85, min_value=0, step=5000, format="%d", help="숙박비, 기타 수당 등"),
                    '기본급': st.column_config.NumberColumn('기본급', width=90, format="%d", disabled=True),
                    '공제': st.column_config.NumberColumn('공제', width=70, format="%d", disabled=True),
                    '실수령': st.column_config.NumberColumn('실수령', width=90, format="%d", disabled=True),
                    '메모': st.column_config.TextColumn('메모', width=140, help="메모사항"),
                },
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key=editor_key,
                on_change=_on_salary_change
            )

            # ── 자동 계산 적용 (edited_df의 기본급·공제·실수령 재계산) ──
            calc_rows = []
            for i, erow in edited_df.iterrows():
                e_rate = int(erow.get('단가', 0) or 0)
                e_days = int(erow.get('일수', 0) or 0)
                e_meal = int(erow.get('식비', 0) or 0)
                e_trans = int(erow.get('교통비', 0) or 0)
                e_overtime = int(erow.get('연장', 0) or 0)
                e_etc = int(erow.get('기타(숙박등)', 0) or 0)
                is_sep = bool(erow.get('별도', False))
                is_paid = bool(erow.get('이체', False))
                person_rate = _parse_tax_rate(erow.get('공제율', default_tax_label))
                e_name = str(erow.get('이름', '')).strip()

                # 팀장이면 팀 합산 기본급 사용
                _e_tc = str(initial_df.iloc[i].get('_팀코드', '')) if i < len(initial_df) else ''
                if _e_tc and _e_tc in team_info:
                    basic = team_info[_e_tc]['sum_amount']
                else:
                    basic = e_rate * e_days
                gross = basic + e_meal + e_trans + e_overtime + e_etc
                tax = int(gross * person_rate) if not is_sep else 0
                net = gross - tax

                # 변동 내역 비교
                changes = []
                if e_name in orig_data:
                    o = orig_data[e_name]
                    if e_rate != o['단가']:
                        changes.append(f"단가 {o['단가']:,}→{e_rate:,}")
                    if e_days != o['일수']:
                        changes.append(f"일수 {o['일수']}→{e_days}")
                elif e_name and e_name != 'N/A' and e_name not in orig_data:
                    changes.append("신규 충원")

                # 은행/계좌 (원본에서 가져오기 — 충원 인원은 비어있음)
                bank_val = ''
                acct_val = ''
                if i < len(initial_df):
                    bank_val = str(initial_df.iloc[i].get('_은행', '')).strip()
                    acct_val = str(initial_df.iloc[i].get('_계좌', '')).strip()

                calc_rows.append({
                    '이름': e_name,
                    '직무': str(erow.get('직무', '')),
                    '구분': str(erow.get('구분', '')),
                    '공제율': str(erow.get('공제율', default_tax_label)),
                    '별도': is_sep,
                    '이체': is_paid,
                    '단가': e_rate,
                    '일수': e_days,
                    '식비': e_meal,
                    '교통비': e_trans,
                    '연장': e_overtime,
                    '기타(숙박등)': e_etc,
                    '기본급': basic,
                    '총액': gross,
                    '공제': tax,
                    '실수령': net,
                    '메모': str(erow.get('메모', '')),
                    '은행': bank_val,
                    '계좌': acct_val,
                    '_changes': changes,
                    '_tax_rate': person_rate,
                    '_팀코드': _e_tc,
                })

            # ── ⚡ 변동내역 배지 ──
            changed_items = [(r['이름'], r['_changes']) for r in calc_rows if r['_changes']]
            if changed_items:
                badges_html = " ".join(
                    f'<span style="background:#FEF3C7;color:#92400E;padding:3px 8px;border-radius:6px;font-size:12px;margin:2px;">'
                    f'⚡ {name}: {", ".join(ch)}</span>'
                    for name, ch in changed_items
                )
                st.markdown(f"""
                <div style="background:#FFFBEB;border:1px solid #F59E0B;border-radius:8px;padding:8px 12px;margin:8px 0;">
                    <b style="font-size:12px;">📋 변동내역</b><br/>{badges_html}
                </div>
                """, unsafe_allow_html=True)

            # ── 💰 지급 요약 메트릭 ──
            normal = [r for r in calc_rows if not r['별도']]
            separate = [r for r in calc_rows if r['별도']]
            paid_count = sum(1 for r in calc_rows if r['이체'])
            unpaid_normal = [r for r in normal if not r['이체']]

            total_gross = sum(r['총액'] for r in normal)
            total_tax = sum(r['공제'] for r in normal)
            total_net = total_gross - total_tax

            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            mc1.metric("지급 대상", f"{len(normal)}명")
            mc2.metric("총 지급액", f"₩{total_gross:,}")
            mc3.metric("공제 합계", f"-₩{total_tax:,}")
            mc4.metric("실수령 합계", f"₩{total_net:,}")
            mc5.metric("이체 진행", f"{paid_count}/{len(calc_rows)}명",
                       delta=f"{len(calc_rows)-paid_count}명 미이체" if paid_count < len(calc_rows) else "전원 완료",
                       delta_color="inverse" if paid_count < len(calc_rows) else "off")

            if separate:
                sep_gross = sum(r['총액'] for r in separate)
                st.markdown(f"""
                <div style="background:#FFF7ED;border:1px solid #FB923C;border-radius:8px;
                            padding:8px 14px;margin:4px 0;font-size:13px;">
                    🏢 <b>별도정산 {len(separate)}명</b> (₩{sep_gross:,}) — 위 합계 미포함
                </div>
                """, unsafe_allow_html=True)

            st.divider()

            # ── 액션 버튼 ──
            btn_c1, btn_c2, btn_c3 = st.columns(3)

            with btn_c1:
                if st.button("🏦 계좌정보 → STAFF 저장", key=f"save_bank_{inq_id}", use_container_width=True):
                    save_count = 0
                    for cr in calc_rows:
                        if cr['은행'] and cr['계좌']:
                            orig_bank, orig_acct = _get_bank_info(cr['이름'], df_staff)
                            if cr['은행'] != (orig_bank or '') or cr['계좌'] != (orig_acct or ''):
                                if _save_bank_to_staff(cr['이름'], cr['은행'], cr['계좌'], df_staff):
                                    save_count += 1
                    if save_count > 0:
                        st.success(f"✅ {save_count}명 계좌정보 저장!")
                        db.invalidate_data()
                    else:
                        st.info("변경된 계좌정보가 없습니다.")

            with btn_c2:
                if st.button("💾 지급기록 일괄 저장", key=f"save_pay_all_{inq_id}", type="primary", use_container_width=True):
                    save_count = 0
                    sep_count = 0
                    for i, cr in enumerate(calc_rows):
                        if cr['별도']:
                            sep_count += 1
                            continue
                        if cr['총액'] <= 0:
                            continue
                        # initial_df에서 배정ID 가져오기 (assignment_df가 아닌 initial_df 사용 — 팀원 제외되었으므로)
                        a_assign_id = ''
                        if i < len(initial_df):
                            # initial_df에는 _은행/_계좌는 있지만 배정ID는 없을 수 있으므로 이름으로 매칭
                            _match_name = cr['이름']
                            _matched = assignment_df[assignment_df[name_col].astype(str) == _match_name] if name_col else pd.DataFrame()
                            if not _matched.empty:
                                a_assign_id = str(_matched.iloc[0].get('배정ID', ''))
                        _tc_note = "[팀일괄] " if cr.get('_팀코드') else ""
                        payment_dict = {
                            '배정ID': a_assign_id,
                            '인력명': cr['이름'],
                            '현장명': row['행사명'],
                            '파견기간': str(row.get('행사시작일', '')),
                            '파견일수': cr['일수'],
                            '기본급': cr['기본급'],
                            '야근비': cr['연장'],
                            '식사비': cr['식비'],
                            '교통비': cr['교통비'],
                            '보너스': cr['기타(숙박등)'],
                            '소계': cr['총액'],
                            '세금공제': cr['공제'],
                            '최종지급액': cr['실수령'],
                            '지급상태': '완료',
                            '지급일': datetime.now().strftime('%Y-%m-%d'),
                            '지급담당자': '',
                            '비고': _tc_note + f"{cr['공제율']} 공제" + (f" | {cr['메모']}" if cr['메모'] else ""),
                        }
                        if db.save_payment_record(payment_dict):
                            save_count += 1
                    parts = []
                    if save_count > 0: parts.append(f"{save_count}명 저장")
                    if sep_count > 0: parts.append(f"{sep_count}명 별도정산 제외")
                    if save_count > 0:
                        st.success(f"✅ {' / '.join(parts)} 완료!")
                        db.invalidate_data()
                    else:
                        st.warning("저장할 기록이 없습니다." + (f" (별도정산 {sep_count}명)" if sep_count else ""))

            with btn_c3:
                # ── 📥 은행이체 엑셀 다운로드 (B) ──
                import io
                transfer_rows = []
                for cr in calc_rows:
                    if cr['별도'] or cr['실수령'] <= 0:
                        continue
                    transfer_rows.append({
                        '이름': cr['이름'],
                        '은행': cr['은행'],
                        '계좌번호': cr['계좌'],
                        '이체금액': cr['실수령'],
                        '메모': cr['메모'] or f"{row['행사명']} 급여",
                    })
                if transfer_rows:
                    transfer_df = pd.DataFrame(transfer_rows)
                    buf = io.BytesIO()
                    transfer_df.to_excel(buf, index=False, sheet_name='이체목록')
                    buf.seek(0)
                    st.download_button(
                        "📥 이체용 엑셀 다운로드",
                        data=buf.getvalue(),
                        file_name=f"이체_{row['행사명']}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key=f"dl_excel_{inq_id}",
                    )
                else:
                    st.button("📥 이체용 엑셀", disabled=True, use_container_width=True, key=f"dl_excel_{inq_id}")

            st.divider()

            # ── 📄 개별 급여명세서 ──
            st.subheader("📄 개별 급여명세서")
            for cr in calc_rows:
                e_name = cr['이름']
                if not e_name or e_name == 'N/A':
                    continue
                gross = cr['총액']
                is_sep = cr['별도']
                is_paid = cr['이체']
                person_rate = cr['_tax_rate']

                # 배지
                if is_paid:
                    badge = "✅"
                    status_txt = " [이체완료]"
                elif is_sep:
                    badge = "🔸"
                    status_txt = " [별도정산]"
                else:
                    badge = "👤"
                    status_txt = ""

                bank_val = cr['은행']
                acct_val = cr['계좌']
                bank_info = f"💳 {bank_val} {acct_val}" if bank_val and acct_val else "❗ 계좌 미등록"
                change_txt = f" | ⚡{', '.join(cr['_changes'])}" if cr['_changes'] else ""
                memo_txt = f" | 📝{cr['메모']}" if cr['메모'] else ""

                with st.expander(f"{badge} {e_name}{status_txt} ({cr['직무']}) — ₩{gross:,} [{cr['공제율']}] {bank_info}{change_txt}{memo_txt}"):
                    if gross <= 0 and not is_sep:
                        st.warning("❌ 지급액 없음")
                        continue
                    if is_sep:
                        st.info("🔸 별도정산 대상 — 지급합계에서 제외됩니다.")
                    if cr['_changes']:
                        st.warning(f"⚡ 변동: {', '.join(cr['_changes'])}")
                    if cr['메모']:
                        st.info(f"📝 메모: {cr['메모']}")

                    c1, c2 = st.columns([2, 1])
                    with c1:
                        html_p = brain.get_payslip_html(
                            e_name, row['행사명'], cr['단가'], cr['일수'], gross,
                            tax_rate=person_rate, meal=cr['식비'], transport=cr['교통비'],
                            overtime=cr['연장'], etc_cost=cr['기타(숙박등)']
                        )
                        st.components.v1.html(html_p, height=450)
                    with c2:
                        if bank_val and acct_val:
                            st.info(f"🏦 {bank_val}\n\n📋 {acct_val}")
                        else:
                            st.warning("계좌 미등록")
                        # 계산 상세
                        st.markdown(f"""
                        | 항목 | 금액 |
                        |------|------|
                        | 기본급 | ₩{cr['기본급']:,} |
                        | 식비 | ₩{cr['식비']:,} |
                        | 교통비 | ₩{cr['교통비']:,} |
                        | 연장 | ₩{cr['연장']:,} |
                        | 기타(숙박등) | ₩{cr['기타(숙박등)']:,} |
                        | **총액** | **₩{cr['총액']:,}** |
                        | 공제({cr['공제율']}) | -₩{cr['공제']:,} |
                        | **실수령** | **₩{cr['실수령']:,}** |
                        """)
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
            if st.button("🏁 최종 정산 완료 (프로젝트 종료)", type="primary"):
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

    # 홈택스 바로가기 버튼
    st.link_button(
        "🏛️ 홈택스 세금계산서 발행 바로가기",
        "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index_pp.xml&menuCd=index3",
        use_container_width=True,
        type="primary"
    )
    st.caption("💡 위 버튼을 눌러 홈택스에서 전자세금계산서를 발행하세요. 아래 업체 정보를 참고하여 입력합니다.")
    st.markdown("")
    
    if col_tax_issued and col_company:
        not_issued_df = settlement_df[
            ~settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)
        ].copy()
        
        if not not_issued_df.empty:
            for idx, row in not_issued_df.iterrows():
                company = str(row.get(col_company, '미등록')).strip()
                site_name = str(row.get('현장명', '')).strip()
                biz_num = str(row.get('사업자번호', '')).strip()
                ceo_name = str(row.get('대표자', '')).strip()
                corp_name = str(row.get('법인명', '')).strip()
                email_val = str(row.get('이메일', '')).strip()
                contact_val = str(row.get('연락처', '')).strip()
                content_val = str(row.get('내용(품목)', '')).strip()
                note_val = str(row.get('발행요청사항', '')).strip()
                
                # 금액 정보
                amount_raw = row.get('청구금액', '')
                supply_raw = row.get('공급가액', '')
                tax_raw = row.get('부가세', '')
                paid_raw = row.get('받은금액', '')
                
                def _fmt_money(v):
                    try:
                        n = int(float(str(v).replace(',', '').strip()))
                        return f"₩{n:,}" if n > 0 else ''
                    except:
                        return str(v).strip() if str(v).strip() not in ('', 'nan', 'None', '0') else ''
                
                amount_str = _fmt_money(amount_raw)
                supply_str = _fmt_money(supply_raw)
                tax_str = _fmt_money(tax_raw)
                paid_str = _fmt_money(paid_raw)
                
                # 공급가액/부가세 자동 계산 (값이 없을 때)
                if not supply_str and amount_str:
                    try:
                        total_amt = int(float(str(amount_raw).replace(',', '').strip()))
                        calc_supply = int(total_amt / 1.1)
                        calc_tax = total_amt - calc_supply
                        supply_str = f"₩{calc_supply:,} (추정)"
                        tax_str = f"₩{calc_tax:,} (추정)"
                    except:
                        pass
                
                col_left, col_right = st.columns([3, 1])
                with col_left:
                    # 기본 정보
                    title_line = f"<b style='font-size:16px;'>{company}</b>"
                    if site_name:
                        title_line += f" <span style='color:#6b7280;'>({site_name})</span>"
                    
                    # 사업자 정보 블록
                    biz_info_lines = []
                    if biz_num and biz_num not in ('nan', 'None', ''):
                        biz_info_lines.append(f"🏢 사업자번호: <b>{biz_num}</b>")
                    if corp_name and corp_name not in ('nan', 'None', ''):
                        biz_info_lines.append(f"🏗️ 법인명: {corp_name}")
                    if ceo_name and ceo_name not in ('nan', 'None', ''):
                        biz_info_lines.append(f"👤 대표자: {ceo_name}")
                    if email_val and email_val not in ('nan', 'None', ''):
                        biz_info_lines.append(f"📧 이메일: <b>{email_val}</b>")
                    if contact_val and contact_val not in ('nan', 'None', ''):
                        biz_info_lines.append(f"📞 연락처: {contact_val}")
                    
                    # 금액 정보 블록
                    money_lines = []
                    if supply_str:
                        money_lines.append(f"💰 공급가액: <b>{supply_str}</b>")
                    if tax_str:
                        money_lines.append(f"💰 부가세: <b>{tax_str}</b>")
                    if amount_str:
                        money_lines.append(f"💰 청구금액(합계): <b>{amount_str}</b>")
                    if paid_str:
                        money_lines.append(f"✅ 받은금액: {paid_str}")
                    
                    # 품목/요청사항
                    extra_lines = []
                    if content_val and content_val not in ('nan', 'None', ''):
                        extra_lines.append(f"📋 내용(품목): {content_val}")
                    if note_val and note_val not in ('nan', 'None', ''):
                        extra_lines.append(f"📝 요청사항: <span style='color:#DC2626;'>{note_val}</span>")
                    
                    # 빠진 정보 경고
                    missing = []
                    if not biz_num or biz_num in ('nan', 'None', ''): missing.append("사업자번호")
                    if not email_val or email_val in ('nan', 'None', ''): missing.append("이메일")
                    if not supply_str: missing.append("공급가액")
                    
                    missing_html = ""
                    if missing:
                        missing_html = f"<div style='background:#FEF3C7;border-radius:4px;padding:4px 8px;margin-top:6px;font-size:12px;color:#92400E;'>⚠️ 미입력: {', '.join(missing)}</div>"
                    
                    # 모든 정보를 하나의 카드로 조합
                    all_info = []
                    all_info.append(title_line)
                    if biz_info_lines:
                        all_info.append("<div style='margin:6px 0 4px 0;border-top:1px solid #fecaca;padding-top:6px;'>" + "<br/>".join(biz_info_lines) + "</div>")
                    if money_lines:
                        all_info.append("<div style='margin:4px 0;padding:6px 8px;background:#FFF7ED;border-radius:4px;'>" + "<br/>".join(money_lines) + "</div>")
                    if extra_lines:
                        all_info.append("<br/>".join(extra_lines))
                    
                    st.markdown(f"""
                    <div style="background-color:#FEF2F2;border-left:4px solid #DC2626;
                                padding:14px;border-radius:6px;margin-bottom:8px;font-size:13px;">
                        {''.join(all_info)}
                        {missing_html}
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_right:
                    if st.button("✅ 발행 완료", key=f"tax_done_{idx}", use_container_width=True):
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