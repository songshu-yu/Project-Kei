import {
  atomicWriteState,
  hasExactStateKeys,
  isPlainStateObject,
  isSafeStateCode,
  isStateDate,
  loadStateFile,
  safeErrorCode,
  settleWithSignal,
  userDedupeKey,
  validateDeliveryBuckets,
} from "./state_store.mjs";

const DEFAULT_SCHEDULE = Object.freeze({ enabled: false, prebuild_time: "07:00", send_time: "08:00" });
const DEFAULT_STATE = Object.freeze({ schema_version: 1, prebuild: {}, deliveries: {} });
const MAX_DELIVERY_DAYS = 14;

export function validateDailyState(value) {
  if (!hasExactStateKeys(value, ["schema_version", "prebuild", "deliveries"])) return false;
  if (value.schema_version !== 1 || !isPlainStateObject(value.prebuild)) return false;
  const prebuildKeys = Object.keys(value.prebuild);
  if (prebuildKeys.length) {
    if (!hasExactStateKeys(value.prebuild, ["date", "status"], ["error_code"])) return false;
    if (!isStateDate(value.prebuild.date) || !["running", "success", "failed"].includes(value.prebuild.status)) return false;
    if (value.prebuild.status === "failed") {
      if (!Object.hasOwn(value.prebuild, "error_code") || !isSafeStateCode(value.prebuild.error_code)) return false;
    } else if (Object.hasOwn(value.prebuild, "error_code")) {
      return false;
    }
  }
  return validateDeliveryBuckets(value.deliveries, {
    maxBuckets: MAX_DELIVERY_DAYS,
    validateBucketKey: isStateDate,
  });
}

export function normalizeDailySchedule(value) {
  const source = value && typeof value === "object" ? value : {};
  const validClock = clock => typeof clock === "string" && /^([01]\d|2[0-3]):[0-5]\d$/.test(clock);
  const prebuild = validClock(source.prebuild_time) ? source.prebuild_time : DEFAULT_SCHEDULE.prebuild_time;
  const send = validClock(source.send_time) ? source.send_time : DEFAULT_SCHEDULE.send_time;
  return { enabled: Boolean(source.enabled) && prebuild < send, prebuild_time: prebuild, send_time: send };
}

