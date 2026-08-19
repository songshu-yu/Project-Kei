let mountedRoot = null;
let tickTimer = null;
let currentStatus = null;

function formatSeconds(value) {
  const seconds = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(seconds / 60);
  const remain = seconds % 60;
  const hours = Math.floor(minutes / 60);
  return hours
    ? `${hours} 小时 ${minutes % 60} 分 ${remain} 秒`
    : `${minutes} 分 ${remain} 秒`;
}

function element(root, role) {
  return root.querySelector(`[data-focus-role="${role}"]`);
}

function render(root, status) {
  const rows = [
    ['状态', status.active ? '进行中' : status.completed ? '已完成' : '空闲'],
    ['模式', status.label || '—'],
    ['剩余', status.active ? formatSeconds(status.remaining_seconds) : '—'],
    ['任务', status.task || '未填写'],
  ];
  const summary = element(root, 'summary');
  summary.replaceChildren(...rows.map(([label, value]) => {
    const card = root.ownerDocument.createElement('div');
    const name = root.ownerDocument.createElement('span');
    const detail = root.ownerDocument.createElement('strong');
    card.className = 'stat-chip';
    name.className = 'label';
    name.textContent = label;
    detail.textContent = value;
    card.append(name, detail);
    return card;
  }));
  element(root, 'status').textContent = status.message || '';
  element(root, 'start').disabled = Boolean(status.active);
  element(root, 'stop').disabled = !status.active;
}

function createField(root, labelText, control) {
  const label = root.ownerDocument.createElement('label');
  label.className = 'field';
  label.append(labelText, control);
  return label;
}

function buildPanel(root) {
  const hint = root.ownerDocument.createElement('p');
  const summary = root.ownerDocument.createElement('div');
  const controls = root.ownerDocument.createElement('div');
  const mode = root.ownerDocument.createElement('select');
  const minutes = root.ownerDocument.createElement('input');
  const task = root.ownerDocument.createElement('input');
  const start = root.ownerDocument.createElement('button');
  const stop = root.ownerDocument.createElement('button');
  const reset = root.ownerDocument.createElement('button');
  const status = root.ownerDocument.createElement('div');

  hint.className = 'hint';
  hint.textContent = '可启动番茄钟或专注模式；自定义分钟留空时使用模式默认时长。';
  summary.className = 'module-grid';
  summary.dataset.focusRole = 'summary';
  controls.className = 'schedule-grid';

  [['pomodoro', '番茄钟（25 分钟）'], ['focus', '专注模式（50 分钟）']]
    .forEach(([value, text]) => {
      const option = root.ownerDocument.createElement('option');
      option.value = value;
      option.textContent = text;
      mode.append(option);
    });
  mode.dataset.focusRole = 'mode';
  minutes.type = 'number';
  minutes.step = '1';
  minutes.placeholder = '例如 40';
  minutes.dataset.focusRole = 'minutes';
  task.type = 'text';
  task.placeholder = '例如：整理实验数据';
  task.dataset.focusRole = 'task';
  start.type = 'button';
  start.textContent = '开始专注';
  start.dataset.focusRole = 'start';
  stop.type = 'button';
  stop.className = 'secondary';
  stop.textContent = '停止计时';
  stop.dataset.focusRole = 'stop';
  reset.type = 'button';
  reset.className = 'secondary';
  reset.textContent = '重置专注记录';
  reset.dataset.focusRole = 'reset';
  status.className = 'detail hint';
  status.dataset.focusRole = 'status';

  controls.append(
    createField(root, '模式', mode),
    createField(root, '自定义分钟（可选）', minutes),
    createField(root, '当前任务（可选）', task),
    start,
    stop,
    reset,
  );
  root.replaceChildren(hint, summary, controls, status);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('focus 面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  buildPanel(root);

  const refresh = async () => {
    currentStatus = await context.request('/api/v1/focus/status');
    if (mountedRoot === root) render(root, currentStatus);
  };
  element(root, 'start').addEventListener('click', async () => {
    const rawMinutes = element(root, 'minutes').value.trim();
    const minutes = rawMinutes ? Number(rawMinutes) : null;
    if (rawMinutes && (!Number.isFinite(minutes) || minutes <= 0)) {
      context.notify('自定义分钟需要是大于 0 的数字。', 'error');
      return;
    }
    const button = element(root, 'start');
    button.disabled = true;
    try {
      const result = await context.request('/api/v1/focus/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          mode: element(root, 'mode').value,
          minutes,
          task: element(root, 'task').value.trim(),
          force: false,
          with_audio: false,
        }),
      });
      currentStatus = result;
      render(root, result);
      context.notify(result.message || '专注计时已开始。');
    } catch (error) {
      context.notify(`启动失败：${error.message}`, 'error');
      await refresh();
    }
  });
  element(root, 'stop').addEventListener('click', async () => {
    const button = element(root, 'stop');
    button.disabled = true;
    try {
      const result = await context.request('/api/v1/focus/stop', {method: 'POST'});
      currentStatus = result;
      render(root, result);
      context.notify(result.message || '专注计时已停止。');
    } catch (error) {
      context.notify(`停止失败：${error.message}`, 'error');
      await refresh();
    }
  });
  let resetArmed = false;
  element(root, 'reset').addEventListener('click', async () => {
    const button = element(root, 'reset');
    if (!resetArmed) {
      resetArmed = true;
      button.textContent = '再次点击确认清空';
      context.notify('再次点击将清空专注记录。', 'error');
      return;
    }
    button.disabled = true;
    try {
      await context.request('/api/v1/focus/reset', {method: 'POST'});
      resetArmed = false;
      button.textContent = '重置专注记录';
      button.disabled = false;
      context.notify('专注记录已重置。');
      await refresh();
    } catch (error) {
      button.disabled = false;
      context.notify(`重置失败：${error.message}`, 'error');
    }
  });

  await refresh();
  tickTimer = globalThis.setInterval(() => {
    if (!currentStatus?.active || mountedRoot !== root) return;
    currentStatus = {
      ...currentStatus,
      remaining_seconds: Math.max(0, Number(currentStatus.remaining_seconds) - 1),
    };
    render(root, currentStatus);
    if (currentStatus.remaining_seconds === 0) void refresh();
  }, 1000);
}

export async function unmount() {
  if (tickTimer !== null) globalThis.clearInterval(tickTimer);
  tickTimer = null;
  currentStatus = null;
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
