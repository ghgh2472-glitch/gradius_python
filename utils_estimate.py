# utils_estimate.py
import pandas as pd
import re
from datetime import datetime, timedelta, time
from helpers import now_kst

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
        if not role_name_kr or role_name_kr == "선택": return info
        # 경비지도사 기본값 (시트에 없는 경우)
        if role_name_kr == '경비지도사':
            info['base_price'] = 250000
            info['cost_price'] = 150000
        if self.df_roles.empty: return info
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
    """날짜 문자열 파싱. 단일 기간 또는 다중 기간 지원
    
    지원 형식:
    - 단일: '2026-02-20~2026-02-22'
    - 다중: '2026-02-15~2026-02-18 / 2026-02-20~2026-02-25'
    - 다중: '2/15~18, 2/20~25'
    
    반환: (시작일, 종료일, 총일수)
    - 다중 기간인 경우: 첫 시작일, 마지막 종료일, 합산 일수
    """
    txt = str(date_str).strip()
    now = now_kst().date()
    if not txt: return (now, now, 1)
    
    y = now_kst().year
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
        # 다중 기간 분리: ' / ' 또는 ', ' 구분 (MM/DD 형식 보호)
        segments = re.split(r'\s+/\s+|\s*,\s+', txt)
        segments = [s.strip() for s in segments if s.strip()]
        
        all_periods = []
        for seg in segments:
            if '~' in seg:
                parts = seg.split('~', 1)
                dt1 = to_d(parts[0])
                dt2 = to_d(parts[1]) if len(parts) > 1 else dt1
                # MM-DD~DD 형식 (종료일에 월이 없는 경우)
                if dt2 is None and dt1 is not None and parts[1].strip().isdigit():
                    day_only = int(parts[1].strip())
                    dt2 = dt1.replace(day=day_only)
            else:
                dt1 = to_d(seg)
                dt2 = dt1
            
            if dt1 is not None:
                if dt2 is None: dt2 = dt1
                all_periods.append((dt1, dt2))
        
        if not all_periods:
            return (now, now, 1)
        
        first_start = all_periods[0][0]
        last_end = all_periods[-1][1]
        total_days = sum(max(1, (e - s).days + 1) for s, e in all_periods)
        
        return (first_start, last_end, total_days)
    except: return (now, now, 1)


def smart_parse_dates_multi(date_str):
    """다중 기간을 개별 기간 리스트로 반환
    
    반환: [(시작일1, 종료일1, 일수1), (시작일2, 종료일2, 일수2), ...]
    """
    txt = str(date_str).strip()
    now = now_kst().date()
    if not txt: return [(now, now, 1)]
    
    y = now_kst().year
    def to_d(s):
        s = s.strip().replace('.', '-').replace('/', '-')
        if not s: return None
        if len(s) >= 8 and s.count('-') == 2:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        if s.count('-') == 1:
            return datetime.strptime(f"{y}-{s}", "%Y-%m-%d").date()
        return None
    
    try:
        segments = re.split(r'\s+/\s+|\s*,\s+', txt)
        segments = [s.strip() for s in segments if s.strip()]
        
        results = []
        for seg in segments:
            if '~' in seg:
                parts = seg.split('~', 1)
                dt1 = to_d(parts[0])
                dt2 = to_d(parts[1]) if len(parts) > 1 else dt1
                if dt2 is None and dt1 is not None and parts[1].strip().isdigit():
                    day_only = int(parts[1].strip())
                    dt2 = dt1.replace(day=day_only)
            else:
                dt1 = to_d(seg)
                dt2 = dt1
            
            if dt1 is not None:
                if dt2 is None: dt2 = dt1
                days = max(1, (dt2 - dt1).days + 1)
                results.append((dt1, dt2, days))
        
        return results if results else [(now, now, 1)]
    except: return [(now, now, 1)]

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

