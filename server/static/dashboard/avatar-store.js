import { request } from './request.js?v=pk100-20260730-modules1';

export const avatarApiRoot = '/api/v1/dashboard/ui-assets';

let avatarCatalogPromise = null;

function encodedPanelId(panelId) {
  const value = String(panelId || '').trim();
  if (!value || value.length > 128) throw new TypeError('invalid panel id');
  return encodeURIComponent(value);
}

export async function loadAvatarCatalog({ refresh = false } = {}) {
  if (!avatarCatalogPromise || refresh) {
    avatarCatalogPromise = request(avatarApiRoot, { cache: 'no-store' }).then((payload) => (
      new Map((payload?.avatars || []).map((item) => [item.panel_id, item]))
    ));
  }
  return avatarCatalogPromise;
}

export async function loadPanelAvatar(panelId) {
  const catalog = await loadAvatarCatalog();
  return catalog.get(String(panelId)) || null;
}

export async function savePanelAvatar(panelId, file) {
  const result = await request(
    `${avatarApiRoot}/${encodedPanelId(panelId)}/avatar`,
    {
      method: 'PUT',
      headers: { 'Content-Type': file.type },
      body: file,
    },
  );
  await loadAvatarCatalog({ refresh: true });
  return result;
}

export async function deletePanelAvatar(panelId) {
  const result = await request(
    `${avatarApiRoot}/${encodedPanelId(panelId)}/avatar`,
    { method: 'DELETE' },
  );
  await loadAvatarCatalog({ refresh: true });
  return result;
}
