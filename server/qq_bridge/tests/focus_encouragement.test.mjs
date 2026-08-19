import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  createFocusEncouragementScheduler,
  validateFocusEncouragementState,
} from "../src/focus_encouragement_scheduler.mjs";

const USER = "fictional-focus-user";
const SESSION = "fictional-session";
const START_AT = "2030-01-02T08:00:00";

function timers() {
  let next = 1;
  const timeouts = new Map();
  return {
    timeouts,
    setTimeoutFn(fn, delay) {
      const id = next++;
      timeouts.set(id, { fn, delay });
      return id;
    },
    clearTimeoutFn(id) {
      timeouts.delete(id);
    },
  };
}

function activeStatus(overrides = {}) {
  return {
    active: true,
    status: "active",
    mode: "pomodoro",
    session_id: SESSION,
    start_at: START_AT,
    elapsed_seconds: 600,
    remaining_seconds: 900,
    ...overrides,
  };
}

function register(scheduler, overrides = {}) {
  return scheduler.register({
    userOpenId: USER,
    sessionId: SESSION,
    startAt: START_AT,
    encouragementAfterMinutes: 10,
    ...overrides,
  });
}

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

test("active focus generates and sends once, then survives restart without duplicate delivery", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-encourage-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statePath = path.join(root, "state.json");
  let statusCalls = 0;
  let generationCalls = 0;
  let sends = 0;
  const make = fakeTimers => createFocusEncouragementScheduler({
    statePath,
    getFocusStatus: async () => { statusCalls += 1; return activeStatus(); },
    generateEncouragement: async payload => {
      generationCalls += 1;
      assert.deepEqual(payload, { session_id: SESSION, start_at: START_AT });
      return { eligible: true, generated: true, text: "虚构模型鼓励" };
    },
    sendText: async (user, inboundId, text) => {
      sends += 1;
      assert.equal(user, USER);
      assert.equal(inboundId, undefined);
      assert.equal(text, "虚构模型鼓励");
    },
    allowedUsers: new Set([USER]),
    now: () => new Date("2030-01-02T08:00:00"),
    ...fakeTimers,
  });
  const first = make(timers());
  first.start();
  register(first);
  const key = Object.keys(first.snapshot().entries)[0];
  await first.deliver(key);
  await first.deliver(key);
  assert.deepEqual({ statusCalls, generationCalls, sends }, { statusCalls: 1, generationCalls: 1, sends: 1 });
  first.stop();

  const secondTimers = timers();
  const second = make(secondTimers);
  second.start();
  assert.equal(secondTimers.timeouts.size, 0);
  await second.deliver(key);
  assert.deepEqual({ statusCalls, generationCalls, sends }, { statusCalls: 1, generationCalls: 1, sends: 1 });
  const raw = fs.readFileSync(statePath, "utf8");
  for (const forbidden of [USER, "虚构模型鼓励", "Authorization", "Token"]) {
    assert.equal(raw.includes(forbidden), false);
  }
  second.stop();
});

test("concurrent delivery attempts claim one status, generation, and send", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-concurrent-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statusGate = deferred();
  let statusCalls = 0;
  let generationCalls = 0;
  let sendCalls = 0;
  const scheduler = createFocusEncouragementScheduler({
    statePath: path.join(root, "state.json"),
    getFocusStatus: async () => {
      statusCalls += 1;
      return statusGate.promise;
    },
    generateEncouragement: async () => {
      generationCalls += 1;
      return { eligible: true, generated: true, text: "fictional" };
    },
    sendText: async () => { sendCalls += 1; },
    allowedUsers: new Set([USER]),
    now: () => new Date("2030-01-02T08:00:00"),
    ...timers(),
  });
  scheduler.start();
  register(scheduler);
  const key = Object.keys(scheduler.snapshot().entries)[0];
  const first = scheduler.deliver(key);
  const second = scheduler.deliver(key);
  assert.equal(statusCalls, 1);
  statusGate.resolve(activeStatus());
  await Promise.all([first, second]);
  assert.deepEqual(
    { statusCalls, generationCalls, sendCalls },
    { statusCalls: 1, generationCalls: 1, sendCalls: 1 },
  );
  assert.equal(scheduler.snapshot().entries[key].status, "sent");
  scheduler.stop();
});

