-- ============================================================
-- Gradius ERP — Supabase PostgreSQL 스키마
-- Supabase 대시보드 > SQL Editor 에서 실행하세요
-- ============================================================

-- 기존 테이블/타입 초기화 (재실행 시 오류 방지)
DROP TABLE IF EXISTS payouts        CASCADE;
DROP TABLE IF EXISTS evaluations    CASCADE;
DROP TABLE IF EXISTS attendances    CASCADE;
DROP TABLE IF EXISTS settlements    CASCADE;
DROP TABLE IF EXISTS assignments    CASCADE;
DROP TABLE IF EXISTS estimate_versions CASCADE;
DROP TABLE IF EXISTS estimate_items CASCADE;
DROP TABLE IF EXISTS estimates      CASCADE;
DROP TABLE IF EXISTS inquiries      CASCADE;
DROP TABLE IF EXISTS guides         CASCADE;
DROP TABLE IF EXISTS factors        CASCADE;
DROP TABLE IF EXISTS roles          CASCADE;
DROP TABLE IF EXISTS staff          CASCADE;
DROP TABLE IF EXISTS customers      CASCADE;

DROP TYPE IF EXISTS inquiry_status   CASCADE;
DROP TYPE IF EXISTS assignment_status CASCADE;
DROP TYPE IF EXISTS payment_status   CASCADE;
DROP TYPE IF EXISTS project_progress CASCADE;
DROP TYPE IF EXISTS deposit_status   CASCADE;
DROP TYPE IF EXISTS attendance_status CASCADE;
DROP TYPE IF EXISTS staff_recommend  CASCADE;
DROP TYPE IF EXISTS eval_grade       CASCADE;

-- ENUM 타입 정의
CREATE TYPE inquiry_status AS ENUM (
    '접수', '견적', '체결', '배정완료', '진행중', '완료', '정산완료', '미체결', '보류', '취소'
);
CREATE TYPE assignment_status AS ENUM ('후보', '배정중', '확정', '취소');
CREATE TYPE payment_status AS ENUM ('대기', '완료', '확인완료', '미지급');
CREATE TYPE project_progress AS ENUM ('계약체결', '행사준비', '행사종료', '정산완료');
CREATE TYPE deposit_status AS ENUM ('입금완료', '부분입금', '미입금');
CREATE TYPE attendance_status AS ENUM ('출석', '지각', '결근', '조퇴', '외출');
CREATE TYPE staff_recommend AS ENUM ('우선투입', '일반', '보류');
CREATE TYPE eval_grade AS ENUM ('우수', '보통', '미흡');

