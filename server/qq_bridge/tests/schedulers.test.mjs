import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { fetchWithTimeout, readSafeJson } from "../src/bridge_core.mjs";
import { createDailyBriefingScheduler } from "../src/daily_briefing_scheduler.mjs";
import { createLifeSupportScheduler } from "../src/life_support_scheduler.mjs";

function timers() {
  let next = 1;
  const timeouts = new Map();
  const intervals = new Map();
  return {
    timeouts, intervals,
    setTimeoutFn(fn, delay) { const id = next++; timeouts.set(id, { fn, delay }); return id; },
    clearTimeoutFn(id) { timeouts.delete(id); },
    setIntervalFn(fn, delay) { const id = next++; intervals.set(id, { fn, delay }); return id; },
    clearIntervalFn(id) { intervals.delete(id); },
  };
}

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
        timer = setTimeout(() => reject(new Error("scheduler_stop_timeout")), windowMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

test("daily prebuild uses explicit generation once and delivery is cache-only across restart", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-daily-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statePath = path.join(root, "state.json");
  const clock = () => new Date("2026-07-22T06:00:00+08:00");
  let generated = 0;
  let cacheReads = 0;
  let sends = 0;
  const make = () => createDailyBriefingScheduler({
    scheduleUrl: "http://127.0.0.1:8000/api/v1/qq-control/schedules/daily-briefing",
    statePath,
    fetchSchedule: async () => ({ enabled: true, prebuild_time: "07:00", send_time: "08:00" }),
    generateBriefing: async () => { generated += 1; },
    getCachedBriefing: async () => { cacheReads += 1; return { cached: true, markdown: "# fake briefing" }; },
    sendMarkdown: async () => { sends += 1; },
    allowedUsers: new Set(["fictional-openid"]), now: clock, ...timers(),
  });
  const first = make();
  await first.start();
  await first.prebuild();
  await first.prebuild();
  await first.send();
  await first.send();
  first.stop();
  const second = make();
  await second.start();
  await second.prebuild();
  await second.send();
  assert.equal(generated, 1);
  assert.equal(cacheReads, 3);
  assert.equal(sends, 1);
  const raw = fs.readFileSync(statePath, "utf8");
  assert.equal(raw.includes("fictional-openid"), false);
  assert.equal(raw.includes("# fake briefing"), false);
  second.stop();
});

test("daily missing cache never triggers generation during send and isolates users", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-daily-failure-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  let generated = 0;
  let sentA = 0;
  let sentB = 0;
  let failB = true;
  const scheduler = createDailyBriefingScheduler({
    scheduleUrl: "local", statePath: path.join(root, "state.json"),
    fetchSchedule: async () => ({ enabled: true, prebuild_time: "07:00", send_time: "08:00" }),
    generateBriefing: async () => { generated += 1; },
    getCachedBriefing: async () => ({ cached: true, markdown: "fake" }),
    sendMarkdown: async user => {
      if (user === "user-a") sentA += 1;
      else { sentB += 1; if (failB) { failB = false; throw Object.assign(new Error("no"), { code: "send_failed" }); } }
    },
    allowedUsers: new Set(["user-a", "user-b"]), now: () => new Date("2026-07-22T06:00:00+08:00"), ...timers(),
  });
  await scheduler.start();
  await scheduler.send();
  await scheduler.send();
  assert.equal(generated, 0);
  assert.equal(sentA, 1);
  assert.equal(sentB, 2);
  scheduler.stop();

  const missing = createDailyBriefingScheduler({
    scheduleUrl: "local", statePath: path.join(root, "missing.json"), fetchSchedule: async () => ({ enabled: true, prebuild_time: "07:00", send_time: "08:00" }),
    generateBriefing: async () => { generated += 1; }, getCachedBriefing: async () => { throw Object.assign(new Error("missing"), { code: "cache_missing" }); },
    sendMarkdown: async () => { throw new Error("unexpected"); }, allowedUsers: new Set(["user-a"]), now: () => new Date("2026-07-22T06:00:00+08:00"), ...timers(),
  });
  await missing.start();
  await missing.send();
  assert.equal(generated, 0);
  missing.stop();
});

