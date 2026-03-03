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

# ── 방안 A: 커넥션 풀링 ──────────────────────────────────
# gspread client와 spreadsheet 객체를 앱 프로세스 수명 동안 재사용.
# oauth2client가 내부적으로 토큰 만료 시 자동 refresh 하므로 안전.
# @st.cache_resource는 모든 세션이 공유하는 싱글턴 캐시.

@st.cache_resource
def _get_cached_client():
    """gspread 클라이언트 1회 생성 → 이후 재사용 (인증 오버헤드 제거)"""
    try:
        try:
            st_secrets = st.secrets
        except Exception:
            st_secrets = None
        client = auth.get_gspread_client(secrets_path="secrets.json", st_secrets=st_secrets, scopes=SCOPES)
        if client:
            print("[Pool] gspread client created (cached)")
        return client
    except Exception as e:
        print(f"[Pool] client creation failed: {e}")
        return None

@st.cache_resource
def _get_cached_spreadsheet():
    """스프레드시트 객체 1회 생성 → 이후 재사용 (open_by_key 오버헤드 제거)"""
    client = _get_cached_client()
    if not client:
        return None
    try:
        sh = client.open_by_key(SHEET_ID)
        print(f"[Pool] spreadsheet opened (cached): {SHEET_ID[:12]}...")
        return sh
    except Exception as e:
        print(f"[Pool] spreadsheet open failed: {e}")
        return None

# ── 방안 B: Worksheet 객체 캐시 ──────────────────────────
# 시트명 → worksheet 객체를 메모리 캐시. ensure_*_sheet() 역할도 통합.
# 시트가 없으면 자동 생성 (기존 ensure_ 로직 흡수).
_worksheet_cache = {}  # {sheet_name: worksheet_object}

# 시트별 헤더 정의 (ensure_* 함수의 헤더 정의를 통합)
_SHEET_HEADERS = {
    "출석부": ["기록ID", "배정ID", "문의ID", "인력명", "출석날짜", "출근시간", "퇴근시간",
               "근무시간", "일급여", "출석상태", "사유", "비고", "기록일시"],
    "평가표": ["평가ID", "배정ID", "인력명", "현장명", "근태", "수행", "외모",
               "팀워크", "현장적응", "총점", "평가등급", "평가자", "평가일시",
               "강점", "개선점", "재추천", "비고"],
    "지급내역": ["지급ID", "배정ID", "문의ID", "인력명", "현장명", "파견기간", "파견일수",
                "기본급", "야근비", "식사비", "교통비", "보너스", "소계",
                "세금공제", "최종지급액", "지급상태", "지급일", "지급담당자",
                "은행명", "계좌번호", "주민등록번호", "비고"],
}

def _get_worksheet(sheet_name: str):
    """워크시트 객체를 캐시에서 반환. 없으면 1회 API → 캐시 저장.
    시트가 존재하지 않으면 _SHEET_HEADERS에 정의된 경우 자동 생성.
    이후 호출은 API 0회 (메모리에서 즉시 반환).
    """
    if sheet_name in _worksheet_cache:
        return _worksheet_cache[sheet_name]
    
    sh = _get_cached_spreadsheet()
    if not sh:
        return None
    
    try:
        wks = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # 시트가 없으면 자동 생성 (ensure_* 역할 통합)
        if sheet_name in _SHEET_HEADERS:
            headers = _SHEET_HEADERS[sheet_name]
            wks = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
            wks.update('A1', [headers], value_input_option='RAW')
            print(f"[Pool] 시트 '{sheet_name}' 자동 생성 (헤더 {len(headers)}컬럼)")
        else:
            print(f"[Pool] 시트 '{sheet_name}' 없음 (자동생성 미정의)")
            return None
    except Exception as e:
        print(f"[Pool] worksheet('{sheet_name}') 오류: {e}")
        return None
    
    _worksheet_cache[sheet_name] = wks
    return wks

def _invalidate_worksheet_cache(sheet_name: str = None):
    """워크시트 캐시 무효화. sheet_name 지정 시 해당 시트만, None이면 전체."""
    if sheet_name:
        _worksheet_cache.pop(sheet_name, None)
    else:
        _worksheet_cache.clear()

def _invalidate_connection_pool():
    """커넥션 풀 전체 무효화 (인증 오류 복구용)"""
    _worksheet_cache.clear()
    try:
        _get_cached_client.clear()
    except Exception:
        pass
    try:
        _get_cached_spreadsheet.clear()
    except Exception:
        pass
    print("[Pool] Connection pool invalidated")

def get_connection(max_retries=3):
    """Google Sheets 연결 — 캐시된 클라이언트 반환 (기존 API 호환 유지).
    
    대부분의 함수는 이제 _get_cached_spreadsheet()을 직접 사용하지만,
    기존 코드와의 호환성을 위해 유지합니다. 내부적으로 풀링된 객체를 반환.
    """
    import time as _time
    for attempt in range(max_retries):
        try:
            client = _get_cached_client()
            if client:
                return client
            # 캐시가 None이면 풀 리셋 후 재시도
            _invalidate_connection_pool()
            client = _get_cached_client()
            return client
        except Exception as e:
            err_msg = str(e)
            is_transient = any(code in err_msg for code in ['503', '429', '500', 'unavailable', 'Unavailable', 'UNAVAILABLE'])
            if is_transient and attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                print(f"⏳ Google API 일시 오류 (시도 {attempt+1}/{max_retries}), {wait}초 후 재시도... : {err_msg[:80]}")
                _invalidate_connection_pool()
                _time.sleep(wait)
                continue
            try:
                st.error(f"❌ 시트 연결 실패: {e}")
            except Exception:
                pass
            return None

