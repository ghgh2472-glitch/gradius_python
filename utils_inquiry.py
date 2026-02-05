# utils_inquiry.py
import re
from datetime import datetime
from dateutil.parser import parse # 설치한 모듈 사용

class InquiryParser:
    def __init__(self):
        pass

    def _smart_date_parse(self, date_str):
        """
        [날짜 변환기] "2.16", "2월 16일" 등을 "2025-02-16" 형태로 변환
        """
        if not date_str: return ""
        try:
            # 1. 숫자와 점, 슬래시만 남기고 정리 (2. 16 -> 2.16)
            clean_str = date_str.replace(" ", "").replace("월", "-").replace("일", "")
            
            # 2. 현재 년도 기준 파싱
            now = datetime.now()
            dt = parse(clean_str, default=datetime(now.year, 1, 1))
            
            # 3. 만약 파싱된 날짜가 과거라면 내년으로 간주 (선택사항)
            # (예: 12월에 "1월 1일" 문의가 오면 내년 1월로 계산)
            if dt.month < now.month and (now.month - dt.month) > 6:
                dt = dt.replace(year=now.year + 1)
            
            return dt.strftime("%Y-%m-%d")
        except:
            return date_str # 실패하면 원본 반환

    def parse_text(self, text):
        """
        [카톡 전문 분석 엔진]
        사용자가 제공한 양식을 기반으로 데이터를 추출합니다.
        """
        if not text: return {}
        
        extracted = {
            "client_name": "", "manager": "", "contact": "",
            "evt_name": "", "evt_place": "",
            "date_start": "", "date_end": "", 
            "evt_time": "", "headcount": "", 
            "service_type": "", "pay": "",
            "note_detail": ""
        }
        
        # 1. 항목별 정규식 패턴 (보내주신 예시 기준 정밀 튜닝)
        patterns = {
            # 기본 정보
            "client_name": [r'업체\s*[:]\s*(.*)'],
            "manager": [r'성함\s*[:]\s*(.*)', r'담당자\s*[:]\s*(.*)', r'이름\s*[:]\s*(.*)'],
            "contact": [r'연락처\s*[:]\s*(.*)', r'010[-\s]?\d{3,4}[-\s]?\d{4}'],
            
            # 행사 정보
            "evt_name": [r'행사명\s*[:]\s*(.*)'],
            "evt_place": [r'장소\s*[:]\s*(.*)', r'위치\s*[:]\s*(.*)'],
            
            # [중요] 일시/시간
            "date_raw": [r'일시\s*[:]\s*(.*)', r'날짜\s*[:]\s*(.*)'],
            "evt_time": [r'시간\s*[:]\s*(.*)'],
            
            # 상세 정보
            "service_type": [r'서비스종류\s*[:]\s*(.*)', r'서비스\s*[:]\s*(.*)'],
            "headcount": [r'요청인원수\s*[:]\s*(.*)', r'인원\s*[:]\s*(.*)', r'인원수\s*[:]\s*(.*)'],
            "pay": [r'페이\s*[:]\s*(.*)', r'예산\s*[:]\s*(.*)', r'금액\s*[:]\s*(.*)'],
            
            # 비고로 보낼 항목들
            "attire": [r'복장\s*[:]\s*(.*)'],
            "meal": [r'식사\s*[:]\s*(.*)'],
            "parking": [r'주차\s*[:]\s*(.*)'],
            "extra_note": [r'특이사항\s*[:]\s*(.*)']
        }
        
        # 2. 데이터 추출 루프
        details = []
        raw_date = ""
        
        for key, pats in patterns.items():
            for p in pats:
                match = re.search(p, text)
                if match:
                    # 연락처인 경우 010 패턴 전체 가져오기
                    val = match.group(0) if key == 'contact' and '010' in p else match.group(1)
                    val = val.strip()
                    
                    if key == 'date_raw':
                        raw_date = val
                    elif key in extracted:
                        extracted[key] = val
                    else:
                        # 비고란 합치기
                        label_map = {"attire": "복장", "meal": "식사", "parking": "주차", "extra_note": "추가요청"}
                        if val:
                            details.append(f"- {label_map.get(key, key)}: {val}")
                    break
        
        # 3. [고도화] 날짜 분리 및 스마트 변환
        # 예: "2. 16 ~ 3.2" -> start: 2024-02-16, end: 2024-03-02
        if raw_date:
            if '~' in raw_date:
                parts = raw_date.split('~')
                extracted['date_start'] = self._smart_date_parse(parts[0])
                extracted['date_end'] = self._smart_date_parse(parts[1])
            else:
                formatted = self._smart_date_parse(raw_date)
                extracted['date_start'] = formatted
                extracted['date_end'] = formatted
                
        # 4. 상세 내용 정리
        if details:
            extracted['note_detail'] = "\n".join(details)
            
        return extracted