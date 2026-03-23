# page_staff.py (개선된 스마트 인력 배정)
import streamlit as st
import pandas as pd
import data_loader as db
from smart_assignment import SmartAssignment, StaffFilter, RoleSkillMatcher
from workflow_automation import auto_link_workflow
from calculators import SalaryCalculator, ValidationEngine
from datetime import datetime, timedelta
from helpers import get_logger, now_kst

logger = get_logger(__name__)

# ==============================================================================
# 1. 스타일링
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 1200px; padding-top: 1rem; }
        .staff-card { 
            background-color: white; padding: 15px; border-radius: 8px; 
            border-left: 4px solid #3b82f6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
            margin-bottom: 10px; 
        }
        .score-badge {
            display: inline-block; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 5px 12px; border-radius: 20px; 
            font-weight: bold; font-size: 14px;
        }
        .available-badge { 
            background-color: #dbeafe; color: #0369a1; 
            padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; 
        }
        .unavailable-badge { 
            background-color: #fee2e2; color: #991b1b; 
            padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; 
        }
        .role-tag {
            display: inline-block;
            background-color: #f0f9ff; color: #0369a1;
            padding: 4px 10px; border-radius: 4px; font-size: 12px; margin: 2px;
        }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 필터 입력 UI
# ==============================================================================
@st.cache_data(ttl=3600)
def get_unique_values(df: pd.DataFrame, column: str) -> list:
    """컬럼의 고유값 추출"""
    if column not in df.columns:
        return []
    return sorted(df[column].dropna().unique().tolist())

def show_filter_panel(staff_df: pd.DataFrame) -> dict:
    """필터 패널 UI 및 필터 값 반환"""
    st.subheader("🔍 인력 검색 필터")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        gender = st.selectbox(
            "성별",
            ["전체"] + get_unique_values(staff_df, '성별'),
            key="filter_gender"
        )
    
    with col2:
        # 나이대 선택
        age_range = st.select_slider(
            "나이대",
            options=[20, 30, 40, 50, 60],
            value=(20, 60),
            key="filter_age"
        )
    
    with col3:
        location = st.selectbox(
            "지역",
            ["전체"] + get_unique_values(staff_df, '지역') if '지역' in staff_df.columns else ["전체"],
            key="filter_location"
        )
    
    col4, col5, col6 = st.columns(3)
    
    with col4:
        # 스킬 다중 선택
        all_skills = []
        skill_col = None
        for col in staff_df.columns:
            if '스킬' in col or '기술' in col:
                skill_col = col
                break
        
        if skill_col:
            for skills_str in staff_df[skill_col].dropna():
                all_skills.extend([s.strip() for s in str(skills_str).split(',')])
            all_skills = list(set(all_skills))
        
        skills = st.multiselect(
            "필수 스킬",
            all_skills,
            key="filter_skills"
        )
    
    with col5:
        role = st.selectbox(
            "역할",
            ["전체"] + get_unique_values(staff_df, '역할') if '역할' in staff_df.columns else ["전체"],
            key="filter_role"
        )
    
    with col6:
        st.write("")  # 빈 공간
        st.write("")
        reset_filters = st.button("🔄 필터 초기화", use_container_width=True)
    
    # 날짜 범위 (배정 기간)
    st.markdown("---")
    col7, col8 = st.columns(2)
    
    with col7:
        start_date = st.date_input("배정 시작일", now_kst())
    
    with col8:
        end_date = st.date_input("배정 종료일", now_kst() + timedelta(days=7))
    
    # 필터 딕셔너리 구성
    filters = {
        'gender': None if gender == '전체' else gender,
        'min_age': age_range[0],
        'max_age': age_range[1],
        'location': None if location == '전체' else location,
        'skills': skills if skills else None,
        'role': None if role == '전체' else role,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
    }
    
    return filters, reset_filters