# ---------------------------------------------------------
# 2. 데이터 로드 (최신성 유지 및 타입 정제)
# ---------------------------------------------------------
@st.cache_data(ttl=1800)  # 1800초(30분) - 안정적 캐시
def load_all_data():
    data = {}
    client = get_connection()
    
    # 필수 시트 로드 (견적 시스템용 Roles/Factors/Guides + 배정/정산 포함)
    sheet_map = {
        "inq": "문의작성",
        "staff": "STAFF",
        "client": "고객정보",
        "roles": "Roles",
        "factors": "Factors",
        "guides": "Guides",
        "estimate": "견적상세",
        "dispatch": "배정기록",
        "settlement": "계약건은청구금액적기",
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
@st.cache_data(ttl=1800)  # 30분 캐시
def load_dispatch_data():
    """배정기록과 계약건은청구금액적기를 함께 로드 (인력배정/정산 탭에서 사용)"""
    client = get_connection()
    if not client:
        return {"dispatch": pd.DataFrame(), "settlement": pd.DataFrame(), "payment": pd.DataFrame()}
    
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
        
        # 지급내역 로드 (payment 캐시 활용)
        try:
            result["payment"] = _load_payment_sheet_cached()
            print(f"[OK] payment sheet: {len(result['payment'])} rows loaded")
        except Exception as e:
            print(f"[WARN] payment sheet load failed: {str(e)[:60]}")
            result["payment"] = pd.DataFrame()

        return result
    except Exception as e:
        print(f"[Error] dispatch data load error: {str(e)[:60]}")
        return {"dispatch": pd.DataFrame(), "settlement": pd.DataFrame(), "payment": pd.DataFrame()}


# ---------------------------------------------------------
# 2-2. 세션 기반 스마트 캐싱 (메뉴 전환 시 즉시 응답)
# ---------------------------------------------------------

def get_data():
    """
    세션에 캐시된 메인 데이터를 반환합니다.
    - 처음 호출 시: 구글 시트에서 로드 후 session_state에 보관
    - 이후 호출 시: session_state에서 즉시 반환 (0초)
    - invalidate_data() 호출 후: 다음 호출 시 자동으로 새로 로드
    """
    if '_app_data' not in st.session_state or st.session_state['_app_data'] is None:
        progress_bar = st.progress(0, text="📡 데이터를 불러오는 중...")
        try:
            st.session_state['_app_data'] = load_all_data_with_progress(progress_bar)
        except Exception as e:
            progress_bar.empty()
            st.error(f"❌ 데이터 로드 실패: {e}")
            # 빈 데이터 반환 (앱은 계속 동작)
            st.session_state['_app_data'] = {
                "inq": pd.DataFrame(), "staff": pd.DataFrame(), "client": pd.DataFrame(),
                "roles": pd.DataFrame(), "factors": pd.DataFrame(), "guides": pd.DataFrame(),
                "estimate": pd.DataFrame(), "dispatch": pd.DataFrame(), "settlement": pd.DataFrame(),
            }
        st.session_state['_data_loaded_at'] = datetime.now().strftime("%H:%M:%S")
        print(f"[SESSION] Main data loaded at {st.session_state['_data_loaded_at']}")
    return st.session_state['_app_data']


def load_all_data_with_progress(progress_bar=None):
    """진행바 표시와 함께 데이터 로드 (개별 시트 타임아웃 포함)
    모든 시트를 사전로딩하여 중간 로딩을 최소화합니다.
    """
    import time as _time

    # 메인 시트 + 배정/정산 + 견적품목/견적안/출석부/지급내역/평가표 모두 사전로딩
    sheet_map = {
        "inq": "문의작성",
        "staff": "STAFF",
        "client": "고객정보",
        "roles": "Roles",
        "factors": "Factors",
        "guides": "Guides",
        "estimate": "견적상세",
        "dispatch": "배정기록",
        "settlement": "계약건은청구금액적기",
        "estimate_items": "견적품목",
        "estimate_versions": "견적안",
        "attendance": "출석부",
        "payment": "지급내역",
        "evaluation": "평가표",
    }
    data = {}
    client = get_connection()

    if not client:
        if progress_bar:
            progress_bar.empty()
        return {k: pd.DataFrame() for k in sheet_map}

    try:
        sh = client.open_by_key(SHEET_ID)
        total = len(sheet_map)

        for idx, (key, tab_name) in enumerate(sheet_map.items()):
            if progress_bar:
                pct = int((idx / total) * 100)
                progress_bar.progress(pct, text=f"📡 {tab_name} 로딩 중... ({idx+1}/{total})")

            try:
                wks = sh.worksheet(tab_name)
                df = None
                try:
                    records = wks.get_all_records()
                    df = pd.DataFrame(records)
                    print(f"[OK] {tab_name}: {len(df)} rows loaded")
                except Exception as e:
                    print(f"[WARN] {tab_name} get_all_records failed, trying raw ({str(e)[:60]})")
                    try:
                        all_values = wks.get_all_values()
                        if len(all_values) > 1:
                            raw_headers = all_values[0]
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
                            print(f"[OK] {tab_name}: {len(df)} rows (raw)")
                        else:
                            df = pd.DataFrame()
                    except Exception as raw_error:
                        print(f"[ERROR] {tab_name} raw load failed: {str(raw_error)[:60]}")
                        df = pd.DataFrame()

                if df is None:
                    df = pd.DataFrame()

                cols_to_str = ['연락처', '문의ID', '사업자번호', '대표자']
                for col in cols_to_str:
                    if col in df.columns:
                        df[col] = df[col].astype(str).str.strip().replace(['nan', 'None'], '')

                data[key] = df

            except gspread.exceptions.WorksheetNotFound:
                print(f"[ERROR] Sheet not found: {tab_name}")
                data[key] = pd.DataFrame()
            except Exception as e:
                print(f"[ERROR] {tab_name}: {type(e).__name__}: {str(e)[:100]}")
                data[key] = pd.DataFrame()

        if progress_bar:
            progress_bar.progress(100, text="✅ 데이터 로드 완료!")
            _time.sleep(0.3)
            progress_bar.empty()

    except Exception as e:
        if progress_bar:
            progress_bar.empty()
        st.error(f"❌ 시트 파일 접속 불가: {e}")
        return {k: pd.DataFrame() for k in sheet_map}

    return data


def get_dispatch():
    """
    세션에 캐시된 배정/정산 데이터를 반환합니다.
    초기 로딩 시 이미 포함되어 있으면 그대로 사용, 없으면 지연 로드.
    **payment는 항상 _load_payment_sheet_cached()에서 fresh하게 가져옴** (캐시 불일치 방지).
    """
    if '_dispatch_data' not in st.session_state or st.session_state['_dispatch_data'] is None:
        # 초기 로딩에서 이미 읽어왔는지 확인
        app_data = st.session_state.get('_app_data')
        if app_data and 'dispatch' in app_data and not app_data['dispatch'].empty:
            st.session_state['_dispatch_data'] = {
                "dispatch": app_data['dispatch'],
                "settlement": app_data.get('settlement', pd.DataFrame()),
                "payment": _load_payment_sheet_cached(),
            }
            # 배정기록 시트 컨텍스트 프리-워밍
            try:
                _get_assign_sheet_ctx()
                print("[SESSION] Dispatch data from initial load + fresh payment + assign ctx warmed")
            except Exception as e:
                print(f"[SESSION] Dispatch data from initial load (assign ctx warm failed: {e})")
        else:
            with st.spinner("📡 배정 데이터를 불러오는 중..."):
                st.session_state['_dispatch_data'] = load_dispatch_data()
                try:
                    _get_assign_sheet_ctx()
                    print("[SESSION] Dispatch data loaded + assign ctx warmed")
                except Exception as e:
                    print(f"[SESSION] Dispatch data loaded (assign ctx warm failed: {e})")
    return st.session_state['_dispatch_data']


def invalidate_data():
    """
    데이터를 저장/수정한 후 호출합니다.
    세션 캐시를 비워서 다음 조회 시 구글 시트에서 최신 데이터를 가져옵니다.
    (구글 시트 저장 자체에는 영향 없음 — 읽기 캐시만 초기화)
    """
    for key in ['_app_data', '_dispatch_data', '_data_loaded_at']:
        st.session_state.pop(key, None)
    # 함수별 캐시도 개별 초기화 (st.cache_data.clear() 대신 정밀 초기화)
    try:
        load_all_data.clear()
    except Exception:
        pass
    try:
        load_dispatch_data.clear()
    except Exception:
        pass
    print("[SESSION] Data cache invalidated")


def invalidate_main_only():
    """메인 데이터만 초기화 (배정/정산 캐시는 유지).
    문의 저장 등 메인 시트만 변경하는 작업 후 사용."""
    st.session_state.pop('_app_data', None)
    st.session_state.pop('_data_loaded_at', None)
    try:
        load_all_data.clear()
    except Exception:
        pass
    print("[SESSION] Main data cache invalidated (dispatch/settlement preserved)")


def invalidate_dispatch_only():
    """배정/정산 관련 캐시만 선택적으로 초기화 (메인 7시트는 보존).
    인력 배정/취소/확정 등 배정기록만 변경하는 작업 후 사용.
    메인 데이터(문의, STAFF, 고객 등)는 그대로 유지 → rerun 시 재로드 불필요.
    """
    # 배정/정산 세션 캐시만 제거
    st.session_state.pop('_dispatch_data', None)
    # st.cache_data 기반 함수 캐시 초기화
    try:
        load_dispatch_data.clear()
    except Exception:
        pass
    try:
        load_dispatch_sheet.clear()
    except Exception:
        pass
    try:
        get_assignments_by_inquiry.clear()
    except Exception:
        pass
    try:
        get_candidates_by_inquiry.clear()
    except Exception:
        pass
    # 배정 시트 컨텍스트 캐시도 무효화
    _invalidate_assign_ctx()
    print("[SESSION] Dispatch-only cache invalidated (main data preserved)")


def ensure_inquiry_headers():
    """
    문의작성 시트에 '복장', '식사', '주차' 헤더(24~26번)가 없으면 자동 추가합니다.
    기존 데이터 중 특이사항에 [복장:xxx] 등으로 합쳐진 항목을 개별 컬럼으로 마이그레이션합니다.
    앱 시작 시 1회만 실행됩니다.
    """
    if st.session_state.get('_inq_headers_checked'):
        return  # 이미 확인 완료
    
    client = get_connection()
    if not client:
        return
    
    try:
        import re as _re
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("문의작성")
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        
        needed = ['복장', '식사', '주차']
        missing = [h for h in needed if h not in headers_clean]
        
        if not missing:
            st.session_state['_inq_headers_checked'] = True
            print("[OK] 문의작성 시트: 복장/식사/주차 헤더 확인됨")
            return
        
        # ── 1) 누락된 헤더 추가 ──
        next_col = len(headers) + 1
        cells_to_add = []
        col_map = {}  # {'복장': col_index, ...}
        for h in missing:
            cells_to_add.append(gspread.Cell(1, next_col, h))
            col_map[h] = next_col
            next_col += 1
        wks.update_cells(cells_to_add, value_input_option='RAW')
        print(f"[OK] 문의작성 시트: 헤더 추가됨 → {missing}")
        
        # ── 2) 기존 데이터 마이그레이션: 특이사항에서 [복장:xxx] 파싱 → 개별 컬럼 ──
        if '특이사항' in headers_clean:
            note_col_idx = headers_clean.index('특이사항')  # 0-based
            all_values = wks.get_all_values()
            
            if len(all_values) > 1:
                cells_to_update = []
                patterns = {
                    '복장': _re.compile(r'\[복장:([^\]]+)\]'),
                    '식사': _re.compile(r'\[식사:([^\]]+)\]'),
                    '주차': _re.compile(r'\[주차:([^\]]+)\]'),
                }
                
                migrated = 0
                for row_idx, row in enumerate(all_values[1:], start=2):
                    if note_col_idx >= len(row):
                        continue
                    note_text = str(row[note_col_idx]).strip()
                    if not note_text:
                        continue
                    
                    note_modified = note_text
                    for field_name, pattern in patterns.items():
                        match = pattern.search(note_text)
                        if match and field_name in col_map:
                            cells_to_update.append(
                                gspread.Cell(row_idx, col_map[field_name], match.group(1).strip())
                            )
                            note_modified = note_modified.replace(match.group(0), '').strip()
                    
                    if note_modified != note_text:
                        cells_to_update.append(
                            gspread.Cell(row_idx, note_col_idx + 1, note_modified)
                        )
                        migrated += 1
                
                if cells_to_update:
                    for i in range(0, len(cells_to_update), 50):
                        batch = cells_to_update[i:i+50]
                        wks.update_cells(batch, value_input_option='RAW')
                    print(f"[OK] 문의작성 마이그레이션: {migrated}건 처리됨")
        
        st.session_state['_inq_headers_checked'] = True
        invalidate_data()
        print("[OK] 문의작성 시트 헤더 확장 완료")
        
    except Exception as e:
        print(f"[WARN] ensure_inquiry_headers 실패: {e}")
        st.session_state['_inq_headers_checked'] = True


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


def update_estimate_send_status(inquiry_id: str, send_method: str, send_memo: str = ""):
    """
    견적상세 시트의 발송 상태를 업데이트합니다.
    발송여부, 발송일시, 발송방법, 발송메모 4개 컬럼을 한 번에 업데이트합니다.
    컬럼이 없으면 자동으로 추가합니다.

    Args:
        inquiry_id (str): 문의ID
        send_method (str): 발송방법 (이메일/카카오톡/팩스/직접전달)
        send_memo (str): 발송 메모 (선택)
    Returns:
        bool: 성공 여부
    """
    client = get_connection()
    if not client:
        return False

    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("견적상세")
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]

        # 필요한 컬럼이 없으면 자동 추가 (시트 크기 부족 시 자동 확장)
        send_cols = ["발송여부", "발송일시", "발송방법", "발송메모"]
        missing_cols = [c for c in send_cols if c not in headers_clean]
        if missing_cols:
            current_cols = wks.col_count
            needed_cols = len(headers_clean) + len(missing_cols)
            if needed_cols > current_cols:
                wks.resize(cols=needed_cols + 2)
                logger.info(f"📝 견적상세 시트 컬럼 확장: {current_cols} → {needed_cols + 2}")
            for col_name in missing_cols:
                next_col = len(headers_clean) + 1
                wks.update_cell(1, next_col, col_name)
                headers_clean.append(col_name)
                logger.info(f"📝 견적상세 시트에 '{col_name}' 컬럼 추가 (col {next_col})")

        # 문의ID로 행 찾기
        id_col_idx = headers_clean.index('문의ID') + 1 if '문의ID' in headers_clean else 1
        id_col = wks.col_values(id_col_idx)
        id_col_clean = [str(x).strip() for x in id_col]

        target_row = None
        for i, cid in enumerate(id_col_clean):
            if cid == str(inquiry_id).strip():
                target_row = i + 1
                break

        if target_row is None:
            logger.error(f"❌ 견적상세에서 문의ID '{inquiry_id}'를 찾을 수 없습니다")
            return False

        # 4개 컬럼 일괄 업데이트
        from gspread.cell import Cell
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        cells = [
            Cell(row=target_row, col=headers_clean.index("발송여부") + 1, value="발송완료"),
            Cell(row=target_row, col=headers_clean.index("발송일시") + 1, value=now_str),
            Cell(row=target_row, col=headers_clean.index("발송방법") + 1, value=send_method),
            Cell(row=target_row, col=headers_clean.index("발송메모") + 1, value=send_memo),
        ]
        wks.update_cells(cells, value_input_option='RAW')
        logger.info(f"✅ 견적 발송 기록: {inquiry_id} → {send_method} ({now_str})")
        return True

    except Exception as e:
        logger.error(f"❌ update_estimate_send_status 오류: {e}")
        return False


def cancel_estimate_send_status(inquiry_id: str):
    """
    견적 발송 상태를 취소(초기화)합니다.
    """
    client = get_connection()
    if not client:
        return False

    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("견적상세")
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]

        if "발송여부" not in headers_clean:
            return False

        id_col_idx = headers_clean.index('문의ID') + 1 if '문의ID' in headers_clean else 1
        id_col = wks.col_values(id_col_idx)
        id_col_clean = [str(x).strip() for x in id_col]

        target_row = None
        for i, cid in enumerate(id_col_clean):
            if cid == str(inquiry_id).strip():
                target_row = i + 1
                break

        if target_row is None:
            return False

        from gspread.cell import Cell
        cells = [
            Cell(row=target_row, col=headers_clean.index("발송여부") + 1, value=""),
            Cell(row=target_row, col=headers_clean.index("발송일시") + 1, value=""),
            Cell(row=target_row, col=headers_clean.index("발송방법") + 1, value=""),
            Cell(row=target_row, col=headers_clean.index("발송메모") + 1, value=""),
        ]
        wks.update_cells(cells, value_input_option='RAW')
        logger.info(f"✅ 견적 발송 취소: {inquiry_id}")
        return True

    except Exception as e:
        logger.error(f"❌ cancel_estimate_send_status 오류: {e}")
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


