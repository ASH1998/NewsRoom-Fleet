import type { ReactNode } from "react";

import type { ArticleView, Claim } from "../types";
import { Badge, Empty, Panel, securityTone } from "./ui";

/** Renders the draft body with each extracted claim highlighted by gate status.
 * Spans are character offsets produced by the extractor, so the annotated draft
 * and the claim map always agree. */
function AnnotatedBody({
  body,
  claims,
  blocked,
  selected,
  onSelect,
}: {
  body: string;
  claims: Claim[];
  blocked: Set<string>;
  selected: string | null;
  onSelect: (claimId: string | null) => void;
}) {
  const ordered = [...claims].sort((a, b) => a.span[0] - b.span[0]);
  const parts: ReactNode[] = [];
  let cursor = 0;

  for (const claim of ordered) {
    const [start, end] = claim.span;
    if (start < cursor || start > body.length) continue; // skip overlaps defensively
    if (start > cursor) parts.push(<span key={`t${cursor}`}>{body.slice(cursor, start)}</span>);

    const isBlocked = blocked.has(claim.claim_id);
    const isSelected = selected === claim.claim_id;
    parts.push(
      <mark
        key={claim.claim_id}
        onClick={() => onSelect(isSelected ? null : claim.claim_id)}
        title={`${claim.claim_id} · ${claim.type} · ${claim.risk_tier} risk`}
        className={`cursor-pointer rounded-sm px-0.5 transition-colors ${
          isBlocked
            ? "bg-red-950/70 text-red-200 decoration-red-500 underline decoration-wavy underline-offset-4"
            : "bg-emerald-950/60 text-emerald-200"
        } ${isSelected ? "ring-1 ring-stone-300" : ""}`}
      >
        {body.slice(start, end)}
      </mark>,
    );
    cursor = end;
  }
  if (cursor < body.length) parts.push(<span key="tail">{body.slice(cursor)}</span>);

  return <p className="font-serif text-[15px] leading-7 text-stone-300">{parts}</p>;
}

export function DraftPanel({
  view,
  selectedClaim,
  onSelectClaim,
}: {
  view: ArticleView;
  selectedClaim: string | null;
  onSelectClaim: (claimId: string | null) => void;
}) {
  const blocked = new Set(view.gate.blocked_claim_ids);
  const bodyScreen = view.security_results.find((s) => s.source_id === null);
  const sourceScreens = view.security_results.filter((s) => s.source_id !== null);

  return (
    <Panel
      title={view.published_text ? "Published version" : "Draft"}
      subtitle={`${view.article.author} · ${view.claims.length} claims · ${blocked.size} blocked`}
      right={bodyScreen && <Badge tone={securityTone(bodyScreen.disposition)}>body: {bodyScreen.disposition}</Badge>}
    >
      <h3 className="mb-3 font-serif text-xl leading-snug text-stone-100">{view.article.title}</h3>

      <AnnotatedBody
        body={view.published_text ?? view.article.body}
        claims={view.published_text ? [] : view.claims}
        blocked={blocked}
        selected={selectedClaim}
        onSelect={onSelectClaim}
      />

      {view.published_text && view.published_text !== view.article.body && (
        <p className="mt-3 rounded border border-emerald-900 bg-emerald-950/30 px-3 py-2 text-[11px] text-emerald-300">
          Showing the published safe version recorded by the editor. The submitted draft is
          preserved unchanged in the audit record.
        </p>
      )}

      <h4 className="mt-6 mb-2 text-[10px] font-semibold tracking-[0.14em] text-stone-500 uppercase">
        Sources — screened at intake
      </h4>
      {sourceScreens.length === 0 && <Empty>No attached sources.</Empty>}
      <ul className="space-y-2">
        {view.article.sources.map((source) => {
          const screen = sourceScreens.find((s) => s.source_id === source.source_id);
          const quarantined = screen && screen.disposition !== "clean";
          return (
            <li
              key={source.source_id}
              className={`rounded border px-3 py-2 ${
                quarantined ? "border-red-900 bg-red-950/25" : "border-stone-800 bg-stone-900/40"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs text-stone-300">{source.name}</span>
                {screen && (
                  <Badge tone={securityTone(screen.disposition)} title={screen.detector_detail}>
                    {screen.disposition}
                  </Badge>
                )}
              </div>
              <p className="mt-1 font-mono text-[10px] text-stone-600">
                {source.source_id} · {source.kind}
                {screen && ` · ${screen.detector} · policy ${screen.policy_version}`}
              </p>
              {quarantined && screen && (
                <p className="mt-1.5 text-[11px] leading-relaxed text-red-300">
                  {screen.detector_detail} — quarantined before any desk received it; no instruction
                  from this document ever entered reviewer context.
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
