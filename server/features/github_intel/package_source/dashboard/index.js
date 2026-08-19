let mountedRoot = null;

function appendRow(root, labelText, valueText) {
  const row = root.ownerDocument.createElement('div');
  const label = root.ownerDocument.createElement('span');
  const value = root.ownerDocument.createElement('strong');
  row.className = 'stat-chip';
  label.className = 'label';
  label.textContent = labelText;
  value.textContent = valueText;
  row.append(label, value);
  root.append(row);
}

export async function mount(context) {
  if (!context?.root) {
    throw new TypeError('GitHub 情报面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;

  const hint = root.ownerDocument.createElement('p');
  const summary = root.ownerDocument.createElement('div');
  hint.className = 'hint';
  hint.textContent = '关注用户和仓库由“情报来源”模块统一管理；只有显式生成或刷新每日情报时才访问公开 GitHub API。';
  summary.className = 'module-grid';
  appendRow(summary, '用户活动', '公开事件');
  appendRow(summary, '仓库更新', 'Release');
  appendRow(summary, '本地存储', '不保存名单或采集响应');
  root.replaceChildren(hint, summary);
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
