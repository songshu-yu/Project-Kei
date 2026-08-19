import crypto from "node:crypto";

import {
  atomicWriteState,
  hasExactStateKeys,
  isPlainStateObject,
  loadStateFile,
  safeErrorCode,
} from "./state_store.mjs";

const PROFILE = "qq_c2c_voice_v1";
const MEDIA_TYPE = "audio/silk";
const MAX_AUDIO_BYTES = 8 * 1024 * 1024;
const MAX_CONFIGURATION_BYTES = 64 * 1024;
const MAX_DURATION_MS = 60_000;
const MAX_STATE_ENTRIES = 1000;
const KEY_PATTERN = /^[a-f0-9]{32}$/;
const UTTERANCE_PATTERN = /^[A-Za-z0-9_-]{16,80}$/;
const VOICE_RESULT_CODES = new Set([
  "voice_sent",
  "voice_disabled",
  "voice_text_invalid",
  "voice_unavailable",
  "voice_duplicate",
  "voice_cancelled",
  "voice_metadata_invalid",
  "voice_audio_invalid",
  "voice_audio_too_large",
  "voice_upload_failed",
  "voice_file_info_invalid",
  "voice_message_failed",
  "voice_delivery_failed",
]);

function voiceResultCode(value, fallback = "voice_delivery_failed") {
  const candidate = safeErrorCode(value, fallback);
  return VOICE_RESULT_CODES.has(candidate) ? candidate : fallback;
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function isSilk(audio) {
  const header = Buffer.from("#!SILK_V3", "ascii");
  return audio.subarray(0, header.length).equals(header)
    || (audio[0] === 0x02 && audio.subarray(1, header.length + 1).equals(header));
}

function validateState(value) {
  if (!hasExactStateKeys(value, ["version", "entries"]) || value.version !== 1
    || !isPlainStateObject(value.entries)) return false;
  const keys = Object.keys(value.entries);
  if (keys.length > MAX_STATE_ENTRIES) return false;
  return keys.every(key => {
    const entry = value.entries[key];
    return KEY_PATTERN.test(key)
      && hasExactStateKeys(entry, ["status"])
      && ["claimed", "sent"].includes(entry.status);
  });
}

function boundedInteger(value, min, max) {
  const number = typeof value === "string" && /^\d+$/.test(value) ? Number(value) : value;
  return Number.isSafeInteger(number) && number >= min && number <= max ? number : null;
}

function safeJsonResponse(response, body) {
  if (!response?.ok) throw Object.assign(new Error("http_failed"), { code: `http_${response?.status || 0}` });
  let value;
  try { value = JSON.parse(Buffer.from(body).toString("utf8")); } catch {
    throw Object.assign(new Error("invalid_response"), { code: "invalid_response" });
  }
  if (!isPlainStateObject(value)) throw Object.assign(new Error("invalid_response"), { code: "invalid_response" });
  return value;
}

export function createVoiceReplyController({
  enabled = false,
  allowedUsers,
  projectKeiUrl,
  qqRequest,
  statePath,
  fetchImpl = fetch,
  timeoutMs = 45_000,
  fsImpl,
  sequence = () => Math.floor(Math.random() * 65_536),
  logger = { info() {}, warn() {}, error() {} },
}) {
  let stopped = false;
  const activeControllers = new Set();
  const inFlight = new Set();
  const loaded = loadStateFile(statePath, { version: 1, entries: {} }, { fsImpl });
  const healthyState = loaded.healthy && validateState(loaded.state);
  const state = healthyState ? loaded.state : null;

  async function withDeadline(operation) {
    if (stopped) throw Object.assign(new Error("voice_stopped"), { code: "voice_stopped" });
    const active = { controller: new AbortController(), reader: null };
    activeControllers.add(active);
    const cancel = () => {
      active.controller.abort();
      if (active.reader) void active.reader.cancel().catch(() => {});
    };
    const timer = setTimeout(cancel, timeoutMs);
    try {
      const result = await operation(active);
      if (active.controller.signal.aborted || stopped) {
        throw Object.assign(new Error("voice_cancelled"), { code: "voice_cancelled" });
      }
      return result;
    } finally {
      clearTimeout(timer);
      activeControllers.delete(active);
    }
  }

  async function readBoundedBody(response, active, {
    maxBytes,
    invalidCode,
    tooLargeCode,
  }) {
    if (!response.body || typeof response.body.getReader !== "function") {
      throw Object.assign(new Error(invalidCode), { code: invalidCode });
    }
    const reader = response.body.getReader();
    active.reader = reader;
    const chunks = [];
    let total = 0;
    const read = () => new Promise((resolve, reject) => {
      const aborted = () => {
        active.controller.signal.removeEventListener("abort", aborted);
        reject(Object.assign(new Error("voice_cancelled"), { code: "voice_cancelled" }));
      };
      active.controller.signal.addEventListener("abort", aborted, { once: true });
      reader.read().then(
        value => {
          active.controller.signal.removeEventListener("abort", aborted);
          resolve(value);
        },
        error => {
          active.controller.signal.removeEventListener("abort", aborted);
          reject(error);
        },
      );
    });
    let completed = false;
    try {
      while (true) {
        const { done, value } = await read();
        if (active.controller.signal.aborted || stopped) {
          throw Object.assign(new Error("voice_cancelled"), { code: "voice_cancelled" });
        }
        if (done) break;
        const chunk = Buffer.from(value || []);
        total += chunk.length;
        if (total > maxBytes) {
          active.controller.abort();
          void reader.cancel().catch(() => {});
          throw Object.assign(new Error(tooLargeCode), { code: tooLargeCode });
        }
        chunks.push(chunk);
      }
      completed = true;
    } catch (error) {
      void reader.cancel().catch(() => {});
      throw error;
    } finally {
      active.reader = null;
      if (completed) reader.releaseLock();
    }
    return Buffer.concat(chunks, total);
  }

  async function readBoundedAudio(response, active, expectedLength) {
    const audio = await readBoundedBody(response, active, {
      maxBytes: MAX_AUDIO_BYTES,
      invalidCode: "voice_audio_invalid",
      tooLargeCode: "voice_audio_too_large",
    });
    if (audio.length !== expectedLength) {
      throw Object.assign(new Error("voice_audio_invalid"), { code: "voice_audio_invalid" });
    }
    return audio;
  }

  async function readiness() {
    return withDeadline(async active => {
      const response = await fetchImpl(`${projectKeiUrl}/api/v1/qq-control/configuration`, {
        method: "GET",
        headers: { "Cache-Control": "no-store" },
        redirect: "error",
        signal: active.controller.signal,
      });
      const payload = await readBoundedBody(response, active, {
        maxBytes: MAX_CONFIGURATION_BYTES,
        invalidCode: "invalid_response",
        tooLargeCode: "invalid_response",
      });
      const body = safeJsonResponse(response, payload);
      return body.reply_with_voice === true
        && body.voice_reply_available === true
        && body.voice_profile === PROFILE
        && body.voice_profile_ready === true
        && body.qq_media_upload_capability === "available";
    });
  }

  function persist() {
    atomicWriteState(statePath, state, { fsImpl });
  }

  function claim(key) {
    if (!state || state.entries[key] || inFlight.has(key)) return false;
    while (Object.keys(state.entries).length >= MAX_STATE_ENTRIES) {
      delete state.entries[Object.keys(state.entries)[0]];
    }
    state.entries[key] = { status: "claimed" };
    try {
      persist();
    } catch {
      delete state.entries[key];
      return false;
    }
    inFlight.add(key);
    return true;
  }

  async function synthesize(text, idempotencyKey) {
    const encoded = JSON.stringify({ purpose: "qq_reply", text });
    return withDeadline(async active => {
      const response = await fetchImpl(`${projectKeiUrl}/api/v1/voice/synthesize`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: encoded,
        redirect: "error",
        signal: active.controller.signal,
      });
      if (response.status !== 200) throw Object.assign(new Error("voice_unavailable"), { code: "voice_unavailable" });
      const contentType = String(response.headers.get("content-type") || "").trim().toLowerCase();
      const final = String(response.headers.get("x-kei-audio-final") || "").trim().toLowerCase();
      const profile = String(response.headers.get("x-kei-audio-profile") || "").trim();
      const utteranceId = String(response.headers.get("x-kei-utterance-id") || "").trim();
      const contentLength = boundedInteger(response.headers.get("content-length"), 1, MAX_AUDIO_BYTES);
      const durationMs = boundedInteger(response.headers.get("x-kei-audio-duration-ms"), 1, MAX_DURATION_MS);
      if (contentType !== MEDIA_TYPE || final !== "true" || profile !== PROFILE
        || !UTTERANCE_PATTERN.test(utteranceId) || contentLength === null || durationMs === null) {
        throw Object.assign(new Error("voice_metadata_invalid"), { code: "voice_metadata_invalid" });
      }
      const audio = await readBoundedAudio(response, active, contentLength);
      if (!isSilk(audio)) {
        throw Object.assign(new Error("voice_audio_invalid"), { code: "voice_audio_invalid" });
      }
      return { audio, durationMs };
    });
  }

  async function upload(user, inboundId, audio) {
    const userPath = encodeURIComponent(user);
    if (stopped || !allowedUsers.has(user)) throw Object.assign(new Error("voice_cancelled"), { code: "voice_cancelled" });
    let completed;
    try {
      completed = await qqRequest("POST", `/v2/users/${userPath}/files`, {
        file_type: 3,
        srv_send_msg: false,
        file_data: audio.toString("base64"),
      });
    } catch (error) {
      if (stopped || safeErrorCode(error) === "voice_cancelled") throw error;
      throw Object.assign(new Error("voice_upload_failed"), { code: "voice_upload_failed" });
    }
    const fileInfo = String(completed?.file_info || "");
    const ttl = completed?.ttl === undefined
      ? undefined
      : boundedInteger(completed.ttl, 0, Number.MAX_SAFE_INTEGER);
    if (!fileInfo || fileInfo.length > 4096 || /[\x00-\x1f\x7f]/.test(fileInfo) || ttl === null) {
      throw Object.assign(new Error("voice_file_info_invalid"), { code: "voice_file_info_invalid" });
    }
    if (stopped || !allowedUsers.has(user)) throw Object.assign(new Error("voice_cancelled"), { code: "voice_cancelled" });
    try {
      await qqRequest("POST", `/v2/users/${userPath}/messages`, {
        content: " ",
        msg_type: 7,
        media: { file_info: fileInfo },
        ...(inboundId ? { msg_id: inboundId } : {}),
        msg_seq: sequence(),
      });
    } catch (error) {
      if (stopped || safeErrorCode(error) === "voice_cancelled") throw error;
      throw Object.assign(new Error("voice_message_failed"), { code: "voice_message_failed" });
    }
  }

  async function deliver({ user, inboundId, text }) {
    if (!enabled || stopped || !healthyState || !allowedUsers?.has(user)) return { sent: false, code: "voice_disabled" };
    const normalized = String(text || "").trim();
    if (!normalized || normalized.length > 1500) return { sent: false, code: "voice_text_invalid" };
    let isReady = false;
    try { isReady = await readiness(); } catch { return { sent: false, code: "voice_unavailable" }; }
    if (!isReady || stopped || !allowedUsers.has(user)) return { sent: false, code: "voice_unavailable" };
    const key = sha256(`${user}\0${String(inboundId || "")}`).slice(0, 32);
    if (!claim(key)) return { sent: false, code: "voice_duplicate" };
    try {
      const result = await synthesize(normalized, `qqv-${key}`);
      if (stopped || !allowedUsers.has(user)) return { sent: false, code: "voice_cancelled" };
      await upload(user, inboundId, result.audio);
      if (stopped) return { sent: false, code: "voice_cancelled" };
      state.entries[key] = { status: "sent" };
      try { persist(); } catch { logger.warn("voice_state_finalize_failed"); }
      return { sent: true, code: "voice_sent" };
    } catch (error) {
      const code = voiceResultCode(error);
      logger.warn(code);
      return { sent: false, code };
    } finally {
      inFlight.delete(key);
    }
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    for (const active of activeControllers) {
      active.controller.abort();
      if (active.reader) void active.reader.cancel().catch(() => {});
    }
    activeControllers.clear();
  }

  return {
    deliver,
    stop,
    snapshot: () => ({ enabled, stopped, healthyState, inFlight: inFlight.size }),
  };
}

export const VOICE_REPLY_LIMITS = Object.freeze({
  profile: PROFILE,
  mediaType: MEDIA_TYPE,
  maxAudioBytes: MAX_AUDIO_BYTES,
  maxDurationMs: MAX_DURATION_MS,
});

export const VOICE_REPLY_RESULT_CODES = Object.freeze([...VOICE_RESULT_CODES]);
