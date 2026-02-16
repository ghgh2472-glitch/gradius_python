# page_contract.py  v3 — 카드형 목록 + OCR + 나중에입력
import streamlit as st
import pandas as pd
import utils_contract as uc
import data_loader as db
import status_config as sc
import time


def _safe_str(row, key, fb=''):
    v = row.get(key, fb)
    if pd.isna(v): return ''
    return str(v).strip()


def show(data):
    st.title("🤝 계약 최종 승인")

    if st.sidebar.button("🔄 전체 데이터 강제 새로고침"):
        st.cache_data.clear()
        st.rerun()

    df_inq = data.get('inq', pd.DataFrame())
    df_est = data.get('estimate', pd.DataFrame())

    pending = df_inq[df_inq['상태'] == sc.STATUS_FLOW[1]] if not df_inq.empty else pd.DataFrame()
    if pending.empty:
        st.info("✅ 승인 대기 중인 계약이 없습니다.")
        return

    # ================================================================
    # 1. 카드형 승인 대기 목록
    # ================================================================
    st.markdown(f"### 📋 승인 대기 ({len(pending)}건)")
    st.caption("카드를 클릭하면 상세 보기가 열립니다.")

    # 카드형 목록 (3열)
    cards_per_row = 3
    rows_list = list(pending.iterrows())
    for chunk_start in range(0, len(rows_list), cards_per_row):
        chunk = rows_list[chunk_start:chunk_start + cards_per_row]
        cols = st.columns(cards_per_row)
        for ci, (_, row) in enumerate(chunk):
            iid = str(row['문의ID']).strip()
            client = _safe_str(row, '업체명')
            event = _safe_str(row, '행사명')
            site = _safe_str(row, '장소', _safe_str(row, '행사장소'))
            sdate = _safe_str(row, '행사시작일')
            edate = _safe_str(row, '행사종료일')
            date_txt = f"{sdate}~{edate}" if sdate and edate else sdate

            # 견적 금액
            est_total = 0
            if not df_est.empty and '문의ID' in df_est.columns:
                m = df_est[df_est['문의ID'].astype(str).str.strip() == iid]
                if not m.empty:
                    est_total = uc.safe_int(m.iloc[0].get('합계금액', 0))

            with cols[ci]:
                is_selected = st.session_state.get('contract_sel_id') == iid
                border_color = "#3b82f6" if is_selected else "#e2e8f0"
                bg = "#eff6ff" if is_selected else "#ffffff"
                st.markdown(f"""
                <div style="background:{bg};border:2px solid {border_color};border-radius:10px;padding:14px;margin-bottom:8px;min-height:130px;">
                    <div style="font-size:15px;font-weight:800;color:#1e293b;">{client}</div>
                    <div style="font-size:13px;color:#475569;margin-top:4px;">{event}</div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:6px;">📍 {site or '-'}</div>
                    <div style="font-size:11px;color:#94a3b8;">📅 {date_txt or '-'}</div>
                    <div style="font-size:16px;font-weight:900;color:#1e40af;margin-top:8px;text-align:right;">{est_total:,}원</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"📋 상세보기", key=f"card_{iid}", use_container_width=True):
                    st.session_state['contract_sel_id'] = iid
                    st.rerun()

    # ── 선택된 프로젝트 ──
    sel_id = st.session_state.get('contract_sel_id')
    if not sel_id:
        # 첫 번째를 기본 선택
        sel_id = str(pending.iloc[0]['문의ID']).strip()
        st.session_state['contract_sel_id'] = sel_id

    matched = pending[pending['문의ID'].astype(str).str.strip() == sel_id]
    if matched.empty:
        sel_id = str(pending.iloc[0]['문의ID']).strip()
        st.session_state['contract_sel_id'] = sel_id
        matched = pending[pending['문의ID'].astype(str).str.strip() == sel_id]

    selected_project = matched.iloc[0]

    st.markdown("---")

    # ================================================================
    # 2. 카드형 견적+문의 요약
    # ================================================================
    report_html = uc.get_contract_summary_html(selected_project, df_est)
    st.markdown(report_html, unsafe_allow_html=True)

    # ── 견적 품목 상세 ──
    est_items = db.load_estimate_items(sel_id)
    if not est_items.empty:
        st.markdown("### 📦 견적 품목 상세")
        display_items = est_items.copy()
        for col in ['매출단가', '매입단가']:
            if col in display_items.columns:
                display_items[col] = display_items[col].apply(lambda x: f"{uc.safe_int(x):,}")
        display_items = display_items.rename(columns={'매입단가': '지급단가'})
        st.dataframe(display_items, use_container_width=True, hide_index=True)

    # ── 견적 데이터 ──
    match_est = pd.Series()
    if not df_est.empty and '문의ID' in df_est.columns:
        match_idx = df_est['문의ID'].astype(str).str.strip() == sel_id
        if match_idx.any():
            match_est = df_est[match_idx].iloc[0]

    if match_est.empty:
        st.warning("⚠️ 이 프로젝트의 견적 데이터가 없습니다. 견적서를 먼저 작성해주세요.")

    st.markdown("---")

    # ================================================================
    # 3. 사업자 정보 입력 (OCR + 나중에 입력)
    # ================================================================
    st.markdown("### 🏢 사업자 정보 입력")

    # ── OCR 사업자등록증 업로드 ──
    with st.expander("📸 사업자등록증 업로드 (자동 인식)", expanded=False):
        uploaded = st.file_uploader("사업자등록증 이미지", type=['jpg', 'jpeg', 'png'], key=f"biz_ocr_{sel_id}")
        if uploaded:
            from PIL import Image
            col_img, col_res = st.columns([1, 2])
            with col_img:
                st.image(Image.open(uploaded), use_column_width=True, caption="업로드된 사업자등록증")
            with col_res:
                try:
                    from ocr_utils import try_extract_with_pytesseract, try_extract_with_easyocr, get_sample_business_info
                    extracted = try_extract_with_pytesseract(uploaded)
                    if not extracted or not extracted.get('business_number'):
                        extracted = try_extract_with_easyocr(uploaded)
                    if not extracted or not extracted.get('business_number'):
                        extracted = get_sample_business_info()
                        st.info("ℹ️ OCR 라이브러리 미설치 — 테스트 모드")
                    else:
                        st.success("✅ 정보 추출 완료!")

                    if extracted:
                        st.session_state['_ocr_biz_num'] = extracted.get('business_number', '')
                        st.session_state['_ocr_ceo'] = extracted.get('representative', '')
                        st.session_state['_ocr_company'] = extracted.get('company_name', '')
                        st.markdown(f"""
                        **추출 결과:**
                        - 사업자번호: `{extracted.get('business_number', '')}`
                        - 대표자: `{extracted.get('representative', '')}`
                        - 법인명: `{extracted.get('company_name', '')}`
                        """)
                except Exception as e:
                    st.error(f"OCR 오류: {e}")

    # ── "나중에 입력하기" 토글 ──
    skip_biz = st.checkbox("⏭️ 사업자 정보 나중에 입력 (개인고객 등)", key="skip_biz_info")

    if skip_biz:
        st.info("💡 사업자 정보 없이 계약을 진행합니다. 나중에 정산 페이지에서 입력할 수 있습니다.")
        biz_num = ""
        biz_ceo = ""
        company_name = _safe_str(selected_project, '업체명')
        email = ""
    else:
        # OCR 결과가 있으면 자동 채움
        default_biz = st.session_state.get('_ocr_biz_num', str(match_est.get('사업자번호', '')) if not match_est.empty else '')
        default_ceo = st.session_state.get('_ocr_ceo', str(match_est.get('대표자', '')) if not match_est.empty else '')
        default_company = st.session_state.get('_ocr_company', '')

        c1, c2 = st.columns(2)
        biz_num = c1.text_input("사업자등록번호", value=default_biz, key="biz_num_input")
        biz_ceo = c2.text_input("대표자 성명", value=default_ceo, key="biz_ceo_input")

        c3, c4 = st.columns(2)
        company_name = c3.text_input("법인명(단체명)", value=default_company, placeholder="발주처 정식 법인명", key="company_name_input")
        email = c4.text_input("세금계산서 발행 이메일", placeholder="example@company.com", key="email_input")

    is_sent = st.checkbox("계약서 발송 완료 확인", key="is_sent_check")

    if st.button("✅ 계약 체결 및 확정", type="primary", use_container_width=True, key="confirm_contract"):
        # 유효성 검사 (나중에 입력이 아닌 경우만)
        if not skip_biz:
            errs = uc.validate_contract_ready(biz_num, biz_ceo, is_sent)
            if errs:
                for e in errs: st.error(e)
                st.stop()
            if not email:
                st.error("세금계산서 발행 이메일을 입력해주세요.")
                st.stop()
            if not company_name:
                st.error("법인명(단체명)을 입력해주세요.")
                st.stop()
        else:
            if not is_sent:
                st.error("계약서 발송 여부를 체크하세요.")
                st.stop()

        with st.spinner("계약 정보 저장 중..."):
            try:
                if db.update_cell("문의작성", sel_id, col_name="상태", value=sc.STATUS_FLOW[2]):
                    st.success(f"✅ 계약 상태가 '{sc.STATUS_FLOW[2]}'로 변경되었습니다")

                def safe_int(val):
                    try:
                        if pd.isna(val): return 0
                        if isinstance(val, str): val = val.replace(',', '').replace('원', '').strip()
                        return int(float(val)) if val else 0
                    except: return 0

                start_date = _safe_str(selected_project, '행사시작일')
                end_date = _safe_str(selected_project, '행사종료일')
                dispatch_date = f"{start_date} ~ {end_date}" if start_date and end_date else start_date

                site_info = {
                    "현장명": _safe_str(selected_project, '행사명'),
                    "책임자": _safe_str(selected_project, '담당자'),
                    "현장주소": _safe_str(selected_project, '행사장소', _safe_str(selected_project, '장소')),
                    "파견일자": dispatch_date
                }

                settlement_data = {
                    "문의ID": sel_id,
                    "업체명": _safe_str(selected_project, '업체명'),
                    "법인명": company_name,
                    "행사명": _safe_str(selected_project, '행사명'),
                    "현장주소": _safe_str(selected_project, '행사장소', _safe_str(selected_project, '장소')),
                    "사업자번호": biz_num,
                    "대표자": biz_ceo,
                    "이메일": email,
                    "계약일": pd.Timestamp.now().strftime("%Y-%m-%d"),
                    "공급가액": safe_int(match_est.get('공급가액', 0)),
                    "부가세": safe_int(match_est.get('부가세', 0)),
                    "합계금액": safe_int(match_est.get('합계금액', 0)),
                    "상태": "계약체결"
                }

                result = db.save_settlement_record(settlement_data, site_info=site_info)
                if result:
                    st.success("✅ 계약건이 청구 시스템에 등록되었습니다")
                    st.info(f"📊 등록 금액: 공급가액 {settlement_data['공급가액']:,}원 + 부가세 {settlement_data['부가세']:,}원 = 청구금액 {settlement_data['합계금액']:,}원")
                else:
                    st.error("❌ 청구 시스템 저장 실패")

                st.info("📧 다음 단계: 세금계산서 발행 준비 완료")
                # OCR 임시값 정리
                for k in ['_ocr_biz_num', '_ocr_ceo', '_ocr_company']:
                    st.session_state.pop(k, None)
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

            except Exception as e:
                st.error(f"저장 중 오류: {e}")