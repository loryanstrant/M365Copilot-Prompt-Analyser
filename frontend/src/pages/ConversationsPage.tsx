import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConversationRow } from "../api/types";
import ConversationDrawer from "../components/ConversationDrawer";
import DataTable, { type Column } from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import FilterBar from "../components/FilterBar";
import GovBadge from "../components/GovBadge";
import ScoreBadge from "../components/ScoreBadge";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";
import { pctSmart, titleCase } from "../lib/format";

const CONV_LIMIT = 1000;

const columns: Column<ConversationRow>[] = [
  {
    key: "user",
    header: "User",
    accessor: (r) => r.user_name,
    render: (r) => (
      <span className="font-medium text-slate-800 dark:text-slate-100" title={r.department ?? undefined}>
        {r.user_name || "—"}
      </span>
    ),
  },
  {
    key: "theme",
    header: "Theme",
    accessor: (r) => r.theme,
    render: (r) => (
      <span
        className="block max-w-[24rem] truncate font-medium text-slate-800 dark:text-slate-100"
        title={r.theme ?? undefined}
      >
        {r.theme || "Untitled conversation"}
      </span>
    ),
  },
  { key: "category", header: "Category", accessor: (r) => r.category, render: (r) => titleCase(r.category) },
  { key: "sentiment", header: "Sentiment", accessor: (r) => r.sentiment, render: (r) => titleCase(r.sentiment) },
  {
    key: "avg_prompt",
    header: "Avg prompt",
    type: "number",
    align: "center",
    accessor: (r) => r.avg_prompt_quality,
    render: (r) => <ScoreBadge score={r.avg_prompt_quality} />,
  },
  {
    key: "conversation",
    header: "Conversation",
    type: "number",
    align: "center",
    accessor: (r) => r.conversation_quality_score,
    render: (r) => <ScoreBadge score={r.conversation_quality_score} />,
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
  {
    key: "sensitive",
    header: "Sensitive",
    type: "number",
    align: "center",
    accessor: (r) => r.avg_sensitive_confidence,
    render: (r) => <GovBadge score={r.avg_sensitive_confidence} label="Sensitive info" />,
  },
];

export default function ConversationsPage() {
  const filters = useFilters();
  const [rows, setRows] = useState<ConversationRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

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
          initialSort={{ key: "conversation", dir: "desc" }}
          emptyMessage="No conversations for this selection."
          columns={columns}
          maxBodyHeight={520}
          rowClassName={(r) =>
            `cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/40 ${
              r.conversation_id === selected ? "bg-brand-50 dark:bg-brand-900/20" : ""
            }`
          }
          onRowClick={(r) => setSelected(r.conversation_id)}
        />
      </div>

      {selected && (
        <ConversationDrawer conversationId={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
