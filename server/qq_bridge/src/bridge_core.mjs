import { safeErrorCode } from "./state_store.mjs";
import {
  BUSINESS_API_OPERATIONS,
  businessFailureMessage,
  createBusinessMenuController,
  mainMenuCard,
} from "./business_menu.mjs";

const DEFAULT_MAX_INPUT = 4000;
const DEFAULT_MAX_REPLY = 1500;
const DEFAULT_MAX_OUTPUT = 12_000;
const DEFAULT_MAX_JSON_BYTES = 4 * 1024 * 1024;
const HTTP_CONTEXT = Symbol("project-kei-http-context");

export function fixedQqEndpointBase(value, fallback, allowed) {
  const raw = String(value || fallback).trim().replace(/\/+$/, "");
  if (!(allowed instanceof Set) || !allowed.has(raw)) {
    throw Object.assign(new Error("qq_endpoint_rejected"), { code: "qq_endpoint_rejected" });
  }
  return raw;
}

export function validateGatewayUrl(value) {
  let parsed;
  try { parsed = new URL(String(value || "")); } catch {
    throw Object.assign(new Error("gateway_url_invalid"), { code: "gateway_url_invalid" });
  }
  if (parsed.protocol !== "wss:" || parsed.username || parsed.password
    || parsed.search || parsed.hash || (parsed.port && parsed.port !== "443")
    || !new Set(["api.bot.qq.com", "api.sgroup.qq.com"]).has(parsed.hostname.toLowerCase())
    || parsed.pathname !== "/websocket") {
    throw Object.assign(new Error("gateway_url_rejected"), { code: "gateway_url_rejected" });
  }
  return parsed.toString();
}

export class BoundedMessageDeduper {
  constructor(limit = 1000) {
    this.limit = Math.max(1, Number(limit) || 1000);
    this.ids = new Map();
  }

  remember(id) {
    const value = String(id || "");
    if (!value || value.length > 384 || this.ids.has(value)) return false;
    this.ids.set(value, true);
    while (this.ids.size > this.limit) this.ids.delete(this.ids.keys().next().value);
    return true;
  }
}

function boundedEventSequence(value) {
  if (Number.isSafeInteger(value) && value >= 0) return String(value);
  if (typeof value === "string" && /^\d{1,20}$/.test(value)) return value;
  return "";
}

export function c2cEventIdentity(event) {
  const id = String(event?.id || "");
  if (!id || id.length > 256) return "";
  const msgSeq = boundedEventSequence(event?.msg_seq);
  const msgIdx = boundedEventSequence(event?.message_scene?.ext?.msg_idx);
  const suffix = [msgSeq ? `seq:${msgSeq}` : "", msgIdx ? `idx:${msgIdx}` : ""]
    .filter(Boolean).join(":");
  return suffix ? `c2c:${id}:${suffix}` : `c2c:${id}`;
}

function c2cText(event, maxInputChars) {
  const messageType = event?.message_type === undefined ? 0 : event.message_type;
  if (![0, 103].includes(messageType) || typeof event?.content !== "string") return "";
  const text = event.content
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
    .trim();
  return text && text.length <= maxInputChars ? text : "";
}

export function createSafeLogger({ info = console.log, warning = console.warn, error = console.error } = {}) {
  const line = (level, code) => `[${new Date().toISOString()}] ${level} ${safeErrorCode(code, "event")}`;
  return {
    info: code => info(line("INFO", code)),
    warn: code => warning(line("WARN", code)),
    error: code => error(line("ERROR", code)),
  };
}

