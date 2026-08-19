import {
  deletePanelAvatar,
  loadPanelAvatar,
  savePanelAvatar,
} from './avatar-store.js?v=pk100-20260730-modules1';
import { notify } from './notifications.js?v=pk100-20260730-modules1';

const statusVisualIds = Object.freeze({
  normal: 'service-status-normal',
  attention: 'service-status-attention',
});
const statusVisualLabels = Object.freeze({
  normal: '正常状态',
  attention: '需要处理状态',
});
const defaultStatusVisualVersion = 'pk100-20260730-defaults1';
const defaultStatusVisuals = Object.freeze({
  normal: `/dashboard/static/default-avatars/service-status-normal.png?v=${defaultStatusVisualVersion}`,
  attention: `/dashboard/static/default-avatars/service-status-attention.png?v=${defaultStatusVisualVersion}`,
});
const imageTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
const imageMaxBytes = 8 * 1024 * 1024;
const statusRecords = new Map();
const statusInputs = new Map();

function renderStatusVisual(root, state) {
  const record = statusRecords.get(state);
  root.querySelectorAll(`[data-service-visual-state="${state}"]`).forEach((control) => {
    const slot = control.querySelector('.service-status-visual-slot');
    if (!slot) return;
    const placeholder = control.querySelector('.service-status-visual-placeholder');
    let image = control.querySelector('.service-status-visual-image');
    const source = record?.url
      ? `${record.url}?v=${encodeURIComponent(record.updated_at || String(record.size || 'current'))}`
      : defaultStatusVisuals[state];
    if (source) {
      if (!image) {
        image = root.createElement('img');
        image.className = 'service-status-visual-image';
        image.alt = '';
        image.draggable = false;
        slot.append(image);
      }
      image.src = source;
      image.hidden = false;
      if (placeholder) placeholder.hidden = true;
    } else {
      if (image) {
        image.removeAttribute('src');
        image.hidden = true;
      }
      if (placeholder) placeholder.hidden = false;
    }
  });
}

async function restoreStatusVisual(root, state) {
  try {
    statusRecords.set(state, await loadPanelAvatar(statusVisualIds[state]));
  } catch (_error) {
    statusRecords.set(state, null);
  }
  renderStatusVisual(root, state);
}

function ensureStatusInput(root, state) {
  const existing = statusInputs.get(state);
  if (existing?.isConnected) return existing;
  const input = root.createElement('input');
  input.type = 'file';
  input.accept = 'image/png,image/jpeg,image/webp';
  input.hidden = true;
  input.dataset.serviceStatusVisualInput = state;
  input.addEventListener('change', async () => {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (!imageTypes.has(file.type) || file.size > imageMaxBytes) {
      notify('请选择 8MB 内的 PNG、JPG 或 WebP', 'error');
      return;
    }
    try {
      const record = await savePanelAvatar(statusVisualIds[state], file);
      statusRecords.set(state, record);
      renderStatusVisual(root, state);
      notify(`${statusVisualLabels[state]}图片已保存为本机自定义素材。`, 'success');
    } catch (_error) {
      notify(`${statusVisualLabels[state]}图片保存失败；项目默认状态图未改变。`, 'error');
    }
  });
  root.body.append(input);
  statusInputs.set(state, input);
  return input;
}

export function setupServiceStatusVisuals(root = document) {
  Object.keys(statusVisualIds).forEach((state) => {
    const input = ensureStatusInput(root, state);
    root.querySelectorAll(`[data-service-visual-state="${state}"]`).forEach((control) => {
      if (control.dataset.serviceVisualReady) return;
      control.dataset.serviceVisualReady = 'true';
      control.querySelector('[data-service-visual-upload]')?.addEventListener('click', () => input.click());
      control.querySelector('[data-service-visual-reset]')?.addEventListener('click', async () => {
        try {
          await deletePanelAvatar(statusVisualIds[state]);
          statusRecords.set(state, null);
          renderStatusVisual(root, state);
          control.removeAttribute('open');
          notify(`${statusVisualLabels[state]}图片已恢复为项目默认素材。`, 'success');
        } catch (_error) {
          notify(`${statusVisualLabels[state]}图片恢复失败，请确认本机 API 正常运行。`, 'error');
        }
      });
    });
    void restoreStatusVisual(root, state);
  });
}