test("cancellation while focus status is pending cannot revive delivery", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-cancel-race-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statusGate = deferred();
  let generationCalls = 0;
  let sendCalls = 0;
  const scheduler = createFocusEncouragementScheduler({
    statePath: path.join(root, "state.json"),
    getFocusStatus: async () => statusGate.promise,
    generateEncouragement: async () => {
      generationCalls += 1;
      return { eligible: true, generated: true, text: "must not run" };
    },
    sendText: async () => { sendCalls += 1; },
    allowedUsers: new Set([USER]),
    now: () => new Date("2030-01-02T08:00:00"),
    ...timers(),
  });
  scheduler.start();
  register(scheduler);
  const key = Object.keys(scheduler.snapshot().entries)[0];
  const pending = scheduler.deliver(key);
  assert.equal(scheduler.cancelUser(USER), true);
  assert.equal(scheduler.snapshot().entries[key].status, "cancelled");
  statusGate.resolve(activeStatus());
  await pending;
  assert.deepEqual({ generationCalls, sendCalls }, { generationCalls: 0, sendCalls: 0 });
  assert.equal(scheduler.snapshot().entries[key].status, "cancelled");
  scheduler.stop();
});

test("new session replacement while focus status is pending keeps old delivery cancelled", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-replace-race-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statusGate = deferred();
  let generationCalls = 0;
  let sendCalls = 0;
  const scheduler = createFocusEncouragementScheduler({
    statePath: path.join(root, "state.json"),
    getFocusStatus: async () => statusGate.promise,
    generateEncouragement: async () => {
      generationCalls += 1;
      return { eligible: true, generated: true, text: "must not run" };
    },
    sendText: async () => { sendCalls += 1; },
    allowedUsers: new Set([USER]),
    now: () => new Date("2030-01-02T08:00:00"),
    ...timers(),
  });
  scheduler.start();
  register(scheduler);
  const oldKey = Object.keys(scheduler.snapshot().entries)[0];
  const pending = scheduler.deliver(oldKey);
  register(scheduler, {
    sessionId: "replacement-session",
    startAt: "2030-01-02T08:01:00",
  });
  const entriesAfterReplacement = scheduler.snapshot().entries;
  const replacementKey = Object.keys(entriesAfterReplacement).find(key => key !== oldKey);
  assert.equal(entriesAfterReplacement[oldKey].status, "cancelled");
  assert.equal(entriesAfterReplacement[replacementKey].status, "scheduled");
  statusGate.resolve(activeStatus());
  await pending;
  assert.deepEqual({ generationCalls, sendCalls }, { generationCalls: 0, sendCalls: 0 });
  const finalEntries = scheduler.snapshot().entries;
  assert.equal(finalEntries[oldKey].status, "cancelled");
  assert.equal(finalEntries[replacementKey].status, "scheduled");
  scheduler.stop();
});

test("allowlist removal while focus status is pending cancels before generation", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-allowlist-race-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statusGate = deferred();
  const allowedUsers = new Set([USER]);
  let generationCalls = 0;
  let sendCalls = 0;
  const scheduler = createFocusEncouragementScheduler({
    statePath: path.join(root, "state.json"),
    getFocusStatus: async () => statusGate.promise,
    generateEncouragement: async () => {
      generationCalls += 1;
      return { eligible: true, generated: true, text: "must not run" };
    },
    sendText: async () => { sendCalls += 1; },
    allowedUsers,
    now: () => new Date("2030-01-02T08:00:00"),
    ...timers(),
  });
  scheduler.start();
  register(scheduler);
  const key = Object.keys(scheduler.snapshot().entries)[0];
  const pending = scheduler.deliver(key);
  allowedUsers.delete(USER);
  statusGate.resolve(activeStatus());
  await pending;
  assert.deepEqual({ generationCalls, sendCalls }, { generationCalls: 0, sendCalls: 0 });
  assert.equal(scheduler.snapshot().entries[key].status, "cancelled");
  scheduler.stop();
});

test("scheduled state restores one timer and duplicate registration never accumulates timers", t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-restore-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statePath = path.join(root, "state.json");
  const firstTimers = timers();
  const common = {
    statePath,
    getFocusStatus: async () => activeStatus(),
    generateEncouragement: async () => ({ eligible: true, generated: false, text: "" }),
    sendText: async () => {},
    allowedUsers: new Set([USER]),
    now: () => new Date("2030-01-02T08:00:00"),
  };
  const first = createFocusEncouragementScheduler({ ...common, ...firstTimers });
  first.start();
  assert.equal(register(first), true);
  assert.equal(register(first), false);
  assert.equal(firstTimers.timeouts.size, 1);
  first.stop();

  const secondTimers = timers();
  const second = createFocusEncouragementScheduler({ ...common, ...secondTimers });
  second.start();
  assert.equal(secondTimers.timeouts.size, 1);
  second.stop();
});

