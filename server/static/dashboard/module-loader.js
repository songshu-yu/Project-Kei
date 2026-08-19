import { createScopedRequest, resolveSameOriginUrl } from './request.js?v=pk100-20260808-localzip2';

const MODULE_LOAD_TIMEOUT_MS = 10000;

const DASHBOARD_GROUPS = Object.freeze({
  intelligence: Object.freeze({
    panelId: 'module-group-intelligence',
    label: '每日情报来源与采集',
    summary: '来源配置、X/Nitter、B 站、GitHub、论文与 RSS 保持独立模块，在这里统一查看。',
    primary: 'intel_sources',
    members: Object.freeze({
      intel_sources: '来源配置',
      x_monitor: 'X / Nitter',
      bilibili: 'B 站',
      github_intel: 'GitHub',
      papers: '论文',
      rss_intel: 'RSS',
    }),
  }),
  voice: Object.freeze({
    panelId: 'module-group-voice',
    label: '语音与 Voice Pack',
    summary: '语音编排、Voice Pack 管理和可信发布保持独立模块，在这里统一查看。',
    primary: 'voice',
    members: Object.freeze({
      voice: '语音编排',
      voice_pack_registry: 'Voice Pack 管理',
      voice_pack_distribution: '下载与安装',
    }),
  }),
});

const GROUP_BY_MODULE = new Map(
  Object.entries(DASHBOARD_GROUPS).flatMap(([groupId, group]) => (
    Object.keys(group.members).map((moduleId) => [moduleId, {groupId, group}])
  )),
);

export function shouldLoadModule(moduleInfo) {
  const configurationSidecar = moduleInfo?.type === 'sidecar'
    && moduleInfo?.install_status === 'needs_configuration'
    && moduleInfo?.enabled !== true;
  return (moduleInfo?.enabled === true || configurationSidecar)
    && typeof moduleInfo.dashboard_entrypoint === 'string'
    && moduleInfo.dashboard_entrypoint.trim() !== '';
}

export function isTrustedModuleEntrypoint(moduleInfo, locationLike = window.location) {
  if (!shouldLoadModule(moduleInfo) || typeof moduleInfo.key !== 'string') return false;
  try {
    const entrypoint = new URL(moduleInfo.dashboard_entrypoint, locationLike.href);
    const prefix = `/api/v1/modules/${encodeURIComponent(moduleInfo.key)}/assets/`;
    return ['http:', 'https:'].includes(entrypoint.protocol)
      && entrypoint.origin === locationLike.origin
      && entrypoint.pathname.startsWith(prefix);
  } catch (_error) {
    return false;
  }
}

function setLoadState(documentRoot, moduleId, text, type = '') {
  const state = documentRoot.querySelector(`[data-module-load-state="${CSS.escape(moduleId)}"]`);
  if (!state) return;
  state.textContent = text;
  state.className = `module-load-state ${type}`.trim();
}

function selectGroupPanel(section, moduleId, {userInitiated = false} = {}) {
  const buttons = section.querySelectorAll('[data-module-group-tab]');
  const panels = section.querySelectorAll('[data-module-group-panel]');
  if (![...panels].some((panel) => panel.dataset.dashboardModule === moduleId)) return;
  for (const button of buttons) {
    const active = button.dataset.moduleGroupTab === moduleId;
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  }
  for (const panel of panels) {
    panel.hidden = panel.dataset.dashboardModule !== moduleId;
  }
  section.dataset.activeGroupModule = moduleId;
  if (userInitiated) section.dataset.groupSelectionTouched = 'true';
}

function projectOwnedConfiguration(documentRoot) {
  const group = documentRoot.querySelector('[data-dashboard-group="intelligence"]');
  if (!group) return;
  const sections = group.querySelectorAll('[data-module-config-target]');
  for (const section of sections) {
    const target = section.dataset.moduleConfigTarget;
    const targetRoot = group.querySelector(
      `[data-dashboard-module="${CSS.escape(target)}"] > .module-mount-content`,
    );
    if (!targetRoot || section.parentElement === targetRoot) continue;
    targetRoot.prepend(section);
  }
}

function ensureGroupSection(documentRoot, mounts, groupId, group) {
  let section = mounts.querySelector(`[data-dashboard-group="${CSS.escape(groupId)}"]`);
  if (section) return section;
  section = documentRoot.createElement('section');
  const heading = documentRoot.createElement('h2');
  const hint = documentRoot.createElement('p');
  const body = documentRoot.createElement('div');
  const tabs = documentRoot.createElement('div');
  const panels = documentRoot.createElement('div');
  section.className = 'section module-mount module-group';
  section.dataset.dashboardGroup = groupId;
  section.dataset.panelId = group.panelId;
  section.dataset.panelSummary = group.summary;
  heading.textContent = group.label;
  hint.className = 'hint';
  hint.textContent = group.summary;
  body.className = 'module-group-body';
  tabs.className = 'module-group-tabs';
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', `${group.label}子模块`);
  panels.className = 'module-group-panels';
  body.append(tabs, panels);
  section.append(heading, hint, body);
  mounts.append(section);
  return section;
}

