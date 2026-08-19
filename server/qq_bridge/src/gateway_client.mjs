import crypto from "node:crypto";
import process from "node:process";

import { atomicWriteState, safeErrorCode, settleWithSignal } from "./state_store.mjs";

const GATEWAY_STATES = new Set([
  "connecting",
  "identified_or_ready",
  "reconnect_wait",
  "failed",
  "stopped",
]);
const SAFE_CODE = /^[a-z0-9_]{1,64}$/;
const GATEWAY_ERROR_CODES = new Set([
  "closed",
  "gateway_failed",
  "gateway_hello_timeout",
  "gateway_request_failed",
  "gateway_rejected",
  "gateway_response_invalid",
  "gateway_ready_timeout",
  "gateway_url_invalid",
  "gateway_url_missing",
  "gateway_url_rejected",
  "heartbeat_send_failed",
  "heartbeat_timeout",
  "identify_send_failed",
  "invalid_session",
  "server_reconnect",
  "token_rejected",
  "token_request_failed",
  "token_response_invalid",
  "token_missing",
  "websocket_closed",
  "websocket_constructor_failed",
  "websocket_error",
]);
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

function gatewayErrorCode(value, fallback = "gateway_failed") {
  const candidate = safeErrorCode(value, fallback);
  return GATEWAY_ERROR_CODES.has(candidate) ? candidate : fallback;
}

function phaseErrorCode(stage, error) {
  const code = safeErrorCode(error, "unknown");
  if (stage === "token") {
    if (["http_401", "http_403", "token_missing"].includes(code)) return "token_rejected";
    if (code === "invalid_response") return "token_response_invalid";
    return "token_request_failed";
  }
  if (["http_401", "http_403"].includes(code)) return "gateway_rejected";
  if (code === "invalid_response") return "gateway_response_invalid";
  if (["gateway_url_invalid", "gateway_url_missing", "gateway_url_rejected"].includes(code)) return code;
  return "gateway_request_failed";
}

function stagedError(stage, error, signal) {
  if (signal?.aborted || error?.code === "request_cancelled") throw error;
  const code = phaseErrorCode(stage, error);
  throw Object.assign(new Error(code), { code });
}

export function createGatewayStatusFile({
  statePath,
  processId = process.pid,
  generation = crypto.randomBytes(16).toString("hex"),
  now = () => Date.now(),
  fsImpl,
}) {
  if (!Number.isSafeInteger(processId) || processId <= 0 || processId > 0x7fffffff
    || !/^[a-f0-9]{32}$/.test(generation)) {
    throw Object.assign(new Error("gateway_status_identity_invalid"), {
      code: "gateway_status_identity_invalid",
    });
  }
  let current = {
    schema_version: 1,
    generation,
    pid: processId,
    shutdown_control_ready: true,
    state: "stopped",
    gateway_ready: false,
    heartbeat_healthy: false,
    last_error_code: null,
    last_close_code: null,
    reconnect_count: 0,
    last_ready_at: null,
    voice_last_result_code: null,
    voice_last_attempt_at: null,
    updated_at: now(),
  };

  function write(snapshot) {
    const state = GATEWAY_STATES.has(snapshot?.state) ? snapshot.state : "failed";
    const candidateErrorCode = snapshot?.last_error_code == null
      ? null
      : gatewayErrorCode(snapshot?.last_error_code);
    const errorCode = candidateErrorCode === null || GATEWAY_ERROR_CODES.has(candidateErrorCode)
      ? candidateErrorCode : "gateway_failed";
    current = {
      schema_version: 1,
      generation,
      pid: processId,
      shutdown_control_ready: true,
      state,
      gateway_ready: snapshot?.gateway_ready === true,
      heartbeat_healthy: snapshot?.heartbeat_healthy === true,
      last_error_code: errorCode === null
        ? null
        : (SAFE_CODE.test(errorCode) ? errorCode : "gateway_failed"),
      last_close_code: Number.isInteger(snapshot?.last_close_code)
        && snapshot.last_close_code >= 1000 && snapshot.last_close_code <= 4999
        ? snapshot.last_close_code : null,
      reconnect_count: Number.isInteger(snapshot?.reconnect_count)
        && snapshot.reconnect_count >= 0 && snapshot.reconnect_count <= 1_000_000
        ? snapshot.reconnect_count : 0,
      last_ready_at: Number.isSafeInteger(snapshot?.last_ready_at)
        && snapshot.last_ready_at > 0 ? snapshot.last_ready_at : null,
      voice_last_result_code: current.voice_last_result_code,
      voice_last_attempt_at: current.voice_last_attempt_at,
      updated_at: now(),
    };
    if (current.gateway_ready && (
      current.state !== "identified_or_ready" || !current.heartbeat_healthy
      || current.last_ready_at === null
    )) {
      current.gateway_ready = false;
    }
    atomicWriteState(statePath, current, { fsImpl });
    return { ...current };
  }

  function writeVoiceResult(value) {
    const candidate = safeErrorCode(value, "voice_delivery_failed");
    current = {
      ...current,
      voice_last_result_code: VOICE_RESULT_CODES.has(candidate)
        ? candidate : "voice_delivery_failed",
      voice_last_attempt_at: now(),
      updated_at: now(),
    };
    atomicWriteState(statePath, current, { fsImpl });
    return { ...current };
  }

  return { generation, write, writeVoiceResult, snapshot: () => ({ ...current }) };
}

