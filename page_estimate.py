# page_estimate.py
import streamlit as st
import pandas as pd
import utils_estimate as ue 
import data_loader as db
import status_config as sc
from datetime import datetime, timedelta
import time  # 라이브러리 전용 time 임포트
import base64
import os

# ==============================================================================
# 1. 스타일링 및 헬퍼 함수
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
    </style>
    """, unsafe_allow_html=True)

def load_local_banner():
    banner_path = "banner.png"
    if os.path.exists(banner_path):
        try:
            with open(banner_path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode()
        except: return None
    return None

def image_to_base64(uploaded_file):
    if uploaded_file is not None:
        try:
            return base64.b64encode(uploaded_file.getvalue()).decode()
        except: return None
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

# ==============================================================================
# 2. 메인 화면 로직
# ==============================================================================
def show(data):
    apply_styles()
    
    # 데이터 로드
    df_inq = data.get('inq', pd.DataFrame())
    df_roles = data.get('roles', pd.DataFrame())
    df_factors = data.get('factors', pd.DataFrame())
    df_guides = data.get('guides', pd.DataFrame())
    df_clients = data.get('client', pd.DataFrame())

    if '문의날짜' in df_inq.columns: df_inq = df_inq.rename(columns={'문의날짜': '작성일'})
    if '작성일' not in df_inq.columns: df_inq['작성일'] = ""
    if not df_roles.empty and '직군명' not in df_roles.columns: df_roles['직군명'] = df_roles['Role']

    st.title("🧮 견적 통합 관리 (Smart V9)")

    # 프로젝트 대기열 필터링
    pending = pd.DataFrame()
    if not df_inq.empty and '상태' in df_inq.columns:
        pending = df_inq[df_inq['상태'] == sc.STATUS_FLOW[0]].sort_values('작성일', ascending=False)  # '접수'
    
    c_load, c_dummy = st.columns([1.5, 2.5])
    with c_load:
        p_list = ["(신규작성)"]
        if not pending.empty:
            pending['label'] = pending['업체명'] + " (" + pending['행사명'] + ")"
            p_list += pending['label'].tolist()
        sel_p = st.selectbox("📂 대기중인 프로젝트", p_list)

    # 세션 초기화
    if 'est_items' not in st.session_state:
        st.session_state['est_items'] = pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','매출합계','매입합계','비고'])

    # 시간 객체 충돌 방지 초기값
    if 'w_client' not in st.session_state:
        st.session_state.update({
            'w_client':'', 'w_event':'', 'w_loc':'', 'w_manager':'', 'w_contact':'', 
            'w_qty':1, 'w_sdate':datetime.now().date(), 'w_edate':datetime.now().date(), 
            'w_time_in': datetime.strptime("09:00", "%H:%M").time(),
            'w_time_out': datetime.strptime("18:00", "%H:%M").time(),
            'w_terms_top': get_default_terms_top(),
            'w_terms_side': get_default_terms_side()
        })

    # 프로젝트 선택 시 데이터 자동 매핑
    if sel_p != "(신규작성)" and not pending.empty and st.session_state.get('last_project') != sel_p:
        try:
            target = pending[pending['label'] == sel_p].iloc[0]
            raw_dates = f"{target.get('행사시작일','')}~{target.get('행사종료일','')}"
            if len(raw_dates) < 5: raw_dates = str(target.get('일시', ''))
            s_d, e_d, _ = ue.smart_parse_date(raw_dates)
            s_t, e_t, _ = ue.smart_parse_time(target.get('행사시간', str(target.get('시간',''))))
            qty = ue.safe_int(str(target.get('요청인원', target.get('인원', '1'))).replace('명',''))
            
            st.session_state.update({
                'w_client': target.get('업체명', ''), 'w_event': target.get('행사명', ''), 
                'w_loc': target.get('장소', ''), 'w_manager': target.get('담당자', ''), 'w_contact': target.get('연락처', ''),
                'w_sdate': s_d, 'w_edate': e_d, 'w_time_in': s_t, 'w_time_out': e_t, 'w_qty': qty,
                'last_project': sel_p,
                'est_items': pd.DataFrame(columns=['품목','규격','수량','일수','매출단가','매입단가','매출합계','매입합계','비고'])
            })
            st.rerun()
        except: pass

    brain = ue.EstimateBrain(df_roles, df_guides, df_factors, df_clients)
    tab1, tab2, tab3 = st.tabs(["🛠️ 견적 산출", "📄 견적서 발행 (Editor)", "📊 상세 수익 리포트"])

    # --- TAB 1: 견적 산출 ---
    with tab1:
        col_L, col_R = st.columns([1, 1.2])
        with col_L:
            with st.container(border=True):
                st.markdown('<div class="sub-header">1️⃣ 기본 정보</div>', unsafe_allow_html=True)
                st.text_input("수신인 (업체명)", key="w_client")
                st.text_input("행사명", key="w_event")
                st.text_input("장소 (현장주소)", key="w_loc") 
                dates = st.date_input("기간", value=(st.session_state['w_sdate'], st.session_state['w_edate']), key="w_date_range")
                calc_days = (dates[1]-dates[0]).days+1 if isinstance(dates, tuple) and len(dates)==2 else 1
            
            with st.container(border=True):
                st.markdown('<div class="sub-header">2️⃣ 인력 품목 추가</div>', unsafe_allow_html=True)
                roles = ["선택"] + (df_roles['직군명'].unique().tolist() if not df_roles.empty else [])
                role_kr = st.selectbox("직군", roles)
                r_info = brain.get_role_info(role_kr)
                role_id, base_p, cost_p = r_info['role_id'], r_info['base_price'], r_info['cost_price']
                factors = brain.get_factors(role_id)
                f_map = {f"{f['name']} (+{f['price']:,})": f for f in factors}
                picks = st.multiselect("할증 옵션", list(f_map.keys()))
                add_p = sum([f_map[p]['price'] for p in picks])
                add_c = sum([f_map[p]['cost_add'] for p in picks])
                c1, c2 = st.columns([1, 1.5])
                is_leader = c1.checkbox("팀장 수당")
                pay_type = c2.radio("지급기준", ["일급","시급"], horizontal=True, label_visibility="collapsed")
                if is_leader: base_p += 10000; cost_p += 10000
                t1, t2, t3 = st.columns([1.1, 1.1, 0.8])
                ti = t1.time_input("출근", key="w_time_in")
                to = t2.time_input("퇴근", key="w_time_out")
                iq = t3.number_input("인원", min_value=1, key="w_qty")
                dur = ue.smart_parse_time(f"{ti}~{to}")[2]
                spec_txt = f"{ti.strftime('%H:%M')}~{to.strftime('%H:%M')} ({dur}H)"
                cc1, cc2 = st.columns(2)
                fb = cc1.number_input("청구단가", value=base_p+add_p, step=5000)
                fp = cc2.number_input("지급단가", value=cost_p+add_c, step=5000)
                if st.button("⬇️ 리스트 추가", type="primary", use_container_width=True):
                    if role_kr=="선택": st.warning("직군 선택")
                    else:
                        qty_calc = iq * calc_days
                        mult = dur if pay_type=="시급" else 1
                        tot_bill = int(fb * mult * qty_calc)
                        tot_cost = int(fp * mult * qty_calc)
                        nm = f"{role_kr} {'[팀장]' if is_leader else ''}"
                        note = ", ".join([f_map[p]['name'] for p in picks])
                        new_row = {"품목":nm, "규격":spec_txt, "수량":iq, "일수":calc_days, "매출단가":fb, "매입단가":fp, "매출합계":tot_bill, "매입합계":tot_cost, "비고":note}
                        st.session_state['est_items'] = pd.concat([st.session_state['est_items'], pd.DataFrame([new_row])], ignore_index=True)
                        st.rerun()

        with col_R:
            st.markdown('<div class="sub-header">📊 AI 분석</div>', unsafe_allow_html=True)
            analysis = brain.get_analysis(role_id)
            g_txt = "<br>".join([f"• {g}" for g in analysis['guide']]) if analysis['guide'] else "직군 선택 시 가이드 표시"
            
            # [AI 분석 지표 완벽 복구]
            st.markdown(f"""
                <div class="analysis-box">
                    <b>📘 {role_kr if role_kr != '선택' else '직군'} 가이드</b><br>{g_txt}<br>
                    <hr style="margin:8px 0; border-color:#fdba74;">
                    <div style="font-size:12px; display:flex; justify-content:space-between;">
                        <span>💰 시장가: {analysis['market']}</span>
                        <span>🏢 타사: {analysis['comp']}</span>
                    </div>
                    <div style="font-size:12px; margin-top:5px; color:#c2410c;">
                        🏆 <b>자사 체결:</b> {analysis['my_best']}
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            st.data_editor(st.session_state['est_items'], width='stretch', hide_index=True, column_config={"매출단가": "청구단가", "매입단가": "지급단가", "매출합계": "청구합계"})
            
            # [부대비용 섹션 추가]
            st.markdown("---")
            st.markdown('<div class="sub-header">🛒 부대비용</div>', unsafe_allow_html=True)
            
            # 부대비용 세션 초기화
            if 'additional_costs' not in st.session_state:
                st.session_state['additional_costs'] = pd.DataFrame(columns=['항목', '금액', '비고'])
            
            # 부대비용 입력 폼
            cost_col1, cost_col2, cost_col3, cost_col4 = st.columns([1.5, 0.8, 1, 0.8])
            with cost_col1:
                cost_item = st.selectbox("항목", ["식비", "숙박비", "교통비", "용역료", "기타"], label_visibility="collapsed", key="cost_item_select")
            with cost_col2:
                cost_amount = st.number_input("금액", min_value=0, step=10000, label_visibility="collapsed", key="cost_amount_input")
            with cost_col3:
                cost_note = st.text_input("설명", label_visibility="collapsed", placeholder="예: 1인당 50,000원 x 10명", key="cost_note_input")
            with cost_col4:
                if st.button("➕", key="add_cost_btn", use_container_width=True):
                    if cost_amount > 0:
                        new_cost_row = pd.DataFrame([{"항목": cost_item, "금액": cost_amount, "비고": cost_note}])
                        st.session_state['additional_costs'] = pd.concat([st.session_state['additional_costs'], new_cost_row], ignore_index=True)
            
            # 부대비용 테이블 표시 및 편집
            if not st.session_state['additional_costs'].empty:
                edited_costs = st.data_editor(
                    st.session_state['additional_costs'], 
                    width='stretch', 
                    hide_index=True,
                    key="additional_costs_editor",
                    column_config={"금액": st.column_config.NumberColumn("금액", format="%d")}
                )
                st.session_state['additional_costs'] = edited_costs
                total_additional = edited_costs['금액'].sum()
                st.caption(f"💰 부대비용 합계: {total_additional:,}원")
            else:
                total_additional = 0
            
            # [결과 박스 고도화: 수익률/부가세 시각화]
            supply_sum = st.session_state['est_items']['매출합계'].sum() if not st.session_state['est_items'].empty else 0
            cost_sum = st.session_state['est_items']['매입합계'].sum() if not st.session_state['est_items'].empty else 0
            vat_val = int(supply_sum * 0.1)
            profit_val = supply_sum - cost_sum - total_additional
            margin_pct = (profit_val / supply_sum * 100) if supply_sum > 0 else 0
            
            st.markdown(f"""
                <div class="result-box">
                    <div style="display:flex; justify-content:space-between; font-size:13px; color:#666;">
                        <span>공급가액: {supply_sum:,}원</span>
                        <span>매입원가: {cost_sum:,}원</span>
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
                    <div style="font-size:24px;font-weight:900;color:#064e3b;">합계 {supply_sum + vat_val:,}원</div>
                </div>
            """, unsafe_allow_html=True)

    # --- TAB 2: 견적서 발행 ---
    with tab2:
        col_edit, col_view = st.columns([1, 2.2]) 
        with col_edit:
            st.markdown("### ✏️ 편집")
            with st.container(border=True):
                st.caption("📌 수신자 정보")
                # [강화] 업체명 사수를 위해 세션 상태와 직접 결합
                f_client = st.text_input("상호", value=st.session_state['w_client'], key="final_client")
                c_1, c_2 = st.columns(2)
                f_ref = c_1.text_input("참조", value=st.session_state.get('w_manager',''), key="final_manager")
                f_tel = c_2.text_input("연락처", value=st.session_state.get('w_contact',''), key="final_contact")
                f_addr = st.text_input("주소(현장)", value=st.session_state['w_loc'], key="final_loc")
            
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
                    if uploaded_file: banner_b64 = image_to_base64(uploaded_file)

            with b3:
                if st.button("💾 견적 저장", type="primary", use_container_width=True):
                    if sel_p != "(신규작성)" and not pending.empty:
                        try:
                            target_row = pending[pending['label'] == sel_p].iloc[0]
                            target_id = str(target_row.get('문의ID', ''))
                            
                            # 실시간 계산
                            s_amt = int(edited_df['매출합계'].sum())
                            c_amt = int(edited_df['매입합계'].sum())
                            
                            # 부대비용 합계
                            additional_total = st.session_state.get('additional_costs', pd.DataFrame())['금액'].sum() if 'additional_costs' in st.session_state else 0
                            
                            # 공급가액 = 직원비 + 부대비용
                            total_supply = s_amt + int(additional_total)
                            v_amt = int(total_supply * 0.1) if vat_yn else 0
                            
                            # [업체명 사수 최종 전략]
                            # 위젯 값(f_client)이 없으면 세션값을, 그것도 없으면 타겟 정보를 사용
                            final_save_name = f_client if f_client else st.session_state.get('w_client', target_row.get('업체명', ''))
                            
                            # 메타데이터 수집
                            metadata = {
                                "현장명": st.session_state.get('w_event', ''),
                                "책임자": target_row.get('담당자', ''),
                                "현장주소": target_row.get('행사장소', '')
                            }
                            
                            est_package = {
                                "문의ID": target_id,
                                "업체명": final_save_name,
                                "행사명": st.session_state.get('w_event', ''),
                                "공급가액": total_supply,
                                "부가세": v_amt,
                                "합계금액": total_supply + v_amt,
                                "매입원가": c_amt,
                                "부대비용": int(additional_total)
                            }
                            
                            with st.spinner("🚀 데이터 파이프라인 동기화 중..."):
                                if db.save_estimate_details(est_package, metadata=metadata):
                                    db.update_status(target_id, sc.STATUS_FLOW[1])  # '견적'
                                    st.balloons()
                                    st.success(f"✅ {final_save_name} 저장 완료!")
                                    time.sleep(1.5)
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("❌ 시트 저장 실패. 터미널 로그를 확인하세요.")
                        except Exception as e:
                            st.error(f"⚠️ 시스템 오류: {e}")
                    else:
                        st.warning("⚠️ 프로젝트를 먼저 선택하세요.")

        with col_view:
            st.markdown("### 📄 미리보기 (Preview)")
            final_supply = edited_df['매출합계'].sum() if not edited_df.empty else 0
            date_range_txt = f"{st.session_state['w_sdate']} ~ {st.session_state['w_edate']}"
            
            # 부대비용 표시
            additional_costs_df = st.session_state.get('additional_costs', pd.DataFrame())
            if not additional_costs_df.empty:
                st.markdown("#### 🛒 부대비용 상세")
                st.dataframe(additional_costs_df, use_container_width=True, hide_index=True)
                total_additional = additional_costs_df['금액'].sum()
                st.metric("부대비용 합계", f"{total_additional:,}원")
            else:
                total_additional = 0
            
            # 미리보기에서도 사수된 업체명 사용
            client_dict = {
                "name": f_client if f_client else st.session_state.get('w_client', ''),
                "ref": f_ref, "tel": f_tel, "addr": f_addr, 
                "date_range": date_range_txt, "date": datetime.now().strftime("%Y-%m-%d")
            }
            supplier_dict = {"reg_no": "429-88-01469", "name": "(주)가디어스", "ceo": "최규성", "tel": "1600-2944", "addr": "서울시 종로구 능망산1길 2, 1층"}
            # 부대비용 포함하여 전달
            total_additional = additional_costs_df['금액'].sum() if not additional_costs_df.empty else 0
            html_quote = ue.get_customer_quote_html(edited_df, client_dict, supplier_dict, final_supply, vat_yn, t_top, t_side, banner_b64, additional_costs_df, total_additional)
            st.components.v1.html(html_quote, height=950, scrolling=True)

    # --- TAB 3: 상세 수익 리포트 ---
    with tab3:
        c1, c2 = st.columns([1, 2.5])
        with c1:
            st.info("📝 결재 메모 작성")
            n1 = st.text_area("1. 전략", height=80)
            n2 = st.text_area("2. 인력", height=80)
            n3 = st.text_area("3. 리스크", height=80)
            n4 = st.text_area("4. 결론", height=80)
        with c2:
            # 리포트에서도 세션 상태의 업체명을 우선 참조하도록 utils 호출
            html_rep = ue.get_detailed_report_html(st.session_state['est_items'], st.session_state.get('w_client', ''), [n1, n2, n3, n4])
            st.components.v1.html(html_rep, height=1000, scrolling=True)