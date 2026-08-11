import { FLAG_THRESHOLD } from "../lib/rag";

// A governance confidence (1–10) for name / sensitive-info / profanity.
// Shows the number, tinted red when it meets the "contains" threshold (>=7),
// muted otherwise. Renders "—" when null.
export default function GovBadge({
  score,
  label,
}: {
  score: number | null | undefined;
  label?: string;
}) {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return <span className="text-slate-400">—</span>;
  }
  const flagged = score >= FLAG_THRESHOLD;
  return (
    <span
      title={label ? `${label}: ${score}/10` : `${score}/10`}
      className={`inline-flex min-w-[2rem] justify-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${
        flagged
          ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
          : "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400"
      }`}
    >
      {score}
    </span>
  );
}
