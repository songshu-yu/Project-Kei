const STATUS_PATH = '/api/v1/briefing/generation-status';
const PHASE_LABELS = Object.freeze({
  idle: '等待生成',
  collecting: '正在采集',
  rewriting: 'Kei 正在改写',
  saving: '正在保存',
  finished: '已结束',
});
const STATE_LABELS = Object.freeze({
  idle: '尚未开始',
  running: '生成中',
  succeeded: '生成成功',
  failed: '生成失败',
});
const SOURCE_LABELS = Object.freeze({
  twitter: 'X',
  github: 'GitHub',
  bilibili: 'B 站',
  youtube: 'YouTube',
  money: 'RSS',
  arxiv: 'arXiv',
  crossref: 'Crossref',
  semantic: 'Semantic Scholar',
});
const SOURCE_STATE_LABELS = Object.freeze({
  not_requested: '未请求',
  pending: '等待',
  running: '采集中',
  complete: '完成',
  partial: '部分完成',
  empty: '今日无内容',
  failed: '失败',
  not_configured: '未配置',
});
const SOURCE_ERROR_LABELS = Object.freeze({
  access_denied: '访问被拒绝',
  anti_bot: '触发平台风控',
  http_error: '上游 HTTP 错误',
  invalid_response: '响应格式无效',
  network_error: '网络连接失败',
  not_found: '资源不存在',
  parse_error: '内容解析失败',
  rate_limited: '请求过于频繁',
  redirect_missing_location: '重定向缺少目标',
  redirect_rejected: '重定向被拒绝',
  response_too_large: '响应超过限制',
  timeout: '请求超时',
  too_many_redirects: '重定向过多',
  upstream_failed: '上游请求失败',
  upstream_rejected: '上游拒绝请求',
  upstream_unavailable: '上游暂时不可用',
});
export function renderBriefingProgress(root, status) {
  if (!root || !status || typeof status !== 'object') return;
  const hasSourceFailure = Object.values(status.sources || {})
    .some((value) => value === 'failed' || value === 'partial');
  const state = status.state === 'succeeded' && hasSourceFailure
    ? '处理完成（部分来源失败）'
    : (STATE_LABELS[status.state] || '状态未知');
  const phase = PHASE_LABELS[status.phase] || '阶段未知';
  const completed = Number.isInteger(status.completed_sources) ? status.completed_sources : 0;
  const total = Number.isInteger(status.total_sources) ? status.total_sources : 0;
  const parts = Object.entries(SOURCE_LABELS)
    .map(([sourceId, label]) => {
      const value = status.sources?.[sourceId];
      const codes = Array.isArray(status.source_error_codes?.[sourceId])
        ? status.source_error_codes[sourceId]
        : [];
      const reason = codes.length
        ? `（${codes.map((code) => SOURCE_ERROR_LABELS[code] || code).join('、')}）`
        : '';
      return value && value !== 'not_requested'
        ? `${label}：${SOURCE_STATE_LABELS[value] || '未知'}${reason}`
        : '';
    })
    .filter(Boolean);
  const progress = total > 0 ? ` · 来源 ${completed}/${total}` : '';
  const sources = parts.length ? `\n${parts.join(' · ')}` : '';
  root.textContent = `${state} · ${phase}${progress}${sources}`;
  root.dataset.state = String(status.state || 'idle');
}

export function createBriefingProgressMonitor({
  request,
  root,
  intervalMs = 1000,
  maxPolls = 2160,
  setTimer = (callback, delay) => window.setTimeout(callback, delay),
  clearTimer = (timer) => window.clearTimeout(timer),
}) {
  if (typeof request !== 'function') throw new TypeError('request must be a function');
  let timer = null;
  let epoch = 0;
  let polls = 0;
  let active = false;
  let waitForStart = false;
  const stop = () => {
    active = false;
    waitForStart = false;
    epoch += 1;
    if (timer !== null) clearTimer(timer);
    timer = null;
  };

  const poll = async (runEpoch) => {
    if (!active || runEpoch !== epoch) return;
    polls += 1;
    try {
      const status = await request(STATUS_PATH);
      if (!active || runEpoch !== epoch) return;
      renderBriefingProgress(root, status);
      const waiting = waitForStart && status.state === 'idle' && polls < 10;
      if ((status.state === 'running' || waiting) && polls < maxPolls) {
        timer = setTimer(() => void poll(runEpoch), intervalMs);
        return;
      }
    } catch (_error) {
      if (active && runEpoch === epoch && polls < maxPolls) {
        timer = setTimer(() => void poll(runEpoch), intervalMs);
        return;
      }
    }
    active = false;
    timer = null;
  };

  const start = ({ awaitStart = false } = {}) => {
    stop();
    active = true;
    waitForStart = Boolean(awaitStart);
    polls = 0;
    const runEpoch = epoch;
    void poll(runEpoch);
  };

  const restore = async () => {
    const status = await request(STATUS_PATH);
    renderBriefingProgress(root, status);
    if (status.state === 'running') start();
    return status;
  };

  const finish = async () => {
    stop();
    try {
      const status = await request(STATUS_PATH);
      renderBriefingProgress(root, status);
      return status;
    } catch (_error) {
      return null;
    }
  };

  return Object.freeze({
    start,
    stop,
    restore,
    finish,
    isActive: () => active,
    pollCount: () => polls,
  });
}

export { STATUS_PATH };
