import gspread
from data_loader import SHEET_ID, get_connection

client = get_connection()
if client:
    sh = client.open_by_key(SHEET_ID)
    
    # 배정기록 시트 확인
    wks = sh.worksheet('배정기록')
    all_values = wks.get_all_values()
    
    print('=== 배정기록 시트 ===')
    print(f'헤더 ({len(all_values[0])} 컬럼):')
    for i, col in enumerate(all_values[0][:12]):
        print(f'  Col {i:2d} ({chr(65+i)}): {col}')
    
    print(f'\nTotal rows: {len(all_values)}')
    if len(all_values) > 1:
        print(f'\nFirst data row:')
        for i, val in enumerate(all_values[1][:12]):
            print(f'  Col {i:2d} ({chr(65+i)}): {val[:30] if val else "[EMPTY]"}')