test("life support deduplicates slots across restart and uses deterministic fallback", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-life-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statePath = path.join(root, "state.json");
  const target = new Date("2026-07-22T10:00:00+08:00");
  let sends = 0;
  let deliveredText = "";
  const make = () => createLifeSupportScheduler({
    scheduleUrl: "local", statePath,
    fetchSchedule: async () => ({ enabled: true, start_time: "08:00", end_time: "22:00", interval_hours: 2, interval_minutes: 0 }),
    generateReminder: async () => { throw Object.assign(new Error("FAKE_SECRET_TOKEN"), { code: "model_failed" }); },
    sendText: async (_user, _id, text) => { sends += 1; deliveredText = text; },
    allowedUsers: new Set(["fictional-openid"]), now: () => new Date("2026-07-22T09:00:00+08:00"), ...timers(),
  });
  const first = make();
  await first.start();
  await first.deliver(target);
  first.stop();
  const second = make();
  await second.start();
  await second.deliver(target);
  assert.equal(sends, 1);
  assert.ok(deliveredText.length > 0);
  const raw = fs.readFileSync(statePath, "utf8");
  assert.equal(raw.includes("fictional-openid"), false);
  assert.equal(raw.includes("FAKE_SECRET_TOKEN"), false);
  second.stop();
});

test("schedule disable/change replaces timers and stop prevents later calls", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-timers-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const fakeTimers = timers();
  let schedule = { enabled: true, start_time: "08:00", end_time: "22:00", interval_hours: 2, interval_minutes: 0 };
  let sends = 0;
  const scheduler = createLifeSupportScheduler({
    scheduleUrl: "local", statePath: path.join(root, "state.json"), fetchSchedule: async () => schedule,
    generateReminder: async () => "fake", sendText: async () => { sends += 1; }, allowedUsers: new Set(["user"]),
    now: () => new Date("2026-07-22T09:00:00+08:00"), ...fakeTimers,
  });
  await scheduler.start();
  assert.equal(fakeTimers.timeouts.size, 1);
  schedule = { ...schedule, interval_hours: 1 };
  await scheduler.refreshSchedule();
  assert.equal(fakeTimers.timeouts.size, 1);
  schedule = { ...schedule, enabled: false };
  await scheduler.refreshSchedule();
  assert.equal(fakeTimers.timeouts.size, 0);
  scheduler.stop();
  await scheduler.deliver(new Date("2026-07-22T10:00:00+08:00"));
  assert.equal(sends, 0);
  assert.equal(fakeTimers.intervals.size, 0);
});

