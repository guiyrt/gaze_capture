import time
import logging

class ThrottledLogger:
    def __init__(self, logger: logging.Logger, interval_sec: float = 5.0) -> None:
        self._logger = logger
        self._interval = interval_sec
        self._last_log_time = 0.0
        self._counter = 0

    def warning(self, message: str, *args, **kwargs):
        self._counter += 1
        now = time.monotonic()
        
        if now - self._last_log_time >= self._interval:
            self._logger.warning("[%d] %s", self._counter, message, *args, **kwargs)
            self._last_log_time = now
            self._counter = 0