-- ============================================================
-- 1. 고객정보 (customers)
-- ============================================================
CREATE TABLE customers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name  TEXT NOT NULL UNIQUE,          -- 업체명
    rep_name      TEXT,                          -- 대표자명
    biz_number    VARCHAR(20),                   -- 사업자번호
    biz_type      TEXT,                          -- 업태
    biz_item      TEXT,                          -- 종목
    address       TEXT,                          -- 주소
    email         VARCHAR(255),                  -- 이메일
    contact_name  TEXT,                          -- 담당자
    phone         VARCHAR(20),                   -- 연락처
    memo          TEXT,                          -- 메모
    customer_type TEXT DEFAULT '법인',            -- '법인' | '개인' (사업자번호 유무로 자동 설정)
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 2. 직군 마스터 (roles)
-- ============================================================
CREATE TABLE roles (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_code     TEXT NOT NULL UNIQUE,          -- 직군코드 (기존 role_id)
    role_name     TEXT NOT NULL,                 -- 직군명
    base_price    INTEGER DEFAULT 0,             -- 기본단가 (청구)
    pay_price     INTEGER DEFAULT 0,             -- 지급단가
    leader_bonus  INTEGER DEFAULT 10000,         -- 팀장가산
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 3. 추가요금 항목 (factors)
-- ============================================================
CREATE TABLE factors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id         UUID REFERENCES roles(id) ON DELETE CASCADE,
    factor_name     TEXT NOT NULL,               -- 체크항목
    description     TEXT,                        -- 상세설명
    add_price       INTEGER DEFAULT 0,           -- 추가금액
    add_pay_price   INTEGER DEFAULT 0,           -- 지급추가금
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 4. 가격 가이드 (guides)
-- ============================================================
CREATE TABLE guides (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id             UUID REFERENCES roles(id) ON DELETE CASCADE,
    consult_points      TEXT,                    -- 상담포인트
    market_avg_price    INTEGER,                 -- 시장 평균가
    competitor_price    INTEGER,                 -- 타업체 견적가
    past_contract_price INTEGER,                 -- 기존 체결가
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 5. 직원 (staff)
-- ============================================================
CREATE TABLE staff (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,               -- 이름
    gender          VARCHAR(10),                 -- 성별
    age             INTEGER,                     -- 나이
    height          INTEGER,                     -- 키 (cm)
    total_score     INTEGER DEFAULT 0,           -- 총점
    english_skill   TEXT,                        -- 영어능력
    driving         TEXT,                        -- 운전면허
    region          TEXT,                        -- 거주지
    available_jobs  TEXT[],                      -- 가능직무 (배열)
    certifications  TEXT[],                      -- 자격증 (배열)
    recommend       staff_recommend DEFAULT '일반',
    phone           VARCHAR(20),                 -- 연락처
    attendance_score INTEGER DEFAULT 0,          -- 근태점수
    performance_score INTEGER DEFAULT 0,         -- 수행점수
    appearance_score  INTEGER DEFAULT 0,         -- 외모점수
    teamwork_score    INTEGER DEFAULT 0,         -- 팀워크점수
    bank_name       TEXT,                        -- 은행명
    account_number  TEXT,                        -- 계좌번호
    id_number       TEXT,                        -- 주민등록번호 (암호화 권장)
    memo            TEXT,                        -- 총평/메모
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 6. 문의 (inquiries)
-- ============================================================
CREATE TABLE inquiries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inquiry_code    TEXT UNIQUE,                 -- 기존 문의ID (마이그레이션 호환)
    created_at      TIMESTAMPTZ DEFAULT now(),
    company_name    TEXT,                        -- 업체명
    customer_id     UUID REFERENCES customers(id),
    contact_name    TEXT,                        -- 담당자
    phone           VARCHAR(20),                 -- 연락처
    event_name      TEXT NOT NULL,               -- 행사명
    location        TEXT,                        -- 장소
    event_start     DATE,                        -- 행사시작일
    event_end       DATE,                        -- 행사종료일
    event_time      TEXT,                        -- 행사시간
    service_type    TEXT,                        -- 서비스종류
    required_staff  INTEGER,                     -- 필요인력
    expected_pay    INTEGER,                     -- 예상페이
    status          inquiry_status DEFAULT '접수',
    notes           TEXT,                        -- 특이사항
    memo            TEXT,                        -- 비고
    satisfaction    SMALLINT CHECK (satisfaction BETWEEN 0 AND 5),
    relationship    TEXT,                        -- '신규' | '기존'
    category        TEXT,                        -- 구분
    attire          TEXT,                        -- 복장
    meal            TEXT,                        -- 식사
    parking         TEXT,                        -- 주차
    consult_notes   TEXT,                        -- 상담내용
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 7. 견적 (estimates)
-- ============================================================
CREATE TABLE estimates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_code   TEXT UNIQUE,                 -- 기존 견적ID (EST-XXXXXX)
    inquiry_id      UUID REFERENCES inquiries(id) ON DELETE CASCADE,
    company_name    TEXT,
    event_name      TEXT,
    site_name       TEXT,                        -- 현장명
    manager         TEXT,                        -- 책임자
    site_address    TEXT,
    supply_price    INTEGER DEFAULT 0,           -- 공급가액
    vat             INTEGER DEFAULT 0,           -- 부가세
    total_price     INTEGER DEFAULT 0,           -- 합계금액
    cost_price      INTEGER DEFAULT 0,           -- 매입원가
    extra_cost      INTEGER DEFAULT 0,           -- 부대비용
    expected_profit INTEGER GENERATED ALWAYS AS (supply_price - cost_price - extra_cost) STORED,
    profit_rate     NUMERIC(5,2),                -- 수익률 %
    attire          TEXT,
    meal            TEXT,
    parking         TEXT,
    notes           TEXT,
    meta_json       JSONB,                       -- 메타데이터
    send_status     TEXT DEFAULT '미발송',
    sent_at         TIMESTAMPTZ,
    send_method     TEXT,
    send_memo       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 8. 견적 품목 (estimate_items)
-- ============================================================
CREATE TABLE estimate_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id     UUID REFERENCES estimates(id) ON DELETE CASCADE,
    inquiry_id      UUID REFERENCES inquiries(id),
    role_name       TEXT,                        -- 직군명
    quantity        INTEGER DEFAULT 1,           -- 수량(인원)
    days            INTEGER DEFAULT 1,           -- 일수
    unit_price      INTEGER DEFAULT 0,           -- 매출단가
    pay_unit_price  INTEGER DEFAULT 0,           -- 매입단가
    spec            TEXT,                        -- 규격(근무시간)
    notes           TEXT,
    is_leader       BOOLEAN DEFAULT FALSE,       -- 팀장여부
    discount        INTEGER DEFAULT 0,           -- 할인액
    item_type       TEXT DEFAULT '인력',          -- '인력' | '부대비용'
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 9. 견적안 버전 (estimate_versions)
-- ============================================================
CREATE TABLE estimate_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_code    TEXT UNIQUE,                 -- 기존 견적안ID
    inquiry_id      UUID REFERENCES inquiries(id) ON DELETE CASCADE,
    version_name    TEXT,                        -- 견적안명
    items_json      JSONB,                       -- 품목 배열
    supply_total    INTEGER DEFAULT 0,
    cost_total      INTEGER DEFAULT 0,
    item_count      INTEGER DEFAULT 0,
    meta_json       JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 10. 배정기록 (assignments)
-- ============================================================
CREATE TABLE assignments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_code TEXT UNIQUE,                 -- 기존 배정ID (A-XXXXXX)
    inquiry_id      UUID REFERENCES inquiries(id) ON DELETE CASCADE,
    event_name      TEXT,
    staff_id        UUID REFERENCES staff(id),
    staff_name      TEXT,                        -- 비정규직/외부 인력 대비
    staff_type      TEXT DEFAULT '본사',          -- '본사' | '외부'
    job_type        TEXT,                        -- 직무
    phone           VARCHAR(20),
    id_number       TEXT,                        -- 주민번호
    bank_name       TEXT,
    account_number  TEXT,
    pay_rate        INTEGER DEFAULT 0,           -- 지급단가
    work_days       INTEGER DEFAULT 0,           -- 근무일수
    total_pay       INTEGER GENERATED ALWAYS AS (pay_rate * work_days) STORED,
    status          assignment_status DEFAULT '후보',
    assigned_at     TIMESTAMPTZ DEFAULT now(),
    work_dates      DATE[],                      -- 근무일자 배열
    team_code       TEXT,                        -- 팀코드
    is_payable      BOOLEAN DEFAULT TRUE,        -- 결제대상
    is_present      BOOLEAN DEFAULT TRUE,        -- 현장참여
    start_date      DATE,
    end_date        DATE,
    memo            TEXT,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 11. 청구/정산 (settlements)
-- ============================================================
CREATE TABLE settlements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inquiry_id          UUID REFERENCES inquiries(id) ON DELETE CASCADE UNIQUE,
    site_name           TEXT,
    company_name        TEXT,
    dispatch_period     TEXT,                    -- 파견일자 (텍스트 범위)
    manager             TEXT,
    site_address        TEXT,
    invoice_amount      INTEGER DEFAULT 0,       -- 청구금액
    supply_price        INTEGER DEFAULT 0,       -- 공급가액
    vat                 INTEGER DEFAULT 0,       -- 부가세
    received_amount     INTEGER DEFAULT 0,       -- 받은금액
    balance             INTEGER GENERATED ALWAYS AS (supply_price + vat - received_amount) STORED,
    progress            project_progress DEFAULT '계약체결',
    deposit_status      deposit_status DEFAULT '미입금',
    tax_invoice_issued  BOOLEAN DEFAULT FALSE,
    payout_amount       INTEGER DEFAULT 0,       -- 지급액
    invoice_calc_amount INTEGER DEFAULT 0,       -- 계산서금액
    withholding_tax     INTEGER DEFAULT 0,       -- 3.3% 원천세
    category            TEXT,
    profit              INTEGER GENERATED ALWAYS AS (supply_price - payout_amount - withholding_tax) STORED,
    biz_number          TEXT,                    -- 사업자번호
    rep_name            TEXT,
    email               VARCHAR(255),
    corp_name           TEXT,                    -- 법인명
    item_description    TEXT,                    -- 내용(품목)
    contact_phone       VARCHAR(20),
    invoice_request     TEXT,
    biz_reg_url         TEXT,                    -- 사업자등록증 URL
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 12. 출석부 (attendances)
-- ============================================================
CREATE TABLE attendances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_code     TEXT UNIQUE,                 -- 기존 기록ID
    assignment_id   UUID REFERENCES assignments(id) ON DELETE CASCADE,
    inquiry_id      UUID REFERENCES inquiries(id),
    staff_name      TEXT,
    work_date       DATE NOT NULL,
    clock_in        TIME,
    clock_out       TIME,
    work_hours      NUMERIC(4,2),
    daily_pay       INTEGER DEFAULT 0,
    status          attendance_status DEFAULT '출석',
    reason          TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 13. 평가표 (evaluations)
-- ============================================================
CREATE TABLE evaluations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_code       TEXT UNIQUE,
    assignment_id   UUID REFERENCES assignments(id) ON DELETE CASCADE,
    staff_id        UUID REFERENCES staff(id),
    staff_name      TEXT,
    site_name       TEXT,
    attendance_score  SMALLINT DEFAULT 0,
    performance_score SMALLINT DEFAULT 0,
    appearance_score  SMALLINT DEFAULT 0,
    teamwork_score    SMALLINT DEFAULT 0,
    adaptability_score SMALLINT DEFAULT 0,
    total_score     SMALLINT DEFAULT 0,
    grade           eval_grade DEFAULT '보통',
    evaluator       TEXT,
    strengths       TEXT,
    improvements    TEXT,
    re_recommend    BOOLEAN DEFAULT TRUE,
    notes           TEXT,
    evaluated_at    TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 14. 지급내역 (payouts)
-- ============================================================
CREATE TABLE payouts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payout_code     TEXT UNIQUE,                 -- 기존 지급ID
    assignment_id   UUID REFERENCES assignments(id) ON DELETE CASCADE,
    inquiry_id      UUID REFERENCES inquiries(id),
    staff_name      TEXT,
    site_name       TEXT,
    dispatch_period TEXT,
    dispatch_days   INTEGER DEFAULT 0,
    base_pay        INTEGER DEFAULT 0,           -- 기본급
    overtime_pay    INTEGER DEFAULT 0,           -- 야근비
    meal_pay        INTEGER DEFAULT 0,           -- 식사비 (3.3% 공제 대상)
    transport_pay   INTEGER DEFAULT 0,           -- 교통비 (택시비 — 3.3% 공제 제외)
    bonus           INTEGER DEFAULT 0,           -- 보너스
    subtotal        INTEGER DEFAULT 0,           -- 소계 (transport_pay 제외 합산)
    tax_deduction   INTEGER DEFAULT 0,           -- 세금공제 (3.3%)
    final_pay       INTEGER DEFAULT 0,           -- 최종지급액 (subtotal - tax + transport_pay)
    status          payment_status DEFAULT '대기',
    paid_at         DATE,
    paid_by         TEXT,
    bank_name       TEXT,
    account_number  TEXT,
    id_number       TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 인덱스 (성능 최적화)
-- ============================================================
CREATE INDEX idx_inquiries_status ON inquiries(status);
CREATE INDEX idx_inquiries_company ON inquiries(company_name);
CREATE INDEX idx_inquiries_event_start ON inquiries(event_start);
CREATE INDEX idx_estimates_inquiry ON estimates(inquiry_id);
CREATE INDEX idx_assignments_inquiry ON assignments(inquiry_id);
CREATE INDEX idx_assignments_staff ON assignments(staff_id);
CREATE INDEX idx_assignments_status ON assignments(status);
CREATE INDEX idx_settlements_inquiry ON settlements(inquiry_id);
CREATE INDEX idx_settlements_progress ON settlements(progress);
CREATE INDEX idx_attendances_assignment ON attendances(assignment_id);
CREATE INDEX idx_attendances_date ON attendances(work_date);
CREATE INDEX idx_payouts_assignment ON payouts(assignment_id);
CREATE INDEX idx_payouts_status ON payouts(status);

-- ============================================================
-- updated_at 자동 갱신 트리거
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_customers_updated BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_staff_updated BEFORE UPDATE ON staff FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_inquiries_updated BEFORE UPDATE ON inquiries FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_estimates_updated BEFORE UPDATE ON estimates FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_settlements_updated BEFORE UPDATE ON settlements FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_payouts_updated BEFORE UPDATE ON payouts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
