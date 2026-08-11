import MultiSelect from "./MultiSelect";
import { useFilters } from "../filters/FiltersContext";

// Compact global slicer bar: date range, app + category multi-selects, reset.
export default function FilterBar() {
  const f = useFilters();
  const o = f.options;

  return (
    <div className="card flex flex-wrap items-end gap-3 p-4">
      <Field label="From">
        <input
          type="date"
          value={f.dateFrom}
          onChange={(e) => f.set({ dateFrom: e.target.value })}
          className="input h-[38px] w-40"
        />
      </Field>
      <Field label="To">
        <input
          type="date"
          value={f.dateTo}
          onChange={(e) => f.set({ dateTo: e.target.value })}
          className="input h-[38px] w-40"
        />
      </Field>
      <MultiSelect
        label="App"
        allLabel="All apps"
        options={(o?.apps ?? []).map((a) => ({ value: a, label: a }))}
        selected={f.apps}
        onChange={(v) => f.set({ apps: v })}
      />
      <MultiSelect
        label="Category"
        allLabel="All categories"
        options={(o?.categories ?? []).map((c) => ({ value: c, label: c }))}
        selected={f.categories}
        onChange={(v) => f.set({ categories: v })}
      />
      {f.activeCount > 0 && (
        <button onClick={f.reset} className="btn-secondary ml-auto h-[38px]">
          Reset ({f.activeCount})
        </button>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
        {label}
      </label>
      {children}
    </div>
  );
}