function localDay(now) {
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function nextOccurrence(clock, now) {
  const [hours, minutes] = clock.split(":").map(Number);
  const target = new Date(now);
  target.setHours(hours, minutes, 0, 0);
  if (target.getTime() <= now.getTime()) target.setDate(target.getDate() + 1);
  return target;
}

function trimDeliveries(deliveries) {
  const keys = Object.keys(deliveries).sort();
  while (keys.length > MAX_DELIVERY_DAYS) delete deliveries[keys.shift()];
}

export function createDailyBriefingScheduler({
  scheduleUrl,
  statePath,
  fetchSchedule,
  generateBriefing,
  getCachedBriefing,
  sendMarkdown,
  allowedUsers,
  log = () => {},
  warn = () => {},
  now = () => new Date(),
  setTimeoutFn = setTimeout,
  clearTimeoutFn = clearTimeout,
  setIntervalFn = setInterval,
  clearIntervalFn = clearInterval,
  stateIo = {},
}) {
  const lifecycleController = new AbortController();
  let schedule = { ...DEFAULT_SCHEDULE };
  const loaded = loadStateFile(statePath, DEFAULT_STATE, stateIo);
  let state = loaded.state;
  let stateHealthy = Boolean(loaded.healthy && validateDailyState(state));
  let prebuildTimer = null;
  let sendTimer = null;
  let refreshTimer = null;
  let stopped = false;
  let started = false;
  let epoch = 0;
  let fingerprint = "";
  let externalSignal = null;
  const onExternalAbort = () => stop();

  const active = token => !stopped && token === epoch;
  const persist = () => {
    if (!stateHealthy || stopped) return false;
    atomicWriteState(statePath, state, stateIo);
    return true;
  };
  const clearTimers = () => {
    if (prebuildTimer) clearTimeoutFn(prebuildTimer);
    if (sendTimer) clearTimeoutFn(sendTimer);
    prebuildTimer = null;
    sendTimer = null;
  };

  function planPrebuild(token = epoch) {
    if (!active(token) || !schedule.enabled || !stateHealthy) return;
    const current = now();
    const target = nextOccurrence(schedule.prebuild_time, current);
    prebuildTimer = setTimeoutFn(async () => {
      prebuildTimer = null;
      await prebuild(token);
      if (active(token)) planPrebuild(token);
    }, Math.max(0, target.getTime() - current.getTime()));
  }

  function planSend(token = epoch) {
    if (!active(token) || !schedule.enabled || !stateHealthy) return;
    const current = now();
    const target = nextOccurrence(schedule.send_time, current);
    sendTimer = setTimeoutFn(async () => {
      sendTimer = null;
      await send(token);
      if (active(token)) planSend(token);
    }, Math.max(0, target.getTime() - current.getTime()));
  }

  async function refreshSchedule(token = epoch, signal = lifecycleController.signal) {
    if (!active(token) || !stateHealthy) return;
    try {
      const next = normalizeDailySchedule(await settleWithSignal(
        () => fetchSchedule(scheduleUrl, { signal }),
        signal,
      ));
      if (!active(token)) return;
      const nextFingerprint = JSON.stringify(next);
      schedule = next;
      if (nextFingerprint !== fingerprint) {
        fingerprint = nextFingerprint;
        epoch += 1;
        const nextToken = epoch;
        clearTimers();
        if (schedule.enabled && stateHealthy) {
          planPrebuild(nextToken);
          planSend(nextToken);
        }
      }
    } catch (error) {
      if (!active(token) || signal?.aborted) return;
      warn(`daily_schedule_${safeErrorCode(error, "refresh_failed")}`);
    }
  }

  async function prebuild(token = epoch) {
    if (!active(token) || !schedule.enabled || !stateHealthy) return;
    const today = localDay(now());
    if (state.prebuild?.date === today) return;
    state = { ...state, prebuild: { date: today, status: "running" } };
    try {
      persist();
    } catch (error) {
      stateHealthy = false;
      warn("daily_state_write_failed");
      return;
    }
    try {
      await settleWithSignal(
        () => generateBriefing({ signal: lifecycleController.signal }),
        lifecycleController.signal,
      );
      if (!active(token)) return;
      state = { ...state, prebuild: { date: today, status: "success" } };
    } catch (error) {
      if (!active(token)) return;
      state = { ...state, prebuild: { date: today, status: "failed", error_code: safeErrorCode(error) } };
    }
    try { persist(); } catch { stateHealthy = false; warn("daily_state_write_failed"); }
  }

  async function send(token = epoch) {
    if (!active(token) || !schedule.enabled || !stateHealthy || !allowedUsers.size) return;
    const today = localDay(now());
    let briefing;
    try {
      briefing = await settleWithSignal(
        () => getCachedBriefing({ signal: lifecycleController.signal }),
        lifecycleController.signal,
      );
    } catch (error) {
      warn(`daily_cache_${safeErrorCode(error, "unavailable")}`);
      return;
    }
    if (!active(token) || !briefing?.cached || !briefing?.markdown) return;
    const deliveries = state.deliveries && typeof state.deliveries === "object" ? state.deliveries : {};
    const dayState = deliveries[today] && typeof deliveries[today] === "object" ? deliveries[today] : {};
    for (const userOpenId of allowedUsers) {
      if (!active(token)) return;
      const userKey = userDedupeKey(userOpenId);
      if (["sending", "success"].includes(dayState[userKey]?.status)) continue;
      dayState[userKey] = { status: "sending" };
      deliveries[today] = dayState;
      trimDeliveries(deliveries);
      state = { schema_version: 1, prebuild: state.prebuild || {}, deliveries };
      try { persist(); } catch { stateHealthy = false; warn("daily_state_write_failed"); return; }
      try {
        await settleWithSignal(
          () => sendMarkdown(
            userOpenId,
            undefined,
            briefing.markdown,
            { signal: lifecycleController.signal },
          ),
          lifecycleController.signal,
        );
        if (!active(token)) return;
        dayState[userKey] = { status: "success" };
      } catch (error) {
        if (!active(token)) return;
        dayState[userKey] = { status: "failed", error_code: safeErrorCode(error, "send_failed") };
      }
      try { persist(); } catch { stateHealthy = false; warn("daily_state_write_failed"); return; }
    }
    log("daily_delivery_cycle_complete");
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    epoch += 1;
    lifecycleController.abort();
    externalSignal?.removeEventListener?.("abort", onExternalAbort);
    clearTimers();
    if (refreshTimer) clearIntervalFn(refreshTimer);
    refreshTimer = null;
  }

  return {
    async start({ signal } = {}) {
      if (started || stopped) return;
      started = true;
      externalSignal = signal || null;
      if (externalSignal?.aborted) { stop(); return; }
      externalSignal?.addEventListener?.("abort", onExternalAbort, { once: true });
      if (!stateHealthy) {
        warn("daily_state_corrupt");
        return;
      }
      await refreshSchedule(epoch, lifecycleController.signal);
      if (!stopped) refreshTimer = setIntervalFn(() => { void refreshSchedule(epoch); }, 30_000);
    },
    stop,
    prebuild,
    send,
    refreshSchedule,
    snapshot: () => ({ schedule: { ...schedule }, stateHealthy, stopped }),
  };
}
