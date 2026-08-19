const DEFAULT_TIMEOUT_MS = 10000;
const MAX_ERROR_LENGTH = 240;

export class DashboardRequestError extends Error {
  constructor(message, {
    status = 0,
    code = 'request_failed',
    stage = '',
    retryable = false,
    receivedBytes = 0,
    retryAfter = null,
  } = {}) {
    super(message);
    this.name = 'DashboardRequestError';
    this.status = status;
    this.code = code;
    this.stage = stage;
    this.retryable = retryable;
    this.receivedBytes = receivedBytes;
    this.retryAfter = retryAfter;
  }
}

function safeMessage(value, fallback = '请求失败') {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return (text || fallback).slice(0, MAX_ERROR_LENGTH);
}

function structuredErrorDetail(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {
      message: safeMessage(value),
      code: 'http_error',
      stage: '',
      retryable: false,
      receivedBytes: 0,
      retryAfter: null,
    };
  }
  const stageValue = typeof value.stage === 'string'
    ? value.stage.trim().slice(0, 80)
    : '';
  const message = safeMessage(value.message || value.detail || value.code);
  const receivedBytes = Number(value.received_bytes);
  return {
    message: safeMessage(`${message}${stageValue ? `（阶段：${stageValue}）` : ''}`),
    code: typeof value.code === 'string' && value.code.trim()
      ? value.code.trim().slice(0, 80)
      : 'http_error',
    stage: stageValue,
    retryable: value.retryable === true,
    receivedBytes: Number.isFinite(receivedBytes) && receivedBytes >= 0 ? receivedBytes : 0,
    retryAfter: typeof value.retry_after === 'string' || Number.isFinite(value.retry_after)
      ? String(value.retry_after).slice(0, 80)
      : null,
  };
}

export function resolveSameOriginUrl(path) {
  if (typeof path !== 'string' || !path.trim()) {
    throw new DashboardRequestError('请求地址不能为空', { code: 'invalid_url' });
  }
  const url = new URL(path, window.location.href);
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== window.location.origin) {
    throw new DashboardRequestError('控制台只允许访问同源 HTTP(S) 接口', { code: 'cross_origin' });
  }
  return url;
}

async function responsePayload(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      return await response.json();
    } catch (_error) {
      return null;
    }
  }
  const text = await response.text();
  return text || null;
}

export async function request(path, options = {}) {
  const url = resolveSameOriginUrl(path);
  const timeoutMs = Number.isFinite(options.timeoutMs) && options.timeoutMs > 0
    ? options.timeoutMs
    : DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const fetchOptions = { ...options, signal: controller.signal };
  delete fetchOptions.timeoutMs;

  try {
    const response = await fetch(url, fetchOptions);
    const payload = await responsePayload(response);
    if (!response.ok) {
      const detail = payload && typeof payload === 'object'
        ? payload.detail || payload.message
        : payload;
      const resolved = structuredErrorDetail(detail);
      throw new DashboardRequestError(resolved.message, {
        status: response.status,
        code: resolved.code,
        stage: resolved.stage,
        retryable: resolved.retryable,
        receivedBytes: resolved.receivedBytes,
        retryAfter: resolved.retryAfter,
      });
    }
    return payload;
  } catch (error) {
    if (error instanceof DashboardRequestError) throw error;
    if (error?.name === 'AbortError') {
      throw new DashboardRequestError('请求超时，请稍后重试', { code: 'timeout' });
    }
    throw new DashboardRequestError(safeMessage(error?.message, '网络请求失败'), {
      code: 'network_error',
    });
  } finally {
    window.clearTimeout(timeout);
  }
}

function pathMatchesPrefix(pathname, prefix) {
  return pathname === prefix || pathname.startsWith(prefix.endsWith('/') ? prefix : `${prefix}/`);
}

export function createScopedRequest(moduleInfo) {
  const prefixes = [...(moduleInfo.api_namespaces || []), ...(moduleInfo.legacy_endpoints || [])]
    .filter((value) => typeof value === 'string' && value.startsWith('/'));
  return (path, options = {}) => {
    const url = resolveSameOriginUrl(path);
    if (!prefixes.some((prefix) => pathMatchesPrefix(url.pathname, prefix))) {
      throw new DashboardRequestError(`模块 ${moduleInfo.key} 不能访问未声明的接口`, {
        code: 'namespace_denied',
      });
    }
    return request(url.href, options);
  };
}
