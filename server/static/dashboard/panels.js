import {
  deletePanelAvatar,
  loadPanelAvatar,
  savePanelAvatar,
} from './avatar-store.js?v=pk100-20260808-localzip2';

export const panelStorageKey = 'project-kei.dashboard.panel-open.v1';
export const panelLayoutMigrationKey = 'project-kei.dashboard.compact-cards.v2';

const defaultAvatarVersion = 'pk100-20260730-defaults1';
const defaultAvatarRoot = '/dashboard/static/default-avatars';

export const panelVisualRegistry = Object.freeze({
  'feature-center': Object.freeze({ avatar: 'feature-center.png', alt: '功能中心组件插图' }),
  'configuration-readiness': Object.freeze({ avatar: 'configuration.png', alt: '配置就绪情况组件插图' }),
  'module-group-intelligence': Object.freeze({ avatar: 'intel-sources.png', alt: '每日情报来源与采集组件插图' }),
  'module-intel_sources': Object.freeze({ avatar: 'intel-sources.png', alt: '每日情报关注对象组件插图' }),
  'module-daily_briefing': Object.freeze({ avatar: 'briefing.png', alt: '今日情报组件插图' }),
  'module-conversation': Object.freeze({ avatar: 'llm.png', alt: '对话与 LLM 组件插图' }),
  'module-affection_memory': Object.freeze({ avatar: 'affection.png', alt: '好感度与长期记忆组件插图' }),
  'module-affection': Object.freeze({ avatar: 'affection.png', alt: '好感度系统组件插图' }),
  'module-long-term-memory': Object.freeze({ avatar: 'memory.png', alt: '长期记忆组件插图' }),
  'module-demon_slayer': Object.freeze({ avatar: 'demon.png', alt: '斩妖除魔组件插图' }),
  'module-fitness': Object.freeze({ avatar: 'fitness.png', alt: '健身打卡组件插图' }),
  'module-calendar': Object.freeze({ avatar: 'calendar.png', alt: '日历备忘录与修炼记录组件插图' }),
  'module-focus': Object.freeze({ avatar: 'module-focus.png', alt: '专注计时组件插图' }),
  'module-qq_bridge': Object.freeze({
    avatar: '/dashboard/assets/qq-launch.png',
    alt: 'QQ bridge 启动组件插图',
    force: true,
  }),
  'module-qq-daily-push': Object.freeze({ avatar: 'briefing-schedule.png', alt: '每日情报定时推送组件插图' }),
  'module-qq-life-support': Object.freeze({ avatar: 'life-support.png', alt: '生命维持系统组件插图' }),
  'module-group-voice': Object.freeze({ avatar: 'voice-pack.png', alt: '语音与 Voice Pack 功能插图' }),
});
const defaultOpenPanels = new Set();
const fallbackSummary = '点击标题展开完整功能与说明';
const previewImageTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
const previewImageMaxBytes = 8 * 1024 * 1024;
const avatarPreviewUrls = new WeakMap();
const avatarDefaultSources = new WeakMap();
const settingsItemLimit = 8;
const panelSettingNotes = Object.freeze({
  'feature-center': [
    '查看官方目录、已安装模块与 Core 固定模块',
    '生命周期写操作只在用户明确确认后执行',
  ],
});

function applyPanelVisualRegistration(section, panelId) {
  const registration = panelVisualRegistry[panelId];
  if (!registration) return;
  if (registration.force || !section.dataset.panelAvatar) {
    section.dataset.panelAvatar = registration.avatar.startsWith('/')
      ? registration.avatar
      : `${defaultAvatarRoot}/${registration.avatar}?v=${defaultAvatarVersion}`;
  }
  if (!section.dataset.panelAvatarAlt) {
    section.dataset.panelAvatarAlt = registration.alt;
  }
}

function readPanelState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(panelStorageKey) || '{}');
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => typeof value === 'boolean'),
    );
  } catch (_error) {
    return {};
  }
}

function writePanelState(state) {
  try {
    localStorage.setItem(panelStorageKey, JSON.stringify(state));
  } catch (_error) {
    // The dashboard remains usable when browser storage is unavailable.
  }
}

function migrateCompactGroupState(state) {
  try {
    if (localStorage.getItem(panelLayoutMigrationKey) === '1') return;
    Object.keys(state).forEach((panelId) => {
      state[panelId] = false;
    });
    [
      'module-group-intelligence',
      'module-group-voice',
      'module-qq_bridge',
      'module-qq-daily-push',
      'module-qq-life-support',
    ].forEach((panelId) => {
      state[panelId] = false;
    });
    writePanelState(state);
    localStorage.setItem(panelLayoutMigrationKey, '1');
  } catch (_error) {
    // A blocked localStorage still falls back to the closed-by-default layout.
  }
}