export function createGatewayClient({
  getAccessToken,
  getGatewayUrl,
  WebSocketFactory,
  onDispatch,
  logger,
  writeStatus = () => {},
  now = () => Date.now(),
  setTimeoutFn = setTimeout,
  clearTimeoutFn = clearTimeout,
  setIntervalFn = setInterval,
  clearIntervalFn = clearInterval,
  maxBackoffMs = 60_000,
  phaseTimeoutMs = 20_000,
  lifecycleSignal = null,
}) {
  const lifecycleController = new AbortController();
  let socket = null;
  let heartbeatTimer = null;
  let reconnectTimer = null;
  let phaseTimer = null;
  let connectPromise = null;
  let stopping = false;
  let attempt = 0;
  let generation = 0;
  let reconnectCount = 0;
  let state = "stopped";
  let gatewayReady = false;
  let heartbeatHealthy = false;
  let lastErrorCode = null;
  let lastCloseCode = null;
  let lastReadyAt = null;
  const onExternalAbort = () => stop();
  if (lifecycleSignal?.aborted) stop();
  else lifecycleSignal?.addEventListener?.("abort", onExternalAbort, { once: true });

  function publish(nextState, changes = {}) {
    state = GATEWAY_STATES.has(nextState) ? nextState : "failed";
    if (Object.prototype.hasOwnProperty.call(changes, "gatewayReady")) gatewayReady = changes.gatewayReady === true;
    if (Object.prototype.hasOwnProperty.call(changes, "heartbeatHealthy")) heartbeatHealthy = changes.heartbeatHealthy === true;
    if (Object.prototype.hasOwnProperty.call(changes, "lastErrorCode")) {
      lastErrorCode = changes.lastErrorCode === null ? null : gatewayErrorCode(changes.lastErrorCode);
    }
    if (Object.prototype.hasOwnProperty.call(changes, "lastCloseCode")) lastCloseCode = changes.lastCloseCode;
    if (Object.prototype.hasOwnProperty.call(changes, "lastReadyAt")) lastReadyAt = changes.lastReadyAt;
    if (!heartbeatHealthy) gatewayReady = false;
    try {
      writeStatus({
        state,
        gateway_ready: gatewayReady,
        heartbeat_healthy: heartbeatHealthy,
        last_error_code: lastErrorCode,
        last_close_code: lastCloseCode,
        reconnect_count: reconnectCount,
        last_ready_at: lastReadyAt,
      });
    } catch {
      logger.warn("gateway_status_write_failed");
    }
  }

  function clearHeartbeat() {
    if (heartbeatTimer) clearIntervalFn(heartbeatTimer);
    heartbeatTimer = null;
  }

  function clearReconnect() {
    if (reconnectTimer) clearTimeoutFn(reconnectTimer);
    reconnectTimer = null;
  }

  function clearPhaseTimer() {
    if (phaseTimer) clearTimeoutFn(phaseTimer);
    phaseTimer = null;
  }

  function scheduleReconnect(code, token, closeCode = null) {
    if (stopping || token !== generation || reconnectTimer) return;
    clearHeartbeat();
    clearPhaseTimer();
    gatewayReady = false;
    heartbeatHealthy = false;
    reconnectCount += 1;
    const delay = Math.min(maxBackoffMs, 1000 * 2 ** Math.min(attempt, 6));
    attempt += 1;
    logger.warn(`gateway_${gatewayErrorCode(code, "closed")}`);
    publish("reconnect_wait", {
      gatewayReady: false,
      heartbeatHealthy: false,
      lastErrorCode: code,
      lastCloseCode: closeCode,
    });
    reconnectTimer = setTimeoutFn(() => {
      reconnectTimer = null;
      void connect();
    }, delay);
  }

  async function connect() {
    if (stopping || socket || connectPromise) return connectPromise;
    const token = generation;
    publish("connecting", {
      gatewayReady: false,
      heartbeatHealthy: false,
      lastErrorCode: null,
      lastCloseCode: null,
    });
    connectPromise = (async () => {
      try {
        let accessToken;
        try {
          accessToken = await settleWithSignal(
            () => getAccessToken(lifecycleController.signal),
            lifecycleController.signal,
          );
        } catch (error) {
          stagedError("token", error, lifecycleController.signal);
        }
        let gatewayUrl;
        try {
          gatewayUrl = await settleWithSignal(
            () => getGatewayUrl(lifecycleController.signal),
            lifecycleController.signal,
          );
        } catch (error) {
          stagedError("gateway", error, lifecycleController.signal);
        }
        if (stopping || token !== generation) return;
        let ws;
        try {
          ws = new WebSocketFactory(gatewayUrl);
        } catch {
          throw Object.assign(new Error("websocket_constructor_failed"), {
            code: "websocket_constructor_failed",
          });
        }
        socket = ws;
        let lastSequence = null;
        let awaitingHeartbeatAck = false;
        let heartbeatAcknowledged = false;
        let readySeen = false;
        let helloSeen = false;
        let heartbeatIntervalMs = null;
        let pendingFailure = null;

        const acceptSequence = payload => {
          if (Number.isSafeInteger(payload?.s) && payload.s >= 0) lastSequence = payload.s;
        };

        const failSocket = code => {
          if (stopping || token !== generation || socket !== ws) return;
          pendingFailure = gatewayErrorCode(code);
          publish("failed", {
            gatewayReady: false,
            heartbeatHealthy: false,
            lastErrorCode: pendingFailure,
          });
          try { ws.close(4000, "reconnect"); } catch {
            if (socket === ws) socket = null;
            scheduleReconnect(pendingFailure, token);
          }
        };

        const armPhaseTimeout = code => {
          clearPhaseTimer();
          phaseTimer = setTimeoutFn(() => failSocket(code), phaseTimeoutMs);
        };

        const sendHeartbeat = () => {
          if (stopping || token !== generation || socket !== ws || ws.readyState !== 1) return;
          if (awaitingHeartbeatAck) {
            failSocket("heartbeat_timeout");
            return;
          }
          try {
            ws.send(JSON.stringify({ op: 1, d: lastSequence }));
            awaitingHeartbeatAck = true;
          } catch {
            failSocket("heartbeat_send_failed");
          }
        };

        armPhaseTimeout("gateway_hello_timeout");
        ws.on("open", () => {
          if (stopping || token !== generation || socket !== ws) return;
          publish("connecting", {
            gatewayReady: false,
            heartbeatHealthy: false,
          });
        });
        ws.on("message", raw => {
          if (stopping || token !== generation || socket !== ws) return;
          let payload;
          try { payload = JSON.parse(raw.toString()); } catch {
            logger.warn("gateway_payload_invalid");
            return;
          }
          if (payload.op === 10) {
            if (helloSeen) {
              logger.warn("gateway_duplicate_hello");
              return;
            }
            helloSeen = true;
            heartbeatIntervalMs = Math.max(
              1000,
              Math.min(120_000, Number(payload.d?.heartbeat_interval || 45_000)),
            );
            clearPhaseTimer();
            try {
              ws.send(JSON.stringify({
                op: 2,
                d: { token: `QQBot ${accessToken}`, intents: (1 << 25), shard: [0, 1] },
              }));
            } catch {
              failSocket("identify_send_failed");
              return;
            }
            publish("identified_or_ready", {
              gatewayReady: false,
              heartbeatHealthy: false,
              lastErrorCode: null,
            });
            clearHeartbeat();
            armPhaseTimeout("gateway_ready_timeout");
          } else if (payload.op === 11) {
            if (!readySeen || !awaitingHeartbeatAck) {
              logger.warn("gateway_heartbeat_ack_unexpected");
              return;
            }
            awaitingHeartbeatAck = false;
            heartbeatAcknowledged = true;
            heartbeatHealthy = true;
            publish("identified_or_ready", {
              gatewayReady: readySeen,
              heartbeatHealthy: true,
              lastErrorCode: null,
            });
          } else if (payload.op === 0 && payload.t === "READY") {
            if (!helloSeen) {
              logger.warn("gateway_ready_before_hello");
              return;
            }
            if (readySeen) {
              logger.warn("gateway_duplicate_ready");
              return;
            }
            readySeen = true;
            acceptSequence(payload);
            lastReadyAt = now();
            attempt = 0;
            clearPhaseTimer();
            sendHeartbeat();
            if (pendingFailure || stopping || token !== generation || socket !== ws) return;
            clearHeartbeat();
            heartbeatTimer = setIntervalFn(sendHeartbeat, heartbeatIntervalMs);
            publish("identified_or_ready", {
              gatewayReady: false,
              heartbeatHealthy: false,
              lastErrorCode: null,
              lastReadyAt,
            });
          } else if (payload.op === 0) {
            if (readySeen && heartbeatAcknowledged) {
              acceptSequence(payload);
              void onDispatch(payload.t, payload.d);
            } else logger.warn("gateway_dispatch_before_ready");
          } else if (payload.op === 7) {
            pendingFailure = "server_reconnect";
            try { ws.close(4000, "reconnect"); } catch { scheduleReconnect(pendingFailure, token); }
          } else if (payload.op === 9) {
            pendingFailure = "invalid_session";
            publish("failed", {
              gatewayReady: false,
              heartbeatHealthy: false,
              lastErrorCode: pendingFailure,
            });
            try { ws.close(4000, "reconnect"); } catch { scheduleReconnect(pendingFailure, token); }
          }
        });
        ws.on("error", () => failSocket("websocket_error"));
        ws.on("close", code => {
          if (socket !== ws) return;
          socket = null;
          const closeCode = Number.isInteger(code) && code >= 1000 && code <= 4999 ? code : null;
          scheduleReconnect(pendingFailure || "websocket_closed", token, closeCode);
        });
      } catch (error) {
        if (stopping || token !== generation) return;
        publish("failed", {
          gatewayReady: false,
          heartbeatHealthy: false,
          lastErrorCode: gatewayErrorCode(error),
        });
        scheduleReconnect(gatewayErrorCode(error), token);
      } finally {
        connectPromise = null;
      }
    })();
    return connectPromise;
  }

  function stop() {
    if (stopping) return;
    stopping = true;
    generation += 1;
    lifecycleController.abort();
    lifecycleSignal?.removeEventListener?.("abort", onExternalAbort);
    clearHeartbeat();
    clearReconnect();
    clearPhaseTimer();
    const active = socket;
    socket = null;
    if (active) {
      try { active.close(1000, "shutdown"); } catch {}
      try { active.terminate?.(); } catch {}
    }
    publish("stopped", {
      gatewayReady: false,
      heartbeatHealthy: false,
      lastErrorCode: null,
      lastCloseCode: 1000,
    });
  }

  return {
    connect,
    stop,
    snapshot: () => ({
      stopping,
      state,
      gatewayReady,
      heartbeatHealthy,
      hasSocket: Boolean(socket),
      hasHeartbeat: Boolean(heartbeatTimer),
      hasReconnect: Boolean(reconnectTimer),
      hasPhaseTimer: Boolean(phaseTimer),
      attempt,
      reconnectCount,
      lastErrorCode,
      lastCloseCode,
      lastReadyAt,
    }),
  };
}
