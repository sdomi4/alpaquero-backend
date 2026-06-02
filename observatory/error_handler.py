from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import threading
from typing import Any, Literal


ErrorLevel = Literal["error", "warning", "info"]
ERROR_LEVELS: set[str] = {"error", "warning", "info"}


def validate_error_level(level: str) -> ErrorLevel:
    if level not in ERROR_LEVELS:
        raise ValueError(f"Unknown error level: {level}")
    return level  # type: ignore[return-value]


def format_error_text(error: BaseException | str, context: str | None = None) -> str:
    if isinstance(error, str):
        text = error
    else:
        text = getattr(error, "message", None) or str(error) or repr(error)

    if context:
        return f"{context}: {text}"
    return text


class ErrorBroadcaster:
    def __init__(self):
        self._connections: set[Any] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.RLock()

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        with self._lock:
            self._loop = loop

    def connect(self, websocket: Any):
        with self._lock:
            self._connections.add(websocket)

        try:
            self.set_loop(asyncio.get_running_loop())
        except RuntimeError:
            pass

    def disconnect(self, websocket: Any):
        with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: str, level: ErrorLevel):
        payload = {
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            connections = list(self._connections)

        failed_connections = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                failed_connections.append(websocket)

        if failed_connections:
            with self._lock:
                for websocket in failed_connections:
                    self._connections.discard(websocket)

    async def report_async(
        self,
        error: BaseException | str,
        context: str | None = None,
        *,
        level: ErrorLevel,
    ) -> str:
        level = validate_error_level(level)
        message = format_error_text(error, context)
        print(f"[{level.upper()}] {message}")
        await self.broadcast(message, level)
        return message

    def report(
        self,
        error: BaseException | str,
        context: str | None = None,
        *,
        level: ErrorLevel,
    ) -> str:
        level = validate_error_level(level)
        message = format_error_text(error, context)
        print(f"[{level.upper()}] {message}")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            with self._lock:
                loop = self._loop

            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message, level), loop)
            return message

        loop.create_task(self.broadcast(message, level))
        return message


error_handler = ErrorBroadcaster()


def set_error_loop(loop: asyncio.AbstractEventLoop):
    error_handler.set_loop(loop)


def connect_error_websocket(websocket: Any):
    error_handler.connect(websocket)


def disconnect_error_websocket(websocket: Any):
    error_handler.disconnect(websocket)


def handle_error(error: BaseException | str, context: str | None = None, *, level: ErrorLevel) -> str:
    return error_handler.report(error, context, level=level)


async def handle_error_async(
    error: BaseException | str,
    context: str | None = None,
    *,
    level: ErrorLevel,
) -> str:
    return await error_handler.report_async(error, context, level=level)