def update_settlement_progress(inquiry_id, progress):
    """계약건은청구금액적기 시트의 '진행상황' 컬럼만 업데이트
    
    Args:
        inquiry_id: 문의ID
        progress: 진행상황 값 (계약체결/행사준비/행사종료/정산완료)
    Returns:
        bool: 성공 여부
    """
    return update_cell("계약건은청구금액적기", inquiry_id, "진행상황", progress)


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
        
        # 2. 시트 헤더 읽기 + 누락 컬럼 자동 추가
        headers = wks.row_values(1)
        headers_clean = [str(h).strip() for h in headers]
        
        # 견적 메타데이터 저장에 필요한 컬럼이 없으면 자동 추가
        _required_extra = ['복장', '식사', '주차', '특이사항', '부대비용', '비고']
        _missing = [c for c in _required_extra if c not in headers_clean]
        if _missing:
            from gspread.cell import Cell as _Cell
            _start_col = len(headers_clean) + 1
            _header_cells = []
            for _mi, _col_name in enumerate(_missing):
                _header_cells.append(_Cell(row=1, col=_start_col + _mi, value=_col_name))
            wks.update_cells(_header_cells, value_input_option='RAW')
            headers_clean.extend(_missing)
            logger.info(f"📝 견적상세 컬럼 자동 추가: {_missing}")
        
        # 3. 문의ID로 기존 행 찾기 (중복 방지)
        target_id = str(est_data.get('문의ID', '')).strip()
        
        # 문의ID 컬럼 위치 찾기 (견적ID가 첫 컬럼일 수 있음)
        inquiry_col_idx = 1  # 기본값
        if '문의ID' in headers_clean:
            inquiry_col_idx = headers_clean.index('문의ID') + 1
        
        id_col_values = wks.col_values(inquiry_col_idx)
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
            if header == "견적ID":
                # 기존 행이면 기존 견적ID 유지, 새 행이면 생성
                if target_id in id_col_clean:
                    existing_row = wks.row_values(target_row)
                    row_data[col_idx] = existing_row[0] if existing_row else f"EST-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
                else:
                    row_data[col_idx] = f"EST-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
            elif header == "문의ID":
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
            elif header == "예상수익":
                supply = int(est_data.get('공급가액', 0))
                cost = int(est_data.get('매입원가', 0))
                additional = int(est_data.get('부대비용', 0))
                row_data[col_idx] = supply - cost - additional
            elif header == "사업자번호":
                row_data[col_idx] = metadata.get('사업자번호', '')
            elif "수익" in header and ("률" in header or "율" in header):
                supply = int(est_data.get('공급가액', 0))
                cost = int(est_data.get('매입원가', 0))
                profit = supply - cost
                margin = f"{round((profit / supply * 100), 1)}%" if supply > 0 else "0%"
                row_data[col_idx] = margin
            elif header == "대표자":
                row_data[col_idx] = metadata.get('대표자', '')
            elif header == "담당자명" or header == "담당자":
                row_data[col_idx] = metadata.get('담당자', metadata.get('책임자', ''))
            elif header == "연락처":
                row_data[col_idx] = metadata.get('연락처', '')
            elif header == "복장":
                row_data[col_idx] = metadata.get('복장', '')
            elif header == "식사":
                row_data[col_idx] = metadata.get('식사', '')
            elif header == "주차":
                row_data[col_idx] = metadata.get('주차', '')
            elif header == "특이사항":
                row_data[col_idx] = metadata.get('특이사항', '')
            elif header == "부대비용":
                row_data[col_idx] = int(est_data.get('부대비용', 0))
            elif header == "기록일시":
                row_data[col_idx] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif header in ["메모", "비고", "Notes", "Meta"]:
                row_data[col_idx] = metadata_json
            elif header.startswith("발송"):
                # 발송여부/발송일시/발송방법/발송메모 — 기존 값 유지 (견적 저장 시 덮어쓰지 않음)
                pass
            else:
                # 기존 값 유지 (빈 값으로 덮어쓰지 않음)
                pass
        
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
    
    실제 시트 헤더 (27컬럼):
      문의ID, 현장명, 업체, 파견일자, 책임자, 현장주소,
      청구금액, 공급가액, 부가세, 받은금액, 잔액, 진행상황,
      입금여부, 세금계산서 발행여부, 지급액, 계산서금액, 3.3%, 구분, 이익,
      사업자번호, 대표자, 이메일, 법인명,
      내용(품목), 연락처, 발행요청사항, 사업자등록증URL
    
    Args:
        settlement_data (dict): 저장할 데이터
        site_info (dict, optional): 현장 정보
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
        headers_clean = [str(h).strip().replace('\n', ' ') for h in headers]
        
        # 2. 현재 데이터 행 확인
        all_values = wks.get_all_values()
        current_rows = len(all_values)
        
        # 3. 행 용량 체크 (990행 넘으면 아카이브)
        if current_rows >= 990:
            logger.warning(f"⚠️ 계약건은청구금액적기: {current_rows}행 - 아카이브로 전환")
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
            target_row = id_col_clean.index(target_id) + 1
            logger.info(f"📝 기존 계약건 업데이트: [{wks.title}] Row {target_row}")
        else:
            target_row = current_rows + 1
            logger.info(f"📝 새 계약건 저장: [{wks.title}] Row {target_row}")
        
        # 6. 현장 정보 준비
        site_info = site_info or {}
        
        # 7. 헤더 → 값 매핑 (실제 시트 헤더 기준)
        #    save_settlement_record에 전달된 키를 실제 헤더에 매핑
        field_map = {
            "문의ID":             lambda: target_id,
            "현장명":             lambda: site_info.get('현장명', settlement_data.get('행사명', '')),
            "업체":              lambda: settlement_data.get('업체명', settlement_data.get('업체', '')),
            "파견일자":           lambda: site_info.get('파견일자', ''),
            "책임자":             lambda: site_info.get('책임자', ''),
            "현장주소":           lambda: site_info.get('현장주소', settlement_data.get('현장주소', '')),
            "청구금액":           lambda: settlement_data.get('합계금액', settlement_data.get('청구금액', 0)),
            "공급가액":           lambda: settlement_data.get('공급가액', 0),
            "부가세":             lambda: settlement_data.get('부가세', 0),
            "진행상황":           lambda: settlement_data.get('상태', settlement_data.get('진행상황', '')),
            "세금계산서 발행여부":  lambda: settlement_data.get('세금계산서 발행여부', settlement_data.get('발행여부', '')),
            "사업자번호":          lambda: settlement_data.get('사업자번호', ''),
            "대표자":             lambda: settlement_data.get('대표자', ''),
            "이메일":             lambda: settlement_data.get('이메일', ''),
            "법인명":             lambda: settlement_data.get('법인명', settlement_data.get('업체명', '')),
            "내용(품목)":         lambda: settlement_data.get('내용(품목)', settlement_data.get('내용', settlement_data.get('품목', ''))),
            "연락처":             lambda: settlement_data.get('연락처', ''),
            "발행요청사항":        lambda: settlement_data.get('발행요청사항', ''),
            "사업자등록증URL":     lambda: settlement_data.get('사업자등록증URL', ''),
            "사업자등록증데이터":    lambda: settlement_data.get('사업자등록증데이터', ''),
        }
        
        from gspread.cell import Cell
        cells_to_update = []
        
        for col_idx, header in enumerate(headers_clean, 1):
            if header in field_map:
                value = field_map[header]()
                # 숫자 변환
                if header in ("청구금액", "공급가액", "부가세"):
                    try:
                        value = int(float(str(value).replace(',', '').replace('원', '').strip() or 0))
                    except (ValueError, TypeError):
                        value = 0
            else:
                # 매핑되지 않은 컬럼 — 기존 행이면 기존 값 유지, 새 행이면 빈값
                if target_id in id_col_clean and target_row <= len(all_values):
                    existing_row = all_values[target_row - 1]
                    value = existing_row[col_idx - 1] if col_idx - 1 < len(existing_row) else ""
                else:
                    value = ""
            
            # ✅ Google Sheets 셀 제한: 50,000자 초과 시 빈값 처리 (base64 잘라내면 깨짐)
            if isinstance(value, str) and len(value) > 49000:
                logger.warning(f"⚠️ {header} 컬럼 데이터 초과 ({len(value)}자) → 빈값 처리")
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
            elif col_clean == '주민등록번호':
                val = staff_row[col]
                info['주민등록번호'] = str(val).strip() if val and str(val).strip() else ''
            elif col_clean == '은행명':
                val = staff_row[col]
                info['은행명'] = str(val).strip() if val and str(val).strip() else ''
            elif col_clean == '계좌번호':
                val = staff_row[col]
                info['계좌번호'] = str(val).strip() if val and str(val).strip() else ''
            elif '단가' in col_clean and '기본' in col_clean:
                try:
                    info['기본단가'] = safe_int(staff_row[col])
                except:
                    pass
        
        return info
    except Exception as e:
        print(f"Staff lookup error: {e}")
        return None


# ==============================================================================
# 후보군 & 배치 배정 API (v5.1 인력배정 업그레이드)
# ==============================================================================
# 지급상태 흐름: 후보 → 배정중 → 확정 → 취소 (이탈)
# 후보: 후보풀에 등록된 상태 (서버 저장, 새로고침 안전)
# 배정중: 직군에 배정되었으나 최종 확정 전
# 확정: 배정 확정 (장기건은 일정 추후입력 가능)

ASSIGN_STATUS_CANDIDATE = '후보'
ASSIGN_STATUS_ASSIGNED = '배정중'
ASSIGN_STATUS_CONFIRMED = '확정'
ASSIGN_STATUS_CANCELLED = '취소'


# ── 배정기록 시트 컨텍스트 캐싱 (API 호출 최소화) ──
_assign_ctx_cache = {}  # {wks, headers, id_col, col_map, ts}

def _get_assign_sheet_ctx(force=False):
    """배정기록 시트의 워크시트 객체 + 헤더 + ID열을 캐싱하여 반환.
    60초 TTL. 매 함수 호출마다 open_by_key/worksheet/row_values/col_values를 반복 안 하도록.
    Returns: (wks, headers_clean, id_col_clean, col_map)
      col_map: {논리명: 1-based 컬럼 인덱스}
    """
    import time as _time
    cache = _assign_ctx_cache
    now = _time.time()
    if not force and cache.get('ts') and (now - cache['ts']) < 60:
        return cache['wks'], cache['headers'], cache['id_col'], cache['col_map']

    client = get_connection()
    if not client:
        raise ConnectionError("Google Sheets 연결 실패")
    sh = client.open_by_key(SHEET_ID)
    wks = sh.worksheet("배정기록")
    headers = [str(h).strip() for h in wks.row_values(1)]

    # 근무일자 컬럼 자동 추가 (16번째 — 최초 1회)
    if '근무일자' not in headers:
        try:
            next_col = len(headers) + 1
            wks.update_cell(1, next_col, '근무일자')
            headers.append('근무일자')
            print(f"[Migration] '근무일자' 헤더 추가 (Col {next_col})")
        except Exception as e:
            print(f"[Migration] 근무일자 헤더 추가 실패: {e}")

    # 팀코드/결제대상/현장참여 헤더 자동 추가 (17-19번째 — 최초 1회)
    _team_headers = ['팀코드', '결제대상', '현장참여']
    for _th in _team_headers:
        if _th not in headers:
            try:
                next_col = len(headers) + 1
                wks.update_cell(1, next_col, _th)
                headers.append(_th)
                print(f"[Migration] '{_th}' 헤더 추가 (Col {next_col})")
            except Exception as e:
                print(f"[Migration] {_th} 헤더 추가 실패: {e}")

    # ── 참고: 팀코드/결제대상/현장참여는 투입시작일/투입종료일/메모 뒤(Col 20~22)에 위치함 ──
    # save_candidates_batch는 헤더 기반으로 정확한 위치에 저장하므로 마이그레이션 불필요

    id_col = [str(v).strip() for v in wks.col_values(1)]

    # 자주 쓰는 컬럼 위치 사전 계산
    def _fc(*names):
        for n in names:
            if n in headers:
                return headers.index(n) + 1
        return None

    col_map = {
        '직무': _fc('직무', '역할'),
        '지급상태': _fc('지급상태', '상태'),
        '지급단가': _fc('지급단가', '단가'),
        '근무일수': _fc('근무일수', '일수'),
        '총지급액': _fc('총지급액'),
        '근무일자': _fc('근무일자'),
        '구분': _fc('구분'),
        '인력명': _fc('인력명', '이름'),
        '팀코드': _fc('팀코드'),
        '결제대상': _fc('결제대상'),
        '현장참여': _fc('현장참여'),
    }

    cache.update(wks=wks, headers=headers, id_col=id_col, col_map=col_map, ts=now)
    return wks, headers, id_col, col_map


def _find_row(id_col, assign_id):
    """id_col 리스트에서 assign_id의 1-based 행 번호를 반환. 없으면 None."""
    aid = str(assign_id).strip()
    for i, v in enumerate(id_col):
        if v == aid:
            return i + 1
    return None


