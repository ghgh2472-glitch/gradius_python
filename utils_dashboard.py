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
            clean_val = val.replace(',', '').replace('원', '').strip()
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
def get_monthly_trend(df_inq):
    if df_inq.empty: return pd.DataFrame()
    col_date = find_col(df_inq, ["문의날짜", "날짜"])
    col_status = find_col(df_inq, ["체결", "상태"])
    col_note = find_col(df_inq, ["특이사항", "비고"])
    
    # 필수 컬럼 없으면 빈 표 반환
    if not col_date or not col_status: return pd.DataFrame()
    
    try:
        df = df_inq.copy()
        df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
        df = df.dropna(subset=[col_date])
        df = df[df[col_status].astype(str).str.contains('체결|완료', na=False)]
        
        if col_note:
            df['parsed_sales'] = df.apply(lambda r: parse_financials(r, col_note)[0], axis=1)
        else:
            df['parsed_sales'] = 0
            
        df['Month'] = df[col_date].dt.strftime('%Y-%m')
        trend = df.groupby('Month')['parsed_sales'].sum().reset_index()
        trend.columns = ['Month', 'Sales']
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
    col_date = find_col(df_inq, ["일시", "행사일시", "날짜"])
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
def get_calendar_events(df_inq):
    if df_inq.empty: return []
    
    col_date = find_col(df_inq, ["행사일시", "일시", "투입일"])
    col_client = find_col(df_inq, ["업체명"]) or "업체명"
    col_event = find_col(df_inq, ["행사명"]) or "행사명"
    col_status = find_col(df_inq, ["체결", "상태"])
    
    if not col_date or not col_status: return []
    if col_date not in df_inq.columns: return [] # 안전장치

    events = []
    try:
        for _, row in df_inq.iterrows():
            raw_val = row[col_date]
            if pd.isna(raw_val) or str(raw_val).strip() == "": continue
                
            raw_str = str(raw_val).strip()
            start_dt = ""; end_dt = ""
            
            if "~" in raw_str:
                splits = raw_str.split("~")
                start_dt = splits[0].strip()
                end_dt = splits[1].strip()
            else:
                start_dt = raw_str[:10]
                end_dt = raw_str[:10]
            
            status = str(row.get(col_status, ''))
            color = "#3B82F6"
            if "체결" in status or "완료" in status: color = "#059669"
            elif "미정" in status or "접수" in status: color = "#D97706"
            elif "취소" in status: color = "#DC2626"
            
            events.append({
                "title": f"{row.get(col_client,'')} ({row.get(col_event,'')})",
                "start": start_dt, "end": end_dt,
                "backgroundColor": color, "borderColor": color, "allDay": True
            })
    except:
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
    col_date = find_col(df_inq, ["행사일시", "일시"])
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
        res.columns = ['업체명', '행사명', '일시', 'D-Day']
        return res
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 7. 신규 대시보드 (인력파견 + 정산 통합)
# ---------------------------------------------------------
def get_most_dispatched_staff(df_dispatch, top_n=5):
    """가장 많이 파견된 인원 순위"""
    if df_dispatch.empty: return pd.DataFrame()
    col_staff = find_col(df_dispatch, ["직원명", "인원"])
    col_position = find_col(df_dispatch, ["직급", "직책"])
    
    if not col_staff: return pd.DataFrame()
    
    try:
        df = df_dispatch.copy()
        df[col_staff] = df[col_staff].fillna('기타').astype(str)
        ranking = df[col_staff].value_counts().reset_index()
        ranking.columns = ['직원명', '파견횟수']
        ranking = ranking.head(top_n).reset_index(drop=True)
        ranking['순위'] = ranking.index + 1
        
        # 직급 정보 추가 (있으면)
        if col_position and col_position in df.columns:
            position_dict = dict(zip(df[col_staff], df[col_position]))
            ranking['직급'] = ranking['직원명'].map(position_dict).fillna('-')
        
        return ranking[['순위', '직원명', '파견횟수']]
    except:
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
    col_balance = find_col(df_settlement, ["잔액"])
    
    try:
        total_invoice = 0
        total_paid = 0
        total_balance = 0
        
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
            
            # 미수금 (잔액에서 직접)
            if col_balance:
                balance_amt = safe_int(row.get(col_balance, 0))
                total_balance += balance_amt
            else:
                # 잔액이 없으면 청구액 - 받은금액으로 계산
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
    
    col_date = find_col(df_inq, ["행사일시", "일시"])
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
    """정산 상태별 분류 (입금완료, 부분입금, 미수금)"""
    if df_settlement.empty: return {}
    
    col_status = find_col(df_settlement, ["진행상황", "상태", "입금상태"])
    
    if not col_status: return {}
    
    try:
        status_count = df_settlement[col_status].value_counts().to_dict()
        return status_count
    except Exception as e:
        print(f"Status breakdown error: {e}")
        return {}

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