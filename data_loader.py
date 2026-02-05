# data_loader.py
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import auth
import os
from datetime import datetime
from uuid import uuid4
from utils import safe_int
from helpers import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------
# 1. 구글 시트 인증 및 연결 설정
# ---------------------------------------------------------
SHEET_ID = "13gzHX1p-oMZnZjVfYR93RV1Zj5YAalOm56FWYU-p7RI" 
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_connection():
    try:
        # allow calling even when Streamlit secrets are not available
        try:
            st_secrets = st.secrets
        except Exception:
            st_secrets = None

        client = auth.get_gspread_client(secrets_path="secrets.json", st_secrets=st_secrets, scopes=SCOPES)
        return client
    except Exception as e:
        # surface a friendly Streamlit error when running inside the app
        try:
            st.error(f"❌ 구글 인증 실패: {e}")
        except Exception:
            pass
        return None

# ---------------------------------------------------------
# 2. 데이터 로드 (최신성 유지 및 타입 정제)
# ---------------------------------------------------------
@st.cache_data(ttl=900)  # 900초(15분) - API 할당량 초과 해결
def load_all_data():
    data = {}
    client = get_connection()
    
    # 필수 시트만 로드 (API 할당량 절약 - 3개 시트만 로드)
    sheet_map = {
        "inq": "문의작성",
        "staff": "STAFF",
        "client": "고객정보"
        # 배정기록, 견적상세, 계약건은청구금액적기는 필요할 때만 로드
    }
    
    if not client:
        return {k: pd.DataFrame() for k in sheet_map}

    try:
        sh = client.open_by_key(SHEET_ID)
        for key, tab_name in sheet_map.items():
            try:
                wks = sh.worksheet(tab_name)
                records = None
                df = None
                
                # Step 1: Try get_all_records() (fastest method)
                try:
                    records = wks.get_all_records()
                    df = pd.DataFrame(records)
                    print(f"[OK] {tab_name}: {len(df)} rows loaded (get_all_records)")
                except Exception as e:
                    # Step 2: If get_all_records fails, use raw data + header processing
                    print(f"[WARN] {tab_name} get_all_records failed, loading raw data ({str(e)[:60]})")
                    try:
                        all_values = wks.get_all_values()
                        if len(all_values) > 1:
                            raw_headers = all_values[0]
                            
                            # 중복 헤더 처리
                            seen = {}
                            unique_headers = []
                            for h in raw_headers:
                                key_h = str(h).strip() if h else ''
                                if key_h in seen:
                                    seen[key_h] += 1
                                    unique_headers.append(f"{key_h}__dup{seen[key_h]}")
                                else:
                                    seen[key_h] = 0
                                    unique_headers.append(key_h)
                            
                            # DataFrame 생성
                            records = [dict(zip(unique_headers, row)) for row in all_values[1:]]
                            df = pd.DataFrame(records)
                            
                            # 중복 헤더 병합
                            for base, cnt in seen.items():
                                if cnt > 0 and base in df.columns:
                                    cols = [c for c in df.columns if c == base or c.startswith(f"{base}__dup")]
                                    if len(cols) > 1:
                                        def first_nonempty(row_vals):
                                            for v in row_vals:
                                                v_str = str(v).strip() if v is not None else ''
                                                if v_str and v_str not in ('nan', 'None', ''):
                                                    return v_str
                                            return ''
                                        df[base] = df[cols].apply(first_nonempty, axis=1)
                                        drop_cols = [c for c in cols if c != base]
                                        df.drop(columns=drop_cols, inplace=True)
                            
                            print(f"[OK] {tab_name}: {len(df)} rows loaded (raw + header merge)")
                        else:
                            df = pd.DataFrame()
                    except Exception as raw_error:
                        print(f"[ERROR] {tab_name} raw load failed: {str(raw_error)[:60]}")
                        df = pd.DataFrame()
                
                if df is None:
                    df = pd.DataFrame()
                
                # 데이터 타입 강제 변환
                cols_to_str = ['연락처', '문의ID', '사업자번호', '대표자']
                for col in cols_to_str:
                    if col in df.columns:
                        df[col] = df[col].astype(str).str.strip().replace(['nan', 'None'], '')
                
                data[key] = df
                
            except gspread.exceptions.WorksheetNotFound:
                print(f"[ERROR] Sheet not found: {tab_name}")
                data[key] = pd.DataFrame()
            except Exception as e:
                print(f"[ERROR] {tab_name} load error: {type(e).__name__}: {str(e)[:100]}")
                data[key] = pd.DataFrame()
                
    except Exception as e:
        st.error(f"❌ 시트 파일 접속 불가: {e}")
        return {k: pd.DataFrame() for k in sheet_map}
            
    return data


