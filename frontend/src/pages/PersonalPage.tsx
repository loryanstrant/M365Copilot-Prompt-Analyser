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
import type { ConversationRow, PersonalCoaching, Person } from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import ConversationDrawer from "../components/ConversationDrawer";
import DataTable, { type Column } from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import GovBadge from "../components/GovBadge";
import KpiCard from "../components/KpiCard";
import ScoreBadge from "../components/ScoreBadge";
import { CHART_COLORS } from "../components/chartTheme";
import { gcseToArray, pctSmart, score10, titleCase } from "../lib/format";

// Conversation columns for the person's own list — same as the Conversations
// page but without the redundant User column (everything is one person).
const convColumns: Column<ConversationRow>[] = [
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

function personLabel(p: Person): string {
  const dept = p.department ? ` · ${p.department}` : "";
  return `${p.name}${dept} (${p.prompts} prompts)`;
}

export default function PersonalPage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleLoaded, setPeopleLoaded] = useState(false);
  const [userId, setUserId] = useState<string>("");

  const [coaching, setCoaching] = useState<PersonalCoaching | null>(null);
  const [conversations, setConversations] = useState<ConversationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedConv, setSelectedConv] = useState<string | null>(null);

  // Load the person roster once, defaulting to the first person.
  useEffect(() => {
    (async () => {
      try {
        const list = await api<Person[]>("/metrics/people");
        setPeople(list);
        if (list.length) setUserId(list[0].user_id);
      } catch {
        /* ignore */
      } finally {
        setPeopleLoaded(true);
      }
    })();
  }, []);

  // Load coaching + conversations whenever the selected person changes.
  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setCoaching(null);
      setConversations([]);
      setSelectedConv(null);
      try {
        const params = new URLSearchParams();
        params.set("user", userId);
        params.set("limit", "1000");
        const [c, convs] = await Promise.all([
          api<PersonalCoaching>(`/metrics/personal/${encodeURIComponent(userId)}`),
          api<ConversationRow[]>(`/metrics/conversations?${params.toString()}`),
        ]);
        if (!cancelled) {
          setCoaching(c);
          setConversations(convs);
        }
      } catch {
        if (!cancelled) {
          setCoaching(null);
          setConversations([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const chartData = useMemo(() => {
    const mine = gcseToArray(coaching?.gcse_mine ?? null);
    const team = gcseToArray(coaching?.gcse_team ?? null);
    return mine.map((m, i) => ({
      lever: m.lever,
      mine: m.value ?? 0,
      team: team[i]?.value ?? 0,
    }));
  }, [coaching]);

  const hasPeople = people.length > 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Personal coaching</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Act as a person to see the coaching view they would get.
        </p>
      </div>

      <EmptyState show={peopleLoaded && !hasPeople} />

      {hasPeople && (
        <div className="card flex flex-wrap items-end gap-3 p-4">
          <div className="min-w-[20rem] flex-1">
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
              Act as
            </label>
            <select
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="input w-full"
            >
              {people.map((p) => (
                <option key={p.user_id} value={p.user_id}>
                  {personLabel(p)}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {loading && <div className="muted text-sm">Loading coaching…</div>}

      {!loading && coaching && (
        <>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard label="Prompts" value={coaching.prompts} />
            <KpiCard label="Conversations" value={coaching.conversations} />
            <KpiCard label="Avg quality" value={score10(coaching.avg_quality)} />
            <KpiCard label="User-generated" value={pctSmart(coaching.user_generated_pct)} />
          </div>

          <div className="rounded-xl border border-brand-200 bg-brand-50 p-5 dark:border-brand-900/40 dark:bg-brand-900/20">
            <div className="text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
              Focus area
            </div>
            <div className="mt-1 text-sm text-slate-700 dark:text-slate-200">
              {coaching.name}&rsquo;s weakest lever is{" "}
              <span className="font-semibold">{titleCase(coaching.weakest_lever)}</span>
              {coaching.strongest_lever && (
                <>
                  {" "}
                  — strongest is{" "}
                  <span className="font-semibold">{titleCase(coaching.strongest_lever)}</span>
                </>
              )}
              . Coaching should prioritise sharpening the weakest lever.
            </div>
          </div>

          <ChartCard title="GCSE vs team" subtitle="Your levers compared with the team average">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ left: -20, right: 8, top: 8 }} barGap={4}>
                <XAxis dataKey="lever" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
                <Legend />
                <Bar dataKey="mine" name="This person" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="team" name="Team average" fill={CHART_COLORS[2]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                Your conversations
              </h3>
            </div>
            <DataTable
              rows={conversations}
              getRowKey={(r) => r.conversation_id}
              initialSort={{ key: "conversation", dir: "desc" }}
              emptyMessage="No conversations for this person."
              columns={convColumns}
              maxBodyHeight={420}
              rowClassName={(r) =>
                `cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/40 ${
                  r.conversation_id === selectedConv ? "bg-brand-50 dark:bg-brand-900/20" : ""
                }`
              }
              onRowClick={(r) => setSelectedConv(r.conversation_id)}
            />
          </div>

          {selectedConv && (
            <ConversationDrawer
              conversationId={selectedConv}
              onClose={() => setSelectedConv(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