def _invalidate_assign_ctx():
    """캐시된 컨텍스트 무효화 (행 추가/삭제 후 호출)"""
    _assign_ctx_cache.clear()


def save_candidates_batch(inquiry_id: str, event_name: str, candidates: list):
    """후보 인력 일괄 등록 (배정기록 시트에 '후보' 상태로 저장)
    
    candidates: list of dict with keys:
        인력명, 구분(본사/외부), 직무(빈칸 가능 - 추후 배정), 지급단가, 근무일수
    Returns: (성공수, 실패수)
    
    ★ 헤더 기반 저장: 실제 시트 헤더를 읽어 컬럼 위치를 동적으로 결정.
       투입시작일/투입종료일/메모 등 추가 컬럼이 있어도 정확한 위치에 기록됨.
    """
    client = get_connection()
    if not client:
        return 0, len(candidates)
    try:
        invalidate_dispatch_only()
        
        # ★ 캐시된 컨텍스트에서 실제 헤더 + 워크시트 가져오기
        wks, headers, id_col_vals, col_map = _get_assign_sheet_ctx(force=True)
        
        next_row = len(id_col_vals) + 1
        
        # 행 부족 시 확장
        needed_rows = next_row + len(candidates)
        if needed_rows > wks.row_count:
            wks.add_rows(max(200, needed_rows - wks.row_count + 50))
        
        # 헤더명 → 0-based index 매핑
        hdr_idx = {h: i for i, h in enumerate(headers)}
        total_cols = len(headers)
        
        # 배치 데이터 준비 (헤더 순서에 맞춰 배치)
        batch_rows = []
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for c in candidates:
            assign_id = f"A-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
            staff_name = str(c.get('인력명', '')).strip()
            staff_info = _lookup_staff_info(staff_name) if staff_name else None
            
            contact = c.get('연락처', '')
            ssn = c.get('주민등록번호', '')
            bank = c.get('은행명', '')
            account = c.get('계좌번호', '')
            if staff_info:
                if not contact: contact = staff_info.get('연락처', '')
                if not ssn: ssn = staff_info.get('주민등록번호', '')
                if not bank: bank = staff_info.get('은행명', '')
                if not account: account = staff_info.get('계좌번호', '')
            
            # 빈 행 (헤더 수 만큼)
            row = [''] * total_cols
            
            # 헤더명으로 정확한 위치에 값 배치
            def _put(header_name, value):
                if header_name in hdr_idx:
                    row[hdr_idx[header_name]] = value
            
            _put('배정ID', assign_id)
            _put('문의ID', str(inquiry_id))
            _put('행사명', str(event_name))
            _put('인력명', staff_name)
            _put('구분', c.get('구분', '외부'))
            _put('직무', c.get('직무', ''))
            _put('연락처', contact)
            _put('주민등록번호', ssn)
            _put('은행명', bank)
            _put('계좌번호', account)
            _put('지급단가', c.get('지급단가', ''))
            _put('근무일수', c.get('근무일수', ''))
            _put('총지급액', c.get('총지급액', ''))
            _put('지급상태', ASSIGN_STATUS_CANDIDATE)
            _put('배정일시', now_str)
            _put('팀코드', c.get('팀코드', ''))
            _put('결제대상', c.get('결제대상', 'Y'))
            _put('현장참여', c.get('현장참여', 'Y'))
            
            batch_rows.append(row)
        
        # 한 번의 API 호출로 배치 저장 (실제 헤더 수만큼)
        if batch_rows:
            # 컬럼 레터 계산 (A~Z, AA~AZ...)
            def _col_letter(n):
                """0-based index → 컬럼 레터 (A, B, ..., Z, AA, AB, ...)"""
                s = ''
                n += 1  # 1-based
                while n > 0:
                    n, r = divmod(n - 1, 26)
                    s = chr(65 + r) + s
                return s
            
            end_col = _col_letter(total_cols - 1)
            cell_range = f'A{next_row}:{end_col}{next_row + len(batch_rows) - 1}'
            _invalidate_assign_ctx()
            wks.update(cell_range, batch_rows, value_input_option='RAW')
            print(f"[Batch] Saved {len(batch_rows)} candidates for {inquiry_id} (cols: A~{end_col}, {total_cols}cols)")
            return len(batch_rows), 0
        return 0, 0
    except Exception as e:
        print(f"save_candidates_batch error: {e}")
        import traceback; traceback.print_exc()
        return 0, len(candidates)


def get_candidates_by_inquiry(inquiry_id: str, include_assigned=True):
    """문의ID별 후보 인력 조회 (후보 + 배정중 상태)
    
    include_assigned: True면 배정중 상태도 포함
    """
    try:
        df = load_dispatch_sheet()
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        
        if '문의ID' in df.columns:
            df = df[df['문의ID'].astype(str).str.strip() == str(inquiry_id).strip()]
        else:
            return pd.DataFrame()
        
        # 후보 + 배정중만 필터 (정규화된 컬럼명 고려)
        status_col = None
        for sc in ['지급상태', '상태']:
            if sc in df.columns:
                status_col = sc
                break
        
        if status_col:
            valid_statuses = [ASSIGN_STATUS_CANDIDATE]
            if include_assigned:
                valid_statuses.append(ASSIGN_STATUS_ASSIGNED)
            df = df[df[status_col].astype(str).str.strip().isin(valid_statuses)]
        else:
            print(f"[get_candidates] Warning: no status column found. Columns: {list(df.columns)}")
            return pd.DataFrame()
        
        print(f"[get_candidates] Found {len(df)} candidates for {inquiry_id} (status_col={status_col})")
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"get_candidates_by_inquiry error: {e}")
        return pd.DataFrame()


def assign_candidate_to_role(assign_id: str, role: str, pay_rate=None, work_days=None):
    """후보를 특정 직군에 배정 (후보 → 배정중) — 캐싱 컨텍스트 사용
    """
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()
        target_row = _find_row(id_col, assign_id)
        if not target_row:
            return False
        
        updates = []
        if cm.get('직무'):
            updates.append(gspread.Cell(target_row, cm['직무'], role))
        if cm.get('지급상태'):
            updates.append(gspread.Cell(target_row, cm['지급상태'], ASSIGN_STATUS_ASSIGNED))
        if pay_rate is not None and cm.get('지급단가'):
            updates.append(gspread.Cell(target_row, cm['지급단가'], pay_rate))
        if work_days is not None and cm.get('근무일수'):
            updates.append(gspread.Cell(target_row, cm['근무일수'], work_days))
        if pay_rate and work_days and cm.get('총지급액'):
            updates.append(gspread.Cell(target_row, cm['총지급액'], int(pay_rate) * int(work_days)))
        
        if updates:
            wks.update_cells(updates, value_input_option='RAW')
            invalidate_dispatch_only()
            print(f"[Assign] {assign_id} → role={role}, status=배정중")
            return True
        return False
    except Exception as e:
        print(f"assign_candidate_to_role error: {e}")
        return False


def batch_confirm_assignments(assign_ids: list, long_term=False):
    """배정 일괄 확정 (배정중 → 확정) — 캐싱 컨텍스트 사용
    """
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()
        sc = cm.get('지급상태')
        if not sc:
            return 0, len(assign_ids)
        
        updates = []
        success = 0
        for aid in assign_ids:
            target_row = _find_row(id_col, aid)
            if target_row:
                new_status = '확정(일정미입력)' if long_term else ASSIGN_STATUS_CONFIRMED
                updates.append(gspread.Cell(target_row, sc, new_status))
                success += 1
        
        if updates:
            wks.update_cells(updates, value_input_option='RAW')
            _invalidate_assign_ctx()
            invalidate_dispatch_only()
            print(f"[Confirm] {success}/{len(assign_ids)} confirmed (long_term={long_term})")
        
        return success, len(assign_ids) - success
    except Exception as e:
        print(f"batch_confirm_assignments error: {e}")
        return 0, len(assign_ids)


def batch_update_schedule(schedule_records: list):
    """장기건 일정 일괄 입력/수정 — 캐싱 컨텍스트 사용
    
    schedule_records: list of dict with keys:
        배정ID, 근무일수, 지급단가, 총지급액, 근무시작일, 근무종료일
    Returns: (성공수, 실패수)
    """
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()
        
        updates = []
        success = 0
        
        for rec in schedule_records:
            target_row = _find_row(id_col, rec.get('배정ID', ''))
            if not target_row:
                continue
            
            if rec.get('근무일수') is not None and cm.get('근무일수'):
                updates.append(gspread.Cell(target_row, cm['근무일수'], rec['근무일수']))
            if rec.get('지급단가') is not None and cm.get('지급단가'):
                updates.append(gspread.Cell(target_row, cm['지급단가'], rec['지급단가']))
            if rec.get('총지급액') is not None and cm.get('총지급액'):
                updates.append(gspread.Cell(target_row, cm['총지급액'], rec['총지급액']))
            if cm.get('지급상태'):
                updates.append(gspread.Cell(target_row, cm['지급상태'], ASSIGN_STATUS_CONFIRMED))
            
            success += 1
        
        if updates:
            wks.update_cells(updates, value_input_option='RAW')
            _invalidate_assign_ctx()
            invalidate_dispatch_only()
            print(f"[Schedule] {success}/{len(schedule_records)} schedules updated")
        
        return success, len(schedule_records) - success
    except Exception as e:
        print(f"batch_update_schedule error: {e}")
        return 0, len(schedule_records)


def remove_candidate(assign_id: str):
    """후보 인력 삭제 (후보 상태인 경우만 — 실제 행 삭제 대신 '취소' 처리)"""
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()
        target_row = _find_row(id_col, assign_id)
        if not target_row:
            return False
        sc = cm.get('지급상태')
        if not sc:
            return False
        wks.update_cell(target_row, sc, ASSIGN_STATUS_CANCELLED)
        _invalidate_assign_ctx()
        invalidate_dispatch_only()
        print(f"[Remove] {assign_id} → 취소")
        return True
    except Exception as e:
        print(f"remove_candidate error: {e}")
        return False


def update_assignment(assign_id: str, **kwargs):
    """배정기록의 임의 필드를 수정 (인라인 편집용) — 캐싱 컨텍스트 사용
    
    사용 예: update_assignment('A001', 직무='안내', 지급단가=150000, 근무일수=3)
    
    지원 키: 직무, 지급단가, 근무일수, 구분, 인력명, 근무일자
    총지급액은 단가×일수로 자동 재계산됨
    """
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()
        target_row = _find_row(id_col, assign_id)
        if not target_row:
            return False

        updates = []
        new_pay = None
        new_days = None
        for key, val in kwargs.items():
            ci = cm.get(key)
            if ci:
                updates.append(gspread.Cell(target_row, ci, val))
            else:
                # col_map에 없으면 헤더에서 직접 검색
                if key in headers:
                    updates.append(gspread.Cell(target_row, headers.index(key) + 1, val))
            if key in ('지급단가', '단가'):
                new_pay = int(val)
            if key in ('근무일수', '일수'):
                new_days = int(val)

        # 총지급액 재계산
        if (new_pay is not None or new_days is not None) and cm.get('총지급액'):
            if new_pay is None and cm.get('지급단가'):
                cur = wks.cell(target_row, cm['지급단가']).value
                new_pay = int(cur or 0)
            if new_days is None and cm.get('근무일수'):
                cur = wks.cell(target_row, cm['근무일수']).value
                new_days = int(cur or 0)
            if new_pay and new_days:
                updates.append(gspread.Cell(target_row, cm['총지급액'], new_pay * new_days))

        if updates:
            wks.update_cells(updates, value_input_option='RAW')
            invalidate_dispatch_only()
            print(f"[Update] {assign_id} → {kwargs}")
            return True
        return False
    except Exception as e:
        print(f"update_assignment error: {e}")
        return False


