import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConversationDetail, ConversationPrompt } from "../api/types";
import DataTable, { type Column } from "../components/DataTable";
import GovBadge from "../components/GovBadge";
import ScoreBadge from "../components/ScoreBadge";
import { fmtTime, pctSmart, titleCase } from "../lib/format";
import { ragColor } from "../lib/rag";

type ThreadRow = ConversationPrompt & { _idx: number };

const threadColumns: Column<ThreadRow>[] = [
  {
    key: "idx",
    header: "#",
    type: "number",
    align: "right",
    accessor: (r) => r._idx,
    render: (r) => <span className="tabular-nums text-slate-400">{r._idx}</span>,
  },
  {
    key: "time",
    header: "Time",
    type: "date",
    accessor: (r) => r.created_at ?? r.date,
    render: (r) => <span className="whitespace-nowrap">{fmtTime(r.created_at ?? r.date)}</span>,
  },
  {
    key: "prompt",
    header: "Prompt",
    accessor: (r) => r.prompt_text,
    render: (r) => (
      <span
        title={r.prompt_text}
        className="block max-w-[26rem] truncate text-slate-700 dark:text-slate-200"
      >
        {r.prompt_text || "—"}
      </span>
    ),
  },
  { key: "source", header: "Source", accessor: (r) => r.source },
  {
    key: "category",
    header: "Category",
    accessor: (r) => r.category,
    render: (r) => titleCase(r.category),
  },
  {
    key: "sentiment",
    header: "Sentiment",
    accessor: (r) => r.sentiment,
    render: (r) => titleCase(r.sentiment),
  },
  {
    key: "quality",
    header: "Quality",
    type: "number",
    align: "center",
    accessor: (r) => r.quality_score,
    render: (r) => <ScoreBadge score={r.quality_score} />,
  },
  { key: "goal", header: "G", type: "number", align: "center", accessor: (r) => r.gcse_goal, render: (r) => <ScoreBadge score={r.gcse_goal} /> },
  { key: "context", header: "C", type: "number", align: "center", accessor: (r) => r.gcse_context, render: (r) => <ScoreBadge score={r.gcse_context} /> },
  { key: "src", header: "S", type: "number", align: "center", accessor: (r) => r.gcse_source, render: (r) => <ScoreBadge score={r.gcse_source} /> },
  { key: "expectation", header: "E", type: "number", align: "center", accessor: (r) => r.gcse_expectation, render: (r) => <ScoreBadge score={r.gcse_expectation} /> },
  {
    key: "name",
    header: "Name",
    type: "number",
    align: "center",
    accessor: (r) => r.name_confidence,
    render: (r) => <GovBadge score={r.name_confidence} label="Name" />,
  },
  {
    key: "sensitive",
    header: "Sensitive",
    type: "number",
    align: "center",
    accessor: (r) => r.sensitive_confidence,
    render: (r) => <GovBadge score={r.sensitive_confidence} label="Sensitive info" />,
  },
  {
    key: "profanity",
    header: "Profanity",
    type: "number",
    align: "center",
    accessor: (r) => r.curse_confidence,
    render: (r) => <GovBadge score={r.curse_confidence} label="Profanity" />,
  },
  {
    key: "rationale",
    header: "Rationale",
    accessor: (r) => r.quality_rationale,
    render: (r) => (
      <span
        title={r.quality_rationale ?? undefined}
        className="block max-w-[20rem] truncate text-slate-500 dark:text-slate-400"
      >
        {r.quality_rationale || "—"}
      </span>
    ),
  },
];

export default function ConversationDrawer({
  conversationId,
  onClose,
  personal = false,
}: {
  conversationId: string;
  onClose?: () => void;
  // Read through the personal endpoint, which confirms the thread belongs to
  // the signed-in person. The organisation endpoint is gated, so someone
  // without org access could not open their own conversation through it.
  personal?: boolean;
}) {
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(false);
      setDetail(null);
      try {
        const d = await api<ConversationDetail>(
          `${personal ? "/metrics/me/conversations" : "/metrics/conversations"}/${encodeURIComponent(conversationId)}`,
        );
        if (!cancelled) setDetail(d);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, personal]);

  const conv = detail?.conversation ?? null;
  const rows: ThreadRow[] = (detail?.prompts ?? []).map((p, i) => ({ ...p, _idx: i + 1 }));

  return (
    <div className="card space-y-6 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Conversation
          </div>
          <h2 className="mt-1 text-lg font-semibold text-slate-800 dark:text-slate-100">
            {conv?.theme || "Conversation detail"}
          </h2>
          {conv?.user_name && (
            <div className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
              {conv.user_name}
            </div>
          )}
        </div>
        {onClose && (
          <button onClick={onClose} className="btn-secondary h-[34px] shrink-0">
            Close
          </button>
        )}
      </div>

      {loading && <div className="muted text-sm">Loading conversation…</div>}
      {error && !loading && (
        <div className="muted text-sm">Conversation details unavailable.</div>
      )}

      {!loading && !error && conv && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <ScoreTile label="Average of prompts" score={conv.avg_of_prompts ?? null} />
            <ScoreTile
              label="Conversation score"
              score={conv.conversation_quality_score ?? null}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <StatChip label="Sentiment" value={titleCase(conv.sentiment)} />
            <StatChip label="Category" value={titleCase(conv.category)} />
            <StatChip
              label="Prompts"
              value={String(conv.prompt_count ?? rows.length)}
            />
            <StatChip label="User-generated" value={pctSmart(conv.user_generated_ratio)} />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <NarrativeCard title="Insight" body={conv.insight} />
            <NarrativeCard title="Theme" body={conv.theme} />
            <NarrativeCard title="Suggested improvement" body={conv.improvement} />
            <NarrativeCard
              title="Suggested starter prompt"
              body={conv.suggested_starter_prompt}
              mono
            />
          </div>

          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                Prompt thread
              </h3>
            </div>
            <DataTable
              rows={rows}
              getRowKey={(r) => r.prompt_id}
              initialSort={{ key: "idx", dir: "asc" }}
              emptyMessage="No prompts recorded."
              columns={threadColumns}
            />
          </div>
        </>
      )}
    </div>
  );
}

function ScoreTile({ label, score }: { label: string; score: number | null }) {
  const display =
    score === null || Number.isNaN(score)
      ? "—"
      : Number.isInteger(score)
        ? String(score)
        : score.toFixed(1);
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-800/60">
      <div className="text-sm font-medium text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-2 flex items-baseline gap-1">
        <span
          className="text-4xl font-bold tabular-nums"
          style={{ color: ragColor(score) }}
        >
          {display}
        </span>
        <span className="text-lg font-semibold text-slate-400">/10</span>
      </div>
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
      <span className="font-medium text-slate-400 dark:text-slate-500">{label}</span>
      <span className="font-semibold">{value}</span>
    </span>
  );
}

function NarrativeCard({
  title,
  body,
  mono = false,
}: {
  title: string;
  body: string | null | undefined;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </div>
      <div
        className={`text-sm leading-relaxed text-slate-700 dark:text-slate-200 ${
          mono ? "rounded-lg bg-slate-50 p-3 font-mono text-xs dark:bg-slate-900" : ""
        }`}
      >
        {body || "—"}
      </div>
    </div>
  );
}