function ensureGroupedModule(documentRoot, mounts, moduleInfo, membership) {
  const {groupId, group} = membership;
  const section = ensureGroupSection(documentRoot, mounts, groupId, group);
  let panel = section.querySelector(
    `[data-dashboard-module="${CSS.escape(moduleInfo.key)}"]`,
  );
  if (panel) return panel;
  const safeId = `${groupId}-${moduleInfo.key}`.replace(/[^a-zA-Z0-9_-]/g, '-');
  const tab = documentRoot.createElement('button');
  const content = documentRoot.createElement('div');
  panel = documentRoot.createElement('article');
  tab.type = 'button';
  tab.id = `module-group-tab-${safeId}`;
  tab.className = 'module-group-tab';
  tab.dataset.moduleGroupTab = moduleInfo.key;
  tab.setAttribute('role', 'tab');
  tab.setAttribute('aria-selected', 'false');
  tab.tabIndex = -1;
  tab.setAttribute('aria-controls', `module-group-panel-${safeId}`);
  tab.textContent = group.members[moduleInfo.key] || moduleInfo.label || moduleInfo.key;
  panel.id = `module-group-panel-${safeId}`;
  panel.className = 'module-group-panel';
  panel.dataset.dashboardModule = moduleInfo.key;
  panel.dataset.moduleGroupPanel = 'true';
  panel.setAttribute('role', 'tabpanel');
  panel.setAttribute('aria-labelledby', tab.id);
  panel.hidden = true;
  content.className = 'module-mount-content';
  panel.append(content);
  section.querySelector('.module-group-tabs').append(tab);
  section.querySelector('.module-group-panels').append(panel);
  tab.addEventListener('click', () => {
    selectGroupPanel(section, moduleInfo.key, {userInitiated: true});
  });
  const preferred = moduleInfo.key === group.primary
    && section.dataset.groupSelectionTouched !== 'true';
  if (!section.dataset.activeGroupModule || preferred) {
    selectGroupPanel(section, moduleInfo.key);
  }
  return panel;
}

function moduleMountRoot(documentRoot, moduleInfo) {
  const mounts = documentRoot.querySelector('#dashboard-module-mounts');
  if (!mounts) return null;
  const membership = GROUP_BY_MODULE.get(moduleInfo.key);
  if (membership) {
    return ensureGroupedModule(documentRoot, mounts, moduleInfo, membership)
      .querySelector('.module-mount-content');
  }
  let section = mounts?.querySelector(`[data-dashboard-module="${CSS.escape(moduleInfo.key)}"]`);
  if (!section && mounts) {
    section = documentRoot.createElement('section');
    section.className = 'section module-mount';
    section.dataset.dashboardModule = moduleInfo.key;
    section.dataset.panelId = `module-${moduleInfo.key}`;
    const heading = documentRoot.createElement('h2');
    const content = documentRoot.createElement('div');
    heading.textContent = moduleInfo.label || moduleInfo.key;
    content.className = 'module-mount-content';
    section.append(heading, content);
    mounts.append(section);
  }
  return section?.querySelector('.module-mount-content') || null;
}

function immutableSnapshot(value) {
  const clone = typeof structuredClone === 'function'
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
  const freeze = (item) => {
    if (!item || typeof item !== 'object' || Object.isFrozen(item)) return item;
    Object.values(item).forEach(freeze);
    return Object.freeze(item);
  };
  return freeze(clone);
}