test("daily semantic state corruption fails closed before schedule or delivery side effects", async t => {
  const validUserKey = "a".repeat(24);
  const validEntry = { status: "success" };
  const cases = {
    full_openid_key: { schema_version: 1, prebuild: {}, deliveries: { "2026-07-22": { FULL_FAKE_OPENID_SHAPE: validEntry } } },
    authorization_field: { schema_version: 1, prebuild: {}, deliveries: {}, Authorization: "Bearer FAKE_TOKEN" },
    message_field: { schema_version: 1, prebuild: {}, deliveries: { "2026-07-22": { [validUserKey]: { status: "success", message: "FAKE_FULL_MESSAGE" } } } },
    invalid_date: { schema_version: 1, prebuild: {}, deliveries: { "2026-02-31": { [validUserKey]: validEntry } } },
    invalid_error_code: { schema_version: 1, prebuild: {}, deliveries: { "2026-07-22": { [validUserKey]: { status: "failed", error_code: "Authorization: Bearer FAKE_TOKEN" } } } },
    too_many_days: { schema_version: 1, prebuild: {}, deliveries: Object.fromEntries(Array.from({ length: 15 }, (_, index) => [`2026-07-${String(index + 1).padStart(2, "0")}`, {}])) },
    prebuild_secret_field: { schema_version: 1, prebuild: { date: "2026-07-22", status: "success", token: "FAKE_SECRET" }, deliveries: {} },
  };
  for (const [name, state] of Object.entries(cases)) {
    await t.test(name, async child => {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-daily-semantic-"));
      child.after(() => fs.rmSync(root, { recursive: true, force: true }));
      const statePath = path.join(root, "state.json");
      const oldBytes = `${JSON.stringify(state)}\n`;
      fs.writeFileSync(statePath, oldBytes, "utf8");
      const fakeTimers = timers();
      let scheduleReads = 0;
      let generated = 0;
      let cacheReads = 0;
      let sends = 0;
      const warnings = [];
      const scheduler = createDailyBriefingScheduler({
        scheduleUrl: "local", statePath,
        fetchSchedule: async () => { scheduleReads += 1; return { enabled: true, prebuild_time: "07:00", send_time: "08:00" }; },
        generateBriefing: async () => { generated += 1; },
        getCachedBriefing: async () => { cacheReads += 1; return { cached: true, markdown: "fake" }; },
        sendMarkdown: async () => { sends += 1; },
        allowedUsers: new Set(["fictional-openid"]),
        warn: value => warnings.push(value),
        now: () => new Date("2026-07-22T06:00:00+08:00"),
        ...fakeTimers,
      });
      await scheduler.start();
      await scheduler.prebuild();
      await scheduler.send();
      assert.equal(scheduler.snapshot().stateHealthy, false);
      assert.deepEqual({ scheduleReads, generated, cacheReads, sends }, { scheduleReads: 0, generated: 0, cacheReads: 0, sends: 0 });
      assert.equal(fakeTimers.timeouts.size, 0);
      assert.equal(fakeTimers.intervals.size, 0);
      assert.equal(fs.readFileSync(statePath, "utf8"), oldBytes);
      assert.deepEqual(fs.readdirSync(root), ["state.json"]);
      assert.deepEqual(warnings, ["daily_state_corrupt"]);
    });
  }
});

test("life-support semantic state corruption fails closed before schedule or delivery side effects", async t => {
  const validUserKey = "b".repeat(24);
  const validEntry = { status: "success" };
  const cases = {
    full_openid_key: { schema_version: 1, slots: { "2026-07-22T10:00": { FULL_FAKE_OPENID_SHAPE: validEntry } } },
    authorization_field: { schema_version: 1, slots: {}, Authorization: "Bearer FAKE_TOKEN" },
    message_field: { schema_version: 1, slots: { "2026-07-22T10:00": { [validUserKey]: { status: "success", message: "FAKE_FULL_MESSAGE" } } } },
    invalid_slot_or_status: { schema_version: 1, slots: { "2026-07-22T25:00": { [validUserKey]: { status: "sent" } } } },
    invalid_error_code: { schema_version: 1, slots: { "2026-07-22T10:00": { [validUserKey]: { status: "failed", error_code: "FAKE-AUTHORIZATION" } } } },
    too_many_slots: {
      schema_version: 1,
      slots: Object.fromEntries(Array.from({ length: 97 }, (_, index) => [
        new Date(Date.UTC(2026, 6, 22, 0, index)).toISOString().slice(0, 16),
        {},
      ])),
    },
  };
  for (const [name, state] of Object.entries(cases)) {
    await t.test(name, async child => {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-life-semantic-"));
      child.after(() => fs.rmSync(root, { recursive: true, force: true }));
      const statePath = path.join(root, "state.json");
      const oldBytes = `${JSON.stringify(state)}\n`;
      fs.writeFileSync(statePath, oldBytes, "utf8");
      const fakeTimers = timers();
      let scheduleReads = 0;
      let generated = 0;
      let sends = 0;
      const warnings = [];
      const scheduler = createLifeSupportScheduler({
        scheduleUrl: "local", statePath,
        fetchSchedule: async () => { scheduleReads += 1; return { enabled: true, start_time: "08:00", end_time: "22:00", interval_hours: 2, interval_minutes: 0 }; },
        generateReminder: async () => { generated += 1; return "fake"; },
        sendText: async () => { sends += 1; },
        allowedUsers: new Set(["fictional-openid"]),
        warn: value => warnings.push(value),
        now: () => new Date("2026-07-22T09:00:00+08:00"),
        ...fakeTimers,
      });
      await scheduler.start();
      await scheduler.deliver(new Date("2026-07-22T10:00:00+08:00"));
      assert.equal(scheduler.snapshot().stateHealthy, false);
      assert.deepEqual({ scheduleReads, generated, sends }, { scheduleReads: 0, generated: 0, sends: 0 });
      assert.equal(fakeTimers.timeouts.size, 0);
      assert.equal(fakeTimers.intervals.size, 0);
      assert.equal(fs.readFileSync(statePath, "utf8"), oldBytes);
      assert.deepEqual(fs.readdirSync(root), ["state.json"]);
      assert.deepEqual(warnings, ["life_support_state_corrupt"]);
    });
  }
});

