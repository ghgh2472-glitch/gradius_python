# utils_dashboard.py
import pandas as pd
import re
from datetime import datetime, timedelta

# ---------------------------------------------------------
# 0. 스마트 컬럼 탐지기 (안전장치 강화)
# ---------------------------------------------------------
def find_col(df, candidates):
    """
    데이터프레임에서 후보군 컬럼을 찾습니다.
    못 찾으면 None을 반환합니다.
    """
    if df.empty: return None
    
    # 1. 정확한 매칭
    for col in df.columns:
        if col in candidates: return col
    # 2. 포함된 단어 매칭
    for col in df.columns:
        for cand in candidates:
            if cand in col: return col
    return None

# ---------------------------------------------------------
# 1. 데이터 클렌징
# ---------------------------------------------------------
def safe_int(val):
    try:
        if pd.isna(val) or val == "": return 0
        if isinstance(val, str):
            clean_val = val.replace(',', '').replace('원', '').replace('명', '').replace('건', '').replace('개', '').strip()
            if not clean_val: return 0
            return int(float(clean_val))
        return int(float(val))
    except: return 0

def parse_financials(row, note_col):
    sales = 0; profit = 0
    text = str(row.get(note_col, ''))
    sales_match = re.search(r'\[매출:([\d,]+)\]', text)
    profit_match = re.search(r'\[수익:([\d,]+)\]', text)
    if sales_match: sales = safe_int(sales_match.group(1))
    if profit_match: profit = safe_int(profit_match.group(1))
    return sales, profit

# ---------------------------------------------------------
# 2. KPI 계산 (KeyError 원천 차단)
# ---------------------------------------------------------
def calculate_kpi(df_inq):
    # 1. 데이터가 아예 없으면 0 반환
    if df_inq.empty: 
        return {"sales":0, "profit":0, "unpaid":0, "active":0}
    
    # 2. 필수 컬럼 찾기
    col_status = find_col(df_inq, ["체결", "상태", "진행상태"])
    col_note = find_col(df_inq, ["특이사항", "비고"])
    col_pay = find_col(df_inq, ["결제", "입금"]) 

    # 3. 필수 컬럼('체결')조차 없으면 0 반환 (에러 방지)
    if not col_status:
        return {"sales":0, "profit":0, "unpaid":0, "active":0}

    total_sales = 0; total_profit = 0; total_unpaid = 0
    active_count = 0
    
    try:
        # 체결된 건만 필터링 (에러 안 나게 안전하게)
        signed_df = df_inq[df_inq[col_status].astype(str).str.contains('체결|완료|진행', na=False)]
        active_count = len(signed_df)
        
        for _, row in signed_df.iterrows():
            # 특이사항 컬럼이 있으면 파싱, 없으면 0
            if col_note:
                s, p = parse_financials(row, col_note)
            else:
                s, p = 0, 0
                
            total_sales += s
            total_profit += p
            
            # 미수금 계산
            if col_pay and col_pay in df_inq.columns:
                if "완료" not in str(row.get(col_pay, '')):
                    total_unpaid += s
            else:
                total_unpaid += s
    except Exception as e:
        print(f"KPI Calc Error: {e}")
        return {"sales":0, "profit":0, "unpaid":0, "active":0}

    return {"sales": total_sales, "profit": total_profit, "unpaid": total_unpaid, "active": active_count}

# ---------------------------------------------------------
# 3. 차트용 데이터
# ---------------------------------------------------------
def get_monthly_trend(df_inq, df_settlement=None, df_estimate=None, selected_year=None):
    """
    월별 매출 추이 (정산 데이터 → 견적 공급가액 → 건수 fallback)
    Args:
        df_inq: 문의 데이터
        df_settlement: 정산 데이터 (있으면 우선 사용)
        df_estimate: 견적 데이터 (정산 없으면 사용)
        selected_year: 특정 연도 필터 (None이면 전체)
    """
    # 1) 정산 데이터에서 매출 추출 (가장 정확)
    if df_settlement is not None and not df_settlement.empty:
        col_date_s = find_col(df_settlement, ["계약일", "정산일", "날짜", "작성일"])
        col_amt = find_col(df_settlement, ["공급가액", "합계금액", "청구금액", "청구금액적기"])
        if col_date_s and col_amt:
            try:
                df_s = df_settlement.copy()
                df_s[col_date_s] = pd.to_datetime(df_s[col_date_s], errors='coerce')
                df_s = df_s.dropna(subset=[col_date_s])
                df_s['_amount'] = df_s[col_amt].apply(safe_int)
                if selected_year:
                    df_s = df_s[df_s[col_date_s].dt.year == selected_year]
                df_s['Month'] = df_s[col_date_s].dt.strftime('%Y-%m')
                trend = df_s.groupby('Month')['_amount'].sum().reset_index()
                trend.columns = ['Month', 'Sales']
                trend = trend[trend['Sales'] > 0].sort_values('Month')
                if not trend.empty:
                    return trend
            except Exception:
                pass

    # 2) 견적 데이터에서 공급가액 추출
    if df_estimate is not None and not df_estimate.empty:
        col_date_e = find_col(df_estimate, ["기록일시", "작성일", "날짜"])
        col_supply = find_col(df_estimate, ["공급가액", "합계금액"])
        if col_date_e and col_supply:
            try:
                df_e = df_estimate.copy()
                df_e[col_date_e] = pd.to_datetime(df_e[col_date_e], errors='coerce')
                df_e = df_e.dropna(subset=[col_date_e])
                df_e['_amount'] = df_e[col_supply].apply(safe_int)
                if selected_year:
                    df_e = df_e[df_e[col_date_e].dt.year == selected_year]
                df_e['Month'] = df_e[col_date_e].dt.strftime('%Y-%m')
                trend = df_e.groupby('Month')['_amount'].sum().reset_index()
                trend.columns = ['Month', 'Sales']
                trend = trend[trend['Sales'] > 0].sort_values('Month')
                if not trend.empty:
                    return trend
            except Exception:
                pass

    # 3) 문의 데이터 기반 건수 fallback (체결 건의 건수 추이)
    if df_inq.empty: return pd.DataFrame()
    col_date = find_col(df_inq, ["작성일", "문의날짜", "날짜", "행사시작일"])
    col_status = find_col(df_inq, ["체결", "상태"])
    
    if not col_date or not col_status: return pd.DataFrame()
    
    try:
        df = df_inq.copy()
        df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
        df = df.dropna(subset=[col_date])
        df = df[df[col_status].astype(str).str.contains('체결|완료|진행|배정', na=False)]
        
        if selected_year:
            df = df[df[col_date].dt.year == selected_year]
        
        if df.empty: return pd.DataFrame()
        
        df['Month'] = df[col_date].dt.strftime('%Y-%m')
        trend = df.groupby('Month').size().reset_index(name='Sales')
        trend = trend.sort_values('Month')
        return trend
    except:
        return pd.DataFrame()

