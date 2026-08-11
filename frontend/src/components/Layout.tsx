import { type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";
import SvgDefs from "./SvgDefs";

function navClass({ isActive }: { isActive: boolean }): string {
  return [
    "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-brand-600 text-white"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white",
  ].join(" ");
}

function BrandMark() {
  return (
    <img
      src="/copilot-logo.png"
      alt="Microsoft 365 Copilot"
      className="h-9 w-9 shrink-0 rounded-lg object-contain"
    />
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();

  return (
    <div className="flex h-full">
      <SvgDefs />
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
        <div className="flex items-center gap-3 px-5 py-5">
          <BrandMark />
          <div>
            <div className="text-sm font-semibold text-brand-600 dark:text-brand-500">
              M365 Copilot
            </div>
            <div className="text-lg font-bold leading-tight text-slate-900 dark:text-white">
              Prompt Analyser
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          <NavLink to="/" className={navClass} end>
            Executive summary
          </NavLink>
          <NavLink to="/usage" className={navClass}>
            Usage breakdown
          </NavLink>
          <NavLink to="/quality" className={navClass}>
            Prompt quality
          </NavLink>
          <NavLink to="/conversations" className={navClass}>
            Conversations
          </NavLink>
          <NavLink to="/personal" className={navClass}>
            Personal coaching
          </NavLink>
          {user?.role === "admin" && (
            <NavLink to="/settings" className={navClass}>
              Settings
            </NavLink>
          )}
          {user?.role === "admin" && (
            <NavLink to="/backfill" className={navClass}>
              Backfill
            </NavLink>
          )}
          <NavLink to="/about" className={navClass}>
            About
          </NavLink>
        </nav>
        <div className="space-y-3 border-t border-slate-200 px-4 py-4 text-sm dark:border-slate-700">
          <button
            onClick={toggle}
            className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            <span>{theme === "dark" ? "Dark" : "Light"} mode</span>
            <span aria-hidden>{theme === "dark" ? "🌙" : "☀️"}</span>
          </button>
          <div>
            <div className="font-medium text-slate-800 dark:text-slate-100">
              {user?.username}
            </div>
            <div className="mb-3 text-xs uppercase tracking-wide text-slate-400">
              {user?.role}
            </div>
            <button
              onClick={logout}
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <header className="flex items-center justify-end border-b border-slate-200 bg-white/70 px-8 py-3 backdrop-blur dark:border-slate-700 dark:bg-slate-800/70">
          <img
            src="/copilot-logo.png"
            alt="Microsoft 365 Copilot"
            className="h-8 w-8 object-contain"
          />
        </header>
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