export async function fetchWithTimeout(url, options = {}, timeoutMs = 45_000, fetchImpl = fetch) {
  const controller = new AbortController();
  const externalSignal = options?.signal;
  let abortCode = "request_cancelled";
  let cleaned = false;
  let timer = null;
  const abort = code => {
    if (controller.signal.aborted) return;
    abortCode = code;
    controller.abort();
  };
  const onExternalAbort = () => abort("request_cancelled");
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    clearTimeout(timer);
    externalSignal?.removeEventListener?.("abort", onExternalAbort);
  };
  if (externalSignal?.aborted) {
    abort("request_cancelled");
    cleanup();
    throw controlledAbortError("request_cancelled");
  }
  externalSignal?.addEventListener?.("abort", onExternalAbort, { once: true });
  timer = setTimeout(() => abort("request_timeout"), timeoutMs);
  try {
    const response = await fetchImpl(url, { ...options, signal: controller.signal });
    if (!response || (typeof response !== "object" && typeof response !== "function")) {
      cleanup();
      throw Object.assign(new Error("request_invalid_response"), { code: "invalid_response" });
    }
    Object.defineProperty(response, HTTP_CONTEXT, {
      configurable: true,
      value: { controller, abort, abortCode: () => abortCode, cleanup },
    });
    if (controller.signal.aborted) {
      try { await Promise.resolve(response.body?.cancel?.()); } catch { /* cancellation is best effort */ }
      cleanup();
      throw controlledAbortError(abortCode);
    }
    return response;
  } catch (error) {
    cleanup();
    if (controller.signal.aborted) throw controlledAbortError(abortCode);
    throw error;
  }
}

function controlledAbortError(code) {
  const error = new Error(code === "request_timeout" ? "request_timeout" : "request_cancelled");
  error.name = "AbortError";
  error.code = code === "request_timeout" ? "request_timeout" : "request_cancelled";
  return error;
}

function safeBodyError(code, label) {
  const error = new Error(`${safeErrorCode(label)}_${code}`);
  error.code = code;
  return error;
}

function throwIfAborted(signal, context) {
  if (signal?.aborted) throw controlledAbortError(context?.abortCode?.() || "request_cancelled");
}

async function readBoundedBody(response, context, label, maxBytes) {
  const body = response?.body;
  const signal = context?.controller?.signal;
  let reader = null;
  let cancelStarted = false;
  const cancelReader = () => {
    if (cancelStarted) return;
    cancelStarted = true;
    try {
      const pending = reader?.cancel?.() ?? body?.cancel?.();
      Promise.resolve(pending).catch(() => {});
    } catch { /* cancellation is best effort */ }
  };
  if (signal?.aborted) {
    if (typeof body?.cancel !== "function" && typeof body?.getReader === "function") reader = body.getReader();
    cancelReader();
    throwIfAborted(signal, context);
  }
  reader = body && typeof body.getReader === "function" ? body.getReader() : null;
  const onAbort = () => cancelReader();
  signal?.addEventListener?.("abort", onAbort, { once: true });
  if (signal?.aborted) {
    cancelReader();
    throwIfAborted(signal, context);
  }
  let rejectOnAbort = null;
  const aborted = new Promise((_, reject) => {
    if (!signal) return;
    if (signal.aborted) reject(controlledAbortError(context.abortCode()));
    else {
      rejectOnAbort = () => reject(controlledAbortError(context.abortCode()));
      signal.addEventListener("abort", rejectOnAbort, { once: true });
    }
  });
  aborted.catch(() => {});
  try {
    const contentLength = String(response?.headers?.get?.("content-length") || "");
    if (/^\d+$/.test(contentLength) && Number(contentLength) > maxBytes) {
      context?.abort?.("response_too_large");
      cancelReader();
      throw safeBodyError("response_too_large", label);
    }
    if (!reader) {
      const raw = await (signal ? Promise.race([Promise.resolve().then(() => response.text()), aborted]) : response.text());
      throwIfAborted(signal, context);
      const bytes = new TextEncoder().encode(String(raw || ""));
      if (bytes.byteLength > maxBytes) {
        context?.abort?.("response_too_large");
        cancelReader();
        throw safeBodyError("response_too_large", label);
      }
      return String(raw || "");
    }
    const decoder = new TextDecoder("utf-8", { fatal: true });
    const chunks = [];
    let total = 0;
    while (true) {
      let result;
      try {
        result = await (signal ? Promise.race([reader.read(), aborted]) : reader.read());
      } catch (error) {
        if (signal?.aborted) throw controlledAbortError(context.abortCode());
        context?.abort?.("response_read_failed");
        cancelReader();
        throw safeBodyError("response_read_failed", label);
      }
      throwIfAborted(signal, context);
      if (result?.done) break;
      const value = result?.value instanceof Uint8Array
        ? result.value
        : new TextEncoder().encode(String(result?.value || ""));
      total += value.byteLength;
      if (total > maxBytes) {
        context?.abort?.("response_too_large");
        cancelReader();
        throw safeBodyError("response_too_large", label);
      }
      chunks.push(decoder.decode(value, { stream: true }));
    }
    throwIfAborted(signal, context);
    chunks.push(decoder.decode());
    throwIfAborted(signal, context);
    return chunks.join("");
  } finally {
    signal?.removeEventListener?.("abort", onAbort);
    if (rejectOnAbort) signal?.removeEventListener?.("abort", rejectOnAbort);
    try { reader?.releaseLock?.(); } catch { /* already cancelled */ }
  }
}

