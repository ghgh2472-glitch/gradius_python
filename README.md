# Gradius ERP (행정자동화 시스템)

고도화된 인력 관리 및 행정 자동화 플랫폼

## 🚀 주요 기능

### 1️⃣ 스마트 인력 배정 시스템
- **다양한 필터링**: 성별, 나이, 스킬, 지역, 가용성 기반 검색
- **역할-스킬 매칭**: 필요 역할에 최적 인력 추천 (매칭 점수 산출)
- **일정 충돌 체크**: 중복 배정 자동 방지
- **자동 연계**: 배정 → 출석부 → 급여 자동 생성

### 2️⃣ 자동 계산 엔진
- **견적 자동 계산**: 품목별 수량 × 단가 자동 합산
- **수익률 계산**: 공급가액 기반 실시간 이익 분석
- **급여 자동 계산**: 일수 × 단가 기반 인건비 자동 산출
- **세금 계산**: 부가세, 소득세 자동 계산

### 3️⃣ 스케줄러 & 자동화
- **일일 작업**: 미처리 항목 알림, 출석 리마인더 (09:00, 17:00)
- **월간 작업**: 자동 정산 생성, 월간 리포트 발송 (1일 08:00, 2일 09:00)
- **상태 변경 알림**: 문의 → 견적 → 계약 → 정산 각 단계별 자동 통지

### 4️⃣ 알림 시스템
- **이메일 알림**: SMTP 기반 자동 발송
- **Slack 통합**: 채널별 그룹 알림
- **카톡 알림**: 개인 연락 (선택)
- **상태 변경 트리거**: 특정 조건 발생 시 자동 통지

## 📂 프로젝트 구조

```
gradius_python/
├── app.py                      # Streamlit 메인 앱
├── 
├── [인증 및 데이터]
├── auth.py                     # Google Service Account 인증
├── data_loader.py              # Google Sheet 데이터 로드/저장
├── 
├── [비즈니스 로직]
├── calculators.py              # 자동 계산 엔진 (견적, 급여, 세금)
├── smart_assignment.py         # 스마트 배정 엔진 (필터링, 매칭)
├── workflow_automation.py       # 배정→출석→급여 자동 연계
├── 
├── [스케줄링 및 알림]
├── scheduler.py                # APScheduler 기반 자동 작업
├── notifications.py            # 이메일, Slack, 카톡 알림
├── 
├── [UI 페이지]
├── page_inquiry.py             # 문의 접수 및 관리
├── page_estimate.py            # 견적 통합 관리
├── page_contract.py            # 계약 관리
├── page_staff.py               # 스마트 인력 배정 (개선)
├── page_attendance.py          # 출석부 관리
├── page_settlement.py          # 정산 및 급여 관리
├── 
├── [유틸리티]
├── utils.py                    # 기본 유틸 함수
├── helpers.py                  # 로깅, 재시도 데코레이터
├── requirements.txt            # Python 의존성
└── README.md                   # 이 파일
```

## 🛠️ 설치 및 실행

### 1️⃣ 설정

**필수**: `secrets.json` 또는 Streamlit `st.secrets`에 Google Service Account 키 정보 추가

```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "...",
  "client_email": "...@iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "..."
}
```

### 2️⃣ 설치

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3️⃣ 실행

```bash
streamlit run app.py
```

### 4️⃣ 테스트

```bash
python test_conn.py  # Google Sheet 연결 확인
pytest               # 단위 테스트 실행 (추후 추가)
```

## 🎯 플로우 개요

```
1️⃣ 문의 접수 (page_inquiry.py)
   ↓
2️⃣ 견적 작성 (page_estimate.py)
   - 품목별 수량 × 단가 자동 계산
   - 수익률 실시간 분석
   ↓
3️⃣ 계약 체결 (page_contract.py)
   - 계약 상태 업데이트
   - 상태 변경 알림 발송
   ↓
4️⃣ 스마트 인력 배정 (page_staff.py) ✨ NEW
   - 다양한 조건으로 최적 인력 검색
   - 배정 → 출석부 → 급여 자동 생성
   ↓
5️⃣ 출석부 관리 (page_attendance.py)
   - 일일 출석 기록 자동 생성
   - 미기록 알림 (매일 09:00)
   ↓
6️⃣ 정산 및 급여 (page_settlement.py)
   - 인건비 자동 집계
   - 월간 정산 자동 생성 (매월 1일 08:00)
   - 세금 계산 및 청구서 발행
```

## 🔐 보안

- **인증**: oauth2client 기반 Google Service Account 인증
- **암호화**: `secrets.json`은 .gitignore에 포함 (공유 금지)
- **권한**: Service Account 이메일을 Google Sheet에 편집자 권한으로 공유
- **환경변수**: SMTP, Slack, Kakao 인증 정보는 환경변수로 관리

## 📊 환경 변수 (.env)

```
# 이메일
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-app-password

# Slack (선택)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK

# 카톡 (선택)
KAKAO_API_KEY=your-kakao-key
KAKAO_SENDER_KEY=your-sender-key

# 관리자 이메일
ADMIN_EMAIL=admin@example.com
```

## 🚀 고급 기능 (추후)

- [ ] REST API (FastAPI) - 외부 시스템 연동
- [ ] 데이터베이스 연동 (SQLite/PostgreSQL)
- [ ] 모바일 앱 (출석 체크인)
- [ ] AI 기반 인력 추천
- [ ] 실시간 대시보드 KPI
- [ ] 감사 로그 및 히스토리
- [ ] CI/CD 파이프라인

## 📝 주의사항

- Google Sheet의 `secrets.json` 키 파일은 .gitignore에 포함되어야 합니다.
- 스케줄러는 Streamlit 앱이 실행되는 동안만 작동합니다. (별도 백그라운드 워커 권장)
- 대용량 데이터 처리 시 캐시 TTL을 조정하세요 (`@st.cache_data(ttl=X)`).

## 🤝 개발 팀

- 코드 작성, 테스트, 배포: GitHub
- 피드백: Issues 또는 Pull Requests

## 📞 문의

문제가 발생하거나 기능 요청이 있으시면 이슈를 등록해주세요.