def batch_assign_to_role(assignments: list):
    """후보 일괄 직군 배정 (N건 → 1 API call) — 캐싱 컨텍스트 사용
    
    assignments: list of dict, each:
        assign_id, role, pay_rate, work_days, work_dates(optional: 'YYYY-MM-DD,...')
    Returns: (성공수, 실패수)
    """
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()

        role_ci = cm.get('직무')
        status_ci = cm.get('지급상태')
        pay_ci = cm.get('지급단가')
        days_ci = cm.get('근무일수')
        total_ci = cm.get('총지급액')
        dates_ci = cm.get('근무일자')  # 16번째 컬럼

        updates = []
        success = 0

        for a in assignments:
            target_row = _find_row(id_col, a.get('assign_id', ''))
            if not target_row:
                continue

            if role_ci:
                updates.append(gspread.Cell(target_row, role_ci, a.get('role', '')))
            if status_ci:
                updates.append(gspread.Cell(target_row, status_ci, ASSIGN_STATUS_ASSIGNED))
            pay = a.get('pay_rate')
            day = a.get('work_days')
            if pay is not None and pay_ci:
                updates.append(gspread.Cell(target_row, pay_ci, pay))
            if day is not None and days_ci:
                updates.append(gspread.Cell(target_row, days_ci, day))
            if pay and day and total_ci:
                updates.append(gspread.Cell(target_row, total_ci, int(pay) * int(day)))
            # 근무일자 저장 (쉼표구분 ISO)
            work_dates_str = a.get('work_dates', '')
            if work_dates_str and dates_ci:
                updates.append(gspread.Cell(target_row, dates_ci, work_dates_str))
            success += 1

        if updates:
            wks.update_cells(updates, value_input_option='RAW')
            _invalidate_assign_ctx()
            invalidate_dispatch_only()
            print(f"[BatchAssign] {success}/{len(assignments)} assigned in 1 API call")

        return success, len(assignments) - success
    except Exception as e:
        print(f"batch_assign_to_role error: {e}")
        return 0, len(assignments)


def unassign_from_role(assign_id: str):
    """배정 취소: 배정중 → 후보 (직무/일자 초기화) — 캐싱 컨텍스트 사용"""
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()
        target_row = _find_row(id_col, assign_id)
        if not target_row:
            return False

        updates = []
        if cm.get('지급상태'):
            updates.append(gspread.Cell(target_row, cm['지급상태'], ASSIGN_STATUS_CANDIDATE))
        if cm.get('직무'):
            updates.append(gspread.Cell(target_row, cm['직무'], ''))
        if cm.get('근무일수'):
            updates.append(gspread.Cell(target_row, cm['근무일수'], 0))
        if cm.get('지급단가'):
            updates.append(gspread.Cell(target_row, cm['지급단가'], 0))
        if cm.get('총지급액'):
            updates.append(gspread.Cell(target_row, cm['총지급액'], 0))
        if cm.get('근무일자'):
            updates.append(gspread.Cell(target_row, cm['근무일자'], ''))

        if updates:
            wks.update_cells(updates, value_input_option='RAW')
            _invalidate_assign_ctx()
            invalidate_dispatch_only()
            print(f"[Unassign] {assign_id} → 후보로 되돌림")
            return True
        return False
    except Exception as e:
        print(f"unassign_from_role error: {e}")
        return False


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
        invalidate_dispatch_only()
        
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
            if not merged_assignment.get('주민등록번호'):
                merged_assignment['주민등록번호'] = staff_info.get('주민등록번호', '')
            if not merged_assignment.get('은행명'):
                merged_assignment['은행명'] = staff_info.get('은행명', '')
            if not merged_assignment.get('계좌번호'):
                merged_assignment['계좌번호'] = staff_info.get('계좌번호', '')
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

        # 배정기록 시트 16컬럼 구조 (근무일자 컬럼 추가)
        # Col 1: 배정ID
        # Col 2: 문의ID
        # Col 3: 행사명
        # Col 4: 인력명
        # Col 5: 구분 (본사/외부)
        # Col 6: 직무
        # Col 7: 연락처
        # Col 8: 주민등록번호
        # Col 9: 은행명
        # Col 10: 계좌번호
        # Col 11: 지급단가
        # Col 12: 근무일수
        # Col 13: 총지급액
        # Col 14: 지급상태
        # Col 15: 배정일시
        # Col 16: 근무일자 (쉼표구분 ISO: '2026-02-18,2026-02-20')
        
        row_values = [
            assign_id,  # Col 1: 배정ID
            merged_assignment.get('문의ID', ''),  # Col 2: 문의ID
            merged_assignment.get('행사명', ''),  # Col 3: 행사명
            merged_assignment.get('인력명', ''),  # Col 4: 인력명
            merged_assignment.get('구분', '외부'),  # Col 5: 구분 (본사/외부)
            merged_assignment.get('직무', ''),  # Col 6: 직무
            merged_assignment.get('연락처', ''),  # Col 7: 연락처
            merged_assignment.get('주민등록번호', ''),  # Col 8: 주민등록번호
            merged_assignment.get('은행명', ''),  # Col 9: 은행명
            merged_assignment.get('계좌번호', ''),  # Col 10: 계좌번호
            merged_assignment.get('지급단가', ''),  # Col 11: 지급단가
            merged_assignment.get('근무일수', ''),  # Col 12: 근무일수
            merged_assignment.get('총지급액', ''),  # Col 13: 총지급액
            merged_assignment.get('지급상태', '배정중'),  # Col 14: 지급상태
            merged_assignment.get('배정일시', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),  # Col 15: 배정일시
            merged_assignment.get('근무일자', ''),  # Col 16: 근무일자
        ]

        # A{next_row} 위치에 한 줄로 업데이트
        _invalidate_assign_ctx()
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
    """배정기록의 상태를 변경 — 캐싱 컨텍스트 사용"""
    try:
        wks, headers, id_col, cm = _get_assign_sheet_ctx()
        target_row = _find_row(id_col, assign_id)
        if not target_row:
            print(f"❌ 배정ID '{assign_id}' not found")
            return False
        sc = cm.get('지급상태')
        if not sc:
            print(f"❌ 지급상태 컬럼 없음")
            return False
        wks.update_cell(target_row, sc, new_status)
        _invalidate_assign_ctx()
        invalidate_dispatch_only()
        print(f"✅ {assign_id} → {new_status}")
        return True
    except Exception as e:
        print(f"❌ update_assignment_status 오류: {e}")
        return False


@st.cache_data(ttl=120)  # 배정기록 120초 캐시 (API 할당량 절약)
def get_assignments_by_inquiry(inquiry_id):
    """특정 문의ID의 배정기록 조회 — load_dispatch_sheet() 캐시 활용으로 API 호출 최소화
    
    Note: '취소'와 '후보' 상태는 제외됨. 후보 조회는 get_candidates_by_inquiry() 사용.
    """
    try:
        # 이미 캐시된 배정기록 시트 데이터를 재사용 (중복 API 호출 방지)
        df = load_dispatch_sheet()
        if df is None or df.empty:
            return pd.DataFrame()
        
        df = df.copy()
        
        # 문의ID로 필터링
        if '문의ID' in df.columns:
            df = df[df['문의ID'].astype(str).str.strip() == str(inquiry_id).strip()]
        else:
            return pd.DataFrame()
        
        # 상태 필터 (취소/후보 제외 — 후보는 get_candidates_by_inquiry에서 조회)
        exclude_statuses = ['취소', ASSIGN_STATUS_CANDIDATE]
        status_col = None
        for sc in ['지급상태', '상태']:
            if sc in df.columns:
                status_col = sc
                break
        if status_col:
            df = df[~df[status_col].astype(str).str.strip().isin(exclude_statuses)]
        
        return df.reset_index(drop=True)
    
    except Exception as e:
        print(f"get_assignments_by_inquiry error: {e}")
        return pd.DataFrame()


def get_confirmed_assignments(inquiry_id):
    """확정 인력만 조회 (출석부/평가/지급용) — '확정' 또는 '확정(일정미입력)' 상태만"""
    try:
        df = load_dispatch_sheet()
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        if '문의ID' in df.columns:
            df = df[df['문의ID'].astype(str).str.strip() == str(inquiry_id).strip()]
        else:
            return pd.DataFrame()
        status_col = None
        for sc in ['지급상태', '상태']:
            if sc in df.columns:
                status_col = sc
                break
        if status_col:
            df = df[df[status_col].astype(str).str.strip().str.startswith(ASSIGN_STATUS_CONFIRMED)]
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"get_confirmed_assignments error: {e}")
        return pd.DataFrame()


