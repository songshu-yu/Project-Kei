const officialRepositoryLabel = 'songshu-yu/Project-Kei-Modules';
const officialDownloadSourceStorageKey = 'project-kei-official-download-source-v1';
const officialDownloadSources = new Set(['auto', 'github', 'gitee']);
export const coreModuleIds = Object.freeze(['catalog', 'module_manager', 'dashboard']);
const coreModuleIdSet = new Set(coreModuleIds);
const coreModuleLabels = Object.freeze({
  catalog: '模块目录',
  module_manager: '模块管理器',
  dashboard: '控制台公共外壳',
});

export const officialModulePhases = Object.freeze([
  'idle',
  'loading_cache',
  'cache_ready',
  'empty',
  'refreshing',
  'confirming',
  'downloading',
  'verifying',
  'installing',
  'success',
  'failed',
]);

const phaseLabels = Object.freeze({
  idle: '等待读取官方模块目录缓存',
  loading_cache: '正在读取本机目录缓存',
  cache_ready: '已读取本机目录缓存',
  empty: '官方目录中暂时没有可安装模块',
  refreshing: '正在从选择的 Project Kei 官方镜像刷新目录',
  confirming: '等待确认下载并安装',
  downloading: '后端正在下载、校验并安装官方模块包',
  verifying: '后端正在校验大小、SHA-256 与 manifest',
  installing: '后端正在原子安装模块',
  success: '操作成功',
  failed: '操作失败',
});

const lifecycleActionLabels = Object.freeze({
  enable: '启用',
  disable: '停用',
  configuration_check: '检查配置',
  uninstall: '卸载',
  rollback: '回滚',
  update_official: '更新',
  rollback_official: '回滚到官方版本',
  purge_data: '清除模块数据',
});

const supportedLifecycleActions = new Set(Object.keys(lifecycleActionLabels));
const destructiveCoreActions = new Set([
  'disable',
  'uninstall',
  'rollback',
  'update_official',
  'rollback_official',
  'purge_data',
]);
const operationPhases = new Set(['refreshing', 'downloading', 'verifying', 'installing']);
const interactionBlockedPhases = new Set([...operationPhases, 'confirming']);
const localModuleIdPattern = /^[a-z][a-z0-9_]{0,63}$/;
const localModuleUploadMaxBytes = 64 * 1024 * 1024;

function officialCatalogSourceLabel(catalog) {
  const source = catalog?.source;
  if (!source || typeof source !== 'object') return officialRepositoryLabel;
  return [source.owner, source.repository].filter(Boolean).join('/') || officialRepositoryLabel;
}

export function normalizeOfficialDownloadSource(value) {
  const normalized = String(value || '').trim().toLowerCase();
  return officialDownloadSources.has(normalized) ? normalized : 'auto';
}

function officialDownloadSourceLabel(value) {
  return {
    auto: '自动（GitHub 优先，传输失败时尝试 Gitee）',
    github: 'GitHub',
    gitee: 'Gitee',
  }[normalizeOfficialDownloadSource(value)];
}

function loadOfficialDownloadSource() {
  try {
    return normalizeOfficialDownloadSource(globalThis.localStorage?.getItem(officialDownloadSourceStorageKey));
  } catch (_error) {
    return 'auto';
  }
}

function saveOfficialDownloadSource(value) {
  const normalized = normalizeOfficialDownloadSource(value);
  try {
    globalThis.localStorage?.setItem(officialDownloadSourceStorageKey, normalized);
  } catch (_error) {
    // Source preference is optional browser-only state.
  }
  return normalized;
}

function safeStrings(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === 'string') : [];
}

function safeObjects(value) {
  return Array.isArray(value)
    ? value.filter((item) => item && typeof item === 'object' && !Array.isArray(item))
    : [];
}

function appendText(parent, tag, text, className = '') {
  const node = document.createElement(tag);
  node.textContent = String(text ?? '');
  if (className) node.className = className;
  parent.append(node);
  return node;
}

function appendMeta(card, label, value, valueClass = '') {
  const row = document.createElement('div');
  row.className = 'module-meta-row';
  appendText(row, 'span', label);
  appendText(row, 'span', value, valueClass);
  card.append(row);
}

function listText(values, empty = '无') {
  const items = safeStrings(values);
  return items.length ? items.join('、') : empty;
}

function runtimeRequirementsText(requirements) {
  const values = safeObjects(requirements).map((item) => {
    const id = String(item.id || 'runtime');
    const majors = Array.isArray(item.supported_major_versions)
      ? item.supported_major_versions.filter(Number.isInteger).join('/')
      : '';
    const architecture = String(item.architecture || '');
    return [id === 'node' ? 'Node.js' : id, majors, architecture].filter(Boolean).join(' ');
  });
  return values.length ? values.join('、') : '无额外电脑运行时';
}

function runtimeReadinessText(readiness) {
  const checks = safeObjects(readiness?.checks);
  if (!checks.length) return '无需额外检查';
  const labels = {
    ready: '已就绪',
    missing: '未安装',
    version_unsupported: '版本不受支持',
    architecture_unsupported: '需要 x64',
  };
  return checks.map((check) => {
    const name = check.id === 'node' ? 'Node.js' : String(check.id || '运行时');
    const detected = [check.detected_version, check.detected_architecture].filter(Boolean).join(' ');
    return `${name}：${labels[check.status] || '待检查'}${detected ? `（${detected}）` : ''}`;
  }).join('；');
}

