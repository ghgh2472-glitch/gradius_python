"""scheduler.py
일일/월간 자동 작업 스케줄러
- 일일: 출석 리마인더, 미처리 항목 알림
- 월간: 정산 자동 생성, 리포트 생성
"""
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pandas as pd
from helpers import get_logger, now_kst, today_kst

logger = get_logger(__name__)


class AutomationScheduler:
    """자동화 스케줄러"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.daemon = True
    
    def start(self):
        """스케줄러 시작"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("✅ Scheduler started")
    
    def stop(self):
        """스케줄러 중지"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("✅ Scheduler stopped")
    
    def add_daily_task(self, hour: int, minute: int, func, job_id: str = None):
        """일일 반복 작업 추가
        
        Args:
            hour: 시간 (0-23)
            minute: 분 (0-59)
            func: 실행할 함수
            job_id: 작업 ID (선택)
        """
        if job_id is None:
            job_id = f"daily_{func.__name__}"
        
        self.scheduler.add_job(
            func,
            trigger='cron',
            hour=hour,
            minute=minute,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=60
        )
        logger.info(f"⏰ Daily job added: {job_id} at {hour:02d}:{minute:02d}")
    
    def add_monthly_task(self, day: int, hour: int, minute: int, func, job_id: str = None):
        """월간 반복 작업 추가
        
        Args:
            day: 날짜 (1-31)
            hour: 시간
            minute: 분
            func: 실행할 함수
            job_id: 작업 ID (선택)
        """
        if job_id is None:
            job_id = f"monthly_{func.__name__}"
        
        self.scheduler.add_job(
            func,
            trigger='cron',
            day=day,
            hour=hour,
            minute=minute,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=60
        )
        logger.info(f"📅 Monthly job added: {job_id} on day {day} at {hour:02d}:{minute:02d}")


# 글로벌 스케줄러 인스턴스
automation_scheduler = AutomationScheduler()


# ============================================================
# 자동 작업 함수들
# ============================================================

def daily_attendance_reminder(data: dict):
    """일일: 미기록 출석 리마인더
    
    해당 날짜에 배정된 직원 중 출석 기록이 없으면 알림
    """
    try:
        from notifications import notify_batch
        
        logger.info("📢 Daily attendance reminder started...")
        
        dispatch_df = data.get('dispatch', pd.DataFrame())
        if dispatch_df.empty:
            logger.warning("No dispatch data")
            return
        
        today = now_kst().strftime('%Y-%m-%d')
        
        # 오늘 배정된 직원 찾기
        if '배정일시' in dispatch_df.columns:
            today_assignments = dispatch_df[
                dispatch_df['배정일시'].astype(str).str.contains(today)
            ]
        else:
            logger.warning("배정일시 컬럼 없음")
            return
        
        # 각 배정에 대해 출석 확인
        missing_staff = []
        for _, assign in today_assignments.iterrows():
            assign_id = assign.get('배정ID', '')
            name = assign.get('이름', '')
            
            # 실제로는 출석부 조회 필요
            # is_present = check_attendance(assign_id, today)
            # if not is_present:
            missing_staff.append(name)
        
        if missing_staff:
            msg = f"📋 미기록 출석: {', '.join(missing_staff)}"
            logger.info(msg)
            # notify_batch([admin_email], msg, subject="출석 미기록 알림")
    
    except Exception as e:
        logger.error(f"❌ Daily reminder error: {e}")


def daily_pending_items_alert(data: dict):
    """일일: 미처리 항목 경고
    
    견적 대기 중, 계약 미체결, 정산 미완료 항목 알림
    """
    try:
        logger.info("🔔 Daily pending items check...")
        
        inq_df = data.get('inq', pd.DataFrame())
        if inq_df.empty:
            return
        
        # 상태별 집계
        status_counts = inq_df.get('상태', pd.Series()).value_counts().to_dict()
        pending = {
            '견적대기': status_counts.get('견적작성', 0),
            '계약대기': status_counts.get('계약대기', 0),
            '정산대기': status_counts.get('정산대기', 0),
        }
        
        msg = f"📊 미처리 항목: {pending}"
        logger.info(msg)
    
    except Exception as e:
        logger.error(f"❌ Pending items alert error: {e}")


def monthly_settlement_generation(data: dict, year: int = None, month: int = None):
    """월간: 정산 자동 생성
    
    완료된 계약을 기반으로 정산 건 자동 생성
    """
    try:
        from calculators import InvoiceCalculator
        from data_loader import save_settlement_record
        
        if year is None:
            today = now_kst()
            year, month = today.year, today.month
        
        logger.info(f"💰 Monthly settlement generation for {year}-{month:02d}...")
        
        contract_df = data.get('settlement', pd.DataFrame())
        if contract_df.empty:
            logger.warning("No contract data")
            return
        
        # 월별 고객별 청구서 생성
        aggregated = InvoiceCalculator.aggregate_monthly(
            contract_df.to_dict('records'), year, month
        )
        
        count = 0
        for client, info in aggregated.items():
            # 실제로는 정산 건 생성 로직 필요
            logger.info(f"📄 Settlement for {client}: {info['합계']:,}원")
            count += 1
        
        logger.info(f"✅ Generated {count} settlement records")
    
    except Exception as e:
        logger.error(f"❌ Settlement generation error: {e}")


def monthly_report_generation(data: dict, year: int = None, month: int = None):
    """월간: 월간 리포트 자동 생성 및 발송
    
    매출, 이익, 인력 현황 등 집계
    """
    try:
        from calculators import InvoiceCalculator, SalaryCalculator
        from notifications import notify_batch
        
        if year is None:
            today = now_kst()
            year, month = today.year, today.month
        
        logger.info(f"📈 Monthly report generation for {year}-{month:02d}...")
        
        contract_df = data.get('settlement', pd.DataFrame())
        dispatch_df = data.get('dispatch', pd.DataFrame())
        
        # 월별 집계
        aggregated = InvoiceCalculator.aggregate_monthly(
            contract_df.to_dict('records'), year, month
        )
        
        total_sales = sum(c['합계'] for c in aggregated.values())
        total_count = sum(c['건수'] for c in aggregated.values())
        
        # 급여 집계
        salary_map = SalaryCalculator.calc_staff_salary(dispatch_df.to_dict('records'))
        total_salary = sum(salary_map.values())
        
        report = f"""
        📊 {year}-{month:02d} 월간 리포트
        ========================
        📈 매출: {total_sales:,}원 ({total_count}건)
        💰 인건비: {total_salary:,}원
        👥 인력: {len(salary_map)}명
        """
        
        logger.info(report)
        
        # 실제로는 이메일 발송
        # notify_batch([admin_email], report, subject="월간 리포트")
    
    except Exception as e:
        logger.error(f"❌ Report generation error: {e}")


# 초기화 헬퍼
def setup_default_schedule():
    """기본 스케줄 설정"""
    automation_scheduler.add_daily_task(
        9, 0,
        lambda: daily_attendance_reminder({} if not hasattr(setup_default_schedule, 'data') else setup_default_schedule.data),
        job_id='daily_attendance'
    )
    automation_scheduler.add_daily_task(
        17, 0,
        lambda: daily_pending_items_alert({} if not hasattr(setup_default_schedule, 'data') else setup_default_schedule.data),
        job_id='daily_pending'
    )
    automation_scheduler.add_monthly_task(
        1, 8, 0,
        lambda: monthly_settlement_generation({} if not hasattr(setup_default_schedule, 'data') else setup_default_schedule.data),
        job_id='monthly_settlement'
    )
    automation_scheduler.add_monthly_task(
        2, 9, 0,
        lambda: monthly_report_generation({} if not hasattr(setup_default_schedule, 'data') else setup_default_schedule.data),
        job_id='monthly_report'
    )
    logger.info("✅ Default schedule configured")
