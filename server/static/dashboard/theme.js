export const themeStorageKey = 'project-kei.dashboard.theme.v1';
export const dashboardThemes = Object.freeze(['cloud', 'sakura', 'moon']);
export const defaultDashboardTheme = 'cloud';

export function normalizeDashboardTheme(value) {
  return dashboardThemes.includes(value) ? value : defaultDashboardTheme;
}

export function readDashboardTheme(storage = null) {
  try {
    return normalizeDashboardTheme(storage?.getItem(themeStorageKey));
  } catch (_error) {
    return defaultDashboardTheme;
  }
}

export function writeDashboardTheme(storage, theme) {
  try {
    storage?.setItem(themeStorageKey, normalizeDashboardTheme(theme));
  } catch (_error) {
    // Theme switching remains usable when browser storage is unavailable.
  }
}

export function applyDashboardTheme(theme, root = document.documentElement) {
  const normalized = normalizeDashboardTheme(theme);
  root.dataset.theme = normalized;
  root.style.colorScheme = normalized === 'moon' ? 'dark' : 'light';
  return normalized;
}

function browserStorage() {
  try {
    return window.localStorage;
  } catch (_error) {
    return null;
  }
}

export function setupDashboardTheme({
  root = document.documentElement,
  control = document.querySelector('#dashboard-theme'),
  storage = browserStorage(),
} = {}) {
  const initial = applyDashboardTheme(readDashboardTheme(storage), root);
  if (!control) return Object.freeze({ theme: initial, destroy() {} });

  control.value = initial;
  const onChange = () => {
    const selected = applyDashboardTheme(control.value, root);
    control.value = selected;
    writeDashboardTheme(storage, selected);
  };
  control.addEventListener('change', onChange);
  return Object.freeze({
    theme: initial,
    destroy: () => control.removeEventListener('change', onChange),
  });
}

function bootstrapTheme() {
  setupDashboardTheme();
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrapTheme, { once: true });
  } else {
    bootstrapTheme();
  }
}
