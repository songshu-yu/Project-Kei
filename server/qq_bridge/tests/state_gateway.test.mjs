import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { createGatewayClient, createGatewayStatusFile } from "../src/gateway_client.mjs";
import { createShutdownRequestWatcher } from "../src/shutdown_control.mjs";
import { atomicWriteState, loadStateFile } from "../src/state_store.mjs";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function settlesQuickly(promise, windowMs = 100) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("did_not_settle_before_adapter_window")), windowMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

test("atomic state failure preserves the previous bytes and removes temp files", t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-atomic-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const target = path.join(root, "state.json");
  fs.writeFileSync(target, "old-bytes", "utf8");
  const fakeFs = new Proxy(fs, { get(object, key) { if (key === "renameSync") return () => { throw new Error("FAKE_SECRET_TOKEN"); }; return object[key]; } });
  assert.throws(() => atomicWriteState(target, { token: "FAKE_TOKEN", openid: "FAKE_OPENID" }, { fsImpl: fakeFs, randomId: () => "fixed" }), /state_write_failed/);
  assert.equal(fs.readFileSync(target, "utf8"), "old-bytes");
  assert.deepEqual(fs.readdirSync(root), ["state.json"]);
});

test("corrupt state fails closed without overwriting", t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-corrupt-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const target = path.join(root, "state.json");
  fs.writeFileSync(target, "{broken", "utf8");
  const loaded = loadStateFile(target, { schema_version: 1 });
  assert.equal(loaded.healthy, false);
  assert.equal(fs.readFileSync(target, "utf8"), "{broken");
});

test("gateway reconnect and heartbeat timers remain singletons and shutdown cancels all", async () => {
  const sockets = [];
  class FakeSocket extends EventEmitter {
    static OPEN = 1;
    constructor() { super(); this.readyState = 1; this.sent = []; sockets.push(this); }
    send(value) { this.sent.push(value); }
    close() { this.emit("close"); }
  }
  let timerId = 1;
  const timeouts = new Map();
  const intervals = new Map();
  const logger = { info() {}, warn() {}, error() {} };
  const gateway = createGatewayClient({
    getAccessToken: async () => "FAKE_TOKEN",
    getGatewayUrl: async () => "wss://gateway.invalid",
    WebSocketFactory: FakeSocket,
    onDispatch: async () => {}, logger,
    setTimeoutFn(fn) { const id = timerId++; timeouts.set(id, fn); return id; },
    clearTimeoutFn(id) { timeouts.delete(id); },
    setIntervalFn(fn) { const id = timerId++; intervals.set(id, fn); return id; },
    clearIntervalFn(id) { intervals.delete(id); },
  });
  await Promise.all([gateway.connect(), gateway.connect(), gateway.connect()]);
  assert.equal(sockets.length, 1);
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 1000 } })));
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 1000 } })));
  assert.equal(sockets[0].sent.filter(value => JSON.parse(value).op === 2).length, 1);
  assert.equal(intervals.size, 0);
  sockets[0].emit("close");
  sockets[0].emit("close");
  assert.equal(timeouts.size, 1);
  gateway.stop();
  assert.equal(timeouts.size, 0);
  assert.equal(intervals.size, 0);
  assert.equal(gateway.snapshot().stopping, true);
});

