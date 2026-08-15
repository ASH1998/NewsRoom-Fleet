import type { AuditEvent } from "../types";
import { Badge, Empty, Panel } from "./ui";

const TONE: Record<string, "good" | "warn" | "bad" | "info" | "neutral"> = {
  source_quarantined: "bad",
  body_rejected: "bad",
  publish_denied: "bad",
  decision_denied: "bad",
  desk_failed: "bad",
  verdict_recorded: "info",
  editor_gate_evaluated: "info",
  state_transition: "neutral",
  publish_approved: "good",
  editor_decision_recorded: "good",
  watcher_candidate_created: "warn",
  correction_disposed: "good",
};

export function AuditTrail({ events }: { events: AuditEvent[] }) {
  return (
    <Panel
      title="Article audit trail"
      subtitle="append-only; telemetry can alert but never approve"
      right={<Badge>{events.length} events</Badge>}
    >
      {events.length === 0 && <Empty>No events recorded yet.</Empty>}
      <ol className="space-y-1">
        {events.map((event) => (
          <li
            key={event.event_id}
            className="flex items-start gap-2 rounded border border-stone-800/70 bg-stone-950/40 px-2 py-1.5"
          >
            <span className="mt-0.5 shrink-0 font-mono text-[9px] text-stone-600">
              {new Date(event.ts).toLocaleTimeString()}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1">
                <Badge tone={TONE[event.event_type] ?? "neutral"}>{event.event_type}</Badge>
                <span className="font-mono text-[10px] text-stone-500">{event.actor}</span>
                {event.claim_id && (
                  <span className="font-mono text-[10px] text-stone-600">{event.claim_id}</span>
                )}
                {event.latency_ms !== null && (
                  <span className="font-mono text-[10px] text-stone-600">
                    {event.latency_ms.toFixed(0)}ms
                  </span>
                )}
              </div>
              {Object.keys(event.payload).length > 0 && (
                <p className="mt-0.5 truncate font-mono text-[10px] text-stone-600">
                  {JSON.stringify(event.payload)}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