# ==============================================================================
# 3. 후보자 카드 표시
# ==============================================================================
def show_candidate_card(candidate: pd.Series, rank: int = 1, score: float = 0):
    """개별 후보자 카드 표시"""
    col1, col2, col3 = st.columns([1, 8, 1])
    
    with col1:
        st.write(f"**#{rank}**")
    
    with col2:
        name = candidate.get('이름', 'N/A')
        age = candidate.get('나이', 'N/A')
        gender = candidate.get('성별', 'N/A')
        location = candidate.get('지역', 'N/A')
        
        # 헤더
        col_name, col_score = st.columns([3, 1])
        with col_name:
            st.markdown(f"### {name}")
        with col_score:
            if score > 0:
                st.markdown(f"<div class='score-badge'>{int(score)}점</div>", 
                           unsafe_allow_html=True)
        
        # 상세 정보
        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            st.write(f"**나이**: {age}세")
        with col_info2:
            st.write(f"**성별**: {gender}")
        with col_info3:
            st.write(f"**지역**: {location}")
        
        # 스킬
        skill_col = None
        for col in candidate.index:
            if '스킬' in col or '기술' in col:
                skill_col = col
                break
        
        if skill_col and candidate.get(skill_col):
            skills = str(candidate[skill_col]).split(',')
            skill_html = ' '.join([
                f"<span class='role-tag'>{s.strip()}</span>" for s in skills
            ])
            st.markdown(skill_html, unsafe_allow_html=True)
        
        # 단가 정보
        col_price1, col_price2 = st.columns(2)
        with col_price1:
            hourly_rate = candidate.get('기본단가', 0)
            st.write(f"**기본단가**: {int(hourly_rate):,}원/일")
        with col_price2:
            phone = candidate.get('연락처', '')
            st.write(f"**연락처**: {phone}")
    
    with col3:
        select_btn = st.button(
            "선택",
            key=f"select_{name}_{rank}",
            use_container_width=True
        )
        return select_btn

# ==============================================================================
# 4. 배정 확정 및 저장
# ==============================================================================
def show_assignment_form(selected_candidate: pd.Series, inquiry_id: str):
    """배정 상세 입력 폼"""
    st.subheader("✏️ 배정 상세 입력")
    
    candidate_name = selected_candidate.get('이름', '')
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        role = st.selectbox(
            "역할",
            ["보안요원", "인원배치", "행사진행", "기술지원", "기타"],
            key="assign_role"
        )
    
    with col2:
        days = st.number_input(
            "배정 일수",
            min_value=1,
            max_value=30,
            value=1,
            key="assign_days"
        )
    
    with col3:
        hourly_rate = st.number_input(
            "단가 (원/일)",
            min_value=0,
            value=int(selected_candidate.get('기본단가', 0)),
            step=10000,
            key="assign_rate"
        )
    
    col4, col5 = st.columns(2)
    
    with col4:
        notes = st.text_input("비고", value="", key="assign_notes")
    
    with col5:
        st.write("")
        st.write("")
    
    # 예상 급여 계산
    total_pay = int(days) * int(hourly_rate)
    st.metric("예상 지급액", f"{total_pay:,}원")
    
    # 배정 저장
    col_save, col_cancel = st.columns(2)
    
    with col_save:
        if st.button("✅ 배정 확정 및 연계", use_container_width=True):
            # 검증
            assignment = {
                '이름': candidate_name,
                '역할': role,
                '일수': int(days),
                '단가': int(hourly_rate),
                '총지급액': total_pay,
                '상태': '배정중',
                '배정일시': now_kst().strftime('%Y-%m-%d %H:%M:%S'),
                '비고': notes,
            }
            
            is_valid, errors = ValidationEngine.validate_assignment(assignment)
            if not is_valid:
                st.error("입력값 오류:\n" + "\n".join(errors))
                return False
            
            # 배정 패키지 구성
            assignment_pkg = {
                '문의ID': inquiry_id,
                **assignment
            }
            
            # 저장
            result = db.save_assignment_record(assignment_pkg)
            
            if result:
                # 자동 워크플로우 연계 (출석부, 급여)
                st.info("🔗 출석부 및 급여 정보를 자동으로 생성 중...")
                
                try:
                    client = db.get_connection()
                    if client:
                        sh = client.open_by_key(db.SHEET_ID)
                        workflow_result = auto_link_workflow(assignment_pkg, sh)
                        st.success(workflow_result['summary'])
                    else:
                        st.warning("⚠️ 워크플로우 자동 연계 실패 (Google Sheet 접근 불가)")
                except Exception as e:
                    logger.error(f"Workflow automation error: {e}")
                    st.warning(f"⚠️ 워크플로우 연계 중 오류: {str(e)}")
                
                st.balloons()
                return True
            else:
                st.error("배정 저장 실패")
                return False
    
    with col_cancel:
        if st.button("❌ 취소", use_container_width=True):
            st.info("취소되었습니다.")
            return None