def get_top_clients(df_inq, top_n=5):
    if df_inq.empty: return pd.DataFrame()
    col_client = find_col(df_inq, ["업체명", "고객명"])
    col_status = find_col(df_inq, ["체결", "상태"])
    col_note = find_col(df_inq, ["특이사항", "비고"])
    
    if not col_client or not col_status: return pd.DataFrame()

    try:
        df = df_inq.copy()
        df = df[df[col_status].astype(str).str.contains('체결|완료', na=False)]
        df[col_client] = df[col_client].fillna('기타').replace('-', '기타').replace('', '기타')
        
        if col_note:
            df['parsed_sales'] = df.apply(lambda r: parse_financials(r, col_note)[0], axis=1)
        else:
            df['parsed_sales'] = 0
        
        ranking = df.groupby(col_client)['parsed_sales'].sum().reset_index()
        ranking = ranking.sort_values(by='parsed_sales', ascending=False).head(top_n)
        ranking.reset_index(drop=True, inplace=True)
        ranking['순위'] = ranking.index + 1
        ranking.columns = ['고객사', '총매출', '순위']
        return ranking[['순위', '고객사', '총매출']]
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 4. 리스트 추출
# ---------------------------------------------------------
def get_unpaid_list(df_inq):
    if df_inq.empty: return pd.DataFrame()
    col_date = find_col(df_inq, ["행사시작일", "시작일", "일시", "행사일시", "날짜"])
    col_client = find_col(df_inq, ["업체명"])
    col_status = find_col(df_inq, ["체결", "상태"])
    col_note = find_col(df_inq, ["특이사항"])
    col_pay = find_col(df_inq, ["결제", "입금"])
    col_phone = find_col(df_inq, ["연락처", "전화번호"])
    
    if not col_date or not col_client or not col_status: return pd.DataFrame()
    
    try:
        df = df_inq[df_inq[col_status].astype(str).str.contains('체결|완료|진행', na=False)].copy()
        
        if col_pay and col_pay in df.columns:
            df = df[~df[col_pay].astype(str).str.contains('완료', na=False)]
        
        if col_note:
            df['미수금액'] = df.apply(lambda r: parse_financials(r, col_note)[0], axis=1)
        else:
            df['미수금액'] = 0
            
        df['연락처'] = df[col_phone] if (col_phone and col_phone in df.columns) else "-"

        target_cols = [col_date, col_client, '미수금액', '연락처']
        if col_pay and col_pay in df.columns: target_cols.append(col_pay)
        
        # 존재하는 컬럼만 선택
        valid_cols = [c for c in target_cols if c in df.columns]
        result = df[valid_cols].sort_values(by=col_date)
        result.rename(columns={col_date: '일자'}, inplace=True)
        return result
    except:
        return pd.DataFrame()

def get_pending_list(df_inq):
    if df_inq.empty: return pd.DataFrame()
    col_date = find_col(df_inq, ["문의날짜", "접수일"])
    col_client = find_col(df_inq, ["업체명"])
    col_status = find_col(df_inq, ["체결", "상태"])
    col_event = find_col(df_inq, ["행사명"])
    col_phone = find_col(df_inq, ["연락처", "전화번호"])
    
    if not col_date or not col_status: return pd.DataFrame()
    
    try:
        df = df_inq[df_inq[col_status].astype(str).str.contains('미정|견적|상담|접수대기', na=False)].copy()
        df['연락처'] = df[col_phone] if (col_phone and col_phone in df.columns) else "-"
        
        cols = [c for c in [col_date, col_client, col_event, '연락처', col_status] if c and c in df.columns]
        result = df[cols].sort_values(by=col_date, ascending=False)
        result.rename(columns={col_date: '문의일', col_client:'업체명', col_event:'건명'}, inplace=True)
        return result
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 5. 캘린더 데이터
# ---------------------------------------------------------
def get_calendar_events(df_inq, df_dispatch=None):
    if df_inq.empty: return []
    
    # 시작일/종료일 별도 컬럼 우선 탐색
    col_start = find_col(df_inq, ["행사시작일", "시작일", "행사일시", "일시", "투입일"])
    col_end = find_col(df_inq, ["행사종료일", "종료일"])
    col_client = find_col(df_inq, ["업체명"]) or "업체명"
    col_event = find_col(df_inq, ["행사명"]) or "행사명"
    col_status = find_col(df_inq, ["상태", "체결"])
    col_time = find_col(df_inq, ["행사시간", "시간"])
    col_headcount = find_col(df_inq, ["필요인력", "요청인원", "인원"])
    
    # 배정기록에서 행사별 인원수 미리 집계
    dispatch_counts = {}
    dispatch_names = {}
    if df_dispatch is not None and not df_dispatch.empty:
        _d_evt_col = find_col(df_dispatch, ["행사명"])
        _d_name_col = find_col(df_dispatch, ["인력명", "직원명", "인원"])
        if _d_evt_col:
            for evt, grp in df_dispatch.groupby(df_dispatch[_d_evt_col].astype(str).str.strip()):
                dispatch_counts[evt] = len(grp)
                if _d_name_col and _d_name_col in grp.columns:
                    names = grp[_d_name_col].astype(str).str.strip().tolist()
                    dispatch_names[evt] = ", ".join([n for n in names if n and n not in ('nan', '')])
    
    if not col_start: return []
    if col_start not in df_inq.columns: return []

    events = []
    try:
        for _, row in df_inq.iterrows():
            raw_start = row.get(col_start, '')
            if pd.isna(raw_start) or str(raw_start).strip() == "": continue
            
            start_str = str(raw_start).strip()
            
            # 종료일 컬럼이 있으면 사용, 없으면 시작일과 동일
            if col_end and col_end in df_inq.columns:
                raw_end = row.get(col_end, '')
                end_str = str(raw_end).strip() if raw_end and not pd.isna(raw_end) and str(raw_end).strip() not in ('', 'nan', 'None') else start_str
            else:
                # 단일 컬럼에 "~"로 구분된 경우
                if "~" in start_str:
                    splits = start_str.split("~")
                    start_str = splits[0].strip()
                    end_str = splits[1].strip()
                else:
                    end_str = start_str
            
            # 날짜 형식 정규화 — 다양한 형식 지원
            def _normalize_date(s):
                """날짜 문자열을 YYYY-MM-DD 형식으로 정규화"""
                s = str(s).strip()
                if not s or s in ('nan', 'None', ''): return None
                # 이미 YYYY-MM-DD 형식이면 [:10] 추출
                if len(s) >= 10 and s[4] in ('-', '/') and s[7] in ('-', '/'):
                    return s[:10].replace('/', '-')
                # YYYY.MM.DD 형식
                m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', s)
                if m:
                    return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
                # MM/DD/YYYY 등
                m2 = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})', s)
                if m2:
                    return f"{m2.group(3)}-{m2.group(1).zfill(2)}-{m2.group(2).zfill(2)}"
                return None

            start_dt = _normalize_date(start_str)
            end_dt = _normalize_date(end_str)

            if not start_dt: continue
            if not end_dt: end_dt = start_dt
            
            # FullCalendar의 end는 exclusive → 1일 추가
            try:
                end_date_obj = datetime.strptime(end_dt, "%Y-%m-%d")
                end_dt_exclusive = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
            except:
                end_dt_exclusive = end_dt
            
            status = str(row.get(col_status, '')) if col_status else ''
            color = "#3B82F6"  # 기본: 파랑
            if "완료" in status or "정산" in status: color = "#059669"  # 녹색
            elif "체결" in status or "배정" in status or "진행" in status: color = "#2563EB"  # 진한파랑
            elif "미정" in status or "접수" in status: color = "#D97706"  # 주황
            elif "취소" in status or "미체결" in status: color = "#DC2626"  # 빨강
            
            client_name = row.get(col_client, '') if col_client in df_inq.columns else ''
            if pd.isna(client_name): client_name = ''
            event_name = row.get(col_event, '') if col_event in df_inq.columns else ''
            if pd.isna(event_name): event_name = ''
            
            # 간략 정보 구성 (인원, 시간)
            info_parts = []
            evt_key = str(event_name).strip()
            need = safe_int(row.get(col_headcount, 0)) if col_headcount and col_headcount in df_inq.columns else 0
            assigned = dispatch_counts.get(evt_key, 0)
            if need > 0:
                if assigned >= need:
                    assign_label = f"{assigned}/{need}명 배정완료"
                elif assigned == 0:
                    assign_label = f"0/{need}명 배정필요"
                else:
                    assign_label = f"{assigned}/{need}명 배정중"
                info_parts.append(assign_label)
            elif assigned > 0:
                info_parts.append(f"{assigned}명")
            
            time_str = str(row.get(col_time, '')).strip() if col_time and col_time in df_inq.columns else ''
            if time_str and time_str not in ('nan', 'None', ''):
                info_parts.append(time_str)
            
            # 배정 인력 이름 (3명까지)
            names_str = dispatch_names.get(evt_key, '')
            if names_str:
                name_list = names_str.split(", ")
                if len(name_list) > 3:
                    names_str = ", ".join(name_list[:3]) + f" 외 {len(name_list)-3}명"
            
            # 타이틀 구성
            base_title = f"{client_name} ({event_name})" if client_name else str(event_name)
            if not base_title.strip() or base_title.strip() == '()': base_title = f"행사 {start_dt}"
            
            info_suffix = " | ".join(info_parts)
            title = f"{base_title} [{info_suffix}]" if info_suffix else base_title
            
            # description (이벤트 클릭 시 표시)
            desc_parts = []
            if names_str:
                desc_parts.append(f"👤 {names_str}")
            if time_str and time_str not in ('nan', 'None', ''):
                desc_parts.append(f"⏰ {time_str}")
            description = " / ".join(desc_parts) if desc_parts else ""
            
            # 관리번호/ID
            col_id = find_col(df_inq, ["문의ID", "ID", "관리번호"])
            inq_id = ''
            if col_id and col_id in df_inq.columns:
                inq_id = str(row.get(col_id, '')).strip()
                if inq_id in ('nan', 'None'):
                    inq_id = ''
            
            col_location = find_col(df_inq, ["장소", "현장"])
            location = ''
            if col_location and col_location in df_inq.columns:
                location = str(row.get(col_location, '')).strip()
                if location in ('nan', 'None'):
                    location = ''
            
            evt_obj = {
                "title": title,
                "start": start_dt, 
                "end": end_dt_exclusive,
                "backgroundColor": color, 
                "borderColor": color, 
                "allDay": True,
                "extendedProps": {
                    "description": description,
                    "inq_id": inq_id,
                    "status": status,
                    "client": str(client_name),
                    "event_name": str(event_name),
                    "headcount": need,
                    "assigned_count": assigned,
                    "assigned_names": names_str,
                    "time": time_str if time_str not in ('nan', 'None', '') else '',
                    "location": location,
                },
            }
            
            events.append(evt_obj)
    except Exception as e:
        print(f"[Calendar] Error: {e}")
        pass
            
    return events

