import assert from 'node:assert/strict';
import {
  STATUS_PATH,
  createBriefingProgressMonitor,
  renderBriefingProgress,
} from '../static/dashboard/briefing-progress.js';

function root() {
  return {textContent: '', dataset: {}};
}

function status(state, phase = state === 'running' ? 'collecting' : 'finished') {
  return {
    state,
    phase,
    completed_sources: state === 'running' ? 1 : 2,
    total_sources: 2,
    sources: {
      twitter: 'complete',
      github: state === 'running' ? 'running' : 'failed',
      bilibili: 'not_requested',
      youtube: 'not_requested',
      money: 'not_requested',
      arxiv: 'not_requested',
      crossref: 'not_requested',
      semantic: 'not_requested',
    },
    source_error_codes: {
      twitter: [],
      github: state === 'running' ? [] : ['timeout'],
    },
    error_code: state === 'failed' ? 'generation_failed' : null,
  };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

{
  const target = root();
  renderBriefingProgress(target, status('running'));
  assert.match(target.textContent, /生成中 · 正在采集 · 来源 1\/2/);
  assert.match(target.textContent, /X：完成/);
  assert.match(target.textContent, /GitHub：采集中/);
  assert.equal(target.dataset.state, 'running');
}

{
  const target = root();
  const timers = [];
  const responses = [status('running'), status('succeeded')];
  const calls = [];
  const monitor = createBriefingProgressMonitor({
    request: async (path) => {
      calls.push(path);
      return responses.shift();
    },
    root: target,
    intervalMs: 1,
    maxPolls: 5,
    setTimer: (callback) => {
      timers.push(callback);
      return timers.length;
    },
    clearTimer: () => {},
  });
  monitor.start();
  await flush();
  assert.equal(monitor.isActive(), true);
  assert.equal(timers.length, 1);
  timers.shift()();
  await flush();
  assert.equal(monitor.isActive(), false);
  assert.equal(calls.length, 2);
  assert.ok(calls.every((path) => path === STATUS_PATH));
  assert.match(target.textContent, /处理完成（部分来源失败）/);
  assert.match(target.textContent, /来源 2\/2/);
  assert.match(target.textContent, /GitHub：失败（请求超时）/);
  assert.doesNotMatch(target.textContent, /B 站|YouTube|RSS/);
}

{
  const target = root();
  const timers = [];
  let calls = 0;
  const monitor = createBriefingProgressMonitor({
    request: async () => {
      calls += 1;
      return status('running', 'rewriting');
    },
    root: target,
    maxPolls: 3,
    setTimer: (callback) => {
      timers.push(callback);
      return timers.length;
    },
    clearTimer: () => {},
  });
  await monitor.restore();
  await flush();
  assert.equal(monitor.isActive(), true);
  assert.match(target.textContent, /Kei 正在改写/);
  monitor.stop();
  assert.equal(monitor.isActive(), false);
  const queued = timers.shift();
  if (queued) queued();
  await flush();
  assert.equal(calls, 2);
}

{
  const target = root();
  const timers = [];
  const monitor = createBriefingProgressMonitor({
    request: async () => {
      throw new Error('fictional failure body');
    },
    root: target,
    maxPolls: 2,
    setTimer: (callback) => {
      timers.push(callback);
      return timers.length;
    },
    clearTimer: () => {},
  });
  monitor.start();
  await flush();
  assert.equal(timers.length, 1);
  timers.shift()();
  await flush();
  assert.equal(monitor.isActive(), false);
  assert.equal(monitor.pollCount(), 2);
  assert.doesNotMatch(target.textContent, /fictional/);
}

console.log('dashboard briefing progress tests passed');
