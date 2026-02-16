# utils_estimate.py
import pandas as pd
import re
from datetime import datetime, timedelta, time

# ==============================================================================
# 1. EstimateBrain (기존 유지)
# ==============================================================================
class EstimateBrain:
    def __init__(self, df_roles=None, df_guides=None, df_factors=None, df_clients=None):
        self.df_roles = df_roles if df_roles is not None else pd.DataFrame()
        self.df_guides = df_guides if df_guides is not None else pd.DataFrame()
        self.df_factors = df_factors if df_factors is not None else pd.DataFrame()
        self.df_clients = df_clients if df_clients is not None else pd.DataFrame()

    def get_role_info(self, role_name_kr):
        info = {"role_id": None, "base_price": 0, "cost_price": 0, "leader_add": 0}
        if self.df_roles.empty or not role_name_kr or role_name_kr == "선택": return info
        try:
            row = self.df_roles[self.df_roles['직군명'] == role_name_kr]
            if not row.empty:
                r = row.iloc[0]
                info['role_id'] = r.get('role_id')
                info['base_price'] = safe_int(r.get('기본단가', 0))
                info['cost_price'] = safe_int(r.get('지급단가', 0))
                info['leader_add'] = safe_int(r.get('팀장가산', 10000)) 
        except: pass
        return info

    def get_factors(self, role_id):
        options = []
        if not role_id or self.df_factors.empty: return options
        try:
            rows = self.df_factors[self.df_factors['role_id'].astype(str) == str(role_id)]
            for _, r in rows.iterrows():
                options.append({
                    "factor_id": r.get('factor_id'),
                    "name": r.get('체크항목'), "desc": r.get('상세설명'),
                    "price": safe_int(r.get('추가금액', 0)), "cost_add": safe_int(r.get('지급추가금', 0))
                })
        except: pass
        return options

    def get_analysis(self, role_id):
        result = {"guide": [], "market": "-", "comp": "-", "my_best": "-"}
        if not role_id or self.df_guides.empty: return result
        try:
            row = self.df_guides[self.df_guides['role_id'].astype(str) == str(role_id)]
            if not row.empty:
                r = row.iloc[0]
                raw = str(r.get('상담포인트', ''))
                if raw: result['guide'] = [l.strip() for l in raw.split('\n') if l.strip()]
                result['market'] = r.get('시장 평균가', '-')
                result['comp'] = r.get('타업체 견적가 케이스', '-')
                result['my_best'] = r.get('기존 체결가 케이스', '-')
        except: pass
        return result

    def get_client_info_from_db(self, client_name):
        info = {}
        if self.df_clients.empty or not client_name: return info
        try:
            row = self.df_clients[self.df_clients['업체명'] == client_name]
            if not row.empty:
                r = row.iloc[0]
                info['biz_num'] = r.get('사업자등록번호', '')
                info['ceo'] = r.get('대표자명', '')
        except: pass
        return info

# ==============================================================================
# 2. 유틸리티
# ==============================================================================
def safe_int(val):
    try:
        if isinstance(val, str):
            clean = val.replace(',', '').replace('원', '').strip()
            if not clean: return 0
            return int(float(clean))
        return int(float(val))
    except: return 0

def smart_parse_date(date_str):
    """날짜 문자열 파싱. '2026-02-20~2026-02-22' 또는 단일 날짜 지원"""
    txt = str(date_str).strip()
    now = datetime.now().date()
    if not txt: return (now, now, 1)
    
    y = datetime.now().year
    def to_d(s):
        s = s.strip().replace('.', '-').replace('/', '-')
        if not s: return None
        # YYYY-MM-DD 형식
        if len(s) >= 8 and s.count('-') == 2:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        # MM-DD 형식 (연도 없음)
        if s.count('-') == 1:
            return datetime.strptime(f"{y}-{s}", "%Y-%m-%d").date()
        return None
    
    try:
        # 1) ~ 구분자 우선 (YYYY-MM-DD~YYYY-MM-DD)
        if '~' in txt:
            parts = txt.split('~', 1)
            dt1 = to_d(parts[0])
            dt2 = to_d(parts[1]) if len(parts) > 1 else dt1
        else:
            # 단일 날짜
            dt1 = to_d(txt)
            dt2 = dt1
        
        if dt1 is None: return (now, now, 1)
        if dt2 is None: dt2 = dt1
        return (dt1, dt2, max(1, (dt2-dt1).days+1))
    except: return (now, now, 1)

