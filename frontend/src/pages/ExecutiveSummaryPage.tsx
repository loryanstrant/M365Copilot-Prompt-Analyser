import { useEffect, useState } from "react";
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
  GovernanceData,
  MetricsSummary,
  NamedCount,
  ScoreBucket,
  SentimentData,
} from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import EmptyState from "../components/EmptyState";
import FilterBar from "../components/FilterBar";
import KpiCard from "../components/KpiCard";
import { CHART_COLORS } from "../components/chartTheme";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";
import { pctSmart, score10, titleCase } from "../lib/format";
import { ragColor } from "../lib/rag";

const BAR_COLOR = "#3b6ef5";

export default function ExecutiveSummaryPage() {
  const filters = useFilters();
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [convQual, setConvQual] = useState<ScoreBucket[]>([]);
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);
  const [categories, setCategories] = useState<NamedCount[]>([]);
  const [byApp, setByApp] = useState<AppQualityRow[]>([]);
  const [gov, setGov] = useState<GovernanceData | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        const [s, cq, se, cm, ba, g] = await Promise.all([
          api<MetricsSummary>(`/metrics/summary${q}`),
          api<ScoreBucket[]>(`/metrics/conversation-quality-distribution${q}`),
          api<SentimentData>(`/metrics/sentiment${q}`),
          api<NamedCount[]>(`/metrics/category-mix${q}`),
          api<AppQualityRow[]>(`/metrics/by-app${q}`),
          api<GovernanceData>(`/metrics/governance${q}`),
        ]);
        setSummary(s);
        setConvQual(cq);
        setSentiment(se);
        setCategories(cm);
        setByApp(ba);
        setGov(g);
      } catch {
        /* ignore */
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterDeps(filters)]);

  const hasData = (summary?.prompts ?? 0) > 0 || (summary?.conversations ?? 0) > 0;
  const convSentiment = (sentiment?.conversation ?? []).map((r) => ({
    name: titleCase(r.name),
    value: r.count,
  }));
  const appData = byApp.map((a) => ({ app: a.app, value: a.avg_quality ?? 0 }));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Executive summary</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          M365 Copilot prompt &amp; conversation quality at a glance.
        </p>
      </div>

      <FilterBar />

      <EmptyState show={loaded && !hasData} />

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <KpiCard label="Conversations" value={summary?.conversations ?? "—"} />
        <KpiCard
          label="Avg prompt quality"
          value={score10(summary?.avg_prompt_quality)}
        />
        <KpiCard label="User generated" value={pctSmart(summary?.user_generated_pct)} />
        <KpiCard
          label="% Neutral conversations"
          value={pctSmart(summary?.pct_neutral_conversations)}
        />
        <KpiCard
          label="% High quality (7–10)"
          value={pctSmart(summary?.pct_high_quality)}
        />
        <KpiCard
          label="Weakest GCSE lever"
          value={titleCase(summary?.weakest_gcse_lever)}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard
          title="Overall conversation quality"
          subtitle="Distribution of conversation scores (1–10)"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={convQual} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="score" tick={{ fontSize: 11 }} stroke="#94a3b8" tickMargin={6} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="count" name="Conversations" radius={[6, 6, 0, 0]}>
                {convQual.map((b, i) => (
                  <Cell key={i} fill={ragColor(b.score)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Conversation sentiment" subtitle="Share of conversations">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={convSentiment}
                dataKey="value"
                nameKey="name"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={2}
              >
                {convSentiment.map((_, i) => (
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
        <ChartCard title="Prompt categories" subtitle="Prompts by detected intent">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={categories}
              layout="vertical"
              margin={{ left: 20, right: 16, top: 8 }}
            >
              <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
                width={120}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="count" name="Prompts" fill={BAR_COLOR} radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Average quality by app" subtitle="Mean prompt quality (RAG)">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={appData} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="app" tick={{ fontSize: 11 }} stroke="#94a3b8" interval={0} height={44} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
              <Bar dataKey="value" name="Avg quality" radius={[6, 6, 0, 0]}>
                {appData.map((a, i) => (
                  <Cell key={i} fill={ragColor(a.value)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ConfidenceChart title="Name confidence" buckets={gov?.name_confidence ?? []} />
        <ConfidenceChart
          title="Sensitive info confidence"
          buckets={gov?.sensitive_confidence ?? []}
        />
      </div>
    </div>
  );
}

function ConfidenceChart({ title, buckets }: { title: string; buckets: ScoreBucket[] }) {
  return (
    <ChartCard title={title} subtitle="Confidence score distribution (1–10)">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={buckets} margin={{ left: -20, right: 8, top: 8 }}>
          <XAxis dataKey="score" tick={{ fontSize: 11 }} stroke="#94a3b8" tickMargin={6} />
          <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
          <Bar dataKey="count" name="Prompts" radius={[6, 6, 0, 0]}>
            {buckets.map((b, i) => (
              <Cell key={i} fill={ragColor(b.score)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
