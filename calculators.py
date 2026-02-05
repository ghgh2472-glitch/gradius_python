"""calculators.py
자동 계산 엔진: 견적, 수익률, 급여 자동 계산
"""
from utils import safe_int
from datetime import datetime
from typing import Dict, List, Tuple


class EstimateCalculator:
    """견적 자동 계산"""
    
    @staticmethod
    def calc_supply_price(items: List[Dict]) -> int:
        """품목별 수량 × 단가 합산"""
        total = 0
        for item in items:
            qty = safe_int(item.get('수량', 0))
            price = safe_int(item.get('매출단가', 0))
            total += qty * price
        return total
    
    @staticmethod
    def calc_total_with_tax(supply_price: int, vat_included: bool = False) -> Tuple[int, int, int]:
        """공급가액 → 부가세 → 합계금액 계산
        
        Returns:
            (공급가액, 부가세, 합계금액)
        """
        supply = safe_int(supply_price)
        
        if vat_included:
            # 합계금액 = 공급가액 × 1.1 형태로 입력된 경우
            total = supply
            vat = total - int(total / 1.1)
            supply = int(total / 1.1)
        else:
            # 공급가액 먼저, 부가세는 10% 별도
            vat = int(supply * 0.1)
            total = supply + vat
        
        return supply, vat, total
    
    @staticmethod
    def calc_margin(supply: int, cost: int) -> Tuple[int, float]:
        """수익 및 수익률 계산
        
        Returns:
            (수익, 수익률%)
        """
        supply = safe_int(supply)
        cost = safe_int(cost)
        profit = supply - cost
        margin = (profit / supply * 100) if supply > 0 else 0.0
        return profit, round(margin, 1)


class SalaryCalculator:
    """급여 자동 계산"""
    
    @staticmethod
    def calc_staff_salary(assign_records: List[Dict], hourly: bool = False) -> Dict:
        """배정기록 기반 급여 계산
        
        Args:
            assign_records: [{'이름': str, '일수': int, '단가': int, ...}, ...]
            hourly: True면 시간 단위, False면 일 단위
        
        Returns:
            {
                '이름': 급여,
                ...
            }
        """
        salary_map = {}
        
        for record in assign_records:
            name = record.get('이름', '').strip()
            if not name:
                continue
            
            # 일수 또는 시간
            units = safe_int(record.get('일수' if not hourly else '시간', 0))
            # 단가 (일당 또는 시간당)
            rate = safe_int(record.get('단가', 0))
            
            # 상태 확인 (취소된 항목 제외)
            status = record.get('상태', '').strip()
            if status in ('취소', '보류'):
                continue
            
            pay = units * rate
            salary_map[name] = salary_map.get(name, 0) + pay
        
        return salary_map
    
    @staticmethod
    def calc_team_salary_sheet(assignments: List[Dict], by_role: bool = False) -> Dict:
        """팀 전체 급여 현황 (역할별 또는 전체)
        
        Returns:
            {
                '역할': {'인원': int, '총지급': int},
                ...
            }
        """
        result = {}
        
        for record in assignments:
            status = record.get('상태', '').strip()
            if status in ('취소', '보류'):
                continue
            
            key = record.get('역할', '기타') if by_role else '전체'
            pay = safe_int(record.get('총지급액', 0))
            
            if key not in result:
                result[key] = {'인원': 0, '총지급': 0}
            
            result[key]['인원'] += 1
            result[key]['총지급'] += pay
        
        return result


class InvoiceCalculator:
    """청구서/세금계산서 자동 계산"""
    
    @staticmethod
    def aggregate_monthly(contracts: List[Dict], year: int, month: int) -> Dict:
        """월별 계약 집계 (고객별)
        
        Returns:
            {
                '고객명': {
                    '건수': int,
                    '공급가액': int,
                    '부가세': int,
                    '합계': int,
                    '계약들': [...]
                },
                ...
            }
        """
        by_client = {}
        
        for contract in contracts:
            # 계약일 필터링
            contract_date = contract.get('계약일', '').strip()
            if not contract_date:
                continue
            
            try:
                dt = datetime.strptime(contract_date, '%Y-%m-%d')
                if dt.year != year or dt.month != month:
                    continue
            except ValueError:
                continue
            
            # 상태 필터링 (완료된 것만)
            status = contract.get('상태', '').strip()
            if status not in ('계약완료', '정산완료'):
                continue
            
            client = contract.get('업체명', '').strip()
            if not client:
                client = '미정'
            
            supply = safe_int(contract.get('공급가액', 0))
            vat = safe_int(contract.get('부가세', 0))
            total = safe_int(contract.get('합계금액', 0))
            
            if client not in by_client:
                by_client[client] = {
                    '건수': 0,
                    '공급가액': 0,
                    '부가세': 0,
                    '합계': 0,
                    '계약들': []
                }
            
            by_client[client]['건수'] += 1
            by_client[client]['공급가액'] += supply
            by_client[client]['부가세'] += vat
            by_client[client]['합계'] += total
            by_client[client]['계약들'].append(contract)
        
        return by_client
    
    @staticmethod
    def calc_tax_due(supply_price: int, tax_type: str = '부가세') -> Dict:
        """납부 세금 계산
        
        Args:
            supply_price: 공급가액
            tax_type: '부가세' (10%) | '소득세' (3.3%) | ...
        
        Returns:
            {'세금명': '부가세', '세율': 10, '금액': int}
        """
        supply = safe_int(supply_price)
        
        tax_rates = {
            '부가세': 10,
            '소득세': 3.3,
            '지방세': 0.4,
        }
        
        rate = tax_rates.get(tax_type, 10)
        amount = int(supply * (rate / 100))
        
        return {
            '세금명': tax_type,
            '세율': rate,
            '금액': amount,
        }


class ValidationEngine:
    """입력값 검증"""
    
    @staticmethod
    def validate_inquiry(data: Dict) -> Tuple[bool, List[str]]:
        """문의 데이터 검증"""
        errors = []
        
        if not data.get('업체명', '').strip():
            errors.append("업체명 필수")
        if not data.get('행사명', '').strip():
            errors.append("행사명 필수")
        if not data.get('연락처', '').strip():
            errors.append("연락처 필수")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_estimate(data: Dict) -> Tuple[bool, List[str]]:
        """견적 데이터 검증"""
        errors = []
        
        if not data.get('문의ID', '').strip():
            errors.append("문의ID 필수")
        if safe_int(data.get('공급가액', 0)) <= 0:
            errors.append("공급가액은 0보다 커야함")
        
        # 수익률 확인 (마이너스 수익은 경고)
        supply = safe_int(data.get('공급가액', 0))
        cost = safe_int(data.get('매입원가', 0))
        if cost > supply:
            errors.append("매입원가가 공급가액보다 클 수 없음")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_assignment(data: Dict) -> Tuple[bool, List[str]]:
        """배정 데이터 검증"""
        errors = []
        
        if not data.get('이름', '').strip():
            errors.append("직원 이름 필수")
        if not data.get('역할', '').strip():
            errors.append("역할 필수")
        if safe_int(data.get('일수', 0)) <= 0:
            errors.append("일수는 0보다 커야함")
        if safe_int(data.get('단가', 0)) < 0:
            errors.append("단가는 0 이상이어야 함")
        
        return len(errors) == 0, errors