def smart_parse_time(time_str):
    txt = str(time_str).strip()
    times = re.findall(r'(\d{1,2}:\d{2})', txt)
    t1, t2, dur = time(9,0), time(18,0), 9.0
    try:
        if len(times) >= 2:
            dt1 = datetime.strptime(times[0], "%H:%M"); dt2 = datetime.strptime(times[1], "%H:%M")
            t1, t2 = dt1.time(), dt2.time()
            if dt2 < dt1: dt2 += timedelta(days=1)
            dur = round((dt2 - dt1).total_seconds()/3600, 1)
        elif len(times) == 1: t1 = datetime.strptime(times[0], "%H:%M").time()
        return (t1, t2, dur)
    except: return (t1, t2, dur)

def num_to_hangul(num):
    try: num = int(num)
    except: return "영"
    if num == 0: return "영"
    units, digits = ["", "만", "억", "조"], ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
    res, s_num = [], str(num)[::-1]
    for i in range(0, len(s_num), 4):
        chunk, chunk_res = s_num[i:i+4], []
        for j, d in enumerate(chunk):
            n = int(d)
            if n > 0:
                u = ""
                if j==1: u="십"
                elif j==2: u="백"
                elif j==3: u="천"
                if n == 1 and j > 0: chunk_res.append(u)
                else: chunk_res.append(digits[n] + u)
        if chunk_res: res.append("".join(reversed(chunk_res)) + units[i//4])
    return "".join(reversed(res)) + "원정"

# ==============================================================================
# 3. HTML 생성 엔진 (합계표 너비 최적화)
# ==============================================================================

def get_customer_quote_html(df, client_info, supplier_info, supply_amt, vat_yn, terms_top, terms_side, footer_img_base64=None, additional_costs_df=None, additional_costs_total=0):
    total = safe_int(supply_amt)
    additional_total = safe_int(additional_costs_total)
    total_with_additional = total + additional_total
    vat = int(total_with_additional * 0.1) if vat_yn else 0
    grand_total = total_with_additional + vat
        
    rows = ""
    for _, r in df.iterrows():
        qty = safe_int(r.get('수량', 0))
        days = safe_int(r.get('일수', 1))
        price = safe_int(r.get('매출단가', 0))
        amt = safe_int(r.get('매출합계', 0))
        spec = r.get('규격', '')
        note = r.get('비고', '')

        rows += f"""
        <tr>
            <td style="text-align:left; padding-left:10px;">{r['품목']}</td>
            <td style="text-align:center; color:#555; font-size:12px;">{spec}</td>
            <td style="text-align:center;">{qty}</td>
            <td style="text-align:center;">{days}</td>
            <td style="text-align:right; padding-right:10px;">{price:,}</td>
            <td style="text-align:right; padding-right:10px;">{amt:,}</td>
            <td style="text-align:left; padding-left:5px; font-size:11px;">{note}</td>
        </tr>
        """
    
    # 부대비용 행 추가
    additional_rows = ""
    if additional_costs_df is not None and not additional_costs_df.empty:
        for _, r in additional_costs_df.iterrows():
            item = r.get('항목', '')
            cost = safe_int(r.get('금액', 0))
            note = r.get('비고', '')
            additional_rows += f"""
        <tr style="background:#fef3c7;">
            <td style="text-align:left; padding-left:10px;">[부대비용] {item}</td>
            <td colspan="4" style="text-align:center; color:#c2410c; font-size:12px;">{note}</td>
            <td style="text-align:right; padding-right:10px; font-weight:bold;">{cost:,}</td>
            <td></td>
        </tr>
        """
    
    for _ in range(max(0, 10 - len(df))): rows += "<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>"
    
    # 행 합계
    rows += f"""
    <tr style="background:#f3f4f6; font-weight:bold;">
        <td colspan="5" style="text-align:right; padding-right:10px;">소계:</td>
        <td style="text-align:right; padding-right:10px;">{total:,}</td>
        <td></td>
    </tr>
    """
    
    # 부대비용이 있으면 추가
    if additional_total > 0:
        rows += f"""
    <tr style="background:#fef3c7; font-weight:bold;">
        <td colspan="5" style="text-align:right; padding-right:10px;">부대비용 합계:</td>
        <td style="text-align:right; padding-right:10px; color:#c2410c;">{additional_total:,}</td>
        <td></td>
    </tr>
    <tr style="background:#f0f0f0; font-weight:bold;">
        <td colspan="5" style="text-align:right; padding-right:10px;">합계 (소계+부대):</td>
        <td style="text-align:right; padding-right:10px;">{total_with_additional:,}</td>
        <td></td>
    </tr>
    """
    
    rows += additional_rows

    footer_img_tag = ""
    if footer_img_base64:
        footer_img_tag = f'<div style="text-align:center; margin-top:20px;"><img src="data:image/png;base64,{footer_img_base64}" style="width:100%; max-width:800px;"></div>'

    fmt_top = terms_top.replace('\n', '<br>')
    fmt_side = terms_side.replace('\n', '<br>')

    return f"""
    <html><head><script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script><script>function saveImage(){{const e=document.getElementById("print_area");html2canvas(e,{{scale:2}}).then(c=>{{var l=document.createElement('a');l.download='견적서_{client_info["name"]}.png';l.href=c.toDataURL("image/png");l.click();}});}}</script>
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    body{{font-family:'Noto Sans KR',sans-serif;background:#525659;padding:20px;display:flex;justify-content:center;}}
    .paper{{width:210mm;min-height:297mm;background:white;padding:10mm;box-shadow:0 0 10px rgba(0,0,0,0.5);box-sizing:border-box;position:relative;}}
    .title{{text-align:center;font-size:42px;font-weight:900;letter-spacing:10px;margin-bottom:30px;border-bottom:3px solid black;padding-bottom:15px;}}
    
    .header-box {{display:flex; border:2px solid black; margin-bottom:10px; height: 160px;}}
    .h-col {{flex:1; display:flex;}}
    .h-col.right {{border-left:1px solid black;}}
    .vertical-text {{width:40px; background:#f3f4f6; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:14px; writing-mode:vertical-rl; letter-spacing:5px; border-right:1px solid #ccc; text-orientation: upright;}}
    
    .info-table {{width:100%; border-collapse:collapse; height:100%; table-layout:fixed;}}
    .info-table td {{border-bottom:1px solid #ccc; padding:0 8px; font-size:13px; vertical-align:middle; height:20%;}}
    .info-table tr:last-child td {{border-bottom:none;}}
    
    .label {{font-weight:bold; text-align:center; background:#fafafa; width:15%; border-right:1px solid #eee; color:#333; white-space:nowrap;}}
    .val {{width:35%; white-space:nowrap;}}
    .val-wide {{width:85%; white-space:nowrap;}}
    
    .total-box {{border:2px solid black; padding:12px; text-align:center; font-size:20px; font-weight:bold; margin-bottom:10px; background:#fffbeb;}}
    .total-box span {{color:#c00; text-decoration:underline; margin: 0 5px;}}
    
    .main-table {{width:100%; border-collapse:collapse; margin-bottom:10px; border-top:2px solid black;}}
    .main-table th {{background:#eee; border:1px solid #333; padding:8px 0; font-size:13px; text-align:center;}}
    .main-table td {{border:1px solid #ccc; padding:8px 5px; font-size:12px;}}
    .main-table tr:last-child td {{border-bottom:2px solid black;}}
    
    /* [레이아웃 조정] 좌측 1.2 : 우측 1 */
    .bottom-container {{display:flex; gap:15px; margin-top:5px; align-items:flex-start;}}
    .bottom-left {{flex:1.2; border:1px solid #ddd; background:#fff; padding:10px; font-size:11px; line-height:1.6; border-radius:4px;}}
    .bottom-right {{flex:1;}}
    
    .summary-table {{width:100%; border-collapse:collapse; height:100%;}}
    /* [줄바꿈 방지] nowrap 및 너비 조정 (30:35:35) */
    .summary-table td {{padding:10px; text-align:right; font-weight:bold; border:1px solid #ccc; background:#f9f9f9; font-size:14px; white-space:nowrap;}}
    
    .top-terms {{border:1px solid #ddd; background:#fff; padding:10px 15px; font-size:12px; line-height:1.6; margin-bottom:15px; border-radius:4px;}}
    
    .bank-box {{
        margin-top: 15px; padding: 12px;
        background-color: #f0fdf4; border: 2px solid #22c55e;
        border-radius: 8px; text-align: center;
        font-weight: bold; font-size: 15px; color: #14532d;
    }}
    .footer-banner {{margin-top:10px; text-align:center;}}
    .btn-save {{position:fixed; top:20px; right:20px; padding:10px 20px; background:#2563eb; color:white; border:none; border-radius:5px; cursor:pointer; font-weight:bold; z-index:999; box-shadow:0 4px 6px rgba(0,0,0,0.3);}}
    </style></head><body><button class="btn-save" onclick="saveImage()">💾 이미지 저장</button>
    <div id="print_area" class="paper"><div class="title">견 적 서</div>
    <div class="header-box">
        <div class="h-col">
            <div class="vertical-text">공급받는자</div>
            <table class="info-table">
                <tr><td class="label">상호</td><td class="val" colspan="3" style="font-weight:bold; font-size:14px;">{client_info['name']} 귀하</td></tr>
                <tr><td class="label">참조</td><td class="val" colspan="3">{client_info['ref']}</td></tr>
                <tr><td class="label">연락처</td><td class="val" colspan="3">{client_info['tel']}</td></tr>
                <tr><td class="label">주소</td><td class="val-wide" colspan="3">{client_info['addr']}</td></tr>
                <tr><td class="label">행사일시</td><td class="val-wide" colspan="3" style="color:#000;">{client_info['date_range']}</td></tr>
            </table>
        </div>
        <div class="h-col right">
            <div class="vertical-text">공급자</div>
            <table class="info-table">
                <tr><td class="label">등록번호</td><td class="val-wide" colspan="3">{supplier_info['reg_no']}</td></tr>
                <tr>
                    <td class="label">상호</td><td class="val">{supplier_info['name']}</td>
                    <td class="label" style="width:15%;">성명</td><td class="val" style="width:35%;">{supplier_info['ceo']}</td>
                </tr>
                <tr><td class="label">주소</td><td class="val-wide" colspan="3">{supplier_info['addr']}</td></tr>
                <tr><td class="label">전화</td><td class="val-wide" colspan="3">{supplier_info['tel']}</td></tr>
                <tr><td class="label">견적일</td><td class="val-wide" colspan="3">{client_info['date']}</td></tr>
            </table>
        </div>
    </div>
    
    <div class="top-terms">{fmt_top}</div>
    <div class="total-box">합계금액 : 일금 <span>{num_to_hangul(grand_total)}</span> (VAT {'포함' if vat_yn else '별도'})</div>
    
    <table class="main-table"><thead><tr><th width="20%">품명</th><th width="20%">규격/상세</th><th width="8%">수량</th><th width="8%">일수</th><th width="12%">단가</th><th width="15%">금액</th><th width="17%">비고</th></tr></thead><tbody>{rows}</tbody></table>
    
    <div class="bottom-container">
        <div class="bottom-left">{fmt_side}</div>
        <div class="bottom-right">
            <table class="summary-table">
                <tr><td width="30%" style="border:none; background:white;"></td><td width="35%">공급가액</td><td width="35%">{total:,}</td></tr>
                <tr><td style="border:none; background:white;"></td><td>부 가 세</td><td>{vat:,}</td></tr>
                <tr><td style="border:none; background:white;"></td><td style="background:#e5e7eb;">합 계</td><td style="background:#e5e7eb; color:#c00;">{grand_total:,}</td></tr>
            </table>
        </div>
    </div>
    
    <div class="bank-box">입금계좌: 기업은행 132-119648-04-019 (예금주: 주식회사 가디어스)</div>
    <div class="footer-banner">{footer_img_tag}</div>
    </div></body></html>
    """

def get_detailed_report_html(df, client, notes):
    """(기존 4단 리포트 유지)"""
    rows = ""
    total_rev, total_cost, total_prof = 0, 0, 0
    for _, r in df.iterrows():
        item = r['품목']
        qty = safe_int(r.get('수량', 0))
        days = safe_int(r.get('일수', 1))
        u_rev = safe_int(r['매출단가'])
        u_cost = safe_int(r['매입단가'])
        u_prof = u_rev - u_cost
        sum_rev = r['매출합계']
        sum_cost = r['매입합계']
        prof = sum_rev - sum_cost
        margin = (prof / sum_rev * 100) if sum_rev > 0 else 0
        total_rev += sum_rev; total_cost += sum_cost; total_prof += prof
        rows += f"""<tr><td style="text-align:left;">{item}</td><td>{days}</td><td>{qty}</td><td style="text-align:right;">{u_rev:,}</td><td style="text-align:right;">{u_cost:,}</td><td style="text-align:right; font-weight:bold; color:#2563eb;">{u_prof:,}</td><td style="text-align:right;">{sum_rev:,}</td><td style="text-align:right;">{sum_cost:,}</td><td style="text-align:right; font-weight:bold; color:{'#ef4444' if margin<10 else '#10b981'};">{prof:,} ({margin:.1f}%)</td></tr>"""
    tot_margin = (total_prof / total_rev * 100) if total_rev > 0 else 0
    return f"""<html><head><style>body{{font-family:'Malgun Gothic';padding:20px;}}.paper{{width:210mm;background:white;padding:30px;margin:0 auto;box-shadow:0 4px 6px rgba(0,0,0,0.1);}}table{{width:100%;border-collapse:collapse;font-size:11px;}}th,td{{border:1px solid #ddd;padding:6px;text-align:center;}}th{{background:#f1f5f9;}}.kpi-bar{{display:flex;gap:10px;margin-bottom:20px;}}.kpi{{flex:1;padding:15px;color:white;text-align:center;border-radius:8px;}}.section{{margin-bottom:15px;border:1px solid #eee;padding:10px;border-radius:5px;font-size:12px;}}</style><script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script><script>function saveReport(){{const e=document.getElementById("report_area");html2canvas(e,{{scale:2}}).then(c=>{{var l=document.createElement('a');l.download='상세리포트_{client}.png';l.href=c.toDataURL("image/png");l.click();}});}}</script></head><body><button onclick="saveReport()" style="background:#059669;color:white;padding:8px 16px;border:none;cursor:pointer;display:block;margin:0 auto 20px auto;">📸 리포트 저장</button><div id="report_area" class="paper"><h2 style="text-align:center;">📊 수익 분석</h2><h3 style="text-align:center; color:#555;">{client}</h3><div class="kpi-bar"><div class="kpi" style="background:#3b82f6;">총 청구<br><span style="font-size:20px;font-weight:bold;">{total_rev:,}</span></div><div class="kpi" style="background:#ef4444;">총 지급<br><span style="font-size:20px;font-weight:bold;">{total_cost:,}</span></div><div class="kpi" style="background:#10b981;">순이익 ({tot_margin:.1f}%)<br><span style="font-size:20px;font-weight:bold;">{total_prof:,}</span></div></div><table><thead><tr><th rowspan="2">품목</th><th colspan="2">투입</th><th colspan="3">1인당 단가</th><th colspan="3">총 합계</th></tr><tr><th>일</th><th>명</th><th>청구</th><th>지급</th><th>마진</th><th>청구</th><th>지급</th><th>순이익</th></tr></thead><tbody>{rows}</tbody><tfoot><tr style="background:#e2e8f0; font-weight:bold;"><td colspan="6">합 계</td><td style="text-align:right;">{total_rev:,}</td><td style="text-align:right;">{total_cost:,}</td><td style="text-align:right; color:#059669;">{total_prof:,}</td></tr></tfoot></table><div class="section"><h4>1. 전략</h4><p>{notes[0]}</p></div><div class="section"><h4>2. 인력</h4><p>{notes[1]}</p></div><div class="section"><h4>3. 특이</h4><p>{notes[2]}</p></div><div class="section"><h4>4. 결론</h4><p>{notes[3]}</p></div></div></body></html>"""