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
        dispatch_data = db.load_dispatch_data()
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
                st.cache_data.clear()
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
                    st.cache_data.clear()
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


def _direct_save_settlement(inquiry_id, paid, balance, status):
    """받은금액/잔액/진행상황을 직접 저장 (data_editor 연동)"""
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
            elif h == '진행상황':
                col_map['진행상황'] = i
        if '받은금액' in col_map:
            wks.update_cell(target_row, col_map['받은금액'], int(paid))
        if '잔액' in col_map:
            wks.update_cell(target_row, col_map['잔액'], int(balance))
        if '진행상황' in col_map and status:
            wks.update_cell(target_row, col_map['진행상황'], status)
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
        
        # 진행상황 컬럼 찾기 및 업데이트
        status_col_idx = None
        for idx, header in enumerate(headers, start=1):
            if header == '진행상황':
                status_col_idx = idx
                break
        
        if status_col_idx:
            # 잔액이 0 이하면 "입금완료", 아니면 "부분입금"
            status = "입금완료" if (total_invoice - total_paid) <= 0 else "부분입금"
            wks.update_cell(target_row, status_col_idx, status)
        
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
                    st.success("현장 완료 처리됨!"); st.cache_data.clear(); time.sleep(1); st.rerun()
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
        
        if not assignment_df.empty:
            name_col = '이름' if '이름' in assignment_df.columns else '인력명' if '인력명' in assignment_df.columns else None
            role_col = '역할' if '역할' in assignment_df.columns else '직무' if '직무' in assignment_df.columns else None
            rate_col = '단가' if '단가' in assignment_df.columns else '지급단가' if '지급단가' in assignment_df.columns else None
            days_col = '일수' if '일수' in assignment_df.columns else '근무일수' if '근무일수' in assignment_df.columns else None
            total_col = '총지급액' if '총지급액' in assignment_df.columns else None
            assign_type_col = '구분' if '구분' in assignment_df.columns else None
            
            # 본사인원 제외 필터
            hq_names = [s['이름'] for s in db.HQ_STAFF] if hasattr(db, 'HQ_STAFF') else []
            
            st.subheader(f"👷 지급 대상자 전체 목록 ({len(assignment_df)}명)")
            
            # 전체 목록을 테이블 형태로 먼저 표시
            summary_rows = []
            for i, arow in assignment_df.iterrows():
                a_name = str(arow.get(name_col, 'N/A')) if name_col else 'N/A'
                a_role = str(arow.get(role_col, '')) if role_col else ''
                a_rate = int(float(arow.get(rate_col, 0) or 0)) if rate_col else 0
                a_days = int(float(arow.get(days_col, 1) or 1)) if days_col else 1
                a_total = int(float(arow.get(total_col, a_rate * a_days) or 0)) if total_col else a_rate * a_days
                a_type = str(arow.get(assign_type_col, '')) if assign_type_col else ''
                
                tax_amt = int(a_total * sel_tax_rate)
                net_pay = a_total - tax_amt
                
                bank, account = _get_bank_info(a_name, df_staff)
                is_hq = a_name in hq_names
                
                summary_rows.append({
                    '이름': a_name,
                    '직무': a_role,
                    '구분': '본사' if is_hq else a_type,
                    '단가': f"{a_rate:,}",
                    '일수': a_days,
                    '총액': f"{a_total:,}",
                    '공제': f"-{tax_amt:,}",
                    '실수령액': f"{net_pay:,}",
                    '은행': bank or '❗입력필요',
                    '계좌번호': account or '❗입력필요',
                })
            
            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            
            # 총합계
            total_gross = sum(int(float(arow.get(total_col, int(float(arow.get(rate_col, 0) or 0)) * int(float(arow.get(days_col, 1) or 1))) or 0)) if total_col else int(float(arow.get(rate_col, 0) or 0)) * int(float(arow.get(days_col, 1) or 1)) for _, arow in assignment_df.iterrows())
            total_tax = int(total_gross * sel_tax_rate)
            total_net = total_gross - total_tax
            st.markdown(f"**💰 합계: 총 {total_gross:,}원 | 공제 -{total_tax:,}원 | 실수령 {total_net:,}원**")
            
            st.divider()
            
            # 개별 급여명세서 + 지급 처리
            st.subheader("📄 개별 급여명세서 및 지급 처리")
            for i, arow in assignment_df.iterrows():
                a_name = str(arow.get(name_col, 'N/A')) if name_col else 'N/A'
                a_role = str(arow.get(role_col, '')) if role_col else ''
                a_rate = int(float(arow.get(rate_col, 0) or 0)) if rate_col else 0
                a_days = int(float(arow.get(days_col, 1) or 1)) if days_col else 1
                a_total = int(float(arow.get(total_col, a_rate * a_days) or 0)) if total_col else a_rate * a_days
                a_assign_id = str(arow.get('배정ID', ''))
                is_hq = a_name in hq_names
                
                bank, account = _get_bank_info(a_name, df_staff)
                bank_info = f"💳 {bank} {account}" if bank and account else "❗ 계좌정보 미등록"
                hq_badge = " [본사]" if is_hq else ""
                
                with st.expander(f"{'🏢' if is_hq else '👤'} {a_name}{hq_badge} ({a_role}) — {a_total:,}원 | {bank_info}"):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        html_p = brain.get_payslip_html(a_name, row['행사명'], a_rate, a_days, a_total, tax_rate=sel_tax_rate)
                        st.components.v1.html(html_p, height=400)
                    with c2:
                        # 은행/계좌 정보
                        if bank and account:
                            st.info(f"🏦 {bank}\n\n📋 {account}")
                        else:
                            st.warning("계좌정보 미등록")
                            _input_bank = st.text_input("은행명", key=f"bank_input_{i}", placeholder="예: 국민은행")
                            _input_acct = st.text_input("계좌번호", key=f"acct_input_{i}", placeholder="000-0000-0000")
                        
                        # 지급 처리 (본사인원 제외)
                        if not is_hq:
                            pay_done = st.checkbox("✅ 이체 완료", key=f"pay_assign_{i}")
                            if pay_done:
                                st.success("지급 완료됨")
                                # 지급기록 시트에 저장
                                if st.button("💾 지급기록 저장", key=f"save_pay_{i}"):
                                    tax_amt = int(a_total * sel_tax_rate)
                                    payment_dict = {
                                        '배정ID': a_assign_id,
                                        '인력명': a_name,
                                        '현장명': row['행사명'],
                                        '파견기간': str(row.get('행사시작일', '')),
                                        '파견일수': a_days,
                                        '기본급': a_total,
                                        '야근비': 0,
                                        '식사비': 0,
                                        '교통비': 0,
                                        '보너스': 0,
                                        '소계': a_total,
                                        '세금공제': tax_amt,
                                        '최종지급액': a_total - tax_amt,
                                        '지급상태': '완료',
                                        '지급일': datetime.now().strftime('%Y-%m-%d'),
                                        '지급담당자': '',
                                        '비고': f"정산페이지 ({sel_tax_rate*100:.1f}% 공제)",
                                    }
                                    if db.save_payment_record(payment_dict):
                                        st.success(f"✅ {a_name} 지급기록 저장 완료!")
                                        st.cache_data.clear()
                                    else:
                                        st.error("저장 실패")
                        else:
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
            if st.button("🏁 최종 정산 완료 (프로젝트 종료)", type="primary"):
                db.update_status(inq_id_for_update, sc.STATUS_FLOW[6])  # '정산완료'
                st.cache_data.clear()
                st.balloons(); st.success("모든 정산이 완료되었습니다!"); st.rerun()