function renderAvatarSource(section, source, documentRoot) {
  const visual = section.querySelector(':scope > .module-shell-header .module-avatar-main');
  const label = visual?.querySelector?.('.module-avatar-picker-label');
  if (!visual) return false;

  if (visual.matches('img')) {
    if (!avatarDefaultSources.has(section)) {
      avatarDefaultSources.set(section, visual.getAttribute('src') || '');
    }
    visual.src = source;
  } else {
    const image = documentRoot.createElement('img');
    const nextLabel = label || documentRoot.createElement('span');
    image.className = 'module-avatar-preview';
    image.src = source;
    image.alt = '';
    image.draggable = false;
    nextLabel.className = 'module-avatar-picker-label';
    nextLabel.textContent = '更换图片';
    visual.classList.add('has-preview');
    visual.replaceChildren(image, nextLabel);
  }
  return true;
}

function applyAvatarBlob(section, blob, documentRoot) {
  const previousUrl = avatarPreviewUrls.get(section);
  if (previousUrl) URL.revokeObjectURL(previousUrl);
  const previewUrl = URL.createObjectURL(blob);
  avatarPreviewUrls.set(section, previewUrl);
  return renderAvatarSource(section, previewUrl, documentRoot);
}

function applyStoredAvatar(section, record, documentRoot) {
  const previousUrl = avatarPreviewUrls.get(section);
  if (previousUrl) URL.revokeObjectURL(previousUrl);
  avatarPreviewUrls.delete(section);
  const separator = record.url.includes('?') ? '&' : '?';
  return renderAvatarSource(
    section,
    `${record.url}${separator}v=${encodeURIComponent(record.updated_at || '')}`,
    documentRoot,
  );
}

function resetAvatarVisual(section, documentRoot) {
  const visual = section.querySelector(':scope > .module-shell-header .module-avatar-main');
  const previousUrl = avatarPreviewUrls.get(section);
  if (previousUrl) URL.revokeObjectURL(previousUrl);
  avatarPreviewUrls.delete(section);
  if (!visual) return;
  if (visual.matches('img')) {
    const defaultSource = avatarDefaultSources.get(section);
    if (defaultSource !== undefined) visual.src = defaultSource;
    return;
  }
  const label = documentRoot.createElement('span');
  label.className = 'module-avatar-picker-label';
  label.textContent = '添加图片';
  visual.classList.remove('has-preview');
  visual.replaceChildren(label);
}

function configureAvatarInput(section, input, documentRoot) {
  input.type = 'file';
  input.className = 'module-avatar-picker-input';
  input.accept = 'image/png,image/jpeg,image/webp';
  input.hidden = true;
  input.setAttribute('data-panel-avatar-input', 'true');
  if (input.dataset.panelAvatarReady) return input;
  input.dataset.panelAvatarReady = 'true';
  input.addEventListener('change', async () => {
    const file = input.files?.[0];
    if (!file) return;
    if (!previewImageTypes.has(file.type) || file.size > previewImageMaxBytes) {
      input.dataset.panelAvatarMessage = '请选择 8MB 内的 PNG、JPG 或 WebP';
      input.dispatchEvent(new Event('panel-avatar-preview'));
      return;
    }
    if (!applyAvatarBlob(section, file, documentRoot)) {
      input.dataset.panelAvatarMessage = '当前组件没有可用的头像位置';
      input.dispatchEvent(new Event('panel-avatar-preview'));
      return;
    }
    try {
      const record = await savePanelAvatar(section.dataset.panelId, file);
      applyStoredAvatar(section, record, documentRoot);
      input.dataset.panelAvatarMessage = '已保存为本机自定义图片；项目默认素材不会改变。';
    } catch (_error) {
      input.dataset.panelAvatarMessage = '头像已在本页预览，但上传失败；刷新后会恢复原图。';
    }
    input.value = '';
    input.dispatchEvent(new Event('panel-avatar-preview'));
  });
  return input;
}

function ensureAvatarInput(section, documentRoot) {
  const existing = section.querySelector('[data-panel-avatar-input]');
  if (existing) return configureAvatarInput(section, existing, documentRoot);
  const input = configureAvatarInput(section, documentRoot.createElement('input'), documentRoot);
  section.querySelector(':scope > .module-shell-header')?.append(input);
  return input;
}

