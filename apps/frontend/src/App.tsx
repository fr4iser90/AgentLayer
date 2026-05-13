import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { SettingsLayout } from "./layout/SettingsLayout";
import { AuthProvider } from "./auth/AuthContext";
import { FriendsSettings } from "./pages/settings/FriendsSettings";
import { RequireAdmin } from "./auth/RequireAdmin";
import { RequireSession } from "./auth/RequireSession";
import { AppLayout } from "./layout/AppLayout";
import { AdminLayout } from "./layout/AdminLayout";
import { AdminDashboard } from "./pages/admin/AdminDashboard";
import { AdminInterfaces } from "./pages/admin/AdminInterfaces";
import { AdminTools } from "./pages/admin/AdminTools";
import { AdminUsers } from "./pages/admin/AdminUsers";
import { AdminScheduledJobs } from "./pages/admin/AdminScheduledJobs";
import { AdminSchedules } from "./pages/admin/AdminSchedules";
import { ChatPage } from "./pages/ChatPage";
import { DocsPage } from "./pages/DocsPage";
import { HomePage } from "./pages/HomePage";
import { AgentSettings } from "./pages/settings/AgentSettings";
import { ConnectionsSettings } from "./pages/settings/ConnectionsSettings";
import { ProfileSettings } from "./pages/settings/ProfileSettings";
import { ToolsSettings } from "./pages/settings/ToolsSettings";
import SharesSettings from "./pages/settings/SharesSettings";
import { StudioPage } from "./pages/StudioPage";
import { IdeIntegrationPlaceholder } from "./pages/IdeIntegrationPlaceholder";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { MySchedulesPage } from "./pages/MySchedulesPage";

export function App() {
  return (
    <BrowserRouter basename="/app">
      <AuthProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="login" element={<LoginPage />} />
            <Route element={<RequireSession />}>
              <Route path="/" element={<HomePage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="ide-agent" element={<IdeIntegrationPlaceholder variant="app" />} />
              <Route path="studio" element={<StudioPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="schedules" element={<MySchedulesPage />} />
              <Route path="docs" element={<DocsPage />} />
              <Route path="settings" element={<SettingsLayout />}>
                <Route index element={<Navigate to="/settings/profile" replace />} />
                <Route path="friends" element={<FriendsSettings />} />
                <Route path="profile" element={<ProfileSettings />} />
                <Route path="connections" element={<ConnectionsSettings />} />
                <Route path="tools" element={<ToolsSettings />} />
                <Route path="agent" element={<AgentSettings />} />
                <Route path="shares" element={<SharesSettings />} />
                <Route path="experimental" element={<Navigate to="/admin/ide-integration" replace />} />
              </Route>
              <Route path="admin" element={<RequireAdmin />}>
                <Route element={<AdminLayout />}>
                  <Route index element={<AdminDashboard />} />
                  <Route path="interfaces" element={<AdminInterfaces />} />
                  <Route path="discord" element={<Navigate to="../interfaces" replace />} />
                  <Route path="telegram" element={<Navigate to="../interfaces" replace />} />
                  <Route path="tools" element={<AdminTools />} />
                  <Route path="users" element={<AdminUsers />} />
                  <Route path="scheduled-jobs" element={<AdminScheduledJobs />} />
                  <Route path="schedules" element={<AdminSchedules />} />
                  <Route path="ide-agent" element={<Navigate to="/admin/ide-integration" replace />} />
                  <Route
                    path="ide-integration"
                    element={<IdeIntegrationPlaceholder variant="admin" />}
                  />
                  <Route path="ide-agents/*" element={<Navigate to="/admin/ide-integration" replace />} />
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
