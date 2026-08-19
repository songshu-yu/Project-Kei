import { setupServiceStatusVisuals } from './status-visuals.js?v=pk100-20260730-modules1';

const serviceNames = Object.freeze({
  api: 'Project Kei API',
  asr: '语音识别 ASR',
  tts: '语音合成 GPT-SoVITS',
  llm: 'LLM 配置',
  qq: 'QQ 服务',
});

function serviceReady(key, value) {
  if (key === 'qq') return value?.process_running === true;
  return key === 'llm' ? value?.configured === true : value?.ok === true;
}

function serviceDetail(key, value) {
  if (key === 'qq') return '';
  return String(value?.error || value?.url || value?.base_url || '').slice(0, 180);
}

function createStatusVisual(documentRoot, state, ready, label) {
  const control = documentRoot.createElement('details');
  const summary = documentRoot.createElement('summary');
  const slot = documentRoot.createElement('span');
  const placeholder = documentRoot.createElement('span');
  const menu = documentRoot.createElement('div');
  const upload = documentRoot.createElement('button');
  const reset = documentRoot.createElement('button');

  control.className = 'service-status-visual';
  control.dataset.serviceVisualState = state;
  summary.setAttribute('aria-label', `${label}状态图片设置`);
  slot.className = 'service-status-visual-slot';
  placeholder.className = 'service-status-visual-placeholder';
  placeholder.setAttribute('aria-hidden', 'true');
  placeholder.textContent = ready ? '✓' : '!';
  menu.className = 'service-status-visual-menu';
  upload.type = 'button';
  upload.className = 'secondary compact-action';
  upload.dataset.serviceVisualUpload = '';
  upload.textContent = '设置本机图片';
  reset.type = 'button';
  reset.className = 'secondary compact-action';
  reset.dataset.serviceVisualReset = '';
  reset.textContent = '恢复默认';

  slot.append(placeholder);
  summary.append(slot);
  menu.append(upload, reset);
  control.append(summary, menu);
  return control;
}

function createServiceCard(documentRoot, key, value, control = {}, onStart = null, onStop = null) {
  const ready = serviceReady(key, value);
  const state = ready ? 'normal' : 'attention';
  const label = key === 'qq' ? (ready ? '启动' : '未启动') : (ready ? '正常' : '需要处理');
  const card = documentRoot.createElement('article');
  const copy = documentRoot.createElement('div');
  const name = documentRoot.createElement('div');
  const status = documentRoot.createElement('div');
  const detail = documentRoot.createElement('div');

  card.className = 'card service-status-card';
  card.dataset.serviceState = state;
  copy.className = 'service-status-copy';
  name.className = 'label';
  name.textContent = serviceNames[key] || key;
  status.className = 'value';
  status.style.color = ready ? 'var(--good)' : 'var(--warn)';
  status.textContent = label;
  detail.className = 'detail';
  detail.textContent = serviceDetail(key, value);
  copy.append(name, status, detail);
  card.append(createStatusVisual(documentRoot, state, ready, label), copy);
  if (control?.running === true) {
    if (control?.can_stop !== true || typeof onStop !== 'function') {
      const external = documentRoot.createElement('span');
      external.className = 'service-status-control service-control-state';
      external.textContent = '外部启动';
      external.title = '该进程不是由当前控制台启动，不能从这里关闭。';
      external.setAttribute('role', 'status');
      card.append(external);
      return card;
    }
    const stop = documentRoot.createElement('button');
    stop.type = 'button';
    stop.className = 'secondary compact-action service-status-control';
    stop.textContent = '关闭服务';
    stop.addEventListener('click', () => onStop(key));
    card.append(stop);
  } else if (
    (key === 'asr' || key === 'tts')
    && control?.state === 'ready'
    && typeof onStart === 'function'
  ) {
    const start = documentRoot.createElement('button');
    start.type = 'button';
    start.className = 'secondary compact-action service-status-control';
    start.textContent = '启动服务';
    start.title = '在后台启动，不打开调试窗口。';
    start.addEventListener('click', () => onStart(key));
    card.append(start);
  }
  return card;
}

