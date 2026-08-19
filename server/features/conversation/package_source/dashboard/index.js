let mountedRoot = null;

const PRESETS = Object.freeze({
  'deepseek-flash': {
    provider: 'deepseek',
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-v4-flash',
  },
  'deepseek-pro': {
    provider: 'deepseek',
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-v4-pro',
  },
});

function control(root, id) {
  return root.querySelector(`#${id}`);
}

function presetFor(profile) {
  for (const [name, preset] of Object.entries(PRESETS)) {
    if (profile.provider === preset.provider
      && profile.base_url === preset.base_url
      && profile.model === preset.model) {
      return name;
    }
  }
  return 'custom';
}

function render(root, profile) {
  const preset = control(root, 'llm-preset');
  const baseUrl = control(root, 'llm-base-url');
  const model = control(root, 'llm-model');
  const thinking = control(root, 'llm-thinking');
  preset.value = presetFor(profile);
  baseUrl.value = profile.base_url || '';
  model.value = profile.model || '';
  thinking.checked = profile.thinking_mode === 'enabled';
  thinking.disabled = profile.provider !== 'deepseek';
  control(root, 'llm-status').textContent = [
    `当前：${profile.model || '未配置'}`,
    profile.base_url || '未配置',
    profile.provider === 'deepseek'
      ? (thinking.checked ? '思考模式' : '非思考模式')
      : null,
  ].filter(Boolean).join(' · ');
}

function applyPreset(root) {
  const name = control(root, 'llm-preset').value;
  const thinking = control(root, 'llm-thinking');
  if (name === 'custom') {
    thinking.checked = false;
    thinking.disabled = true;
    return;
  }
  const preset = PRESETS[name];
  control(root, 'llm-base-url').value = preset.base_url;
  control(root, 'llm-model').value = preset.model;
  thinking.checked = false;
  thinking.disabled = false;
}

function field(root, labelText, input) {
  const label = root.ownerDocument.createElement('label');
  label.className = 'field';
  label.append(labelText, input);
  return label;
}

function buildPanel(root) {
  const hint = root.ownerDocument.createElement('p');
  const grid = root.ownerDocument.createElement('div');
  const preset = root.ownerDocument.createElement('select');
  const baseUrl = root.ownerDocument.createElement('input');
  const model = root.ownerDocument.createElement('input');
  const thinkingLabel = root.ownerDocument.createElement('label');
  const thinking = root.ownerDocument.createElement('input');
  const thinkingText = root.ownerDocument.createElement('span');
  const apply = root.ownerDocument.createElement('button');
  const status = root.ownerDocument.createElement('div');

  hint.className = 'hint';
  hint.textContent = 'API Key 只来自服务端环境；此面板只测试并保存非秘密模型方案。';
  grid.className = 'schedule-grid';
  grid.style.marginTop = '12px';
  for (const [value, text] of [
    ['deepseek-flash', 'DeepSeek V4 Flash（推荐）'],
    ['deepseek-pro', 'DeepSeek V4 Pro'],
    ['custom', '自定义 OpenAI 兼容方案'],
  ]) {
    const option = root.ownerDocument.createElement('option');
    option.value = value;
    option.textContent = text;
    preset.append(option);
  }
  preset.id = 'llm-preset';
  baseUrl.id = 'llm-base-url';
  baseUrl.type = 'text';
  baseUrl.spellcheck = false;
  model.id = 'llm-model';
  model.type = 'text';
  model.spellcheck = false;
  thinkingLabel.className = 'switch-row';
  thinking.id = 'llm-thinking';
  thinking.type = 'checkbox';
  thinkingText.textContent = '启用 DeepSeek 思考模式';
  thinkingLabel.append(thinking, thinkingText);
  apply.id = 'apply-llm';
  apply.type = 'button';
  apply.textContent = '测试并应用';
  status.id = 'llm-status';
  status.className = 'detail hint';
  grid.append(
    field(root, '方案', preset),
    field(root, 'Base URL', baseUrl),
    field(root, '模型 ID', model),
    thinkingLabel,
    apply,
  );
  root.dataset.panelSettings = '模型方案|Base URL|模型 ID|思考模式';
  root.replaceChildren(hint, grid, status);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== 'function') {
    throw new TypeError('conversation 面板缺少受限挂载上下文');
  }
  await unmount();
  const root = context.root;
  mountedRoot = root;
  buildPanel(root);
  control(root, 'llm-preset').addEventListener('change', () => applyPreset(root));
  control(root, 'apply-llm').addEventListener('click', async () => {
    const button = control(root, 'apply-llm');
    const presetName = control(root, 'llm-preset').value;
    const base_url = control(root, 'llm-base-url').value.trim();
    const model = control(root, 'llm-model').value.trim();
    if (!base_url || !model) {
      context.notify('请填写 Base URL 和模型 ID。', 'error');
      return;
    }
    button.disabled = true;
    button.textContent = '正在测试…';
    try {
      const profile = await context.request('/api/v1/llm-profile', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          provider: presetName === 'custom' ? 'custom' : 'deepseek',
          base_url,
          model,
          thinking_mode: control(root, 'llm-thinking').checked
            ? 'enabled'
            : 'disabled',
        }),
      });
      if (mountedRoot !== root) return;
      render(root, profile);
      context.notify(`已切换到 ${profile.model}。`);
    } catch (error) {
      context.notify(`模型方案未切换：${error.message}`, 'error');
      try {
        const active = await context.request('/api/v1/llm-profile');
        if (mountedRoot === root) render(root, active);
      } catch {
        // The failed candidate remains visible only when the active profile
        // cannot be re-read; no profile data is cached in the browser.
      }
    } finally {
      if (mountedRoot === root) {
        button.disabled = false;
        button.textContent = '测试并应用';
      }
    }
  });
  const profile = await context.request('/api/v1/llm-profile');
  if (mountedRoot === root) render(root, profile);
}

export async function unmount() {
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
