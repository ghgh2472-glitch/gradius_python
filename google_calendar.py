# google_calendar.py — 구글 캘린더 연동 모듈 (앱 → 구글 캘린더 단방향)
"""
앱의 행사 일정을 구글 캘린더에 자동 동기화합니다.
- 체결 시 자동 이벤트 생성
- 대시보드에서 수동 동기화 가능
- 이벤트 업데이트/삭제 지원
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# Google Calendar API 관련 import
try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials
    GCAL_AVAILABLE = True
except ImportError:
    GCAL_AVAILABLE = False
    logger.warning("google-api-python-client 미설치 — 구글 캘린더 연동 비활성화")

# 기본 캘린더 ID (대표님 캘린더 — 설정에서 변경 가능)
DEFAULT_CALENDAR_ID = "primary"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_calendar_service():
    """Google Calendar API 서비스 객체 반환"""
    if not GCAL_AVAILABLE:
        logger.error("google-api-python-client 패키지가 없습니다.")
        return None

    try:
        # 1) secrets.json 파일에서 인증
        secrets_path = "secrets.json"
        if os.path.exists(secrets_path):
            creds = Credentials.from_service_account_file(secrets_path, scopes=SCOPES)
            return build("calendar", "v3", credentials=creds)

        # 2) Streamlit secrets에서 인증
        try:
            import streamlit as st
            if hasattr(st, 'secrets'):
                svc_dict = None
                if hasattr(st.secrets, 'gcp_service_account'):
                    svc_dict = dict(st.secrets.gcp_service_account)
                elif hasattr(st.secrets, 'service_account'):
                    svc_dict = dict(st.secrets.service_account)

                if svc_dict:
                    creds = Credentials.from_service_account_info(svc_dict, scopes=SCOPES)
                    return build("calendar", "v3", credentials=creds)
        except Exception:
            pass

        logger.error("인증 정보를 찾을 수 없습니다.")
        return None
    except Exception as e:
        logger.error(f"Calendar API 인증 실패: {e}")
        return None


def _get_calendar_id():
    """설정된 캘린더 ID 반환"""
    try:
        import streamlit as st
        return st.session_state.get('google_calendar_id', DEFAULT_CALENDAR_ID)
    except Exception:
        return DEFAULT_CALENDAR_ID


def is_calendar_available():
    """구글 캘린더 연동이 가능한지 확인"""
    if not GCAL_AVAILABLE:
        return False, "google-api-python-client 패키지 미설치"
    service = _get_calendar_service()
    if not service:
        return False, "Google Calendar API 인증 실패"
    try:
        service.calendarList().list(maxResults=1).execute()
        return True, "연동 가능"
    except Exception as e:
        err = str(e)
        if "accessNotConfigured" in err or "not been used" in err or "403" in err:
            return False, "Google Cloud Console에서 Calendar API를 활성화해주세요"
        if "notFound" in err or "404" in err:
            return False, "캘린더를 찾을 수 없습니다. 서비스 계정에 캘린더 공유가 필요합니다"
        return False, f"연결 오류: {err[:100]}"


def _make_event_id(inq_id: str) -> str:
    """문의ID로부터 구글 캘린더 이벤트ID 생성 (영소문자+숫자만 허용)"""
    clean = inq_id.lower().replace("-", "").replace("_", "").replace(" ", "")
    # Google Calendar eventId: 5~1024자, [a-v0-9] 만 허용
    safe = "".join(c for c in clean if c.isalnum() and c in "abcdefghijklmnopqrstuv0123456789")
    if not safe:
        import hashlib
        safe = hashlib.md5(inq_id.encode()).hexdigest()[:20]
        safe = "".join(c for c in safe if c in "abcdefghijklmnopqrstuv0123456789")
    prefix = "gradius"
    event_id = prefix + safe
    # 최소 5자
    while len(event_id) < 5:
        event_id += "0"
    return event_id[:1024]


def create_or_update_event(
    inq_id: str,
    event_name: str,
    client_name: str,
    start_date: str,
    end_date: str = None,
    location: str = "",
    description: str = "",
    need_staff: int = 0,
    assigned_staff: int = 0,
    staff_names: str = "",
    status: str = "",
    time_str: str = "",
    calendar_id: str = None,
) -> Dict:
    """
    구글 캘린더에 이벤트 생성 또는 업데이트
    
    Args:
        inq_id: 문의ID (이벤트 고유 식별자)
        event_name: 행사명
        client_name: 업체명
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (YYYY-MM-DD), None이면 start_date와 동일
        location: 행사장소
        description: 추가 설명
        need_staff: 필요 인력 수
        assigned_staff: 배정된 인력 수
        staff_names: 배정 인력 이름
        status: 진행 상태
        time_str: 행사 시간
        calendar_id: 대상 캘린더 ID
    
    Returns:
        {"success": bool, "message": str, "event_id": str or None}
    """
    service = _get_calendar_service()
    if not service:
        return {"success": False, "message": "Calendar API 연결 실패", "event_id": None}

    cal_id = calendar_id or _get_calendar_id()

    if not end_date:
        end_date = start_date

    # 종료일은 exclusive → 1일 추가
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        end_exclusive = end_dt.strftime("%Y-%m-%d")
    except ValueError:
        end_exclusive = end_date

    # 타이틀 구성
    title = f"[{status}] {client_name} — {event_name}" if status else f"{client_name} — {event_name}"

    # 설명 구성
    desc_parts = [f"📋 문의ID: {inq_id}"]
    if status:
        desc_parts.append(f"📌 상태: {status}")
    if need_staff > 0:
        desc_parts.append(f"👥 필요인력: {need_staff}명 (배정: {assigned_staff}명)")
    if staff_names:
        desc_parts.append(f"👤 배정인력: {staff_names}")
    if time_str:
        desc_parts.append(f"⏰ 시간: {time_str}")
    if description:
        desc_parts.append(f"📝 {description}")
    desc_parts.append(f"\n— Gradius 행정시스템 자동 동기화")
    full_desc = "\n".join(desc_parts)

    # 상태별 색상 (Google Calendar colorId: 1~11)
    color_map = {
        "체결": "9",       # 블루베리
        "배정완료": "9",   # 블루베리
        "진행중": "7",     # 피콕
        "완료": "2",       # 세이지
        "정산완료": "10",  # 바질
        "미정": "5",       # 바나나
        "접수": "6",       # 탠저린
        "취소": "11",      # 토마토
    }
    color_id = None
    for key, cid in color_map.items():
        if key in status:
            color_id = cid
            break

    event_body = {
        "summary": title,
        "location": location,
        "description": full_desc,
        "start": {"date": start_date},
        "end": {"date": end_exclusive},
        "reminders": {"useDefault": True},
    }
    if color_id:
        event_body["colorId"] = color_id

    event_id = _make_event_id(inq_id)

    try:
        # 기존 이벤트 업데이트 시도
        try:
            existing = service.events().get(calendarId=cal_id, eventId=event_id).execute()
            result = service.events().update(
                calendarId=cal_id, eventId=event_id, body=event_body
            ).execute()
            logger.info(f"📅 캘린더 이벤트 업데이트: {inq_id} → {result.get('htmlLink', '')}")
            return {"success": True, "message": "이벤트 업데이트 완료", "event_id": event_id}
        except Exception:
            pass

        # 새 이벤트 생성
        event_body["id"] = event_id
        result = service.events().insert(calendarId=cal_id, body=event_body).execute()
        logger.info(f"📅 캘린더 이벤트 생성: {inq_id} → {result.get('htmlLink', '')}")
        return {"success": True, "message": "이벤트 생성 완료", "event_id": event_id}

    except Exception as e:
        err_msg = str(e)
        logger.error(f"❌ 캘린더 이벤트 생성/업데이트 실패: {err_msg}")
        return {"success": False, "message": f"실패: {err_msg[:100]}", "event_id": None}


def delete_event(inq_id: str, calendar_id: str = None) -> Dict:
    """구글 캘린더에서 이벤트 삭제"""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "message": "Calendar API 연결 실패"}

    cal_id = calendar_id or _get_calendar_id()
    event_id = _make_event_id(inq_id)

    try:
        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
        logger.info(f"🗑️ 캘린더 이벤트 삭제: {inq_id}")
        return {"success": True, "message": "이벤트 삭제 완료"}
    except Exception as e:
        if "notFound" in str(e) or "404" in str(e):
            return {"success": True, "message": "이벤트가 이미 없음"}
        return {"success": False, "message": f"삭제 실패: {str(e)[:100]}"}


def sync_all_events(events_data: List[Dict], calendar_id: str = None) -> Dict:
    """
    앱 캘린더 이벤트를 구글 캘린더에 일괄 동기화
    
    Args:
        events_data: get_calendar_events()가 반환하는 이벤트 리스트
        calendar_id: 대상 캘린더 ID
    
    Returns:
        {"success": bool, "synced": int, "failed": int, "message": str}
    """
    service = _get_calendar_service()
    if not service:
        return {"success": False, "synced": 0, "failed": 0, "message": "Calendar API 연결 실패"}

    # 문의ID 기반으로 중복 제거 (같은 문의의 여러 세그먼트 중 첫 번째만)
    seen_events = {}
    for evt in events_data:
        ep = evt.get("extendedProps", {})
        evt_name = ep.get("event_name", "")
        client_name = ep.get("client_name", "")
        key = f"{client_name}_{evt_name}"
        if key not in seen_events:
            seen_events[key] = evt

    synced = 0
    failed = 0
    errors = []

    for key, evt in seen_events.items():
        ep = evt.get("extendedProps", {})
        # 문의ID가 없으면 키에서 생성
        inq_id = key.replace(" ", "_")

        start = evt.get("start", "")
        end_raw = evt.get("end", "")
        # end는 exclusive이므로 1일 빼서 실제 종료일로 변환
        if end_raw:
            try:
                end_dt = datetime.strptime(end_raw, "%Y-%m-%d") - timedelta(days=1)
                end_date = end_dt.strftime("%Y-%m-%d")
            except ValueError:
                end_date = start
        else:
            end_date = start

        result = create_or_update_event(
            inq_id=inq_id,
            event_name=ep.get("event_name", ""),
            client_name=ep.get("client_name", ""),
            start_date=start,
            end_date=end_date,
            location=ep.get("location", ""),
            need_staff=int(ep.get("need", 0) or 0),
            assigned_staff=int(ep.get("assigned", 0) or 0),
            staff_names=ep.get("names", ""),
            status=ep.get("status", ""),
            time_str=ep.get("time", ""),
            calendar_id=calendar_id,
        )
        if result["success"]:
            synced += 1
        else:
            failed += 1
            errors.append(f"{key}: {result['message']}")

    total = synced + failed
    msg = f"총 {total}건 중 {synced}건 동기화 완료"
    if failed > 0:
        msg += f", {failed}건 실패"
    if errors:
        msg += f"\n실패 상세: {'; '.join(errors[:3])}"

    return {"success": failed == 0, "synced": synced, "failed": failed, "message": msg}


def sync_single_event_from_inquiry(inq_row: dict, df_dispatch=None) -> Dict:
    """
    문의 데이터 1건을 구글 캘린더에 동기화
    (체결 시점 등에서 호출)
    
    Args:
        inq_row: 문의 시트 1행 데이터 (dict)
        df_dispatch: 배정기록 DataFrame (배정 인원 계산용)
    """
    import pandas as pd

    inq_id = str(inq_row.get("문의ID", "")).strip()
    if not inq_id:
        return {"success": False, "message": "문의ID가 없습니다", "event_id": None}

    event_name = str(inq_row.get("행사명", "")).strip()
    client_name = str(inq_row.get("업체명", "")).strip()

    # 날짜 파싱
    start_raw = str(inq_row.get("행사시작일", inq_row.get("시작일", ""))).strip()
    end_raw = str(inq_row.get("행사종료일", inq_row.get("종료일", ""))).strip()

    if not start_raw or start_raw in ("nan", "None", ""):
        return {"success": False, "message": "행사시작일이 없습니다", "event_id": None}

    # "~" 구분 처리
    if "~" in start_raw:
        parts = start_raw.split("~")
        start_raw = parts[0].strip()
        if not end_raw or end_raw in ("nan", "None", ""):
            end_raw = parts[1].strip()

    start_date = start_raw[:10].replace("/", "-")
    end_date = (end_raw[:10].replace("/", "-")) if end_raw and end_raw not in ("nan", "None", "") else start_date

    location = str(inq_row.get("장소", inq_row.get("현장", ""))).strip()
    if location in ("nan", "None"):
        location = ""

    status = str(inq_row.get("상태", "")).strip()
    time_str = str(inq_row.get("행사시간", inq_row.get("시간", ""))).strip()
    if time_str in ("nan", "None"):
        time_str = ""

    need = 0
    for col in ["필요인력", "요청인원", "인원"]:
        val = inq_row.get(col, 0)
        try:
            need = int(float(str(val).replace(",", "") or 0))
            if need > 0:
                break
        except (ValueError, TypeError):
            continue

    # 배정 인원 계산
    assigned = 0
    staff_names = ""
    if df_dispatch is not None and not df_dispatch.empty:
        evt_col = None
        for c in ["행사명"]:
            if c in df_dispatch.columns:
                evt_col = c
                break
        if evt_col:
            matched = df_dispatch[df_dispatch[evt_col].astype(str).str.strip() == event_name]
            # 후보/취소 제외
            status_col = None
            for c in ["지급상태", "상태"]:
                if c in matched.columns:
                    status_col = c
                    break
            if status_col:
                matched = matched[~matched[status_col].astype(str).str.strip().isin({"후보", "취소"})]
            assigned = len(matched)
            name_col = None
            for c in ["인력명", "직원명"]:
                if c in matched.columns:
                    name_col = c
                    break
            if name_col:
                names = matched[name_col].astype(str).str.strip().tolist()
                names = [n for n in names if n and n not in ("nan", "")]
                if len(names) > 3:
                    staff_names = ", ".join(names[:3]) + f" 외 {len(names)-3}명"
                else:
                    staff_names = ", ".join(names)

    return create_or_update_event(
        inq_id=inq_id,
        event_name=event_name,
        client_name=client_name,
        start_date=start_date,
        end_date=end_date,
        location=location,
        need_staff=need,
        assigned_staff=assigned,
        staff_names=staff_names,
        status=status,
        time_str=time_str,
    )
