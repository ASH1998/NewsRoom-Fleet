import type { ReactNode } from "react";

import type { PublicationState, SecurityDisposition, VerdictResult } from "../types";

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex min-h-0 flex-col rounded-lg border border-stone-800 bg-stone-900/60 ${className}`}
    >
      <header className="flex shrink-0 items-baseline justify-between gap-3 border-b border-stone-800 px-4 py-2.5">
        <div className="min-w-0">
          <h2 className="text-xs font-semibold tracking-[0.14em] text-stone-300 uppercase">
            {title}
          </h2>
          {subtitle && <p className="mt-0.5 truncate text-[11px] text-stone-500">{subtitle}</p>}
        </div>
        {right}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
    </section>
  );
}

export function Badge({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad" | "info";
  title?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "border-stone-700 bg-stone-800/60 text-stone-300",
    good: "border-emerald-800 bg-emerald-950/60 text-emerald-300",
    warn: "border-amber-800 bg-amber-950/60 text-amber-300",
    bad: "border-red-800 bg-red-950/60 text-red-300",
    info: "border-sky-800 bg-sky-950/60 text-sky-300",
  };
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] tracking-wide whitespace-nowrap ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export const verdictTone = (result: VerdictResult) =>
  result === "verified"
    ? "good"
    : result === "contradicted" || result === "error"
      ? "bad"
      : result === "unsupported"
        ? "warn"
        : "info";

export const securityTone = (disposition: SecurityDisposition) =>
  disposition === "clean" ? "good" : disposition === "quarantined" ? "bad" : "warn";

export const stateTone = (state: PublicationState) =>
  state === "published"
    ? "good"
    : state === "editor_ready" || state === "editor_approved"
      ? "info"
      : state === "human_review" || state === "correction_candidate"
        ? "warn"
        : "neutral";

export function Button({
  children,
  onClick,
  disabled,
  variant = "default",
  title,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "default" | "primary" | "danger" | "ghost";
  title?: string;
  type?: "button" | "submit";
}) {
  const variants: Record<string, string> = {
    default: "border-stone-700 bg-stone-800 text-stone-200 hover:bg-stone-700",
    primary: "border-emerald-700 bg-emerald-800/80 text-emerald-50 hover:bg-emerald-700",
    danger: "border-red-800 bg-red-900/70 text-red-100 hover:bg-red-800",
    ghost: "border-transparent bg-transparent text-stone-400 hover:text-stone-200",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`rounded border px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]}`}
    >
      {children}
    </button>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-xs text-stone-600">{children}</p>;
}

export const deskLabel = (desk: string) =>
  desk.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
