import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const SAFE_CODE = /^[a-z][a-z0-9_]{0,47}$/;
const USER_KEY = /^[a-f0-9]{24}$/;
const DELIVERY_STATUSES = new Set(["sending", "success", "failed"]);

export function lifecycleCancelledError() {
  return Object.assign(new Error("lifecycle_cancelled"), { code: "lifecycle_cancelled" });
}

export function settleWithSignal(factory, signal) {
  if (signal?.aborted) return Promise.reject(lifecycleCancelledError());
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = callback => value => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener?.("abort", onAbort);
      callback(value);
    };
    const onAbort = () => finish(reject)(lifecycleCancelledError());
    signal?.addEventListener?.("abort", onAbort, { once: true });
    let pending;
    try { pending = factory(); } catch (error) { finish(reject)(error); return; }
    Promise.resolve(pending).then(finish(resolve), finish(reject));
  });
}

export function isPlainStateObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
}

export function hasExactStateKeys(value, required, optional = []) {
  if (!isPlainStateObject(value)) return false;
  const keys = Object.keys(value);
  const allowed = new Set([...required, ...optional]);
  return required.every(key => Object.hasOwn(value, key)) && keys.every(key => allowed.has(key));
}

export function isStateDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function isStateSlot(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) return false;
  return isStateDate(value.slice(0, 10));
}

export function isSafeStateCode(value) {
  return typeof value === "string" && SAFE_CODE.test(value);
}

export function validateDeliveryBuckets(
  buckets,
  { maxBuckets, validateBucketKey },
) {
  if (!isPlainStateObject(buckets)) return false;
  const bucketKeys = Object.keys(buckets);
  if (bucketKeys.length > maxBuckets) return false;
  return bucketKeys.every(bucketKey => {
    const entries = buckets[bucketKey];
    if (!validateBucketKey(bucketKey) || !isPlainStateObject(entries)) return false;
    const userKeys = Object.keys(entries);
    return userKeys.every(userKey => {
      if (!USER_KEY.test(userKey)) return false;
      const entry = entries[userKey];
      if (!hasExactStateKeys(entry, ["status"], ["error_code"])) return false;
      if (!DELIVERY_STATUSES.has(entry.status)) return false;
      if (entry.status === "failed") return Object.hasOwn(entry, "error_code") && isSafeStateCode(entry.error_code);
      return !Object.hasOwn(entry, "error_code");
    });
  });
}

export function userDedupeKey(userOpenId) {
  return crypto.createHash("sha256").update(String(userOpenId || ""), "utf8").digest("hex").slice(0, 24);
}

export function safeErrorCode(value, fallback = "operation_failed") {
  const source = value && typeof value === "object" ? value.code : value;
  const candidate = String(source || "").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  return SAFE_CODE.test(candidate) ? candidate : fallback;
}

export function loadStateFile(statePath, defaultState, { fsImpl = fs } = {}) {
  try {
    const parsed = JSON.parse(fsImpl.readFileSync(statePath, "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid_root");
    return { healthy: true, state: parsed, errorCode: "" };
  } catch (error) {
    if (error?.code === "ENOENT") return { healthy: true, state: structuredClone(defaultState), errorCode: "" };
    return { healthy: false, state: null, errorCode: "state_corrupt" };
  }
}

export function atomicWriteState(statePath, state, { fsImpl = fs, randomId = () => crypto.randomUUID() } = {}) {
  const directory = path.dirname(statePath);
  const tempPath = path.join(directory, `.${path.basename(statePath)}.${process.pid}.${randomId()}.tmp`);
  let descriptor = null;
  try {
    fsImpl.mkdirSync(directory, { recursive: true });
    descriptor = fsImpl.openSync(tempPath, "wx", 0o600);
    fsImpl.writeFileSync(descriptor, `${JSON.stringify(state, null, 2)}\n`, "utf8");
    fsImpl.fsyncSync(descriptor);
    fsImpl.closeSync(descriptor);
    descriptor = null;
    fsImpl.renameSync(tempPath, statePath);
  } catch (error) {
    if (descriptor !== null) {
      try { fsImpl.closeSync(descriptor); } catch {}
    }
    try { fsImpl.unlinkSync(tempPath); } catch {}
    const wrapped = new Error("state_write_failed");
    wrapped.code = "state_write_failed";
    throw wrapped;
  }
}
