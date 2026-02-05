"""
사업자등록증 OCR 처리 모듈
"""
import re
import os
from typing import Dict, Optional
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np

# Pytesseract 시도
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

def extract_business_info_advanced(image_text: str) -> Dict[str, str]:
    """
    추출된 텍스트에서 사업자 정보 파싱 (개선된 버전)
    
    Args:
        image_text: OCR으로 추출된 텍스트
    
    Returns:
        dict: 사업자 정보 (사업자번호, 업체명, 대표자, 업종 등)
    """
    result = {
        "business_number": None,
        "company_name": None,
        "representative": None,
        "business_type": None,
        "address": None,
        "issue_date": None
    }
    
    # 정규표현식 패턴들 (더 정확하게 개선)
    
    # 1. 사업자등록번호 추출 (###-##-##### 또는 ###-##-#####의 형태)
    # 한국 사업자번호는 10자리
    biz_num_patterns = [
        r'(\d{3}[-\s]?\d{2}[-\s]?\d{5})',
        r'(\d{3}\d{2}\d{5})',
        r'사업자.*?(\d{3}[-\s]?\d{2}[-\s]?\d{5})',
    ]
    for pattern in biz_num_patterns:
        biz_match = re.search(pattern, image_text, re.IGNORECASE)
        if biz_match:
            num = biz_match.group(1).replace(' ', '').replace('-', '')
            if len(num) >= 9:  # 최소 길이 체크
                result["business_number"] = f"{num[:3]}-{num[3:5]}-{num[5:]}"
                break
    
    # 2. 업체명/상호 추출 (더 정확한 패턴)
    name_patterns = [
        r'상호\s*[:：]?\s*([^\n※\d]{2,}?)(?:\n|$)',
        r'(?:상호|회사명)\s*[:：]?\s*([^\n※]{2,}?)(?:\n|$)',
        r'^([가-힣a-zA-Z0-9\s\-&()]{2,})$',  # 첫 라인이 상호일 가능성
    ]
    for pattern in name_patterns:
        name_match = re.search(pattern, image_text, re.MULTILINE)
        if name_match:
            candidate = name_match.group(1).strip()
            # 숫자나 특수문자만 있는 것 제외
            if any(c.isalpha() or ord(c) >= 0xAC00 for c in candidate):
                result["company_name"] = candidate
                break
    
    # 3. 대표자 추출 (더 정확한 패턴)
    rep_patterns = [
        r'대표자\s*[:：]?\s*([가-힣a-zA-Z\s]{2,}?)(?:\n|$)',
        r'(?:대표|대표자)\s*[:：]?\s*([^\n]{2,})(?:\n|$)',
    ]
    for pattern in rep_patterns:
        rep_match = re.search(pattern, image_text, re.MULTILINE)
        if rep_match:
            candidate = rep_match.group(1).strip()
            if candidate and len(candidate) <= 10:  # 이름 길이 제한
                result["representative"] = candidate
                break
    
    # 4. 업종 추출 (더 정확한 패턴)
    type_patterns = [
        r'업종\s*[:：]?\s*([^\n※]{2,})(?:\n|$)',
        r'(?:업종|사업의종류)\s*[:：]?\s*([^\n]{2,})(?:\n|$)',
    ]
    for pattern in type_patterns:
        type_match = re.search(pattern, image_text, re.MULTILINE | re.IGNORECASE)
        if type_match:
            result["business_type"] = type_match.group(1).strip()
            break
    
    # 5. 주소 추출 (더 정확한 패턴)
    addr_patterns = [
        r'(?:소재지|주소)\s*[:：]?\s*([^\n※]{5,})(?:\n|$)',
        r'([가-힣\d로리가길\s]{10,})',  # 주소 구성 요소 찾기
    ]
    for pattern in addr_patterns:
        addr_match = re.search(pattern, image_text, re.MULTILINE)
        if addr_match:
            candidate = addr_match.group(1).strip()
            if len(candidate) > 4:
                result["address"] = candidate
                break
    
    return result


