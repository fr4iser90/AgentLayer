import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { SettingsLayout } from "./layout/SettingsLayout";
import { AuthProvider } from "./auth/AuthContext";
import { FriendsSettings } from "./pages/settings/FriendsSettings";
import { RequireAdmin } from "./auth/RequireAdmin";
import { RequireSession } from "./auth/RequireSession";
import { AppLayout } from "./layout/AppLayout";
import { AdminLayout } from "./layout/AdminLayout";
import { AdminDashboard } from "./pages/admin/AdminDashboard";
import { InterfacesLayout } from "./layout/InterfacesLayout";
import { AdminInterfacesOverviewPage } from "./pages/admin/interfaces/AdminInterfacesOverviewPage";
import { AdminInterfacesBridgesPage } from "./pages/admin/interfaces/AdminInterfacesBridgesPage";
import { AdminInterfacesLlmPage } from "./pages/admin/interfaces/AdminInterfacesLlmPage";
import { AdminInterfacesMemoryPage } from "./pages/admin/interfaces/AdminInterfacesMemoryPage";
import { AdminInterfacesAutomationPage } from "./pages/admin/interfaces/AdminInterfacesAutomationPage";
import { AdminInterfacesPlatformPage } from "./pages/admin/interfaces/AdminInterfacesPlatformPage";
import { AdminTools } from "./pages/admin/AdminTools";
import { AdminAgents } from "./pages/admin/AdminAgents";
import { AdminUsers } from "./pages/admin/AdminUsers";
import { AdminScheduledJobs } from "./pages/admin/AdminScheduledJobs";
import { AdminSchedules } from "./pages/admin/AdminSchedules";
import { AdminAgentTraces } from "./pages/admin/AdminAgentTraces";
import { ChatPage } from "./pages/ChatPage";
import { DocsPage } from "./pages/DocsPage";
import { HomePage } from "./pages/HomePage";
import { AgentSettings } from "./pages/settings/AgentSettings";
import { DelegateSettings } from "./pages/settings/DelegateSettings";
import { NotificationsSettings } from "./pages/settings/NotificationsSettings";
import { ConnectionsSettings } from "./pages/settings/ConnectionsSettings";
import { ProfileSettings } from "./pages/settings/ProfileSettings";
import { ToolsSettings } from "./pages/settings/ToolsSettings";
import SharesSettings from "./pages/settings/SharesSettings";
import { StudioPage } from "./pages/StudioPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DashboardPublicSharePage } from "./pages/DashboardPublicSharePage";
import { LoginPage } from "./pages/LoginPage";
import { SetupWizardPage } from "./pages/SetupWizardPage";
import { MySchedulesPage } from "./pages/MySchedulesPage";
import { TasksPage } from "./pages/TasksPage";

function LegacyCodingAgentRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/chat${search}`} replace />;
}

export function App() {
  return (
    <BrowserRouter basename="/app">
      <AuthProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="login" element={<LoginPage />} />
            <Route path="setup" element={<SetupWizardPage />} />
            <Route path="dashboard/shared" element={<DashboardPublicSharePage />} />
            <Route element={<RequireSession />}>
              <Route path="/" element={<HomePage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="coding-agent" element={<LegacyCodingAgentRedirect />} />
              <Route path="studio" element={<StudioPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="schedules" element={<MySchedulesPage />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="docs" element={<DocsPage />} />
              <Route path="settings" element={<SettingsLayout />}>
                <Route index element={<Navigate to="/settings/profile" replace />} />
                <Route path="friends" element={<FriendsSettings />} />
                <Route path="profile" element={<ProfileSettings />} />
                <Route path="connections" element={<ConnectionsSettings />} />
                <Route path="notifications" element={<NotificationsSettings />} />
                <Route path="tools" element={<ToolsSettings />} />
                <Route path="agent" element={<AgentSettings />} />
                <Route path="delegate" element={<DelegateSettings />} />
                <Route path="shares" element={<SharesSettings />} />
                <Route path="experimental" element={<Navigate to="/settings/profile" replace />} />
              </Route>
              <Route path="admin" element={<RequireAdmin />}>
                <Route element={<AdminLayout />}>
                  <Route index element={<AdminDashboard />} />
                  <Route path="interfaces" element={<InterfacesLayout />}>
                    <Route index element={<AdminInterfacesOverviewPage />} />
                    <Route path="bridges" element={<AdminInterfacesBridgesPage />} />
                    <Route path="llm" element={<AdminInterfacesLlmPage />} />
                    <Route path="memory" element={<AdminInterfacesMemoryPage />} />
                    <Route path="automation" element={<AdminInterfacesAutomationPage />} />
                    <Route path="platform" element={<AdminInterfacesPlatformPage />} />
                  </Route>
                  <Route path="discord" element={<Navigate to="../interfaces/bridges" replace />} />
                  <Route path="telegram" element={<Navigate to="../interfaces/bridges" replace />} />
                  <Route path="tools" element={<AdminTools />} />
                  <Route path="agents" element={<AdminAgents />} />
                  <Route path="users" element={<AdminUsers />} />
                  <Route path="scheduled-jobs" element={<AdminScheduledJobs />} />
                  <Route path="schedules" element={<AdminSchedules />} />
                  <Route path="run-traces" element={<AdminAgentTraces />} />
                  <Route path="workflows" element={<Navigate to="../scheduled-jobs" replace />} />
                </Route>
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
