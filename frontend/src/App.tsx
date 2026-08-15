import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "./api";
import { AuditTrail } from "./components/AuditTrail";
import { ClaimMap } from "./components/ClaimMap";
import { DraftPanel } from "./components/DraftPanel";
import { EditorGate } from "./components/EditorGate";
import { Masthead } from "./components/Masthead";
import { SubmitDialog, type SubmissionDraft } from "./components/SubmitDialog";
import { TopBar } from "./components/TopBar";
import { WatcherPanel } from "./components/WatcherPanel";
import { Button } from "./components/ui";
import type {
  ArticleView,
  AuditEvent,
  Desk,
  DeskRegistration,
  Identity,
  Runtime,
} from "./types";

const REPORTER: Identity = { actor: "reporter:j.reyes", role: "reporter" };

type SideTab = "audit" | "watcher" | "masthead";

export default function App() {
  const [identity, setIdentity] = useState<Identity>(REPORTER);
  const [view, setView] = useState<ArticleView | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [desks, setDesks] = useState<DeskRegistration[]>([]);
  const [deskImpl, setDeskImpl] = useState<string | undefined>();
  const [runtime, setRuntime] = useState<Runtime | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failDesk, setFailDesk] = useState<Desk | null>(null);
  const [dataset, setDataset] = useState("v1");
  const [busy, setBusy] = useState(false);
  const [denials, setDenials] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedClaim, setSelectedClaim] = useState<string | null>(null);
  const [tab, setTab] = useState<SideTab>("audit");

  const refresh = useCallback(async (articleId: string) => {
    const [next, audit] = await Promise.all([api.getArticle(articleId), api.getAudit(articleId)]);
    setView(next);
    setEvents(audit.events.slice().reverse());
  }, []);

  /** Every mutation funnels through here so server-side denials surface as
   * denials (the product), and everything else surfaces as an error. */
  const run = useCallback(
    async (action: () => Promise<string | void>, { clearDenials = true } = {}) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      if (clearDenials) setDenials([]);
      try {
        const message = await action();
        if (typeof message === "string") setNotice(message);
      } catch (exc) {
        if (exc instanceof ApiError && exc.denials.length > 0) {
          setDenials(exc.denials);
        } else if (exc instanceof ApiError) {
          setError(`${exc.status} — ${exc.message}`);
        } else {
          setError(exc instanceof Error ? exc.message : String(exc));
        }
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  useEffect(() => {
    void (async () => {
      try {
        const [registry, list, env] = await Promise.all([
          api.masthead(),
          api.listArticles(),
          api.runtime(),
        ]);
        setDesks(registry.desks);
        setDeskImpl(registry.implementation);
        setRuntime(env);
        const latest = list.articles.at(-1);
        if (latest) await refresh(latest.article_id);
      } catch (exc) {
        setError(
          exc instanceof Error
            ? `${exc.message} — is the backend running on :8000?`
            : "backend unreachable",
        );
      }
    })();
  }, [refresh]);

  const loadGolden = () =>
    run(async () => {
      const next = await api.loadGolden();
      await refresh(next.article.article_id);
      return "Golden article submitted: screened, decomposed, and routed to the desks.";
    });

  const submitOwn = (draft: SubmissionDraft) =>
    run(async () => {
      const next = await api.submitArticle(draft);
      setSubmitting(false);
      await refresh(next.article.article_id);
      const quarantined = next.security_results.filter(
        (result) => result.disposition !== "clean",
      ).length;
      return (
        `Submitted: ${next.claims.length} claim(s) extracted, ${next.verdicts.length} verdict(s) recorded` +
        (quarantined ? `, ${quarantined} source(s) quarantined at intake.` : ".")
      );
    });

  const changeFailDesk = (desk: Desk | null) =>
    run(async () => {
      await api.setFailDesk(desk);
      setFailDesk(desk);
      return desk
        ? `${desk.replace(/_/g, " ")} will now crash on every attempt — reload the golden article to see the fleet degrade gracefully.`
        : "Desk failure cleared.";
    });

  const advanceData = () =>
    run(async () => {
      const { authoritative_dataset } = await api.advanceData();
      setDataset(authoritative_dataset);
      return `Authoritative dataset is now ${authoritative_dataset}. Run the watcher on a published article.`;
    });

  const recordDecision = (payload: {
    rationale: string;
    revised_text: string | null;
    resolved_verdict_ids: string[];
  }) =>
    run(async () => {
      if (!view) return;
      await api.recordDecision(view.article.article_id, identity, {
        disposition: "approve",
        ...payload,
      });
      await refresh(view.article.article_id);
      return "Editorial decision recorded.";
    });

  const publish = () =>
    run(async () => {
      if (!view) return;
      const decisionId = view.decisions.at(-1)?.decision_id ?? null;
      await api.publish(view.article.article_id, identity, decisionId);
      await refresh(view.article.article_id);
      return "Published. The safe version is now immutable and snapshotted for the watcher.";
    });

  const reReview = () =>
    run(async () => {
      if (!view) return;
      await api.reReview(view.article.article_id, identity);
      await refresh(view.article.article_id);
      return "Failed desks retried.";
    });

  const recheck = () =>
    run(async () => {
      if (!view) return;
      const { candidates } = await api.recheck(view.article.article_id, {
        actor: "service:scheduler",
        role: "service",
      });
      await refresh(view.article.article_id);
      setTab("watcher");
      return candidates.length
        ? `Watcher drafted ${candidates.length} correction candidate(s) for editor review.`
        : "Watcher found no material change; the published version stands.";
    });

  const dispose = (watcherId: string, accept: boolean, correctedText: string | null) =>
    run(async () => {
      if (!view) return;
      // A correction appends to the published version; it never replaces the story.
      const corrected =
        accept && correctedText
          ? `${view.published_text ?? view.article.body}\n\n${correctedText}`
          : null;
      await api.disposeCorrection(view.article.article_id, watcherId, identity, {
        accept,
        rationale: accept ? "correction accepted by editor" : "sent back for reporting",
        corrected_text: corrected,
      });
      await refresh(view.article.article_id);
      return accept ? "Correction published." : "Candidate sent back.";
    });

  return (
    <div className="flex h-full flex-col">
      <TopBar
        identity={identity}
        onIdentityChange={setIdentity}
        state={view?.state ?? null}
        articleTitle={view?.article.title ?? null}
        failDesk={failDesk}
        dataset={dataset}
        runtime={runtime}
        busy={busy}
        onLoadGolden={loadGolden}
        onSubmitOwn={() => setSubmitting(true)}
        onSetFailDesk={changeFailDesk}
        onAdvanceData={advanceData}
        onRefresh={() => view && run(() => refresh(view.article.article_id))}
      />

      {(error || notice) && (
        <div
          className={`shrink-0 border-b px-4 py-1.5 text-xs ${
            error
              ? "border-red-900 bg-red-950/40 text-red-300"
              : "border-stone-800 bg-stone-900/60 text-stone-400"
          }`}
        >
          {error ?? notice}
        </div>
      )}

      {submitting && (
        <SubmitDialog busy={busy} onSubmit={submitOwn} onClose={() => setSubmitting(false)} />
      )}

      {!view ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
          <p className="max-w-md text-sm text-stone-500">
            No article in the newsroom yet. Load the golden article to run the full fleet — intake
            screening, claim extraction, independent desks, and the editor gate — or submit a draft
            of your own through the same pipeline.
          </p>
          <div className="flex gap-2">
            <Button variant="primary" onClick={loadGolden} disabled={busy}>
              Load golden article
            </Button>
            <Button onClick={() => setSubmitting(true)} disabled={busy}>
              Submit a draft
            </Button>
          </div>
        </div>
      ) : (
        <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1fr)]">
          <DraftPanel
            view={view}
            selectedClaim={selectedClaim}
            onSelectClaim={setSelectedClaim}
          />
          <ClaimMap view={view} selectedClaim={selectedClaim} onSelectClaim={setSelectedClaim} />

          <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_minmax(0,1fr)] gap-3">
            <EditorGate
              view={view}
              identity={identity}
              busy={busy}
              denials={denials}
              onRecordDecision={recordDecision}
              onPublish={publish}
              onReReview={reReview}
              onRecheck={recheck}
            />

            <div className="flex min-h-0 flex-col gap-1.5">
              <div className="flex shrink-0 gap-1">
                {(["audit", "watcher", "masthead"] as SideTab[]).map((name) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setTab(name)}
                    className={`rounded px-2 py-0.5 text-[11px] font-medium capitalize transition-colors ${
                      tab === name
                        ? "bg-stone-200 text-stone-900"
                        : "text-stone-500 hover:text-stone-300"
                    }`}
                  >
                    {name}
                  </button>
                ))}
              </div>
              {tab === "audit" && <AuditTrail events={events} />}
              {tab === "watcher" && (
                <WatcherPanel view={view} identity={identity} busy={busy} onDispose={dispose} />
              )}
              {tab === "masthead" && <Masthead desks={desks} implementation={deskImpl} />}
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