test("gateway requires READY and heartbeat ACK before dispatch or connected status", async () => {
  const sockets = [];
  const statuses = [];
  const dispatches = [];
  const warnings = [];
  class FakeSocket extends EventEmitter {
    constructor() { super(); this.readyState = 1; this.sent = []; sockets.push(this); }
    send(value) { this.sent.push(JSON.parse(value)); }
    close(code) { this.emit("close", code); }
  }
  const timeouts = new Map();
  const intervals = new Map();
  let id = 1;
  const gateway = createGatewayClient({
    getAccessToken: async () => "FICTIONAL_ACCESS_TOKEN",
    getGatewayUrl: async () => "wss://api.bot.qq.com/websocket",
    WebSocketFactory: FakeSocket,
    onDispatch: async (type, event) => dispatches.push([type, event]),
    logger: { info() {}, warn: code => warnings.push(code), error() {} },
    writeStatus: status => statuses.push(structuredClone(status)),
    now: () => 1_800_000_000_000,
    setTimeoutFn(fn) { const key = id++; timeouts.set(key, fn); return key; },
    clearTimeoutFn(key) { timeouts.delete(key); },
    setIntervalFn(fn) { const key = id++; intervals.set(key, fn); return key; },
    clearIntervalFn(key) { intervals.delete(key); },
  });
  await gateway.connect();
  const socket = sockets[0];
  socket.emit("message", Buffer.from(JSON.stringify({ op: 0, t: "READY", s: 90, d: {} })));
  assert.equal(socket.sent.filter(item => item.op === 1).length, 0);
  socket.emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 45_000 } })));
  assert.equal(socket.sent[0].op, 2);
  assert.equal(socket.sent[0].d.intents, 1 << 25);
  assert.equal(socket.sent.filter(item => item.op === 1).length, 0);
  socket.emit("message", Buffer.from(JSON.stringify({ op: 11, d: null })));
  assert.equal(gateway.snapshot().gatewayReady, false);
  assert.equal(gateway.snapshot().heartbeatHealthy, false);
  assert.equal(warnings.at(-1), "gateway_heartbeat_ack_unexpected");
  socket.emit("message", Buffer.from(JSON.stringify({ op: 0, t: "READY", s: 1, d: {} })));
  assert.equal(socket.sent.filter(item => item.op === 1).length, 1);
  assert.equal(socket.sent.filter(item => item.op === 1)[0].d, 1);
  assert.equal(intervals.size, 1);
  socket.emit("message", Buffer.from(JSON.stringify({ op: 0, t: "READY", s: 99, d: {} })));
  assert.equal(socket.sent.filter(item => item.op === 1).length, 1);
  assert.equal(intervals.size, 1);
  assert.equal(warnings.at(-1), "gateway_duplicate_ready");
  socket.emit("message", Buffer.from(JSON.stringify({ op: 0, t: "C2C_MESSAGE_CREATE", s: 77, d: { id: "before-ack" } })));
  assert.equal(gateway.snapshot().gatewayReady, false);
  assert.equal(dispatches.length, 0);
  socket.emit("message", Buffer.from(JSON.stringify({ op: 11, d: null })));
  assert.equal(gateway.snapshot().gatewayReady, true);
  const heartbeat = [...intervals.values()][0];
  heartbeat();
  assert.equal(socket.sent.filter(item => item.op === 1).at(-1).d, 1);
  socket.emit("message", Buffer.from(JSON.stringify({ op: 0, t: "C2C_MESSAGE_CREATE", s: 88, d: { id: "after-ack" } })));
  assert.equal(dispatches.length, 1);
  socket.emit("message", Buffer.from(JSON.stringify({ op: 11, s: 123, d: null })));
  heartbeat();
  assert.equal(socket.sent.filter(item => item.op === 1).at(-1).d, 88);
  assert.equal(statuses.at(-1).gateway_ready, true);
  assert.equal(statuses.at(-1).last_error_code, null);
  gateway.stop();
  assert.equal(statuses.at(-1).state, "stopped");
  assert.equal(timeouts.size, 0);
  assert.equal(intervals.size, 0);
});

test("invalid session, server reconnect, close, and eventual READY use one reconnect path", async () => {
  const sockets = [];
  class FakeSocket extends EventEmitter {
    constructor() { super(); this.readyState = 1; this.sent = []; sockets.push(this); }
    send(value) { this.sent.push(JSON.parse(value)); }
    close(code) { this.emit("close", code); }
  }
  let id = 1;
  const timeouts = new Map();
  const intervals = new Map();
  const gateway = createGatewayClient({
    getAccessToken: async () => "FICTIONAL_ACCESS_TOKEN",
    getGatewayUrl: async () => "wss://api.bot.qq.com/websocket",
    WebSocketFactory: FakeSocket,
    onDispatch: async () => {},
    logger: { info() {}, warn() {}, error() {} },
    setTimeoutFn(fn) { const key = id++; timeouts.set(key, fn); return key; },
    clearTimeoutFn(key) { timeouts.delete(key); },
    setIntervalFn(fn) { const key = id++; intervals.set(key, fn); return key; },
    clearIntervalFn(key) { intervals.delete(key); },
  });
  await gateway.connect();
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 1000 } })));
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 9, d: false })));
  assert.equal(gateway.snapshot().state, "reconnect_wait");
  assert.equal(gateway.snapshot().lastErrorCode, "invalid_session");
  assert.equal(timeouts.size, 1);
  const [retryId, retry] = [...timeouts.entries()][0];
  timeouts.delete(retryId);
  retry();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(sockets.length, 2);
  sockets[1].emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 1000 } })));
  sockets[1].emit("message", Buffer.from(JSON.stringify({ op: 0, t: "READY", s: 9, d: {} })));
  sockets[1].emit("message", Buffer.from(JSON.stringify({ op: 11, d: null })));
  assert.equal(gateway.snapshot().gatewayReady, true);
  sockets[1].emit("message", Buffer.from(JSON.stringify({ op: 7, d: null })));
  assert.equal(gateway.snapshot().state, "reconnect_wait");
  assert.equal(gateway.snapshot().lastErrorCode, "server_reconnect");
  gateway.stop();
});

