import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type {
  ConversationRow,
  Gcse,
  PersonalCoaching,
} from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import DataTable, { type Column } from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import KpiCard from "../components/KpiCard";
import ScoreBadge from "../components/ScoreBadge";
import { CHART_COLORS } from "../components/chartTheme";
import { metricsQuery, useFilters } from "../filters/FiltersContext";
import { gcseToArray, score10 } from "../lib/format";

const CONV_LIMIT = 200;

function convScore(r: ConversationRow | null): number | null {
  if (!r) return null;
  return r.conversation_quality_score ?? r.avg_quality_score;
}

// Strongest / weakest lever names from a GCSE object (ignoring nulls).
function leverExtremes(g: Gcse | null): { strongest: string; weakest: string } {
  const arr = gcseToArray(g).filter((x) => x.value !== null) as {
    lever: string;
    value: number;
  }[];
  if (arr.length === 0) return { strongest: "—", weakest: "—" };
  const sorted = [...arr].sort((a, b) => a.value - b.value);
  return { weakest: sorted[0].lever, strongest: sorted[sorted.length - 1].lever };
}

const promptColumns: Column<PersonalCoaching["detail"]["prompts"][number]>[] = [
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

export default function PersonalPage() {
  const filters = useFilters();
  const [conversations, setConversations] = useState<ConversationRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<string>("");
  const [coaching, setCoaching] = useState<PersonalCoaching | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams(metricsQuery(filters).replace(/^\?/, ""));
        params.set("limit", String(CONV_LIMIT));
        const rows = await api<ConversationRow[]>(`/metrics/conversations?${params.toString()}`);
        setConversations(rows);
        if (rows.length && !selected) {
          setSelected(rows[0].conversation_id);
        }
      } catch {
        /* ignore */
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selected) return;
    (async () => {
      setLoading(true);
      setCoaching(null);
      try {
        setCoaching(
          await api<PersonalCoaching>(`/metrics/personal/${encodeURIComponent(selected)}`),
        );
      } catch {
        setCoaching(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [selected]);

  const extremes = leverExtremes(coaching?.gcse_mine ?? null);
  const chartData = useMemo(() => {
    const mine = gcseToArray(coaching?.gcse_mine ?? null);
    const team = gcseToArray(coaching?.gcse_team ?? null);
    return mine.map((m, i) => ({
      lever: m.lever,
      mine: m.value ?? 0,
      team: team[i]?.value ?? 0,
    }));
  }, [coaching]);

  const conv = coaching?.detail.conversation ?? null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Personal coaching</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Coaching is keyed by conversation for now — per-user identity arrives once
          individual attribution is available.
        </p>
      </div>

      <EmptyState show={loaded && conversations.length === 0} />

      <div className="card flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-[18rem] flex-1">
          <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
            Conversation
          </label>
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="input"
            disabled={conversations.length === 0}
          >
            {conversations.length === 0 && <option value="">No conversations</option>}
            {conversations.map((c) => (
              <option key={c.conversation_id} value={c.conversation_id}>
                {c.theme || `Conversation ${c.conversation_id}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="muted text-sm">Loading coaching…</div>}

      {!loading && coaching && (
        <>
          <div className="grid gap-5 sm:grid-cols-3">
            <KpiCard label="Avg quality" value={score10(convScore(conv))} />
            <KpiCard label="Strongest lever" value={extremes.strongest} />
            <KpiCard label="Weakest lever" value={extremes.weakest} />
          </div>

          <ChartCard title="GCSE vs team" subtitle="Your levers compared with the team average">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ left: -20, right: 8, top: 8 }} barGap={4}>
                <XAxis dataKey="lever" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
                <Legend />
                <Bar dataKey="mine" name="This conversation" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="team" name="Team average" fill={CHART_COLORS[2]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <div className="card">
            <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                Prompts in this conversation
              </h3>
            </div>
            <DataTable
              rows={coaching.detail.prompts}
              getRowKey={(r) => r.prompt_id}
              emptyMessage="No prompts recorded."
              columns={promptColumns}
            />
          </div>
        </>
      )}
    </div>
  );
}