export async function readSafeJson(response, label = "request", maxBytes = DEFAULT_MAX_JSON_BYTES) {
  const context = response?.[HTTP_CONTEXT];
  let body = {};
  let invalidJson = false;
  try {
    const raw = await readBoundedBody(response, context, label, Math.max(1, Number(maxBytes) || DEFAULT_MAX_JSON_BYTES));
    throwIfAborted(context?.controller?.signal, context);
    body = raw ? JSON.parse(raw) : {};
    throwIfAborted(context?.controller?.signal, context);
  } catch (error) {
    if (error?.name === "AbortError" || ["response_too_large", "response_read_failed"].includes(error?.code)) throw error;
    body = {};
    invalidJson = true;
  } finally {
    context?.cleanup?.();
  }
  throwIfAborted(context?.controller?.signal, context);
  if (invalidJson || !body || typeof body !== "object" || Array.isArray(body)) {
    const error = new Error(`${safeErrorCode(label)}_invalid_response`);
    error.code = "invalid_response";
    throw error;
  }
  if (!response.ok) {
    const error = new Error(`${safeErrorCode(label)}_http_${response.status}`);
    error.code = `http_${response.status}`;
    throw error;
  }
  throwIfAborted(context?.controller?.signal, context);
  return body;
}

export function createQqApiClient({ appId, secret, apiBase, tokenBase, timeoutMs = 45_000, fetchImpl = fetch }) {
  let tokenCache = { value: "", expiresAt: 0 };

  async function token(force = false, signal) {
    throwIfAborted(signal, null);
    if (!force && tokenCache.value && Date.now() < tokenCache.expiresAt - 60_000) return tokenCache.value;
    const response = await fetchWithTimeout(`${tokenBase}/app/getAppAccessToken`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "User-Agent": "Project-Kei-QQ-Bridge" },
      body: JSON.stringify({ appId, clientSecret: secret }),
      signal,
    }, timeoutMs, fetchImpl);
    const body = await readSafeJson(response, "qq_token");
    throwIfAborted(signal, null);
    if (!body.access_token) {
      const error = new Error("token_missing");
      error.code = "token_missing";
      throw error;
    }
    tokenCache = { value: String(body.access_token), expiresAt: Date.now() + Math.max(60, Number(body.expires_in || 7200)) * 1000 };
    return tokenCache.value;
  }

  async function request(method, requestPath, body, allowRetry = true, signal) {
    throwIfAborted(signal, null);
    const accessToken = await token(false, signal);
    throwIfAborted(signal, null);
    const response = await fetchWithTimeout(`${apiBase}${requestPath}`, {
      method,
      headers: {
        Authorization: `QQBot ${accessToken}`,
        "Content-Type": "application/json",
        "User-Agent": "Project-Kei-QQ-Bridge",
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal,
    }, timeoutMs, fetchImpl);
    try {
      return await readSafeJson(response, "qq_api");
    } catch (error) {
      if (error?.code === "http_401" && allowRetry && !signal?.aborted) {
        throwIfAborted(signal, null);
        await token(true, signal);
        throwIfAborted(signal, null);
        return request(method, requestPath, body, false, signal);
      }
      throw error;
    }
  }

  return {
    request,
    getAccessToken: signal => token(false, signal),
    clearToken: () => { tokenCache = { value: "", expiresAt: 0 }; },
  };
}

