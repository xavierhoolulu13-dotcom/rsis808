# RSIS808 v5 — Unified Validation & Execution

> "Bouncers, not thinkers. Returns only ALLOW, BLOCK, or ESCALATE."
> Zero Friction. Zero Magic.

The governor for the Hoolulu Factory: a deterministic validation and execution
system. Every signal flows through one synchronous event bus. Every action
passes the Sentinel before it runs. Nothing outbound without an ALLOW.

## Run it

```
python3 main.py
```

Stdlib only. No dependencies. Python 3.10+.

## Architecture

```
Input Event → Sentinel Engine → ALLOW → Orchestrator (TaskExecutor) → done
                             → BLOCK     (never executes)
                             → ESCALATE  (human review)
```

- **core/event_bus.py** — Synchronous EventBus. Single source of truth, ordered
  handlers, fail-open (handler errors are logged, never crash the bus).
- **core/state_machine.py** — IDLE → PROCESSING → COMPLETE; FAIL → RETRY_WAIT
  (exponential backoff: `2^retry_count * base_interval`) → FAILED_STATE.
  Illegal transitions raise.
- **sentinel/engine.py** — Frozen Charter. Validators run in strict order;
  first non-ALLOW verdict wins. Returns only ALLOW / BLOCK / ESCALATE.
- **sentinel/validators.py** — The four bouncers:
  - `InputValidator` — required fields (intent, source, user_id); BLOCK if missing.
  - `WorkflowValidator` — workflow must be whitelisted; ESCALATE if unknown.
  - `PolicyValidator` — enforces `execution_limits.yaml` (max_retries, max_runtime_s).
  - `AgentIntegrityValidator` — agent_id vs trusted checksum; BLOCK if modified.
- **orchestrator/executor.py** — TaskExecutor: asyncio.Semaphore (default 4),
  exponential-backoff retries, non-blocking heartbeat every 30s.
- **audit/log.py** — Append-only JSONL. Every event + every Sentinel decision.
- **config/** — `charter.json` (frozen rules), `execution_limits.yaml`, `settings.yaml`.

## Charter rules (frozen)

1. Every signal flows through the EventBus. No side channels.
2. The Sentinel returns only ALLOW, BLOCK, or ESCALATE.
3. Validators check; they never decide policy.
4. Charter rules load once, never mutate at runtime.
5. Handler failures are logged. The bus never crashes.
6. State transitions are rigid. Illegal transitions raise.
7. Retries use exponential backoff.
8. Nothing outbound without an ALLOW verdict.

## Extend it

Add a validator: subclass the pattern in `sentinel/validators.py` (a `name`
and a `check(payload, ctx) -> Verdict`), register it with
`sentinel.add_validator(...)` **before** `freeze()`. After freeze, the
Charter is locked — to change rules, you change code and redeploy.