export function renderCoreStatus(
  payload,
  documentRoot = document,
  qqStatus = {},
  voiceRuntime = {},
  onStart = null,
  onStop = null,
) {
  const services = documentRoot.querySelector('#services');
  const overall = documentRoot.querySelector('#overall');
  const dot = documentRoot.querySelector('#overall-dot');
  const updated = documentRoot.querySelector('#updated');
  if (!services || !overall || !dot || !updated) return;

  const values = payload?.services && typeof payload.services === 'object'
    ? payload.services
    : {};
  const keys = Object.keys(serviceNames).filter((key) => key !== 'qq' && values[key]);
  const readyCount = keys.filter((key) => serviceReady(key, values[key])).length;
  const healthy = keys.length > 0 && readyCount === keys.length;

  const cards = keys.map((key) => createServiceCard(
    documentRoot,
    key,
    values[key],
    key === 'asr' ? voiceRuntime?.asr : key === 'tts' ? voiceRuntime?.['gpt-sovits'] : {},
    onStart,
    onStop,
  ));
  cards.push(createServiceCard(documentRoot, 'qq', qqStatus, qqStatus, null, onStop));
  services.replaceChildren(...cards);
  if (!keys.length) {
    const empty = documentRoot.createElement('div');
    empty.className = 'module-empty-state';
    empty.textContent = 'Core 未返回可展示的服务健康项。';
    services.append(empty);
  }
  overall.textContent = healthy
    ? 'Core 服务已就绪'
    : `Core 尚未完全就绪（${readyCount}/${keys.length || 0}）`;
  dot.classList.toggle('ok', healthy);
  updated.textContent = payload?.server_time ? `最后检查：${payload.server_time}` : '';
  setupServiceStatusVisuals(documentRoot);
}

export function renderCoreStatusError(message, documentRoot = document) {
  const overall = documentRoot.querySelector('#overall');
  const dot = documentRoot.querySelector('#overall-dot');
  const updated = documentRoot.querySelector('#updated');
  if (overall) overall.textContent = `Core 状态读取失败：${String(message || '请求失败').slice(0, 160)}`;
  dot?.classList.remove('ok');
  if (updated) updated.textContent = '动态模块和模块管理将继续独立尝试加载。';
}

export function createCoreStatusController({ request, notify, documentRoot = document }) {
  const startRoutes = Object.freeze({
    asr: '/api/v1/voice-control/asr/start-background',
    tts: '/api/v1/voice-control/gpt-sovits/start-background',
  });
  const stopRoutes = Object.freeze({
    qq: '/api/v1/qq-control/stop',
    asr: '/api/v1/voice-control/asr/stop',
    tts: '/api/v1/voice-control/gpt-sovits/stop',
  });

  async function startService(key) {
    const route = startRoutes[key];
    const label = serviceNames[key] || key;
    if (!route) return;
    try {
      await request(route, { method: 'POST' });
      notify(`${label} 正在后台启动；不会打开调试窗口。`);
    } catch (error) {
      notify(`${label} 未能启动：${String(error?.message || '请求失败').slice(0, 120)}`, 'error');
    }
    await refresh();
  }

  async function stopService(key) {
    const route = stopRoutes[key];
    const label = serviceNames[key] || key;
    if (!route || typeof globalThis.confirm !== 'function' || !globalThis.confirm(`确认关闭由当前控制台启动的 ${label}？`)) return;
    try {
      await request(route, { method: 'POST' });
      notify(`${label} 已安全关闭。`);
    } catch (error) {
      notify(`${label} 未能关闭：${String(error?.message || '请求失败').slice(0, 120)}`, 'error');
    }
    await refresh();
  }

  async function refresh() {
    try {
      const [coreResult, qqResult, voiceResult] = await Promise.allSettled([
        request('/dashboard/status', { cache: 'no-store' }),
        request('/api/v1/qq-control/status', { cache: 'no-store' }),
        request('/api/v1/voice-control/status', { cache: 'no-store' }),
      ]);
      if (coreResult.status === 'rejected') throw coreResult.reason;
      const payload = coreResult.value;
      const qqStatus = qqResult.status === 'fulfilled' ? qqResult.value : {};
      const voiceRuntime = voiceResult.status === 'fulfilled' ? voiceResult.value : {};
      renderCoreStatus(payload, documentRoot, qqStatus, voiceRuntime, startService, stopService);
      return payload;
    } catch (error) {
      renderCoreStatusError(error?.message, documentRoot);
      notify('Core 健康状态读取失败；模块管理与已加载面板不受影响。', 'error');
      throw error;
    }
  }

  return Object.freeze({ refresh });
}