function sanitizeVisibleText(value) {
  return String(value || "")
    .replace(/\b(authorization|cookie|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+/gi, "$1=[redacted]")
    .replace(/\bbearer\s+[a-z0-9._~+\/-]+/gi, "Bearer [redacted]")
    .replace(/[A-Za-z]:\\[^\s]+/g, "[internal-path]")
    .replace(/\/(?:home|Users|var|tmp)\/[^\s]+/g, "[internal-path]");
}

function compactText(value, maxLength) {
  const text = sanitizeVisibleText(value)
    .replace(/\s+/g, " ")
    .trim();
  return text.length > maxLength ? `${text.slice(0, Math.max(0, maxLength - 1))}…` : text;
}

function escapeMarkdown(value) {
  return String(value || "").replace(/[\\`*_{}[\]()#+!|]/g, "\\$&");
}

function safeUrl(value) {
  try {
    const parsed = new URL(String(value || ""));
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) return "";
    parsed.hash = "";
    for (const key of [...parsed.searchParams.keys()]) {
      if (/token|secret|auth|cookie|session|signature|key/i.test(key)) parsed.searchParams.delete(key);
    }
    return parsed.toString().slice(0, 2048);
  } catch {
    return "";
  }
}

function markdownLink(label, url) {
  const text = escapeMarkdown(compactText(label, 180) || "查看详情");
  const href = safeUrl(url);
  return href ? `[${text}](${href})` : text;
}

function normalizedItems(body) {
  if (Array.isArray(body?.items)) return body.items.slice(0, 60);
  const result = [];
  if (body?.items && typeof body.items === "object") {
    for (const [category, values] of Object.entries(body.items)) {
      if (!Array.isArray(values)) continue;
      for (const item of values.slice(0, 10)) result.push({ ...item, category });
    }
  }
  return result.slice(0, 60);
}

export function formatDailyBriefingMarkdown(body, maxLength = DEFAULT_MAX_OUTPUT) {
  const date = escapeMarkdown(compactText(body?.date, 24) || new Date().toISOString().slice(0, 10));
  const lines = ["# 天童 Kei · 每日情报", `> ${date} · 老师，今日情报已经整理好。`];
  const summary = compactText(String(body?.script || "").replace(/\[emotion:[^\]]+\]\s*/gi, ""), 1800);
  if (summary) lines.push("", "## 📝 Kei 总结", escapeMarkdown(summary));

  const warnings = Array.isArray(body?.warnings) ? body.warnings.slice(0, 6) : [];
  if (warnings.length) {
    lines.push("", "## ⚠ 数据覆盖");
    for (const warning of warnings) lines.push(`- ${escapeMarkdown(compactText(warning, 180))}`);
  }

  const titles = {
    papers: "## 📄 论文动态",
    social: "## 💬 社交动态",
    development: "## 💻 GitHub 动态",
    video: "## 📺 视频动态",
    money: "## 💡 信息差线索",
    general: "## 📌 其他动态",
    twitter: "## 💬 社交动态",
    github: "## 💻 GitHub 动态",
    bilibili: "## 📺 B站动态",
    youtube: "## ▶ YouTube 更新",
  };
  const grouped = new Map();
  for (const item of normalizedItems(body)) {
    const category = String(item?.category || item?.source_id || "general");
    if (!grouped.has(category)) grouped.set(category, []);
    if (grouped.get(category).length < 8) grouped.get(category).push(item);
  }
  for (const [category, items] of grouped) {
    lines.push("", titles[category] || titles.general);
    for (const item of items) {
      const title = markdownLink(item?.title, item?.url);
      const source = escapeMarkdown(compactText(item?.author || item?.source_id || item?.source, 80));
      const summaryText = escapeMarkdown(compactText(item?.summary, 180));
      lines.push(`- ${source ? `**${source}**：` : ""}${title}`);
      if (summaryText) lines.push(`  - ${summaryText}`);
    }
  }
  if (lines.length === 2) lines.push("", escapeMarkdown(compactText(body?.text, 1200) || "暂时没有可显示的情报内容。"));
  return lines.join("\n").slice(0, maxLength);
}

export function splitBoundedText(text, maxChars = DEFAULT_MAX_REPLY, maxTotal = DEFAULT_MAX_OUTPUT) {
  let remaining = sanitizeVisibleText(text).trim().slice(0, maxTotal);
  const chunks = [];
  while (remaining.length > maxChars && chunks.length < 12) {
    let end = remaining.lastIndexOf("\n", maxChars);
    if (end < maxChars * 0.55) end = remaining.lastIndexOf("。", maxChars);
    if (end < maxChars * 0.55) end = maxChars;
    chunks.push(remaining.slice(0, end).trim());
    remaining = remaining.slice(end).trim();
  }
  if (remaining && chunks.length < 12) chunks.push(remaining);
  return chunks.length ? chunks : ["老师，我刚才没有生成有效回复。请再说一次。"];
}

export function createBridgeMessageHandler({
  allowedUsers,
  qqRequest,
  projectKeiUrl,
  fetchImpl = fetch,
  timeoutMs = 45_000,
  maxInputChars = DEFAULT_MAX_INPUT,
  maxReplyChars = DEFAULT_MAX_REPLY,
  maxOutputChars = DEFAULT_MAX_OUTPUT,
  deduper = new BoundedMessageDeduper(),
  logger = createSafeLogger(),
  focusEncouragements = null,
  voiceReplies = null,
  onVoiceResult = () => {},
  lifecycleSignal = null,
  now = () => Date.now(),
  lifeForecastEnabled = false,
}) {
  const sequence = () => Math.floor(Math.random() * 65_536);
  const sendPayload = (user, body, { signal } = {}) => qqRequest(
    "POST",
    `/v2/users/${encodeURIComponent(user)}/messages`,
    body,
    true,
    signal || lifecycleSignal,
  );

  async function sendText(user, inboundId, text, control = {}) {
    for (const chunk of splitBoundedText(text, maxReplyChars, maxOutputChars)) {
      await sendPayload(user, { content: chunk, msg_type: 0, ...(inboundId ? { msg_id: inboundId } : {}), msg_seq: sequence() }, control);
    }
  }

  async function sendMarkdown(user, inboundId, markdown, control = {}) {
    for (const chunk of splitBoundedText(markdown, maxReplyChars, maxOutputChars)) {
      await sendPayload(user, { markdown: { content: chunk }, msg_type: 2, ...(inboundId ? { msg_id: inboundId } : {}), msg_seq: sequence() }, control);
    }
  }

  async function sendCard(user, inboundId, response) {
    await sendPayload(user, {
      markdown: { content: String(response?.markdown || "").slice(0, Math.min(maxReplyChars, 1200)) },
      msg_type: 2,
      ...(inboundId ? { msg_id: inboundId } : {}),
      msg_seq: sequence(),
      keyboard: { content: { rows: Array.isArray(response?.rows) ? response.rows.slice(0, 5) : [] } },
    });
  }

  async function sendBusinessResponse(user, inboundId, response) {
    if (response?.kind === "card") return sendCard(user, inboundId, response);
    return sendMarkdown(user, inboundId, String(response?.markdown || ""));
  }

  async function projectJson(url, options, label) {
    const response = await fetchWithTimeout(url, {
      ...options,
      signal: options?.signal || lifecycleSignal,
    }, timeoutMs, fetchImpl);
    return readSafeJson(response, label);
  }

  async function conversation(message) {
    const body = await projectJson(`${projectKeiUrl}/api/v1/conversation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }, "conversation");
    const text = String(body.text || "").trim().slice(0, maxOutputChars);
    if (!text) throw Object.assign(new Error("empty_reply"), { code: "empty_reply" });
    return text;
  }

  async function cachedBriefing({ signal } = {}) {
    const body = await projectJson(`${projectKeiUrl}/api/v1/briefing/today`, { signal }, "briefing_cache");
    if (!body.ready) throw Object.assign(new Error("cache_unavailable"), { code: "cache_unavailable" });
    return { cached: true, markdown: formatDailyBriefingMarkdown(body, maxOutputChars) };
  }

  async function businessApi(operation, payload) {
    if (!Object.prototype.hasOwnProperty.call(BUSINESS_API_OPERATIONS, operation)) {
      throw Object.assign(new Error("business_operation_rejected"), { code: "operation_rejected" });
    }
    const spec = BUSINESS_API_OPERATIONS[operation];
    if (spec.method === "GET" && payload !== undefined) {
      throw Object.assign(new Error("business_payload_rejected"), { code: "payload_rejected" });
    }
    const options = { method: spec.method };
    if (spec.method === "POST") {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(payload && typeof payload === "object" ? payload : {});
    }
    return projectJson(`${projectKeiUrl}${spec.path}`, options, `business_${operation}`);
  }

  const businessMenu = createBusinessMenuController({
    callApi: businessApi,
    now,
    lifeForecastEnabled,
    onFocusStarted: async value => {
      if (value.encouragementAfterMinutes === null) {
        focusEncouragements?.cancelUser?.(value.userOpenId);
        return;
      }
      if (typeof focusEncouragements?.register !== "function") {
        throw Object.assign(new Error("focus_encouragement_unavailable"), {
          code: "focus_encouragement_unavailable",
        });
      }
      return focusEncouragements.register(value);
    },
    onFocusStopped: async user => {
      focusEncouragements?.cancelUser?.(user);
    },
  });
  const normalized = message => String(message || "").toLowerCase().replace(/\s+/g, "");
  const isBriefing = message => ["每日情报", "今日情报", "今天情报", "今日简报", "dailybriefing"].some(value => normalized(message).includes(value));
  const isMenu = message => ["菜单", "功能菜单", "快捷菜单", "/menu", "功能"].includes(normalized(message));

  async function sendMenu(user, inboundId) {
    await sendBusinessResponse(user, inboundId, mainMenuCard());
  }

  async function handleC2C(event) {
    if (lifecycleSignal?.aborted) return;
    const user = String(event?.author?.user_openid || event?.author?.id || "");
    const id = String(event?.id || "");
    if (!user || user.length > 256 || !id || id.length > 256) return;
    if (!allowedUsers.size || !allowedUsers.has(user)) { logger.warn("c2c_unauthorized"); return; }
    const content = c2cText(event, maxInputChars);
    const identity = c2cEventIdentity(event);
    if (!content || !identity || !deduper.remember(identity)) return;
    try {
      if (isMenu(content)) await sendMenu(user, id);
      else {
        const routed = await businessMenu.handleText(content, { user });
        if (routed.handled) await sendBusinessResponse(user, id, routed.response);
        else if (isBriefing(content)) await sendMarkdown(user, id, (await cachedBriefing()).markdown);
        else {
          const reply = await conversation(content);
          await sendText(user, id, reply);
          if (typeof voiceReplies?.deliver === "function") {
            try {
              const voice = await voiceReplies.deliver({ user, inboundId: id, text: reply });
              try { onVoiceResult(voice?.code); } catch { logger.warn("c2c_voice_result_unavailable"); }
              if (voice?.sent) logger.info("c2c_voice_delivered");
            } catch {
              try { onVoiceResult("voice_delivery_failed"); } catch { logger.warn("c2c_voice_result_unavailable"); }
              logger.warn("c2c_voice_delivery_failed");
            }
          }
        }
      }
      logger.info("c2c_delivered");
    } catch (error) {
      if (lifecycleSignal?.aborted) return;
      logger.error(`c2c_${safeErrorCode(error)}`);
      try { await sendText(user, id, "抱歉，Kei 的本地服务暂时没有回应。请稍后再试一次。"); } catch { logger.error("c2c_fallback_send_failed"); }
    }
  }

  async function handleInteraction(event) {
    if (lifecycleSignal?.aborted) return;
    const user = String(event?.user_openid || event?.data?.resolved?.user_id || "");
    const id = String(event?.id || "");
    const button = String(event?.data?.resolved?.button_data || "");
    const briefingAction = button === "kei:daily-briefing";
    if ((!briefingAction && !businessMenu.recognizesAction(button)) || button.length > 128
      || !user || user.length > 256 || !id || id.length > 256) return;
    if (!allowedUsers.size || !allowedUsers.has(user)) { logger.warn("interaction_unauthorized"); return; }
    if (!deduper.remember(`interaction:${id}`)) return;
    try {
      await qqRequest("PUT", `/interactions/${encodeURIComponent(id)}`, { code: 0 }, true, lifecycleSignal);
    } catch (error) {
      if (lifecycleSignal?.aborted) return;
      logger.error(`interaction_ack_${safeErrorCode(error)}`);
      return;
    }
    try {
      if (briefingAction) await sendMarkdown(user, undefined, (await cachedBriefing()).markdown);
      else await sendBusinessResponse(user, undefined, await businessMenu.handleAction(button, { user }));
    } catch (error) {
      if (lifecycleSignal?.aborted) return;
      logger.error(`interaction_action_${safeErrorCode(error)}`);
      try {
        await sendText(user, undefined, businessFailureMessage(button, error));
      } catch {
        logger.error("interaction_fallback_send_failed");
      }
    }
  }

  return {
    handleDispatch(type, event) {
      if (type === "C2C_MESSAGE_CREATE") return handleC2C(event);
      if (type === "INTERACTION_CREATE") return handleInteraction(event);
      return Promise.resolve();
    },
    sendText,
    sendMarkdown,
    cachedBriefing,
  };
}