# ---------------------------------------------------------
# 2-1. 인력배정 데이터 지연 로드 (Lazy Load - 필요할 때만 로드)
# ---------------------------------------------------------
@st.cache_data(ttl=900)  # 15분 캐시
def load_dispatch_data():
    """배정기록과 계약건은청구금액적기를 함께 로드 (인력배정/정산 탭에서 사용)"""
    client = get_connection()
    if not client:
        return {"dispatch": pd.DataFrame(), "settlement": pd.DataFrame()}
    
    try:
        sh = client.open_by_key(SHEET_ID)
        result = {}
        
        # 배정기록 로드
        try:
            wks = sh.worksheet("배정기록")
            try:
                records = wks.get_all_records()
                result["dispatch"] = pd.DataFrame(records)
            except Exception as header_error:
                # 헤더 문제 시 raw data 사용
                all_values = wks.get_all_values()
                if len(all_values) > 1:
                    headers = [str(h).strip() for h in all_values[0]]
                    records = [dict(zip(headers, row)) for row in all_values[1:]]
                    result["dispatch"] = pd.DataFrame(records)
                else:
                    result["dispatch"] = pd.DataFrame()
            
            print(f"[OK] dispatch sheet: {len(result['dispatch'])} rows loaded")
        except Exception as e:
            print(f"[WARN] dispatch sheet load failed: {str(e)[:60]}")
            result["dispatch"] = pd.DataFrame()
        
        # 계약건은청구금액적기 로드
        try:
            wks = sh.worksheet("계약건은청구금액적기")
            try:
                records = wks.get_all_records()
                result["settlement"] = pd.DataFrame(records)
            except Exception as header_error:
                # 헤더 문제 시 raw data 사용
                all_values = wks.get_all_values()
                if len(all_values) > 1:
                    headers = [str(h).strip() for h in all_values[0]]
                    # 중복/빈 헤더 처리
                    clean_headers = []
                    for i, h in enumerate(headers):
                        if not h or h == '':
                            clean_headers.append(f"col_{i}")
                        else:
                            clean_headers.append(h)
                    records = [dict(zip(clean_headers, row)) for row in all_values[1:]]
                    result["settlement"] = pd.DataFrame(records)
                else:
                    result["settlement"] = pd.DataFrame()
            
            print(f"[OK] settlement sheet: {len(result['settlement'])} rows loaded")
        except Exception as e:
            print(f"[WARN] settlement sheet load failed: {str(e)[:60]}")
            result["settlement"] = pd.DataFrame()
        
        return result
    except Exception as e:
        print(f"[Error] dispatch data load error: {str(e)[:60]}")
        return {"dispatch": pd.DataFrame(), "settlement": pd.DataFrame()}


# ---------------------------------------------------------
# 3. 데이터 업데이트 (계약/견적 통합 처리)
# ---------------------------------------------------------

def update_status(inquiry_id, new_status, col_idx=14):
    """문의작성 시트의 상태 열 업데이트"""
    client = get_connection()
    if client:
        try:
            sh = client.open_by_key(SHEET_ID)
            wks = sh.worksheet("문의작성")
            # ID를 정확히 찾아 행 번호 획득
            cell = wks.find(str(inquiry_id).strip(), in_column=1) 
            if cell:
                wks.update_cell(cell.row, col_idx, new_status)
                return True
        except: pass
    return False

def update_cell(sheet_name, inquiry_id, col_name=None, value=""):
    """
    특정 셀 업데이트 (문의ID 기반)
    
    Args:
        sheet_name (str): 시트 이름 (예: '문의작성')
        inquiry_id (str): 업데이트할 행의 문의ID
        col_name (str): 업데이트할 컬럼 이름
        value: 업데이트할 값
    """
    client = get_connection()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet(sheet_name)
        
        # 1. 컬럼 헤더 찾기
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        
        if col_name not in headers_clean:
            print(f"❌ 컬럼 '{col_name}'을(를) 찾을 수 없습니다.")
            return False
        
        col_idx = headers_clean.index(col_name) + 1
        
        # 2. 문의ID 행 찾기
        id_col = wks.col_values(1)  # 첫 번째 컬럼 (문의ID)
        id_col_clean = [str(x).strip() for x in id_col]
        
        target_row = None
        for i, cell_id in enumerate(id_col_clean):
            if cell_id == str(inquiry_id).strip():
                target_row = i + 1
                break
        
        if target_row is None:
            print(f"❌ 문의ID '{inquiry_id}'를 찾을 수 없습니다.")
            return False
        
        # 3. 셀 업데이트
        wks.update_cell(target_row, col_idx, str(value))
        print(f"✅ [{sheet_name}] {inquiry_id} - {col_name} = {value}")
        return True
        
    except Exception as e:
        print(f"❌ update_cell 오류: {e}")
        return False

