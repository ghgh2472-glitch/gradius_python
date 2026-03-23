import logging
import time
from datetime import datetime, timezone, timedelta
from functools import wraps

# 한국 표준시 (UTC+9)
_KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 한국 시간 반환 (timezone-aware)"""
    return datetime.now(_KST)


def today_kst() -> datetime:
    """오늘 한국 날짜 자정 (timezone-naive, 날짜 비교용)"""
    return now_kst().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def get_logger(name=__name__):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def retry(times=3, delay=1, backoff=2, allowed_exceptions=(Exception,)):
    """Retry decorator with exponential backoff.

    Usage:
        @retry(times=3)
        def write():
            ...
    """
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _times = times
            _delay = delay
            last_exc = None
            for attempt in range(1, _times + 1):
                try:
                    return func(*args, **kwargs)
                except allowed_exceptions as e:
                    last_exc = e
                    time.sleep(_delay)
                    _delay *= backoff
            # re-raise the last exception
            raise last_exc
        return wrapper
    return deco
