"""구조화 JSON 로깅 초기화."""
import io
import json
import logging
import logging.config
import sys
from datetime import UTC, datetime


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log: dict = {
            "ts": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if hasattr(record, "error_code"):
            log["code"] = record.error_code
        if hasattr(record, "context"):
            log["context"] = record.context
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


def setup_logging(log_level: str = "INFO") -> None:
    # Windows cp949 터미널에서 한글·특수문자(em dash 등) 출력 시 UnicodeEncodeError 방지
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    handler = logging.StreamHandler(utf8_stdout)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = [handler]

    for name, level in [
        ("app", log_level),
        ("uvicorn", "INFO"),
        ("sqlalchemy.engine", "WARNING"),
    ]:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers = [handler]
        logger.propagate = False
