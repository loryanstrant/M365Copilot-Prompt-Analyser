import ChartCard from "./ChartCard";
import { score10 } from "../lib/format";
import type { Gcse } from "../api/types";

export interface PeerComparisonData {
  mine: Gcse;
  team: Gcse | null;
  team_label: string | null;
  team_size: number;
  team_withheld: "too_small" | "unknown_team" | null;
  min_team_peers: number;
  organisation: Gcse;
  organisation_size: number;
  percentile: Partial<Record<keyof Gcse, number | null>>;
  percentile_band: Partial<Record<keyof Gcse, string | null>>;
  period_from: string | null;
  period_to: string | null;
}

const MEASURES: { key: keyof Gcse; label: string }[] = [
  { key: "goal", label: "Goal" },
  { key: "context", label: "Context" },
  { key: "source", label: "Source" },
  { key: "expectation", label: "Expectation" },
];

// The levers are scored 1-10, so the bars are drawn against a fixed 10 rather
// than against the largest value present. A relative scale would make a 6.1 and
// a 6.3 look like a rout.
const SCALE_MAX = 10;

function fmtPeriod(from: string | null, to: string | null): string {
  if (!from && !to) return "the period this data covers";
  const d = (s: string) =>
    new Date(`${s}T00:00:00`).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  if (from && to) return `${d(from)} – ${d(to)}`;
  return from ? `since ${d(from)}` : `up to ${d(to as string)}`;
}

/**
 * You, your team and your organisation on the four GCSE levers, out of 10.
 *
 * What this replaced drew its second bar from the average across the entire
 * tenant and called it "Team average". Three things this component is careful
 * about, all decided in docs/specs/comparisons-and-timelines.md:
 *
 * - The team row is **absent** when the server withholds it, never a zero bar.
 *   An empty bar reads as "you are miles ahead of your team" when it means
 *   "that team is too small to show without identifying someone".
 * - The period is named, because three series over different windows would be
 *   arithmetically fine and completely misleading.
 * - The percentile says which population it is measured against — the
 *   organisation, never the team.
 */
export default function PeerComparison({
  data,
  /**
   * Whose comparison this is. CoachingPage shows one person to somebody else
   * with organisation access, where "you" would name the wrong person.
   */
  perspective = "self",
}: {
  data: PeerComparisonData;
  perspective?: "self" | "other";
}) {
  const self = perspective === "self";
  const hasTeam = data.team !== null;
  const subject = self ? "You" : "This person";
  const theirTeam = self ? "your team" : "their team";
  const who = hasTeam
    ? `${subject}, ${theirTeam} (${data.team_label}) and the organisation`
    : `${subject} and the organisation`;
  const subtitle = `${who} · each lever out of 10 · ${fmtPeriod(
    data.period_from,
    data.period_to,
  )}`;

  return (
    <ChartCard
      title={self ? "How you compare" : "How they compare"}
      subtitle={subtitle}
    >
      <div className="space-y-5 text-sm">
        {MEASURES.map((m) => {
          const mine = data.mine?.[m.key] ?? null;
          const team = data.team ? data.team[m.key] ?? null : null;
          const org = data.organisation?.[m.key] ?? null;
          // The band rather than the exact percentile: a lever average out of 10
          // has so little spread that two people displaying the same 4.8 land
          // five percentile points apart, which is precision the figure has not
          // got. The exact number is still in the payload.
          const band = data.percentile_band?.[m.key];
          const rows: { label: string; value: number | null; bar: string }[] = [
            { label: subject, value: mine, bar: "bg-brand-600" },
            ...(data.team !== null
              ? [
                  {
                    label: self ? "Your team" : "Their team",
                    value: team,
                    bar: "bg-brand-300",
                  },
                ]
              : []),
            { label: "Organisation", value: org, bar: "bg-slate-400" },
          ];
          return (
            <div key={m.key}>
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <span className="font-medium text-slate-800 dark:text-slate-100">
                  {m.label}
                </span>
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {band
                    ? `In the ${band} of the organisation`
                    : "not enough data to rank"}
                </span>
              </div>
              <div className="space-y-1">
                {rows.map((r) => (
                  <div key={r.label} className="flex items-center gap-2">
                    <span className="w-28 shrink-0 text-xs text-slate-500 dark:text-slate-400">
                      {r.label}
                    </span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
                      <div
                        className={`h-full rounded-full ${r.bar}`}
                        style={{
                          width:
                            r.value === null
                              ? "0%"
                              : `${Math.max((r.value / SCALE_MAX) * 100, 2)}%`,
                        }}
                      />
                    </div>
                    <span className="w-16 shrink-0 text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">
                      {score10(r.value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {!hasTeam && (
        <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
          No team comparison:{" "}
          {data.team_withheld === "too_small"
            ? `${theirTeam} is too small to show without identifying someone — a team average needs at least ${data.min_team_peers} other people in it, and ${
                self ? "yours" : "theirs"
              } has ${data.team_size}.`
            : self
              ? "we don't know which team you're in — your directory record has no department or manager."
              : "we don't know which team they're in — their directory record has no department or manager."}
        </p>
      )}
    </ChartCard>
  );
}