test("inactive, completed, replaced, malformed, missing, and timed-out focus status cause zero model and zero send", async t => {
  const cases = {
    inactive: activeStatus({ active: false, remaining_seconds: 0 }),
    completed: activeStatus({ active: false, status: "completed", remaining_seconds: 0 }),
    replaced: activeStatus({ session_id: "replacement-session" }),
    wrong_start: activeStatus({ start_at: "2030-01-02T08:01:00" }),
    malformed: { active: true, session_id: SESSION, start_at: START_AT, mode: "pomodoro" },
    missing: Object.assign(new Error("missing"), { code: "http_404" }),
    timeout: Object.assign(new Error("timeout"), { name: "AbortError" }),
  };
  for (const [name, statusOrError] of Object.entries(cases)) {
    await t.test(name, async child => {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-inactive-"));
      child.after(() => fs.rmSync(root, { recursive: true, force: true }));
      let generated = 0;
      let sent = 0;
      const scheduler = createFocusEncouragementScheduler({
        statePath: path.join(root, "state.json"),
        getFocusStatus: async () => {
          if (statusOrError instanceof Error) throw statusOrError;
          return statusOrError;
        },
        generateEncouragement: async () => { generated += 1; return {}; },
        sendText: async () => { sent += 1; },
        allowedUsers: new Set([USER]),
        now: () => new Date("2030-01-02T08:00:00"),
        ...timers(),
      });
      scheduler.start();
      register(scheduler);
      await scheduler.deliver(Object.keys(scheduler.snapshot().entries)[0]);
      assert.deepEqual({ generated, sent }, { generated: 0, sent: 0 });
      scheduler.stop();
    });
  }
});

test("model generated=false and timeout use one deterministic fallback without a second paid call", async t => {
  for (const mode of ["generated_false", "timeout"]) {
    await t.test(mode, async child => {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-fallback-"));
      child.after(() => fs.rmSync(root, { recursive: true, force: true }));
      let generated = 0;
      const sent = [];
      const scheduler = createFocusEncouragementScheduler({
        statePath: path.join(root, "state.json"),
        getFocusStatus: async () => activeStatus(),
        generateEncouragement: async () => {
          generated += 1;
          if (mode === "timeout") throw Object.assign(new Error("FAKE_SECRET_TIMEOUT"), { name: "AbortError" });
          return { eligible: true, generated: false, text: "", error_code: "model_failed" };
        },
        sendText: async (_user, _id, text) => sent.push(text),
        allowedUsers: new Set([USER]),
        now: () => new Date("2030-01-02T08:00:00"),
        warn() {},
        ...timers(),
      });
      scheduler.start();
      register(scheduler);
      await scheduler.deliver(Object.keys(scheduler.snapshot().entries)[0]);
      assert.equal(generated, 1);
      assert.equal(sent.length, 1);
      assert.ok(sent[0].includes("10 分钟"));
      assert.equal(sent[0].includes("FAKE_SECRET_TIMEOUT"), false);
      scheduler.stop();
    });
  }
});

test("generation 404/409/500, invalid payload, whitelist removal, and cancellation never send", async t => {
  const modes = ["http_404", "http_409", "http_500", "invalid", "allowlist", "cancel"];
  for (const mode of modes) {
    await t.test(mode, async child => {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-no-send-"));
      child.after(() => fs.rmSync(root, { recursive: true, force: true }));
      const allowedUsers = new Set([USER]);
      let generated = 0;
      let sent = 0;
      const scheduler = createFocusEncouragementScheduler({
        statePath: path.join(root, "state.json"),
        getFocusStatus: async () => activeStatus(),
        generateEncouragement: async () => {
          generated += 1;
          if (mode.startsWith("http_")) throw Object.assign(new Error("FAKE_UPSTREAM_BODY"), { code: mode });
          return mode === "invalid" ? { Authorization: "Bearer FAKE_TOKEN" } : { eligible: true, generated: true, text: "fake" };
        },
        sendText: async () => { sent += 1; },
        allowedUsers,
        now: () => new Date("2030-01-02T08:00:00"),
        ...timers(),
      });
      scheduler.start();
      register(scheduler);
      const key = Object.keys(scheduler.snapshot().entries)[0];
      if (mode === "allowlist") allowedUsers.delete(USER);
      if (mode === "cancel") scheduler.cancelUser(USER);
      await scheduler.deliver(key);
      assert.equal(sent, 0);
      assert.equal(generated, ["allowlist", "cancel"].includes(mode) ? 0 : 1);
      const raw = fs.readFileSync(path.join(root, "state.json"), "utf8");
      for (const forbidden of ["FAKE_UPSTREAM_BODY", "FAKE_TOKEN", "Authorization", USER]) {
        assert.equal(raw.includes(forbidden), false);
      }
      scheduler.stop();
    });
  }
});

