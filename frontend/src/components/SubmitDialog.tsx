import { useState } from "react";

import { Badge, Button } from "./ui";

export interface SubmissionDraft {
  title: string;
  body: string;
  author: string;
  sources: { source_id: string; kind: string; name: string; content: string }[];
}

interface SourceRow {
  source_id: string;
  kind: string;
  name: string;
  content: string;
}

const SOURCE_KINDS = ["interview", "document", "memo", "dataset", "statement"];

const BLANK_SOURCE = (index: number): SourceRow => ({
  source_id: `src_${index}`,
  kind: "document",
  name: "",
  content: "",
});

const field =
  "w-full rounded border border-stone-700 bg-stone-950 px-2 py-1.5 text-xs text-stone-200 " +
  "placeholder:text-stone-600 focus:border-stone-500 focus:outline-none";

const label = "mb-1 block text-[10px] font-medium tracking-[0.12em] text-stone-500 uppercase";

/**
 * Submit a fresh article. The deployed product is not a fixture player: any
 * draft submitted here runs the same intake screening, extraction, routing, and
 * Editor Gate as the golden article — the fixture is one input, not the path.
 */
export function SubmitDialog({
  busy,
  onSubmit,
  onClose,
}: {
  busy: boolean;
  onSubmit: (draft: SubmissionDraft) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("reporter:j.reyes");
  const [body, setBody] = useState("");
  const [sources, setSources] = useState<SourceRow[]>([BLANK_SOURCE(1)]);

  const named = sources.filter((s) => s.name.trim() && s.content.trim());
  const canSubmit = title.trim().length > 0 && body.trim().length > 0 && !busy;

  const updateSource = (index: number, patch: Partial<SourceRow>) =>
    setSources((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const cite = (sourceId: string) => setBody((current) => `${current}[source:${sourceId}]`);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-6">
      <div className="w-full max-w-3xl rounded-lg border border-stone-700 bg-stone-900 shadow-2xl">
        <header className="flex items-baseline justify-between border-b border-stone-800 px-5 py-3">
          <div>
            <h2 className="text-xs font-semibold tracking-[0.14em] text-stone-200 uppercase">
              Submit a draft
            </h2>
            <p className="mt-0.5 text-[11px] text-stone-500">
              Screened at intake, decomposed into claims, and routed to the desks — same pipeline
              as the golden article.
            </p>
          </div>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </header>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[2fr_1fr]">
            <div>
              <label className={label} htmlFor="draft-title">
                Headline
              </label>
              <input
                id="draft-title"
                className={field}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="County board approves the riverfront plan"
              />
            </div>
            <div>
              <label className={label} htmlFor="draft-author">
                Byline
              </label>
              <input
                id="draft-author"
                className={field}
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className={label} htmlFor="draft-body">
              Draft body
            </label>
            <textarea
              id="draft-body"
              className={`${field} min-h-44 font-serif leading-relaxed`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={
                "One sentence per claim. Add [source:src_1] after a sentence to cite a source below."
              }
            />
            <p className="mt-1 text-[11px] text-stone-600">
              Every sentence becomes a checkable claim. Figures route to the Data Checker,
              quotations to the Source Verifier, charge-and-conviction wording to Standards.
            </p>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className={`${label} mb-0`}>Attached sources</span>
              <Button
                onClick={() => setSources((rows) => [...rows, BLANK_SOURCE(rows.length + 1)])}
                disabled={busy}
              >
                Add source
              </Button>
            </div>

            <div className="space-y-3">
              {sources.map((source, index) => (
                <div
                  key={index}
                  className="rounded border border-stone-800 bg-stone-950/60 p-3"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <input
                      className={`${field} w-28 font-mono`}
                      value={source.source_id}
                      onChange={(e) => updateSource(index, { source_id: e.target.value })}
                      aria-label="Source id"
                    />
                    <select
                      className={`${field} w-32`}
                      value={source.kind}
                      onChange={(e) => updateSource(index, { kind: e.target.value })}
                      aria-label="Source kind"
                    >
                      {SOURCE_KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {kind}
                        </option>
                      ))}
                    </select>
                    <input
                      className={`${field} min-w-40 flex-1`}
                      value={source.name}
                      onChange={(e) => updateSource(index, { name: e.target.value })}
                      placeholder="Interview transcript — county clerk"
                      aria-label="Source name"
                    />
                    <Button onClick={() => cite(source.source_id)} disabled={busy}>
                      Cite
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setSources((rows) => rows.filter((_, i) => i !== index))}
                      disabled={busy || sources.length === 1}
                    >
                      Remove
                    </Button>
                  </div>
                  <textarea
                    className={`${field} min-h-20`}
                    value={source.content}
                    onChange={(e) => updateSource(index, { content: e.target.value })}
                    placeholder="Paste the source material. It is screened before any desk sees it."
                    aria-label="Source content"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-stone-800 px-5 py-3">
          <div className="flex items-center gap-2 text-[11px] text-stone-500">
            <Badge tone="info">{named.length} source(s)</Badge>
            <span>Sources are screened at intake; a hostile one is quarantined before review.</span>
          </div>
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={() =>
              onSubmit({ title: title.trim(), body, author: author.trim(), sources: named })
            }
          >
            {busy ? "Reviewing…" : "Submit to the fleet"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