test("heartbeat timeout fails closed and never dispatches", async () => {
  const sockets = [];
  let dispatches = 0;
  let id = 1;
  const timeouts = new Map();
  const intervals = new Map();
  class FakeSocket extends EventEmitter {
    constructor() { super(); this.readyState = 1; sockets.push(this); }
    send() {}
    close(code) { this.emit("close", code); }
  }
  const gateway = createGatewayClient({
    getAccessToken: async () => "FICTIONAL_ACCESS_TOKEN",
    getGatewayUrl: async () => "wss://api.bot.qq.com/websocket",
    WebSocketFactory: FakeSocket,
    onDispatch: async () => { dispatches += 1; },
    logger: { info() {}, warn() {}, error() {} },
    setTimeoutFn(fn) { const key = id++; timeouts.set(key, fn); return key; },
    clearTimeoutFn(key) { timeouts.delete(key); },
    setIntervalFn(fn) { const key = id++; intervals.set(key, fn); return key; },
    clearIntervalFn(key) { intervals.delete(key); },
  });
  await gateway.connect();
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 1000 } })));
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 0, t: "READY", s: 1, d: {} })));
  const heartbeat = [...intervals.values()][0];
  heartbeat();
  assert.equal(gateway.snapshot().state, "reconnect_wait");
  assert.equal(gateway.snapshot().lastErrorCode, "heartbeat_timeout");
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 0, t: "C2C_MESSAGE_CREATE", d: {} })));
  assert.equal(dispatches, 0);
  gateway.stop();
});

test("gateway status file is atomic, finite, and contains no credentials or event data", t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-gateway-status-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statePath = path.join(root, "gateway_status.json");
  const status = createGatewayStatusFile({
    statePath,
    processId: 4321,
    generation: "a".repeat(32),
    now: () => 1_800_000_000_000,
  });
  status.write({
    state: "identified_or_ready",
    gateway_ready: true,
    heartbeat_healthy: true,
    last_error_code: null,
    last_close_code: null,
    reconnect_count: 2,
    last_ready_at: 1_800_000_000_000,
    token: "FICTIONAL_TOKEN",
    openid: "fictional-openid",
    content: "private message",
  });
  const raw = fs.readFileSync(statePath, "utf8");
  const saved = JSON.parse(raw);
  assert.deepEqual(Object.keys(saved).sort(), [
    "gateway_ready", "generation", "heartbeat_healthy", "last_close_code",
    "last_error_code", "last_ready_at", "pid", "reconnect_count",
    "schema_version", "shutdown_control_ready", "state", "updated_at",
    "voice_last_attempt_at", "voice_last_result_code",
  ]);
  for (const secret of ["FICTIONAL_TOKEN", "fictional-openid", "private message"]) {
    assert.equal(raw.includes(secret), false);
  }
  assert.equal(saved.last_error_code, null);
  assert.equal(saved.shutdown_control_ready, true);
  assert.equal(saved.voice_last_result_code, null);
  assert.equal(saved.voice_last_attempt_at, null);
  status.writeVoiceResult("voice_upload_failed");
  assert.equal(status.snapshot().voice_last_result_code, "voice_upload_failed");
  assert.equal(status.snapshot().voice_last_attempt_at, 1_800_000_000_000);
  status.write({
    state: "identified_or_ready",
    gateway_ready: true,
    heartbeat_healthy: true,
    last_error_code: null,
    reconnect_count: 2,
    last_ready_at: 1_800_000_000_000,
  });
  assert.equal(status.snapshot().voice_last_result_code, "voice_upload_failed");
  status.writeVoiceResult("authorization_fictional_secret");
  assert.equal(status.snapshot().voice_last_result_code, "voice_delivery_failed");
  assert.equal(fs.readFileSync(statePath, "utf8").includes("fictional_secret"), false);
  status.write({
    state: "failed",
    gateway_ready: false,
    heartbeat_healthy: false,
    last_error_code: "authorization_fictional_secret",
    reconnect_count: 3,
  });
  assert.equal(status.snapshot().last_error_code, "gateway_failed");
  assert.equal(fs.readFileSync(statePath, "utf8").includes("fictional_secret"), false);
});

