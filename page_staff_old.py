# page_staff.py
import streamlit as st
import pandas as pd
import data_loader as db
from utils_staff import StaffBrain, get_staff_price_level
from datetime import datetime
import json

# ==============================================================================
# 1. 스타일링
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 1000px; padding-top: 1rem; }
        .staff-card { background-color: white; padding: 15px; border-radius: 8px; border-left: 4px solid #3b82f6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 10px; }
        .available-badge { background-color: #dbeafe; color: #0369a1; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .assigned-badge { background-color: #dcfce7; color: #166534; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .busy-badge { background-color: #fee2e2; color: #991b1b; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 유틸리티 함수
# ==============================================================================
def parse_staff_from_note(note_text):
    """
    특이사항 필드에서 배정된 인원 정보 파싱
    형식: JSON 배열
    """
    if not note_text or pd.isna(note_text):
        return []
    
    try:
        # JSON 형식 시도
        if isinstance(note_text, str) and (note_text.startswith('[') or note_text.startswith('{')):
            return json.loads(note_text)
    except:
        pass
    
    return []


def save_staff_assignment_record(inquiry_id, staff):
    """
    배정 레코드 하나를 '배정기록' 시트에 저장
    """
    try:
        pkg = {
            '문의ID': inquiry_id,
            '이름': staff.get('이름',''),
            '역할': staff.get('역할',''),
            '일수': staff.get('일수',1),
            '단가': staff.get('단가',0),
            '총지급액': staff.get('총지급액',0),
            '배정일시': staff.get('배정일시', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            '상태': staff.get('상태','배정중')
        }
        result = db.save_assignment_record(pkg)
        if result:
            st.success(f"배정됨: {staff.get('이름')} (문의ID: {inquiry_id})")
        else:
            st.error("배정 저장 실패했습니다.")
        return result
    except Exception as e:
        st.error(f"저장 실패: {str(e)}")
        return False

def get_available_staff(df_staff, assigned_ids):
    """
    현재 사용 가능한 스태프 목록 반환
    """
    if df_staff.empty:
        return pd.DataFrame()
    
    available = df_staff.copy()
    
    # 이미 배정된 인원 제외
    if assigned_ids:
        available = available[~available['이름'].isin(assigned_ids)]
    
    return available

# ==============================================================================
# 3. 메인 로직
# ==============================================================================
def show(data):
    apply_styles()
    st.title("👥 인원 배정 관리")
    
    df_inq = data.get('inq', pd.DataFrame())
    df_staff = data.get('staff', pd.DataFrame())
    
    # 배정기록은 별도의 더 짧은 TTL로 로드
    df_assign = db.load_dispatch_sheet()
    
    if df_inq.empty:
        st.warning("문의 데이터를 불러올 수 없습니다.")
        return

    # --------------------------------------------------------------------------
    # 배정 대상 필터링: 상태가 "체결"인 프로젝트만
    # --------------------------------------------------------------------------
    if '상태' not in df_inq.columns:
        df_inq['상태'] = ""
    
    # 상태가 "체결"인 건을 배정 대상으로 함
    eligible = df_inq[
        (df_inq['상태'].astype(str).str.strip() == '체결')
    ].copy()
    
    if eligible.empty:
        st.info("📌 배정할 프로젝트가 없습니다. (계약 완료 필요)")
        st.caption("계약 관리 단계에서 계약을 '체결'로 완료하면 여기서 인원을 배정할 수 있습니다.")
        return
    
    # --------------------------------------------------------------------------
    # 프로젝트 선택
    # --------------------------------------------------------------------------
    eligible['label'] = (
        eligible['업체명'].astype(str) + 
        " > " + 
        eligible['행사명'].astype(str)
    )
    
    sel_project = st.selectbox(
        "📂 프로젝트 선택",
        eligible['label'].unique(),
        help="계약이 완료된 프로젝트만 표시됩니다"
    )
    
    selected_row = eligible[eligible['label'] == sel_project].iloc[0]
    selected_idx = eligible[eligible['label'] == sel_project].index[0]
    
    # --------------------------------------------------------------------------
    # 선택된 프로젝트 정보 표시
    # --------------------------------------------------------------------------
    st.markdown("### 📋 프로젝트 정보")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("업체명", selected_row.get('업체명', '-'))
    with col2:
        st.metric("행사명", selected_row.get('행사명', '-'))
    with col3:
        st.metric("예상 인원", selected_row.get('인원수', '-'))
    with col4:
        st.metric("상태", selected_row.get('상태', '미지정'))
    
    st.divider()
    
    # --------------------------------------------------------------------------
    # 현재 배정 상황 (배정기록 시트에서 조회)
    # --------------------------------------------------------------------------
    st.markdown("### 👷 배정된 인원")
    
    # 배정기록 필터링
    current_assignment = []
    if not df_assign.empty:
        inquiry_id_str = str(selected_row.get('문의ID','')).strip()
        # 문의ID로 필터링
        matching = df_assign[df_assign['문의ID'].astype(str).str.strip() == inquiry_id_str].copy()
        
        # 상태가 '취소' 또는 '삭제'가 아닌 것만
        if not matching.empty and '상태' in matching.columns:
            matching = matching[~matching['상태'].astype(str).str.strip().isin(['취소','삭제'])]
        
        current_assignment = matching.to_dict(orient='records') if not matching.empty else []
    
    assigned_staff_names = [s.get('이름') for s in current_assignment if isinstance(s, dict) and s.get('이름')]
    
    if current_assignment:
        st.info(f"현재 {len(current_assignment)}명 배정됨")
        
        # 배정된 인원 테이블
        col_display = st.columns([2, 1, 1, 1, 1])
        with col_display[0]: st.write("**이름**")
        with col_display[1]: st.write("**역할**")
        with col_display[2]: st.write("**일수**")
        with col_display[3]: st.write("**단가**")
        with col_display[4]: st.write("**작업**")
        
        st.divider()

        for idx, staff in enumerate(current_assignment):
            if not isinstance(staff, dict):
                continue

            col_staff = st.columns([2, 1, 1, 1, 1])

            with col_staff[0]:
                st.write(staff.get('이름', '-'))
            with col_staff[1]:
                st.write(staff.get('역할', '-'))
            with col_staff[2]:
                st.write(str(staff.get('일수', '-')))
            with col_staff[3]:
                st.write(f"{staff.get('단가', 0):,}원")
            with col_staff[4]:
                assign_id = staff.get('배정ID') or staff.get('배정아이디') or staff.get('ID')
                if st.button("제거", key=f"remove_{idx}", use_container_width=True):
                    if assign_id:
                        if db.update_assignment_status(assign_id, '취소'):
                            st.success("인원이 제거(취소) 처리되었습니다.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("삭제 처리에 실패했습니다.")
                    else:
                        st.error("해당 배정의 ID를 찾을 수 없습니다.")
        
        st.divider()
    else:
        st.info("아직 배정된 인원이 없습니다.")
    
    # --------------------------------------------------------------------------
    # 스태프 검색 (필터 + 카드형 결과)
    # --------------------------------------------------------------------------
    st.markdown("### 🔎 스태프 검색")
    brain = StaffBrain(df_staff)

    # 필터 레이아웃
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)
    with fcol1:
        name_kw = st.text_input("이름 검색 (키워드)", value="")
        gender = st.selectbox("성별", options=["무관"] + sorted(df_staff['성별'].dropna().unique().astype(str).tolist()), index=0)
    with fcol2:
        age_groups = st.multiselect("연령대", options=sorted(df_staff.get('연령대', pd.Series([])).dropna().unique().tolist()), default=[])
        rec_levels = st.multiselect("추천도", options=sorted(df_staff.get('추천도', pd.Series([])).dropna().unique().tolist()), default=[])
    with fcol3:
        min_height = st.number_input("최소 키(cm)", min_value=0, value=0)
        min_score = st.number_input("최소 총점", min_value=0, value=0)
    with fcol4:
        english = st.selectbox("영어", options=["무관","가능","불가"], index=0)
        driving = st.selectbox("운전", options=["무관","가능","불가"], index=0)

    # 기타 필드 (OR 검색, 쉼표 구분)
    rcol1, rcol2 = st.columns(2)
    with rcol1:
        region_kw = st.text_input("거주지 (콤마로 OR)", value="")
    with rcol2:
        role_kw = st.text_input("가능직무 (콤마로 OR)", value="")

    if st.button("검색", type="secondary", use_container_width=True):
        filters = {
            'name': name_kw,
            'gender': gender,
            'age_groups': age_groups,
            'rec_levels': rec_levels,
            'min_height': min_height,
            'min_score': min_score,
            'english': english if english != '무관' else None,
            'driving': driving if driving != '무관' else None,
            'region': region_kw,
            'role': role_kw
        }
        result = brain.search_staff(filters)

        if result.empty:
            st.info("검색 결과가 없습니다.")
        else:
            st.markdown(f"**검색 결과: {len(result)}명**")
            # 카드형 결과 표시 (3열)
            cards_per_row = 3
            rows = (len(result) + cards_per_row - 1) // cards_per_row
            idx = 0
            for r in range(rows):
                cols = st.columns(cards_per_row)
                for c in cols:
                    if idx >= len(result):
                        break
                    row = result.iloc[idx]
                    name = row.get('이름','')
                    rec = row.get('추천도','')
                    sex = row.get('성별','')
                    age = row.get('실제나이','')
                    height = row.get('키','')
                    phone = row.get('연락처','')
                    total = row.get('총점','')
                    memo = row.get('총평','')

                    # Build a safe card HTML without native <form> or buttons that trigger browser navigation
                    card_html = f"""
                    <div class='staff-card'>
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <div style='font-weight:700; font-size:16px;'>{name} <span style='font-size:12px; color:#6b7280;'>({sex} · {age})</span></div>
                            <div style='text-align:right;'>추천도: <b>{rec}</b></div>
                        </div>
                        <div style='margin-top:6px; color:#374151;'>키: {height} cm · 총점: {total}</div>
                        <div style='margin-top:6px; color:#374151; font-size:13px;'>{memo}</div>
                        <div style='margin-top:8px; display:flex; justify-content:space-between; align-items:center;'>
                            <div style='font-size:12px; color:#6b7280;'>{row.get('가능직무','')}</div>
                            <div style='font-size:12px; color:#6b7280;'>{row.get('자격증','')}</div>
                        </div>
                        <div style='margin-top:8px; display:flex; justify-content:space-between; align-items:center;'>
                            <div style='font-size:12px; color:#9ca3af;'>연락처: {phone}</div>
                            <div style='font-size:12px; color:#6b7280;'>소속: {row.get('소속','')}</div>
                        </div>
                    </div>
                    """

                    c.markdown(card_html, unsafe_allow_html=True)

                    # 배정 버튼 (Streamlit 버튼 under the card)
                    if c.button("배정", key=f"card_assign_{idx}", type="primary"):
                        # build minimal staff payload
                        s = {
                            '이름': name,
                            '역할': row.get('가능직무','').split(',')[0] if row.get('가능직무') else '',
                            '일수': 1,
                            '단가': get_staff_price_level(rec),
                            '총지급액': get_staff_price_level(rec) * 1,
                            '배정일시': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        with st.spinner(f"{name}님 배정 중..."):
                            ok = save_staff_assignment_record(selected_row.get('문의ID',''), s)
                        
                        if ok:
                            # 캐시 초기화: 모든 캐시 제거
                            db.load_all_data.clear()
                            db.load_dispatch_sheet.clear()
                            st.rerun()
                        else:
                            st.error("배정 저장에 실패했습니다.")

                    idx += 1

    st.divider()

    # --------------------------------------------------------------------------
    # 새 인원 배정 추가
    # --------------------------------------------------------------------------
    st.markdown("### ➕ 새 인원 추가")
    
    # 사용 가능한 스태프
    available_staff = get_available_staff(df_staff, assigned_staff_names)
    
    if available_staff.empty:
        st.warning("사용 가능한 스태프가 없습니다.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            staff_options = available_staff['이름'].tolist()
            sel_staff = st.selectbox("👤 스태프 선택", staff_options)
            sel_staff_row = available_staff[available_staff['이름'] == sel_staff].iloc[0]
        
        with col2:
            role = st.text_input("역할", placeholder="예: 가이드", value="")
        
        with col3:
            days = st.number_input("일수", min_value=1, max_value=30, value=1)
        
        with col4:
            # 스태프의 추천도/등급에 따른 기본 단가
            default_rate = 100000  # 기본값
            rate = st.number_input("단가(원)", min_value=10000, step=10000, value=default_rate)
        
        if st.button("✅ 배정하기", type="primary", use_container_width=True):
            new_staff = {
                '이름': sel_staff,
                '역할': role,
                '일수': int(days),
                '단가': int(rate),
                '총지급액': int(days) * int(rate),
                '배정일시': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            with st.spinner(f"{sel_staff}님 배정 중..."):
                ok = save_staff_assignment_record(selected_row.get('문의ID',''), new_staff)
            
            if ok:
                # 캐시 초기화: 모든 캐시 제거
                db.load_all_data.clear()
                db.load_dispatch_sheet.clear()
                st.rerun()
            else:
                st.error("배정 저장에 실패했습니다.")
    
    st.divider()
    
    # --------------------------------------------------------------------------
    # 배정 완료 버튼
    # --------------------------------------------------------------------------
    if current_assignment:
        total_assigned = len(current_assignment)
        required_staff = selected_row.get('인원수', 1)
        
        col_info, col_btn = st.columns([3, 1])
        
        with col_info:
            if total_assigned >= required_staff:
                st.success(f"✅ 필요 인원 {required_staff}명 이상 배정 완료 ({total_assigned}명)")
            else:
                st.warning(f"⚠️ 필요 인원: {required_staff}명, 현재: {total_assigned}명")
        
        with col_btn:
            if st.button("🏁 배정 완료", type="primary", use_container_width=True):
                # 문의작성 시트의 상태를 '배정완료'로 업데이트
                try:
                    # 문의ID로 행 찾기
                    inquiry_id = selected_row['문의ID']
                    
                    # Google Sheets 직접 업데이트 (상태 컬럼 변경)
                    if db.update_cell("문의작성", inquiry_id, col_name="상태", value="배정완료"):
                        st.success("🎉 인원 배정이 완료되었습니다!")
                        st.info("✅ 다음 단계: 정산 및 급여 관리에서 청구금액 및 급여를 정산할 수 있습니다.")
                        
                        # 캐시 초기화
                        db.load_all_data.clear()
                        db.load_dispatch_sheet.clear()
                        st.rerun()
                    else:
                        st.error("상태 업데이트에 실패했습니다.")
                except Exception as e:
                    st.error(f"상태 업데이트 실패: {e}")
    else:
        st.info("인원을 배정한 후 '배정 완료' 버튼을 클릭하세요.")
    
    # --------------------------------------------------------------------------
    # 스태프 목록 (참고용)
    # --------------------------------------------------------------------------
    with st.expander("📊 전체 스태프 조회", expanded=False):
        if not df_staff.empty:
            display_cols = ['이름', '성별', '나이', '거주지', '연락처']
            available_cols = [c for c in display_cols if c in df_staff.columns]
            
            st.dataframe(
                df_staff[available_cols],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("스태프 정보를 불러올 수 없습니다.")