test("daily schedule changes replace both timers and old state schema fails closed", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-daily-timers-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const statePath = path.join(root, "state.json");
  fs.writeFileSync(statePath, JSON.stringify({ sent_users: { "FULL_FAKE_OPENID": "2026-07-22" } }), "utf8");
  const fakeTimers = timers();
  let schedule = { enabled: true, prebuild_time: "07:00", send_time: "08:00" };
  let sends = 0;
  const scheduler = createDailyBriefingScheduler({
    scheduleUrl: "local", statePath, fetchSchedule: async () => schedule,
    generateBriefing: async () => {}, getCachedBriefing: async () => ({ cached: true, markdown: "fake" }),
    sendMarkdown: async () => { sends += 1; }, allowedUsers: new Set(["FULL_FAKE_OPENID"]),
    now: () => new Date("2026-07-22T06:00:00+08:00"), ...fakeTimers,
  });
  await scheduler.start();
  assert.equal(scheduler.snapshot().stateHealthy, false);
  assert.equal(fakeTimers.timeouts.size, 0);
  await scheduler.send();
  assert.equal(sends, 0);
  assert.ok(fs.readFileSync(statePath, "utf8").includes("FULL_FAKE_OPENID"));
  scheduler.stop();

  const cleanTimers = timers();
  const clean = createDailyBriefingScheduler({
    scheduleUrl: "local", statePath: path.join(root, "clean.json"), fetchSchedule: async () => schedule,
    generateBriefing: async () => {}, getCachedBriefing: async () => ({ cached: true, markdown: "fake" }), sendMarkdown: async () => {},
    allowedUsers: new Set(["user"]), now: () => new Date("2026-07-22T06:00:00+08:00"), ...cleanTimers,
  });
  await clean.start();
  assert.equal(cleanTimers.timeouts.size, 2);
  schedule = { enabled: true, prebuild_time: "06:30", send_time: "07:30" };
  await clean.refreshSchedule();
  assert.equal(cleanTimers.timeouts.size, 2);
  schedule = { ...schedule, enabled: false };
  await clean.refreshSchedule();
  assert.equal(cleanTimers.timeouts.size, 0);
  clean.stop();
});

