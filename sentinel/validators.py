"""RSIS808 v5 — Validators. Bouncers, not thinkers.

Each validator returns a Verdict. The Sentinel runs them in strict order;
the first non-ALLOW verdict wins. Validators never mutate the Charter.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


ALLOW = "ALLOW"
BLOCK = "BLOCK"
ESCALATE = "ESCALATE"


@dataclass
class Verdict:
    decision: str  # ALLOW | BLOCK | ESCALATE
    validator: str
    reason: str

    @classmethod
    def allow(cls, validator: str, reason: str = "checks passed") -> "Verdict":
        return cls(ALLOW, validator, reason)


class InputValidator:
    """Required fields: intent, source, user_id. BLOCK if any are missing."""

    name = "InputValidator"
    REQUIRED = ("intent", "source", "user_id")

    def check(self, payload: dict[str, Any], ctx: dict[str, Any]) -> Verdict:
        missing = [f for f in self.REQUIRED if not payload.get(f)]
        if missing:
            return Verdict(BLOCK, self.name, f"missing required fields: {missing}")
        return Verdict.allow(self.name)


class WorkflowValidator:
    """Whitelist check: workflow must be in the approved list. ESCALATE if unknown."""

    name = "WorkflowValidator"

    def __init__(self, approved_workflows: list[str]) -> None:
        self.approved = set(approved_workflows)

    def check(self, payload: dict[str, Any], ctx: dict[str, Any]) -> Verdict:
        workflow = payload.get("workflow", "default")
        if workflow not in self.approved:
            return Verdict(
                ESCALATE, self.name, f"unknown workflow '{workflow}' — needs human review"
            )
        return Verdict.allow(self.name, f"workflow '{workflow}' approved")


class PolicyValidator:
    """Enforces execution_limits: max_retries and max_runtime_s."""

    name = "PolicyValidator"

    def __init__(self, max_retries: int = 3, max_runtime_s: int = 300) -> None:
        self.max_retries = max_retries
        self.max_runtime_s = max_runtime_s

    def check(self, payload: dict[str, Any], ctx: dict[str, Any]) -> Verdict:
        requested_retries = int(payload.get("max_retries", 0))
        if requested_retries > self.max_retries:
            return Verdict(
                BLOCK,
                self.name,
                f"requested max_retries={requested_retries} exceeds limit {self.max_retries}",
            )
        est_runtime = float(payload.get("estimated_runtime_s", 0))
        if est_runtime > self.max_runtime_s:
            return Verdict(
                BLOCK,
                self.name,
                f"estimated runtime {est_runtime}s exceeds limit {self.max_runtime_s}s",
            )
        return Verdict.allow(self.name)


class AgentIntegrityValidator:
    """Compares agent_id against a trusted checksum registry. BLOCK if modified/unknown."""

    name = "AgentIntegrityValidator"

    def __init__(self, trusted: dict[str, str] | None = None) -> None:
        # trusted: {agent_id: sha256 checksum}
        self.trusted = trusted or {}

    @staticmethod
    def checksum(agent_id: str, secret: str = "") -> str:
        return hashlib.sha256(f"{agent_id}:{secret}".encode()).hexdigest()

    def check(self, payload: dict[str, Any], ctx: dict[str, Any]) -> Verdict:
        agent_id = payload.get("agent_id")
        if not agent_id:
            return Verdict.allow(self.name, "no agent_id claimed")
        expected = self.trusted.get(agent_id)
        if expected is None:
            return Verdict(BLOCK, self.name, f"agent_id '{agent_id}' not in trust registry")
        presented = payload.get("agent_checksum", "")
        if presented != expected:
            return Verdict(BLOCK, self.name, f"checksum mismatch for agent '{agent_id}'")
        return Verdict.allow(self.name, f"agent '{agent_id}' integrity verified")