export function createModuleLoader({
  registry,
  notify,
  onPanelAdded,
  documentRoot = document,
}) {
  const active = new Map();
  const failed = new Set();
  let operationQueue = Promise.resolve();

  function importWithTimeout(url) {
    let timeout;
    return Promise.race([
      import(url),
      new Promise((_, reject) => {
        timeout = window.setTimeout(
          () => reject(new Error('前端入口加载超时')),
          MODULE_LOAD_TIMEOUT_MS,
        );
      }),
    ]).finally(() => window.clearTimeout(timeout));
  }

  async function loadOne(moduleInfo, catalogSnapshot) {
    const root = moduleMountRoot(documentRoot, moduleInfo);
    if (!root) throw new Error('模块挂载容器不存在');
    root.replaceChildren();
    if (!isTrustedModuleEntrypoint(moduleInfo)) {
      throw new Error('前端入口不是该模块的同源受信任资源');
    }
    const entrypoint = resolveSameOriginUrl(moduleInfo.dashboard_entrypoint);
    const lifecycle = await importWithTimeout(entrypoint.href);
    registry.register(moduleInfo.key, lifecycle);
    const context = Object.freeze({
      root,
      module: immutableSnapshot(moduleInfo),
      catalog: catalogSnapshot,
      request: createScopedRequest(moduleInfo),
      notify: (text, type = 'success') => notify(`${moduleInfo.label || moduleInfo.key}：${text}`, type),
    });
    await registry.mount(moduleInfo.key, context);
    const hostSection = root.closest('[data-dashboard-module]');
    if (root.querySelector(':scope > .module-owned-panels')) {
      hostSection?.classList.add('module-panel-host');
    }
    projectOwnedConfiguration(documentRoot);
    active.set(moduleInfo.key, moduleInfo.dashboard_entrypoint);
    failed.delete(moduleInfo.key);
    setLoadState(documentRoot, moduleInfo.key, '前端入口已加载。', 'success-text');
    onPanelAdded?.();
  }

  async function deactivateNow(moduleId) {
    await registry.unregister(moduleId);
    if (moduleId === 'intel_sources') {
      documentRoot.querySelectorAll('[data-config-owner="intel_sources"]').forEach(node => node.remove());
    }
    const section = documentRoot.querySelector(
      `[data-dashboard-module="${CSS.escape(moduleId)}"]`,
    );
    const group = section?.closest?.('[data-dashboard-group]');
    if (group) {
      const wasActive = group.dataset.activeGroupModule === moduleId;
      group.querySelector(`[data-module-group-tab="${CSS.escape(moduleId)}"]`)?.remove();
      section.remove();
      const next = group.querySelector('[data-module-group-panel]');
      if (!next) {
        group.remove();
      } else if (wasActive) {
        selectGroupPanel(group, next.dataset.dashboardModule);
      }
    } else {
      section?.remove();
    }
    active.delete(moduleId);
    failed.delete(moduleId);
  }

  async function reconcileNow(catalog) {
    const modules = Array.isArray(catalog?.modules) ? catalog.modules : [];
    const desiredModules = modules.filter(shouldLoadModule);
    const desired = new Map(desiredModules.map((item) => [item.key, item]));
    const mountedSections = documentRoot.querySelectorAll('[data-dashboard-module]');
    for (const section of mountedSections) {
      const moduleId = section.dataset.dashboardModule;
      const target = desired.get(moduleId);
      const entrypointChanged = target
        && active.has(moduleId)
        && active.get(moduleId) !== target.dashboard_entrypoint;
      if (!target || entrypointChanged) {
        await deactivateNow(moduleId);
      }
    }

    const snapshot = immutableSnapshot(catalog);
    for (const moduleInfo of desiredModules) {
      if (active.has(moduleInfo.key)) {
        setLoadState(documentRoot, moduleInfo.key, '前端入口已加载。', 'success-text');
        continue;
      }
      setLoadState(documentRoot, moduleInfo.key, '正在加载前端入口…');
      try {
        await loadOne(moduleInfo, snapshot);
      } catch (error) {
        failed.add(moduleInfo.key);
        const root = moduleMountRoot(documentRoot, moduleInfo);
        if (root) {
          root.replaceChildren();
          const message = documentRoot.createElement('div');
          message.className = 'module-error';
          message.textContent = `模块加载失败：${String(error?.message || '未知错误').slice(0, 160)}`;
          root.append(message);
        }
        setLoadState(
          documentRoot,
          moduleInfo.key,
          '前端入口加载失败；其他模块不受影响。',
          'error-text',
        );
        onPanelAdded?.();
      }
    }
  }

  function enqueue(operation) {
    const result = operationQueue.then(operation);
    operationQueue = result.catch(() => {});
    return result;
  }

  function reconcile(catalog) {
    return enqueue(() => reconcileNow(catalog));
  }

  function beforeLifecycleAction(moduleId, action) {
    if (!['disable', 'uninstall'].includes(action)) return Promise.resolve();
    return enqueue(() => deactivateNow(moduleId));
  }

  function destroy() {
    return enqueue(async () => {
      await Promise.allSettled([...active.keys()].map((moduleId) => deactivateNow(moduleId)));
      for (const moduleId of [...failed]) await deactivateNow(moduleId);
    });
  }

  return Object.freeze({ reconcile, beforeLifecycleAction, destroy });
}
