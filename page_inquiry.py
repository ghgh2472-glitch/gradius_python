# page_inquiry.py
import streamlit as st
import pandas as pd
import data_loader as db
import status_config as sc
from datetime import datetime
import uuid
from utils_inquiry import InquiryParser

# ==============================================================================
# 1. 스타일링
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 900px; padding-top: 2rem; }
        .form-box { background-color: white; padding: 30px; border-radius: 12px; border: 1px solid #e5e7eb; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        .header-text { font-size: 18px; font-weight: bold; color: #111827; margin-bottom: 15px; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; }
        .label-text { font-size: 12px; color: #6b7280; margin-bottom: 2px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 저장 로직 (콜백 함수) - 에러 해결의 핵심!
# ==============================================================================
def save_inquiry():
    """
    저장 버튼을 눌렀을 때 실행되는 함수입니다.
    여기서는 위젯 렌더링과 상관없이 세션 상태를 자유롭게 조작할 수 있습니다.
    """
    # 1. 업체명 결정 로직
    sel_client = st.session_state.get('form_client_select')
    new_client = st.session_state.get('form_new_client_name')
    
    final_client_name = ""
    is_new_client = False
    
    if sel_client == "(신규 입력)":
        final_client_name = new_client
        is_new_client = True
    else:
        final_client_name = sel_client

    # 2. 필수값 유효성 검사
    if not final_client_name:
        st.error("🚨 업체명을 확인해주세요.")
        return
    if not st.session_state.get('form_evt_name'):
        st.error("🚨 행사명을 입력해주세요.")
        return

    # 3. 데이터 준비
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_id = str(uuid.uuid4())[:8]

    # [매우 중요] 구글 시트 '문의작성' 탭의 23개 헤더 순서와 100% 일치시킴
    # 1.문의ID | 2.작성일 | 3.업체명 | 4.담당자 | 5.연락처 | 6.행사명 | 7.장소 |
    # 8.행사시작일 | 9.행사종료일 | 10.행사시간 | 11.서비스종류 | 12.필요인력 |
    # 13.페이 | 14.상태 | 15.특이사항 | 16.비고 | 17.만족도 | 18.관계 |
    # 19.구분 | 20.진행여부 | 21.진행상태 | 22.인력세팅현황 | 23.상담내용및 고객성향
    
    inq_row = [
        new_id,                                      # 1. 문의ID
        now_str,                                     # 2. 작성일
        final_client_name,                           # 3. 업체명
        st.session_state.get('form_manager', ''),    # 4. 담당자
        st.session_state.get('form_contact', ''),    # 5. 연락처
        st.session_state.get('form_evt_name', ''),   # 6. 행사명
        st.session_state.get('form_evt_place', ''),  # 7. 장소
        st.session_state.get('form_date_start', ''), # 8. 행사시작일
        st.session_state.get('form_date_end', ''),   # 9. 행사종료일
        st.session_state.get('form_evt_time', ''),   # 10. 행사시간
        st.session_state.get('form_service', ''),    # 11. 서비스종류
        st.session_state.get('form_headcount', ''),  # 12. 필요인력
        st.session_state.get('form_pay', ''),        # 13. 페이
        sc.STATUS_FLOW[0],                              # 14. 상태 ('접수')
        st.session_state.get('form_note', ''),       # 15. 특이사항
        "",                                          # 16. 비고
        "",                                          # 17. 만족도
        "",                                          # 18. 관계
        "",                                          # 19. 구분
        "",                                          # 20. 진행여부
        "",                                          # 21. 진행상태
        "",                                          # 22. 인력세팅현황
        "",                                          # 23. 상담내용및 고객성향
    ]

    # 4. 신규 업체면 고객 DB에 추가
    if is_new_client:
        # 헤더: 업체명, 대표자명, 사업자번호, 업태, 종목, 주소, 이메일, 담당자, 연락처, 메모
        c_row = [
            final_client_name, "", "", "", "", "", "", 
            st.session_state.get('form_manager', ''), 
            st.session_state.get('form_contact', ''), 
            f"최초등록: {now_str}"
        ]
        db.append_row("client", c_row)

    # 5. 문의 저장 실행
    res, msg = db.append_row("inq", inq_row)

    if res:
        # 성공 시 입력 폼 초기화 (여기서 초기화하면 에러 안 남)
        keys_to_clear = [
            'form_evt_name', 'form_evt_place', 'form_date_start', 'form_date_end', 
            'form_evt_time', 'form_service', 'form_headcount', 'form_pay',
            'form_contact', 'form_manager', 'form_note', 'form_new_client_name'
        ]
        for k in keys_to_clear:
            st.session_state[k] = ""
        
        # 성공 메시지를 위한 플래그 설정
        st.session_state['save_success'] = True
    else:
        st.error(f"저장 실패: {msg}")

# ==============================================================================
# 3. 메인 화면
# ==============================================================================
def show(data):
    apply_styles()
    st.title("📝 신규 문의 접수")
    
    # 저장 성공 메시지 처리 (rerun 후 표시)
    if st.session_state.get('save_success'):
        st.balloons()
        st.success("✅ 문의가 정상적으로 접수되었습니다!")
        st.session_state['save_success'] = False # 메시지 1회만 표시
    
    parser = InquiryParser()
    
    # 고객 리스트 로드
    df_client = data.get('client', pd.DataFrame())
    client_list = []
    if not df_client.empty and '업체명' in df_client.columns:
        client_list = df_client['업체명'].unique().tolist()

    # --------------------------------------------------------------------------
    # 카톡 자동 분석 섹션
    # --------------------------------------------------------------------------
    with st.expander("📩 카톡/문자 내용 붙여넣기 (자동 입력)", expanded=True):
        c_txt, c_btn = st.columns([4, 1])
        with c_txt:
            raw_text = st.text_area("문의 내용 원본", height=150, placeholder="카톡 내용을 복사해서 붙여넣으세요.")
        with c_btn:
            st.write("\n\n")
            if st.button("⚡ 분석 실행", type="primary"):
                if raw_text:
                    parsed = parser.parse_text(raw_text)
                    
                    # 분석된 데이터를 세션에 넣기
                    st.session_state['form_evt_name'] = parsed.get('evt_name', '')
                    st.session_state['form_evt_place'] = parsed.get('evt_place', '')
                    st.session_state['form_date_start'] = parsed.get('date_start', '')
                    st.session_state['form_date_end'] = parsed.get('date_end', '')
                    st.session_state['form_evt_time'] = parsed.get('evt_time', '')
                    st.session_state['form_service'] = parsed.get('service_type', '')
                    st.session_state['form_headcount'] = parsed.get('headcount', '')
                    st.session_state['form_pay'] = parsed.get('pay', '')
                    st.session_state['form_contact'] = parsed.get('contact', '')
                    st.session_state['form_manager'] = parsed.get('manager', '')
                    st.session_state['form_note'] = parsed.get('note_detail', raw_text)
                    
                    # 업체명 매칭 로직
                    p_client = parsed.get('client_name', '')
                    if p_client in client_list:
                        # 리스트에 있으면 해당 인덱스 선택
                        try:
                            st.session_state['client_idx'] = client_list.index(p_client) + 1
                        except:
                            st.session_state['client_idx'] = 0
                    else:
                        # 없으면 신규 입력
                        st.session_state['client_idx'] = 0
                        st.session_state['form_new_client_name'] = p_client
                        
                    st.toast("자동 분석 완료! 내용을 확인하세요.", icon="✅")
                    st.rerun() # 화면 갱신
                else:
                    st.warning("내용을 입력해주세요.")

    # --------------------------------------------------------------------------
    # 입력 폼
    # --------------------------------------------------------------------------
    
    # 세션 키 초기화 (없으면 생성)
    form_keys = [
        'form_evt_name', 'form_evt_place', 'form_date_start', 'form_date_end', 
        'form_evt_time', 'form_service', 'form_headcount', 'form_pay',
        'form_contact', 'form_manager', 'form_note', 'form_new_client_name'
    ]
    for k in form_keys:
        if k not in st.session_state: st.session_state[k] = ""
    if 'client_idx' not in st.session_state: st.session_state['client_idx'] = 0

    with st.container():
        st.markdown('<div class="form-box">', unsafe_allow_html=True)
        
        # [1] 고객 정보
        st.markdown('<div class="header-text">1. 고객 정보</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.5, 1, 1])
        
        with c1:
            # 업체명 선택 (key='form_client_select'로 지정하여 저장 함수에서 참조)
            client_name = st.selectbox(
                "업체명", 
                ["(신규 입력)"] + client_list, 
                index=st.session_state['client_idx'],
                key="form_client_select"
            )
            
            # 신규 입력창
            if client_name == "(신규 입력)":
                st.text_input("업체명 직접 입력", key="form_new_client_name")
                is_new = True
            else:
                is_new = False
                
            # 기존 정보 자동 채우기 (화면 표시용)
            if not is_new and not df_client.empty:
                try:
                    c_info = df_client[df_client['업체명'] == client_name].iloc[0]
                    # 값이 비어있을 때만 DB 값으로 덮어쓰기 (분석값 유지)
                    if not st.session_state['form_manager']: st.session_state['form_manager'] = str(c_info.get('담당자명', ''))
                    if not st.session_state['form_contact']: st.session_state['form_contact'] = str(c_info.get('담당자연락처', ''))
                except: pass

        with c2: st.text_input("담당자", key="form_manager")
        with c3: st.text_input("연락처", key="form_contact")

        st.markdown("<br>", unsafe_allow_html=True)

        # [2] 행사 상세
        st.markdown('<div class="header-text">2. 행사 상세</div>', unsafe_allow_html=True)
        
        r1_c1, r1_c2 = st.columns([2, 1])
        r1_c1.text_input("행사명", key="form_evt_name")
        r1_c2.text_input("장소", key="form_evt_place")
        
        st.markdown('<div class="label-text">일시 / 시간</div>', unsafe_allow_html=True)
        r2_c1, r2_c2, r2_c3 = st.columns([1, 1, 1.5])
        r2_c1.text_input("시작일", key="form_date_start", placeholder="2025-02-16")
        r2_c2.text_input("종료일", key="form_date_end", placeholder="2025-03-02")
        r2_c3.text_input("시간", key="form_evt_time", placeholder="10:30~20:30")
        
        st.markdown('<div class="label-text">세부 조건</div>', unsafe_allow_html=True)
        r3_c1, r3_c2, r3_c3 = st.columns([1, 1, 1])
        r3_c1.text_input("서비스 종류", key="form_service", placeholder="행사스탭")
        r3_c2.text_input("요청 인원", key="form_headcount", placeholder="2명")
        r3_c3.text_input("페이 (예산)", key="form_pay", placeholder="500만원 내외")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.text_area("특이사항 (복장, 식사, 주차 등)", key="form_note", height=100)

        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # 저장 버튼 (콜백 함수 연결)
        # ----------------------------------------------------------------------
        # on_click에 save_inquiry 함수를 연결하여 위젯 렌더링 충돌 방지
        st.button("🚀 문의 접수 등록", type="primary", use_container_width=True, on_click=save_inquiry)