# ---------------------------------------------------------
# 6. AI & 알림
# ---------------------------------------------------------
def generate_ai_insight(kpi, unpaid_cnt, pending_cnt):
    insights = []
    if kpi['sales'] > 0: insights.append(f"💰 **매출:** {kpi['sales']:,}원")
    if kpi['unpaid'] > 0: insights.append(f"🚨 **미수금:** {kpi['unpaid']:,}원")
    else: insights.append("✅ **자금:** 건전")
    if pending_cnt > 0: insights.append(f"🔥 **영업:** {pending_cnt}건 대기")
    if not insights: return "데이터가 없습니다."
    return "  |  ".join(insights)

def generate_smart_briefing(df_inq, df_dispatch, df_settlement):
    """AI 스마트 브리핑: 오늘 확인해야 할 것"""
    briefing_items = []
    
    # 1️⃣ 미수금 업체
    unpaid = get_unpaid_companies(df_settlement, top_n=3)
    if not unpaid.empty:
        companies = ", ".join(unpaid['업체'].tolist())
        amount = unpaid['미수금액'].sum()
        briefing_items.append(f"💸 <b>미수금 수금 필요</b><br/>아직 돈을 받지 못한 업체: <b>{companies}</b> (총 {amount:,}원)")
    
    # 2️⃣ 곧 나갈 현장 (D-3)
    upcoming = get_upcoming_dispatch_info(df_dispatch, df_inq, days=3)
    if not upcoming.empty:
        for idx, row in upcoming.head(2).iterrows():
            d_day = int(row['D-Day'])
            location = row['장소'] if pd.notna(row['장소']) and str(row['장소']).strip() else "장소미기입"
            staff_count = int(row['배정인원'])
            briefing_items.append(
                f"🔥 <b>곧 나갈 현장 (D-{d_day})</b><br/>"
                f"행사: <b>{row['행사명']}</b><br/>"
                f"장소: {location} | 배정인원: {staff_count}명"
            )
    
    # 3️⃣ 계약 완료 대기
    if not df_inq.empty:
        col_status = find_col(df_inq, ["체결", "상태"])
        if col_status:
            pending_count = len(df_inq[df_inq[col_status].astype(str).str.contains('미정|견적|상담', na=False)])
            if pending_count > 0:
                briefing_items.append(f"📋 <b>계약 완료 대기</b><br/>{pending_count}건의 문의가 진행 중입니다")
    
    return briefing_items if briefing_items else ["✅ 오늘은 특별히 확인할 사항이 없습니다"]

def get_upcoming_events(df_inq, days=7):
    if df_inq.empty: return pd.DataFrame()
    col_date = find_col(df_inq, ["행사시작일", "시작일", "행사일시", "일시", "투입일"])
    col_client = find_col(df_inq, ["업체명"])
    col_event = find_col(df_inq, ["행사명"])
    
    if not col_date: return pd.DataFrame()
    
    try:
        df = df_inq.copy()
        today = datetime.now()
        def parse_dt(d):
            try: return datetime.strptime(str(d).split('~')[0].strip()[:10], "%Y-%m-%d")
            except: return None
        df['evt_dt'] = df[col_date].apply(parse_dt)
        df = df.dropna(subset=['evt_dt'])
        
        df = df[(df['evt_dt'] >= today) & (df['evt_dt'] <= today + timedelta(days=days))]
        if df.empty: return pd.DataFrame()
        
        df['D-Day'] = df['evt_dt'].apply(lambda x: (x-today).days)
        df.sort_values('D-Day', inplace=True)
        
        cols = [col_client, col_event, col_date, 'D-Day']
        # 존재하는 컬럼만 선택
        final_cols = [c for c in cols if c and c in df.columns]
        res = df[final_cols].copy()
        res.columns = ['업체명', '행사명', '일시', 'D-Day'][:len(final_cols)]
        return res
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 7. 신규 대시보드 (인력파견 + 정산 통합)
# ---------------------------------------------------------
def get_most_dispatched_staff(df_dispatch, top_n=5):
    """가장 많이 파견된 인원 순위"""
    if df_dispatch.empty: return pd.DataFrame()
    col_staff = find_col(df_dispatch, ["인력명", "직원명", "인원", "이름"])
    col_role = find_col(df_dispatch, ["직무", "직급", "직책", "구분"])
    col_event = find_col(df_dispatch, ["행사명"])
    
    if not col_staff: return pd.DataFrame()
    
    try:
        df = df_dispatch.copy()
        df[col_staff] = df[col_staff].fillna('기타').astype(str)
        ranking = df[col_staff].value_counts().reset_index()
        ranking.columns = ['직원명', '파견횟수']
        ranking = ranking.head(top_n).reset_index(drop=True)
        ranking['순위'] = ranking.index + 1
        
        # 직무 정보 추가 (있으면)
        if col_role and col_role in df.columns:
            role_dict = dict(zip(df[col_staff], df[col_role]))
            ranking['직무'] = ranking['직원명'].map(role_dict).fillna('-')
            return ranking[['순위', '직원명', '직무', '파견횟수']]
        
        return ranking[['순위', '직원명', '파견횟수']]
    except:
        return pd.DataFrame()


