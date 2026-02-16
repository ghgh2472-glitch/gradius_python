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
from datetime import datetime, timedelta
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
    </style>
    """, unsafe_allow_html=True)


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
    return """<span style="color:#000080; font-weight:bold;">1. 결제사항</span> | 행사시작전 2주이내 선금 50% | 행사 종료 후 1주이내 잔금 50%
<span style="font-size:11px; color:#666;">※ 견적은 상황에 따라 변동될 수 있습니다.</span>
<span style="color:#000080; font-weight:bold;">2. 계약 확정 안내</span> | 우수한 인력 확보 및 행사 품질 유지를 위해 행사일 기준 3주 전 계약을 권장합니다.
<span style="font-size:11px; color:#666;">※ 부득이한 경우라도 최소 2주 전까지는 확정해 주시기 바랍니다.</span>"""


def get_default_terms_side():
    return """<span style="color:#000080; font-weight:bold;">3. 근무 및 비용 기준</span>
- 계약시간 근무 기준 | 계약시간 이후 추가시간 발생 시 시간당 추가 금액
  • 경호원 & 경비지도사 : 30,000원 (VAT 별도) • STAFF : 20,000원 (VAT 별도)
- 복리후생비, 일반관리비, 직책수당 단가 포함"""


def _load_existing_items(inquiry_id):
    """기존 견적품목을 est_items 형식 DataFrame으로 로드"""
    raw = db.load_estimate_items(inquiry_id)
    if raw.empty:
        return pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','매출합계','매입합계','비고'])
    rows = []
    for _, r in raw.iterrows():
        name = str(r.get('직군명', ''))
        if str(r.get('팀장여부', '')).strip() == '팀장':
            name += ' [팀장]'
        qty = ue.safe_int(r.get('수량', 0))
        days = ue.safe_int(r.get('일수', 1))
        sell = ue.safe_int(r.get('매출단가', 0))
        buy = ue.safe_int(r.get('매입단가', 0))
        rows.append({
            '품목': name, '규격': str(r.get('규격', '')),
            '수량': qty, '일수': days,
            '매출단가': sell, '매입단가': buy,
            '매출합계': sell * qty * days, '매입합계': buy * qty * days,
            '비고': str(r.get('비고', ''))
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','매출합계','매입합계','비고'])


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
    # 프로젝트 대기열 (접수 + 견적수정)
    # ================================================================
    pending_new = pd.DataFrame()
    pending_edit = pd.DataFrame()
    if not df_inq.empty and '상태' in df_inq.columns:
        pending_new = df_inq[df_inq['상태'] == sc.STATUS_FLOW[0]].sort_values('작성일', ascending=False).copy()
        pending_edit = df_inq[df_inq['상태'] == sc.STATUS_FLOW[1]].sort_values('작성일', ascending=False).copy()

    p_list = ["(신규작성)"]
    if not pending_new.empty:
        pending_new['label'] = "[접수] " + pending_new['업체명'].astype(str) + " (" + pending_new['행사명'].astype(str) + ")"
        p_list += pending_new['label'].tolist()
    if not pending_edit.empty:
        pending_edit['label'] = "[수정] " + pending_edit['업체명'].astype(str) + " (" + pending_edit['행사명'].astype(str) + ")"
        p_list += pending_edit['label'].tolist()

    all_pending = pd.concat([pending_new, pending_edit], ignore_index=True) if (not pending_new.empty or not pending_edit.empty) else pd.DataFrame()

    c_load, c_info = st.columns([1.5, 2.5])
    with c_load:
        sel_p = st.selectbox("📂 프로젝트 선택", p_list, key="est_project_sel")
    with c_info:
        if sel_p.startswith("[수정]"):
            st.info("📝 기존 견적을 수정합니다. 저장 시 기존 데이터를 덮어씁니다.")
        elif sel_p.startswith("[접수]"):
            st.success("🆕 새 견적을 작성합니다.")

    # ── 세션 초기화 ──
    if 'est_items' not in st.session_state:
        st.session_state['est_items'] = pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','매출합계','매입합계','비고'])
    if 'w_client' not in st.session_state:
        st.session_state.update({
            'w_client': '', 'w_event': '', 'w_loc': '', 'w_manager': '', 'w_contact': '',
            'w_qty': 1, 'w_sdate': datetime.now().date(), 'w_edate': datetime.now().date(),
            'w_time_in': datetime.strptime("09:00", "%H:%M").time(),
            'w_time_out': datetime.strptime("18:00", "%H:%M").time(),
            'w_terms_top': get_default_terms_top(),
            'w_terms_side': get_default_terms_side()
        })

    # ================================================================
    # 프로젝트 선택 시 데이터 로드
    # ================================================================
    if sel_p != "(신규작성)" and not all_pending.empty and st.session_state.get('last_project') != sel_p:
        try:
            target = all_pending[all_pending['label'] == sel_p].iloc[0]
            target_id = str(target.get('문의ID', '')).strip()

            # ▶ 날짜 개별 파싱
            start_raw = str(target.get('행사시작일', target.get('시작일', ''))).strip()
            end_raw = str(target.get('행사종료일', target.get('종료일', ''))).strip()
            if start_raw and end_raw:
                raw_dates = f"{start_raw}~{end_raw}"
            elif start_raw:
                raw_dates = start_raw
            else:
                raw_dates = str(target.get('일시', ''))

            s_d, e_d, _ = ue.smart_parse_date(raw_dates)
            s_t, e_t, _ = ue.smart_parse_time(target.get('행사시간', str(target.get('시간', ''))))
            qty = ue.safe_int(str(target.get('필요인력', target.get('요청인원', target.get('인원', '1')))).replace('명', ''))

            st.session_state.update({
                'w_client': target.get('업체명', ''),
                'w_event': target.get('행사명', ''),
                'w_loc': target.get('장소', ''),
                'w_manager': target.get('담당자', ''),
                'w_contact': target.get('연락처', str(target.get('담당자연락처', ''))),
                'w_sdate': s_d, 'w_edate': e_d,
                'w_qty': qty,
                'last_project': sel_p,
                '_current_inq_id': target_id,
            })

            # ▶ 견적수정 시 기존 품목 로드
            if sel_p.startswith("[수정]"):
                st.session_state['est_items'] = _load_existing_items(target_id)
            else:
                st.session_state['est_items'] = pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','매출합계','매입합계','비고'])

            # ▶ 모든 위젯 키 강제 삭제 (Streamlit key→value 우선 문제 해소)
            for k in ['final_client', 'final_manager', 'final_contact', 'final_loc',
                       'w_date_range', 'w_time_in', 'w_time_out',
                       'est_items_editor', 'final_edit_table', 'additional_costs_editor']:
                if k in st.session_state:
                    del st.session_state[k]

            st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '금액', '비고'])
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
    tab1, tab2, tab3, tab4 = st.tabs([
        "🛠️ 견적 산출", "📄 견적서 발행", "📋 견적 히스토리 & 비교", "📊 상세 수익 리포트"
    ])

    # ==================================================================
    # TAB 1: 견적 산출
    # ==================================================================
    with tab1:
        col_L, col_R = st.columns([1, 1.2])

        with col_L:
            with st.container(border=True):
                st.markdown('<div class="sub-header">1️⃣ 기본 정보</div>', unsafe_allow_html=True)
                st.text_input("수신인 (업체명)", key="w_client")
                st.text_input("행사명", key="w_event")
                st.text_input("장소 (현장주소)", key="w_loc")
                dates = st.date_input("기간", value=(st.session_state['w_sdate'], st.session_state['w_edate']), key="w_date_range")
                calc_days = (dates[1] - dates[0]).days + 1 if isinstance(dates, tuple) and len(dates) == 2 else 1

            with st.container(border=True):
                st.markdown('<div class="sub-header">2️⃣ 인력 품목 추가</div>', unsafe_allow_html=True)
                roles = ["선택"] + (df_roles['직군명'].unique().tolist() if not df_roles.empty else [])
                role_kr = st.selectbox("직군", roles)
                r_info = brain.get_role_info(role_kr)
                role_id, base_p, cost_p = r_info['role_id'], r_info['base_price'], r_info['cost_price']

                # ▶ 고객별 자동 추천 단가
                if role_kr != "선택" and st.session_state.get('w_client'):
                    _show_auto_recommend(df_est, st.session_state['w_client'], role_kr)

                factors = brain.get_factors(role_id)
                f_map = {f"{f['name']} (+{f['price']:,})": f for f in factors}
                picks = st.multiselect("할증 옵션", list(f_map.keys()))
                add_p = sum([f_map[p]['price'] for p in picks])
                add_c = sum([f_map[p]['cost_add'] for p in picks])

                c1, c2 = st.columns([1, 1.5])
                is_leader = c1.checkbox("팀장 수당")
                pay_type = c2.radio("지급기준", ["일급", "시급"], horizontal=True, label_visibility="collapsed")
                if is_leader:
                    base_p += 10000; cost_p += 10000

                t1, t2, t3 = st.columns([1.1, 1.1, 0.8])
                ti = t1.time_input("출근", key="w_time_in")
                to_ = t2.time_input("퇴근", key="w_time_out")
                iq = t3.number_input("인원", min_value=1, key="w_qty")
                dur = ue.smart_parse_time(f"{ti}~{to_}")[2]
                spec_txt = f"{ti.strftime('%H:%M')}~{to_.strftime('%H:%M')} ({dur}H)"

                cc1, cc2 = st.columns(2)
                fb = cc1.number_input("청구단가", value=base_p + add_p, step=5000)
                fp = cc2.number_input("지급단가", value=cost_p + add_c, step=5000)

                if st.button("⬇️ 리스트 추가", type="primary", use_container_width=True):
                    if role_kr == "선택":
                        st.warning("직군 선택")
                    else:
                        qty_calc = iq * calc_days
                        mult = dur if pay_type == "시급" else 1
                        tot_bill = int(fb * mult * qty_calc)
                        tot_cost = int(fp * mult * qty_calc)
                        nm = f"{role_kr} {'[팀장]' if is_leader else ''}"
                        note = ", ".join([f_map[p]['name'] for p in picks])
                        new_row = {"품목": nm, "규격": spec_txt, "수량": iq, "일수": calc_days,
                                   "매출단가": fb, "매입단가": fp, "매출합계": tot_bill, "매입합계": tot_cost, "비고": note}
                        st.session_state['est_items'] = pd.concat(
                            [st.session_state['est_items'], pd.DataFrame([new_row])], ignore_index=True)
                        st.rerun()

        with col_R:
            # ── AI 분석 ──
            st.markdown('<div class="sub-header">📊 AI 분석</div>', unsafe_allow_html=True)
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

            # ── 품목 테이블 ──
            st.data_editor(
                st.session_state['est_items'], width='stretch', hide_index=True,
                num_rows="dynamic", key="est_items_editor",
                column_config={
                    "매출단가": st.column_config.NumberColumn("청구단가", format="%d"),
                    "매입단가": st.column_config.NumberColumn("지급단가", format="%d"),
                    "매출합계": st.column_config.NumberColumn("청구합계", format="%d"),
                    "매입합계": st.column_config.NumberColumn("지출합계", format="%d"),
                })

            # 삭제 버튼
            if not st.session_state['est_items'].empty:
                n_items = len(st.session_state['est_items'])
                del_cols = st.columns(min(n_items, 8) + 1)
                for idx in range(min(n_items, 8)):
                    r = st.session_state['est_items'].iloc[idx]
                    with del_cols[idx]:
                        if st.button(f"🗑️{idx+1}", key=f"del_item_{idx}", help=f"{r['품목']} 삭제"):
                            st.session_state['est_items'] = st.session_state['est_items'].drop(idx).reset_index(drop=True)
                            st.rerun()
                with del_cols[-1]:
                    if st.button("🗑️전체", key="del_all_items"):
                        st.session_state['est_items'] = pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','매출합계','매입합계','비고'])
                        st.rerun()

            # ── 단가 일괄 조정 ──
            st.markdown("---")
            st.markdown('<div class="sub-header">⚡ 단가 일괄 조정</div>', unsafe_allow_html=True)
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

            # ── 부대비용 ──
            st.markdown("---")
            st.markdown('<div class="sub-header">🛒 부대비용</div>', unsafe_allow_html=True)
            if 'additional_costs' not in st.session_state:
                st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '금액', '비고'])

            cost_c1, cost_c2, cost_c3, cost_c4 = st.columns([1.5, 0.8, 1, 0.8])
            with cost_c1:
                cost_item = st.selectbox("항목", ["식비","숙박비","교통비","용역료","기타"], label_visibility="collapsed", key="cost_item_select")
            with cost_c2:
                cost_amt = st.number_input("금액", min_value=0, step=10000, label_visibility="collapsed", key="cost_amount_input")
            with cost_c3:
                cost_note = st.text_input("설명", label_visibility="collapsed", placeholder="예: 1인당 50,000원 x 10명", key="cost_note_input")
            with cost_c4:
                if st.button("➕", key="add_cost_btn", use_container_width=True):
                    if cost_amt > 0:
                        st.session_state['additional_costs'] = pd.concat([
                            st.session_state['additional_costs'],
                            pd.DataFrame([{"항목": cost_item, "금액": cost_amt, "비고": cost_note}])
                        ], ignore_index=True)

            total_additional = 0
            if not st.session_state['additional_costs'].empty:
                edited_costs = st.data_editor(
                    st.session_state['additional_costs'], width='stretch', hide_index=True,
                    num_rows="dynamic", key="additional_costs_editor",
                    column_config={"금액": st.column_config.NumberColumn("금액", format="%d")}
                )
                st.session_state['additional_costs'] = edited_costs
                total_additional = int(edited_costs['금액'].sum())
                dc1, dc2 = st.columns([3, 1])
                with dc1:
                    st.caption(f"💰 부대비용 합계: {total_additional:,}원")
                with dc2:
                    if st.button("🗑️ 초기화", key="del_all_costs"):
                        st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '금액', '비고'])
                        st.rerun()

            # ── 결과 박스 ──
            supply_sum = int(st.session_state['est_items']['매출합계'].sum()) if not st.session_state['est_items'].empty else 0
            cost_sum = int(st.session_state['est_items']['매입합계'].sum()) if not st.session_state['est_items'].empty else 0
            vat_val = int(supply_sum * 0.1)
            profit_val = supply_sum - cost_sum - total_additional
            margin_pct = (profit_val / supply_sum * 100) if supply_sum > 0 else 0

            st.markdown(f"""
                <div class="result-box">
                    <div style="display:flex; justify-content:space-between; font-size:13px; color:#666;">
                        <span>공급가액: {supply_sum:,}원</span>
                        <span>지출금액: {cost_sum:,}원</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:13px; color:#c2410c; margin-top:2px;">
                        <span>부가세(10%): {vat_val:,}원</span>
                        <span>부대비용: {total_additional:,}원</span>
                    </div>
                    <hr style="margin:8px 0;">
                    <div style="display:flex; justify-content:space-between; font-size:16px; color:#064e3b; margin-bottom:5px;">
                        <span>예상수익:</span>
                        <span><b>{profit_val:,}원 ({margin_pct:.1f}%)</b></span>
                    </div>
                    <div style="font-size:24px;font-weight:900;color:#064e3b;">
                        합계 {supply_sum + vat_val:,}원
                        <span style="font-size:13px;color:#666;">(VAT {vat_val:,}원 포함)</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # ==================================================================
    # TAB 2: 견적서 발행
    # ==================================================================
    with tab2:
        col_edit, col_view = st.columns([1, 2.2])
        with col_edit:
            st.markdown("### ✏️ 편집")
            with st.container(border=True):
                st.caption("📌 수신자 정보")
                f_client = st.text_input("상호", value=st.session_state.get('w_client', ''), key="final_client")
                c_1, c_2 = st.columns(2)
                f_ref = c_1.text_input("참조 (담당자)", value=st.session_state.get('w_manager', ''), key="final_manager")
                f_tel = c_2.text_input("연락처", value=st.session_state.get('w_contact', ''), key="final_contact")
                f_addr = st.text_input("주소 (현장)", value=st.session_state.get('w_loc', ''), key="final_loc")

            st.caption("📋 리스트 수정")
            edited_df = st.data_editor(
                st.session_state['est_items'], width='stretch', num_rows="dynamic",
                column_config={"매출합계": st.column_config.NumberColumn("금액", format="%d")},
                hide_index=True, key="final_edit_table"
            )

            t_top = st.text_area("상단 약관", value=st.session_state['w_terms_top'], height=120)
            t_side = st.text_area("측면 약관", value=st.session_state['w_terms_side'], height=120)

            st.markdown('<div class="action-bar"></div>', unsafe_allow_html=True)
            b1, b2, b3 = st.columns([0.8, 1.2, 1])
            with b1:
                vat_yn = st.checkbox("VAT 포함", value=True)
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
                            target_row = all_pending[all_pending['label'] == sel_p].iloc[0]
                            target_id = str(target_row.get('문의ID', ''))

                            s_amt = int(edited_df['매출합계'].sum()) if not edited_df.empty else 0
                            c_amt = int(edited_df['매입합계'].sum()) if not edited_df.empty else 0
                            add_total = int(st.session_state.get('additional_costs', pd.DataFrame()).get('금액', pd.Series([0])).sum())
                            total_supply = s_amt + add_total
                            v_amt = int(total_supply * 0.1) if vat_yn else 0

                            final_save_name = f_client if f_client else st.session_state.get('w_client', target_row.get('업체명', ''))

                            metadata = {
                                "현장명": st.session_state.get('w_event', ''),
                                "책임자": f_ref or target_row.get('담당자', ''),
                                "현장주소": f_addr or target_row.get('장소', ''),
                                "사업자번호": "", "대표자": "",
                                "담당자": f_ref or target_row.get('담당자', ''),
                                "연락처": f_tel or target_row.get('연락처', '')
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

                                    # ▶ 저장 후 값 보존 (rerun하지 않음!)
                                    st.session_state['_est_saved'] = True
                                    st.session_state['w_client'] = final_save_name
                                    st.session_state['w_manager'] = f_ref
                                    st.session_state['w_contact'] = f_tel
                                    st.session_state['w_loc'] = f_addr
                                    st.balloons()
                                    st.success(f"✅ {final_save_name} 견적 저장 완료!")
                                    st.cache_data.clear()
                                else:
                                    st.error("❌ 시트 저장 실패.")
                        except Exception as e:
                            st.error(f"⚠️ 시스템 오류: {e}")

        with col_view:
            st.markdown("### 📄 미리보기 (Preview)")
            final_supply = edited_df['매출합계'].sum() if not edited_df.empty else 0
            date_range_txt = f"{st.session_state['w_sdate']} ~ {st.session_state['w_edate']}"

            additional_costs_df = st.session_state.get('additional_costs', pd.DataFrame())
            if not additional_costs_df.empty:
                st.markdown("#### 🛒 부대비용 상세")
                st.dataframe(additional_costs_df, use_container_width=True, hide_index=True)
                total_additional_v = int(additional_costs_df['금액'].sum())
                st.metric("부대비용 합계", f"{total_additional_v:,}원")
            else:
                total_additional_v = 0

            client_dict = {
                "name": f_client if f_client else st.session_state.get('w_client', ''),
                "ref": f_ref, "tel": f_tel, "addr": f_addr,
                "date_range": date_range_txt, "date": datetime.now().strftime("%Y-%m-%d")
            }
            supplier_dict = {"reg_no": "429-88-01469", "name": "(주)가디어스", "ceo": "최규성", "tel": "1600-2944", "addr": "서울시 종로구 동망산1길 2, 1층"}
            html_quote = ue.get_customer_quote_html(edited_df, client_dict, supplier_dict, final_supply, vat_yn, t_top, t_side, banner_b64, additional_costs_df, total_additional_v)
            st.components.v1.html(html_quote, height=950, scrolling=True)

    # ==================================================================
    # TAB 3: 견적 히스토리 & 비교
    # ==================================================================
    with tab3:
        _show_history_tab(df_est, df_inq, st.session_state.get('w_client', ''))

    # ==================================================================
    # TAB 4: 상세 수익 리포트
    # ==================================================================
    with tab4:
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
