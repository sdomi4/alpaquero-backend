from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
from types import TracebackType
from typing import TextIO

import yaml

from observatory.log_broker import log_broker


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LoggingSettings:
    level: str = "INFO"
    directory: Path = PROJECT_ROOT / "logs"
    filename: str = "arriero.log"
    max_bytes: int = 20 * 1024 * 1024
    backup_count: int = 10
    frontend_history: int = 100
    frontend_queue_size: int = 250

    @property
    def file_path(self) -> Path:
        return self.directory / self.filename


class UtcFormatter(logging.Formatter):
    converter = staticmethod(__import__("time").gmtime)


class LoggingStream:
    """Line-buffered text stream that turns writes into log records."""

    def __init__(self, logger: logging.Logger, level: int, original: TextIO):
        self._logger = logger
        self._level = level
        self._original = original
        self._local = threading.local()

    @property
    def encoding(self) -> str | None:
        return getattr(self._original, "encoding", "utf-8")

    @property
    def errors(self) -> str | None:
        return getattr(self._original, "errors", "strict")

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return 0

        if getattr(self._local, "emitting", False):
            self._original.write(text)
            return len(text)

        buffer = getattr(self._local, "buffer", "") + text
        lines = buffer.splitlines(keepends=True)
        remainder = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            remainder = lines.pop()
        self._local.buffer = remainder

        self._local.emitting = True
        try:
            for line in lines:
                self._logger.log(self._level, line.rstrip("\r\n"))
        finally:
            self._local.emitting = False
        return len(text)

    def flush(self) -> None:
        buffer = getattr(self._local, "buffer", "")
        if buffer:
            self._local.buffer = ""
            self._local.emitting = True
            try:
                self._logger.log(self._level, buffer)
            finally:
                self._local.emitting = False
        self._original.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._original, "isatty", lambda: False)())

    def fileno(self) -> int:
        return self._original.fileno()

    def writable(self) -> bool:
        return True


class FrontendLogHandler(logging.Handler):
    """Publish formatted records to the in-memory broker without recursion."""

    def __init__(self, fallback_stream: TextIO):
        super().__init__()
        self._fallback_stream = fallback_stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            lines = message.splitlines() or [""]
            timestamp = datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z")
            log_broker.publish(
                lines,
                timestamp=timestamp,
                level=record.levelname,
                logger_name=record.name,
            )
        except Exception:
            # Handler failures must never re-enter the logging pipeline.
            try:
                self._fallback_stream.write("Failed to publish a frontend log record\n")
                self._fallback_stream.flush()
            except Exception:
                pass


_setup_lock = threading.RLock()
_configured = False
_original_stdout: TextIO = sys.stdout
_original_stderr: TextIO = sys.stderr
_stdout_bridge: LoggingStream | None = None
_stderr_bridge: LoggingStream | None = None
_installed_handlers: list[logging.Handler] = []
_active_settings: LoggingSettings | None = None
_previous_sys_excepthook = sys.excepthook
_previous_threading_excepthook = threading.excepthook


def load_logging_settings() -> LoggingSettings:
    values: dict[str, object] = {}
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}
        values = config.get("logging", {}) or {}

    directory = Path(
        os.getenv("ARRIERO_LOG_DIR", str(values.get("directory", "logs")))
    )
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory

    return LoggingSettings(
        level=os.getenv("ARRIERO_LOG_LEVEL", str(values.get("level", "INFO"))),
        directory=directory,
        filename=os.getenv(
            "ARRIERO_LOG_FILENAME",
            str(values.get("filename", "arriero.log")),
        ),
        max_bytes=int(
            os.getenv("ARRIERO_LOG_MAX_BYTES", str(values.get("max_bytes", 20 * 1024 * 1024)))
        ),
        backup_count=int(
            os.getenv("ARRIERO_LOG_BACKUP_COUNT", str(values.get("backup_count", 10)))
        ),
        frontend_history=int(
            os.getenv("ARRIERO_LOG_FRONTEND_HISTORY", str(values.get("frontend_history", 100)))
        ),
        frontend_queue_size=int(
            os.getenv(
                "ARRIERO_LOG_FRONTEND_QUEUE_SIZE",
                str(values.get("frontend_queue_size", 250)),
            )
        ),
    )


