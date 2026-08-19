const SOURCE_SECTIONS = [
  {
    target: 'intel_sources',
    title: '来源配置总览',
    description: '各来源的关注对象已移入对应子页；这里仅保留尚未单独展示的 YouTube 来源。',
    fields: [
      ['youtube_channel_ids', 'YouTube Channel ID', '每行一个以 UC 开头的 Channel ID。'],
    ],
  },
  {
    target: 'x_monitor',
    title: 'X / Nitter 关注对象',
    description: '只维护账号名单；读取、切换和保存不会自动联网。',
    fields: [
      ['twitter_users', 'X / Nitter 用户', '每行一个用户名，可带 @。'],
      ['money_twitter_users', '信息差 X 用户', '每行一个用户名，可带 @。'],
    ],
  },
  {
    target: 'bilibili',
    title: 'B 站关注对象',
    description: '这里只维护 UID；Cookie 参数仍由下方 B 站模块独立管理。',
    fields: [
      ['bilibili_uids', 'B 站 UID', '每行一个正整数 UID。'],
    ],
  },
  {
    target: 'github_intel',
    title: 'GitHub 关注对象',
    description: '用户与仓库名单分别保存，页面操作不会触发采集。',
    fields: [
      ['github_users', 'GitHub 用户', '每行一个 GitHub 用户名。'],
      ['github_repos', 'GitHub 仓库', '每行一个 owner/repository。'],
    ],
  },
  {
    target: 'papers',
    title: '论文作者配置',
    description: '作者分组只影响后续显式论文采集，不会在页面加载时访问外部来源。',
    fields: [
      ['paper_priority_authors', '论文优先作者', '每行一个作者名。'],
      ['paper_secondary_authors', '论文常规作者', '每行一个作者名。'],
      ['paper_ai_authors', '论文 AI 作者', '每行一个作者名。'],
    ],
  },
];

const SOURCE_GROUPS = SOURCE_SECTIONS.flatMap(section => section.fields);

let mountedRoot = null;
let mountedContext = null;
let fieldControls = new Map();
let statusNodes = [];
let saveButtons = [];
let reloadButtons = [];
let sectionNodes = [];

function create(root, tag, text = '') {
  const node = root.ownerDocument.createElement(tag);
  node.textContent = text;
  return node;
}

function setBusy(busy) {
  saveButtons.forEach(button => { button.disabled = busy; });
  reloadButtons.forEach(button => { button.disabled = busy; });
}

function valuesFromControl(control) {
  return control.value
    .split(/\r?\n/)
    .map(value => value.trim())
    .filter(Boolean);
}

function renderConfig(config) {
  for (const [field] of SOURCE_GROUPS) {
    const values = Array.isArray(config?.[field]) ? config[field] : [];
    fieldControls.get(field).value = values.join('\n');
  }
  const status = config?.using_local_override
      ? `已读取本机配置${config.updated_at ? ` · ${config.updated_at}` : ''}`
      : '当前使用默认来源；首次保存后会建立本机覆盖。';
  statusNodes.forEach(node => { node.textContent = status; });
}

async function loadConfig() {
  if (!mountedContext) return;
  setBusy(true);
  try {
    const config = await mountedContext.request('/api/v1/intel-sources');
    if (mountedContext) renderConfig(config);
  } catch (error) {
    mountedContext.notify(`读取来源配置失败：${error.message}`, 'error');
  } finally {
    setBusy(false);
  }
}

async function saveConfig() {
  if (!mountedContext) return;
  const payload = {};
  for (const [field] of SOURCE_GROUPS) {
    payload[field] = valuesFromControl(fieldControls.get(field));
  }
  setBusy(true);
  try {
    const config = await mountedContext.request('/api/v1/intel-sources', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (mountedContext) {
      renderConfig(config);
      mountedContext.notify('来源配置已保存；未触发资料查询、采集或缓存刷新。');
    }
  } catch (error) {
    mountedContext.notify(`保存来源配置失败：${error.message}`, 'error');
  } finally {
    setBusy(false);
  }
}

function buildSourceSection(root, section) {
  const container = create(root, 'section');
  const heading = create(root, 'h3', section.title);
  const hint = create(
    root,
    'p',
    section.description,
  );
  const form = create(root, 'div');
  const actions = create(root, 'div');
  const saveButton = create(root, 'button', '保存此来源配置');
  const reloadButton = create(root, 'button', '重新读取');
  const statusNode = create(root, 'div');
  container.className = 'intel-source-config-section';
  container.dataset.configOwner = 'intel_sources';
  container.dataset.moduleConfigTarget = section.target;
  hint.className = 'hint';
  form.className = 'module-grid';
  actions.className = 'toolbar-actions';

  for (const [field, labelText, helpText] of section.fields) {
    const label = create(root, 'label');
    const title = create(root, 'strong', labelText);
    const help = create(root, 'span', helpText);
    const control = create(root, 'textarea');
    label.className = 'field';
    help.className = 'hint';
    control.rows = 4;
    control.dataset.intelSourcesField = field;
    control.setAttribute('aria-label', labelText);
    label.append(title, help, control);
    form.append(label);
    fieldControls.set(field, control);
  }

  saveButton.type = 'button';
  saveButton.dataset.intelSourcesRole = 'save';
  reloadButton.type = 'button';
  reloadButton.className = 'secondary';
  reloadButton.dataset.intelSourcesRole = 'reload';
  statusNode.className = 'detail hint';
  statusNode.setAttribute('role', 'status');
  statusNode.dataset.intelSourcesRole = 'status';
  saveButton.addEventListener('click', saveConfig);
  reloadButton.addEventListener('click', loadConfig);
  actions.append(saveButton, reloadButton);
  container.append(heading, hint, form, actions, statusNode);
  saveButtons.push(saveButton);
  reloadButtons.push(reloadButton);
  statusNodes.push(statusNode);
  sectionNodes.push(container);
  return container;
}

function buildPanel(root) {
  const intro = create(
    root,
    'p',
    '关注对象配置已放入 X / Nitter、B 站、GitHub 和论文子页。顶部切换只读取已加载界面，不会联网。',
  );
  intro.className = 'hint';
  fieldControls = new Map();
  statusNodes = [];
  saveButtons = [];
  reloadButtons = [];
  sectionNodes = [];
  root.replaceChildren(intro, ...SOURCE_SECTIONS.map(section => buildSourceSection(root, section)));
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function' || typeof context.notify !== 'function') {
    throw new TypeError('情报来源面板缺少受限挂载上下文');
  }
  await unmount();
  mountedRoot = context.root;
  mountedContext = context;
  buildPanel(mountedRoot);
  await loadConfig();
}

export async function unmount() {
  const root = mountedRoot;
  const projectedSections = [...sectionNodes];
  mountedRoot = null;
  mountedContext = null;
  fieldControls = new Map();
  statusNodes = [];
  saveButtons = [];
  reloadButtons = [];
  sectionNodes = [];
  projectedSections.forEach(section => section.remove?.());
  if (root) root.replaceChildren();
}