def get_dispatch_detail_for_event(df_dispatch, event_name):
    """특정 행사의 배정 인력 상세 정보"""
    if df_dispatch.empty: return pd.DataFrame()
    col_event = find_col(df_dispatch, ["행사명"])
    col_staff = find_col(df_dispatch, ["인력명", "직원명", "인원"])
    col_role = find_col(df_dispatch, ["직무"])
    col_type = find_col(df_dispatch, ["구분"])
    col_status = find_col(df_dispatch, ["지급상태"])
    
    if not col_event or not col_staff: return pd.DataFrame()
    
    try:
        matched = df_dispatch[df_dispatch[col_event].astype(str).str.strip() == str(event_name).strip()]
        if matched.empty: return pd.DataFrame()
        
        cols = [col_staff]
        col_names = ['인력명']
        if col_type and col_type in matched.columns:
            cols.append(col_type); col_names.append('구분')
        if col_role and col_role in matched.columns:
            cols.append(col_role); col_names.append('직무')
        if col_status and col_status in matched.columns:
            cols.append(col_status); col_names.append('상태')
        
        result = matched[cols].copy()
        result.columns = col_names
        return result
    except:
        return pd.DataFrame()


def get_all_events_with_status(df_inq, df_dispatch):
    """전체 행사 목록을 D-Day + 배정현황과 함께 반환"""
    if df_inq.empty: return pd.DataFrame()
    
    col_date = find_col(df_inq, ["행사시작일", "시작일", "행사일시", "일시"])
    col_end = find_col(df_inq, ["행사종료일", "종료일"])
    col_client = find_col(df_inq, ["업체명"])
    col_event = find_col(df_inq, ["행사명"])
    col_location = find_col(df_inq, ["장소", "현장"])
    col_status = find_col(df_inq, ["상태", "체결"])
    col_need = find_col(df_inq, ["필요인력", "인원"])
    
    if not col_date: return pd.DataFrame()
    
    try:
        df = df_inq.copy()
        today = datetime.now()
        
        def parse_dt(d):
            try: return datetime.strptime(str(d).split('~')[0].strip()[:10], "%Y-%m-%d")
            except: return None
        
        df['evt_dt'] = df[col_date].apply(parse_dt)
        df = df.dropna(subset=['evt_dt'])
        if df.empty: return pd.DataFrame()
        
        df['D-Day'] = df['evt_dt'].apply(lambda x: (x - today).days)
        df = df.sort_values('D-Day')
        
        # 배정인원 집계
        if not df_dispatch.empty and col_event:
            col_dispatch_event = find_col(df_dispatch, ["행사명"])
            if col_dispatch_event and col_dispatch_event in df_dispatch.columns:
                dispatch_count = df_dispatch[col_dispatch_event].value_counts().to_dict()
                df['배정인원'] = df[col_event].map(dispatch_count).fillna(0).astype(int)
            else:
                df['배정인원'] = 0
        else:
            df['배정인원'] = 0
        
        # 필요인력
        if col_need:
            df['필요인원'] = df[col_need].apply(lambda x: safe_int(x) if x else 0)
        else:
            df['필요인원'] = 0
        
        result_cols = {
            '업체': col_client,
            '행사명': col_event,
            '장소': col_location,
            '시작일': col_date,
        }
        if col_end: result_cols['종료일'] = col_end
        if col_status: result_cols['상태'] = col_status
        
        valid_cols = {k: v for k, v in result_cols.items() if v and v in df.columns}
        res = df[list(valid_cols.values()) + ['배정인원', '필요인원', 'D-Day']].copy()
        rename_map = {v: k for k, v in valid_cols.items()}
        res = res.rename(columns=rename_map)
        
        return res
    except Exception as e:
        print(f"get_all_events_with_status error: {e}")
        return pd.DataFrame()

def get_top_customers(df_inq, top_n=5):
    """가장 많이 체결된 고객 순위"""
    if df_inq.empty: return pd.DataFrame()
    col_client = find_col(df_inq, ["업체명", "고객명"])
    col_status = find_col(df_inq, ["체결", "상태"])
    
    if not col_client or not col_status: return pd.DataFrame()
    
    try:
        df = df_inq[df_inq[col_status].astype(str).str.contains('체결|완료', na=False)].copy()
        df[col_client] = df[col_client].fillna('기타').astype(str).replace('-', '기타').replace('', '기타')
        
        ranking = df[col_client].value_counts().reset_index()
        ranking.columns = ['고객사', '체결건수']
        ranking = ranking.head(top_n).reset_index(drop=True)
        ranking['순위'] = ranking.index + 1
        
        return ranking[['순위', '고객사', '체결건수']]
    except:
        return pd.DataFrame()

def get_settlement_overview(df_settlement):
    """정산 현황 요약 (실제 미수금 계산)"""
    if df_settlement.empty:
        return {"총청구액": 0, "받은금액": 0, "미수금액": 0, "수금률": 0}
    
    col_invoice = find_col(df_settlement, ["공급가액"])
    col_tax = find_col(df_settlement, ["부가세"])
    col_paid = find_col(df_settlement, ["받은금액"])
    
    try:
        total_invoice = 0
        total_paid = 0
        
        for _, row in df_settlement.iterrows():
            # 청구액 = 공급가액 + 부가세
            invoice_amt = 0
            if col_invoice:
                invoice_amt = safe_int(row.get(col_invoice, 0))
            if col_tax:
                tax_amt = safe_int(row.get(col_tax, 0))
                invoice_amt += tax_amt
            
            total_invoice += invoice_amt
            
            # 받은금액
            if col_paid:
                paid_amt = safe_int(row.get(col_paid, 0))
                total_paid += paid_amt
        
        # 미수금 = 총청구액 - 받은금액 (잔액 컬럼 대신 직접 계산하여 정확성 보장)
        total_balance = total_invoice - total_paid
        
        수금률 = int((total_paid / total_invoice * 100) if total_invoice > 0 else 0)
        
        return {
            "총청구액": total_invoice,
            "받은금액": total_paid,
            "미수금액": total_balance,
            "수금률": 수금률
        }
    except Exception as e:
        print(f"Settlement overview error: {e}")
        return {"총청구액": 0, "받은금액": 0, "미수금액": 0, "수금률": 0}

