import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { FiltersProvider } from "./filters/FiltersContext";
import { useSetupStatus } from "./hooks/useSetupStatus";
import AboutPage from "./pages/AboutPage";
import BackfillPage from "./pages/BackfillPage";
import CoachingPage from "./pages/CoachingPage";
import ConversationsPage from "./pages/ConversationsPage";
import ExecutiveSummaryPage from "./pages/ExecutiveSummaryPage";
import LoginPage from "./pages/LoginPage";
import PersonalPage from "./pages/PersonalPage";
import PromptQualityPage from "./pages/PromptQualityPage";
import SettingsPage from "./pages/SettingsPage";
import SetupGuidePage from "./pages/SetupGuidePage";
import UsageBreakdownPage from "./pages/UsageBreakdownPage";

export default function App() {
  const { user, loading } = useAuth();
  const { configured, checked } = useSetupStatus(Boolean(user));

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  // First run: send admins straight to Settings (where the wizard opens itself)
  // until a connection is configured. Non-admins carry on to the dashboards and
  // see the usual empty states.
  const needsSetup = checked && !configured && user.role === "admin";

  // Org pages are gated on the server too; this only keeps the SPA from showing
  // a page that would answer 403. Someone without access is sent to their own
  // view rather than a dead end.
  const org = (element: JSX.Element) =>
    user.can_view_org ? element : <Navigate to="/me" replace />;

  // People with a work-account identity land on their own data; the password
  // admin has no personal view, so they land on the organisation summary.
  const landing = needsSetup ? (
    <Navigate to="/settings" replace />
  ) : user.has_personal_view ? (
    <PersonalPage />
  ) : (
    <ExecutiveSummaryPage />
  );

  return (
    <FiltersProvider>
      <Layout>
        <Routes>
          <Route path="/" element={landing} />
          <Route path="/me" element={<PersonalPage />} />
          <Route path="/summary" element={org(<ExecutiveSummaryPage />)} />
          <Route path="/usage" element={org(<UsageBreakdownPage />)} />
          <Route path="/quality" element={org(<PromptQualityPage />)} />
          <Route path="/conversations" element={org(<ConversationsPage />)} />
          <Route path="/coaching" element={org(<CoachingPage />)} />
          <Route path="/help" element={<SetupGuidePage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route
            path="/settings"
            element={user.role === "admin" ? <SettingsPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/backfill"
            element={user.role === "admin" ? <BackfillPage /> : <Navigate to="/" replace />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </FiltersProvider>
  );
}
