const gptSovitsStatusPath = '/api/v1/gpt-sovits-engine/status';
const gptSovitsSelectPath = '/api/v1/gpt-sovits-engine/select-existing';

function statusCopy(payload) {
  if (payload?.selection_in_progress === true) return '正在等待本机目录选择或验证，请在系统窗口中完成或取消。';
  const registration = String(payload?.registration_state || 'unregistered');
  const integrity = String(payload?.integrity_status || '');
  if (registration === 'registered_existing') {
    return integrity === 'unverified_existing_install'
      ? '已登记现有引擎；该本机安装尚未由 Project Kei 发布摘要验证。'
      : '已登记并验证现有 GPT-SoVITS 引擎。';
  }
  return '尚未登记本机 GPT-SoVITS 引擎。目录由本机选择器处理，控制台不会接收路径。';
}

export function setupGptSovitsEngineControl({ request, notify, documentRoot = document }) {
  const button = documentRoot.querySelector('#select-gpt-sovits-engine');
  const status = documentRoot.querySelector('#gpt-sovits-engine-status');
  let busy = false;
  let available = false;

  function render(message) {
    if (status) status.textContent = message;
    if (button) {
      button.disabled = busy || !available;
      button.setAttribute('aria-busy', busy ? 'true' : 'false');
      button.textContent = busy ? '等待本机目录选择…' : '选择已有引擎目录';
    }
  }

  function acceptStatus(payload) {
    available = payload?.can_select_existing !== false;
    busy = payload?.selection_in_progress === true;
    render(statusCopy(payload));
    return payload;
  }

  async function refreshStatus({ quiet = false } = {}) {
    try {
      return acceptStatus(await request(gptSovitsStatusPath, { cache: 'no-store' }));
    } catch (error) {
      available = false;
      busy = false;
      render(error?.status === 404
        ? '本机引擎选择接口尚未装配；不会自动扫描或下载。'
        : `本机引擎状态读取失败：${String(error?.message || '请求失败').slice(0, 160)}`);
      if (!quiet && error?.status !== 404) notify('GPT-SoVITS 本机引擎状态读取失败。', 'error');
      throw error;
    }
  }

  async function selectExisting() {
    if (busy || !available) return;
    busy = true;
    render('正在打开本机目录选择器…');
    try {
      const payload = await request(gptSovitsSelectPath, { method: 'POST' });
      if (payload?.action === 'cancelled') {
        busy = false;
        available = payload?.can_select_existing !== false;
        render('已取消选择；原有引擎登记保持不变。');
        return;
      }
      acceptStatus(payload);
      notify('GPT-SoVITS 本机引擎已登记。', 'success');
    } catch (error) {
      busy = false;
      available = true;
      render(`选择或验证失败：${String(error?.message || '请求失败').slice(0, 160)}`);
      notify('GPT-SoVITS 引擎选择未完成；原有登记保持不变。', 'error');
    }
  }

  button?.addEventListener('click', selectExisting);
  render('正在读取本机引擎注册状态…');
  return Object.freeze({
    refreshStatus,
    destroy() { button?.removeEventListener('click', selectExisting); },
  });
}

export { gptSovitsSelectPath, gptSovitsStatusPath, statusCopy };
