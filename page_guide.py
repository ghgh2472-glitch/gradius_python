# page_guide.py
"""
📘 사용 가이드 — 전체 업무 흐름, 각 단계별 상세 안내, 입력 주의사항
"""
import streamlit as st


def show(data=None):
    st.title("📘 Gradius ERP 사용 가이드")
    st.caption("처음 사용하는 분도 따라할 수 있도록, 전체 업무 흐름과 각 단계별 안내를 정리했습니다.")

    # ──────────────────────────────────────────────
    # 스타일
    # ──────────────────────────────────────────────
    st.markdown("""
    <style>
        .guide-flow-step {
            border-radius: 12px; padding: 18px 20px; text-align: center;
            min-height: 90px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            display: flex; flex-direction: column; justify-content: center;
        }
        .guide-flow-arrow { display: flex; align-items: center; justify-content: center;
                            font-size: 22px; color: #9CA3AF; padding-top: 25px; }
        .guide-section { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px;
                         padding: 20px 24px; margin-bottom: 16px; }
        .guide-tip { background: #EFF6FF; border-left: 4px solid #3B82F6; padding: 12px 16px;
                     border-radius: 6px; margin: 8px 0; font-size: 13px; line-height: 1.7; }
        .guide-warn { background: #FEF2F2; border-left: 4px solid #EF4444; padding: 12px 16px;
                      border-radius: 6px; margin: 8px 0; font-size: 13px; line-height: 1.7; }
        .guide-ok { background: #F0FDF4; border-left: 4px solid #10B981; padding: 12px 16px;
                    border-radius: 6px; margin: 8px 0; font-size: 13px; line-height: 1.7; }
    </style>
    """, unsafe_allow_html=True)

    # ──────────────────────────────────────────────
    # 0. 전체 업무 흐름도
    # ──────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🗺️ 전체 업무 흐름도")
    st.caption("Gradius ERP는 아래 7단계 파이프라인으로 운영됩니다. 좌→우 순서로 진행하세요.")

    flow_data = [
        ("📞", "접수", "#FEF3C7", "#F59E0B", "고객 문의 등록"),
        ("🧮", "견적", "#DBEAFE", "#3B82F6", "견적서 작성"),
        ("📝", "체결", "#EDE9FE", "#8B5CF6", "계약 확정"),
        ("👷", "배정", "#E0F2FE", "#0EA5E9", "인력 배정"),
        ("🔥", "진행", "#FFF7ED", "#F97316", "현장 투입"),
        ("✅", "완료", "#D1FAE5", "#10B981", "행사 종료"),
        ("💰", "정산", "#A7F3D0", "#059669", "수금 · 급여"),
    ]

    cols = st.columns([3, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3])
    for i, (icon, label, bg, color, desc) in enumerate(flow_data):
        col_idx = i * 2
        with cols[col_idx]:
            st.markdown(f"""
            <div class="guide-flow-step" style="background:{bg};border:2px solid {color};">
                <div style="font-size:24px;">{icon}</div>
                <div style="font-weight:800;color:{color};font-size:15px;">{label}</div>
                <div style="font-size:11px;color:{color};opacity:0.8;margin-top:2px;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)
        if i < len(flow_data) - 1:
            with cols[col_idx + 1]:
                st.markdown('<div class="guide-flow-arrow">→</div>', unsafe_allow_html=True)

    st.markdown("")
    st.markdown("""
    <div class="guide-tip">
        💡 <b>이탈 상태</b>: 어느 단계에서든 <b>미체결 / 보류 / 취소</b>로 전환 가능합니다.
        보류 상태에서는 이전 단계로 복귀할 수 있습니다.
    </div>
    """, unsafe_allow_html=True)

    # ──────────────────────────────────────────────
    # 단계별 상세 가이드 (각각 expander)
    # ──────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📋 단계별 상세 가이드")
    st.caption("각 단계를 클릭하면 상세 안내가 펼쳐집니다.")

    # ── STEP 1: 문의 접수 ──
    with st.expander("📞 STEP 1. 문의 접수 및 관리", expanded=False):
        st.markdown("##### 이 단계에서 하는 일")
        st.markdown("""
        - 고객으로부터 전화/메일/카톡 등으로 문의를 받으면 **문의 접수** 페이지에서 등록합니다.
        - 등록 시 자동으로 **관리번호(문의ID)**가 생성됩니다.
        """)

        st.markdown("##### 입력 항목")
        st.markdown("""
        | 항목 | 필수 | 설명 | 예시 |
        |------|------|------|------|
        | **업체명** | ✅ | 문의한 고객사 이름 | ABC이벤트 |
        | **담당자** | ✅ | 고객사 담당자 이름 | 김철수 |
        | **연락처** | ✅ | 담당자 연락처 | 010-1234-5678 |
        | **행사명** | ✅ | 행사/현장 이름 | 2026 서울 마라톤 |
        | **행사시작일** | ✅ | YYYY-MM-DD 형식 | 2026-03-15 |
        | **행사종료일** | 선택 | 시작일과 같으면 생략 가능 | 2026-03-16 |
        | **장소** | ✅ | 행사 장소 | 잠실종합운동장 |
        | **서비스종류** | ✅ | 필요 서비스 유형 | 경호, 안내, 주차 |
        | **필요인력** | ✅ | 필요한 인원 수 | 8 |
        | **특이사항** | 선택 | 기타 참고사항 | VIP 경호 2명 포함 |
        """)

        st.markdown("""
        <div class="guide-warn">
            ⚠️ <b>주의사항</b><br/>
            • 행사시작일은 <b>YYYY-MM-DD</b> 형식을 권장합니다 (예: 2026-03-15)<br/>
            • "2026년 3월 15일" 같은 형식도 저장은 되지만, <b>캘린더/D-Day 계산이 안 될 수</b> 있습니다<br/>
            • 업체명이 기존 고객과 동일하면 자동으로 매칭됩니다<br/>
            • 접수 후 상태는 자동으로 <b>"접수"</b>로 설정됩니다
        </div>
        """, unsafe_allow_html=True)

        st.markdown("##### 📱 카톡 접수 양식 예시")
        st.markdown("고객에게 아래 양식을 보내서 정보를 받으면 그대로 붙여넣기 하면 됩니다.")
        st.code("""문의날짜: 2026-03-10
업체 : (주)해피이벤트
성함 : 박지영 과장
행사명 : 2026 강남 플라워페스타
연락처 : 010-9876-5432
장소 : 코엑스 1층 로비
일시 : 2026-03-28 ~ 2026-03-30
시간 : 09:00 ~ 18:00
서비스종류 : 안내, 주차, 경호
요청인원수 : 안내 4명, 주차 2명, 경호 2명
페이 : 협의
복장 : 정장 (검정)
식사 : 도시락 제공
주차 : 지하주차장 가능
특이사항: VIP 경호 1명 필요, 3일간 동일인력 희망""", language="text")

        st.markdown("""
        <div class="guide-tip">
            💡 <b>카톡 자동 파싱 기능</b><br/>
            • 문의 접수 페이지 상단에 <b>"📋 카톡 붙여넣기"</b> 영역이 있습니다<br/>
            • 위 양식을 그대로 붙여넣으면 <b>각 필드가 자동으로 채워집니다</b><br/>
            • 자동 채워진 값을 확인·수정 후 "🚀 문의 접수 등록" 클릭
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="guide-ok">
            ✅ <b>완료 후 다음 단계</b><br/>
            문의 접수가 끝나면 → <b>견적 통합 관리</b> 페이지에서 해당 문의에 대한 견적서를 작성합니다.
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 2: 견적 ──
    with st.expander("🧮 STEP 2. 견적 통합 관리", expanded=False):
        st.markdown("##### 이 단계에서 하는 일")
        st.markdown("""
        - 접수된 문의에 대해 **견적서**를 작성합니다.
        - 직군별 인원, 일수, 단가를 입력하면 **공급가액, 부가세, 합계**가 자동 계산됩니다.
        - AI가 시장 시세 기반 **적정 단가 가이드**를 제공합니다.
        """)

        st.markdown("##### 견적 작성 흐름")
        st.markdown("""
        1. **문의 선택** — 좌측에서 견적할 문의건을 선택합니다
        2. **업체 정보 확인** — 업체명, 행사명, 장소 등 자동 표시
        3. **견적 품목 추가** — 직군 선택 → 수량/일수/매출단가/매입단가 입력
        4. **부대비용 추가** — 교통비, 식대 등 (해당 시)
        5. **견적서 미리보기** — PDF 스타일 미리보기 확인
        6. **저장** 클릭
        """)

        st.markdown("""
        <div class="guide-tip">
            💡 <b>팁</b><br/>
            • <b>매출단가</b> = 고객에게 청구하는 단가, <b>매입단가</b> = 인력에 지급하는 단가<br/>
            • 차이(매출-매입)가 회사 마진이므로 반드시 매출 > 매입인지 확인하세요<br/>
            • 견적서 저장 시 상태가 자동으로 <b>"견적"</b>으로 변경됩니다
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="guide-warn">
            ⚠️ <b>주의사항</b><br/>
            • 단가에 콤마(,)를 넣지 마세요. 숫자만 입력합니다 (예: 150000)<br/>
            • 부가세는 공급가액의 10%로 자동 계산됩니다<br/>
            • 견적 후 7일 이상 체결되지 않으면 대시보드에 알림이 표시됩니다
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="guide-ok">
            ✅ <b>완료 후 다음 단계</b><br/>
            고객이 견적을 승인하면 → <b>계약 관리</b> 페이지에서 계약을 체결합니다.<br/>
            거절 시 → 대시보드에서 <b>"미체결"</b>로 상태 변경
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 3: 계약 체결 ──
    with st.expander("📝 STEP 3. 계약 관리 및 승인", expanded=False):
        st.markdown("##### 이 단계에서 하는 일")
        st.markdown("""
        - 견적 승인된 건에 대해 **계약 체결**을 확정합니다.
        - 체결 시 자동으로 **정산 시트**에 기본 정보가 등록됩니다.
        """)

        st.markdown("##### 계약 체결 흐름")
        st.markdown("""
        1. "견적" 상태인 건 목록에서 대상 선택
        2. 계약 내용 확인 (업체, 금액, 일정)
        3. **"체결" 버튼** 클릭 → 상태가 "체결"로 변경
        """)

        st.markdown("""
        <div class="guide-tip">
            💡 <b>팁</b><br/>
            • 체결 시 정산 시트에 공급가액, 부가세 등이 자동 입력됩니다<br/>
            • 체결 취소가 필요하면 대시보드 파이프라인에서 상태를 되돌릴 수 있습니다
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="guide-ok">
            ✅ <b>완료 후 다음 단계</b><br/>
            계약 체결 후 → <b>인원 배정 관리</b> 페이지에서 인력을 배정합니다.
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 4: 인원 배정 ──
    with st.expander("👷 STEP 4. 인원 배정 관리", expanded=False):
        st.markdown("##### 이 단계에서 하는 일")
        st.markdown("""
        - 체결된 건에 **인력을 배정**합니다.
        - 개별 배정 / 팀 배정 / 본사 투입 등 다양한 방식을 지원합니다.
        """)

        st.markdown("##### 배정 모드 3가지")
        st.markdown("""
        | 모드 | 설명 | 사용 시점 |
        |------|------|-----------|
        | **개별 배정** | STAFF DB에서 1명씩 검색·배정 | 일반적인 경우 |
        | **팀 배정** | 팀장 선택 → 팀원 수동 입력 | 팀장이 팀원을 데리고 올 때 |
        | **본사 투입** | 자사 직원 배정 (급여 0원) | 본사 인력 투입 시 |
        """)

        st.markdown("##### 배정 흐름")
        st.markdown("""
        1. **체결 건 선택** — 좌측 셀렉트박스에서 선택
        2. **필요 직군 확인** — 견적서 기반 직군별 필요인원 표시
        3. **직군 선택** — 배정할 직군 선택
        4. **배정 모드 선택** — 개별/팀/본사
        5. **인력 검색 & 선택** — 이름, 지역, 직무로 검색
        6. **단가·일수 확인** → **"배정 확정"** 클릭
        """)

        st.markdown("""
        <div class="guide-tip">
            💡 <b>팀 배정 시</b><br/>
            • 팀장을 STAFF에서 검색·선택하고, 팀원은 이름을 직접 입력합니다<br/>
            • 급여는 팀장에게만 지급됩니다 (팀원 결제대상 = N)<br/>
            • 팀코드가 자동 생성되어 팀원이 묶입니다
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="guide-warn">
            ⚠️ <b>배정 스킵 (위약금 케이스)</b><br/>
            • 고객 취소 등으로 인력 배정이 불필요한 경우<br/>
            • <b>"⏭️ 배정 불필요"</b> 버튼으로 바로 '완료' 상태로 전환 가능<br/>
            • 이후 정산에서 위약금만 청구하면 됩니다
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="guide-ok">
            ✅ <b>완료 후 다음 단계</b><br/>
            모든 직군 배정 완료 → 상태가 <b>"배정완료"</b>로 전환<br/>
            현장 진행 시작 → <b>"진행중"</b> 전환 (대시보드에서 변경)
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 5: 출석부 ──
    with st.expander("📋 STEP 5. 출석부 관리", expanded=False):
        st.markdown("##### 이 단계에서 하는 일")
        st.markdown("""
        - 현장에 배정된 인력의 **출퇴근 기록**을 관리합니다.
        - 배정된 인원 목록이 자동으로 표시되며, 출석/결석/지각 등을 기록합니다.
        """)

        st.markdown("""
        <div class="guide-tip">
            💡 <b>팁</b><br/>
            • 출석부 데이터는 정산 시 근무일수 확인에 활용됩니다<br/>
            • 현장 진행 중일 때 사용합니다
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 6: 정산 ──
    with st.expander("💰 STEP 6. 정산 및 급여 관리", expanded=False):
        st.markdown("##### 이 단계에서 하는 일")
        st.markdown("""
        - 행사 완료 후 **고객 청구**(수금)와 **인력 급여 지급**을 처리합니다.
        - 공급가액 - 지급액 = 영업이익이 자동 계산됩니다.
        """)

        st.markdown("##### 정산 흐름")
        st.markdown("""
        1. **"완료" 상태인 건** 목록에서 선택
        2. 좌측: **청구 정보** 확인 (공급가액, 부가세 등)
        3. **입금여부** 업데이트 (입금완료 / 부분입금 / 미수금)
        4. **받은금액** 입력 → 잔액 자동 계산
        5. 우측: **인력 급여** 검토 → 급여 지급 처리
        6. 지급 완료 시 **지급액/이익 자동 갱신**
        """)

        st.markdown("""
        <div class="guide-tip">
            💡 <b>핵심 컬럼 정리</b><br/>
            • <b>입금여부</b>: 고객이 돈을 보냈는가 (입금완료/부분입금/미수금)<br/>
            • <b>세금계산서 발행여부</b>: 세금계산서를 발행했는가<br/>
            • <b>지급액</b>: 인력에 지급한 총 급여<br/>
            • <b>이익</b>: 공급가액 − 지급액 (자동 계산)
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="guide-warn">
            ⚠️ <b>주의사항</b><br/>
            • 받은금액에 콤마(,) 없이 숫자만 입력하세요<br/>
            • 부분입금 시 잔액이 자동 갱신됩니다<br/>
            • 모든 입금 + 급여 처리 완료 후 → 대시보드에서 <b>"정산완료"</b>로 전환
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 7: 대시보드 ──
    with st.expander("🚀 경영 대시보드 활용법", expanded=False):
        st.markdown("##### 대시보드에서 볼 수 있는 것들")
        st.markdown("""
        | 영역 | 내용 |
        |------|------|
        | **KPI 카드** | 총 청구액, 수금액, 미수금, 수금률, 영업이익, 이익률, 견적전환율 |
        | **스마트 브리핑** | 미수금 알림, 임박 현장, 미체결 경과 건, 이익률 경고 |
        | **파이프라인** | 전체 상태별 건수, 클릭하면 해당 건 상세 표시 |
        | **상태 변경** | 어떤 건이든 다음 단계로 전환 가능 |
        | **분석 탭** | 월별 매출, Top 고객사, 수금 비율 |
        | **긴급 탭** | D-7 이내 현장, 미수금 Top 업체 |
        | **인력 탭** | 현장별 배정현황, 직군별 통계, 팀배정 현황 |
        | **수익분석 탭** | 공급가액 vs 지급액, 전환율, 건별 이익 |
        | **AI 분석 탭** | 매출 예측, 리스크 분석, 인력 수요, 고객 분석 |
        | **리포트 탭** | 일일/주간/월간 보고서 자동 생성 및 다운로드 |
        """)

        st.markdown("""
        <div class="guide-tip">
            💡 <b>상태 변경 방법</b><br/>
            • 대시보드 → 파이프라인 아래 <b>"🔧 상태 변경 관리"</b> 섹션을 펼치세요<br/>
            • 상태 필터 → 건 선택 → 다음 상태 선택 → "✅ 상태 변경" 클릭
        </div>
        """, unsafe_allow_html=True)

    # ──────────────────────────────────────────────
    # FAQ / 자주 묻는 질문
    # ──────────────────────────────────────────────
    st.markdown("---")
    st.subheader("❓ 자주 묻는 질문 (FAQ)")

    with st.expander("Q. 데이터가 안 보여요 / 로딩이 안 됩니다"):
        st.markdown("""
        **A.** 사이드바 하단의 **🔄 데이터 동기화** 버튼을 클릭하세요.
        그래도 안 되면 페이지를 새로고침(F5)하세요.

        구글 시트 API 할당량 초과 시 1~2분 후 자동 복구됩니다.
        """)

    with st.expander("Q. 상태를 잘못 변경했어요. 되돌릴 수 있나요?"):
        st.markdown("""
        **A.** 네! 대시보드 → 상태 변경 관리에서 이전 단계로 되돌릴 수 있습니다.

        - **보류 → 접수/견적/체결 등**: 원래 단계로 복귀 가능
        - **미체결 → 접수**: 재검토 가능
        - **취소/정산완료**: 최종 상태이므로 되돌릴 수 없음
        """)

    with st.expander("Q. 견적서에서 직군을 추가하고 싶은데 목록에 없어요"):
        st.markdown("""
        **A.** 견적 직군 드롭다운 맨 아래 **"기타 (직접입력)"**을 선택하면 자유롭게 입력 가능합니다.
        Roles 시트에 직군을 추가하면 다음부터 드롭다운에 나타납니다.
        """)

    with st.expander("Q. 팀 배정은 어떻게 하나요?"):
        st.markdown("""
        **A.** 인원 배정 관리 → 배정 모드에서 **"👥 팀 배정"** 선택

        1. 팀장을 STAFF에서 검색·선택
        2. 팀원은 이름을 직접 입력 (STAFF DB에 없어도 OK)
        3. 급여는 팀장에게만 지급 (팀원은 결제대상 = N)
        """)

    with st.expander("Q. 위약금만 받고 인력 투입 안 하는 경우는?"):
        st.markdown("""
        **A.** 인원 배정 관리 → **"⏭️ 배정 불필요 (위약금/취소 등)"** 클릭

        배정 없이 바로 "완료" 상태로 전환됩니다.
        이후 정산에서 지급액 0원, 청구금액에 위약금을 입력하면 됩니다.
        """)

    with st.expander("Q. 영업이익은 어디서 확인하나요?"):
        st.markdown("""
        **A.** 두 곳에서 확인 가능합니다:

        1. **대시보드 KPI 카드** (2행): 💎 영업이익, 💸 총 지급액, 📊 이익률
        2. **대시보드 → 💎 수익분석 탭**: 건별 이익, 직군별 지급액 분포 등 상세 분석

        영업이익 = 공급가액 - 지급액
        """)

    # ──────────────────────────────────────────────
    # 입력 규칙 요약
    # ──────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📝 입력 규칙 총정리")

    st.markdown("""
    | 항목 | 권장 입력 | 가능은 하지만 비권장 | 이유 |
    |------|----------|-------------------|------|
    | **날짜** | `2026-03-15` | 2026년 3월 15일 | 캘린더/D-Day 계산에 YYYY-MM-DD 필요 |
    | **금액** | `150000` | 150,000 / 15만원 | 견적 계산 시 숫자만 인식 |
    | **연락처** | `010-1234-5678` | 01012345678 | 하이픈 포함 권장 |
    | **인원수** | `8` | 8명 | 숫자만 권장 |
    | **시간** | `09:00~18:00` | 오전9시~오후6시 | 통일된 형식 권장 |
    | **직군** | 드롭다운 선택 | 약어 사용 | 정확한 이름 사용 |
    """)

    st.markdown("""
    <div class="guide-ok">
        ✅ <b>핵심 원칙</b><br/>
        • 날짜는 <b>YYYY-MM-DD</b>, 금액은 <b>숫자만</b><br/>
        • 필수 항목은 빠짐없이 입력<br/>
        • 모르겠으면 이 가이드로 돌아오세요!
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.caption("📘 이 가이드는 언제든 사이드바 → '📘 사용 가이드'에서 다시 확인할 수 있습니다.")
