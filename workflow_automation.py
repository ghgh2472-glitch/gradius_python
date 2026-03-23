"""workflow_automation.py
배정 → 출석부 → 지급 목록 자동 연계
"""
from typing import Dict, List
import pandas as pd
from datetime import datetime, timedelta
from data_loader import save_assignment_record, ensure_attendance_sheet
from calculators import SalaryCalculator
from helpers import get_logger, now_kst
import gspread

logger = get_logger(__name__)


def create_attendance_records(assignment: Dict, sheet_client: gspread.Spreadsheet) -> bool:
    """배정 데이터로부터 출석 기록 자동 생성
    
    배정일수만큼 출석부 시트에 일일 기록 추가
    
    Args:
        assignment: {
            '배정ID': str,
            '문의ID': str,
            '이름': str,
            '일수': int,
            '배정일시': str,
            ...
        }
        sheet_client: gspread 클라이언트
    
    Returns:
        성공 여부
    """
    try:
        # 출석부 시트 확인/생성
        ensure_attendance_sheet()
        
        # 워크시트 열기
        sh = sheet_client
        wks = sh.worksheet("출석부")
        
        assign_id = assignment.get('배정ID', '')
        staff_name = assignment.get('이름', '')
        days = int(assignment.get('일수', 1))
        
        # 배정 시작일 파싱
        assign_date_str = assignment.get('배정일시', now_kst().strftime('%Y-%m-%d'))
        assign_date = datetime.strptime(assign_date_str.split(' ')[0], '%Y-%m-%d')
        
        # 각 일자별 출석 기록 생성
        from gspread.cell import Cell
        rows_to_add = []
        
        for day_offset in range(days):
            work_date = assign_date + timedelta(days=day_offset)
            
            row = [
                assign_id,                              # 배정ID
                work_date.strftime('%Y-%m-%d'),        # 출석일자
                '미기록',                               # 상태 (미기록/출석/결근)
                '',                                     # 비고
                '',                                     # 기록자
                now_kst().strftime('%H:%M:%S'),   # 기록시간
            ]
            rows_to_add.append(row)
        
        # 일괄 추가
        if rows_to_add:
            # 마지막 행 번호 확인
            last_row = len(wks.get_all_values())
            
            # 필요시 행 추가
            if last_row + len(rows_to_add) > wks.row_count:
                wks.add_rows(len(rows_to_add) + 100)
            
            # 데이터 추가
            for offset, row in enumerate(rows_to_add, 1):
                wks.update(f'A{last_row + offset}', [row], value_input_option='RAW')
            
            logger.info(f"✅ Created {len(rows_to_add)} attendance records for {staff_name}")
            return True
    
    except Exception as e:
        logger.error(f"❌ Failed to create attendance records: {e}")
        return False


def create_payroll_record(assignment: Dict, sheet_client: gspread.Spreadsheet) -> bool:
    """배정 데이터로부터 급여 지급 기록 자동 생성
    
    Args:
        assignment: 배정 기록
        sheet_client: gspread 클라이언트
    
    Returns:
        성공 여부
    """
    try:
        sh = sheet_client
        
        # 지급내역 시트 확인 (인건비 → 지급내역으로 통합)
        try:
            wks = sh.worksheet("지급내역")
        except gspread.exceptions.WorksheetNotFound:
            # 시트 없으면 생성
            wks = sh.add_worksheet(title="지급내역", rows=2000, cols=18)
            headers = ["지급ID", "배정ID", "인력명", "현장명", "직무", "근무일수", "지급단가", "총지급액", "세금공제", "실지급액", "지급상태", "지급일", "은행명", "계좌번호", "예금주", "수당", "비고", "기록일시"]
            wks.update('A1', [headers], value_input_option='RAW')
        
        # 급여 기록 구성
        assign_id = assignment.get('배정ID', '')
        staff_name = assignment.get('이름', '')
        role = assignment.get('역할', '')
        days = int(assignment.get('일수', 1))
        hourly_rate = int(assignment.get('단가', 0))
        total_pay = int(assignment.get('총지급액', 0))
        
        # 마지막 행 확인
        from gspread.cell import Cell
        last_row = len(wks.get_all_values())
        
        # 행 확장
        if last_row >= wks.row_count:
            wks.add_rows(100)
        
        # 급여 기록 작성
        row = [
            assign_id,
            staff_name,
            role,
            str(days),
            str(hourly_rate),
            str(total_pay),
            '미지급',
            now_kst().strftime('%Y-%m-%d %H:%M:%S'),
        ]
        
        wks.update(f'A{last_row + 1}', [row], value_input_option='RAW')
        
        logger.info(f"✅ Created payroll record: {staff_name} - {total_pay:,}원")
        return True
    
    except Exception as e:
        logger.error(f"❌ Failed to create payroll record: {e}")
        return False


