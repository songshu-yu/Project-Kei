let mountedRoot = null;

function el(root, role) {
  return root.querySelector(`[data-life-forecast-role="${role}"]`);
}

function node(root, tag, text = '') {
  const result = root.ownerDocument.createElement(tag);
  result.textContent = text;
  return result;
}

function field(root, label, control) {
  const wrapper = node(root, 'label');
  wrapper.className = 'field';
  wrapper.append(label, control);
  return wrapper;
}

function section(root, title, role) {
  const result = node(root, 'section');
  result.className = 'detail';
  result.setAttribute('aria-labelledby', `life-forecast-${role}-title`);
  const heading = node(root, 'h4', title);
  heading.id = `life-forecast-${role}-title`;
  const body = node(root, 'div');
  body.dataset.lifeForecastRole = role;
  result.append(heading, body);
  return result;
}

function build(root) {
  root.dataset.panelId = 'life-forecast';
  root.dataset.panelSummary = '天气事实、生活建议与可关闭的本地娱乐运势';
  const form = node(root, 'form');
  form.className = 'schedule-grid';
  form.dataset.lifeForecastRole = 'config-form';
  const city = node(root, 'input');
  city.type = 'text';
  city.maxLength = 80;
  city.required = true;
  city.autocomplete = 'off';
  city.dataset.lifeForecastRole = 'city';
  const latitude = node(root, 'input');
  latitude.type = 'number';
  latitude.min = '-90';
  latitude.max = '90';
  latitude.step = '0.000001';
  latitude.required = true;
  latitude.dataset.lifeForecastRole = 'latitude';
  const longitude = node(root, 'input');
  longitude.type = 'number';
  longitude.min = '-180';
  longitude.max = '180';
  longitude.step = '0.000001';
  longitude.required = true;
  longitude.dataset.lifeForecastRole = 'longitude';
  const provider = node(root, 'select');
  provider.dataset.lifeForecastRole = 'provider';
  [['disabled', '禁用联网'], ['open_meteo', 'Open-Meteo（显式刷新才联网）']].forEach(([value, text]) => {
    const option = node(root, 'option', text);
    option.value = value;
    provider.append(option);
  });
  const fortune = node(root, 'input');
  fortune.type = 'checkbox';
  fortune.dataset.lifeForecastRole = 'fortune-enabled';
  const save = node(root, 'button', '保存本机配置');
  save.type = 'submit';
  const refresh = node(root, 'button', '显式刷新');
  refresh.type = 'button';
  refresh.dataset.lifeForecastRole = 'refresh';
  const privacy = node(root, 'p');
  privacy.className = 'hint';
  privacy.dataset.lifeForecastRole = 'privacy';
  const status = node(root, 'p');
  status.className = 'hint';
  status.setAttribute('aria-live', 'polite');
  status.dataset.lifeForecastRole = 'status';

  form.append(
    field(root, '城市显示名（仅本机）', city),
    field(root, '纬度', latitude),
    field(root, '经度', longitude),
    field(root, 'Provider', provider),
    field(root, '开启今日运势（娱乐）', fortune),
    save,
  );
  root.replaceChildren(
    form,
    refresh,
    privacy,
    status,
    section(root, '天气事实', 'facts'),
    section(root, '生活建议', 'advice'),
    section(root, '娱乐运势', 'fortune'),
  );
}

function line(root, label, value) {
  const row = node(root, 'p');
  const strong = node(root, 'strong', `${label}：`);
  row.append(strong, String(value));
  return row;
}

function render(root, payload) {
  const facts = el(root, 'facts');
  const advice = el(root, 'advice');
  const fortune = el(root, 'fortune');
  el(root, 'status').textContent = `日期 ${payload.date} · 缓存 ${payload.cache_status}`;
  if (!payload.forecast) {
    facts.replaceChildren(node(root, 'p', '今天没有可用缓存。保存地点后点击“显式刷新”。'));
    advice.replaceChildren(node(root, 'p', '天气事实不可用，生活建议 unavailable。'));
  } else {
    const value = payload.forecast;
    facts.replaceChildren(
      line(root, '地点', payload.city),
      line(root, '天气', `${value.condition}（${value.current_temperature_c}°C）`),
      line(root, '最高 / 最低温', `${value.temperature_max_c}°C / ${value.temperature_min_c}°C`),
      line(root, '体感温度', `${value.apparent_temperature_c}°C`),
      line(root, '最高降水概率', `${value.precipitation_probability_max_pct}%`),
      line(root, '最大风速', `${value.wind_speed_max_kmh} km/h`),
      line(root, '紫外线', value.uv_index_max ?? 'unavailable'),
      line(root, '美国 AQI', value.us_aqi ?? 'unavailable'),
      line(root, '必要预警', value.warnings_status === 'available' ? value.warnings.length : 'unavailable（Provider 未提供）'),
    );
    value.attribution.forEach((item) => {
      const link = node(root, 'a', item.label);
      link.href = item.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      facts.append(link, node(root, 'br'));
    });
    advice.replaceChildren(...Object.entries(payload.life_advice || {}).map(([key, item]) => {
      const labels = {clothing: '穿衣', travel_umbrella: '出行 / 带伞', uv: '紫外线', air_quality: '空气质量'};
      return line(root, labels[key] || key, `${item.text} [${item.status}]`);
    }));
  }
  if (payload.fortune?.enabled) {
    fortune.replaceChildren(
      line(root, '声明', payload.fortune.disclaimer),
      line(root, '今日提示', payload.fortune.focus),
      line(root, '娱乐色彩', payload.fortune.color),
      line(root, '小行动', payload.fortune.small_action),
      line(root, '公开规则', `${payload.fortune.ruleset}：规则版本 + 本地日期经 SHA-256 从固定文案表选取`),
    );
  } else {
    fortune.replaceChildren(line(root, '状态', `已关闭 · ${payload.fortune?.disclaimer || '娱乐内容、非事实预测'}`));
  }
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('life_forecast 面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  build(root);
  const load = async () => {
    const [config, today] = await Promise.all([
      context.request('/api/v1/life-forecast/config'),
      context.request('/api/v1/life-forecast/today'),
    ]);
    if (mountedRoot !== root) return;
    el(root, 'city').value = config.city === '未配置' ? '' : config.city;
    el(root, 'latitude').value = String(config.latitude);
    el(root, 'longitude').value = String(config.longitude);
    el(root, 'provider').value = config.provider;
    el(root, 'fortune-enabled').checked = config.fortune_enabled;
    el(root, 'privacy').textContent = config.privacy_notice;
    render(root, today);
  };
  el(root, 'config-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await context.request('/api/v1/life-forecast/config', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          city: el(root, 'city').value.trim(),
          latitude: Number(el(root, 'latitude').value),
          longitude: Number(el(root, 'longitude').value),
          provider: el(root, 'provider').value,
          fortune_enabled: el(root, 'fortune-enabled').checked,
        }),
      });
      context.notify('每日生活预报配置已保存在本机。');
      await load();
    } catch (error) {
      context.notify(`保存配置失败：${error.message}`, 'error');
    }
  });
  el(root, 'refresh').addEventListener('click', async () => {
    const button = el(root, 'refresh');
    button.disabled = true;
    try {
      const result = await context.request('/api/v1/life-forecast/refresh', {method: 'POST'});
      render(root, result);
      context.notify('每日生活预报已显式刷新。');
    } catch (error) {
      context.notify(`刷新失败，旧缓存已保留：${error.message}`, 'error');
    } finally {
      button.disabled = false;
    }
  });
  await load();
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
