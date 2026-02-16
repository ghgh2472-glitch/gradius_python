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

# Google Cloud Vision 시도
try:
    from google.cloud import vision
    GCLOUD_VISION_AVAILABLE = True
except ImportError:
    GCLOUD_VISION_AVAILABLE = False


def extract_business_info_advanced(image_text: str) -> Dict[str, str]:
    """추출된 텍스트에서 사업자 정보 파싱"""
    result = {
        "business_number": None,
        "company_name": None,
        "representative": None,
        "business_type": None,
        "address": None,
        "issue_date": None
    }

    # 1. 사업자등록번호
    for pattern in [
        r'사업자.*?(\d{3}[-\s]?\d{2}[-\s]?\d{5})',
        r'등록번호.*?(\d{3}[-\s]?\d{2}[-\s]?\d{5})',
        r'(\d{3}[-\s]?\d{2}[-\s]?\d{5})',
    ]:
        m = re.search(pattern, image_text, re.IGNORECASE)
        if m:
            num = m.group(1).replace(' ', '').replace('-', '')
            if len(num) >= 9:
                result["business_number"] = f"{num[:3]}-{num[3:5]}-{num[5:10]}"
                break

    # 2. 법인명/상호
    for pattern in [
        r'(?:법\s*인\s*명|상\s*호)\s*[(:：\s]?\s*(?:\(법인명\))?\s*([^\n,;]{2,30})',
        r'(?:상호|회사명|법인명)\s*[:：]?\s*([^\n]{2,30}?)(?:\n|$)',
    ]:
        m = re.search(pattern, image_text, re.MULTILINE)
        if m:
            candidate = m.group(1).strip().strip('()')
            if any(c.isalpha() or ord(c) >= 0xAC00 for c in candidate) and len(candidate) >= 2:
                result["company_name"] = candidate
                break

    # 3. 대표자
    for pattern in [
        r'대\s*표\s*자\s*[:：]?\s*([가-힣]{2,5})',
        r'(?:대표|성명)\s*[:：]?\s*([가-힣]{2,5})',
    ]:
        m = re.search(pattern, image_text, re.MULTILINE)
        if m:
            candidate = m.group(1).strip()
            if 2 <= len(candidate) <= 5:
                result["representative"] = candidate
                break

    # 4. 업종/업태
    for pattern in [
        r'(?:업\s*종)\s*[:：]?\s*([^\n]{2,30}?)(?:\n|업태|$)',
        r'(?:업\s*태)\s*[:：]?\s*([^\n]{2,30}?)(?:\n|$)',
    ]:
        m = re.search(pattern, image_text, re.MULTILINE | re.IGNORECASE)
        if m:
            result["business_type"] = m.group(1).strip()
            break

    # 5. 주소
    for pattern in [
        r'(?:소\s*재\s*지|사업장\s*소재지|주\s*소)\s*[:：]?\s*([^\n]{5,80})',
        r'((?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)[가-힣\d\s로리가길\-,]{5,60})',
    ]:
        m = re.search(pattern, image_text, re.MULTILINE)
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
    """Google Cloud Vision API로 사업자등록증 OCR"""
    if not GCLOUD_VISION_AVAILABLE:
        return None
    try:
        creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')
        if not creds_path:
            for candidate in ['service_account.json', 'credentials.json', 'google_credentials.json']:
                if os.path.exists(candidate):
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.abspath(candidate)
                    break

        client = vision.ImageAnnotatorClient()
        image_file.seek(0)
        content = image_file.read()
        image_file.seek(0)

        img = vision.Image(content=content)
        response = client.document_text_detection(
            image=img,
            image_context={"language_hints": ["ko", "en"]}
        )

        if response.error.message:
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
    """EasyOCR로 사업자등록증 OCR"""
    try:
        import easyocr
        image_file.seek(0)
        image = Image.open(image_file)
        img_array = np.array(image)

        if CV2_AVAILABLE and len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
        else:
            enhanced = np.array(image.convert('L'))

        reader = easyocr.Reader(['ko', 'en'], gpu=False)
        results = reader.readtext(enhanced, detail=0)
        extracted_text = "\n".join(results)

        info = extract_business_info_advanced(extracted_text)
        info['_raw_text'] = extracted_text[:500]
        return info if info.get('business_number') or info.get('company_name') else None

    except ImportError:
        return None
    except Exception as e:
        print(f"EasyOCR 실패: {e}")
        return None


# ==============================================================
# Pytesseract (최종 폴백)
# ==============================================================
def try_extract_with_pytesseract(image_file) -> Optional[Dict[str, str]]:
    """Pytesseract로 사업자등록증 OCR"""
    if not PYTESSERACT_AVAILABLE:
        return None
    try:
        image_file.seek(0)
        image = Image.open(image_file)
        if image.mode != 'L':
            image = image.convert('L')
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        image = image.filter(ImageFilter.MedianFilter())

        try:
            extracted_text = pytesseract.image_to_string(np.array(image), lang='kor')
        except Exception:
            try:
                extracted_text = pytesseract.image_to_string(np.array(image))
            except Exception:
                return None

        if not extracted_text or len(extracted_text.strip()) < 5:
            return None

        info = extract_business_info_advanced(extracted_text)
        return info if info.get('business_number') else None
    except Exception:
        return None


# ==============================================================
# 통합 OCR 함수 (메인 진입점)
# ==============================================================
def extract_business_info(image_file) -> tuple:
    """
    사업자등록증에서 정보 추출 (여러 엔진 자동 시도)
    Returns: (result_dict, engine_name, raw_text)
    """
    engines = [
        ("Google Cloud Vision", try_extract_with_google_vision),
        ("EasyOCR", try_extract_with_easyocr),
        ("Pytesseract", try_extract_with_pytesseract),
    ]

    for engine_name, engine_func in engines:
        try:
            image_file.seek(0)
            result = engine_func(image_file)
            if result and (result.get('business_number') or result.get('company_name')):
                raw = result.pop('_raw_text', '')
                return result, engine_name, raw
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
