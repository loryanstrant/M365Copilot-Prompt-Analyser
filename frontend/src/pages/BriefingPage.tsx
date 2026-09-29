// The executive briefing: a plain-English snapshot of the last period.
//
// Every number comes from SQL (GET /metrics/briefing) and every sentence is
// assembled here from fixed thresholds. This app has Azure OpenAI configured
// and deliberately does not use it for this page: a summary read out in front
// of a customer must never contain a figure the app invented, and a narrated
// briefing is exactly where an invented figure would go unnoticed.
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { Briefing, BriefingIntent, DailyPoint } from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import { gradId } from "../components/chartTheme";
import { score10, titleCase } from "../lib/format";

type Tone = "positive" | "negative" | "neutral";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

// Fractional change cur vs prev. null = no prior baseline (treat as "new").
function delta(cur: number, prev: number): number | null {
  if (prev === 0) return cur > 0 ? null : 0;
  return (cur - prev) / prev;
}

function intentDelta(a: BriefingIntent): number | null {
  return delta(a.prompts, a.prev_prompts);
}

// "up 18%" / "down 9%" / "flat"
function movement(d: number): string {
  if (Math.abs(d) < 0.005) return "flat";
  return `${d > 0 ? "up" : "down"} ${Math.round(Math.abs(d) * 100)}%`;
}

// "+18%" / "−9%" / "flat" / "new"
function chip(d: number | null): string {
  if (d === null) return "new";
  if (Math.abs(d) < 0.005) return "flat";
  return `${d > 0 ? "+" : "−"}${Math.round(Math.abs(d) * 100)}%`;
}

function toneOf(d: number | null): Tone {
  if (d === null) return "positive";
  if (d > 0.005) return "positive";
  if (d < -0.005) return "negative";
  return "neutral";
}

// Quality moves on a 1-10 scale, so a fractional-change chip would be
// meaningless — half a point is the band the personal view already treats as
// noise, and the same threshold is used here.
function qualityTone(cur: number | null, prev: number | null): Tone {
  if (cur == null || prev == null) return "neutral";
  if (cur - prev > 0.5) return "positive";
  if (cur - prev < -0.5) return "negative";
  return "neutral";
}

function buildNarrative(b: Briefing): { tone: Tone; text: string }[] {
  const w = b.window_days;
  const end = fmtDate(b.period_end);
  const dP = delta(b.current.prompts, b.previous.prompts);
  const out: { tone: Tone; text: string }[] = [];

  const trend =
    dP === null
      ? `, with no comparable activity in the prior ${w} days`
      : Math.abs(dP) < 0.005
        ? ", holding roughly flat against the previous period"
        : `, ${movement(dP)} versus the previous ${w} days`;
  out.push({
    tone: toneOf(dP),
    text: `In the ${w} days to ${end}, ${b.current.people.toLocaleString()} people wrote ${b.current.prompts.toLocaleString()} Copilot prompts across ${b.current.conversations.toLocaleString()} conversations${trend}.`,
  });

  if (b.current.avg_quality != null) {
    const qt = qualityTone(b.current.avg_quality, b.previous.avg_quality);
    const against =
      b.previous.avg_quality == null
        ? ""
        : qt === "neutral"
          ? `, level with the previous period`
          : `, ${qt === "positive" ? "up" : "down"} from ${b.previous.avg_quality.toFixed(1)}`;
    out.push({
      tone: qt,
      text: `Prompt quality averaged ${b.current.avg_quality.toFixed(1)} out of 10${against}.`,
    });
  }

  out.push({
    tone: b.current.user_generated_pct >= 70 ? "positive" : "neutral",
    text: `${Math.round(b.current.user_generated_pct)}% of those prompts were written by the person rather than accepted from a suggestion, which is the share that shows people driving Copilot rather than being led by it.`,
  });

  const top = b.top_intents[0];
  if (top) {
    const growing = b.top_intents
      .map((a) => ({ a, d: intentDelta(a) }))
      .filter((x) => x.d !== null && (x.d as number) > 0.05)
      .sort((x, y) => (y.d as number) - (x.d as number))[0];
    const grownText = growing
      ? ` ${titleCase(growing.a.name)} is growing fastest (${movement(growing.d as number)}).`
      : "";
    out.push({
      tone: "positive",
      text: `The most common thing people asked for was ${titleCase(top.name).toLowerCase()}, at ${top.prompts.toLocaleString()} prompts.${grownText}`,
    });
  }

  if (b.people_needing_coaching > 0) {
    out.push({
      tone: "negative",
      text: `${b.people_needing_coaching.toLocaleString()} ${
        b.people_needing_coaching === 1 ? "person is" : "people are"
      } averaging below 4 out of 10 on prompt quality and would gain most from coaching.`,
    });
  }

  return out;
}

