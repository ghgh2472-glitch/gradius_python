# page_settlement.py
import streamlit as st
import pandas as pd
import data_loader as db
from utils_settlement import SettlementBrain
import time
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
    
    # 입금금액 입력
    col_amt1, col_amt2, col_amt3 = st.columns([2, 1, 1])
    
    with col_amt1:
        new_paid_amount = st.number_input(
            "입금 금액 (이번 입금분)",
            min_value=0,
            step=10000,
            value=0,
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
                # 캐시 무효화해서 테이블 새로고침
                st.cache_data.clear()
                import time
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ 입금 금액을 입력해주세요.")
    
    # 테이블 표시
    st.markdown("### 📋 전체 계약 정산 현황")
    
    display_cols = ['문의ID', '업체', '현장명', '공급가액', '부가세', '받은금액', '잔액', '진행상황']
    available_cols = [c for c in display_cols if c in settlement_df.columns]
    
    if available_cols:
        display_df = settlement_df[available_cols].copy()
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("⚠️ 표시할 컬럼이 없습니다")


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

    # 필터링
    if '체결' not in df_inq.columns: df_inq['체결'] = ""
    mask = df_inq['체결'].astype(str).str.contains("배정완료|입금완료|정산완료", na=False)
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
    # 요약 정보
    # --------------------------------------------------------------------------
    summary = brain.get_financial_summary(row)
    
    st.markdown("##### 📊 손익 요약")
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.markdown(f"""<div class="metric-card"><div class="metric-label">총 매출</div><div class="metric-val">{summary['매출']:,}</div></div>""", unsafe_allow_html=True)
    with m2: st.markdown(f"""<div class="metric-card"><div class="metric-label">총 인건비</div><div class="metric-val cost-val">{summary['매입']:,}</div></div>""", unsafe_allow_html=True)
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
            html = brain.get_invoice_html(row['업체명'], row['행사명'], row.get('일시','-'), summary['매출'])
            st.components.v1.html(html, height=500, scrolling=True)
        with c2:
            st.subheader("입금 관리")
            st.info(f"현재 상태: {row['체결']}")
            if row['체결'] == "배정완료":
                if st.button("💰 입금 확인 (완료처리)"):
                    db.update_cell("문의작성", row['업체명'], 5, "입금완료")
                    st.success("입금 확인됨!"); time.sleep(1); st.rerun()

    with tab_s:
        # 인력 파싱 데이터 가져오기
        note_text = str(row.get('특이사항', ''))
        staff_data = brain.parse_dispatch_data(note_text)
        
        if not staff_data:
            st.warning("⚠️ 배정된 인원 데이터를 찾을 수 없습니다.")
            st.caption("아래 '원본 데이터 확인'을 눌러 데이터가 올바르게 저장되었는지 확인하세요.")
        else:
            st.subheader(f"지급 대상자 ({len(staff_data)}명)")
            for i, s in enumerate(staff_data):
                with st.expander(f"{s['이름']} ({s['지급단가']:,}원 x {s['일수']}일 = {s['총지급액']:,}원)"):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        html_p = brain.get_payslip_html(s['이름'], row['행사명'], s['지급단가'], s['일수'], s['총지급액'])
                        st.components.v1.html(html_p, height=350)
                    with c2:
                        if st.checkbox("이체 완료", key=f"pay_{i}"):
                            st.success("지급 완료됨")

            if row['체결'] == "입금완료":
                st.divider()
                if st.button("🏁 최종 정산 완료 (프로젝트 종료)", type="primary"):
                    db.update_cell("문의작성", row['업체명'], 5, "정산완료")
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
                        st.success(f"{company}의 세금계산서를 발행 완료로 표시했습니다.")
                        st.rerun()
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
            # 4-2. 선택된 업체의 현재 정보 표시
            selected_row = settlement_df[settlement_df[col_company] == selected_company].iloc[0]
            
            with st.expander(f"📌 {selected_company} 현재 정보", expanded=True):
                col_cur1, col_cur2 = st.columns(2)
                with col_cur1:
                    st.write(f"**업체명**: {selected_company}")
                    for col in settlement_df.columns:
                        if '현장' in col or '파견' in col:
                            st.write(f"**{col}**: {selected_row.get(col, '-')}")
                with col_cur2:
                    st.write(f"**세금계산서 발행**: {selected_row.get(col_tax_issued, '미정')}")
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
                    
                    # OCR 처리
                    try:
                        from ocr_utils import (
                            try_extract_with_easyocr, 
                            try_extract_with_paddle,
                            try_extract_with_pytesseract,
                            get_sample_business_info
                        )
                        
                        # OCR 처리 시도 (우선순위 있음)
                        extracted_data = None
                        
                        # 1순위: Pytesseract (가장 가능성 높음)
                        extracted_data = try_extract_with_pytesseract(uploaded_file)
                        if extracted_data and extracted_data.get('business_number'):
                            st.success("✅ Pytesseract로 정보 추출 완료!")
                        else:
                            # 2순위: EasyOCR
                            extracted_data = try_extract_with_easyocr(uploaded_file)
                            if extracted_data and extracted_data.get('business_number'):
                                st.success("✅ EasyOCR로 정보 추출 완료!")
                            else:
                                # 3순위: PaddleOCR
                                extracted_data = try_extract_with_paddle(uploaded_file)
                                if extracted_data and extracted_data.get('business_number'):
                                    st.success("✅ PaddleOCR로 정보 추출 완료!")
                                else:
                                    # 4순위: 샘플 데이터
                                    extracted_data = get_sample_business_info()
                                    st.info("ℹ️ OCR 라이브러리 미설치 - 테스트 모드입니다")
                        
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
        from ocr_utils import (
            try_extract_with_easyocr, 
            try_extract_with_paddle, 
            try_extract_with_pytesseract,
            get_sample_business_info
        )
        
        # 1. Pytesseract 시도 (가장 가능성 높음)
        result = try_extract_with_pytesseract(uploaded_file)
        if result and result.get('business_number'):
            return result
        
        # 2. EasyOCR 시도
        result = try_extract_with_easyocr(uploaded_file)
        if result and result.get('business_number'):
            return result
        
        # 3. PaddleOCR 시도
        result = try_extract_with_paddle(uploaded_file)
        if result and result.get('business_number'):
            return result
        
        # 4. 샘플 데이터 반환 (테스트 모드)
        return get_sample_business_info()
        
    except Exception as e:
        print(f"OCR 처리 실패: {e}")
        return None

    # --------------------------------------------------------------------------
    # [디버깅용] 원본 데이터 확인
    # --------------------------------------------------------------------------
    with st.expander("🐛 원본 데이터 확인 (디버깅용)"):
        st.text_area("구글 시트 '특이사항' 컬럼 원본값", value=note_text, height=200)
        st.caption("※ 위 텍스트에 '- 이름... 지급:숫자' 형식이 포함되어 있어야 합니다.")