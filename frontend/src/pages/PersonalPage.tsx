// The signed-in person's own coaching.
//
// Everything here comes from /metrics/me/*, which derives the person from the
// token. There is deliberately no person picker and no user id in any URL: if
// the page could name a user, anyone could read anyone else's prompts by
// editing the address bar. Picking a person is an organisation activity and
// lives on CoachingPage, behind the organisation-view gate.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
import type { ConversationRow, PersonalCoaching } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import ConversationDrawer from "../components/ConversationDrawer";
import DataTable, { type Column } from "../components/DataTable";
import GovBadge from "../components/GovBadge";
import KpiCard from "../components/KpiCard";
import ScoreBadge from "../components/ScoreBadge";
import { CHART_COLORS } from "../components/chartTheme";
import { gcseToArray, pctSmart, score10, titleCase } from "../lib/format";

// No "User" column: every row here belongs to the person reading the page.
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

function OrgViewBanner({ canViewOrg }: { canViewOrg: boolean }) {
  // The switch is shown locked rather than hidden: people should be able to see
  // that organisation reporting exists and who to ask, instead of wondering
  // whether the app is broken.
  return (
    <div className="card flex flex-wrap items-center justify-between gap-4 p-5">
      {canViewOrg ? (
        <>
          <div>
            <div className="font-medium text-slate-800 dark:text-slate-100">
              Looking for everyone else?
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              You have access to organisation-wide reporting.
            </div>
          </div>
          <Link to="/overview" className="btn-primary whitespace-nowrap">
            View organisation data →
          </Link>
        </>
      ) : (
        <>
          <div>
            <div className="font-medium text-slate-800 dark:text-slate-100">
              Organisation view
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              🔒 Organisation-wide reporting is limited to an approved group. Ask
              your administrator if you need access.
            </div>
          </div>
          <button className="btn-secondary whitespace-nowrap" disabled>
            Not available
          </button>
        </>
      )}
    </div>
  );
}

export default function PersonalPage() {
  const { user } = useAuth();
  const [coaching, setCoaching] = useState<PersonalCoaching | null>(null);
  const [conversations, setConversations] = useState<ConversationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedConv, setSelectedConv] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [c, convs] = await Promise.all([
          api<PersonalCoaching>("/metrics/me/coaching"),
          api<ConversationRow[]>("/metrics/me/conversations?limit=1000"),
        ]);
        if (!cancelled) {
          setCoaching(c);
          setConversations(convs);
        }
      } catch {
        if (!cancelled) {
          setError(
            "We couldn't load your coaching view. Sign in with your work account to see your own prompts.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const chartData = useMemo(() => {
    const mine = gcseToArray(coaching?.gcse_mine ?? null);
    const team = gcseToArray(coaching?.gcse_team ?? null);
    return mine.map((m, i) => ({
      lever: m.lever,
      mine: m.value ?? 0,
      team: team[i]?.value ?? 0,
    }));
  }, [coaching]);

  const hasData = (coaching?.prompts ?? 0) > 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Your coaching</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          How you prompt Microsoft 365 Copilot, and where to sharpen it.
        </p>
      </div>

      <OrgViewBanner canViewOrg={user?.can_view_org ?? false} />

      {error && (
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          {error}
        </div>
      )}

      {loading && <div className="muted text-sm">Loading your coaching…</div>}

      {!loading && !error && !hasData && (
        <div className="card p-10 text-center">
          <h2 className="mb-2 text-lg font-semibold text-slate-800 dark:text-slate-100">
            Nothing to show yet
          </h2>
          <p className="mx-auto max-w-md text-sm text-slate-500 dark:text-slate-400">
            We can&rsquo;t find any analysed prompts for your account. That usually
            means you haven&rsquo;t used Copilot since reporting started, or the
            latest prompts haven&rsquo;t been analysed yet.
          </p>
        </div>
      )}

      {!loading && !error && hasData && coaching && (
        <>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard label="Your prompts" value={coaching.prompts} />
            <KpiCard label="Your conversations" value={coaching.conversations} />
            <KpiCard label="Avg quality" value={score10(coaching.avg_quality)} />
            <KpiCard
              label="User-generated"
              value={pctSmart(coaching.user_generated_pct)}
            />
          </div>

          <div className="rounded-xl border border-brand-200 bg-brand-50 p-5 dark:border-brand-900/40 dark:bg-brand-900/20">
            <div className="text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
              Focus area
            </div>
            <div className="mt-1 text-sm text-slate-700 dark:text-slate-200">
              Your weakest lever is{" "}
              <span className="font-semibold">{titleCase(coaching.weakest_lever)}</span>
              {coaching.strongest_lever && (
                <>
                  {" "}
                  — your strongest is{" "}
                  <span className="font-semibold">
                    {titleCase(coaching.strongest_lever)}
                  </span>
                </>
              )}
              . Sharpening the weakest lever gives the biggest gain.
            </div>
          </div>

          <ChartCard
            title="GCSE vs team"
            subtitle="Your levers compared with the team average"
          >
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ left: -20, right: 8, top: 8 }} barGap={4}>
                <XAxis dataKey="lever" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 10]} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
                <Legend />
                <Bar dataKey="mine" name="You" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
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
              emptyMessage="No conversations of yours have been analysed yet."
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
              personal
              onClose={() => setSelectedConv(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
