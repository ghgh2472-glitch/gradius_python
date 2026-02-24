# page_contract.py  v3 — 카드형 목록 + 나중에입력 + 사업자등록증 이미지 업로드
import streamlit as st
import pandas as pd
import utils_contract as uc
import data_loader as db
import status_config as sc
import time
import base64
import io
try:
    from PIL import Image
except ImportError:
    Image = None


def _safe_str(row, key, fb=''):
    v = row.get(key, fb)
    if pd.isna(v): return ''
    return str(v).strip()


def show(data):
    st.title("🤝 계약 최종 승인")

    if st.sidebar.button("🔄 전체 데이터 강제 새로고침"):
        db.invalidate_data()
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
    # 3. 사업자 정보 입력 (좌측 입력 / 우측 이미지)
    # ================================================================
    st.markdown("### 🏢 사업자 정보 입력")
    
    # ── 사업자등록증 이미지 업로드 ──
    uploaded_biz_file = st.file_uploader(
        "📸 사업자등록증 이미지 업로드 (이미지를 보면서 좌측 폼에 입력)",
        type=["jpg", "jpeg", "png", "gif"],
        help="사업자등록증 이미지를 업로드하면 오른쪽에 표시됩니다. 구글 시트에 저장되어 나중에도 불러올 수 있습니다.",
        key=f"biz_upload_{sel_id}"
    )
    
    # base64 변환 (업로드된 경우)
    _biz_b64 = ''
    if uploaded_biz_file is not None:
        try:
            uploaded_biz_file.seek(0)
            _img_bytes = uploaded_biz_file.read()
            # 압축 (50KB 제한 대응 — 시트 셀 제한)
            if Image is not None:
                uploaded_biz_file.seek(0)
                _img = Image.open(uploaded_biz_file)
                # 큰 이미지 리사이즈 (800px 이하)
                _max_dim = 800
                if max(_img.size) > _max_dim:
                    _img.thumbnail((_max_dim, _max_dim), Image.LANCZOS)
                _buf = io.BytesIO()
                _img.save(_buf, format='JPEG', quality=60)
                _img_bytes = _buf.getvalue()
            _biz_b64 = base64.b64encode(_img_bytes).decode('utf-8')
            uploaded_biz_file.seek(0)
        except Exception as _e:
            st.warning(f"이미지 처리 오류: {_e}")

    # 좌우 레이아웃: 좌측 입력 / 우측 이미지
    col_form, col_image = st.columns([1.3, 1])

    with col_image:
        st.markdown("#### 📸 사업자등록증")
        if uploaded_biz_file is not None:
            uploaded_biz_file.seek(0)
            if Image is not None:
                _preview = Image.open(uploaded_biz_file)
                st.image(_preview, use_container_width=True, caption="업로드된 사업자등록증")
                uploaded_biz_file.seek(0)
            else:
                st.info("이미지 미리보기를 위해 Pillow 라이브러리가 필요합니다.")
        else:
            # 기존 저장된 base64 이미지 확인
            _existing_b64 = ''
            try:
                _dispatch_data = db.get_dispatch()
                _settlement_df = _dispatch_data.get('settlement', pd.DataFrame())
                if not _settlement_df.empty and '사업자등록증데이터' in _settlement_df.columns:
                    _match = _settlement_df[_settlement_df['문의ID'].astype(str).str.strip() == sel_id]
                    if not _match.empty:
                        _existing_b64 = str(_match.iloc[0].get('사업자등록증데이터', '')).strip()
                        if _existing_b64 in ('nan', 'None', ''):
                            _existing_b64 = ''
            except:
                pass
            
            if _existing_b64:
                try:
                    _img_data = base64.b64decode(_existing_b64)
                    st.image(_img_data, use_container_width=True, caption="저장된 사업자등록증")
                except:
                    st.caption("저장된 이미지를 표시할 수 없습니다.")
            else:
                st.markdown("""
                <div style="border:2px dashed #cbd5e1; border-radius:12px; padding:40px 20px; text-align:center; color:#94a3b8;">
                    <div style="font-size:48px;">📸</div>
                    <div style="margin-top:10px;">사업자등록증 이미지를<br>업로드하면 여기에 표시됩니다</div>
                    <div style="margin-top:8px; font-size:12px;">이미지를 보면서 좌측 폼에 직접 입력</div>
                </div>
                """, unsafe_allow_html=True)

    with col_form:
        # ── 이전 업체 사업자정보 검색/재사용 ──
        with st.expander("🔍 이전 업체 사업자정보 검색 (기존 데이터 재사용)", expanded=False):
            df_settlement_all = pd.DataFrame()
            try:
                _dispatch_data = db.get_dispatch()
                df_settlement_all = _dispatch_data.get('settlement', pd.DataFrame())
            except Exception:
                pass
            # 정산 데이터에서 이전 사업자번호 보유 업체 추출
            _prev_biz = pd.DataFrame()
            if not df_settlement_all.empty:
                _biz_col = None
                for _c in ['사업자번호', '사업자등록번호']:
                    if _c in df_settlement_all.columns:
                        _biz_col = _c
                        break
                _comp_col = None
                for _c in ['업체명', '법인명', '업체']:
                    if _c in df_settlement_all.columns:
                        _comp_col = _c
                        break
                if _biz_col and _comp_col:
                    _prev_biz = df_settlement_all[df_settlement_all[_biz_col].astype(str).str.strip() != ''][[_comp_col, _biz_col]].drop_duplicates()
                    _prev_biz = _prev_biz.rename(columns={_comp_col: '업체명', _biz_col: '사업자번호'})
                    # 대표자/이메일 추가
                    for _extra in ['대표자', '이메일']:
                        if _extra in df_settlement_all.columns:
                            _prev_biz[_extra] = df_settlement_all.loc[_prev_biz.index, _extra].values
            
            # 고객 DB에서도 검색
            df_client_all = data.get('client', pd.DataFrame())
            if not df_client_all.empty and '업체명' in df_client_all.columns:
                _client_biz_col = None
                for _c in ['사업자번호', '사업자등록번호']:
                    if _c in df_client_all.columns:
                        _client_biz_col = _c
                        break
                if _client_biz_col:
                    _client_with_biz = df_client_all[df_client_all[_client_biz_col].astype(str).str.strip() != ''][['업체명', _client_biz_col]].drop_duplicates()
                    _client_with_biz = _client_with_biz.rename(columns={_client_biz_col: '사업자번호'})
                    if not _client_with_biz.empty:
                        _prev_biz = pd.concat([_prev_biz, _client_with_biz], ignore_index=True).drop_duplicates(subset=['업체명'])
            
            if not _prev_biz.empty:
                _search_q = st.text_input("업체명 검색", key="biz_search_q", placeholder="업체명을 입력하세요")
                if _search_q:
                    _filtered = _prev_biz[_prev_biz['업체명'].astype(str).str.contains(_search_q, na=False, case=False)]
                else:
                    _filtered = _prev_biz
                
                if not _filtered.empty:
                    st.dataframe(_filtered, use_container_width=True, hide_index=True)
                    _sel_biz_options = _filtered['업체명'].tolist()
                    _sel_biz = st.selectbox("재사용할 업체 선택", _sel_biz_options, key="reuse_biz_select")
                    if st.button("✅ 사업자정보 적용", key="apply_prev_biz"):
                        _sel_row = _filtered[_filtered['업체명'] == _sel_biz].iloc[0]
                        st.session_state['_prev_biz_num'] = str(_sel_row.get('사업자번호', '')).strip()
                        st.session_state['_prev_biz_ceo'] = str(_sel_row.get('대표자', '')).strip() if '대표자' in _sel_row.index else ''
                        st.session_state['_prev_biz_company'] = str(_sel_row.get('업체명', '')).strip()
                        st.session_state['_prev_biz_email'] = str(_sel_row.get('이메일', '')).strip() if '이메일' in _sel_row.index else ''
                        st.success(f"✅ {_sel_biz}의 사업자정보가 적용되었습니다.")
                        st.rerun()
                else:
                    st.info("검색 결과가 없습니다.")
            else:
                st.info("이전 사업자정보 데이터가 없습니다.")

    # ── "나중에 입력하기" 토글 ──
    skip_biz = st.checkbox("⏭️ 사업자 정보 나중에 입력 (개인고객 등)", key="skip_biz_info")

    if skip_biz:
        st.info("💡 사업자 정보 없이 계약을 진행합니다. 나중에 정산 페이지에서 입력할 수 있습니다.")
        biz_num = ""
        biz_ceo = ""
        company_name = _safe_str(selected_project, '업체명')
        email = ""
        biz_contact = ""
        biz_content = ""
        biz_invoice_note = ""
    else:
        with col_form:
            default_biz = st.session_state.get('_prev_biz_num', str(match_est.get('사업자번호', '')) if not match_est.empty else '')
            default_ceo = st.session_state.get('_prev_biz_ceo', str(match_est.get('대표자', '')) if not match_est.empty else '')
            default_company = st.session_state.get('_prev_biz_company', str(match_est.get('법인명', '')) if not match_est.empty else '')

            c1, c2 = st.columns(2)
            biz_num = c1.text_input("사업자등록번호", value=default_biz, key="biz_num_input")
            biz_ceo = c2.text_input("대표자 성명", value=default_ceo, key="biz_ceo_input")

            c3, c4 = st.columns(2)
            company_name = c3.text_input("법인명(단체명)", value=default_company, placeholder="발주처 정식 법인명", key="company_name_input")
            default_email = st.session_state.get('_prev_biz_email', str(match_est.get('이메일', '')) if not match_est.empty else '')
            email = c4.text_input("세금계산서 발행 이메일", value=default_email, placeholder="example@company.com", key="email_input")

            c5, c6 = st.columns(2)
            default_contact = _safe_str(selected_project, '연락처')
            biz_contact = c5.text_input("연락처", value=default_contact, placeholder="010-0000-0000", key="biz_contact_input")
            biz_content = c6.text_input("내용(품목)", value=_safe_str(selected_project, '행사명'), placeholder="인력파견 등", key="biz_content_input")

            biz_invoice_note = st.text_area("발행관련 요청사항", placeholder="계산서 발행일 지정, 분할 발행 등 요청사항을 입력하세요", key="invoice_note_input", height=80)

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
                    st.toast(f"✅ 계약 상태가 '{sc.STATUS_FLOW[2]}'로 변경되었습니다")

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
                    "연락처": biz_contact if not skip_biz else '',
                    "내용(품목)": biz_content if not skip_biz else _safe_str(selected_project, '행사명'),
                    "발행요청사항": biz_invoice_note if not skip_biz else '',
                    "계약일": pd.Timestamp.now().strftime("%Y-%m-%d"),
                    "공급가액": safe_int(match_est.get('공급가액', 0)),
                    "부가세": safe_int(match_est.get('부가세', 0)),
                    "합계금액": safe_int(match_est.get('합계금액', 0)),
                    "상태": "계약체결",
                    "사업자등록증데이터": _biz_b64,
                }

                result = db.save_settlement_record(settlement_data, site_info=site_info)
                if result:
                    st.toast("✅ 계약체결 완료! 청구 시스템에 등록되었습니다")
                    st.info(f"📊 등록 금액: 공급가액 {settlement_data['공급가액']:,}원 + 부가세 {settlement_data['부가세']:,}원 = 청구금액 {settlement_data['합계금액']:,}원")
                else:
                    st.error("❌ 청구 시스템 저장 실패")

                # ── 고객정보 시트에도 사업자 정보 업데이트 ──
                if not skip_biz and biz_num:
                    try:
                        _client = db.get_connection()
                        if _client:
                            _sh = _client.open_by_key(db.SHEET_ID)
                            _cust_wks = _sh.worksheet("고객정보")
                            _cust_headers = [str(h).strip() for h in _cust_wks.row_values(1)]
                            _cust_all = _cust_wks.get_all_values()
                            
                            # 업체명으로 매칭
                            _company = _safe_str(selected_project, '업체명')
                            _target_row = None
                            if '업체명' in _cust_headers:
                                _ci = _cust_headers.index('업체명')
                                for _ri in range(1, len(_cust_all)):
                                    if str(_cust_all[_ri][_ci]).strip() == _company:
                                        _target_row = _ri + 1
                                        break
                            
                            if _target_row:
                                from gspread.cell import Cell
                                _cells = []
                                _cust_map = {
                                    '사업자등록번호': biz_num,
                                    '대표자명': biz_ceo,
                                    '세금계산서이메일': email,
                                    '담당자연락처': biz_contact,
                                }
                                for _hdr, _val in _cust_map.items():
                                    if _hdr in _cust_headers and _val:
                                        _col_i = _cust_headers.index(_hdr) + 1
                                        _cells.append(Cell(row=_target_row, col=_col_i, value=str(_val).strip()))
                                if _cells:
                                    _cust_wks.update_cells(_cells, value_input_option='RAW')
                                    st.toast("✅ 고객정보 시트에도 사업자 정보 업데이트 완료")
                    except Exception as _ce:
                        st.warning(f"⚠️ 고객정보 업데이트 실패 (계약은 정상 저장됨): {_ce}")

                st.info("📧 다음 단계: 세금계산서 발행 준비 완료")
                # 이전 업체 검색 임시값 정리
                for k in ['_prev_biz_num', '_prev_biz_ceo', '_prev_biz_company', '_prev_biz_email']:
                    st.session_state.pop(k, None)
                db.invalidate_data()
                time.sleep(0.5)
                st.rerun()

            except Exception as e:
                st.error(f"저장 중 오류: {e}")