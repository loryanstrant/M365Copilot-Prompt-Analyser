import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { FiltersProvider } from "./filters/FiltersContext";
import AboutPage from "./pages/AboutPage";
import BackfillPage from "./pages/BackfillPage";
import ConversationsPage from "./pages/ConversationsPage";
import ExecutiveSummaryPage from "./pages/ExecutiveSummaryPage";
import LoginPage from "./pages/LoginPage";
import PersonalPage from "./pages/PersonalPage";
import PromptQualityPage from "./pages/PromptQualityPage";
import SettingsPage from "./pages/SettingsPage";
import UsageBreakdownPage from "./pages/UsageBreakdownPage";

export default function App() {
  const { user, loading } = useAuth();

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

  return (
    <FiltersProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<ExecutiveSummaryPage />} />
          <Route path="/usage" element={<UsageBreakdownPage />} />
          <Route path="/quality" element={<PromptQualityPage />} />
          <Route path="/conversations" element={<ConversationsPage />} />
          <Route path="/personal" element={<PersonalPage />} />
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
