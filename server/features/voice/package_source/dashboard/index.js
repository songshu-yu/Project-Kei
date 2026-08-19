let mountedRoot = null;
let runtimeStatus = null;
let modelDirectoryStatus = null;

function providerStatus(provider) {
  const health = provider?.health || {};
  if (health.available === true) return '可用';
  const code = health.error_code || health.code || '';
  if (code.endsWith('_unavailable')) return '未配置或未启动';
  if (code.endsWith('_timeout')) return '检查超时';
  return health.status === 'closed' ? '已关闭' : '不可用';
}

function buildPanel(root) {
  const hint = root.ownerDocument.createElement('p');
  const summary = root.ownerDocument.createElement('div');
  const detail = root.ownerDocument.createElement('p');
  const controls = root.ownerDocument.createElement('div');
  const asrStart = root.ownerDocument.createElement('button');
  const asrStop = root.ownerDocument.createElement('button');
  const asrDirectory = root.ownerDocument.createElement('button');
  const ttsStart = root.ownerDocument.createElement('button');
  const ttsStop = root.ownerDocument.createElement('button');
  const runtimeDetail = root.ownerDocument.createElement('p');
  const modelDirectoryDetail = root.ownerDocument.createElement('p');
  const refresh = root.ownerDocument.createElement('button');
  hint.className = 'hint';
  hint.textContent = '语音按 ASR → 对话 → TTS 编排；TTS 不可用时会明确返回文字。';
  summary.className = 'module-grid';
  summary.dataset.voiceRole = 'summary';
  detail.className = 'detail hint';
  detail.dataset.voiceRole = 'detail';
  controls.className = 'module-grid';
  asrStart.type = 'button';
  asrStart.textContent = '调试启动 ASR（打开窗口）';
  asrStart.dataset.voiceRole = 'start-asr';
  asrStop.type = 'button';
  asrStop.textContent = '关闭 ASR';
  asrStop.dataset.voiceRole = 'stop-asr';
  asrDirectory.type = 'button';
  asrDirectory.textContent = '选择 ASR 模型目录';
  asrDirectory.dataset.voiceRole = 'select-asr-model-directory';
  ttsStart.type = 'button';
  ttsStart.textContent = '调试启动 GPT-SoVITS（打开窗口）';
  ttsStart.dataset.voiceRole = 'start-gpt-sovits';
  ttsStop.type = 'button';
  ttsStop.textContent = '关闭 GPT-SoVITS';
  ttsStop.dataset.voiceRole = 'stop-gpt-sovits';
  runtimeDetail.className = 'detail hint';
  runtimeDetail.dataset.voiceRole = 'runtime-detail';
  modelDirectoryDetail.className = 'detail hint';
  modelDirectoryDetail.dataset.voiceRole = 'asr-model-directory-detail';
  refresh.type = 'button';
  refresh.textContent = '刷新语音状态';
  refresh.dataset.voiceRole = 'refresh';
  controls.append(asrStart, asrStop, asrDirectory, ttsStart, ttsStop);
  root.replaceChildren(
    hint,
    summary,
    detail,
    controls,
    runtimeDetail,
    modelDirectoryDetail,
    refresh,
  );
}

function renderModelDirectory(root, status) {
  modelDirectoryStatus = status;
  const button = root.querySelector('[data-voice-role="select-asr-model-directory"]');
  button.disabled = status?.available !== true || status?.state === 'selection_in_progress';
  const name = status?.configured && status?.directory_name
    ? `（${status.directory_name}）`
    : '';
  root.querySelector('[data-voice-role="asr-model-directory-detail"]').textContent =
    `${status?.message || '本机 ASR 目录选择能力不可用。'}${name}`;
}

function render(root, status) {
  const labels = [
    ['asr', '语音识别'],
    ['conversation', '文字对话'],
    ['tts', '语音合成'],
    ['voice_pack', 'Voice Pack'],
  ];
  const summary = root.querySelector('[data-voice-role="summary"]');
  summary.replaceChildren(...labels.map(([key, label]) => {
    const card = root.ownerDocument.createElement('div');
    const name = root.ownerDocument.createElement('span');
    const value = root.ownerDocument.createElement('strong');
    card.className = 'stat-chip';
    name.className = 'label';
    name.textContent = label;
    value.textContent = providerStatus(status.providers?.[key]);
    card.append(name, value);
    return card;
  }));
  const audioReady = status.providers?.tts?.health?.available === true
    && status.providers?.voice_pack?.health?.available === true;
  root.querySelector('[data-voice-role="detail"]').textContent = audioReady
    ? '语音回复可用。'
    : '当前会保留文字回复，不会伪装生成音频。';
}

