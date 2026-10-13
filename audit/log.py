"""RSIS808 v5 — Audit Log.

Every event and every Sentinel decision lands here as JSONL.
Append-only. If it didn't get logged, it didn't happen.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: str | Path = "audit.jsonl") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, data: dict[str, Any]) -> None:
        entry = {"kind": kind, "timestamp": time.time(), **data}
        line = json.dumps(entry, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def record_event(self, event) -> None:
        self.record(
            "event",
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "source": event.source,
                "payload": event.payload,
            },
        )

    def record_decision(
        self, event_id: str, decision: str, validator: str, reason: str
    ) -> None:
        self.record(
            "decision",
            {
                "event_id": event_id,
                "decision": decision,
                "validator": validator,
                "reason": reason,
            },
        )
