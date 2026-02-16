# utils_settlement.py
import pandas as pd
import re
from datetime import datetime

class SettlementBrain:
    def __init__(self, df_inq):
        self.df = df_inq

    def parse_dispatch_data(self, note_text):
        """
        [Super Robust Parsing]
        형식이 조금 달라도 최대한 데이터를 복구해내는 강력한 파서
        """
        if not isinstance(note_text, str): return []
        
        staff_list = []
        lines = note_text.split('\n')
        
        for line in lines:
            line = line.strip()
            # 1. 데이터 행인지 확인 ('-'로 시작하거나, '지급'이라는 단어가 있으면 시도)
            if not line.startswith("-") and "지급" not in line:
                continue

            try:
                # 초기값
                name = "미상"
                role = "직무미상"
                pay = 0
                days = 1
                
                # 데이터 정제 (특수문자 제거 후 공백 기준 분리 시도)
                # 예: "- 홍길동(경호) / 010-1234-5678 / 지급:100,000 (2일)"
                
                # (A) 이름/직무 파싱
                # '-' 뒤에 오는 첫 단어들을 분석
                # 괄호 안의 내용 추출
                role_match = re.search(r'\((.*?)\)', line)
                if role_match:
                    role = role_match.group(1)
                
                # 이름 추출 (괄호 앞부분 or '-' 뒤의 첫 단어)
                name_match = re.search(r'-\s*(.*?)\s*[\(\/]', line)
                if name_match:
                    name = name_match.group(1).strip()
                else:
                    # 정규식 실패 시 단순 분리
                    parts = line.replace('-', '').split('/')
                    if len(parts) > 0:
                        name_part = parts[0].strip()
                        name = name_part.split('(')[0].strip()

                # (B) 지급액 파싱 (가장 중요!)
                # '지급' 이라는 글자 뒤에 나오는 숫자(콤마 포함)를 무조건 찾음
                pay_match = re.search(r'지급\D*([\d,]+)', line)
                if pay_match:
                    pay_str = pay_match.group(1).replace(',', '')
                    if pay_str.isdigit():
                        pay = int(pay_str)
                
                # (C) 일수 파싱
                # '일' 앞의 숫자, 혹은 'days' 앞의 숫자
                days_match = re.search(r'(\d+)\s*일', line)
                if days_match:
                    days = int(days_match.group(1))

                # 유효성 검사: 지급액이 있으면 리스트에 추가
                if pay > 0:
                    staff_list.append({
                        "이름": name,
                        "직무": role,
                        "지급단가": pay,
                        "일수": days,
                        "총지급액": pay * days,
                        "상태": "대기"
                    })
                    
            except Exception as e:
                # 에러 발생 시 로그만 찍고 넘어감 (시스템 멈춤 방지)
                print(f"Parsing Error: {line} / {e}")
                continue
                
        return staff_list

    def get_financial_summary(self, row):
        """재무 요약 계산"""
        sales = 0
        note = str(row.get('특이사항', '')) # 특이사항 or 비고 컬럼
        
        # 매출 파싱 [매출:100000] 형태
        m_sales = re.search(r'매출\D*([\d,]+)', note)
        if m_sales:
            try:
                sales = int(m_sales.group(1).replace(',', ''))
            except: sales = 0
            
        # 매입 계산 (위의 파서 사용)
        staff_data = self.parse_dispatch_data(note)
        cost = sum([s['총지급액'] for s in staff_data])
        
        profit = sales - cost
        margin = (profit / sales * 100) if sales > 0 else 0
        
        return {
            "매출": sales,
            "매입": cost,
            "수익": profit,
            "수익률": margin,
            "인원수": len(staff_data),
            "raw_text": note # 디버깅용 원본 텍스트
        }

    # ... (HTML 생성 함수들은 기존과 동일하게 유지) ...
    def get_invoice_html(self, client_name, project_name, date_str, amount, items=None):
        """
        거래명세서 HTML — items가 있으면 품목별 상세 표시
        items: list of dict [{'품목명': ..., '수량': ..., '단가': ..., '금액': ...}, ...]
        """
        now = datetime.now().strftime("%Y-%m-%d")
        amount = int(amount) if amount else 0
        amount_vat = int(amount * 1.1)
        vat = amount_vat - amount

        # 품목별 상세 행
        item_rows = ""
        if items and len(items) > 0:
            for idx, it in enumerate(items, 1):
                it_name = it.get('품목명', it.get('직종', f'항목{idx}'))
                it_qty = it.get('수량', it.get('인원수', 1))
                it_unit = it.get('단가', it.get('단가(일)', 0))
                it_days = it.get('일수', it.get('일수', 1))
                it_amt = it.get('금액', it.get('소계', 0))
                try:
                    it_qty = int(float(it_qty or 0))
                    it_unit = int(float(it_unit or 0))
                    it_days = int(float(it_days or 1))
                    it_amt = int(float(it_amt or 0))
                except:
                    it_qty, it_unit, it_days, it_amt = 1, 0, 1, 0
                if it_amt == 0:
                    it_amt = it_qty * it_unit * it_days
                item_rows += f"""
                <tr>
                    <td style="padding:8px; border:1px solid #ddd;">{idx}</td>
                    <td style="padding:8px; border:1px solid #ddd; text-align:left;">{it_name}</td>
                    <td style="padding:8px; border:1px solid #ddd;">{it_qty}</td>
                    <td style="padding:8px; border:1px solid #ddd;">{it_unit:,}</td>
                    <td style="padding:8px; border:1px solid #ddd;">{it_days}</td>
                    <td style="padding:8px; border:1px solid #ddd; text-align:right; font-weight:bold;">{it_amt:,}</td>
                </tr>"""
        else:
            item_rows = f"""
            <tr>
                <td style="padding:8px; border:1px solid #ddd;">1</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:left;">{project_name}</td>
                <td style="padding:8px; border:1px solid #ddd;">1</td>
                <td style="padding:8px; border:1px solid #ddd;">{amount:,}</td>
                <td style="padding:8px; border:1px solid #ddd;">1</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right; font-weight:bold;">{amount:,}</td>
            </tr>"""

        return f"""<html><body style="font-family:'맑은 고딕',sans-serif; padding:20px;">
        <div style="border:2px solid #333; padding:24px;">
        <h1 style="text-align:center; border-bottom:3px double #333; padding-bottom:12px; margin-bottom:20px;">거 래 명 세 서</h1>
        <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
            <tr>
                <th style="background:#f0f0f0; padding:8px; border:1px solid #ddd; width:15%;">발행일</th>
                <td style="padding:8px; border:1px solid #ddd; width:35%;">{now}</td>
                <th style="background:#f0f0f0; padding:8px; border:1px solid #ddd; width:15%;">공급받는자</th>
                <td style="padding:8px; border:1px solid #ddd; width:35%; font-weight:bold;">{client_name}</td>
            </tr>
            <tr>
                <th style="background:#f0f0f0; padding:8px; border:1px solid #ddd;">행사명</th>
                <td style="padding:8px; border:1px solid #ddd;" colspan="3">{project_name}</td>
            </tr>
            <tr>
                <th style="background:#f0f0f0; padding:8px; border:1px solid #ddd;">행사일</th>
                <td style="padding:8px; border:1px solid #ddd;" colspan="3">{date_str}</td>
            </tr>
        </table>

        <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
            <thead>
                <tr style="background:#2563eb; color:white;">
                    <th style="padding:8px; border:1px solid #ddd; width:8%;">No</th>
                    <th style="padding:8px; border:1px solid #ddd;">품목</th>
                    <th style="padding:8px; border:1px solid #ddd; width:10%;">수량</th>
                    <th style="padding:8px; border:1px solid #ddd; width:15%;">단가</th>
                    <th style="padding:8px; border:1px solid #ddd; width:10%;">일수</th>
                    <th style="padding:8px; border:1px solid #ddd; width:18%;">금액</th>
                </tr>
            </thead>
            <tbody>
                {item_rows}
            </tbody>
        </table>

        <table style="width:100%; border-collapse:collapse;">
            <tr>
                <th style="background:#f0f0f0; padding:10px; border:1px solid #ddd; width:25%;">공급가액</th>
                <td style="padding:10px; border:1px solid #ddd; text-align:right; width:25%;">{amount:,}원</td>
                <th style="background:#f0f0f0; padding:10px; border:1px solid #ddd; width:25%;">부가세(10%)</th>
                <td style="padding:10px; border:1px solid #ddd; text-align:right; width:25%;">{vat:,}원</td>
            </tr>
            <tr>
                <th style="background:#1e40af; color:white; padding:12px; border:1px solid #ddd;" colspan="2">합 계</th>
                <td style="padding:12px; border:1px solid #ddd; text-align:right; font-size:18px; font-weight:bold; color:#1e40af;" colspan="2">{amount_vat:,}원</td>
            </tr>
        </table>
        </div>
        </body></html>"""

    def get_payslip_html(self, staff_name, project_name, pay, days, total, tax_rate=0.033):
        """급여명세서 HTML — tax_rate: 0.033 (3.3%) 또는 0.009 (0.9%)"""
        tax_rate = float(tax_rate) if tax_rate else 0.033
        tax = int(total * tax_rate)
        net = total - tax
        tax_pct = f"{tax_rate * 100:.1f}%"
        tax_label = "소득세(3.3%)" if abs(tax_rate - 0.033) < 0.001 else f"원천징수({tax_pct})"
        return f"""<html><body style="font-family:'맑은 고딕',sans-serif; padding:16px;">
        <div style="border:2px solid #333; padding:20px;">
        <h2 style="text-align:center; border-bottom:2px solid #333; padding-bottom:8px;">급여명세서</h2>
        <table style="width:100%; border-collapse:collapse; margin:12px 0;">
            <tr>
                <th style="background:#f0f0f0; padding:8px; border:1px solid #ddd; width:25%;">성명</th>
                <td style="padding:8px; border:1px solid #ddd; font-weight:bold;">{staff_name}</td>
            </tr>
            <tr>
                <th style="background:#f0f0f0; padding:8px; border:1px solid #ddd;">프로젝트</th>
                <td style="padding:8px; border:1px solid #ddd;">{project_name}</td>
            </tr>
        </table>
        <table style="width:100%; border-collapse:collapse; margin:12px 0;">
            <tr style="background:#2563eb; color:white;">
                <th style="padding:8px; border:1px solid #ddd;">항목</th>
                <th style="padding:8px; border:1px solid #ddd;">내용</th>
                <th style="padding:8px; border:1px solid #ddd; text-align:right;">금액</th>
            </tr>
            <tr>
                <td style="padding:8px; border:1px solid #ddd;">기본급</td>
                <td style="padding:8px; border:1px solid #ddd;">{pay:,}원 × {days}일</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{total:,}원</td>
            </tr>
            <tr style="color:#dc2626;">
                <td style="padding:8px; border:1px solid #ddd;">공제</td>
                <td style="padding:8px; border:1px solid #ddd;">{tax_label}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">-{tax:,}원</td>
            </tr>
        </table>
        <div style="background:#1e40af; color:white; padding:14px; text-align:right; border-radius:4px; margin-top:12px;">
            <span style="font-size:14px;">실 수령액</span>
            <span style="font-size:22px; font-weight:bold; margin-left:12px;">{net:,}원</span>
        </div>
        </div></body></html>"""