function dependencyReadinessText(readiness) {
  const checks = safeObjects(readiness?.checks);
  if (!checks.length) return '无必需模块依赖';
  const labels = {
    ready: '已就绪',
    missing: '未安装',
    disabled: '未启用',
  };
  return checks.map((check) => {
    const id = String(check.module_id || 'module');
    return `${id}：${labels[check.status] || '待检查'}`;
  }).join('；');
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return '未知';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 ** 2)).toFixed(1)} MiB`;
}

export async function sha256Hex(file) {
  if (!globalThis.crypto?.subtle || typeof file?.arrayBuffer !== 'function') {
    throw new Error('当前浏览器不支持本地 SHA-256 校验');
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
}

export function manualModuleIdNeedsConfirmation(origin, value) {
  return origin === 'manual' && Boolean(String(value || '').trim());
}

function parseControlledSemver(value) {
  const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/.exec(String(value || ''));
  if (!match) throw new Error(`无效的语义版本：${String(value || '')}`);
  if (typeof BigInt !== 'function') throw new Error('当前浏览器不支持精确语义版本比较');
  return [BigInt(match[1]), BigInt(match[2]), BigInt(match[3]), match[4] ? match[4].split('.') : []];
}

export function compareModuleVersions(left, right) {
  const a = parseControlledSemver(left);
  const b = parseControlledSemver(right);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] < b[index] ? -1 : 1;
  }
  const aPre = a[3];
  const bPre = b[3];
  if (!aPre.length && !bPre.length) return 0;
  if (!aPre.length) return 1;
  if (!bPre.length) return -1;
  for (let index = 0; index < Math.min(aPre.length, bPre.length); index += 1) {
    const leftPart = aPre[index];
    const rightPart = bPre[index];
    if (leftPart === rightPart) continue;
    const leftNumeric = /^\d+$/.test(leftPart);
    const rightNumeric = /^\d+$/.test(rightPart);
    if (leftNumeric && rightNumeric) return BigInt(leftPart) < BigInt(rightPart) ? -1 : 1;
    if (leftNumeric !== rightNumeric) return leftNumeric ? -1 : 1;
    return leftPart < rightPart ? -1 : 1;
  }
  if (aPre.length === bPre.length) return 0;
  return aPre.length < bPre.length ? -1 : 1;
}

function moduleId(moduleInfo) {
  return String(moduleInfo?.key || moduleInfo?.module_id || '');
}

function isManagedInstall(moduleInfo) {
  return moduleInfo?.managed === true
    && typeof moduleInfo?.installed_version === 'string'
    && moduleInfo.installed_version.trim() !== ''
    && moduleInfo.install_status !== 'available';
}

export function isBuiltinFeature(moduleInfo) {
  if (!moduleInfo || typeof moduleInfo !== 'object') return false;
  return coreModuleIdSet.has(moduleId(moduleInfo));
}

export function allowedLifecycleActions(moduleInfo) {
  if (!isManagedInstall(moduleInfo) || isBuiltinFeature(moduleInfo)) return [];
  return safeStrings(moduleInfo.available_actions)
    .filter((action) => supportedLifecycleActions.has(action))
    .filter((action) => !(moduleInfo.required && destructiveCoreActions.has(action)));
}

function statusLabel(moduleInfo) {
  if (moduleInfo.restart_required) return '等待重启';
  if (moduleInfo.install_status === 'enabled' && moduleInfo.enabled === false) return '已停用';
  const labels = {
    available: '尚未安装',
    installing: '安装中',
    installed_disabled: '已安装 · 未启用',
    needs_configuration: '需要配置',
    enabled: '已启用',
    update_available: '有可用更新',
    broken: '需要修复',
    uninstalling: '卸载中',
  };
  return labels[moduleInfo.install_status]
    || (moduleInfo.enabled ? '已启用' : moduleInfo.install_status || '状态未知');
}

function sourceLabel(moduleInfo) {
  if (isBuiltinFeature(moduleInfo)) return 'Core 内置功能';
  if (moduleInfo.package_source === 'official_github_release') return '官方 GitHub 模块';
  return '本机导入模块';
}

export function createOfficialModuleState(initial = {}) {
  const phase = officialModulePhases.includes(initial.phase) ? initial.phase : 'idle';
  return Object.freeze({
    phase,
    catalog: initial.catalog && typeof initial.catalog === 'object' ? initial.catalog : null,
    selected: initial.selected && typeof initial.selected === 'object' ? initial.selected : null,
    selectedAction: String(initial.selectedAction || ''),
    message: String(initial.message || ''),
  });
}

export function transitionOfficialModuleState(state, event) {
  const current = createOfficialModuleState(state);
  const type = String(event?.type || '');
  if (type === 'LOAD_CACHE') return createOfficialModuleState({ ...current, phase: 'loading_cache', message: '' });
  if (type === 'CACHE_READY') {
    const modules = safeObjects(event.catalog?.modules);
    return createOfficialModuleState({
      phase: modules.length ? 'cache_ready' : 'empty',
      catalog: event.catalog,
      message: String(event.message || ''),
    });
  }
  if (type === 'REFRESH') return createOfficialModuleState({ ...current, phase: 'refreshing', message: '' });
  if (type === 'CONFIRM') {
    return createOfficialModuleState({
      ...current,
      phase: 'confirming',
      selected: event.module,
      selectedAction: event.action || 'install_official',
      message: '',
    });
  }
  if (type === 'DOWNLOAD') return createOfficialModuleState({ ...current, phase: 'downloading', message: '' });
  if (type === 'VERIFY') return createOfficialModuleState({ ...current, phase: 'verifying', message: '' });
  if (type === 'INSTALL') return createOfficialModuleState({ ...current, phase: 'installing', message: '' });
  if (type === 'SUCCESS') {
    return createOfficialModuleState({
      ...current,
      phase: 'success',
      selected: null,
      selectedAction: '',
      message: String(event.message || ''),
    });
  }
  if (type === 'FAILURE') {
    return createOfficialModuleState({
      ...current,
      phase: 'failed',
      message: String(event.message || '操作失败'),
    });
  }
  if (type === 'CANCEL') {
    const modules = safeObjects(current.catalog?.modules);
    return createOfficialModuleState({
      ...current,
      phase: modules.length ? 'cache_ready' : 'empty',
      selected: null,
      selectedAction: '',
      message: '',
    });
  }
  return current;
}

export function recoverOfficialModuleState(state, { message = '', failed = false } = {}) {
  const current = createOfficialModuleState(state);
  return createOfficialModuleState({
    ...current,
    phase: failed
      ? 'failed'
      : safeObjects(current.catalog?.modules).length ? 'cache_ready' : 'empty',
    selected: null,
    selectedAction: '',
    message: String(message || current.message || ''),
  });
}

function officialModuleKey(moduleInfo) {
  return `${moduleInfo.module_id || ''}@${moduleInfo.version || ''}`;
}

function trustedOfficialCatalog(catalog) {
  return catalog?.source?.owner === 'songshu-yu'
    && catalog?.source?.repository === 'Project-Kei-Modules';
}

function strictRegistryModuleId(moduleInfo) {
  const id = moduleInfo?.module_id;
  return typeof id === 'string' && localModuleIdPattern.test(id) ? id : '';
}

function indexInstalledRegistry(installedCatalog) {
  const records = new Map();
  const conflicts = new Set();
  const seenIds = new Set();
  safeObjects(installedCatalog?.modules).forEach((item) => {
    const id = strictRegistryModuleId(item);
    if (!id) return;
    if (seenIds.has(id)) conflicts.add(id);
    else seenIds.add(id);
    if (typeof item.installed_version === 'string' && item.installed_version.trim() && !records.has(id)) {
      records.set(id, item);
    }
  });
  return { records, conflicts };
}

export function reconcileOfficialModules(catalog, installedCatalog) {
  const releases = safeObjects(catalog?.modules);
  const registryReady = Boolean(installedCatalog && Array.isArray(installedCatalog.modules));
  const installedRegistry = indexInstalledRegistry(installedCatalog);
  const groups = new Map();
  releases.forEach((item) => {
    const id = String(item.module_id || '');
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id).push(item);
  });
  const reconciled = [];
  groups.forEach((items, id) => {
    const officialIdentityValid = localModuleIdPattern.test(id);
    const registryConflict = officialIdentityValid && installedRegistry.conflicts.has(id);
    const local = officialIdentityValid && !registryConflict
      ? installedRegistry.records.get(id)
      : null;
    const valid = items.filter((item) => {
      try {
        compareModuleVersions(item.version, item.version);
        return true;
      } catch (_error) {
        return false;
      }
    });
    let localVersionValid = true;
    if (local) {
      try {
        compareModuleVersions(local.installed_version, local.installed_version);
      } catch (_error) {
        localVersionValid = false;
      }
    }
    const sourceConflict = Boolean(local) && (
      !isManagedInstall(local) || local.package_source !== 'official_github_release'
    );
    const eligible = valid.filter((item) => item.compatible !== false);
    const action = local ? 'update_official' : 'install_official';
    const actionAllowed = local
      ? safeStrings(local.available_actions).includes(action)
      : true;
    const actionable = eligible.filter((item) => (
      safeStrings(item.available_actions).includes(action)
      && (!local || (localVersionValid && compareModuleVersions(item.version, local.installed_version) > 0))
    ));
    const target = actionAllowed && actionable.length
      ? actionable.slice().sort((left, right) => compareModuleVersions(right.version, left.version))[0]
      : null;
    items.forEach((item) => {
      let state = 'unavailable';
      let label = '当前不可操作';
      if (!registryReady) {
        state = 'registry_unavailable';
        label = '等待本机模块目录';
      } else if (!trustedOfficialCatalog(catalog)) {
        state = 'source_untrusted';
        label = '官方来源校验失败';
      } else if (!officialIdentityValid) {
        state = 'identity_invalid';
        label = '官方 module_id 无效';
      } else if (registryConflict) {
        state = 'registry_conflict';
        label = '本机 registry 身份冲突，拒绝操作';
      } else if (!valid.includes(item) || (local && !localVersionValid)) {
        state = 'invalid_version';
        label = '版本信息无效';
      } else if (sourceConflict) {
        state = 'source_conflict';
        label = '本机来源冲突，拒绝覆盖';
      } else if (item.compatible === false) {
        state = 'incompatible';
        label = '当前 Core 不兼容';
      } else if (!local) {
        if (target === item) {
          state = 'install';
          label = '可下载并安装';
        } else {
          state = 'superseded';
          label = '已有更高兼容版本';
        }
      } else {
        const comparison = compareModuleVersions(item.version, local.installed_version);
        if (comparison === 0) {
          state = 'installed';
          label = '已安装';
        } else if (comparison < 0) {
          state = 'local_newer';
          label = '本机版本较新';
        } else if (target === item) {
          state = 'update';
          label = '可下载并更新';
        } else if (!actionAllowed || !safeStrings(item.available_actions).includes(action)) {
          state = 'update_unavailable';
          label = 'Core 当前不允许更新';
        } else {
          state = 'superseded';
          label = '已有更高兼容版本';
        }
      }
      reconciled.push(Object.freeze({ ...item, local_module: local || null, comparison_state: state, comparison_label: label }));
    });
  });
  return Object.freeze(reconciled);
}

function officialInstallCandidates(catalog, installedCatalog) {
  return reconcileOfficialModules(catalog, installedCatalog)
    .filter((moduleInfo) => moduleInfo.comparison_state === 'install');
}

function batchPlanError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

export function buildOfficialBatchPlan(catalog, installedCatalog, selectedKeys) {
  const selected = new Set(safeStrings(Array.from(selectedKeys || [])));
  if (!selected.size) throw batchPlanError('batch_selection_empty', '请至少选择一个兼容模块');
  const candidates = officialInstallCandidates(catalog, installedCatalog);
  const byKey = new Map(candidates.map((item) => [officialModuleKey(item), item]));
  const allByKey = new Map(
    reconcileOfficialModules(catalog, installedCatalog).map((item) => [officialModuleKey(item), item]),
  );
  const chosenById = new Map();
  selected.forEach((key) => {
    const item = byKey.get(key);
    if (!item) {
      const unavailable = allByKey.get(key);
      if (unavailable?.comparison_state === 'incompatible') {
        throw batchPlanError('batch_module_incompatible', `${unavailable.module_id} 与当前 Core 不兼容`);
      }
      throw batchPlanError('batch_selection_stale', `所选模块 ${key} 已不可安装，请重新选择`);
    }
    if (chosenById.has(item.module_id)) {
      throw batchPlanError('batch_version_ambiguous', `${item.module_id} 同时选择了多个版本`);
    }
    chosenById.set(item.module_id, item);
  });
  const installedRegistry = indexInstalledRegistry(installedCatalog);
  const installed = new Set(
    Array.from(installedRegistry.records)
      .filter(([id, item]) => !installedRegistry.conflicts.has(id) && isManagedInstall(item))
      .map(([id]) => id),
  );
  const outgoing = new Map(Array.from(chosenById, ([id]) => [id, []]));
  const indegree = new Map(Array.from(chosenById, ([id]) => [id, 0]));
  chosenById.forEach((item, id) => {
    safeStrings(item.dependencies).forEach((dependencyId) => {
      if (installed.has(dependencyId)) return;
      if (!chosenById.has(dependencyId)) {
        throw batchPlanError(
          'batch_dependency_missing',
          `${id} 需要先安装 ${dependencyId}；请把依赖一并选中`,
        );
      }
      outgoing.get(dependencyId).push(id);
      indegree.set(id, indegree.get(id) + 1);
    });
  });
  const ready = Array.from(indegree)
    .filter(([, degree]) => degree === 0)
    .map(([id]) => id)
    .sort();
  const queue = [];
  while (ready.length) {
    const id = ready.shift();
    queue.push(chosenById.get(id));
    outgoing.get(id).sort().forEach((dependentId) => {
      const next = indegree.get(dependentId) - 1;
      indegree.set(dependentId, next);
      if (next === 0) {
        ready.push(dependentId);
        ready.sort();
      }
    });
  }
  if (queue.length !== chosenById.size) {
    throw batchPlanError('batch_dependency_cycle', '所选模块的必需依赖存在循环，未发送任何安装请求');
  }
  return Object.freeze({
    queue: Object.freeze(queue),
    totalBytes: queue.reduce((total, item) => total + (Number(item.package_size) || 0), 0),
    dependencies: Object.freeze(Array.from(new Set(queue.flatMap((item) => safeStrings(item.dependencies)))).sort()),
    permissions: Object.freeze(Array.from(new Set(queue.flatMap((item) => safeStrings(item.permissions)))).sort()),
  });
}

export async function runOfficialBatchQueue(queue, installOne) {
  const completed = [];
  const items = Array.from(queue || []);
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    try {
      await installOne(item, index, items.length);
      completed.push(item);
    } catch (error) {
      return Object.freeze({
        completed: Object.freeze(completed),
        failed: item,
        remaining: Object.freeze(items.slice(index + 1)),
        error,
      });
    }
  }
  return Object.freeze({
    completed: Object.freeze(completed),
    failed: null,
    remaining: Object.freeze([]),
    error: null,
  });
}

function renderOfficialPhase(state) {
  const status = document.querySelector('#official-module-catalog-status');
  if (!status) return;
  const generatedAt = state.catalog?.generated_at;
  const cacheSource = state.catalog?.cache_source;
  const source = state.catalog?.source;
  const sourceLabel = source && typeof source === 'object'
    ? [source.owner, source.repository].filter(Boolean).join('/')
    : '';
  const refreshStatus = state.catalog?.refresh_status;
  const networkAccessed = state.catalog?.network_accessed === true;
  const moduleCount = safeObjects(state.catalog?.modules).length;
  const metadata = [
    sourceLabel ? `来源：${sourceLabel}` : '',
    state.catalog ? `目录模块：${moduleCount} 项` : '',
    generatedAt ? `目录时间：${generatedAt}` : '',
    cacheSource ? `缓存：${cacheSource}` : '',
    refreshStatus && refreshStatus !== 'not_requested' ? `刷新：${refreshStatus}` : '',
    networkAccessed ? '本次显式刷新使用了网络' : '本次读取未联网',
  ].filter(Boolean).join('；');
  status.textContent = [
    phaseLabels[state.phase] || phaseLabels.idle,
    metadata,
    state.message,
  ].filter(Boolean).join('；');
  status.classList.toggle('error-text', state.phase === 'failed');
  status.dataset.phase = state.phase;
  status.dataset.networkAccessed = networkAccessed ? 'true' : 'false';
}

function renderOfficialModules(state, installedCatalog, batchMode = false, selectedKeys = new Set()) {
  const root = document.querySelector('#official-module-catalog');
  if (!root) return;
  root.replaceChildren();
  const modules = reconcileOfficialModules(state.catalog, installedCatalog);
  if (!modules.length) {
    appendText(
      root,
      'div',
      '当前缓存中没有可安装版本。请显式刷新官方目录，或等待对应模块发布受信 Release；这里不会生成虚假的下载按钮。',
      'module-empty-state',
    );
    return;
  }
  modules.forEach((moduleInfo) => {
    const card = document.createElement('article');
    card.className = 'module-card official-module-card';
    card.dataset.officialModule = officialModuleKey(moduleInfo);
    const head = document.createElement('div');
    head.className = 'module-card-head';
    if (batchMode && moduleInfo.comparison_state === 'install') {
      const choice = document.createElement('label');
      choice.className = 'official-module-choice';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.dataset.officialBatchChoice = officialModuleKey(moduleInfo);
      checkbox.checked = selectedKeys.has(officialModuleKey(moduleInfo));
      checkbox.disabled = interactionBlockedPhases.has(state.phase);
      const choiceText = document.createElement('span');
      choiceText.className = 'visually-hidden';
      choiceText.textContent = `选择 ${moduleInfo.name || moduleInfo.module_id} ${moduleInfo.version}`;
      choice.append(checkbox, choiceText);
      head.append(choice);
    }
    const heading = document.createElement('div');
    appendText(heading, 'strong', moduleInfo.name || moduleInfo.module_id || '未命名模块');
    appendText(heading, 'div', moduleInfo.module_id || '未知 ID', 'module-card-id');
    const badge = appendText(head, 'span', moduleInfo.version || '未知版本', 'module-badge');
    badge.dataset.state = moduleInfo.compatible === false ? 'failed' : 'ready';
    head.prepend(heading);
    card.append(head);
    appendMeta(card, 'Core 兼容', moduleInfo.core_compatibility || '未声明');
    appendMeta(card, '版本状态', moduleInfo.comparison_label);
    if (moduleInfo.local_module?.installed_version) {
      appendMeta(card, '本机版本', moduleInfo.local_module.installed_version);
    }
    appendMeta(card, '包大小', formatBytes(moduleInfo.package_size));
    appendMeta(
      card,
      '官方来源',
      `${officialCatalogSourceLabel(state.catalog)} · ${moduleInfo.release_tag || 'Release'} · ${moduleInfo.asset_name || 'ZIP'}`,
    );
    appendMeta(card, '包 SHA-256', moduleInfo.package_sha256 || '未提供', 'module-digest');
    appendMeta(card, '必需依赖', listText(moduleInfo.dependencies));
    appendMeta(card, '可选依赖', listText(moduleInfo.optional_dependencies));
    appendMeta(card, '电脑运行时', runtimeRequirementsText(moduleInfo.runtime_requirements));
    appendMeta(card, '冲突模块', listText(moduleInfo.conflicts));
    appendMeta(card, '权限', listText(moduleInfo.permissions));
    appendMeta(card, '数据', moduleInfo.data_policy === 'preserve_on_uninstall'
      ? '卸载默认保留数据'
      : moduleInfo.data_policy || '遵循模块声明');
    appendMeta(card, '重启', moduleInfo.requires_restart
      ? '安装后启用可能需要重启 Core'
      : '通常不需要');
    const actions = document.createElement('div');
    actions.className = 'module-management-actions';
    const operation = moduleInfo.comparison_state === 'install'
      ? 'install_official'
      : moduleInfo.comparison_state === 'update' ? 'update_official' : '';
    const label = operation === 'install_official'
      ? '下载并安装'
      : operation === 'update_official' ? '下载并更新' : moduleInfo.comparison_label;
    const install = appendText(actions, 'button', label, operation ? '' : 'secondary');
    install.type = 'button';
    if (operation) {
      install.dataset.officialOperation = officialModuleKey(moduleInfo);
      install.dataset.officialAction = operation;
    }
    install.disabled = !operation || !['cache_ready', 'failed'].includes(state.phase);
    install.hidden = batchMode;
    install.setAttribute(
      'aria-label',
      `${label} ${moduleInfo.name || moduleInfo.module_id || '模块'} ${moduleInfo.version || ''}`,
    );
    if (!operation) install.title = moduleInfo.comparison_label;
    card.append(actions);
    root.append(card);
  });
}

function renderBuiltinCard(moduleInfo, missing = false) {
  const id = moduleId(moduleInfo);
  const card = document.createElement('article');
  card.className = 'module-card builtin-module-card';
  card.dataset.builtinModule = id;
  const head = document.createElement('div');
  head.className = 'module-card-head';
  const heading = document.createElement('div');
  appendText(heading, 'strong', moduleInfo.label || coreModuleLabels[id] || id);
  appendText(heading, 'div', id, 'module-card-id');
  const badge = appendText(
    head,
    'span',
    missing ? 'Core · 未报告' : moduleInfo.configuration_ready ? 'Core · 已就绪' : 'Core · 待配置',
    'module-badge',
  );
  badge.dataset.state = missing ? 'failed' : moduleInfo.configuration_ready ? 'ready' : 'pending';
  head.prepend(heading);
  card.append(head);
  appendMeta(card, '状态', missing ? 'registry 未返回该固定模块' : statusLabel(moduleInfo));
  appendMeta(card, '配置', missing ? '未知' : moduleInfo.configuration_ready ? '已就绪' : '待配置');
  appendMeta(card, '接口', moduleInfo.target_namespace || listText(moduleInfo.api_namespaces));
  appendText(
    card,
    'div',
    '这是 Core 固定模块，不是业务功能包；控制台不会为它显示下载、停用、卸载或清除数据操作。',
    'module-protection-note',
  );
  return card;
}

function renderBuiltinFeatures(catalog) {
  const root = document.querySelector('#builtin-module-catalog');
  const status = document.querySelector('#builtin-module-catalog-status');
  if (!root || !status) return;
  root.replaceChildren();
  const byId = new Map(
    safeObjects(catalog?.modules)
      .filter(isBuiltinFeature)
      .map((moduleInfo) => [moduleId(moduleInfo), moduleInfo]),
  );
  const reported = coreModuleIds.filter((id) => byId.has(id)).length;
  status.textContent = `已读取 ${reported}/${coreModuleIds.length} 个 Core 固定模块；只读展示，不提供生命周期操作。`;
  coreModuleIds.forEach((id) => {
    const moduleInfo = byId.get(id) || {
      key: id,
      label: coreModuleLabels[id],
      configuration_ready: false,
      api_namespaces: [],
    };
    root.append(renderBuiltinCard(moduleInfo, !byId.has(id)));
  });
}

function renderInstalledCard(moduleInfo, busyModules, officialCatalog) {
  const id = moduleId(moduleInfo);
  const card = document.createElement('article');
  card.className = 'module-card installed-module-card';
  card.dataset.installedModule = id;
  card.setAttribute('aria-busy', busyModules.has(id) ? 'true' : 'false');
  const head = document.createElement('div');
  head.className = 'module-card-head';
  const heading = document.createElement('div');
  appendText(heading, 'strong', moduleInfo.label || moduleInfo.name || id);
  appendText(heading, 'div', id, 'module-card-id');
  const badge = appendText(head, 'span', statusLabel(moduleInfo), 'module-badge');
  badge.dataset.state = moduleInfo.restart_required ? 'pending' : moduleInfo.enabled ? 'ready' : 'idle';
  head.prepend(heading);
  card.append(head);
  appendMeta(card, '属性', '可选模块');
  appendMeta(card, '来源', sourceLabel(moduleInfo));
  appendMeta(card, '版本', moduleInfo.installed_version);
  appendMeta(card, '必需依赖', listText(moduleInfo.dependencies));
  appendMeta(card, '可选依赖', listText(moduleInfo.optional_dependencies));
  appendMeta(card, '电脑运行时', runtimeRequirementsText(moduleInfo.runtime_requirements));
  appendMeta(card, '运行时检查', runtimeReadinessText(moduleInfo.runtime_readiness));
  appendMeta(card, '模块依赖检查', dependencyReadinessText(moduleInfo.dependency_readiness));
  if (
    id === 'qq_bridge'
    && moduleInfo.runtime_readiness?.ready === false
  ) {
    appendText(
      card,
      'div',
      '请先安装受支持的 Node.js x64，再显式运行 setup.bat --profile qq；模块安装不会静默运行 npm。',
      'module-protection-note',
    );
  }
  appendMeta(card, '冲突模块', listText(moduleInfo.conflicts));
  appendMeta(card, '配置', moduleInfo.configuration_ready ? '已就绪' : '待配置');
  appendMeta(card, '重启', moduleInfo.restart_required
    ? '需要重启 Core 才生效'
    : moduleInfo.requires_restart ? '生命周期操作可能需要重启' : '通常不需要');
  appendMeta(card, '前端入口', moduleInfo.dashboard_entrypoint || '无');
  appendMeta(card, '权限', listText(moduleInfo.permissions));
  appendMeta(card, '数据', moduleInfo.data_policy === 'preserve_on_uninstall'
    ? '卸载默认保留数据'
    : moduleInfo.data_policy || '遵循模块声明');
  if (moduleInfo.last_operation) {
    const lastOperation = moduleInfo.last_operation;
    appendMeta(
      card,
      '最近操作',
      [lastOperation.action, lastOperation.status, lastOperation.message, lastOperation.at]
        .filter(Boolean).join(' · ') || '已记录',
    );
  }

  const releases = safeObjects(officialCatalog?.modules)
    .filter((release) => release.module_id === id);
  const actions = document.createElement('div');
  actions.className = 'module-management-actions';
  const declaredActions = allowedLifecycleActions(moduleInfo);
  declaredActions.filter((action) => action !== 'purge_data').forEach((action) => {
    const button = appendText(actions, 'button', lifecycleActionLabels[action], 'secondary compact-action');
    button.type = 'button';
    button.dataset.moduleAction = action;
    button.dataset.moduleId = id;
    button.disabled = busyModules.has(id);
    if (action === 'uninstall') button.classList.add('warning-action');
    if (action === 'update_official') {
      const target = reconcileOfficialModules(officialCatalog, { modules: [moduleInfo] })
        .find((release) => release.module_id === id && release.comparison_state === 'update');
      if (target) button.dataset.officialTarget = officialModuleKey(target);
      else {
        button.disabled = true;
        button.textContent = moduleInfo.package_source === 'official_github_release'
          ? '暂无目录更新'
          : '官方更新不可用';
        button.setAttribute('aria-label', `${moduleInfo.name || id} 官方更新不可用`);
        button.title = moduleInfo.package_source === 'official_github_release'
          ? '目录缓存中没有合法的更高兼容版本'
          : '本机模块不是官方受管来源，控制台拒绝自动覆盖';
      }
    }
    if (action === 'rollback_official') {
      const target = releases.find((release) => release.version === moduleInfo.previous_version);
      if (target) button.dataset.officialTarget = officialModuleKey(target);
      else {
        button.disabled = true;
        button.title = '目录缓存中没有可验证的上一版本';
      }
    }
  });
  if (!declaredActions.filter((action) => action !== 'purge_data').length) {
    appendText(actions, 'span', '当前没有可执行的生命周期操作。', 'module-action-empty');
  }
  card.append(actions);

  if (declaredActions.includes('purge_data')) {
    const danger = document.createElement('details');
    danger.className = 'module-danger-zone';
    const summary = appendText(danger, 'summary', '危险区：清除模块数据');
    summary.setAttribute('aria-label', `展开 ${id} 模块数据危险区`);
    const body = document.createElement('div');
    body.className = 'module-danger-body';
    appendText(
      body,
      'p',
      `清除数据与卸载完全独立。请输入模块 ID“${id}”后再确认；该操作不会被默认执行。`,
      'hint',
    );
    const input = document.createElement('input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.dataset.modulePurgeConfirmation = id;
    input.setAttribute('aria-label', `输入 ${id} 以确认清除模块数据`);
    const purge = appendText(body, 'button', '确认清除模块数据', 'danger compact-action');
    purge.type = 'button';
    purge.dataset.moduleConfirmAction = 'purge_data';
    purge.dataset.moduleId = id;
    purge.disabled = true;
    body.append(input, purge);
    danger.append(body);
    card.append(danger);
  }

  const confirmation = document.createElement('div');
  confirmation.className = 'module-confirmation';
  confirmation.dataset.moduleConfirmation = id;
  confirmation.hidden = true;
  card.append(confirmation);
  const loadState = document.createElement('div');
  loadState.className = 'module-load-state';
  loadState.dataset.moduleLoadState = id;
  loadState.textContent = moduleInfo.enabled && moduleInfo.dashboard_entrypoint
    ? '等待加载前端入口…'
    : '后台 Collector / 服务模块，无独立面板。';
  card.append(loadState);
  return card;
}

export function renderInstalledModules(
  catalog,
  { busyModules = new Set(), officialCatalog = null } = {},
) {
  const root = document.querySelector('#module-catalog');
  const status = document.querySelector('#module-catalog-status');
  if (!root || !status) return;
  root.replaceChildren();
  status.classList.remove('error-text');
  const modules = safeObjects(catalog?.modules).filter(isManagedInstall);
  status.textContent = catalog?.module_manager_error
    ? `已读取 ${modules.length} 个已安装模块；本机生命周期状态暂不可用。`
    : `已读取 ${modules.length} 个已安装模块。刷新只读取本机 registry，不访问 GitHub。`;
  if (!modules.length) {
    appendText(
      root,
      'div',
      '当前没有已安装的业务模块。Core 固定模块在下方单独展示，官方目录中未安装的条目不会被伪装成已安装。',
      'module-empty-state',
    );
  } else {
    modules.forEach((moduleInfo) => root.append(
      renderInstalledCard(moduleInfo, busyModules, officialCatalog),
    ));
  }
  renderBuiltinFeatures(catalog);
}

export function renderInstalledModulesError(message) {
  const status = document.querySelector('#module-catalog-status');
  if (!status) return;
  status.textContent = `已安装模块读取失败：${String(message || '请求失败').slice(0, 160)}；现有模块面板保持不变。`;
  status.classList.add('error-text');
}

function openLifecycleConfirmation(moduleInfo, action) {
  const id = moduleId(moduleInfo);
  const root = document.querySelector(`[data-module-confirmation="${CSS.escape(id)}"]`);
  if (!root) return;
  root.replaceChildren();
  root.hidden = false;
  const headingId = `module-confirm-${id}-${action}`;
  const heading = appendText(root, 'strong', action === 'disable' ? '确认停用模块' : '确认卸载模块');
  heading.id = headingId;
  root.setAttribute('role', 'group');
  root.setAttribute('aria-labelledby', headingId);
  appendText(
    root,
    'p',
    action === 'disable'
      ? '停用只更新生命周期状态；进程内模块可能仍需重启 Core 才不再装载。控制台不会自动重启或结束进程。'
      : '卸载只移除模块程序，默认保留模块数据。清除数据位于独立危险区，不会与本次卸载合并。',
    'hint',
  );
  const actions = document.createElement('div');
  actions.className = 'module-management-actions';
  const confirm = appendText(
    actions,
    'button',
    action === 'disable' ? '确认停用' : '确认卸载并保留数据',
    action === 'uninstall' ? 'warning-action' : '',
  );
  confirm.type = 'button';
  confirm.dataset.moduleConfirmAction = action;
  confirm.dataset.moduleId = id;
  const cancel = appendText(actions, 'button', '取消', 'secondary');
  cancel.type = 'button';
  cancel.dataset.moduleCancel = id;
  root.append(actions);
  confirm.focus();
}

function lifecycleRequest(request, id, action, confirmation = '') {
  const base = `/api/v1/modules/${encodeURIComponent(id)}`;
  if (action === 'enable' || action === 'disable') {
    return request(`${base}/${action}`, { method: 'POST' });
  }
  if (action === 'configuration_check') {
    return request(`${base}/configuration/check`, { method: 'POST' });
  }
  if (action === 'rollback') {
    return request(`${base}/rollback`, { method: 'POST' });
  }
  if (action === 'uninstall') {
    return request(base, { method: 'DELETE' });
  }
  if (action === 'purge_data') {
    return request(`${base}/purge-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation }),
    });
  }
  throw new Error('当前操作没有安全的公共契约');
}

