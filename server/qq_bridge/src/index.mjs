import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";

import {
  createBridgeMessageHandler,
  createQqApiClient,
  createSafeLogger,
  fetchWithTimeout,
  fixedQqEndpointBase,
  readSafeJson,
  validateGatewayUrl,
} from "./bridge_core.mjs";
import { createDailyBriefingScheduler } from "./daily_briefing_scheduler.mjs";
import { createGatewayClient, createGatewayStatusFile } from "./gateway_client.mjs";
import { createFocusEncouragementScheduler } from "./focus_encouragement_scheduler.mjs";
import { createLifeSupportScheduler } from "./life_support_scheduler.mjs";
import { safeErrorCode } from "./state_store.mjs";
import { createShutdownRequestWatcher } from "./shutdown_control.mjs";
import { createVoiceReplyController } from "./voice_reply.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ENV_PATH = path.resolve(String(process.env.PROJECT_KEI_QQ_ENV_PATH || path.join(ROOT, ".env")));
const DATA_ROOT = path.resolve(String(process.env.PROJECT_KEI_QQ_DATA_ROOT || path.join(ROOT, "data")));

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  for (const rawLine of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const separator = line.indexOf("=");
    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
    if (key && !process.env[key]) process.env[key] = value;
  }
}

function required(name) {
  const value = String(process.env[name] || "").trim();
  if (!value) throw Object.assign(new Error("required_configuration_missing"), { code: "required_configuration_missing" });
  return value;
}

function localProjectKeiUrl(value) {
  const parsed = new URL(String(value || "http://127.0.0.1:8000"));
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]", "::1"].includes(host) || (parsed.port && parsed.port !== "8000") || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw Object.assign(new Error("project_kei_url_not_loopback"), { code: "project_kei_url_not_loopback" });
  }
  parsed.pathname = parsed.pathname.replace(/\/+$/, "");
  return parsed.toString().replace(/\/+$/, "");
}

