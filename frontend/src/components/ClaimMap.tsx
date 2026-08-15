import type { ArticleView, Claim, ClaimAssessment, Verdict } from "../types";
import { Badge, Empty, Panel, deskLabel, verdictTone } from "./ui";

function VerdictCard({ verdict }: { verdict: Verdict }) {
  return (
    <li className="rounded border border-stone-800 bg-stone-950/50 px-2.5 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium text-stone-300">{deskLabel(verdict.desk)}</span>
        <div className="flex items-center gap-1">
          {verdict.needs_human && <Badge tone="warn">needs human</Badge>}
          <Badge tone={verdictTone(verdict.result)}>{verdict.result}</Badge>
        </div>
      </div>

      <p className="mt-1 text-[11px] leading-relaxed text-stone-400">{verdict.reason}</p>

      {verdict.error_detail && (
        <p className="mt-1 font-mono text-[10px] text-red-400">{verdict.error_detail}</p>
      )}

      {verdict.flags.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {verdict.flags.map((flag) => (
            <Badge key={flag} tone="warn">
              {flag}
            </Badge>
          ))}
        </div>
      )}

      {/* Evidence is first-class: a verdict without a locator can never be VERIFIED. */}
      {verdict.evidence.length > 0 && (
        <ul className="mt-1.5 space-y-1 border-l border-stone-800 pl-2">
          {verdict.evidence.map((evidence) => (
            <li key={evidence.locator} className="text-[10px] text-stone-500">
              <span className="font-mono text-sky-400/80">{evidence.locator}</span>
              <span className="text-stone-600"> · {evidence.source_identity}</span>
              {evidence.excerpt && (
                <p className="mt-0.5 text-stone-500 italic">“{evidence.excerpt}”</p>
              )}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-1.5 font-mono text-[9px] text-stone-700">
        {verdict.verdict_id} · {verdict.agent_version} · schema {verdict.schema_version} · conf{" "}
        {verdict.confidence.toFixed(2)}
      </p>
    </li>
  );
}

function ClaimCard({
  claim,
  verdicts,
  assessment,
  selected,
  onSelect,
}: {
  claim: Claim;
  verdicts: Verdict[];
  assessment: ClaimAssessment | undefined;
  selected: boolean;
  onSelect: () => void;
}) {
  const ok = assessment?.ok ?? false;
  const deskVerdicts = verdicts.filter((v) => v.desk !== "verdict_aggregator");
  const aggregate = verdicts.find((v) => v.desk === "verdict_aggregator");

  return (
    <li
      onClick={onSelect}
      className={`cursor-pointer rounded-lg border px-3 py-2.5 transition-colors ${
        ok ? "border-stone-800 bg-stone-900/40" : "border-red-900/70 bg-red-950/15"
      } ${selected ? "ring-1 ring-stone-400" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-serif text-[13px] leading-snug text-stone-200">{claim.text}</p>
        <Badge tone={ok ? "good" : "bad"}>{ok ? "clear" : "blocked"}</Badge>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        <Badge>{claim.claim_id}</Badge>
        <Badge tone="info">{claim.type}</Badge>
        <Badge tone={claim.risk_tier === "high" ? "bad" : claim.risk_tier === "medium" ? "warn" : "neutral"}>
          {claim.risk_tier} risk
        </Badge>
        {claim.source_refs.map((ref) => (
          <Badge key={ref}>cites {ref}</Badge>
        ))}
        {assessment?.conflict && <Badge tone="warn">desk conflict</Badge>}
      </div>

      {/* Routing: only these desks may see this claim, each with its own evidence. */}
      <p className="mt-1.5 font-mono text-[10px] text-stone-600">
        routed to {claim.required_desks.map(deskLabel).join(" · ")}
      </p>

      <ul className="mt-2 space-y-1.5">
        {deskVerdicts.map((verdict) => (
          <VerdictCard key={verdict.verdict_id} verdict={verdict} />
        ))}
      </ul>

      {assessment && assessment.missing_desks.length > 0 && (
        <p className="mt-1.5 rounded border border-amber-900 bg-amber-950/30 px-2 py-1 text-[11px] text-amber-300">
          awaiting {assessment.missing_desks.map(deskLabel).join(", ")} — a missing reviewer result
          is never an implicit verification
        </p>
      )}

      {aggregate && (
        <p className="mt-1.5 text-[10px] text-stone-500">
          <span className="text-stone-600">aggregator:</span> {aggregate.reason}
        </p>
      )}
    </li>
  );
}

export function ClaimMap({
  view,
  selectedClaim,
  onSelectClaim,
}: {
  view: ArticleView;
  selectedClaim: string | null;
  onSelectClaim: (claimId: string | null) => void;
}) {
  const byClaim = new Map<string, Verdict[]>();
  for (const verdict of view.verdicts) {
    byClaim.set(verdict.claim_id, [...(byClaim.get(verdict.claim_id) ?? []), verdict]);
  }
  const assessments = new Map(view.gate.assessments.map((a) => [a.claim_id, a]));

  return (
    <Panel
      title="Claim map"
      subtitle="atomic claims fanned out to independent desks"
      right={<Badge tone="info">{view.verdicts.length} verdicts</Badge>}
    >
      {view.claims.length === 0 && <Empty>No claims extracted yet.</Empty>}
      <ul className="space-y-2.5">
        {view.claims.map((claim) => (
          <ClaimCard
            key={claim.claim_id}
            claim={claim}
            verdicts={byClaim.get(claim.claim_id) ?? []}
            assessment={assessments.get(claim.claim_id)}
            selected={selectedClaim === claim.claim_id}
            onSelect={() => onSelectClaim(selectedClaim === claim.claim_id ? null : claim.claim_id)}
          />
        ))}
      </ul>
    </Panel>
  );
}