# ==============================================================================
# 5. 메인 페이지
# ==============================================================================
def show(data):
    apply_styles()
    st.title("👥 스마트 인력 배정")
    st.markdown("다양한 조건으로 최적의 인력을 검색하고 배정합니다.")
    
    # 데이터 로드
    df_inq = data.get('inq', pd.DataFrame())
    df_staff = data.get('staff', pd.DataFrame())
    df_dispatch = db.load_dispatch_sheet() if hasattr(db, 'load_dispatch_sheet') else pd.DataFrame()
    
    if df_inq.empty or df_staff.empty:
        st.error("📊 필요한 데이터를 로드할 수 없습니다.")
        return
    
    # 문의 선택
    st.subheader("📋 배정할 문의 선택")
    
    # 업체명 + 행사명으로 표시하고, 문의ID를 값으로 사용
    if not df_inq.empty and '문의ID' in df_inq.columns:
        inq_options = {}
        for _, row in df_inq.iterrows():
            inq_id = str(row['문의ID']).strip()
            client = str(row.get('업체명', 'N/A')).strip()
            event = str(row.get('행사명', 'N/A')).strip()
            inq_options[inq_id] = f"{client} / {event}"
        
        inquiry_id = st.selectbox(
            "문의 선택",
            list(inq_options.keys()),
            format_func=lambda x: inq_options[x],
            key="select_inquiry"
        )
    else:
        st.error("문의 데이터를 로드할 수 없습니다.")
        return
    
    if inquiry_id:
        # 선택된 문의 정보 표시
        inq_info = df_inq[df_inq['문의ID'] == inquiry_id].iloc[0]
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("업체명", inq_info.get('업체명', 'N/A'))
        with col2:
            st.metric("행사명", inq_info.get('행사명', 'N/A'))
        with col3:
            st.metric("연락처", inq_info.get('연락처', 'N/A'))
        with col4:
            # 배정 현황 표시 (배정인원/필요인원)
            _need_col = None
            for _c in ['필요인력', '요청인원', '인원']:
                if _c in inq_info.index:
                    _need_col = _c
                    break
            _needed = 0
            if _need_col:
                try:
                    _needed = int(float(inq_info.get(_need_col, 0) or 0))
                except:
                    _needed = 0
            _assigned_cnt = len(df_dispatch[df_dispatch['행사명'].astype(str).str.strip() == str(inq_info.get('행사명', '')).strip()]) if not df_dispatch.empty and '행사명' in df_dispatch.columns else 0
            
            if _needed > 0:
                if _assigned_cnt >= _needed:
                    st.markdown(f"""<div style="background:#DCFCE7;color:#166534;padding:10px;border-radius:8px;text-align:center;font-weight:bold;margin-top:8px;">
                        ✅ 배정완료 {_assigned_cnt}/{_needed}명
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div style="background:#FEF3C7;color:#92400E;padding:10px;border-radius:8px;text-align:center;font-weight:bold;margin-top:8px;">
                        ⚠️ {_assigned_cnt}/{_needed}명 (부족 {_needed - _assigned_cnt}명)
                    </div>""", unsafe_allow_html=True)
            else:
                st.metric("배정인원", f"{_assigned_cnt}명")
    
    st.markdown("---")
    
    # 필터 패널
    filters, reset_filters = show_filter_panel(df_staff)
    
    if reset_filters:
        st.rerun()
    
    st.markdown("---")
    
    # 후보자 검색
    st.subheader("🔎 검색 결과")
    
    candidates = SmartAssignment.search_candidates(df_staff, df_dispatch, filters)
    
    if candidates.empty:
        st.info("⚠️ 조건에 맞는 인력이 없습니다. 필터를 조정해주세요.")
        return
    
    st.success(f"✅ {len(candidates)}명의 후보자를 찾았습니다.")
    
    # 후보자 리스트 표시
    st.subheader("👥 추천 인력 목록")
    
    selected_idx = None
    selected_candidate = None
    
    for rank, (idx, candidate) in enumerate(candidates.iterrows(), 1):
        with st.container():
            score = candidate.get('매칭점수', 0) if '매칭점수' in candidates.columns else 0
            is_selected = show_candidate_card(candidate, rank, score)
            
            if is_selected:
                selected_idx = idx
                selected_candidate = candidate
                break
        
        st.divider()
    
    # 선택된 후보자 배정 폼
    if selected_candidate is not None:
        st.markdown("---")
        
        if show_assignment_form(selected_candidate, inquiry_id):
            # 배정 완료 후 다음 단계 안내
            st.markdown("---")
            st.subheader("✅ 다음 단계")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.info("📋 출석부 기록")
            with col2:
                st.info("💰 지급 목록 생성")
            with col3:
                st.info("📊 리포트 조회")

if __name__ == "__main__":
    # 테스트용
    sample_data = {
        'inq': pd.DataFrame(),
        'staff': pd.DataFrame(),
    }
    show(sample_data)
