import gspread
from data_loader import SHEET_ID, get_connection
import pandas as pd

client = get_connection()
if client:
    sh = client.open_by_key(SHEET_ID)
    wks = sh.worksheet('계약건은청구금액적기')
    
    all_values = wks.get_all_values()
    
    print('=== HEADER ===')
    print(f'Total columns in header: {len(all_values[0])}')
    print('Column mapping:')
    for i, col in enumerate(all_values[0][:15]):
        print(f'  Col {i:2d} ({chr(65+i)}): {col}')
    
    print('\n=== FIRST DATA ROW ===')
    print(f'Total columns in data: {len(all_values[1])}')
    print('Data mapping:')
    for i, val in enumerate(all_values[1][:15]):
        print(f'  Col {i:2d} ({chr(65+i)}): {val[:30] if val else "[EMPTY]"}')
