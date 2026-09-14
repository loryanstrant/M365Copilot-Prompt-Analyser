import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import SetupWizard from "../components/SetupWizard";
import DemoDataCard from "../components/DemoDataCard";
import type {
  AppConfig,
  IngestRunResult,
  StatusResult,
  TestAoaiResult,
  TestConnectionResult,
} from "../api/types";

const DEFAULT_SKU = "639dec6b-bb19-468b-871c-c5c441c4b0cb";
const DEFAULT_DEPLOYMENT = "gpt-5.4-mini";
const DEFAULT_API_VERSION = "2025-01-01-preview";

const SCHEDULE_OPTIONS = [
  { hours: 24, label: "Once a day" },
  { hours: 12, label: "Every 12 hours" },
  { hours: 6, label: "Every 6 hours" },
  { hours: 3, label: "Every 3 hours" },
  { hours: 1, label: "Every hour" },
];

interface Banner {
  kind: "ok" | "error" | "info";
  text: string;
}

function bannerClass(kind: Banner["kind"]): string {
  return {
    ok: "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400",
    error: "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",
    info: "bg-brand-50 text-brand-700 dark:bg-brand-900/20 dark:text-brand-400",
  }[kind];
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testingAoai, setTestingAoai] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);
  const [test, setTest] = useState<TestConnectionResult | null>(null);
  const [status, setStatus] = useState<StatusResult | null>(null);

  // Microsoft Graph
  const [tenantId, setTenantId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [hasSecret, setHasSecret] = useState(false);
  const [skuIds, setSkuIds] = useState(DEFAULT_SKU);
  const [scheduleHours, setScheduleHours] = useState(24);
  const [groupId, setGroupId] = useState("");
  const [redirectUri, setRedirectUri] = useState("");

  // Azure OpenAI
  const [aoaiEndpoint, setAoaiEndpoint] = useState("");
  const [aoaiDeployment, setAoaiDeployment] = useState("");
  const [aoaiApiVersion, setAoaiApiVersion] = useState("");
  const [aoaiKey, setAoaiKey] = useState("");
  const [hasAoaiKey, setHasAoaiKey] = useState(false);
  const [analysisMode, setAnalysisMode] = useState<"combined" | "split">("combined");
  const [aoaiConfigured, setAoaiConfigured] = useState(false);

  function applyConfig(cfg: AppConfig) {
    setTenantId(cfg.tenant_id ?? "");
    setClientId(cfg.client_id ?? "");
    setHasSecret(cfg.has_client_secret);
    setSkuIds((cfg.copilot_sku_ids ?? []).join(", ") || DEFAULT_SKU);
    setScheduleHours(cfg.schedule_interval_hours ?? 24);
    setGroupId(cfg.report_access_group_id ?? "");
    setAoaiEndpoint(cfg.aoai_endpoint ?? "");
    setAoaiDeployment(cfg.aoai_deployment ?? "");
    setAoaiApiVersion(cfg.aoai_api_version ?? "");
    setHasAoaiKey(cfg.has_aoai_key);
    setAnalysisMode(cfg.analysis_mode ?? "combined");
    setAoaiConfigured(cfg.aoai_configured);
  }

  async function refreshStatus() {
    try {
      setStatus(await api<StatusResult>("/admin/status"));
    } catch {
      /* ignore transient status errors */
    }
  }

  useEffect(() => {
    (async () => {
      try {
        applyConfig(await api<AppConfig>("/admin/config"));
        await refreshStatus();
        try {
          const auth = await api<{ redirect_uri: string }>("/auth/config");
          setRedirectUri(auth.redirect_uri);
        } catch {
          /* non-fatal: the sign-in card just won't show a URI to copy */
        }
      } catch (err) {
        setBanner({
          kind: "error",
          text: err instanceof ApiError ? err.message : "Failed to load settings",
        });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setBanner(null);
    try {
      const payload: Record<string, unknown> = {
        tenant_id: tenantId,
        client_id: clientId,
        copilot_sku_ids: skuIds.split(",").map((s) => s.trim()).filter(Boolean),
        schedule_interval_hours: scheduleHours,
        report_access_group_id: groupId,
        aoai_endpoint: aoaiEndpoint,
        aoai_deployment: aoaiDeployment,
        aoai_api_version: aoaiApiVersion,
        analysis_mode: analysisMode,
      };
      if (clientSecret) payload.client_secret = clientSecret;
      if (aoaiKey) payload.aoai_key = aoaiKey;
      const cfg = await api<AppConfig>("/admin/config", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      applyConfig(cfg);
      setClientSecret("");
      setAoaiKey("");
      setBanner({ kind: "ok", text: "Settings saved." });
      await refreshStatus();
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Save failed",
      });
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    setTesting(true);
    setTest(null);
    setBanner(null);
    try {
      const result = await api<TestConnectionResult>("/admin/test-connection", {
        method: "POST",
      });
      setTest(result);
      setBanner(
        result.ok
          ? { kind: "ok", text: "Connection successful." }
          : { kind: "error", text: result.detail ?? "Connection failed." },
      );
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Test failed",
      });
    } finally {
      setTesting(false);
    }
  }

  async function onTestAoai() {
    setTestingAoai(true);
    setBanner(null);
    try {
      const result = await api<TestAoaiResult>("/admin/test-aoai", { method: "POST" });
      setBanner(
        result.ok
          ? { kind: "ok", text: result.detail ?? "Azure OpenAI reachable." }
          : { kind: "error", text: result.detail ?? "Azure OpenAI test failed." },
      );
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Azure OpenAI test failed",
      });
    } finally {
      setTestingAoai(false);
    }
  }

  async function onRunIngest() {
    setIngesting(true);
    setBanner(null);
    try {
      const res = await api<IngestRunResult>("/admin/ingest/run", { method: "POST" });
      setBanner({ kind: "info", text: res.detail });
      pollStatus();
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Ingest failed to start",
      });
    } finally {
      setIngesting(false);
    }
  }

  async function onRunAnalysis() {
    setAnalysing(true);
    setBanner(null);
    try {
      const res = await api<IngestRunResult>("/admin/analysis/run", { method: "POST" });
      setBanner({ kind: "info", text: res.detail });
      pollStatus();
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Analysis failed to start",
      });
    } finally {
      setAnalysing(false);
    }
  }

  function pollStatus() {
    let ticks = 0;
    const timer = setInterval(async () => {
      ticks += 1;
      await refreshStatus();
      if (ticks >= 20) clearInterval(timer);
    }, 3000);
  }

  if (loading) return <div className="text-slate-500">Loading settings…</div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Connect Microsoft Graph and Azure OpenAI. Secrets are stored encrypted and
          never shown again.
        </p>
      </div>

      {banner && (
        <div className={`rounded-lg px-4 py-3 text-sm ${bannerClass(banner.kind)}`}>
          {banner.text}
        </div>
      )}

      <DemoDataCard />

      <SetupWizard defaultOpen={!status?.configured} />

      <form onSubmit={onSave} className="space-y-8">
        <div className="grid gap-8 lg:grid-cols-3">
          <div className="card space-y-5 p-6 lg:col-span-2">
            <h2 className="text-lg font-semibold">Microsoft Graph</h2>

            <Field label="Tenant ID">
              <input
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
                className="input"
              />
            </Field>

            <Field label="Client ID (application ID)">
              <input
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
                className="input"
              />
            </Field>

            <Field
              label="Client secret"
              hint={
                hasSecret
                  ? "A secret is stored. Leave blank to keep it, or enter a new value to replace."
                  : "Enter the client secret value from your app registration."
              }
            >
              <input
                type="password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder={hasSecret ? "•••••••• (unchanged)" : "Enter secret value"}
                className="input"
              />
            </Field>

            <Field
              label="Copilot SKU IDs"
              hint="Comma-separated. Defaults to the Microsoft 365 Copilot SKU."
            >
              <input value={skuIds} onChange={(e) => setSkuIds(e.target.value)} className="input" />
            </Field>

            <Field
              label="Refresh frequency"
              hint="How often the report pulls new usage. After the first pull it stays up to date automatically."
            >
              <select
                value={scheduleHours}
                onChange={(e) => setScheduleHours(Number(e.target.value))}
                className="input w-full sm:w-64"
              >
                {SCHEDULE_OPTIONS.map((o) => (
                  <option key={o.hours} value={o.hours}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>

            <div className="border-t border-slate-200 pt-5 dark:border-slate-700">
              <h2 className="text-lg font-semibold">Sign in with Microsoft (optional)</h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Lets colleagues sign in with their work account as read-only viewers. It
                reuses the app registration above, so there is nothing extra to create —
                you only need to register the redirect URI below. Administration stays
                behind the admin password.
              </p>
            </div>

            <Field label="Redirect URI — add this to your app registration under Authentication → Web">
              <input
                value={redirectUri}
                readOnly
                onFocus={(e) => e.currentTarget.select()}
                className="input font-mono text-xs"
              />
            </Field>

            <Field
              label="Report access group ID"
              hint="Optional Entra security group whose members may view the report via single sign-on. Leave blank to allow any signed-in user."
            >
              <input value={groupId} onChange={(e) => setGroupId(e.target.value)} className="input" />
            </Field>

            <div className="flex flex-wrap gap-3 pt-2">
              <button type="button" onClick={onTest} disabled={testing} className="btn-secondary">
                {testing ? "Testing…" : "Test connection"}
              </button>
              <button
                type="button"
                onClick={onRunIngest}
                disabled={ingesting}
                className="rounded-lg border border-brand-300 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 dark:border-brand-700 dark:bg-brand-900/20 dark:text-brand-400"
              >
                {ingesting ? "Starting…" : "Run now"}
              </button>
            </div>
          </div>

          <div className="space-y-6">
            {test && (
              <div className="card p-6">
                <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
                  Connection test
                </h3>
                <ul className="space-y-2 text-sm">
                  <CheckRow ok={test.token_acquired} label="Token acquired" />
                  <CheckRow ok={test.subscribed_skus} label="Read subscribed SKUs" />
                  <CheckRow ok={test.directory_read} label="Directory read" />
                </ul>
                {test.copilot_licensed_users != null && (
                  <div className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                    Copilot-licensed users:{" "}
                    <span className="font-semibold">{test.copilot_licensed_users}</span>
                  </div>
                )}
                {test.detail && (
                  <div className="mt-3 rounded bg-slate-50 p-2 text-xs text-slate-500 dark:bg-slate-900">
                    {test.detail}
                  </div>
                )}
              </div>
            )}

            <div className="card p-6">
              <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
                Data status
              </h3>
              <dl className="space-y-2 text-sm">
                <StatRow label="Configured" value={status?.configured ? "Yes" : "No"} />
                <StatRow label="Analysis engine" value={aoaiConfigured ? "Ready" : "Not set"} />
                <StatRow label="Prompts" value={status?.prompts ?? 0} />
                <StatRow label="Conversations" value={status?.conversations ?? 0} />
                <StatRow label="Licensed users" value={status?.licensed_users ?? 0} />
                <StatRow label="Directory users" value={status?.entra_users ?? 0} />
              </dl>
              {status?.last_run && (
                <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500 dark:border-slate-700">
                  Last run: <span className="font-medium">{status.last_run.job_name}</span>{" "}
                  — {status.last_run.status}
                </div>
              )}
            </div>

            <div className="card p-6">
              <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
                Historical backfill
              </h3>
              <p className="mb-4 text-xs text-slate-400 dark:text-slate-500">
                Load older history in one intelligent, resumable pass.
              </p>
              <Link
                to="/backfill"
                className="inline-flex items-center gap-1 rounded-lg border border-brand-300 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-100 dark:border-brand-700 dark:bg-brand-900/20 dark:text-brand-400"
              >
                Open historical backfill →
              </Link>
            </div>
          </div>
        </div>

        {/* Azure OpenAI analysis engine */}
        <div className="card space-y-5 p-6">
          <div>
            <h2 className="text-lg font-semibold">Azure OpenAI (analysis engine)</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              The deployment used to score prompt and conversation quality. Required
              before analysis can run.
            </p>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <Field label="Endpoint" hint="e.g. https://my-resource.openai.azure.com">
              <input
                value={aoaiEndpoint}
                onChange={(e) => setAoaiEndpoint(e.target.value)}
                placeholder="https://my-resource.openai.azure.com"
                className="input"
              />
            </Field>

            <Field label="Deployment">
              <input
                value={aoaiDeployment}
                onChange={(e) => setAoaiDeployment(e.target.value)}
                placeholder={DEFAULT_DEPLOYMENT}
                className="input"
              />
            </Field>

            <Field label="API version">
              <input
                value={aoaiApiVersion}
                onChange={(e) => setAoaiApiVersion(e.target.value)}
                placeholder={DEFAULT_API_VERSION}
                className="input"
              />
            </Field>

            <Field
              label="API key"
              hint={
                hasAoaiKey
                  ? "A key is stored. Leave blank to keep it, or enter a new value to replace."
                  : "Enter the Azure OpenAI key."
              }
            >
              <input
                type="password"
                value={aoaiKey}
                onChange={(e) => setAoaiKey(e.target.value)}
                placeholder={hasAoaiKey ? "•••••••• (unchanged)" : "Enter API key"}
                className="input"
              />
            </Field>

            <Field
              label="Analysis mode"
              hint="How sensitivity scoring is performed."
            >
              <select
                value={analysisMode}
                onChange={(e) => setAnalysisMode(e.target.value as "combined" | "split")}
                className="input"
              >
                <option value="combined">One call per conversation (recommended)</option>
                <option value="split">Separate sensitivity call per prompt</option>
              </select>
            </Field>
          </div>

          <div className="flex flex-wrap gap-3 pt-2">
            <button type="submit" disabled={saving} className="btn-primary">
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={onTestAoai}
              disabled={testingAoai}
              className="btn-secondary"
            >
              {testingAoai ? "Testing…" : "Test Azure OpenAI"}
            </button>
            <button
              type="button"
              onClick={onRunAnalysis}
              disabled={analysing}
              className="rounded-lg border border-brand-300 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 dark:border-brand-700 dark:bg-brand-900/20 dark:text-brand-400"
            >
              {analysing ? "Starting…" : "Run analysis now"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{hint}</p>}
    </div>
  );
}

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className={ok ? "text-green-600" : "text-slate-300"}>{ok ? "✓" : "○"}</span>
      <span className="text-slate-600 dark:text-slate-300">{label}</span>
    </li>
  );
}

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  );
}