function buildHighlights(b: Briefing): string[] {
  const items: string[] = [];
  const dP = delta(b.current.prompts, b.previous.prompts);
  if (dP !== null && dP > 0.005)
    items.push(`Prompt volume ${movement(dP)} period-on-period.`);
  if (
    b.current.avg_quality != null &&
    qualityTone(b.current.avg_quality, b.previous.avg_quality) === "positive"
  )
    items.push(
      `Average quality improved to ${b.current.avg_quality.toFixed(1)} out of 10.`,
    );
  if (b.current.user_generated_pct >= 70)
    items.push(
      `${Math.round(b.current.user_generated_pct)}% of prompts were written by hand rather than suggested.`,
    );
  const growing = b.top_intents
    .map((a) => ({ a, d: intentDelta(a) }))
    .filter((x) => x.d !== null && (x.d as number) > 0.05)
    .sort((x, y) => (y.d as number) - (x.d as number))[0];
  if (growing)
    items.push(
      `${titleCase(growing.a.name)} is accelerating (${chip(growing.d)}).`,
    );
  const theme = b.top_themes[0];
  if (theme)
    items.push(
      `Most conversations were about ${theme.name.toLowerCase()} (${theme.conversations.toLocaleString()}).`,
    );
  const best = [...b.levers].sort((a, c) => c.score - a.score)[0];
  if (best) items.push(`Strongest prompting habit: ${titleCase(best.lever)}.`);
  return items.slice(0, 5);
}

function buildWatchouts(b: Briefing): string[] {
  const items: string[] = [];
  const dP = delta(b.current.prompts, b.previous.prompts);
  if (dP !== null && dP < -0.005)
    items.push(`Usage ${movement(dP)} versus the previous period.`);
  if (
    b.current.avg_quality != null &&
    qualityTone(b.current.avg_quality, b.previous.avg_quality) === "negative"
  )
    items.push(
      `Average quality slipped to ${b.current.avg_quality.toFixed(1)} out of 10.`,
    );
  if (b.people_needing_coaching > 0)
    items.push(
      `${b.people_needing_coaching.toLocaleString()} ${
        b.people_needing_coaching === 1 ? "person averages" : "people average"
      } below 4 out of 10.`,
    );
  if (b.low_quality_prompts > 0 && b.current.prompts > 0)
    items.push(
      `${Math.round((100 * b.low_quality_prompts) / b.current.prompts)}% of prompts scored in the weakest band.`,
    );
  const weakest = b.levers[0];
  if (weakest)
    items.push(
      `${titleCase(weakest.lever)} is the weakest lever organisation-wide (${weakest.score.toFixed(1)} out of 10).`,
    );
  const declining = b.top_intents
    .map((a) => ({ a, d: intentDelta(a) }))
    .filter((x) => x.d !== null && (x.d as number) < -0.1)
    .sort((x, y) => (x.d as number) - (y.d as number))[0];
  if (declining)
    items.push(`${titleCase(declining.a.name)} fell ${chip(declining.d)}.`);
  return items.slice(0, 5);
}

