import { useState } from "react";

import type { ArticleView, Identity, Verdict } from "../types";
import { Badge, Button, Empty, Panel, deskLabel, stateTone } from "./ui";

export function EditorGate({
  view,
  identity,
  busy,
  denials,
  onRecordDecision,
  onPublish,
  onReReview,
  onRecheck,
}: {
  view: ArticleView;
  identity: Identity;
  busy: boolean;
  denials: string[];
  onRecordDecision: (payload: {
    rationale: string;
    revised_text: string | null;
    resolved_verdict_ids: string[];
  }) => void;
  onPublish: () => void;
  onReReview: () => void;
  onRecheck: () => void;
}) {
  const [resolved, setResolved] = useState<string[]>([]);
  const [revisedText, setRevisedText] = useState("");
  const [rationale, setRationale] = useState("");

  const blockingIds = view.gate.blocking_verdict_ids;
  const blockingVerdicts = view.verdicts.filter((v) => blockingIds.includes(v.verdict_id));
  const latestDecision = view.decisions.at(-1) ?? null;
  const isEditor = identity.role === "editor";
  const published = view.state === "published" || view.state === "correction_candidate";

  const toggle = (verdictId: string) =>
    setResolved((current) =>
      current.includes(verdictId)
        ? current.filter((id) => id !== verdictId)
        : [...current, verdictId],
    );

  const missingReasons = view.gate.assessments.flatMap((a) =>
    a.missing_desks.map((desk) => `${a.claim_id}: ${deskLabel(desk)} has no verdict on record`),
  );

  return (
    <Panel
      title="Editor gate"
      subtitle="deterministic policy over persisted verdict state"
      right={
        <Badge tone={stateTone(view.gate.state)} title="gate evaluation over persisted verdicts">
          gate: {view.gate.state.replace(/_/g, " ")}
        </Badge>
      }
    >
      {/* After publication the gate report still reads HUMAN_REVIEW: the editor
          resolved the blocking verdicts, but nothing rewrote them. */}
      {published && (
        <div className="mb-3 rounded border border-emerald-900 bg-emerald-950/30 px-3 py-2 text-[11px] text-emerald-300">
          Published under editor authority. The blocking verdicts below are preserved exactly as the
          desks recorded them — an editorial decision resolves them, it never rewrites them.
        </div>
      )}

      {/* The decisive demo moment: a server-side refusal, with reasons. */}
      {denials.length > 0 && (
        <div className="mb-3 rounded border border-red-800 bg-red-950/40 px-3 py-2">
          <p className="text-xs font-semibold text-red-200">
            The editor gate refuses publication
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-red-300">
            {denials.map((denial) => (
              <li key={denial}>{denial}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mb-3 grid grid-cols-3 gap-2 text-center">
        {[
          ["claims", view.claims.length, "neutral"],
          ["blocked", view.gate.blocked_claim_ids.length, view.gate.blocked_claim_ids.length ? "bad" : "good"],
          ["decisions", view.decisions.length, "info"],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded border border-stone-800 bg-stone-950/50 py-1.5">
            <p className="font-mono text-base text-stone-200">{value as number}</p>
            <p className="text-[10px] tracking-wide text-stone-600 uppercase">{label as string}</p>
          </div>
        ))}
      </div>

      <h4 className="mb-1.5 text-[10px] font-semibold tracking-[0.14em] text-stone-500 uppercase">
        Blocking verdicts
      </h4>
      {blockingVerdicts.length === 0 && missingReasons.length === 0 && (
        <Empty>Nothing blocks publication. Every required desk returned defensible evidence.</Empty>
      )}
      <ul className="space-y-1.5">
        {blockingVerdicts.map((verdict: Verdict) => (
          <li
            key={verdict.verdict_id}
            className="rounded border border-stone-800 bg-stone-950/50 px-2.5 py-1.5"
          >
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                disabled={!isEditor || published}
                checked={resolved.includes(verdict.verdict_id)}
                onChange={() => toggle(verdict.verdict_id)}
                className="mt-0.5 accent-emerald-600"
              />
              <span className="min-w-0">
                <span className="text-[11px] text-stone-300">
                  {verdict.claim_id} · {deskLabel(verdict.desk)} —{" "}
                  <span className="text-red-300">{verdict.result}</span>
                </span>
                <span className="block text-[11px] text-stone-500">{verdict.reason}</span>
                <span className="block font-mono text-[9px] text-stone-700">
                  {verdict.verdict_id}
                </span>
              </span>
            </label>
          </li>
        ))}
        {missingReasons.map((reason) => (
          <li
            key={reason}
            className="rounded border border-amber-900 bg-amber-950/25 px-2.5 py-1.5 text-[11px] text-amber-300"
          >
            {reason}
          </li>
        ))}
      </ul>

      {/* Human authority, recorded. Identity is enforced server-side either way. */}
      <h4 className="mt-5 mb-1.5 text-[10px] font-semibold tracking-[0.14em] text-stone-500 uppercase">
        Editorial decision
      </h4>
      {!isEditor && (
        <p className="mb-2 rounded border border-stone-800 bg-stone-950/50 px-2.5 py-1.5 text-[11px] text-stone-400">
          You are acting as <span className="text-stone-200">{identity.actor}</span>. A reporter
          cannot record an editorial decision or clear the gate — try it and the server denies it.
        </p>
      )}
      <textarea
        value={revisedText}
        onChange={(e) => setRevisedText(e.target.value)}
        disabled={!isEditor || published}
        placeholder="Safe revised text (required when any claim is blocked)"
        rows={4}
        className="w-full resize-y rounded border border-stone-800 bg-stone-950/70 px-2.5 py-1.5 font-serif text-[12px] text-stone-200 placeholder:text-stone-600 disabled:opacity-40"
      />
      <input
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
        disabled={!isEditor || published}
        placeholder="Rationale for the record"
        className="mt-1.5 w-full rounded border border-stone-800 bg-stone-950/70 px-2.5 py-1.5 text-[12px] text-stone-200 placeholder:text-stone-600 disabled:opacity-40"
      />

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Button
          variant="default"
          disabled={busy || published}
          onClick={() =>
            onRecordDecision({
              rationale: rationale || "editor review",
              revised_text: revisedText || null,
              resolved_verdict_ids: resolved,
            })
          }
        >
          Record decision
        </Button>
        <Button variant="primary" disabled={busy || published} onClick={onPublish}>
          Attempt publish
        </Button>
        <Button
          variant="ghost"
          disabled={busy || view.state !== "human_review"}
          onClick={onReReview}
          title="Retry desks that returned an ERROR verdict"
        >
          Re-review failed desks
        </Button>
        <Button
          variant="ghost"
          disabled={busy || view.state !== "published"}
          onClick={onRecheck}
          title="Run the corrections watcher against the current authoritative data"
        >
          Run watcher
        </Button>
      </div>

      {latestDecision && (
        <p className="mt-2 rounded border border-stone-800 bg-stone-950/50 px-2.5 py-1.5 text-[10px] text-stone-500">
          last decision <span className="font-mono text-stone-400">{latestDecision.decision_id}</span>{" "}
          · {latestDecision.disposition} by {latestDecision.actor} · resolved{" "}
          {latestDecision.resolved_verdict_ids.length} verdict(s) ·{" "}
          {new Date(latestDecision.created_at).toLocaleTimeString()}
        </p>
      )}
    </Panel>
  );
}
