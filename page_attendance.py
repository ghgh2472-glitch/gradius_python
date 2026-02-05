# page_attendance.py
"""
출석부 관리 및 증명 페이지
- 배정기록에서 직원 정보 로드
- 일일 출석 상태 기록
- 출석 증명서 생성 및 내보내기
"""
import streamlit as st
import pandas as pd
import data_loader as db
from datetime import datetime, timedelta
import json

# ==============================================================================
# 1. 스타일링
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 1200px; padding-top: 1rem; }
        .attendance-card { 
            background-color: white; 
            padding: 15px; 
            border-radius: 8px; 
            border-left: 4px solid #3b82f6; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
            margin-bottom: 10px; 
        }
        .present-badge { background-color: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .absent-badge { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .late-badge { background-color: #fef3c7; color: #92400e; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .summary-metric { 
            background-color: #f3f4f6; 
            padding: 15px; 
            border-radius: 6px; 
            text-align: center;
            margin-bottom: 10px;
        }
        .metric-title { font-size: 12px; color: #6b7280; font-weight: 600; }
        .metric-value { font-size: 24px; font-weight: 800; color: #111827; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 배정기록 로드 및 처리
# ==============================================================================
def get_active_assignments(inquiry_id=None):
    """
    활성 배정 기록 조회
    inquiry_id: 특정 문의에 대한 배정만 조회 (None이면 전체)
    """
    dispatch_df = db.load_dispatch_sheet()
    if dispatch_df is None or dispatch_df.empty:
        return pd.DataFrame()
    
    # 상태 필터링: 배정중 또는 진행중 만 (완료/취소 제외)
    valid_statuses = ['배정중', '진행중', '']
    dispatch_df = dispatch_df[dispatch_df.get('상태', '').astype(str).isin(valid_statuses)]
    
    # 특정 문의에 대해서만 조회
    if inquiry_id:
        dispatch_df = dispatch_df[dispatch_df.get('문의ID', '').astype(str) == str(inquiry_id)]
    
    return dispatch_df.sort_values('배정일시', ascending=False) if not dispatch_df.empty else pd.DataFrame()


def get_attendance_data(assignment_id):
    """
    특정 배정에 대한 출석 데이터 로드
    Google Sheet의 '출석부' 시트에서 조회
    """
    client = db.get_connection()
    if not client:
        return pd.DataFrame()
    
    try:
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("출석부")
        records = wks.get_all_records()
        df = pd.DataFrame(records)
        df = df[df.get('배정ID', '').astype(str) == str(assignment_id)]
        return df
    except:
        return pd.DataFrame()


def save_attendance_record(assignment_id, attendance_date, status, note=''):
    """
    출석 기록 저장
    status: '출석', '결근', '지각', '조퇴'
    """
    client = db.get_connection()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("출석부")
        
        # 기존 기록 확인
        records = wks.get_all_records()
        df = pd.DataFrame(records)
        existing = df[
            (df.get('배정ID', '').astype(str) == str(assignment_id)) &
            (df.get('출석일자', '').astype(str) == str(attendance_date))
        ]
        
        if not existing.empty:
            # 업데이트: 기존 행 찾기
            row_idx = None
            for i, rec in enumerate(records):
                if (rec.get('배정ID', '') == str(assignment_id) and 
                    rec.get('출석일자', '') == str(attendance_date)):
                    row_idx = i + 2
                    break
            
            if row_idx:
                headers = wks.row_values(1)
                headers_clean = [str(h).strip() for h in headers]
                
                # 상태 및 비고 컬럼 위치 찾기
                status_col = headers_clean.index('상태') + 1 if '상태' in headers_clean else 3
                note_col = headers_clean.index('비고') + 1 if '비고' in headers_clean else 4
                
                wks.update_cell(row_idx, status_col, status)
                if note:
                    wks.update_cell(row_idx, note_col, note)
                return True
        else:
            # 신규 기록
            headers = wks.row_values(1)
            headers_clean = [str(h).strip() for h in headers]
            
            new_row = [assignment_id, attendance_date, status, note] + [''] * (len(headers) - 4)
            wks.append_row(new_row)
            return True
    except Exception as e:
        print(f"Attendance save error: {e}")
        return False


# ==============================================================================
# 3. 출석 증명서 HTML 생성
# ==============================================================================
def generate_certificate_html(staff_name, inquiry_name, total_days, attended_days):
    """
    출석 증명서 HTML 생성
    """
    attendance_rate = (attended_days / total_days * 100) if total_days > 0 else 0
    today = datetime.now().strftime('%Y년 %m월 %d일')
    
    html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Arial', sans-serif; margin: 40px; }}
            .certificate {{ 
                border: 3px solid #333; 
                padding: 40px; 
                text-align: center;
                max-width: 800px;
                margin: 0 auto;
            }}
            .title {{ font-size: 28px; font-weight: bold; margin-bottom: 30px; }}
            .info-table {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin: 30px 0;
            }}
            .info-table td {{ 
                border: 1px solid #ccc; 
                padding: 12px; 
                text-align: left;
            }}
            .info-table td:first-child {{ 
                font-weight: bold; 
                width: 30%;
                background-color: #f5f5f5;
            }}
            .signature {{ margin-top: 40px; text-align: right; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="certificate">
            <div class="title">근무 증명서</div>
            
            <table class="info-table">
                <tr>
                    <td>성명</td>
                    <td>{staff_name}</td>
                </tr>
                <tr>
                    <td>프로젝트명</td>
                    <td>{inquiry_name}</td>
                </tr>
                <tr>
                    <td>근무 기간</td>
                    <td>{total_days}일</td>
                </tr>
                <tr>
                    <td>실제 출석</td>
                    <td>{attended_days}일</td>
                </tr>
                <tr>
                    <td>출석률</td>
                    <td>{attendance_rate:.1f}%</td>
                </tr>
            </table>
            
            <p>위 직원은 상기 프로젝트에 위 기간 동안 근무하였음을 증명합니다.</p>
            
            <div class="signature">
                <div>{today}</div>
                <div style="margin-top: 40px;">_______________</div>
                <div>발행자 서명</div>
            </div>
            
            <div class="footer">
                This document is computer-generated and does not require a signature.
            </div>
        </div>
    </body>
    </html>
    """
    return html


# ==============================================================================
# 4. 메인 UI
# ==============================================================================
def show(data):
    apply_styles()
    
    # 출석부 시트 확인 및 생성
    db.ensure_attendance_sheet()
    
    st.title("Attendance Management")
    
    # 데이터 로드
    df_inq = data.get('inq', pd.DataFrame())
    
    # 탭 분리
    tab_list, tab_input, tab_cert = st.tabs(["Attendance List", "Record Entry", "Certificate"])
    
    # ========================================================================
    # 탭1: 출석 목록
    # ========================================================================
    with tab_list:
        st.subheader("Recorded Attendance")
        
        # 프로젝트 선택
        col1, col2 = st.columns([2, 2])
        with col1:
            if not df_inq.empty:
                # 다이나믹 날짜 컬럼 선택
                date_cols = [col for col in df_inq.columns if any(x in col for x in ['날짜', '일', 'date'])]
                sort_col = date_cols[0] if date_cols else df_inq.columns[0]
                
                projects = df_inq.sort_values(sort_col, ascending=False) if sort_col in df_inq.columns else df_inq
                selected_project = st.selectbox(
                    "프로젝트 선택",
                    projects.index,
                    format_func=lambda x: f"{projects.loc[x, '업체명']} ({projects.loc[x, '행사명']})"
                )
                inquiry_id = projects.loc[selected_project, '문의ID']
            else:
                st.warning("프로젝트 정보가 없습니다.")
                return
        
        # 배정 인원 로드
        assignments = get_active_assignments(inquiry_id)
        
        if assignments.empty:
            st.info("이 프로젝트에 배정된 인원이 없습니다.")
        else:
            # 요약 통계
            total_staff = len(assignments)
            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(f"""
                <div class="summary-metric">
                    <div class="metric-title">배정 인원</div>
                    <div class="metric-value">{total_staff}</div>
                </div>
                """, unsafe_allow_html=True)
            with m2:
                st.markdown(f"""
                <div class="summary-metric">
                    <div class="metric-title">활성 배정</div>
                    <div class="metric-value">{len(assignments[assignments.get('상태', '').astype(str) == '배정중'])}</div>
                </div>
                """, unsafe_allow_html=True)
            with m3:
                st.markdown(f"""
                <div class="summary-metric">
                    <div class="metric-title">완료</div>
                    <div class="metric-value">{len(assignments[assignments.get('상태', '').astype(str) == '완료'])}</div>
                </div>
                """, unsafe_allow_html=True)
            
            st.divider()
            
            # 배정 인원 목록
            st.subheader("배정된 인원 목록")
            for idx, row in assignments.iterrows():
                name = row.get('이름', '(이름 없음)')
                role = row.get('역할', '')
                days = row.get('일수', '-')
                status = row.get('상태', '배정중')
                contact = row.get('연락처', '')
                
                with st.expander(f"{name} ({role}) - {days}일"):
                    col_info1, col_info2 = st.columns(2)
                    with col_info1:
                        st.write(f"**배정ID**: {row.get('배정ID', '')}")
                        st.write(f"**역할**: {role}")
                        st.write(f"**배정 기간**: {days}일")
                    with col_info2:
                        st.write(f"**상태**: {status}")
                        st.write(f"**연락처**: {contact}")
                        st.write(f"**소속**: {row.get('소속', '')}")
    
    # ========================================================================
    # Tab 2: Record Entry
    # ========================================================================
    with tab_input:
        st.subheader("Record Attendance")
        
        if df_inq.empty:
            st.warning("프로젝트 정보가 없습니다.")
        else:
            # 프로젝트/인원 선택
            col_p, col_s = st.columns(2)
            with col_p:
                # 다이나믹 날짜 컬럼 선택
                date_cols = [col for col in df_inq.columns if any(x in col for x in ['날짜', '일', 'date'])]
                sort_col = date_cols[0] if date_cols else df_inq.columns[0]
                projects = df_inq.sort_values(sort_col, ascending=False) if sort_col in df_inq.columns else df_inq
                sel_p_idx = st.selectbox(
                    "프로젝트",
                    projects.index,
                    key="input_project",
                    format_func=lambda x: f"{projects.loc[x, '업체명']} ({projects.loc[x, '행사명']})"
                )
                sel_inquiry_id = projects.loc[sel_p_idx, '문의ID']
            
            assignments_sel = get_active_assignments(sel_inquiry_id)
            
            with col_s:
                if not assignments_sel.empty:
                    staff_options = assignments_sel[['이름', '역할', '배정ID']].drop_duplicates()
                    staff_labels = [f"{row['이름']} ({row['역할']})" for _, row in staff_options.iterrows()]
                    selected_staff_idx = st.selectbox("인원 선택", range(len(staff_options)), format_func=lambda x: staff_labels[x])
                    selected_assign_id = staff_options.iloc[selected_staff_idx]['배정ID']
                else:
                    st.warning("배정된 인원이 없습니다.")
                    selected_assign_id = None
            
            if selected_assign_id:
                # 출석 정보 입력
                st.write("---")
                col_date, col_status, col_note = st.columns([1, 1, 1.5])
                with col_date:
                    att_date = st.date_input("출석일자", datetime.now())
                with col_status:
                    att_status = st.selectbox("상태", ["출석", "결근", "지각", "조퇴"], index=0)
                with col_note:
                    att_note = st.text_input("비고")
                
                if st.button("출석 기록 저장", type="primary"):
                    result = save_attendance_record(
                        selected_assign_id,
                        att_date.strftime('%Y-%m-%d'),
                        att_status,
                        att_note
                    )
                    if result:
                        st.success(f"{att_date} 출석 기록이 저장되었습니다.")
                    else:
                        st.error("출석 기록 저장에 실패했습니다.")
    
    # ========================================================================
    # 탭3: 증명서 생성
    # ========================================================================
    with tab_cert:
        st.subheader("출석 증명서 생성")
        
        if df_inq.empty:
            st.warning("프로젝트 정보가 없습니다.")
        else:
            # 다이나믹 날짜 컬럼 선택
            date_cols = [col for col in df_inq.columns if any(x in col for x in ['날짜', '일', 'date'])]
            sort_col = date_cols[0] if date_cols else df_inq.columns[0]
            projects = df_inq.sort_values(sort_col, ascending=False) if sort_col in df_inq.columns else df_inq
            sel_p_idx_cert = st.selectbox(
                "프로젝트 선택",
                projects.index,
                key="cert_project",
                format_func=lambda x: f"{projects.loc[x, '업체명']} ({projects.loc[x, '행사명']})"
            )
            sel_inquiry_id_cert = projects.loc[sel_p_idx_cert, '문의ID']
            project_name = projects.loc[sel_p_idx_cert, '행사명']
            
            assignments_cert = get_active_assignments(sel_inquiry_id_cert)
            
            if not assignments_cert.empty:
                staff_options_cert = assignments_cert[['이름', '역할', '배정ID']].drop_duplicates()
                staff_labels_cert = [f"{row['이름']} ({row['역할']})" for _, row in staff_options_cert.iterrows()]
                selected_staff_idx_cert = st.selectbox(
                    "인원 선택",
                    range(len(staff_options_cert)),
                    format_func=lambda x: staff_labels_cert[x],
                    key="cert_staff"
                )
                
                selected_staff = staff_options_cert.iloc[selected_staff_idx_cert]
                staff_name = selected_staff['이름']
                total_days = int(assignments_cert[assignments_cert['이름'] == staff_name]['일수'].iloc[0] or 1)
                
                # 기본값: 모든 배정 일수 출석
                attended_days = st.number_input("출석한 일수", min_value=0, max_value=total_days, value=total_days)
                
                if st.button("증명서 생성", type="primary"):
                    cert_html = generate_certificate_html(
                        staff_name,
                        project_name,
                        total_days,
                        attended_days
                    )
                    st.components.v1.html(cert_html, height=700, scrolling=True)
                    
                    st.download_button(
                        label="증명서 다운로드 (HTML)",
                        data=cert_html,
                        file_name=f"{staff_name}_출석증명_{datetime.now().strftime('%Y%m%d')}.html",
                        mime="text/html"
                    )
            else:
                st.warning("배정된 인원이 없습니다.")
