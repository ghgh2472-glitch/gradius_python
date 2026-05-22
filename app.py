# app.py
import streamlit as st
from datetime import datetime

# 페이지 모듈 임포트
import page_ceo        # 대표님 전용
import page_dashboard  # 대시보드 (메인)
import page_inquiry   # 1단계: 문의
import page_estimate  # 2단계: 견적
import page_contract  # 3단계: 계약
import page_staff_new as page_staff     # 4단계: 인원배정 (고도화 버전)
import data_management                   # 데이터 관리 도구
import page_attendance # 5단계: 출석부
import page_settlement  # 6단계: 정산
import page_project_detail  # 프로젝트 상세확인
import page_ai_assistant    # AI 비서 에이전트

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
# 3. 데이터 로드 (세션 기반 캐싱 — 메뉴 전환 시 즉시 응답)
# ==============================================================================

# ==============================================================================
# 4. 사이드바 (메뉴 및 컨트롤)
# ==============================================================================
with st.sidebar:
    st.title("🦅 Gradius ERP")
    st.caption("Integrated Management System")
    st.markdown("---")
    
    # 메뉴 선택
    _menu_items = [
        "🏢 대표님 전용",
        "📊 경영 대시보드",
        "📞 문의 접수 및 관리",
        "🧮 견적 통합 관리",
        "📝 계약 관리 및 승인",
        "👷 인원 배정 관리",
        "📋 출석부 관리",
        "💰 정산 및 급여 관리",
        "🔍 프로젝트 상세확인",
        "🤖 AI 비서",
        "🛠️ 데이터 관리"
    ]
    
    # 대시보드 바로가기 버튼 → 메뉴 전환
    _nav_map = {
        "대표님": 0, "문의": 2, "견적": 3, "계약": 4, "인원": 5,
        "출석": 6, "정산": 7, "상세확인": 8, "AI비서": 9, "데이터": 10
    }
    _default_idx = 0
    if '_nav_target' in st.session_state:
        _target = st.session_state.pop('_nav_target')
        _default_idx = _nav_map.get(_target, 0)
    
    menu = st.radio(
        "업무 선택",
        _menu_items,
        index=_default_idx
    )
    
    st.markdown("---")
    
    # 데이터 새로고침 버튼
    if st.button("🔄 데이터 동기화", use_container_width=True, help="클릭 시 구글 시트에서 최신 데이터를 다시 불러옵니다"):
        db.invalidate_data()
        st.rerun()
    
    # 마지막 동기화 시각 표시
    _loaded_at = st.session_state.get('_data_loaded_at', '')
    if _loaded_at:
        st.caption(f"📡 마지막 동기화: {_loaded_at}")
    st.caption("💡 저장 시 자동 동기화 | 버튼으로 수동 동기화")

    # 시트 서식 정리 버튼
    if st.button("🎨 시트 서식 정리", use_container_width=True, help="구글 시트의 서식(헤더, 열 너비, 색상 등)을 보기 좋게 정리합니다"):
        with st.spinner("시트 서식 적용 중..."):
            try:
                from format_sheets import format_all_sheets
                success = format_all_sheets()
                if success:
                    st.success("✅ 시트 서식이 정리되었습니다!")
                else:
                    st.error("❌ 서식 적용 실패")
            except Exception as e:
                st.error(f"❌ 서식 적용 오류: {e}")

    st.markdown("""
    <div style='position: fixed; bottom: 20px; font-size: 12px; color: #94a3b8;'>
        v 1.0.0 | Powered by Streamlit
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 5. 페이지 라우팅
# ==============================================================================
# 데이터 로드 (세션 캐시 활용 — 최초 1회만 구글시트 호출)
try:
    # 문의작성 시트 헤더 자동 확장 (복장/식사/주차 컬럼 보장)
    db.ensure_inquiry_headers()
    # 지급내역 시트 헤더 확장 (은행명/계좌번호/주민등록번호/문의ID 컬럼 보장)
    db.ensure_payment_headers()
    data = db.get_data()
except Exception as e:
    st.error(f"데이터 로드 중 오류 발생: {e}")
    st.stop()

# 메뉴에 따른 화면 표시
if "대표님" in menu:
    page_ceo.show(data)

elif "대시보드" in menu:
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

elif "상세확인" in menu:
    page_project_detail.show(data)

elif "AI 비서" in menu:
    page_ai_assistant.show(data)

elif "데이터 관리" in menu:
    data_management.show_data_management()

else:
    st.info("🚧 추가 기능은 현재 개발 중입니다. (Coming Soon)")

    # ------------------------------------------------------------------
    # 감사 로그 조회
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📋 감사 로그 (변경 이력)")
    from utils_audit import AuditLogger
    audit_df = AuditLogger.get_recent(30)
    if audit_df.empty:
        st.caption("아직 기록된 변경 이력이 없습니다.")
    else:
        st.dataframe(audit_df, use_container_width=True)

    # ------------------------------------------------------------------
    # Excel 일괄 내보내기
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📥 데이터 내보내기 (Excel)")
    from utils_export import export_multiple_sheets, render_download_button

    export_targets = {}
    for label, key in [("문의", "inq"), ("STAFF", "staff"), ("고객", "client")]:
        df = data.get(key, pd.DataFrame())
        if not df.empty:
            export_targets[label] = df

    if export_targets:
        excel_bytes = export_multiple_sheets(export_targets)
        render_download_button(
            excel_bytes,
            filename=f"Gradius_ERP_Export_{datetime.now().strftime('%Y%m%d')}.xlsx",
            label="📥 전체 데이터 Excel 다운로드",
        )
    else:
        st.caption("내보낼 데이터가 없습니다.")