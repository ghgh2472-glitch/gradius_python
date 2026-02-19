"""
format_sheets.py
================
Google Sheets 서식 개선 스크립트
- 데이터/헤더 텍스트는 절대 변경하지 않음
- 순수 시각적 서식만 적용 (프로그램 동작에 영향 없음)

적용 항목:
1. 헤더 행 서식 (진한 배경 + 흰색 볼드 텍스트)
2. 헤더 행 고정 (freeze)
3. 열 너비 최적화
4. 숫자/날짜 서식
5. 조건부 서식 (상태 컬럼 색상)
6. 테두리
7. 교대 행 색상
8. 자동 필터
9. 탭 색상
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import auth
import time
import sys

SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


def get_connection():
    client = auth.get_gspread_client(secrets_path="secrets.json", st_secrets=None, scopes=SCOPES)
    return client


# =====================================================
# 색상 & 유틸리티
# =====================================================

def rgb(r, g, b):
    """0-255 RGB → 0-1 Google Sheets API 형식"""
    return {"red": r / 255, "green": g / 255, "blue": b / 255}

# 시트별 테마 색상 (헤더 배경)
THEME = {
    "문의작성":           {"header_bg": rgb(30, 64, 175),   "tab": rgb(30, 64, 175)},     # 진한파랑
    "STAFF":             {"header_bg": rgb(109, 40, 217),  "tab": rgb(109, 40, 217)},    # 보라
    "고객정보":           {"header_bg": rgb(14, 116, 144),  "tab": rgb(14, 116, 144)},    # 청록
    "견적상세":           {"header_bg": rgb(161, 98, 7),    "tab": rgb(161, 98, 7)},      # 황금
    "배정기록":           {"header_bg": rgb(21, 128, 61),   "tab": rgb(21, 128, 61)},     # 초록
    "계약건은청구금액적기": {"header_bg": rgb(190, 24, 93),   "tab": rgb(190, 24, 93)},     # 핑크
    "출석부":            {"header_bg": rgb(37, 99, 235),   "tab": rgb(37, 99, 235)},     # 파랑
    "평가표":            {"header_bg": rgb(220, 38, 38),   "tab": rgb(220, 38, 38)},     # 빨강
    "지급내역":           {"header_bg": rgb(5, 150, 105),   "tab": rgb(5, 150, 105)},     # 민트
    "Roles":            {"header_bg": rgb(75, 85, 99),    "tab": rgb(75, 85, 99)},      # 회색
    "Factors":          {"header_bg": rgb(75, 85, 99),    "tab": rgb(107, 114, 128)},   # 회색
    "Guides":           {"header_bg": rgb(75, 85, 99),    "tab": rgb(156, 163, 175)},   # 연회색
}

# 교대 행 색상 (연한 색)
ALT_ROW_COLOR = rgb(248, 250, 252)   # 매우 연한 회색 (#F8FAFC)
WHITE = rgb(255, 255, 255)
HEADER_TEXT = rgb(255, 255, 255)      # 흰색

# 테두리 스타일
THIN_BORDER = {"style": "SOLID", "colorStyle": {"rgbColor": rgb(229, 231, 235)}}       # #E5E7EB
MEDIUM_BORDER = {"style": "SOLID_MEDIUM", "colorStyle": {"rgbColor": rgb(156, 163, 175)}}  # #9CA3AF


# =====================================================
# 열 너비 설정 (시트별)
# =====================================================

# 너비 프리셋 (픽셀)
W_ID = 110       # ID 컬럼
W_NAME = 90      # 이름
W_DATE = 100     # 날짜
W_DATETIME = 140 # 날짜시간
W_PHONE = 115    # 전화번호
W_STATUS = 80    # 상태
W_MONEY = 100    # 금액
W_TEXT = 130     # 일반 텍스트
W_LONG = 200     # 긴 텍스트 (주소, 메모)
W_SHORT = 60     # 짧은 값 (성별, 나이)
W_MED = 90       # 중간 (직무 등)
W_NUM = 70       # 숫자

COLUMN_WIDTHS = {
    "문의작성": [
        W_ID,        # 문의ID
        W_DATETIME,  # 작성일
        W_TEXT,      # 업체명
        W_NAME,      # 담당자
        W_PHONE,     # 연락처
        W_TEXT,      # 행사명
        W_LONG,      # 장소
        W_DATE,      # 행사시작일
        W_DATE,      # 행사종료일
        W_MED,       # 행사시간
        W_MED,       # 서비스카테고리
        W_SHORT,     # 필요인력
        W_SHORT,     # 나이
        W_STATUS,    # 상태
        W_LONG,      # 특이사항
        W_TEXT,      # 비고
        W_SHORT,     # 만족도
        W_SHORT,     # 관고
        W_SHORT,     # 구분
        W_MED,       # 진행담당
        W_STATUS,    # 진행상태
        W_MED,       # 인력배팅현황
        W_LONG,      # 상담내용및고객반응
    ],
    "STAFF": [
        W_ID,        # StaffID
        W_NAME,      # 이름
        W_SHORT,     # 성별
        W_DATE,      # 생년월일
        W_SHORT,     # 나이
        W_MED,       # 경력
        W_PHONE,     # 연락처
        W_TEXT,      # 이동가능지역
        W_TEXT,      # 가능직무
        W_MED,       # 학력
        W_SHORT,     # 키
        W_SHORT,     # 영어
        W_MED,       # 이전
        W_NAME,      # 추천자
        W_SHORT,     # 근태
        W_SHORT,     # 수행
        W_SHORT,     # 인용
        W_SHORT,     # 네트워크
        W_SHORT,     # 총점
        W_TEXT,      # 사진URL
        W_TEXT,      # 현장이력
        W_LONG,      # 총평
        W_LONG,      # 메모
        W_TEXT,      # 주민등록번호
        W_MED,       # 은행명
        W_TEXT,      # 계좌번호
    ],
    "고객정보": [
        W_TEXT,      # 업체명
        W_NAME,      # 대표자명
        W_TEXT,      # 사업자등록번호
        W_STATUS,    # 상태
        W_MED,       # 종목
        W_LONG,      # 사업자주소
        W_LONG,      # 담당계산서이메일
        W_NAME,      # 해당담당
        W_PHONE,     # 해당담당연락처
        W_LONG,      # 메모
    ],
    "견적상세": [
        W_ID,        # 견적ID
        W_ID,        # 문의ID
        W_TEXT,      # 업체명
        W_TEXT,      # 행사명
        W_MONEY,     # 공급가액
        W_MONEY,     # 부가세
        W_MONEY,     # 합계금액
        W_MONEY,     # 매입원가
        W_MONEY,     # 부대비용
        W_MONEY,     # 예상수익
        W_TEXT,      # 사업자번호
        W_NUM,       # 수익률
        W_NAME,      # 대표자
        W_NAME,      # 담당자명
        W_PHONE,     # 연락처
        W_DATETIME,  # 기록일시
        W_TEXT,      # 현장명
        W_NAME,      # 책임자
        W_LONG,      # 현장주소
    ],
    "배정기록": [
        W_ID,        # 배정ID
        W_ID,        # 문의ID
        W_TEXT,      # 행사명
        W_NAME,      # 인력명
        W_MED,       # 구분(본사/외부)
        W_MED,       # 직무
        W_PHONE,     # 연락처
        W_TEXT,      # 주민등록번호
        W_MED,       # 은행명
        W_TEXT,      # 계좌번호
        W_MONEY,     # 지급단가
        W_NUM,       # 근무일수
        W_MONEY,     # 총지급액
        W_STATUS,    # 지급상태
        W_DATETIME,  # 배정일시
    ],
    "계약건은청구금액적기": [
        W_ID,        # 문의ID
        W_TEXT,      # 현장명
        W_TEXT,      # 업체
        W_NAME,      # 책임자
        W_LONG,      # 현장주소
        W_DATE,      # 파견일자
        W_MONEY,     # 청구금액
        W_MONEY,     # 공급가액
        W_MONEY,     # 부가세
        W_MONEY,     # 받을금액
        W_MONEY,     # 세금
        W_STATUS,    # 진행상황
        W_NAME,      # 담당담당
        W_TEXT,      # 담당계산서/발행담당
        W_MONEY,     # 지급금
        W_DATE,      # 계산서등록일
        W_NUM,       # 3.3%
        W_SHORT,     # 구분
        W_LONG,      # 비고
        W_SHORT,     # (빈)
        W_MED,       # 국비부
        W_MED,       # 기본정보
        W_TEXT,      # 사업자번호
        W_NAME,      # 대표자
        W_LONG,      # 이메일
        W_TEXT,      # 법인명
    ],
    "출석부": [
        W_ID,        # 기록ID / 배정ID
        W_ID,        # 배정ID / 인력명  
        W_ID,        # 문의ID / 출석날짜
        W_NAME,      # 인력명
        W_DATE,      # 출석날짜
        W_MED,       # 출근시간
        W_MED,       # 퇴근시간
        W_MED,       # 근무시간
        W_MONEY,     # 일급여
        W_STATUS,    # 출석상태
        W_TEXT,      # 사유
        W_TEXT,      # 비고
        W_DATETIME,  # 기록일시
    ],
    "평가표": [
        W_ID,        # 평가ID
        W_ID,        # 배정ID
        W_NAME,      # 인력명
        W_TEXT,      # 현장명
        W_SHORT,     # 근태
        W_SHORT,     # 수행
        W_SHORT,     # 외모/태도
        W_SHORT,     # 팀워크/의사소통
        W_SHORT,     # 현장적응
        W_SHORT,     # 총점
        W_SHORT,     # 평가등급
        W_NAME,      # 평가자
        W_DATETIME,  # 평가일시
        W_LONG,      # 강점
        W_LONG,      # 개선점
        W_SHORT,     # 재추천
        W_LONG,      # 비고
    ],
    "지급내역": [
        W_ID,        # 지급ID
        W_ID,        # 배정ID
        W_NAME,      # 인력명
        W_TEXT,      # 현장명
        W_DATE,      # 파견기간
        W_NUM,       # 파견일수
        W_MONEY,     # 기본급
        W_MONEY,     # 야근비
        W_MONEY,     # 식사비
        W_MONEY,     # 교통비
        W_MONEY,     # 보너스
        W_MONEY,     # 소계
        W_MONEY,     # 세금공제
        W_MONEY,     # 최종지급액
        W_STATUS,    # 지급상태
        W_DATE,      # 지급일
        W_NAME,      # 지급담당자
        W_LONG,      # 비고
    ],
    "Roles": [
        W_ID,        # role_id
        W_TEXT,      # 직무명
        W_MONEY,     # 기본단가
        W_NUM,       # 기본시간
        W_MONEY,     # 청구추가수당
        W_MED,       # 시간유형
        W_MONEY,     # 야외가산
        W_MONEY,     # 야간수당
        W_MONEY,     # 지급단가
        W_MONEY,     # 지급추가수당
        W_LONG,      # 비고
    ],
    "Factors": [
        W_ID,        # role_id
        W_ID,        # factor_id
        W_TEXT,      # 체크항목
        W_LONG,      # 상세설명
        W_MONEY,     # 추가금액
        W_MONEY,     # 지급추가기금
        W_LONG,      # 추가설명
    ],
    "Guides": [
        W_ID,        # role_id
        W_LONG,      # 상담포인트
        W_MONEY,     # 시장평균가
        W_MONEY,     # 대업체견적가케이스
        W_MONEY,     # 기존청구가케이스
        W_NUM,       # 청구율
        W_LONG,      # 견적멘트
    ],
}

# =====================================================
# 금액/숫자 컬럼 인덱스 (0-based, 시트별)
# =====================================================

MONEY_COLUMNS = {
    "문의작성": [],
    "STAFF": [],
    "고객정보": [],
    "견적상세": [4, 5, 6, 7, 8, 9],      # 공급가액~예상수익
    "배정기록": [10, 12],                 # 지급단가, 총지급액
    "계약건은청구금액적기": [6, 7, 8, 9, 10, 14],  # 청구~세금, 지급금
    "출석부": [8],                        # 일급여
    "평가표": [],
    "지급내역": [6, 7, 8, 9, 10, 11, 12, 13],  # 기본급~최종지급액
    "Roles": [2, 4, 6, 7, 8, 9],         # 단가류
    "Factors": [4, 5],                    # 추가금액, 지급추가기금
    "Guides": [2, 3, 4],                  # 시장평균가~기존청구가
}

DATE_COLUMNS = {
    "문의작성": [7, 8],          # 행사시작일, 행사종료일
    "STAFF": [3],               # 생년월일
    "견적상세": [],
    "배정기록": [],
    "계약건은청구금액적기": [5, 15],  # 파견일자, 계산서등록일
    "출석부": [4],               # 출석날짜
    "지급내역": [15],            # 지급일
}

# =====================================================
# 조건부 서식 — 상태 컬럼
# =====================================================

STATUS_RULES = {
    "문의작성": {
        "col_index": 13,  # 상태 (0-based)
        "rules": [
            {"values": ["접수", "문의"],         "bg": rgb(219, 234, 254), "text": rgb(30, 64, 175)},    # 파랑
            {"values": ["상담중", "견적"],        "bg": rgb(254, 249, 195), "text": rgb(133, 77, 14)},    # 노랑
            {"values": ["진행", "체결", "배정"],   "bg": rgb(191, 219, 254), "text": rgb(30, 58, 138)},   # 진파랑
            {"values": ["완료", "정산완료"],       "bg": rgb(209, 250, 229), "text": rgb(6, 95, 70)},     # 초록
            {"values": ["취소", "보류"],          "bg": rgb(254, 226, 226), "text": rgb(153, 27, 27)},    # 빨강
        ]
    },
    "배정기록": {
        "col_index": 13,  # 지급상태
        "rules": [
            {"values": ["미지급", "대기"],     "bg": rgb(254, 249, 195), "text": rgb(133, 77, 14)},
            {"values": ["지급완료", "완료"],   "bg": rgb(209, 250, 229), "text": rgb(6, 95, 70)},
            {"values": ["취소"],             "bg": rgb(254, 226, 226), "text": rgb(153, 27, 27)},
        ]
    },
    "계약건은청구금액적기": {
        "col_index": 11,  # 진행상황
        "rules": [
            {"values": ["미청구", "대기"],    "bg": rgb(254, 249, 195), "text": rgb(133, 77, 14)},
            {"values": ["청구", "청구완료"],   "bg": rgb(191, 219, 254), "text": rgb(30, 58, 138)},
            {"values": ["입금", "입금완료", "정산완료", "완료"], "bg": rgb(209, 250, 229), "text": rgb(6, 95, 70)},
            {"values": ["미입금", "지연"],     "bg": rgb(254, 226, 226), "text": rgb(153, 27, 27)},
        ]
    },
    "출석부": {
        "col_index": 9,  # 출석상태
        "rules": [
            {"values": ["정상", "출근"],   "bg": rgb(209, 250, 229), "text": rgb(6, 95, 70)},
            {"values": ["지각"],          "bg": rgb(254, 249, 195), "text": rgb(133, 77, 14)},
            {"values": ["조퇴"],          "bg": rgb(254, 215, 170), "text": rgb(154, 52, 18)},
            {"values": ["결근", "무단"],   "bg": rgb(254, 226, 226), "text": rgb(153, 27, 27)},
        ]
    },
    "지급내역": {
        "col_index": 14,  # 지급상태
        "rules": [
            {"values": ["대기"],           "bg": rgb(254, 249, 195), "text": rgb(133, 77, 14)},
            {"values": ["확정"],           "bg": rgb(191, 219, 254), "text": rgb(30, 58, 138)},
            {"values": ["완료", "지급완료"], "bg": rgb(209, 250, 229), "text": rgb(6, 95, 70)},
            {"values": ["취소", "반품"],    "bg": rgb(254, 226, 226), "text": rgb(153, 27, 27)},
        ]
    },
}


# =====================================================
# API 빌더 함수들
# =====================================================

def col_letter(idx):
    """0-based index → A, B, ..., Z, AA, AB..."""
    result = ""
    while True:
        result = chr(65 + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


def build_format_requests(sheet_id, sheet_name, num_cols, num_rows):
    """한 시트에 대한 전체 서식 요청 목록 반환"""
    requests = []
    theme = THEME.get(sheet_name, {"header_bg": rgb(55, 65, 81), "tab": rgb(107, 114, 128)})
    
    # ─── 1. 탭 색상 ───
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "tabColorStyle": {"rgbColor": theme["tab"]}
            },
            "fields": "tabColorStyle"
        }
    })
    
    # ─── 2. 헤더 행 고정 (freeze) ───
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1}
            },
            "fields": "gridProperties.frozenRowCount"
        }
    })
    
    # ─── 3. 헤더 행 서식 ───
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": theme["header_bg"],
                    "textFormat": {
                        "bold": True,
                        "fontSize": 10,
                        "foregroundColorStyle": {"rgbColor": HEADER_TEXT}
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "CLIP",
                    "padding": {"top": 4, "bottom": 4, "left": 6, "right": 6}
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy,padding)"
        }
    })
    
    # ─── 4. 헤더 행 높이 ───
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": 0,
                "endIndex": 1
            },
            "properties": {"pixelSize": 36},
            "fields": "pixelSize"
        }
    })
    
    # ─── 5. 데이터 행 기본 서식 (전체) ───
    data_end_row = min(num_rows, 1000)  # 최대 1000행까지만 서식 적용 (속도)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": data_end_row,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"fontSize": 10},
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "CLIP",
                    "padding": {"top": 2, "bottom": 2, "left": 4, "right": 4}
                }
            },
            "fields": "userEnteredFormat(textFormat.fontSize,verticalAlignment,wrapStrategy,padding)"
        }
    })
    
    # ─── 6. 열 너비 ───
    widths = COLUMN_WIDTHS.get(sheet_name, [])
    for i, w in enumerate(widths):
        if i >= num_cols:
            break
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1
                },
                "properties": {"pixelSize": w},
                "fields": "pixelSize"
            }
        })
    
    # ─── 7. 헤더 아래 굵은 테두리 ───
    requests.append({
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols
            },
            "bottom": MEDIUM_BORDER
        }
    })
    
    # ─── 8. 데이터 영역 얇은 테두리 ───
    requests.append({
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": data_end_row,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols
            },
            "top": THIN_BORDER,
            "bottom": THIN_BORDER,
            "left": THIN_BORDER,
            "right": THIN_BORDER,
            "innerHorizontal": THIN_BORDER,
            "innerVertical": THIN_BORDER
        }
    })
    
    # ─── 9. 교대 행 색상 (banding) ───
    # 기존 banding 제거 후 추가 (중복 방지)
    requests.append({
        "addBanding": {
            "bandedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": data_end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols
                },
                "rowProperties": {
                    "headerColor": theme["header_bg"],
                    "firstBandColor": WHITE,
                    "secondBandColor": ALT_ROW_COLOR
                }
            }
        }
    })
    
    # ─── 10. 자동 필터 ───
    requests.append({
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": data_end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols
                }
            }
        }
    })
    
    # ─── 11. 금액 컬럼 서식 (#,##0) ───
    money_cols = MONEY_COLUMNS.get(sheet_name, [])
    for ci in money_cols:
        if ci >= num_cols:
            continue
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": data_end_row,
                    "startColumnIndex": ci,
                    "endColumnIndex": ci + 1
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
                        "horizontalAlignment": "RIGHT"
                    }
                },
                "fields": "userEnteredFormat(numberFormat,horizontalAlignment)"
            }
        })
    
    # ─── 12. 날짜 컬럼 서식 ───
    date_cols = DATE_COLUMNS.get(sheet_name, [])
    for ci in date_cols:
        if ci >= num_cols:
            continue
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": data_end_row,
                    "startColumnIndex": ci,
                    "endColumnIndex": ci + 1
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER"
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment)"
            }
        })
    
    # ─── 13. 조건부 서식 (상태 컬럼) ───
    status_config = STATUS_RULES.get(sheet_name)
    if status_config:
        ci = status_config["col_index"]
        if ci < num_cols:
            for rule in status_config["rules"]:
                for value in rule["values"]:
                    requests.append({
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": data_end_row,
                                    "startColumnIndex": ci,
                                    "endColumnIndex": ci + 1
                                }],
                                "booleanRule": {
                                    "condition": {
                                        "type": "TEXT_EQ",
                                        "values": [{"userEnteredValue": value}]
                                    },
                                    "format": {
                                        "backgroundColor": rule["bg"],
                                        "textFormat": {
                                            "bold": True,
                                            "foregroundColorStyle": {"rgbColor": rule["text"]}
                                        }
                                    }
                                }
                            },
                            "index": 0
                        }
                    })
            # TEXT_CONTAINS 버전도 추가 (부분 일치)
            for rule in status_config["rules"]:
                for value in rule["values"]:
                    requests.append({
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": data_end_row,
                                    "startColumnIndex": ci,
                                    "endColumnIndex": ci + 1
                                }],
                                "booleanRule": {
                                    "condition": {
                                        "type": "TEXT_CONTAINS",
                                        "values": [{"userEnteredValue": value}]
                                    },
                                    "format": {
                                        "backgroundColor": rule["bg"],
                                        "textFormat": {
                                            "foregroundColorStyle": {"rgbColor": rule["text"]}
                                        }
                                    }
                                }
                            },
                            "index": 0
                        }
                    })
    
    return requests


# =====================================================
# 메인 실행
# =====================================================

def format_all_sheets(target_sheets=None):
    """
    전체 시트 서식 적용
    
    Parameters:
        target_sheets: 적용할 시트 이름 목록 (None이면 전체)
    """
    client = get_connection()
    if not client:
        print("❌ 구글 시트 연결 실패")
        return False
    
    sh = client.open_by_key(SHEET_ID)
    all_worksheets = sh.worksheets()
    
    # 대상 시트 필터링
    default_targets = [
        "문의작성", "STAFF", "고객정보", "견적상세",
        "배정기록", "계약건은청구금액적기",
        "출석부", "평가표", "지급내역",
        "Roles", "Factors", "Guides"
    ]
    targets = target_sheets or default_targets
    
    print("=" * 60)
    print("📊 Google Sheets 서식 개선 시작")
    print("=" * 60)
    
    total_requests = []
    formatted_sheets = []
    
    for wks in all_worksheets:
        if wks.title not in targets:
            continue
        
        sheet_id = wks.id
        sheet_name = wks.title
        num_cols = wks.col_count
        num_rows = wks.row_count
        
        # 실제 헤더 수 확인 (빈 헤더 제외)
        try:
            headers = wks.row_values(1)
            actual_cols = len(headers) if headers else num_cols
            # 빈 셀 뒤쪽 자르기
            while actual_cols > 0 and (actual_cols > len(headers) or not headers[actual_cols - 1].strip()):
                actual_cols -= 1
            if actual_cols == 0:
                actual_cols = num_cols
        except Exception:
            actual_cols = num_cols
        
        print(f"\n🔧 [{sheet_name}] 서식 적용 중... ({actual_cols}열 × {num_rows}행)")
        
        # 기존 banding 제거 (중복 방지)
        try:
            metadata = sh.fetch_sheet_metadata()
            for s in metadata.get("sheets", []):
                if s["properties"]["sheetId"] == sheet_id:
                    for banding in s.get("bandedRanges", []):
                        total_requests.append({
                            "deleteBandedRange": {
                                "bandedRangeId": banding["bandedRangeId"]
                            }
                        })
                    # 기존 조건부 서식도 제거 (중복 방지)
                    cond_rules = s.get("conditionalFormats", [])
                    if cond_rules:
                        for i in range(len(cond_rules) - 1, -1, -1):
                            total_requests.append({
                                "deleteConditionalFormatRule": {
                                    "sheetId": sheet_id,
                                    "index": i
                                }
                            })
                    # 기존 필터 제거
                    if s.get("basicFilter"):
                        total_requests.append({
                            "clearBasicFilter": {
                                "sheetId": sheet_id
                            }
                        })
                    break
        except Exception as e:
            print(f"  ⚠️ 기존 서식 제거 중 경고: {e}")
        
        # 서식 요청 생성
        reqs = build_format_requests(sheet_id, sheet_name, actual_cols, num_rows)
        total_requests.extend(reqs)
        formatted_sheets.append(sheet_name)
        
        print(f"  ✅ {len(reqs)}개 서식 요청 생성됨")
    
    if not total_requests:
        print("\n⚠️ 적용할 시트가 없습니다.")
        return False
    
    # batch_update 실행 (한번에 보내기 — API 호출 최소화)
    print(f"\n📤 총 {len(total_requests)}개 서식 요청 전송 중...")
    
    # Google Sheets API 제한: 한번에 최대 ~500 요청
    BATCH_SIZE = 400
    for i in range(0, len(total_requests), BATCH_SIZE):
        batch = total_requests[i:i + BATCH_SIZE]
        try:
            sh.batch_update({"requests": batch})
            print(f"  ✅ 배치 {i // BATCH_SIZE + 1} 완료 ({len(batch)}개 요청)")
        except Exception as e:
            print(f"  ❌ 배치 {i // BATCH_SIZE + 1} 실패: {e}")
            # 실패해도 나머지 배치 계속 진행
            continue
        
        # API rate limit 방지
        if i + BATCH_SIZE < len(total_requests):
            time.sleep(1)
    
    print("\n" + "=" * 60)
    print("✅ 서식 개선 완료!")
    print("=" * 60)
    print(f"\n📋 적용된 시트 ({len(formatted_sheets)}개):")
    for name in formatted_sheets:
        print(f"  • {name}")
    
    print(f"\n적용 항목:")
    print(f"  1. ✅ 헤더 행 서식 (시트별 테마 색상)")
    print(f"  2. ✅ 헤더 행 고정 (스크롤 시 고정)")
    print(f"  3. ✅ 열 너비 최적화")
    print(f"  4. ✅ 금액 서식 (#,##0)")
    print(f"  5. ✅ 조건부 서식 (상태 색상)")
    print(f"  6. ✅ 테두리 (헤더 굵은선 + 데이터 얇은선)")
    print(f"  7. ✅ 교대 행 색상 (줄무늬)")
    print(f"  8. ✅ 자동 필터")
    print(f"  9. ✅ 탭 색상")
    
    return True


if __name__ == "__main__":
    success = format_all_sheets()
    sys.exit(0 if success else 1)
