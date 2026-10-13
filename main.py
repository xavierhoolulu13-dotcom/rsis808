"""RSIS808 v5 — Unified Validation & Execution. Demo entrypoint.

    python3 main.py

[INFO] System initialized. Mode = Unified. Friction = 0.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from audit.log import AuditLog
from core.event_bus import EventBus
from orchestrator.executor import Task, TaskExecutor
from sentinel.engine import SentinelEngine
from sentinel.validators import (
    AgentIntegrityValidator,
    InputValidator,
    PolicyValidator,
    WorkflowValidator,
)


def log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}")


async def main() -> None:
    bus = EventBus()
    audit = AuditLog("audit.jsonl")
    bus.subscribe("*", audit.record_event)

    # Sentinel: frozen Charter, validators in strict order.
    sentinel = SentinelEngine([
        InputValidator(),
        WorkflowValidator(approved_workflows=["default", "build", "notify"]),
        PolicyValidator(max_retries=3, max_runtime_s=300),
        AgentIntegrityValidator(trusted={"agent-1": AgentIntegrityValidator.checksum("agent-1")}),
    ])
    sentinel.freeze()
    log("INFO", "System initialized.")
    log("INFO", "Mode = Unified")
    log("INFO", "Sentinel loaded. Rules = Frozen.")
    log("INFO", "Orchestrator ready. Threads = 4.")

    def on_event(kind: str, data: dict) -> None:
        if kind == "sentinel_decision":
            audit.record_decision(
                data.get("task_id", ""), data["decision"],
                data["validator"], data["reason"],
            )
            log("SENTINEL", f"{data['decision']} — {data['validator']}: {data['reason']}")

    executor = TaskExecutor(sentinel, max_parallel=4, on_event=on_event)

    async def ok_task():
        await asyncio.sleep(0.1)
        return "done"

    attempt = {"n": 0}

    async def flaky_task():
        attempt["n"] += 1
        if attempt["n"] < 3:
            raise RuntimeError("transient failure")
        return "recovered on attempt 3"

    checksum = AgentIntegrityValidator.checksum("agent-1")
    tasks = [
        # ALLOW: valid, known workflow, trusted agent
        Task("t-allow", {"intent": "build", "source": "demo", "user_id": "u1",
                         "workflow": "build", "agent_id": "agent-1",
                         "agent_checksum": checksum}, ok_task),
        # BLOCK: missing user_id
        Task("t-block-input", {"intent": "build", "source": "demo",
                               "workflow": "build"}, ok_task),
        # ESCALATE: unknown workflow
        Task("t-escalate", {"intent": "notify", "source": "demo", "user_id": "u1",
                            "workflow": "nuke_everything"}, ok_task),
        # BLOCK: untrusted agent
        Task("t-block-agent", {"intent": "build", "source": "demo", "user_id": "u1",
                               "workflow": "default", "agent_id": "agent-9",
                               "agent_checksum": "bogus"}, ok_task),
        # ALLOW then retry -> COMPLETE (exponential backoff)
        Task("t-retry", {"intent": "notify", "source": "demo", "user_id": "u1",
                         "workflow": "notify"}, flaky_task),
    ]

    results = await executor.run(tasks)
    print()
    for r in results:
        log("RESULT", f"{r.task_id}: {r.state.value} after {r.attempts} attempt(s)"
            + (f" — {r.error}" if r.error else f" — {r.output}"))
    log("INFO", "Friction = 0.")


if __name__ == "__main__":
    asyncio.run(main())
