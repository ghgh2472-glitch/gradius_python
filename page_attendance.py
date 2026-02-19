# page_attendance.py  v3.0
"""
출석부 관리 — 확정 인력 기반 통합 출석부 시스템
- 📅 스케줄표: 확정 인력 + 근무일자 자동 상속, 이미지 다운로드
- ✏️ 출석 기록: 스마트 필터링 + 배치 저장 + 변동없음 원클릭
- 🖨️ 인쇄용 출석부: HTML 인쇄
- 📄 증명서: 근무 증명서
"""
import streamlit as st
import pandas as pd
import data_loader as db
import status_config as sc
from datetime import datetime, timedelta, date as dt_date, time as dt_time
import io


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _parse_event_date(val):
    if not val or str(val).strip() in ('', 'nan', 'None'):
        return None
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_date_safe(s):
    if not s or str(s).strip() in ('', 'nan', 'None'):
        return None
    txt = str(s).strip()[:10]
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d'):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


def _parse_work_time(wt_str):
    fallback = (dt_time(9, 0), dt_time(18, 0))
    if not wt_str or str(wt_str).strip() in ('', 'nan', 'None'):
        return fallback
    try:
        parts = str(wt_str).replace('–', '~').replace('-', '~').replace('−', '~').split('~')
        if len(parts) >= 2:
            st_p = parts[0].strip().replace('시', ':').replace('분', '')
            et_p = parts[1].strip().replace('시', ':').replace('분', '')
            sh, sm = int(st_p.split(':')[0]), int(st_p.split(':')[1]) if ':' in st_p else 0
            eh, em = int(et_p.split(':')[0]), int(et_p.split(':')[1]) if ':' in et_p else 0
            return dt_time(sh, sm), dt_time(eh, em)
    except Exception:
        pass
    return fallback


def _safe_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return names[0] if names else ''


def _generate_dates(start_str, end_str):
    dates = []
    try:
        start = datetime.strptime(str(start_str).strip()[:10], "%Y-%m-%d")
        end = datetime.strptime(str(end_str).strip()[:10], "%Y-%m-%d")
        cur = start
        while cur <= end:
            dates.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
    except Exception:
        today = datetime.now()
        for i in range(3):
            dates.append((today + timedelta(days=i)).strftime("%Y-%m-%d"))
    return dates


# ─── 스타일 ────────────────────────────────────────────────────────────────────