function buildActions(b: Briefing): string[] {
  const items: string[] = [];
  const weakest = b.levers[0];
  if (weakest)
    items.push(
      `Run a short session on ${titleCase(weakest.lever).toLowerCase()} — it is the lever the whole organisation scores lowest on, so it is the one with the most to gain.`,
    );
  if (b.people_needing_coaching > 0)
    items.push(
      `Start with the ${b.people_needing_coaching.toLocaleString()} ${
        b.people_needing_coaching === 1 ? "person" : "people"
      } averaging below 4 out of 10 — People coaching names them and shows where each one loses marks.`,
    );
  const worstIntent = [...b.top_intents]
    .filter((i) => i.avg_quality != null)
    .sort((a, c) => (a.avg_quality as number) - (c.avg_quality as number))[0];
  if (worstIntent)
    items.push(
      `Publish a worked example for ${titleCase(worstIntent.name).toLowerCase()} prompts, which score lowest of the common requests (${(worstIntent.avg_quality as number).toFixed(1)} out of 10).`,
    );
  if (b.current.user_generated_pct < 70)
    items.push(
      `Only ${Math.round(b.current.user_generated_pct)}% of prompts are written by hand — show people how to open with their own goal rather than a suggested starter.`,
    );
  items.push(
    "Dig into the detail on the Usage breakdown and Prompt quality pages.",
  );
  return items.slice(0, 5);
}