test("shutdown during generation blocks later QQ send and state writes", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-shutdown-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let sends = 0;
  const scheduler = createFocusEncouragementScheduler({
    statePath: path.join(root, "state.json"),
    getFocusStatus: async () => activeStatus(),
    generateEncouragement: async () => {
      await gate;
      return { eligible: true, generated: true, text: "late" };
    },
    sendText: async () => { sends += 1; },
    allowedUsers: new Set([USER]),
    now: () => new Date("2030-01-02T08:00:00"),
    ...timers(),
  });
  scheduler.start();
  register(scheduler);
  const pending = scheduler.deliver(Object.keys(scheduler.snapshot().entries)[0]);
  await Promise.resolve();
  scheduler.stop();
  const before = fs.readFileSync(path.join(root, "state.json"), "utf8");
  release();
  await pending;
  assert.equal(sends, 0);
  assert.equal(fs.readFileSync(path.join(root, "state.json"), "utf8"), before);
});

test("QQ failure is not retried and a failed sent-state save remains fail-closed as sending", async t => {
  const sendFailureRoot = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-send-fail-"));
  t.after(() => fs.rmSync(sendFailureRoot, { recursive: true, force: true }));
  let generated = 0;
  let sendAttempts = 0;
  const failed = createFocusEncouragementScheduler({
    statePath: path.join(sendFailureRoot, "state.json"),
    getFocusStatus: async () => activeStatus(),
    generateEncouragement: async () => {
      generated += 1;
      return { eligible: true, generated: true, text: "fictional encouragement" };
    },
    sendText: async () => {
      sendAttempts += 1;
      throw Object.assign(new Error("Authorization: Bearer FAKE_TOKEN"), { code: "send_failed" });
    },
    allowedUsers: new Set([USER]),
    now: () => new Date("2030-01-02T08:00:00"),
    ...timers(),
  });
  failed.start();
  register(failed);
  const failedKey = Object.keys(failed.snapshot().entries)[0];
  await failed.deliver(failedKey);
  await failed.deliver(failedKey);
  assert.deepEqual({ generated, sendAttempts }, { generated: 1, sendAttempts: 1 });
  const failedRaw = fs.readFileSync(path.join(sendFailureRoot, "state.json"), "utf8");
  assert.equal(failedRaw.includes("FAKE_TOKEN"), false);
  assert.equal(JSON.parse(failedRaw).entries[failedKey].status, "failed");
  failed.stop();

  const saveFailureRoot = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-sent-save-fail-"));
  t.after(() => fs.rmSync(saveFailureRoot, { recursive: true, force: true }));
  const statePath = path.join(saveFailureRoot, "state.json");
  let renames = 0;
  const fakeFs = {
    ...fs,
    renameSync(source, destination) {
      renames += 1;
      if (renames === 3) throw new Error("FAKE_SECRET_FINAL_SAVE");
      return fs.renameSync(source, destination);
    },
  };
  let modelCalls = 0;
  let sends = 0;
  const stateIo = { fsImpl: fakeFs, randomId: () => `fake-${renames}` };
  const scheduler = createFocusEncouragementScheduler({
    statePath,
    getFocusStatus: async () => activeStatus(),
    generateEncouragement: async () => {
      modelCalls += 1;
      return { eligible: true, generated: true, text: "x".repeat(300) };
    },
    sendText: async (_user, _id, text) => {
      sends += 1;
      assert.equal(text.length, 180);
    },
    allowedUsers: new Set([USER]),
    stateIo,
    now: () => new Date("2030-01-02T08:00:00"),
    ...timers(),
  });
  scheduler.start();
  register(scheduler);
  const key = Object.keys(scheduler.snapshot().entries)[0];
  await scheduler.deliver(key);
  assert.deepEqual({ modelCalls, sends }, { modelCalls: 1, sends: 1 });
  assert.equal(scheduler.snapshot().stateHealthy, false);
  assert.equal(JSON.parse(fs.readFileSync(statePath, "utf8")).entries[key].status, "sending");
  assert.deepEqual(fs.readdirSync(saveFailureRoot), ["state.json"]);
  scheduler.stop();

  const restarted = createFocusEncouragementScheduler({
    statePath,
    getFocusStatus: async () => { throw new Error("must not run"); },
    generateEncouragement: async () => { modelCalls += 1; return {}; },
    sendText: async () => { sends += 1; },
    allowedUsers: new Set([USER]),
    ...timers(),
  });
  restarted.start();
  await restarted.deliver(key);
  assert.deepEqual({ modelCalls, sends }, { modelCalls: 1, sends: 1 });
  restarted.stop();
});

