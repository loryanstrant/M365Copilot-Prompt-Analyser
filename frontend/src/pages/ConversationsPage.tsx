import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  ConversationDetail,
  ConversationRow,
} from "../api/types";
import DataTable, { type Column } from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import FilterBar from "../components/FilterBar";
import ScoreBadge from "../components/ScoreBadge";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";
import { pctSmart, titleCase } from "../lib/format";

const CONV_LIMIT = 200;

function convScore(r: ConversationRow): number | null {
  return r.conversation_quality_score ?? r.avg_quality_score;
}

const columns: Column<ConversationRow>[] = [
  {
    key: "theme",
    header: "Theme",
    accessor: (r) => r.theme,
    render: (r) => (
      <span className="block max-w-[24rem] truncate font-medium text-slate-800 dark:text-slate-100" title={r.theme ?? undefined}>
        {r.theme || "Untitled conversation"}
      </span>
    ),
  },
  { key: "category", header: "Category", accessor: (r) => r.category, render: (r) => titleCase(r.category) },
  { key: "sentiment", header: "Sentiment", accessor: (r) => r.sentiment, render: (r) => titleCase(r.sentiment) },
  {
    key: "quality",
    header: "Quality",
    type: "number",
    align: "center",
    accessor: (r) => convScore(r),
    render: (r) => <ScoreBadge score={convScore(r)} />,
  },
  { key: "prompts", header: "Prompts", type: "number", align: "right", accessor: (r) => r.prompt_count },
  {
    key: "usergen",
    header: "User-gen %",
    type: "number",
    align: "right",
    accessor: (r) => r.user_generated_ratio,
    render: (r) => pctSmart(r.user_generated_ratio),
  },
];

const promptColumns: Column<ConversationDetail["prompts"][number]>[] = [
  {
    key: "text",
    header: "Prompt",
    accessor: (r) => r.prompt_text,
    render: (r) => (
      <span className="block max-w-[30rem] truncate" title={r.prompt_text}>
        {r.prompt_text || "—"}
      </span>
    ),
  },
  {
    key: "quality",
    header: "Quality",
    type: "number",
    align: "center",
    accessor: (r) => r.quality_score,
    render: (r) => <ScoreBadge score={r.quality_score} />,
  },
  {
    key: "rationale",
    header: "Rationale",
    accessor: (r) => r.quality_rationale,
    render: (r) => (
      <span className="block max-w-[24rem] truncate text-slate-500 dark:text-slate-400" title={r.quality_rationale ?? undefined}>
        {r.quality_rationale || "—"}
      </span>
    ),
  },
];

export default function ConversationsPage() {
  const filters = useFilters();
  const [rows, setRows] = useState<ConversationRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams(metricsQuery(filters).replace(/^\?/, ""));
        params.set("limit", String(CONV_LIMIT));
        setRows(await api<ConversationRow[]>(`/metrics/conversations?${params.toString()}`));
      } catch {
        /* ignore */
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterDeps(filters)]);

  async function openConversation(id: string) {
    setSelected(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await api<ConversationDetail>(`/metrics/conversations/${encodeURIComponent(id)}`));
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  const conv = detail?.conversation;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Conversations</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Session-level themes, sentiment and quality. Select a row for the full narrative.
        </p>
      </div>

      <FilterBar />

      <EmptyState show={loaded && rows.length === 0} />

      <div className="card overflow-hidden">
        <DataTable
          rows={rows}
          getRowKey={(r) => r.conversation_id}
          initialSort={{ key: "quality", dir: "desc" }}
          emptyMessage="No conversations for this selection."
          columns={columns}
          rowClassName={(r) =>
            `cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/40 ${
              r.conversation_id === selected ? "bg-brand-50 dark:bg-brand-900/20" : ""
            }`
          }
          onRowClick={(r) => openConversation(r.conversation_id)}
        />
      </div>

      {selected && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Conversation detail</h2>
            <button
              onClick={() => {
                setSelected(null);
                setDetail(null);
              }}
              className="btn-secondary h-[34px]"
            >
              Close
            </button>
          </div>

          {detailLoading && <div className="muted text-sm">Loading conversation…</div>}

          {!detailLoading && conv && (
            <>
              <div className="grid gap-5 md:grid-cols-2">
                <NarrativeCard title="Theme" body={conv.theme} />
                <NarrativeCard title="Insight" body={conv.insight} />
                <NarrativeCard title="Improvement" body={conv.improvement} />
                <NarrativeCard title="Suggested starter prompt" body={conv.suggested_starter_prompt} mono />
              </div>

              <div className="card">
                <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-700">
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                    Prompts in this conversation
                  </h3>
                </div>
                <DataTable
                  rows={detail?.prompts ?? []}
                  getRowKey={(r) => r.prompt_id}
                  emptyMessage="No prompts recorded."
                  columns={promptColumns}
                />
              </div>
            </>
          )}

          {!detailLoading && !conv && (
            <div className="muted text-sm">Conversation details unavailable.</div>
          )}
        </div>
      )}
    </div>
  );
}

function NarrativeCard({
  title,
  body,
  mono = false,
}: {
  title: string;
  body: string | null;
  mono?: boolean;
}) {
  return (
    <div className="card p-5">
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
