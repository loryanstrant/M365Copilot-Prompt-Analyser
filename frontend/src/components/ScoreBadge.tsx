import { ragBadgeClass } from "../lib/rag";

// Small RAG-coloured badge for a 1–10 score. Renders "—" when null.
export default function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return <span className="text-slate-400">—</span>;
  }
  return (
    <span
      className={`inline-flex min-w-[2rem] justify-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${ragBadgeClass(
        score,
      )}`}
    >
      {Number.isInteger(score) ? score : score.toFixed(1)}
    </span>
  );
}
