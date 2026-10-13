"""RSIS808 v5 — Orchestrator / TaskExecutor. The parallel executor.

- Concurrency: asyncio.Semaphore caps parallel tasks (default 4).
- Retry policy: exponential backoff, wait = 2^attempt * base_interval. Boring, deterministic.
- Heartbeat: non-blocking background task updates last_beat every 30s.
- Every task runs through the Sentinel first: BLOCK/ESCALATE never reach execution.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.state_machine import State, TaskState
from sentinel.engine import SentinelEngine


@dataclass
class TaskResult:
    task_id: str
    state: State
    attempts: int
    output: Any = None
    error: str = ""
    duration_s: float = 0.0


@dataclass
class Task:
    task_id: str
    payload: dict
    coro: Callable[[], Awaitable[Any]]
    state: TaskState = field(init=False)

    def __post_init__(self) -> None:
        self.state = TaskState(task_id=self.task_id)


class TaskExecutor:
    def __init__(
        self,
        sentinel: SentinelEngine,
        max_parallel: int = 4,
        max_retries: int = 3,
        base_interval_s: float = 1.0,
        heartbeat_interval_s: float = 30.0,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.sentinel = sentinel
        self.semaphore = asyncio.Semaphore(max_parallel)
        self.max_retries = max_retries
        self.base_interval_s = base_interval_s
        self.heartbeat_interval_s = heartbeat_interval_s
        self.on_event = on_event or (lambda kind, data: None)
        self.last_beat: float = time.time()
        self._heartbeat_task: asyncio.Task | None = None

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval_s)
            self.last_beat = time.time()
            self.on_event("heartbeat", {"last_beat": self.last_beat})

    async def run(self, tasks: list[Task]) -> list[TaskResult]:
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        try:
            return await asyncio.gather(*(self._run_one(t) for t in tasks))
        finally:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()

    async def _run_one(self, task: Task) -> TaskResult:
        started = time.time()
        task.state.max_retries = self.max_retries
        task.state.base_interval_s = self.base_interval_s

        # Gate: Sentinel decides before anything executes.
        verdict = self.sentinel.evaluate(task.payload)
        self.on_event("sentinel_decision", {
            "task_id": task.task_id,
            "decision": verdict.decision,
            "validator": verdict.validator,
            "reason": verdict.reason,
        })
        if verdict.decision != "ALLOW":
            return TaskResult(
                task_id=task.task_id,
                state=State.FAILED_STATE,
                attempts=0,
                error=f"{verdict.decision} by {verdict.validator}: {verdict.reason}",
                duration_s=time.time() - started,
            )

        async with self.semaphore:
            task.state.start()
            attempts = 0
            while True:
                attempts += 1
                try:
                    output = await task.coro()
                    task.state.succeed()
                    return TaskResult(task.task_id, State.COMPLETE, attempts, output,
                                     duration_s=time.time() - started)
                except Exception as exc:
                    wait = task.state.fail(f"{type(exc).__name__}: {exc}")
                    self.on_event("task_failed", {
                        "task_id": task.task_id, "attempt": attempts,
                        "error": task.state.last_error, "retry_in_s": wait,
                    })
                    if wait < 0:
                        return TaskResult(task.task_id, State.FAILED_STATE, attempts,
                                          error=task.state.last_error,
                                          duration_s=time.time() - started)
                    await asyncio.sleep(wait)
                    task.state.retry_now()
