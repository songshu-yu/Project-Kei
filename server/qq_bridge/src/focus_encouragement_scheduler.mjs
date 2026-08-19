import crypto from "node:crypto";

import {
  atomicWriteState,
  hasExactStateKeys,
  isPlainStateObject,
  isSafeStateCode,
  loadStateFile,
  safeErrorCode,
  userDedupeKey,
} from "./state_store.mjs";

const DEFAULT_STATE = Object.freeze({ schema_version: 1, entries: {} });
const MAX_ENTRIES = 256;
const USER_KEY = /^[a-f0-9]{24}$/;
const ENTRY_KEY = /^[a-f0-9]{24}$/;
const SESSION_ID = /^[A-Za-z0-9_-]{1,64}$/;
const STATUSES = new Set(["scheduled", "sending", "sent", "failed", "cancelled"]);

function validLocalTimestamp(value) {
  if (typeof value !== "string" || value.length > 64 || !/^\d{4}-\d{2}-\d{2}T/.test(value)) return false;
  return Number.isFinite(new Date(value).getTime());
}

function validEntry(entry) {
  if (!hasExactStateKeys(
    entry,
    ["user_key", "session_id", "start_at", "due_at", "status"],
    ["error_code"],
  )) return false;
  if (
    !USER_KEY.test(entry.user_key)
    || !SESSION_ID.test(entry.session_id)
    || !validLocalTimestamp(entry.start_at)
    || !validLocalTimestamp(entry.due_at)
    || !STATUSES.has(entry.status)
  ) return false;
  if (entry.status === "failed") {
    return Object.hasOwn(entry, "error_code") && isSafeStateCode(entry.error_code);
  }
  return !Object.hasOwn(entry, "error_code");
}

export function validateFocusEncouragementState(value) {
  if (
    !hasExactStateKeys(value, ["schema_version", "entries"])
    || value.schema_version !== 1
    || !isPlainStateObject(value.entries)
  ) return false;
  const entries = Object.entries(value.entries);
  if (entries.length > MAX_ENTRIES) return false;
  return entries.every(([key, entry]) => ENTRY_KEY.test(key) && validEntry(entry));
}

function entryKey(userKey, sessionId, startAt) {
  return crypto.createHash("sha256")
    .update(`${userKey}:${sessionId}:${startAt}`, "utf8")
    .digest("hex")
    .slice(0, 24);
}

function makeEntryCapacity(entries) {
  if (Object.keys(entries).length < MAX_ENTRIES) return true;
  for (const [key, entry] of Object.entries(entries)) {
    if (["sent", "failed", "cancelled"].includes(entry.status)) delete entries[key];
    if (Object.keys(entries).length < MAX_ENTRIES) return true;
  }
  return false;
}

function validFocusStatus(value, entry) {
  return isPlainStateObject(value)
    && value.active === true
    && value.session_id === entry.session_id
    && value.start_at === entry.start_at
    && ["pomodoro", "focus"].includes(value.mode)
    && Number.isFinite(Number(value.elapsed_seconds))
    && Number(value.elapsed_seconds) >= 0
    && Number.isFinite(Number(value.remaining_seconds))
    && Number(value.remaining_seconds) > 0;
}

function fallbackText(status) {
  const elapsed = Math.max(0, Math.floor(Number(status?.elapsed_seconds || 0) / 60));
  return elapsed > 0
    ? `老师，已经稳稳专注 ${elapsed} 分钟了。别分心，继续把眼前这一小段守住。`
    : "老师，专注才刚开始。把无关的声音放远一点，继续做眼前这一件事。";
}

