let mountedRoot = null;

function addRow(root, grid, labelText, valueText) {
  const card = root.ownerDocument.createElement('div');
  const label = root.ownerDocument.createElement('span');
  const value = root.ownerDocument.createElement('strong');
  card.className = 'stat-chip';
  label.className = 'label';
  label.textContent = labelText;
  value.textContent = valueText;
  card.append(label, value);
  grid.append(card);
}

function registrationLabel(status) {
  const labels = {
    unregistered: '尚未登记',
    registered_existing: '已有安装 · 未验证归档',
    installed_verified: '固定归档已验证',
    invalid: '登记需要处理',
  };
  return labels[status?.registration_state] || '状态未知';
}

function renderRegistration(root, status) {
  const statusText = root.querySelector('[data-engine-role="status"]');
  const button = root.querySelector('[data-engine-role="select"]');
  const displayName = status?.display_name ? `（${status.display_name}）` : '';
  statusText.textContent = `本机引擎：${registrationLabel(status)}${displayName}`;
  button.disabled = status?.selection_in_progress === true || status?.can_select_existing !== true;
  button.textContent = status?.selection_in_progress === true
    ? '正在选择…'
    : status?.registration_state === 'unregistered'
      ? '选择已有引擎目录'
      : '重新选择已有引擎目录';
}

function buildPanel(root, context) {
  const hint = root.ownerDocument.createElement('p');
  const grid = root.ownerDocument.createElement('div');
  const status = root.ownerDocument.createElement('p');
  const select = root.ownerDocument.createElement('button');
  const boundary = root.ownerDocument.createElement('p');
  hint.className = 'hint';
  grid.className = 'module-grid';
  status.className = 'detail hint';
  status.dataset.engineRole = 'status';
  select.type = 'button';
  select.dataset.engineRole = 'select';
  select.textContent = '选择已有引擎目录';
  boundary.className = 'detail hint';
  hint.textContent = '此安装项只提供 Project Kei 的 GPT-SoVITS Provider 与受控 sidecar adapter。';
  boundary.textContent = '按钮只打开本机 Windows 目录选择器。页面不接收路径；取消不会写入。所选目录只检查固定入口和固定标记，不执行脚本、不安装依赖，也不读取或移动模型、权重和参考音频。未带 Project Kei 固定标记的已有安装会明确显示为“未验证归档”。';
  addRow(root, grid, 'Provider 包', context.module.installed_version || '未知');
  addRow(root, grid, '生命周期', context.module.enabled ? '已启用' : '已安装 · 未启用');
  addRow(root, grid, '外部引擎', '不随模块包分发');
  addRow(root, grid, '固定端点', '127.0.0.1:9880');
  const operation = context.module.last_operation;
  if (operation) {
    addRow(
      root,
      grid,
      '最近操作',
      [operation.action, operation.status].filter(Boolean).join(' · ') || '已记录',
    );
  }
  root.replaceChildren(hint, grid, status, select, boundary);
}

async function refreshRegistration(root, context) {
  const status = await context.request('/api/v1/gpt-sovits-engine/status');
  if (mountedRoot === root) renderRegistration(root, status);
}

export async function mount(context) {
  if (!context?.root || !context.module || typeof context.request !== 'function') {
    throw new TypeError('GPT-SoVITS Provider 面板缺少受限模块上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  buildPanel(root, context);
  root.querySelector('[data-engine-role="select"]').addEventListener('click', async () => {
    const button = root.querySelector('[data-engine-role="select"]');
    button.disabled = true;
    button.textContent = '正在选择…';
    try {
      const result = await context.request('/api/v1/gpt-sovits-engine/select-existing', {method: 'POST'});
      if (mountedRoot === root) renderRegistration(root, result);
      if (result.action === 'registered' && typeof context.notify === 'function') {
        context.notify('GPT-SoVITS 本机引擎已登记。', 'success');
      }
    } catch (error) {
      if (typeof context.notify === 'function') {
        context.notify(error?.message || 'GPT-SoVITS 引擎目录登记失败。', 'error');
      }
      await refreshRegistration(root, context);
    }
  });
  await refreshRegistration(root, context);
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
