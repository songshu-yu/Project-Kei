let mountedRoot = null;
let operationToken = 0;

const FIELD_LABELS = {
  sessdata: 'SESSDATA',
  bili_jct: 'bili_jct',
  buvid3: 'buvid3',
};

function el(root, role) {
  return root.querySelector(`[data-bilibili-role="${role}"]`);
}

function node(root, tag, role, text = '') {
  const value = root.ownerDocument.createElement(tag);
  if (role) value.dataset.bilibiliRole = role;
  value.textContent = text;
  return value;
}

function stateText(status) {
  if (status?.operation_state === 'validating') return '验证中';
  if (status?.operation_state === 'succeeded') return '采集成功';
  if (status?.operation_state === 'failed') return '采集失败';
  return {
    missing: '未配置',
    configured: '已配置',
    invalid: '已失效',
  }[status?.state] || '状态未知';
}

function safeTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

function renderStatus(root, status) {
  el(root, 'state').textContent = stateText(status);
  el(root, 'updated').textContent = `更新时间：${safeTime(status?.updated_at)}`;
  el(root, 'validated').textContent = `最近验证：${safeTime(status?.validated_at)}`;
  const retry = status?.retry_after ? `；可重试时间：${safeTime(status.retry_after)}` : '';
  el(root, 'notice').textContent = status?.state === 'invalid'
    ? `参数已失效，请重新填写三项同一浏览器会话参数后再验证${retry}`
    : '保存只写入本机候选参数，不会联网；只有“验证并重新采集”会访问 B 站。';

  const fieldRoot = el(root, 'field-status');
  fieldRoot.replaceChildren(...(status?.fields || []).map((field) => {
    const row = node(root, 'div', '', '');
    row.className = 'stat-chip';
    const label = node(root, 'span', '', FIELD_LABELS[field.key] || field.key);
    label.className = 'label';
    const detail = node(
      root,
      'strong',
      '',
      field.configured ? `已配置 ${field.masked_tail || ''}`.trim() : '缺失',
    );
    row.append(label, detail);
    return row;
  }));
}

function renderProfiles(root, payload) {
  const profiles = Object.values(payload?.profiles || {});
  const list = el(root, 'profiles');
  if (!profiles.length) {
    list.replaceChildren(node(root, 'p', '', '暂无本机资料缓存。'));
    return;
  }
  list.replaceChildren(...profiles.map((profile) => {
    const card = node(root, 'div', '', '');
    card.className = 'stat-chip';
    const avatar = node(
      root,
      'span',
      '',
      profile.status === 'ok' && profile.name ? profile.name.slice(0, 1) : 'B',
    );
    avatar.className = 'module-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    const text = node(
      root,
      'strong',
      '',
      profile.status === 'ok'
        ? `${profile.name} · UID ${profile.uid}`
        : `UID ${profile.uid} · 资料暂不可用`,
    );
    card.append(avatar, text);
    return card;
  }));
}

function inputField(root, key, title, help) {
  const wrapper = node(root, 'label', '', '');
  wrapper.className = 'field';
  const label = node(root, 'span', '', `${title}（必填）`);
  const input = node(root, 'input', key, '');
  input.type = 'password';
  input.name = `bilibili-${key}`;
  input.autocomplete = 'off';
  input.spellcheck = false;
  input.maxLength = 4096;
  input.placeholder = '仅在本机输入，保存后不会回填';
  const hint = node(root, 'small', '', help);
  hint.className = 'hint';
  wrapper.append(label, input, hint);
  return wrapper;
}