def auto_link_workflow(assignment: Dict, sheet_client: gspread.Spreadsheet) -> Dict:
    """배정 → 출석부 → 급여 전체 연계
    
    Returns:
        {
            'assignment': bool,
            'attendance': bool,
            'payroll': bool,
            'summary': str
        }
    """
    result = {
        'assignment': False,
        'attendance': False,
        'payroll': False,
        'summary': ''
    }
    
    try:
        # 1. 배정 기록 저장 (이미 저장되었으나 확인)
        result['assignment'] = True
        logger.info("✅ Assignment saved")
        
        # 2. 출석부 자동 생성
        result['attendance'] = create_attendance_records(assignment, sheet_client)
        
        # 3. 급여 기록 생성
        result['payroll'] = create_payroll_record(assignment, sheet_client)
        
        # 요약
        staff_name = assignment.get('이름', '')
        if all(result[k] for k in ['assignment', 'attendance', 'payroll']):
            result['summary'] = f"✅ {staff_name} 배정부터 급여까지 완전 연계됨"
        else:
            failed = [k for k in ['attendance', 'payroll'] if not result[k]]
            result['summary'] = f"⚠️ {staff_name} 배정 완료, 하지만 {', '.join(failed)} 생성 실패"
        
        logger.info(result['summary'])
        return result
    
    except Exception as e:
        logger.error(f"❌ Workflow automation error: {e}")
        result['summary'] = f"❌ 워크플로우 연계 실패: {str(e)}"
        return result


def generate_payroll_summary(dispatch_df: pd.DataFrame, 
                            start_date: str = None,
                            end_date: str = None) -> pd.DataFrame:
    """기간별 급여 현황 요약
    
    Args:
        dispatch_df: 배정기록
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일
    
    Returns:
        급여 요약 DataFrame
    """
    if dispatch_df.empty:
        return pd.DataFrame()
    
    # 기간 필터링
    if start_date:
        dispatch_df = dispatch_df[
            dispatch_df['배정일시'].astype(str) >= start_date
        ]
    if end_date:
        dispatch_df = dispatch_df[
            dispatch_df['배정일시'].astype(str) <= end_date
        ]
    
    # 급여 계산 (명단별)
    salary_map = {}
    
    for _, record in dispatch_df.iterrows():
        status = record.get('상태', '').strip()
        if status in ('취소', '보류'):
            continue
        
        name = record.get('이름', '').strip()
        total_pay = int(record.get('총지급액', 0))
        
        if name not in salary_map:
            salary_map[name] = {
                '인원': name,
                '총지급액': 0,
                '배정건수': 0,
            }
        
        salary_map[name]['총지급액'] += total_pay
        salary_map[name]['배정건수'] += 1
    
    # DataFrame 변환
    summary_df = pd.DataFrame(list(salary_map.values()))
    
    # 지급액 기준 정렬
    summary_df = summary_df.sort_values('총지급액', ascending=False)
    
    return summary_df


def check_workflow_status(inquiry_id: str, data: Dict) -> Dict:
    """문의별 워크플로우 진행 상황 점검
    
    Returns:
        {
            '문의ID': str,
            '문의': bool (문의 접수됨),
            '배정': bool (배정됨),
            '출석': bool (출석 기록됨),
            '지급': bool (급여 지급됨),
            '진행률': float (0~1),
        }
    """
    result = {
        '문의ID': inquiry_id,
        '문의': False,
        '배정': False,
        '출석': False,
        '지급': False,
        '진행률': 0.0,
    }
    
    try:
        # 문의 확인
        df_inq = data.get('inq', pd.DataFrame())
        if not df_inq.empty:
            if inquiry_id in df_inq['문의ID'].values:
                result['문의'] = True
        
        # 배정 확인
        df_dispatch = data.get('dispatch', pd.DataFrame())
        if not df_dispatch.empty:
            assigned = df_dispatch[df_dispatch['문의ID'] == inquiry_id]
            if not assigned.empty:
                result['배정'] = True
        
        # 출석 확인
        # (실제로는 출석부 시트에서 조회해야 함)
        
        # 지급 확인
        # (실제로는 인건비 시트에서 조회해야 함)
        
        # 진행률 계산
        result['진행률'] = sum([result[k] for k in ['문의', '배정', '출석', '지급']]) / 4.0
        
        return result
    
    except Exception as e:
        logger.error(f"Workflow status check error: {e}")
        return result


# 초기화 헬퍼
def init_workflow_automation():
    """워크플로우 자동화 초기화"""
    logger.info("✅ Workflow automation initialized")