test("semantic corruption and atomic write failure preserve old bytes and perform zero side effects", async t => {
  const corruptCases = [
    { schema_version: 1, entries: { FULL_FAKE_OPENID: {} } },
    { schema_version: 1, entries: {}, Authorization: "Bearer FAKE_TOKEN" },
    { schema_version: 1, entries: { ["a".repeat(24)]: { user_key: "b".repeat(24), session_id: SESSION, start_at: START_AT, due_at: "2030-01-02T08:10:00.000Z", status: "scheduled", message: "FAKE_MESSAGE" } } },
  ];
  for (const [index, corrupt] of corruptCases.entries()) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-corrupt-"));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    const statePath = path.join(root, `state-${index}.json`);
    const oldBytes = `${JSON.stringify(corrupt)}\n`;
    fs.writeFileSync(statePath, oldBytes, "utf8");
    let sideEffects = 0;
    const scheduler = createFocusEncouragementScheduler({
      statePath,
      getFocusStatus: async () => { sideEffects += 1; return activeStatus(); },
      generateEncouragement: async () => { sideEffects += 1; return {}; },
      sendText: async () => { sideEffects += 1; },
      allowedUsers: new Set([USER]),
      ...timers(),
    });
    scheduler.start();
    assert.equal(scheduler.snapshot().stateHealthy, false);
    assert.throws(() => register(scheduler), /unavailable/);
    assert.equal(sideEffects, 0);
    assert.equal(fs.readFileSync(statePath, "utf8"), oldBytes);
  }

  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-focus-write-fail-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statePath = path.join(root, "state.json");
  const oldState = { schema_version: 1, entries: {} };
  const oldBytes = `${JSON.stringify(oldState)}\n`;
  fs.writeFileSync(statePath, oldBytes, "utf8");
  const fakeFs = { ...fs, renameSync() { throw new Error("FAKE_SECRET_RENAME"); } };
  const fakeTimers = timers();
  let sideEffects = 0;
  const scheduler = createFocusEncouragementScheduler({
    statePath,
    getFocusStatus: async () => { sideEffects += 1; return activeStatus(); },
    generateEncouragement: async () => { sideEffects += 1; return {}; },
    sendText: async () => { sideEffects += 1; },
    allowedUsers: new Set([USER]),
    stateIo: { fsImpl: fakeFs, randomId: () => "fictional-temp" },
    ...fakeTimers,
  });
  scheduler.start();
  assert.throws(() => register(scheduler), /state_write_failed/);
  assert.equal(fakeTimers.timeouts.size, 0);
  assert.equal(sideEffects, 0);
  assert.equal(fs.readFileSync(statePath, "utf8"), oldBytes);
  assert.deepEqual(fs.readdirSync(root), ["state.json"]);
});

test("state validator rejects secrets, full identities, messages, and unbounded entries", () => {
  assert.equal(validateFocusEncouragementState({ schema_version: 1, entries: {} }), true);
  assert.equal(validateFocusEncouragementState({ schema_version: 1, entries: {}, token: "FAKE" }), false);
  assert.equal(validateFocusEncouragementState({
    schema_version: 1,
    entries: Object.fromEntries(Array.from({ length: 257 }, (_, index) => [
      index.toString(16).padStart(24, "0"),
      {
        user_key: "a".repeat(24),
        session_id: SESSION,
        start_at: START_AT,
        due_at: "2030-01-02T08:10:00.000Z",
        status: "scheduled",
      },
    ])),
  }), false);
});