export default function BriefingPage() {
  const [b, setB] = useState<Briefing | null>(null);
  const [daily, setDaily] = useState<DailyPoint[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [brief, d] = await Promise.all([
          api<Briefing>("/metrics/briefing"),
          api<DailyPoint[]>("/metrics/daily"),
        ]);
        if (active) {
          setB(brief);
          setDaily(d);
        }
      } catch {
        /* the empty state below covers it */
      } finally {
        if (active) setLoaded(true);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const narrative = useMemo(() => (b ? buildNarrative(b) : []), [b]);
  const highlights = useMemo(() => (b ? buildHighlights(b) : []), [b]);
  const watchouts = useMemo(() => (b ? buildWatchouts(b) : []), [b]);
  const actions = useMemo(() => (b ? buildActions(b) : []), [b]);
  const spark = useMemo(() => daily.slice(-60), [daily]);
  const generatedAt = useMemo(
    () =>
      new Date().toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }),
    [],
  );

  if (loaded && (!b || b.total_prompts === 0)) {
    return (
      <div className="space-y-6">
        <Header period="" generatedAt={generatedAt} />
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          No analysed prompts yet. Configure Microsoft Graph and Azure OpenAI in
          Settings and run a collection to generate your first briefing.
        </div>
      </div>
    );
  }

  // History exists but this window is empty — a gap in collection, or genuinely
  // quiet weeks. Saying so is better than a briefing full of zeroes describing
  // a period nothing happened in.
  if (loaded && b && b.current.prompts === 0) {
    return (
      <div className="space-y-6">
        <Header
          period={`${b.window_days} days to ${fmtDate(b.period_end)}`}
          generatedAt={generatedAt}
        />
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          No prompts were analysed in the last {b.window_days} days, so there is
          nothing to compare this period against the one before it.{" "}
          {b.total_prompts.toLocaleString()} prompts are stored from earlier
          periods — check Settings for when the last collection ran.
        </div>
      </div>
    );
  }

  if (!b) {
    return (
      <div className="space-y-6">
        <Header period="" generatedAt={generatedAt} />
        <div className="text-sm text-slate-500 dark:text-slate-400">
          Preparing briefing…
        </div>
      </div>
    );
  }

  const period = `${b.window_days} days to ${fmtDate(b.period_end)}`;
  const dPrompts = delta(b.current.prompts, b.previous.prompts);
  const dConv = delta(b.current.conversations, b.previous.conversations);
  const dPeople = delta(b.current.people, b.previous.people);

  return (
    <div className="space-y-8">
      <Header period={period} generatedAt={generatedAt} />

      {/* Narrative commentary — the heart of the briefing. */}
      <div className="card border-l-4 border-l-brand-500 p-6">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
          <span>Summary</span>
          <span className="text-slate-300 dark:text-slate-600">•</span>
          <span className="font-normal normal-case text-slate-400">
            Assembled from your own figures — nothing here is generated by a
            language model
          </span>
        </div>
        <div className="space-y-2.5">
          {narrative.map((p, i) => (
            <p
              key={i}
              className="flex gap-2 text-[15px] leading-relaxed text-slate-700 dark:text-slate-200"
            >
              <span aria-hidden className={`mt-1 text-xs ${toneColor(p.tone)}`}>
                {p.tone === "positive" ? "▲" : p.tone === "negative" ? "▼" : "■"}
              </span>
              <span>{p.text}</span>
            </p>
          ))}
        </div>
      </div>

      {/* Headline movement vs the previous period. */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <DeltaStat label="Prompts" value={b.current.prompts} d={dPrompts} />
        <DeltaStat
          label="Conversations"
          value={b.current.conversations}
          d={dConv}
        />
        <DeltaStat label="People prompting" value={b.current.people} d={dPeople} />
        <DeltaStat
          label="User-generated"
          value={`${Math.round(b.current.user_generated_pct)}%`}
          d={null}
          hint="Written by the person, not a suggestion"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard
          title="Momentum"
          subtitle="Daily prompt volume, last 60 days"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={spark} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
                tickMargin={8}
                minTickGap={24}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
                allowDecimals={false}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="prompts"
                name="Prompts"
                stroke="#3b6ef5"
                strokeWidth={2.5}
                fill={`url(#${gradId(0)})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <div className="card flex flex-col items-center justify-center gap-3 p-6 text-center">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Average prompt quality
          </div>
          <ScoreRing score={b.current.avg_quality} />
          <div className="text-xs text-slate-400 dark:text-slate-500">
            {b.current.prompts.toLocaleString()} prompts this period ·{" "}
            {b.total_prompts.toLocaleString()} all time
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ListCard
          title="Highlights"
          tone="positive"
          items={highlights}
          empty="Nothing notable this period."
        />
        <ListCard
          title="Watch-outs"
          tone="negative"
          items={watchouts}
          empty="No concerns flagged — nice."
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
            What people asked for
          </h3>
          <p className="mb-4 text-xs text-slate-400 dark:text-slate-500">
            The most common request types, and how well each was prompted
          </p>
          {b.top_intents.length === 0 ? (
            <div className="text-sm text-slate-400">
              No analysed prompts this period.
            </div>
          ) : (
            <RankedBars
              rows={b.top_intents.map((i) => ({
                name: titleCase(i.name),
                value: i.prompts,
                note: i.avg_quality != null ? score10(i.avg_quality) : undefined,
                delta: intentDelta(i),
              }))}
            />
          )}
        </div>

        <div className="card p-6">
          <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
            What the work was about
          </h3>
          <p className="mb-4 text-xs text-slate-400 dark:text-slate-500">
            The themes running through this period's conversations
          </p>
          {b.top_themes.length === 0 ? (
            <div className="text-sm text-slate-400">
              No analysed conversations this period.
            </div>
          ) : (
            <RankedBars
              rows={b.top_themes.map((t) => ({
                name: t.name,
                value: t.conversations,
              }))}
            />
          )}
        </div>
      </div>

      <ListCard
        title="Suggested actions"
        tone="neutral"
        items={actions}
        empty=""
        numbered
      />
    </div>
  );
}

function Header({
  period,
  generatedAt,
}: {
  period: string;
  generatedAt: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold">Executive briefing</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {period
            ? `A plain-English snapshot for the ${period}.`
            : "Copilot prompting at a glance."}
        </p>
      </div>
      <div className="text-right text-xs text-slate-400 dark:text-slate-500">
        Generated {generatedAt}
      </div>
    </div>
  );
}

function toneColor(tone: Tone): string {
  return tone === "positive"
    ? "text-emerald-500"
    : tone === "negative"
      ? "text-rose-500"
      : "text-slate-400";
}

function DeltaChip({ d }: { d: number | null }) {
  const tone = toneOf(d);
  const cls =
    tone === "positive"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
      : tone === "negative"
        ? "bg-rose-50 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400"
        : "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${cls}`}
    >
      {chip(d)}
    </span>
  );
}

