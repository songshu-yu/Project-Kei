const restartConfirmation = 'restart-project-kei-core';
const restartStatusPath = '/api/v1/dashboard/service/restart/status';
const restartRequestPath = '/api/v1/dashboard/service/restart';
const reconnectLimitMs = 90000;

export function boundedRetryDelay(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(5000, Math.max(250, parsed)) : 1000;
}

function publicMessage(payload, fallback) {
  const text = String(payload?.message || fallback || '').replace(/\s+/g, ' ').trim();
  return text.slice(0, 200);
}

export function setupRestartControl({ request, notify, documentRoot = document }) {
  const button = documentRoot.querySelector('#restart-project-kei');
  const status = documentRoot.querySelector('#restart-project-kei-status');
  const dialog = documentRoot.querySelector('#restart-project-kei-confirmation');
  const confirm = documentRoot.querySelector('#confirm-restart-project-kei');
  const cancel = documentRoot.querySelector('#cancel-restart-project-kei');
  let busy = false;
  let destroyed = false;
  let available = false;
  let generation = null;
  let retryTimer = 0;

  function render(message) {
    if (status) status.textContent = message;
    if (button) {
      button.disabled = busy || !available;
      button.setAttribute('aria-busy', busy ? 'true' : 'false');
      button.textContent = busy ? '正在重启并重连…' : '重启 Project Kei 服务';
    }
  }

  function acceptStatus(payload) {
    available = payload?.available === true;
    const nextGeneration = Number(payload?.generation);
    if (Number.isFinite(nextGeneration)) generation = nextGeneration;
    const state = String(payload?.state || 'unavailable');
    if (!available) {
      render(publicMessage(payload, '受控重启不可用；请通过 Project Kei supervisor 启动服务。'));
    } else if (state === 'failed') {
      render(publicMessage(payload, '上次重启失败，可以安全重试。'));
    } else if (['accepted', 'restarting', 'starting'].includes(state)) {
      render(publicMessage(payload, 'Core 正在重启，请稍候…'));
    } else {
      render(publicMessage(payload, '受控重启已就绪。'));
    }
    return payload;
  }

  async function refreshStatus({ quiet = false } = {}) {
    try {
      return acceptStatus(await request(restartStatusPath, { cache: 'no-store' }));
    } catch (error) {
      available = false;
      render(error?.status === 404
        ? '当前 Core 尚未装配受控重启接口。'
        : `重启状态读取失败：${String(error?.message || '请求失败').slice(0, 160)}`);
      if (!quiet && error?.status !== 404) notify('受控重启状态读取失败。', 'error');
      throw error;
    }
  }

  async function reconnect(startGeneration) {
    const deadline = Date.now() + reconnectLimitMs;
    while (!destroyed && Date.now() < deadline) {
      try {
        const payload = await refreshStatus({ quiet: true });
        const state = String(payload?.state || '');
        const nextGeneration = Number(payload?.generation);
        if (state === 'running' && (!Number.isFinite(startGeneration)
          || (Number.isFinite(nextGeneration) && nextGeneration > startGeneration))) {
          busy = false;
          render('Project Kei Core 已重启并重新连接。');
          notify('Project Kei Core 已重启并重新连接。', 'success');
          return;
        }
        if (state === 'failed') {
          busy = false;
          available = payload?.available === true;
          render(publicMessage(payload, 'Core 重启失败，可以安全重试。'));
          notify('Project Kei Core 重启失败，控制台已恢复可操作状态。', 'error');
          return;
        }
        await new Promise((resolve) => {
          retryTimer = window.setTimeout(resolve, boundedRetryDelay(payload?.retry_after_ms));
        });
      } catch (error) {
        if (Date.now() >= deadline) break;
        render('Core 暂时断开，正在安全重连…');
        await new Promise((resolve) => {
          retryTimer = window.setTimeout(resolve, 1000);
        });
      }
    }
    busy = false;
    available = true;
    render('未能在限定时间内确认重连；请检查 supervisor 状态后重试。');
    notify('Core 重启后的自动重连未确认；控制台已恢复可操作状态。', 'error');
  }

  function openConfirmation() {
    if (busy || !available || !dialog) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    confirm?.focus();
  }

  function closeConfirmation() {
    if (!dialog) return;
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  }

  async function confirmRestart() {
    if (busy || !available) return;
    busy = true;
    closeConfirmation();
    render('正在提交受控重启请求…');
    const startGeneration = generation;
    try {
      const payload = await request(restartRequestPath, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation: restartConfirmation }),
      });
      acceptStatus(payload);
      void reconnect(startGeneration);
    } catch (error) {
      busy = false;
      render(`重启请求失败：${String(error?.message || '请求失败').slice(0, 160)}`);
      notify('Project Kei Core 重启请求失败，控制台已恢复可操作状态。', 'error');
    }
  }

  function cancelDialog(event) {
    event?.preventDefault?.();
    closeConfirmation();
    button?.focus();
  }

  button?.addEventListener('click', openConfirmation);
  confirm?.addEventListener('click', confirmRestart);
  cancel?.addEventListener('click', cancelDialog);
  dialog?.addEventListener('cancel', cancelDialog);
  render('正在检查受控重启能力…');

  return Object.freeze({
    refreshStatus,
    destroy() {
      destroyed = true;
      window.clearTimeout(retryTimer);
      button?.removeEventListener('click', openConfirmation);
      confirm?.removeEventListener('click', confirmRestart);
      cancel?.removeEventListener('click', cancelDialog);
      dialog?.removeEventListener('cancel', cancelDialog);
    },
  });
}

export { restartConfirmation, restartRequestPath, restartStatusPath };
