# ai_helper.py — AI 헬퍼 모듈 (규칙 기반 + 통계 분석)
"""
AI 기능 모듈:
1. 매출 예측 (이동평균 기반)
2. 리스크 분석 (미수금/미배정/임박현장)
3. 인력 수요 예측
4. 고객 이탈 분석
5. 최적 견적가 추천
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from helpers import now_kst, today_kst


# ==============================================================================
# 1. AI 매출 예측
# ==============================================================================

def predict_monthly_revenue(df_settlement: pd.DataFrame, months_ahead: int = 3) -> List[Dict]:
    """이동평균 기반 월별 매출 예측
    
    Returns:
        [{"month": "2025-02", "predicted": 15000000, "confidence": "높음"}, ...]
    """
    if df_settlement.empty:
        return []
    
    try:
        # 월별 매출 집계
        df = df_settlement.copy()
        
        # 날짜 컬럼 찾기
        date_col = None
        for col in ['계약일', '작성일', '등록일']:
            if col in df.columns:
                date_col = col
                break
        
        if not date_col:
            return []
        
        df['_date'] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.dropna(subset=['_date'])
        
        if df.empty:
            return []
        
        # 공급가액 숫자 변환
        amount_col = None
        for col in ['공급가액', '합계금액', '청구금액']:
            if col in df.columns:
                amount_col = col
                break
        
        if not amount_col:
            return []
        
        df['_amount'] = pd.to_numeric(df[amount_col], errors='coerce').fillna(0)
        df['_month'] = df['_date'].dt.to_period('M')
        
        monthly = df.groupby('_month')['_amount'].sum().sort_index()
        
        if len(monthly) < 2:
            return []
        
        # 3개월 이동평균
        window = min(3, len(monthly))
        ma = monthly.rolling(window=window, min_periods=1).mean()
        last_ma = ma.iloc[-1]
        
        # 추세 계산 (최근 vs 이전)
        if len(monthly) >= 3:
            recent_avg = monthly.iloc[-2:].mean()
            older_avg = monthly.iloc[-4:-2].mean() if len(monthly) >= 4 else monthly.iloc[0]
            trend = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
        else:
            trend = 0
        
        # 예측
        predictions = []
        last_period = monthly.index[-1]
        
        for i in range(1, months_ahead + 1):
            future_period = last_period + i
            predicted = last_ma * (1 + trend * 0.5)  # 추세 50% 반영
            predicted = max(0, predicted)
            
            # 신뢰도
            if len(monthly) >= 6:
                confidence = "높음"
            elif len(monthly) >= 3:
                confidence = "보통"
            else:
                confidence = "낮음"
            
            predictions.append({
                "month": str(future_period),
                "predicted": int(predicted),
                "confidence": confidence,
                "trend": f"{'+' if trend > 0 else ''}{trend*100:.1f}%"
            })
        
        return predictions
    except Exception as e:
        print(f"매출 예측 오류: {e}")
        return []


# ==============================================================================
# 2. 리스크 분석
# ==============================================================================

def analyze_risks(df_inq: pd.DataFrame, df_dispatch: pd.DataFrame, 
                  df_settlement: pd.DataFrame) -> List[Dict]:
    """사업 리스크 종합 분석
    
    Returns:
        [{"level": "높음", "type": "미수금", "message": "...", "action": "..."}, ...]
    """
    risks = []
    
    # 1. 미수금 리스크
    if not df_settlement.empty:
        for col in ['잔액', '미수금액']:
            if col in df_settlement.columns:
                unpaid = pd.to_numeric(df_settlement[col], errors='coerce').fillna(0)
                total_unpaid = unpaid.sum()
                if total_unpaid > 0:
                    unpaid_count = (unpaid > 0).sum()
                    level = "높음" if total_unpaid > 5000000 else "보통" if total_unpaid > 1000000 else "낮음"
                    risks.append({
                        "level": level,
                        "type": "💸 미수금",
                        "message": f"미수금 {unpaid_count}건, 총 ₩{int(total_unpaid):,}",
                        "action": "미수금 업체에 입금 독촉 필요"
                    })
                break
    
    # 2. 인력 미배정 리스크
    if not df_inq.empty:
        status_col = None
        for col in ['상태', '체결']:
            if col in df_inq.columns:
                status_col = col
                break
        
        if status_col:
            confirmed = df_inq[df_inq[status_col].astype(str).str.strip().isin(['체결'])]
            if not confirmed.empty:
                for _, row in confirmed.iterrows():
                    event_name = str(row.get('행사명', ''))
                    date_str = str(row.get('행사시작일', row.get('일시', '')))
                    
                    # D-7 이내 체결건 중 배정 안 된 건
                    try:
                        event_date = pd.to_datetime(date_str)
                        d_day = (event_date - now_kst()).days
                        if 0 <= d_day <= 7:
                            # 배정 인원 확인
                            assigned = 0
                            if not df_dispatch.empty:
                                evt_col = None
                                for c in ['행사명']:
                                    if c in df_dispatch.columns:
                                        evt_col = c
                                        break
                                if evt_col:
                                    assigned = len(df_dispatch[df_dispatch[evt_col].astype(str).str.strip() == event_name.strip()])
                            
                            needed = 0
                            for n_col in ['필요인력', '인원']:
                                if n_col in row.index:
                                    try:
                                        needed = int(float(row[n_col]))
                                    except:
                                        pass
                                    break
                            
                            if needed > 0 and assigned < needed:
                                risks.append({
                                    "level": "높음" if d_day <= 3 else "보통",
                                    "type": "👥 인력부족",
                                    "message": f"D-{d_day} {event_name}: {assigned}/{needed}명 배정",
                                    "action": f"추가 {needed - assigned}명 긴급 배정 필요"
                                })
                    except:
                        pass
    
    # 3. 견적 미진행 리스크
    if not df_inq.empty and status_col:
        inquiry_only = df_inq[df_inq[status_col].astype(str).str.strip() == '접수']
        old_inquiries = []
        for _, row in inquiry_only.iterrows():
            date_str = str(row.get('작성일', row.get('문의날짜', '')))
            try:
                inq_date = pd.to_datetime(date_str)
                days_old = (now_kst() - inq_date).days
                if days_old > 7:
                    old_inquiries.append(str(row.get('업체명', '미정')))
            except:
                pass
        
        if old_inquiries:
            risks.append({
                "level": "보통",
                "type": "📋 영업지연",
                "message": f"7일 이상 견적 미진행: {len(old_inquiries)}건",
                "action": f"업체: {', '.join(old_inquiries[:3])}{'...' if len(old_inquiries) > 3 else ''}"
            })
    
    # 리스크 정렬 (높음 → 보통 → 낮음)
    level_order = {"높음": 0, "보통": 1, "낮음": 2}
    risks.sort(key=lambda x: level_order.get(x['level'], 9))
    
    return risks


# ==============================================================================
# 3. 최적 견적가 추천
# ==============================================================================

def suggest_estimate_price(df_estimate: pd.DataFrame, event_type: str = None,
                           num_staff: int = 0, num_days: int = 1) -> Dict:
    """과거 견적 데이터 기반 최적 견적가 추천
    
    Returns:
        {"recommended_supply": int, "min_price": int, "max_price": int, 
         "avg_margin": float, "similar_count": int}
    """
    result = {
        "recommended_supply": 0,
        "min_price": 0,
        "max_price": 0,
        "avg_margin": 0.0,
        "similar_count": 0,
        "message": ""
    }
    
    if df_estimate.empty or num_staff <= 0:
        result["message"] = "견적 데이터가 부족합니다."
        return result
    
    try:
        df = df_estimate.copy()
        
        # 숫자 변환
        for col in ['공급가액', '매입원가', '예상수익']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 유효한 견적만
        if '공급가액' in df.columns:
            df = df[df['공급가액'] > 0]
        
        if df.empty:
            result["message"] = "유효한 견적 데이터가 없습니다."
            return result
        
        # 인원당 단가 계산
        if '필요인력' in df.columns and '공급가액' in df.columns:
            df['_per_person'] = df['공급가액'] / pd.to_numeric(df['필요인력'], errors='coerce').replace(0, np.nan)
            df = df.dropna(subset=['_per_person'])
            
            if not df.empty:
                avg_per_person = df['_per_person'].median()
                recommended = int(avg_per_person * num_staff * num_days)
                
                result["recommended_supply"] = recommended
                result["min_price"] = int(df['_per_person'].quantile(0.25) * num_staff * num_days)
                result["max_price"] = int(df['_per_person'].quantile(0.75) * num_staff * num_days)
                result["similar_count"] = len(df)
                
                # 마진율
                if '매입원가' in df.columns:
                    margins = (df['공급가액'] - df['매입원가']) / df['공급가액'] * 100
                    result["avg_margin"] = round(margins.median(), 1)
                
                result["message"] = f"과거 {len(df)}건 기반 추천 (인당 평균 ₩{int(avg_per_person):,})"
        else:
            # 인원 데이터 없으면 전체 평균
            avg_supply = df['공급가액'].median()
            result["recommended_supply"] = int(avg_supply)
            result["min_price"] = int(df['공급가액'].quantile(0.25))
            result["max_price"] = int(df['공급가액'].quantile(0.75))
            result["similar_count"] = len(df)
            result["message"] = f"과거 {len(df)}건 기반 평균 추천"
        
        return result
    except Exception as e:
        result["message"] = f"분석 오류: {e}"
        return result


# ==============================================================================
# 4. 고객 이탈 분석 (재계약률)
# ==============================================================================

def analyze_customer_retention(df_inq: pd.DataFrame) -> Dict:
    """고객 재계약률 분석
    
    Returns:
        {"retention_rate": float, "top_loyal": [...], "at_risk": [...]}
    """
    result = {"retention_rate": 0, "top_loyal": [], "at_risk": [], "total_customers": 0}
    
    if df_inq.empty:
        return result
    
    try:
        company_col = None
        for col in ['업체명', '업체', '고객사']:
            if col in df_inq.columns:
                company_col = col
                break
        
        if not company_col:
            return result
        
        # 업체별 문의 횟수
        company_counts = df_inq[company_col].astype(str).value_counts()
        result["total_customers"] = len(company_counts)
        
        # 재계약 고객 (2회 이상)
        repeat_customers = company_counts[company_counts >= 2]
        if len(company_counts) > 0:
            result["retention_rate"] = round(len(repeat_customers) / len(company_counts) * 100, 1)
        
        # 충성 고객 Top 5
        result["top_loyal"] = [
            {"company": name, "count": int(cnt)}
            for name, cnt in repeat_customers.head(5).items()
        ]
        
        # 이탈 위험 고객 (1회만 + 3개월 이상 경과)
        one_time = company_counts[company_counts == 1].index.tolist()
        date_col = None
        for col in ['작성일', '문의날짜', '등록일']:
            if col in df_inq.columns:
                date_col = col
                break
        
        if date_col and one_time:
            for company in one_time[:10]:
                rows = df_inq[df_inq[company_col].astype(str) == company]
                if not rows.empty:
                    try:
                        last_date = pd.to_datetime(rows[date_col].iloc[-1])
                        days_since = (now_kst() - last_date).days
                        if days_since > 90:
                            result["at_risk"].append({
                                "company": company,
                                "days_since": days_since,
                            })
                    except:
                        pass
        
        return result
    except Exception as e:
        print(f"고객 분석 오류: {e}")
        return result


# ==============================================================================
# 5. AI 종합 대시보드 인사이트
# ==============================================================================

def generate_executive_summary(df_inq: pd.DataFrame, df_dispatch: pd.DataFrame,
                                df_settlement: pd.DataFrame) -> str:
    """AI 경영 종합 요약 생성"""
    lines = []
    
    # 1. 현재 파이프라인 상태
    if not df_inq.empty:
        status_col = None
        for col in ['상태', '체결']:
            if col in df_inq.columns:
                status_col = col
                break
        
        if status_col:
            statuses = df_inq[status_col].astype(str).str.strip().value_counts()
            total = len(df_inq)
            confirmed = sum(statuses.get(s, 0) for s in ['체결', '배정완료', '진행중', '완료', '정산완료'])
            conv_rate = (confirmed / total * 100) if total > 0 else 0
            lines.append(f"📊 전환율 {conv_rate:.0f}% (전체 {total}건 중 {confirmed}건 체결)")
    
    # 2. 매출/수금 현황
    if not df_settlement.empty:
        for supply_col in ['공급가액', '합계금액']:
            if supply_col in df_settlement.columns:
                total_supply = pd.to_numeric(df_settlement[supply_col], errors='coerce').fillna(0).sum()
                lines.append(f"💰 총 청구액: ₩{int(total_supply):,}")
                break
        
        for paid_col in ['받은금액']:
            if paid_col in df_settlement.columns:
                total_paid = pd.to_numeric(df_settlement[paid_col], errors='coerce').fillna(0).sum()
                lines.append(f"✅ 수금액: ₩{int(total_paid):,}")
                break
    
    # 3. 리스크 요약
    risks = analyze_risks(df_inq, df_dispatch, df_settlement)
    high_risks = [r for r in risks if r['level'] == '높음']
    if high_risks:
        lines.append(f"🚨 긴급 리스크 {len(high_risks)}건: {high_risks[0]['message']}")
    else:
        lines.append("✅ 긴급 리스크 없음")
    
    # 4. 인력 현황
    if not df_dispatch.empty:
        lines.append(f"👥 현재 배정 인력: {len(df_dispatch)}명")
    
    return " | ".join(lines) if lines else "데이터를 분석 중입니다."


# ==============================================================================
# 6. 인력 수요 예측
# ==============================================================================

def predict_staff_demand(df_inq: pd.DataFrame, weeks_ahead: int = 4) -> List[Dict]:
    """향후 인력 수요 예측
    
    Returns:
        [{"week": "1/6~1/12", "estimated_staff": 15, "events": 3}, ...]
    """
    predictions = []
    
    if df_inq.empty:
        return predictions
    
    try:
        status_col = None
        for col in ['상태', '체결']:
            if col in df_inq.columns:
                status_col = col
                break
        
        if not status_col:
            return predictions
        
        # 체결 이후 건만
        confirmed = df_inq[df_inq[status_col].astype(str).str.strip().isin(
            ['체결', '배정완료', '진행중'])]
        
        date_col = None
        for col in ['행사시작일', '시작일', '일시']:
            if col in confirmed.columns:
                date_col = col
                break
        
        if not date_col:
            return predictions
        
        confirmed = confirmed.copy()
        confirmed['_date'] = pd.to_datetime(confirmed[date_col], errors='coerce')
        confirmed = confirmed.dropna(subset=['_date'])
        
        today = now_kst()
        
        for w in range(weeks_ahead):
            week_start = today + timedelta(weeks=w)
            week_end = week_start + timedelta(days=6)
            
            week_events = confirmed[
                (confirmed['_date'] >= week_start) & (confirmed['_date'] <= week_end)
            ]
            
            # 필요 인원 합계
            total_staff = 0
            for _, row in week_events.iterrows():
                for n_col in ['필요인력', '인원']:
                    if n_col in row.index:
                        try:
                            total_staff += int(float(row[n_col]))
                        except:
                            pass
                        break
            
            predictions.append({
                "week": f"{week_start.strftime('%m/%d')}~{week_end.strftime('%m/%d')}",
                "estimated_staff": total_staff,
                "events": len(week_events),
            })
        
        return predictions
    except Exception as e:
        print(f"수요 예측 오류: {e}")
        return predictions
