import fs from "node:fs";

const GENERATION = /^[a-f0-9]{32}$/;
const EXACT_FIELDS = new Set(["schema_version", "generation", "requested_at", "expires_at"]);

function validRequest(value, generation, now) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  if (keys.length !== EXACT_FIELDS.size || keys.some(key => !EXACT_FIELDS.has(key))) return false;
  if (value.schema_version !== 1 || value.generation !== generation) return false;
  if (!Number.isSafeInteger(value.requested_at) || !Number.isSafeInteger(value.expires_at)) return false;
  if (value.requested_at > now + 1000 || value.requested_at < now - 10_000) return false;
  return value.expires_at >= now && value.expires_at <= value.requested_at + 10_000;
}
export function createShutdownRequestWatcher({
  requestPath,
  generation,
  onShutdown,
  now = () => Date.now(),
  fsImpl = fs,
  setIntervalFn = setInterval,
  clearIntervalFn = clearInterval,
  intervalMs = 200,
}) {
  if (typeof requestPath !== "string" || !requestPath
    || !GENERATION.test(String(generation || "")) || typeof onShutdown !== "function") {
    throw Object.assign(new Error("shutdown_control_invalid"), { code: "shutdown_control_invalid" });
  }
  let timer = null;
  let stopped = false;
  let consumed = false;

  const inspect = () => {
    if (stopped || consumed) return false;
    try {
      const stat = fsImpl.lstatSync(requestPath);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0 || stat.size > 512) return false;
      const request = JSON.parse(fsImpl.readFileSync(requestPath, "utf8"));
      if (!validRequest(request, generation, now())) return false;
      consumed = true;
      try { fsImpl.unlinkSync(requestPath); } catch {}
      onShutdown();
      return true;
    } catch (error) {
      if (error?.code === "ENOENT") return false;
      return false;
    }
  };

  return {
    start() {
      if (stopped || timer !== null) return;
      inspect();
      if (!stopped && !consumed) timer = setIntervalFn(inspect, Math.max(50, Math.min(Number(intervalMs) || 200, 1000)));
    },
    stop() {
      if (stopped) return;
      stopped = true;
      if (timer !== null) clearIntervalFn(timer);
      timer = null;
    },
    inspect,
    snapshot: () => ({ stopped, consumed, active: timer !== null }),
  };
}
