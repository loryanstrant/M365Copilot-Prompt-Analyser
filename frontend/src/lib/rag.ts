// Shared Red/Amber/Green colouring for 1–10 quality & GCSE scores.
// >=7 green, 4–6 amber, <4 red. Null/undefined falls back to a neutral slate.

export const RAG_GREEN = "#1F8A4C";
export const RAG_AMBER = "#B9791A";
export const RAG_RED = "#C8362F";
export const RAG_NEUTRAL = "#94a3b8";

// A governance confidence >= this counts as "contains a name / sensitive
// info / profanity" (mirrors the API's FLAG_THRESHOLD).
export const FLAG_THRESHOLD = 7;

export function ragColor(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return RAG_NEUTRAL;
  if (score >= 7) return RAG_GREEN;
  if (score >= 4) return RAG_AMBER;
  return RAG_RED;
}

export type RagBand = "green" | "amber" | "red" | "neutral";

export function ragBand(score: number | null | undefined): RagBand {
  if (score === null || score === undefined || Number.isNaN(score)) return "neutral";
  if (score >= 7) return "green";
  if (score >= 4) return "amber";
  return "red";
}

// Tailwind-friendly badge classes (bg + text) for the same bands, light+dark.
export function ragBadgeClass(score: number | null | undefined): string {
  switch (ragBand(score)) {
    case "green":
      return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400";
    case "amber":
      return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400";
    case "red":
      return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400";
    default:
      return "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300";
  }
}
