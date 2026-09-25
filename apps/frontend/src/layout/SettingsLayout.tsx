import { Outlet } from "react-router-dom";

/**
 * Padding for the settings pages.
 *
 * This used to be a sidebar with nine links mounted inside `AppLayout`'s own
 * nav — the second level the design rule forbids. Its links are a section set of
 * the rail now (`settingsNav` in `navModel.ts`), so what is left here is the
 * inset those pages were laid out against.
 */
export function SettingsLayout() {
  return (
    <div className="px-broad py-deep">
      <Outlet />
    </div>
  );
}