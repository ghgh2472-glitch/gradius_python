# utils.py
import re
from datetime import datetime, timedelta
from helpers import now_kst
import base64
import pandas as pd

# ---------------------------------------------------------
# 1. 안전한 숫자 변환 및 계산 도구
# ---------------------------------------------------------
def safe_int(val):
    try:
        if isinstance(val, str):
            clean_val = val.replace(',', '').replace('원', '').replace('명', '').replace('건', '').replace('개', '').strip()
            if not clean_val: return 0
            return int(float(clean_val))
        return int(float(val))
    except:
        return 0

def calc_hours(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        if isinstance(t_in, str): t_in = datetime.strptime(t_in[:5], "%H:%M").time()
        if isinstance(t_out, str): t_out = datetime.strptime(t_out[:5], "%H:%M").time()
        dummy = datetime(2000, 1, 1)
        d_in = datetime.combine(dummy, t_in)
        d_out = datetime.combine(dummy, t_out)
        if d_out < d_in: d_out += timedelta(days=1)
        return round((d_out - d_in).total_seconds() / 3600, 1)
    except: return 0

def num_to_hangul(num):
    try: num = int(float(num))
    except: return "영"
    if num == 0: return "영"
    
    units = ["", "만", "억", "조"]
    digits = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
    result = []
    str_num = str(num)[::-1]
    
    for i in range(0, len(str_num), 4):
        chunk = str_num[i:i+4]
        chunk_res = []
        for j, digit in enumerate(chunk):
            d = int(digit)
            if d > 0:
                if j == 0: chunk_res.append(digits[d])
                elif j == 1: chunk_res.append(digits[d] + "십" if d > 1 else "십")
                elif j == 2: chunk_res.append(digits[d] + "백" if d > 1 else "백")
                elif j == 3: chunk_res.append(digits[d] + "천" if d > 1 else "천")
        if chunk_res:
            result.append("".join(reversed(chunk_res)) + units[i//4])
    return "".join(reversed(result)) + "원정"

# ---------------------------------------------------------
# 2. [HTML] 공통 스크립트 (이미지 다운로드용)
# ---------------------------------------------------------
def get_capture_script(filename):
    return f"""
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
    <script>
        function downloadImage() {{
            var btn = document.getElementById('down-btn');
            btn.style.display = 'none';
            // scale: 2로 설정하여 고화질 캡처
            html2canvas(document.querySelector("#capture_area"), {{scale: 2, backgroundColor: "#ffffff"}}).then(canvas => {{
                var link = document.createElement('a');
                link.download = '{filename}.png';
                link.href = canvas.toDataURL("image/png");
                link.click();
                btn.style.display = 'block';
            }});
        }}
    </script>
    """

def get_common_css():
    return """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Malgun+Gothic&display=swap');
        body { 
            font-family: 'Noto Sans KR', sans-serif; background-color: #525659; 
            margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; 
        }
        #capture_area {
            width: 210mm; min-height: 297mm; padding: 20mm; margin: 0 auto;
            background: white; box-shadow: 0 0 15px rgba(0,0,0,0.3); box-sizing: border-box; position: relative;
        }
        .down-btn {
            margin-bottom: 20px; padding: 12px 25px; background: #2563EB; color: white; 
            border: none; border-radius: 25px; font-size: 15px; font-weight: bold; 
            cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.2); transition: 0.2s;
        }
        .down-btn:hover { background: #1D4ED8; transform: translateY(-2px); }
        table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; }
        th, td { border: 1px solid #333; padding: 6px; }
        .box { border: 2px solid black; display: flex; }
    </style>
    """

# ---------------------------------------------------------
# 3. [HTML] 고객용 견적서 (이미지 저장)
# ---------------------------------------------------------
def get_customer_quote_html(df, client_name, project_name, date_str, location, t_sales, vat_included, custom_note):
    t_sales = safe_int(t_sales)
    
    if vat_included:
        grand_total = t_sales
        supply_val = int(t_sales / 1.1)
        vat_val = grand_total - supply_val
    else:
        supply_val = t_sales
        vat_val = int(t_sales * 0.1)
        grand_total = supply_val + vat_val

    hangul = num_to_hangul(grand_total)
    
    rows = ""
    for _, r in df.iterrows():
        qty = safe_int(r.get('수량', 0))
        price = safe_int(r.get('매출단가', 0))
        amt = safe_int(r.get('매출합계', 0))
        note = r.get('비고', '')
        rows += f"""<tr style="height:32px;">
            <td style="text-align:center;">{r.get('품목','')}</td>
            <td style="text-align:center; color:#555;">{note}</td>
            <td style="text-align:center;">{qty if qty>0 else ''}</td>
            <td style="text-align:right; padding-right:5px;">{f'{price:,}' if price>0 else ''}</td>
            <td style="text-align:right; padding-right:5px;">{f'{amt:,}' if amt>0 else ''}</td>
        </tr>"""
    
    for _ in range(max(0, 14 - len(df))):
        rows += "<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td></tr>"

    return f"""
    <html>
    <head>{get_capture_script(f'견적서_{client_name}')}{get_common_css()}</head>
    <body>
        <button id="down-btn" class="down-btn" onclick="downloadImage()">📸 견적서 이미지로 저장</button>
        <div id="capture_area">
            <div style="text-align:center; font-size:36px; font-weight:bold; letter-spacing:10px; margin-bottom:40px; text-decoration:underline; text-underline-offset:10px;">견 적 서</div>
            <div class="box" style="height:130px; margin-bottom:20px;">
                <div style="flex:1; border-right:1px solid black; padding:10px;">
                    <table style="height:100%; margin:0; border:none;">
                        <tr><td style="background:#f0f0f0; text-align:center; font-weight:bold; width:70px; border:none;">수신</td><td style="border:none;">{client_name} 귀하</td></tr>
                        <tr><td style="background:#f0f0f0; text-align:center; font-weight:bold; border:none;">건명</td><td style="border:none;">{project_name}</td></tr>
                        <tr><td style="background:#f0f0f0; text-align:center; font-weight:bold; border:none;">일시</td><td style="border:none;">{date_str}</td></tr>
                    </table>
                </div>
                <div style="flex:1; padding:10px;">
                    <table style="height:100%; margin:0; border:none;">
                        <tr><td rowspan="3" style="background:#f0f0f0; text-align:center; font-weight:bold; width:30px; border:none;">공<br>급<br>자</td>
                            <td style="background:#f0f0f0; text-align:center; font-weight:bold; border:none;">등록번호</td><td style="border:none;">123-45-67890</td></tr>
                        <tr><td style="background:#f0f0f0; text-align:center; font-weight:bold; border:none;">상호</td><td style="border:none;">(주)가디어스</td></tr>
                        <tr><td style="background:#f0f0f0; text-align:center; font-weight:bold; border:none;">주소</td><td style="border:none;">서울시 강남구 테헤란로</td></tr>
                    </table>
                </div>
            </div>
            <div style="border:2px solid black; padding:10px; text-align:center; font-weight:bold; font-size:16px; background:#f9f9f9; margin-bottom:10px;">
                합계금액 : 일금 {hangul} (VAT {'포함' if vat_included else '별도'})
            </div>
            <table>
                <thead style="background:#e0e0e0;"><tr><th width="25%">품명</th><th width="25%">상세</th><th width="10%">수량</th><th width="20%">단가</th><th width="20%">금액</th></tr></thead>
                <tbody>{rows}</tbody>
                <tfoot>
                    <tr><td colspan="3" align="center" style="background:#f9f9f9;"><b>공 급 가 액</b></td><td colspan="2" align="right">{supply_val:,}</td></tr>
                    <tr><td colspan="3" align="center" style="background:#f9f9f9;"><b>부 가 세 (10%)</b></td><td colspan="2" align="right">{vat_val:,}</td></tr>
                    <tr style="background:#ddd; font-size:14px;"><td colspan="3" align="center"><b>총 합 계</b></td><td colspan="2" align="right" style="font-weight:bold;">{grand_total:,}</td></tr>
                </tfoot>
            </table>
            <div style="margin-top:30px; border:1px solid black; padding:15px; font-size:12px; line-height:1.8;">
                <b>[안내사항]</b><br>{custom_note.replace(chr(10), '<br>')}
            </div>
            <div style="text-align:center; margin-top:60px; font-size:22px; font-weight:bold;">주식회사 가디어스 (인)</div>
        </div>
    </body>
    </html>
    """

# ---------------------------------------------------------
# 4. [HTML] 내부 리포트 (스마트 디자인 + 이미지 저장)
# ---------------------------------------------------------
def get_internal_report_html(df, client_name, t_sales, t_cost, n1, n2, n3, n4):
    t_sales = safe_int(t_sales); t_cost = safe_int(t_cost)
    profit = t_sales - t_cost
    margin = (profit / t_sales * 100) if t_sales > 0 else 0
    today = now_kst().strftime('%Y-%m-%d')
    
    rows = ""
    for _, r in df.iterrows():
        s = safe_int(r.get('매출합계',0)); c = safe_int(r.get('매입합계',0)); p = s - c
        # 이익률이 낮으면 빨간색 표시
        p_color = 'red' if p < 0 else ('black' if p == 0 else 'blue')
        rows += f"<tr><td style='text-align:left;'>{r.get('품목','')}</td><td align='right'>{s:,}</td><td align='right'>{c:,}</td><td align='right' style='color:{p_color}; font-weight:bold;'>{p:,}</td></tr>"

    return f"""
    <html>
    <head>{get_capture_script(f'승인리포트_{client_name}')}{get_common_css()}</head>
    <body>
        <button id="down-btn" class="down-btn" style="background:#10B981;" onclick="downloadImage()">📸 리포트 이미지로 저장</button>
        <div id="capture_area">
            <h2 style="color:#1E3A8A; border-bottom:3px solid #1E3A8A; padding-bottom:10px; margin-top:0;">📊 경영 승인 요청서</h2>
            <div style="display:flex; justify-content:space-between; margin-bottom:20px; color:#555; font-size:14px;">
                <span><b>프로젝트:</b> {client_name}</span><span><b>작성일:</b> {today}</span>
            </div>
            
            <div style="display:flex; gap:15px; margin-bottom:30px;">
                <div style="flex:1; border:1px solid #ccc; padding:15px; text-align:center; border-radius:8px; background:#f8f9fa;">
                    <div style="font-size:12px; color:#666;">총 매출 (Sales)</div><div style="font-size:20px; font-weight:bold;">{t_sales:,}</div>
                </div>
                <div style="flex:1; border:1px solid #ccc; padding:15px; text-align:center; border-radius:8px; background:#fff5f5;">
                    <div style="font-size:12px; color:#666;">총 원가 (Cost)</div><div style="font-size:20px; font-weight:bold;">{t_cost:,}</div>
                </div>
                <div style="flex:1; border:2px solid #10B981; padding:15px; text-align:center; border-radius:8px; background:#f0fdf4;">
                    <div style="font-size:12px; color:#166534;">예상 이익 (Profit)</div>
                    <div style="font-size:20px; font-weight:bold; color:#15803D;">+{profit:,} <span style="font-size:14px;">({margin:.1f}%)</span></div>
                </div>
            </div>
            
            <h4 style="background:#e0e7ff; padding:8px; border-left:5px solid #3b82f6; margin:0;">1. 손익 상세 내역</h4>
            <table style="width:100%; margin-bottom:30px;">
                <tr style="background:#eee; height:30px;"><th>항목</th><th>매출</th><th>매입</th><th>이익</th></tr>
                {rows}
            </table>
            
            <h4 style="background:#e0e7ff; padding:8px; border-left:5px solid #3b82f6; margin:0;">2. 전략 코멘트</h4>
            <div style="border:1px solid #ddd; padding:15px; font-size:13px; line-height:1.6; min-height:150px;">
                <p><b>① 산출 근거:</b><br>{n1}</p>
                <p><b>② 인력 배정:</b><br>{n2}</p>
                <p><b>③ 특이 사항:</b><br>{n3}</p>
                <hr style="border:0; border-top:1px dashed #ccc;">
                <p><b>④ 최종 결론:</b><br>{n4}</p>
            </div>
            <div style="margin-top:40px; text-align:right; font-weight:bold;">위와 같이 견적 승인을 요청합니다.</div>
        </div>
    </body>
    </html>
    """

# (기존 get_download_btn은 삭제해도 됨)