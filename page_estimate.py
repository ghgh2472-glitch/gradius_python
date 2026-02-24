# page_estimate.py  v10 — 견적 통합관리 Ultimate
"""
견적 통합 관리:
- 버그 수정: 기간 전달 (w_date_range key), 저장 후 값 소실
- 접수 + 견적수정 모두 지원
- 견적 히스토리 & 비교 뷰
- 단가 일괄 조정
- 고객별 자동 추천 단가
- 매입원가→지출금액 명칭
"""
import streamlit as st
import pandas as pd
import utils_estimate as ue
import data_loader as db
import status_config as sc
from datetime import datetime, timedelta, date, time
import time as _time
import base64
import os

# ==============================================================================
# 1. 스타일 & 헬퍼
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .block-container { max-width: 95% !important; padding-top: 1rem; }
        .stButton>button { border-radius: 6px; font-weight: 600; width: 100%; }
        .analysis-box { background:#fff7ed; border:1px solid #fdba74; padding:15px; border-radius:8px; margin-bottom:10px; }
        .result-box { background:#f0fdf4; border:2px solid #166534; padding:20px; border-radius:12px; margin-top:15px; text-align:right; }
        .sub-header { font-size:15px; font-weight:bold; color:#1e3a8a; border-bottom:2px solid #e2e8f0; padding-bottom:5px; margin:15px 0 10px 0; }
        .action-bar { margin-top: 20px; padding-top: 10px; border-top: 2px solid #3b82f6; }
        .history-card { background:white; border:1px solid #e5e7eb; padding:14px; border-radius:8px; margin-bottom:8px; border-left:4px solid #6366f1; }
        .recommend-box { background:#eff6ff; border:2px solid #3b82f6; padding:12px 16px; border-radius:10px; margin-bottom:8px; }
        .saved-banner { background:#dcfce7; border:2px solid #22c55e; padding:12px 16px; border-radius:8px; margin-bottom:10px; text-align:center; font-weight:bold; color:#166534; }
        /* data_editor 스크롤바 겹침 해소 */
        [data-testid="stDataFrame"] > div { padding-bottom: 12px; }
        div[data-testid="stDataEditor"] iframe { min-height: 200px; }
        /* radio-as-tabs */
        div[data-testid="stRadio"] > div[role="radiogroup"] {
            gap: 0; display: flex; flex-wrap: wrap;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label {
            background: #f0f2f6; border: 1px solid #d1d5db; padding: 8px 20px;
            cursor: pointer; font-weight: 700; font-size: 14px;
            border-radius: 0; margin: 0 -1px 0 0;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label:first-child { border-radius: 8px 0 0 8px; }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label:last-child { border-radius: 0 8px 8px 0; }
        div[data-testid="stRadio"] > div[role="radiogroup"] > label[data-checked="true"] {
            background: #0f766e; color: white; border-color: #0f766e;
        }
    </style>
    """, unsafe_allow_html=True)


def _safe_str(val, default=''):
    """NaN/None/nan 문자열 안전 변환"""
    if val is None:
        return default
    s = str(val).strip()
    if s in ('nan', 'None', 'NaN', ''):
        return default
    return s


def _safe_int(val, default=0):
    """NaN/None 안전 정수 변환"""
    if val is None:
        return default
    try:
        import math
        f = float(val)
        if math.isnan(f):
            return default
        return int(f)
    except (ValueError, TypeError):
        return default


def load_local_banner():
    if os.path.exists("banner.png"):
        try:
            with open("banner.png", "rb") as f:
                return base64.b64encode(f.read()).decode()
        except: pass
    return None


def image_to_base64(uploaded_file):
    if uploaded_file:
        try: return base64.b64encode(uploaded_file.getvalue()).decode()
        except: pass
    return None


def get_default_terms_top():
    return """1. 결제사항 | 행사시작전 2주이내 선금 50% | 행사 종료 후 1주이내 잔금 50%
※ 견적은 상황에 따라 변동될 수 있습니다.
2. 계약 확정 안내 | 우수한 인력 확보 및 행사 품질 유지를 위해 행사일 기준 3주 전 계약을 권장합니다.
※ 부득이한 경우라도 최소 2주 전까지는 확정해 주시기 바랍니다."""


def get_default_terms_side():
    return """3. 근무 및 비용 기준
- 계약시간 근무 기준 | 계약시간 이후 추가시간 발생 시 시간당 추가 금액
  • 경호원 & 경비지도사 : 30,000원 (VAT 별도) • STAFF : 20,000원 (VAT 별도)
- 복리후생비, 일반관리비, 직책수당 단가 포함"""


def _load_existing_items(inquiry_id):
    """기존 견적품목을 est_items 형식 DataFrame으로 로드"""
    raw = db.load_estimate_items(inquiry_id)
    if raw.empty:
        return pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','할인액','매출합계','매입합계','비고'])
    rows = []
    for _, r in raw.iterrows():
        name = str(r.get('직군명', ''))
        if str(r.get('팀장여부', '')).strip() == '팀장':
            name += ' [팀장]'
        # 컬럼명 호환: 인원수→수량 (load_estimate_items에서도 정규화하지만 안전장치)
        qty = ue.safe_int(r.get('수량', r.get('인원수', 0)))
        days = ue.safe_int(r.get('일수', 1))
        sell = ue.safe_int(r.get('매출단가', 0))
        buy = ue.safe_int(r.get('매입단가', 0))
        disc = ue.safe_int(r.get('할인액', r.get('할인율', 0)))
        discounted_sell = max(0, sell - disc)
        rows.append({
            '품목': name,
            '규격': str(r.get('규격', r.get('근무시간', ''))),
            '수량': qty, '일수': days,
            '매출단가': sell, '매입단가': buy,
            '할인액': disc,
            '매출합계': discounted_sell * qty * days,
            '매입합계': buy * qty * days,
            '비고': str(r.get('비고', ''))
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','할인액','매출합계','매입합계','비고'])


# ==============================================================================
# 2. 메인 show()
# ==============================================================================
def show(data):
    apply_styles()

    # ── 데이터 로드 ──
    df_inq = data.get('inq', pd.DataFrame())
    df_est = data.get('estimate', pd.DataFrame())
    df_roles = data.get('roles', pd.DataFrame())
    df_factors = data.get('factors', pd.DataFrame())
    df_guides = data.get('guides', pd.DataFrame())
    df_clients = data.get('client', pd.DataFrame())

    if '문의날짜' in df_inq.columns:
        df_inq = df_inq.rename(columns={'문의날짜': '작성일'})
    if '작성일' not in df_inq.columns:
        df_inq['작성일'] = ""
    if not df_roles.empty and '직군명' not in df_roles.columns:
        df_roles['직군명'] = df_roles['Role']

    st.title("🧮 견적 통합 관리")

    # ── 저장 완료 배너 ──
    if st.session_state.get('_est_saved'):
        st.markdown('<div class="saved-banner">✅ 견적이 정상 저장되었습니다. 다른 프로젝트를 선택하거나 계속 수정할 수 있습니다.</div>', unsafe_allow_html=True)
        if st.button("확인", key="dismiss_saved"):
            del st.session_state['_est_saved']
            st.rerun()

    # ================================================================
    # 프로젝트 대기열 (접수 + 견적수정 + 체결수정)
    # ================================================================
    pending_new = pd.DataFrame()
    pending_edit = pd.DataFrame()
    pending_contracted = pd.DataFrame()
    if not df_inq.empty and '상태' in df_inq.columns:
        pending_new = df_inq[df_inq['상태'] == sc.STATUS_FLOW[0]].sort_values('작성일', ascending=False).copy()
        pending_edit = df_inq[df_inq['상태'] == sc.STATUS_FLOW[1]].sort_values('작성일', ascending=False).copy()
        # 체결 이후 상태도 견적 수정 가능 (체결, 배정완료, 진행중)
        _edit_statuses = [sc.STATUS_FLOW[i] for i in range(2, min(5, len(sc.STATUS_FLOW)))]
        pending_contracted = df_inq[df_inq['상태'].isin(_edit_statuses)].sort_values('작성일', ascending=False).copy()

    p_list = ["(신규작성)"]
    if not pending_new.empty:
        pending_new['label'] = "[접수] " + pending_new['업체명'].astype(str) + " (" + pending_new['행사명'].astype(str) + ")"
        p_list += pending_new['label'].tolist()
    if not pending_edit.empty:
        pending_edit['label'] = "[수정] " + pending_edit['업체명'].astype(str) + " (" + pending_edit['행사명'].astype(str) + ")"
        p_list += pending_edit['label'].tolist()
    if not pending_contracted.empty:
        pending_contracted['label'] = "[체결수정] " + pending_contracted['업체명'].astype(str) + " (" + pending_contracted['행사명'].astype(str) + ")"
        p_list += pending_contracted['label'].tolist()

    _frames = [df for df in [pending_new, pending_edit, pending_contracted] if not df.empty]
    all_pending = pd.concat(_frames, ignore_index=True) if _frames else pd.DataFrame()

    est_left, est_right = st.columns([1, 3])
    with est_left:
        st.markdown("##### 📂 프로젝트")
        # 신규작성 버튼
        _new_selected = st.session_state.get('_est_selected', '(신규작성)') == '(신규작성)'
        _new_border = "2px solid #10b981" if _new_selected else "1px solid #e5e7eb"
        _new_bg = "#ecfdf5" if _new_selected else "white"
        st.markdown(f"""
        <div style="background:{_new_bg}; border:{_new_border}; border-radius:8px; padding:10px; margin-bottom:4px; text-align:center;">
            <span style="font-weight:700; font-size:13px;">➕ 신규 작성</span>
        </div>
        """, unsafe_allow_html=True)
        if st.button("신규", key="_est_sel_new", use_container_width=True):
            st.session_state['_est_selected'] = '(신규작성)'
            st.rerun()

        # 프로젝트 카드 목록
        for idx, lbl in enumerate(p_list[1:]):  # [1:]은 (신규작성) 제외
            # 상태별 색상
            if lbl.startswith("[접수]"):
                badge = "🆕"; color = "#10b981"; bg_sel = "#ecfdf5"
            elif lbl.startswith("[수정]"):
                badge = "📝"; color = "#f59e0b"; bg_sel = "#fffbeb"
            else:
                badge = "⚠️"; color = "#ef4444"; bg_sel = "#fef2f2"

            is_sel = st.session_state.get('_est_selected') == lbl
            border = f"2px solid {color}" if is_sel else "1px solid #e5e7eb"
            bg = bg_sel if is_sel else "white"
            # 라벨에서 업체/행사 추출
            _display = lbl.split("] ", 1)[-1] if "] " in lbl else lbl
            _parts = _display.split(" (")
            _company = _parts[0] if _parts else _display
            _event = _parts[1].rstrip(")") if len(_parts) > 1 else ""

            st.markdown(f"""
            <div style="background:{bg}; border:{border}; border-radius:8px; padding:8px 10px; margin-bottom:4px;">
                <div style="font-weight:700; font-size:12px; color:#111;">{badge} {_company}</div>
                <div style="font-size:11px; color:#6b7280; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{_event}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("선택", key=f"_est_sel_{idx}", use_container_width=True):
                st.session_state['_est_selected'] = lbl
                st.rerun()

        # 기본 선택
        if '_est_selected' not in st.session_state:
            st.session_state['_est_selected'] = p_list[0]

    sel_p = st.session_state.get('_est_selected', p_list[0])

    with est_right:
        if sel_p.startswith("[체결수정]"):
            st.warning("⚠️ 체결된 견적을 수정합니다. 저장 시 기존 데이터를 덮어씁니다.")
        elif sel_p.startswith("[수정]"):
            st.info("📝 기존 견적을 수정합니다. 저장 시 기존 데이터를 덮어씁니다.")
        elif sel_p.startswith("[접수]"):
            st.success("🆕 새 견적을 작성합니다.")

    # ── 세션 초기화 ──
    if 'est_items' not in st.session_state:
        st.session_state['est_items'] = pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','할인액','매출합계','매입합계','비고'])
    if 'w_client' not in st.session_state:
        st.session_state.update({
            'w_client': '', 'w_event': '', 'w_loc': '', 'w_manager': '', 'w_contact': '',
            'w_qty': 1, 'w_sdate': None, 'w_edate': None,
            'w_date_periods': [],
            'w_time_in': datetime.strptime("09:00", "%H:%M").time(),
            'w_time_out': datetime.strptime("18:00", "%H:%M").time(),
            'w_time_mode': '출퇴근 지정',  # '출퇴근 지정' | '시간 기준'
            'w_hour_base': 8,
            'w_terms_top': get_default_terms_top(),
            'w_terms_side': get_default_terms_side()
        })

    # ================================================================
    # 프로젝트 선택 시 데이터 로드
    # ================================================================
    if sel_p != "(신규작성)" and not all_pending.empty and st.session_state.get('last_project') != sel_p:
        try:
            _matched_pending = all_pending[all_pending['label'] == sel_p]
            if _matched_pending.empty:
                st.warning("⚠️ 선택한 프로젝트를 찾을 수 없습니다. 목록을 다시 확인해주세요.")
                st.session_state['_est_selected'] = '(신규작성)'
                st.session_state['last_project'] = '(신규작성)'
                st.rerun()
            target = _matched_pending.iloc[0]
            target_id = str(target.get('문의ID', '')).strip()

            # ▶ 날짜 개별 파싱 (행사시작일 > 시작일 > 일시 순으로 시도)
            start_raw = str(target.get('행사시작일', '')).strip()
            end_raw = str(target.get('행사종료일', '')).strip()
            if not start_raw or start_raw in ('nan', 'None', ''):
                start_raw = str(target.get('시작일', '')).strip()
            if not end_raw or end_raw in ('nan', 'None', ''):
                end_raw = str(target.get('종료일', '')).strip()
            # fallback: 일시 컬럼 (~ 구분자 포함 가능)
            if (not start_raw or start_raw in ('nan', 'None', '')):
                raw_ilsi = str(target.get('일시', '')).strip()
                if raw_ilsi and raw_ilsi not in ('nan', 'None', ''):
                    if '~' in raw_ilsi:
                        parts = raw_ilsi.split('~', 1)
                        start_raw = parts[0].strip()
                        end_raw = parts[1].strip() if len(parts) > 1 else start_raw
                    else:
                        start_raw = raw_ilsi
                        end_raw = raw_ilsi

            # 다중 기간 처리: / 구분자가 있으면 각각 파싱
            _has_multi = '/' in start_raw or '/' in end_raw
            if _has_multi:
                _starts = [s.strip() for s in start_raw.split('/')]
                _ends = [e.strip() for e in end_raw.split('/')]
                _raw_segments = []
                for _i in range(max(len(_starts), len(_ends))):
                    _s = _starts[_i] if _i < len(_starts) else _starts[-1]
                    _e = _ends[_i] if _i < len(_ends) else _ends[-1]
                    if _s and _s not in ('nan', 'None', ''):
                        _raw_segments.append(f"{_s}~{_e}")
                raw_dates = " / ".join(_raw_segments)
            else:
                if start_raw and end_raw and start_raw not in ('nan', 'None', ''):
                    raw_dates = f"{start_raw}~{end_raw}"
                elif start_raw and start_raw not in ('nan', 'None', ''):
                    raw_dates = start_raw
                else:
                    raw_dates = ''

            s_d, e_d, _ = ue.smart_parse_date(raw_dates)
            # 다중 기간 파싱
            _multi_periods = ue.smart_parse_dates_multi(raw_dates)
            _date_periods = [(p[0], p[1]) for p in _multi_periods]
            s_t, e_t, _ = ue.smart_parse_time(target.get('행사시간', str(target.get('시간', ''))))
            qty = ue.safe_int(str(target.get('필요인력', target.get('요청인원', target.get('인원', '1')))).replace('명', ''))

            # ▶ 기존 견적 메타데이터 로드 (복장/식사/주차/특이사항)
            _est_meta = {}
            if not df_est.empty and '문의ID' in df_est.columns:
                _matched_est = df_est[df_est['문의ID'].astype(str).str.strip() == target_id]
                if not _matched_est.empty:
                    _est_meta = _matched_est.iloc[0].to_dict()

            # ▶ 문의에서 복장/식사/주차 읽기 (개별 컬럼 우선, 특이사항 regex fallback)
            _inq_note = str(target.get('특이사항', '')).strip()
            _inq_dress = str(target.get('복장', '')).strip()
            _inq_meal = str(target.get('식사', '')).strip()
            _inq_parking = str(target.get('주차', '')).strip()
            _inq_note_clean = _inq_note
            
            # 개별 컬럼에 값이 없으면 (기존 데이터 호환) 특이사항에서 regex 파싱
            import re as _re
            if not _inq_dress or _inq_dress in ('nan', 'None'):
                _dress_m = _re.search(r'\[복장:([^\]]+)\]', _inq_note)
                if _dress_m:
                    _inq_dress = _dress_m.group(1).strip()
                    _inq_note_clean = _inq_note_clean.replace(_dress_m.group(0), '').strip()
            else:
                # 개별 컬럼에 있으면 특이사항에서도 [복장:...] 제거
                _dress_m = _re.search(r'\[복장:[^\]]+\]', _inq_note_clean)
                if _dress_m:
                    _inq_note_clean = _inq_note_clean.replace(_dress_m.group(0), '').strip()
            
            if not _inq_meal or _inq_meal in ('nan', 'None'):
                _meal_m = _re.search(r'\[식사:([^\]]+)\]', _inq_note)
                if _meal_m:
                    _inq_meal = _meal_m.group(1).strip()
                    _inq_note_clean = _inq_note_clean.replace(_meal_m.group(0), '').strip()
            else:
                _meal_m = _re.search(r'\[식사:[^\]]+\]', _inq_note_clean)
                if _meal_m:
                    _inq_note_clean = _inq_note_clean.replace(_meal_m.group(0), '').strip()
            
            if not _inq_parking or _inq_parking in ('nan', 'None'):
                _parking_m = _re.search(r'\[주차:([^\]]+)\]', _inq_note)
                if _parking_m:
                    _inq_parking = _parking_m.group(1).strip()
                    _inq_note_clean = _inq_note_clean.replace(_parking_m.group(0), '').strip()
            else:
                _parking_m = _re.search(r'\[주차:[^\]]+\]', _inq_note_clean)
                if _parking_m:
                    _inq_note_clean = _inq_note_clean.replace(_parking_m.group(0), '').strip()
            
            # 견적 메타 > 문의 파싱 순으로 결정
            def _pick(est_key, inq_val):
                v = str(_est_meta.get(est_key, '')).strip()
                if v and v not in ('nan', 'None', ''): return v
                return inq_val

            # 시간 상속: 파싱된 출퇴근 시간 반영
            _time_mode = '출퇴근 지정'
            _hour_base = 8
            _time_str = str(target.get('행사시간', target.get('시간', ''))).strip()
            # '8시간', '10시간 기준' 같은 패턴 감지
            import re as _re2
            _hour_match = _re2.search(r'(\d+)\s*시간', _time_str)
            if _hour_match and ('~' not in _time_str and ':' not in _time_str):
                _time_mode = '시간 기준'
                _hour_base = int(_hour_match.group(1))

            st.session_state.update({
                'w_client': _safe_str(target.get('업체명', '')),
                'w_event': _safe_str(target.get('행사명', '')),
                'w_loc': _safe_str(target.get('장소', '')),
                'w_manager': _safe_str(target.get('담당자', '')),
                'w_contact': _safe_str(target.get('연락처', target.get('담당자연락처', ''))),
                'w_sdate': s_d, 'w_edate': e_d,
                'w_date_periods': _date_periods,
                'w_qty': qty,
                'w_time_in': s_t,
                'w_time_out': e_t,
                'w_time_mode': _time_mode,
                'w_hour_base': _hour_base,
                'last_project': sel_p,
                '_current_inq_id': target_id,
                'w_dress': _safe_str(_pick('복장', _inq_dress)),
                'w_meal': _safe_str(_pick('식사', _inq_meal)),
                'w_parking': _safe_str(_pick('주차', _inq_parking)),
                'w_note': _safe_str(_pick('특이사항', _inq_note_clean)),
            })

            # ▶ 견적수정/체결수정 시 기존 품목 로드
            if sel_p.startswith("[수정]") or sel_p.startswith("[체결수정]"):
                st.session_state['est_items'] = _load_existing_items(target_id)
            else:
                st.session_state['est_items'] = pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','할인액','매출합계','매입합계','비고'])

            # ▶ 세대 카운터 증가 → TAB2 위젯을 완전히 새로 생성 (Streamlit 위젯 상태 복원 문제 회피)
            st.session_state['_tab2_gen'] = st.session_state.get('_tab2_gen', 0) + 1
            _keys_to_del = ['w_date_range', 'discount_amt']
            # 이전 세대 위젯 키 정리
            for _sk in list(st.session_state.keys()):
                if any(_sk.startswith(p) for p in ['final_client_', 'final_manager_', 'final_contact_', 'final_loc_',
                                                     'final_edit_table_', 'est_items_editor_', 'additional_costs_editor_']):
                    _keys_to_del.append(_sk)
            # 견적안 캐시 무효화 (프로젝트 전환 시)
            for _ck in list(st.session_state.keys()):
                if _ck.startswith('_loaded_versions_'):
                    _keys_to_del.append(_ck)
            # 날짜 위젯 키는 올바른 값으로 설정
            for _ki in range(20):
                if _ki < len(_date_periods):
                    st.session_state[f'dp_s_{_ki}'] = _date_periods[_ki][0]
                    st.session_state[f'dp_e_{_ki}'] = _date_periods[_ki][1]
                else:
                    _keys_to_del.extend([f"dp_s_{_ki}", f"dp_e_{_ki}"])
            for k in _keys_to_del:
                if k in st.session_state:
                    del st.session_state[k]

            st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '수량', '일수', '단가', '금액', '비고'])
            if '_est_saved' in st.session_state:
                del st.session_state['_est_saved']

            st.rerun()
        except Exception as e:
            st.warning(f"데이터 로드 오류: {e}")

    current_inq_id = st.session_state.get('_current_inq_id', '')
    brain = ue.EstimateBrain(df_roles, df_guides, df_factors, df_clients)

    # ================================================================
    # 탭 구성
    # ================================================================
    # ── 복수 견적안 관리 (시트 영구 저장) ──
    _cur_inq = st.session_state.get('_current_inq_id', '')

    # ── 메타데이터 수집 헬퍼 ──
    def _collect_metadata():
        """현재 session_state에서 프로젝트 메타데이터를 수집"""
        _periods = st.session_state.get('w_date_periods', [])
        _period_strs = []
        for _ps, _pe in _periods:
            _period_strs.append([str(_ps), str(_pe)])
        # 부대비용 DataFrame → 리스트
        _add_costs = []
        _add_df = st.session_state.get('additional_costs', pd.DataFrame())
        if not _add_df.empty:
            for _, _ar in _add_df.iterrows():
                _add_costs.append({
                    '항목': str(_ar.get('항목', '') or ''),
                    '수량': _safe_int(_ar.get('수량', 1)),
                    '일수': _safe_int(_ar.get('일수', 1)),
                    '단가': _safe_int(_ar.get('단가', 0)),
                    '금액': _safe_int(_ar.get('금액', 0)),
                    '비고': str(_ar.get('비고', '') or ''),
                })
        return {
            'w_client': _safe_str(st.session_state.get('w_client')),
            'w_event': _safe_str(st.session_state.get('w_event')),
            'w_loc': _safe_str(st.session_state.get('w_loc')),
            'w_manager': _safe_str(st.session_state.get('w_manager')),
            'w_contact': _safe_str(st.session_state.get('w_contact')),
            'w_sdate': str(st.session_state.get('w_sdate', '')),
            'w_edate': str(st.session_state.get('w_edate', '')),
            'w_date_periods': _period_strs,
            'w_qty': int(st.session_state.get('w_qty', 1)),
            'w_dress': _safe_str(st.session_state.get('w_dress')),
            'w_meal': _safe_str(st.session_state.get('w_meal')),
            'w_parking': _safe_str(st.session_state.get('w_parking')),
            'w_note': _safe_str(st.session_state.get('w_note')),
            'additional_costs': _add_costs,
        }

    def _restore_metadata(meta):
        """메타데이터 딕셔너리 → session_state 복원"""
        if not meta:
            return
        for _k in ['w_client', 'w_event', 'w_loc', 'w_manager', 'w_contact',
                    'w_dress', 'w_meal', 'w_parking', 'w_note']:
            if _k in meta:
                st.session_state[_k] = _safe_str(meta[_k])
        if 'w_qty' in meta:
            st.session_state['w_qty'] = int(meta.get('w_qty', 1))
        # 날짜 복원
        _periods = meta.get('w_date_periods', [])
        _restored = []
        for _pair in _periods:
            if isinstance(_pair, (list, tuple)) and len(_pair) == 2:
                try:
                    from datetime import date as _d
                    _s = _d.fromisoformat(str(_pair[0])) if str(_pair[0]) not in ('None','') else None
                    _e = _d.fromisoformat(str(_pair[1])) if str(_pair[1]) not in ('None','') else None
                    if _s and _e:
                        _restored.append((_s, _e))
                except:
                    pass
        if _restored:
            st.session_state['w_date_periods'] = _restored
        # 부대비용 복원
        _add_costs = meta.get('additional_costs', [])
        if _add_costs:
            st.session_state['additional_costs'] = pd.DataFrame(_add_costs)
        elif 'additional_costs' in meta:
            # 메타에 키가 있지만 비어있으면 초기화
            st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '수량', '일수', '단가', '금액', '비고'])
        # 날짜 위젯 키 설정
        if _restored:
            st.session_state['w_sdate'] = _restored[0][0]
            st.session_state['w_edate'] = _restored[-1][1]
            for _ri, (_rs, _re) in enumerate(_restored):
                st.session_state[f'dp_s_{_ri}'] = _rs
                st.session_state[f'dp_e_{_ri}'] = _re

    with st.expander("📋 복수 견적안 관리 (하나의 문의에 여러 견적)", expanded=False):
        if not _cur_inq:
            st.info("💡 프로젝트를 먼저 선택하세요. 선택 후 견적안을 저장/불러올 수 있습니다.")
        else:
            st.caption(f"💡 문의 **{_cur_inq}** — 같은 문의에서 여러 견적안을 만들어 비교하세요.")
            
            # 저장된 견적안 로드
            if f'_loaded_versions_{_cur_inq}' not in st.session_state:
                st.session_state[f'_loaded_versions_{_cur_inq}'] = db.load_estimate_versions(_cur_inq)
            _versions = st.session_state[f'_loaded_versions_{_cur_inq}']
            
            _ver_c1, _ver_c2 = st.columns([1.5, 1])
            with _ver_c1:
                _ver_name = st.text_input("견적안 이름", placeholder="예: A안, B안, 경량안", key="ver_name_input")
            with _ver_c2:
                st.write("")  # 간격
                if st.button("💾 현재 견적 → 저장 (품목+프로젝트정보)", key="save_ver"):
                    if _ver_name.strip():
                        with st.spinner("저장 중..."):
                            _meta = _collect_metadata()
                            if db.save_estimate_version(_cur_inq, _ver_name.strip(), st.session_state['est_items'], metadata=_meta):
                                # 캐시 갱신
                                st.session_state[f'_loaded_versions_{_cur_inq}'] = db.load_estimate_versions(_cur_inq)
                                st.session_state['_ver_saved_msg'] = f"✅ '{_ver_name.strip()}' 저장 완료! (품목 {len(st.session_state['est_items'])}건 + 프로젝트정보)"
                                st.rerun()
                            else:
                                st.error("저장 실패")
                    else:
                        st.warning("견적안 이름을 입력해주세요")

            # 저장 완료 메시지 표시
            if '_ver_saved_msg' in st.session_state:
                st.success(st.session_state.pop('_ver_saved_msg'))
            
            # 저장된 견적안 목록
            if _versions:
                _ver_summary = []
                for _vn, _vdata in _versions.items():
                    _vdf = _vdata['items'] if isinstance(_vdata, dict) else _vdata
                    _v_supply = int(_vdf['매출합계'].sum()) if not _vdf.empty and '매출합계' in _vdf.columns else 0
                    _v_cost = int(_vdf['매입합계'].sum()) if not _vdf.empty and '매입합계' in _vdf.columns else 0
                    _has_meta = '✅' if (isinstance(_vdata, dict) and _vdata.get('meta')) else '❌'
                    _ver_summary.append({"견적안": _vn, "품목수": len(_vdf), "공급가액": f"{_v_supply:,}원", "매입원가": f"{_v_cost:,}원", "정보": _has_meta})
                st.dataframe(pd.DataFrame(_ver_summary), use_container_width=True, hide_index=True)
                
                _load_c1, _load_c2 = st.columns([2, 1])
                with _load_c1:
                    _load_ver = st.selectbox("견적안 불러오기", ["선택"] + list(_versions.keys()), key="load_ver_select")
                with _load_c2:
                    st.write("")
                    _btn_c1, _btn_c2 = st.columns(2)
                    with _btn_c1:
                        if _load_ver != "선택" and st.button("📂 불러오기", key="load_ver_btn"):
                            _vdata = _versions[_load_ver]
                            _loaded_df = (_vdata['items'] if isinstance(_vdata, dict) else _vdata).copy()
                            # JSON에서 로드 시 숫자 컬럼 타입 보정
                            _num_cols = ['수량','일수','매출단가','매입단가','할인액','매출합계','매입합계']
                            for _nc in _num_cols:
                                if _nc in _loaded_df.columns:
                                    _loaded_df[_nc] = pd.to_numeric(_loaded_df[_nc], errors='coerce').fillna(0).astype(int)
                            # 필수 컬럼 보장
                            for _rc in ['품목','규격','수량','일수','매출단가','매입단가','할인액','매출합계','매입합계','비고']:
                                if _rc not in _loaded_df.columns:
                                    _loaded_df[_rc] = 0 if _rc in _num_cols else ''
                            st.session_state['est_items'] = _loaded_df
                            # ★ 메타데이터 복원 (수신인, 행사명, 장소, 날짜 등)
                            _meta = _vdata.get('meta', {}) if isinstance(_vdata, dict) else {}
                            if _meta:
                                _restore_metadata(_meta)
                            # 세대 카운터 증가 → data_editor 위젯 완전 재생성
                            st.session_state['_tab2_gen'] = st.session_state.get('_tab2_gen', 0) + 1
                            st.session_state['_ver_loaded_msg'] = f"✅ '{_load_ver}' 불러옴! (품목 {len(_loaded_df)}건" + (" + 프로젝트정보 복원)" if _meta else ")")
                            st.rerun()
                    with _btn_c2:
                        if _load_ver != "선택" and st.button("🗑️ 삭제", key="del_ver_btn"):
                            db.delete_estimate_version(_cur_inq, _load_ver)
                            st.session_state[f'_loaded_versions_{_cur_inq}'] = db.load_estimate_versions(_cur_inq)
                            st.rerun()

                # 불러오기 완료 메시지 표시
                if '_ver_loaded_msg' in st.session_state:
                    st.success(st.session_state.pop('_ver_loaded_msg'))
            else:
                st.info("저장된 견적안이 없습니다. 위에서 이름을 입력하고 저장하세요.")

    _est_tabs = ["🛠️ 견적 산출", "📄 견적서 발행", "📋 히스토리 & 리포트"]
    _active_est = st.radio("estimate", _est_tabs, key="_estimate_tab", horizontal=True, label_visibility="collapsed")
    st.markdown("---")

    # ── 탭 전환 시 위젯 값 보존 로직 ──
    # Streamlit은 렌더링되지 않는 위젯의 키를 session_state에서 삭제하므로
    # TAB1 떠날 때 백업, 돌아올 때 복원
    # (1) 위젯 키 (TAB1에서만 렌더되므로 탭 이동 시 Streamlit이 삭제)
    _widget_keys = ['w_client', 'w_event', 'w_loc', 'w_manager', 'w_contact',
                    'w_qty', 'w_time_in', 'w_time_out', 'w_dress', 'w_meal', 'w_parking', 'w_note']
    # (2) 상속 데이터 키 (위젯이 아닌 순수 세션값이지만, 안전하게 백업)
    _data_keys = ['w_sdate', 'w_edate', 'w_date_periods', 'w_time_mode', 'w_hour_base',
                  '_current_inq_id', 'last_project']
    # (3) 날짜 위젯 키 (dp_s_0 ~ dp_e_19)
    _date_widget_keys = [f'dp_{t}_{i}' for i in range(20) for t in ['s', 'e']]
    _all_backup_keys = _widget_keys + _data_keys + _date_widget_keys

    if _active_est != _est_tabs[0]:
        # TAB1을 떠남 → 현재 값 백업
        for _bk in _all_backup_keys:
            if _bk in st.session_state:
                st.session_state[f'_bak_{_bk}'] = st.session_state[_bk]
        # DataFrame은 별도 백업 (.copy() 필요)
        if 'est_items' in st.session_state:
            st.session_state['_bak_est_items'] = st.session_state['est_items'].copy()
        if 'additional_costs' in st.session_state:
            st.session_state['_bak_additional_costs'] = st.session_state['additional_costs'].copy()
    else:
        # TAB1 진입 → 백업값 복원 (위젯이 아직 렌더 전이라 키를 미리 설정)
        for _bk in _all_backup_keys:
            _bak_key = f'_bak_{_bk}'
            if _bak_key in st.session_state and _bk not in st.session_state:
                st.session_state[_bk] = st.session_state[_bak_key]
        # DataFrame 복원
        if '_bak_est_items' in st.session_state and 'est_items' not in st.session_state:
            st.session_state['est_items'] = st.session_state['_bak_est_items'].copy()
        if '_bak_additional_costs' in st.session_state and 'additional_costs' not in st.session_state:
            st.session_state['additional_costs'] = st.session_state['_bak_additional_costs'].copy()

    # 세대 카운터 (프로젝트 전환/견적안 불러오기 시 위젯 재생성용)
    _g = st.session_state.get('_tab2_gen', 0)

    # ==================================================================
    # TAB 1: 견적 산출 (좌=입력 / 우=결과 장바구니 레이아웃)
    # ==================================================================
    if _active_est == _est_tabs[0]:
        # ── 상단: 프로젝트 정보 (접을 수 있게) ──
        with st.expander("📋 프로젝트 정보", expanded=True):
            pi1, pi2, pi3 = st.columns([1.2, 1.2, 1])
            pi1.text_input("수신인 (업체명)", key="w_client")
            pi2.text_input("행사명", key="w_event")
            pi3.text_input("장소 (현장주소)", key="w_loc")

            # ── 다중 기간 입력 ──
            if 'w_date_periods' not in st.session_state:
                _init_s = st.session_state.get('w_sdate')
                _init_e = st.session_state.get('w_edate')
                if _init_s and _init_e:
                    st.session_state['w_date_periods'] = [(_init_s, _init_e)]
                else:
                    st.session_state['w_date_periods'] = []
            
            # 날짜 미설정 시 안내
            if not st.session_state['w_date_periods']:
                st.info("📅 프로젝트를 선택하면 날짜가 자동으로 설정됩니다. 직접 추가하려면 아래 버튼을 클릭하세요.")
            
            calc_days = 0
            periods_to_keep = []
            for _pi, (_ps, _pe) in enumerate(st.session_state['w_date_periods']):
                # 세션에 위젯 키가 없을 때만 초기값 설정 (value와 key 동시 사용 경고 방지)
                if f'dp_s_{_pi}' not in st.session_state:
                    st.session_state[f'dp_s_{_pi}'] = _ps
                if f'dp_e_{_pi}' not in st.session_state:
                    st.session_state[f'dp_e_{_pi}'] = _pe
                _dc1, _dc2, _dc3, _dc4 = st.columns([1, 1, 0.5, 0.3])
                with _dc1:
                    _new_s = st.date_input(f"시작일" if _pi == 0 else f"시작일 {_pi+1}", key=f"dp_s_{_pi}")
                with _dc2:
                    _new_e = st.date_input(f"종료일" if _pi == 0 else f"종료일 {_pi+1}", key=f"dp_e_{_pi}")
                # None 방어
                if _new_s is None: _new_s = _ps
                if _new_e is None: _new_e = _pe
                with _dc3:
                    try:
                        _p_days = max(1, (_new_e - _new_s).days + 1)
                    except (TypeError, AttributeError):
                        _p_days = 1
                    st.markdown(f"<div style='padding-top:28px;font-size:14px;font-weight:bold;'>{_p_days}일</div>", unsafe_allow_html=True)
                with _dc4:
                    if _pi > 0:
                        if st.button("🗑️", key=f"dp_del_{_pi}", help="이 기간 삭제"):
                            st.session_state['w_date_periods'] = [p for j, p in enumerate(st.session_state['w_date_periods']) if j != _pi]
                            st.rerun()
                calc_days += _p_days
                periods_to_keep.append((_new_s, _new_e))
            
            st.session_state['w_date_periods'] = periods_to_keep
            # 첫 기간 값을 w_sdate/w_edate에도 동기화
            if periods_to_keep:
                st.session_state['w_sdate'] = periods_to_keep[0][0]
                st.session_state['w_edate'] = periods_to_keep[-1][1]
            
            _add_col1, _add_col2, _add_col3 = st.columns([0.3, 1, 2])
            with _add_col1:
                st.write("")  # 사이드바와 간격
            with _add_col2:
                if st.button("➕ 기간 추가", key="add_period_btn"):
                    if st.session_state['w_date_periods']:
                        last_end = st.session_state['w_date_periods'][-1][1]
                        new_start = last_end + timedelta(days=2) if last_end else date.today()
                        new_end = new_start
                    else:
                        new_start = date.today() + timedelta(days=7)
                        new_end = new_start
                    st.session_state['w_date_periods'].append((new_start, new_end))
                    st.rerun()
            with _add_col3:
                if len(st.session_state['w_date_periods']) > 1:
                    st.caption(f"📅 전체 {len(st.session_state['w_date_periods'])}개 기간, 총 **{calc_days}일**")
                else:
                    st.caption(f"📅 총 **{calc_days}일** (비연속 기간이면 '기간 추가' 버튼 클릭)")

            xi1, xi2, xi3, xi4 = st.columns(4)
            xi1.text_input("👔 복장", key="w_dress", placeholder="예: 정장, 캐주얼, 유니폼")
            xi2.text_input("🍽️ 식사", key="w_meal", placeholder="예: 제공, 각자, 도시락")
            xi3.text_input("🅿️ 주차", key="w_parking", placeholder="예: 가능, 불가, 인근 유료")
            xi4.text_input("📝 특이사항", key="w_note", placeholder="유의사항 입력")

        # ── 좌우 2컬럼 (입력 | 결과) ──
        col_input, col_result = st.columns([1, 1.3])

        # ────────────────────────────────────
        # 좌측: 인력추가 → AI분석 → 부대비용입력
        # ────────────────────────────────────
        with col_input:
            # ▶ 인력 품목 추가
            with st.container(border=True):
                st.markdown('<div class="sub-header">➕ 인력 품목 추가</div>', unsafe_allow_html=True)

                # 직군 선택 + 직접 입력
                roles_list = df_roles['직군명'].unique().tolist() if not df_roles.empty else []
                # 경비지도사가 목록에 없으면 추가
                if '경비지도사' not in roles_list:
                    roles_list.append('경비지도사')
                role_options = ["선택"] + roles_list + ["✏️ 직접 입력"]
                role_kr = st.selectbox("직군", role_options, key="role_select")

                custom_role = ""
                if role_kr == "✏️ 직접 입력":
                    custom_role = st.text_input("직군명 직접 입력", placeholder="예: 포토그래퍼, MC, 통역사", key="custom_role_input")
                    role_kr = custom_role if custom_role.strip() else "선택"

                r_info = brain.get_role_info(role_kr)
                role_id, base_p, cost_p = r_info['role_id'], r_info['base_price'], r_info['cost_price']

                if custom_role and base_p == 0:
                    st.info("💡 새 직군입니다. 아래에서 청구/지급 단가를 직접 입력해주세요.")

                # 고객별 자동 추천 단가
                if role_kr != "선택" and st.session_state.get('w_client'):
                    _show_auto_recommend(df_est, st.session_state['w_client'], role_kr)

                # 할증/팀장 (접이식)
                factors = brain.get_factors(role_id)
                f_map = {f"{f['name']} (+{f['price']:,})": f for f in factors}
                picks = []
                is_leader = False
                pay_type = "일급"
                with st.expander("⚙️ 할증/팀장/시급 옵션", expanded=False):
                    picks = st.multiselect("할증 옵션", list(f_map.keys()))
                    opt1, opt2 = st.columns(2)
                    is_leader = opt1.checkbox("팀장 수당")
                    pay_type = opt2.radio("지급기준", ["일급", "시급"], horizontal=True, label_visibility="collapsed")

                add_p = sum([f_map[p]['price'] for p in picks])
                add_c = sum([f_map[p]['cost_add'] for p in picks])
                if is_leader:
                    base_p += 10000; cost_p += 10000

                # ──────────── 근무시간 설정 (개선) ────────────
                # 탭 전환 시 값 복원
                if 'w_time_mode' not in st.session_state:
                    st.session_state['w_time_mode'] = '출퇴근 지정'
                if 'w_hour_base' not in st.session_state:
                    st.session_state['w_hour_base'] = 8

                _tm_col1, _tm_col2 = st.columns([1.2, 2])
                with _tm_col1:
                    time_mode = st.radio("⏰ 근무시간", ["출퇴근 지정", "시간 기준"],
                                         index=0 if st.session_state.get('w_time_mode', '출퇴근 지정') == '출퇴근 지정' else 1,
                                         horizontal=True, key="_time_mode_radio", label_visibility="collapsed")
                    st.session_state['w_time_mode'] = time_mode

                dur = 9.0
                spec_txt = ""

                if time_mode == "출퇴근 지정":
                    # 프리셋 버튼
                    _presets = {"09~18": ("09:00", "18:00"), "08~17": ("08:00", "17:00"),
                                "07~16": ("07:00", "16:00"), "10~19": ("10:00", "19:00"),
                                "22~07": ("22:00", "07:00")}
                    _preset_cols = st.columns(len(_presets) + 1)
                    for _pi, (_plabel, (_ps_t, _pe_t)) in enumerate(_presets.items()):
                        with _preset_cols[_pi]:
                            if st.button(f"⏱ {_plabel}", key=f"preset_{_plabel}", use_container_width=True):
                                st.session_state['w_time_in'] = datetime.strptime(_ps_t, "%H:%M").time()
                                st.session_state['w_time_out'] = datetime.strptime(_pe_t, "%H:%M").time()
                                st.rerun()
                    with _preset_cols[-1]:
                        _use_manual = st.checkbox("직접입력", key="_manual_time_chk")

                    if _use_manual:
                        _mt1, _mt2 = st.columns(2)
                        _manual_in = _mt1.text_input("출근시간", value=st.session_state.get('w_time_in', time(9,0)).strftime('%H:%M'), key="_manual_time_in", placeholder="07:30")
                        _manual_out = _mt2.text_input("퇴근시간", value=st.session_state.get('w_time_out', time(18,0)).strftime('%H:%M'), key="_manual_time_out", placeholder="16:30")
                        try:
                            ti = datetime.strptime(_manual_in.strip(), "%H:%M").time()
                            to_ = datetime.strptime(_manual_out.strip(), "%H:%M").time()
                            st.session_state['w_time_in'] = ti
                            st.session_state['w_time_out'] = to_
                        except ValueError:
                            st.warning("⚠️ 시간 형식은 HH:MM (예: 07:30)")
                            ti = st.session_state.get('w_time_in', time(9,0))
                            to_ = st.session_state.get('w_time_out', time(18,0))
                    else:
                        _tt1, _tt2 = st.columns(2)
                        ti = _tt1.time_input("출근", key="w_time_in")
                        to_ = _tt2.time_input("퇴근", key="w_time_out")

                    dur = ue.smart_parse_time(f"{ti}~{to_}")[2]
                    spec_txt = f"{ti.strftime('%H:%M')}~{to_.strftime('%H:%M')} ({dur}H)"

                else:  # 시간 기준 모드
                    _hb_col1, _hb_col2 = st.columns([1.5, 2])
                    with _hb_col1:
                        _hour_presets = [4, 5, 6, 7, 8, 9, 10, 11, 12]
                        _cur_hb = st.session_state.get('w_hour_base', 8)
                        _hb_idx = _hour_presets.index(_cur_hb) if _cur_hb in _hour_presets else 4
                        hour_base = st.selectbox("⏳ 기준 시간", _hour_presets, index=_hb_idx, key="_hour_base_sel",
                                                 format_func=lambda x: f"{x}시간")
                        st.session_state['w_hour_base'] = hour_base
                    with _hb_col2:
                        _optional_start = st.text_input("시작시간 (선택, 미정이면 비워두세요)", key="_hour_mode_start", placeholder="예: 09:00")

                    dur = float(hour_base)
                    if _optional_start and _optional_start.strip():
                        try:
                            _st_parsed = datetime.strptime(_optional_start.strip(), "%H:%M")
                            _et_parsed = _st_parsed + timedelta(hours=hour_base)
                            ti = _st_parsed.time()
                            to_ = _et_parsed.time()
                            spec_txt = f"{ti.strftime('%H:%M')}~{to_.strftime('%H:%M')} ({dur}H)"
                        except ValueError:
                            ti = time(9, 0)
                            to_ = time(9 + hour_base, 0) if 9 + hour_base < 24 else time(23, 0)
                            spec_txt = f"{hour_base}H 기준 (시간 미정)"
                    else:
                        ti = time(0, 0)
                        to_ = time(0, 0)
                        spec_txt = f"{hour_base}H 기준 (시간 미정)"
                    st.info(f"📌 **{hour_base}시간 기준** 견적으로 산출됩니다")

                # 인원 입력
                iq = st.number_input("👥 인원", min_value=1, key="w_qty")

                cc1, cc2 = st.columns(2)
                fb = cc1.number_input("청구단가", value=base_p + add_p, step=5000)
                fp = cc2.number_input("지급단가", value=cost_p + add_c, step=5000)

                # ── 일자별 상세 입력 (고도화) ──
                use_daily_detail = st.checkbox(
                    "📅 일자별 상세 입력 (날짜마다 인원/시간/단가가 다를 때)",
                    key="use_daily_detail",
                    help="날짜별로 투입 인원, 근무시간, 단가를 개별 설정할 수 있습니다."
                )

                daily_detail_df = None
                if use_daily_detail:
                    # 기간 정보에서 날짜 목록 생성
                    all_dates = []
                    for _ps, _pe in st.session_state.get('w_date_periods', []):
                        _cur = _ps
                        while _cur <= _pe:
                            all_dates.append(_cur)
                            _cur += timedelta(days=1)

                    if not all_dates:
                        st.warning("기간 정보가 없습니다. 위에서 날짜를 먼저 설정해주세요.")
                    else:
                        _KR_DAYS = {'Mon':'월','Tue':'화','Wed':'수','Thu':'목','Fri':'금','Sat':'토','Sun':'일'}

                        # ── 날짜 체크 선택 ──
                        st.caption("📅 투입할 날짜를 선택하세요")

                        # 전체선택/해제 + 평일만/주말만 빠른 버튼
                        _sel_c1, _sel_c2, _sel_c3, _sel_c4 = st.columns(4)
                        with _sel_c1:
                            if st.button("✅ 전체 선택", key="_dd_sel_all", use_container_width=True):
                                for _di, _d in enumerate(all_dates):
                                    st.session_state[f'_dd_chk_{_di}'] = True
                                st.rerun()
                        with _sel_c2:
                            if st.button("⬜ 전체 해제", key="_dd_desel_all", use_container_width=True):
                                for _di in range(len(all_dates)):
                                    st.session_state[f'_dd_chk_{_di}'] = False
                                st.rerun()
                        with _sel_c3:
                            if st.button("📆 평일만", key="_dd_sel_weekday", use_container_width=True):
                                for _di, _d in enumerate(all_dates):
                                    st.session_state[f'_dd_chk_{_di}'] = _d.strftime('%a') not in ('Sat', 'Sun')
                                st.rerun()
                        with _sel_c4:
                            if st.button("🗓️ 주말만", key="_dd_sel_weekend", use_container_width=True):
                                for _di, _d in enumerate(all_dates):
                                    st.session_state[f'_dd_chk_{_di}'] = _d.strftime('%a') in ('Sat', 'Sun')
                                st.rerun()

                        # 체크박스 그리드 (한 줄에 최대 7개)
                        _n_per_row = 7
                        _selected_indices = []
                        for _row_start in range(0, len(all_dates), _n_per_row):
                            _chunk = all_dates[_row_start:_row_start + _n_per_row]
                            _chk_cols = st.columns(len(_chunk))
                            for _ci, _d in enumerate(_chunk):
                                _di = _row_start + _ci
                                _eng_day = _d.strftime('%a')
                                _kr_day = _KR_DAYS.get(_eng_day, _eng_day)
                                _lbl = f"{_d.strftime('%m/%d')}({_kr_day})"
                                _is_weekend = _eng_day in ('Sat', 'Sun')
                                # 기본값: 전체 선택 (초기 상태)
                                _default = st.session_state.get(f'_dd_chk_{_di}', True)
                                with _chk_cols[_ci]:
                                    _checked = st.checkbox(
                                        _lbl, value=_default, key=f'_dd_chk_{_di}',
                                        help="주말" if _is_weekend else None
                                    )
                                    if _checked:
                                        _selected_indices.append(_di)

                        _n_selected = len(_selected_indices)
                        st.caption(f"✅ {_n_selected}/{len(all_dates)}일 선택됨")

                        if _n_selected > 0:
                            # ── 이전 직군 설정 복사 ──
                            _last_daily = st.session_state.get('_last_daily_setting', None)
                            if _last_daily and st.session_state.get('_daily_copy_avail', False):
                                _ldr = _last_daily.get('role', '')
                                st.info(f"💡 마지막 설정(**{_ldr}**)의 시간이 자동 반영됩니다.")
                                if st.button("🔄 이전 설정 무시", key="ignore_last_daily"):
                                    st.session_state['_daily_copy_avail'] = False
                                    st.rerun()

                            # ── 빠른 일괄 설정 ──
                            with st.expander("⚡ 빠른 일괄 설정", expanded=False):
                                _qc1, _qc2, _qc3 = st.columns(3)
                                with _qc1:
                                    _bulk_qty = st.number_input("전체 인원 일괄", min_value=0, value=iq, step=1, key="_bulk_qty")
                                with _qc2:
                                    _bulk_bill = st.number_input("전체 청구단가 일괄", min_value=0, value=int(fb), step=5000, key="_bulk_bill")
                                with _qc3:
                                    _bulk_pay = st.number_input("전체 지급단가 일괄", min_value=0, value=int(fp), step=5000, key="_bulk_pay")
                                if st.button("✅ 일괄 적용", key="_apply_bulk", use_container_width=True):
                                    st.session_state['_daily_bulk'] = {
                                        'qty': _bulk_qty, 'bill': _bulk_bill, 'pay': _bulk_pay
                                    }
                                    st.rerun()

                            # 일괄 설정값 반영
                            _bulk = st.session_state.pop('_daily_bulk', None)

                            # 선택된 날짜만 상세 테이블 생성
                            _daily_rows = []
                            _daily_ti_str = ti.strftime('%H:%M') if time_mode == "출퇴근 지정" or (ti.hour != 0 or ti.minute != 0) else "미정"
                            _daily_to_str = to_.strftime('%H:%M') if time_mode == "출퇴근 지정" or (to_.hour != 0 or to_.minute != 0) else "미정"

                            for _di in _selected_indices:
                                _d = all_dates[_di]
                                _eng_day = _d.strftime('%a')
                                _kr_day = _KR_DAYS.get(_eng_day, _eng_day)
                                _d_str = _d.strftime('%Y-%m-%d')

                                _init_qty = iq
                                _init_bill = int(fb)
                                _init_pay = int(fp)
                                _init_ti = _daily_ti_str
                                _init_to = _daily_to_str

                                # 이전 직군 복사 적용
                                if _last_daily and st.session_state.get('_daily_copy_avail', False):
                                    _prev_dates = _last_daily.get('dates', {})
                                    if _d_str in _prev_dates:
                                        _pd = _prev_dates[_d_str]
                                        _init_ti = _pd.get('ti', _init_ti)
                                        _init_to = _pd.get('to', _init_to)

                                # 일괄 설정 적용
                                if _bulk:
                                    _init_qty = _bulk['qty']
                                    _init_bill = _bulk['bill']
                                    _init_pay = _bulk['pay']

                                _daily_rows.append({
                                    '날짜': f"{_d.strftime('%m/%d')} ({_kr_day})",
                                    '_date_raw': _d_str,
                                    '인원': _init_qty,
                                    '출근시간': _init_ti,
                                    '퇴근시간': _init_to,
                                    '청구단가': _init_bill,
                                    '지급단가': _init_pay,
                                })
                            _daily_init = pd.DataFrame(_daily_rows)

                            st.caption(f"📋 선택된 {_n_selected}일 — 인원·시간·단가를 수정하세요")
                            daily_detail_df = st.data_editor(
                                _daily_init[['날짜', '인원', '출근시간', '퇴근시간', '청구단가', '지급단가']],
                                column_config={
                                    '날짜': st.column_config.TextColumn('날짜', disabled=True, width="small"),
                                    '인원': st.column_config.NumberColumn('인원', min_value=0, step=1, width="small"),
                                    '출근시간': st.column_config.TextColumn('출근', help="HH:MM 형식", width="small"),
                                    '퇴근시간': st.column_config.TextColumn('퇴근', help="HH:MM 형식", width="small"),
                                    '청구단가': st.column_config.NumberColumn('청구단가', min_value=0, step=5000, format="%d", width="small"),
                                    '지급단가': st.column_config.NumberColumn('지급단가', min_value=0, step=5000, format="%d", width="small"),
                                },
                                use_container_width=True, hide_index=True,
                                num_rows="fixed", key="daily_detail_editor",
                            )
                            # _date_raw 컬럼 복원
                            daily_detail_df['_date_raw'] = _daily_init['_date_raw'].values

                            # 요약 표시
                            _active_days = daily_detail_df[daily_detail_df['인원'] > 0]
                            _total_pd = int(_active_days['인원'].sum()) if not _active_days.empty else 0
                            _skip_days = _n_selected - len(_active_days)
                            _sum_bill = int((_active_days['인원'] * _active_days['청구단가']).sum()) if not _active_days.empty else 0
                            _sum_cost = int((_active_days['인원'] * _active_days['지급단가']).sum()) if not _active_days.empty else 0

                            _sc1, _sc2 = st.columns(2)
                            with _sc1:
                                st.caption(f"👥 투입: **{_total_pd}명·일** ({len(_active_days)}일 투입" +
                                           (f", {_skip_days}일 0명)" if _skip_days > 0 else ")"))
                            with _sc2:
                                st.caption(f"💰 예상: 청구 **{_sum_bill:,}원** / 지급 **{_sum_cost:,}원**")

                if st.button("⬇️ 리스트에 추가", type="primary", use_container_width=True):
                    if role_kr == "선택":
                        st.warning("직군을 선택하거나 직접 입력해주세요")
                    elif use_daily_detail and daily_detail_df is not None:
                        # ── B방식: 일자별 행 생성 (단가 오버라이드 지원) ──
                        nm_base = f"{role_kr} {'[팀장]' if is_leader else ''}".strip()
                        note = ", ".join([f_map[p]['name'] for p in picks])
                        new_rows = []
                        _daily_dates_info = {}  # 이전 직군 복사용 설정 저장
                        for _, drow in daily_detail_df.iterrows():
                            d_qty = int(drow['인원'])
                            if d_qty <= 0:
                                continue  # 0명인 날 스킵
                            d_date = str(drow['_date_raw'])
                            d_date_short = str(drow['날짜'])
                            # 날짜별 단가 (오버라이드)
                            d_fb = int(drow.get('청구단가', fb)) if pd.notna(drow.get('청구단가')) else int(fb)
                            d_fp = int(drow.get('지급단가', fp)) if pd.notna(drow.get('지급단가')) else int(fp)
                            # 시간 파싱 (미정인 경우 시간기준 모드의 dur 사용)
                            _d_tin = str(drow['출근시간']).strip()
                            _d_tout = str(drow['퇴근시간']).strip()
                            if _d_tin in ('미정', '') or _d_tout in ('미정', ''):
                                d_dur = dur  # 시간기준 모드의 기본 dur
                                d_spec = f"{dur}H 기준 (시간 미정)"
                            else:
                                try:
                                    d_dur = ue.smart_parse_time(f"{_d_tin}~{_d_tout}")[2]
                                except Exception:
                                    d_dur = dur
                                d_spec = f"{_d_tin}~{_d_tout} ({d_dur}H)"
                            d_mult = d_dur if pay_type == "시급" else 1
                            d_bill = int(d_fb * d_mult * d_qty)
                            d_cost = int(d_fp * d_mult * d_qty)
                            new_rows.append({
                                "품목": f"{nm_base}\n({d_date_short})",
                                "규격": d_spec,
                                "수량": d_qty,
                                "일수": 1,
                                "매출단가": int(d_fb * d_mult),
                                "매입단가": int(d_fp * d_mult),
                                "할인액": 0,
                                "매출합계": d_bill,
                                "매입합계": d_cost,
                                "비고": note,
                            })
                            _daily_dates_info[d_date] = {'ti': _d_tin, 'to': _d_tout, 'qty': d_qty}
                        if new_rows:
                            st.session_state['est_items'] = pd.concat(
                                [st.session_state['est_items'], pd.DataFrame(new_rows)], ignore_index=True)
                            # 설정 기억 (다음 직군 추가 시 복사용)
                            st.session_state['_last_daily_setting'] = {
                                'role': role_kr, 'dates': _daily_dates_info
                            }
                            st.session_state['_daily_copy_avail'] = True
                            st.rerun()
                        else:
                            st.warning("인원이 0인 날만 있습니다. 인원을 입력해주세요.")
                    else:
                        # ── 기존 방식: 총합 1행 ──
                        qty_calc = iq * calc_days
                        mult = dur if pay_type == "시급" else 1
                        tot_bill = int(fb * mult * qty_calc)
                        tot_cost = int(fp * mult * qty_calc)
                        nm = f"{role_kr} {'[팀장]' if is_leader else ''}"
                        note = ", ".join([f_map[p]['name'] for p in picks])
                        new_row = {"품목": nm, "규격": spec_txt, "수량": iq, "일수": calc_days,
                                   "매출단가": fb, "매입단가": fp, "할인액": 0, "매출합계": tot_bill, "매입합계": tot_cost, "비고": note}
                        st.session_state['est_items'] = pd.concat(
                            [st.session_state['est_items'], pd.DataFrame([new_row])], ignore_index=True)
                        st.rerun()

            # ▶ AI 분석 가이드 (접기 가능)
            with st.expander("📊 AI 분석 가이드", expanded=True):
                analysis = brain.get_analysis(role_id)
                g_txt = "<br>".join([f"• {g}" for g in analysis['guide']]) if analysis['guide'] else "직군 선택 시 가이드 표시"
                st.markdown(f"""
                    <div class="analysis-box">
                        <b>📘 {role_kr if role_kr != '선택' else '직군'} 가이드</b><br>{g_txt}<br>
                        <hr style="margin:8px 0; border-color:#fdba74;">
                        <div style="font-size:12px; display:flex; justify-content:space-between;">
                            <span>💰 시장가: {analysis['market']}</span><span>🏢 타사: {analysis['comp']}</span>
                        </div>
                        <div style="font-size:12px; margin-top:5px; color:#c2410c;">🏆 <b>자사 체결:</b> {analysis['my_best']}</div>
                    </div>
                """, unsafe_allow_html=True)

                # AI 견적가 추천
                try:
                    import ai_helper as ai
                    num_items = len(st.session_state['est_items']) if not st.session_state['est_items'].empty else 0
                    if num_items > 0:
                        df_est_all = data.get('estimate', pd.DataFrame())
                        suggestion = ai.suggest_estimate_price(df_est_all, num_staff=num_items, num_days=1)
                        if suggestion['recommended_supply'] > 0 and suggestion['similar_count'] >= 2:
                            st.markdown(f"""
                            <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:8px;font-size:12px;">
                                🤖 <b>AI 추천가:</b> ₩{suggestion['recommended_supply']:,}
                                (과거 {suggestion['similar_count']}건, 평균 마진 {suggestion['avg_margin']}%)
                            </div>
                            """, unsafe_allow_html=True)
                except Exception:
                    pass

                # 고객별 자동 추천 단가 (AI 영역 내로 이동)
                if role_kr != "선택" and st.session_state.get('w_client'):
                    _show_auto_recommend(df_est, st.session_state['w_client'], role_kr)

            # ▶ 부대비용 & 지원품목 (통합)
            with st.container(border=True):
                st.markdown('<div class="sub-header">🛒 부대비용 & 지원품목</div>', unsafe_allow_html=True)
                if 'additional_costs' not in st.session_state:
                    st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '수량', '일수', '단가', '금액', '비고'])

                # 빠른 추가 — 부대비용
                st.caption("💰 부대비용")

                # 의뢰사제공(식비) 빠른 추가 버튼 (1식 / 2식)
                _meal_c1, _meal_c2 = st.columns(2)
                with _meal_c1:
                    if st.button("🍽️ 식비 의뢰사제공 (1식)", key="tpl_client_meal_1", use_container_width=True,
                                 help="1인 1식 의뢰사 제공. 미제공 시 1식당 1만원 추가청구"):
                        st.session_state['additional_costs'] = pd.concat([
                            st.session_state['additional_costs'],
                            pd.DataFrame([{"항목": "식비", "수량": st.session_state.get('w_qty', 1),
                                           "일수": max(1, calc_days), "단가": 0, "금액": 0,
                                           "비고": "의뢰사제공|1인 1식|미제공시 1식당 1만원 추가청구"}])
                        ], ignore_index=True)
                        st.rerun()
                with _meal_c2:
                    if st.button("🍽️ 식비 의뢰사제공 (2식)", key="tpl_client_meal_2", use_container_width=True,
                                 help="1인 2식 의뢰사 제공. 미제공 시 1식당 1만원 추가청구"):
                        st.session_state['additional_costs'] = pd.concat([
                            st.session_state['additional_costs'],
                            pd.DataFrame([{"항목": "식비", "수량": st.session_state.get('w_qty', 1),
                                           "일수": max(1, calc_days), "단가": 0, "금액": 0,
                                           "비고": "의뢰사제공|1인 2식|미제공시 1식당 1만원 추가청구"}])
                        ], ignore_index=True)
                        st.rerun()

                # 입력란: 항목 / 수량 / 일수 / 단가 / 추가 버튼
                _sel_idx = st.session_state.pop('_cost_sel_idx', 0)
                _price_def = st.session_state.pop('_cost_price_default', 0)
                _qty_def = st.session_state.pop('_cost_qty_default', 1)
                _days_def = st.session_state.pop('_cost_days_default', max(1, calc_days))
                cc1, cc2, cc3, cc4, cc5 = st.columns([1.4, 0.5, 0.5, 0.8, 0.4])
                with cc1:
                    cost_item = st.selectbox("항목", ["식비","숙박비","교통비","용역료","장비","기타"], index=_sel_idx, label_visibility="collapsed", key="cost_item_select")
                with cc2:
                    cost_qty = st.number_input("수량", min_value=1, value=_qty_def, label_visibility="collapsed", key="cost_qty_input")
                with cc3:
                    cost_days = st.number_input("일수", min_value=1, value=_days_def, label_visibility="collapsed", key="cost_days_input")
                with cc4:
                    cost_unit = st.number_input("단가", min_value=0, step=1000, value=_price_def, label_visibility="collapsed", key="cost_unit_input")
                with cc5:
                    if st.button("➕", key="add_cost_btn", use_container_width=True):
                        cost_amt = cost_qty * cost_days * cost_unit
                        if cost_amt > 0:
                            st.session_state['additional_costs'] = pd.concat([
                                st.session_state['additional_costs'],
                                pd.DataFrame([{"항목": cost_item, "수량": cost_qty, "일수": cost_days, "단가": cost_unit, "금액": cost_amt, "비고": ""}])
                            ], ignore_index=True)
                            st.rerun()
                        else:
                            st.warning("수량·일수·단가를 입력하세요")
                # 입력란 라벨 안내
                st.markdown('<div style="display:flex;gap:4px;font-size:10px;color:#999;margin-top:-8px;"><span style="flex:1.4">항목</span><span style="flex:0.5">수량</span><span style="flex:0.5">일수</span><span style="flex:0.8">단가</span><span style="flex:0.4"></span></div>', unsafe_allow_html=True)

                # 빠른 추가 — 지원품목 (본사 무료 제공)
                st.divider()
                st.caption("📦 지원품목 (본사 무료 제공 → 견적서 표시, 금액 0원)")
                _sup_templates = [
                    ("📻 무전기", "무전기"), ("🦺 안전조끼", "안전조끼"),
                    ("🚨 경광봉", "경광봉"), ("📷 바디캠", "바디캠"), ("✏️ 직접입력", ""),
                ]
                _sup_cols = st.columns(len(_sup_templates))
                for _si, (_slbl, _sname) in enumerate(_sup_templates):
                    with _sup_cols[_si]:
                        if _sname:
                            if st.button(_slbl, key=f"sup_tpl_{_si}", use_container_width=True):
                                st.session_state['est_items'] = pd.concat([
                                    st.session_state['est_items'],
                                    pd.DataFrame([{"품목": f"[지원] {_sname}", "규격": "본사 제공", "수량": iq,
                                                   "일수": calc_days, "매출단가": 0, "매입단가": 0,
                                                   "매출합계": 0, "매입합계": 0, "비고": "무료 지원"}])
                                ], ignore_index=True)
                                st.rerun()
                # 지원품목 직접 입력
                with st.expander("✏️ 지원품목 직접 입력", expanded=False):
                    _sc1, _sc2, _sc3 = st.columns([2, 1, 1])
                    with _sc1:
                        _sup_name = st.text_input("품목명", placeholder="예: 확성기, 텐트", key="sup_custom_name")
                    with _sc2:
                        _sup_qty = st.number_input("수량", min_value=1, value=1, key="sup_custom_qty")
                    with _sc3:
                        _sup_days = st.number_input("일수", min_value=1, value=max(1, calc_days), key="sup_custom_days")
                    if st.button("⬇️ 지원품목 추가", key="add_support_item", use_container_width=True):
                        if _sup_name.strip():
                            st.session_state['est_items'] = pd.concat([
                                st.session_state['est_items'],
                                pd.DataFrame([{"품목": f"[지원] {_sup_name.strip()}", "규격": "본사 제공",
                                               "수량": _sup_qty, "일수": _sup_days,
                                               "매출단가": 0, "매입단가": 0,
                                               "매출합계": 0, "매입합계": 0, "비고": "무료 지원"}])
                            ], ignore_index=True)
                            st.rerun()
                        else:
                            st.warning("품목명을 입력해주세요")

        # ────────────────────────────────────
        # 우측: 합계 → 품목리스트 → 단가조정 → 부대비용리스트
        # ────────────────────────────────────
        with col_result:
            # ▶ 합계 요약 박스 (항상 최상단)
            supply_sum = int(st.session_state['est_items']['매출합계'].sum()) if not st.session_state['est_items'].empty else 0
            cost_sum = int(st.session_state['est_items']['매입합계'].sum()) if not st.session_state['est_items'].empty else 0
            total_additional = int(st.session_state['additional_costs']['금액'].sum()) if not st.session_state.get('additional_costs', pd.DataFrame()).empty and '금액' in st.session_state.get('additional_costs', pd.DataFrame()).columns else 0
            vat_val = int((supply_sum + total_additional) * 0.1)
            profit_val = supply_sum - cost_sum
            margin_pct = (profit_val / supply_sum * 100) if supply_sum > 0 else 0

            st.markdown(f"""
                <div class="result-box">
                    <div style="display:flex; justify-content:space-between; font-size:13px; color:#666;">
                        <span>공급가액: {supply_sum:,}원</span>
                        <span>지출금액: {cost_sum:,}원</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:13px; color:#c2410c; margin-top:2px;">
                        <span>부대비용: {total_additional:,}원</span>
                        <span>부가세(10%): {vat_val:,}원 <span style="font-size:11px;color:#999;">(공급가+부대비용)</span></span>
                    </div>
                    <hr style="margin:8px 0;">
                    <div style="display:flex; justify-content:space-between; font-size:14px; color:#064e3b; margin-bottom:5px;">
                        <span>인력 수익: <b>{profit_val:,}원 ({margin_pct:.1f}%)</b></span>
                        <span style="font-size:11px;color:#888;">부대비용은 실비 정산</span>
                    </div>
                    <div style="font-size:24px;font-weight:900;color:#064e3b;">
                        합계 {supply_sum + total_additional + vat_val:,}원
                        <span style="font-size:13px;color:#666;">(VAT {vat_val:,}원 포함)</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # ▶ 📅 일정 요약 카드 (날짜별 투입 현황)
            if not st.session_state['est_items'].empty:
                _items_df = st.session_state['est_items']
                # 날짜별 행 감지: 품목명에 (MM/DD 형식이 포함된 행들
                import re as _re_sched
                _date_items = []
                _normal_items = []
                for _si, _sr in _items_df.iterrows():
                    _sn = str(_sr.get('품목', ''))
                    _dm = _re_sched.search(r'\((\d{2}/\d{2})', _sn)
                    if _dm:
                        _date_items.append((_dm.group(1), _sn, _sr))
                    elif not _sn.startswith('[지원]'):
                        _normal_items.append(_sr)

                if _date_items:
                    # 날짜별 그룹핑
                    _date_groups = {}
                    for _dt_str, _name, _row in _date_items:
                        if _dt_str not in _date_groups:
                            _date_groups[_dt_str] = []
                        # 직군명 추출 (날짜 부분 제거)
                        _role_clean = _re_sched.sub(r'\n?\(.*\)$', '', _name).strip()
                        _date_groups[_dt_str].append({
                            'role': _role_clean,
                            'qty': int(_row.get('수량', 0)),
                            'spec': str(_row.get('규격', '')),
                            'bill': int(_row.get('매출합계', 0)),
                            'cost': int(_row.get('매입합계', 0)),
                        })

                    with st.expander(f"📅 날짜별 투입 현황 ({len(_date_groups)}일)", expanded=False):
                        _sorted_dates = sorted(_date_groups.keys())
                        _n_cols = min(len(_sorted_dates), 4)
                        for _chunk_start in range(0, len(_sorted_dates), _n_cols):
                            _chunk = _sorted_dates[_chunk_start:_chunk_start + _n_cols]
                            _cols = st.columns(len(_chunk))
                            for _ci, _dt_key in enumerate(_chunk):
                                _roles_in_day = _date_groups[_dt_key]
                                _day_total_qty = sum(r['qty'] for r in _roles_in_day)
                                _day_total_bill = sum(r['bill'] for r in _roles_in_day)
                                _roles_txt = "".join([
                                    f"<div style='font-size:11px;'>{r['role']} {r['qty']}명 <span style='color:#888;'>{r['spec'][:15]}</span></div>"
                                    for r in _roles_in_day
                                ])
                                with _cols[_ci]:
                                    st.markdown(f"""
                                    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px;margin-bottom:4px;">
                                        <div style="font-weight:700;font-size:13px;color:#1e3a8a;border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin-bottom:4px;">
                                            📅 {_dt_key} · {_day_total_qty}명
                                        </div>
                                        {_roles_txt}
                                        <div style="font-size:10px;color:#059669;margin-top:4px;">₩{_day_total_bill:,}</div>
                                    </div>
                                    """, unsafe_allow_html=True)

            # ▶ 견적 품목 리스트
            st.markdown('<div class="sub-header">📦 견적 품목 리스트</div>', unsafe_allow_html=True)
            st.caption("💡 수량·일수·단가·합계 모두 직접 수정 가능합니다. 할인액: 품목별 할인 금액(원) 입력 시 청구합계에서 차감됩니다.")
            # 할인액 컬럼 호환 (기존 '할인율' → '할인액' 마이그레이션)
            if '할인율' in st.session_state['est_items'].columns and '할인액' not in st.session_state['est_items'].columns:
                st.session_state['est_items'] = st.session_state['est_items'].rename(columns={'할인율': '할인액'})
            if '할인액' not in st.session_state['est_items'].columns:
                _idx = st.session_state['est_items'].columns.tolist().index('매출합계') if '매출합계' in st.session_state['est_items'].columns else len(st.session_state['est_items'].columns)
                st.session_state['est_items'].insert(_idx, '할인액', 0)
            # ── 텍스트 컬럼 NaN 정리 (data_editor 텍스트 편집 안정화) ──
            _ed_src = st.session_state['est_items'].copy()
            for _sc in ['품목', '규격', '비고']:
                if _sc in _ed_src.columns:
                    _ed_src[_sc] = _ed_src[_sc].fillna('').astype(str).replace('nan', '')
            edited_items = st.data_editor(
                _ed_src, use_container_width=True, hide_index=True,
                num_rows="dynamic", key=f"est_items_editor_{_g}",
                disabled=["매출합계", "매입합계"],
                column_config={
                    "품목": st.column_config.TextColumn("품목"),
                    "규격": st.column_config.TextColumn("규격/상세"),
                    "수량": st.column_config.NumberColumn("수량", min_value=0, step=1, format="%d"),
                    "일수": st.column_config.NumberColumn("일수", min_value=0, step=1, format="%d"),
                    "매출단가": st.column_config.NumberColumn("청구단가", min_value=0, step=5000, format="%d"),
                    "매입단가": st.column_config.NumberColumn("지급단가", min_value=0, step=5000, format="%d"),
                    "할인액": st.column_config.NumberColumn("할인액(원)", min_value=0, step=10000, format="%d", help="품목별 할인 금액. 예: 10000 = 1만원 할인"),
                    "매출합계": st.column_config.NumberColumn("청구합계", format="%d"),
                    "매입합계": st.column_config.NumberColumn("지출합계", format="%d"),
                    "비고": st.column_config.TextColumn("비고"),
                })
            # 편집 결과를 세션에 반영 (수식 기반 재계산 — 변경 시에만 업데이트)
            if not edited_items.empty:
                _recalc = edited_items.copy()
                if '할인액' not in _recalc.columns:
                    _recalc['할인액'] = 0
                _needs_rerun = False
                for _ci in _recalc.index:
                    _q = int(_recalc.loc[_ci, '수량']) if pd.notna(_recalc.loc[_ci, '수량']) else 0
                    _d = int(_recalc.loc[_ci, '일수']) if pd.notna(_recalc.loc[_ci, '일수']) else 1
                    _up = int(_recalc.loc[_ci, '매출단가']) if pd.notna(_recalc.loc[_ci, '매출단가']) else 0
                    _uc = int(_recalc.loc[_ci, '매입단가']) if pd.notna(_recalc.loc[_ci, '매입단가']) else 0
                    _disc_amt = _safe_int(_recalc.loc[_ci, '할인액']) if pd.notna(_recalc.loc[_ci, '할인액']) else 0
                    _discounted_up = max(0, _up - _disc_amt)
                    _new_sale = _q * _d * _discounted_up
                    _new_cost = _q * _d * _uc
                    _old_sale = _safe_int(_recalc.loc[_ci, '매출합계'])
                    _old_cost = _safe_int(_recalc.loc[_ci, '매입합계'])
                    if _new_sale != _old_sale:
                        _recalc.loc[_ci, '매출합계'] = _new_sale
                        _needs_rerun = True
                    if _new_cost != _old_cost:
                        _recalc.loc[_ci, '매입합계'] = _new_cost
                        _needs_rerun = True
                # 텍스트 컬럼 NaN → '' 정리
                for _sc in ['품목', '규격', '비고']:
                    if _sc in _recalc.columns:
                        _recalc[_sc] = _recalc[_sc].fillna('').astype(str).replace('nan', '')
                if _needs_rerun:
                    # 수치 변경 시에만 세션 업데이트 + rerun
                    st.session_state['est_items'] = _recalc
                    st.rerun()

            # 삭제 & 행 이동 버튼
            if not st.session_state['est_items'].empty:
                n_items = len(st.session_state['est_items'])
                # 삭제 버튼
                del_cols = st.columns(min(n_items, 10) + 1)
                for idx in range(min(n_items, 10)):
                    r = st.session_state['est_items'].iloc[idx]
                    with del_cols[idx]:
                        if st.button(f"🗑️{idx+1}", key=f"del_item_{idx}", help=f"{r['품목']} 삭제"):
                            st.session_state['est_items'] = st.session_state['est_items'].drop(idx).reset_index(drop=True)
                            st.rerun()
                with del_cols[-1]:
                    if st.button("🗑️전체", key="del_all_items"):
                        st.session_state['est_items'] = pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','할인액','매출합계','매입합계','비고'])
                        st.rerun()

                # 행 순서 이동
                if n_items >= 2:
                    with st.expander("🔀 행 순서 변경", expanded=False):
                        _mv_labels = [f"{i+1}. {str(st.session_state['est_items'].iloc[i]['품목'])[:20]}" for i in range(n_items)]
                        _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns([2.5, 1, 1, 1, 1])
                        with _mc1:
                            _mv_idx = st.selectbox("이동할 품목", range(n_items), format_func=lambda i: _mv_labels[i], key="mv_item_sel")
                        with _mc2:
                            st.write("")
                            if st.button("🔝 맨위", key="mv_top", use_container_width=True):
                                if _mv_idx > 0:
                                    _df = st.session_state['est_items']
                                    _row = _df.iloc[[_mv_idx]]
                                    _rest = _df.drop(_mv_idx)
                                    st.session_state['est_items'] = pd.concat([_row, _rest], ignore_index=True)
                                    st.session_state['_tab2_gen'] = _g + 1
                                    st.rerun()
                        with _mc3:
                            st.write("")
                            if st.button("⬆️ 위로", key="mv_up", use_container_width=True):
                                if _mv_idx > 0:
                                    _df = st.session_state['est_items'].copy()
                                    _df.iloc[_mv_idx], _df.iloc[_mv_idx - 1] = _df.iloc[_mv_idx - 1].copy(), _df.iloc[_mv_idx].copy()
                                    st.session_state['est_items'] = _df.reset_index(drop=True)
                                    st.session_state['_tab2_gen'] = _g + 1
                                    st.rerun()
                        with _mc4:
                            st.write("")
                            if st.button("⬇️ 아래", key="mv_down", use_container_width=True):
                                if _mv_idx < n_items - 1:
                                    _df = st.session_state['est_items'].copy()
                                    _df.iloc[_mv_idx], _df.iloc[_mv_idx + 1] = _df.iloc[_mv_idx + 1].copy(), _df.iloc[_mv_idx].copy()
                                    st.session_state['est_items'] = _df.reset_index(drop=True)
                                    st.session_state['_tab2_gen'] = _g + 1
                                    st.rerun()
                        with _mc5:
                            st.write("")
                            if st.button("🔚 맨끝", key="mv_bottom", use_container_width=True):
                                if _mv_idx < n_items - 1:
                                    _df = st.session_state['est_items']
                                    _row = _df.iloc[[_mv_idx]]
                                    _rest = _df.drop(_mv_idx)
                                    st.session_state['est_items'] = pd.concat([_rest, _row], ignore_index=True)
                                    st.session_state['_tab2_gen'] = _g + 1
                                    st.rerun()

            # ▶ 단가 일괄 조정
            with st.expander("⚡ 단가 일괄 조정", expanded=False):
                adj1, adj2, adj3 = st.columns([1, 1, 1])
                with adj1:
                    adj_target = st.selectbox("대상", ["청구단가", "지급단가", "양쪽 모두"], key="adj_target")
                with adj2:
                    adj_mode = st.selectbox("방식", ["% 증감", "원 증감"], key="adj_mode")
                with adj3:
                    adj_val = st.number_input("값", value=0, step=5 if adj_mode == "% 증감" else 5000,
                                              key="adj_val", help="예: +10(10%인상), -5000(5천원 할인)")

                if st.button("🔄 일괄 적용", key="apply_adj", use_container_width=True):
                    if not st.session_state['est_items'].empty and adj_val != 0:
                        df_adj = st.session_state['est_items'].copy()
                        targets = []
                        if adj_target in ["청구단가", "양쪽 모두"]:
                            targets.append(('매출단가', '매출합계'))
                        if adj_target in ["지급단가", "양쪽 모두"]:
                            targets.append(('매입단가', '매입합계'))
                        for ucol, tcol in targets:
                            if adj_mode == "% 증감":
                                df_adj[ucol] = (df_adj[ucol] * (1 + adj_val / 100)).astype(int)
                            else:
                                df_adj[ucol] = (df_adj[ucol] + adj_val).astype(int)
                            df_adj[tcol] = (df_adj[ucol] * df_adj['수량'] * df_adj['일수']).astype(int)
                        st.session_state['est_items'] = df_adj
                        st.success(f"✅ {adj_target} {adj_val}{'%' if adj_mode == '% 증감' else '원'} 적용 완료!")
                        st.rerun()

            # ▶ 부대비용 리스트
            if not st.session_state['additional_costs'].empty:
                st.markdown('<div class="sub-header">🛒 부대비용 내역</div>', unsafe_allow_html=True)
                edited_costs = st.data_editor(
                    st.session_state['additional_costs'], use_container_width=True, hide_index=True,
                    num_rows="dynamic", key=f"additional_costs_editor_{_g}",
                    column_config={
                        "수량": st.column_config.NumberColumn("수량", format="%d", width="small"),
                        "일수": st.column_config.NumberColumn("일수", format="%d", width="small"),
                        "단가": st.column_config.NumberColumn("단가", format="%d"),
                        "금액": st.column_config.NumberColumn("금액", format="%d"),
                    }
                )
                # 금액 재계산 (수량 x 일수 x 단가)
                if '수량' in edited_costs.columns and '일수' in edited_costs.columns and '단가' in edited_costs.columns:
                    edited_costs['금액'] = (edited_costs['수량'].fillna(1) * edited_costs['일수'].fillna(1) * edited_costs['단가'].fillna(0)).astype(int)
                st.session_state['additional_costs'] = edited_costs
                total_additional = int(edited_costs['금액'].sum())
                dc1, dc2 = st.columns([3, 1])
                with dc1:
                    st.caption(f"💰 부대비용 합계: {total_additional:,}원")
                with dc2:
                    if st.button("🗑️ 초기화", key="del_all_costs"):
                        st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '수량', '일수', '단가', '금액', '비고'])
                        st.rerun()

    # ==================================================================
    # TAB 2: 견적서 발행
    # ==================================================================
    if _active_est == _est_tabs[1]:
        col_edit, col_view = st.columns([1, 2.2])
        with col_edit:
            st.markdown("### ✏️ 편집")
            with st.container(border=True):
                st.caption("📌 수신자 정보")
                # 항상 w_*에서 안전하게 읽어서 초기화 (세대 키 기반)
                _ck_client = f"final_client_{_g}"
                _ck_manager = f"final_manager_{_g}"
                _ck_contact = f"final_contact_{_g}"
                _ck_loc = f"final_loc_{_g}"
                if _ck_client not in st.session_state:
                    st.session_state[_ck_client] = _safe_str(st.session_state.get('w_client'))
                if _ck_manager not in st.session_state:
                    st.session_state[_ck_manager] = _safe_str(st.session_state.get('w_manager'))
                if _ck_contact not in st.session_state:
                    st.session_state[_ck_contact] = _safe_str(st.session_state.get('w_contact'))
                if _ck_loc not in st.session_state:
                    st.session_state[_ck_loc] = _safe_str(st.session_state.get('w_loc'))
                f_client = st.text_input("상호", key=_ck_client)
                c_1, c_2 = st.columns(2)
                f_ref = c_1.text_input("참조 (담당자)", key=_ck_manager)
                f_tel = c_2.text_input("연락처", key=_ck_contact)
                f_addr = st.text_input("주소 (현장)", key=_ck_loc)

            st.caption("📋 리스트 수정")
            # 할인액 컬럼 호환
            if '할인율' in st.session_state['est_items'].columns and '할인액' not in st.session_state['est_items'].columns:
                st.session_state['est_items'] = st.session_state['est_items'].rename(columns={'할인율': '할인액'})
            if '할인액' not in st.session_state['est_items'].columns:
                st.session_state['est_items']['할인액'] = 0
            # ── 텍스트 컬럼 NaN 정리 (data_editor 텍스트 편집 안정화) ──
            _t2_src = st.session_state['est_items'].copy()
            for _sc in ['품목', '규격', '비고']:
                if _sc in _t2_src.columns:
                    _t2_src[_sc] = _t2_src[_sc].fillna('').astype(str).replace('nan', '')
            edited_df = st.data_editor(
                _t2_src, width='stretch', num_rows="dynamic",
                disabled=["매출합계", "매입합계"],
                column_config={
                    "품목": st.column_config.TextColumn("품목", width="medium"),
                    "규격": st.column_config.TextColumn("규격/상세", width="medium"),
                    "수량": st.column_config.NumberColumn("수량", min_value=0, step=1, format="%d"),
                    "일수": st.column_config.NumberColumn("일수", min_value=0, step=1, format="%d"),
                    "매출단가": st.column_config.NumberColumn("단가", min_value=0, step=5000, format="%d"),
                    "할인액": st.column_config.NumberColumn("할인액", min_value=0, step=10000, format="%d"),
                    "매출합계": st.column_config.NumberColumn("금액", format="%d"),
                    "비고": st.column_config.TextColumn("비고", width="medium"),
                },
                hide_index=True, key=f"final_edit_table_{_g}"
            )

            # ── TAB2 편집 결과도 수식 기반 재계산 (변경 시에만 업데이트) ──
            if not edited_df.empty:
                _t2_recalc = edited_df.copy()
                if '할인액' not in _t2_recalc.columns:
                    _t2_recalc['할인액'] = 0
                _t2_needs_rerun = False
                for _ci in _t2_recalc.index:
                    _q = int(_t2_recalc.loc[_ci, '수량']) if pd.notna(_t2_recalc.loc[_ci, '수량']) else 0
                    _d = int(_t2_recalc.loc[_ci, '일수']) if pd.notna(_t2_recalc.loc[_ci, '일수']) else 1
                    _up = int(_t2_recalc.loc[_ci, '매출단가']) if pd.notna(_t2_recalc.loc[_ci, '매출단가']) else 0
                    _uc = int(_t2_recalc.loc[_ci, '매입단가']) if pd.notna(_t2_recalc.loc[_ci, '매입단가']) else 0
                    _disc_amt = _safe_int(_t2_recalc.loc[_ci, '할인액']) if pd.notna(_t2_recalc.loc[_ci, '할인액']) else 0
                    _discounted_up = max(0, _up - _disc_amt)
                    _new_sale = _q * _d * _discounted_up
                    _new_cost = _q * _d * _uc
                    _old_sale = _safe_int(_t2_recalc.loc[_ci, '매출합계'])
                    _old_cost = _safe_int(_t2_recalc.loc[_ci, '매입합계'])
                    if _new_sale != _old_sale:
                        _t2_recalc.loc[_ci, '매출합계'] = _new_sale
                        _t2_needs_rerun = True
                    if _new_cost != _old_cost:
                        _t2_recalc.loc[_ci, '매입합계'] = _new_cost
                        _t2_needs_rerun = True
                # 텍스트 컬럼 NaN → '' 정리
                for _sc in ['품목', '규격', '비고']:
                    if _sc in _t2_recalc.columns:
                        _t2_recalc[_sc] = _t2_recalc[_sc].fillna('').astype(str).replace('nan', '')
                edited_df = _t2_recalc
                if _t2_needs_rerun:
                    # 수치 변경 시에만 세션 업데이트 + rerun
                    st.session_state['est_items'] = _t2_recalc
                    st.rerun()

            # 빈 행 삭제 & 행 이동 버튼
            _empty_mask = edited_df['품목'].fillna('').astype(str).str.strip() == ''
            _empty_count = _empty_mask.sum()
            _t2_n = len(edited_df) - _empty_count
            _t2_btns = st.columns([1, 1, 1] if _empty_count > 0 else [1, 1])
            with _t2_btns[0]:
                if _t2_n >= 2:
                    if st.button("🔀 행 순서 변경", key="t2_toggle_move", use_container_width=True):
                        st.session_state['_t2_show_move'] = not st.session_state.get('_t2_show_move', False)
                        st.rerun()
            with _t2_btns[1]:
                if _empty_count > 0:
                    if st.button(f"🗑️ 빈 행 삭제 ({_empty_count}개)", key="remove_empty_rows", use_container_width=True):
                        st.session_state['est_items'] = edited_df[~_empty_mask].reset_index(drop=True)
                        st.session_state['_tab2_gen'] = _g + 1
                        st.rerun()

            # 행 순서 변경 UI
            if st.session_state.get('_t2_show_move', False) and _t2_n >= 2:
                _t2_items_only = st.session_state['est_items'][~_empty_mask].reset_index(drop=True) if _empty_count > 0 else st.session_state['est_items']
                _t2_n_real = len(_t2_items_only)
                _t2_mv_labels = [f"{i+1}. {str(_t2_items_only.iloc[i]['품목'])[:20]}" for i in range(_t2_n_real)]
                _tc1, _tc2, _tc3, _tc4, _tc5 = st.columns([2.5, 1, 1, 1, 1])
                with _tc1:
                    _t2_mv_idx = st.selectbox("이동할 품목", range(_t2_n_real), format_func=lambda i: _t2_mv_labels[i], key="t2_mv_sel")
                with _tc2:
                    st.write("")
                    if st.button("🔝 맨위", key="t2_mv_top", use_container_width=True):
                        if _t2_mv_idx > 0:
                            _df = st.session_state['est_items']
                            _row = _df.iloc[[_t2_mv_idx]]
                            _rest = _df.drop(_t2_mv_idx)
                            st.session_state['est_items'] = pd.concat([_row, _rest], ignore_index=True)
                            st.session_state['_tab2_gen'] = _g + 1
                            st.rerun()
                with _tc3:
                    st.write("")
                    if st.button("⬆️ 위로", key="t2_mv_up", use_container_width=True):
                        if _t2_mv_idx > 0:
                            _df = st.session_state['est_items'].copy()
                            _df.iloc[_t2_mv_idx], _df.iloc[_t2_mv_idx - 1] = _df.iloc[_t2_mv_idx - 1].copy(), _df.iloc[_t2_mv_idx].copy()
                            st.session_state['est_items'] = _df.reset_index(drop=True)
                            st.session_state['_tab2_gen'] = _g + 1
                            st.rerun()
                with _tc4:
                    st.write("")
                    if st.button("⬇️ 아래", key="t2_mv_down", use_container_width=True):
                        if _t2_mv_idx < _t2_n_real - 1:
                            _df = st.session_state['est_items'].copy()
                            _df.iloc[_t2_mv_idx], _df.iloc[_t2_mv_idx + 1] = _df.iloc[_t2_mv_idx + 1].copy(), _df.iloc[_t2_mv_idx].copy()
                            st.session_state['est_items'] = _df.reset_index(drop=True)
                            st.session_state['_tab2_gen'] = _g + 1
                            st.rerun()
                with _tc5:
                    st.write("")
                    if st.button("🔚 맨끝", key="t2_mv_bottom", use_container_width=True):
                        if _t2_mv_idx < _t2_n_real - 1:
                            _df = st.session_state['est_items']
                            _row = _df.iloc[[_t2_mv_idx]]
                            _rest = _df.drop(_t2_mv_idx)
                            st.session_state['est_items'] = pd.concat([_rest, _row], ignore_index=True)
                            st.session_state['_tab2_gen'] = _g + 1
                            st.rerun()

            t_top = st.text_area("상단 약관", value=st.session_state['w_terms_top'], height=120)
            t_side = st.text_area("측면 약관", value=st.session_state['w_terms_side'], height=120)

            st.markdown('<div class="action-bar"></div>', unsafe_allow_html=True)
            b1, b2, b3 = st.columns([0.8, 1.2, 1])
            with b1:
                vat_yn = st.checkbox("VAT 포함", value=True)
                discount_amt = st.number_input("💸 할인금액", min_value=0, step=10000, value=0, key="discount_amt", help="견적 총액에서 차감할 할인 금액")
            with b2:
                banner_b64 = load_local_banner()
                if not banner_b64:
                    uploaded_file = st.file_uploader("배너", type=['png', 'jpg'], label_visibility="collapsed")
                    if uploaded_file:
                        banner_b64 = image_to_base64(uploaded_file)

            with b3:
                if st.button("💾 견적 저장", type="primary", use_container_width=True):
                    if sel_p == "(신규작성)" or all_pending.empty:
                        st.warning("⚠️ 프로젝트를 먼저 선택하세요.")
                    else:
                        try:
                            _save_matched = all_pending[all_pending['label'] == sel_p]
                            if _save_matched.empty:
                                st.error("⚠️ 선택한 프로젝트를 찾을 수 없습니다. 프로젝트를 다시 선택해주세요.")
                                st.stop()
                            target_row = _save_matched.iloc[0]
                            target_id = str(target_row.get('문의ID', ''))

                            s_amt = int(edited_df['매출합계'].sum()) if not edited_df.empty else 0
                            c_amt = int(edited_df['매입합계'].sum()) if not edited_df.empty else 0
                            _add_costs_df = st.session_state.get('additional_costs', pd.DataFrame())
                            add_total = int(_add_costs_df['금액'].sum()) if not _add_costs_df.empty and '금액' in _add_costs_df.columns else 0
                            total_supply = s_amt + add_total
                            v_amt = int(total_supply * 0.1) if vat_yn else 0

                            final_save_name = f_client if f_client else st.session_state.get('w_client', target_row.get('업체명', ''))

                            metadata = {
                                "현장명": st.session_state.get('w_event', ''),
                                "책임자": f_ref or target_row.get('담당자', ''),
                                "현장주소": f_addr or target_row.get('장소', ''),
                                "사업자번호": "", "대표자": "",
                                "담당자": f_ref or target_row.get('담당자', ''),
                                "연락처": f_tel or target_row.get('연락처', ''),
                                "복장": st.session_state.get('w_dress', ''),
                                "식사": st.session_state.get('w_meal', ''),
                                "주차": st.session_state.get('w_parking', ''),
                                "특이사항": st.session_state.get('w_note', ''),
                            }

                            est_package = {
                                "문의ID": target_id, "업체명": final_save_name,
                                "행사명": st.session_state.get('w_event', ''),
                                "공급가액": total_supply, "부가세": v_amt,
                                "합계금액": total_supply + v_amt,
                                "매입원가": c_amt, "부대비용": add_total
                            }

                            with st.spinner("🚀 저장 중..."):
                                if db.save_estimate_details(est_package, metadata=metadata):
                                    if not edited_df.empty:
                                        db.save_estimate_items(target_id, edited_df)
                                    if sel_p.startswith("[접수]"):
                                        db.update_status(target_id, sc.STATUS_FLOW[1])

                                    # ▶ 저장 후 값 보존 (위젯 키 직접 수정 금지!)
                                    st.session_state['_est_saved'] = True
                                    # w_client 등은 text_input 위젯에 바인딩되어 있으므로
                                    # 직접 수정하면 오류 발생. 위젯 값은 자동 유지됨.
                                    st.balloons()
                                    st.success(f"✅ {final_save_name} 견적 저장 완료!")
                                    db.invalidate_data()
                                else:
                                    st.error("❌ 시트 저장 실패.")
                        except Exception as e:
                            st.error(f"⚠️ 시스템 오류: {e}")

        with col_view:
            st.markdown("### 📄 미리보기 (Preview)")
            # 빈 행 필터링 (미리보기에도 적용)
            _preview_df = edited_df.copy()
            _preview_mask = _preview_df['품목'].fillna('').astype(str).str.strip() != ''
            _preview_df = _preview_df[_preview_mask].reset_index(drop=True)
            final_supply = _preview_df['매출합계'].sum() if not _preview_df.empty else 0
            # 다중 기간이면 / 구분자로 표시
            _periods = st.session_state.get('w_date_periods', [])
            if _periods:
                date_range_txt = " / ".join([f"{p[0]} ~ {p[1]}" for p in _periods if p[0] and p[1]])
            else:
                date_range_txt = "날짜 미설정"

            additional_costs_df = st.session_state.get('additional_costs', pd.DataFrame())
            if not additional_costs_df.empty:
                st.markdown("#### 🛒 부대비용 상세")
                st.dataframe(additional_costs_df, use_container_width=True, hide_index=True)
                total_additional_v = int(additional_costs_df['금액'].sum())
                st.metric("부대비용 합계", f"{total_additional_v:,}원")
            else:
                total_additional_v = 0

            client_dict = {
                "name": f_client if f_client else _safe_str(st.session_state.get('w_client')),
                "ref": f_ref if f_ref else _safe_str(st.session_state.get('w_manager')),
                "tel": f_tel if f_tel else _safe_str(st.session_state.get('w_contact')),
                "addr": f_addr if f_addr else _safe_str(st.session_state.get('w_loc')),
                "date_range": date_range_txt, "date": datetime.now().strftime("%Y-%m-%d")
            }
            supplier_dict = {"reg_no": "429-88-01469", "name": "(주)가디어스", "ceo": "최규성", "tel": "1600-2944", "addr": "서울시 종로구 동망산1길 2, 1층"}
            html_quote = ue.get_customer_quote_html(_preview_df, client_dict, supplier_dict, final_supply, vat_yn, t_top, t_side, banner_b64, additional_costs_df, total_additional_v, discount_amt)
            st.components.v1.html(html_quote, height=950, scrolling=True)

            # ── 디버그 (값 추적) ──
            with st.expander("🔧 값 디버그 (문제 발생 시 펼쳐서 확인)", expanded=False):
                st.json({
                    "_tab2_gen": _g,
                    "w_client": repr(st.session_state.get('w_client')),
                    "w_manager": repr(st.session_state.get('w_manager')),
                    "w_contact": repr(st.session_state.get('w_contact')),
                    "w_loc": repr(st.session_state.get('w_loc')),
                    "w_date_periods_len": len(st.session_state.get('w_date_periods', [])),
                    "last_project": repr(st.session_state.get('last_project')),
                    "_current_inq_id": repr(st.session_state.get('_current_inq_id')),
                    "f_client_key": _ck_client,
                    "f_client_val": repr(f_client),
                    "f_ref_val": repr(f_ref),
                    "f_tel_val": repr(f_tel),
                    "f_addr_val": repr(f_addr),
                    "preview_name": repr(client_dict.get('name')),
                    "preview_ref": repr(client_dict.get('ref')),
                })

    # ==================================================================
    # TAB 3: 히스토리 & 리포트 (통합)
    # ==================================================================
    if _active_est == _est_tabs[2]:
        # ── 📬 견적서 발송 현황 (최상단) ──
        _show_send_status_section(df_est, df_inq)

        st.markdown("---")

        _show_history_tab(df_est, df_inq, st.session_state.get('w_client', ''))

        st.markdown("---")

        # ── 상세 수익 리포트 ──
        with st.expander("📊 상세 수익 리포트 & 결재 메모", expanded=False):
            c1, c2 = st.columns([1, 2.5])
            with c1:
                st.info("📝 결재 메모 작성")
                n1 = st.text_area("1. 전략", height=80)
                n2 = st.text_area("2. 인력", height=80)
                n3 = st.text_area("3. 리스크", height=80)
                n4 = st.text_area("4. 결론", height=80)
            with c2:
                html_rep = ue.get_detailed_report_html(st.session_state['est_items'], st.session_state.get('w_client', ''), [n1, n2, n3, n4])
                st.components.v1.html(html_rep, height=1000, scrolling=True)


# ==============================================================================
# 2-1. 견적서 발송 현황
# ==============================================================================
def _show_send_status_section(df_est, df_inq):
    """히스토리 탭 상단에 견적서 발송 확인/처리 섹션"""
    st.subheader("📬 견적서 발송 현황")

    if df_est.empty:
        st.info("저장된 견적이 없어 발송 현황을 표시할 수 없습니다.")
        return

    # ── 발송 여부 컬럼 확인 ──
    has_send_col = '발송여부' in df_est.columns
    if has_send_col:
        sent_mask = df_est['발송여부'].astype(str).str.strip() == '발송완료'
        sent_count = sent_mask.sum()
        unsent_count = len(df_est) - sent_count
    else:
        sent_count = 0
        unsent_count = len(df_est)

    # ── 요약 카드 ──
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(f"""
        <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:10px;padding:16px;text-align:center;">
            <div style="font-size:28px;font-weight:900;color:#059669;">{sent_count}</div>
            <div style="font-size:13px;color:#065F46;font-weight:600;">✅ 발송 완료</div>
        </div>""", unsafe_allow_html=True)
    with s2:
        st.markdown(f"""
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:10px;padding:16px;text-align:center;">
            <div style="font-size:28px;font-weight:900;color:#DC2626;">{unsent_count}</div>
            <div style="font-size:13px;color:#991B1B;font-weight:600;">⏳ 미발송</div>
        </div>""", unsafe_allow_html=True)
    with s3:
        rate = round(sent_count / max(len(df_est), 1) * 100)
        bar_color = "#059669" if rate >= 70 else "#F59E0B" if rate >= 40 else "#DC2626"
        st.markdown(f"""
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:16px;text-align:center;">
            <div style="font-size:28px;font-weight:900;color:{bar_color};">{rate}%</div>
            <div style="font-size:13px;color:#475569;font-weight:600;">📊 발송률</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── 견적별 발송 상태 목록 ──
    # 최신순 정렬
    display_df = df_est.copy()
    if '기록일시' in display_df.columns:
        display_df = display_df.sort_values('기록일시', ascending=False)

    # 필터
    f1, f2 = st.columns([1, 3])
    with f1:
        send_filter = st.selectbox("📌 필터", ["전체", "미발송만", "발송완료만"], key="send_filter_sel")

    if send_filter == "미발송만" and has_send_col:
        display_df = display_df[display_df['발송여부'].astype(str).str.strip() != '발송완료']
    elif send_filter == "발송완료만" and has_send_col:
        display_df = display_df[display_df['발송여부'].astype(str).str.strip() == '발송완료']

    if display_df.empty:
        st.info("해당 조건의 견적이 없습니다.")
        return

    for idx, (_, row) in enumerate(display_df.iterrows()):
        inq_id = str(row.get('문의ID', '')).strip()
        client = str(row.get('업체명', '')).strip()
        event = str(row.get('행사명', row.get('현장명', ''))).strip()
        total = ue.safe_int(row.get('합계금액', 0))
        rec_date = str(row.get('기록일시', ''))[:10]

        is_sent = has_send_col and str(row.get('발송여부', '')).strip() == '발송완료'
        send_date = str(row.get('발송일시', '')).strip() if has_send_col else ''
        send_method_val = str(row.get('발송방법', '')).strip() if has_send_col else ''
        send_memo_val = str(row.get('발송메모', '')).strip() if has_send_col and '발송메모' in df_est.columns else ''

        # 상태 뱃지
        if is_sent:
            badge = f'<span style="background:#D1FAE5;color:#065F46;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;">✅ 발송완료</span>'
            sub_info = f'📤 {send_method_val} | 📅 {send_date}'
        else:
            badge = f'<span style="background:#FEE2E2;color:#991B1B;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;">⏳ 미발송</span>'
            sub_info = ''

        # 카드
        border_color = "#10B981" if is_sent else "#F87171"
        st.markdown(f"""
        <div style="background:white;border:1px solid #e5e7eb;border-left:4px solid {border_color};
                    border-radius:8px;padding:12px 16px;margin-bottom:6px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span style="font-weight:700;font-size:14px;">{client}</span>
                    <span style="color:#6B7280;font-size:12px;margin-left:8px;">{event}</span>
                    {badge}
                </div>
                <div style="text-align:right;">
                    <span style="font-size:16px;font-weight:800;color:#1E40AF;">{total:,}원</span>
                    <div style="font-size:11px;color:#9CA3AF;">ID: {inq_id} | {rec_date}</div>
                </div>
            </div>
            {"<div style='font-size:11px;color:#6B7280;margin-top:4px;'>" + sub_info + ("  |  💬 " + send_memo_val if send_memo_val else "") + "</div>" if sub_info else ""}
        </div>
        """, unsafe_allow_html=True)

        # 발송 처리 / 취소 토글
        if not is_sent:
            with st.expander(f"📤 발송완료 처리 — {client} {event}", expanded=False):
                mc1, mc2 = st.columns([1, 2])
                with mc1:
                    method = st.selectbox("발송방법", ["이메일", "카카오톡", "휴대폰", "팩스", "직접전달"], key=f"send_method_{inq_id}_{idx}")
                with mc2:
                    memo = st.text_input("발송 메모 (선택)", key=f"send_memo_{inq_id}_{idx}", placeholder="예: 담당자 김OO에게 발송")
                if st.button("✅ 발송 완료 처리", key=f"send_btn_{inq_id}_{idx}", type="primary"):
                    with st.spinner("발송 기록 중..."):
                        res = db.update_estimate_send_status(inq_id, method, memo)
                    if res:
                        st.success(f"✅ {client} 견적서 발송 완료 기록됨!")
                        db.invalidate_data()
                        import time; time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ 발송 기록 실패. 시트 연결을 확인해주세요.")
        else:
            with st.expander(f"🔄 발송 취소 — {client} {event}", expanded=False):
                st.warning("발송 완료를 취소하면 미발송 상태로 돌아갑니다.")
                if st.button("🔄 발송 취소", key=f"unsend_btn_{inq_id}_{idx}"):
                    with st.spinner("취소 처리 중..."):
                        res = db.cancel_estimate_send_status(inq_id)
                    if res:
                        st.success("발송 상태가 초기화되었습니다.")
                        db.invalidate_data()
                        import time; time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ 취소 실패")


# ==============================================================================
# 3. 견적 히스토리 & 비교
# ==============================================================================
def _show_history_tab(df_est, df_inq, current_client):
    st.subheader("📋 견적 히스토리 & 비교")

    if df_est.empty:
        st.info("아직 저장된 견적이 없습니다.")
        return

    # ── 업체 필터 ──
    clients = df_est['업체명'].dropna().unique().tolist() if '업체명' in df_est.columns else []
    if not clients:
        st.info("견적 데이터가 없습니다.")
        return

    default_idx = clients.index(current_client) if current_client in clients else 0
    hist_client = st.selectbox("🏢 업체 선택", clients, index=default_idx, key="hist_client")

    client_est = df_est[df_est['업체명'].astype(str).str.strip() == str(hist_client).strip()].copy()
    if client_est.empty:
        st.info(f"'{hist_client}'의 견적 이력이 없습니다.")
        return

    st.markdown(f"**{hist_client}** — 총 **{len(client_est)}건** 견적 이력")

    # ── 히스토리 카드 ──
    for _, row in client_est.iterrows():
        inq_id = str(row.get('문의ID', '')).strip()
        event = str(row.get('행사명', row.get('현장명', '')))
        supply = ue.safe_int(row.get('공급가액', 0))
        cost = ue.safe_int(row.get('매입원가', 0))
        total = ue.safe_int(row.get('합계금액', 0))
        vat = ue.safe_int(row.get('부가세', 0))
        margin = str(row.get('수익률', row.get('수익율', '')))
        rec_date = str(row.get('기록일시', ''))[:10]
        profit = supply - cost
        pcolor = "#dc2626" if profit < 0 else "#059669"

        inq_status = ""
        if not df_inq.empty and '문의ID' in df_inq.columns:
            matched = df_inq[df_inq['문의ID'].astype(str).str.strip() == inq_id]
            if not matched.empty:
                inq_status = str(matched.iloc[0].get('상태', ''))
        sbadge = f'<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">{inq_status}</span>' if inq_status else ''

        st.markdown(f"""
        <div class="history-card">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span style="font-weight:bold;font-size:15px;">{event}</span> {sbadge}
                    <div style="font-size:11px;color:#6b7280;margin-top:2px;">ID: {inq_id} | {rec_date}</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:18px;font-weight:900;color:#1e40af;">{total:,}원</div>
                    <div style="font-size:12px;color:{pcolor};">수익 {profit:,}원 {margin}</div>
                </div>
            </div>
            <div style="display:flex;gap:15px;margin-top:8px;font-size:12px;color:#64748b;">
                <span>공급가액: {supply:,}</span>
                <span>지출금액: {cost:,}</span>
                <span>부가세: {vat:,}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # ── 견적 품목 상세내역 (직군/인원/날짜) ──
        try:
            _hist_items = db.load_estimate_items(inq_id)
            if not _hist_items.empty:
                with st.expander(f"📦 {event} — 품목 상세 ({len(_hist_items)}건)", expanded=False):
                    _hist_display = _hist_items.copy()
                    _show_cols = []
                    for _hc in ['직군명', '수량', '일수', '매출단가', '매입단가', '규격', '비고']:
                        if _hc in _hist_display.columns:
                            _show_cols.append(_hc)
                    if _show_cols:
                        # 단가 포맷팅
                        for _fc in ['매출단가', '매입단가']:
                            if _fc in _hist_display.columns:
                                _hist_display[_fc] = _hist_display[_fc].apply(lambda x: f"{ue.safe_int(x):,}")
                        _hist_display = _hist_display.rename(columns={'매출단가': '청구단가', '매입단가': '지급단가'})
                        _show_cols = [c.replace('매출단가', '청구단가').replace('매입단가', '지급단가') for c in _show_cols]
                        st.dataframe(_hist_display[_show_cols], use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(_hist_display, use_container_width=True, hide_index=True)
        except Exception:
            pass

    # ── 견적 비교 ──
    st.markdown("---")
    st.subheader("🔍 견적 비교")
    if len(client_est) >= 2:
        labels = [f"{r.get('행사명', '')} ({str(r.get('기록일시', ''))[:10]})" for _, r in client_est.iterrows()]
        cc1, cc2 = st.columns(2)
        with cc1:
            sel_a = st.selectbox("비교 A", range(len(client_est)), format_func=lambda x: labels[x], key="comp_a")
        with cc2:
            sel_b = st.selectbox("비교 B", range(len(client_est)), index=min(1, len(client_est) - 1),
                                 format_func=lambda x: labels[x], key="comp_b")

        row_a, row_b = client_est.iloc[sel_a], client_est.iloc[sel_b]
        items = ['공급가액', '매입원가', '합계금액', '부가세', '부대비용']
        comp = []
        for it in items:
            va, vb = ue.safe_int(row_a.get(it, 0)), ue.safe_int(row_b.get(it, 0))
            diff = vb - va
            lbl = it.replace('매입원가', '지출금액')
            comp.append({"항목": lbl, "A": f"{va:,}", "B": f"{vb:,}", "차이": f"{diff:+,}"})
        st.dataframe(pd.DataFrame(comp), hide_index=True, use_container_width=True)
    else:
        st.caption("비교하려면 2건 이상의 견적이 필요합니다.")

    # ── 전체 통계 ──
    st.markdown("---")
    st.subheader("📊 전체 견적 통계")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("총 견적 수", f"{len(df_est)}건")
    with m2:
        total_rev = int(df_est['합계금액'].apply(ue.safe_int).sum()) if '합계금액' in df_est.columns else 0
        st.metric("총 합계금액", f"{total_rev:,}원")
    with m3:
        avg_rev = int(total_rev / max(len(df_est), 1))
        st.metric("평균 견적가", f"{avg_rev:,}원")
    with m4:
        uq = df_est['업체명'].nunique() if '업체명' in df_est.columns else 0
        st.metric("거래 업체 수", f"{uq}곳")


# ==============================================================================
# 4. 고객별 자동 추천 단가
# ==============================================================================
def _show_auto_recommend(df_est, client_name, role_name):
    if df_est.empty or not client_name:
        return
    try:
        client_ests = df_est[df_est['업체명'].astype(str).str.strip() == str(client_name).strip()]
        if client_ests.empty:
            return
        inq_ids = client_ests['문의ID'].astype(str).str.strip().tolist()

        prices = []
        for iid in inq_ids[:5]:
            items = db.load_estimate_items(iid)
            if not items.empty and '직군명' in items.columns:
                matched = items[items['직군명'].astype(str).str.contains(role_name.replace(' [팀장]', ''), na=False)]
                for _, r in matched.iterrows():
                    sell = ue.safe_int(r.get('매출단가', 0))
                    buy = ue.safe_int(r.get('매입단가', 0))
                    if sell > 0:
                        prices.append({'청구': sell, '지급': buy})

        if prices:
            avg_s = int(sum(p['청구'] for p in prices) / len(prices))
            avg_b = int(sum(p['지급'] for p in prices) / len(prices))
            mn_s = min(p['청구'] for p in prices)
            mx_s = max(p['청구'] for p in prices)
            st.markdown(f"""
            <div class="recommend-box">
                <div style="font-size:12px;font-weight:bold;color:#1e40af;">💡 {client_name} — {role_name} 과거 단가</div>
                <div style="display:flex;gap:15px;margin-top:6px;font-size:13px;">
                    <span>평균 청구: <b>{avg_s:,}원</b></span>
                    <span>평균 지급: <b>{avg_b:,}원</b></span>
                </div>
                <div style="font-size:11px;color:#6b7280;margin-top:3px;">범위: {mn_s:,} ~ {mx_s:,}원 ({len(prices)}건)</div>
            </div>
            """, unsafe_allow_html=True)
    except Exception:
        pass
