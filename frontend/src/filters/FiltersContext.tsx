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

// A simple shared slicer. Categorical filters are multi-select: [] means "All".
export interface FilterState {
  dateFrom: string;
  dateTo: string;
  apps: string[];
  categories: string[];
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
      state.categories.length;
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
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** A dependency key so effects re-run when any filter changes. */
export function filterDeps(f: FilterState): string {
  return metricsQuery(f);
}
