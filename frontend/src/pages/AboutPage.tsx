import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Freshness } from "../api/types";
import KpiCard from "../components/KpiCard";
import SuiteBlock from "../components/SuiteBlock";
import { RAG_AMBER, RAG_GREEN, RAG_RED } from "../lib/rag";

interface AboutMeta {
  version: string;
  build_date: string;
  build_time: string;
}

function fmtDay(value: string | null): string {
  if (!value) return "—";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t).toLocaleDateString();
}

export default function AboutPage() {
  const [fresh, setFresh] = useState<Freshness | null>(null);
  const [meta, setMeta] = useState<AboutMeta | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setFresh(await api<Freshness>("/metrics/freshness"));
      } catch {
        /* ignore */
      }
      try {
        setMeta(await api<AboutMeta>("/metrics/about"));
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
          What this is
        </h3>
        <p>
          The M365 Copilot Prompt Analyser ingests Microsoft 365 Copilot prompts and
          uses Azure OpenAI to score how well people are prompting. Every prompt and
          conversation is rated for quality, sentiment, grounding and sensitivity so
          you can coach users and track improvement over time.
        </p>
        {meta && (
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
            Version{" "}
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {meta.version}
            </span>{" "}
            · built{" "}
            {new Date(meta.build_date).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            })}
            {meta.build_time ? ` at ${meta.build_time}` : ""}
          </p>
        )}
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

      <SuiteBlock />

      <div className="card flex items-center gap-4 p-6">
        <img
          src="/loryan-cyborg.png"
          alt="Loryan Strant"
          className="h-16 w-16 rounded-full object-cover"
        />
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Created by
          </div>
          <a
            href="https://www.loryanstrant.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-lg font-semibold text-brand-600 hover:underline dark:text-brand-500"
          >
            Loryan Strant
          </a>
          <div className="mt-1">
            <a
              href="https://github.com/loryanstrant/M365Copilot-Prompt-Analyser"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600 hover:underline dark:text-slate-400 dark:hover:text-brand-500"
            >
              <svg
                viewBox="0 0 16 16"
                aria-hidden="true"
                className="h-4 w-4 fill-current"
              >
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
              </svg>
              View on GitHub
            </a>
          </div>
        </div>
      </div>

      <div className="text-xs text-slate-400 dark:text-slate-500">
        MIT-licensed. Community project — no Microsoft support agreement or SLA.
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
