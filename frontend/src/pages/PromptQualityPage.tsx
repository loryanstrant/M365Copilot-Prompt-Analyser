import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { MetricsSummary, PromptRow, ScoreBucket } from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import DataTable, { type Column } from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import FilterBar from "../components/FilterBar";
import KpiCard from "../components/KpiCard";
import ScoreBadge from "../components/ScoreBadge";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";
import { gcseToArray } from "../lib/format";
import { pctSmart, score10, titleCase } from "../lib/format";
import { ragColor } from "../lib/rag";

const PROMPT_LIMIT = 200;

const columns: Column<PromptRow>[] = [
  {
    key: "prompt",
    header: "Prompt",
    accessor: (r) => r.prompt_text,
    render: (r) => (
      <span
        title={r.prompt_text}
        className="block max-w-[22rem] truncate text-slate-700 dark:text-slate-200"
      >
        {r.prompt_text || "—"}
      </span>
    ),
  },
  { key: "category", header: "Category", accessor: (r) => r.category, render: (r) => titleCase(r.category) },
  { key: "app", header: "App", accessor: (r) => r.app },
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
  { key: "source", header: "S", type: "number", align: "center", accessor: (r) => r.gcse_source, render: (r) => <ScoreBadge score={r.gcse_source} /> },
  { key: "expectation", header: "E", type: "number", align: "center", accessor: (r) => r.gcse_expectation, render: (r) => <ScoreBadge score={r.gcse_expectation} /> },
  {
    key: "rationale",
    header: "Rationale",
    accessor: (r) => r.quality_rationale,
    render: (r) => (
      <span
        title={r.quality_rationale ?? undefined}
        className="block max-w-[18rem] truncate text-slate-500 dark:text-slate-400"
      >
        {r.quality_rationale || "—"}
      </span>
    ),
  },
];

export default function PromptQualityPage() {
  const filters = useFilters();
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [dist, setDist] = useState<ScoreBucket[]>([]);
  const [prompts, setPrompts] = useState<PromptRow[]>([]);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [loaded, setLoaded] = useState(false);

  const depsKey = filterDeps(filters);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        const [s, d] = await Promise.all([
          api<MetricsSummary>(`/metrics/summary${q}`),
          api<ScoreBucket[]>(`/metrics/quality-distribution${q}`),
        ]);
        setSummary(s);
        setDist(d);
      } catch {
        /* ignore */
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depsKey]);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams(metricsQuery(filters).replace(/^\?/, ""));
        params.set("limit", String(PROMPT_LIMIT));
        params.set("offset", "0");
        if (debounced) params.set("search", debounced);
        setPrompts(await api<PromptRow[]>(`/metrics/prompts?${params.toString()}`));
      } catch {
        /* ignore */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depsKey, debounced]);

  const gcseData = gcseToArray(summary?.gcse).map((g) => ({
    lever: g.lever,
    value: g.value ?? 0,
  }));
  const hasData = (summary?.prompts ?? 0) > 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Prompt quality</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          How well-crafted individual prompts are, scored 1–10 across GCSE levers.
        </p>
      </div>

      <FilterBar />

      <EmptyState show={loaded && !hasData} />

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Avg prompt quality" value={score10(summary?.avg_prompt_quality)} />
        <KpiCard label="% High quality (7–10)" value={pctSmart(summary?.pct_high_quality)} />
        <KpiCard label="% Well grounded" value={pctSmart(summary?.pct_well_grounded)} />
        <KpiCard label="Weakest GCSE lever" value={titleCase(summary?.weakest_gcse_lever)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Quality score distribution" subtitle="Prompts by score (1–10)">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={dist} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="score" tick={{ fontSize: 11 }} stroke="#94a3b8" tickMargin={6} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="count" name="Prompts" radius={[6, 6, 0, 0]}>
                {dist.map((b, i) => (
                  <Cell key={i} fill={ragColor(b.score)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="GCSE components" subtitle="Average across Goal · Context · Source · Expectation">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={gcseData} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="lever" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="value" name="Avg score" radius={[6, 6, 0, 0]}>
                {gcseData.map((g, i) => (
                  <Cell key={i} fill={ragColor(g.value)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Prompts</h3>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search prompt text…"
            className="input h-[38px] w-64"
          />
        </div>
        <DataTable
          rows={prompts}
          getRowKey={(r) => r.prompt_id}
          initialSort={{ key: "quality", dir: "desc" }}
          emptyMessage="No prompts match this selection."
          columns={columns}
        />
      </div>
    </div>
  );
}
