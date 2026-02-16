# page_project_detail.py  v1.0
"""
프로젝트 상세확인 — 고객관리 카드
- 전체 프로젝트 흐름을 한눈에 확인
- 접수 → 견적 → 체결 → 배정 → 진행 → 완료 → 정산 단계별 정보 표시
- 고객 카드 (거래처 관리) 기능
"""
import streamlit as st
import pandas as pd
import data_loader as db
import status_config as sc
from datetime import datetime


def _safe(val, default='—'):
    """안전한 값 출력"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    s = str(val).strip()
    return s if s and s not in ('nan', 'None', '') else default


def _safe_int(val, default=0):
    try:
        n = pd.to_numeric(val, errors='coerce')
        return default if pd.isna(n) else int(n)
    except:
        return default


def show(data):
    st.markdown("""
    <style>
        .block-container { max-width: 95% !important; padding-top: 1rem; }
        .project-card {
            border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px;
            background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            margin-bottom: 16px;
        }
        .flow-step {
            display: inline-block; padding: 6px 14px; border-radius: 20px;
            margin: 3px 2px; font-size: 13px; font-weight: 600;
        }
        .flow-active { background: #2563eb; color: white; }
        .flow-done { background: #10b981; color: white; }
        .flow-pending { background: #f3f4f6; color: #9ca3af; }
        .customer-card {
            border: 2px solid #8b5cf6; border-radius: 12px; padding: 24px;
            background: linear-gradient(135deg, #faf5ff 0%, #ede9fe 100%);
            margin-bottom: 20px;
        }
        .info-row { display: flex; margin-bottom: 8px; }
        .info-label { font-weight: 700; color: #6b7280; width: 120px; flex-shrink: 0; }
        .info-value { color: #111827; }
        .section-header { 
            font-size: 16px; font-weight: 700; color: #1e40af;
            border-bottom: 2px solid #dbeafe; padding-bottom: 6px; margin: 16px 0 12px 0;
        }
    </style>
    """, unsafe_allow_html=True)

    st.title("🔍 프로젝트 상세확인")
    st.caption("프로젝트 전체 흐름과 고객 정보를 한눈에 확인합니다.")

    df_inq = data.get('inq', pd.DataFrame())
    if df_inq.empty:
        st.warning("📭 문의 데이터가 없습니다.")
        return

    df_inq = df_inq.fillna('').copy()

    # ─── 필터 ───
    col_f1, col_f2, col_f3 = st.columns([1.5, 1, 1])
    with col_f1:
        # 검색어
        search_q = st.text_input("🔎 검색 (업체명 / 행사명 / 문의ID)", key="proj_detail_search")
    with col_f2:
        # 상태 필터
        all_statuses = ['전체'] + sc.STATUS_FLOW + sc.STATUS_EXIT
        status_col = '상태' if '상태' in df_inq.columns else None
        sel_status = st.selectbox("📌 상태 필터", all_statuses, key="proj_detail_status")
    with col_f3:
        sort_order = st.selectbox("정렬", ["최신순", "오래된순"], key="proj_detail_sort")

    # 필터링 적용
    filtered = df_inq.copy()
    if search_q:
        q_lower = search_q.lower()
        mask = filtered.apply(lambda r: any(q_lower in str(v).lower() for v in r.values), axis=1)
        filtered = filtered[mask]
    if sel_status != '전체' and status_col:
        filtered = filtered[filtered[status_col].astype(str).str.strip() == sel_status]

    # 정렬
    sort_col = '문의날짜' if '문의날짜' in filtered.columns else '일시' if '일시' in filtered.columns else None
    if sort_col:
        filtered = filtered.sort_values(sort_col, ascending=(sort_order == "오래된순"))

    st.markdown(f"**총 {len(filtered)}건**")

    if filtered.empty:
        st.info("조건에 맞는 프로젝트가 없습니다.")
        return

    # ─── 프로젝트 선택 (카드 목록) ───
    # 카드 그리드  (3열)
    cols_grid = st.columns(3)
    card_items = filtered.head(30).reset_index(drop=True)

    for idx, row in card_items.iterrows():
        col = cols_grid[idx % 3]
        with col:
            inq_id = _safe(row.get('문의ID'))
            company = _safe(row.get('업체명', row.get('업체', '')))
            event = _safe(row.get('행사명', ''))
            cur_status = _safe(row.get(status_col, '접수') if status_col else '접수')
            cfg = sc.STATUS_CONFIG.get(cur_status, sc.STATUS_CONFIG.get('접수'))
            icon = cfg.get('icon', '📋')
            bg = cfg.get('bg', '#f3f4f6')
            color = cfg.get('color', '#333')

            st.markdown(f"""
            <div style="border:1px solid {color}; border-left:5px solid {color}; border-radius:8px;
                        padding:12px; margin-bottom:8px; background:{bg};">
                <div style="font-size:13px; color:#6b7280;">{inq_id}</div>
                <div style="font-size:16px; font-weight:700; margin:4px 0;">{icon} {company}</div>
                <div style="font-size:13px; color:#374151;">{event}</div>
                <div style="margin-top:6px;">
                    <span style="background:{color}; color:white; padding:3px 10px; border-radius:12px; font-size:12px;">{cur_status}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("📋 상세보기", key=f"detail_card_{idx}", use_container_width=True):
                st.session_state['proj_detail_sel'] = inq_id

    st.divider()

    # ─── 선택된 프로젝트 상세 ───
    sel_id = st.session_state.get('proj_detail_sel')
    if not sel_id:
        st.info("💡 위 카드에서 프로젝트를 선택해주세요.")
        return

    # 해당 프로젝트 데이터 로드
    sel_rows = df_inq[df_inq['문의ID'].astype(str).str.strip() == str(sel_id).strip()]
    if sel_rows.empty:
        st.warning(f"문의ID '{sel_id}'를 찾을 수 없습니다.")
        return

    row = sel_rows.iloc[0]
    company = _safe(row.get('업체명', row.get('업체', '')))
    event = _safe(row.get('행사명', ''))
    cur_status = str(row.get(status_col, '접수')).strip() if status_col else '접수'

    # ━━━ 1. 고객 관리 카드 ━━━
    st.markdown(f"## 🏢 {company} — {event}")

    st.markdown('<div class="customer-card">', unsafe_allow_html=True)
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        st.markdown("##### 👤 고객 정보")
        st.write(f"**업체명:** {company}")
        st.write(f"**담당자:** {_safe(row.get('담당자명', row.get('담당자', '')))}")
        st.write(f"**연락처:** {_safe(row.get('연락처', row.get('전화번호', '')))}")
        st.write(f"**이메일:** {_safe(row.get('이메일', ''))}")
    with cc2:
        st.markdown("##### 📅 행사 정보")
        st.write(f"**행사명:** {event}")
        st.write(f"**일시:** {_safe(row.get('행사시작일', row.get('일시', '')))}")
        end_d = _safe(row.get('행사종료일', ''))
        if end_d != '—':
            st.write(f"**종료일:** {end_d}")
        st.write(f"**장소:** {_safe(row.get('행사장소', row.get('장소', '')))}")
        st.write(f"**인원:** {_safe(row.get('요청인원', row.get('인원', '')))}명")
    with cc3:
        st.markdown("##### 💼 사업자 정보")
        # 견적상세에서 사업자 정보 조회
        df_est = data.get('estimate', pd.DataFrame())
        biz_info = {}
        if not df_est.empty and '문의ID' in df_est.columns:
            est_matches = df_est[df_est['문의ID'].astype(str).str.strip() == str(sel_id).strip()]
            if not est_matches.empty:
                er = est_matches.iloc[0]
                biz_info = {
                    '사업자번호': _safe(er.get('사업자번호', '')),
                    '대표자': _safe(er.get('대표자', '')),
                }
        st.write(f"**사업자번호:** {biz_info.get('사업자번호', '—')}")
        st.write(f"**대표자:** {biz_info.get('대표자', '—')}")
        # 정산 시트에서 입금 정보
        try:
            disp = db.load_dispatch_data()
            sdf = disp.get('settlement', pd.DataFrame())
            if not sdf.empty and '문의ID' in sdf.columns:
                sm = sdf[sdf['문의ID'].astype(str).str.strip() == str(sel_id).strip()]
                if not sm.empty:
                    sr = sm.iloc[0]
                    st.write(f"**청구액:** ₩{_safe_int(sr.get('공급가액', 0)):,}")
                    st.write(f"**입금액:** ₩{_safe_int(sr.get('받은금액', 0)):,}")
        except:
            pass
    st.markdown('</div>', unsafe_allow_html=True)

    # ━━━ 2. 프로젝트 흐름 타임라인 ━━━
    st.markdown('<div class="section-header">📊 프로젝트 흐름</div>', unsafe_allow_html=True)

    try:
        cur_idx = sc.STATUS_FLOW.index(cur_status)
    except ValueError:
        cur_idx = -1

    flow_html = '<div style="text-align:center; margin:12px 0;">'
    for i, step in enumerate(sc.STATUS_FLOW):
        cfg_s = sc.STATUS_CONFIG.get(step, {})
        icon_s = cfg_s.get('icon', '')
        if i < cur_idx:
            cls = "flow-done"
        elif i == cur_idx:
            cls = "flow-active"
        else:
            cls = "flow-pending"
        arrow = ' → ' if i < len(sc.STATUS_FLOW) - 1 else ''
        flow_html += f'<span class="flow-step {cls}">{icon_s} {step}</span>{arrow}'
    flow_html += '</div>'
    st.markdown(flow_html, unsafe_allow_html=True)

    progress_pct = int((cur_idx + 1) / len(sc.STATUS_FLOW) * 100) if cur_idx >= 0 else 0
    st.progress(progress_pct / 100, text=f"진행률 {progress_pct}%")

    # ━━━ 3. 단계별 상세 정보 탭 ━━━
    tab_inq, tab_est, tab_contract, tab_assign, tab_settle = st.tabs([
        "📞 접수/문의", "🧮 견적", "📝 계약/체결", "👷 인력배정", "💰 정산"
    ])

    # Tab 1: 접수/문의
    with tab_inq:
        st.markdown("##### 📞 문의 접수 정보")
        info_cols = ['문의ID', '문의날짜', '일시', '업체명', '행사명', '행사장소', '장소',
                     '요청인원', '인원', '담당자명', '담당자', '연락처', '전화번호',
                     '이메일', '행사시작일', '행사종료일', '요청사항', '특이사항', '비고']
        info_data = {}
        for c in info_cols:
            v = _safe(row.get(c, ''))
            if v != '—':
                info_data[c] = v
        if info_data:
            df_info = pd.DataFrame(list(info_data.items()), columns=['항목', '내용'])
            st.dataframe(df_info, use_container_width=True, hide_index=True)
        else:
            st.info("접수 정보가 없습니다.")

    # Tab 2: 견적
    with tab_est:
        st.markdown("##### 🧮 견적 정보")
        df_est = data.get('estimate', pd.DataFrame())
        if not df_est.empty and '문의ID' in df_est.columns:
            est_rows = df_est[df_est['문의ID'].astype(str).str.strip() == str(sel_id).strip()]
            if not est_rows.empty:
                er = est_rows.iloc[0]
                e1, e2 = st.columns(2)
                with e1:
                    st.metric("공급가액", f"₩{_safe_int(er.get('공급가액', 0)):,}")
                    st.metric("매입원가", f"₩{_safe_int(er.get('매입원가', 0)):,}")
                with e2:
                    st.metric("예상수익", f"₩{_safe_int(er.get('예상수익', 0)):,}")
                    margin = _safe_int(er.get('수익률', 0))
                    st.metric("수익률", f"{margin}%")

                # 견적 품목
                try:
                    items_df = db.load_estimate_items(sel_id)
                    if items_df is not None and not items_df.empty:
                        st.markdown("##### 📦 견적 품목 상세")
                        st.dataframe(items_df, use_container_width=True, hide_index=True)
                except:
                    pass
            else:
                st.info("견적 데이터가 없습니다.")
        else:
            st.info("견적 데이터가 없습니다.")

    # Tab 3: 계약/체결
    with tab_contract:
        st.markdown("##### 📝 계약 정보")
        contract_info = {}
        for c in ['계약일', '체결일', '계약금액', '계약상태', '사업자번호', '대표자', '업종', '주소']:
            v = ''
            if not df_est.empty and '문의ID' in df_est.columns:
                em = df_est[df_est['문의ID'].astype(str).str.strip() == str(sel_id).strip()]
                if not em.empty:
                    v = _safe(em.iloc[0].get(c, ''))
            if v == '—':
                v = _safe(row.get(c, ''))
            if v != '—':
                contract_info[c] = v

        if contract_info:
            for k, v in contract_info.items():
                st.write(f"**{k}:** {v}")
        else:
            if cur_idx >= 2:  # 체결 이후
                st.success("✅ 계약 체결 완료")
            else:
                st.info("아직 계약 단계에 도달하지 않았습니다.")

    # Tab 4: 인력배정
    with tab_assign:
        st.markdown("##### 👷 배정된 인력")
        try:
            assign_df = db.get_assignments_by_inquiry(sel_id)
            if assign_df is not None and not assign_df.empty:
                display_assign_cols = []
                for c in ['인력명', '이름', '직무', '역할', '연락처', '지급단가', '단가', '근무일수', '일수', '총지급액', '지급상태']:
                    if c in assign_df.columns and c not in display_assign_cols:
                        display_assign_cols.append(c)
                if display_assign_cols:
                    st.dataframe(assign_df[display_assign_cols], use_container_width=True, hide_index=True)
                else:
                    st.dataframe(assign_df, use_container_width=True, hide_index=True)
                st.metric("배정 인원", f"{len(assign_df)}명")
            else:
                if cur_idx >= 3:
                    st.success("✅ 배정 완료 (데이터 조회 실패)")
                else:
                    st.info("아직 인력이 배정되지 않았습니다.")
        except:
            st.info("배정 데이터를 조회할 수 없습니다.")

    # Tab 5: 정산
    with tab_settle:
        st.markdown("##### 💰 정산 현황")
        try:
            disp_data = db.load_dispatch_data()
            s_df = disp_data.get('settlement', pd.DataFrame())
            if not s_df.empty and '문의ID' in s_df.columns:
                s_match = s_df[s_df['문의ID'].astype(str).str.strip() == str(sel_id).strip()]
                if not s_match.empty:
                    sr = s_match.iloc[0]
                    s1, s2, s3, s4 = st.columns(4)
                    supply = _safe_int(sr.get('공급가액', 0))
                    tax = _safe_int(sr.get('부가세', 0))
                    paid = _safe_int(sr.get('받은금액', 0))
                    balance = _safe_int(sr.get('잔액', 0))
                    with s1:
                        st.metric("공급가액", f"₩{supply:,}")
                    with s2:
                        st.metric("부가세", f"₩{tax:,}")
                    with s3:
                        st.metric("받은금액", f"₩{paid:,}")
                    with s4:
                        st.metric("잔액", f"₩{balance:,}")
                    status_settle = _safe(sr.get('진행상황', ''))
                    if status_settle != '—':
                        st.write(f"**진행상황:** {status_settle}")
                else:
                    st.info("정산 데이터가 없습니다.")
            else:
                st.info("정산 데이터가 없습니다.")
        except:
            st.info("정산 데이터를 조회할 수 없습니다.")

    # ━━━ 4. 메모/히스토리 ━━━
    st.divider()
    st.markdown("##### ✏️ 프로젝트 메모")
    memo_key = f"proj_memo_{sel_id}"
    memo = st.text_area(
        "메모 입력",
        value=st.session_state.get(memo_key, ''),
        placeholder="이 프로젝트에 대한 메모를 입력하세요...",
        key=f"memo_input_{sel_id}"
    )
    if st.button("💾 메모 저장", key=f"save_memo_{sel_id}"):
        st.session_state[memo_key] = memo
        st.success("메모가 저장되었습니다.")