def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 1200px; padding-top: 1rem; }
        .section-title {
            font-size: 18px; font-weight: 700; color: #1e293b;
            border-bottom: 2px solid #0ea5e9; padding-bottom: 6px;
            margin: 20px 0 14px 0;
        }
        .sched-work { background: #dcfce7; color: #166534; padding: 2px 8px;
                       border-radius: 4px; font-size: 12px; font-weight: 600; text-align: center; }
        .sched-off  { color: #d1d5db; text-align: center; }
    </style>
    """, unsafe_allow_html=True)


# ─── 프로젝트 선택 (공통) ──────────────────────────────────────────────────────

def _select_project(df_inq, allowed_statuses, key_prefix):
    status_col = _safe_col(df_inq, ['상태', '진행상태'])
    if status_col:
        filtered = df_inq[df_inq[status_col].astype(str).str.strip().isin(allowed_statuses)]
    else:
        filtered = df_inq.copy()
    if filtered.empty:
        st.info("📌 배정완료/진행중/완료 상태의 프로젝트가 필요합니다.")
        return None, None
    sort_col = _safe_col(filtered, ['작성일', '문의날짜', '날짜'])
    if sort_col and sort_col in filtered.columns:
        filtered = filtered.sort_values(sort_col, ascending=False)
    options = []
    for idx, row in filtered.iterrows():
        company = str(row.get('업체명', '')).strip()
        event = str(row.get('행사명', '')).strip()
        status = str(row.get(status_col, '')).strip() if status_col else ''
        options.append((idx, f"{company} — {event} [{status}]"))
    if not options:
        return None, None
    sel = st.selectbox(
        "프로젝트 선택", [o[0] for o in options],
        format_func=lambda x: next(o[1] for o in options if o[0] == x),
        key=f"proj_{key_prefix}")
    row = filtered.loc[sel]
    inquiry_id = str(row.get('문의ID', ''))
    return inquiry_id, row


# ─── 날짜/근무일자 파싱 ────────────────────────────────────────────────────────

def _build_event_dates(sel):
    raw_start = str(sel.get('행사시작일', '')).strip()
    raw_end = str(sel.get('행사종료일', '')).strip()
    if '/' in raw_start:
        parts = [p.strip() for p in raw_start.split('/') if p.strip()]
        start_date = _parse_date_safe(parts[0]) if parts else None
    else:
        start_date = _parse_event_date(raw_start)
    if '/' in raw_end:
        parts = [p.strip() for p in raw_end.split('/') if p.strip()]
        end_date = _parse_date_safe(parts[-1]) if parts else None
    else:
        end_date = _parse_event_date(raw_end)
    event_dates = []
    if start_date and end_date and end_date >= start_date:
        event_dates = [start_date + timedelta(days=d) for d in range((end_date - start_date).days + 1)]
    elif start_date:
        event_dates = [start_date]
    return event_dates, start_date, end_date


def _build_staff_work_dates(confirmed_df, event_dates):
    """확정 인력의 근무일자 파싱.
    - 근무일자 컬럼에 ISO 날짜가 있으면 그대로 사용
    - 비어있으면 근무일수를 참조하여 앞쪽 N일만 할당
    - 근무일수도 없으면 전 일정
    """
    staff_work_dates = {}
    total_event_days = len(event_dates)
    for _, row in confirmed_df.iterrows():
        aid = str(row.get('배정ID', ''))
        dates_str = str(row.get('근무일자', '')).strip()
        if dates_str and dates_str not in ('', 'nan', 'None'):
            parsed = set()
            for d_iso in dates_str.split(','):
                d = _parse_date_safe(d_iso.strip())
                if d:
                    parsed.add(d)
            staff_work_dates[aid] = parsed
        else:
            # 근무일자 비어있음 → 근무일수 기반 폴백
            try:
                work_days = int(row.get('근무일수', 0) or 0)
            except (ValueError, TypeError):
                work_days = 0
            if work_days > 0 and work_days < total_event_days:
                # 앞쪽 N일만 할당 (정확한 날짜는 인력배정에서 재설정 필요)
                staff_work_dates[aid] = set(event_dates[:work_days])
            else:
                staff_work_dates[aid] = set(event_dates)
    return staff_work_dates


# ──────────────────────────────────────────────────────────────────────────────
#  스케줄표 이미지 (Pillow — 고급 디자인)
# ──────────────────────────────────────────────────────────────────────────────

def _generate_schedule_image(event_name, date_list, staff_schedule,
                              work_time_str='', company=''):
    """스케줄표를 고품질 PNG 이미지로 생성

    staff_schedule: list[dict{name, role, dates:[bool,...]}]
    Returns: PIL Image
    """
    from PIL import Image, ImageDraw, ImageFont
    import glob

    # ── 폰트 ──
    bold_paths = glob.glob('/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf')
    regular_paths = glob.glob('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
    bold_path = bold_paths[0] if bold_paths else (regular_paths[0] if regular_paths else None)
    regular_path = regular_paths[0] if regular_paths else bold_path

    if bold_path:
        font_title    = ImageFont.truetype(bold_path, 26)
        font_subtitle = ImageFont.truetype(regular_path or bold_path, 15)
        font_header   = ImageFont.truetype(bold_path, 14)
        font_cell     = ImageFont.truetype(regular_path or bold_path, 13)
        font_small    = ImageFont.truetype(regular_path or bold_path, 11)
        font_legend   = ImageFont.truetype(regular_path or bold_path, 11)
    else:
        font_title = font_subtitle = font_header = font_cell = font_small = font_legend = ImageFont.load_default()

    # ── 레이아웃 ──
    row_h       = 40
    col_w       = 68
    name_w      = 130
    role_w      = 80
    header_h    = 56
    title_area  = 80
    padding     = 28
    footer_h    = 50
    legend_h    = 36

    num_days  = len(date_list)
    num_staff = len(staff_schedule)
    table_w   = name_w + role_w + col_w * num_days

    img_w = padding * 2 + table_w
    img_h = padding * 2 + title_area + header_h + row_h * num_staff + row_h + legend_h + footer_h

    img  = Image.new('RGB', (img_w, img_h), '#F8FAFC')
    draw = ImageDraw.Draw(img)

    # ── 타이틀 영역 (그라데이션) ──
    for y in range(title_area):
        ratio = y / title_area
        r = int(15 + (30 - 15) * ratio)
        g = int(23 + (58 - 23) * ratio)
        b = int(42 + (82 - 42) * ratio)
        draw.line([(0, y), (img_w, y)], fill=(r, g, b))

    draw.text((padding, 16), f"📋  {event_name}", fill='#FFFFFF', font=font_title)
    parts = []
    if company:
        parts.append(f"업체: {company}")
    if work_time_str:
        parts.append(f"근무시간: {work_time_str}")
    parts.append(f"인원: {num_staff}명")
    parts.append(f"기간: {num_days}일")
    draw.text((padding, 50), "  |  ".join(parts), fill='#94A3B8', font=font_subtitle)

    # ── 테이블 ──
    tx = padding
    ty = title_area

    # 헤더
    draw.rectangle([tx, ty, tx + table_w, ty + header_h], fill='#0F766E')
    draw.text((tx + 12, ty + 20), "이름", fill='white', font=font_header)
    draw.text((tx + name_w + 10, ty + 20), "직무", fill='white', font=font_header)

    for di, d in enumerate(date_list):
        x = tx + name_w + role_w + col_w * di
        is_weekend = d.weekday() >= 5
        if is_weekend:
            draw.rectangle([x, ty, x + col_w, ty + header_h], fill='#115E59')
        draw.text((x + 14, ty + 14), f"{d.month}/{d.day}", fill='white', font=font_header)
        wd_color = '#FBBF24' if is_weekend else '#A7F3D0'
        draw.text((x + 24, ty + 34), '월화수목금토일'[d.weekday()], fill=wd_color, font=font_small)

    # ── 데이터 행 ──
    daily_counts = [0] * num_days
    for ri, staff in enumerate(staff_schedule):
        y = ty + header_h + row_h * ri
        bg = '#FFFFFF' if ri % 2 == 0 else '#F1F5F9'
        draw.rectangle([tx, y, tx + table_w, y + row_h], fill=bg)
        draw.line([(tx, y + row_h), (tx + table_w, y + row_h)], fill='#E2E8F0')
        draw.text((tx + 12, y + 12), staff['name'], fill='#1E293B', font=font_cell)
        draw.text((tx + name_w + 10, y + 12), staff.get('role', ''), fill='#64748B', font=font_small)

        for di, checked in enumerate(staff['dates']):
            x = tx + name_w + role_w + col_w * di
            is_weekend = date_list[di].weekday() >= 5
            if is_weekend:
                overlay = '#FEF9C3' if ri % 2 == 0 else '#FEF3C7'
                draw.rectangle([x, y, x + col_w, y + row_h], fill=overlay)
                draw.line([(x, y + row_h), (x + col_w, y + row_h)], fill='#E2E8F0')
            if checked:
                bx, by = x + 16, y + 8
                draw.rounded_rectangle([bx, by, bx + 36, by + 24], radius=6, fill='#10B981')
                draw.text((bx + 9, by + 4), "✓", fill='white', font=font_header)
                daily_counts[di] += 1
            else:
                draw.text((x + 28, y + 12), "—", fill='#CBD5E1', font=font_cell)

    # ── 합계 행 ──
    sy = ty + header_h + row_h * num_staff
    draw.rectangle([tx, sy, tx + table_w, sy + row_h], fill='#ECFDF5')
    draw.line([(tx, sy), (tx + table_w, sy)], fill='#0F766E', width=2)
    draw.text((tx + 12, sy + 12), "일자별 합계", fill='#0F766E', font=font_header)
    for di, cnt in enumerate(daily_counts):
        x = tx + name_w + role_w + col_w * di
        draw.text((x + 16, sy + 12), f"{cnt}명", fill='#0F766E', font=font_header)

    # ── 범례 ──
    ly = sy + row_h + 8
    draw.text((tx + 4, ly + 8), "범례:", fill='#64748B', font=font_legend)
    draw.rounded_rectangle([tx + 50, ly + 4, tx + 72, ly + 24], radius=4, fill='#10B981')
    draw.text((tx + 56, ly + 6), "✓", fill='white', font=font_small)
    draw.text((tx + 78, ly + 8), "근무", fill='#64748B', font=font_legend)
    draw.text((tx + 120, ly + 8), "—  비근무", fill='#94A3B8', font=font_legend)
    draw.rectangle([tx + 200, ly + 4, tx + 222, ly + 24], fill='#FEF3C7', outline='#E5E7EB')
    draw.text((tx + 228, ly + 8), "주말/공휴일", fill='#92400E', font=font_legend)

    # 외곽
    draw.rectangle([tx, ty, tx + table_w, sy + row_h], outline='#94A3B8')

    # 푸터
    fy = img_h - footer_h + 10
    draw.text((padding, fy),
              f"(주)가디어스 Gradius ERP | 출력: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
              fill='#94A3B8', font=font_legend)

    return img


# ──────────────────────────────────────────────────────────────────────────────
#  인쇄용 출석부 HTML
# ──────────────────────────────────────────────────────────────────────────────

def generate_printable_attendance_html(event_name, company, location,
                                        date_range, staff_list, dates,
                                        attendance_records):
    today = datetime.now().strftime('%Y-%m-%d')

    date_headers = ""
    for d in dates:
        try:
            dt_ = datetime.strptime(d, "%Y-%m-%d")
            wd = ["월","화","수","목","금","토","일"][dt_.weekday()]
            date_headers += f'<th style="width:60px;">{dt_.month}/{dt_.day}<br/>({wd})</th>'
        except Exception:
            date_headers += f'<th style="width:60px;">{d}</th>'

    rows_html = ""
    for i, staff in enumerate(staff_list, 1):
        name = staff.get('인력명', '')
        role = staff.get('직무', '')
        contact = staff.get('연락처', '')

        cells = ""
        for d in dates:
            status_mark = ""
            if not attendance_records.empty:
                date_col = _safe_col(attendance_records, ['출석날짜'])
                name_c   = _safe_col(attendance_records, ['인력명'])
                stat_c   = _safe_col(attendance_records, ['출석상태'])
                if date_col and name_c and stat_c:
                    matched = attendance_records[
                        (attendance_records[name_c].astype(str).str.strip() == name.strip()) &
                        (attendance_records[date_col].astype(str).str.strip() == d)
                    ]
                    if not matched.empty:
                        s = str(matched.iloc[0][stat_c])
                        if '출근' in s or '출석' in s:
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

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>출석부 - {event_name}</title>
<style>
    @media print {{ body {{ margin: 0; padding: 10mm; }} .no-print {{ display: none !important; }} }}
    body {{ font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; color: #222; margin: 20px; }}
    .header-section {{ text-align: center; margin-bottom: 20px; }}
    .header-section h1 {{ font-size: 28px; margin: 0; letter-spacing: 10px; }}
    .info-box {{ display: flex; justify-content: space-between; border: 1px solid #333; margin-bottom: 15px; }}
    .info-box .item {{ flex: 1; padding: 8px 12px; border-right: 1px solid #333; font-size: 13px; }}
    .info-box .item:last-child {{ border-right: none; }}
    .info-box .label {{ font-weight: bold; color: #555; font-size: 11px; }}
    .info-box .value {{ font-size: 14px; margin-top: 2px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border: 1px solid #333; padding: 6px 4px; }}
    th {{ background-color: #f0f0f0; font-weight: bold; text-align: center; font-size: 11px; }}
    .legend {{ margin-top: 15px; font-size: 11px; color: #666; }}
    .footer-sign {{ display: flex; justify-content: flex-end; margin-top: 30px; gap: 40px; }}
    .sign-box {{ text-align: center; width: 150px; }}
    .sign-box .line {{ border-bottom: 1px solid #333; height: 40px; margin-bottom: 5px; }}
    .sign-box .label {{ font-size: 12px; color: #555; }}
    .print-btn {{ position: fixed; top: 10px; right: 10px; background: #3B82F6; color: white;
        border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer;
        font-size: 14px; font-weight: bold; z-index: 999; }}
    .print-btn:hover {{ background: #2563EB; }}
</style></head><body>
<button class="print-btn no-print" onclick="window.print()">🖨️ 인쇄하기</button>
<div class="header-section">
    <h1>출 석 부</h1>
    <p style="color:#666; font-size:13px; margin-top:5px;">(주) 가디어스 인력파견</p>
</div>
<div class="info-box">
    <div class="item"><div class="label">현장명 / 행사명</div><div class="value">{event_name}</div></div>
    <div class="item"><div class="label">업체명</div><div class="value">{company}</div></div>
    <div class="item"><div class="label">현장주소</div><div class="value">{location}</div></div>
    <div class="item"><div class="label">파견기간</div><div class="value">{date_range}</div></div>
</div>
<table><thead><tr>
    <th style="width:30px;">No</th><th style="width:70px;">성명</th>
    <th style="width:70px;">직무</th><th style="width:100px;">연락처</th>
    {date_headers}<th style="width:70px;">서명</th>
</tr></thead><tbody>{rows_html}</tbody></table>
<div class="legend">✅ 출석 &nbsp; ❌ 결근 &nbsp; ⏰ 지각 &nbsp; 🔻 조퇴 &nbsp; (빈칸: 미기록)</div>
<div class="footer-sign">
    <div class="sign-box"><div class="line"></div><div class="label">현장 책임자</div></div>
    <div class="sign-box"><div class="line"></div><div class="label">업체 담당자</div></div>
</div>
<p style="text-align:center; color:#999; font-size:10px; margin-top:30px;">
    출력일: {today} | (주)가디어스 Gradius ERP System</p>
</body></html>"""
    return html


# ──────────────────────────────────────────────────────────────────────────────
#  증명서 HTML
# ──────────────────────────────────────────────────────────────────────────────

def generate_certificate_html(staff_name, inquiry_name, total_days, attended_days):
    rate = (attended_days / total_days * 100) if total_days > 0 else 0
    today_str = datetime.now().strftime('%Y년 %m월 %d일')
    return f"""<html><head><meta charset="UTF-8">
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
        <tr><td>출석률</td><td>{rate:.1f}%</td></tr>
    </table>
    <p>위 직원은 상기 프로젝트에 위 기간 동안 근무하였음을 증명합니다.</p>
    <div class="signature">
        <div>{today_str}</div>
        <div style="margin-top: 40px;">_______________</div>
        <div>(주) 가디어스</div>
    </div>
</div></body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  탭1: 📅 스케줄표
# ══════════════════════════════════════════════════════════════════════════════

def _tab_schedule(data):
    df_inq = data.get('inq', pd.DataFrame())
    sel_id, sel = _select_project(df_inq, ['배정완료', '진행중', '완료'], "sched")
    if sel_id is None:
        return

    confirmed_df = db.get_confirmed_assignments(sel_id)
    if confirmed_df.empty:
        st.warning("⚠️ 확정된 인력이 없습니다. 인원배정관리 → ③ 확정 단계를 먼저 완료하세요.")
        all_df = db.get_assignments_by_inquiry(sel_id)
        if not all_df.empty:
            st.caption(f"📋 현재 배정 인원: {len(all_df)}명 (확정 전환 필요)")
        return

    event_name = str(sel.get('행사명', ''))
    company    = str(sel.get('업체명', ''))
    name_col   = _col(confirmed_df, '인력명', '이름')
    role_col   = _col(confirmed_df, '직무', '역할')

    event_dates, start_date, end_date = _build_event_dates(sel)
    if not event_dates:
        st.warning("행사 날짜를 파싱할 수 없습니다. 행사시작일/종료일을 확인하세요.")
        return

    est_items = db.load_estimate_items(sel_id)
    work_time_str = ''
    if not est_items.empty:
        work_time_str = str(est_items.iloc[0].get('근무시간', ''))

    staff_work_dates = _build_staff_work_dates(confirmed_df, event_dates)

    st.markdown(f"**{event_name}** — 확정 인력 **{len(confirmed_df)}명** · 기간 **{len(event_dates)}일**")
    st.caption("💡 인력배정 단계에서 선택한 근무일자가 자동으로 반영됩니다.")

    # ── 페이징 ──
    dates_pp = 7
    total_pages = max(1, (len(event_dates) + dates_pp - 1) // dates_pp)
    sp = 0
    if total_pages > 1:
        sp = st.number_input("주차", 1, total_pages, 1, key="sched_pg") - 1
    pg_dates = event_dates[sp * dates_pp: (sp + 1) * dates_pp]

    # ── 테이블 헤더 ──
    hcols = st.columns([2.5] + [1] * len(pg_dates) + [0.8])
    hcols[0].markdown("**인력 (직무)**")
    for di, dd in enumerate(pg_dates):
        wd = '월화수목금토일'[dd.weekday()]
        marker = "🔴 " if dd.weekday() >= 5 else ""
        hcols[di + 1].markdown(f"**{marker}{dd.strftime('%m/%d')}**\n{wd}")
    hcols[-1].markdown("**일수**")

    # ── 인력별 행 ──
    daily_totals = [0] * len(pg_dates)
    img_data = []

    for _, row in confirmed_df.iterrows():
        sname = str(row.get(name_col, ''))
        srole = str(row.get(role_col, ''))
        aid   = str(row.get('배정ID', ''))
        work_set = staff_work_dates.get(aid, set())
        total_days_worked = len(work_set)
        category = str(row.get('구분', '외부'))
        badge = "🏢" if category == '본사' else "👤"

        rcols = st.columns([2.5] + [1] * len(pg_dates) + [0.8])
        rcols[0].markdown(f"{badge} **{sname}** ({srole})")
        for di, dd in enumerate(pg_dates):
            with rcols[di + 1]:
                if dd in work_set:
                    st.markdown('<div class="sched-work">✅</div>', unsafe_allow_html=True)
                    daily_totals[di] += 1
                else:
                    st.markdown('<div class="sched-off">—</div>', unsafe_allow_html=True)
        rcols[-1].markdown(f"**{total_days_worked}일**")

        img_data.append({
            'name': sname, 'role': srole,
            'dates': [dd in work_set for dd in event_dates]
        })

    # ── 합계 ──
    tcols = st.columns([2.5] + [1] * len(pg_dates) + [0.8])
    tcols[0].markdown("**📊 일자별 합계**")
    for di in range(len(pg_dates)):
        tcols[di + 1].markdown(f"**{daily_totals[di]}명**")
    tcols[-1].markdown(f"**{len(confirmed_df)}**")

    # ── 이미지 생성 & 다운로드 ──
    st.divider()
    if st.button("🖼️ 스케줄표 이미지 만들기 (PNG 다운로드)",
                  key="gen_sched_img", use_container_width=True):
        with st.spinner("스케줄표 이미지 생성 중..."):
            pil_img = _generate_schedule_image(
                event_name, event_dates, img_data, work_time_str, company)
            buf = io.BytesIO()
            pil_img.save(buf, format='PNG', dpi=(150, 150))
            buf.seek(0)
        st.image(pil_img, caption=f"{event_name} 스케줄표", use_container_width=True)
        st.download_button(
            "📥 PNG 다운로드", data=buf.getvalue(),
            file_name=f"스케줄표_{event_name}_{datetime.now().strftime('%Y%m%d')}.png",
            mime="image/png", use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  탭2: ✏️ 출석 기록
# ══════════════════════════════════════════════════════════════════════════════

def _tab_attendance_input(data):
    df_inq = data.get('inq', pd.DataFrame())
    sel_id, sel = _select_project(df_inq, ['배정완료', '진행중', '완료'], "att_in")
    if sel_id is None:
        return

    confirmed_df = db.get_confirmed_assignments(sel_id)
    if confirmed_df.empty:
        st.warning("⚠️ 확정된 인력이 없습니다. 인원배정관리에서 확정 단계를 먼저 완료하세요.")
        return

    event_name     = str(sel.get('행사명', ''))
    current_status = str(sel.get('상태', sel.get('진행상태', '')))
    name_col = _col(confirmed_df, '인력명', '이름')
    role_col = _col(confirmed_df, '직무', '역할')
    rate_col = _col(confirmed_df, '지급단가', '단가')

    event_dates, start_date, end_date = _build_event_dates(sel)

    est_items = db.load_estimate_items(sel_id)
    work_time_str = ''
    if not est_items.empty:
        work_time_str = str(est_items.iloc[0].get('근무시간', ''))
    default_start, default_end = _parse_work_time(work_time_str)

    staff_work_dates = _build_staff_work_dates(confirmed_df, event_dates)

    st.markdown(f"**{event_name}** — 확정 인력 **{len(confirmed_df)}명**")

    # ── 행사완료 처리 ──
    if current_status == '진행중':
        if st.button("🏁 행사 완료 처리", type="primary", key="att_complete"):
            db.update_status(sel_id, sc.STATUS_FLOW[5])   # 완료
            db.invalidate_data()
            st.balloons()
            st.success("✅ 행사가 완료 처리되었습니다.")
            st.rerun()
    elif current_status == '완료':
        st.success("✅ 행사 완료 — 정산 페이지에서 후속 처리를 진행하세요.")

    st.divider()

    # ── 날짜 선택 ──
    today = datetime.now().date()
    if start_date and end_date:
        default_date = max(start_date, min(today, end_date))
        att_date = st.date_input("출석 날짜", value=default_date,
                                 min_value=start_date, max_value=end_date, key="att_date")
    elif start_date:
        att_date = st.date_input("출석 날짜", value=max(start_date, today), key="att_date")
    else:
        att_date = st.date_input("출석 날짜", value=today, key="att_date")

    # ── 출퇴근 시간 ──
    ct1, ct2 = st.columns(2)
    start_time = ct1.time_input("출근 시간", value=default_start, key="att_ti_s")
    end_time   = ct2.time_input("퇴근 시간", value=default_end,   key="att_ti_e")
    if work_time_str:
        st.caption(f"⏰ 견적 기준 근무시간: {work_time_str}")

    start_dt = datetime.combine(today, start_time)
    end_dt   = datetime.combine(today, end_time)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    worked_hours = (end_dt - start_dt).total_seconds() / 3600
    st.caption(f"근무시간: {worked_hours:.1f}시간")

    # ── 해당 날짜 근무자 필터 ──
    att_date_d = att_date if isinstance(att_date, dt_date) else att_date
    working_today     = []
    not_working_today = []
    for _, row in confirmed_df.iterrows():
        aid = str(row.get('배정ID', ''))
        work_set = staff_work_dates.get(aid, set())
        if att_date_d in work_set:
            working_today.append(row)
        else:
            not_working_today.append(row)

    if not working_today:
        st.info(f"📌 {att_date} 에 근무 예정인 인력이 없습니다.")
        if not_working_today:
            st.caption(f"비근무: {', '.join(str(r.get(name_col, '')) for r in not_working_today)}")
        return

    st.markdown(f"##### 👥 {att_date.strftime('%m/%d')} 출근 인력 ({len(working_today)}명)")
    if not_working_today:
        st.caption(f"비근무: {', '.join(str(r.get(name_col, '')) for r in not_working_today)}")

    # ── 인력별 출석 입력 ──
    att_records = []
    all_normal  = True

    for idx, row in enumerate(working_today):
        name       = str(row.get(name_col, 'N/A'))
        assign_id  = str(row.get('배정ID', ''))
        category   = str(row.get('구분', '외부'))
        role       = str(row.get(role_col, ''))
        hourly_rate = int(row.get(rate_col, 0) or 0)
        daily_wage  = int(worked_hours * (hourly_rate / 8)) if hourly_rate > 0 else 0
        badge = "🏢" if category == '본사' else "👤"

        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        with c1:
            st.markdown(f"{badge} **{name}** ({role}) — ₩{daily_wage:,}")
        with c2:
            status = st.selectbox("상태", ["출근", "지각", "조퇴", "결근"],
                                  index=0, key=f"att_s_{idx}")
        with c3:
            actual_start = st.time_input("출근", value=default_start,
                                         key=f"att_i_{idx}", label_visibility="collapsed")
        with c4:
            reason = st.text_input("사유", key=f"att_r_{idx}",
                                   label_visibility="collapsed", placeholder="사유(선택)")

        if status != "출근" or reason:
            all_normal = False

        att_records.append({
            '배정ID': assign_id, '문의ID': sel_id, '인력명': name,
            '출석날짜': att_date.strftime('%Y-%m-%d'),
            '출근시간': actual_start.strftime('%H:%M'),
            '퇴근시간': end_time.strftime('%H:%M'),
            '근무시간': worked_hours, '일급여': daily_wage,
            '출석상태': status, '사유': reason,
            '비고': f'구분:{category} 직무:{role}',
            '기록일시': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })

    # ── 저장 ──
    st.markdown("---")
    bc1, bc2 = st.columns(2)
    with bc1:
        if all_normal and st.button("✅ 변동 없음 — 전원 출근 저장", type="primary",
                                     use_container_width=True, key="save_att_q"):
            _do_save(sel_id, current_status, att_records)
    with bc2:
        if st.button("💾 출석 일괄 저장", use_container_width=True, key="save_att_b"):
            _do_save(sel_id, current_status, att_records)


def _do_save(sel_id, current_status, att_records):
    with st.spinner("출석 기록 저장 중..."):
        ok, fail = db.batch_save_attendance(att_records)
    if ok > 0:
        if current_status == '배정완료':
            try:
                db.update_status(sel_id, sc.STATUS_FLOW[4])   # 진행중
            except Exception:
                pass
        db.invalidate_data()
        st.toast(f"✅ {ok}명 출석 기록 저장 완료!", icon="✅")
        st.balloons()
    else:
        st.error("❌ 저장 실패 — 다시 시도해주세요.")


# ══════════════════════════════════════════════════════════════════════════════
#  탭3: 🖨️ 인쇄용 출석부
# ══════════════════════════════════════════════════════════════════════════════

def _tab_printable(data):
    df_inq = data.get('inq', pd.DataFrame())
    sel_id, sel = _select_project(df_inq, ['배정완료', '진행중', '완료'], "print")
    if sel_id is None:
        return

    confirmed_df = db.get_confirmed_assignments(sel_id)
    event_name = str(sel.get('행사명', ''))
    company    = str(sel.get('업체명', ''))
    location   = str(sel.get('장소', ''))

    if confirmed_df.empty:
        st.warning("확정된 인원이 없습니다. 먼저 인원배정을 완료하세요.")
        return

    name_col = _col(confirmed_df, '인력명', '이름')
    role_col = _col(confirmed_df, '직무', '역할')

    event_dates, start_date, end_date = _build_event_dates(sel)

    cd1, cd2 = st.columns(2)
    with cd1:
        print_start = st.date_input("시작일",
                                     value=start_date or datetime.now().date(), key="pr_s")
    with cd2:
        print_end = st.date_input("종료일",
                                   value=end_date or (datetime.now() + timedelta(days=3)).date(),
                                   key="pr_e")

    dates = _generate_dates(print_start.strftime("%Y-%m-%d"), print_end.strftime("%Y-%m-%d"))
    date_range_str = f"{print_start} ~ {print_end}"

    staff_list = []
    for _, r in confirmed_df.iterrows():
        staff_list.append({
            '인력명': str(r.get(name_col, '')),
            '직무':  str(r.get(role_col, '')),
            '연락처': str(r.get('연락처', '')),
            '배정ID': str(r.get('배정ID', '')),
        })

    st.markdown(f"**인원**: {len(staff_list)}명 | **기간**: {date_range_str} ({len(dates)}일)")

    att_records = _load_attendance_data(sel_id)

    if st.button("📄 출석부 생성", type="primary", use_container_width=True, key="gen_pr"):
        html = generate_printable_attendance_html(
            event_name, company, location, date_range_str,
            staff_list, dates, att_records)
        st.session_state['_print_html'] = html

    if '_print_html' in st.session_state:
        html = st.session_state['_print_html']
        st.components.v1.html(html, height=600, scrolling=True)
        cdl1, cdl2 = st.columns(2)
        with cdl1:
            st.download_button(
                "📥 HTML 파일로 저장", data=html,
                file_name=f"출석부_{event_name}_{print_start.strftime('%Y%m%d')}.html",
                mime="text/html", use_container_width=True)
        with cdl2:
            st.info("💡 미리보기의 '🖨️ 인쇄하기' 버튼을 클릭하거나, HTML 파일을 브라우저로 열어 인쇄하세요.")


# ══════════════════════════════════════════════════════════════════════════════
#  탭4: 📄 증명서
# ══════════════════════════════════════════════════════════════════════════════

def _tab_certificate(data):
    df_inq = data.get('inq', pd.DataFrame())
    sel_id, sel = _select_project(df_inq, ['배정완료', '진행중', '완료', '정산완료'], "cert")
    if sel_id is None:
        return

    confirmed_df = db.get_confirmed_assignments(sel_id)
    project_name = str(sel.get('행사명', ''))

    if confirmed_df.empty:
        st.warning("확정된 인원이 없습니다.")
        return

    name_col = _col(confirmed_df, '인력명', '이름')
    role_col = _col(confirmed_df, '직무', '역할')
    days_col = _col(confirmed_df, '근무일수', '일수')

    labels = []
    for _, r in confirmed_df.iterrows():
        n  = str(r.get(name_col, ''))
        ro = str(r.get(role_col, ''))
        labels.append(f"{n} ({ro})" if ro else n)

    sel_idx = st.selectbox("인원 선택", range(len(confirmed_df)),
                           format_func=lambda x: labels[x], key="cert_sel")
    sel_row    = confirmed_df.iloc[sel_idx]
    staff_name = str(sel_row.get(name_col, ''))
    try:
        total_days = int(sel_row.get(days_col, 1) or 1)
    except Exception:
        total_days = 1
    if total_days <= 0:
        total_days = 1

    attended_days = st.number_input("출석 일수", 0, total_days, total_days, key="cert_days")

    if st.button("📄 증명서 생성", type="primary", key="gen_cert"):
        cert_html = generate_certificate_html(staff_name, project_name, total_days, attended_days)
        st.components.v1.html(cert_html, height=700, scrolling=True)
        st.download_button(
            "📥 증명서 다운로드 (HTML)", data=cert_html,
            file_name=f"{staff_name}_출석증명_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html")


# ─── 출석 데이터 로드 ─────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _load_attendance_data(inquiry_id):
    client = db.get_connection()
    if not client:
        return pd.DataFrame()
    try:
        sh  = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("출석부")
        records = wks.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return df
        inq_col = _safe_col(df, ['문의ID'])
        if inq_col:
            df = df[df[inq_col].astype(str).str.strip() == str(inquiry_id).strip()]
        return df
    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════════════════════════════

def show(data):
    apply_styles()
    db.ensure_attendance_sheet()

    st.title("📋 출석부 관리")

    df_inq = data.get('inq', pd.DataFrame())
    if df_inq.empty:
        st.warning("프로젝트(문의) 정보가 없습니다.")
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 스케줄표", "✏️ 출석 기록", "🖨️ 인쇄용 출석부", "📄 증명서"
    ])

    with tab1:
        _tab_schedule(data)
    with tab2:
        _tab_attendance_input(data)
    with tab3:
        _tab_printable(data)
    with tab4:
        _tab_certificate(data)