def batch_save_attendance(records: list):
    """출석 기록 일괄 저장 (1 API call) — 동일 날짜 기존 기록은 덮어쓰기
    
    records: list of dict {배정ID, 문의ID, 인력명, 출석날짜, 출근시간, 퇴근시간, 
             근무시간, 일급여, 출석상태, 사유, 비고, 기록일시}
    Returns: (성공수, 실패수)
    """
    client = get_connection()
    if not client:
        return 0, len(records)
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("출석부")
        
        # 기존 데이터 로드 — 중복 체크용
        all_vals = wks.get_all_values()
        headers = [str(h).strip() for h in all_vals[0]] if all_vals else []
        
        # 배정ID + 출석날짜로 기존 행 찾기
        bid_ci = headers.index('배정ID') + 1 if '배정ID' in headers else 2
        date_ci = headers.index('출석날짜') + 1 if '출석날짜' in headers else 5
        
        existing_map = {}  # (배정ID, 출석날짜) → row_number
        for i, row in enumerate(all_vals[1:], 2):
            if len(row) >= max(bid_ci, date_ci):
                key = (str(row[bid_ci - 1]).strip(), str(row[date_ci - 1]).strip())
                existing_map[key] = i
        
        next_row = len(all_vals) + 1
        new_rows = []
        update_cells = []
        success = 0
        
        for rec in records:
            bid = str(rec.get('배정ID', '')).strip()
            att_date = str(rec.get('출석날짜', '')).strip()
            key = (bid, att_date)
            
            record_id = f"R-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
            row_values = [
                record_id,
                rec.get('배정ID', ''),
                rec.get('문의ID', ''),
                rec.get('인력명', ''),
                rec.get('출석날짜', ''),
                rec.get('출근시간', ''),
                rec.get('퇴근시간', ''),
                rec.get('근무시간', 0),
                rec.get('일급여', 0),
                rec.get('출석상태', ''),
                rec.get('사유', ''),
                rec.get('비고', ''),
                rec.get('기록일시', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            ]
            
            if key in existing_map:
                # 기존 행 업데이트
                target = existing_map[key]
                for ci, val in enumerate(row_values):
                    update_cells.append(gspread.Cell(target, ci + 1, val))
            else:
                new_rows.append(row_values)
            success += 1
        
        # 기존 행 업데이트
        if update_cells:
            wks.update_cells(update_cells, value_input_option='RAW')
        
        # 신규 행 추가
        if new_rows:
            if next_row + len(new_rows) > wks.row_count:
                wks.add_rows(max(100, len(new_rows)))
            cell_range = f'A{next_row}:M{next_row + len(new_rows) - 1}'
            wks.update(cell_range, new_rows, value_input_option='RAW')
        
        print(f"[Attendance] Saved {success} records ({len(update_cells)//13} updated, {len(new_rows)} new)")
        return success, len(records) - success
    except Exception as e:
        print(f"batch_save_attendance error: {e}")
        import traceback; traceback.print_exc()
        return 0, len(records)


@st.cache_data(ttl=120)  # 배정기록 120초 캐시 (TTL 증가)
def load_dispatch_sheet():
    """배정기록 시트를 독립적으로 로드 (TTL=10초로 더 자주 갱신)"""
    client = get_connection()
    if not client:
        return pd.DataFrame()  # None 대신 빈 DataFrame 반환
    
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("배정기록")
        
        # ★ 읽기 전 헤더 마이그레이션: 팀코드/결제대상/현장참여 헤더 보장 + 데이터 위치 보정
        try:
            _get_assign_sheet_ctx()  # 헤더 추가 + 기존 데이터 이동 (자체 캐시 60초)
        except Exception as _mig_err:
            print(f"[Dispatch-Migration] 헤더/데이터 마이그레이션 건너뜀: {_mig_err}")
        
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
                    # 구체적(longer) 매칭을 먼저 체크하여 짧은 패턴에 잘못 매칭되지 않도록
                    if any(x in k for x in ['배정id', '배정아이디', '배정ID'.lower()]):
                        return '배정ID'
                    if any(x in k for x in ['문의id', '문의아이디', '문의ID'.lower()]):
                        return '문의ID'
                    # 인력명은 원본 유지 (이름/성명보다 구체적)
                    if k == '인력명':
                        return '인력명'
                    if any(x in k for x in ['이름', '성명', 'name']):
                        return '이름'
                    # 직무는 원본 유지 (역할과 구분)
                    if k == '직무':
                        return '직무'
                    if k == '역할' or k == 'role':
                        return '역할'
                    # 지급단가는 원본 유지
                    if k == '지급단가':
                        return '지급단가'
                    if any(x in k for x in ['단가', '단가(원)', 'rate']):
                        return '단가'
                    # 근무일수는 원본 유지
                    if k == '근무일수':
                        return '근무일수'
                    if any(x in k for x in ['일수']):
                        return '일수'
                    if any(x in k for x in ['총지급액', '총지급', '지급액']):
                        return '총지급액'
                    if any(x in k for x in ['배정일시', '배정일', 'date']):
                        return '배정일시'
                    # 지급상태는 원본 유지
                    if k == '지급상태':
                        return '지급상태'
                    if any(x in k for x in ['상태', 'status']):
                        return '상태'
                    if any(x in k for x in ['연락처', '전화', 'phone']):
                        return '연락처'
                    if any(x in k for x in ['소속', 'company', 'affil']):
                        return '소속'
                    # 팀 관련 컬럼 (원본 유지)
                    if k == '팀코드':
                        return '팀코드'
                    if k == '결제대상':
                        return '결제대상'
                    if k == '현장참여':
                        return '현장참여'
                    # 기타 유용 컬럼
                    if k == '구분':
                        return '구분'
                    if k == '행사명':
                        return '행사명'
                    if k == '근무일자':
                        return '근무일자'
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

        # get_all_records 성공 시 df 반환 (이전에 누락되어 있던 return)
        return df if df is not None and not df.empty else pd.DataFrame()

    except Exception as e:
        print(f"[Dispatch] Load error: {str(e)[:60]}")
        return pd.DataFrame()


def ensure_attendance_sheet():
    """출석부 시트 존재 확인 및 필요시 생성 — _get_worksheet() 위임 (API 0회)"""
    return _get_worksheet("출석부") is not None


def ensure_evaluation_sheet():
    """평가표 시트 존재 확인 및 필요시 생성 — _get_worksheet() 위임 (API 0회)"""
    return _get_worksheet("평가표") is not None


def ensure_payment_sheet():
    """지급내역 시트 존재 확인 및 필요시 생성 — _get_worksheet() 위임 (API 0회)"""
    return _get_worksheet("지급내역") is not None


def ensure_payment_headers():
    """지급내역 시트에 은행명/계좌번호/주민등록번호/문의ID 컬럼이 없으면 추가 (마이그레이션).
    기존 18컬럼 → 22컬럼 확장. 앱 시작 시 1회만 실행됩니다.
    """
    if st.session_state.get('_payment_headers_checked'):
        return  # 이미 확인 완료
    try:
        wks = _get_worksheet("지급내역")
        if not wks:
            st.session_state['_payment_headers_checked'] = True
            return
        headers = [str(h).strip() for h in wks.row_values(1)]
        # 필요한 새 컬럼 확인 (비고 앞에 삽입하기 위해 순서 중요)
        new_cols_after_지급담당자 = ['은행명', '계좌번호', '주민등록번호']
        new_col_after_배정ID = '문의ID'
        changed = False

        # 문의ID 컬럼 (배정ID 뒤, 인력명 앞)
        if new_col_after_배정ID not in headers:
            bid_idx = headers.index('배정ID') + 1 if '배정ID' in headers else 2
            # 인력명 컬럼 앞에 삽입
            target_insert = bid_idx  # 0-based로는 bid_idx
            wks.insert_cols([1], col=target_insert + 1)
            wks.update_cell(1, target_insert + 1, '문의ID')
            headers.insert(target_insert, '문의ID')
            changed = True
            print(f"[Payment] '문의ID' 컬럼 추가 (Col {target_insert + 1})")

        # 은행명/계좌번호/주민등록번호 (지급담당자 뒤, 비고 앞)
        for col_name in new_cols_after_지급담당자:
            if col_name not in headers:
                # 비고 컬럼 앞에 삽입
                if '비고' in headers:
                    bigo_idx = headers.index('비고')  # 0-based
                    wks.insert_cols([1], col=bigo_idx + 1)
                    wks.update_cell(1, bigo_idx + 1, col_name)
                    headers.insert(bigo_idx, col_name)
                else:
                    # 비고 없으면 끝에 추가
                    next_col = len(headers) + 1
                    wks.update_cell(1, next_col, col_name)
                    headers.append(col_name)
                changed = True
                print(f"[Payment] '{col_name}' 컬럼 추가")

        if changed:
            _invalidate_worksheet_cache("지급내역")
            invalidate_payment_cache()

        st.session_state['_payment_headers_checked'] = True
        print(f"[OK] 지급내역 시트: 헤더 확인됨 ({len(headers)}컬럼)")
    except Exception as e:
        print(f"ensure_payment_headers error: {e}")
        st.session_state['_payment_headers_checked'] = True


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


# ---------------------------------------------------------
# 복수 견적안 관리 (시트 영구 저장)
# ---------------------------------------------------------

def save_estimate_version(inquiry_id: str, version_name: str, items_df, metadata: dict = None):
    """견적안을 시트에 저장 (같은 문의+이름이면 덮어쓰기)
    metadata: 프로젝트 메타데이터 (수신인, 행사명, 장소, 날짜 등)
    """
    import json
    client = get_connection()
    if not client:
        return False
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("견적안")
        all_vals = wks.get_all_values()
        
        # 헤더에 메타JSON 컬럼이 없으면 추가
        if all_vals and len(all_vals[0]) < 9:
            all_vals[0] = list(all_vals[0]) + ['메타JSON']
            # 기존 데이터 행도 9번째 컬럼 빈값 추가
            for i in range(1, len(all_vals)):
                if len(all_vals[i]) < 9:
                    all_vals[i] = list(all_vals[i]) + ['']
        
        # 기존 같은 문의+같은 이름 행 삭제
        rows_to_keep = [all_vals[0]] if all_vals else []
        for row in all_vals[1:]:
            if len(row) >= 3:
                if str(row[1]).strip() == str(inquiry_id).strip() and str(row[2]).strip() == version_name.strip():
                    continue  # 기존 항목 제거 (덮어쓰기)
            rows_to_keep.append(row)
        
        # 품목 DataFrame → JSON (매출합계 등 숫자를 int로)
        import math
        def _to_int(v):
            """NaN/None/float 안전 정수 변환"""
            if v is None:
                return 0
            try:
                fv = float(v)
                if math.isnan(fv):
                    return 0
                return int(fv)
            except (ValueError, TypeError):
                return 0

        items_list = []
        for _, r in items_df.iterrows():
            items_list.append({
                '품목': str(r.get('품목', '') or ''),
                '규격': str(r.get('규격', '') or ''),
                '수량': _to_int(r.get('수량', 0)),
                '일수': _to_int(r.get('일수', 0)),
                '매출단가': _to_int(r.get('매출단가', 0)),
                '매입단가': _to_int(r.get('매입단가', 0)),
                '할인액': _to_int(r.get('할인액', r.get('할인율', 0))),
                '매출합계': _to_int(r.get('매출합계', 0)),
                '매입합계': _to_int(r.get('매입합계', 0)),
                '비고': str(r.get('비고', '') or ''),
            })
        json_str = json.dumps(items_list, ensure_ascii=False)
        supply = sum(i['매출합계'] for i in items_list)
        cost = sum(i['매입합계'] for i in items_list)
        
        # 메타데이터 JSON
        meta_json = json.dumps(metadata, ensure_ascii=False, default=str) if metadata else ''
        
        ver_id = f"V-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:4]}"
        new_row = [ver_id, str(inquiry_id), version_name, json_str, supply, cost, 
                   datetime.now().strftime("%Y-%m-%d %H:%M"), len(items_list), meta_json]
        
        rows_to_keep.append(new_row)
        wks.clear()
        wks.update(values=rows_to_keep, range_name='A1', value_input_option='RAW')
        
        print(f"✅ 견적안 저장: {inquiry_id}/{version_name} ({len(items_list)}개 품목, meta={'Y' if metadata else 'N'})")
        return True
    except Exception as e:
        print(f"❌ save_estimate_version 오류: {e}")
        return False


def load_estimate_versions(inquiry_id: str):
    """특정 문의ID의 모든 견적안 로드 → dict {이름: {'items': DataFrame, 'meta': dict}}"""
    import json
    client = get_connection()
    if not client:
        return {}
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("견적안")
        records = wks.get_all_records()
        if not records:
            return {}
        
        versions = {}
        for r in records:
            if str(r.get('문의ID', '')).strip() == str(inquiry_id).strip():
                name = str(r.get('견적안명', '')).strip()
                try:
                    items = json.loads(str(r.get('품목JSON', '[]')))
                    df = pd.DataFrame(items)
                    # 숫자 컬럼 타입 강제 변환
                    for nc in ['수량','일수','매출단가','매입단가','할인액','매출합계','매입합계']:
                        if nc in df.columns:
                            df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0).astype(int)
                    # 메타데이터 파싱
                    meta = {}
                    meta_raw = str(r.get('메타JSON', '')).strip()
                    if meta_raw and meta_raw not in ('nan', 'None', ''):
                        try:
                            meta = json.loads(meta_raw)
                        except:
                            pass
                    versions[name] = {'items': df, 'meta': meta}
                except:
                    pass
        return versions
    except Exception as e:
        print(f"load_estimate_versions error: {e}")
        return {}


def delete_estimate_version(inquiry_id: str, version_name: str):
    """특정 견적안 삭제"""
    client = get_connection()
    if not client:
        return False
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("견적안")
        all_vals = wks.get_all_values()
        rows_to_keep = [all_vals[0]] if all_vals else []
        for row in all_vals[1:]:
            if len(row) >= 3:
                if str(row[1]).strip() == str(inquiry_id).strip() and str(row[2]).strip() == version_name.strip():
                    continue
            rows_to_keep.append(row)
        wks.clear()
        wks.update(values=rows_to_keep, range_name='A1', value_input_option='RAW')
        return True
    except Exception as e:
        print(f"delete_estimate_version error: {e}")
        return False


# ---------------------------------------------------------
# 견적품목 관리
# ---------------------------------------------------------

# 견적품목 표준 헤더 (save/load 동기화)
_ESTIMATE_ITEMS_HEADERS = ['품목ID', '문의ID', '직군명', '수량', '일수', '매출단가', '매입단가', '규격', '비고', '팀장여부', '할인액', '구분']


def _safe_num(val, default=0):
    """NaN/문자열 안전 정수 변환"""
    try:
        if val is None or (isinstance(val, float) and str(val) == 'nan'):
            return default
        if isinstance(val, str):
            clean = val.replace(',', '').replace('원', '').strip()
            if not clean:
                return default
            return int(float(clean))
        return int(float(val))
    except (ValueError, TypeError):
        return default