def get_unpaid_companies(df_settlement, top_n=5):
    """미수금 있는 업체 Top N (금액순)"""
    if df_settlement.empty: return pd.DataFrame()
    
    col_client = find_col(df_settlement, ["업체", "업체명"])
    col_balance = find_col(df_settlement, ["잔액", "미수금액"])
    col_amount = find_col(df_settlement, ["청구금액", "공급가액"])
    
    if not col_client or not col_balance: return pd.DataFrame()
    
    try:
        df = df_settlement.copy()
        df['미수금'] = df[col_balance].apply(safe_int)
        df = df[df['미수금'] > 0]  # 미수금 > 0인 것만
        df = df.sort_values('미수금', ascending=False).head(top_n)
        
        result = pd.DataFrame({
            '업체': df[col_client],
            '미수금액': df['미수금']
        })
        result = result.reset_index(drop=True)
        result['순위'] = result.index + 1
        return result[['순위', '업체', '미수금액']]
    except Exception as e:
        print(f"Unpaid companies error: {e}")
        return pd.DataFrame()

def get_upcoming_dispatch_info(df_dispatch, df_inq, days=7):
    """곧 나갈 현장 정보 (인원/장소/일정 포함)"""
    if df_inq.empty: return pd.DataFrame()
    
    col_date = find_col(df_inq, ["행사시작일", "시작일", "행사일시", "일시"])
    col_client = find_col(df_inq, ["업체명"])
    col_event = find_col(df_inq, ["행사명"])
    col_location = find_col(df_inq, ["장소", "현장"])
    
    if not col_date: return pd.DataFrame()
    
    try:
        df = df_inq.copy()
        today = datetime.now()
        
        def parse_dt(d):
            try: 
                return datetime.strptime(str(d).split('~')[0].strip()[:10], "%Y-%m-%d")
            except: 
                return None
        
        df['evt_dt'] = df[col_date].apply(parse_dt)
        df = df.dropna(subset=['evt_dt'])
        
        df = df[(df['evt_dt'] >= today) & (df['evt_dt'] <= today + timedelta(days=days))]
        if df.empty: return pd.DataFrame()
        
        df['D-Day'] = df['evt_dt'].apply(lambda x: (x-today).days)
        
        # 배정기록에서 각 행사의 인원 수 집계
        if not df_dispatch.empty:
            col_dispatch_event = find_col(df_dispatch, ["행사명", "이벤트"])
            if col_dispatch_event and col_dispatch_event in df_dispatch.columns:
                dispatch_count = df_dispatch[col_dispatch_event].value_counts().to_dict()
                df['배정인원'] = df[col_event].map(dispatch_count).fillna(0).astype(int)
            else:
                df['배정인원'] = 0
        else:
            df['배정인원'] = 0
        
        df.sort_values('D-Day', inplace=True)
        
        cols = [col_client, col_event, col_location, col_date, '배정인원', 'D-Day']
        valid_cols = [c for c in cols if c and c in df.columns]
        res = df[valid_cols].copy()
        
        res.columns = ['업체', '행사명', '장소', '일정', '배정인원', 'D-Day']
        return res.head(10)
    except Exception as e:
        print(f"Upcoming dispatch error: {e}")
        return pd.DataFrame()

def get_payment_status_breakdown(df_settlement):
    """정산 상태별 분류 (입금완료, 부분입금, 미수금) - 입금여부 컬럼 우선 사용"""
    if df_settlement.empty: return {}
    
    col_status = find_col(df_settlement, ["입금여부", "진행상황", "상태", "입금상태"])
    
    if not col_status: return {}
    
    try:
        status_count = df_settlement[col_status].value_counts().to_dict()
        return status_count
    except Exception as e:
        print(f"Status breakdown error: {e}")
        return {}


def get_operating_profit(df_settlement, df_dispatch, df_payment=None):
    """영업이익 계산: 공급가액 합계 - 총지급액 합계 (지급내역 우선 사용)"""
    total_supply = 0
    total_payment = 0
    
    # 1) 정산 시트에서 공급가액 합계
    if not df_settlement.empty:
        col_supply = find_col(df_settlement, ["공급가액"])
        col_payment_s = find_col(df_settlement, ["지급액"])
        if col_supply:
            total_supply = df_settlement[col_supply].apply(safe_int).sum()
        if col_payment_s:
            total_payment = df_settlement[col_payment_s].apply(safe_int).sum()
    
    # 2) 지급내역 시트에서 실제 최종지급액 합산 (가장 정확한 데이터)
    if df_payment is not None and not df_payment.empty:
        col_final_pay = find_col(df_payment, ["최종지급액", "실지급액"])
        if col_final_pay:
            actual_payment = df_payment[col_final_pay].apply(safe_int).sum()
            if actual_payment > 0:
                total_payment = actual_payment
    
    # 3) 지급액이 아직 0이면 배정기록에서 총지급액 합산 (예상치 fallback)
    if total_payment == 0 and not df_dispatch.empty:
        col_total_pay = find_col(df_dispatch, ["총지급액", "지급액"])
        if col_total_pay:
            total_payment = df_dispatch[col_total_pay].apply(safe_int).sum()
    
    profit = total_supply - total_payment
    margin_rate = round(profit / total_supply * 100, 1) if total_supply > 0 else 0
    
    return {
        "공급가액": total_supply,
        "지급액": total_payment,
        "영업이익": profit,
        "이익률": margin_rate
    }


def get_stale_estimates(df_inq, days_threshold=7):
    """견적 작성 후 N일 이상 체결 안 된 건 목록"""
    if df_inq.empty: return pd.DataFrame()
    
    col_status = find_col(df_inq, ["체결", "상태"])
    col_date = find_col(df_inq, ["작성일", "문의날짜", "날짜"])
    col_client = find_col(df_inq, ["업체명", "고객명"])
    col_event = find_col(df_inq, ["행사명"])
    col_id = find_col(df_inq, ["문의ID", "ID", "관리번호"])
    
    if not col_status or not col_date: return pd.DataFrame()
    
    try:
        df = df_inq[df_inq[col_status].astype(str).str.strip() == '견적'].copy()
        if df.empty: return pd.DataFrame()
        
        df['_date'] = pd.to_datetime(df[col_date], errors='coerce')
        df = df.dropna(subset=['_date'])
        if df.empty: return pd.DataFrame()
        
        today = datetime.now()
        df['경과일'] = (today - df['_date']).dt.days
        df = df[df['경과일'] >= days_threshold]
        if df.empty: return pd.DataFrame()
        
        df = df.sort_values('경과일', ascending=False)
        
        result_cols = {}
        if col_id: result_cols['문의ID'] = col_id
        if col_client: result_cols['업체명'] = col_client
        if col_event: result_cols['행사명'] = col_event
        result_cols['경과일'] = '경과일'
        
        res = df[list(result_cols.values())].copy()
        res.columns = list(result_cols.keys())
        return res.head(10)
    except Exception as e:
        print(f"Stale estimates error: {e}")
        return pd.DataFrame()


