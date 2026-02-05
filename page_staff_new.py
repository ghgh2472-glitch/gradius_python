# page_staff_new.py
"""
🚀 인력파견 시스템 - 고도화 버전 (v3.0)
- 탭1: 인력배정 (스마트 검색 + 자동 추천)
- 탭2: 출석부 (일일 기록)
- 탭3: 평가 & 지급 (평가 입력 + 급여 자동계산)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from st_aggrid import AgGrid, GridOptionsBuilder
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors
from pydantic import BaseModel, validator
import data_loader as db
import json
from uuid import uuid4

# ==============================================================================
# 0. 설정 및 스타일링
# ==============================================================================

def apply_styles():
    """고도화된 스타일링"""
    st.markdown("""
    <style>
        .block-container { max-width: 1400px; padding-top: 1rem; }
        
        /* 탭 스타일 */
        .stTabs [data-baseweb="tab-list"] button { 
            font-size: 16px; font-weight: 700; padding: 12px 24px;
            border-radius: 8px 8px 0 0;
        }
        
        /* 메인 버튼 */
        .stButton>button { 
            border-radius: 8px; font-weight: 700; height: 45px; 
            background-color: #0f766e; color: white; border: none;
            transition: all 0.3s;
            font-size: 14px;
        }
        .stButton>button:hover { 
            background-color: #14b8a6; 
            box-shadow: 0 4px 12px rgba(15, 118, 110, 0.3); 
        }
        
        /* 섹션 제목 */
        .section-title {
            font-size: 20px; font-weight: 900; color: #0f2f3f;
            margin: 20px 0 15px 0; border-left: 6px solid #0f766e;
            padding-left: 15px;
        }
        
        /* 카드 스타일 */
        .staff-card {
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border-left: 5px solid #0369a1;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        
        .score-badge {
            display: inline-block;
            background: linear-gradient(135deg, #0f766e 0%, #14b8a6 100%);
            color: white; padding: 6px 14px; border-radius: 20px;
            font-weight: bold; font-size: 13px;
        }
        
        .metric-box {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }
        
        .metric-value {
            font-size: 24px; font-weight: 900; color: #0f766e;
        }
        
        .metric-label {
            font-size: 12px; color: #64748b; margin-top: 5px;
        }
        
        /* 배지 */
        .available-badge { 
            background-color: #dcfce7; color: #166534; 
            padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700;
            display: inline-block; margin: 2px;
        }
        .unavailable-badge { 
            background-color: #fee2e2; color: #991b1b; 
            padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700;
            display: inline-block; margin: 2px;
        }
        
        /* 등급 배지 */
        .grade-a { background-color: #dcfce7; color: #166534; }
        .grade-b { background-color: #dbeafe; color: #0c4a6e; }
        .grade-c { background-color: #fef3c7; color: #92400e; }
        .grade-d { background-color: #fee2e2; color: #991b1b; }
    </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# 1. 데이터 모델 (Pydantic 검증)
# ==============================================================================

class AssignmentModel(BaseModel):
    """배정 데이터 검증"""
    문의ID: str
    인력명: str
    직무: str
    파견일수: int
    기본시급: int
    
    @validator('파견일수')
    def check_days(cls, v):
        if v <= 0 or v > 365:
            raise ValueError('파견일수는 1~365일 사이여야 합니다')
        return v
    
    @validator('기본시급')
    def check_salary(cls, v):
        if v < 10000 or v > 500000:
            raise ValueError('기본시급은 10,000~500,000원 사이여야 합니다')
        return v


class AttendanceModel(BaseModel):
    """출석 데이터 검증"""
    배정ID: str
    출석날짜: str  # YYYY-MM-DD
    출근시간: str  # HH:MM
    퇴근시간: str  # HH:MM
    
    @validator('출석날짜')
    def check_date(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except:
            raise ValueError('날짜 형식: YYYY-MM-DD')
        return v


# ==============================================================================
# 2. 스마트 인력 검색 및 추천 (scikit-learn)
# ==============================================================================

class SmartStaffMatcher:
    """머신러닝 기반 인력 매칭 엔진"""
    
    def __init__(self, df_staff):
        self.df_staff = df_staff.copy() if not df_staff.empty else pd.DataFrame()
        self.scaler = StandardScaler()
        self.features = None
        self._prepare_features()
    
    def _prepare_features(self):
        """인력 특징 벡터화"""
        if self.df_staff.empty:
            return
        
        df = self.df_staff.copy()
        
        # 나이 정규화 (20~70)
        df['나이_정규화'] = pd.to_numeric(df.get('나이', 0), errors='coerce').fillna(0)
        df['나이_정규화'] = (df['나이_정규화'] - 20) / (70 - 20)
        
        # 키 정규화 (150~200)
        df['키_정규화'] = pd.to_numeric(df.get('키', 0), errors='coerce').fillna(0)
        df['키_정규화'] = (df['키_정규화'] - 150) / (200 - 150)
        
        # 평점 정규화 (0~100)
        df['총점_정규화'] = pd.to_numeric(df.get('총점', 0), errors='coerce').fillna(0) / 100
        
        # 특징 선택
        self.features = df[['나이_정규화', '키_정규화', '총점_정규화']].fillna(0).values
    
    def recommend_staff(self, requirements: dict, top_k=5) -> pd.DataFrame:
        """
        조건에 맞는 인력 추천
        
        Args:
            requirements: {
                '이름': str or None,
                '성별': 'M' or 'F' or None,
                '나이': (min, max),
                '지역': str or None (이동가능지역),
                '직무': [jobs] or None (가능직무),
                '최소평점': 0~100,
                '최소추천도': 0~5,
                '영어': bool,
                '운전': bool
            }
            top_k: 추천할 인력 수
        
        Returns:
            추천 인력 DataFrame
        """
        if self.df_staff.empty:
            return pd.DataFrame()
        
        df = self.df_staff.copy()
        
        # 1. 이름 검색 (부분 일치)
        if '이름' in requirements and requirements['이름']:
            name_pattern = requirements['이름'].replace('*', '.*')
            df = df[df['이름'].astype(str).str.contains(name_pattern, na=False, case=False)]
        
        # 2. 성별 필터
        if '성별' in requirements and requirements['성별']:
            df = df[df['성별'].astype(str) == requirements['성별']]
        
        # 3. 나이 필터
        if '나이' in requirements:
            min_age, max_age = requirements['나이']
            if min_age > 0 or max_age < 100:  # 유효한 범위인 경우만
                df['나이_num'] = pd.to_numeric(df.get('나이', 0), errors='coerce').fillna(0)
                df = df[(df['나이_num'] >= min_age) & (df['나이_num'] <= max_age)]
        
        # 4. 지역 필터 (이동가능지역 컬럼 사용)
        if '지역' in requirements and requirements['지역']:
            region_pattern = requirements['지역'].replace(',', '|')
            df = df[df.get('이동가능지역', '').astype(str).str.contains(region_pattern, na=False)]
        
        # 5. 직무 필터 (가능직무 컬럼 사용)
        if '직무' in requirements and requirements['직무']:
            job_pattern = '|'.join(requirements['직무'])
            df = df[df.get('가능직무', '').astype(str).str.contains(job_pattern, na=False)]
        
        # 6. 평점 필터 (0~100)
        if '최소평점' in requirements and requirements['최소평점'] > 0:
            df['총점_num'] = pd.to_numeric(df.get('총점', 0), errors='coerce').fillna(0)
            df = df[df['총점_num'] >= requirements['최소평점']]
        
        # 7. 추천도 필터 (0~5)
        if '최소추천도' in requirements and requirements['최소추천도'] > 0:
            df['추천도_num'] = pd.to_numeric(df.get('추천도', 0), errors='coerce').fillna(0)
            df = df[df['추천도_num'] >= requirements['최소추천도']]
        
        # 8. 영어 가능 필터
        if '영어' in requirements and requirements['영어']:
            english_values = df.get('영어', '').astype(str).str.upper()
            df = df[english_values.isin(['Y', 'YES', '1', 'TRUE', 'O', 'OK', 'TRUE'])]
        
        # 9. 운전 가능 필터
        if '운전' in requirements and requirements['운전']:
            driving_values = df.get('운전', '').astype(str).str.upper()
            df = df[driving_values.isin(['Y', 'YES', '1', 'TRUE', 'O', 'OK', 'TRUE'])]
        
        # 10. 가용성 체크 (배정기록에서 확인)
        if '파견기간' in requirements:
            df = self._filter_available(df, requirements['파견기간'])
        
        # 11. 평점 기반 정렬 (총점 > 추천도)
        if not df.empty:
            df['총점_num'] = pd.to_numeric(df.get('총점', 0), errors='coerce').fillna(0)
            df['추천도_num'] = pd.to_numeric(df.get('추천도', 0), errors='coerce').fillna(0)
            df = df.sort_values(['총점_num', '추천도_num'], ascending=[False, False])
        
        return df.head(top_k)
    
    def _filter_available(self, df, dispatch_period):
        """파견기간에 이미 배정된 인력 제외"""
        try:
            dispatch_df = db.load_dispatch_sheet()
            if dispatch_df is None or dispatch_df.empty:
                return df
            
            # 배정된 인력 리스트
            assigned_names = set(dispatch_df.get('이름', []).dropna().unique())
            
            # 이미 배정된 인력 제외
            df = df[~df.get('이름', '').isin(assigned_names)]
            
        except:
            pass  # 무시하고 계속
        
        return df


# ==============================================================================
# 3. 태그 1: 인력배정
# ==============================================================================

def tab_assignment(data):
    """탭1: 인력배정 - 스마트 검색 + 자동 추천"""
    
    st.markdown('<div class="section-title">🔍 인력 검색 및 배정</div>', unsafe_allow_html=True)
    
    # ✅ session_state 초기화
    if 'search_results' not in st.session_state:
        st.session_state.search_results = pd.DataFrame()
    if 'search_performed' not in st.session_state:
        st.session_state.search_performed = False
    if 'selected_staff' not in st.session_state:
        st.session_state.selected_staff = None
    if 'show_assignment_form' not in st.session_state:
        st.session_state.show_assignment_form = False
    
    # 데이터 로드
    df_inq = data.get('inq', pd.DataFrame())
    df_staff = data.get('staff', pd.DataFrame())
    
    # DEBUG: STAFF 데이터 확인
    with st.expander("🔧 DEBUG - STAFF 데이터 상태"):
        st.write(f"**STAFF 행 수**: {len(df_staff)}")
        st.write(f"**STAFF 컬럼 수**: {len(df_staff.columns)}")
        if not df_staff.empty:
            st.write(f"**컬럼 목록**: {list(df_staff.columns)}")
            st.write(f"**샘플 데이터 (처음 3명)**:")
            st.dataframe(df_staff[['이름', '성별', '나이', '이동가능지역', '가능직무']].head(3))
        else:
            st.error("❌ STAFF 데이터가 비어있습니다!")
    
    # 체결된 계약만 필터링
    if not df_inq.empty and '상태' in df_inq.columns:
        contracts = df_inq[df_inq['상태'] == '체결'].sort_values('작성일', ascending=False)
    else:
        contracts = pd.DataFrame()
    
    if contracts.empty:
        st.warning("⚠️ 체결된 계약이 없습니다. 계약을 먼저 체결해주세요.")
        return
    
    # [좌측] 계약 선택
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.markdown("### 📋 계약 선택")
        options = {row['문의ID']: f"{row['업체명']} - {row['행사명']}" 
                   for _, row in contracts.iterrows()}
        selected_inq_id = st.selectbox("계약 선택", options.keys(), 
                                        format_func=lambda x: options[x])
        selected_contract = contracts[contracts['문의ID'] == selected_inq_id].iloc[0]
        
        # 선택된 계약 정보 표시
        st.markdown("#### 📌 선택 계약 정보")
        st.write(f"**업체**: {selected_contract.get('업체명', 'N/A')}")
        st.write(f"**현장**: {selected_contract.get('행사명', 'N/A')}")
        st.write(f"**지역**: {selected_contract.get('장소', 'N/A')}")
        st.write(f"**담당자**: {selected_contract.get('담당자', 'N/A')}")
    
    with col_right:
        st.markdown("### 🔎 스마트 검색 필터")
        
        # 기본 검색 필터
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            search_name = st.text_input("이름 검색", placeholder="김*")
        with col_f2:
            gender = st.selectbox("성별", ["전체", "M", "F"], key="gender_filter")
        with col_f3:
            age_range = st.slider("나이대", 20, 70, (18, 70), key="age_filter")
        
        col_f4, col_f5, col_f6 = st.columns(3)
        with col_f4:
            location = st.text_input("이동가능지역", placeholder="서울, 인천")
        with col_f5:
            job = st.multiselect("가능직무", 
                                 ["사회자", "진행자", "보조진행자", "스태프", "기술담당"],
                                 key="job_filter")
        with col_f6:
            min_score = st.slider("최소평점", 0.0, 5.0, 0.0, key="score_filter")
        
        col_f7, col_f8, col_f9 = st.columns(3)
        with col_f7:
            english_ok = st.checkbox("✅ 영어 가능", key="english_filter")
        with col_f8:
            driving_ok = st.checkbox("✅ 운전 가능", key="driving_filter")
        with col_f9:
            min_recommend = st.slider("최소추천도", 0.0, 5.0, 0.0, key="recommend_filter")
        
        # 검색 버튼
        if st.button("🔍 검색", use_container_width=True, key="search_btn"):
            with st.spinner("조건에 맞는 인력을 검색 중입니다..."):
                # 필터 조건 구성
                requirements = {
                    '이름': search_name if search_name else None,
                    '성별': gender if gender != "전체" else None,
                    '나이': age_range,
                    '지역': location if location else None,
                    '직무': job if job else None,
                    '최소평점': min_score * 20,  # 0~5점 → 0~100점
                    '최소추천도': min_recommend,
                    '영어': english_ok,
                    '운전': driving_ok
                }
                
                # DEBUG: 필터 조건 확인
                with st.expander("🔧 DEBUG - 검색 조건"):
                    st.json(requirements)
                
                # 스마트 매칭
                matcher = SmartStaffMatcher(df_staff)
                recommended = matcher.recommend_staff(requirements, top_k=10)
                
                # DEBUG: 매칭 결과 확인
                with st.expander("🔧 DEBUG - 매칭 단계별 결과"):
                    st.write(f"전체 STAFF 수: {len(df_staff)}")
                    st.write(f"매칭 결과 수: {len(recommended)}")
                    if len(recommended) > 0:
                        st.write(f"**반환된 인력**: {recommended[['이름', '성별', '나이', '총점']].to_dict(orient='records')}")
                
                if not recommended.empty:
                    # ✅ 검색 결과를 session_state에 저장
                    st.session_state.search_results = recommended
                    st.session_state.search_performed = True
                    st.success(f"✅ {len(recommended)}명의 인력을 찾았습니다!")
                else:
                    st.warning("⚠️ 조건에 맞는 인력이 없습니다. 필터를 조정해주세요.")
                    st.session_state.search_results = pd.DataFrame()
                    st.session_state.search_performed = True
        
        # ===== 검색 결과 표시 (항상 표시) =====
        if 'search_performed' in st.session_state and st.session_state.search_performed:
            if 'search_results' in st.session_state and not st.session_state.search_results.empty:
                recommended = st.session_state.search_results
                
                st.markdown(f"#### 🌟 검색 결과: {len(recommended)}명 발견")
                
                # 테이블로 표시
                display_df = recommended[['이름', '성별', '나이', '이동가능지역', '가능직무', 
                                         '키', '영어', '운전', '추천도', '총점']].copy()
                display_df = display_df.reset_index(drop=True)
                display_df.index = display_df.index + 1
                
                st.dataframe(display_df, use_container_width=True)
                
                # 선택 UI
                st.markdown("#### 📌 인력 선택")
                selected_idx = st.selectbox("배정할 인력을 선택하세요", 
                                           range(len(recommended)),
                                           format_func=lambda x: f"{x+1}. {recommended.iloc[x]['이름']} ({recommended.iloc[x]['나이']}세, {recommended.iloc[x]['가능직무']}) - 평점: {recommended.iloc[x]['총점']}")
                
                if st.button("✅ 선택 확정", key="select_staff", use_container_width=True):
                    selected_staff_data = recommended.iloc[selected_idx].to_dict()
                    st.session_state.selected_staff = selected_staff_data
                    st.session_state.show_assignment_form = True
                    st.balloons()
                    st.success(f"✅ {recommended.iloc[selected_idx]['이름']}님을 선택했습니다!")
    
    # 선택된 인력 배정 폼
    st.markdown('<div class="section-title">📝 배정 정보 입력</div>', unsafe_allow_html=True)
    
    # 폼 표시 (session_state 기반)
    if st.session_state.selected_staff is not None and st.session_state.show_assignment_form:
        selected_staff = st.session_state.selected_staff
        
        # 선택된 인력 정보 표시
        st.info(f"""
        **선택된 인력:**
        - 👤 이름: {selected_staff.get('이름', 'N/A')}
        - 🎂 나이: {selected_staff.get('나이', 'N/A')}세
        - 👔 직무: {selected_staff.get('가능직무', 'N/A')}
        - ⭐ 평점: {selected_staff.get('총점', 'N/A')}
        - 🌟 추천도: {selected_staff.get('추천도', 'N/A')}
        """)
        
        st.markdown("##### 📋 배정 조건 입력")
        
        col_assign1, col_assign2, col_assign3 = st.columns(3)
        
        with col_assign1:
            assigned_name = st.text_input("인력명", value=selected_staff.get('이름', ''), disabled=True)
        with col_assign2:
            assigned_job = st.selectbox("직무", 
                                       ["사회자", "진행자", "보조진행자", "스태프", "기술담당"],
                                       key="job_select")
        with col_assign3:
            dispatch_days = st.number_input("파견일수", min_value=1, max_value=365, value=1, key="dispatch_days")
        
        col_assign4, col_assign5 = st.columns(2)
        with col_assign4:
            base_salary = st.number_input("기본시급 (원/시간)", 
                                         min_value=10000, max_value=500000, 
                                         value=100000, step=10000, key="base_salary")
        with col_assign5:
            allowance = st.number_input("추가수당 (원/일)", min_value=0, max_value=500000, 
                                       value=0, step=10000, key="allowance")
        
        # 예상급여 자동 계산
        expected_salary = (base_salary * 8 * dispatch_days) + (allowance * dispatch_days)
        
        st.markdown("##### 💰 급여 예상액")
        col_calc1, col_calc2, col_calc3 = st.columns(3)
        with col_calc1:
            st.metric("일일 예상급여", f"₩{base_salary:,}")
        with col_calc2:
            st.metric("파견기간 총급여", f"₩{expected_salary:,}")
        with col_calc3:
            st.metric("상태", "🟢 배정중")
        
        # 배정 저장 버튼
        st.markdown("##### 💾 배정 저장")
        col_btn1, col_btn2 = st.columns([3, 1])
        
        with col_btn1:
            if st.button("💾 배정 정보 저장", use_container_width=True, key="save_assign"):
                try:
                    # 배정 데이터 검증
                    assignment_data = AssignmentModel(
                        문의ID=selected_inq_id,
                        인력명=assigned_name,
                        직무=assigned_job,
                        파견일수=dispatch_days,
                        기본시급=int(base_salary)
                    )
                    
                    # 시트에 저장
                    with st.spinner("배정 정보를 저장 중..."):
                        assignment_dict = {
                            "배정ID": "",  # auto-generated
                            "문의ID": selected_inq_id,
                            "행사명": selected_contract.get('행사명', ''),
                            "인력명": assigned_name,
                            "직무": assigned_job,
                            "근무일수": dispatch_days,
                            "지급단가": int(base_salary),
                            "총지급액": expected_salary,
                            "지급상태": "배정중",
                            "배정일시": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        
                        success = db.save_assignment_record(assignment_dict)
                        
                        if success:
                            # 저장 후 캐시 명시적 무효화
                            st.cache_data.clear()
                            
                            st.balloons()
                            st.success(f"""
                            ✅ **배정 완료!**
                            
                            {assigned_name}님이 **{selected_contract.get('행사명', '')}** 현장에 배정되었습니다.
                            
                            📌 배정 정보:
                            - 직무: {assigned_job}
                            - 파견기간: {dispatch_days}일
                            - 예상급여: ₩{expected_salary:,}
                            """)
                            # 폼 초기화
                            st.session_state.selected_staff = None
                            st.session_state.show_assignment_form = False
                        else:
                            st.error("배정 저장에 실패했습니다.")
                
                except Exception as e:
                    st.error(f"❌ 오류: {str(e)}")
        
        with col_btn2:
            if st.button("❌ 취소", key="cancel_assign", use_container_width=True):
                st.session_state.selected_staff = None
                st.session_state.show_assignment_form = False
    else:
        # 인력이 선택되지 않았을 때
        st.info("👉 위의 검색 결과에서 인력을 선택하면 배정 정보 입력 폼이 나타납니다.")
    
    # ===== 배정된 인력 목록 표시 =====
    st.markdown('<div class="section-title">📋 배정된 인력 목록</div>', unsafe_allow_html=True)
    
    # 현재 계약의 배정된 인력 조회 (항상 최신 데이터 로드)
    # 매번 새로 조회하여 변경사항을 반영
    import time
    
    # 자동 새로고침 버튼 추가
    if st.button("🔄 목록 새로고침", use_container_width=True, key="refresh_list"):
        st.cache_data.clear()
        st.rerun()
    
    assignments_df = pd.DataFrame()
    
    # 배정 데이터 조회
    try:
        assignments_df = db.get_assignments_by_inquiry(selected_inq_id)
    except Exception as e:
        print(f"배정 조회 실패: {e}")
        time.sleep(0.5)
        try:
            # 재시도
            assignments_df = db.get_assignments_by_inquiry(selected_inq_id)
        except Exception as e2:
            print(f"2차 조회 실패: {e2}")
            st.warning("배정 목록을 불러올 수 없습니다.")
    
    if not assignments_df.empty:
        st.markdown(f"#### {selected_contract.get('행사명', '')} - 배정 현황: **{len(assignments_df)}명**")
        
        # DEBUG: 배정기록 컬럼 확인
        with st.expander("🔧 DEBUG - 배정기록 컬럼 정보"):
            st.write(f"**컬럼 목록**: {list(assignments_df.columns)}")
            st.write(f"**첫 행 데이터**:")
            st.dataframe(assignments_df.iloc[0:1])
        
        # 배정 목록 테이블
        display_cols = ['배정ID', '이름', '역할', '일수', '단가', '총지급액', '배정일시', '상태']
        available_cols = [col for col in display_cols if col in assignments_df.columns]
        
        display_df = assignments_df[available_cols].copy()
        display_df = display_df.reset_index(drop=True)
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # 배정 수정/삭제 섹션
        st.markdown("##### 🔧 배정 관리")
        col_manage1, col_manage2 = st.columns(2)
        
        with col_manage1:
            # 안전한 컬럼명 처리 - 존재하는 컬럼만 사용
            name_col = '이름' if '이름' in assignments_df.columns else '인력명' if '인력명' in assignments_df.columns else None
            role_col = '역할' if '역할' in assignments_df.columns else '직무' if '직무' in assignments_df.columns else None
            days_col = '일수' if '일수' in assignments_df.columns else '파견일수' if '파견일수' in assignments_df.columns else None
            
            # 표시 문자열 생성 함수
            def format_assignment(idx):
                row = assignments_df.iloc[idx]
                name = row.get(name_col, 'N/A') if name_col else 'N/A'
                role = row.get(role_col, 'N/A') if role_col else 'N/A'
                days = row.get(days_col, 'N/A') if days_col else 'N/A'
                return f"{name} - {role} ({days}일)"
            
            selected_assign_idx = st.selectbox(
                "수정/삭제할 배정을 선택하세요",
                range(len(assignments_df)),
                format_func=format_assignment
            )
            
            selected_assign = assignments_df.iloc[selected_assign_idx]
        
        col_m1, col_m2, col_m3 = st.columns(3)
        
        with col_m1:
            if st.button("✏️ 수정", key="edit_assign", use_container_width=True):
                st.session_state.edit_assignment = selected_assign.to_dict()
                assigned_name = selected_assign.get(name_col, '해당 직원') if name_col else '해당 직원'
                st.info(f"✏️ **{assigned_name}**님의 배정 정보를 수정 중입니다...")
        
        with col_m2:
            if st.button("❌ 삭제", key="delete_assign", use_container_width=True):
                assign_id = selected_assign.get('배정ID', '')
                if assign_id:
                    success = db.update_assignment_status(assign_id, '취소')
                    if success:
                        st.cache_data.clear()
                        assigned_name = selected_assign.get(name_col, '해당 직원') if name_col else '해당 직원'
                        st.success(f"✅ {assigned_name}님의 배정이 취소되었습니다.")
                    else:
                        st.error("배정 취소에 실패했습니다.")
        
        with col_m3:
            if st.button("📊 확정", key="confirm_assign", use_container_width=True):
                assign_id = selected_assign.get('배정ID', '')
                if assign_id:
                    try:
                        success = db.update_assignment_status(assign_id, '확정')
                        if success:
                            st.cache_data.clear()
                            assigned_name = selected_assign.get(name_col, '해당 직원') if name_col else '해당 직원'
                            st.success(f"✅ {assigned_name}님의 배정이 확정되었습니다.")
                        else:
                            st.error("배정 확정에 실패했습니다. (Sheet 업데이트 실패)")
                    except Exception as e:
                        st.error(f"❌ 배정 확정 중 오류: {str(e)}")
    
    else:
        st.info("👉 위에서 인력을 선택하면 배정 정보를 입력할 수 있습니다.")


# ==============================================================================
# 4. 탭 2: 출석부
# ==============================================================================

def tab_attendance(data):
    """탭2: 출석부 - 일일 기록 입력"""
    
    st.markdown('<div class="section-title">📋 출석부 기록</div>', unsafe_allow_html=True)
    
    # 데이터 로드
    df_inq = data.get('inq', pd.DataFrame())
    
    if df_inq.empty:
        st.warning("⚠️ 체결된 계약이 없습니다.")
        return
    
    # 체결된 계약 필터링
    contracts = df_inq[df_inq['상태'] == '체결'].sort_values('작성일', ascending=False)
    if contracts.empty:
        st.warning("⚠️ 체결된 계약이 없습니다. 계약을 먼저 체결해주세요.")
        return
    
    # 계약 선택
    col_contract1, col_contract2 = st.columns([1, 2])
    
    with col_contract1:
        contract_options = {row['문의ID']: f"{row['업체명']} - {row['행사명']}" 
                           for _, row in contracts.iterrows()}
        selected_inq_id = st.selectbox("계약 선택", contract_options.keys(), 
                                       format_func=lambda x: contract_options[x], key="att_contract")
    
    selected_contract = contracts[contracts['문의ID'] == selected_inq_id].iloc[0]
    
    with col_contract2:
        st.write(f"**업체**: {selected_contract.get('업체명', '')}")
        st.write(f"**행사**: {selected_contract.get('행사명', '')}")
    
    # 배정된 인력 로드
    assignments_df = db.get_assignments_by_inquiry(selected_inq_id)
    
    if assignments_df.empty:
        st.info("👉 이 계약에 배정된 인력이 없습니다.")
        return
    
    # 배정된 인력 목록
    st.markdown("#### 👥 배정된 인력 목록")
    
    # 컬럼명 처리 (안전한 방식)
    name_col = '이름' if '이름' in assignments_df.columns else '인력명' if '인력명' in assignments_df.columns else None
    role_col = '역할' if '역할' in assignments_df.columns else '직무' if '직무' in assignments_df.columns else None
    days_col = '일수' if '일수' in assignments_df.columns else '근무일수' if '근무일수' in assignments_df.columns else None
    rate_col = '단가' if '단가' in assignments_df.columns else '지급단가' if '지급단가' in assignments_df.columns else None
    
    # 선택 UI
    col_select1, col_select2 = st.columns([2, 1])
    
    with col_select1:
        selected_staff_idx = st.selectbox(
            "인력 선택",
            range(len(assignments_df)),
            format_func=lambda x: f"{assignments_df.iloc[x].get(name_col, 'N/A')} - {assignments_df.iloc[x].get(role_col, 'N/A')}",
            key="att_staff"
        )
    
    selected_staff = assignments_df.iloc[selected_staff_idx]
    assigned_name = selected_staff.get(name_col, 'N/A')
    assigned_role = selected_staff.get(role_col, 'N/A')
    assigned_days = int(selected_staff.get(days_col, 1) or 1)
    hourly_rate = int(selected_staff.get(rate_col, 100000) or 100000)
    
    with col_select2:
        st.metric("배정일수", f"{assigned_days}일")
    
    # 출석 기록 입력
    st.markdown("#### 📅 출석 기록 입력")
    
    col_att1, col_att2, col_att3 = st.columns(3)
    
    with col_att1:
        att_date = st.date_input("출석날짜", value=datetime.now().date(), key="att_date")
    
    with col_att2:
        start_time = st.time_input("출근시간", value=datetime.strptime("09:00", "%H:%M").time(), key="start_time")
    
    with col_att3:
        end_time = st.time_input("퇴근시간", value=datetime.strptime("18:00", "%H:%M").time(), key="end_time")
    
    # 실제근무시간 자동 계산
    start_dt = datetime.combine(datetime.today(), start_time)
    end_dt = datetime.combine(datetime.today(), end_time)
    
    if end_dt < start_dt:
        end_dt = end_dt + timedelta(days=1)
    
    worked_hours = (end_dt - start_dt).total_seconds() / 3600
    worked_str = f"{int(worked_hours)}:{int((worked_hours % 1) * 60):02d}"
    daily_wage = int(worked_hours * (hourly_rate / 8))
    
    col_calc1, col_calc2, col_calc3 = st.columns(3)
    with col_calc1:
        st.metric("실제근무시간", worked_str)
    with col_calc2:
        st.metric("일급여", f"₩{daily_wage:,}")
    with col_calc3:
        status = st.selectbox("출석상태", ["정상", "지각", "조퇴", "결근"], key="att_status")
    
    col_att_note1, col_att_note2 = st.columns(2)
    with col_att_note1:
        absence_reason = st.text_input("휴무사유 (있을 경우)", key="att_reason")
    with col_att_note2:
        memo = st.text_input("비고", key="att_memo")
    
    # 저장 버튼
    if st.button("✅ 출석 기록 저장", use_container_width=True, key="save_attendance"):
        try:
            with st.spinner("출석 기록을 저장 중..."):
                attendance_dict = {
                    "배정ID": selected_staff.get('배정ID', ''),
                    "문의ID": selected_inq_id,
                    "인력명": assigned_name,
                    "출석날짜": att_date.strftime('%Y-%m-%d'),
                    "출근시간": start_time.strftime('%H:%M'),
                    "퇴근시간": end_time.strftime('%H:%M'),
                    "근무시간": worked_hours,
                    "일급여": daily_wage,
                    "출석상태": status,
                    "사유": absence_reason if absence_reason else "",
                    "비고": memo if memo else "",
                    "기록일시": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                success = db.save_attendance_record(attendance_dict)
                
                if success:
                    st.cache_data.clear()
                    st.balloons()
                    st.success(f"✅ {assigned_name}님의 {att_date.strftime('%Y-%m-%d')} 출석이 기록되었습니다!")
                else:
                    st.error("❌ 출석 기록 저장에 실패했습니다.")
        
        except Exception as e:
            st.error(f"❌ 오류: {str(e)}")
    
    # 최근 출석 기록 표시
    st.markdown("#### 📊 최근 출석 기록")
    st.info("📌 이 인력의 최근 7일 출석 기록")


# ==============================================================================
# 5. 탭 3: 정산
# ==============================================================================

def tab_settlement(data):
    """탭3: 정산 - 계약건 청구 및 수금 관리"""
    st.markdown('<div class="section-title">💰 정산 관리 - 고객사 청구 및 수금</div>', unsafe_allow_html=True)
    
    # 정산 데이터 로드
    try:
        dispatch_data = db.load_dispatch_data()
        settlement_df = dispatch_data.get('settlement', pd.DataFrame())
    except Exception as e:
        st.error(f"❌ 정산 데이터 로드 실패: {e}")
        return
    
    # DEBUG 정보
    with st.expander("🔧 DEBUG - 정산 데이터 상태"):
        st.write(f"**Settlement 행 수**: {len(settlement_df)}")
        st.write(f"**Settlement 컬럼 수**: {len(settlement_df.columns)}")
        if not settlement_df.empty:
            st.write(f"**컬럼 목록**: {list(settlement_df.columns)}")
            st.write(f"**첫 번째 행 문의ID**: {settlement_df.iloc[0].get('문의ID', 'N/A')}")
        else:
            st.error("❌ Settlement 데이터가 비어있습니다!")
    
    if settlement_df.empty:
        st.warning("⚠️ 정산 데이터가 없습니다.")
        return
    
    # 데이터 정리 (빈 값 처리)
    settlement_df = settlement_df.fillna('').copy()
    
    # 탭 구분
    tab_list, tab_input = st.tabs(["📊 정산 현황", "✍️ 입금 기록"])
    
    with tab_list:
        st.markdown("### 📋 계약별 청구 및 수금 현황")
        
        # 기본 컬럼 확인
        has_supply = '공급가액' in settlement_df.columns
        has_tax = '부가세' in settlement_df.columns
        has_paid = '받은금액' in settlement_df.columns
        has_balance = '잔액' in settlement_df.columns
        
        # 통계 계산 (안전하게)
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
        
        # 간단한 테이블 표시
        st.markdown("#### 📑 계약별 정산 상세")
        
        # 표시할 컬럼 선택
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
            st.write(f"사용 가능한 컬럼: {list(settlement_df.columns)}")
    
    with tab_input:
        st.markdown("### ✍️ 입금 기록 입력")
        
        st.info("📌 고객사로부터 입금받은 금액을 기록합니다.")
        
        # 미수금액이 있는 계약 필터링
        pending = settlement_df[pd.to_numeric(settlement_df.get('잔액', [0]), errors='coerce') > 0].copy()
        
        if pending.empty:
            st.success("✅ 모든 계약의 수금이 완료되었습니다!")
        else:
            st.markdown("#### 1️⃣ 입금 대상 선택")
            
            # 계약 선택
            pending_inq_ids = pending['문의ID'].unique()
            selected_inq = st.selectbox(
                "계약 선택",
                pending_inq_ids,
                key="settlement_inq"
            )
            
            # 선택된 계약 정보 표시
            contract_info = pending[pending['문의ID'] == selected_inq].iloc[0]
            
            st.markdown("#### 2️⃣ 현재 청구 현황")
            col_info1, col_info2, col_info3 = st.columns(3)
            
            with col_info1:
                supply = pd.to_numeric(contract_info.get('공급가액', 0), errors='coerce') or 0
                st.metric("공급가액", f"₩{int(supply):,}")
            
            with col_info2:
                paid = pd.to_numeric(contract_info.get('받은금액', 0), errors='coerce') or 0
                st.metric("받은금액", f"₩{int(paid):,}")
            
            with col_info3:
                balance = pd.to_numeric(contract_info.get('잔액', 0), errors='coerce') or 0
                st.metric("남은 잔액", f"₩{int(balance):,}")
            
            st.markdown("#### 3️⃣ 입금 정보 입력")
            
            # 입금 금액
            payment_amount = st.number_input(
                "입금 금액 (원)",
                min_value=0,
                max_value=int(balance) if balance > 0 else 100000000,
                step=10000,
                value=0,
                key="payment_amt"
            )
            
            # 입금일
            payment_date = st.date_input("입금일", value=datetime.now(), key="pay_date")
            
            # 입금 메모
            payment_memo = st.text_input(
                "입금 메모",
                placeholder="선금 / 중도금 / 잔금",
                key="pay_memo"
            )
            
            # 저장 버튼
            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                if st.button("💾 입금 기록 저장", use_container_width=True, key="save_payment"):
                    if payment_amount > 0:
                        st.success(f"""
                        ✅ 입금 기록 저장 완료!
                        - 계약: {selected_inq}
                        - 입금액: ₩{payment_amount:,}
                        - 입금일: {payment_date}
                        - 메모: {payment_memo}
                        """)
                        st.cache_data.clear()
                    else:
                        st.error("❌ 입금 금액을 입력해주세요.")
            
            with col_btn2:
                if st.button("❌ 취소", use_container_width=True, key="cancel_payment"):
                    st.info("취소되었습니다.")



# ==============================================================================
# 5-1. 탭 4: 평가 & 지급
# ==============================================================================

def tab_evaluation_payment(data):
    """탭3: 평가표 & 지급 - 평가 입력 + 급여 자동계산"""
    
    tab_eval, tab_payment = st.tabs(["📋 평가표", "💰 지급현황"])
    
    with tab_eval:
        st.markdown('<div class="section-title">⭐ 현장 평가</div>', unsafe_allow_html=True)
        
        # 배정된 인력 로드
        dispatch_df = db.load_dispatch_sheet()
        if dispatch_df is None:
            dispatch_df = pd.DataFrame()
        
        if dispatch_df.empty:
            st.warning("⚠️ 평가할 인력이 없습니다.")
            return
        
        # 평가 대상 선택
        evaluated_people = dispatch_df.get('이름', []).unique()
        eval_person = st.selectbox("평가 대상 선택", evaluated_people, key="eval_person")
        
        person_eval_data = dispatch_df[dispatch_df['이름'] == eval_person].iloc[0]
        
        st.write(f"**배정ID**: {person_eval_data.get('배정ID', 'N/A')}")
        
        # 5점 척도 평가
        st.markdown("#### 평가 항목 (1~5점)")
        
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            score_attitude = st.slider("근태", 1, 5, 3, key="eval_attitude")
        with col_e2:
            score_performance = st.slider("수행력", 1, 5, 3, key="eval_perf")
        with col_e3:
            score_personality = st.slider("태도", 1, 5, 3, key="eval_pers")
        
        col_e4, col_e5 = st.columns(2)
        with col_e4:
            score_communication = st.slider("의사소통", 1, 5, 3, key="eval_comm")
        with col_e5:
            score_adaptation = st.slider("현장적응", 1, 5, 3, key="eval_adapt")
        
        # 총점 계산
        total_score = (score_attitude + score_performance + score_personality + 
                      score_communication + score_adaptation) / 5
        
        # 등급 결정 (A/B/C/D)
        if total_score >= 4.5:
            grade = "🟢 A"
            bonus_rate = 0.10
        elif total_score >= 4.0:
            grade = "🔵 B"
            bonus_rate = 0.05
        elif total_score >= 3.0:
            grade = "🟡 C"
            bonus_rate = 0.0
        else:
            grade = "🔴 D"
            bonus_rate = -0.05
        
        col_calc1, col_calc2, col_calc3 = st.columns(3)
        with col_calc1:
            st.metric("총점", f"{total_score:.1f}점")
        with col_calc2:
            st.metric("평가등급", grade)
        with col_calc3:
            st.metric("보너스율", f"{bonus_rate*100:+.0f}%")
        
        # 평가 코멘트
        col_comment1, col_comment2 = st.columns(2)
        with col_comment1:
            strengths = st.text_area("강점", placeholder="예: 성실함, 전문성 우수...")
        with col_comment2:
            improvements = st.text_area("개선점", placeholder="예: 의견 제시 시 더 주도적으로...")
        
        recommend = st.checkbox("재추천 여부", value=total_score >= 3.5)
        
        # 평가 저장
        if st.button("✅ 평가 저장", use_container_width=True, key="save_eval"):
            st.success(f"✅ {eval_person}님의 평가가 저장되었습니다!")
    
    with tab_payment:
        st.markdown('<div class="section-title">💳 급여 자동계산</div>', unsafe_allow_html=True)
        
        # 배정된 인력 로드
        dispatch_df = db.load_dispatch_sheet()
        if dispatch_df is None:
            dispatch_df = pd.DataFrame()
        
        if dispatch_df.empty:
            st.warning("⚠️ 지급 대상이 없습니다.")
            return
        
        # 지급 대상 선택
        payment_people = dispatch_df.get('이름', []).unique()
        pay_person = st.selectbox("지급 대상 선택", payment_people, key="payment_person")
        
        person_pay_data = dispatch_df[dispatch_df['이름'] == pay_person].iloc[0]
        
        # 급여 계산
        base_salary = int(person_pay_data.get('단가', 0))
        days = int(person_pay_data.get('일수', 1))
        total_worked_hours = 8 * days  # 하루 8시간 기준
        
        # 기본급
        basic_pay = total_worked_hours * (base_salary / 8)
        
        # 야근비 (임시: 없음)
        overtime_pay = 0
        
        # 식사비
        meal_allowance = 30000
        
        # 교통비
        transportation = 20000
        
        # 보너스 (평가 기반 - 임시로 5% 설정)
        bonus = basic_pay * 0.05
        
        # 소계
        subtotal = basic_pay + overtime_pay + meal_allowance + transportation + bonus
        
        # 세금공제 (10% 추정)
        tax_deduction = subtotal * 0.10
        
        # 최종지급액
        final_payment = subtotal - tax_deduction
        
        # 급여 명세서 표시
        st.markdown("#### 💰 급여 명세서")
        
        col_pay1, col_pay2, col_pay3 = st.columns(3)
        with col_pay1:
            st.metric("기본급", f"₩{int(basic_pay):,}")
        with col_pay2:
            st.metric("보너스", f"₩{int(bonus):,}")
        with col_pay3:
            st.metric("식사비", f"₩{int(meal_allowance):,}")
        
        col_pay4, col_pay5, col_pay6 = st.columns(3)
        with col_pay4:
            st.metric("교통비", f"₩{int(transportation):,}")
        with col_pay5:
            st.metric("세금공제", f"₩{int(tax_deduction):,}")
        with col_pay6:
            st.metric("최종지급액", f"₩{int(final_payment):,}", 
                     delta=f"₩{int(bonus):,}")
        
        # 지급 상태
        col_status1, col_status2 = st.columns(2)
        with col_status1:
            payment_status = st.selectbox("지급상태", 
                                         ["대기", "확정", "완료", "반품"],
                                         key="pay_status")
        with col_status2:
            payment_date = st.date_input("지급일", value=datetime.now())
        
        memo = st.text_area("비고")
        
        # 지급 저장
        if st.button("✅ 지급 완료", use_container_width=True, key="save_payment"):
            st.success(f"✅ {pay_person}님의 급여 ₩{int(final_payment):,}가 확정되었습니다!")


# ==============================================================================
# 6. 메인 페이지
# ==============================================================================

def show(data):
    """메인 페이지"""
    apply_styles()
    
    st.title("👥 인력파견 시스템 v3.0")
    st.caption("🚀 스마트 AI 기반 인력배정 & 자동 급여계산 시스템")
    
    # 대시보드 요약
    st.markdown('<div class="section-title">📊 오늘의 현황</div>', unsafe_allow_html=True)
    
    col_dash1, col_dash2, col_dash3, col_dash4 = st.columns(4)
    
    dispatch_df = db.load_dispatch_sheet()
    if dispatch_df is None:
        dispatch_df = pd.DataFrame()
    
    with col_dash1:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-value">{len(dispatch_df) if not dispatch_df.empty else 0}</div>
            <div class="metric-label">배정 인력</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_dash2:
        if not dispatch_df.empty:
            total_cost = dispatch_df.get('총지급액', []).sum()
        else:
            total_cost = 0
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-value">₩{int(total_cost)/1000000:.1f}M</div>
            <div class="metric-label">예상 급여</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_dash3:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-value">4.6</div>
            <div class="metric-label">평균 평점</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_dash4:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-value">98%</div>
            <div class="metric-label">출석률</div>
        </div>
        """, unsafe_allow_html=True)
    
    # 탭 구조
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs([
        "🎯 인력배정",
        "📋 출석부",
        "⭐ 평가 & 지급"
    ])
    
    with tab1:
        tab_assignment(data)
    
    with tab2:
        tab_attendance(data)
    
    with tab3:
        tab_evaluation_payment(data)