def save_estimate_items(inquiry_id: str, items_df, additional_costs_df=None):
    """견적품목 시트에 직군별 품목 + 부대비용 저장 (기존 항목 삭제 후 재작성)"""
    client = get_connection()
    if not client:
        return False
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("견적품목")
        
        # 기존 해당 문의의 품목 삭제 (전체 재작성)
        all_vals = wks.get_all_values()
        # 헤더를 표준 형식으로 고정 (기존 헤더 불일치 문제 방지)
        rows_to_keep = [_ESTIMATE_ITEMS_HEADERS]
        old_headers = all_vals[0] if all_vals else []
        for row in all_vals[1:]:
            if len(row) >= 2 and str(row[1]).strip() != str(inquiry_id).strip():
                # 기존 데이터 행을 표준 헤더 길이에 맞춤
                padded = list(row) + [''] * max(0, len(_ESTIMATE_ITEMS_HEADERS) - len(row))
                rows_to_keep.append(padded[:len(_ESTIMATE_ITEMS_HEADERS)])
        
        # 시트 클리어 후 재작성
        wks.clear()
        if rows_to_keep:
            wks.update('A1', rows_to_keep, value_input_option='RAW')
        
        # 새 품목 추가 — 배치 1회 API 호출 (방안 E)
        next_row = len(rows_to_keep) + 1
        batch_rows = []
        # ── 인력 품목 ──
        for idx, item in items_df.iterrows():
            item_id = f"I-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:4]}"
            role_name = str(item.get('품목', '')).replace('[팀장]', '').strip()
            # NaN 안전 변환
            row = [
                item_id,
                str(inquiry_id),
                role_name,
                _safe_num(item.get('수량', 0)),
                _safe_num(item.get('일수', 0)),
                _safe_num(item.get('매출단가', 0)),
                _safe_num(item.get('매입단가', 0)),
                str(item.get('규격', '') if pd.notna(item.get('규격', '')) else ''),
                str(item.get('비고', '') if pd.notna(item.get('비고', '')) else ''),
                '팀장' if '[팀장]' in str(item.get('품목', '')) else '',
                _safe_num(item.get('할인액', 0)),
                '인력',
            ]
            batch_rows.append(row)
        
        # ── 부대비용 품목 ──
        if additional_costs_df is not None and not additional_costs_df.empty:
            for _, ac in additional_costs_df.iterrows():
                ac_id = f"A-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:4]}"
                row = [
                    ac_id,
                    str(inquiry_id),
                    str(ac.get('항목', '') or ''),           # 직군명 → 항목명
                    _safe_num(ac.get('수량', 1)),
                    _safe_num(ac.get('일수', 1)),
                    _safe_num(ac.get('단가', 0)),             # 매출단가 → 단가
                    0,                                        # 매입단가 (부대비용은 매입 없음)
                    '',                                       # 규격
                    str(ac.get('비고', '') or ''),
                    '',                                       # 팀장여부
                    0,                                        # 할인액
                    '부대비용',                                # 구분
                ]
                batch_rows.append(row)
        
        if batch_rows:
            col_cnt = len(_ESTIMATE_ITEMS_HEADERS)  # 12 (A~L)
            end_col = chr(ord('A') + col_cnt - 1)   # 'L'
            end_row = next_row + len(batch_rows) - 1
            wks.update(f'A{next_row}:{end_col}{end_row}', batch_rows, value_input_option='RAW')
        
        _ac_cnt = len(additional_costs_df) if additional_costs_df is not None and not additional_costs_df.empty else 0
        print(f"✅ 견적품목 저장: {inquiry_id} - 인력 {len(items_df)}개 + 부대비용 {_ac_cnt}개 (배치 1회)")
        return True
    except Exception as e:
        print(f"❌ save_estimate_items 오류: {e}")
        return False


@st.cache_data(ttl=120)
def load_estimate_items(inquiry_id: str, item_type: str = '인력'):
    """특정 문의ID의 견적품목 조회
    
    Args:
        inquiry_id: 문의ID
        item_type: '인력' (인력 품목만), '부대비용' (부대비용만), 'all' (전체)
    """
    client = get_connection()
    if not client:
        return pd.DataFrame()
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("견적품목")
        records = wks.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        # 구버전 헤더 호환: 인원수→수량, 근무시간→규격 등
        _col_map = {'인원수': '수량', '근무시간': '규격', '할증옵션': '비고_old'}
        for old_name, new_name in _col_map.items():
            if old_name in df.columns and new_name not in df.columns:
                df = df.rename(columns={old_name: new_name})
        # 구분 컬럼 없으면 기본값 '인력'
        if '구분' not in df.columns:
            df['구분'] = '인력'
        else:
            df['구분'] = df['구분'].fillna('').astype(str).str.strip()
            df.loc[df['구분'] == '', '구분'] = '인력'
        # 숫자 컬럼 타입 보정
        for nc in ['수량', '일수', '매출단가', '매입단가', '할인액']:
            if nc in df.columns:
                df[nc] = pd.to_numeric(df[nc], errors='coerce').fillna(0).astype(int)
        if '문의ID' in df.columns:
            df = df[df['문의ID'].astype(str).str.strip() == str(inquiry_id).strip()]
        # 구분 필터링
        if item_type != 'all':
            df = df[df['구분'] == item_type]
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"load_estimate_items error: {e}")
        return pd.DataFrame()


