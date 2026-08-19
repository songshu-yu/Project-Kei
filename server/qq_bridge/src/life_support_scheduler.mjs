import {
  atomicWriteState,
  hasExactStateKeys,
  isStateSlot,
  loadStateFile,
  safeErrorCode,
  settleWithSignal,
  userDedupeKey,
  validateDeliveryBuckets,
} from "./state_store.mjs";

const DEFAULT_SCHEDULE = Object.freeze({ enabled: false, start_time: "08:00", end_time: "22:00", interval_hours: 2, interval_minutes: 0 });
const DEFAULT_STATE = Object.freeze({ schema_version: 1, slots: {} });
const MAX_SLOTS = 96;
const REMINDERS = [
  ["move", "老师，起身活动一下。坐太久会让身体先提出抗议，我不接受这种低效损耗。"],
  ["hydrate", "喝几口水。不是建议，是 Kei 的生命维持提醒。"],
  ["eyes", "视线离开屏幕，看远处二十秒，再转转肩颈。老师，执行。"],
  ["stretch", "该站起来走两分钟了。思路卡住时，身体也需要重新加载。"],
  ["rest", "老师，补充一点水分，然后做几次伸展。别等不舒服了才想起来。"],
];

export function validateLifeSupportState(value) {
  return hasExactStateKeys(value, ["schema_version", "slots"])
    && value.schema_version === 1
    && validateDeliveryBuckets(value.slots, {
      maxBuckets: MAX_SLOTS,
      validateBucketKey: isStateSlot,
    });
}

export function normalizeLifeSupportSchedule(value) {
  const source = value && typeof value === "object" ? value : {};
  const validClock = clock => typeof clock === "string" && /^([01]\d|2[0-3]):[0-5]\d$/.test(clock);
  const start = validClock(source.start_time) ? source.start_time : DEFAULT_SCHEDULE.start_time;
  const end = validClock(source.end_time) ? source.end_time : DEFAULT_SCHEDULE.end_time;
  const hours = Number.isInteger(source.interval_hours) ? source.interval_hours : DEFAULT_SCHEDULE.interval_hours;
  const minutes = Number.isInteger(source.interval_minutes) ? source.interval_minutes : DEFAULT_SCHEDULE.interval_minutes;
  const enabled = Boolean(source.enabled) && start < end && hours >= 0 && minutes >= 0 && minutes < 60 && hours * 60 + minutes > 0;
  return { enabled, start_time: start, end_time: end, interval_hours: hours, interval_minutes: minutes };
}

function atTime(day, clock) {
  const [hours, minutes] = clock.split(":").map(Number);
  const value = new Date(day);
  value.setHours(hours, minutes, 0, 0);
  return value;
}

