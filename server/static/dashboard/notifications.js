export function notify(text, type = 'success') {
  const notice = document.querySelector('#notice');
  if (!notice) return;
  const safeType = type === 'error' ? 'error' : 'success';
  notice.textContent = String(text ?? '');
  notice.className = `notice show ${safeType}`;
  notice.setAttribute('role', safeType === 'error' ? 'alert' : 'status');
  notice.setAttribute('aria-live', safeType === 'error' ? 'assertive' : 'polite');
}

export function clearNotification() {
  const notice = document.querySelector('#notice');
  if (!notice) return;
  notice.textContent = '';
  notice.className = 'notice';
  notice.removeAttribute('role');
  notice.removeAttribute('aria-live');
}
