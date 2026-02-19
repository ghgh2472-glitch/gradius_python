# page_contract.py
import streamlit as st
import pandas as pd
import utils_contract as uc 
import data_loader as db
from datetime import datetime
import time

# ==============================================================================
# 1. 스타일링
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 95% !important; padding-top: 1rem; }
        .stButton>button { 
            border-radius: 8px; font-weight: 700; height: 50px; 
            background-color: #1e40af; color: white; border: none;
            transition: all 0.3s;
        }
        .stButton>button:hover { background-color: #1d4ed8; box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3); }
        .section-title {
            font-size: 18px; font-weight: 800; color: #1e293b;
            margin: 25px 0 12px 0; border-left: 5px solid #3b82f6;
            padding-left: 12px;
        }
        .info-label { font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 메인 화면
# ==============================================================================
def show(data):
    apply_styles()
    
    st.title("🤝 계약 최종 승인 및 관리")
    st.caption("견적이 확정된 프로젝트의 사업자 정보를 보완하여 최종 계약을 체결합니다.")

    # 데이터 로드 (문의작성, 견적상세)
    df_inq = data.get('inq', pd.DataFrame())
    df_est = data.get('estimate', pd.DataFrame()) 
    
    # 상태가 '견적'인 건만 필터링 (계약 대기열)
    pending = pd.DataFrame()
    if not df_inq.empty and '상태' in df_inq.columns:
        pending = df_inq[df_inq['상태'] == '견적'].sort_values('작성일', ascending=False)

    # 레이아웃 분할
    col_list, col_main = st.columns([1, 2.3])
    selected_project = None

    # [좌측: 승인 대기 목록]
    with col_list:
        st.markdown("### 📂 승인 대기열")
        if pending.empty:
            st.info("현재 계약 승인 대기 중인 프로젝트가 없습니다.")
            if st.button("🔄 리스트 새로고침"): st.rerun()
        else:
            # 선택 인터페이스
            options = {row['문의ID']: f"[{row['업체명']}] {row['행사명']}" for _, row in pending.iterrows()}
            sel_id = st.radio(
                "프로젝트 선택", 
                options.keys(), 
                format_func=lambda x: options[x],
                label_visibility="collapsed"
            )
            selected_project = pending[pending['문의ID'] == sel_id].iloc[0]

    # [우측: 계약 상세 정보 및 승인 폼]
    with col_main:
        if selected_project is not None:
            target_id = str(selected_project.get('문의ID', ''))
            
            # 1. 고도화된 브리핑 리포트 출력 (HTML)
            report_html = uc.get_contract_summary_html(selected_project, df_est)
            st.markdown(report_html, unsafe_allow_html=True)
            
            # 2. 견적 데이터에서 기존 정보 상속 (사업자번호, 대표자 등)
            est_match = df_est[df_est['문의ID'].astype(str) == target_id] if not df_est.empty else pd.DataFrame()
            
            # 시트의 기존 값 미리 채우기
            exist_biz_num = est_match.iloc[-1].get('사업자번호', '') if not est_match.empty else ""
            exist_ceo = est_match.iloc[-1].get('대표자', '') if not est_match.empty else ""

            # 3. 사업자 정보 입력 섹션
            st.markdown('<div class="section-title">🏢 계약처(Client) 정보 보완</div>', unsafe_allow_html=True)
            with st.container(border=True):
                c1, c2 = st.columns(2)
                biz_num = c1.text_input("사업자등록번호", value=exist_biz_num, placeholder="000-00-00000")
                biz_ceo = c2.text_input("대표자 성명", value=exist_ceo, placeholder="홍길동")
                
                biz_email = st.text_input("전자세금계산서 수신 이메일", placeholder="tax@company.com")
                biz_addr = st.text_input("사업자 주소지 (계약서 기재용)", value=selected_project.get('장소', ''))

            # 4. 프로세스 마일스톤 체크
            st.markdown('<div class="section-title">📜 리스크 및 프로세스 체크</div>', unsafe_allow_html=True)
            with st.container(border=True):
                ck1, ck2, ck3 = st.columns(3)
                is_sent = ck1.checkbox("📤 계약서 발송")
                is_signed = ck2.checkbox("📥 날인본 회수")
                is_ready = ck3.checkbox("✅ 운영팀 전달")
                
                if is_signed:
                    st.file_uploader("최종 계약서 보관(PDF)", type=['pdf'], help="회수된 날인본을 업로드하여 아카이브합니다.")

            # 5. 최종 체결 버튼
            st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
            if st.button("🤝 최종 계약 체결 및 운영 확정", use_container_width=True):
                # 유효성 검사 (utils_contract.py)
                val_errors = uc.validate_contract_ready(biz_num, biz_ceo, is_sent)
                
                if val_errors:
                    for err in val_errors: st.error(f"⚠️ {err}")
                else:
                    with st.spinner("계약 데이터를 시트에 완벽하게 기록 중입니다..."):
                        # [핵심 로직] 기존 견적 데이터에 사업자 정보 덮어쓰기
                        # db.save_estimate_details 함수가 ID 매칭 시 업데이트 하도록 설계됨
                        final_data = {
                            "문의ID": target_id,
                            "업체명": selected_project.get('업체명', ''),
                            "행사명": selected_project.get('행사명', ''),
                            "사업자번호": biz_num,
                            "대표자": biz_ceo,
                            # 금액 정보는 기존 시트값 유지 (안전 방어)
                            "공급가액": uc.safe_int(est_match.iloc[-1].get('공급가액', 0)) if not est_match.empty else 0,
                            "부가세": uc.safe_int(est_match.iloc[-1].get('부가세', 0)) if not est_match.empty else 0,
                            "합계금액": uc.safe_int(est_match.iloc[-1].get('합계금액', 0)) if not est_match.empty else 0,
                            "매입원가": uc.safe_int(est_match.iloc[-1].get('매입원가', 0)) if not est_match.empty else 0
                        }
                        
                        # 1) 견적상세 시트 업데이트
                        success_save = db.save_estimate_details(final_data)
                        # 2) 문의작성 시트 상태 '체결'로 변경
                        success_status = db.update_status(target_id, "체결")
                        
                        if success_save and success_status:
                            st.balloons()
                            st.success(f"🎊 [계약 체결] {selected_project['업체명']} 프로젝트가 운영 단계로 성공적으로 전환되었습니다!")
                            time.sleep(2)
                            db.invalidate_data()
                            st.rerun()
                        else:
                            st.error("시트 저장 중 통신 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        else:
            # 선택된 건이 없을 때의 가이드
            st.markdown("""
            <div style="background-color: #f8fafc; border: 2px dashed #e2e8f0; border-radius: 15px; padding: 50px; text-align: center; color: #64748b;">
                <div style="font-size: 40px; margin-bottom: 20px;">👈</div>
                <div style="font-size: 18px; font-weight: 700;">승인할 프로젝트를 선택해 주세요</div>
                <div style="font-size: 14px; margin-top: 10px;">좌측 대기열에서 '견적 완료' 상태의 건을 선택하면<br>상세 계약 정보 보완 및 체결 처리가 가능합니다.</div>
            </div>
            """, unsafe_allow_html=True)