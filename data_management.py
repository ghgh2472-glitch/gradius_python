# -*- coding: utf-8 -*-
"""
📋 데이터 관리 도구
- 전체 리셋 (STAFF/고객정보/Roles/Factors/Guides 제외)
- 문의ID별 관련 데이터 일괄 삭제
"""

import streamlit as st
import pandas as pd
import data_loader as db


# 리셋 대상 시트 (데이터 행만 삭제, 헤더는 보존)
RESET_SHEETS = [
    "문의작성",
    "견적상세",
    "견적품목",
    "배정기록",
    "계약건은청구금액적기",
    "지급내역",
    "평가표",
    "고객정보",
]

# 절대 건드리면 안되는 시트
PROTECTED_SHEETS = [
    "STAFF",
    "Roles",
    "Factors",
    "Guides",
]


def reset_all_data(selected_sheets=None):
    """
    선택된 시트들의 데이터를 리셋 (헤더 1행 보존, 데이터 행 삭제)
    selected_sheets: None이면 RESET_SHEETS 전체, 지정하면 해당 시트만
    """
    client = db.get_connection()
    if not client:
        return False, "Google Sheets 연결 실패"

    target = selected_sheets or RESET_SHEETS
    results = []

    try:
        sh = client.open_by_key(db.SHEET_ID)

        for sheet_name in target:
            if sheet_name in PROTECTED_SHEETS:
                results.append(f"⛔ {sheet_name} — 보호된 시트 (건너뜀)")
                continue
            try:
                wks = sh.worksheet(sheet_name)
                all_vals = wks.get_all_values()

                if len(all_vals) <= 1:
                    results.append(f"⏭️ {sheet_name} — 이미 비어있음")
                    continue

                # 헤더 보존, 데이터 행 삭제
                data_rows = len(all_vals) - 1
                # 2행부터 끝까지 삭제 (batch clear)
                last_col = chr(64 + len(all_vals[0])) if len(all_vals[0]) <= 26 else "Z"
                range_str = f"A2:{last_col}{len(all_vals)}"
                wks.batch_clear([range_str])

                results.append(f"✅ {sheet_name} — {data_rows}행 삭제 완료")
            except Exception as e:
                if 'not found' in str(e).lower():
                    results.append(f"⏭️ {sheet_name} — 시트 없음 (건너뜀)")
                else:
                    results.append(f"❌ {sheet_name} — 오류: {str(e)[:50]}")

        db.invalidate_data()
        return True, results

    except Exception as e:
        return False, f"오류: {e}"


def delete_by_inquiry_id(inquiry_id: str):
    """
    특정 문의ID에 관련된 모든 데이터를 삭제
    대상: 문의작성, 견적상세, 견적품목, 배정기록, 계약건은청구금액적기, 지급내역, 평가표
    """
    client = db.get_connection()
    if not client:
        return False, "Google Sheets 연결 실패"

    inquiry_id = str(inquiry_id).strip()
    if not inquiry_id:
        return False, "문의ID가 비어있습니다"

    # 각 시트별 문의ID가 있을 수 있는 컬럼명
    sheet_id_cols = {
        "문의작성": "문의ID",
        "견적상세": "문의ID",
        "견적품목": "문의ID",
        "배정기록": "문의ID",
        "계약건은청구금액적기": "문의ID",
        "지급내역": "문의ID",
        "평가표": "문의ID",
    }

    results = []
    total_deleted = 0

    try:
        sh = client.open_by_key(db.SHEET_ID)

        for sheet_name, id_col in sheet_id_cols.items():
            try:
                wks = sh.worksheet(sheet_name)
                all_vals = wks.get_all_values()

                if len(all_vals) <= 1:
                    continue

                headers = [str(h).strip() for h in all_vals[0]]

                # 문의ID 컬럼 찾기
                col_idx = None
                for possible_col in [id_col, '문의ID', 'inquiry_id']:
                    if possible_col in headers:
                        col_idx = headers.index(possible_col)
                        break

                if col_idx is None:
                    results.append(f"⏭️ {sheet_name} — 문의ID 컬럼 없음")
                    continue

                # 매칭 행 찾기 (역순으로 삭제해야 인덱스가 안 밀림)
                rows_to_delete = []
                for ri in range(1, len(all_vals)):
                    cell_val = str(all_vals[ri][col_idx]).strip()
                    if cell_val == inquiry_id:
                        rows_to_delete.append(ri + 1)  # 1-based

                if not rows_to_delete:
                    continue

                # 역순 삭제 (아래 행부터 삭제해야 행 번호 안 밀림)
                for row_num in sorted(rows_to_delete, reverse=True):
                    wks.delete_rows(row_num)

                deleted = len(rows_to_delete)
                total_deleted += deleted
                results.append(f"✅ {sheet_name} — {deleted}행 삭제")

            except Exception as e:
                if 'not found' in str(e).lower():
                    continue
                results.append(f"❌ {sheet_name} — 오류: {str(e)[:50]}")

        db.invalidate_data()
        return True, results, total_deleted

    except Exception as e:
        return False, f"오류: {e}", 0


