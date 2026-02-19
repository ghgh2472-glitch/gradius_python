# utils_contract.py  v2 — 카드형 계약 승인 UI
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


def _safe_str(row, key, fallback=''):
    v = row.get(key, fallback)
    if pd.isna(v): return ''
    return str(v).strip()


def get_contract_summary_html(inq_row, est_df):
    """카드형 계약 미리보기 — 문의 상세 + 금액 요약"""
    target_id = str(inq_row.get('문의ID', '')).strip()

    # ── 견적 데이터 매칭 ──
    match_row = pd.Series()
    has_data = False
    if not est_df.empty and '문의ID' in est_df.columns:
        mask = est_df['문의ID'].astype(str).str.strip() == target_id
        if mask.any():
            match_row = est_df[mask].iloc[0]
            has_data = True

    supply = safe_int(match_row.get('공급가액', 0)) if has_data else 0
    cost = safe_int(match_row.get('매입원가', 0)) if has_data else 0
    total = safe_int(match_row.get('합계금액', 0)) if has_data else 0
    vat = safe_int(match_row.get('부가세', 0)) if has_data else 0
    extra = safe_int(match_row.get('부대비용', 0)) if has_data else 0
    profit = supply - cost - extra
    margin_val = match_row.get('수익률', match_row.get('수익율', '')) if has_data else ''
    margin = str(margin_val) if margin_val and not pd.isna(margin_val) else (f"{profit/supply*100:.1f}%" if supply > 0 else "0%")

    status_color = "#1e40af" if has_data else "#dc2626"
    status_msg = "✅ 견적 연동됨" if has_data else f"❌ 견적 미검출 (ID:{target_id})"
    profit_color = "#dc2626" if profit < 0 else "#059669" if profit > 0 else "#64748b"

    # ── 문의 상세 정보 ──
    client = _safe_str(inq_row, '업체명')
    event = _safe_str(inq_row, '행사명')
    site = _safe_str(inq_row, '장소', _safe_str(inq_row, '행사장소'))
    manager = _safe_str(inq_row, '담당자')
    contact = _safe_str(inq_row, '연락처', _safe_str(inq_row, '담당자연락처'))
    sdate = _safe_str(inq_row, '행사시작일', _safe_str(inq_row, '시작일'))
    edate = _safe_str(inq_row, '행사종료일', _safe_str(inq_row, '종료일'))
    htime = _safe_str(inq_row, '행사시간', _safe_str(inq_row, '시간'))
    svc = _safe_str(inq_row, '서비스종류')
    people = _safe_str(inq_row, '필요인력', _safe_str(inq_row, '요청인원'))
    pay = _safe_str(inq_row, '페이')
    special = _safe_str(inq_row, '특이사항')
    note = _safe_str(inq_row, '비고')
    counsel = _safe_str(inq_row, '상담내용및 고객성향', _safe_str(inq_row, '상담내용'))
    relation = _safe_str(inq_row, '관계')
    category = _safe_str(inq_row, '구분')
    date_range = f"{sdate} ~ {edate}" if sdate and edate else sdate

    def _info_row(icon, label, value):
        if not value: return ''
        return f'<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;"><span style="min-width:22px;">{icon}</span><span style="color:#64748b;min-width:65px;font-size:12px;font-weight:600;">{label}</span><span style="font-size:13px;color:#1e293b;">{value}</span></div>'

    info_rows = ''.join(filter(None, [
        _info_row('🏢', '업체명', client),
        _info_row('🎪', '행사명', event),
        _info_row('📍', '장소', site),
        _info_row('📅', '기간', date_range),
        _info_row('⏰', '시간', htime),
        _info_row('👤', '담당자', f"{manager} ({contact})" if contact else manager),
        _info_row('🔧', '서비스', svc),
        _info_row('👥', '인력', people),
        _info_row('💵', '페이', pay),
        _info_row('🏷️', '구분', category),
        _info_row('🤝', '관계', relation),
    ]))

    # 특이사항 / 메모 섹션
    memo_section = ''
    
    # 복장/식사/주차/특이사항 (견적 메타데이터에서 가져오기)
    est_dress = str(match_row.get('복장', '')).strip() if has_data else ''
    est_meal = str(match_row.get('식사', '')).strip() if has_data else ''
    est_parking = str(match_row.get('주차', '')).strip() if has_data else ''
    est_note_raw = str(match_row.get('특이사항', '')).strip() if has_data else ''
    
    # 견적 메타 없으면 → 문의 개별 컬럼 → 문의 특이사항 regex fallback
    if not est_dress or est_dress in ('nan', 'None'):
        est_dress = _safe_str(inq_row, '복장')
    if not est_meal or est_meal in ('nan', 'None'):
        est_meal = _safe_str(inq_row, '식사')
    if not est_parking or est_parking in ('nan', 'None'):
        est_parking = _safe_str(inq_row, '주차')
    
    # 여전히 없으면 기존 데이터 호환: 특이사항에서 regex 파싱
    if not est_dress or est_dress in ('nan', 'None'):
        import re as _re
        _dm = _re.search(r'\[복장:([^\]]+)\]', special)
        est_dress = _dm.group(1).strip() if _dm else ''
    if not est_meal or est_meal in ('nan', 'None'):
        import re as _re
        _mm = _re.search(r'\[식사:([^\]]+)\]', special)
        est_meal = _mm.group(1).strip() if _mm else ''
    if not est_parking or est_parking in ('nan', 'None'):
        import re as _re
        _pm = _re.search(r'\[주차:([^\]]+)\]', special)
        est_parking = _pm.group(1).strip() if _pm else ''
    if est_note_raw in ('nan', 'None'): est_note_raw = ''
    
    if est_dress or est_meal or est_parking:
        _cond_items = []
        if est_dress: _cond_items.append(f"👔 복장: <b>{est_dress}</b>")
        if est_meal: _cond_items.append(f"🍽️ 식사: <b>{est_meal}</b>")
        if est_parking: _cond_items.append(f"🅿️ 주차: <b>{est_parking}</b>")
        memo_section += f'<div style="background:#EFF6FF;padding:10px 14px;border-radius:6px;margin-top:10px;border-left:4px solid #3B82F6;"><div style="font-size:11px;font-weight:bold;color:#1E40AF;">📋 현장 조건</div><div style="font-size:13px;color:#1E3A5F;margin-top:4px;display:flex;gap:20px;">{"&nbsp;&nbsp;|&nbsp;&nbsp;".join(_cond_items)}</div></div>'
    
    if est_note_raw:
        memo_section += f'<div style="background:#F0FDF4;padding:10px 14px;border-radius:6px;margin-top:8px;border-left:4px solid #10B981;"><div style="font-size:11px;font-weight:bold;color:#065F46;">📝 견적 특이사항</div><div style="font-size:13px;color:#064E3B;margin-top:4px;">{est_note_raw}</div></div>'
    
    if special:
        memo_section += f'<div style="background:#fef3c7;padding:10px 14px;border-radius:6px;margin-top:10px;border-left:4px solid #f59e0b;"><div style="font-size:11px;font-weight:bold;color:#92400e;">⚠️ 특이사항</div><div style="font-size:13px;color:#78350f;margin-top:4px;">{special}</div></div>'
    if note:
        memo_section += f'<div style="background:#ede9fe;padding:10px 14px;border-radius:6px;margin-top:8px;border-left:4px solid #7c3aed;"><div style="font-size:11px;font-weight:bold;color:#5b21b6;">📝 비고</div><div style="font-size:13px;color:#4c1d95;margin-top:4px;">{note}</div></div>'
    if counsel:
        memo_section += f'<div style="background:#ecfdf5;padding:10px 14px;border-radius:6px;margin-top:8px;border-left:4px solid #10b981;"><div style="font-size:11px;font-weight:bold;color:#065f46;">💬 상담 내용 / 고객성향</div><div style="font-size:13px;color:#064e3b;margin-top:4px;">{counsel}</div></div>'

    return f"""
    <div style="font-family:'Malgun Gothic',sans-serif;">
        <!-- 헤더 -->
        <div style="background:linear-gradient(135deg,#1e40af,#3b82f6);padding:18px 20px;border-radius:12px 12px 0 0;color:white;display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="font-size:11px;opacity:.8;text-transform:uppercase;letter-spacing:1px;">계약 승인 미리보기</div>
                <div style="font-size:22px;font-weight:900;margin-top:4px;">{event or '제목없음'}</div>
                <div style="font-size:12px;opacity:.75;margin-top:4px;">{client} | ID: {target_id}</div>
            </div>
            <span style="background:rgba(255,255,255,.2);padding:6px 12px;border-radius:20px;font-size:12px;font-weight:bold;">{status_msg}</span>
        </div>

        <!-- 문의 상세 카드 -->
        <div style="background:white;padding:18px 20px;border:1px solid #e2e8f0;border-top:none;">
            <div style="font-size:13px;font-weight:bold;color:#334155;margin-bottom:8px;">📋 문의 상세</div>
            {info_rows}
            {memo_section}
        </div>

        <!-- 금액 카드 -->
        <div style="background:#f8fafc;padding:18px 20px;border:1px solid #e2e8f0;border-top:none;">
            <div style="font-size:13px;font-weight:bold;color:#334155;margin-bottom:12px;">💰 금액 요약</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                <div style="background:white;padding:14px;border-radius:8px;border:1px solid #dbeafe;text-align:center;">
                    <div style="font-size:11px;color:#3b82f6;font-weight:bold;">공급가액</div>
                    <div style="font-size:20px;font-weight:900;color:#1e40af;margin-top:4px;">{supply:,}원</div>
                </div>
                <div style="background:white;padding:14px;border-radius:8px;border:1px solid #fecaca;text-align:center;">
                    <div style="font-size:11px;color:#ef4444;font-weight:bold;">지출금액</div>
                    <div style="font-size:20px;font-weight:900;color:#dc2626;margin-top:4px;">{cost:,}원</div>
                </div>
            </div>
            <!-- 합계 대형 배너 -->
            <div style="background:linear-gradient(135deg,#1e40af,#1e3a8a);padding:16px;border-radius:10px;color:white;margin-top:12px;display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-size:12px;opacity:.85;">🎯 최종 합계</div>
                    <div style="font-size:11px;opacity:.7;margin-top:2px;">부가세(VAT) {vat:,}원 포함</div>
                </div>
                <div style="font-size:28px;font-weight:900;">{total:,}원</div>
            </div>
            <!-- 수익 -->
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:10px;">
                <div style="background:white;padding:10px;border-radius:8px;border:1px solid #d1fae5;text-align:center;">
                    <div style="font-size:11px;color:#64748b;">예상 수익</div>
                    <div style="font-size:16px;font-weight:900;color:{profit_color};margin-top:2px;">{profit:,}원</div>
                </div>
                <div style="background:white;padding:10px;border-radius:8px;border:1px solid #fef3c7;text-align:center;">
                    <div style="font-size:11px;color:#64748b;">수익률</div>
                    <div style="font-size:16px;font-weight:900;color:#f59e0b;margin-top:2px;">{margin}</div>
                </div>
                <div style="background:white;padding:10px;border-radius:8px;border:1px solid #e2e8f0;text-align:center;">
                    <div style="font-size:11px;color:#64748b;">부대비용</div>
                    <div style="font-size:16px;font-weight:900;color:#64748b;margin-top:2px;">{extra:,}원</div>
                </div>
            </div>
        </div>

        <!-- 하단 -->
        <div style="background:#f1f5f9;padding:10px 20px;border-radius:0 0 12px 12px;border:1px solid #e2e8f0;border-top:none;text-align:right;">
            <span style="font-size:11px;color:#94a3b8;">위 내용을 검토한 후 아래에서 계약을 확정하세요.</span>
        </div>
    </div>
    """.replace('\n', '').strip()


def validate_contract_ready(biz_num, biz_ceo, is_sent):
    errs = []
    if not biz_num or len(biz_num) < 5: errs.append("사업자번호를 정확히 입력하세요.")
    if not biz_ceo: errs.append("대표자 성명을 입력하세요.")
    if not is_sent: errs.append("계약서 발송 여부를 체크하세요.")
    return errs