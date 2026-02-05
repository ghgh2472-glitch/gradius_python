"""smart_assignment.py
스마트 인력 배정 엔진:
- 다양한 필터 조건 기반 인력 검색
- 역할-스킬 매칭
- 일정 충돌 체크
- 추천 스코링
"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import pandas as pd
from utils import safe_int
from helpers import get_logger

logger = get_logger(__name__)


class StaffFilter:
    """인력 필터링 엔진"""
    
    @staticmethod
    def filter_by_gender(staff_df: pd.DataFrame, gender: str = None) -> pd.DataFrame:
        """성별 필터"""
        if not gender or gender == '전체':
            return staff_df
        if '성별' not in staff_df.columns:
            return staff_df
        return staff_df[staff_df['성별'].astype(str).str.strip() == gender]
    
    @staticmethod
    def filter_by_age_range(staff_df: pd.DataFrame, min_age: int = None, 
                           max_age: int = None) -> pd.DataFrame:
        """나이대 필터"""
        if not min_age and not max_age:
            return staff_df
        
        if '나이' not in staff_df.columns:
            return staff_df
        
        try:
            ages = pd.to_numeric(staff_df['나이'], errors='coerce')
            if min_age:
                staff_df = staff_df[ages >= min_age]
            if max_age:
                staff_df = staff_df[ages <= max_age]
        except Exception as e:
            logger.warning(f"Age filter error: {e}")
        
        return staff_df
    
    @staticmethod
    def filter_by_skills(staff_df: pd.DataFrame, required_skills: List[str] = None,
                        match_type: str = 'any') -> pd.DataFrame:
        """스킬 필터
        
        Args:
            required_skills: 필요 스킬 리스트
            match_type: 'any' (하나라도 만족) | 'all' (모두 만족)
        """
        if not required_skills:
            return staff_df
        
        skill_col = None
        for col in staff_df.columns:
            if '스킬' in col or '기술' in col or '경험' in col:
                skill_col = col
                break
        
        if not skill_col:
            return staff_df
        
        results = []
        for idx, row in staff_df.iterrows():
            staff_skills = str(row[skill_col]).split(',') if row[skill_col] else []
            staff_skills = [s.strip().lower() for s in staff_skills]
            required_skills_lower = [s.lower() for s in required_skills]
            
            if match_type == 'all':
                # 모든 필수 스킬 보유
                match = all(req in staff_skills for req in required_skills_lower)
            else:
                # 하나라도 보유
                match = any(req in staff_skills for req in required_skills_lower)
            
            if match:
                results.append(idx)
        
        return staff_df.loc[results]
    
    @staticmethod
    def filter_by_location(staff_df: pd.DataFrame, location: str = None,
                          regions: List[str] = None) -> pd.DataFrame:
        """위치/지역 필터"""
        if not location and not regions:
            return staff_df
        
        loc_col = None
        for col in staff_df.columns:
            if '지역' in col or '위치' in col or '주소' in col:
                loc_col = col
                break
        
        if not loc_col:
            return staff_df
        
        if location:
            return staff_df[staff_df[loc_col].astype(str).str.contains(location, case=False, na=False)]
        
        if regions:
            mask = staff_df[loc_col].astype(str).apply(
                lambda x: any(reg in x for reg in regions)
            )
            return staff_df[mask]
        
        return staff_df
    
    @staticmethod
    def filter_by_availability(staff_df: pd.DataFrame, dispatch_df: pd.DataFrame,
                               start_date: str, end_date: str,
                               role: str = None) -> pd.DataFrame:
        """가용성 필터 (이미 배정된 일정 제외)
        
        Args:
            staff_df: 직원 데이터
            dispatch_df: 배정 기록
            start_date: 배정 시작일 (YYYY-MM-DD)
            end_date: 배정 종료일
            role: 역할 (선택, 같은 역할만 중복 배정 불가)
        """
        # dispatch_df가 None이거나 비어있으면 그대로 반환
        if dispatch_df is None or dispatch_df.empty:
            return staff_df
        
        unavailable_names = set()
        
        for _, dispatch in dispatch_df.iterrows():
            # 취소/보류 항목은 제외
            status = dispatch.get('상태', '').strip()
            if status in ('취소', '보류'):
                continue
            
            # 날짜 충돌 확인
            disp_start = dispatch.get('배정일시', '').split(' ')[0] if dispatch.get('배정일시') else None
            
            # 간단한 날짜 겹침 체크 (실제로는 더 복잡한 로직 필요)
            if disp_start:
                try:
                    disp_dt = datetime.strptime(disp_start, '%Y-%m-%d')
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                    
                    # 겹침 확인
                    if start_dt <= disp_dt <= end_dt:
                        name = dispatch.get('이름', '').strip()
                        # 역할이 같으면 중복 배정 불가
                        disp_role = dispatch.get('역할', '').strip()
                        if role is None or disp_role == role:
                            unavailable_names.add(name)
                except ValueError:
                    pass
        
        # 가용 인력 반환
        if unavailable_names:
            name_col = None
            for col in staff_df.columns:
                if '이름' in col or '성명' in col:
                    name_col = col
                    break
            
            if name_col:
                available = staff_df[~staff_df[name_col].astype(str).isin(unavailable_names)]
                logger.info(f"⏰ {len(staff_df) - len(available)} staff members unavailable")
                return available
        
        return staff_df
    
    @staticmethod
    def apply_filters(staff_df: pd.DataFrame, dispatch_df: pd.DataFrame,
                     filters: Dict) -> pd.DataFrame:
        """모든 필터 한 번에 적용
        
        Args:
            filters: {
                'gender': str,
                'min_age': int,
                'max_age': int,
                'skills': [str],
                'location': str,
                'start_date': str,
                'end_date': str,
                'role': str,
            }
        """
        result = staff_df.copy()
        
        # 순차 필터 적용
        result = StaffFilter.filter_by_gender(result, filters.get('gender'))
        result = StaffFilter.filter_by_age_range(
            result, filters.get('min_age'), filters.get('max_age')
        )
        result = StaffFilter.filter_by_skills(
            result, filters.get('skills'), filters.get('skill_match', 'any')
        )
        result = StaffFilter.filter_by_location(result, filters.get('location'))
        
        # 가용성은 날짜가 있을 때만
        if filters.get('start_date'):
            result = StaffFilter.filter_by_availability(
                result, dispatch_df,
                filters['start_date'],
                filters.get('end_date', filters['start_date']),
                filters.get('role')
            )
        
        logger.info(f"📊 Filter result: {len(result)} candidates")
        return result


class RoleSkillMatcher:
    """역할-스킬 매칭 엔진"""
    
    # 역할별 필수/권장 스킬
    ROLE_REQUIREMENTS = {
        '보안요원': {
            'required': ['경호'],
            'preferred': ['체력', '신체조건'],
        },
        '인원배치': {
            'required': ['인원관리'],
            'preferred': ['경험', '신뢰도'],
        },
        '행사진행': {
            'required': ['커뮤니케이션'],
            'preferred': ['경험', '발성'],
        },
        '기술지원': {
            'required': ['기술'],
            'preferred': ['문제해결', '빠른학습'],
        },
    }
    
    @staticmethod
    def calc_skill_match_score(staff_skills: List[str], role: str) -> float:
        """스킬 매칭 점수 계산 (0~100)
        
        - 필수 스킬 보유: +50점
        - 권장 스킬 보유 (개당): +10점
        """
        staff_skills_lower = [s.lower() for s in staff_skills]
        requirements = RoleSkillMatcher.ROLE_REQUIREMENTS.get(role, {})
        
        score = 0
        
        # 필수 스킬
        required = requirements.get('required', [])
        if required:
            has_required = all(
                any(req.lower() in skill for skill in staff_skills_lower)
                for req in required
            )
            if has_required:
                score += 50
        
        # 권장 스킬
        preferred = requirements.get('preferred', [])
        for pref in preferred:
            if any(pref.lower() in skill for skill in staff_skills_lower):
                score += 10
        
        return min(score, 100)


class SmartAssignment:
    """스마트 배정 엔진"""
    
    @staticmethod
    def search_candidates(staff_df: pd.DataFrame, dispatch_df: pd.DataFrame,
                         filters: Dict) -> pd.DataFrame:
        """필터 적용 후 후보자 리스트 반환"""
        candidates = StaffFilter.apply_filters(staff_df, dispatch_df, filters)
        
        if candidates.empty:
            logger.warning("⚠️ No candidates found")
            return candidates
        
        # 스킬 매칭 스코어 추가
        role = filters.get('role', '')
        if role:
            candidates = candidates.copy()
            
            # 스킬 컬럼 찾기
            skill_col = None
            for col in candidates.columns:
                if '스킬' in col or '기술' in col:
                    skill_col = col
                    break
            
            if skill_col:
                candidates['매칭점수'] = candidates[skill_col].apply(
                    lambda x: RoleSkillMatcher.calc_skill_match_score(
                        str(x).split(',') if x else [],
                        role
                    )
                )
                # 점수 높은 순으로 정렬
                candidates = candidates.sort_values('매칭점수', ascending=False)
        
        return candidates
    
    @staticmethod
    def recommend_best_candidate(candidates: pd.DataFrame, 
                                dispatch_df: pd.DataFrame = None) -> Optional[Dict]:
        """최적 후보자 추천"""
        if candidates.empty:
            return None
        
        # 매칭점수가 있으면 그 기준, 없으면 첫 번째
        if '매칭점수' in candidates.columns:
            best = candidates.iloc[0]
            score = best.get('매칭점수', 0)
            logger.info(f"✅ Recommended: {best.get('이름')} (Score: {score})")
        else:
            best = candidates.iloc[0]
            logger.info(f"✅ Recommended: {best.get('이름')}")
        
        return best.to_dict()
    
    @staticmethod
    def assign_staff(staff_name: str, inquiry_id: str, role: str, 
                    days: int, hourly_rate: int = 0,
                    notes: str = '') -> Dict:
        """배정 기록 생성
        
        Returns:
            {
                '문의ID': str,
                '이름': str,
                '역할': str,
                '일수': int,
                '단가': int,
                '총지급액': int,
                '상태': '배정중',
                '배정일시': str,
                '비고': str,
            }
        """
        from datetime import datetime as dt
        from calculators import SalaryCalculator
        
        days = safe_int(days) if days else 0
        hourly_rate = safe_int(hourly_rate) if hourly_rate else 0
        
        total_pay = days * hourly_rate if days > 0 and hourly_rate > 0 else 0
        
        assignment = {
            '문의ID': inquiry_id,
            '이름': staff_name.strip(),
            '역할': role.strip(),
            '일수': days,
            '단가': hourly_rate,
            '총지급액': total_pay,
            '상태': '배정중',
            '배정일시': dt.now().strftime('%Y-%m-%d %H:%M:%S'),
            '비고': notes,
        }
        
        logger.info(f"📋 Assignment created: {staff_name} ({role}) - {days}일 @ {hourly_rate:,}원/일")
        return assignment


# 초기화 헬퍼
def init_smart_assignment():
    """스마트 배정 엔진 초기화"""
    logger.info("✅ Smart assignment engine initialized")