def get_all_inquiry_ids():
    """문의작성 시트에서 모든 문의ID + 업체명 + 행사명 조회"""
    client = db.get_connection()
    if not client:
        return []

    try:
        sh = client.open_by_key(db.SHEET_ID)
        wks = sh.worksheet("문의작성")
        records = wks.get_all_records()
        if not records:
            return []
        df = pd.DataFrame(records)
        if '문의ID' not in df.columns:
            return []

        items = []
        for _, row in df.iterrows():
            iid = str(row.get('문의ID', '')).strip()
            client_name = str(row.get('업체명', '')).strip()
            event = str(row.get('행사명', '')).strip()
            status = str(row.get('상태', '')).strip()
            if iid:
                items.append({
                    'id': iid,
                    'label': f"{iid} | {client_name} — {event} [{status}]"
                })
        return items
    except Exception:
        return []


# ==============================================================================
# Streamlit UI
# ==============================================================================

def show_data_management():
    """데이터 관리 UI — 사이드바 또는 별도 페이지에서 호출"""
    st.markdown("## 🛠️ 데이터 관리")
    st.caption("⚠️ 이 기능은 되돌릴 수 없습니다. 신중하게 사용하세요.")

    tab_reset, tab_delete = st.tabs(["🗑️ 전체 리셋", "🔍 문의ID별 삭제"])

    # ── 전체 리셋 ──
    with tab_reset:
        st.markdown("### 전체 데이터 리셋")
        st.warning("⚠️ STAFF, 고객정보, Roles, Factors, Guides는 보호됩니다.")

        selected = st.multiselect(
            "리셋할 시트 선택",
            RESET_SHEETS,
            default=RESET_SHEETS,
            key="reset_sheets"
        )

        st.markdown("**리셋 대상:**")
        for s in selected:
            st.markdown(f"- 📋 {s}")

        st.markdown("---")
        confirm_text = st.text_input(
            "확인을 위해 '리셋' 이라고 입력하세요",
            key="reset_confirm"
        )

        if st.button("🗑️ 데이터 리셋 실행", type="primary", key="do_reset",
                      disabled=(confirm_text != "리셋")):
            with st.spinner("데이터를 리셋하는 중..."):
                success, results = reset_all_data(selected)
                if success:
                    st.balloons()
                    st.success("✅ 리셋 완료!")
                    for r in results:
                        st.markdown(f"  {r}")
                else:
                    st.error(f"❌ {results}")

    # ── 문의ID별 삭제 ──
    with tab_delete:
        st.markdown("### 문의ID별 데이터 삭제")
        st.info("💡 특정 문의에 관련된 모든 데이터(견적/배정/지급 등)를 한번에 삭제합니다.")

        # 문의 목록 로드
        if st.button("🔄 문의 목록 불러오기", key="load_inquiries"):
            st.session_state['_inq_list'] = get_all_inquiry_ids()

        inq_list = st.session_state.get('_inq_list', [])

        if inq_list:
            st.markdown(f"**총 {len(inq_list)}건의 문의**")

            # 다중 선택
            selected_ids = st.multiselect(
                "삭제할 문의 선택 (복수 선택 가능)",
                [item['label'] for item in inq_list],
                key="del_inquiries"
            )

            if selected_ids:
                st.warning(f"⚠️ 선택된 {len(selected_ids)}건의 문의 관련 데이터가 모두 삭제됩니다.")
                st.markdown("**삭제 대상 시트:** 문의작성, 견적상세, 견적품목, 배정기록, 계약건, 지급내역, 평가표")

                confirm_del = st.text_input(
                    "확인을 위해 '삭제' 라고 입력하세요",
                    key="del_confirm"
                )

                if st.button("🗑️ 선택 문의 삭제 실행", type="primary", key="do_delete",
                              disabled=(confirm_del != "삭제")):
                    total = 0
                    all_results = []
                    with st.spinner("데이터를 삭제하는 중..."):
                        for sel_label in selected_ids:
                            # label에서 문의ID 추출
                            iid = sel_label.split(" | ")[0].strip()
                            success, results, count = delete_by_inquiry_id(iid)
                            total += count
                            if success and results:
                                all_results.append(f"**{iid}:**")
                                all_results.extend([f"  {r}" for r in results])

                    if total > 0:
                        st.success(f"✅ 총 {total}행 삭제 완료!")
                        for r in all_results:
                            st.markdown(r)
                        st.session_state['_inq_list'] = get_all_inquiry_ids()
                    else:
                        st.info("삭제할 데이터가 없습니다.")
        else:
            st.caption("👆 '문의 목록 불러오기' 버튼을 눌러주세요")

        # 직접 입력
        st.divider()
        st.markdown("##### 직접 문의ID 입력")
        manual_id = st.text_input("문의ID", placeholder="예: INQ-240101-abc123", key="manual_del_id")
        if st.button("🗑️ 이 문의 삭제", key="manual_delete") and manual_id.strip():
            with st.spinner("삭제 중..."):
                success, results, count = delete_by_inquiry_id(manual_id.strip())
                if success and count > 0:
                    st.success(f"✅ {manual_id} — 총 {count}행 삭제 완료!")
                    for r in results:
                        st.markdown(f"  {r}")
                elif success:
                    st.info(f"'{manual_id}'에 해당하는 데이터가 없습니다.")
                else:
                    st.error(f"❌ {results}")
