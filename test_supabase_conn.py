"""
test_supabase_conn.py
Supabase 연결 및 테이블 존재 여부 확인 스크립트
실행: python test_supabase_conn.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ .env 파일에 SUPABASE_URL 과 SUPABASE_SERVICE_KEY 를 입력하세요.")
    exit(1)

try:
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase 클라이언트 생성 성공")
except ImportError:
    print("❌ supabase 패키지가 없습니다. 아래 명령어로 설치하세요:")
    print("   pip install supabase")
    exit(1)

# 테이블 목록 확인 (스키마 실행 후 확인용)
EXPECTED_TABLES = [
    "customers", "roles", "factors", "guides", "staff",
    "inquiries", "estimates", "estimate_items", "estimate_versions",
    "assignments", "settlements", "attendances", "evaluations", "payouts"
]

print("\n테이블 존재 여부 확인:")
all_ok = True
for table in EXPECTED_TABLES:
    try:
        resp = client.table(table).select("id").limit(1).execute()
        print(f"  ✅ {table}")
    except Exception as e:
        print(f"  ❌ {table} — {e}")
        all_ok = False

if all_ok:
    print("\n✅ 모든 테이블 확인 완료! 마이그레이션 준비 완료.")
else:
    print("\n⚠️  누락된 테이블이 있습니다. supabase_schema.sql 을 SQL Editor에서 실행하세요.")
