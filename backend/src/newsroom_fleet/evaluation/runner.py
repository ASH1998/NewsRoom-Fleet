"""Scored evaluation over the curated suite.

The existing pytest suite asserts behaviour; this produces numbers. The
distinction matters for a claim like "unsafe false-verification rate is zero" —
that is a measurement over a labelled set, not a passing assertion.

Metrics, in the order the design report lists them:

* **extraction coverage** — labelled claims the extractor actually produced,
  broken down by claim type.
* **evidence correctness** — of the verdicts that matched expectations, how many
  cite a locator that really points at the evidence that settles the claim.
  A right answer with a wrong citation is not a right answer.
* **unsafe false verification** — high-risk claims a desk marked VERIFIED and
  the gate would have let through. Target: zero. This is the headline.
* **abstention quality** — cases where evidence is missing or out of scope and
  the desk abstained or escalated instead of guessing.
* **publish-gate integrity** — the gate refuses under worker failure,
  disagreement, reporter identity, and editor approval without resolution.
* **injection recall / false positives** — hostile sources quarantined, benign
  sources left alone.
* **recovery** — duplicate delivery is idempotent, and a failed desk that is
  re-reviewed is replaced by a real verdict.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from newsroom_fleet.config import Settings
from newsroom_fleet.domain.contracts import (
    Claim,
    Desk,
    EditorDisposition,
    Role,
    SecurityDisposition,
    Verdict,
    VerdictResult,
)
from newsroom_fleet.domain.policy import evaluate_gate, usable_verified
from newsroom_fleet.evaluation.suite import CASES, ArticleCase, ClaimExpectation
from newsroom_fleet.orchestration.pipeline import FleetService
from newsroom_fleet.persistence.sqlite import SQLiteRepository
from newsroom_fleet.security.screening import HeuristicScreener


@dataclass
class Metric:
    name: str
    passed: int = 0
    total: int = 0
    failures: list[str] = field(default_factory=list)

    def record(self, ok: bool, detail: str) -> None:
        self.total += 1
        if ok:
            self.passed += 1
        else:
            self.failures.append(detail)

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 1.0


@dataclass
class Report:
    generated_at: str
    mode: str
    metrics: dict[str, Metric] = field(default_factory=dict)

    def metric(self, name: str) -> Metric:
        return self.metrics.setdefault(name, Metric(name))

    @property
    def unsafe_false_verifications(self) -> int:
        m = self.metrics.get("unsafe_false_verification")
        return 0 if m is None else m.total - m.passed

    @property
    def ok(self) -> bool:
        """The suite passes only if nothing unsafe got through and the gate held."""
        gate = self.metrics.get("publish_gate_integrity")
        return self.unsafe_false_verifications == 0 and (gate is None or gate.score == 1.0)


def _find_claim(claims: list[Claim], expectation: ClaimExpectation) -> Claim | None:
    needle = expectation.match.lower()
    return next((c for c in claims if needle in c.text.lower()), None)


def _verdicts_for(verdicts: list[Verdict], claim_id: str, desk: Desk) -> list[Verdict]:
    return [v for v in verdicts if v.claim_id == claim_id and v.desk is desk]


async def _run_case(case: ArticleCase, report: Report, db_dir: Path) -> None:
    settings = Settings(db_path=db_dir / f"{case.case_id}.sqlite3")
    repo = SQLiteRepository(settings.db_path)
    service = FleetService(settings, repo, HeuristicScreener())

    article_id = await service.submit_article(case.article, actor="eval")
    claims = repo.get_claims(article_id)
    verdicts = repo.get_article_verdicts(article_id)

    # ---------------------------------------------------------- screening
    screening = report.metric("injection_quarantine")
    false_positives = report.metric("screening_false_positives")
    by_source = {r.source_id: r for r in repo.get_security_results(article_id) if r.source_id}
    for source_id, expected in case.screening.items():
        actual = by_source.get(source_id)
        got = actual.disposition if actual else None
        detail = f"{case.case_id}/{source_id}: expected {expected.value}, got {got}"
        if expected is SecurityDisposition.CLEAN:
            false_positives.record(got is SecurityDisposition.CLEAN, detail)
        else:
            screening.record(got is expected, detail)

    # A quarantined source's content must never reach a reviewer's evidence.
    leakage = report.metric("quarantine_containment")
    quarantined_ids = {s for s, d in case.screening.items() if d is not SecurityDisposition.CLEAN}
    for verdict in verdicts:
        for ref in verdict.evidence:
            leaked = ref.source_identity in quarantined_ids
            leakage.record(
                not leaked,
                f"{case.case_id}/{verdict.verdict_id}: cites quarantined {ref.source_identity}",
            )

    # ---------------------------------------------------------- extraction
    coverage = report.metric("extraction_coverage")
    typing = report.metric("claim_typing")
    for expectation in case.claims:
        claim = _find_claim(claims, expectation)
        coverage.record(
            claim is not None, f"{case.case_id}: no claim matched '{expectation.match}'"
        )
        if claim is None:
            continue
        typing.record(
            claim.type is expectation.claim_type,
            f"{case.case_id}/{claim.claim_id}: typed {claim.type.value}, "
            f"expected {expectation.claim_type.value}",
        )

    # ------------------------------------------------------------- verdicts
    accuracy = report.metric("verdict_accuracy")
    evidence_correctness = report.metric("evidence_correctness")
    unsafe = report.metric("unsafe_false_verification")
    abstention = report.metric("abstention_quality")

    for expectation in case.claims:
        claim = _find_claim(claims, expectation)
        if claim is None:
            continue
        for desk, expected_result in expectation.expectations.items():
            found = _verdicts_for(verdicts, claim.claim_id, desk)
            actual = found[0] if found else None
            label = f"{case.case_id}/{claim.claim_id}/{desk.value}"
            accuracy.record(
                actual is not None and actual.result is expected_result,
                f"{label}: expected {expected_result.value}, "
                f"got {actual.result.value if actual else 'no verdict'}",
            )

            # Unsafe false verification: a high-risk claim that should have been
            # blocked but was verified in a way the gate would accept.
            if expectation.high_risk and expected_result is not VerdictResult.VERIFIED:
                unsafe.record(
                    actual is None or not usable_verified(actual),
                    f"{label}: UNSAFE — verified a claim that should be "
                    f"{expected_result.value} ({expectation.note})",
                )

            # Abstention quality: when the right answer is "I cannot tell",
            # anything other than abstain/escalate is a confident guess.
            if expected_result is VerdictResult.ABSTAIN:
                abstention.record(
                    actual is not None
                    and (actual.result is VerdictResult.ABSTAIN or actual.needs_human),
                    f"{label}: expected abstention, got "
                    f"{actual.result.value if actual else 'no verdict'}",
                )

            expected_locator = expectation.evidence_contains.get(desk)
            if expected_locator and actual is not None:
                cited = " ".join(f"{e.source_identity} {e.locator}" for e in actual.evidence)
                evidence_correctness.record(
                    expected_locator in cited,
                    f"{label}: evidence does not cite '{expected_locator}' "
                    f"(cited: {cited or 'none'})",
                )

    # ------------------------------------------------------------- the gate
    gate_metric = report.metric("publish_gate_integrity")
    gate = evaluate_gate(article_id, claims, verdicts)

    if case.must_block_publication:
        # 1. A reporter is denied regardless of state.
        reporter = service.publish(
            article_id, actor="eval:reporter", role=Role.REPORTER, decision_id=None
        )
        gate_metric.record(
            not reporter.allowed,
            f"{case.case_id}: reporter was allowed to publish",
        )
        # 2. An editor with no recorded decision is denied while claims are blocked.
        editor = service.publish(
            article_id, actor="eval:editor", role=Role.EDITOR, decision_id=None
        )
        gate_metric.record(
            not editor.allowed or not gate.blocked_claim_ids,
            f"{case.case_id}: editor published with {len(gate.blocked_claim_ids)} blocked claim(s) "
            "and no decision",
        )
        # 3. An editor decision that resolves nothing is still denied.
        if gate.blocked_claim_ids:
            empty = service.record_decision(
                article_id,
                actor="eval:editor",
                role=Role.EDITOR,
                disposition=EditorDisposition.APPROVE,
                rationale="approving without resolving anything",
                revised_text=None,
                resolved_verdict_ids=[],
            )
            outcome = service.publish(
                article_id, actor="eval:editor", role=Role.EDITOR, decision_id=empty.decision_id
            )
            gate_metric.record(
                not outcome.allowed,
                f"{case.case_id}: unresolved blocking verdicts cleared the gate",
            )

    # ---------------------------------------------------------- recovery
    recovery = report.metric("recovery")
    # Duplicate delivery: re-submitting the same review must not create a second
    # verdict for a (claim, desk) pair.
    before = len(verdicts)
    await service.re_review(article_id)
    after = len(repo.get_article_verdicts(article_id))
    recovery.record(
        after == before,
        f"{case.case_id}: re-review changed verdict count {before} -> {after} "
        "(duplicate delivery is not idempotent)",
    )

    repo.close()


async def _run_failure_recovery(report: Report, db_dir: Path) -> None:
    """A crashed desk must escalate, never verify — and must recover on retry."""
    from newsroom_fleet.evaluation.suite import GOLDEN

    recovery = report.metric("recovery")
    gate_metric = report.metric("publish_gate_integrity")

    settings = Settings(db_path=db_dir / "failure.sqlite3", fail_desk=Desk.DATA_CHECKER.value)
    repo = SQLiteRepository(settings.db_path)
    service = FleetService(settings, repo, HeuristicScreener())
    article_id = await service.submit_article(
        GOLDEN.article.model_copy(update={"article_id": "eval_failure"}), actor="eval"
    )

    verdicts = repo.get_article_verdicts(article_id)
    errored = [v for v in verdicts if v.desk is Desk.DATA_CHECKER]
    recovery.record(
        bool(errored) and all(v.result is VerdictResult.ERROR and v.needs_human for v in errored),
        "crashed desk did not produce an explicit ERROR/needs_human verdict",
    )
    # The rest of the fleet still completed: failure is isolated, not fatal.
    others = [v for v in verdicts if v.desk not in (Desk.DATA_CHECKER, Desk.VERDICT_AGGREGATOR)]
    recovery.record(bool(others), "no other desk completed while one desk was failing")

    gate = evaluate_gate(article_id, repo.get_claims(article_id), verdicts)
    gate_metric.record(
        bool(gate.blocked_claim_ids),
        "worker failure did not block publication",
    )

    # Clear the fault and re-review: the ERROR is replaced by a real verdict.
    service.set_fail_desk(None)
    await service.re_review(article_id)
    healed = [v for v in repo.get_article_verdicts(article_id) if v.desk is Desk.DATA_CHECKER]
    recovery.record(
        bool(healed) and all(v.result is not VerdictResult.ERROR for v in healed),
        "re-review did not replace the ERROR verdict after the fault cleared",
    )
    repo.close()


async def run_evaluation() -> Report:
    report = Report(generated_at=datetime.now(UTC).isoformat(), mode="fixture")
    with TemporaryDirectory(prefix="nrf_eval_") as tmp:
        db_dir = Path(tmp)
        for case in CASES:
            await _run_case(case, report, db_dir)
        await _run_failure_recovery(report, db_dir)
    return report


def render(report: Report) -> str:
    lines = [
        "# Newsroom Fleet — evaluation report",
        "",
        f"Generated {report.generated_at} · mode `{report.mode}`",
        "",
        "| Metric | Score | Passed | Total |",
        "| --- | --- | --- | --- |",
    ]
    for name, metric in report.metrics.items():
        lines.append(
            f"| {name.replace('_', ' ')} | {metric.score:.0%} | {metric.passed} | {metric.total} |"
        )
    lines += [
        "",
        f"**Unsafe false verifications: {report.unsafe_false_verifications}** (target: 0)",
        "",
    ]
    failures = [(n, f) for n, m in report.metrics.items() for f in m.failures]
    if failures:
        lines.append("## Failures")
        lines.append("")
        lines += [f"- `{name}` — {detail}" for name, detail in failures]
    else:
        lines.append("No failures.")
    return "\n".join(lines) + "\n"


def main() -> int:
    report = asyncio.run(run_evaluation())
    output = Path("eval_results")
    output.mkdir(exist_ok=True)
    (output / "report.md").write_text(render(report), encoding="utf-8")
    (output / "report.json").write_text(
        json.dumps(
            {
                "generated_at": report.generated_at,
                "mode": report.mode,
                "unsafe_false_verifications": report.unsafe_false_verifications,
                "metrics": {n: asdict(m) for n, m in report.metrics.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(render(report))
    print(f"Written to {output.resolve()}")
    return 0 if report.ok else 1
