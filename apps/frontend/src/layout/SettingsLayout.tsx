import { Outlet } from "react-router-dom";

/**
 * Settings route group: rail section only.
 * Content width/padding comes from each page's <PageShell> — do not nest another max-w here.
 */
export function SettingsLayout() {
  return <Outlet />;
}
