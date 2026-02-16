"""utils_audit.py
감사 로그 유틸리티 – 데이터 변경 이력을 추적한다.

사용 예:
    from utils_audit import AuditLogger
    audit = AuditLogger()
    audit.log("CREATE", "문의", "INQ-001", {"업체명": "테스트"})
    recent = audit.get_recent(10)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from helpers import get_logger

logger = get_logger(__name__)


class AuditLogger:
    """인메모리 감사 로그 – Streamlit session_state에 저장된다."""

    _KEY = "_audit_log"

    # ------------------------------------------------------------------
    # 내부 저장소 접근
    # ------------------------------------------------------------------
    @staticmethod
    def _get_store() -> List[Dict]:
        """session_state 기반 저장소를 반환한다."""
        try:
            import streamlit as st

            if AuditLogger._KEY not in st.session_state:
                st.session_state[AuditLogger._KEY] = []
            return st.session_state[AuditLogger._KEY]
        except Exception:
            # Streamlit 바깥(테스트 등)에서는 모듈 레벨 리스트 사용
            if not hasattr(AuditLogger, "_fallback"):
                AuditLogger._fallback: List[Dict] = []
            return AuditLogger._fallback

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    @staticmethod
    def log(
        action: str,
        entity_type: str,
        entity_id: str,
        details: Optional[Dict[str, Any]] = None,
        user: str = "system",
    ) -> None:
        """감사 로그를 기록한다.

        Args:
            action: 동작 유형 (CREATE, UPDATE, DELETE, STATUS_CHANGE 등)
            entity_type: 대상 엔티티 (문의, 견적, 계약, 배정, 정산 등)
            entity_id: 엔티티 식별자
            details: 변경 상세 정보 (변경 전/후 값 등)
            user: 수행자 이름 (기본 'system')
        """
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "details": details or {},
            "user": user,
        }
        store = AuditLogger._get_store()
        store.append(entry)
        logger.info(
            f"[AUDIT] {action} {entity_type} {entity_id} by {user}"
        )

    @staticmethod
    def get_recent(n: int = 20) -> pd.DataFrame:
        """최근 n건의 감사 로그를 DataFrame으로 반환한다."""
        store = AuditLogger._get_store()
        recent = store[-n:] if len(store) > n else store
        if not recent:
            return pd.DataFrame(
                columns=["timestamp", "action", "entity_type", "entity_id", "details", "user"]
            )
        df = pd.DataFrame(recent)
        return df.iloc[::-1].reset_index(drop=True)  # 최신 순

    @staticmethod
    def get_by_entity(entity_type: str, entity_id: str) -> pd.DataFrame:
        """특정 엔티티의 변경 이력을 반환한다."""
        store = AuditLogger._get_store()
        filtered = [
            e
            for e in store
            if e["entity_type"] == entity_type and e["entity_id"] == entity_id
        ]
        if not filtered:
            return pd.DataFrame(
                columns=["timestamp", "action", "entity_type", "entity_id", "details", "user"]
            )
        return pd.DataFrame(filtered).iloc[::-1].reset_index(drop=True)

    @staticmethod
    def clear() -> None:
        """감사 로그를 모두 삭제한다 (테스트용)."""
        store = AuditLogger._get_store()
        store.clear()
