import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Freshness } from "../api/types";
import KpiCard from "../components/KpiCard";
import { RAG_AMBER, RAG_GREEN, RAG_RED } from "../lib/rag";

function fmtDay(value: string | null): string {
  if (!value) return "—";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t).toLocaleDateString();
}

export default function AboutPage() {
  const [fresh, setFresh] = useState<Freshness | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setFresh(await api<Freshness>("/metrics/freshness"));
      } catch {
        /* ignore */
      }
    })();
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">About</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          What this tool does, how fresh the data is, and how scores are calculated.
        </p>
      </div>

      <div className="card p-6 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          What is the Prompt Analyser?
        </h3>
        <p>
          The M365 Copilot Prompt Analyser ingests Microsoft 365 Copilot prompts and
          uses Azure OpenAI to score how well people are prompting. Every prompt and
          conversation is rated for quality, sentiment, grounding and sensitivity so
          you can coach users and track improvement over time.
        </p>
      </div>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Total prompts" value={fresh?.total_prompts ?? "—"} />
        <KpiCard label="Analysed prompts" value={fresh?.analysed_prompts ?? "—"} />
        <KpiCard label="Conversations" value={fresh?.conversations ?? "—"} />
        <KpiCard
          label="Coverage"
          value={
            fresh && fresh.total_prompts > 0
              ? `${Math.round((fresh.analysed_prompts / fresh.total_prompts) * 100)}%`
              : "—"
          }
          hint="Prompts scored by the analysis engine"
        />
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Data freshness
        </h3>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <Row label="Earliest prompt" value={fmtDay(fresh?.earliest ?? null)} />
          <Row label="Most recent prompt" value={fmtDay(fresh?.latest ?? null)} />
        </dl>
      </div>

      <div className="card p-6 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Methodology
        </h3>
        <ul className="list-inside list-disc space-y-2">
          <li>
            <span className="font-medium">Quality</span> is scored 1–10 per prompt and
            per conversation by Azure OpenAI.
          </li>
          <li>
            <span className="font-medium">GCSE</span> breaks each prompt into four
            levers — <span className="font-medium">Goal</span>,{" "}
            <span className="font-medium">Context</span>,{" "}
            <span className="font-medium">Source</span> and{" "}
            <span className="font-medium">Expectation</span> — each rated 1–10.
          </li>
          <li>
            <span className="font-medium">Sentiment</span> and{" "}
            <span className="font-medium">grounding</span> are classified per prompt;
            governance signals score name &amp; sensitive-info confidence 1–10.
          </li>
        </ul>

        <div className="mt-5">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            RAG thresholds
          </div>
          <div className="flex flex-wrap gap-3">
            <Band color={RAG_GREEN} label="Green · 7–10 (strong)" />
            <Band color={RAG_AMBER} label="Amber · 4–6 (developing)" />
            <Band color={RAG_RED} label="Red · 1–3 (needs work)" />
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 pb-2 dark:border-slate-700">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  );
}

function Band({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-900 dark:text-slate-300">
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
