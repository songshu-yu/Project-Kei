let mountedRoot = null;
let pollTimer = null;
let pollCount = 0;

function el(root, role) {
  return root.querySelector(`[data-briefing-role="${role}"]`);
}

function button(root, text, role, className = '') {
  const value = root.ownerDocument.createElement('button');
  value.type = 'button';
  value.textContent = text;
  value.dataset.briefingRole = role;
  value.className = className;
  return value;
}

function build(root) {
  const intro = root.ownerDocument.createElement('p');
  const status = root.ownerDocument.createElement('div');
  const actions = root.ownerDocument.createElement('div');
  const details = root.ownerDocument.createElement('div');
  intro.className = 'hint';
  intro.textContent = '读取当天缓存不会联网；生成与强制刷新只在明确点击后执行。';
  status.className = 'detail';
  status.dataset.briefingRole = 'status';
  actions.className = 'module-actions';
  actions.append(
    button(root, '读取当天缓存', 'read', 'secondary'),
    button(root, '生成今日情报', 'generate'),
    button(root, '强制刷新', 'refresh', 'secondary'),
  );
  details.className = 'detail hint';
  details.dataset.briefingRole = 'details';
  root.replaceChildren(intro, status, actions, details);
}

function render(root, result, generation = null) {
  const ready = Boolean(result?.ready);
  el(root, 'status').textContent = ready
    ? `今日缓存已就绪 · ${result.date || ''}`
    : '今日缓存尚未生成';
  const coverage = result?.coverage && typeof result.coverage === 'object'
    ? Object.entries(result.coverage)
      .map(([source, value]) => `${source}: ${value?.status || 'unknown'}`)
      .join(' · ')
    : '';
  const phase = generation?.state === 'running'
    ? `处理中：${generation.phase || 'collecting'}`
    : '';
  el(root, 'details').textContent = [phase, coverage].filter(Boolean).join(' · ')
    || '缺少可选来源包时会显示未配置，其余已安装来源仍可继续。';
}

function stopPolling() {
  if (pollTimer !== null) globalThis.clearTimeout(pollTimer);
  pollTimer = null;
  pollCount = 0;
}

async function readAndRender(context, root) {
  const [today, generation] = await Promise.all([
    context.request('/api/v1/briefing/today'),
    context.request('/api/v1/briefing/generation-status'),
  ]);
  if (mountedRoot === root) render(root, today, generation);
  return generation;
}

function pollWhileRunning(context, root) {
  stopPolling();
  const tick = async () => {
    if (mountedRoot !== root || pollCount >= 180) {
      stopPolling();
      return;
    }
    pollCount += 1;
    try {
      const generation = await readAndRender(context, root);
      if (generation?.state !== 'running') {
        stopPolling();
        return;
      }
    } catch (error) {
      context.notify(`读取生成状态失败：${error.message}`, 'error');
      stopPolling();
      return;
    }
    pollTimer = globalThis.setTimeout(tick, 1000);
  };
  void tick();
}

async function mutate(context, root, path, body) {
  ['generate', 'refresh'].forEach((role) => {
    el(root, role).disabled = true;
  });
  pollWhileRunning(context, root);
  try {
    const result = await context.request(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (mountedRoot === root) render(root, result);
    context.notify(result.ready ? '每日情报已更新。' : '每日情报尚未就绪。');
  } catch (error) {
    context.notify(`每日情报操作失败：${error.message}`, 'error');
  } finally {
    stopPolling();
    if (mountedRoot === root) {
      ['generate', 'refresh'].forEach((role) => {
        el(root, role).disabled = false;
      });
      await readAndRender(context, root);
    }
  }
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('每日情报面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  build(root);
  el(root, 'read').addEventListener('click', async () => {
    try {
      await readAndRender(context, root);
    } catch (error) {
      context.notify(`读取缓存失败：${error.message}`, 'error');
    }
  });
  el(root, 'generate').addEventListener('click', () => {
    void mutate(context, root, '/api/v1/briefing/generate', {
      refresh: false,
      rewrite: true,
      rewrite_refresh: false,
      patch_missing: true,
      lookback: 24,
    });
  });
  el(root, 'refresh').addEventListener('click', () => {
    void mutate(context, root, '/api/v1/briefing/refresh', {
      refresh: true,
      rewrite: true,
      rewrite_refresh: true,
      patch_missing: true,
      lookback: 24,
    });
  });
  const generation = await readAndRender(context, root);
  if (generation?.state === 'running') pollWhileRunning(context, root);
}

export async function unmount() {
  stopPolling();
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