def load_additional_costs(inquiry_id: str):
    """견적품목 시트에서 부대비용 항목만 로드 → additional_costs DataFrame 형식으로 반환"""
    raw = load_estimate_items(inquiry_id, item_type='부대비용')
    if raw.empty:
        return pd.DataFrame(columns=['항목', '수량', '일수', '단가', '금액', '비고'])
    rows = []
    for _, r in raw.iterrows():
        qty = int(r.get('수량', 1))
        days = int(r.get('일수', 1))
        unit_price = int(r.get('매출단가', 0))
        rows.append({
            '항목': str(r.get('직군명', '')),
            '수량': qty,
            '일수': days,
            '단가': unit_price,
            '금액': qty * days * unit_price,
            '비고': str(r.get('비고', '')),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['항목', '수량', '일수', '단가', '금액', '비고'])


# ---------------------------------------------------------
# 평가표 저장
# ---------------------------------------------------------


def save_evaluation(eval_dict: dict):
    """평가표 시트에 평가 기록 저장"""
    ensure_evaluation_sheet()  # 시트 존재 보장
    client = get_connection()
    if not client:
        return False
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("평가표")
        
        eval_id = f"E-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
        
        # 기존 평가 중복 체크 (배정ID 기준)
        all_vals = wks.get_all_values()
        headers = all_vals[0] if all_vals else []
        bid_col = headers.index('배정ID') + 1 if '배정ID' in headers else 2
        
        target_bid = str(eval_dict.get('배정ID', '')).strip()
        target_row = None
        for i, row in enumerate(all_vals[1:], 2):
            if len(row) >= bid_col and str(row[bid_col - 1]).strip() == target_bid:
                target_row = i
                break
        
        if target_row is None:
            target_row = len(all_vals) + 1
            if target_row > wks.row_count:
                wks.add_rows(100)
        
        # 평가표 17컬럼 구조 (STAFF DB 일치: 근태/수행/외모/팀워크)
        eval_id_to_use = eval_id if target_row == len(all_vals) + 1 else (
            all_vals[target_row - 1][0] if len(all_vals) >= target_row else eval_id)
        row_values = [
            eval_id_to_use,
            eval_dict.get('배정ID', ''),
            eval_dict.get('인력명', ''),
            eval_dict.get('현장명', ''),
            eval_dict.get('근태', 3),
            eval_dict.get('수행', eval_dict.get('수행력', 3)),      # 수행 (구버전 호환: 수행력)
            eval_dict.get('외모', eval_dict.get('태도', 3)),        # 외모 (구버전 호환: 태도)
            eval_dict.get('팀워크', eval_dict.get('의사소통', 3)),  # 팀워크 (구버전 호환: 의사소통)
            '',                                                      # 현장적응 (미사용, 호환용 빈값)
            eval_dict.get('총점', 0),
            eval_dict.get('평가등급', 'C'),
            eval_dict.get('평가자', ''),
            eval_dict.get('평가일시', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            eval_dict.get('강점', eval_dict.get('총평', '')),  # 강점 (구버전 호환: 총평)
            eval_dict.get('개선점', ''),
            eval_dict.get('재추천', 'No'),
            eval_dict.get('비고', ''),
        ]
        
        wks.update(f'A{target_row}', [row_values], value_input_option='RAW')
        print(f"✅ 평가 저장: {eval_dict.get('인력명', '')} at row {target_row}")
        return True
    except Exception as e:
        print(f"❌ save_evaluation 오류: {e}")
        return False


# ---------------------------------------------------------
# 지급내역 저장
# ---------------------------------------------------------

def save_payment_record(payment_dict: dict):
    """지급내역 시트에 급여 기록 저장"""
    ensure_payment_sheet()  # 시트 존재 보장
    client = get_connection()
    if not client:
        return False
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("지급내역")
        
        pay_id = f"P-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
        
        # 기존 지급 중복 체크 (배정ID 기준)
        all_vals = wks.get_all_values()
        headers = all_vals[0] if all_vals else []
        bid_col = headers.index('배정ID') + 1 if '배정ID' in headers else 2
        
        target_bid = str(payment_dict.get('배정ID', '')).strip()
        target_row = None
        for i, row in enumerate(all_vals[1:], 2):
            if len(row) >= bid_col and str(row[bid_col - 1]).strip() == target_bid:
                target_row = i
                break
        
        if target_row is None:
            target_row = len(all_vals) + 1
            if target_row > wks.row_count:
                wks.add_rows(100)
        
        # 지급내역 22컬럼 구조 (은행명/계좌번호/주민등록번호/문의ID 포함)
        row_values = [
            pay_id if target_row == len(all_vals) + 1 else all_vals[target_row - 1][0] if len(all_vals) >= target_row else pay_id,
            payment_dict.get('배정ID', ''),
            payment_dict.get('문의ID', ''),
            payment_dict.get('인력명', ''),
            payment_dict.get('현장명', ''),
            payment_dict.get('파견기간', ''),
            payment_dict.get('파견일수', 0),
            payment_dict.get('기본급', 0),
            payment_dict.get('야근비', 0),
            payment_dict.get('식사비', 0),
            payment_dict.get('교통비', 0),
            payment_dict.get('보너스', 0),
            payment_dict.get('소계', 0),
            payment_dict.get('세금공제', 0),
            payment_dict.get('최종지급액', 0),
            payment_dict.get('지급상태', '대기'),
            payment_dict.get('지급일', ''),
            payment_dict.get('지급담당자', ''),
            payment_dict.get('은행명', ''),
            payment_dict.get('계좌번호', ''),
            payment_dict.get('주민등록번호', ''),
            payment_dict.get('비고', ''),
        ]
        
        wks.update(f'A{target_row}', [row_values], value_input_option='RAW')
        print(f"✅ 지급내역 저장: {payment_dict.get('인력명', '')} at row {target_row}")
        invalidate_payment_cache()
        return True
    except Exception as e:
        print(f"❌ save_payment_record 오류: {e}")
        return False


@st.cache_data(ttl=120)  # 지급내역 시트 120초 캐시 (API 할당량 절약)
def _load_payment_sheet_cached():
    """지급내역 시트 전체를 캐시하여 반복 API 호출 방지"""
    try:
        ensure_payment_sheet()
        client = get_connection()
        if not client:
            return pd.DataFrame()
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("지급내역")
        try:
            records = wks.get_all_records()
        except Exception:
            all_vals = wks.get_all_values()
            if len(all_vals) <= 1:
                return pd.DataFrame()
            records = [dict(zip(all_vals[0], row)) for row in all_vals[1:]]
        if not records:
            return pd.DataFrame()
        pay_df = pd.DataFrame(records)
        if '지급ID' in pay_df.columns:
            pay_df = pay_df[pay_df['지급ID'].astype(str).str.strip() != '']
        print(f"[Payment] Loaded {len(pay_df)} payment records (cached)")
        return pay_df.reset_index(drop=True)
    except Exception as e:
        print(f"_load_payment_sheet_cached error: {e}")
        return pd.DataFrame()


def invalidate_payment_cache():
    """지급내역 캐시 초기화 (저장/수정 후 호출)"""
    try:
        _load_payment_sheet_cached.clear()
    except Exception:
        pass
    print("[SESSION] Payment cache invalidated")


def get_payment_records_by_inquiry(inquiry_id: str) -> pd.DataFrame:
    """특정 문의ID에 해당하는 지급내역 조회 (캐시된 시트 사용).
    지급내역에 문의ID 컬럼이 있으면 직접 필터, 없으면 배정ID → 배정기록.문의ID 매칭으로 우회."""
    try:
        pay_df = _load_payment_sheet_cached()
        if pay_df.empty:
            return pd.DataFrame()

        # 문의ID 컬럼이 있으면 직접 필터 (API 절약)
        if '문의ID' in pay_df.columns:
            filtered = pay_df[pay_df['문의ID'].astype(str).str.strip() == str(inquiry_id).strip()]
            if not filtered.empty:
                return filtered.reset_index(drop=True)

        # fallback: 배정ID → 배정기록에서 문의ID로 필터
        assignments = get_assignments_by_inquiry(inquiry_id)
        if assignments.empty:
            return pd.DataFrame()
        valid_aids = set(assignments['배정ID'].astype(str).str.strip()) if '배정ID' in assignments.columns else set()
        if not valid_aids or '배정ID' not in pay_df.columns:
            return pd.DataFrame()
        pay_df = pay_df[pay_df['배정ID'].astype(str).str.strip().isin(valid_aids)]
        return pay_df.reset_index(drop=True)
    except Exception as e:
        print(f"get_payment_records_by_inquiry error: {e}")
        return pd.DataFrame()


def update_payment_status(assign_id: str, new_status: str, pay_date: str = '') -> bool:
    """지급내역 시트에서 배정ID로 찾아 지급상태와 지급일을 업데이트.
    레코드가 없으면 새로 생성 (최소 정보만).
    """
    try:
        ensure_payment_sheet()
        client = get_connection()
        if not client:
            return False
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("지급내역")
        all_vals = wks.get_all_values()
        headers = all_vals[0] if all_vals else []
        bid_col = headers.index('배정ID') + 1 if '배정ID' in headers else 2
        status_col_idx = headers.index('지급상태') + 1 if '지급상태' in headers else 15
        date_col_idx = headers.index('지급일') + 1 if '지급일' in headers else 16

        target_row = None
        for i, row in enumerate(all_vals[1:], 2):
            if len(row) >= bid_col and str(row[bid_col - 1]).strip() == str(assign_id).strip():
                target_row = i
                break

        if target_row:
            # 기존 레코드 업데이트
            from gspread.cell import Cell
            cells = [
                Cell(row=target_row, col=status_col_idx, value=new_status),
            ]
            if pay_date:
                cells.append(Cell(row=target_row, col=date_col_idx, value=pay_date))
            wks.update_cells(cells, value_input_option='RAW')
            print(f"✅ 지급상태 업데이트: {assign_id} → {new_status}")
            invalidate_payment_cache()
            return True
        else:
            # 레코드 없으면 무시 (먼저 지급기록 저장 필요)
            print(f"⚠️ 지급내역에 {assign_id} 미존재 — 지급기록 저장을 먼저 해주세요")
            return False
    except Exception as e:
        print(f"❌ update_payment_status 오류: {e}")
        return False


def batch_save_payment_records(records: list) -> dict:
    """지급내역 시트에 여러 건을 한 번에 저장 (API 호출 최소화).
    
    Args:
        records: list of payment_dict
    Returns:
        {'saved': int, 'updated': int, 'failed': int}
    """
    if not records:
        return {'saved': 0, 'updated': 0, 'failed': 0}
    ensure_payment_sheet()
    client = get_connection()
    if not client:
        return {'saved': 0, 'updated': 0, 'failed': len(records)}
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("지급내역")
        all_vals = wks.get_all_values()
        headers = all_vals[0] if all_vals else []
        bid_col = headers.index('배정ID') + 1 if '배정ID' in headers else 2

        # 기존 배정ID → 행번호 맵핑 (1회 읽기)
        existing_map = {}
        for i, row in enumerate(all_vals[1:], 2):
            if len(row) >= bid_col:
                _bid = str(row[bid_col - 1]).strip()
                if _bid:
                    existing_map[_bid] = i

        saved, updated, failed = 0, 0, 0
        from gspread.cell import Cell
        batch_cells = []
        new_rows = []

        for pd_dict in records:
            try:
                target_bid = str(pd_dict.get('배정ID', '')).strip()
                if not target_bid:
                    failed += 1
                    continue

                pay_id = f"P-{datetime.now().strftime('%y%m%d')}-{str(uuid4())[:6]}"
                row_values = [
                    '',  # placeholder for pay_id
                    pd_dict.get('배정ID', ''),
                    pd_dict.get('문의ID', ''),
                    pd_dict.get('인력명', ''),
                    pd_dict.get('현장명', ''),
                    pd_dict.get('파견기간', ''),
                    pd_dict.get('파견일수', 0),
                    pd_dict.get('기본급', 0),
                    pd_dict.get('야근비', 0),
                    pd_dict.get('식사비', 0),
                    pd_dict.get('교통비', 0),
                    pd_dict.get('보너스', 0),
                    pd_dict.get('소계', 0),
                    pd_dict.get('세금공제', 0),
                    pd_dict.get('최종지급액', 0),
                    pd_dict.get('지급상태', '대기'),
                    pd_dict.get('지급일', ''),
                    pd_dict.get('지급담당자', ''),
                    pd_dict.get('은행명', ''),
                    pd_dict.get('계좌번호', ''),
                    pd_dict.get('주민등록번호', ''),
                    pd_dict.get('비고', ''),
                ]

                if target_bid in existing_map:
                    # 업데이트: 기존 행 위에 덮어쓰기 (셀 단위 배치)
                    target_row = existing_map[target_bid]
                    row_values[0] = all_vals[target_row - 1][0] if len(all_vals) >= target_row else pay_id
                    # 기존 완료/확인완료 건의 지급상태와 지급일은 보존 (덮어쓰기 방지)
                    existing_row = all_vals[target_row - 1] if len(all_vals) >= target_row else []
                    status_col = headers.index('지급상태') if '지급상태' in headers else -1
                    date_col = headers.index('지급일') if '지급일' in headers else -1
                    if status_col >= 0 and len(existing_row) > status_col:
                        existing_status = str(existing_row[status_col]).strip()
                        if existing_status in ('완료', '확인완료'):
                            row_values[status_col] = existing_status
                            if date_col >= 0 and len(existing_row) > date_col:
                                row_values[date_col] = existing_row[date_col]
                    for col_idx, val in enumerate(row_values):
                        batch_cells.append(Cell(row=target_row, col=col_idx + 1, value=val))
                    updated += 1
                else:
                    # 신규: 새 행 추가
                    row_values[0] = pay_id
                    new_rows.append(row_values)
                    saved += 1
            except Exception:
                failed += 1

        # 배치 업데이트 (기존 행 수정)
        if batch_cells:
            wks.update_cells(batch_cells, value_input_option='RAW')

        # 신규 행 추가 (일괄 append)
        if new_rows:
            next_row = len(all_vals) + 1
            needed = next_row + len(new_rows) - wks.row_count
            if needed > 0:
                wks.add_rows(max(needed, 100))
            wks.update(f'A{next_row}', new_rows, value_input_option='RAW')

        invalidate_payment_cache()
        print(f"✅ batch_save: {saved} saved, {updated} updated, {failed} failed")
        return {'saved': saved, 'updated': updated, 'failed': failed}
    except Exception as e:
        print(f"❌ batch_save_payment_records 오류: {e}")
        return {'saved': 0, 'updated': 0, 'failed': len(records)}


def batch_update_payment_status(updates: list) -> dict:
    """여러 건의 지급상태를 한 번에 업데이트 (API 호출 최소화).
    
    Args:
        updates: list of {'배정ID': str, '지급상태': str, '지급일': str}
    Returns:
        {'success': int, 'not_found': int, 'failed': int}
    """
    if not updates:
        return {'success': 0, 'not_found': 0, 'failed': 0}
    try:
        ensure_payment_sheet()
        client = get_connection()
        if not client:
            return {'success': 0, 'not_found': 0, 'failed': len(updates)}
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("지급내역")
        all_vals = wks.get_all_values()
        headers = all_vals[0] if all_vals else []
        bid_col = headers.index('배정ID') + 1 if '배정ID' in headers else 2
        status_col_idx = headers.index('지급상태') + 1 if '지급상태' in headers else 15
        date_col_idx = headers.index('지급일') + 1 if '지급일' in headers else 16

        # 기존 배정ID → 행번호 맵핑 (1회 읽기)
        existing_map = {}
        for i, row in enumerate(all_vals[1:], 2):
            if len(row) >= bid_col:
                _bid = str(row[bid_col - 1]).strip()
                if _bid:
                    existing_map[_bid] = i

        from gspread.cell import Cell
        batch_cells = []
        success, not_found = 0, 0

        for u in updates:
            _bid = str(u.get('배정ID', '')).strip()
            _status = u.get('지급상태', '')
            _date = u.get('지급일', '')
            if _bid in existing_map:
                _row = existing_map[_bid]
                batch_cells.append(Cell(row=_row, col=status_col_idx, value=_status))
                if _date:
                    batch_cells.append(Cell(row=_row, col=date_col_idx, value=_date))
                success += 1
            else:
                not_found += 1

        if batch_cells:
            wks.update_cells(batch_cells, value_input_option='RAW')

        invalidate_payment_cache()
        print(f"✅ batch_update_status: {success} ok, {not_found} not found")
        return {'success': success, 'not_found': not_found, 'failed': 0}
    except Exception as e:
        print(f"❌ batch_update_payment_status 오류: {e}")
        return {'success': 0, 'not_found': 0, 'failed': len(updates)}


# ---------------------------------------------------------
# 본사 인원 정보 (코드 내 상수)
# ---------------------------------------------------------

HQ_STAFF = [
    {"이름": "최규성", "직무": "현장총괄", "구분": "본사"},
    {"이름": "송무재", "직무": "현장관리", "구분": "본사"},
    {"이름": "여지은", "직무": "현장관리", "구분": "본사"},
]


# ---------------------------------------------------------
# 신규 인력 STAFF 시트 등록
# ---------------------------------------------------------

def add_new_staff(staff_info: dict) -> bool:
    """
    STAFF 시트에 신규 인력 등록
    staff_info: {"이름": str, "연락처": str, "성별": str, "가능직무": str, ...}
    """
    client = get_connection()
    if not client:
        return False
    try:
        sh = client.open_by_key(SHEET_ID)
        wks = sh.worksheet("STAFF")
        headers = [str(h).strip() for h in wks.row_values(1)]

        if not headers:
            print("STAFF 시트에 헤더가 없습니다")
            return False

        # 이름 중복 체크
        name = str(staff_info.get('이름', '')).strip()
        if not name:
            print("이름이 비어있습니다")
            return False

        name_col_idx = None
        for nc in ['이름', '인력명', '성명']:
            if nc in headers:
                name_col_idx = headers.index(nc)
                break
        if name_col_idx is not None:
            existing_names = wks.col_values(name_col_idx + 1)
            if name in [str(n).strip() for n in existing_names]:
                print(f"이미 존재하는 이름: {name}")
                return False  # 중복

        # 추가할 행 데이터 구성
        row_values = [''] * len(headers)
        for key, val in staff_info.items():
            key = str(key).strip()
            if key in headers:
                row_values[headers.index(key)] = str(val) if val else ''

        # 다음 빈 행
        all_vals = wks.col_values(1)
        next_row = len(all_vals) + 1

        if next_row > wks.row_count:
            wks.add_rows(100)

        wks.update(f'A{next_row}', [row_values], value_input_option='RAW')
        invalidate_data()
        print(f"STAFF 신규 등록: {name} at row {next_row}")
        return True

    except Exception as e:
        print(f"add_new_staff error: {e}")
        return False