test("daily startup refresh settles promptly on stop and late schedule cannot create timers", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-daily-start-cancel-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const pending = deferred();
  const fakeTimers = timers();
  let providerSignal;
  const scheduler = createDailyBriefingScheduler({
    scheduleUrl: "local",
    statePath: path.join(root, "state.json"),
    fetchSchedule: (_url, { signal }) => { providerSignal = signal; return pending.promise; },
    generateBriefing: async () => {},
    getCachedBriefing: async () => ({ cached: true, markdown: "fake" }),
    sendMarkdown: async () => {},
    allowedUsers: new Set(["fictional-user"]),
    ...fakeTimers,
  });
  const starting = scheduler.start();
  while (!providerSignal) await Promise.resolve();
  scheduler.stop();
  scheduler.stop();
  assert.equal(providerSignal.aborted, true);
  await settlesQuickly(starting);
  pending.resolve({ enabled: true, prebuild_time: "07:00", send_time: "08:00" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(fakeTimers.timeouts.size, 0);
  assert.equal(fakeTimers.intervals.size, 0);
  assert.equal(scheduler.snapshot().stopped, true);
});

test("shared lifecycle abort settles pending life-support startup and ignores late rejection", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-life-start-cancel-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const pending = deferred();
  const fakeTimers = timers();
  const lifecycle = new AbortController();
  let providerSignal;
  const scheduler = createLifeSupportScheduler({
    scheduleUrl: "local",
    statePath: path.join(root, "state.json"),
    fetchSchedule: (_url, { signal }) => { providerSignal = signal; return pending.promise; },
    generateReminder: async () => "fake",
    sendText: async () => {},
    allowedUsers: new Set(["fictional-user"]),
    ...fakeTimers,
  });
  const starting = scheduler.start({ signal: lifecycle.signal });
  while (!providerSignal) await Promise.resolve();
  lifecycle.abort();
  assert.equal(providerSignal.aborted, true);
  await settlesQuickly(starting);
  pending.reject(new Error("LATE_PRIVATE_SCHEDULE_BODY"));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(fakeTimers.timeouts.size, 0);
  assert.equal(fakeTimers.intervals.size, 0);
  assert.equal(scheduler.snapshot().stopped, true);
});

test("daily and life schedule JSON bodies are truly aborted and cancelled on stop", async t => {
  for (const kind of ["daily", "life"]) {
    await t.test(kind, async child => {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), `kei-qq-${kind}-body-cancel-`));
      child.after(() => fs.rmSync(root, { recursive: true, force: true }));
      const fakeTimers = timers();
      let requestSignal;
      let abortEvents = 0;
      let reads = 0;
      let cancels = 0;
      let finishRead;
      const pendingRead = new Promise((resolve, reject) => { finishRead = { resolve, reject }; });
      const fetchSchedule = async (_url, { signal }) => {
        const response = await fetchWithTimeout("http://127.0.0.1:8000/fake-schedule", { signal }, 60_000, async (_target, options) => {
          requestSignal = options.signal;
          requestSignal.addEventListener("abort", () => { abortEvents += 1; });
          return {
            ok: true,
            status: 200,
            body: { getReader: () => ({
              read() {
                reads += 1;
                if (reads === 1) return Promise.resolve({ done: false, value: new TextEncoder().encode('{"enabled":') });
                return pendingRead;
              },
              cancel() { cancels += 1; return Promise.resolve(); },
              releaseLock() {},
            }) },
          };
        });
        return readSafeJson(response, "schedule");
      };
      const common = {
        scheduleUrl: "local", statePath: path.join(root, "state.json"), fetchSchedule,
        allowedUsers: new Set(["fictional-user"]), ...fakeTimers,
      };
      const scheduler = kind === "daily"
        ? createDailyBriefingScheduler({
          ...common, generateBriefing: async () => {},
          getCachedBriefing: async () => ({ cached: true, markdown: "fake" }), sendMarkdown: async () => {},
        })
        : createLifeSupportScheduler({ ...common, generateReminder: async () => "fake", sendText: async () => {} });
      const starting = scheduler.start();
      while (!requestSignal || reads < 2) await Promise.resolve();
      scheduler.stop();
      scheduler.stop();
      await settlesQuickly(starting);
      assert.equal(requestSignal.aborted, true);
      assert.equal(abortEvents, 1);
      assert.equal(cancels, 1);
      assert.equal(fakeTimers.timeouts.size, 0);
      assert.equal(fakeTimers.intervals.size, 0);
      finishRead.reject(new Error("late schedule body"));
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(scheduler.snapshot().stopped, true);
    });
  }
});