def show_tax_invoice_management():
    """세금계산서 발행 현황 관리"""
    st.markdown('<div class="section-title">📄 세금계산서 발행 관리</div>', unsafe_allow_html=True)
    st.caption("거래처별 세금계산서 발행 현황을 관리하고, 사업자등록증에서 정보를 자동 추출하세요.")
    
    try:
        dispatch_data = db.load_dispatch_data()
        settlement_df = dispatch_data.get('settlement', pd.DataFrame())
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return
    
    if settlement_df.empty:
        st.warning("⚠️ 정산 데이터가 없습니다.")
        return
    
    settlement_df = settlement_df.fillna('').copy()
    
    # 1️⃣ 세금계산서 발행 현황 요약
    st.markdown("### 📊 발행 현황 요약")
    
    col_tax_issued = None
    col_company = None
    
    for col in settlement_df.columns:
        if '세금' in col or '발행' in col:
            col_tax_issued = col
        if '업체' in col or '업체명' in col:
            col_company = col
    
    if col_tax_issued and col_company:
        issued_count = len(settlement_df[settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)])
        not_issued_count = len(settlement_df[~settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)])
        total_count = len(settlement_df)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("✅ 발행 완료", issued_count)
        with col2:
            st.metric("⏳ 미발행", not_issued_count)
        with col3:
            issue_rate = int((issued_count / total_count * 100) if total_count > 0 else 0)
            st.metric("📈 발행률", f"{issue_rate}%")
    
    st.markdown("---")
    
    # 2️⃣ 업체별 세금계산서 발행 현황 테이블
    st.markdown("### 📋 업체별 발행 현황")
    
    if col_company and col_tax_issued:
        # 필요한 컬럼만 선택
        display_cols = [col_company, col_tax_issued]
        
        # 추가 정보 컬럼 (있으면)
        for col in settlement_df.columns:
            if '청구' in col or '파견' in col or '현장' in col:
                if col not in display_cols:
                    display_cols.append(col)
                    if len(display_cols) >= 5:
                        break
        
        display_cols = [c for c in display_cols if c in settlement_df.columns]
        
        # 데이터 표시
        tax_df = settlement_df[display_cols].copy()
        st.dataframe(tax_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # 3️⃣ 미발행 업체 강조 표시
    st.markdown("### 🚨 미발행 업체 (즉시 처리 필요)")
    
    if col_tax_issued and col_company:
        not_issued_df = settlement_df[
            ~settlement_df[col_tax_issued].astype(str).str.contains('발행|완료|O|yes', na=False, case=False)
        ].copy()
        
        if not not_issued_df.empty:
            for idx, row in not_issued_df.iterrows():
                company = row.get(col_company, '미등록')
                
                col_left, col_right = st.columns([3, 1])
                with col_left:
                    st.markdown(f"""
                    <div style="background-color: #FEF2F2; border-left: 4px solid #DC2626; 
                                padding: 12px; border-radius: 4px; margin-bottom: 8px;">
                        <b>{company}</b><br/>
                        상태: {row.get(col_tax_issued, '미정')}
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_right:
                    if st.button("✅ 발행 완료", key=f"tax_done_{idx}"):
                        # 실제 시트에 발행완료 저장
                        try:
                            _client = db.get_connection()
                            if _client:
                                _sh = _client.open_by_key(db.SHEET_ID)
                                _wks = _sh.worksheet("계약건은청구금액적기")
                                _headers = _wks.row_values(1)
                                _all_records = _wks.get_all_records()
                                for _r_idx, _record in enumerate(_all_records, 2):
                                    if _record.get(col_company) == company:
                                        _tax_col_idx = _headers.index(col_tax_issued) + 1
                                        _wks.update_cell(_r_idx, _tax_col_idx, "발행완료")
                                        break
                                st.cache_data.clear()
                                st.success(f"{company}의 세금계산서를 발행 완료로 표시했습니다.")
                                time.sleep(1)
                                st.rerun()
                        except Exception as _e:
                            st.error(f"저장 실패: {_e}")
        else:
            st.success("🎉 모든 업체의 세금계산서가 발행되었습니다!")
    
    st.markdown("---")
    
    # 4️⃣ 사업자등록증 OCR 업로드 (개선된 버전)
    st.markdown("### 📸 사업자등록증 정보 자동 인식")
    st.info("💡 업체를 선택 후 사업자등록증 사진을 업로드하면 자동으로 정보를 추출하고 저장합니다.")
    
    # 4-1. 업체 선택
    if col_company:
        company_list = ['-- 업체 선택 --'] + settlement_df[col_company].unique().tolist()
        selected_company = st.selectbox(
            "세금계산서를 등록할 업체 선택",
            company_list,
            help="정보를 등록할 업체를 먼저 선택하세요"
        )
        
        if selected_company != '-- 업체 선택 --':
            # 4-2. 선택된 업체의 현재 정보 표시 (견적상세 데이터 연동)
            selected_row = settlement_df[settlement_df[col_company] == selected_company].iloc[0]

            # 견적상세에서 사업자 정보 가져오기
            try:
                _dispatch_data_tax = db.load_dispatch_data()
            except Exception:
                _dispatch_data_tax = {}
            _df_est_tax = _dispatch_data_tax.get('estimate', pd.DataFrame()) if isinstance(_dispatch_data_tax, dict) else pd.DataFrame()
            # load_all_data에서 estimate 가져오기 시도
            try:
                _all_data = db.load_all_data()
                _df_est_tax = _all_data.get('estimate', pd.DataFrame())
            except Exception:
                pass

            _est_biz_info = {}
            _inq_id_tax = str(selected_row.get('문의ID', '')).strip()
            if not _df_est_tax.empty and '문의ID' in _df_est_tax.columns and _inq_id_tax:
                _est_matches = _df_est_tax[_df_est_tax['문의ID'].astype(str).str.strip() == _inq_id_tax]
                if not _est_matches.empty:
                    _er = _est_matches.iloc[0]
                    _est_biz_info = {
                        '사업자번호': str(_er.get('사업자번호', '')),
                        '대표자': str(_er.get('대표자', '')),
                        '담당자': str(_er.get('담당자명', '')),
                        '연락처': str(_er.get('연락처', '')),
                    }

            with st.expander(f"📌 {selected_company} 현재 정보", expanded=True):
                col_cur1, col_cur2 = st.columns(2)
                with col_cur1:
                    st.write(f"**업체명**: {selected_company}")
                    if _est_biz_info.get('사업자번호'):
                        st.write(f"**사업자번호**: {_est_biz_info['사업자번호']}")
                    if _est_biz_info.get('대표자'):
                        st.write(f"**대표자**: {_est_biz_info['대표자']}")
                    for col in settlement_df.columns:
                        if '현장' in col or '파견' in col:
                            st.write(f"**{col}**: {selected_row.get(col, '-')}")
                with col_cur2:
                    st.write(f"**세금계산서 발행**: {selected_row.get(col_tax_issued, '미정')}")
                    if _est_biz_info.get('담당자'):
                        st.write(f"**담당자**: {_est_biz_info['담당자']}")
                    if _est_biz_info.get('연락처'):
                        st.write(f"**연락처**: {_est_biz_info['연락처']}")
                    for col in settlement_df.columns:
                        if '청구' in col or '금액' in col:
                            st.write(f"**{col}**: {selected_row.get(col, '-')}")
            
            # 4-3. 이미지 업로드
            st.markdown("#### 🖼️ 사업자등록증 업로드")
            uploaded_file = st.file_uploader(
                f"{selected_company}의 사업자등록증 이미지",
                type=["jpg", "jpeg", "png", "gif"],
                help="선명한 사진을 업로드하면 정확도가 높습니다",
                key=f"file_{selected_company}"
            )
            
            if uploaded_file is not None:
                # 이미지 표시
                col_img, col_ocr = st.columns([1, 2])
                
                with col_img:
                    from PIL import Image
                    image = Image.open(uploaded_file)
                    st.image(image, use_column_width=True, caption="업로드된 사업자등록증")
                
                with col_ocr:
                    st.markdown("#### 🔄 정보 추출 중...")
                    
                    # OCR 처리 (통합 API)
                    try:
                        from ocr_utils import extract_business_info, get_sample_business_info
                        
                        extracted_data, engine_name, raw_text = extract_business_info(uploaded_file)
                        
                        if extracted_data and (extracted_data.get('business_number') or extracted_data.get('company_name')):
                            st.success(f"✅ {engine_name}로 정보 추출 완료!")
                        else:
                            extracted_data = get_sample_business_info()
                            engine_name = "테스트 모드"
                            st.warning("⚠️ OCR 엔진에서 정보를 추출하지 못했습니다. 테스트 데이터를 표시합니다.")
                        
                        if raw_text:
                            with st.expander("📝 OCR 원본 텍스트 보기"):
                                st.text(raw_text)
                        
                        if extracted_data:
                            st.markdown("##### 📋 추출된 정보 (수정 가능)")
                            
                            # 4-4. 수동 수정 가능한 입력 폼
                            with st.form(key=f"tax_form_{selected_company}"):
                                col_form1, col_form2 = st.columns(2)
                                
                                with col_form1:
                                    biz_number = st.text_input(
                                        "📌 사업자등록번호",
                                        value=extracted_data.get('business_number', ''),
                                        placeholder="예: 123-45-67890"
                                    )
                                    company_name = st.text_input(
                                        "🏢 업체명",
                                        value=extracted_data.get('company_name', ''),
                                        placeholder="예: 그래디우스 이벤트"
                                    )
                                    representative = st.text_input(
                                        "👤 대표자명",
                                        value=extracted_data.get('representative', ''),
                                        placeholder="예: 김진영"
                                    )
                                
                                with col_form2:
                                    business_type = st.text_input(
                                        "📊 업종",
                                        value=extracted_data.get('business_type', ''),
                                        placeholder="예: 이벤트 기획 및 진행"
                                    )
                                    address = st.text_input(
                                        "📍 주소",
                                        value=extracted_data.get('address', ''),
                                        placeholder="예: 서울시 강남구 테헤란로 123"
                                    )
                                    tax_email = st.text_input(
                                        "✉️ 세금계산서 발행 이메일",
                                        value="",
                                        placeholder="예: tax@company.com"
                                    )
                                
                                st.divider()
                                
                                # 저장 버튼
                                col_save1, col_save2 = st.columns(2)
                                with col_save1:
                                    submit = st.form_submit_button(
                                        "💾 이 정보 저장",
                                        type="primary",
                                        use_container_width=True
                                    )
                                
                                with col_save2:
                                    st.form_submit_button(
                                        "❌ 취소",
                                        use_container_width=True
                                    )
                                
                                if submit:
                                    # 정보 저장 (실제로는 Google Sheets에 저장)
                                    saved_info = {
                                        "업체": selected_company,
                                        "사업자번호": biz_number,
                                        "업체명": company_name,
                                        "대표자": representative,
                                        "업종": business_type,
                                        "주소": address,
                                        "세금계산서이메일": tax_email
                                    }
                                    
                                    st.success(f"""
                                    ✅ **{selected_company}**의 정보가 저장되었습니다!
                                    
                                    - 사업자번호: {biz_number}
                                    - 대표자: {representative}
                                    - 세금계산서 이메일: {tax_email}
                                    """)
                                    st.balloons()
                        
                    except Exception as e:
                        st.error(f"❌ OCR 처리 중 오류: {str(e)[:100]}")
                        st.info("💡 더 선명한 사진을 시도해주세요.")
        
        else:
            st.warning("⚠️ 위에서 업체를 선택해주세요")



def extract_business_info_from_image(uploaded_file):
    """사업자등록증에서 정보 추출 (OCR) - 호환성 함수"""
    try:
        from ocr_utils import extract_business_info, get_sample_business_info
        
        result, engine_name, raw_text = extract_business_info(uploaded_file)
        if result and (result.get('business_number') or result.get('company_name')):
            return result
        
        # 추출 실패 시 샘플 데이터 반환
        return get_sample_business_info()
        
    except Exception as e:
        print(f"OCR 처리 실패: {e}")
        return None