test("shutdown request watcher accepts only one fresh request for the exact generation", t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-shutdown-control-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const requestPath = path.join(root, "shutdown_request.json");
  const generation = "b".repeat(32);
  const nowMs = 1_800_000_000_000;
  let shutdowns = 0;
  const watcher = createShutdownRequestWatcher({
    requestPath,
    generation,
    now: () => nowMs,
    onShutdown: () => { shutdowns += 1; },
  });

  const write = value => fs.writeFileSync(requestPath, JSON.stringify(value), "utf8");
  const valid = {
    schema_version: 1,
    generation,
    requested_at: nowMs,
    expires_at: nowMs + 5000,
  };
  for (const invalid of [
    { ...valid, generation: "c".repeat(32) },
    { ...valid, requested_at: nowMs - 10_001, expires_at: nowMs + 1 },
    { ...valid, expires_at: nowMs - 1 },
    { ...valid, command: "taskkill" },
  ]) {
    write(invalid);
    assert.equal(watcher.inspect(), false);
    assert.equal(shutdowns, 0);
  }
  write(valid);
  assert.equal(watcher.inspect(), true);
  assert.equal(shutdowns, 1);
  assert.equal(fs.existsSync(requestPath), false);
  write(valid);
  assert.equal(watcher.inspect(), false);
  assert.equal(shutdowns, 1);
  watcher.stop();
});

test("shutdown request watcher rejects symlinks and oversized requests before parsing", t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-shutdown-tripwire-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const requestPath = path.join(root, "shutdown_request.json");
  const target = path.join(root, "outside.json");
  fs.writeFileSync(target, JSON.stringify({ schema_version: 1 }), "utf8");
  let shutdowns = 0;
  const watcher = createShutdownRequestWatcher({
    requestPath,
    generation: "d".repeat(32),
    onShutdown: () => { shutdowns += 1; },
  });
  try {
    fs.symlinkSync(target, requestPath, "file");
    assert.equal(watcher.inspect(), false);
    fs.unlinkSync(requestPath);
  } catch (error) {
    if (error?.code !== "EPERM") throw error;
  }
  fs.writeFileSync(requestPath, "x".repeat(513), "utf8");
  assert.equal(watcher.inspect(), false);
  assert.equal(shutdowns, 0);
  watcher.stop();
});