def try_extract_with_easyocr(image_file) -> Optional[Dict[str, str]]:
    """
    EasyOCR을 사용하여 이미지에서 텍스트 추출 (개선 버전)
    
    Args:
        image_file: Streamlit 업로드 파일 객체
    
    Returns:
        dict: 추출된 사업자 정보
    """
    try:
        import easyocr
        from PIL import Image
        import io
        import cv2
        import numpy as np
        
        # 이미지 로드 및 전처리
        image = Image.open(image_file)
        
        # 이미지 품질 개선 (대비 증가, 노이즈 제거)
        img_array = np.array(image)
        
        # 그레이스케일 변환
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # 대비 개선 (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # OCR 리더 초기화 (한국어 중심)
        reader = easyocr.Reader(['ko'], gpu=False)
        
        # 전처리된 이미지로 텍스트 추출
        results = reader.readtext(enhanced, detail=0)
        
        # 추출된 텍스트 조합
        extracted_text = "\n".join(results)
        
        # 정보 파싱
        business_info = extract_business_info_advanced(extracted_text)
        
        return business_info if business_info.get('business_number') else None
        
    except ImportError:
        return None
    except Exception as e:
        print(f"EasyOCR 처리 실패: {e}")
        return None


def try_extract_with_paddle(image_file) -> Optional[Dict[str, str]]:
    """
    PaddleOCR을 사용하여 이미지에서 텍스트 추출
    
    Args:
        image_file: Streamlit 업로드 파일 객체
    
    Returns:
        dict: 추출된 사업자 정보
    """
    try:
        from paddleocr import PaddleOCR
        from PIL import Image
        import io
        
        # 이미지 로드
        image = Image.open(image_file)
        image_path = "/tmp/temp_ocr_image.png"
        image.save(image_path)
        
        # OCR 초기화 (한국어)
        ocr = PaddleOCR(use_angle_cls=True, lang='korean')
        
        # 텍스트 추출
        result = ocr.ocr(image_path, cls=True)
        
        # 추출된 텍스트 조합
        extracted_text = "\n".join([line[0][1] for line in result if line])
        
        # 정보 파싱
        business_info = extract_business_info_advanced(extracted_text)
        
        return business_info if business_info.get('business_number') else None
        
    except ImportError:
        return None
    except Exception as e:
        print(f"PaddleOCR 처리 실패: {e}")
        return None


def get_sample_business_info() -> Dict[str, str]:
    """
    테스트용 샘플 사업자 정보 반환
    """
    return {
        "business_number": "123-45-67890",
        "company_name": "그래디우스 이벤트",
        "representative": "김진영",
        "business_type": "이벤트 기획 및 진행",
        "address": "서울시 강남구 테헤란로 123",
        "issue_date": "2024-01-15"
    }


def try_extract_with_pytesseract(image_file) -> Optional[Dict[str, str]]:
    """
    Pytesseract를 사용하여 이미지에서 텍스트 추출
    한글 OCR을 위해서는 Tesseract 엔진이 설치되어야 함
    
    Args:
        image_file: Streamlit 업로드 파일 객체
    
    Returns:
        dict: 추출된 사업자 정보
    """
    if not PYTESSERACT_AVAILABLE:
        return None
    
    try:
        from PIL import Image
        import io
        
        # 이미지 로드
        image = Image.open(image_file)
        
        # 이미지 전처리
        # 그레이스케일 변환
        if image.mode != 'L':
            image = image.convert('L')
        
        # 대비 증가
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        
        # 노이즈 감소
        image = image.filter(ImageFilter.MedianFilter())
        
        # 이미지를 배열로 변환
        img_array = np.array(image)
        
        # Tesseract 설정 (한글 지원을 위해 -l kor 사용)
        try:
            # 한글 설정 시도
            extracted_text = pytesseract.image_to_string(img_array, lang='kor')
        except Exception as tesseract_error:
            # Tesseract가 설치되지 않은 경우
            if 'not installed' in str(tesseract_error) or 'PATH' in str(tesseract_error):
                return None
            # 한글이 없으면 기본 설정으로 시도
            try:
                extracted_text = pytesseract.image_to_string(img_array)
            except:
                return None
        
        if not extracted_text or len(extracted_text.strip()) < 5:
            return None
        
        # 정보 파싱
        business_info = extract_business_info_advanced(extracted_text)
        
        return business_info if business_info.get('business_number') else None
        
    except Exception as e:
        # 조용히 None 반환 (다음 OCR 방식으로 폴백)
        return None

