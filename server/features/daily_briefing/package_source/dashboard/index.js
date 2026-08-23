let mountedRoot = null;
let pollTimer = null;
let pollCount = 0;

const LIFE_FORECAST_FIELDS = [
  ['weather_condition', '天气状况'],
  ['temperature_range', '最高/最低温'],
  ['apparent_temperature', '体感温度'],
  ['precipitation_probability', '降水概率'],
  ['wind', '风速'],
  ['alerts', '天气预警'],
  ['clothing', '穿衣建议'],
  ['travel_umbrella', '出行与雨伞'],
  ['uv', '紫外线建议'],
  ['air_quality', '空气质量建议'],
  ['fortune', '娱乐内容'],
];

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
  const projection = root.ownerDocument.createElement('fieldset');
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
  projection.className = 'detail';
  const legend = root.ownerDocument.createElement('legend');
  legend.textContent = '每日情报中的生活预报';
  const masterLabel = root.ownerDocument.createElement('label');
  const master = root.ownerDocument.createElement('input');
  master.type = 'checkbox';
  master.dataset.briefingRole = 'life-forecast-enabled';
  masterLabel.append(master, ' 启用只读投影');
  projection.append(legend, masterLabel);
  for (const [fieldId, labelText] of LIFE_FORECAST_FIELDS) {
    const label = root.ownerDocument.createElement('label');
    const input = root.ownerDocument.createElement('input');
    input.type = 'checkbox';
    input.dataset.lifeForecastField = fieldId;
    label.append(input, ` ${labelText}`);
    projection.append(label);
  }
  projection.append(button(root, '保存生活预报显示项', 'save-life-forecast', 'secondary'));
  root.replaceChildren(intro, status, actions, details, projection);
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
  const forecast = result?.life_forecast;
  const forecastStatus = forecast?.enabled
    ? (forecast.ready ? `生活预报已投影 ${Object.keys(forecast.fields || {}).length} 项` : '生活预报暂不可用')
    : '生活预报投影已关闭';
  el(root, 'details').textContent = [phase, coverage, forecastStatus].filter(Boolean).join(' · ')
    || '缺少可选来源包时会显示未配置，其余已安装来源仍可继续。';
}

function renderProjectionConfiguration(root, configuration) {
  el(root, 'life-forecast-enabled').checked = configuration?.enabled === true;
  for (const [fieldId] of LIFE_FORECAST_FIELDS) {
    const input = root.querySelector(`[data-life-forecast-field="${fieldId}"]`);
    input.checked = configuration?.fields?.[fieldId] === true;
  }
}

async function saveProjectionConfiguration(context, root) {
  const save = el(root, 'save-life-forecast');
  save.disabled = true;
  try {
    const fields = Object.fromEntries(LIFE_FORECAST_FIELDS.map(([fieldId]) => [
      fieldId,
      root.querySelector(`[data-life-forecast-field="${fieldId}"]`).checked,
    ]));
    const result = await context.request('/api/v1/briefing/life-forecast-projection', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        enabled: el(root, 'life-forecast-enabled').checked,
        fields,
      }),
    });
    if (mountedRoot === root) renderProjectionConfiguration(root, result);
    context.notify('生活预报显示项已保存。');
    if (mountedRoot === root) await readAndRender(context, root);
  } catch (error) {
    context.notify(`生活预报显示项保存失败：${error.message}`, 'error');
  } finally {
    if (mountedRoot === root) save.disabled = false;
  }
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
  el(root, 'save-life-forecast').addEventListener('click', () => {
    void saveProjectionConfiguration(context, root);
  });
  const projectionConfiguration = await context.request(
    '/api/v1/briefing/life-forecast-projection',
  );
  if (mountedRoot === root) {
    renderProjectionConfiguration(root, projectionConfiguration);
  }
  const generation = await readAndRender(context, root);
  if (generation?.state === 'running') pollWhileRunning(context, root);
}

export async function unmount() {
  stopPolling();
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