export function slotKey(value) {
  const pad = number => String(number).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

export function nextLifeSupportSlot(schedule, current) {
  const intervalMs = (schedule.interval_hours * 60 + schedule.interval_minutes) * 60_000;
  for (let dayOffset = 0; dayOffset <= 1; dayOffset += 1) {
    const day = new Date(current);
    day.setDate(current.getDate() + dayOffset);
    const start = atTime(day, schedule.start_time);
    const end = atTime(day, schedule.end_time);
    let candidate = new Date(start);
    while (candidate <= current) candidate = new Date(candidate.getTime() + intervalMs);
    if (candidate <= end) return candidate;
  }
  return atTime(new Date(current.getFullYear(), current.getMonth(), current.getDate() + 1), schedule.start_time);
}

function reminderFor(slot) {
  let hash = 0;
  for (const char of slotKey(slot)) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const [kind, fallback] = REMINDERS[hash % REMINDERS.length];
  return { kind, fallback };
}

function trimSlots(slots) {
  const keys = Object.keys(slots).sort();
  while (keys.length > MAX_SLOTS) delete slots[keys.shift()];
}

export function createLifeSupportScheduler({
  scheduleUrl,
  statePath,
  fetchSchedule,
  generateReminder,
  sendText,
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
  let stateHealthy = Boolean(loaded.healthy && validateLifeSupportState(state));
  let reminderTimer = null;
  let refreshTimer = null;
  let stopped = false;
  let started = false;
  let epoch = 0;
  let fingerprint = "";
  let externalSignal = null;
  const onExternalAbort = () => stop();
  const active = token => !stopped && token === epoch;
  const clearReminder = () => {
    if (reminderTimer) clearTimeoutFn(reminderTimer);
    reminderTimer = null;
  };
  const persist = () => {
    if (!stateHealthy || stopped) return false;
    atomicWriteState(statePath, state, stateIo);
    return true;
  };

  function planReminder(token = epoch) {
    if (!active(token) || !schedule.enabled || !stateHealthy || !allowedUsers.size) return;
    const current = now();
    const target = nextLifeSupportSlot(schedule, current);
    reminderTimer = setTimeoutFn(async () => {
      reminderTimer = null;
      await deliver(target, token);
      if (active(token)) planReminder(token);
    }, Math.max(0, target.getTime() - current.getTime()));
  }

  async function deliver(target, token = epoch) {
    if (!active(token) || !schedule.enabled || !stateHealthy || !allowedUsers.size) return;
    const key = slotKey(target);
    const slots = state.slots && typeof state.slots === "object" ? state.slots : {};
    const slot = slots[key] && typeof slots[key] === "object" ? slots[key] : {};
    const reminder = reminderFor(target);
    let text = reminder.fallback;
    try {
      const generated = await settleWithSignal(
        () => generateReminder(reminder.kind, { signal: lifecycleController.signal }),
        lifecycleController.signal,
      );
      if (active(token) && String(generated || "").trim()) text = String(generated).trim().slice(0, 1500);
    } catch (error) {
      warn(`life_support_generate_${safeErrorCode(error, "fallback")}`);
    }
    if (!active(token)) return;
    for (const userOpenId of allowedUsers) {
      if (!active(token)) return;
      const userKey = userDedupeKey(userOpenId);
      if (["sending", "success"].includes(slot[userKey]?.status)) continue;
      slot[userKey] = { status: "sending" };
      slots[key] = slot;
      trimSlots(slots);
      state = { schema_version: 1, slots };
      try { persist(); } catch { stateHealthy = false; warn("life_support_state_write_failed"); return; }
      try {
        await settleWithSignal(
          () => sendText(
            userOpenId,
            undefined,
            text,
            { signal: lifecycleController.signal },
          ),
          lifecycleController.signal,
        );
        if (!active(token)) return;
        slot[userKey] = { status: "success" };
      } catch (error) {
        if (!active(token)) return;
        slot[userKey] = { status: "failed", error_code: safeErrorCode(error, "send_failed") };
      }
      try { persist(); } catch { stateHealthy = false; warn("life_support_state_write_failed"); return; }
    }
    log("life_support_delivery_cycle_complete");
  }

  async function refreshSchedule(token = epoch, signal = lifecycleController.signal) {
    if (!active(token) || !stateHealthy) return;
    try {
      const next = normalizeLifeSupportSchedule(await settleWithSignal(
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
        clearReminder();
        if (schedule.enabled) planReminder(nextToken);
      }
    } catch (error) {
      if (!active(token) || signal?.aborted) return;
      warn(`life_support_schedule_${safeErrorCode(error, "refresh_failed")}`);
    }
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    epoch += 1;
    lifecycleController.abort();
    externalSignal?.removeEventListener?.("abort", onExternalAbort);
    clearReminder();
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
        warn("life_support_state_corrupt");
        return;
      }
      await refreshSchedule(epoch, lifecycleController.signal);
      if (!stopped) refreshTimer = setIntervalFn(() => { void refreshSchedule(epoch); }, 30_000);
    },
    stop,
    deliver,
    refreshSchedule,
    snapshot: () => ({ schedule: { ...schedule }, stateHealthy, stopped }),
  };
}
