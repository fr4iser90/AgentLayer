import { Outlet } from "react-router-dom";
import { OperatorSettingsProvider } from "../features/admin/operatorSettings/OperatorSettingsProvider";
import { OperatorSettingsStickySave } from "../features/admin/operatorSettings/OperatorSettingsStickySave";

/**
 * Provider scope for the interface settings.
 *
 * Its own sidebar of nine links is gone — that was a third nav container nested
 * inside the admin one. The pages are leaves of the admin rail now
 * (`INTERFACES_SECTIONS` in `navModel.ts`), spliced in while the path is inside
 * the area. What remains is the shared operator-settings state and the sticky
 * save bar that reads it.
 */
export function InterfacesLayout() {
  return (
    <OperatorSettingsProvider>
      <div className="relative">
        <Outlet />
        <OperatorSettingsStickySave />
      </div>
    </OperatorSettingsProvider>
  );
}