async function restoreAvatar(section, documentRoot, input) {
  try {
    const record = await loadPanelAvatar(section.dataset.panelId);
    if (!record) return;
    if (applyStoredAvatar(section, record, documentRoot)) {
      input.dataset.panelAvatarMessage = '已恢复本机保存的自定义图片。';
      input.dispatchEvent(new Event('panel-avatar-preview'));
    }
  } catch (_error) {
    input.dataset.panelAvatarMessage = '组件头像读取失败；当前页面已使用默认图片。';
    input.dispatchEvent(new Event('panel-avatar-preview'));
  }
}

function buildAvatar(section, documentRoot) {
  const source = section.dataset.panelAvatar;
  if (source) {
    const image = documentRoot.createElement('img');
    image.className = 'module-avatar module-avatar-main';
    image.src = source;
    image.alt = section.dataset.panelAvatarAlt || '';
    image.width = 64;
    image.height = 64;
    image.draggable = false;
    return image;
  }

  const picker = documentRoot.createElement('div');
  const button = documentRoot.createElement('button');
  const label = documentRoot.createElement('span');
  const input = documentRoot.createElement('input');

  picker.className = 'module-avatar-picker-wrap';
  button.type = 'button';
  button.className = 'module-avatar module-avatar-main module-avatar-placeholder module-avatar-picker';
  button.setAttribute('aria-label', '选择本地图片并保存为此组件头像');
  button.title = '图片将上传到本机 Project Kei，作为控制台 UI 素材保存';
  label.className = 'module-avatar-picker-label';
  label.textContent = '添加图片';
  configureAvatarInput(section, input, documentRoot);

  button.addEventListener('click', () => input.click());

  button.append(label);
  picker.append(button, input);
  return picker;
}

function enhanceQQLaunchVisual(section, header, panelId, documentRoot) {
  if (panelId !== 'module-qq_bridge') return;
  const original = header.querySelector(':scope > .module-avatar-main');
  const start = section.querySelector(':scope > .module-feature-body > button');
  if (!original || !start || original.matches('.qq-launch-button')) return;

  const button = documentRoot.createElement('button');
  const image = documentRoot.createElement('img');
  const label = documentRoot.createElement('span');
  button.type = 'button';
  button.className = 'qq-launch-button module-avatar-main';
  button.setAttribute('aria-label', '启动 QQ Bridge');
  button.title = '启动 QQ Bridge';
  image.src = section.dataset.panelAvatar;
  image.alt = section.dataset.panelAvatarAlt || 'QQ 功能启动';
  image.draggable = false;
  label.className = 'qq-launch-label';
  label.textContent = '启动 QQ Bridge';
  button.append(image, label);

  const syncDisabled = () => {
    button.disabled = start.disabled;
  };
  button.addEventListener('click', () => {
    if (!button.disabled) start.click();
  });
  start.classList.add('qq-launch-fallback-control');
  const Observer = documentRoot.defaultView?.MutationObserver;
  if (Observer) {
    new Observer(syncDisabled).observe(start, {
      attributes: true,
      attributeFilter: ['disabled'],
    });
  }
  original.replaceWith(button);
  syncDisabled();
}

function buildGeneratedHeader(section, heading, documentRoot) {
  const summarySource = section.querySelector(':scope > p.hint');
  const header = documentRoot.createElement('div');
  const headingGroup = documentRoot.createElement('div');
  const summary = documentRoot.createElement('p');

  header.className = 'module-shell-header module-shell-header-generated';
  headingGroup.className = 'module-shell-heading';
  summary.className = 'module-shell-summary';
  summary.textContent = section.dataset.panelSummary
    || summarySource?.textContent.trim()
    || fallbackSummary;

  header.append(buildAvatar(section, documentRoot), headingGroup);
  headingGroup.append(heading, summary);
  section.insertBefore(header, section.firstChild);
  return header;
}

function normalizedText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function labelWithoutControlText(label) {
  const copy = label.cloneNode(true);
  copy.querySelectorAll('input, select, textarea, button').forEach((node) => node.remove());
  return normalizedText(copy.textContent);
}

function collectSettingTargets(section) {
  const result = [];
  const seen = new Set();
  section.querySelectorAll('label.field, label.switch-row, [data-setting-label]').forEach((item) => {
    const target = item.matches('input, select, textarea, button')
      ? item
      : item.querySelector('input, select, textarea, button');
    if (!target || target.closest('.module-settings-panel')) return;
    const label = normalizedText(item.dataset.settingLabel)
      || (item.matches('label') ? labelWithoutControlText(item) : '')
      || normalizedText(target.getAttribute('aria-label'))
      || normalizedText(target.name)
      || normalizedText(target.id);
    if (!label || seen.has(label)) return;
    seen.add(label);
    result.push({ label, target });
  });
  return result;
}

