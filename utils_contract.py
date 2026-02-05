# utils_contract.py
import pandas as pd
import streamlit as st

def safe_int(val):
    try:
        if pd.isna(val) or val == '': return 0
        if isinstance(val, str):
            clean = "".join(filter(lambda x: x.isdigit() or x == '.', val))
            return int(float(clean)) if clean else 0
        return int(float(val))
    except: return 0

def get_contract_summary_html(inq_row, est_df):
    """
    [V20 Header-Based Matching]
    헤더명 기반으로 데이터를 찾아 열 번호 변화에 강합니다.
    """
    target_id = str(inq_row.get('문의ID', '')).strip()
    
    match_row = pd.Series()
    has_data = False
    
    # 1. 정확한 ID 매칭 (문의ID 컬럼 기반)
    if not est_df.empty and '문의ID' in est_df.columns:
        mask = est_df['문의ID'].astype(str).str.strip() == target_id
        if mask.any():
            match_row = est_df[mask].iloc[0]
            has_data = True
    
    # 2. 헤더명으로 데이터 추출 (안전한 방식)
    supply = 0
    cost = 0
    total = 0
    profit = 0
    margin = "0%"
    
    if has_data:
        # DataFrame 행 접근 시 값이 없으면 0 또는 기본값 반환
        try:
            supply = safe_int(match_row.get('공급가액', 0))
        except:
            supply = 0
        try:
            cost = safe_int(match_row.get('매입원가', 0))
        except:
            cost = 0
        try:
            total = safe_int(match_row.get('합계금액', 0))
        except:
            total = 0
        try:
            profit = safe_int(match_row.get('예상수익', 0))
        except:
            profit = 0
        # 수익률 또는 수익율 컬럼 확인
        margin_val = None
        if '수익률' in match_row.index:
            margin_val = match_row.get('수익률', '0%')
        elif '수익율' in match_row.index:
            margin_val = match_row.get('수익율', '0%')
        margin = str(margin_val) if margin_val else '0%'

    status_color = "#1e40af" if has_data else "#dc2626"
    status_msg = f"✅ 데이터 연동됨" if has_data else f"❌ 데이터 미검출 (ID:{target_id})"
    
    # 수익률 색상 (음수면 빨강, 양수면 초록)
    profit_color = "#dc2626" if profit < 0 else "#059669" if profit > 0 else "#64748b"

    return f"""
    <div style="background:white; border-radius:12px; border:2px solid {status_color}; font-family:'Malgun Gothic'; box-shadow:0 4px 16px rgba(0,0,0,0.1); overflow:hidden;">
        <div style="background:linear-gradient(135deg, {status_color}15 0%, {status_color}05 100%); padding:16px; border-bottom:2px solid {status_color}; display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="font-size:12px; color:{status_color}; font-weight:bold; text-transform:uppercase;">📋 계약 미리보기</span>
                <div style="font-size:20px; font-weight:900; color:#0f172a; margin-top:4px;">{inq_row.get('행사명', '제목없음')}</div>
                <div style="font-size:13px; color:#64748b; margin-top:4px;">문의ID: <b>{target_id}</b></div>
            </div>
            <span style="font-size:13px; color:{status_color}; font-weight:bold; background:white; padding:8px 12px; border-radius:6px; border:1px solid {status_color};">{status_msg}</span>
        </div>
        <div style="padding:20px;">
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:16px;">
                <div style="background:#f0f9ff; padding:14px; border-radius:8px; border-left:4px solid #3b82f6;">
                    <div style="font-size:12px; color:#1e40af; font-weight:bold; text-transform:uppercase;">💰 공급가액</div>
                    <div style="font-size:20px; font-weight:900; color:#1e40af; margin-top:6px;">{supply:,}원</div>
                </div>
                <div style="background:#fef2f2; padding:14px; border-radius:8px; border-left:4px solid #ef4444;">
                    <div style="font-size:12px; color:#dc2626; font-weight:bold; text-transform:uppercase;">📦 매입원가</div>
                    <div style="font-size:20px; font-weight:900; color:#dc2626; margin-top:6px;">{cost:,}원</div>
                </div>
            </div>
            
            <div style="background:linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%); padding:16px; border-radius:10px; color:white; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:13px; font-weight:bold; text-transform:uppercase; opacity:0.9;">🎯 최종 합계</span>
                    <span style="font-size:28px; font-weight:900;">{total:,}원</span>
                </div>
            </div>
            
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                <div style="background:#f0fdf4; padding:12px; border-radius:8px; border-left:4px solid {profit_color}; text-align:center;">
                    <div style="font-size:12px; color:#64748b; font-weight:bold;">예상 수익</div>
                    <div style="font-size:18px; font-weight:900; color:{profit_color}; margin-top:4px;">{profit:,}원</div>
                </div>
                <div style="background:#fef3c7; padding:12px; border-radius:8px; border-left:4px solid #f59e0b; text-align:center;">
                    <div style="font-size:12px; color:#64748b; font-weight:bold;">수익률</div>
                    <div style="font-size:18px; font-weight:900; color:#f59e0b; margin-top:4px;">{margin}</div>
                </div>
            </div>
        </div>
    </div>
    """.replace('\n', '').strip()

def validate_contract_ready(biz_num, biz_ceo, is_sent):
    errs = []
    if not biz_num or len(biz_num) < 5: errs.append("사업자번호를 정확히 입력하세요.")
    if not biz_ceo: errs.append("대표자 성명을 입력하세요.")
    if not is_sent: errs.append("계약서 발송 여부를 체크하세요.")
    return errs