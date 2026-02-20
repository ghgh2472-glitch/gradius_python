# page_search.py - 스마트 데이터 조회
import streamlit as st
import pandas as pd
import data_loader as db
from datetime import datetime, timedelta
from io import BytesIO

# ==============================================================================
# 0. 스타일
# ==============================================================================
def apply_styles():
    st.markdown("""
    <style>
        .search-header {
            background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
            border-radius: 14px; padding: 28px 32px; color: white;
            margin-bottom: 24px; box-shadow: 0 4px 16px rgba(37,99,235,0.25);
        }
        .search-header h2 { margin: 0 0 6px 0; font-size: 26px; }
        .search-header p  { margin: 0; opacity: 0.85; font-size: 14px; }

        .preset-btn {
            display: inline-block; padding: 8px 18px; margin: 4px;
            border-radius: 20px; font-size: 13px; font-weight: 600;
            cursor: pointer; transition: all 0.2s; border: none;
        }
        .result-card {
            background: white; border-radius: 12px; padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.06); margin-bottom: 16px;
        }
        .stat-pill {
            display: inline-block; background: #eff6ff; color: #1e40af;
            padding: 6px 14px; border-radius: 16px; font-weight: 700;
            font-size: 14px; margin-right: 8px;
        }
        .kpi-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
        .kpi-box {
            flex: 1; min-width: 140px; border-radius: 10px; padding: 14px 18px;
            text-align: center; color: white; box-shadow: 0 2px 8px rgba(0,0,0,0.10);
        }
        .kpi-box .label { font-size: 12px; opacity: 0.9; }
        .kpi-box .value { font-size: 22px; font-weight: 800; }
    </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# 1. 유틸리티
# ==============================================================================
def safe_int(val):
    """숫자 안전 변환"""
    try:
        if pd.isna(val) or val == "":
            return 0
        if isinstance(val, str):
            return int(float(val.replace(",", "").replace("원", "").replace("명", "").strip() or 0))
        return int(float(val))
    except:
        return 0


def fmt_money(val):
    """금액 포맷"""
    v = safe_int(val)
    if abs(v) >= 1_0000_0000:
        return f"{v / 1_0000_0000:.1f}억"
    if abs(v) >= 1_0000:
        return f"{v / 1_0000:,.0f}만"
    return f"{v:,}"


def fmt_won(val):
    """원 단위 표기"""
    return f"{safe_int(val):,}원"


def to_excel(df, sheet_name="조회결과"):
    """DataFrame → 엑셀 바이트"""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)
    return buf.getvalue()


def parse_month_year(text):
    """텍스트에서 년/월 추출. 없으면 현재 년월 반환."""
    import re
    now = datetime.now()
    # 2026년 2월, 2026-02, 26년2월...
    m = re.search(r'(\d{4})\s*[년\-/\.]\s*(\d{1,2})', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # 2월, 3월...
    m = re.search(r'(\d{1,2})\s*월', text)
    if m:
        return now.year, int(m.group(1))
    return now.year, now.month


def filter_by_month(df, date_col, year, month):
    """날짜 컬럼 기준 월 필터"""
    if date_col not in df.columns:
        return df
    df = df.copy()
    df["_parsed_date"] = pd.to_datetime(df[date_col].astype(str).str.split("~").str[0].str.strip(),
                                         errors="coerce", format="mixed")
    mask = (df["_parsed_date"].dt.year == year) & (df["_parsed_date"].dt.month == month)
    result = df[mask].drop(columns=["_parsed_date"], errors="ignore")
    return result


# ==============================================================================
# 2. 프리셋 검색 함수들
# ==============================================================================
def query_monthly_revenue(data, year, month):
    """이번달/특정월 매출 조회"""
    dispatch_data = db.load_dispatch_data()
    df_settle = dispatch_data.get("settlement", pd.DataFrame())

    if df_settle.empty:
        return None, "정산 데이터가 없습니다."

    df_month = filter_by_month(df_settle, "파견일자", year, month)

    if df_month.empty:
        return None, f"{year}년 {month}월 정산 데이터가 없습니다."

    # KPI 계산
    total_billing = df_month["청구금액"].apply(safe_int).sum()
    total_supply = df_month["공급가액"].apply(safe_int).sum()
    total_vat = df_month["부가세"].apply(safe_int).sum()
    total_paid_staff = df_month["지급액"].apply(safe_int).sum() if "지급액" in df_month.columns else 0
    total_received = df_month["받은금액"].apply(safe_int).sum() if "받은금액" in df_month.columns else 0
    total_profit = df_month["이익"].apply(safe_int).sum() if "이익" in df_month.columns else total_supply - total_paid_staff

    summary = {
        "제목": f"📊 {year}년 {month}월 매출 현황",
        "kpi": [
            {"label": "청구금액(VAT포함)", "value": fmt_won(total_billing), "color": "#2563eb"},
            {"label": "공급가액", "value": fmt_won(total_supply), "color": "#7c3aed"},
            {"label": "부가세", "value": fmt_won(total_vat), "color": "#6366f1"},
            {"label": "인력지급액", "value": fmt_won(total_paid_staff), "color": "#dc2626"},
            {"label": "이익", "value": fmt_won(total_profit), "color": "#059669"},
            {"label": "입금액", "value": fmt_won(total_received), "color": "#0891b2"},
        ],
        "table": df_month[["문의ID", "현장명", "업체", "파견일자", "청구금액",
                           "공급가액", "부가세", "받은금액", "잔액", "진행상황"]].copy()
                          if all(c in df_month.columns for c in ["문의ID", "현장명"]) else df_month,
        "count": len(df_month),
    }
    return summary, None


def query_payment_history(data, year, month):
    """지급내역 (세무사 전달용)"""
    dispatch_data = db.load_dispatch_data()
    df_disp = dispatch_data.get("dispatch", pd.DataFrame())

    if df_disp.empty:
        return None, "배정 데이터가 없습니다."

    # 확정된 건만
    status_col = None
    for c in ["지급상태", "상태"]:
        if c in df_disp.columns:
            status_col = c
            break

    if status_col:
        df_confirmed = df_disp[df_disp[status_col].astype(str).str.contains("확정", na=False)].copy()
    else:
        df_confirmed = df_disp.copy()

    # 월 필터
    date_col = None
    for c in ["배정일시", "투입시작일"]:
        if c in df_confirmed.columns:
            date_col = c
            break

    if date_col:
        df_month = filter_by_month(df_confirmed, date_col, year, month)
    else:
        df_month = df_confirmed

    if df_month.empty:
        return None, f"{year}년 {month}월 지급 내역이 없습니다."

    # 지급액 계산
    df_month["_지급단가"] = df_month["지급단가"].apply(safe_int) if "지급단가" in df_month.columns else 0
    df_month["_근무일수"] = df_month["근무일수"].apply(safe_int) if "근무일수" in df_month.columns else 0
    df_month["_총지급액"] = df_month["총지급액"].apply(safe_int) if "총지급액" in df_month.columns else df_month["_지급단가"] * df_month["_근무일수"]

    total_pay = df_month["_총지급액"].sum()
    tax_33 = int(total_pay * 0.033)
    net_pay = total_pay - tax_33

    # 표시 컬럼
    show_cols = [c for c in ["행사명", "인력명", "직무", "지급단가", "근무일수", "총지급액",
                              "주민등록번호", "은행명", "계좌번호", "배정일시", "투입시작일", "투입종료일"]
                 if c in df_month.columns]

    summary = {
        "제목": f"💸 {year}년 {month}월 지급내역 (세무용)",
        "kpi": [
            {"label": "총 지급액", "value": fmt_won(total_pay), "color": "#dc2626"},
            {"label": "3.3% 원천징수", "value": fmt_won(tax_33), "color": "#f59e0b"},
            {"label": "실지급액", "value": fmt_won(net_pay), "color": "#059669"},
            {"label": "지급 인원", "value": f"{len(df_month)}명", "color": "#6366f1"},
        ],
        "table": df_month[show_cols].sort_values(by=show_cols[0] if show_cols else df_month.columns[0]),
        "count": len(df_month),
        "excel_name": f"지급내역_{year}년{month}월",
    }
    return summary, None


def query_top_jobs(data):
    """가장 많이 파견된 직군 랭킹"""
    dispatch_data = db.load_dispatch_data()
    df_disp = dispatch_data.get("dispatch", pd.DataFrame())

    if df_disp.empty or "직무" not in df_disp.columns:
        return None, "배정 데이터에 직무 정보가 없습니다."

    # 확정 건만
    status_col = None
    for c in ["지급상태", "상태"]:
        if c in df_disp.columns:
            status_col = c
            break

    if status_col:
        df_confirmed = df_disp[df_disp[status_col].astype(str).str.contains("확정|배정", na=False)].copy()
    else:
        df_confirmed = df_disp.copy()

    df_confirmed = df_confirmed[df_confirmed["직무"].astype(str).str.strip() != ""]

    ranking = (
        df_confirmed.groupby("직무")
        .agg(파견횟수=("직무", "count"),
             총지급액=("총지급액", lambda x: sum(safe_int(v) for v in x)))
        .sort_values("파견횟수", ascending=False)
        .reset_index()
    )
    ranking["평균단가"] = (ranking["총지급액"] / ranking["파견횟수"].replace(0, 1)).apply(lambda x: fmt_won(x))
    ranking["총지급액"] = ranking["총지급액"].apply(fmt_won)

    summary = {
        "제목": "👷 직군별 파견 랭킹",
        "kpi": [
            {"label": "1위 직군", "value": ranking.iloc[0]["직무"] if len(ranking) > 0 else "-", "color": "#f59e0b"},
            {"label": "총 직군 수", "value": f"{len(ranking)}개", "color": "#6366f1"},
            {"label": "총 파견 건수", "value": f"{ranking['파견횟수'].sum()}건", "color": "#2563eb"},
        ],
        "table": ranking,
        "count": len(ranking),
    }
    return summary, None


def query_unpaid(data):
    """미수금 현황"""
    dispatch_data = db.load_dispatch_data()
    df_settle = dispatch_data.get("settlement", pd.DataFrame())

    if df_settle.empty:
        return None, "정산 데이터가 없습니다."

    df_settle["_잔액"] = df_settle["잔액"].apply(safe_int) if "잔액" in df_settle.columns else 0
    df_unpaid = df_settle[df_settle["_잔액"] > 0].copy()

    if df_unpaid.empty:
        return None, "미수금이 없습니다! 🎉"

    total_unpaid = df_unpaid["_잔액"].sum()

    show_cols = [c for c in ["현장명", "업체", "파견일자", "청구금액", "받은금액", "잔액", "진행상황", "입금여부"]
                 if c in df_unpaid.columns]

    summary = {
        "제목": "🚨 미수금 현황",
        "kpi": [
            {"label": "총 미수금", "value": fmt_won(total_unpaid), "color": "#dc2626"},
            {"label": "미수 건수", "value": f"{len(df_unpaid)}건", "color": "#f59e0b"},
        ],
        "table": df_unpaid[show_cols].sort_values(by="잔액" if "잔액" in show_cols else show_cols[0], ascending=False),
        "count": len(df_unpaid),
    }
    return summary, None


def query_company_history(data, company_name):
    """업체별 전체 이력 조회"""
    results = {}

    # 1. 문의
    df_inq = data.get("inq", pd.DataFrame())
    if not df_inq.empty and "업체명" in df_inq.columns:
        matched = df_inq[df_inq["업체명"].astype(str).str.contains(company_name, na=False, case=False)]
        if not matched.empty:
            results["문의"] = matched

    # 2. 견적
    df_est = data.get("estimate", pd.DataFrame())
    if not df_est.empty and "업체명" in df_est.columns:
        matched = df_est[df_est["업체명"].astype(str).str.contains(company_name, na=False, case=False)]
        if not matched.empty:
            results["견적"] = matched

    # 3. 정산
    dispatch_data = db.load_dispatch_data()
    df_settle = dispatch_data.get("settlement", pd.DataFrame())
    if not df_settle.empty and "업체" in df_settle.columns:
        matched = df_settle[df_settle["업체"].astype(str).str.contains(company_name, na=False, case=False)]
        if not matched.empty:
            results["정산"] = matched

    # 4. 배정
    df_disp = dispatch_data.get("dispatch", pd.DataFrame())
    if not df_disp.empty:
        # 문의ID로 연결
        inq_ids = []
        for key in ["문의", "견적", "정산"]:
            if key in results and "문의ID" in results[key].columns:
                inq_ids.extend(results[key]["문의ID"].tolist())
        if inq_ids and "문의ID" in df_disp.columns:
            matched = df_disp[df_disp["문의ID"].isin(inq_ids)]
            if not matched.empty:
                results["배정"] = matched

    if not results:
        return None, f"'{company_name}' 관련 데이터가 없습니다."

    total_billing = 0
    if "정산" in results and "청구금액" in results["정산"].columns:
        total_billing = results["정산"]["청구금액"].apply(safe_int).sum()

    total_dispatched = len(results.get("배정", pd.DataFrame()))

    summary = {
        "제목": f"🏢 '{company_name}' 전체 이력",
        "kpi": [
            {"label": "문의", "value": f"{len(results.get('문의', []))}건", "color": "#6366f1"},
            {"label": "견적", "value": f"{len(results.get('견적', []))}건", "color": "#7c3aed"},
            {"label": "정산", "value": f"{len(results.get('정산', []))}건", "color": "#2563eb"},
            {"label": "배정인원", "value": f"{total_dispatched}명", "color": "#059669"},
            {"label": "총 청구액", "value": fmt_won(total_billing), "color": "#dc2626"},
        ],
        "tabs": results,
        "count": sum(len(v) for v in results.values()),
    }
    return summary, None


def query_staff_ranking(data):
    """인력 활용 랭킹 (가장 많이 투입된 인력)"""
    dispatch_data = db.load_dispatch_data()
    df_disp = dispatch_data.get("dispatch", pd.DataFrame())

    if df_disp.empty or "인력명" not in df_disp.columns:
        return None, "배정 데이터가 없습니다."

    status_col = None
    for c in ["지급상태", "상태"]:
        if c in df_disp.columns:
            status_col = c
            break

    if status_col:
        df = df_disp[df_disp[status_col].astype(str).str.contains("확정|배정", na=False)].copy()
    else:
        df = df_disp.copy()

    df = df[df["인력명"].astype(str).str.strip() != ""]

    agg_dict = {"인력명": "count"}
    if "총지급액" in df.columns:
        agg_dict["총지급액"] = lambda x: sum(safe_int(v) for v in x)

    ranking = (
        df.groupby("인력명")
        .agg(**{
            "투입횟수": ("인력명", "count"),
            "총지급액": ("총지급액", lambda x: sum(safe_int(v) for v in x)) if "총지급액" in df.columns else ("인력명", "count"),
        })
        .sort_values("투입횟수", ascending=False)
        .reset_index()
        .head(30)
    )

    if "총지급액" in ranking.columns:
        ranking["총지급액"] = ranking["총지급액"].apply(fmt_won)

    summary = {
        "제목": "🏆 인력 투입 랭킹 (TOP 30)",
        "kpi": [
            {"label": "1위", "value": ranking.iloc[0]["인력명"] if len(ranking) > 0 else "-", "color": "#f59e0b"},
            {"label": "활동 인원", "value": f"{len(ranking)}명", "color": "#6366f1"},
        ],
        "table": ranking,
        "count": len(ranking),
    }
    return summary, None


def query_full_text_search(data, keyword):
    """전체 데이터 키워드 검색"""
    results = {}
    label_map = {
        "inq": "문의",
        "staff": "인력(STAFF)",
        "client": "고객정보",
        "estimate": "견적",
    }

    # 메인 데이터 검색
    for key, label in label_map.items():
        df = data.get(key, pd.DataFrame())
        if df.empty:
            continue
        mask = df.apply(lambda row: row.astype(str).str.contains(keyword, case=False, na=False).any(), axis=1)
        matched = df[mask]
        if not matched.empty:
            results[label] = matched

    # 배정/정산 검색
    dispatch_data = db.load_dispatch_data()
    for key, label in [("dispatch", "배정기록"), ("settlement", "정산")]:
        df = dispatch_data.get(key, pd.DataFrame())
        if df.empty:
            continue
        mask = df.apply(lambda row: row.astype(str).str.contains(keyword, case=False, na=False).any(), axis=1)
        matched = df[mask]
        if not matched.empty:
            results[label] = matched

    if not results:
        return None, f"'{keyword}'에 대한 검색 결과가 없습니다."

    summary = {
        "제목": f"🔍 '{keyword}' 검색 결과",
        "kpi": [
            {"label": "총 결과", "value": f"{sum(len(v) for v in results.values())}건", "color": "#2563eb"},
            {"label": "영역 수", "value": f"{len(results)}개", "color": "#7c3aed"},
        ],
        "tabs": results,
        "count": sum(len(v) for v in results.values()),
    }
    return summary, None


# ==============================================================================
# 2-1. 상세필터 검색
# ==============================================================================
def query_custom_filter(data, source, date_range, status_filter, sort_col, sort_asc):
    """사용자 정의 필터 검색"""
    dispatch_data = db.load_dispatch_data()

    source_map = {
        "문의": ("inq", data),
        "견적": ("estimate", data),
        "인력(STAFF)": ("staff", data),
        "고객정보": ("client", data),
        "배정기록": ("dispatch", dispatch_data),
        "정산": ("settlement", dispatch_data),
    }

    if source not in source_map:
        return None, "잘못된 데이터 소스입니다."

    key, src = source_map[source]
    df = src.get(key, pd.DataFrame())

    if df.empty:
        return None, f"{source} 데이터가 없습니다."

    df = df.copy()

    # 날짜 필터
    if date_range:
        date_cols_priority = {
            "문의": ["작성일", "행사시작일"],
            "견적": ["기록일시"],
            "배정기록": ["배정일시", "투입시작일"],
            "정산": ["파견일자"],
            "인력(STAFF)": [],
            "고객정보": [],
        }
        for dc in date_cols_priority.get(source, []):
            if dc in df.columns:
                df["_parsed_date"] = pd.to_datetime(
                    df[dc].astype(str).str.split("~").str[0].str.strip(),
                    errors="coerce", format="mixed"
                )
                start_dt, end_dt = date_range
                mask = (df["_parsed_date"] >= pd.Timestamp(start_dt)) & (df["_parsed_date"] <= pd.Timestamp(end_dt))
                df = df[mask].drop(columns=["_parsed_date"], errors="ignore")
                break

    # 상태 필터
    if status_filter:
        status_cols = ["상태", "진행상황", "진행상태", "지급상태"]
        for sc in status_cols:
            if sc in df.columns:
                df = df[df[sc].astype(str).str.contains(status_filter, na=False, case=False)]
                break

    # 정렬
    if sort_col and sort_col in df.columns:
        # 숫자형 정렬 시도
        try:
            df["_sort_key"] = df[sort_col].apply(safe_int)
            if df["_sort_key"].sum() != 0:
                df = df.sort_values("_sort_key", ascending=sort_asc).drop(columns=["_sort_key"])
            else:
                df = df.sort_values(sort_col, ascending=sort_asc)
        except:
            df = df.sort_values(sort_col, ascending=sort_asc)

    if df.empty:
        return None, "조건에 맞는 데이터가 없습니다."

    summary = {
        "제목": f"📋 {source} 상세 조회 ({len(df)}건)",
        "table": df,
        "count": len(df),
    }
    return summary, None


# ==============================================================================
# 3. 결과 렌더링
# ==============================================================================
def render_kpi_row(kpis):
    """KPI 카드 행 렌더링"""
    cols = st.columns(len(kpis))
    for col, kpi in zip(cols, kpis):
        col.markdown(f"""
        <div class="kpi-box" style="background: {kpi['color']};">
            <div class="label">{kpi['label']}</div>
            <div class="value">{kpi['value']}</div>
        </div>
        """, unsafe_allow_html=True)


def render_result(summary):
    """검색 결과 통합 렌더링"""
    if not summary:
        return

    st.markdown(f"### {summary['제목']}")
    st.caption(f"총 {summary.get('count', 0)}건 조회됨")

    # KPI
    if "kpi" in summary:
        render_kpi_row(summary["kpi"])
        st.markdown("")

    # tabs (업체이력처럼 여러 카테고리)
    if "tabs" in summary:
        tab_labels = list(summary["tabs"].keys())
        tabs = st.tabs(tab_labels)
        for tab, label in zip(tabs, tab_labels):
            with tab:
                df = summary["tabs"][label].copy()
                # Arrow 호환: 혼합 타입 컬럼을 문자열로 변환
                for col in df.columns:
                    if df[col].dtype == object:
                        df[col] = df[col].astype(str).replace({"nan": "", "None": ""})
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(
                    f"📥 {label} 엑셀 다운로드",
                    data=to_excel(df, label),
                    file_name=f"{label}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_{label}_{id(df)}",
                )

    # 단일 테이블
    elif "table" in summary:
        df = summary["table"].copy()
        # Arrow 호환: 혼합 타입 컬럼을 문자열로 변환
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).replace({"nan": "", "None": ""})
        st.dataframe(df, use_container_width=True, hide_index=True)
        excel_name = summary.get("excel_name", "조회결과")
        st.download_button(
            "📥 엑셀 다운로드",
            data=to_excel(summary["table"], excel_name),
            file_name=f"{excel_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# ==============================================================================
# 4. 메인 페이지
# ==============================================================================
def show(data):
    apply_styles()

    # 헤더
    st.markdown("""
    <div class="search-header">
        <h2>🔍 스마트 데이터 조회</h2>
        <p>키워드 검색 또는 상세 필터로 필요한 데이터를 빠르게 찾아보세요</p>
    </div>
    """, unsafe_allow_html=True)

    # ──────────────────────────────────────────
    # A. 키워드 검색 영역
    # ──────────────────────────────────────────
    st.markdown("#### ⚡ 빠른 검색")

    # 프리셋 버튼
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    preset = None
    with col1:
        if st.button("📊 이번달 매출", use_container_width=True):
            preset = "monthly_revenue"
    with col2:
        if st.button("💸 지급내역", use_container_width=True):
            preset = "payment_history"
    with col3:
        if st.button("👷 직군 랭킹", use_container_width=True):
            preset = "top_jobs"
    with col4:
        if st.button("🚨 미수금", use_container_width=True):
            preset = "unpaid"
    with col5:
        if st.button("🏆 인력 랭킹", use_container_width=True):
            preset = "staff_ranking"
    with col6:
        if st.button("🔄 초기화", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key.startswith("search_"):
                    del st.session_state[key]
            st.rerun()

    # 프리셋 클릭 시 세션에 저장
    if preset:
        st.session_state["search_preset"] = preset
        st.session_state.pop("search_result", None)

    st.markdown("---")

    # 검색창
    search_col1, search_col2 = st.columns([4, 1])
    with search_col1:
        keyword = st.text_input(
            "🔍 검색어 입력",
            placeholder="업체명, 인력명, 직군, 날짜(예: 2월 매출), 또는 아무 키워드...",
            key="search_keyword_input",
            label_visibility="collapsed",
        )
    with search_col2:
        search_clicked = st.button("검색", type="primary", use_container_width=True)

    if search_clicked and keyword:
        st.session_state["search_keyword"] = keyword
        st.session_state.pop("search_preset", None)
        st.session_state.pop("search_result", None)

    # ──────────────────────────────────────────
    # 검색 실행
    # ──────────────────────────────────────────
    now = datetime.now()
    result = None
    error = None

    # 프리셋 처리
    active_preset = st.session_state.get("search_preset")
    if active_preset:
        with st.spinner("데이터 조회 중..."):
            if active_preset == "monthly_revenue":
                result, error = query_monthly_revenue(data, now.year, now.month)
            elif active_preset == "payment_history":
                result, error = query_payment_history(data, now.year, now.month)
            elif active_preset == "top_jobs":
                result, error = query_top_jobs(data)
            elif active_preset == "unpaid":
                result, error = query_unpaid(data)
            elif active_preset == "staff_ranking":
                result, error = query_staff_ranking(data)

    # 키워드 검색 처리
    active_keyword = st.session_state.get("search_keyword")
    if active_keyword and not active_preset:
        kw = active_keyword.strip()
        with st.spinner("검색 중..."):
            # 키워드→프리셋 자동 매핑
            if any(w in kw for w in ["매출", "수익", "실적", "revenue"]):
                y, m = parse_month_year(kw)
                result, error = query_monthly_revenue(data, y, m)
            elif any(w in kw for w in ["지급", "급여", "세무", "원천", "3.3"]):
                y, m = parse_month_year(kw)
                result, error = query_payment_history(data, y, m)
            elif any(w in kw for w in ["직군", "직무", "포지션", "가장 많이"]):
                result, error = query_top_jobs(data)
            elif any(w in kw for w in ["미수", "미입금", "잔액", "unpaid"]):
                result, error = query_unpaid(data)
            elif any(w in kw for w in ["인력 랭킹", "많이 투입", "자주 나간"]):
                result, error = query_staff_ranking(data)
            else:
                # 일반 전문 검색
                result, error = query_full_text_search(data, kw)

    # 결과 렌더링
    if error:
        st.warning(error)
    elif result:
        render_result(result)

    # ──────────────────────────────────────────
    # B. 상세 필터 영역
    # ──────────────────────────────────────────
    st.markdown("---")
    with st.expander("🔧 상세 필터로 직접 조회", expanded=False):

        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            source = st.selectbox(
                "데이터 소스",
                ["문의", "견적", "배정기록", "정산", "인력(STAFF)", "고객정보"],
                key="filter_source",
            )
        with filter_col2:
            use_date = st.checkbox("날짜 범위 지정", key="filter_use_date")

        date_range = None
        if use_date:
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                start_date = st.date_input("시작일", value=now - timedelta(days=30), key="filter_start")
            with d_col2:
                end_date = st.date_input("종료일", value=now, key="filter_end")
            date_range = (start_date, end_date)

        filter_col3, filter_col4, filter_col5 = st.columns(3)
        with filter_col3:
            status_filter = st.text_input("상태 필터 (예: 체결, 확정, 완료)", key="filter_status")
        with filter_col4:
            # 소스에 따라 정렬 컬럼 후보 제안
            sort_candidates = {
                "문의": ["작성일", "업체명", "상태", "행사시작일"],
                "견적": ["기록일시", "공급가액", "합계금액", "업체명"],
                "배정기록": ["배정일시", "총지급액", "인력명", "직무"],
                "정산": ["파견일자", "청구금액", "공급가액", "잔액", "업체"],
                "인력(STAFF)": ["이름", "가능직무", "총점"],
                "고객정보": ["업체명"],
            }
            sort_col = st.selectbox("정렬 기준", sort_candidates.get(source, [""]), key="filter_sort")
        with filter_col5:
            sort_asc = st.radio("정렬 방향", ["오름차순", "내림차순"], horizontal=True, key="filter_sort_dir") == "오름차순"

        if st.button("🔍 필터 조회", type="primary", key="filter_go"):
            with st.spinner("조회 중..."):
                result2, error2 = query_custom_filter(data, source, date_range, status_filter, sort_col, sort_asc)
                if error2:
                    st.warning(error2)
                elif result2:
                    render_result(result2)
