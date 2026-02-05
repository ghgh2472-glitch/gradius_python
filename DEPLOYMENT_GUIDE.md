# Streamlit Cloud 배포 가이드

이 문서는 Gradius ERP 애플리케이션을 Streamlit Cloud에 배포하는 방법을 설명합니다.

## 📋 사전 준비사항

### 1단계: GitHub 계정 준비
- GitHub 계정이 없으면 [github.com](https://github.com) 에서 가입
- 새 저장소 생성 (Private 또는 Public 선택)

### 2단계: Git 설치 및 저장소 생성

```bash
# 현재 디렉토리에서 Git 초기화
cd C:\Users\Win11\Desktop\gradius_python
git init
git add .
git commit -m "Initial commit: Gradius ERP application"
```

### 3단계: GitHub에 푸시

```bash
# GitHub의 저장소 URL을 설정 (YOUR_REPO_URL 부분을 실제 URL로 변경)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

## 🔐 Google Sheets 인증 설정 (중요!)

Streamlit Cloud에서는 `secrets.json` 파일을 직접 커밋할 수 없습니다. 대신 Streamlit Cloud의 Secrets 기능을 사용합니다.

### Streamlit Cloud 대시보드에서:

1. [share.streamlit.io](https://share.streamlit.io) 접속
2. "New app" 클릭
3. 배포 후 우측 상단 "Edit Secrets" 클릭
4. 아래 내용을 복사하여 입력:

```toml
[gcp_service_account]
type = "service_account"
project_id = "gradius-system"
private_key_id = "YOUR_PRIVATE_KEY_ID"
private_key = "YOUR_PRIVATE_KEY"
client_email = "YOUR_CLIENT_EMAIL"
client_id = "YOUR_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "YOUR_CERT_URL"

[spreadsheet]
url = "YOUR_SPREADSHEET_URL"
```

> 💡 `secrets.json` 파일의 내용을 복사하여 위의 `YOUR_PRIVATE_KEY_ID` 등을 대체합니다.

## 🚀 Streamlit Cloud 배포

### 1단계: Streamlit 계정 생성
- [share.streamlit.io](https://share.streamlit.io) 접속
- GitHub 계정으로 로그인

### 2단계: 새 앱 배포

1. "New app" 클릭
2. 다음 정보 입력:
   - **Repository**: `YOUR_USERNAME/YOUR_REPO_NAME`
   - **Branch**: `main`
   - **Main file path**: `app.py`

3. "Deploy" 클릭

### 3단계: Secrets 설정
배포 후:
1. 우측 상단 "≡" (메뉴) → "Settings" → "Secrets" 클릭
2. `.toml` 형식으로 Google 서비스 계정 키 입력
3. 저장

## 📝 필수 파일 확인사항

✅ 다음 파일들이 준비되어 있습니다:

- `.gitignore` - 민감한 파일 제외
- `.streamlit/config.toml` - Streamlit 설정
- `requirements.txt` - Python 의존성
- `app.py` - 메인 애플리케이션

## ⚠️ 주의사항

1. **`secrets.json` 은 절대 GitHub에 올리지 마세요!**
   - `.gitignore` 에 이미 추가됨
   
2. **Google Sheets API 활성화 확인**
   - Google Cloud Console에서 "Google Sheets API"와 "Google Drive API" 활성화되어 있는지 확인

3. **메모리/프로세스 제한**
   - 무료 티어: 메모리 1GB
   - 대용량 데이터 처리 시 업그레이드 필요

4. **첫 배포 시 시간**
   - 의존성 설치로 인해 5~10분 소요

## 🔗 배포 후 URL
배포 완료 후 다음 형식의 URL에서 접속 가능:
```
https://share.streamlit.io/YOUR_USERNAME/YOUR_REPO_NAME/main/app.py
```

## 📚 추가 리소스
- [Streamlit 공식 배포 가이드](https://docs.streamlit.io/streamlit-cloud)
- [Streamlit Secrets 관리](https://docs.streamlit.io/streamlit-cloud/get-started/deploy-an-app/connect-to-data-sources/secrets-management)

## ✨ 배포 후 모니터링

Streamlit Cloud 대시보드에서:
- 앱 상태 확인
- 로그 모니터링
- 리소스 사용량 확인
- 성능 최적화

---
**문제 발생 시:** [Streamlit Community Forum](https://discuss.streamlit.io) 에서 도움을 받을 수 있습니다.
