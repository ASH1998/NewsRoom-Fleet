import type { Desk, Identity, PublicationState, Role, Runtime } from "../types";
import { Badge, Button, stateTone } from "./ui";

const FAILABLE_DESKS: Desk[] = ["source_verifier", "data_checker", "standards_reviewer"];

/** Components whose local implementation is the default; anything else is cloud. */
const LOCAL_IMPLEMENTATIONS = new Set(["fixture", "sqlite", "heuristic", "inprocess", "file", "off"]);

export function TopBar({
  identity,
  onIdentityChange,
  state,
  articleTitle,
  failDesk,
  dataset,
  runtime,
  busy,
  onLoadGolden,
  onSubmitOwn,
  onSetFailDesk,
  onAdvanceData,
  onRefresh,
}: {
  identity: Identity;
  onIdentityChange: (identity: Identity) => void;
  state: PublicationState | null;
  articleTitle: string | null;
  failDesk: Desk | null;
  dataset: string;
  runtime: Runtime | null;
  busy: boolean;
  onLoadGolden: () => void;
  onSubmitOwn: () => void;
  onSetFailDesk: (desk: Desk | null) => void;
  onAdvanceData: () => void;
  onRefresh: () => void;
}) {
  const setRole = (role: Role) =>
    onIdentityChange({ role, actor: role === "editor" ? "editor:t.okafor" : "reporter:j.reyes" });

  // Resolved, not requested: a component that fell back to its local
  // implementation must not be advertised as running on Google Cloud.
  const cloudComponents = Object.entries(runtime?.resolved ?? {}).filter(
    ([, value]) => !LOCAL_IMPLEMENTATIONS.has(value),
  );

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b border-stone-800 bg-stone-900 px-4 py-2.5">
      <div className="flex items-baseline gap-3">
        <h1 className="font-serif text-lg leading-none font-semibold text-stone-100">
          Newsroom Fleet
        </h1>
        <span className="text-[11px] tracking-wide text-stone-500">Editor Desk</span>
      </div>

      {articleTitle && (
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-xs text-stone-400">{articleTitle}</span>
          {state && <Badge tone={stateTone(state)}>{state.replace(/_/g, " ")}</Badge>}
        </div>
      )}

      {runtime && (
        <div
          className="flex flex-wrap items-center gap-1"
          title={
            cloudComponents.length
              ? `Running on Google Cloud: ${cloudComponents
                  .map(([k, v]) => `${k}=${v}`)
                  .join(", ")}`
              : "Fixture mode: zero API keys, zero network, zero cloud"
          }
        >
          {cloudComponents.length === 0 ? (
            <Badge tone="neutral">local · no cloud</Badge>
          ) : (
            cloudComponents.map(([key, value]) => (
              <Badge key={key} tone="info">
                {key === "mode" ? value : `${key}:${value}`}
              </Badge>
            ))
          )}
        </div>
      )}

      <div className="ml-auto flex flex-wrap items-center gap-3">
        {/* Identity: the same UI under two identities — only one can clear the gate. */}
        <div className="flex items-center gap-1 rounded border border-stone-700 p-0.5">
          {(["reporter", "editor"] as Role[]).map((role) => (
            <button
              key={role}
              type="button"
              onClick={() => setRole(role)}
              className={`rounded px-2 py-0.5 text-[11px] font-medium capitalize transition-colors ${
                identity.role === role
                  ? "bg-stone-200 text-stone-900"
                  : "text-stone-400 hover:text-stone-200"
              }`}
            >
              {role}
            </button>
          ))}
        </div>

        <Button
          variant="primary"
          onClick={onSubmitOwn}
          disabled={busy}
          title="Submit a fresh article through the same pipeline"
        >
          Submit a draft
        </Button>

        <div className="flex items-center gap-1.5">
          <span className="text-[10px] tracking-[0.12em] text-stone-600 uppercase">Demo</span>
          <Button onClick={onLoadGolden} disabled={busy} title="Reset and submit the golden article">
            Load golden article
          </Button>

          <select
            value={failDesk ?? ""}
            disabled={busy}
            onChange={(e) => onSetFailDesk((e.target.value || null) as Desk | null)}
            title="Crash one desk's worker on every attempt"
            className="rounded border border-stone-700 bg-stone-800 px-2 py-1 text-xs text-stone-200 disabled:opacity-40"
          >
            <option value="">no desk failure</option>
            {FAILABLE_DESKS.map((desk) => (
              <option key={desk} value={desk}>
                crash {desk.replace(/_/g, " ")}
              </option>
            ))}
          </select>

          <Button
            onClick={onAdvanceData}
            disabled={busy}
            title="Swap the authoritative adapter dataset (upstream value changes)"
          >
            Advance data ({dataset})
          </Button>
          <Button variant="ghost" onClick={onRefresh} disabled={busy}>
            Refresh
          </Button>
        </div>
      </div>
    </header>
  );
}
