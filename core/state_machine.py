"""RSIS808 v5 — Deterministic State Machine.

IDLE -> PROCESSING -> COMPLETE
                  -> FAIL -> RETRY_WAIT -> PROCESSING (retry)
                                     -> FAILED_STATE (retries exhausted)

Retries use exponential backoff: wait_time = 2^retry_count * base_interval.
Boring is good. Transitions are rigid. No surprises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    RETRY_WAIT = "RETRY_WAIT"
    FAILED_STATE = "FAILED_STATE"


# Allowed transitions. Anything else raises — deterministic means deterministic.
_TRANSITIONS: dict[State, set[State]] = {
    State.IDLE: {State.PROCESSING},
    State.PROCESSING: {State.COMPLETE, State.FAIL},
    State.FAIL: {State.RETRY_WAIT, State.FAILED_STATE},
    State.RETRY_WAIT: {State.PROCESSING, State.FAILED_STATE},
    State.COMPLETE: set(),
    State.FAILED_STATE: set(),
}


class IllegalTransition(Exception):
    pass


@dataclass
class TaskState:
    task_id: str
    state: State = State.IDLE
    retry_count: int = 0
    max_retries: int = 3
    base_interval_s: float = 1.0
    last_error: str = ""

    def transition(self, to: State) -> None:
        if to not in _TRANSITIONS[self.state]:
            raise IllegalTransition(f"{self.state} -> {to} is not allowed")
        self.state = to

    def start(self) -> None:
        self.transition(State.PROCESSING)

    def succeed(self) -> None:
        self.transition(State.COMPLETE)

    def fail(self, error: str = "") -> float:
        """Record a failure. Returns seconds to wait before retry, or -1 if exhausted."""
        self.last_error = error
        self.transition(State.FAIL)
        if self.retry_count < self.max_retries:
            self.retry_count += 1
            self.transition(State.RETRY_WAIT)
            return (2 ** (self.retry_count - 1)) * self.base_interval_s
        self.transition(State.FAILED_STATE)
        return -1.0

    def retry_now(self) -> None:
        self.transition(State.PROCESSING)