function declaredSettingNotes(section, panelId) {
  const moduleRoot = section.querySelector(':scope > .module-mount-content');
  const declared = section.dataset.panelSettings || moduleRoot?.dataset.panelSettings || '';
  const values = declared.split('|').map(normalizedText).filter(Boolean);
  return values.length ? values : panelSettingNotes[panelId] || [];
}

function buildSettingsControl(section, header, panelId, panelLabel, documentRoot, requestOpen) {
  let actions = header.querySelector(':scope > .module-shell-actions');
  if (!actions) {
    actions = documentRoot.createElement('div');
    actions.className = 'module-shell-actions';
    header.append(actions);
  }

  const button = documentRoot.createElement('button');
  const icon = documentRoot.createElement('span');
  const label = documentRoot.createElement('span');
  const panel = documentRoot.createElement('aside');
  const heading = documentRoot.createElement('div');
  const title = documentRoot.createElement('strong');
  const description = documentRoot.createElement('p');
  const avatarTools = documentRoot.createElement('div');
  const avatarButton = documentRoot.createElement('button');
  const avatarResetButton = documentRoot.createElement('button');
  const avatarHint = documentRoot.createElement('span');
  const items = documentRoot.createElement('div');
  const safeId = panelId.replace(/[^a-zA-Z0-9_-]/g, '-');
  const avatarInput = ensureAvatarInput(section, documentRoot);

  button.type = 'button';
  button.className = 'secondary compact-action module-settings-button';
  button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-controls', `panel-settings-${safeId}`);
  button.setAttribute('aria-label', `${panelLabel || panelId}：功能设置`);
  icon.className = 'module-settings-icon';
  icon.textContent = '⚙';
  icon.setAttribute('aria-hidden', 'true');
  label.textContent = '设置';
  button.append(icon, label);
  actions.append(button);

  panel.id = `panel-settings-${safeId}`;
  panel.className = 'module-settings-panel';
  panel.setAttribute('aria-labelledby', `panel-settings-title-${safeId}`);
  panel.hidden = true;
  heading.className = 'module-settings-panel-heading';
  title.id = `panel-settings-title-${safeId}`;
  title.textContent = '功能设置';
  description.textContent = '这里汇总当前组件已有选项；定位、展开和头像设置不会调用业务接口。';
  avatarTools.className = 'module-avatar-settings';
  avatarButton.type = 'button';
  avatarButton.className = 'secondary compact-action module-avatar-setting';
  avatarButton.textContent = '设置本机图片';
  avatarButton.setAttribute('aria-label', `${panelLabel || panelId}：保存本机自定义图片`);
  avatarResetButton.type = 'button';
  avatarResetButton.className = 'secondary compact-action module-avatar-reset';
  avatarResetButton.textContent = '恢复默认';
  avatarResetButton.setAttribute('aria-label', `${panelLabel || panelId}：删除已上传头像并恢复默认`);
  avatarHint.className = 'module-avatar-setting-hint';
  avatarHint.setAttribute('role', 'status');
  avatarHint.setAttribute('aria-live', 'polite');
  avatarHint.textContent = '支持 PNG、JPG、WebP，最大 8MB；保存为本机自定义图片，不会修改项目默认素材。';
  avatarButton.addEventListener('click', () => avatarInput.click());
  avatarResetButton.addEventListener('click', async () => {
    try {
      await deletePanelAvatar(panelId);
      resetAvatarVisual(section, documentRoot);
      avatarHint.textContent = '已删除本机自定义图片并恢复项目默认素材。';
    } catch (_error) {
      avatarHint.textContent = '未能删除上传头像，请确认本机 API 正常运行。';
    }
  });
  avatarInput.addEventListener('panel-avatar-preview', () => {
    avatarHint.textContent = avatarInput.dataset.panelAvatarMessage;
  });
  avatarTools.append(avatarButton, avatarResetButton, avatarHint);
  items.className = 'module-settings-items';
  heading.append(title, description);
  panel.append(heading, avatarTools, items);
  header.insertAdjacentElement('afterend', panel);

  const render = () => {
    items.replaceChildren();
    const targets = collectSettingTargets(section);
    targets.slice(0, settingsItemLimit).forEach(({ label: itemLabel, target }) => {
      const link = documentRoot.createElement('button');
      link.type = 'button';
      link.className = 'secondary compact-action module-setting-link';
      link.textContent = itemLabel;
      link.addEventListener('click', () => {
        target.closest('details')?.setAttribute('open', '');
        target.scrollIntoView({ block: 'center' });
        target.focus({ preventScroll: true });
      });
      items.append(link);
    });
    if (targets.length > settingsItemLimit) {
      const remainder = documentRoot.createElement('span');
      remainder.className = 'module-settings-more';
      remainder.textContent = `另有 ${targets.length - settingsItemLimit} 项，请在完整功能区继续查看`;
      items.append(remainder);
    }
    if (targets.length) return;

    const notes = declaredSettingNotes(section, panelId);
    if (!notes.length) {
      const empty = documentRoot.createElement('p');
      empty.className = 'module-settings-empty';
      empty.textContent = '该组件暂未声明独立设置；原有功能仍保留在详情区。';
      items.append(empty);
      return;
    }
    notes.forEach((note) => {
      const item = documentRoot.createElement('span');
      item.className = 'module-setting-note';
      item.textContent = note;
      items.append(item);
    });
  };

  const setSettingsOpen = (open) => {
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    label.textContent = open ? '关闭设置' : '设置';
    section.classList.toggle('module-settings-open', open);
    if (open) render();
  };
  button.addEventListener('click', () => {
    const next = panel.hidden;
    if (next) requestOpen();
    setSettingsOpen(next);
  });
  void restoreAvatar(section, documentRoot, avatarInput);

  return Object.freeze({
    close: () => setSettingsOpen(false),
  });
}