function buildPanel(root) {
  const intro = node(
    root,
    'p',
    '',
    '维护本人已登录 B 站浏览器会话中的三项 Cookie。请从浏览器开发者工具的 Cookie 存储中逐项复制，勿粘贴整段 Header、脚本或 JSON。',
  );
  intro.className = 'hint';

  const summary = node(root, 'div', '', '');
  summary.className = 'module-grid';
  summary.append(
    node(root, 'strong', 'state', '读取中'),
    node(root, 'span', 'updated', '更新时间：—'),
    node(root, 'span', 'validated', '最近验证：—'),
  );
  const notice = node(root, 'p', 'notice', '');
  notice.className = 'hint';
  const fieldStatus = node(root, 'div', 'field-status', '');
  fieldStatus.className = 'module-grid';

  const details = node(root, 'details', 'details', '');
  const detailsSummary = node(root, 'summary', '', '参数维护与恢复采集');
  const form = node(root, 'div', '', '');
  form.className = 'schedule-grid';
  form.append(
    inputField(root, 'sessdata', 'SESSDATA', '本人登录会话标识。'),
    inputField(root, 'bili_jct', 'bili_jct', '与 SESSDATA 同一会话的 CSRF Cookie。'),
    inputField(root, 'buvid3', 'buvid3', '同一浏览器会话的设备 Cookie。'),
  );
  const save = node(root, 'button', 'save', '保存候选参数');
  save.type = 'button';
  const collect = node(root, 'button', 'collect', '验证并重新采集');
  collect.type = 'button';
  collect.className = 'secondary';
  const actionStatus = node(root, 'p', 'action-status', '');
  actionStatus.className = 'hint';
  details.append(detailsSummary, form, save, collect, actionStatus);

  const profileHeading = node(root, 'h4', '', '本机资料缓存');
  const profiles = node(root, 'div', 'profiles', '');
  profiles.className = 'module-grid';
  root.replaceChildren(intro, summary, notice, fieldStatus, details, profileHeading, profiles);
}

function clearSecrets(root) {
  Object.keys(FIELD_LABELS).forEach((key) => {
    const input = el(root, key);
    if (input) input.value = '';
  });
}

async function refreshLocal(context, root) {
  const [status, profiles] = await Promise.all([
    context.request('/api/v1/bilibili/credentials/status'),
    context.request('/api/v1/bilibili/profiles'),
  ]);
  if (mountedRoot !== root) return;
  renderStatus(root, status);
  renderProfiles(root, profiles);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('B站面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  const token = ++operationToken;
  buildPanel(root);

  el(root, 'save').addEventListener('click', async () => {
    const payload = {};
    for (const key of Object.keys(FIELD_LABELS)) {
      payload[key] = el(root, key).value.trim();
      if (!payload[key]) {
        el(root, 'action-status').textContent = '三项参数都必须填写。';
        return;
      }
    }
    const button = el(root, 'save');
    button.disabled = true;
    el(root, 'action-status').textContent = '正在保存到本机候选区…';
    try {
      const status = await context.request('/api/v1/bilibili/credentials', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (mountedRoot === root && token === operationToken) {
        renderStatus(root, status);
        el(root, 'action-status').textContent = '候选参数已原子保存，尚未联网。';
        context.notify('B站候选参数已保存');
      }
    } catch (_error) {
      if (mountedRoot === root) {
        el(root, 'action-status').textContent = '保存失败，原有参数保持不变。';
        context.notify('B站参数保存失败，原有配置未改变', 'error');
      }
    } finally {
      clearSecrets(root);
      if (mountedRoot === root) button.disabled = false;
    }
  });

  el(root, 'collect').addEventListener('click', async () => {
    const button = el(root, 'collect');
    button.disabled = true;
    el(root, 'save').disabled = true;
    el(root, 'state').textContent = '验证中';
    el(root, 'action-status').textContent = '正在验证参数并采集资料与动态…';
    try {
      const result = await context.request(
        '/api/v1/bilibili/credentials/validate-and-collect',
        {method: 'POST'},
      );
      if (mountedRoot === root && token === operationToken) {
        renderStatus(root, result.credential_status);
        renderProfiles(root, {profiles: result.profiles});
        el(root, 'action-status').textContent = '参数验证与重新采集成功。';
        context.notify('B站资料与动态采集成功');
      }
    } catch (_error) {
      if (mountedRoot === root) {
        el(root, 'state').textContent = '采集失败';
        el(root, 'action-status').textContent =
          '验证或采集失败。旧参数与旧缓存未被覆盖，请查看安全状态后更正再试。';
        context.notify('B站验证或采集失败，旧数据保持不变', 'error');
        try {
          await refreshLocal(context, root);
        } catch (_refreshError) {
          // Keep the bounded local message; never surface response bodies.
        }
      }
    } finally {
      if (mountedRoot === root) {
        button.disabled = false;
        el(root, 'save').disabled = false;
      }
    }
  });

  try {
    await refreshLocal(context, root);
  } catch (_error) {
    if (mountedRoot === root) {
      el(root, 'state').textContent = '状态读取失败';
      el(root, 'notice').textContent = '本机状态暂不可用；未发起 B 站网络请求。';
    }
  }
}

export async function unmount() {
  operationToken += 1;
  if (mountedRoot) {
    clearSecrets(mountedRoot);
    mountedRoot.replaceChildren();
  }
  mountedRoot = null;
}
