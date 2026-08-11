import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { FilterOptions } from "../api/types";

// A shared slicer. Categorical filters are multi-select: [] means "All".
// A numeric quality range is optional (null = unbounded).
export interface FilterState {
  dateFrom: string;
  dateTo: string;
  apps: string[];
  categories: string[];
  users: string[];        // user_ids
  departments: string[];
  managers: string[];     // manager user_ids
  countries: string[];
  sources: string[];      // "user" | "system"
  flags: string[];        // "name" | "sensitive" | "profanity"
  qualityMin: number | null;
  qualityMax: number | null;
}

export interface Filters extends FilterState {
  options: FilterOptions | null;
  set: (patch: Partial<FilterState>) => void;
  reset: () => void;
  activeCount: number;
}

const EMPTY: FilterState = {
  dateFrom: "",
  dateTo: "",
  apps: [],
  categories: [],
  users: [],
  departments: [],
  managers: [],
  countries: [],
  sources: [],
  flags: [],
  qualityMin: null,
  qualityMax: null,
};

const FiltersContext = createContext<Filters | null>(null);

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FilterState>(EMPTY);
  const [options, setOptions] = useState<FilterOptions | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setOptions(await api<FilterOptions>("/metrics/filters"));
      } catch {
        /* ignore — filters are optional */
      }
    })();
  }, []);

  const value = useMemo<Filters>(() => {
    const set = (patch: Partial<FilterState>) => setState((s) => ({ ...s, ...patch }));
    const reset = () => setState(EMPTY);
    const activeCount =
      (state.dateFrom ? 1 : 0) +
      (state.dateTo ? 1 : 0) +
      state.apps.length +
      state.categories.length +
      state.users.length +
      state.departments.length +
      state.managers.length +
      state.countries.length +
      state.sources.length +
      state.flags.length +
      (state.qualityMin !== null ? 1 : 0) +
      (state.qualityMax !== null ? 1 : 0);
    return { ...state, options, set, reset, activeCount };
  }, [state, options]);

  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>;
}

export function useFilters(): Filters {
  const ctx = useContext(FiltersContext);
  if (!ctx) throw new Error("useFilters must be used within FiltersProvider");
  return ctx;
}

/** Serialise active filters into a metrics query string (repeated params). */
export function metricsQuery(f: FilterState): string {
  const p = new URLSearchParams();
  if (f.dateFrom) p.set("date_from", f.dateFrom);
  if (f.dateTo) p.set("date_to", f.dateTo);
  f.apps.forEach((v) => p.append("app", v));
  f.categories.forEach((v) => p.append("category", v));
  f.users.forEach((v) => p.append("user", v));
  f.departments.forEach((v) => p.append("department", v));
  f.managers.forEach((v) => p.append("manager", v));
  f.countries.forEach((v) => p.append("country", v));
  f.sources.forEach((v) => p.append("source", v));
  f.flags.forEach((v) => p.append("flag", v));
  if (f.qualityMin !== null) p.set("quality_min", String(f.qualityMin));
  if (f.qualityMax !== null) p.set("quality_max", String(f.qualityMax));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** A dependency key so effects re-run when any filter changes. */
export function filterDeps(f: FilterState): string {
  return metricsQuery(f);
}
