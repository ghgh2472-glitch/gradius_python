"""
EasyOCR 설치 확인 및 테스트
"""
import sys

print("🔍 EasyOCR 설치 확인 중...")

# 1. 기본 import 테스트
try:
    import easyocr
    print("✅ EasyOCR import 성공")
except ImportError as e:
    print(f"❌ EasyOCR import 실패: {e}")
    sys.exit(1)

try:
    import torch
    print(f"✅ PyTorch import 성공 (버전: {torch.__version__})")
except ImportError as e:
    print(f"❌ PyTorch import 실패: {e}")
    sys.exit(1)

try:
    import cv2
    print(f"✅ OpenCV import 성공 (버전: {cv2.__version__})")
except ImportError as e:
    print(f"❌ OpenCV import 실패: {e}")
    sys.exit(1)

# 2. CUDA 확인
print(f"\n🖥️  CUDA 가용성: {torch.cuda.is_available()}")
print(f"📊 사용 디바이스: {'GPU' if torch.cuda.is_available() else 'CPU'}")

# 3. EasyOCR Reader 초기화 시도 (한국어)
print("\n🌐 EasyOCR 한국어 Reader 초기화 중... (첫 실행 시 모델 다운로드)")
try:
    reader = easyocr.Reader(['ko'], gpu=torch.cuda.is_available())
    print("✅ EasyOCR 한국어 Reader 초기화 성공")
except Exception as e:
    print(f"❌ EasyOCR Reader 초기화 실패: {e}")
    sys.exit(1)

# 4. 테스트 OCR 실행
print("\n📝 테스트 OCR 실행 중...")
try:
    # 간단한 이미지 생성 (한글 텍스트)
    from PIL import Image, ImageDraw, ImageFont
    import os
    
    # 이미지 생성
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    
    # 한글 텍스트 작성 (기본 폰트)
    text = "사업자등록번호: 123-45-67890\n업체명: 테스트회사\n대표자: 홍길동"
    draw.text((20, 50), text, fill='black')
    
    # 이미지 저장
    test_img_path = 'test_ocr_image.png'
    img.save(test_img_path)
    
    # OCR 실행
    result = reader.readtext(test_img_path)
    extracted_text = '\n'.join([text[1] for text in result])
    
    print(f"✅ OCR 테스트 성공:")
    print(f"   추출된 텍스트:\n{extracted_text}")
    
    # 정리
    if os.path.exists(test_img_path):
        os.remove(test_img_path)
    
except Exception as e:
    print(f"❌ OCR 테스트 실패: {e}")
    sys.exit(1)

print("\n" + "="*50)
print("✨ EasyOCR 설치 및 테스트 완료! 모든 구성이 정상입니다.")
print("="*50)