def get_estimate_conversion_rate(df_inq):
    """견적 → 체결 전환율 (월별 + 전체)"""
    if df_inq.empty: return {"전체전환율": 0, "견적건수": 0, "체결건수": 0, "대기건수": 0}
    
    col_status = find_col(df_inq, ["체결", "상태"])
    if not col_status: return {"전체전환율": 0, "견적건수": 0, "체결건수": 0, "대기건수": 0}
    
    try:
        statuses = df_inq[col_status].astype(str).str.strip()
        
        # 견적 단계를 거친 건 = 현재 견적 + 체결 이후 + 미체결
        estimate_passed = statuses.isin(['견적', '체결', '배정완료', '진행중', '완료', '정산완료', '미체결'])
        total_estimated = int(estimate_passed.sum())
        
        # 체결된 건 (체결 이후 모든 단계)
        contracted = statuses.isin(['체결', '배정완료', '진행중', '완료', '정산완료'])
        total_contracted = int(contracted.sum())
        
        # 아직 견적 대기 중인 건
        waiting = int((statuses == '견적').sum())
        
        rate = round(total_contracted / total_estimated * 100, 1) if total_estimated > 0 else 0
        
        return {
            "전체전환율": rate,
            "견적건수": total_estimated,
            "체결건수": total_contracted,
            "대기건수": waiting
        }
    except:
        return {"전체전환율": 0, "견적건수": 0, "체결건수": 0, "대기건수": 0}


def get_role_statistics(df_dispatch):
    """직군별 배정 통계 (가장 많이 배정된 직군 순위)"""
    if df_dispatch.empty: return pd.DataFrame()
    
    col_role = find_col(df_dispatch, ["직무", "직급", "직책", "역할"])
    if not col_role: return pd.DataFrame()
    
    try:
        df = df_dispatch.copy()
        df[col_role] = df[col_role].fillna('기타').astype(str).str.strip()
        df = df[df[col_role] != '']
        df = df[df[col_role] != '기타']
        
        ranking = df[col_role].value_counts().reset_index()
        ranking.columns = ['직군', '배정횟수']
        ranking = ranking.head(10).reset_index(drop=True)
        ranking['순위'] = ranking.index + 1
        
        # 총지급액 집계
        col_pay = find_col(df_dispatch, ["총지급액", "지급액"])
        if col_pay:
            pay_by_role = df.groupby(col_role)[col_pay].apply(lambda x: x.apply(safe_int).sum())
            ranking['총지급액'] = ranking['직군'].map(pay_by_role).fillna(0).astype(int)
        
        return ranking[['순위', '직군', '배정횟수'] + (['총지급액'] if '총지급액' in ranking.columns else [])]
    except Exception as e:
        print(f"Role statistics error: {e}")
        return pd.DataFrame()


def get_team_dispatch_stats(df_dispatch):
    """팀 배정 통계"""
    if df_dispatch.empty: return {"팀배정건수": 0, "개별배정건수": 0, "팀수": 0, "팀원수": 0}
    
    col_team = find_col(df_dispatch, ["팀코드"])
    if not col_team: return {"팀배정건수": 0, "개별배정건수": 0, "팀수": 0, "팀원수": 0}
    
    try:
        team_mask = df_dispatch[col_team].astype(str).str.strip().ne('') & df_dispatch[col_team].astype(str).str.strip().ne('nan')
        team_count = int(team_mask.sum())
        individual_count = len(df_dispatch) - team_count
        
        unique_teams = df_dispatch.loc[team_mask, col_team].nunique()
        
        col_pay_target = find_col(df_dispatch, ["결제대상"])
        team_leaders = 0
        if col_pay_target:
            team_leaders = int((df_dispatch.loc[team_mask, col_pay_target].astype(str).str.strip() == 'Y').sum())
        
        return {
            "팀배정건수": team_count,
            "개별배정건수": individual_count,
            "팀수": int(unique_teams),
            "팀장수": team_leaders,
            "팀원수": team_count - team_leaders
        }
    except Exception as e:
        print(f"Team stats error: {e}")
        return {"팀배정건수": 0, "개별배정건수": 0, "팀수": 0, "팀원수": 0}

# ---------------------------------------------------------
# 8. 자동화 리포트 생성
# ---------------------------------------------------------
def generate_daily_report(df_inq, df_dispatch, df_settlement):
    """일일 요약 리포트"""
    report = {
        "제목": "📅 일일 보고서",
        "생성일": datetime.now().strftime("%Y년 %m월 %d일 %H:%M"),
        "섹션": []
    }
    
    # 1. 오늘의 매출
    settlement_overview = get_settlement_overview(df_settlement)
    report["섹션"].append({
        "제목": "💰 본일 정산 현황",
        "데이터": [
            f"총청구액: {settlement_overview['총청구액']:,}원",
            f"수금액: {settlement_overview['받은금액']:,}원",
            f"미수금: {settlement_overview['미수금액']:,}원",
            f"수금률: {settlement_overview['수금률']}%"
        ]
    })
    
    # 2. 오늘 나가는 현장
    upcoming = get_upcoming_dispatch_info(df_dispatch, df_inq, days=1)
    if not upcoming.empty:
        today_events = upcoming[upcoming['D-Day'] == 0]
        if not today_events.empty:
            report["섹션"].append({
                "제목": "🔴 오늘의 현장",
                "데이터": [f"{row['업체']} - {row['행사명']} ({row['배정인원']}명)" 
                          for _, row in today_events.iterrows()]
            })
    
    # 3. 긴급 미수금
    unpaid = get_unpaid_companies(df_settlement, top_n=3)
    if not unpaid.empty:
        report["섹션"].append({
            "제목": "🚨 미수금 Top 3",
            "데이터": [f"{row['업체']}: {row['미수금액']:,}원" 
                      for _, row in unpaid.iterrows()]
        })
    
    # 4. 대기 중인 계약
    if not df_inq.empty:
        col_status = find_col(df_inq, ["체결", "상태"])
        if col_status:
            pending = len(df_inq[df_inq[col_status].astype(str).str.contains('미정|견적|상담', na=False)])
            report["섹션"].append({
                "제목": "📋 진행 중인 문의",
                "데이터": [f"총 {pending}건"]
            })
    
    return report

def generate_weekly_report(df_inq, df_dispatch, df_settlement):
    """주간 성과 리포트"""
    report = {
        "제목": "📊 주간 성과 리포트",
        "생성일": datetime.now().strftime("%Y년 %m월 %d일"),
        "주간": f"{(datetime.now() - timedelta(days=6)).strftime('%m/%d')} ~ {datetime.now().strftime('%m/%d')}",
        "섹션": []
    }
    
    # 1. 주간 정산 현황
    settlement = get_settlement_overview(df_settlement)
    report["섹션"].append({
        "제목": "💳 주간 정산 현황",
        "데이터": {
            "총청구액": f"{settlement['총청구액']:,}원",
            "수금액": f"{settlement['받은금액']:,}원",
            "미수금": f"{settlement['미수금액']:,}원",
            "수금률": f"{settlement['수금률']}%"
        }
    })
    
    # 2. 최다 파견 인력
    top_staff = get_most_dispatched_staff(df_dispatch, top_n=5)
    if not top_staff.empty:
        report["섹션"].append({
            "제목": "👥 최다 파견 인력 Top 5",
            "데이터": [f"{row['순위']}. {row['직원명']} ({row['파견횟수']}회)" 
                      for _, row in top_staff.iterrows()]
        })
    
    # 3. 주요 거래처
    top_clients = get_top_customers(df_inq, top_n=5)
    if not top_clients.empty:
        report["섹션"].append({
            "제목": "🏢 주요 거래처 Top 5",
            "데이터": [f"{row['순위']}. {row['고객사']} ({row['체결건수']}건)" 
                      for _, row in top_clients.iterrows()]
        })
    
    # 4. 미수금 현황
    unpaid = get_unpaid_companies(df_settlement, top_n=5)
    if not unpaid.empty:
        total_unpaid = unpaid['미수금액'].sum()
        report["섹션"].append({
            "제목": "🚨 미수금 현황",
            "데이터": {
                "미수금 업체": len(unpaid),
                "총 미수금": f"{total_unpaid:,}원",
                "상위 3업체": [f"{row['업체']}: {row['미수금액']:,}원" 
                              for _, row in unpaid.head(3).iterrows()]
            }
        })
    
    return report

