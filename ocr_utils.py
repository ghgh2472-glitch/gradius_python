"""
사업자등록증 OCR 처리 모듈 v2
- Google Cloud Vision API (서비스 계정 기반, 최우선)
- EasyOCR (로컬 폴백)
- Pytesseract (최종 폴백)
"""
import re
import os
import io
from typing import Dict, Optional
from PIL import Image, ImageEnhance, ImageFilter

# cv2는 선택적 의존성
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    try:
        import numpy as np
    except ImportError:
        np = None

# Pytesseract 시도
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

# Google Cloud Vision — 현재 GCP 프로젝트에서 비활성화 (401/403 발생)
# Vision API를 사용하려면 GCP Console에서 Cloud Vision API를 활성화 후 아래 주석 해제
# try:
#     from google.cloud import vision
#     GCLOUD_VISION_AVAILABLE = True
# except ImportError:
#     GCLOUD_VISION_AVAILABLE = False
GCLOUD_VISION_AVAILABLE = False


def extract_business_info_advanced(image_text: str) -> Dict[str, str]:
    """추출된 텍스트에서 사업자 정보 파싱
    
    Tesseract OCR의 한국어 인식 특성을 고려하여 패턴을 넓게 설정:
    - 글자 사이 공백 (예: '사 업 자 등 록 증')
    - OCR 오인식 (예: '0' ↔ 'O', '1' ↔ 'l')
    - 불완전한 한글 인식
    """
    result = {
        "business_number": None,
        "company_name": None,
        "representative": None,
        "business_type": None,
        "address": None,
        "issue_date": None
    }
    
    # 텍스트 정규화: 연속 공백 → 단일 공백 (개행 유지)
    cleaned = re.sub(r'[^\S\n]+', ' ', image_text)

    # 1. 사업자등록번호 — 10자리 숫자 패턴 (가장 신뢰도 높음)
    for pattern in [
        r'사업자.*?등록.*?(\d{3})\s*[-–—.]\s*(\d{2})\s*[-–—.]\s*(\d{5})',
        r'등록\s*번호.*?(\d{3})\s*[-–—.]\s*(\d{2})\s*[-–—.]\s*(\d{5})',
        r'(\d{3})\s*[-–—.]\s*(\d{2})\s*[-–—.]\s*(\d{5})',
        # 구분자 없는 연속 숫자
        r'사업자.*?(\d{3})(\d{2})(\d{5})',
        r'등록.*?번호.*?(\d{3})(\d{2})(\d{5})',
        # OCR이 숫자를 틀리게 읽을 수 있으므로 유사 패턴
        r'(\d{3})\s*[-–—.\s]\s*(\d{2})\s*[-–—.\s]\s*(\d{4,5})',
    ]:
        m = re.search(pattern, cleaned, re.IGNORECASE)
        if m:
            p1, p2, p3 = m.group(1), m.group(2), m.group(3)
            num = f"{p1}-{p2}-{p3.ljust(5, '0')[:5]}"
            result["business_number"] = num
            break

    # 2. 법인명/상호 — 다양한 패턴 지원
    for pattern in [
        r'(?:법\s*인\s*명|상\s*호)\s*[(:：\s]*\s*(?:\(?법인명\)?\s*)?([^\n,;]{2,30})',
        r'(?:상\s*호|회\s*사\s*명|법\s*인\s*명)\s*[:：]?\s*([^\n]{2,30}?)(?:\n|$)',
        r'(?:상호\s*\(?법인명\)?)\s*[:：]?\s*([^\n,;]{2,30})',
        # (주), 주식회사 등 법인 키워드가 포함된 라인
        r'(?:^|\n)\s*((?:\(?주\)?|주식회사)\s*[가-힣a-zA-Z]{1,20})',
        r'(?:^|\n)\s*([가-힣]{2,10}\s*(?:\(?주\)?|주식회사))',
    ]:
        m = re.search(pattern, cleaned, re.MULTILINE | re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().strip('()')
            # 노이즈 제거 — 숫자만이거나 너무 짧으면 스킵
            if any(c.isalpha() or ord(c) >= 0xAC00 for c in candidate) and len(candidate) >= 2:
                # "등록증", "사업자" 같은 제목은 제외
                if not re.match(r'^(사\s*업\s*자|등\s*록\s*증|발\s*급)', candidate):
                    result["company_name"] = candidate
                    break

    # 3. 대표자 — 한글 2~5자 이름
    for pattern in [
        r'대\s*표\s*자\s*[:：]?\s*([가-힣]{2,5})',
        r'(?:대\s*표|성\s*명)\s*[:：]?\s*([가-힣]{2,5})',
        r'대표자\s*\(?\s*성\s*명\s*\)?\s*[:：]?\s*([가-힣]{2,5})',
    ]:
        m = re.search(pattern, cleaned, re.MULTILINE)
        if m:
            candidate = m.group(1).strip()
            if 2 <= len(candidate) <= 5:
                result["representative"] = candidate
                break

    # 4. 업종/업태
    for pattern in [
        r'업\s*종\s*[:：]?\s*([^\n]{2,30}?)(?:\n|업\s*태|$)',
        r'업\s*태\s*[:：]?\s*([^\n]{2,30}?)(?:\n|$)',
        r'종\s*목\s*[:：]?\s*([^\n]{2,30}?)(?:\n|$)',
    ]:
        m = re.search(pattern, cleaned, re.MULTILINE | re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            # 레이블 잔여물 제거 (예: "목 이벤트" → "이벤트")
            val = re.sub(r'^[장종목태]\s*', '', val).strip()
            if len(val) >= 2:
                result["business_type"] = val
                break

    # 5. 주소/소재지
    for pattern in [
        r'(?:소\s*재\s*지|사업장\s*소재지|주\s*소)\s*[:：]?\s*([^\n]{5,80})',
        r'((?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)[가-힣\d\s로리가길동구시군읍면\-,\.]{5,60})',
    ]:
        m = re.search(pattern, cleaned, re.MULTILINE)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) > 4:
                result["address"] = candidate
                break

    return result


# ==============================================================
# Google Cloud Vision API (최우선)
# ==============================================================
def try_extract_with_google_vision(image_file) -> Optional[Dict[str, str]]:
    """Google Cloud Vision API로 사업자등록증 OCR (타임아웃 10초)"""
    if not GCLOUD_VISION_AVAILABLE:
        return None
    try:
        import threading

        # secrets.json을 GOOGLE_APPLICATION_CREDENTIALS로 설정
        creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')
        if not creds_path:
            for candidate in ['secrets.json', 'service_account.json', 'credentials.json', 'google_credentials.json']:
                if os.path.exists(candidate):
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.abspath(candidate)
                    break

        image_file.seek(0)
        content = image_file.read()
        image_file.seek(0)

        result_holder = [None]
        error_holder = [None]

        def _call_vision():
            try:
                client = vision.ImageAnnotatorClient()
                img = vision.Image(content=content)
                response = client.document_text_detection(
                    image=img,
                    image_context={"language_hints": ["ko", "en"]}
                )
                if response.error.message:
                    error_holder[0] = response.error.message
                    return
                result_holder[0] = response
            except Exception as e:
                error_holder[0] = str(e)

        thread = threading.Thread(target=_call_vision)
        thread.start()
        thread.join(timeout=10)

        if thread.is_alive():
            print("Google Vision API 타임아웃 (10초)")
            return None

        if error_holder[0]:
            err_msg = str(error_holder[0])
            # 401/403 에러는 API 미활성화 — 조용히 폴백
            if '401' in err_msg or '403' in err_msg or 'PERMISSION_DENIED' in err_msg:
                print(f"Google Vision API 미활성화 (권한 없음) — 로컬 OCR로 폴백")
            else:
                print(f"Google Vision API 오류: {err_msg[:100]}")
            return None

        response = result_holder[0]
        if response is None:
            return None

        extracted_text = response.full_text_annotation.text if response.full_text_annotation else ""
        if not extracted_text or len(extracted_text.strip()) < 5:
            return None

        info = extract_business_info_advanced(extracted_text)
        info['_raw_text'] = extracted_text[:500]
        return info if info.get('business_number') or info.get('company_name') else None

    except Exception as e:
        print(f"Google Vision API 실패: {e}")
        return None


# ==============================================================
# EasyOCR (로컬 폴백)
# ==============================================================
def try_extract_with_easyocr(image_file) -> Optional[Dict[str, str]]:
    """EasyOCR로 사업자등록증 OCR (타임아웃 15초)"""
    try:
        import easyocr
        import threading

        image_file.seek(0)
        image = Image.open(image_file)
        img_array = np.array(image)

        if CV2_AVAILABLE and len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
        else:
            enhanced = np.array(image.convert('L'))

        result_holder = [None]

        def _run_ocr():
            try:
                reader = easyocr.Reader(['ko', 'en'], gpu=False)
                results = reader.readtext(enhanced, detail=0)
                result_holder[0] = "\n".join(results)
            except Exception:
                pass

        thread = threading.Thread(target=_run_ocr)
        thread.start()
        thread.join(timeout=8)

        if thread.is_alive() or not result_holder[0]:
            print("EasyOCR 타임아웃 또는 실패 — Pytesseract로 폴백")
            return None

        extracted_text = result_holder[0]
        info = extract_business_info_advanced(extracted_text)
        info['_raw_text'] = extracted_text[:500]
        return info if info.get('business_number') or info.get('company_name') else None

    except ImportError:
        return None
    except Exception as e:
        print(f"EasyOCR 실패: {e}")
        return None


# ==============================================================
# Pytesseract (메인 OCR 엔진)
# ==============================================================
def try_extract_with_pytesseract(image_file) -> Optional[Dict[str, str]]:
    """Pytesseract로 사업자등록증 OCR — 다중 전처리 시도"""
    if not PYTESSERACT_AVAILABLE:
        print("Pytesseract 미설치")
        return None
    try:
        image_file.seek(0)
        image = Image.open(image_file)

        # 이미지가 너무 작으면 확대
        w, h = image.size
        if w < 800:
            ratio = 800 / w
            image = image.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        results = []

        # 전처리 방법 여러 개 시도
        preprocess_methods = []

        # 방법 1: 그레이스케일 + 대비 강화
        img1 = image.convert('L')
        enhancer1 = ImageEnhance.Contrast(img1)
        img1 = enhancer1.enhance(2.0)
        preprocess_methods.append(("contrast", img1))

        # 방법 2: 그레이스케일 + 샤프닝
        img2 = image.convert('L')
        enhancer2 = ImageEnhance.Sharpness(img2)
        img2 = enhancer2.enhance(2.0)
        preprocess_methods.append(("sharp", img2))

        # 방법 3: 이진화 (threshold)
        img3 = image.convert('L')
        img3 = img3.point(lambda x: 0 if x < 140 else 255, '1')
        preprocess_methods.append(("binary", img3))

        # 방법 4: 원본 그대로
        preprocess_methods.append(("original", image.convert('L')))

        best_text = ""
        for method_name, processed_img in preprocess_methods:
            try:
                # numpy 없이도 동작하도록 PIL Image 직접 전달
                text = pytesseract.image_to_string(processed_img, lang='kor+eng')
                if not text:
                    text = pytesseract.image_to_string(processed_img, lang='kor')
                if text and len(text.strip()) > len(best_text.strip()):
                    best_text = text
                    # 사업자번호가 발견되면 바로 사용
                    if re.search(r'\d{3}[-\s]?\d{2}[-\s]?\d{5}', text):
                        break
            except Exception as e:
                print(f"Pytesseract {method_name} 실패: {e}")
                continue

        if not best_text or len(best_text.strip()) < 3:
            print(f"Pytesseract: 텍스트 추출 실패 (길이: {len(best_text.strip()) if best_text else 0})")
            return None

        info = extract_business_info_advanced(best_text)
        info['_raw_text'] = best_text[:500]
        # 사업자번호 또는 법인명 중 하나라도 있으면 성공
        if info.get('business_number') or info.get('company_name') or info.get('representative'):
            return info
        # 텍스트는 추출했지만 파싱 실패 — 원본 텍스트라도 반환
        if len(best_text.strip()) > 20:
            info['_raw_text'] = best_text[:500]
            return info
        return None
    except Exception as e:
        print(f"Pytesseract 오류: {e}")
        return None
        return None


# ==============================================================
# 통합 OCR 함수 (메인 진입점)
# ==============================================================
def extract_business_info(image_file) -> tuple:
    """
    사업자등록증에서 정보 추출 (여러 엔진 자동 시도)
    Returns: (result_dict, engine_name, raw_text)
    """
    # Pytesseract를 최우선으로 사용 (빠르고 안정적)
    # Google Vision API는 현재 GCP 프로젝트에서 미활성화 상태
    # EasyOCR은 CPU에서 너무 느림 (15초+) → 마지막 폴백
    engines = [
        ("Pytesseract", try_extract_with_pytesseract),
    ]
    # EasyOCR은 Pytesseract 실패 시에만 시도 (느리지만 정확도 높음)
    # Vision API는 비활성화 상태이므로 제외

    for engine_name, engine_func in engines:
        try:
            image_file.seek(0)
            result = engine_func(image_file)
            if result:
                raw = result.pop('_raw_text', '')
                # 핵심 정보가 하나라도 있으면 성공
                if result.get('business_number') or result.get('company_name') or result.get('representative'):
                    return result, engine_name, raw
                # 원본 텍스트만이라도 있으면 부분 성공으로 반환
                if raw and len(raw.strip()) > 20:
                    return result, f"{engine_name} (부분)", raw
        except Exception as e:
            print(f"{engine_name} 실패: {e}")
            continue

    return None, None, ""


def get_sample_business_info() -> Dict[str, str]:
    """테스트용 샘플 사업자 정보"""
    return {
        "business_number": "123-45-67890",
        "company_name": "그래디우스 이벤트",
        "representative": "김진영",
        "business_type": "이벤트 기획 및 진행",
        "address": "서울시 강남구 테헤란로 123",
        "issue_date": "2024-01-15"
    }
