import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type {
  AppQualityRow,
  GcseByIntentRow,
  IntentQualityRow,
  NamedCount,
} from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import EmptyState from "../components/EmptyState";
import FilterBar from "../components/FilterBar";
import { CHART_COLORS } from "../components/chartTheme";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";
import { ragColor } from "../lib/rag";

const BAR_COLOR = "#3b6ef5";
const GCSE_KEYS = [
  { key: "goal", label: "Goal", color: CHART_COLORS[0] },
  { key: "context", label: "Context", color: CHART_COLORS[1] },
  { key: "source", label: "Source", color: CHART_COLORS[3] },
  { key: "expectation", label: "Expectation", color: CHART_COLORS[5] },
] as const;

export default function UsageBreakdownPage() {
  const filters = useFilters();
  const [byApp, setByApp] = useState<AppQualityRow[]>([]);
  const [categories, setCategories] = useState<NamedCount[]>([]);
  const [byIntent, setByIntent] = useState<IntentQualityRow[]>([]);
  const [gcseByIntent, setGcseByIntent] = useState<GcseByIntentRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        const [ba, cm, bi, gi] = await Promise.all([
          api<AppQualityRow[]>(`/metrics/by-app${q}`),
          api<NamedCount[]>(`/metrics/category-mix${q}`),
          api<IntentQualityRow[]>(`/metrics/by-intent${q}`),
          api<GcseByIntentRow[]>(`/metrics/gcse-by-intent${q}`),
        ]);
        setByApp(ba);
        setCategories(cm);
        setByIntent(bi);
        setGcseByIntent(gi);
      } catch {
        /* ignore */
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterDeps(filters)]);

  const hasData =
    byApp.length > 0 || categories.length > 0 || byIntent.length > 0;
  const appQuality = byApp.map((a) => ({ app: a.app, value: a.avg_quality ?? 0 }));
  const intentQuality = byIntent.map((r) => ({
    category: r.category,
    value: r.avg_quality ?? 0,
  }));
  const gcseData = useMemo(
    () =>
      gcseByIntent.map((r) => ({
        category: r.category,
        goal: r.goal ?? 0,
        context: r.context ?? 0,
        source: r.source ?? 0,
        expectation: r.expectation ?? 0,
      })),
    [gcseByIntent],
  );

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Usage breakdown</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Where prompts happen and how quality varies by app and intent.
        </p>
      </div>

      <FilterBar />

      <EmptyState show={loaded && !hasData} />

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Conversations by app" subtitle="Prompt volume per surface">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={byApp} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="app" tick={{ fontSize: 11 }} stroke="#94a3b8" interval={0} height={44} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="prompts" name="Prompts" fill={BAR_COLOR} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Category mix" subtitle="Prompts by detected intent">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={categories}
                dataKey="count"
                nameKey="name"
                innerRadius={55}
                outerRadius={90}
                paddingAngle={2}
              >
                {categories.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip content={<ChartTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Average quality by app" subtitle="Mean prompt quality (RAG)">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={appQuality} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="app" tick={{ fontSize: 11 }} stroke="#94a3b8" interval={0} height={44} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="value" name="Avg quality" radius={[6, 6, 0, 0]}>
                {appQuality.map((a, i) => (
                  <Cell key={i} fill={ragColor(a.value)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Average quality by intent" subtitle="Mean prompt quality (RAG)">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={intentQuality}
              layout="vertical"
              margin={{ left: 20, right: 16, top: 8 }}
            >
              <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
              <YAxis
                type="category"
                dataKey="category"
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
                width={120}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="value" name="Avg quality" radius={[0, 6, 6, 0]}>
                {intentQuality.map((r, i) => (
                  <Cell key={i} fill={ragColor(r.value)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard title="GCSE by intent" subtitle="Goal · Context · Source · Expectation per category">
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={gcseData} margin={{ left: -20, right: 8, top: 8 }} barGap={2}>
            <XAxis dataKey="category" tick={{ fontSize: 11 }} stroke="#94a3b8" interval={0} height={48} />
            <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
            <Legend />
            {GCSE_KEYS.map((g) => (
              <Bar key={g.key} dataKey={g.key} name={g.label} fill={g.color} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