export function officialRequest(request, moduleInfo, action, downloadSource = 'auto') {
  const id = String(moduleInfo.module_id || '');
  const version = String(moduleInfo.version || '');
  const actionPath = {
    install_official: 'install-official',
    update_official: 'update-official',
    rollback_official: 'rollback-official',
  }[action];
  if (!actionPath || !id || !version) throw new Error('官方模块选择无效');
  return request(`/api/v1/modules/${encodeURIComponent(id)}/${actionPath}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      version,
      confirmation: `${id}@${version}`,
      download_source: normalizeOfficialDownloadSource(downloadSource),
    }),
    timeoutMs: 120000,
  });
}

function restartInstruction(response) {
  if (!response?.restart_required) return '';
  return ' 需要重启 Core 才生效；请先保存当前工作，再关闭原 Core 窗口并重新运行 start.bat。控制台不会自动重启或结束进程。';
}

function operationError(error) {
  const text = String(error?.message || '请求失败').replace(/\s+/g, ' ').trim();
  if (text === '[object Object]') return '服务端拒绝了请求，请查看 Core 日志中的结构化错误';
  const labels = {
    official_catalog_refresh_failed: '官方目录刷新失败',
    official_catalog_unavailable: '本机没有可用的官方目录缓存',
    official_module_download_failed: '官方模块下载失败',
    official_module_download_timeout: '官方模块下载超时',
    official_module_integrity_mismatch: '安装包 SHA-256 校验失败',
    official_module_size_mismatch: '安装包大小校验失败',
    official_module_manifest_mismatch: '安装包 manifest 与官方目录不一致',
    official_module_archive_invalid: '安装包归档无效',
    official_module_redirect_rejected: '下载重定向离开受信来源',
    official_catalog_source_untrusted: '官方目录来源校验失败',
    official_github_rate_limited: 'GitHub 匿名访问暂时受限',
    official_gitee_rate_limited: 'Gitee 匿名访问暂时受限',
    local_module_upload_content_type_invalid: '本地安装包类型无效',
    local_module_upload_sha256_required: '缺少本地安装包摘要',
    local_module_upload_integrity_mismatch: '本地安装包摘要不匹配',
    local_module_upload_too_large: '本地安装包超过 64 MiB',
    local_module_upload_module_id_invalid: '模块 ID 无效',
    local_module_upload_failed: '本地安装包上传失败',
  };
  const prefix = labels[error?.code];
  const details = [];
  if (Number.isFinite(error?.receivedBytes) && error.receivedBytes > 0) {
    details.push(`已接收 ${formatBytes(error.receivedBytes)}`);
  }
  if (error?.retryAfter) {
    details.push(`建议在 ${String(error.retryAfter).slice(0, 80)} 后重试`);
  } else if (error?.retryable === true) {
    details.push('可稍后重试');
  }
  return [
    `${prefix ? `${prefix}：` : ''}${text}`,
    ...details,
  ].filter(Boolean).join('；').slice(0, 240);
}

export function setupModuleManagement({
  request,
  notify,
  reconcileInstalled,
  beforeLifecycleAction = async () => {},
}) {
  const abortController = new AbortController();
  const busyModules = new Set();
  const moduleSnapshot = new Map();
  let officialState = createOfficialModuleState();
  let lastCatalog = null;
  let localUploadFile = null;
  let localUploadSha256 = '';
  let localUploadBusy = false;
  let localModuleIdOrigin = document.querySelector('#local-module-id')?.value.trim()
    ? 'manual'
    : 'empty';
  let localUploadSelectionVersion = 0;
  let batchMode = false;
  let batchBusy = false;
  let officialDownloadSource = loadOfficialDownloadSource();
  const batchSelection = new Set();

  function setLocalModuleId(value, origin) {
    const input = document.querySelector('#local-module-id');
    if (input) input.value = String(value || '');
    localModuleIdOrigin = origin;
  }

  function renderLocalUpload() {
    const moduleIdInput = document.querySelector('#local-module-id');
    const button = document.querySelector('#install-local-module-zip');
    if (!moduleIdInput || !button) return;
    const id = moduleIdInput.value.trim();
    button.disabled = localUploadBusy
      || (id && !localModuleIdPattern.test(id))
      || !localUploadFile
      || !localUploadSha256;
    button.textContent = localUploadBusy
      ? '正在上传并安装…'
      : id ? `上传并安装（校验 ${id}）` : '上传并安装（manifest 自动识别）';
    button.setAttribute('aria-busy', localUploadBusy ? 'true' : 'false');
  }

  function setLocalUploadStatus(message, failed = false) {
    const status = document.querySelector('#local-module-upload-status');
    if (!status) return;
    status.textContent = String(message || '');
    status.classList.toggle('error-text', failed);
  }

  function currentLocalUploadStatus() {
    const status = document.querySelector('#local-module-upload-status');
    return {
      message: status?.textContent || '',
      failed: Boolean(status?.classList.contains('error-text')),
    };
  }

  function restoreLocalFileInput(file) {
    const input = document.querySelector('#local-module-zip');
    if (!input) return;
    try {
      if (file && typeof globalThis.DataTransfer === 'function') {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
      } else {
        input.value = '';
      }
    } catch (_error) {
      input.value = '';
    }
  }

  function chooseLocalModuleIdMode() {
    const dialog = document.querySelector('#local-module-id-choice');
    if (!dialog || typeof dialog.showModal !== 'function') {
      const keep = globalThis.confirm?.(
        '当前预期模块 ID 是手工填写的。确定保留手工 ID；取消则使用新包 manifest 自动识别。',
      );
      return Promise.resolve(keep ? 'keep' : 'manifest');
    }
    return new Promise((resolve) => {
      const buttons = Array.from(dialog.querySelectorAll('[data-local-module-id-choice]'));
      const finish = (choice) => {
        buttons.forEach((button) => button.removeEventListener('click', onChoice));
        dialog.removeEventListener('cancel', onCancel);
        if (dialog.open) dialog.close();
        resolve(choice);
      };
      const onChoice = (event) => finish(event.currentTarget.dataset.localModuleIdChoice);
      const onCancel = (event) => {
        event.preventDefault();
        finish('cancel');
      };
      buttons.forEach((button) => button.addEventListener('click', onChoice));
      dialog.addEventListener('cancel', onCancel);
      dialog.showModal();
      dialog.querySelector('[data-local-module-id-choice="keep"]')?.focus();
    });
  }

  function refreshLocalModuleSuggestions() {
    const root = document.querySelector('#local-module-id-suggestions');
    if (!root) return;
    const ids = new Set();
    safeObjects(lastCatalog?.modules).forEach((item) => {
      const id = moduleId(item);
      if (localModuleIdPattern.test(id)) ids.add(id);
    });
    safeObjects(officialState.catalog?.modules).forEach((item) => {
      const id = String(item.module_id || '');
      if (localModuleIdPattern.test(id)) ids.add(id);
    });
    root.replaceChildren(...Array.from(ids).sort().map((id) => {
      const option = document.createElement('option');
      option.value = id;
      return option;
    }));
  }

  function renderOfficial() {
    const validBatchKeys = new Set(
      officialInstallCandidates(officialState.catalog, lastCatalog).map(officialModuleKey),
    );
    Array.from(batchSelection).forEach((key) => {
      if (!validBatchKeys.has(key)) batchSelection.delete(key);
    });
    renderOfficialPhase(officialState);
    renderOfficialModules(officialState, lastCatalog, batchMode, batchSelection);
    const refresh = document.querySelector('#refresh-official-module-catalog');
    const source = document.querySelector('#official-module-download-source');
    if (source) {
      source.value = officialDownloadSource;
      source.disabled = batchBusy || interactionBlockedPhases.has(officialState.phase);
    }
    if (refresh) {
      refresh.disabled = batchBusy || interactionBlockedPhases.has(officialState.phase);
      refresh.setAttribute('aria-busy', officialState.phase === 'refreshing' ? 'true' : 'false');
    }
    const toggle = document.querySelector('#toggle-official-module-batch');
    const toolbar = document.querySelector('#official-module-batch-toolbar');
    const count = document.querySelector('#official-module-batch-count');
    const install = document.querySelector('#install-selected-official-modules');
    if (toggle) {
      toggle.textContent = batchMode ? '取消批量选择' : '批量选择';
      toggle.setAttribute('aria-pressed', batchMode ? 'true' : 'false');
      toggle.disabled = batchBusy || interactionBlockedPhases.has(officialState.phase);
    }
    if (toolbar) toolbar.hidden = !batchMode;
    if (count) count.textContent = `已选择 ${batchSelection.size} 项`;
    if (install) {
      install.disabled = batchBusy || batchSelection.size === 0
        || interactionBlockedPhases.has(officialState.phase);
      install.setAttribute('aria-busy', batchBusy ? 'true' : 'false');
      install.textContent = batchBusy ? '正在依次安装…' : '安装已选';
    }
  }

  function renderInstalled() {
    if (lastCatalog) {
      renderInstalledModules(lastCatalog, {
        busyModules,
        officialCatalog: officialState.catalog,
      });
    }
  }

  function rememberCatalog(catalog) {
    lastCatalog = catalog;
    moduleSnapshot.clear();
    safeObjects(catalog?.modules).forEach((item) => {
      const id = moduleId(item);
      if (id) moduleSnapshot.set(id, item);
    });
    refreshLocalModuleSuggestions();
  }

  async function refreshInstalled() {
    try {
      const catalog = await request('/api/v1/modules', { cache: 'no-store' });
      rememberCatalog(catalog);
      renderInstalled();
      renderOfficial();
      await reconcileInstalled(catalog);
      return catalog;
    } catch (error) {
      renderInstalledModulesError(operationError(error));
      throw error;
    }
  }

  async function reloadLocalModuleViews(message) {
    const warnings = [];
    try {
      await refreshInstalled();
    } catch (error) {
      warnings.push(`本机模块列表刷新失败：${operationError(error)}`);
    }
    try {
      const catalog = await request('/api/v1/modules/official-catalog', { cache: 'no-store' });
      officialState = transitionOfficialModuleState(officialState, {
        type: 'CACHE_READY',
        catalog,
        message: [message, ...warnings].filter(Boolean).join('；'),
      });
      renderInstalled();
      refreshLocalModuleSuggestions();
    } catch (error) {
      warnings.push(`官方目录本机缓存刷新失败：${operationError(error)}`);
      officialState = recoverOfficialModuleState(officialState, {
        failed: true,
        message: [message, ...warnings, '可手动刷新后继续操作'].filter(Boolean).join('；'),
      });
    } finally {
      if (interactionBlockedPhases.has(officialState.phase) || officialState.phase === 'success') {
        officialState = recoverOfficialModuleState(officialState);
      }
      renderOfficial();
    }
    return warnings;
  }

  async function readOfficialCache() {
    officialState = transitionOfficialModuleState(officialState, { type: 'LOAD_CACHE' });
    renderOfficial();
    try {
      const catalog = await request('/api/v1/modules/official-catalog', { cache: 'no-store' });
      officialState = transitionOfficialModuleState(officialState, { type: 'CACHE_READY', catalog });
      renderOfficial();
      renderInstalled();
      refreshLocalModuleSuggestions();
      return catalog;
    } catch (error) {
      officialState = transitionOfficialModuleState(officialState, {
        type: 'FAILURE',
        message: `本机目录缓存不可用：${operationError(error)}。页面没有访问 GitHub；已安装模块和 Core 固定模块不受影响`,
      });
      renderOfficial();
      return null;
    }
  }

  async function refreshOfficialCatalog() {
    if (interactionBlockedPhases.has(officialState.phase)) return;
    officialState = transitionOfficialModuleState(officialState, { type: 'REFRESH' });
    renderOfficial();
    try {
      const catalog = await request('/api/v1/modules/official-catalog/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ download_source: officialDownloadSource }),
        timeoutMs: 30000,
      });
      officialState = transitionOfficialModuleState(officialState, { type: 'CACHE_READY', catalog });
      renderOfficial();
      renderInstalled();
      refreshLocalModuleSuggestions();
      notify('官方模块目录已刷新。', 'success');
    } catch (error) {
      officialState = transitionOfficialModuleState(officialState, {
        type: 'FAILURE',
        message: `刷新失败：${operationError(error)}。最后一次有效缓存仍可使用`,
      });
      renderOfficial();
      notify('官方模块目录刷新失败；已安装模块和 Core 固定模块不受影响。', 'error');
    }
  }

  async function runLifecycleAction(moduleInfo, action, confirmation = '') {
    const id = moduleId(moduleInfo);
    if (busyModules.has(id)) return;
    if (!allowedLifecycleActions(moduleInfo).includes(action)) {
      notify(`${moduleInfo.label || id}：当前状态不允许该操作。`, 'error');
      return;
    }
    busyModules.add(id);
    renderInstalled();
    const operationStatus = document.querySelector('#module-operation-status');
    if (operationStatus) {
      operationStatus.textContent = `正在${lifecycleActionLabels[action]} ${moduleInfo.label || id}…`;
      operationStatus.classList.remove('error-text');
    }
    let response;
    let panelDetached = false;
    try {
      if (action === 'disable' || action === 'uninstall') {
        await beforeLifecycleAction(id, action);
        panelDetached = true;
      }
      response = await lifecycleRequest(request, id, action, confirmation);
    } catch (error) {
      if (operationStatus) {
        operationStatus.textContent = `${moduleInfo.label || id}：${lifecycleActionLabels[action]}失败：${operationError(error)}`;
        operationStatus.classList.add('error-text');
      }
      notify(`${moduleInfo.label || id}：操作失败；原有模块和其他卡片保持不变。`, 'error');
      busyModules.delete(id);
      renderInstalled();
      if (panelDetached && lastCatalog) {
        try {
          await reconcileInstalled(lastCatalog);
        } catch (_reconcileError) {
          notify(`${moduleInfo.label || id}：面板恢复失败，请刷新本机模块。`, 'error');
        }
      }
      return;
    }
    const message = `${moduleInfo.label || id}：${lifecycleActionLabels[action]}成功。${restartInstruction(response)}`;
    if (operationStatus) operationStatus.textContent = message;
    notify(message, 'success');
    busyModules.delete(id);
    try {
      await refreshInstalled();
    } catch (_error) {
      if (operationStatus) {
        operationStatus.textContent = `${message} 但本机目录刷新失败，请手动刷新。`;
        operationStatus.classList.add('error-text');
      }
    }
  }

  async function runOfficialOperation(moduleInfo, action) {
    if (!moduleInfo || operationPhases.has(officialState.phase)) return;
    officialState = transitionOfficialModuleState(officialState, { type: 'DOWNLOAD' });
    renderOfficial();
    try {
      const response = await officialRequest(request, moduleInfo, action, officialDownloadSource);
      const verb = action === 'install_official' ? '安装' : action === 'update_official' ? '更新' : '回滚';
      officialState = transitionOfficialModuleState(officialState, {
        type: 'SUCCESS',
        message: `已${verb} ${officialModuleKey(moduleInfo)}；模块不会被静默启用${restartInstruction(response)}`,
      });
      renderOfficial();
      await reloadLocalModuleViews(officialState.message);
      notify(`官方模块${verb}完成；请在“已安装模块”中显式启用。`, 'success');
    } catch (error) {
      officialState = transitionOfficialModuleState(officialState, {
        type: 'FAILURE',
        message: `${operationError(error)}；旧模块和其他卡片不受影响`,
      });
      renderOfficial();
      notify('官方模块操作失败；旧模块和其他卡片不受影响。', 'error');
    } finally {
      if (interactionBlockedPhases.has(officialState.phase) || officialState.phase === 'success') {
        officialState = recoverOfficialModuleState(officialState);
        renderOfficial();
      }
    }
  }

  function setBatchMode(enabled) {
    if (batchBusy) return;
    batchMode = Boolean(enabled);
    batchSelection.clear();
    renderOfficial();
  }

  function selectAllCompatibleOfficialModules() {
    batchSelection.clear();
    officialInstallCandidates(officialState.catalog, lastCatalog)
      .forEach((item) => batchSelection.add(officialModuleKey(item)));
    renderOfficial();
  }

  function openOfficialBatchConfirmation() {
    let plan;
    try {
      plan = buildOfficialBatchPlan(officialState.catalog, lastCatalog, batchSelection);
    } catch (error) {
      officialState = createOfficialModuleState({
        ...officialState,
        phase: 'failed',
        message: `${operationError(error)}；未发送任何安装请求`,
      });
      renderOfficial();
      notify('批量安装计划无效；未发送任何安装请求。', 'error');
      return;
    }
    const dialog = document.querySelector('#official-module-batch-confirmation');
    const summary = document.querySelector('#official-module-batch-summary');
    const list = document.querySelector('#official-module-batch-list');
    if (!dialog || !summary || !list || typeof dialog.showModal !== 'function') return;
    summary.textContent = `目录身份：${officialCatalogSourceLabel(officialState.catalog)}；下载源：${officialDownloadSourceLabel(officialDownloadSource)}；${plan.queue.length} 个模块；总大小 ${formatBytes(plan.totalBytes)}；必需依赖：${listText(plan.dependencies)}；权限：${listText(plan.permissions)}。Core 会逐包独立校验，安装后不会自动启用或重启。`;
    list.replaceChildren(...plan.queue.map((item, index) => {
      const row = document.createElement('li');
      row.textContent = `${index + 1}. ${item.name || item.module_id} ${item.version}`;
      return row;
    }));
    dialog.dataset.batchPlan = JSON.stringify(plan.queue.map(officialModuleKey));
    dialog.showModal();
    dialog.querySelector('[data-confirm-official-batch]')?.focus();
  }

  async function runOfficialBatch(planKeys) {
    if (batchBusy || interactionBlockedPhases.has(officialState.phase)) return;
    let plan;
    try {
      plan = buildOfficialBatchPlan(officialState.catalog, lastCatalog, planKeys);
    } catch (error) {
      officialState = createOfficialModuleState({ ...officialState, phase: 'failed', message: operationError(error) });
      renderOfficial();
      return;
    }
    batchBusy = true;
    officialState = transitionOfficialModuleState(officialState, { type: 'DOWNLOAD' });
    renderOfficial();
    let result;
    try {
      result = await runOfficialBatchQueue(plan.queue, async (item, index, total) => {
        officialState = createOfficialModuleState({
          ...officialState,
          phase: 'installing',
          message: `正在安装 ${index + 1}/${total}：${officialModuleKey(item)}`,
        });
        renderOfficial();
        await officialRequest(request, item, 'install_official', officialDownloadSource);
      });
      const completed = result.completed.map(officialModuleKey);
      const remaining = result.remaining.map(officialModuleKey);
      const report = result.failed
        ? `批量安装已停止；已完成：${listText(completed)}；失败：${officialModuleKey(result.failed)}（${operationError(result.error)}）；未执行：${listText(remaining)}`
        : `批量安装完成：${listText(completed)}；模块不会被自动启用或重启`;
      officialState = createOfficialModuleState({
        ...officialState,
        phase: result.failed ? 'failed' : 'success',
        message: report,
      });
      await reloadLocalModuleViews(report);
      if (result.failed) {
        batchSelection.clear();
        result.remaining.forEach((item) => batchSelection.add(officialModuleKey(item)));
        notify('批量安装遇到失败并已停止；已完成模块不会回滚。', 'error');
      } else {
        batchMode = false;
        batchSelection.clear();
        notify('所选官方模块已依次安装；请按需逐个启用。', 'success');
      }
    } finally {
      batchBusy = false;
      if (interactionBlockedPhases.has(officialState.phase) || officialState.phase === 'success') {
        officialState = recoverOfficialModuleState(officialState);
      }
      renderOfficial();
    }
  }

  async function selectLocalModuleZip(file) {
    const selectionVersion = ++localUploadSelectionVersion;
    const previous = {
      file: localUploadFile,
      sha256: localUploadSha256,
      id: document.querySelector('#local-module-id')?.value || '',
      origin: localModuleIdOrigin,
      status: currentLocalUploadStatus(),
    };
    if (!file) {
      localUploadFile = null;
      localUploadSha256 = '';
      if (localModuleIdOrigin !== 'manual') setLocalModuleId('', 'empty');
      setLocalUploadStatus(
        '尚未选择 ZIP。选择文件后将从 manifest 自动识别模块 ID；选择文件不会联网或安装。',
      );
      renderLocalUpload();
      return;
    }
    if (!String(file.name || '').toLowerCase().endsWith('.zip')) {
      localUploadFile = null;
      localUploadSha256 = '';
      if (localModuleIdOrigin !== 'manual') setLocalModuleId('', 'empty');
      setLocalUploadStatus('请选择扩展名为 .zip 的模块安装包。', true);
      renderLocalUpload();
      return;
    }
    if (!Number.isFinite(file.size) || file.size < 1 || file.size > localModuleUploadMaxBytes) {
      localUploadFile = null;
      localUploadSha256 = '';
      if (localModuleIdOrigin !== 'manual') setLocalModuleId('', 'empty');
      setLocalUploadStatus('模块 ZIP 必须大于 0 B 且不超过 64 MiB。', true);
      renderLocalUpload();
      return;
    }

    let idMode = 'manifest';
    if (manualModuleIdNeedsConfirmation(localModuleIdOrigin, previous.id)) {
      idMode = await chooseLocalModuleIdMode();
      if (selectionVersion !== localUploadSelectionVersion) return;
      if (idMode === 'cancel') {
        localUploadFile = previous.file;
        localUploadSha256 = previous.sha256;
        setLocalModuleId(previous.id, previous.origin);
        restoreLocalFileInput(previous.file);
        setLocalUploadStatus(
          previous.file
            ? `已取消换包；继续保留 ${previous.file.name} 和手工预期模块 ID。`
            : '已取消换包；未选择新的 ZIP。',
          previous.status.failed,
        );
        renderLocalUpload();
        return;
      }
    }
    if (idMode === 'manifest') {
      setLocalModuleId('', 'manifest_pending');
    }
    localUploadFile = null;
    localUploadSha256 = '';
    renderLocalUpload();
    setLocalUploadStatus(
      `已选择 ${file.name}；将从 manifest 自动识别模块 ID，并在本机计算 SHA-256。不会联网或安装…`,
    );
    try {
      const digest = await sha256Hex(file);
      if (selectionVersion !== localUploadSelectionVersion) return;
      localUploadFile = file;
      localUploadSha256 = digest;
      const expectedId = document.querySelector('#local-module-id')?.value.trim() || '';
      setLocalUploadStatus(
        `已选择 ${file.name}（${formatBytes(file.size)}）；SHA-256：${digest}。`
          + `${expectedId
            ? `Core 将从 manifest 识别实际 ID，并额外核对手工预期 ID ${expectedId}。`
            : '点击上传后，Core 才会从已验证的 manifest 自动识别模块 ID。'}`,
      );
    } catch (error) {
      if (selectionVersion !== localUploadSelectionVersion) return;
      try {
        localUploadSha256 = await sha256Hex(file);
        localUploadFile = file;
      } catch (_digestError) {
        localUploadFile = null;
        localUploadSha256 = '';
      }
      if (idMode === 'manifest') setLocalModuleId('', 'empty');
      setLocalUploadStatus(
        `${operationError(error)}。文件名不会作为模块身份；Core 只使用已验证的包内 manifest。`,
        true,
      );
    }
    renderLocalUpload();
  }

  async function installLocalModuleZip() {
    const moduleIdInput = document.querySelector('#local-module-id');
    const id = moduleIdInput?.value.trim() || '';
    if (localUploadBusy || !localUploadFile || !localUploadSha256) return;
    if (id && !localModuleIdPattern.test(id)) {
      setLocalUploadStatus('模块 ID 必须以小写字母开头，只能包含小写字母、数字和下划线。', true);
      renderLocalUpload();
      return;
    }
    localUploadBusy = true;
    renderLocalUpload();
    setLocalUploadStatus(
      `正在把 ${localUploadFile.name} 上传到本机 Core；`
        + `${id ? `将额外核对预期 ID ${id}` : '将从 manifest 自动识别模块 ID'}…`,
    );
    try {
      const query = id ? `?expected_module_id=${encodeURIComponent(id)}` : '';
      const response = await request(`/api/v1/modules/install-upload${query}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/zip',
          'X-Project-Kei-Package-SHA256': localUploadSha256,
        },
        body: localUploadFile,
        timeoutMs: 120000,
      });
      const uploaded = response?.local_upload;
      const installedId = String(response?.module_id || id || '未知模块');
      setLocalUploadStatus(
        `已安装 ${installedId}；接收 ${formatBytes(uploaded?.received_bytes)}，SHA-256：${uploaded?.sha256 || localUploadSha256}。模块不会被自动启用。${restartInstruction(response)}`,
      );
      notify(`本地模块 ${installedId} 安装完成；请在“已安装模块”中显式启用。`, 'success');
      try {
        await refreshInstalled();
      } catch (_error) {
        setLocalUploadStatus(`已安装 ${installedId}，但本机模块列表刷新失败，请手动刷新。`, true);
      }
    } catch (error) {
      setLocalUploadStatus(`本地 ZIP 安装失败：${operationError(error)}。原有模块保持不变。`, true);
      notify(`本地模块${id ? ` ${id}` : ''}安装失败；原有模块保持不变。`, 'error');
    } finally {
      localUploadBusy = false;
      renderLocalUpload();
    }
  }

  function openOfficialConfirmation(moduleInfo, action) {
    officialState = transitionOfficialModuleState(officialState, {
      type: 'CONFIRM',
      module: moduleInfo,
      action,
    });
    renderOfficial();
    const confirmation = document.querySelector('#official-module-install-confirmation');
    if (!confirmation) return;
    confirmation.hidden = false;
    confirmation.replaceChildren();
    const verb = action === 'install_official' ? '下载并安装' : action === 'update_official' ? '更新到' : '回滚到';
    const heading = appendText(
      confirmation,
      'strong',
      `确认${verb} ${moduleInfo.name || moduleInfo.module_id} ${moduleInfo.version}`,
    );
    heading.id = 'official-module-install-confirmation-heading';
    confirmation.setAttribute('role', 'group');
    confirmation.setAttribute('aria-labelledby', heading.id);
    appendText(
      confirmation,
      'p',
      `目录身份：${officialRepositoryLabel}；下载源：${officialDownloadSourceLabel(officialDownloadSource)}；大小：${formatBytes(moduleInfo.package_size)}；SHA-256：${moduleInfo.package_sha256 || '未提供'}。请求由 Core 下载、校验并安装；浏览器不下载或解包。安装后不会自动启用或重启。`,
      'hint module-confirmation-copy',
    );
    const actions = document.createElement('div');
    actions.className = 'module-management-actions';
    const confirm = appendText(actions, 'button', `确认${verb}`);
    confirm.type = 'button';
    confirm.dataset.confirmOfficialOperation = officialModuleKey(moduleInfo);
    const cancel = appendText(actions, 'button', '取消', 'secondary');
    cancel.type = 'button';
    cancel.dataset.cancelOfficialInstall = 'true';
    confirmation.append(actions);
    confirm.focus();
  }

  document.querySelector('#refresh-installed-modules')?.addEventListener(
    'click',
    () => void refreshInstalled(),
    { signal: abortController.signal },
  );
  document.querySelector('#refresh-official-module-catalog')?.addEventListener(
    'click',
    () => void refreshOfficialCatalog(),
    { signal: abortController.signal },
  );
  document.querySelector('#official-module-download-source')?.addEventListener(
    'change',
    (event) => {
      officialDownloadSource = saveOfficialDownloadSource(event.target.value);
      event.target.value = officialDownloadSource;
      batchSelection.clear();
      renderOfficial();
    },
    { signal: abortController.signal },
  );
  document.querySelector('#toggle-official-module-batch')?.addEventListener(
    'click',
    () => setBatchMode(!batchMode),
    { signal: abortController.signal },
  );
  document.querySelector('#select-all-official-modules')?.addEventListener(
    'click',
    selectAllCompatibleOfficialModules,
    { signal: abortController.signal },
  );
  document.querySelector('#cancel-official-module-batch')?.addEventListener(
    'click',
    () => setBatchMode(false),
    { signal: abortController.signal },
  );
  document.querySelector('#install-selected-official-modules')?.addEventListener(
    'click',
    openOfficialBatchConfirmation,
    { signal: abortController.signal },
  );
  document.querySelector('#local-module-id')?.addEventListener(
    'input',
    (event) => {
      localModuleIdOrigin = event.target.value.trim() ? 'manual' : 'empty';
      renderLocalUpload();
    },
    { signal: abortController.signal },
  );
  document.querySelector('#local-module-zip')?.addEventListener(
    'change',
    (event) => void selectLocalModuleZip(event.target.files?.[0] || null),
    { signal: abortController.signal },
  );
  document.querySelector('#install-local-module-zip')?.addEventListener(
    'click',
    () => void installLocalModuleZip(),
    { signal: abortController.signal },
  );

  document.querySelector('#module-catalog')?.addEventListener('input', (event) => {
    const input = event.target.closest('[data-module-purge-confirmation]');
    if (!input) return;
    const id = input.dataset.modulePurgeConfirmation;
    const button = input.parentElement?.querySelector('[data-module-confirm-action="purge_data"]');
    if (button) button.disabled = input.value !== id || busyModules.has(id);
  }, { signal: abortController.signal });

  document.querySelector('#module-catalog')?.addEventListener('click', (event) => {
    const actionButton = event.target.closest('[data-module-action]');
    if (actionButton) {
      const moduleInfo = moduleSnapshot.get(actionButton.dataset.moduleId);
      const action = actionButton.dataset.moduleAction;
      if (!moduleInfo || busyModules.has(moduleId(moduleInfo))) return;
      if (action === 'disable' || action === 'uninstall') {
        openLifecycleConfirmation(moduleInfo, action);
      } else if (action === 'update_official' || action === 'rollback_official') {
        const target = safeObjects(officialState.catalog?.modules)
          .find((item) => officialModuleKey(item) === actionButton.dataset.officialTarget);
        if (target) openOfficialConfirmation(target, action);
      } else {
        void runLifecycleAction(moduleInfo, action);
      }
      return;
    }
    const confirmButton = event.target.closest('[data-module-confirm-action]');
    if (confirmButton) {
      const moduleInfo = moduleSnapshot.get(confirmButton.dataset.moduleId);
      const action = confirmButton.dataset.moduleConfirmAction;
      if (!moduleInfo || busyModules.has(moduleId(moduleInfo))) return;
      const confirmation = action === 'purge_data'
        ? confirmButton.parentElement?.querySelector('[data-module-purge-confirmation]')?.value || ''
        : '';
      if (action === 'purge_data' && confirmation !== moduleId(moduleInfo)) return;
      void runLifecycleAction(moduleInfo, action, confirmation);
      return;
    }
    const cancel = event.target.closest('[data-module-cancel]');
    if (cancel) {
      const confirmation = document.querySelector(
        `[data-module-confirmation="${CSS.escape(cancel.dataset.moduleCancel)}"]`,
      );
      if (confirmation) {
        confirmation.hidden = true;
        confirmation.replaceChildren();
      }
    }
  }, { signal: abortController.signal });

  document.querySelector('#official-module-catalog')?.addEventListener('click', (event) => {
    const install = event.target.closest('[data-official-operation]');
    if (!install || interactionBlockedPhases.has(officialState.phase)) return;
    const selected = reconcileOfficialModules(officialState.catalog, lastCatalog)
      .find((moduleInfo) => officialModuleKey(moduleInfo) === install.dataset.officialOperation);
    if (selected && ['install_official', 'update_official'].includes(install.dataset.officialAction)) {
      openOfficialConfirmation(selected, install.dataset.officialAction);
    }
  }, { signal: abortController.signal });

  document.querySelector('#official-module-catalog')?.addEventListener('change', (event) => {
    const choice = event.target.closest('[data-official-batch-choice]');
    if (!choice || !batchMode || batchBusy) return;
    if (choice.checked) batchSelection.add(choice.dataset.officialBatchChoice);
    else batchSelection.delete(choice.dataset.officialBatchChoice);
    renderOfficial();
  }, { signal: abortController.signal });

  document.querySelector('#official-module-install-confirmation')?.addEventListener('click', (event) => {
    const confirm = event.target.closest('[data-confirm-official-operation]');
    if (confirm) {
      const selected = officialState.selected;
      const action = officialState.selectedAction;
      if (selected && officialModuleKey(selected) === confirm.dataset.confirmOfficialOperation) {
        document.querySelector('#official-module-install-confirmation').hidden = true;
        void runOfficialOperation(selected, action);
      }
      return;
    }
    if (event.target.closest('[data-cancel-official-install]')) {
      officialState = transitionOfficialModuleState(officialState, { type: 'CANCEL' });
      const confirmation = document.querySelector('#official-module-install-confirmation');
      confirmation.hidden = true;
      confirmation.replaceChildren();
      renderOfficial();
    }
  }, { signal: abortController.signal });

  document.querySelector('#official-module-batch-confirmation')?.addEventListener('click', (event) => {
    const dialog = event.currentTarget;
    if (event.target.closest('[data-cancel-official-batch-confirmation]')) {
      dialog.close();
      return;
    }
    if (event.target.closest('[data-confirm-official-batch]')) {
      let keys = [];
      try {
        keys = JSON.parse(dialog.dataset.batchPlan || '[]');
      } catch (_error) {
        keys = [];
      }
      dialog.close();
      void runOfficialBatch(keys);
    }
  }, { signal: abortController.signal });
  document.querySelector('#official-module-batch-confirmation')?.addEventListener('cancel', (event) => {
    event.preventDefault();
    event.currentTarget.close();
  }, { signal: abortController.signal });
  document.querySelector('#official-module-batch-confirmation')?.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    event.currentTarget.close();
  }, { signal: abortController.signal });

  renderOfficial();

  return Object.freeze({
    refreshInstalled,
    readOfficialCache,
    refreshOfficialCatalog,
    destroy: () => abortController.abort(),
  });
}
