"""Result structures shared by the library API, the CLI and the MCP server.

One serialisable shape carries a whole run, so there is no second representation to keep in
sync. A run is a flat list of :class:`Check` records; grouping (by target, by check id, by
meta-schema version) is done at render time rather than baked into the structure.

Statuses follow the reference harness (``scripts/validate.mjs`` in oold-schema): only ``fail``
is fatal to the verdict. ``warn`` marks a SHOULD-level finding, ``skip`` marks a check that
could not run for a documented reason (a cyclic scoped ``@context``, for instance).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["ok", "fail", "warn", "skip"]
Verbosity = Literal["summary", "full"]

OK: Status = "ok"
FAIL: Status = "fail"
WARN: Status = "warn"
SKIP: Status = "skip"


@dataclass
class Check:
    """One check applied to one target.

    ``id`` is a stable dotted identifier (``schema.meta``, ``roundtrip.instance``, ...) so
    results can be filtered and compared across runs; the golden parity test keys on it.
    ``meta_version`` is set only for the checks whose outcome depends on which meta-schema
    version was used, which keeps a multi-version run readable.
    """

    id: str
    target: str
    status: Status
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    meta_version: str | None = None
    #: The normative rule this check enforces, e.g. ``OOLD-RT-08f2``. None when the check maps to
    #: no single requirement, or when the meta version in use predates the rule catalog.
    rule: str | None = None

    @property
    def failed(self) -> bool:
        return self.status == FAIL

    def to_dict(self, verbosity: Verbosity = "summary") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "target": self.target,
            "status": self.status,
        }
        if self.message:
            payload["message"] = self.message
        if self.meta_version is not None:
            payload["meta_version"] = self.meta_version
        if self.rule is not None:
            payload["rule"] = self.rule
        if self.detail and verbosity == "full":
            payload["detail"] = self.detail
        return payload

    def line(self) -> str:
        """A single-line rendering, in the reference harness's column style."""
        label = self.status.upper().ljust(4)
        rule = f" {self.rule}" if self.rule else ""
        version = f" [{self.meta_version}]" if self.meta_version else ""
        message = f": {self.message}" if self.message else ""
        return f"{label}{rule} {self.id:<24} {self.target}{version}{message}"


@dataclass
class Report:
    """Everything one run produced."""

    source: str
    meta_versions: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    fatal_error: str | None = None

    # ------------------------------------------------------------------ building

    def add(
        self,
        id: str,
        target: str,
        status: Status,
        message: str = "",
        detail: dict[str, Any] | None = None,
        meta_version: str | None = None,
        rule: str | None = None,
    ) -> Check:
        check = Check(
            id=id,
            target=target,
            status=status,
            message=message,
            detail=detail or {},
            meta_version=meta_version,
            rule=rule,
        )
        self.checks.append(check)
        return check

    def extend(self, checks: list[Check]) -> None:
        self.checks.extend(checks)

    # ------------------------------------------------------------------ querying

    @property
    def passed(self) -> bool:
        return self.fatal_error is None and not any(c.failed for c in self.checks)

    @property
    def counts(self) -> dict[str, int]:
        tally = Counter(c.status for c in self.checks)
        return {status: tally.get(status, 0) for status in (OK, FAIL, WARN, SKIP)}

    def by_status(self, status: Status) -> list[Check]:
        return [c for c in self.checks if c.status == status]

    def failures(self) -> list[Check]:
        return self.by_status(FAIL)

    def warnings(self) -> list[Check]:
        return self.by_status(WARN)

    def targets(self) -> list[str]:
        seen: list[str] = []
        for check in self.checks:
            if check.target not in seen:
                seen.append(check.target)
        return seen

    # ------------------------------------------------------------------ rendering

    def summary(self) -> dict[str, Any]:
        counts = self.counts
        return {
            "source": self.source,
            "passed": self.passed,
            "meta_versions": list(self.meta_versions),
            "targets": len(self.targets()),
            "checks": len(self.checks),
            **counts,
            "fatal_error": self.fatal_error,
        }

    def to_dict(self, verbosity: Verbosity = "summary") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "passed": self.passed,
            "summary": self.summary(),
            "checks": [c.to_dict(verbosity) for c in self.checks],
        }
        if self.notes:
            payload["notes"] = list(self.notes)
        if self.fatal_error:
            payload["fatal_error"] = self.fatal_error
        return payload


def failure_reasons(report: Report) -> list[str]:
    """Human-readable reasons the run did not pass, most important first."""
    if report.fatal_error:
        return [report.fatal_error]
    return [f"{c.id} {c.target}: {c.message}" for c in report.failures()]
