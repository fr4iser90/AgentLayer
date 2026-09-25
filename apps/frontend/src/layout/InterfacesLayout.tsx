import { Outlet } from "react-router-dom";
import { OperatorSettingsProvider } from "../features/admin/operatorSettings/OperatorSettingsProvider";
import { OperatorSettingsStickySave } from "../features/admin/operatorSettings/OperatorSettingsStickySave";

/**
 * Provider scope for the interface settings.
 *
 * Its own sidebar of nine links is gone — that was a third nav container nested
 * inside the admin one. The pages are a fold under the admin rail's door now
 * (`children` of `/admin/interfaces` in `navModel.ts`), so the rail keeps its
 * shape while the path moves around inside the area and the door above them
 * stands for the lot. What remains here is the shared operator-settings state
 * and the sticky save bar that reads it.
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