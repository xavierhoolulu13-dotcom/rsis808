"""RSIS808 v5 — Synchronous Event Bus.

Single source of truth: every signal in the system flows through here.
- Synchronous + ordered: one lock, handlers run in registration order.
- Fail-open: a handler that raises is logged and skipped; the bus never crashes.
- Zero magic: no hidden side effects, no async fan-out.

Event shape: {event_type, timestamp, source, payload, event_id}
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Event:
    event_type: str
    source: str
    payload: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: dict[str, list[Handler]] = {}
        self._errors: list[dict[str, Any]] = []

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler. Handlers for a type run in subscription order."""
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event_type: str, source: str, payload: dict | None = None) -> Event:
        """Emit an event synchronously. Returns the event."""
        event = Event(event_type=event_type, source=source, payload=payload or {})
        # Snapshot handlers under lock, then run outside it (still strictly ordered).
        with self._lock:
            handlers = list(self._handlers.get(event_type, [])) + list(
                self._handlers.get("*", [])
            )
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # fail-open: log, never crash
                with self._lock:
                    self._errors.append(
                        {
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "handler": getattr(handler, "__name__", repr(handler)),
                            "error": f"{type(exc).__name__}: {exc}",
                            "timestamp": time.time(),
                        }
                    )
        return event

    def handler_errors(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._errors)
