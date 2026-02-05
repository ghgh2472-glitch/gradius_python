import gspread
from data_loader import SHEET_ID, get_connection
from datetime import datetime, timedelta
import random

client = get_connection()
if client:
    sh = client.open_by_key(SHEET_ID)
    
    # ========== 1. 배정기록에 더 많은 인력 데이터 추가 ==========
    print('[STEP 1] 배정기록 샘플 데이터 추가...')
    
    wks_dispatch = sh.worksheet('배정기록')
    all_values = wks_dispatch.get_all_values()
    
    # 현재 마지막 행이 14개인데, 더 많은 인력 데이터 추가
    staff_data = [
        # INQ001 - 삼성전자
        ['INQ001-001', 'INQ001', '회의실세팅', '김민지', '스태프', '010-1234-5001', '', '', '', 80000, 3, 240000],
        ['INQ001-002', 'INQ001', '회의실세팅', '박준호', '운영자', '010-1234-5002', '', '', '', 100000, 3, 300000],
        
        # INQ002 - LG전자
        ['INQ002-001', 'INQ002', '제품전시회', '이수진', '안내', '010-1234-5003', '', '', '', 70000, 4, 280000],
        ['INQ002-002', 'INQ002', '제품전시회', '정재현', '매니저', '010-1234-5004', '', '', '', 120000, 4, 480000],
        ['INQ002-003', 'INQ002', '제품전시회', '최은지', '스태프', '010-1234-5005', '', '', '', 70000, 4, 280000],
        
        # INQ003 - 현대자동차
        ['INQ003-001', 'INQ003', '직원교육', '한동욱', '강사', '010-1234-5006', '', '', '', 150000, 2, 300000],
        ['INQ003-002', 'INQ003', '직원교육', '윤소정', '조교', '010-1234-5007', '', '', '', 80000, 2, 160000],
        
        # INQ004 - SK하이닉스
        ['INQ004-001', 'INQ004', '컨퍼런스', '김서영', '등록', '010-1234-5008', '', '', '', 85000, 3, 255000],
        
        # INQ005 - CJ CGV
        ['INQ005-001', 'INQ005', '영상촬영', '이준희', '촬영', '010-1234-5009', '', '', '', 200000, 2, 400000],
        ['INQ005-002', 'INQ005', '영상촬영', '박지현', '편집', '010-1234-5010', '', '', '', 150000, 2, 300000],
        
        # INQ006 - 롯데백화점
        ['INQ006-001', 'INQ006', '행사진행', '신현준', '진행자', '010-1234-5011', '', '', '', 110000, 3, 330000],
        ['INQ006-002', 'INQ006', '행사진행', '김현희', '보조', '010-1234-5012', '', '', '', 75000, 3, 225000],
        
        # INQ007 - 신한은행
        ['INQ007-001', 'INQ007', '세미나', '장준호', '강연자', '010-1234-5013', '', '', '', 180000, 2, 360000],
        
        # INQ008 - 카카오
        ['INQ008-001', 'INQ008', '워크샵', '우지은', '워크샵운영', '010-1234-5014', '', '', '', 120000, 2, 240000],
        ['INQ008-002', 'INQ008', '워크샵', '손준호', '보조강사', '010-1234-5015', '', '', '', 95000, 2, 190000],
    ]
    
    for row_data in staff_data:
        wks_dispatch.append_row(row_data)
        print(f'  추가: {row_data[0]} - {row_data[3]} ({row_data[4]})')
    
    print(f'✅ {len(staff_data)}개 인력 데이터 추가 완료!\n')
    
    # ========== 2. 정산 데이터 업데이트 (파견일자를 미래로 변경) ==========
    print('[STEP 2] 정산 데이터 파견일자 업데이트 (긴급탭용)...')
    
    wks_settle = sh.worksheet('계약건은청구금액적기')
    all_settle = wks_settle.get_all_values()
    
    # 파견 일자를 다양하게 설정 (D-1부터 D-30까지)
    new_dates = [
        '2026-02-04',  # D-1 (내일)
        '2026-02-05',  # D-2
        '2026-02-06',  # D-3
        '2026-02-08',  # D-5
        '2026-02-10',  # D-7
        '2026-02-15',  # D-12
        '2026-02-20',  # D-17
        '2026-03-01',  # D-28
    ]
    
    for idx, date in enumerate(new_dates):
        if idx + 1 < len(all_settle):  # 헤더 제외
            wks_settle.update_cell(idx + 2, 4, date)  # Column D (파견일자)
            print(f'  Row {idx+1}: {all_settle[idx+1][1]} → {date}')
    
    print('✅ 파견일자 업데이트 완료!\n')
    
    # ========== 3. 월별 데이터 확인 ==========
    print('[STEP 3] 월별 매출 데이터 현황...')
    
    wks_inq = sh.worksheet('문의작성')
    all_inq = wks_inq.get_all_values()
    
    months = {}
    for row in all_inq[1:]:
        if len(row) > 5:  # 충분한 데이터가 있어야 함
            # 행사날짜 컬럼 찾기
            event_date = row[5] if len(row) > 5 else None
            if event_date and len(str(event_date)) >= 7:
                try:
                    month = event_date[:7]  # YYYY-MM
                    if month not in months:
                        months[month] = 0
                    months[month] += 1
                except:
                    pass
    
    print(f'  발견된 월별 데이터: {sorted(months.items())}')
    print('✅ 분석 완료!\n')
    
    print('[SUCCESS] 모든 샘플 데이터 추가 완료!')
    print('대시보드를 새로고침해주세요.')
