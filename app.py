# app.py
import streamlit as st

# 페이지 모듈 임포트
import page_dashboard  # 대시보드 (메인)
import page_inquiry   # 1단계: 문의
import page_estimate  # 2단계: 견적
import page_contract  # 3단계: 계약
import page_staff_new as page_staff     # 4단계: 인원배정 (고도화 버전)
import page_attendance # 5단계: 출석부
import page_settlement  # 6단계: 정산

# 데이터 모듈 임포트
import data_loader as db

# ==============================================================================
# 1. 기본 설정 (반드시 최상단)
# ==============================================================================
st.set_page_config(
    page_title="Gradius ERP",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 2. 스타일링 (전체 공통)
# ==============================================================================
st.markdown("""
<style>
    /* 사이드바 스타일 */
    [data-testid="stSidebar"] {
        background-color: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
    .sidebar-content {
        padding: 20px;
    }
    
    /* 버튼 스타일 통일 */
    .stButton>button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #fff;
        border-radius: 6px;
        border: 1px solid #e5e7eb;
        padding: 0 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #eff6ff;
        border-color: #3b82f6;
        color: #1e3a8a;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. 데이터 로드 (캐싱 적용)
# ==============================================================================
@st.cache_data(ttl=60) # 60초마다 만료 (자동 갱신 효과)
def load_all_data():
    return db.load_all_data()

# ==============================================================================
# 4. 사이드바 (메뉴 및 컨트롤)
# ==============================================================================
with st.sidebar:
    st.title("🦅 Gradius ERP")
    st.caption("Integrated Management System")
    st.markdown("---")
    
    # 메뉴 선택
    menu = st.radio(
        "업무 선택",
        [
            "� 경영 대시보드",
            "�📞 문의 접수 및 관리",
            "🧮 견적 통합 관리",
            "📝 계약 관리 및 승인",
            "👷 인원 배정 관리",
            "📋 출석부 관리",
            "💰 정산 및 급여 관리",
            "🚌 기타 (준비중)"
        ],
        index=0
    )
    
    st.markdown("---")
    
    # 데이터 새로고침 버튼
    if st.button("🔄 데이터 동기화", use_container_width=True):
        st.cache_data.clear() # 캐시 삭제
        st.rerun() # 앱 재실행
        
    st.markdown("""
    <div style='position: fixed; bottom: 20px; font-size: 12px; color: #94a3b8;'>
        v 1.0.0 | Powered by Streamlit
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 5. 페이지 라우팅
# ==============================================================================
# 데이터 로드
try:
    data = load_all_data()
except Exception as e:
    st.error(f"데이터 로드 중 오류 발생: {e}")
    st.stop()

# 메뉴에 따른 화면 표시
if "대시보드" in menu:
    page_dashboard.show(data)

elif "문의" in menu:
    page_inquiry.show(data)

elif "견적" in menu:
    page_estimate.show(data)

elif "계약" in menu:
    page_contract.show(data)

elif "인원" in menu:
    page_staff.show(data)

elif "출석" in menu:
    page_attendance.show(data)

elif "정산" in menu:
    page_settlement.show(data)

else:
    st.info("🚧 추가 기능은 현재 개발 중입니다. (Coming Soon)")