import logging
import time
from functools import wraps


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