def save_estimate_details(est_data, metadata=None):
    """
    견적상세 시트에 견적 정보를 저장합니다.
    시트가 가득 차면 자동으로 아카이브 시트로 저장합니다.
    
    Args:
        est_data (dict): {
            '문의ID': str,
            '업체명': str,
            '행사명': str,
            '공급가액': int,
            '부가세': int,
            '합계금액': int,
            '매입원가': int,
            '부대비용': int (optional)
        }
        metadata (dict, optional): {
            '현장명': str,
            '책임자': str,
            '현장주소': str,
            '사업자번호': str,
            '대표자': str
        }
    
    Returns:
        bool: 성공 여부
    """
    client = get_connection()
    if not client:
        logger.error("❌ Google 인증 실패")
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # 1. 저장할 시트 결정 (메인 또는 아카이브)
        target_sheet_name = "견적상세"
        try:
            wks = sh.worksheet(target_sheet_name)
            all_values = wks.get_all_values()
            current_rows = len(all_values)
            
            # 용량 부족 시 아카이브 시트로 변경
            if current_rows >= 1980:
                logger.warning(f"⚠️ {target_sheet_name}: {current_rows}행 - 아카이브 시트로 전환")
                target_sheet_name = "견적상세_아카이브"
                try:
                    wks = sh.worksheet(target_sheet_name)
                except gspread.exceptions.WorksheetNotFound:
                    # 아카이브 시트 없으면 생성
                    logger.info(f"📝 {target_sheet_name} 시트 생성 중...")
                    headers = ["문의ID", "업체명", "행사명", "현장명", "책임자", "현장주소", "공급가액", "부가세", "합계금액", "매입원가", "부대비용", "수익률", "기록일시"]
                    wks = sh.add_worksheet(title=target_sheet_name, rows=2000, cols=len(headers))
                    wks.update('A1', [headers], value_input_option='RAW')
                    logger.info(f"✅ {target_sheet_name} 시트 생성 완료")
                
                all_values = wks.get_all_values()
                current_rows = len(all_values)
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ {target_sheet_name} 시트를 찾을 수 없습니다")
            return False
        
        # 2. 시트 헤더 읽기
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        
        # 3. 문의ID로 기존 행 찾기 (중복 방지)
        target_id = str(est_data.get('문의ID', '')).strip()
        id_col_values = wks.col_values(1)  # 첫 번째 컬럼 (문의ID)
        id_col_clean = [str(x).strip() for x in id_col_values]
        
        # 4. 행 위치 결정
        if target_id in id_col_clean:
            # 기존 견적 업데이트
            target_row = id_col_clean.index(target_id) + 1
            logger.info(f"📝 기존 견적 업데이트: [{target_sheet_name}] Row {target_row} (ID: {target_id})")
        else:
            # 새 견적 추가
            target_row = current_rows + 1
            logger.info(f"📝 새 견적 추가: [{target_sheet_name}] Row {target_row} (ID: {target_id})")
        
        # 5. 데이터 준비
        metadata = metadata or {}
        row_data = {}
        
        # 메타데이터를 JSON 형식으로 준비 (존재하는 경우)
        import json
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else ""
        
        for col_idx, header in enumerate(headers_clean, 1):
            if header == "문의ID":
                row_data[col_idx] = target_id
            elif header == "업체명":
                row_data[col_idx] = est_data.get('업체명', '')
            elif header == "행사명":
                row_data[col_idx] = est_data.get('행사명', '')
            elif header == "현장명":
                row_data[col_idx] = metadata.get('현장명', est_data.get('행사명', ''))
            elif header == "책임자":
                row_data[col_idx] = metadata.get('책임자', '')
            elif header == "현장주소":
                row_data[col_idx] = metadata.get('현장주소', '')
            elif header == "공급가액":
                row_data[col_idx] = int(est_data.get('공급가액', 0))
            elif header == "부가세":
                row_data[col_idx] = int(est_data.get('부가세', 0))
            elif header == "합계금액":
                row_data[col_idx] = int(est_data.get('합계금액', 0))
            elif header == "매입원가":
                row_data[col_idx] = int(est_data.get('매입원가', 0))
            elif header == "부대비용":
                row_data[col_idx] = int(est_data.get('부대비용', 0))
            elif "수익" in header and ("률" in header or "율" in header):
                # 수익률/수익율 계산
                supply = int(est_data.get('공급가액', 0))
                cost = int(est_data.get('매입원가', 0))
                profit = supply - cost
                margin = f"{round((profit / supply * 100), 1)}%" if supply > 0 else "0%"
                row_data[col_idx] = margin
            elif header in ["메모", "비고", "Notes", "Meta"]:
                # 메타데이터를 메모 필드에 저장
                row_data[col_idx] = metadata_json
            elif "기록" in header or "일시" in header or "시간" in header:
                row_data[col_idx] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                row_data[col_idx] = ""
        
        # 6. 행 업데이트 (gspread Cell 사용)
        from gspread.cell import Cell
        cells_to_update = []
        for col_num, value in row_data.items():
            cells_to_update.append(Cell(row=target_row, col=col_num, value=value))
        
        if cells_to_update:
            wks.update_cells(cells_to_update, value_input_option='RAW')
            logger.info(f"✅ 견적 저장 완료: [{target_sheet_name}] {target_id}")
            return True
        
        return False
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ save_estimate_details error: {error_msg}")
        return False

