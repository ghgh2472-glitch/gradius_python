# page_contract.py
import streamlit as st
import pandas as pd
import utils_contract as uc 
import data_loader as db
import status_config as sc
import time

def show(data):
    st.title("🤝 계약 최종 승인")
    
    # [근본 해결 1] 강제 새로고침 버튼 추가 (캐시 무력화)
    if st.sidebar.button("🔄 전체 데이터 강제 새로고침"):
        st.cache_data.clear()
        st.rerun()

    df_inq = data.get('inq', pd.DataFrame())
    df_est = data.get('estimate', pd.DataFrame()) 
    
    pending = df_inq[df_inq['상태'] == sc.STATUS_FLOW[1]] if not df_inq.empty else pd.DataFrame()  # '견적'

    col_list, col_main = st.columns([1, 2.5])

    with col_list:
        st.subheader(" 승인 대기")
        if pending.empty:
            st.info("대기중인 계약이 없습니다.")
            return
        
        options = {str(row['문의ID']).strip(): f"{row['업체명']} | {row['행사명']}" for _, row in pending.iterrows()}
        sel_id = st.radio("프로젝트", options.keys(), format_func=lambda x: options[x])
        selected_project = pending[pending['문의ID'].astype(str).str.strip() == sel_id].iloc[0]

    with col_main:
        # 견적 리포트
        report_html = uc.get_contract_summary_html(selected_project, df_est)
        st.markdown(report_html, unsafe_allow_html=True)
        
        # 견적 시트에서 해당 프로젝트의 원본 행을 정확히 찾아냄
        match_est = pd.Series()
        sel_id_clean = str(sel_id).strip()
        if not df_est.empty and '문의ID' in df_est.columns:
            match_idx = df_est['문의ID'].astype(str).str.strip() == sel_id_clean
            if match_idx.any():
                match_est = df_est[match_idx].iloc[0]
        
        if match_est.empty:
            st.warning("⚠️ 이 프로젝트의 견적 데이터가 없습니다. 견적서를 먼저 작성해주세요.")

        st.markdown("### 🏢 사업자 정보 입력")
        with st.form("contract_form"):
            c1, c2 = st.columns(2)
            biz_num = c1.text_input("사업자등록번호", value=str(match_est.get('사업자번호', '')) if not match_est.empty else "")
            biz_ceo = c2.text_input("대표자 성명", value=str(match_est.get('대표자', '')) if not match_est.empty else "")
            
            # 법인명(단체명) - 새로 추가
            c3, c4 = st.columns(2)
            company_name = c3.text_input("법인명(단체명)", placeholder="발주처의 정식 법인명", value="")
            
            # 세금계산서 발행을 위한 이메일
            email = c4.text_input("세금계산서 발행 이메일", placeholder="example@company.com", value="")
            
            is_sent = st.checkbox("계약서 발송 완료 확인")
            
            submit = st.form_submit_button("계약 체결 및 확정", use_container_width=True)
            
            if submit:
                errs = uc.validate_contract_ready(biz_num, biz_ceo, is_sent)
                if errs:
                    for e in errs: st.error(e)
                elif not email:
                    st.error("세금계산서 발행 이메일을 입력해주세요.")
                elif not company_name:
                    st.error("법인명(단체명)을 입력해주세요.")
                else:
                    with st.spinner("계약 정보 저장 중..."):
                        try:
                            # 1. 문의작성 시트 - 상태를 "체결"로 변경
                            if db.update_cell("문의작성", sel_id, col_name="상태", value=sc.STATUS_FLOW[2]):  # '체결'
                                st.success(f"✅ 계약 상태가 '{sc.STATUS_FLOW[2]}'로 변경되었습니다")
                            
                            # 2. 계약건은 청구금액적기 시트에 계약 정보 저장
                            # 안전한 정수 변환
                            def safe_int(val):
                                try:
                                    if pd.isna(val): return 0
                                    if isinstance(val, str):
                                        val = val.replace(',', '').replace('원', '').strip()
                                    return int(float(val)) if val else 0
                                except:
                                    return 0
                            
                            # 현장 정보 수집
                            # 파견일자: 행사시작일 ~ 행사종료일 형식
                            start_date = str(selected_project.get('행사시작일', '')).strip()
                            end_date = str(selected_project.get('행사종료일', '')).strip()
                            dispatch_date = f"{start_date} ~ {end_date}" if start_date and end_date else start_date
                            
                            site_info = {
                                "현장명": str(selected_project.get('행사명', '')).strip(),
                                "책임자": str(selected_project.get('담당자', '')).strip(),
                                "현장주소": str(selected_project.get('행사장소', '')).strip(),
                                "파견일자": dispatch_date
                            }
                            
                            settlement_data = {
                                "문의ID": str(sel_id).strip(),
                                "업체명": str(selected_project.get('업체명', '')).strip(),
                                "법인명": str(company_name).strip(),  # 새로 추가
                                "행사명": str(selected_project.get('행사명', '')).strip(),
                                "현장주소": str(selected_project.get('행사장소', '')).strip(),  # 새로 추가
                                "사업자번호": str(biz_num).strip(),
                                "대표자": str(biz_ceo).strip(),
                                "이메일": str(email).strip(),
                                "계약일": pd.Timestamp.now().strftime("%Y-%m-%d"),
                                "공급가액": safe_int(match_est.get('공급가액', 0)),
                                "부가세": safe_int(match_est.get('부가세', 0)),
                                "합계금액": safe_int(match_est.get('합계금액', 0)),
                                "상태": "계약체결"
                            }
                            
                            result = db.save_settlement_record(settlement_data, site_info=site_info)
                            if result:
                                st.success("✅ 계약건이 청구 시스템에 등록되었습니다")
                                st.info(f"📊 등록된 금액: 공급가액 {settlement_data['공급가액']:,}원 + 부가세 {settlement_data['부가세']:,}원 = 청구금액 {settlement_data['합계금액']:,}원")
                            else:
                                st.error("❌ 청구 시스템 저장에 실패했습니다. 정보를 확인하고 다시 시도해주세요.")
                            
                            st.info("📧 다음 단계: 세금계산서 발행 준비 완료")
                            st.cache_data.clear()
                            import time; time.sleep(1)
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"저장 중 오류 발생: {e}")