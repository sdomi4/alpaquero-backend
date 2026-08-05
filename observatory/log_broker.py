from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import threading
from typing import Any


@dataclass(eq=False)
class LogSubscription:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]
    active: bool = True
    dropped_count: int = 0


class LogBroker:
    """Thread-safe history and non-blocking fan-out for frontend log clients."""

    def __init__(self, history_size: int = 100, queue_size: int = 250):
        self._lock = threading.RLock()
        self._history_size = history_size
        self._queue_size = queue_size
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._subscriptions: set[LogSubscription] = set()
        self._next_sequence = 1
        self._next_record_id = 1

    def configure(self, *, history_size: int, queue_size: int) -> None:
        if history_size < 1:
            raise ValueError("history_size must be at least 1")
        if queue_size < 1:
            raise ValueError("queue_size must be at least 1")

        with self._lock:
            if self._subscriptions:
                raise RuntimeError("Cannot reconfigure the log broker with active clients")
            existing = list(self._history)[-history_size:]
            self._history_size = history_size
            self._queue_size = queue_size
            self._history = deque(existing, maxlen=history_size)

    def publish(
        self,
        lines: list[str],
        *,
        timestamp: str,
        level: str,
        logger_name: str,
    ) -> None:
        if not lines:
            lines = [""]

        with self._lock:
            record_id = self._next_record_id
            self._next_record_id += 1
            entries = []

            for line_index, line in enumerate(lines):
                entry = {
                    "seq": self._next_sequence,
                    "record_id": record_id,
                    "line_index": line_index,
                    "timestamp": timestamp,
                    "level": level,
                    "logger": logger_name,
                    "text": line,
                }
                self._next_sequence += 1
                self._history.append(entry)
                entries.append(entry)

            subscriptions = list(self._subscriptions)

        for subscription in subscriptions:
            try:
                subscription.loop.call_soon_threadsafe(
                    self._enqueue_entries,
                    subscription,
                    entries,
                )
            except RuntimeError:
                self.unsubscribe(subscription)

    def subscribe(self) -> tuple[LogSubscription, list[dict[str, Any]]]:
        loop = asyncio.get_running_loop()
        subscription = LogSubscription(
            loop=loop,
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        with self._lock:
            self._subscriptions.add(subscription)
            snapshot = [entry.copy() for entry in self._history]
        return subscription, snapshot

    def unsubscribe(self, subscription: LogSubscription) -> None:
        with self._lock:
            subscription.active = False
            self._subscriptions.discard(subscription)

    async def next_event(self, subscription: LogSubscription) -> dict[str, Any]:
        if subscription.dropped_count:
            dropped_count = subscription.dropped_count
            subscription.dropped_count = 0
            return {"type": "dropped", "count": dropped_count}
        return await subscription.queue.get()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [entry.copy() for entry in self._history]

    def clear(self) -> None:
        """Clear broker state. Intended for orderly shutdown and tests."""
        with self._lock:
            for subscription in self._subscriptions:
                subscription.active = False
            self._subscriptions.clear()
            self._history.clear()
            self._next_sequence = 1
            self._next_record_id = 1

    @staticmethod
    def _enqueue_entries(
        subscription: LogSubscription,
        entries: list[dict[str, Any]],
    ) -> None:
        if not subscription.active:
            return

        for entry in entries:
            if subscription.queue.full():
                try:
                    subscription.queue.get_nowait()
                    subscription.dropped_count += 1
                except asyncio.QueueEmpty:
                    pass
            subscription.queue.put_nowait({"type": "entry", "entry": entry})


log_broker = LogBroker()