test("Gateway bootstrap phases expose only fixed codes and shutdown blocks stale retry", async () => {
  const error = code => Object.assign(new Error(`PRIVATE_${code}_BODY https://private.invalid/path`), { code });
  const cases = [
    ["token network", async () => { throw error("private_network_failure"); }, async () => "wss://api.bot.qq.com/websocket", "token_request_failed"],
    ["token 401", async () => { throw error("http_401"); }, async () => "wss://api.bot.qq.com/websocket", "token_rejected"],
    ["token invalid body", async () => { throw error("invalid_response"); }, async () => "wss://api.bot.qq.com/websocket", "token_response_invalid"],
    ["gateway network", async () => "FICTIONAL_TOKEN", async () => { throw error("private_network_failure"); }, "gateway_request_failed"],
    ["gateway 401", async () => "FICTIONAL_TOKEN", async () => { throw error("http_401"); }, "gateway_rejected"],
    ["gateway invalid body", async () => "FICTIONAL_TOKEN", async () => { throw error("invalid_response"); }, "gateway_response_invalid"],
    ["gateway invalid URL", async () => "FICTIONAL_TOKEN", async () => { throw error("gateway_url_rejected"); }, "gateway_url_rejected"],
  ];
  assert.equal(new Set(cases.map(item => item[3])).size, cases.length);
  for (const [name, getAccessToken, getGatewayUrl, expected] of cases) {
    let tokenCalls = 0;
    let gatewayCalls = 0;
    let sockets = 0;
    const statuses = [];
    const warnings = [];
    const timeouts = new Map();
    let timerId = 1;
    const gateway = createGatewayClient({
      getAccessToken: async signal => { tokenCalls += 1; return getAccessToken(signal); },
      getGatewayUrl: async signal => { gatewayCalls += 1; return getGatewayUrl(signal); },
      WebSocketFactory: class { constructor() { sockets += 1; } },
      onDispatch: async () => {},
      logger: { info() {}, warn: code => warnings.push(code), error() {} },
      writeStatus: status => statuses.push(structuredClone(status)),
      setTimeoutFn(fn) { const id = timerId++; timeouts.set(id, fn); return id; },
      clearTimeoutFn(id) { timeouts.delete(id); },
    });
    await gateway.connect();
    assert.equal(gateway.snapshot().state, "reconnect_wait", name);
    assert.equal(gateway.snapshot().lastErrorCode, expected, name);
    assert.equal(timeouts.size, 1, name);
    assert.equal(sockets, 0, name);
    const serialized = JSON.stringify({ statuses, warnings });
    for (const forbidden of ["PRIVATE_", "private.invalid", "FICTIONAL_TOKEN", "/path"]) {
      assert.equal(serialized.includes(forbidden), false, `${name}: ${forbidden}`);
    }
    const staleRetry = [...timeouts.values()][0];
    const countsAtStop = [tokenCalls, gatewayCalls, sockets];
    gateway.stop();
    staleRetry();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual([tokenCalls, gatewayCalls, sockets], countsAtStop, name);
    assert.equal(gateway.snapshot().hasReconnect, false, name);
  }
});

test("WebSocket constructor, transport, Hello and READY failures have stable bounded codes", async () => {
  const scenarios = [
    ["constructor", "websocket_constructor_failed"],
    ["error", "websocket_error"],
    ["close", "websocket_closed"],
    ["hello timeout", "gateway_hello_timeout"],
    ["ready timeout", "gateway_ready_timeout"],
  ];
  assert.equal(new Set(scenarios.map(item => item[1])).size, scenarios.length);
  for (const [scenario, expected] of scenarios) {
    const sockets = [];
    const timeouts = new Map();
    const intervals = new Map();
    let timerId = 1;
    class FakeSocket extends EventEmitter {
      constructor() {
        super();
        if (scenario === "constructor") throw new Error("PRIVATE_CONSTRUCTOR_SECRET");
        this.readyState = 1;
        sockets.push(this);
      }
      send() {}
      close(code) { this.emit("close", code); }
    }
    const gateway = createGatewayClient({
      getAccessToken: async () => "FICTIONAL_TOKEN",
      getGatewayUrl: async () => "wss://api.bot.qq.com/websocket",
      WebSocketFactory: FakeSocket,
      onDispatch: async () => {},
      logger: { info() {}, warn() {}, error() {} },
      setTimeoutFn(fn) { const id = timerId++; timeouts.set(id, fn); return id; },
      clearTimeoutFn(id) { timeouts.delete(id); },
      setIntervalFn(fn) { const id = timerId++; intervals.set(id, fn); return id; },
      clearIntervalFn(id) { intervals.delete(id); },
    });
    await gateway.connect();
    if (scenario === "error") sockets[0].emit("error", new Error("PRIVATE_SOCKET_SECRET"));
    if (scenario === "close") sockets[0].emit("close", 1006);
    if (scenario === "hello timeout") [...timeouts.values()][0]();
    if (scenario === "ready timeout") {
      sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 1000 } })));
      [...timeouts.values()][0]();
    }
    assert.equal(gateway.snapshot().state, "reconnect_wait", scenario);
    assert.equal(gateway.snapshot().lastErrorCode, expected, scenario);
    assert.equal(gateway.snapshot().hasReconnect, true, scenario);
    const staleRetry = [...timeouts.values()][0];
    const socketsAtStop = sockets.length;
    gateway.stop();
    staleRetry();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sockets.length, socketsAtStop, scenario);
    assert.equal(gateway.snapshot().state, "stopped", scenario);
    assert.equal(gateway.snapshot().hasReconnect, false, scenario);
    assert.equal(gateway.snapshot().hasPhaseTimer, false, scenario);
    assert.equal(intervals.size, 0, scenario);
  }
});