function DeltaStat({
  label,
  value,
  d,
  hint,
}: {
  label: string;
  value: string | number;
  d: number | null;
  hint?: string;
}) {
  const showDelta = d !== null;
  const tone = toneOf(d);
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm dark:border-slate-700 dark:from-slate-800 dark:to-slate-900/60">
      <div className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full bg-brand-500/10 blur-2xl" />
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
          {label}
        </span>
        {showDelta && <DeltaChip d={d} />}
      </div>
      <div className="mt-2 bg-gradient-to-br from-slate-900 to-slate-500 bg-clip-text text-3xl font-bold tabular-nums text-transparent dark:from-white dark:to-slate-400">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
        {hint ?? (showDelta ? "vs previous period" : "")}
        {showDelta && !hint && tone !== "neutral"
          ? ` · ${movement(d as number)}`
          : ""}
      </div>
    </div>
  );
}

/**
 * A ranked list of labelled bars.
 *
 * Bars are sized against the largest value present rather than a total, so one
 * dominant row doesn't flatten the rest into invisibility.
 */
function RankedBars({
  rows,
}: {
  rows: { name: string; value: number; note?: string; delta?: number | null }[];
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <div key={row.name}>
          <div className="flex items-center justify-between gap-2">
            <span
              className="truncate text-sm font-medium text-slate-800 dark:text-slate-100"
              title={row.name}
            >
              {row.name}
            </span>
            <div className="flex shrink-0 items-center gap-2">
              {row.note && (
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {row.note}
                </span>
              )}
              <span className="tabular-nums text-sm text-slate-500 dark:text-slate-400">
                {row.value.toLocaleString()}
              </span>
              {row.delta !== undefined && <DeltaChip d={row.delta} />}
            </div>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
            <div
              className="h-full rounded-full bg-brand-500"
              style={{ width: `${Math.max((row.value / max) * 100, 2)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function ListCard({
  title,
  tone,
  items,
  empty,
  numbered = false,
}: {
  title: string;
  tone: Tone;
  items: string[];
  empty: string;
  numbered?: boolean;
}) {
  const dot =
    tone === "positive"
      ? "text-emerald-500"
      : tone === "negative"
        ? "text-amber-500"
        : "text-brand-500";
  return (
    <div className="card p-6">
      <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
        {title}
      </h3>
      {items.length === 0 ? (
        <div className="text-sm text-slate-400">{empty}</div>
      ) : (
        <ul className="space-y-2.5">
          {items.map((it, i) => (
            <li
              key={i}
              className="flex gap-2.5 text-sm text-slate-600 dark:text-slate-300"
            >
              <span className={`shrink-0 font-semibold ${dot}`}>
                {numbered ? `${i + 1}.` : "•"}
              </span>
              <span>{it}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Average prompt quality as a ring. Scores are 1-10, so the ring is filled to
 *  score/10 and the figure is shown as written everywhere else in the app. */
function ScoreRing({ score }: { score: number | null }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(10, score ?? 0)) / 10;
  return (
    <svg
      width={96}
      height={96}
      viewBox="0 0 88 88"
      role="img"
      aria-label={`Average prompt quality ${score ?? "unknown"} out of 10`}
    >
      <circle
        cx={44}
        cy={44}
        r={r}
        fill="none"
        strokeWidth={8}
        className="stroke-slate-200 dark:stroke-slate-700"
      />
      <circle
        cx={44}
        cy={44}
        r={r}
        fill="none"
        stroke="#3b6ef5"
        strokeWidth={8}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - frac)}
        transform="rotate(-90 44 44)"
      />
      <text
        x={44}
        y={42}
        textAnchor="middle"
        className="fill-slate-900 dark:fill-white"
        fontSize={22}
        fontWeight={700}
      >
        {score == null ? "—" : score.toFixed(1)}
      </text>
      <text x={44} y={58} textAnchor="middle" className="fill-slate-400" fontSize={10}>
        / 10
      </text>
    </svg>
  );
}
