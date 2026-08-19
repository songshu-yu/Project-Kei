let mountedRoot = null;
let currentContext = null;

function node(root, tag, text = '') {
  const element = root.ownerDocument.createElement(tag);
  element.textContent = text;
  return element;
}

function button(root, label, action, tone = '') {
  const control = node(root, 'button', label);
  control.type = 'button';
  control.dataset.voicePackAction = action;
  if (tone) control.className = tone;
  return control;
}

function describeEngine(pack) {
  const provider = pack?.engine?.provider || '未知';
  const protocol = pack?.engine?.protocol_version || '';
  return protocol ? `${provider} / ${protocol}` : provider;
}

function buildRow(root, pack) {
  const row = node(root, 'article');
  const title = node(root, 'h3', `${pack.name} · ${pack.id}@${pack.version}`);
  const meta = node(
    root,
    'p',
    `${describeEngine(pack)} · ${(pack.supported_languages || []).join(', ') || '语言未知'}`,
  );
  const state = node(
    root,
    'p',
    pack.active ? '当前使用' : pack.enabled ? '已启用' : '已停用',
  );
  const actions = node(root, 'div');
  row.className = 'voice-pack-card';
  meta.className = 'hint';
  state.className = 'status-pill';
  actions.className = 'module-shell-actions';

  if (!pack.enabled) actions.append(button(root, '启用', 'enable'));
  if (pack.enabled && !pack.active) actions.append(button(root, '选择', 'select'));
  if (pack.enabled) actions.append(button(root, '停用', 'disable', 'secondary'));
  actions.append(button(root, '注销记录', 'unregister', 'secondary'));
  for (const control of actions.querySelectorAll('button')) {
    control.addEventListener('click', () => runAction(pack, control));
  }
  row.append(title, meta, state, actions);
  return row;
}

function render(snapshot) {
  if (!mountedRoot) return;
  const list = mountedRoot.querySelector('[data-voice-pack-role="list"]');
  list.replaceChildren();
  if (!snapshot.packs?.length) {
    list.append(node(mountedRoot, 'p', '尚未登记 Voice Pack。Core 与文字功能仍可正常使用。'));
    return;
  }
  list.append(...snapshot.packs.map((pack) => buildRow(mountedRoot, pack)));
}

async function refresh() {
  const snapshot = await currentContext.request('/api/v1/voice-packs');
  render(snapshot);
}

async function runAction(pack, control) {
  const action = control.dataset.voicePackAction;
  if (action === 'unregister') {
    const confirmed = globalThis.confirm?.(
      `仅注销 ${pack.id}@${pack.version} 的注册记录；源模型和参考音频不会删除。继续吗？`,
    );
    if (!confirmed) return;
  }
  control.disabled = true;
  try {
    const path = `/api/v1/voice-packs/${encodeURIComponent(pack.id)}/${encodeURIComponent(pack.version)}`;
    await currentContext.request(
      action === 'unregister' ? path : `${path}/${action}`,
      {method: action === 'unregister' ? 'DELETE' : 'POST'},
    );
    currentContext.notify(`Voice Pack ${action} 操作已完成。`);
    await refresh();
  } catch (error) {
    currentContext.notify(`Voice Pack 操作失败：${error.message}`, 'error');
    await refresh();
  }
}

function buildPanel(root) {
  const intro = node(
    root,
    'p',
    '管理已校验的本机声音包。Voice Pack、LLM Profile 与 GPT-SoVITS Engine 相互独立。',
  );
  const importBox = node(root, 'form');
  const label = node(root, 'label', '高级本机导入路径');
  const input = node(root, 'input');
  const submit = button(root, '导入并校验', 'import');
  const hint = node(
    root,
    'p',
    '仅接受当前电脑上的明确目录或 ZIP；路径不会写入浏览器存储或出现在 API 响应中。',
  );
  const list = node(root, 'div');

  intro.className = 'hint';
  importBox.className = 'schedule-grid';
  label.className = 'field';
  input.type = 'text';
  input.autocomplete = 'off';
  input.placeholder = '本机 Voice Pack ZIP 或目录';
  input.dataset.voicePackRole = 'package-path';
  hint.className = 'hint';
  list.className = 'module-grid';
  list.dataset.voicePackRole = 'list';
  label.append(input);
  importBox.append(label, submit);
  importBox.addEventListener('submit', async (event) => {
    event.preventDefault();
    const packagePath = input.value.trim();
    if (!packagePath) {
      currentContext.notify('请输入明确的本机 Voice Pack 路径。', 'error');
      return;
    }
    submit.disabled = true;
    try {
      await currentContext.request('/api/v1/voice-packs/import', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({package_path: packagePath}),
      });
      input.value = '';
      currentContext.notify('Voice Pack 已导入并完成校验。');
      await refresh();
    } catch (error) {
      currentContext.notify(`Voice Pack 导入失败：${error.message}`, 'error');
    } finally {
      submit.disabled = false;
    }
  });
  root.replaceChildren(intro, importBox, hint, list);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('Voice Pack 面板缺少受限挂载上下文');
  }
  await unmount();
  mountedRoot = context.root;
  currentContext = context;
  buildPanel(mountedRoot);
  await refresh();
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
  currentContext = null;
}
