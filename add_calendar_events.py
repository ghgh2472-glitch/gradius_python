import gspread
from data_loader import SHEET_ID, get_connection
from datetime import datetime, timedelta

client = get_connection()
if client:
    sh = client.open_by_key(SHEET_ID)
    
    # 문의 시트에 더 많은 행사 데이터 추가 (캘린더 채우기)
    print('[STEP 1] 문의 시트에 행사 일정 데이터 추가...')
    
    wks_inq = sh.worksheet('문의작성')
    
    # 추가할 행사 데이터 (기존 8개 문의에 더 추가)
    additional_inquiries = [
        # 기존 문의들의 행사 날짜 업데이트 + 추가 문의
        ['INQ009', '현대건설 세미나', '현대건설', '2026-02-12', '최민준', '', '3800000', '', '', '미정', ''],
        ['INQ010', 'SK 신입교육', 'SK에너지', '2026-02-18', '박영희', '', '5200000', '', '', '견적', ''],
        ['INQ011', '포스코 워크숍', 'POSCO', '2026-02-24~2026-02-25', '이순신', '', '7500000', '', '', '상담중', ''],
        ['INQ012', 'GS칼텍스 행사', 'GS칼텍스', '2026-03-03', '홍길동', '', '4200000', '', '', '미정', ''],
        ['INQ013', 'LG 임직원 MT', 'LG에너지솔루션', '2026-03-10~2026-03-11', '김진영', '', '9800000', '', '', '견적', ''],
        ['INQ014', '삼성전기 발표회', '삼성전기', '2026-03-15', '우지은', '', '3600000', '', '', '미정', ''],
        ['INQ015', '한전 컨퍼런스', '한국전력공사', '2026-03-22', '장호준', '', '6500000', '', '', '상담중', ''],
        ['INQ016', 'KT 기술 심포지엄', 'KT', '2026-03-28~2026-03-29', '신현준', '', '8200000', '', '', '미정', ''],
        ['INQ017', 'SK 이노베이션 포럼', 'SK이노베이션', '2026-04-05', '김민지', '', '5900000', '', '', '견적', ''],
        ['INQ018', '현대차 미래포럼', '현대자동차', '2026-04-12', '박준호', '', '7800000', '', '', '미정', ''],
    ]
    
    for idx, row in enumerate(additional_inquiries):
        wks_inq.append_row(row)
        print(f'  {idx+1}. {row[0]}: {row[1]} ({row[3]})')
    
    print(f'✅ {len(additional_inquiries)}개 문의 추가 완료!\n')
    
    # 확인
    all_inq = wks_inq.get_all_values()
    print(f'[VERIFY] 문의 시트 현황:')
    print(f'  Total rows: {len(all_inq)} (헤더 포함)')
    print(f'  Data rows: {len(all_inq) - 1}')
    print(f'  Latest: {all_inq[-1][0]} - {all_inq[-1][1]}')
    
    print('\n[SUCCESS] 캘린더 행사 일정 데이터 추가 완료!')
    print('대시보드를 새로고침해주세요.')