def save_settlement_record(settlement_data, site_info=None):
    """
    계약 체결 시 '계약건은 청구금액적기' 시트에 기록 저장
    
    Args:
        settlement_data (dict): {
            '문의ID': str,
            '업체명': str,
            '행사명': str,
            '사업자번호': str,
            '대표자': str,
            '이메일': str,
            '계약일': str (YYYY-MM-DD),
            '공급가액': int,
            '부가세': int,
            '합계금액': int,
            '상태': str
        }
        site_info (dict, optional): {
            '현장명': str,
            '책임자': str,
            '현장주소': str
        }
    """
    client = get_connection()
    if not client:
        logger.error("❌ Google 인증 실패")
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("계약건은청구금액적기")
        
        # 1. 헤더 읽기
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        
        # 2. 현재 데이터 행 확인
        all_values = wks.get_all_values()
        current_rows = len(all_values)
        
        # 3. 행 용량 체크 (993행 제한 -> 990행이 넘으면 새 시트 생성)
        if current_rows >= 990:
            logger.warning(f"⚠️ 계약건은청구금액적기: {current_rows}행 - 아카이브로 전환")
            # 새 시트로 저장하도록 처리
            target_sheet_name = "계약건은청구금액적기_아카이브"
            try:
                wks = sh.worksheet(target_sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                logger.info(f"📝 {target_sheet_name} 시트 생성 중...")
                wks = sh.add_worksheet(title=target_sheet_name, rows=1000, cols=len(headers_clean))
                wks.update('A1', [headers_clean], value_input_option='RAW')
                logger.info(f"✅ {target_sheet_name} 시트 생성 완료")
                all_values = wks.get_all_values()
                current_rows = len(all_values)
        
        # 4. 문의ID로 중복 확인
        target_id = str(settlement_data.get('문의ID', '')).strip()
        id_col_values = wks.col_values(1)
        id_col_clean = [str(x).strip() for x in id_col_values]
        
        # 5. 행 위치 결정
        if target_id in id_col_clean:
            # 기존 행 업데이트
            target_row = id_col_clean.index(target_id) + 1
            logger.info(f"📝 기존 계약건 업데이트: [{wks.title}] Row {target_row}")
        else:
            # 새 행 추가
            target_row = current_rows + 1
            logger.info(f"📝 새 계약건 저장: [{wks.title}] Row {target_row}")
        
        # 6. 현장 정보 준비
        site_info = site_info or {}
        
        # 7. 데이터 준비
        from gspread.cell import Cell
        cells_to_update = []
        
        for col_idx, header in enumerate(headers_clean, 1):
            if header == "문의ID":
                value = target_id
            elif header == "현장명":
                value = site_info.get('현장명', settlement_data.get('행사명', ''))
            elif header == "업체":
                # 새로 추가된 업체 컬럼
                value = settlement_data.get('업체명', '')
            elif header == "파견일자":
                # 새로 추가된 파견일자 컬럼 (행사시작일 ~ 행사종료일 형식)
                value = site_info.get('파견일자', '')
            elif "내용" in header or header == "행사명":
                value = settlement_data.get('행사명', '')
            elif header == "책임자":
                value = site_info.get('책임자', '')
            elif header == "현장주소":
                value = site_info.get('현장주소', '')
            elif header == "청구금액":
                # 청구금액 = 합계금액
                value = int(settlement_data.get('합계금액', 0))
            elif header == "공급가액":
                value = int(settlement_data.get('공급가액', 0))
            elif header == "부가세":
                value = int(settlement_data.get('부가세', 0))
            elif header == "합계금액":
                value = int(settlement_data.get('합계금액', 0))
            elif header == "사업자번호":
                value = settlement_data.get('사업자번호', '')
            elif header == "업체명":
                value = settlement_data.get('업체명', '')
            elif header == "대표자":
                value = settlement_data.get('대표자', '')
            elif header == "이메일":
                value = settlement_data.get('이메일', '')
            elif header == "상태":
                value = settlement_data.get('상태', '대기')
            elif "기록" in header or "일시" in header:
                value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                value = ""
            
            cells_to_update.append(Cell(row=target_row, col=col_idx, value=value))
        
        # 8. 일괄 업데이트
        if cells_to_update:
            wks.update_cells(cells_to_update, value_input_option='RAW')
            logger.info(f"✅ 계약 기록 저장 완료: {target_id}")
            return True
        
        return False
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 계약 기록 저장 실패: {error_msg}")
        if "exceeds grid limits" in error_msg:
            logger.error("💡 시트 용량 초과 - 아카이브 시트를 생성하거나 오래된 데이터를 정리하세요")
        return False

# `safe_int` is provided by `utils.safe_int` (centralized utility)


def _lookup_staff_info(staff_name):
    """
    STAFF 시트에서 이름으로 직원 정보 조회
    반환: {'이름': str, '연락처': str, '소속': str, '기본단가': int, ...}
    """
    try:
        data = load_all_data()
        df_staff = data.get('staff', pd.DataFrame())
        if df_staff.empty:
            return None
        
        # 이름 컬럼 찾기
        name_col = None
        for col in df_staff.columns:
            if '이름' in col or '성명' in col or col.strip() == '이름':
                name_col = col
                break
        
        if name_col is None:
            return None
        
        # 이름으로 검색
        match = df_staff[df_staff[name_col].astype(str).str.strip() == str(staff_name).strip()]
        if match.empty:
            return None
        
        staff_row = match.iloc[0]
        
        # 필요한 필드 추출
        info = {'이름': str(staff_name).strip()}
        
        for col in df_staff.columns:
            col_clean = str(col).strip()
            if '연락처' in col_clean or '전화' in col_clean or '폰' in col_clean:
                info['연락처'] = str(staff_row[col]).strip() if staff_row[col] else ''
            elif '소속' in col_clean or '부서' in col_clean:
                info['소속'] = str(staff_row[col]).strip() if staff_row[col] else ''
            elif '단가' in col_clean and '기본' in col_clean:
                try:
                    info['기본단가'] = safe_int(staff_row[col])
                except:
                    pass
        
        return info
    except Exception as e:
        print(f"Staff lookup error: {e}")
        return None


def save_assignment_record(assignment):
    """
    배정기록 시트에 단일 배정 레코드 저장 (Auto-fill 기능 포함)
    assignment: dict with keys: 문의ID, 이름, 역할, 일수, 단가, 총지급액, 배정일시, 상태
    
    기능:
    - STAFF 시트에서 이름으로 직원 정보 자동 조회
    - 연락처, 소속 등 누락된 정보 자동 채우기
    - 단가 미제공 시 STAFF의 기본단가 사용
    """
    client = get_connection()
    if not client:
        return False

    try:
        # 배정기록 캐시 무효화 (저장 후 목록이 업데이트되도록)
        import streamlit as st
        st.cache_data.clear()
        
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("배정기록")

        # 배정ID 생성
        assign_id = f"A-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"

        # STAFF에서 직원 정보 조회 (Auto-fill)
        staff_name = assignment.get('이름', '').strip()
        staff_info = _lookup_staff_info(staff_name) if staff_name else None
        
        # 배정 정보에 STAFF 정보 병합 (미제공 필드만 채우기)
        merged_assignment = dict(assignment)
        # '상태'를 '지급상태'로 변환 (Google Sheets 컬럼명)
        if '상태' in merged_assignment:
            merged_assignment['지급상태'] = merged_assignment.pop('상태')
        
        if staff_info:
            if not merged_assignment.get('연락처'):
                merged_assignment['연락처'] = staff_info.get('연락처', '')
            if not merged_assignment.get('소속'):
                merged_assignment['소속'] = staff_info.get('소속', '')
            # 단가가 없으면 기본단가 사용
            if not merged_assignment.get('단가') and '기본단가' in staff_info:
                merged_assignment['단가'] = staff_info['기본단가']
                # 총지급액도 재계산
                days = safe_int(merged_assignment.get('일수', 0))
                if merged_assignment.get('단가') and days > 0:
                    merged_assignment['총지급액'] = merged_assignment['단가'] * days

        # 다음 빈 행 번호 계산
        id_col_vals = wks.col_values(1)
        next_row = len(id_col_vals) + 1

        # 시트 행이 부족하면 확장
        if next_row > wks.row_count:
            try:
                wks.add_rows(200)
            except Exception as e:
                print(f"Failed to add rows before write: {e}")

        # 배정기록 시트의 실제 컬럼 구조 (Google Sheets에 있는 그대로)
        # Col 1: 배정ID
        # Col 2: 문의ID
        # Col 3: 행사명
        # Col 4: 인력명
        # Col 5: 직무
        # Col 6: 연락처
        # Col 7: 주민등록번호
        # Col 8: 은행명
        # Col 9: 계좌번호
        # Col 10: 지급단가
        # Col 11: 근무일수
        # Col 12: 총지급액
        # Col 13: 지급상태
        # Col 14: 배정일시
        
        row_values = [
            assign_id,  # Col 1: 배정ID
            merged_assignment.get('문의ID', ''),  # Col 2: 문의ID
            merged_assignment.get('행사명', ''),  # Col 3: 행사명
            merged_assignment.get('인력명', ''),  # Col 4: 인력명
            merged_assignment.get('직무', ''),  # Col 5: 직무
            merged_assignment.get('연락처', ''),  # Col 6: 연락처
            '',  # Col 7: 주민등록번호
            '',  # Col 8: 은행명
            '',  # Col 9: 계좌번호
            merged_assignment.get('지급단가', ''),  # Col 10: 지급단가
            merged_assignment.get('근무일수', ''),  # Col 11: 근무일수
            merged_assignment.get('총지급액', ''),  # Col 12: 총지급액
            merged_assignment.get('지급상태', '배정중'),  # Col 13: 지급상태
            merged_assignment.get('배정일시', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),  # Col 14: 배정일시
        ]

        # A{next_row} 위치에 한 줄로 업데이트
        try:
            wks.update(f'A{next_row}', [row_values], value_input_option='RAW')
            name = merged_assignment.get('이름', '')
            role = merged_assignment.get('역할', '')
            print(f"Assignment saved: {assign_id} at row {next_row} - {name} ({role})")
            if staff_info:
                contact = merged_assignment.get('연락처', '')
                dept = merged_assignment.get('소속', '')
                print(f"Auto-fill: contact={contact}, dept={dept}")
            return True
        except Exception as e:
            print(f"Assignment write failed: {e}")
            return False

    except Exception as e:
        print(f"Assignment save failed: {e}")
        return False


def update_assignment_status(assign_id, new_status):
    """배정기록의 상태를 변경 (예: '취소')"""
    client = get_connection()
    if not client:
        print("❌ Google Sheets 클라이언트 연결 실패")
        return False
    try:
        # Note: 호출한 쪽에서 cache_data.clear()를 호출하므로 여기서는 호출하지 않음
        
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("배정기록")
        print(f"📝 배정기록 시트 연결 성공")

        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        print(f"📋 헤더: {headers_clean}")

        # 배정ID는 첫 열에 없을 수도 있으므로 전체 컬럼 검색
        id_col = wks.col_values(1)
        id_col_clean = [str(x).strip() for x in id_col]
        print(f"🔍 첫 번째 컬럼 내용 (첫 5개): {id_col_clean[:5]}")

        target_row = None
        for i, v in enumerate(id_col_clean):
            if v == str(assign_id).strip():
                target_row = i + 1
                break

        # 만약 첫 열에 없다면 '배정ID' 컬럼 위치를 찾아 검색
        if target_row is None and '배정ID' in headers_clean:
            col_idx = headers_clean.index('배정ID') + 1
            col_vals = wks.col_values(col_idx)
            print(f"🔍 배정ID 컬럼에서 검색 중... (컬럼 {col_idx})")
            for i, v in enumerate(col_vals):
                if str(v).strip() == str(assign_id).strip():
                    target_row = i + 1
                    break

        if target_row is None:
            print(f"❌ 배정ID '{assign_id}' not found in any column")
            return False
        
        print(f"✅ 배정 찾음: {assign_id} at row {target_row}")

        # 상태 컬럼 위치 찾기 (지급상태 또는 상태)
        status_col = None
        if '지급상태' in headers_clean:
            status_col = headers_clean.index('지급상태') + 1
            print(f"✅ 지급상태 컬럼 위치: {status_col}")
        elif '상태' in headers_clean:
            status_col = headers_clean.index('상태') + 1
            print(f"✅ 상태 컬럼 위치: {status_col}")
        else:
            print(f"❌ '지급상태' 또는 '상태' 컬럼을 찾을 수 없음. 사용 가능한 컬럼: {headers_clean}")

        if status_col:
            print(f"💾 {target_row}행 {status_col}열에 '{new_status}' 업데이트 중...")
            wks.update_cell(target_row, status_col, new_status)
            print(f"✅ 배정 {assign_id} 상태 변경 완료: {new_status}")
            return True
        else:
            print(f"❌ 상태 컬럼이 없어서 업데이트 불가")
            return False

    except Exception as e:
        print(f"❌ update_assignment_status 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


@st.cache_data(ttl=120)  # 배정기록 120초 캐시 (API 할당량 절약)
def get_assignments_by_inquiry(inquiry_id):
    """특정 문의ID의 배정기록 조회 (캐시됨)"""
    client = get_connection()
    if not client:
        return pd.DataFrame()
    
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("배정기록")
        
        # 모든 배정기록 가져오기
        all_records = wks.get_all_records()
        if not all_records:
            return pd.DataFrame()
        
        df = pd.DataFrame(all_records)
        
        # 문의ID로 필터링
        if '문의ID' in df.columns:
            df = df[df['문의ID'].astype(str).str.strip() == str(inquiry_id).strip()]
        
        # 상태 필터 (취소된 배정 제외)
        if '지급상태' in df.columns:
            df = df[df['지급상태'].astype(str).str.strip() != '취소']
        elif '상태' in df.columns:
            df = df[df['상태'].astype(str).str.strip() != '취소']
        
        return df.reset_index(drop=True)
    
    except Exception as e:
        import time
        # [429] 에러 시 더 오래 대기 후 재시도
        if "[429]" in str(e):
            print(f"API 할당량 초과, 30초 대기 후 재시도...")
            time.sleep(30)
            try:
                sh = client.open_by_key(SHEET_ID)
                wks = sh.worksheet("배정기록")
                all_records = wks.get_all_records()
                if not all_records:
                    return pd.DataFrame()
                df = pd.DataFrame(all_records)
                if '문의ID' in df.columns:
                    df = df[df['문의ID'].astype(str).str.strip() == str(inquiry_id).strip()]
                if '상태' in df.columns:
                    df = df[df['상태'].astype(str).str.strip() != '취소']
                return df.reset_index(drop=True)
            except Exception as e2:
                print(f"[429] 재시도 실패: {e2}")
                return pd.DataFrame()
        
        print(f"get_assignments_by_inquiry error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)  # 배정기록 120초 캐시 (TTL 증가)
def load_dispatch_sheet():
    """배정기록 시트를 독립적으로 로드 (TTL=10초로 더 자주 갱신)"""
    client = get_connection()
    if not client:
        return pd.DataFrame()  # None 대신 빈 DataFrame 반환
    
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("배정기록")
        
        # get_all_records 시도
        try:
            records = wks.get_all_records()
            df = pd.DataFrame(records)
            print(f"[Dispatch] Loaded {len(df)} records via get_all_records")
            if df is not None and not df.empty:
                # Normalize column names for downstream code: map common Korean headers to canonical keys
                def _canonical(col):
                    c = str(col).strip()
                    # lowercase safe check
                    k = c.replace(' ', '')
                    # exact/contains matches for expected fields
                    if any(x in k for x in ['배정id', '배정아이디', '배정ID'.lower()]):
                        return '배정ID'
                    if any(x in k for x in ['문의id', '문의아이디', '문의ID'.lower()]):
                        return '문의ID'
                    if any(x in k for x in ['이름', '성명', 'name']):
                        return '이름'
                    if any(x in k for x in ['역할', '직무', 'role']):
                        return '역할'
                    if any(x in k for x in ['일수', '근무일수']):
                        return '일수'
                    if any(x in k for x in ['단가', '단가(원)', 'rate']):
                        return '단가'
                    if any(x in k for x in ['총지급액', '총지급', '지급액']):
                        return '총지급액'
                    if any(x in k for x in ['배정일시', '배정일', 'date']):
                        return '배정일시'
                    if any(x in k for x in ['상태', 'status']):
                        return '상태'
                    if any(x in k for x in ['연락처', '전화', 'phone']):
                        return '연락처'
                    if any(x in k for x in ['소속', 'company', 'affil']):
                        return '소속'
                    return c

                col_map = {orig: _canonical(orig) for orig in df.columns}
                # If multiple original cols map to same canonical, keep first and drop duplicates after filling
                df = df.rename(columns=col_map)
                # coalesce duplicate canonical columns
                for canon in set(col_map.values()):
                    matches = [c for c in df.columns if c == canon or c.startswith(canon + '__dup')]
                    if len(matches) > 1:
                        def first_nonempty(row_vals):
                            for v in row_vals:
                                try:
                                    v_str = str(v).strip()
                                except:
                                    v_str = ''
                                if v_str and v_str not in ('nan', 'None', ''):
                                    return v_str
                            return ''
                        df[canon] = df[matches].apply(first_nonempty, axis=1)
                        drop_cols = [c for c in matches if c != canon]
                        df.drop(columns=drop_cols, inplace=True)

                # cast numeric fields
                for ncol in ['단가', '총지급액', '일수']:
                    if ncol in df.columns:
                        try:
                            df[ncol] = pd.to_numeric(df[ncol].astype(str).str.replace(',', '').replace('', '0'), errors='coerce').fillna(0).astype(int)
                        except Exception:
                            pass

                # debug print first record summary
                rec = df.iloc[0].to_dict()
                non_empty = {k: v for k, v in rec.items() if v and str(v).strip()}
                print(f"[Dispatch] Loaded {len(df)} records; sample non-empty fields: {list(non_empty.keys())}")
        except Exception as e:
            # raw 로드
            print(f"[Dispatch] get_all_records failed: {str(e)[:50]}, trying raw...")
            all_values = wks.get_all_values()
            if len(all_values) > 1:
                raw_headers = all_values[0]
                
                # 중복 헤더 처리
                seen = {}
                unique_headers = []
                for h in raw_headers:
                    key_h = str(h).strip() if h else ''
                    if key_h in seen:
                        seen[key_h] += 1
                        unique_headers.append(f"{key_h}__dup{seen[key_h]}")
                    else:
                        seen[key_h] = 0
                        unique_headers.append(key_h)
                
                records = [dict(zip(unique_headers, row)) for row in all_values[1:]]
                df = pd.DataFrame(records)
                
                # 중복 헤더 병합
                for base, cnt in seen.items():
                    if cnt > 0 and base in df.columns:
                        cols = [c for c in df.columns if c == base or c.startswith(f"{base}__dup")]
                        if len(cols) > 1:
                            def first_nonempty(row_vals):
                                for v in row_vals:
                                    v_str = str(v).strip() if v is not None else ''
                                    if v_str and v_str not in ('nan', 'None', ''):
                                        return v_str
                                return ''
                            df[base] = df[cols].apply(first_nonempty, axis=1)
                            drop_cols = [c for c in cols if c != base]
                            df.drop(columns=drop_cols, inplace=True)
                
                print(f"[Dispatch] Loaded {len(df)} records via raw + merge")
                return df
            return pd.DataFrame()
    except Exception as e:
        print(f"[Dispatch] Load error: {str(e)[:60]}")
        return pd.DataFrame()


def ensure_attendance_sheet():
    """
    출석부 시트 존재 확인 및 필요시 생성
    """
    client = get_connection()
    if not client:
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        
        # 출석부 시트 확인
        try:
            wks = sh.worksheet("출석부")
            # 이미 존재함
            return True
        except:
            # 시트가 없음 → 생성
            wks = sh.add_worksheet(title="출석부", rows=1000, cols=10)
            
            # 헤더 설정
            headers = ["배정ID", "출석일자", "상태", "비고", "기록자", "기록시간", "", "", "", ""]
            wks.update('A1', [headers], value_input_option='RAW')
            
            print("출석부 시트가 생성되었습니다.")
            return True
            
    except Exception as e:
        print(f"Attendance sheet error: {e}")
        return False


def append_row(sheet_name: str, row_values: list) -> tuple:
    """
    특정 시트에 새로운 행을 추가합니다.
    gspread의 append_row() 메서드를 사용합니다.
    
    Args:
        sheet_name: 시트 이름 ('inq', 'client', 'estimate', 등)
        row_values: 추가할 행의 값 리스트
    
    Returns:
        (성공 여부, 메시지) 튜플
    """
    client = get_connection()
    if not client:
        return False, "❌ Google 인증 실패"
    
    try:
        # 시트명 매핑
        sheet_map = {
            'inq': '문의작성',
            'client': '고객정보',
            'estimate': '견적상세',
            'dispatch': '배정기록',
            'settlement': '계약건은 청구금액적기',
            'staff': 'STAFF',
        }
        
        actual_sheet_name = sheet_map.get(sheet_name, sheet_name)
        
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet(actual_sheet_name)
        
        # 1. 현재 행 수 확인
        all_values = wks.get_all_values()
        current_rows = len(all_values)
        
        # 2. 행 용량 체크 (2002행 제한)
        if current_rows >= 2000:
            logger.warning(f"⚠️ {actual_sheet_name}: {current_rows}행 - 시트 거의 찼음!")
            return False, f"❌ 시트 용량 부족 ({current_rows}/2002 행 사용 중)"
        
        # 3. 값 정제
        safe_values = [str(v) if v is not None else "" for v in row_values]
        
        # 4. gspread의 append_row() 메서드 사용
        # 이 메서드는 마지막 행 다음에 추가합니다
        wks.append_row(safe_values, table_range=None)
        
        logger.info(f"✅ Row appended to {actual_sheet_name}: Row {current_rows + 1}")
        return True, f"✅ {actual_sheet_name}에 정상 저장됨 (행 {current_rows + 1})"
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ append_row error: {error_msg}")
        if "exceeds grid limits" in error_msg or "Max rows" in error_msg:
            return False, "❌ 시트 용량 초과 (최대 2002행)"
        return False, f"❌ 저장 실패: {error_msg[:100]}"


# ==============================================================================
# 출석부 저장 함수
# ==============================================================================

def save_attendance_record(attendance_dict):
    """
    출석부 기록 저장
    attendance_dict: {배정ID, 문의ID, 인력명, 출석날짜, 출근시간, 퇴근시간, 근무시간, 일급여, 출석상태, 사유, 비고, 기록일시}
    """
    client = get_connection()
    if not client:
        print("❌ Google Sheets 클라이언트 연결 실패")
        return False
    
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("출석부")
        print("📝 출석부 시트 연결 성공")
        
        # 헤더 확인
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        print(f"📋 헤더: {headers_clean}")
        
        # 다음 빈 행 번호 계산
        id_col_vals = wks.col_values(1)
        next_row = len(id_col_vals) + 1
        
        # 시트 확장
        if next_row > wks.row_count:
            try:
                wks.add_rows(100)
                print(f"📝 시트 확장: {next_row}행까지")
            except Exception as e:
                print(f"⚠️ 시트 확장 실패: {e}")
        
        # 실제 Google Sheets 컬럼명에 맞춰 작성
        # Col 1: 기록ID (자동생성)
        # Col 2: 배정ID
        # Col 3: 문의ID
        # Col 4: 인력명
        # Col 5: 출석날짜
        # Col 6: 출근시간
        # Col 7: 퇴근시간
        # Col 8: 근무시간
        # Col 9: 일급여
        # Col 10: 출석상태
        # Col 11: 사유
        # Col 12: 비고
        # Col 13: 기록일시
        
        record_id = f"R-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
        
        row_values = [
            record_id,  # Col 1: 기록ID
            attendance_dict.get('배정ID', ''),  # Col 2: 배정ID
            attendance_dict.get('문의ID', ''),  # Col 3: 문의ID
            attendance_dict.get('인력명', ''),  # Col 4: 인력명
            attendance_dict.get('출석날짜', ''),  # Col 5: 출석날짜
            attendance_dict.get('출근시간', ''),  # Col 6: 출근시간
            attendance_dict.get('퇴근시간', ''),  # Col 7: 퇴근시간
            attendance_dict.get('근무시간', 0),  # Col 8: 근무시간
            attendance_dict.get('일급여', 0),  # Col 9: 일급여
            attendance_dict.get('출석상태', ''),  # Col 10: 출석상태
            attendance_dict.get('사유', ''),  # Col 11: 사유
            attendance_dict.get('비고', ''),  # Col 12: 비고
            attendance_dict.get('기록일시', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),  # Col 13: 기록일시
        ]
        
        wks.update(f'A{next_row}', [row_values], value_input_option='RAW')
        print(f"✅ 출석 기록 저장: {record_id} at row {next_row}")
        return True
    
    except Exception as e:
        print(f"❌ save_attendance_record 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