function renderRuntime(root, status) {
  runtimeStatus = status;
  const asr = status?.asr || {state: 'unavailable', ready: false};
  const tts = status?.['gpt-sovits'] || {state: 'unavailable', ready: false};
  const asrButton = root.querySelector('[data-voice-role="start-asr"]');
  const asrStop = root.querySelector('[data-voice-role="stop-asr"]');
  const ttsButton = root.querySelector('[data-voice-role="start-gpt-sovits"]');
  const ttsStop = root.querySelector('[data-voice-role="stop-gpt-sovits"]');
  asrButton.disabled = asr.state !== 'ready';
  ttsButton.disabled = tts.state !== 'ready';
  asrStop.disabled = asr.running !== true || asr.can_stop !== true;
  ttsStop.disabled = tts.running !== true || tts.can_stop !== true;
  asrStop.title = asr.running === true && asr.can_stop !== true
    ? '该 ASR 不是由当前控制台启动，不能从这里关闭。'
    : '';
  ttsStop.title = tts.running === true && tts.can_stop !== true
    ? '该 GPT-SoVITS 不是由当前控制台启动，不能从这里关闭。'
    : '';
  const lines = [
    `ASR：${asr.message || asr.state || 'unavailable'}`,
    `GPT-SoVITS：${tts.message || tts.state || 'unavailable'}`,
  ];
  root.querySelector('[data-voice-role="runtime-detail"]').textContent = lines.join(' ');
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('voice 面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  buildPanel(root);
  const refreshVoice = async () => {
    const status = await context.request('/api/v1/voice/health');
    if (mountedRoot === root) render(root, status);
  };
  const refreshRuntime = async () => {
    const status = await context.request('/api/v1/voice-control/status');
    if (mountedRoot === root) renderRuntime(root, status);
  };
  const refreshModelDirectory = async () => {
    const status = await context.request(
      '/api/v1/voice-control/asr/model-directory/status',
    );
    if (mountedRoot === root) renderModelDirectory(root, status);
  };
  const refresh = async () => {
    await Promise.all([refreshVoice(), refreshRuntime(), refreshModelDirectory()]);
  };
  const selectAsrModelDirectory = async () => {
    const button = root.querySelector(
      '[data-voice-role="select-asr-model-directory"]',
    );
    button.disabled = true;
    try {
      const result = await context.request(
        '/api/v1/voice-control/asr/model-directory/select',
        {method: 'POST'},
      );
      if (mountedRoot === root) renderModelDirectory(root, result);
      context.notify(result.message || 'ASR 模型目录状态已更新。');
      await refreshRuntime();
    } catch (error) {
      context.notify(`选择 ASR 模型目录失败：${error.message}`, 'error');
      try {
        await Promise.all([refreshModelDirectory(), refreshRuntime()]);
      } catch (_refreshError) {
        if (mountedRoot === root) {
          renderModelDirectory(root, {
            available: false,
            configured: false,
            state: 'unavailable',
          });
        }
      }
    }
  };
  const startRuntime = async (target) => {
    const role = target === 'asr' ? 'start-asr' : 'start-gpt-sovits';
    const path = target === 'asr'
      ? '/api/v1/voice-control/asr/start'
      : '/api/v1/voice-control/gpt-sovits/start';
    const button = root.querySelector(`[data-voice-role="${role}"]`);
    button.disabled = true;
    try {
      const result = await context.request(path, {method: 'POST'});
      const next = {...(runtimeStatus || {}), [target]: result};
      if (mountedRoot === root) renderRuntime(root, next);
      context.notify(result.message || `${target} 正在启动。`);
    } catch (error) {
      context.notify(`启动 ${target} 失败：${error.message}`, 'error');
      try {
        await refreshRuntime();
      } catch (_refreshError) {
        if (mountedRoot === root) {
          renderRuntime(root, {
            ...(runtimeStatus || {}),
            [target]: {state: 'unavailable', ready: false},
          });
        }
      }
    }
  };
  const stopRuntime = async (target) => {
    const role = target === 'asr' ? 'stop-asr' : 'stop-gpt-sovits';
    const path = target === 'asr'
      ? '/api/v1/voice-control/asr/stop'
      : '/api/v1/voice-control/gpt-sovits/stop';
    const label = target === 'asr' ? 'ASR' : 'GPT-SoVITS';
    if (typeof globalThis.confirm !== 'function' || !globalThis.confirm(`确认关闭由当前控制台启动的 ${label}？`)) return;
    const button = root.querySelector(`[data-voice-role="${role}"]`);
    button.disabled = true;
    try {
      const result = await context.request(path, {method: 'POST'});
      const next = {...(runtimeStatus || {}), [target]: result};
      if (mountedRoot === root) renderRuntime(root, next);
      context.notify(`${label} 已安全关闭。`);
    } catch (error) {
      context.notify(`关闭 ${label} 失败：${error.message}`, 'error');
      try { await refreshRuntime(); } catch (_refreshError) {}
    }
  };
  root.querySelector('[data-voice-role="start-asr"]').addEventListener(
    'click',
    async () => startRuntime('asr'),
  );
  root.querySelector('[data-voice-role="start-gpt-sovits"]').addEventListener(
    'click',
    async () => startRuntime('gpt-sovits'),
  );
  root.querySelector('[data-voice-role="stop-asr"]').addEventListener(
    'click',
    async () => stopRuntime('asr'),
  );
  root.querySelector('[data-voice-role="stop-gpt-sovits"]').addEventListener(
    'click',
    async () => stopRuntime('gpt-sovits'),
  );
  root.querySelector('[data-voice-role="select-asr-model-directory"]').addEventListener(
    'click',
    selectAsrModelDirectory,
  );
  root.querySelector('[data-voice-role="refresh"]').addEventListener('click', async () => {
    try {
      await refresh();
    } catch (error) {
      context.notify(`读取语音状态失败：${error.message}`, 'error');
    }
  });
  await refresh();
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
  runtimeStatus = null;
  modelDirectoryStatus = null;
}