test("stop promptly settles pending token bootstrap and ignores its late result", async () => {
  const token = deferred();
  let gatewayCalls = 0;
  let sockets = 0;
  const statuses = [];
  const gateway = createGatewayClient({
    getAccessToken: signal => {
      assert.equal(signal.aborted, false);
      return token.promise;
    },
    getGatewayUrl: async () => { gatewayCalls += 1; return "wss://api.bot.qq.com/websocket"; },
    WebSocketFactory: class { constructor() { sockets += 1; } },
    onDispatch: async () => {},
    logger: { info() {}, warn() {}, error() {} },
    writeStatus: value => statuses.push(value.state),
  });
  const connecting = gateway.connect();
  await Promise.resolve();
  gateway.stop();
  await settlesQuickly(connecting);
  const countAtStop = statuses.length;
  token.resolve("LATE_FICTIONAL_TOKEN");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(gatewayCalls, 0);
  assert.equal(sockets, 0);
  assert.equal(statuses.length, countAtStop);
  assert.equal(statuses.at(-1), "stopped");
  gateway.stop();
});

test("stop promptly settles pending Gateway URL and ignores late resolve or reject", async () => {
  for (const late of ["resolve", "reject"]) {
    const url = deferred();
    let urlSignal;
    let sockets = 0;
    const statuses = [];
    const gateway = createGatewayClient({
      getAccessToken: async () => "FICTIONAL_TOKEN",
      getGatewayUrl: signal => { urlSignal = signal; return url.promise; },
      WebSocketFactory: class { constructor() { sockets += 1; } },
      onDispatch: async () => {},
      logger: { info() {}, warn() {}, error() {} },
      writeStatus: value => statuses.push(value.state),
    });
    const connecting = gateway.connect();
    while (!urlSignal) await Promise.resolve();
    gateway.stop();
    assert.equal(urlSignal.aborted, true);
    await settlesQuickly(connecting);
    const countAtStop = statuses.length;
    if (late === "resolve") url.resolve("wss://api.bot.qq.com/websocket");
    else url.reject(new Error("LATE_PRIVATE_UPSTREAM_BODY"));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sockets, 0);
    assert.equal(statuses.length, countAtStop);
    assert.equal(statuses.at(-1), "stopped");
  }
});

test("stop terminates a CONNECTING socket and late events cannot revive state or dispatch", async () => {
  const sockets = [];
  let dispatches = 0;
  const statuses = [];
  class ConnectingSocket extends EventEmitter {
    constructor() { super(); this.readyState = 0; this.terminated = 0; sockets.push(this); }
    close() {}
    terminate() { this.terminated += 1; }
    send() {}
  }
  const gateway = createGatewayClient({
    getAccessToken: async () => "FICTIONAL_TOKEN",
    getGatewayUrl: async () => "wss://api.bot.qq.com/websocket",
    WebSocketFactory: ConnectingSocket,
    onDispatch: async () => { dispatches += 1; },
    logger: { info() {}, warn() {}, error() {} },
    writeStatus: value => statuses.push(value.state),
  });
  await gateway.connect();
  gateway.stop();
  gateway.stop();
  assert.equal(sockets[0].terminated, 1);
  const countAtStop = statuses.length;
  sockets[0].emit("open");
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 10, d: { heartbeat_interval: 1000 } })));
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 11 })));
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 0, t: "READY", d: {} })));
  sockets[0].emit("message", Buffer.from(JSON.stringify({ op: 0, t: "C2C_MESSAGE_CREATE", d: {} })));
  assert.equal(dispatches, 0);
  assert.equal(statuses.length, countAtStop);
  assert.equal(gateway.snapshot().state, "stopped");
  assert.equal(gateway.snapshot().hasPhaseTimer, false);
});

test("index installs the single stdin shutdown channel before every startup await", () => {
  const source = fs.readFileSync(new URL("../src/index.mjs", import.meta.url), "utf8");
  const listener = source.indexOf('process.stdin.on("data", stdinListener)');
  assert.ok(listener > 0);
  for (const awaitedStartup of [
    "await dailyScheduler.start",
    "await lifeScheduler.start",
    "await gateway.connect",
  ]) {
    assert.ok(listener < source.indexOf(awaitedStartup), awaitedStartup);
  }
  assert.equal(source.match(/process\.stdin\.on\("data", stdinListener\)/g)?.length, 1);
  assert.ok(source.indexOf("lifecycleController.abort()") < source.indexOf("gateway.stop()"));
});