def get_customer_quote_html(df, client_info, supplier_info, supply_amt, vat_yn, terms_top, terms_side, footer_img_base64=None, additional_costs_df=None, additional_costs_total=0, discount_amount=0):
    total = safe_int(supply_amt)
    additional_total = safe_int(additional_costs_total)
    discount = safe_int(discount_amount)
    total_with_additional = total + additional_total
    total_after_discount = total_with_additional - discount
    vat = int(total_after_discount * 0.1) if vat_yn else 0
    grand_total = total_after_discount + vat
        
    # ── 인력 품목 / [지원] 품목 분리 ──
    labor_rows = ""
    support_rows = ""
    for _, r in df.iterrows():
        _item_name = str(r.get('품목', '')).strip()
        if not _item_name or _item_name in ('nan', 'None'):
            continue
        qty = safe_int(r.get('수량', 0))
        days = safe_int(r.get('일수', 1))
        price = safe_int(r.get('매출단가', 0))
        amt = safe_int(r.get('매출합계', 0))
        spec = r.get('규격', '')
        note = r.get('비고', '')
        _disc_amt = safe_int(r.get('할인액', r.get('할인율', 0)))
        if _disc_amt > 0 and price > 0:
            _discounted_price = max(0, price - _disc_amt)
            _price_html = f'<del style="color:#999;font-size:11px;">{price:,}</del><br><span style="color:#c2410c;font-weight:bold;">{_discounted_price:,}</span>'
            _amt_html = f'{amt:,}'
        elif price == 0:
            _price_html = '무료'
            _amt_html = '무료'
        else:
            _price_html = f'{price:,}'
            _amt_html = f'{amt:,}'

        _is_support = _item_name.startswith('[지원]')
        if _is_support:
            _display_name = _item_name.replace('[지원]', '').strip()
            support_rows += f"""
        <tr style="background:#f0fdf4;">
            <td style="text-align:center; padding:4px 6px; white-space:pre-line; color:#15803d;">{_display_name}</td>
            <td style="text-align:center; color:#555; font-size:12px;">{spec}</td>
            <td style="text-align:center; color:#999;">-</td>
            <td style="text-align:center; color:#999;">-</td>
            <td style="text-align:right; padding-right:10px; color:#15803d;">{_price_html}</td>
            <td style="text-align:right; padding-right:10px; color:#15803d;">{_amt_html}</td>
            <td style="text-align:center; padding:4px 5px; font-size:10px; color:#15803d; font-weight:bold;">본사 지원</td>
        </tr>
        """
        else:
            labor_rows += f"""
        <tr>
            <td style="text-align:center; padding:4px 6px; white-space:pre-line;">{_item_name.replace(chr(10), '<br>')}</td>
            <td style="text-align:center; color:#555; font-size:12px;">{spec}</td>
            <td style="text-align:center;">{qty}</td>
            <td style="text-align:center;">{days}</td>
            <td style="text-align:right; padding-right:10px;">{_price_html}</td>
            <td style="text-align:right; padding-right:10px;">{_amt_html}</td>
            <td style="text-align:center; padding:4px 5px; font-size:11px;">{note}</td>
        </tr>
        """
    
    # ── 부대비용 행 (의뢰사제공 / 일반 구분) ──
    additional_rows = ""
    client_provided_rows = ""
    if additional_costs_df is not None and not additional_costs_df.empty:
        for _, r in additional_costs_df.iterrows():
            item = r.get('항목', '')
            cost = safe_int(r.get('금액', 0))
            note = str(r.get('비고', ''))
            _c_qty = safe_int(r.get('수량', 1))
            _c_days = safe_int(r.get('일수', 1))
            _c_unit = safe_int(r.get('단가', 0))
            _spec_disp = ''
            if '의뢰사제공' in note:
                _parts = note.split('|')
                _meal_info = _parts[1] if len(_parts) > 1 else '1인 1식'
                _meal_note = _parts[2] if len(_parts) > 2 else '미제공시 1식당\n1만원 추가청구'
                _spec_disp = '의뢰사제공'
                _note_disp = _meal_note.replace('\n', '<br>')
                client_provided_rows += f"""
        <tr style="background:#eff6ff;">
            <td style="text-align:center; padding:4px 6px; color:#1e40af;">{item}</td>
            <td style="text-align:center; color:#1e40af; font-size:12px;">{_spec_disp}</td>
            <td style="text-align:center;">{_meal_info}</td>
            <td style="text-align:center;">{_c_days}</td>
            <td style="text-align:right; padding-right:10px;">-</td>
            <td style="text-align:right; padding-right:10px; font-weight:bold;">-</td>
            <td style="text-align:center; padding:4px 5px; font-size:11px;">{_note_disp}</td>
        </tr>
        """
            else:
                if _c_unit == 0:
                    _unit_disp = '무료'
                    _cost_disp = '무료'
                else:
                    _unit_disp = f'{_c_unit:,}'
                    _cost_disp = f'{cost:,}'
                additional_rows += f"""
        <tr style="background:#fef3c7;">
            <td style="text-align:center; padding:4px 6px;">{item}</td>
            <td style="text-align:center; color:#555; font-size:12px;">{_spec_disp}</td>
            <td style="text-align:center;">{_c_qty}</td>
            <td style="text-align:center;">{_c_days}</td>
            <td style="text-align:right; padding-right:10px;">{_unit_disp}</td>
            <td style="text-align:right; padding-right:10px; font-weight:bold;">{_cost_disp}</td>
            <td style="text-align:center; padding:4px 5px; font-size:11px;">{note}</td>
        </tr>
        """
    
    # ── 조립: 인력 → 지원 → 소계 → 부대품목 → 의뢰사제공 → 부대합계 → 할인 → 총합계 ──
    rows = labor_rows + support_rows
    
    rows += f"""
    <tr style="background:#f3f4f6; font-weight:bold;">
        <td colspan="5" style="text-align:right; padding-right:10px;">소계:</td>
        <td style="text-align:right; padding-right:10px;">{total:,}</td>
        <td></td>
    </tr>
    """
    
    if additional_total > 0 or additional_rows or client_provided_rows:
        rows += additional_rows + client_provided_rows
        if additional_total > 0:
            rows += f"""
    <tr style="background:#fef3c7; font-weight:bold;">
        <td colspan="5" style="text-align:right; padding-right:10px;">부대비용 합계:</td>
        <td style="text-align:right; padding-right:10px; color:#c2410c;">{additional_total:,}</td>
        <td></td>
    </tr>
    """
    
    if discount > 0:
        rows += f"""
    <tr style="background:#fff5f5; font-weight:bold;">
        <td colspan="5" style="text-align:right; padding-right:10px; color:#dc2626;">할인:</td>
        <td style="text-align:right; padding-right:10px; color:#dc2626;">-{discount:,}</td>
        <td></td>
    </tr>
    """
    
    rows += f"""
    <tr style="background:#e5e7eb; font-weight:bold; font-size:13px;">
        <td colspan="5" style="text-align:right; padding-right:10px;">총 합계:</td>
        <td style="text-align:right; padding-right:10px;">{total_with_additional - discount:,}</td>
        <td></td>
    </tr>
    """

    footer_img_tag = ""
    if footer_img_base64:
        footer_img_tag = f'<div style="text-align:center; margin-top:20px;"><img src="data:image/png;base64,{footer_img_base64}" style="width:100%; max-width:800px;"></div>'

    def _terms_to_html(text):
        """약관 텍스트를 HTML로 변환. 이미 HTML 태그가 있으면 그대로, 순수 텍스트면 자동 스타일링"""
        import re as _re
        if '<span' in text or '<b>' in text or '<div' in text:
            # 이미 HTML 포함 — 줄바꿈만 처리
            return text.replace('\n', '<br>')
        # 순수 텍스트 → 자동 스타일링
        lines = text.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # "1." "2." 등 번호로 시작하는 제목
            if _re.match(r'^\d+\.', line):
                parts = line.split('|')
                title = parts[0].strip()
                rest = ' | '.join(parts[1:]).strip() if len(parts) > 1 else ''
                result.append(f'<span style="color:#000080; font-weight:bold;">{title}</span>')
                if rest:
                    result.append(f'{rest}')
            elif line.startswith('※'):
                result.append(f'<span style="font-size:11px; color:#666;">{line}</span>')
            else:
                result.append(line)
        return '<br>'.join(result)

    fmt_top = _terms_to_html(terms_top)
    fmt_side = _terms_to_html(terms_side)

    return f"""
    <html><head><script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script><script>function saveImage(){{const e=document.getElementById("print_area");html2canvas(e,{{scale:2,useCORS:true,allowTaint:true,scrollY:0,windowHeight:e.scrollHeight+100}}).then(c=>{{var l=document.createElement('a');l.download='견적서_{client_info["name"]}.png';l.href=c.toDataURL("image/png");l.click();}});}}</script>
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    body{{font-family:'Noto Sans KR',sans-serif;background:#525659;padding:20px;display:flex;justify-content:center;}}
    .paper{{width:210mm;background:white;padding:10mm;box-shadow:0 0 10px rgba(0,0,0,0.5);box-sizing:border-box;position:relative;overflow:visible;}}
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
                <tr><td width="30%" style="border:none; background:white;"></td><td width="35%">공급가액</td><td width="35%">{total_with_additional:,}</td></tr>
                {"" if discount == 0 else f'<tr><td style="border:none; background:white;"></td><td style="color:#c2410c;">할 인</td><td style="color:#c2410c;">-{discount:,}</td></tr>'}
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
        item = str(r['품목']).replace('\n', ' ')  # 날짜 태그 줄바꿈 정리
        qty = safe_int(r.get('수량', 0))
        days = safe_int(r.get('일수', 1))
        u_rev = safe_int(r['매출단가'])
        u_cost = safe_int(r['매입단가'])
        u_prof = u_rev - u_cost
        sum_rev = safe_int(r['매출합계'])
        sum_cost = safe_int(r['매입합계'])
        prof = sum_rev - sum_cost
        margin = (prof / sum_rev * 100) if sum_rev > 0 else 0
        total_rev += sum_rev; total_cost += sum_cost; total_prof += prof
        rows += f"""<tr><td style="text-align:left;">{item}</td><td>{days}</td><td>{qty}</td><td style="text-align:right;">{u_rev:,}</td><td style="text-align:right;">{u_cost:,}</td><td style="text-align:right; font-weight:bold; color:#2563eb;">{u_prof:,}</td><td style="text-align:right;">{sum_rev:,}</td><td style="text-align:right;">{sum_cost:,}</td><td style="text-align:right; font-weight:bold; color:{'#ef4444' if margin<10 else '#10b981'};">{prof:,} ({margin:.1f}%)</td></tr>"""
    tot_margin = (total_prof / total_rev * 100) if total_rev > 0 else 0
    return f"""<html><head><style>body{{font-family:'Malgun Gothic';padding:20px;}}.paper{{width:210mm;background:white;padding:30px;margin:0 auto;box-shadow:0 4px 6px rgba(0,0,0,0.1);}}table{{width:100%;border-collapse:collapse;font-size:11px;}}th,td{{border:1px solid #ddd;padding:6px;text-align:center;}}th{{background:#f1f5f9;}}.kpi-bar{{display:flex;gap:10px;margin-bottom:20px;}}.kpi{{flex:1;padding:15px;color:white;text-align:center;border-radius:8px;}}.section{{margin-bottom:15px;border:1px solid #eee;padding:10px;border-radius:5px;font-size:12px;}}</style><script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script><script>function saveReport(){{const e=document.getElementById("report_area");html2canvas(e,{{scale:2}}).then(c=>{{var l=document.createElement('a');l.download='상세리포트_{client}.png';l.href=c.toDataURL("image/png");l.click();}});}}</script></head><body><button onclick="saveReport()" style="background:#059669;color:white;padding:8px 16px;border:none;cursor:pointer;display:block;margin:0 auto 20px auto;">📸 리포트 저장</button><div id="report_area" class="paper"><h2 style="text-align:center;">📊 수익 분석</h2><h3 style="text-align:center; color:#555;">{client}</h3><div class="kpi-bar"><div class="kpi" style="background:#3b82f6;">총 청구<br><span style="font-size:20px;font-weight:bold;">{total_rev:,}</span></div><div class="kpi" style="background:#ef4444;">총 지급<br><span style="font-size:20px;font-weight:bold;">{total_cost:,}</span></div><div class="kpi" style="background:#10b981;">순이익 ({tot_margin:.1f}%)<br><span style="font-size:20px;font-weight:bold;">{total_prof:,}</span></div></div><table><thead><tr><th rowspan="2">품목</th><th colspan="2">투입</th><th colspan="3">1인당 단가</th><th colspan="3">총 합계</th></tr><tr><th>일</th><th>명</th><th>청구</th><th>지급</th><th>마진</th><th>청구</th><th>지급</th><th>순이익</th></tr></thead><tbody>{rows}</tbody><tfoot><tr style="background:#e2e8f0; font-weight:bold;"><td colspan="6">합 계</td><td style="text-align:right;">{total_rev:,}</td><td style="text-align:right;">{total_cost:,}</td><td style="text-align:right; color:#059669;">{total_prof:,}</td></tr></tfoot></table><div class="section"><h4>1. 전략</h4><p>{notes[0]}</p></div><div class="section"><h4>2. 인력</h4><p>{notes[1]}</p></div><div class="section"><h4>3. 특이</h4><p>{notes[2]}</p></div><div class="section"><h4>4. 결론</h4><p>{notes[3]}</p></div></div></body></html>"""