def generate_monthly_report(df_inq, df_dispatch, df_settlement):
    """월간 분석 리포트"""
    report = {
        "제목": "📈 월간 분석 리포트",
        "생성일": datetime.now().strftime("%Y년 %m월"),
        "섹션": []
    }
    
    # 1. 월간 매출
    monthly = get_monthly_trend(df_inq)
    current_month = datetime.now().strftime('%Y-%m')
    previous_month = (datetime.now() - timedelta(days=30)).strftime('%Y-%m')
    
    current_sales = 0
    previous_sales = 0
    
    if not monthly.empty:
        current = monthly[monthly['Month'] == current_month]
        previous = monthly[monthly['Month'] == previous_month]
        
        if not current.empty:
            current_sales = int(current['Sales'].values[0])
        if not previous.empty:
            previous_sales = int(previous['Sales'].values[0])
    
    growth_rate = 0
    if previous_sales > 0:
        growth_rate = ((current_sales - previous_sales) / previous_sales) * 100
    
    report["섹션"].append({
        "제목": "💰 월간 매출",
        "데이터": {
            f"{current_month}": f"{current_sales:,}원",
            f"{previous_month}": f"{previous_sales:,}원",
            "전월 대비 증감": f"{growth_rate:+.1f}%" if growth_rate != 0 else "신규"
        }
    })
    
    # 2. 정산 현황
    settlement = get_settlement_overview(df_settlement)
    report["섹션"].append({
        "제목": "📊 월간 정산 현황",
        "데이터": {
            "총청구액": f"{settlement['총청구액']:,}원",
            "수금액": f"{settlement['받은금액']:,}원",
            "미수금": f"{settlement['미수금액']:,}원",
            "수금률": f"{settlement['수금률']}%"
        }
    })
    
    # 3. 실행 지표
    total_dispatch = len(df_dispatch)
    total_inquiries = len(df_inq)
    
    col_status = find_col(df_inq, ["체결", "상태"])
    completed_count = 0
    if col_status:
        completed_count = len(df_inq[df_inq[col_status].astype(str).str.contains('체결|완료', na=False)])
    
    report["섹션"].append({
        "제목": "📈 실행 지표",
        "데이터": {
            "전체 문의": f"{total_inquiries}건",
            "체결 건수": f"{completed_count}건",
            "체결율": f"{int((completed_count/total_inquiries*100) if total_inquiries > 0 else 0)}%",
            "파견 건수": f"{total_dispatch}건"
        }
    })
    
    return report

def format_report_text(report):
    """리포트를 텍스트 형식으로 변환"""
    text = f"\n{'='*60}\n"
    text += f"{report['제목']}\n"
    text += f"생성일: {report['생성일']}\n"
    text += f"{'='*60}\n\n"
    
    for section in report.get('섹션', []):
        text += f"【{section['제목']}】\n"
        
        if isinstance(section['데이터'], list):
            for item in section['데이터']:
                text += f"  • {item}\n"
        elif isinstance(section['데이터'], dict):
            for key, value in section['데이터'].items():
                if isinstance(value, list):
                    text += f"  {key}:\n"
                    for item in value:
                        text += f"    - {item}\n"
                else:
                    text += f"  • {key}: {value}\n"
        
        text += "\n"
    
    text += f"{'='*60}\n"
    return text


# ---------------------------------------------------------
# 미수금 상세 분석 함수
# ---------------------------------------------------------
def _calc_balance(df_settlement):
    """잔액 컬럼을 계산하여 '_잔액' 컬럼 추가. 잔액 컬럼이 있으면 사용, 없으면 공급가액+부가세-받은금액으로 계산."""
    df = df_settlement.copy()
    col_balance = find_col(df, ["잔액", "미수금액"])
    col_amount = find_col(df, ["공급가액", "청구금액"])
    col_tax = find_col(df, ["부가세"])
    col_paid = find_col(df, ["받은금액"])
    
    if col_balance and col_balance in df.columns:
        df['_잔액'] = df[col_balance].apply(safe_int)
    elif col_amount and col_paid:
        # 공급가액 + 부가세 - 받은금액으로 계산
        df['_잔액'] = df[col_amount].apply(safe_int)
        if col_tax and col_tax in df.columns:
            df['_잔액'] = df['_잔액'] + df[col_tax].apply(safe_int)
        df['_잔액'] = df['_잔액'] - df[col_paid].apply(safe_int)
    else:
        df['_잔액'] = 0
    
    return df


def get_unpaid_detail(df_settlement):
    """미수금 업체별 상세 내역 (전체)"""
    if df_settlement.empty:
        return pd.DataFrame()
    
    col_client = find_col(df_settlement, ["업체", "업체명"])
    col_event = find_col(df_settlement, ["현장명", "행사명"])
    col_date = find_col(df_settlement, ["파견일자", "계약일", "날짜"])
    col_amount = find_col(df_settlement, ["청구금액", "공급가액"])
    col_paid = find_col(df_settlement, ["받은금액"])
    col_progress = find_col(df_settlement, ["입금여부", "진행상황"])
    
    if not col_client:
        return pd.DataFrame()
    
    try:
        df = _calc_balance(df_settlement)
        df = df[df['_잔액'] > 0].copy()
        
        if df.empty:
            return pd.DataFrame()
        
        result_cols = {'업체': col_client}
        if col_event: result_cols['현장명'] = col_event
        if col_date: result_cols['파견일자'] = col_date
        if col_amount: result_cols['청구금액'] = col_amount
        if col_paid: result_cols['받은금액'] = col_paid
        result_cols['미수금액'] = '_잔액'
        if col_progress: result_cols['입금상태'] = col_progress
        
        valid_cols = {k: v for k, v in result_cols.items() if v in df.columns}
        res = df[list(valid_cols.values())].copy()
        res.columns = list(valid_cols.keys())
        
        # 숫자 변환
        for nc in ['청구금액', '받은금액', '미수금액']:
            if nc in res.columns:
                res[nc] = res[nc].apply(safe_int)
        
        return res.sort_values('미수금액', ascending=False).reset_index(drop=True)
    except Exception as e:
        print(f"get_unpaid_detail error: {e}")
        return pd.DataFrame()


