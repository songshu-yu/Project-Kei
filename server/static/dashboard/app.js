import { createCoreStatusController } from './core-status.js?v=pk100-20260812-voicebackground1';
import { setupGptSovitsEngineControl } from './gpt-sovits-control.js?v=pk100-20260808-controls1';
import { createModuleLoader } from './module-loader.js?v=pk100-20260808-controls1';
import { setupModuleManagement } from './module-management.js?v=pk100-20260812-servicestate2';
import { notify } from './notifications.js?v=pk100-20260808-controls1';
import { setupDashboardPanels } from './panels.js?v=pk100-20260808-controls1';
import { createModuleRegistry } from './registry.js?v=pk100-20260808-controls1';
import { setupRestartControl } from './restart-control.js?v=pk100-20260808-controls1';
import { request } from './request.js?v=pk100-20260808-controls1';

export async function bootstrapDashboard({
  refreshIntervalMs = 15000,
  documentRoot = document,
} = {}) {
  const registry = createModuleRegistry();
  const loader = createModuleLoader({
    registry,
    notify,
    documentRoot,
    onPanelAdded: () => setupDashboardPanels(documentRoot),
  });
  const coreStatus = createCoreStatusController({ request, notify, documentRoot });
  const restartControl = setupRestartControl({ request, notify, documentRoot });
  const gptSovitsControl = setupGptSovitsEngineControl({ request, notify, documentRoot });

  setupDashboardPanels(documentRoot);
  const moduleManagement = setupModuleManagement({
    request,
    notify,
    documentRoot,
    reconcileInstalled: (catalog) => loader.reconcile(catalog),
    beforeLifecycleAction: (moduleId, action) => loader.beforeLifecycleAction(moduleId, action),
  });

  const refresh = async () => {
    await Promise.allSettled([
      coreStatus.refresh(),
      moduleManagement.refreshInstalled(),
      moduleManagement.readOfficialCache(),
      restartControl.refreshStatus(),
      gptSovitsControl.refreshStatus(),
    ]);
  };

  const refreshButton = documentRoot.querySelector('#refresh');
  refreshButton?.addEventListener('click', refresh);
  await refresh();
  const timer = window.setInterval(() => void coreStatus.refresh(), refreshIntervalMs);

  return Object.freeze({
    refresh,
    destroy: async () => {
      window.clearInterval(timer);
      refreshButton?.removeEventListener('click', refresh);
      moduleManagement.destroy();
      restartControl.destroy();
      gptSovitsControl.destroy();
      await loader.destroy();
    },
  });
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  void bootstrapDashboard();
}
