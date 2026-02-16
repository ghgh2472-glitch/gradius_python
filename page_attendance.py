# page_attendance.py  v2.0
"""
출석부 관리 — 실제 현장 출석부 스타일
- 배정기록(15컬럼)에서 인력 정보 로드
- 일일 출석 상태 기록
- 인쇄용 출석부 HTML 생성 (인쇄/저장)
- 출석 증명서 생성
"""
import streamlit as st
import pandas as pd
import data_loader as db
from datetime import datetime, timedelta
import json


def _parse_event_date(val):
    """행사시작일/종료일 문자열을 date 객체로 변환"""
    if not val or str(val).strip() == '':
        return None
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# 배정기록 컬럼명 매핑 (시트 실제 컬럼 → 표시명)
COL_MAP = {
    '배정ID': '배정ID',
    '문의ID': '문의ID',
    '행사명': '행사명',
    '인력명': '인력명',
    '구분': '구분',
    '직무': '직무',
    '연락처': '연락처',
    '주민등록번호': '주민등록번호',
    '은행명': '은행명',
    '계좌번호': '계좌번호',
    '지급단가': '지급단가',
    '근무일수': '근무일수',
    '총지급액': '총지급액',
    '지급상태': '지급상태',
    '배정일시': '배정일시',
}


def _safe_col(df, candidates):
    """DataFrame에서 후보 컬럼명 중 실제 존재하는 것을 반환"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


# ==============================================================================
# 1. 스타일링
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 1200px; padding-top: 1rem; }
        .attendance-card { 
            background-color: white; padding: 15px; border-radius: 8px; 
            border-left: 4px solid #3b82f6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
            margin-bottom: 10px; 
        }
        .present-badge { background-color: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .absent-badge { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .late-badge { background-color: #fef3c7; color: #92400e; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .summary-metric { background-color: #f3f4f6; padding: 15px; border-radius: 6px; text-align: center; margin-bottom: 10px; }
        .metric-title { font-size: 12px; color: #6b7280; font-weight: 600; }
        .metric-value { font-size: 24px; font-weight: 800; color: #111827; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# 2. 데이터 로드
# ==============================================================================
def get_active_assignments(inquiry_id=None):
    """활성 배정 기록 조회 (배정기록 15컬럼)"""
    dispatch_data = db.load_dispatch_data()
    dispatch_df = dispatch_data.get('dispatch', pd.DataFrame())
    if dispatch_df.empty:
        return pd.DataFrame()

    # 문의ID 필터
    if inquiry_id:
        id_col = _safe_col(dispatch_df, ['문의ID'])
        if id_col:
            dispatch_df = dispatch_df[dispatch_df[id_col].astype(str).str.strip() == str(inquiry_id).strip()]

    # 정렬
    sort_col = _safe_col(dispatch_df, ['배정일시'])
    if sort_col:
        dispatch_df = dispatch_df.sort_values(sort_col, ascending=False)

    return dispatch_df


@st.cache_data(ttl=60)
def get_attendance_data(assignment_id=None, inquiry_id=None):
    """출석부 시트에서 데이터 로드 (캐시 60초)"""
    client = db.get_connection()
    if not client:
        return pd.DataFrame()
    try:
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("출석부")
        records = wks.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return df
        if assignment_id:
            id_col = _safe_col(df, ['배정ID'])
            if id_col:
                df = df[df[id_col].astype(str) == str(assignment_id)]
        if inquiry_id:
            inq_col = _safe_col(df, ['문의ID'])
            if inq_col:
                df = df[df[inq_col].astype(str).str.strip() == str(inquiry_id).strip()]
        return df
    except Exception:
        return pd.DataFrame()


def save_attendance_record(assignment_id, staff_name, inquiry_id, attendance_date, status, check_in='', check_out='', note=''):
    """출석 기록 저장"""
    attendance_dict = {
        "배정ID": str(assignment_id),
        "문의ID": str(inquiry_id),
        "인력명": str(staff_name),
        "출석날짜": str(attendance_date),
        "출근시간": str(check_in),
        "퇴근시간": str(check_out),
        "근무시간": 0,
        "일급여": 0,
        "출석상태": status,
        "사유": "",
        "비고": note or "",
        "기록일시": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return db.save_attendance_record(attendance_dict)


# ==============================================================================
# 3. 인쇄용 출석부 HTML
# ==============================================================================
def generate_printable_attendance_html(event_name, company, location, date_range, staff_list, dates, attendance_records):
    """
    실제 현장 출석부 스타일 HTML 생성
    staff_list: [{이름, 직무, 연락처}, ...]
    dates: ['2026-02-20', '2026-02-21', ...]
    attendance_records: DataFrame (출석부 시트 데이터)
    """
    today = datetime.now().strftime('%Y-%m-%d')

    # 날짜 헤더 (월/일만)
    date_headers = ""
    for d in dates:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            date_headers += f'<th style="width:60px;">{dt.month}/{dt.day}<br/>({["월","화","수","목","금","토","일"][dt.weekday()]})</th>'
        except Exception:
            date_headers += f'<th style="width:60px;">{d}</th>'

    # 인력별 행
    rows_html = ""
    for i, staff in enumerate(staff_list, 1):
        name = staff.get('인력명', '')
        role = staff.get('직무', '')
        contact = staff.get('연락처', '')
        assign_id = staff.get('배정ID', '')

        cells = ""
        for d in dates:
            # 출석 데이터에서 해당 인력+날짜 매칭
            status_mark = ""
            if not attendance_records.empty:
                date_col = _safe_col(attendance_records, ['출석날짜'])
                name_col = _safe_col(attendance_records, ['인력명'])
                status_col = _safe_col(attendance_records, ['출석상태'])
                if date_col and name_col and status_col:
                    matched = attendance_records[
                        (attendance_records[name_col].astype(str).str.strip() == name.strip()) &
                        (attendance_records[date_col].astype(str).str.strip() == d)
                    ]
                    if not matched.empty:
                        s = str(matched.iloc[0][status_col])
                        if '출석' in s:
                            status_mark = "✅"
                        elif '결근' in s:
                            status_mark = "❌"
                        elif '지각' in s:
                            status_mark = "⏰"
                        elif '조퇴' in s:
                            status_mark = "🔻"

            cells += f'<td style="text-align:center; height:36px;">{status_mark}</td>'

        rows_html += f"""
        <tr>
            <td style="text-align:center;">{i}</td>
            <td style="text-align:center; font-weight:bold;">{name}</td>
            <td style="text-align:center;">{role}</td>
            <td style="text-align:center; font-size:11px;">{contact}</td>
            {cells}
            <td style="text-align:center;">서명란</td>
        </tr>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <title>출석부 - {event_name}</title>
    <style>
        @media print {{
            body {{ margin: 0; padding: 10mm; }}
            .no-print {{ display: none !important; }}
        }}
        body {{
            font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
            color: #222;
            margin: 20px;
        }}
        .header-section {{
            text-align: center;
            margin-bottom: 20px;
        }}
        .header-section h1 {{
            font-size: 28px;
            margin: 0;
            letter-spacing: 10px;
        }}
        .info-box {{
            display: flex;
            justify-content: space-between;
            border: 1px solid #333;
            margin-bottom: 15px;
        }}
        .info-box .item {{
            flex: 1;
            padding: 8px 12px;
            border-right: 1px solid #333;
            font-size: 13px;
        }}
        .info-box .item:last-child {{ border-right: none; }}
        .info-box .label {{ font-weight: bold; color: #555; font-size: 11px; }}
        .info-box .value {{ font-size: 14px; margin-top: 2px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }}
        th, td {{
            border: 1px solid #333;
            padding: 6px 4px;
        }}
        th {{
            background-color: #f0f0f0;
            font-weight: bold;
            text-align: center;
            font-size: 11px;
        }}
        .legend {{
            margin-top: 15px;
            font-size: 11px;
            color: #666;
        }}
        .footer-sign {{
            display: flex;
            justify-content: flex-end;
            margin-top: 30px;
            gap: 40px;
        }}
        .sign-box {{
            text-align: center;
            width: 150px;
        }}
        .sign-box .line {{
            border-bottom: 1px solid #333;
            height: 40px;
            margin-bottom: 5px;
        }}
        .sign-box .label {{ font-size: 12px; color: #555; }}
        .print-btn {{
            position: fixed;
            top: 10px;
            right: 10px;
            background: #3B82F6;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            z-index: 999;
        }}
        .print-btn:hover {{ background: #2563EB; }}
    </style>
    </head>
    <body>
    <button class="print-btn no-print" onclick="window.print()">🖨️ 인쇄하기</button>

    <div class="header-section">
        <h1>출 석 부</h1>
        <p style="color:#666; font-size:13px; margin-top:5px;">(주) 가디어스 인력파견</p>
    </div>

    <div class="info-box">
        <div class="item">
            <div class="label">현장명 / 행사명</div>
            <div class="value">{event_name}</div>
        </div>
        <div class="item">
            <div class="label">업체명</div>
            <div class="value">{company}</div>
        </div>
        <div class="item">
            <div class="label">현장주소</div>
            <div class="value">{location}</div>
        </div>
        <div class="item">
            <div class="label">파견기간</div>
            <div class="value">{date_range}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width:30px;">No</th>
                <th style="width:70px;">성명</th>
                <th style="width:70px;">직무</th>
                <th style="width:100px;">연락처</th>
                {date_headers}
                <th style="width:70px;">서명</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="legend">
        ✅ 출석 &nbsp; ❌ 결근 &nbsp; ⏰ 지각 &nbsp; 🔻 조퇴 &nbsp; (빈칸: 미기록)
    </div>

    <div class="footer-sign">
        <div class="sign-box">
            <div class="line"></div>
            <div class="label">현장 책임자</div>
        </div>
        <div class="sign-box">
            <div class="line"></div>
            <div class="label">업체 담당자</div>
        </div>
    </div>

    <p style="text-align:center; color:#999; font-size:10px; margin-top:30px;">
        출력일: {today} &nbsp;|&nbsp; (주)가디어스 Gradius ERP System
    </p>
    </body>
    </html>
    """
    return html


# ==============================================================================
# 4. 증명서 HTML
# ==============================================================================
def generate_certificate_html(staff_name, inquiry_name, total_days, attended_days):
    attendance_rate = (attended_days / total_days * 100) if total_days > 0 else 0
    today = datetime.now().strftime('%Y년 %m월 %d일')
    html = f"""
    <html><head><meta charset="UTF-8">
    <style>
        body {{ font-family: 'Malgun Gothic', sans-serif; margin: 40px; }}
        .certificate {{ border: 3px solid #333; padding: 40px; text-align: center; max-width: 800px; margin: 0 auto; }}
        .title {{ font-size: 28px; font-weight: bold; margin-bottom: 30px; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin: 30px 0; }}
        .info-table td {{ border: 1px solid #ccc; padding: 12px; text-align: left; }}
        .info-table td:first-child {{ font-weight: bold; width: 30%; background-color: #f5f5f5; }}
        .signature {{ margin-top: 40px; text-align: right; }}
    </style></head><body>
    <div class="certificate">
        <div class="title">근무 증명서</div>
        <table class="info-table">
            <tr><td>성명</td><td>{staff_name}</td></tr>
            <tr><td>프로젝트명</td><td>{inquiry_name}</td></tr>
            <tr><td>근무 기간</td><td>{total_days}일</td></tr>
            <tr><td>실제 출석</td><td>{attended_days}일</td></tr>
            <tr><td>출석률</td><td>{attendance_rate:.1f}%</td></tr>
        </table>
        <p>위 직원은 상기 프로젝트에 위 기간 동안 근무하였음을 증명합니다.</p>
        <div class="signature">
            <div>{today}</div>
            <div style="margin-top: 40px;">_______________</div>
            <div>(주) 가디어스</div>
        </div>
    </div></body></html>
    """
    return html


# ==============================================================================
# 5. 날짜 범위 생성
# ==============================================================================
def _generate_dates(start_str, end_str):
    """시작~종료 사이의 날짜 리스트 생성"""
    dates = []
    try:
        start = datetime.strptime(str(start_str).strip()[:10], "%Y-%m-%d")
        end = datetime.strptime(str(end_str).strip()[:10], "%Y-%m-%d")
        cur = start
        while cur <= end:
            dates.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
    except Exception:
        # 파싱 실패 시 오늘 기준 3일
        today = datetime.now()
        for i in range(3):
            dates.append((today + timedelta(days=i)).strftime("%Y-%m-%d"))
    return dates


# ==============================================================================
# 6. 메인 UI
# ==============================================================================
def show(data):
    apply_styles()
    db.ensure_attendance_sheet()

    st.title("📋 출석부 관리")

    df_inq = data.get('inq', pd.DataFrame())
    if df_inq.empty:
        st.warning("프로젝트(문의) 정보가 없습니다.")
        return

    tab_list, tab_input, tab_print, tab_cert = st.tabs([
        "📊 출석 현황", "✏️ 출석 기록", "🖨️ 인쇄용 출석부", "📄 증명서"
    ])

    # ------------------------------------------------------------------
    # 프로젝트 선택 (공통)
    # ------------------------------------------------------------------
    sort_col = _safe_col(df_inq, ['작성일', '문의날짜', '날짜']) or df_inq.columns[0]
    projects = df_inq.sort_values(sort_col, ascending=False) if sort_col in df_inq.columns else df_inq.copy()

    # ========================================================================
    # 탭1: 출석 현황
    # ========================================================================
    with tab_list:
        st.subheader("📊 프로젝트별 출석 현황")

        sel_idx1 = st.selectbox(
            "프로젝트 선택", projects.index, key="att_list_proj",
            format_func=lambda x: f"{projects.loc[x, '업체명']} ({projects.loc[x, '행사명']})"
        )
        inquiry_id = str(projects.loc[sel_idx1, '문의ID'])
        event_name = str(projects.loc[sel_idx1, '행사명'])

        assignments = get_active_assignments(inquiry_id)

        if assignments.empty:
            st.info("이 프로젝트에 배정된 인원이 없습니다.")
        else:
            # 요약
            total_staff = len(assignments)
            name_col = _safe_col(assignments, ['인력명', '이름'])
            role_col = _safe_col(assignments, ['직무', '역할'])
            days_col = _safe_col(assignments, ['근무일수', '일수'])
            status_col = _safe_col(assignments, ['지급상태', '상태'])

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("👥 배정 인원", total_staff)
            with m2:
                # 출석 기록 수
                att_data = get_attendance_data(inquiry_id=inquiry_id)
                att_count = len(att_data[att_data.get('출석상태', pd.Series(dtype=str)).astype(str).str.contains('출석', na=False)]) if not att_data.empty and '출석상태' in att_data.columns else 0
                st.metric("✅ 출석 기록", f"{att_count}건")
            with m3:
                absent_count = len(att_data[att_data.get('출석상태', pd.Series(dtype=str)).astype(str).str.contains('결근', na=False)]) if not att_data.empty and '출석상태' in att_data.columns else 0
                st.metric("❌ 결근", f"{absent_count}건")

            st.divider()

            # 배정 인원 카드
            st.subheader("배정 인원 목록")
            for _, row in assignments.iterrows():
                name = row.get(name_col, '(이름없음)') if name_col else '(이름없음)'
                role = row.get(role_col, '') if role_col else ''
                days = row.get(days_col, '-') if days_col else '-'
                status = row.get(status_col, '배정중') if status_col else '배정중'
                contact = row.get('연락처', '')
                assign_type = row.get('구분', '')

                with st.expander(f"👤 {name} ({role}) — {assign_type} | {days}일"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**배정ID**: {row.get('배정ID', '')}")
                        st.write(f"**직무**: {role}")
                        st.write(f"**근무일수**: {days}일")
                    with c2:
                        st.write(f"**구분**: {assign_type}")
                        st.write(f"**연락처**: {contact}")
                        st.write(f"**지급상태**: {status}")

                    # 이 인력의 출석 기록
                    if not att_data.empty:
                        person_att = att_data[att_data.get('인력명', pd.Series(dtype=str)).astype(str).str.strip() == str(name).strip()] if '인력명' in att_data.columns else pd.DataFrame()
                        if not person_att.empty:
                            display_cols = [c for c in ['출석날짜', '출석상태', '출근시간', '퇴근시간', '비고'] if c in person_att.columns]
                            st.dataframe(person_att[display_cols], hide_index=True, use_container_width=True)

    # ========================================================================
    # 탭2: 출석 기록 입력 (체크박스 매트릭스)
    # ========================================================================
    with tab_input:
        st.subheader("✏️ 출석 기록 입력")

        sel_idx2 = st.selectbox(
            "프로젝트", projects.index, key="att_input_proj",
            format_func=lambda x: f"{projects.loc[x, '업체명']} ({projects.loc[x, '행사명']})"
        )
        sel_inq_id = str(projects.loc[sel_idx2, '문의ID'])

        assignments_sel = get_active_assignments(sel_inq_id)

        if assignments_sel.empty:
            st.warning("배정된 인원이 없습니다.")
        else:
            name_col2 = _safe_col(assignments_sel, ['인력명', '이름'])
            role_col2 = _safe_col(assignments_sel, ['직무', '역할'])

            if name_col2:
                # 인원 목록 추출
                staff_df = assignments_sel[[name_col2, '배정ID']].drop_duplicates() if '배정ID' in assignments_sel.columns else assignments_sel[[name_col2]].drop_duplicates()
                if role_col2 and role_col2 in assignments_sel.columns:
                    staff_df = assignments_sel[[name_col2, role_col2, '배정ID']].drop_duplicates() if '배정ID' in assignments_sel.columns else assignments_sel[[name_col2, role_col2]].drop_duplicates()

                staff_names = [str(r[name_col2]) for _, r in staff_df.iterrows()]
                staff_ids = [str(r.get('배정ID', '')) for _, r in staff_df.iterrows()]

                # 행사 기간에서 날짜 범위 생성
                sel_proj = projects.loc[sel_idx2]
                _s_date = _parse_event_date(sel_proj.get('행사시작일', ''))
                _e_date = _parse_event_date(sel_proj.get('행사종료일', ''))

                if _s_date and _e_date:
                    dates = _generate_dates(_s_date.strftime("%Y-%m-%d"), _e_date.strftime("%Y-%m-%d"))
                    st.caption(f"📅 행사기간: {_s_date} ~ {_e_date} ({len(dates)}일)")
                elif _s_date:
                    dates = [_s_date.strftime("%Y-%m-%d")]
                    st.caption(f"📅 행사일: {_s_date}")
                else:
                    dates = [datetime.now().date().strftime("%Y-%m-%d")]
                    st.caption("📅 행사일 미설정 — 오늘 기준")

                # 기존 출석 데이터 로드 (한번만)
                existing_att = get_attendance_data(inquiry_id=sel_inq_id)

                def _is_attended(name, date_str, existing_df):
                    """기존 출석 기록에서 해당 인원+날짜의 출석 여부 확인"""
                    if existing_df.empty:
                        return False
                    name_c = _safe_col(existing_df, ['인력명'])
                    date_c = _safe_col(existing_df, ['출석날짜'])
                    status_c = _safe_col(existing_df, ['출석상태'])
                    if not (name_c and date_c and status_c):
                        return False
                    matched = existing_df[
                        (existing_df[name_c].astype(str).str.strip() == str(name).strip()) &
                        (existing_df[date_c].astype(str).str.strip() == str(date_str).strip())
                    ]
                    if not matched.empty:
                        return '출석' in str(matched.iloc[0][status_c])
                    return False

                st.markdown(f"**배정 인원: {len(staff_names)}명 | 행사 일수: {len(dates)}일**")
                st.markdown("아래 체크박스로 출석을 기록하세요. ✅ = 출석")
                st.divider()

                # 체크박스 매트릭스 (날짜 × 인원)
                with st.form("attendance_matrix_form", clear_on_submit=False):
                    # 헤더 행 — 날짜 표시
                    if len(dates) <= 7:
                        date_cols = st.columns([1.5] + [1] * len(dates))
                        date_cols[0].markdown("**이름**")
                        for di, d in enumerate(dates):
                            try:
                                dt = datetime.strptime(d, "%Y-%m-%d")
                                day_name = ["월","화","수","목","금","토","일"][dt.weekday()]
                                date_cols[di + 1].markdown(f"**{dt.month}/{dt.day}**({day_name})")
                            except Exception:
                                date_cols[di + 1].markdown(f"**{d}**")

                        # 각 인원별 체크박스 행
                        attendance_checks = {}
                        for si, sname in enumerate(staff_names):
                            row_cols = st.columns([1.5] + [1] * len(dates))
                            role_str = f" ({staff_df.iloc[si][role_col2]})" if role_col2 and role_col2 in staff_df.columns else ""
                            row_cols[0].markdown(f"👤 **{sname}**{role_str}")
                            for di, d in enumerate(dates):
                                default_val = _is_attended(sname, d, existing_att)
                                key = f"att_chk_{si}_{di}"
                                attendance_checks[(si, di)] = row_cols[di + 1].checkbox(
                                    "출석", value=default_val, key=key, label_visibility="collapsed"
                                )
                    else:
                        # 날짜가 7일 초과 시 — 스크롤 가능한 테이블 형식
                        st.info(f"📎 행사기간이 {len(dates)}일입니다. 날짜별 탭으로 표시합니다.")
                        attendance_checks = {}
                        date_tabs = st.tabs([f"{datetime.strptime(d, '%Y-%m-%d').month}/{datetime.strptime(d, '%Y-%m-%d').day}" if len(d) >= 10 else d for d in dates])
                        for di, (d, dtab) in enumerate(zip(dates, date_tabs)):
                            with dtab:
                                try:
                                    dt = datetime.strptime(d, "%Y-%m-%d")
                                    day_name = ["월","화","수","목","금","토","일"][dt.weekday()]
                                    st.markdown(f"**{d} ({day_name})**")
                                except Exception:
                                    st.markdown(f"**{d}**")
                                for si, sname in enumerate(staff_names):
                                    default_val = _is_attended(sname, d, existing_att)
                                    key = f"att_chk_{si}_{di}"
                                    role_str = f" ({staff_df.iloc[si][role_col2]})" if role_col2 and role_col2 in staff_df.columns else ""
                                    attendance_checks[(si, di)] = st.checkbox(
                                        f"👤 {sname}{role_str}", value=default_val, key=key
                                    )

                    # 전체 출석 / 전체 결근 토글
                    c_action1, c_action2, _ = st.columns([1, 1, 2])
                    
                    submitted = st.form_submit_button("💾 출석 일괄 저장", type="primary", use_container_width=True)

                if submitted:
                    success_count = 0
                    total_count = 0
                    with st.spinner("출석 기록 저장 중..."):
                        for (si, di), checked in attendance_checks.items():
                            sname = staff_names[si]
                            sid = staff_ids[si] if si < len(staff_ids) else ''
                            d = dates[di]
                            status = "출석" if checked else "결근"
                            total_count += 1
                            result = save_attendance_record(
                                sid, sname, sel_inq_id,
                                d, status, '', '', ''
                            )
                            if result:
                                success_count += 1
                    st.success(f"✅ {success_count}/{total_count}건 출석 기록 저장 완료!")
                    st.cache_data.clear()
            else:
                st.warning("인력명 컬럼을 찾을 수 없습니다.")

    # ========================================================================
    # 탭3: 인쇄용 출석부
    # ========================================================================
    with tab_print:
        st.subheader("🖨️ 인쇄용 출석부")
        st.caption("실제 현장에서 사용할 수 있는 출석부를 생성합니다. HTML로 저장하거나 브라우저에서 바로 인쇄할 수 있습니다.")

        sel_idx3 = st.selectbox(
            "프로젝트 선택", projects.index, key="att_print_proj",
            format_func=lambda x: f"{projects.loc[x, '업체명']} ({projects.loc[x, '행사명']})"
        )
        sel_inq_id3 = str(projects.loc[sel_idx3, '문의ID'])
        sel_event = str(projects.loc[sel_idx3, '행사명'])
        sel_company = str(projects.loc[sel_idx3, '업체명'])
        sel_location = str(projects.loc[sel_idx3].get('장소', ''))

        # 날짜 범위
        start_date_col = _safe_col(projects, ['행사시작일', '시작일'])
        end_date_col = _safe_col(projects, ['행사종료일', '종료일'])

        start_val = str(projects.loc[sel_idx3].get(start_date_col, '')) if start_date_col else ''
        end_val = str(projects.loc[sel_idx3].get(end_date_col, '')) if end_date_col else ''

        c_d1, c_d2 = st.columns(2)
        with c_d1:
            try:
                s_default = datetime.strptime(start_val[:10], "%Y-%m-%d").date()
            except Exception:
                s_default = datetime.now().date()
            print_start = st.date_input("시작일", value=s_default, key="print_start")
        with c_d2:
            try:
                e_default = datetime.strptime(end_val[:10], "%Y-%m-%d").date()
            except Exception:
                e_default = (datetime.now() + timedelta(days=3)).date()
            print_end = st.date_input("종료일", value=e_default, key="print_end")

        dates = _generate_dates(print_start.strftime("%Y-%m-%d"), print_end.strftime("%Y-%m-%d"))
        date_range_str = f"{print_start.strftime('%Y-%m-%d')} ~ {print_end.strftime('%Y-%m-%d')}"

        assignments3 = get_active_assignments(sel_inq_id3)

        if assignments3.empty:
            st.warning("배정된 인원이 없습니다. 먼저 인원배정을 완료하세요.")
        else:
            name_col3 = _safe_col(assignments3, ['인력명', '이름'])
            role_col3 = _safe_col(assignments3, ['직무', '역할'])

            staff_list = []
            for _, r in assignments3.iterrows():
                staff_list.append({
                    '인력명': r.get(name_col3, '') if name_col3 else '',
                    '직무': r.get(role_col3, '') if role_col3 else '',
                    '연락처': r.get('연락처', ''),
                    '배정ID': r.get('배정ID', ''),
                })

            st.markdown(f"**인원**: {len(staff_list)}명 &nbsp;|&nbsp; **기간**: {date_range_str} ({len(dates)}일)")

            # 출석 기록 로드
            att_records = get_attendance_data(inquiry_id=sel_inq_id3)

            if st.button("📄 출석부 생성", type="primary", use_container_width=True):
                html = generate_printable_attendance_html(
                    sel_event, sel_company, sel_location, date_range_str,
                    staff_list, dates, att_records
                )
                st.session_state['_print_html'] = html

            if '_print_html' in st.session_state:
                html = st.session_state['_print_html']

                # 미리보기
                st.components.v1.html(html, height=600, scrolling=True)

                # 다운로드 버튼
                c_dl1, c_dl2 = st.columns(2)
                with c_dl1:
                    st.download_button(
                        "📥 HTML 파일로 저장",
                        data=html,
                        file_name=f"출석부_{sel_event}_{print_start.strftime('%Y%m%d')}.html",
                        mime="text/html",
                        use_container_width=True,
                    )
                with c_dl2:
                    st.info("💡 미리보기 안의 **'🖨️ 인쇄하기'** 버튼을 클릭하거나, HTML 파일을 브라우저로 열어 인쇄하세요.")

    # ========================================================================
    # 탭4: 증명서
    # ========================================================================
    with tab_cert:
        st.subheader("📄 출석 증명서 생성")

        sel_idx4 = st.selectbox(
            "프로젝트 선택", projects.index, key="att_cert_proj",
            format_func=lambda x: f"{projects.loc[x, '업체명']} ({projects.loc[x, '행사명']})"
        )
        sel_inq_id4 = str(projects.loc[sel_idx4, '문의ID'])
        project_name = str(projects.loc[sel_idx4, '행사명'])

        assignments_cert = get_active_assignments(sel_inq_id4)

        if assignments_cert.empty:
            st.warning("배정된 인원이 없습니다.")
        else:
            name_col4 = _safe_col(assignments_cert, ['인력명', '이름'])
            role_col4 = _safe_col(assignments_cert, ['직무', '역할'])
            days_col4 = _safe_col(assignments_cert, ['근무일수', '일수'])

            if name_col4:
                if role_col4:
                    cert_labels = [f"{r[name_col4]} ({r[role_col4]})" for _, r in assignments_cert.iterrows()]
                else:
                    cert_labels = [f"{r[name_col4]}" for _, r in assignments_cert.iterrows()]

                sel_cert_idx = st.selectbox("인원 선택", range(len(assignments_cert)), format_func=lambda x: cert_labels[x], key="cert_staff")
                sel_cert_row = assignments_cert.iloc[sel_cert_idx]

                staff_name = sel_cert_row.get(name_col4, '')
                try:
                    total_days = int(sel_cert_row.get(days_col4, 1)) if days_col4 else 1
                except Exception:
                    total_days = 1
                if total_days <= 0:
                    total_days = 1

                attended_days = st.number_input("출석 일수", min_value=0, max_value=total_days, value=total_days)

                if st.button("📄 증명서 생성", type="primary"):
                    cert_html = generate_certificate_html(staff_name, project_name, total_days, attended_days)
                    st.components.v1.html(cert_html, height=700, scrolling=True)

                    st.download_button(
                        "📥 증명서 다운로드 (HTML)",
                        data=cert_html,
                        file_name=f"{staff_name}_출석증명_{datetime.now().strftime('%Y%m%d')}.html",
                        mime="text/html"
                    )
            else:
                st.warning("인력명 컬럼을 찾을 수 없습니다.")