async function main() {
  loadEnvFile(ENV_PATH);
  const config = {
    appId: required("QQBOT_APPID"),
    secret: required("QQBOT_SECRET"),
    projectKeiUrl: localProjectKeiUrl(process.env.PROJECT_KEI_URL),
    apiBase: fixedQqEndpointBase(
      process.env.QQBOT_API_BASE,
      "https://api.bot.qq.com",
      new Set(["https://api.bot.qq.com", "https://api.sgroup.qq.com"]),
    ),
    tokenBase: fixedQqEndpointBase(
      process.env.QQBOT_TOKEN_BASE,
      "https://bots.qq.com",
      new Set(["https://bots.qq.com"]),
    ),
    allowedUsers: new Set(String(process.env.QQBOT_ALLOW_FROM || "").split(",").map(value => value.trim()).filter(Boolean)),
    maxReplyChars: Math.min(2000, Math.max(200, Number.parseInt(process.env.QQBOT_REPLY_MAX_CHARS || "1500", 10) || 1500)),
    timeoutMs: Math.min(120_000, Math.max(5000, Number.parseInt(process.env.QQBOT_REQUEST_TIMEOUT_MS || "45000", 10) || 45000)),
    replyWithVoice: String(process.env.QQBOT_REPLY_WITH_VOICE || "false").trim().toLowerCase() === "true",
    lifeForecastEnabled: String(process.env.QQBOT_LIFE_FORECAST_ENABLED || "false").trim().toLowerCase() === "true",
  };
  const logger = createSafeLogger();
  const lifecycleController = new AbortController();
  const gatewayStatus = createGatewayStatusFile({
    statePath: path.join(DATA_ROOT, "gateway_status.json"),
  });
  const qq = createQqApiClient({ ...config });
  const voiceReplies = createVoiceReplyController({
    enabled: config.replyWithVoice,
    allowedUsers: config.allowedUsers,
    projectKeiUrl: config.projectKeiUrl,
    qqRequest: qq.request,
    statePath: path.join(DATA_ROOT, "voice_reply_delivery_state.json"),
    timeoutMs: config.timeoutMs,
    logger,
  });
  let focusScheduler = null;
  const focusEncouragements = {
    register: value => focusScheduler?.register(value),
    cancelUser: user => focusScheduler?.cancelUser(user),
  };
  const handler = createBridgeMessageHandler({
    allowedUsers: config.allowedUsers,
    qqRequest: qq.request,
    projectKeiUrl: config.projectKeiUrl,
    timeoutMs: config.timeoutMs,
    maxReplyChars: config.maxReplyChars,
    logger,
    focusEncouragements,
    voiceReplies,
    onVoiceResult: gatewayStatus.writeVoiceResult,
    lifecycleSignal: lifecycleController.signal,
    lifeForecastEnabled: config.lifeForecastEnabled,
  });

  const projectJson = async (url, options, label, timeout = config.timeoutMs) => {
    const response = await fetchWithTimeout(url, options, timeout);
    return readSafeJson(response, label);
  };
  const fetchSchedule = (url, { signal } = {}) => projectJson(url, { signal }, "schedule");
  const generateBriefing = ({ signal } = {}) => projectJson(`${config.projectKeiUrl}/api/v1/briefing/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rewrite: true, rewrite_refresh: false, patch_missing: true }),
    signal,
  }, "briefing_generate", 1_250_000);
  const generateReminder = async (kind, { signal } = {}) => {
    const body = await projectJson(`${config.projectKeiUrl}/life-support/reminder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
      signal,
    }, "life_support");
    const text = String(body.text || "").trim();
    if (!text) throw Object.assign(new Error("empty_reminder"), { code: "empty_reminder" });
    return text;
  };

  const dailyScheduler = createDailyBriefingScheduler({
    scheduleUrl: `${config.projectKeiUrl}/api/v1/qq-control/schedules/daily-briefing`,
    statePath: path.join(DATA_ROOT, "daily_briefing_schedule_state.json"),
    fetchSchedule,
    generateBriefing,
    getCachedBriefing: handler.cachedBriefing,
    sendMarkdown: handler.sendMarkdown,
    allowedUsers: config.allowedUsers,
    log: logger.info,
    warn: logger.warn,
  });
  const lifeScheduler = createLifeSupportScheduler({
    scheduleUrl: `${config.projectKeiUrl}/api/v1/qq-control/schedules/life-support`,
    statePath: path.join(DATA_ROOT, "life_support_schedule_state.json"),
    fetchSchedule,
    generateReminder,
    sendText: handler.sendText,
    allowedUsers: config.allowedUsers,
    log: logger.info,
    warn: logger.warn,
  });
  focusScheduler = createFocusEncouragementScheduler({
    statePath: path.join(DATA_ROOT, "focus_encouragement_state.json"),
    getFocusStatus: () => projectJson(
      `${config.projectKeiUrl}/api/v1/focus/status`,
      {},
      "focus_status",
    ),
    generateEncouragement: payload => projectJson(
      `${config.projectKeiUrl}/api/v1/focus/encouragement`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      "focus_encouragement",
    ),
    sendText: handler.sendText,
    allowedUsers: config.allowedUsers,
    log: logger.info,
    warn: logger.warn,
  });
  const gateway = createGatewayClient({
    getAccessToken: qq.getAccessToken,
    getGatewayUrl: async signal => {
      const body = await qq.request("GET", "/gateway", undefined, true, signal);
      if (!body.url) throw Object.assign(new Error("gateway_url_missing"), { code: "gateway_url_missing" });
      return validateGatewayUrl(body.url);
    },
    WebSocketFactory: WebSocket,
    onDispatch: handler.handleDispatch,
    logger,
    writeStatus: gatewayStatus.write,
    lifecycleSignal: lifecycleController.signal,
  });

  let stopped = false;
  let stdinListener = null;
  let shutdownControl = null;
  const shutdown = () => {
    if (stopped) return;
    stopped = true;
    lifecycleController.abort();
    gateway.stop();
    voiceReplies.stop();
    dailyScheduler.stop();
    lifeScheduler.stop();
    focusScheduler.stop();
    shutdownControl?.stop();
    if (stdinListener) process.stdin.off("data", stdinListener);
    process.off("SIGINT", shutdown);
    process.off("SIGTERM", shutdown);
    process.off("SIGBREAK", shutdown);
    process.stdin.pause();
    if (!process.stdin.isTTY && !process.stdin.destroyed) process.stdin.destroy();
    process.exitCode = 0;
    logger.info("bridge_stopped");
  };
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
  process.once("SIGBREAK", shutdown);
  if (!process.stdin.isTTY) {
    let controlBuffer = "";
    process.stdin.setEncoding("utf8");
    stdinListener = chunk => {
      controlBuffer = `${controlBuffer}${chunk}`.slice(-64);
      const lines = controlBuffer.split(/\r?\n/);
      controlBuffer = lines.pop() || "";
      if (lines.some(line => line === "shutdown")) shutdown();
    };
    process.stdin.on("data", stdinListener);
    process.stdin.resume();
  }
  shutdownControl = createShutdownRequestWatcher({
    requestPath: path.join(DATA_ROOT, "shutdown_request.json"),
    generation: gatewayStatus.generation,
    onShutdown: shutdown,
  });
  shutdownControl.start();
  logger.info(config.allowedUsers.size ? "bridge_starting_allowlist_configured" : "bridge_starting_allowlist_empty");
  try {
    await dailyScheduler.start({ signal: lifecycleController.signal });
    if (stopped) return;
    await lifeScheduler.start({ signal: lifecycleController.signal });
    if (stopped) return;
    focusScheduler.start();
    if (stopped) return;
    await gateway.connect();
  } catch (error) {
    shutdown();
    throw error;
  }
}

main().catch(error => {
  const logger = createSafeLogger();
  logger.error(`bridge_start_${safeErrorCode(error)}`);
  process.exitCode = 1;
});
