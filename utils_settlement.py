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
    def get_invoice_html(self, client_name, project_name, date_str, amount):
        now = datetime.now().strftime("%Y-%m-%d")
        amount_vat = int(amount * 1.1)
        vat = amount_vat - amount
        return f"""<html><body>
        <h1 style="text-align:center;">거 래 명 세 서</h1>
        <table border="1" style="width:100%; border-collapse:collapse; text-align:center;">
            <tr><th>날짜</th><td>{now}</td><th>공급받는자</th><td>{client_name}</td></tr>
            <tr><th>품목</th><td>{project_name}</td><th>공급가액</th><td>{amount:,}</td></tr>
            <tr><th>세액</th><td>{vat:,}</td><th>합계</th><td><b>{amount_vat:,}</b></td></tr>
        </table></body></html>"""

    def get_payslip_html(self, staff_name, project_name, pay, days, total):
        tax = int(total * 0.033)
        net = total - tax
        return f"""<html><body>
        <h2 style="text-align:center;">급여명세서 ({staff_name})</h2>
        <div style="border:1px solid #ccc; padding:20px;">
            <p><b>프로젝트:</b> {project_name}</p>
            <p><b>지급내역:</b> {pay:,}원 x {days}일 = {total:,}원</p>
            <p><b>공제내역:</b> 소득세(3.3%) -{tax:,}원</p>
            <hr>
            <h3 style="text-align:right; color:blue;">실 수령액: {net:,}원</h3>
        </div></body></html>"""