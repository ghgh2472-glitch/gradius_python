# create_dispatch_sheets.py
"""
인력파견 시스템 필수 시트 생성 및 초기화 함수
- 인력배정 시트 (인력배정 상세)
- 출석부 시트 (일일 출퇴근 기록)
- 평가표 시트 (현장 만족도 평가)
- 지급내역 시트 (급여 계산)
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import auth
import streamlit as st
from datetime import datetime

SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_connection():
    """Google Sheets 연결"""
    try:
        try:
            st_secrets = st.secrets
        except Exception:
            st_secrets = None
        
        client = auth.get_gspread_client(secrets_path="secrets.json", st_secrets=st_secrets, scopes=SCOPES)
        return client
    except Exception as e:
        print(f"❌ 구글 인증 실패: {e}")
        return None


def create_assignment_sheet():
    """
    인력배정 시트 생성
    
    컬럼:
    1. 배정ID (자동생성: A-YYMMDD-XXXXXX)
    2. 문의ID (조회용)
    3. 현장명 (자동입력)
    4. 인력명 (검색/선택)
    5. 성별 (자동입력)
    6. 나이 (자동입력)
    7. 직급 (자동입력)
    8. 직무/역할 (선택: 사회자/진행자/보조진행자/스태프/기술담당 등)
    9. 파견기간 (YYYY-MM-DD ~ YYYY-MM-DD)
    10. 파견일수
    11. 기본시급 (자동입력)
    12. 추가수당 (수동입력)
    13. 예상급여 (자동계산)
    14. 배정상태 (배정중/확정/취소)
    15. 배정담당자
    16. 배정일시
    17. 비고
    """
    client = get_connection()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # 기존 시트 확인
        try:
            wks = sh.worksheet("인력배정")
            print("✅ 인력배정 시트가 이미 존재합니다.")
            return True
        except gspread.exceptions.WorksheetNotFound:
            # 시트 생성
            headers = [
                "배정ID",
                "문의ID",
                "현장명",
                "인력명",
                "성별",
                "나이",
                "직급",
                "직무",
                "파견기간",
                "파견일수",
                "기본시급",
                "추가수당",
                "예상급여",
                "배정상태",
                "배정담당자",
                "배정일시",
                "비고"
            ]
            
            wks = sh.add_worksheet(title="인력배정", rows=2000, cols=len(headers))
            wks.update('A1', [headers], value_input_option='RAW')
            
            # 기본 스타일 (첫 행을 헤더로 표시)
            wks.format('A1:Q1', {
                "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })
            
            print("✅ 인력배정 시트가 생성되었습니다.")
            return True
            
    except Exception as e:
        print(f"❌ 인력배정 시트 생성 실패: {e}")
        return False


def create_attendance_sheet():
    """
    출석부 시트 생성
    
    컬럼:
    1. 배정ID (조회용)
    2. 인력명
    3. 출석날짜 (YYYY-MM-DD)
    4. 출근시간 (HH:MM)
    5. 퇴근시간 (HH:MM)
    6. 실제근무시간 (시간:분, 자동계산)
    7. 휴무사유 (있을 경우)
    8. 출석상태 (정상/지각/조퇴/결근)
    9. 기록자
    10. 기록일시
    11. 비고
    """
    client = get_connection()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # 기존 시트 확인
        try:
            wks = sh.worksheet("출석부")
            print("✅ 출석부 시트가 이미 존재합니다.")
            return True
        except gspread.exceptions.WorksheetNotFound:
            # 시트 생성
            headers = [
                "배정ID",
                "인력명",
                "출석날짜",
                "출근시간",
                "퇴근시간",
                "실제근무시간",
                "휴무사유",
                "출석상태",
                "기록자",
                "기록일시",
                "비고"
            ]
            
            wks = sh.add_worksheet(title="출석부", rows=3000, cols=len(headers))
            wks.update('A1', [headers], value_input_option='RAW')
            
            # 기본 스타일
            wks.format('A1:K1', {
                "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.2},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })
            
            print("✅ 출석부 시트가 생성되었습니다.")
            return True
            
    except Exception as e:
        print(f"❌ 출석부 시트 생성 실패: {e}")
        return False


def create_evaluation_sheet():
    """
    평가표 시트 생성
    
    컬럼:
    1. 평가ID (자동생성: E-YYMMDD-XXXXXX)
    2. 배정ID
    3. 인력명
    4. 현장명
    5. 근태 (5점: 매우불만족(1) ~ 매우만족(5))
    6. 수행력 (5점)
    7. 태도/소통 (5점)
    8. 의사소통 (5점)
    9. 현장적응 (5점)
    10. 총점 (자동계산: 평균)
    11. 평가등급 (자동계산: 5점 이상=A, 4점 이상=B, 3점 이상=C, 이하=D)
    12. 평가자 (현장담당자)
    13. 평가일시
    14. 강점 (텍스트)
    15. 개선점 (텍스트)
    16. 추천여부 (Yes/No)
    17. 비고
    """
    client = get_connection()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # 기존 시트 확인
        try:
            wks = sh.worksheet("평가표")
            print("✅ 평가표 시트가 이미 존재합니다.")
            return True
        except gspread.exceptions.WorksheetNotFound:
            # 시트 생성
            headers = [
                "평가ID",
                "배정ID",
                "인력명",
                "현장명",
                "근태",
                "수행력",
                "태도",
                "의사소통",
                "현장적응",
                "총점",
                "평가등급",
                "평가자",
                "평가일시",
                "강점",
                "개선점",
                "재추천",
                "비고"
            ]
            
            wks = sh.add_worksheet(title="평가표", rows=2000, cols=len(headers))
            wks.update('A1', [headers], value_input_option='RAW')
            
            # 기본 스타일
            wks.format('A1:Q1', {
                "backgroundColor": {"red": 0.6, "green": 0.2, "blue": 0.2},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })
            
            print("✅ 평가표 시트가 생성되었습니다.")
            return True
            
    except Exception as e:
        print(f"❌ 평가표 시트 생성 실패: {e}")
        return False


def create_payment_sheet():
    """
    지급내역 시트 생성
    
    컬럼:
    1. 지급ID (자동생성: P-YYMMDD-XXXXXX)
    2. 배정ID
    3. 인력명
    4. 현장명
    5. 파견기간
    6. 파견일수
    7. 기본급 (기본시급 × 근무시간)
    8. 야근비 (초과근무 시급 × 초과시간)
    9. 식사비 (현장 제공 여부에 따라)
    10. 교통비 (일정액 또는 실비)
    11. 보너스 (현장평가 기반)
    12. 소계 (7+8+9+10+11)
    13. 세금공제 (지방소득세 등)
    14. 최종지급액 (12-13)
    15. 지급상태 (대기/확정/완료/반품)
    16. 지급일
    17. 지급담당자
    18. 비고
    """
    client = get_connection()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # 기존 시트 확인
        try:
            wks = sh.worksheet("지급내역")
            print("✅ 지급내역 시트가 이미 존재합니다.")
            return True
        except gspread.exceptions.WorksheetNotFound:
            # 시트 생성
            headers = [
                "지급ID",
                "배정ID",
                "인력명",
                "현장명",
                "파견기간",
                "파견일수",
                "기본급",
                "야근비",
                "식사비",
                "교통비",
                "보너스",
                "소계",
                "세금공제",
                "최종지급액",
                "지급상태",
                "지급일",
                "지급담당자",
                "비고"
            ]
            
            wks = sh.add_worksheet(title="지급내역", rows=2000, cols=len(headers))
            wks.update('A1', [headers], value_input_option='RAW')
            
            # 기본 스타일
            wks.format('A1:R1', {
                "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.6},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })
            
            print("✅ 지급내역 시트가 생성되었습니다.")
            return True
            
    except Exception as e:
        print(f"❌ 지급내역 시트 생성 실패: {e}")
        return False


def init_all_dispatch_sheets():
    """
    모든 인력파견 시트 일괄 생성 초기화
    """
    print("\n" + "="*60)
    print("🚀 인력파견 시스템 시트 생성 시작...")
    print("="*60)
    
    results = {
        "인력배정": create_assignment_sheet(),
        "출석부": create_attendance_sheet(),
        "평가표": create_evaluation_sheet(),
        "지급내역": create_payment_sheet()
    }
    
    print("\n" + "="*60)
    print("📊 생성 결과:")
    print("="*60)
    for sheet_name, success in results.items():
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{sheet_name}: {status}")
    
    all_success = all(results.values())
    print("="*60 + "\n")
    
    return all_success


if __name__ == "__main__":
    # 테스트용
    success = init_all_dispatch_sheets()
    if success:
        print("🎉 모든 시트가 성공적으로 생성되었습니다!")
    else:
        print("⚠️ 일부 시트 생성에 실패했습니다.")