function safeOutboundText(value) {
  return String(value || "")
    .replace(/\b(authorization|cookie|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+/gi, "$1=[redacted]")
    .replace(/\bbearer\s+[a-z0-9._~+\/-]+/gi, "Bearer [redacted]")
    .replace(/[A-Za-z]:\\[^\s]+/g, "[internal-path]")
    .replace(/\/(?:home|Users|var|tmp)\/[^\s]+/g, "[internal-path]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180);
}

export function createFocusEncouragementScheduler({
  statePath,
  getFocusStatus,
  generateEncouragement,
  sendText,
  allowedUsers,
  log = () => {},
  warn = () => {},
  now = () => new Date(),
  setTimeoutFn = setTimeout,
  clearTimeoutFn = clearTimeout,
  stateIo = {},
}) {
  if (typeof getFocusStatus !== "function") throw new TypeError("getFocusStatus is required");
  if (typeof generateEncouragement !== "function") throw new TypeError("generateEncouragement is required");
  if (typeof sendText !== "function") throw new TypeError("sendText is required");
  const loaded = loadStateFile(statePath, DEFAULT_STATE, stateIo);
  let state = loaded.state;
  let stateHealthy = Boolean(loaded.healthy && validateFocusEncouragementState(state));
  let stopped = false;
  let started = false;
  const timers = new Map();
  const inFlight = new Set();

  const userByKey = () => new Map(
    [...allowedUsers].map(userOpenId => [userDedupeKey(userOpenId), userOpenId]),
  );
  const claimMatches = (key, claim, status) => {
    const current = state.entries[key];
    return Boolean(
      current
      && current.status === status
      && current.user_key === claim.user_key
      && current.session_id === claim.session_id
      && current.start_at === claim.start_at
      && current.due_at === claim.due_at
    );
  };
  const allowedUserFor = claim => {
    const userOpenId = userByKey().get(claim.user_key);
    return userOpenId && allowedUsers.has(userOpenId) ? userOpenId : undefined;
  };
  const persist = () => {
    if (!stateHealthy || stopped) return false;
    atomicWriteState(statePath, state, stateIo);
    return true;
  };
  const clearTimer = key => {
    const timer = timers.get(key);
    if (timer !== undefined) clearTimeoutFn(timer);
    timers.delete(key);
  };
  const persistOrClose = code => {
    try {
      persist();
      return true;
    } catch {
      stateHealthy = false;
      for (const key of timers.keys()) clearTimer(key);
      warn(code);
      return false;
    }
  };

  function arm(key) {
    clearTimer(key);
    if (stopped || !stateHealthy) return;
    const entry = state.entries[key];
    if (!entry || entry.status !== "scheduled") return;
    const delay = Math.max(0, new Date(entry.due_at).getTime() - now().getTime());
    timers.set(key, setTimeoutFn(() => {
      timers.delete(key);
      void deliver(key);
    }, delay));
  }

  function cancelEntry(key) {
    clearTimer(key);
    const entry = state.entries[key];
    if (!entry || !["scheduled", "sending"].includes(entry.status)) return false;
    state.entries[key] = { ...entry, status: "cancelled" };
    return true;
  }

  function cancelUser(userOpenId) {
    if (stopped || !stateHealthy) return false;
    const userKey = userDedupeKey(userOpenId);
    let changed = false;
    for (const [key, entry] of Object.entries(state.entries)) {
      if (entry.user_key === userKey) changed = cancelEntry(key) || changed;
    }
    if (changed) persistOrClose("focus_encouragement_state_write_failed");
    return changed;
  }

  function register({
    userOpenId,
    sessionId,
    startAt,
    encouragementAfterMinutes,
  }) {
    if (stopped || !stateHealthy || !allowedUsers.has(userOpenId)) {
      const error = new Error("focus_encouragement_unavailable");
      error.code = stateHealthy ? "focus_encouragement_unavailable" : "focus_encouragement_state_corrupt";
      throw error;
    }
    const delayMinutes = Number(encouragementAfterMinutes);
    if (
      !SESSION_ID.test(String(sessionId || ""))
      || !validLocalTimestamp(startAt)
      || !Number.isInteger(delayMinutes)
      || delayMinutes < 1
      || delayMinutes > 239
    ) {
      const error = new Error("focus_encouragement_invalid");
      error.code = "focus_encouragement_invalid";
      throw error;
    }
    const userKey = userDedupeKey(userOpenId);
    const key = entryKey(userKey, sessionId, startAt);
    if (state.entries[key]) return false;
    cancelUser(userOpenId);
    if (!stateHealthy) {
      const error = new Error("focus_encouragement_state_write_failed");
      error.code = "focus_encouragement_state_write_failed";
      throw error;
    }
    if (!makeEntryCapacity(state.entries)) {
      const error = new Error("focus_encouragement_state_capacity");
      error.code = "focus_encouragement_state_capacity";
      throw error;
    }
    const dueAt = new Date(new Date(startAt).getTime() + delayMinutes * 60_000);
    state.entries[key] = {
      user_key: userKey,
      session_id: sessionId,
      start_at: startAt,
      due_at: dueAt.toISOString(),
      status: "scheduled",
    };
    if (!persistOrClose("focus_encouragement_state_write_failed")) {
      const error = new Error("focus_encouragement_state_write_failed");
      error.code = "focus_encouragement_state_write_failed";
      throw error;
    }
    arm(key);
    return true;
  }

  async function deliver(key) {
    if (stopped || !stateHealthy) return;
    const entry = state.entries[key];
    if (!entry || entry.status !== "scheduled" || inFlight.has(key)) return;
    const claim = {
      user_key: entry.user_key,
      session_id: entry.session_id,
      start_at: entry.start_at,
      due_at: entry.due_at,
    };
    inFlight.add(key);
    try {
      let userOpenId = allowedUserFor(claim);
      if (!userOpenId) {
        if (claimMatches(key, claim, "scheduled")) {
          cancelEntry(key);
          persistOrClose("focus_encouragement_state_write_failed");
        }
        return;
      }
      let status;
      try {
        status = await getFocusStatus();
      } catch (error) {
        if (stopped || !stateHealthy || !claimMatches(key, claim, "scheduled")) return;
        userOpenId = allowedUserFor(claim);
        if (!userOpenId) {
          cancelEntry(key);
          persistOrClose("focus_encouragement_state_write_failed");
          return;
        }
        state.entries[key] = {
          ...state.entries[key],
          status: "failed",
          error_code: safeErrorCode(error, "focus_status_failed"),
        };
        persistOrClose("focus_encouragement_state_write_failed");
        return;
      }
      if (stopped || !stateHealthy || !claimMatches(key, claim, "scheduled")) return;
      userOpenId = allowedUserFor(claim);
      if (!userOpenId) {
        cancelEntry(key);
        persistOrClose("focus_encouragement_state_write_failed");
        return;
      }
      const current = state.entries[key];
      if (!validFocusStatus(status, current)) {
        cancelEntry(key);
        persistOrClose("focus_encouragement_state_write_failed");
        return;
      }
      state.entries[key] = { ...current, status: "sending" };
      if (!persistOrClose("focus_encouragement_state_write_failed")) return;
      let text = fallbackText(status);
      try {
        const result = await generateEncouragement({
          session_id: claim.session_id,
          start_at: claim.start_at,
        });
        if (
          stopped
          || !stateHealthy
          || !claimMatches(key, claim, "sending")
          || !allowedUserFor(claim)
        ) return;
        if (!isPlainStateObject(result) || result.eligible !== true || typeof result.generated !== "boolean") {
          state.entries[key] = {
            ...state.entries[key],
            status: "failed",
            error_code: "generation_invalid",
          };
          persistOrClose("focus_encouragement_state_write_failed");
          return;
        }
        if (result.generated === true) {
          if (typeof result.text !== "string" || !result.text.trim()) {
            state.entries[key] = {
              ...state.entries[key],
              status: "failed",
              error_code: "generation_invalid",
            };
            persistOrClose("focus_encouragement_state_write_failed");
            return;
          }
          text = safeOutboundText(result.text);
          if (!text) {
            state.entries[key] = {
              ...state.entries[key],
              status: "failed",
              error_code: "generation_invalid",
            };
            persistOrClose("focus_encouragement_state_write_failed");
            return;
          }
        }
      } catch (error) {
        if (
          stopped
          || !stateHealthy
          || !claimMatches(key, claim, "sending")
          || !allowedUserFor(claim)
        ) return;
        const code = safeErrorCode(error, "generation_failed");
        if (error?.name !== "AbortError" && code !== "timeout") {
          state.entries[key] = {
            ...state.entries[key],
            status: "failed",
            error_code: code,
          };
          persistOrClose("focus_encouragement_state_write_failed");
          return;
        }
        warn("focus_encouragement_generate_timeout_fallback");
      }
      userOpenId = allowedUserFor(claim);
      if (
        stopped
        || !stateHealthy
        || !userOpenId
        || !claimMatches(key, claim, "sending")
      ) return;
      try {
        await sendText(userOpenId, undefined, safeOutboundText(text));
      } catch (error) {
        if (stopped || !stateHealthy || !claimMatches(key, claim, "sending")) return;
        state.entries[key] = {
          ...state.entries[key],
          status: "failed",
          error_code: safeErrorCode(error, "send_failed"),
        };
        persistOrClose("focus_encouragement_state_write_failed");
        return;
      }
      if (stopped || !stateHealthy || !claimMatches(key, claim, "sending")) return;
      state.entries[key] = { ...state.entries[key], status: "sent" };
      if (persistOrClose("focus_encouragement_state_write_failed")) {
        log("focus_encouragement_sent");
      }
    } finally {
      inFlight.delete(key);
    }
  }

  return {
    start() {
      if (started || stopped) return;
      started = true;
      if (!stateHealthy) {
        warn("focus_encouragement_state_corrupt");
        return;
      }
      const users = userByKey();
      for (const [key, entry] of Object.entries(state.entries)) {
        if (entry.status === "scheduled" && users.has(entry.user_key)) arm(key);
      }
    },
    stop() {
      if (stopped) return;
      stopped = true;
      for (const key of [...timers.keys()]) clearTimer(key);
    },
    register,
    cancelUser,
    deliver,
    snapshot: () => ({
      stateHealthy,
      stopped,
      timerCount: timers.size,
      entries: structuredClone(state?.entries || {}),
    }),
  };
}
