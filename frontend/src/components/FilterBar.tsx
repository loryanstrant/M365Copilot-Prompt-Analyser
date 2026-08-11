import MultiSelect from "./MultiSelect";
import { useFilters } from "../filters/FiltersContext";

// Global slicer bar: date range, people & org dimensions, app/category/source,
// governance flags, and a reset. Options that have no data are hidden.
export default function FilterBar({ showFlags = false }: { showFlags?: boolean }) {
  const f = useFilters();
  const o = f.options;

  const userOpts = (o?.users ?? []).map((u) => ({
    value: u.id,
    label: u.department ? `${u.name} · ${u.department}` : u.name,
  }));
  const mgrOpts = (o?.managers ?? []).map((m) => ({ value: m.id, label: m.name }));

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
        label="User"
        allLabel="All users"
        options={userOpts}
        selected={f.users}
        onChange={(v) => f.set({ users: v })}
      />
      {(o?.departments ?? []).length > 0 && (
        <MultiSelect
          label="Department"
          allLabel="All departments"
          options={(o?.departments ?? []).map((d) => ({ value: d, label: d }))}
          selected={f.departments}
          onChange={(v) => f.set({ departments: v })}
        />
      )}
      {mgrOpts.length > 0 && (
        <MultiSelect
          label="Manager"
          allLabel="All managers"
          options={mgrOpts}
          selected={f.managers}
          onChange={(v) => f.set({ managers: v })}
        />
      )}
      {(o?.countries ?? []).length > 0 && (
        <MultiSelect
          label="Country"
          allLabel="All countries"
          options={(o?.countries ?? []).map((c) => ({ value: c, label: c }))}
          selected={f.countries}
          onChange={(v) => f.set({ countries: v })}
        />
      )}
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
      <MultiSelect
        label="Source"
        allLabel="User & system"
        options={[
          { value: "user", label: "User-generated" },
          { value: "system", label: "System-generated" },
        ]}
        selected={f.sources}
        onChange={(v) => f.set({ sources: v })}
      />
      {showFlags && (
        <MultiSelect
          label="Contains"
          allLabel="Any content"
          options={[
            { value: "name", label: "A name" },
            { value: "sensitive", label: "Sensitive info" },
            { value: "profanity", label: "Profanity" },
          ]}
          selected={f.flags}
          onChange={(v) => f.set({ flags: v })}
        />
      )}
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
