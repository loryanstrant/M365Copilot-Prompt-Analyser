import type { Gcse } from "../api/types";

// Format a 0..1 fraction as a rounded percentage.
export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

// Percentage that tolerates either a 0..1 fraction or an already-scaled 0..100
// value from the backend (the contract doesn't pin the scale down).
export function pctSmart(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const scaled = Math.abs(value) <= 1 ? value * 100 : value;
  return `${Math.round(scaled)}%`;
}

// Format a 1..10 score with one decimal and a "/10" suffix.
export function score10(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}/10`;
}

export function num1(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(1);
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t).toLocaleDateString();
}

// Short time-of-day, e.g. "14:32". Falls back to "—" when unparseable.
export function fmtTime(value: string | null | undefined): string {
  if (!value) return "—";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return "—";
  return new Date(t).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const GCSE_LABELS: Record<keyof Gcse, string> = {
  goal: "Goal",
  context: "Context",
  source: "Source",
  expectation: "Expectation",
};

// Turn a GCSE object into a chart-friendly [{ lever, value }] array.
export function gcseToArray(g: Gcse | null | undefined) {
  if (!g) return [] as { lever: string; value: number | null }[];
  return (Object.keys(GCSE_LABELS) as (keyof Gcse)[]).map((k) => ({
    lever: GCSE_LABELS[k],
    value: g[k],
  }));
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "—";
  return value.charAt(0).toUpperCase() + value.slice(1);
}