function buildPanelLayout(section, header, documentRoot) {
  if (header.querySelector(':scope > .module-shell-detail')) return;
  const heading = header.querySelector(':scope > .module-shell-heading');
  const actions = header.querySelector(':scope > .module-shell-actions');
  const settingsPanel = section.querySelector(':scope > .module-settings-panel');
  const contentNodes = Array.from(section.children).filter(
    (node) => node !== header && node !== settingsPanel,
  );
  const detail = documentRoot.createElement('div');
  const content = documentRoot.createElement('div');

  header.classList.add('module-shell-layout');
  detail.className = 'module-shell-detail';
  content.className = 'module-shell-content';
  if (heading) detail.append(heading);
  if (actions) detail.append(actions);
  if (settingsPanel) detail.append(settingsPanel);
  content.append(...contentNodes);
  if (contentNodes.length) detail.append(content);
  header.append(detail);
}

export function setupDashboardPanels(root = document) {
  const saved = readPanelState();
  migrateCompactGroupState(saved);
  root.querySelectorAll(
    'main > section.section, #dashboard-module-mounts > section.section:not(.module-panel-host), '
      + '#dashboard-module-mounts .module-owned-panels > section.section',
  ).forEach((section, index) => {
    if (section.dataset.panelReady) return;
    let structuredHeader = section.querySelector(':scope > .module-shell-header');
    let heading = structuredHeader
      ? structuredHeader.querySelector('.module-shell-heading > h2')
      : section.querySelector(':scope > h2');
    if (!heading) return;

    const panelId = section.dataset.panelId || `panel-${index}`;
    section.dataset.panelId = panelId;
    section.dataset.panelReady = 'true';
    applyPanelVisualRegistration(section, panelId);
    if (!structuredHeader) {
      structuredHeader = buildGeneratedHeader(section, heading, root);
      heading = structuredHeader.querySelector('.module-shell-heading > h2');
    }
    enhanceQQLaunchVisual(section, structuredHeader, panelId, root);
    section.classList.add('has-module-shell-header');

    const label = heading.textContent.trim();
    const toggle = root.createElement('button');
    const name = root.createElement('span');
    const state = root.createElement('span');
    toggle.type = 'button';
    toggle.className = 'section-toggle module-shell-toggle';
    toggle.setAttribute('aria-label', `${label}：展开或收起`);
    name.textContent = label;
    state.className = 'panel-state';
    toggle.append(name, state);
    heading.replaceChildren(toggle);

    const setOpen = (open, shouldSave = false) => {
      section.classList.toggle('collapsed', !open);
      toggle.setAttribute('aria-expanded', String(open));
      state.textContent = open ? '收起详情 ▴' : '展开详情 ▾';
      if (shouldSave) {
        saved[panelId] = open;
        writePanelState(saved);
      }
    };
    const initial = Object.prototype.hasOwnProperty.call(saved, panelId)
      ? saved[panelId]
      : defaultOpenPanels.has(panelId);
    setOpen(initial);
    const settings = buildSettingsControl(
      section,
      structuredHeader,
      panelId,
      label,
      root,
      () => setOpen(true, true),
    );
    buildPanelLayout(section, structuredHeader, root);
    toggle.addEventListener('click', () => {
      const open = section.classList.contains('collapsed');
      if (!open) settings.close();
      setOpen(open, true);
    });
  });
}