def get_unpaid_by_company(df_settlement):
    """업체별 미수금 집계 (그룹핑)"""
    if df_settlement.empty:
        return pd.DataFrame()
    
    col_client = find_col(df_settlement, ["업체", "업체명"])
    col_amount = find_col(df_settlement, ["청구금액", "공급가액"])
    col_paid = find_col(df_settlement, ["받은금액"])
    
    if not col_client:
        return pd.DataFrame()
    
    try:
        df = _calc_balance(df_settlement)
        df['_청구'] = df[col_amount].apply(safe_int) if col_amount else 0
        df['_입금'] = df[col_paid].apply(safe_int) if col_paid else 0
        
        df = df[df['_잔액'] > 0]
        if df.empty:
            return pd.DataFrame()
        
        grouped = df.groupby(df[col_client].astype(str).str.strip()).agg(
            건수=('_잔액', 'count'),
            총청구액=('_청구', 'sum'),
            총입금액=('_입금', 'sum'),
            미수금액=('_잔액', 'sum'),
        ).reset_index()
        grouped.columns = ['업체', '건수', '총청구액', '총입금액', '미수금액']
        grouped = grouped.sort_values('미수금액', ascending=False).reset_index(drop=True)
        grouped['순위'] = grouped.index + 1
        grouped['수금률'] = grouped.apply(
            lambda r: round(r['총입금액'] / r['총청구액'] * 100, 1) if r['총청구액'] > 0 else 0, axis=1
        )
        return grouped[['순위', '업체', '건수', '총청구액', '총입금액', '미수금액', '수금률']]
    except Exception as e:
        print(f"get_unpaid_by_company error: {e}")
        return pd.DataFrame()


def get_unpaid_aging(df_settlement):
    """미수금 경과일 분석 (30일/60일/90일+)"""
    if df_settlement.empty:
        return {'30일이내': 0, '30~60일': 0, '60~90일': 0, '90일이상': 0,
                '30일이내_금액': 0, '30~60일_금액': 0, '60~90일_금액': 0, '90일이상_금액': 0}
    
    col_date = find_col(df_settlement, ["파견일자", "계약일", "날짜"])
    
    if not col_date:
        return {'30일이내': 0, '30~60일': 0, '60~90일': 0, '90일이상': 0,
                '30일이내_금액': 0, '30~60일_금액': 0, '60~90일_금액': 0, '90일이상_금액': 0}
    
    try:
        df = _calc_balance(df_settlement)
        df = df[df['_잔액'] > 0].copy()
        
        if df.empty:
            return {'30일이내': 0, '30~60일': 0, '60~90일': 0, '90일이상': 0,
                    '30일이내_금액': 0, '30~60일_금액': 0, '60~90일_금액': 0, '90일이상_금액': 0}
        
        today = datetime.now()
        
        def _calc_days(d):
            try:
                dt = pd.to_datetime(str(d).strip()[:10])
                return (today - dt).days
            except:
                return 999
        
        df['_경과일'] = df[col_date].apply(_calc_days)
        
        result = {
            '30일이내': len(df[df['_경과일'] <= 30]),
            '30~60일': len(df[(df['_경과일'] > 30) & (df['_경과일'] <= 60)]),
            '60~90일': len(df[(df['_경과일'] > 60) & (df['_경과일'] <= 90)]),
            '90일이상': len(df[df['_경과일'] > 90]),
            '30일이내_금액': int(df[df['_경과일'] <= 30]['_잔액'].sum()),
            '30~60일_금액': int(df[(df['_경과일'] > 30) & (df['_경과일'] <= 60)]['_잔액'].sum()),
            '60~90일_금액': int(df[(df['_경과일'] > 60) & (df['_경과일'] <= 90)]['_잔액'].sum()),
            '90일이상_금액': int(df[df['_경과일'] > 90]['_잔액'].sum()),
        }
        return result
    except Exception as e:
        print(f"get_unpaid_aging error: {e}")
        return {'30일이내': 0, '30~60일': 0, '60~90일': 0, '90일이상': 0,
                '30일이내_금액': 0, '30~60일_금액': 0, '60~90일_금액': 0, '90일이상_금액': 0}


def get_event_detail_for_calendar(df_inq, df_dispatch, event_title=None, event_start=None, inq_id=None):
    """캘린더 이벤트 클릭 시 상세 정보 반환"""
    if df_inq.empty:
        return {}
    
    col_id = find_col(df_inq, ["문의ID", "ID", "관리번호"])
    col_client = find_col(df_inq, ["업체명"])
    col_event = find_col(df_inq, ["행사명"])
    col_date = find_col(df_inq, ["행사시작일", "시작일", "행사일시", "일시"])
    col_date_end = find_col(df_inq, ["행사종료일", "종료일"])
    col_location = find_col(df_inq, ["장소", "현장"])
    col_status = find_col(df_inq, ["상태", "체결"])
    col_time = find_col(df_inq, ["행사시간", "시간"])
    col_headcount = find_col(df_inq, ["필요인력", "요청인원", "인원"])
    col_manager = find_col(df_inq, ["담당자"])
    col_contact = find_col(df_inq, ["연락처", "담당자연락처"])
    col_service = find_col(df_inq, ["서비스종류", "서비스"])
    col_note = find_col(df_inq, ["특이사항"])
    
    try:
        matched = pd.DataFrame()
        
        # 1. inq_id로 매칭
        if inq_id and col_id and col_id in df_inq.columns:
            matched = df_inq[df_inq[col_id].astype(str).str.strip() == str(inq_id).strip()]
        
        # 2. 제목+날짜로 매칭
        if matched.empty and event_title:
            # 제목에서 업체명/행사명 추출 (format: "업체명 (행사명) [...]")
            for idx, row in df_inq.iterrows():
                client = str(row.get(col_client, '')) if col_client else ''
                event = str(row.get(col_event, '')) if col_event else ''
                if client and client in str(event_title) and event and event in str(event_title):
                    matched = df_inq.loc[[idx]]
                    break
        
        # 3. 날짜로 매칭 (여러 건이면 첫 건)
        if matched.empty and event_start and col_date:
            start_str = str(event_start)[:10]
            for idx, row in df_inq.iterrows():
                raw = str(row.get(col_date, ''))[:10]
                if raw == start_str:
                    matched = df_inq.loc[[idx]]
                    break
        
        if matched.empty:
            return {}
        
        row = matched.iloc[0]
        
        def _safe(val):
            if pd.isna(val) or str(val).strip() in ('nan', 'None', ''):
                return ''
            return str(val).strip()
        
        # 배정 인력 상세
        evt_name = _safe(row.get(col_event)) if col_event else ''
        staff_detail = get_dispatch_detail_for_event(df_dispatch, evt_name) if evt_name else pd.DataFrame()
        
        need = safe_int(row.get(col_headcount, 0)) if col_headcount else 0
        assigned = len(staff_detail) if not staff_detail.empty else 0
        
        staff_names = []
        if not staff_detail.empty and '인력명' in staff_detail.columns:
            staff_names = staff_detail['인력명'].tolist()
        
        detail = {
            'inq_id': _safe(row.get(col_id)) if col_id else '',
            '업체명': _safe(row.get(col_client)) if col_client else '',
            '행사명': evt_name,
            '상태': _safe(row.get(col_status)) if col_status else '',
            '시작일': _safe(row.get(col_date)) if col_date else '',
            '종료일': _safe(row.get(col_date_end)) if col_date_end else '',
            '장소': _safe(row.get(col_location)) if col_location else '',
            '시간': _safe(row.get(col_time)) if col_time else '',
            '필요인원': need,
            '배정인원': assigned,
            '담당자': _safe(row.get(col_manager)) if col_manager else '',
            '연락처': _safe(row.get(col_contact)) if col_contact else '',
            '서비스': _safe(row.get(col_service)) if col_service else '',
            '특이사항': _safe(row.get(col_note)) if col_note else '',
            '배정인력': staff_names,
            '배정상세': staff_detail,
        }
        return detail
    except Exception as e:
        print(f"get_event_detail_for_calendar error: {e}")
        return {}