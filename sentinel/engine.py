"""RSIS808 v5 — Sentinel Engine. The gatekeeper.

- Charter rules are frozen and loaded once. Never mutated at runtime.
- Validators run in strict registration order. First non-ALLOW verdict wins.
- Returns only ALLOW, BLOCK, or ESCALATE. Dumb, loyal, predictable.
"""
from __future__ import annotations

from typing import Any

from .validators import ALLOW, Verdict


class SentinelEngine:
    def __init__(self, validators: list | None = None) -> None:
        self._validators: list = list(validators or [])
        self._frozen = False

    def add_validator(self, validator) -> None:
        if self._frozen:
            raise RuntimeError("Charter is frozen — validators cannot be added at runtime")
        self._validators.append(validator)

    def freeze(self) -> None:
        """Lock the Charter. Call once after setup; never unfreeze in production."""
        self._frozen = True

    def evaluate(self, payload: dict[str, Any], ctx: dict[str, Any] | None = None) -> Verdict:
        ctx = ctx or {}
        for validator in self._validators:
            try:
                verdict = validator.check(payload, ctx)
            except Exception as exc:
                # A validator that errors cannot vouch for the input — escalate.
                return Verdict("ESCALATE", validator.name, f"validator error: {exc}")
            if verdict.decision != ALLOW:
                return verdict
        return Verdict.allow("SentinelEngine", "all validators passed")
