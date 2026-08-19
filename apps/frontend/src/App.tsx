import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { SettingsLayout } from "./layout/SettingsLayout";
import { AuthProvider } from "./auth/AuthContext";
import { FriendsSettings } from "./pages/settings/FriendsSettings";
import { RequireSiteAdmin } from "./auth/RequireSiteAdmin";
import { RequireOrgAdmin } from "./auth/RequireOrgAdmin";
import { OrgSetupPage } from "./pages/org/OrgSetupPage";
import { RequireSession } from "./auth/RequireSession";
import { AppLayout } from "./layout/AppLayout";
import { AdminLayout } from "./layout/AdminLayout";
import { AdminDashboard } from "./pages/admin/AdminDashboard";
import { InterfacesLayout } from "./layout/InterfacesLayout";
import { AdminInterfacesOverviewPage } from "./pages/admin/interfaces/AdminInterfacesOverviewPage";
import { AdminInterfacesBridgesPage } from "./pages/admin/interfaces/AdminInterfacesBridgesPage";
import { AdminInterfacesProvidersPage } from "./pages/admin/interfaces/AdminInterfacesProvidersPage";
import { AdminInterfacesModelPoliciesPage } from "./pages/admin/interfaces/AdminInterfacesModelPoliciesPage";
import { AdminInterfacesRoutingPage } from "./pages/admin/interfaces/AdminInterfacesRoutingPage";
import { AdminInterfacesMemoryPage } from "./pages/admin/interfaces/AdminInterfacesMemoryPage";
import { AdminInterfacesVoicePage } from "./pages/admin/interfaces/AdminInterfacesVoicePage";
import { AdminInterfacesAutomationPage } from "./pages/admin/interfaces/AdminInterfacesAutomationPage";
import { AdminInterfacesPlatformPage } from "./pages/admin/interfaces/AdminInterfacesPlatformPage";
import { AdminTools } from "./pages/admin/AdminTools";
import { AdminAgents } from "./pages/admin/AdminAgents";
import { AdminUsers } from "./pages/admin/AdminUsers";
import { AdminScheduledJobs } from "./pages/admin/AdminScheduledJobs";
import { AdminSchedules } from "./pages/admin/AdminSchedules";
import { AdminAgentTraces } from "./pages/admin/AdminAgentTraces";
import { AdminBenchmarks } from "./pages/admin/AdminBenchmarks";
import { AdminAgentConfig } from "./pages/admin/AdminAgentConfig";
import { OrgAdminLayout } from "./layout/OrgAdminLayout";
import { OrgKnowledgePage } from "./pages/org/OrgKnowledgePage";
import { OrgTeamPage } from "./pages/org/OrgTeamPage";
import { ChatPage } from "./pages/ChatPage";
import { DocsPage } from "./pages/DocsPage";
import { HomePage, RestrictedNavRedirect } from "./pages/HomePage";
import { AgentSettings } from "./pages/settings/AgentSettings";
import { DelegateSettings } from "./pages/settings/DelegateSettings";
import { NotificationsSettings } from "./pages/settings/NotificationsSettings";
import { ConnectionsSettings } from "./pages/settings/ConnectionsSettings";
import { ProfileSettings } from "./pages/settings/ProfileSettings";
import { VoiceSettings } from "./pages/settings/VoiceSettings";
import { ToolsSettings } from "./pages/settings/ToolsSettings";
import SharesSettings from "./pages/settings/SharesSettings";
import { StudioPage } from "./pages/StudioPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DashboardPublicSharePage } from "./pages/DashboardPublicSharePage";
import { LegalPage } from "./pages/LegalPage";
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
            <Route path="legal/:slug" element={<LegalPage />} />
            <Route path="dashboard/shared" element={<DashboardPublicSharePage />} />
            <Route element={<RequireSession />}>
              <Route path="/" element={<HomePage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="coding-agent" element={<LegacyCodingAgentRedirect />} />
              <Route
                path="studio"
                element={
                  <RestrictedNavRedirect nav="studio">
                    <StudioPage />
                  </RestrictedNavRedirect>
                }
              />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route
                path="schedules"
                element={
                  <RestrictedNavRedirect nav="schedules">
                    <MySchedulesPage />
                  </RestrictedNavRedirect>
                }
              />
              <Route
                path="tasks"
                element={
                  <RestrictedNavRedirect nav="tasks">
                    <TasksPage />
                  </RestrictedNavRedirect>
                }
              />
              <Route path="docs" element={<DocsPage />} />
              <Route path="settings" element={<SettingsLayout />}>
                <Route index element={<Navigate to="/settings/profile" replace />} />
                <Route path="friends" element={<FriendsSettings />} />
                <Route path="profile" element={<ProfileSettings />} />
                <Route path="voice" element={<VoiceSettings />} />
                <Route path="connections" element={<ConnectionsSettings />} />
                <Route path="notifications" element={<NotificationsSettings />} />
                <Route path="tools" element={<ToolsSettings />} />
                <Route path="agent" element={<AgentSettings />} />
                <Route path="delegate" element={<DelegateSettings />} />
                <Route
                  path="shares"
                  element={
                    <RestrictedNavRedirect nav="shares">
                      <SharesSettings />
                    </RestrictedNavRedirect>
                  }
                />
                <Route path="experimental" element={<Navigate to="/settings/profile" replace />} />
              </Route>
              <Route path="org" element={<RequireOrgAdmin />}>
                <Route element={<OrgAdminLayout />}>
                  <Route index element={<Navigate to="knowledge" replace />} />
                  <Route path="setup" element={<OrgSetupPage />} />
                  <Route path="knowledge" element={<OrgKnowledgePage />} />
                  <Route path="team" element={<OrgTeamPage />} />
                </Route>
              </Route>
              <Route path="admin" element={<RequireSiteAdmin />}>
                <Route element={<AdminLayout />}>
                  <Route index element={<AdminDashboard />} />
                  <Route path="interfaces" element={<InterfacesLayout />}>
                    <Route index element={<AdminInterfacesOverviewPage />} />
                    <Route path="bridges" element={<AdminInterfacesBridgesPage />} />
                    <Route path="providers" element={<AdminInterfacesProvidersPage />} />
                    <Route path="model-policies" element={<AdminInterfacesModelPoliciesPage />} />
                    <Route path="routing" element={<AdminInterfacesRoutingPage />} />
                    <Route path="llm" element={<Navigate to="../routing" replace />} />
                    <Route path="memory" element={<AdminInterfacesMemoryPage />} />
                    <Route path="voice" element={<AdminInterfacesVoicePage />} />
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
                  <Route path="benchmarks" element={<AdminBenchmarks />} />
                  <Route path="harness" element={<Navigate to="../agent-config" replace />} />
                  <Route path="agent-config" element={<AdminAgentConfig />} />
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
