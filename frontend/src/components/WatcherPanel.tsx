import type { ArticleView, Identity } from "../types";
import { Badge, Button, Empty, Panel } from "./ui";

export function WatcherPanel({
  view,
  identity,
  busy,
  onDispose,
}: {
  view: ArticleView;
  identity: Identity;
  busy: boolean;
  onDispose: (watcherId: string, accept: boolean, correctedText: string | null) => void;
}) {
  const isEditor = identity.role === "editor";
  const pending = view.watcher_results.filter((w) => w.status === "pending_editor_review");

  return (
    <Panel
      title="Corrections watcher"
      subtitle="published claims resumed from persisted snapshots"
      right={<Badge tone={pending.length ? "warn" : "neutral"}>{pending.length} candidate(s)</Badge>}
    >
      {view.snapshots.length === 0 && view.watcher_results.length === 0 && (
        <Empty>No published snapshots yet. Publish first, then run the watcher.</Empty>
      )}

      {view.snapshots.length > 0 && (
        <>
          <h4 className="mb-1.5 text-[10px] font-semibold tracking-[0.14em] text-stone-500 uppercase">
            Published snapshots
          </h4>
          <ul className="mb-4 space-y-1">
            {view.snapshots.map((snapshot) => (
              <li
                key={`${snapshot.claim_id}-${snapshot.recorded_at}`}
                className="rounded border border-stone-800 bg-stone-950/50 px-2.5 py-1.5"
              >
                <p className="text-[11px] text-stone-300">
                  {snapshot.claim_id} · <span className="font-mono">{snapshot.published_value}</span>
                </p>
                <p className="font-mono text-[10px] text-stone-600">{snapshot.locator}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      {view.watcher_results.map((candidate) => {
        const disposed = candidate.status === "disposed";
        return (
          <div
            key={candidate.watcher_id}
            className={`mb-2 rounded border px-3 py-2 ${
              disposed ? "border-stone-800 bg-stone-950/40" : "border-amber-900 bg-amber-950/20"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-stone-300">{candidate.claim_id}</span>
              <div className="flex gap-1">
                <Badge tone={candidate.materiality === "material" ? "warn" : "neutral"}>
                  {candidate.materiality}
                </Badge>
                <Badge tone={disposed ? "good" : "warn"}>{candidate.status.replace(/_/g, " ")}</Badge>
              </div>
            </div>

            <p className="mt-1 text-[11px] text-stone-400">
              <span className="font-mono text-stone-500">{candidate.prior_value}</span> →{" "}
              <span className="font-mono text-amber-300">{candidate.current_value}</span>
            </p>
            <p className="font-mono text-[10px] text-stone-600">{candidate.current_locator}</p>

            <p className="mt-1.5 rounded border border-stone-800 bg-stone-950/60 px-2 py-1.5 font-serif text-[12px] leading-relaxed text-stone-300">
              {candidate.candidate_language}
            </p>

            {!disposed && (
              <div className="mt-2 flex gap-1.5">
                <Button
                  variant="primary"
                  disabled={busy || !isEditor}
                  onClick={() => onDispose(candidate.watcher_id, true, candidate.candidate_language)}
                  title={isEditor ? undefined : "only an editor disposes a correction candidate"}
                >
                  Accept correction
                </Button>
                <Button
                  disabled={busy || !isEditor}
                  onClick={() => onDispose(candidate.watcher_id, false, null)}
                >
                  Send back
                </Button>
              </div>
            )}
          </div>
        );
      })}
    </Panel>
  );
}