def configure_logging(settings: LoggingSettings | None = None) -> LoggingSettings:
    global _configured, _stdout_bridge, _stderr_bridge, _installed_handlers, _active_settings

    with _setup_lock:
        if _configured:
            assert _active_settings is not None
            return _active_settings

        settings = settings or load_logging_settings()
        numeric_level = logging.getLevelNamesMapping().get(settings.level.upper())
        if not isinstance(numeric_level, int):
            raise ValueError(f"Unknown logging level: {settings.level}")
        if settings.max_bytes < 1:
            raise ValueError("logging.max_bytes must be at least 1")
        if settings.backup_count < 1:
            raise ValueError("logging.backup_count must be at least 1")

        settings.directory.mkdir(parents=True, exist_ok=True)
        log_broker.configure(
            history_size=settings.frontend_history,
            queue_size=settings.frontend_queue_size,
        )

        formatter = UtcFormatter(
            "%(asctime)s.%(msecs)03dZ | %(levelname)-8s | %(name)s | %(threadName)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        frontend_formatter = logging.Formatter("%(message)s")

        file_handler = RotatingFileHandler(
            settings.file_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler(_original_stderr)
        console_handler.setFormatter(formatter)

        frontend_handler = FrontendLogHandler(_original_stderr)
        frontend_handler.setFormatter(frontend_formatter)

        root_logger = logging.getLogger()
        for existing_handler in root_logger.handlers[:]:
            root_logger.removeHandler(existing_handler)
            existing_handler.close()
        root_logger.setLevel(numeric_level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(frontend_handler)
        _installed_handlers = [file_handler, console_handler, frontend_handler]

        for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logger = logging.getLogger(logger_name)
            for existing_handler in logger.handlers[:]:
                logger.removeHandler(existing_handler)
                existing_handler.close()
            logger.setLevel(numeric_level)
            logger.propagate = True

        # WatchFiles reports every raw filesystem event before Uvicorn applies
        # its reload include/exclude filter. Writing that INFO record to the log
        # file creates another event and can feed back indefinitely in dev mode.
        logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

        logging.captureWarnings(True)
        sys.excepthook = _log_uncaught_exception
        threading.excepthook = _log_uncaught_thread_exception

        _stdout_bridge = LoggingStream(
            logging.getLogger("stdout"),
            logging.INFO,
            _original_stdout,
        )
        _stderr_bridge = LoggingStream(
            logging.getLogger("stderr"),
            logging.ERROR,
            _original_stderr,
        )
        sys.stdout = _stdout_bridge
        sys.stderr = _stderr_bridge
        _active_settings = settings
        _configured = True

        logging.getLogger(__name__).info("Logging to %s", settings.file_path)
        return settings


def install_asyncio_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    def handle_asyncio_exception(
        event_loop: asyncio.AbstractEventLoop,
        context: dict[str, object],
    ) -> None:
        exception = context.get("exception")
        message = str(context.get("message", "Unhandled asyncio exception"))
        if isinstance(exception, BaseException):
            logging.getLogger("asyncio").error(
                message,
                exc_info=(type(exception), exception, exception.__traceback__),
            )
        else:
            logging.getLogger("asyncio").error("%s: %r", message, context)

    loop.set_exception_handler(handle_asyncio_exception)


def shutdown_logging() -> None:
    global _configured, _stdout_bridge, _stderr_bridge, _installed_handlers, _active_settings

    with _setup_lock:
        if not _configured:
            return
        if _stdout_bridge is not None:
            _stdout_bridge.flush()
        if _stderr_bridge is not None:
            _stderr_bridge.flush()

        if sys.stdout is _stdout_bridge:
            sys.stdout = _original_stdout
        if sys.stderr is _stderr_bridge:
            sys.stderr = _original_stderr
        sys.excepthook = _previous_sys_excepthook
        threading.excepthook = _previous_threading_excepthook
        logging.captureWarnings(False)

        root_logger = logging.getLogger()
        for handler in _installed_handlers:
            root_logger.removeHandler(handler)
            handler.flush()
            handler.close()
        _installed_handlers = []
        _stdout_bridge = None
        _stderr_bridge = None
        _active_settings = None
        _configured = False
        log_broker.clear()


def _log_uncaught_exception(
    exception_type: type[BaseException],
    exception: BaseException,
    traceback: TracebackType | None,
) -> None:
    if issubclass(exception_type, KeyboardInterrupt):
        _previous_sys_excepthook(exception_type, exception, traceback)
        return
    logging.getLogger("exceptions").critical(
        "Uncaught exception",
        exc_info=(exception_type, exception, traceback),
    )


def _log_uncaught_thread_exception(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    logging.getLogger("exceptions.thread").critical(
        "Uncaught exception in thread %s",
        args.thread.name if args.thread else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
