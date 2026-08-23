const ROOT_CLASS = "qq-bridge-module";
const STATUS_STATES = new Set([
  "running",
  "connecting",
  "identified_or_ready",
  "reconnect_wait",
  "gateway_failed",
  "gateway_unavailable",
  "stopped",
  "ready",
  "starting",
  "missing_launcher",
  "missing_env",
  "missing_node",
  "missing_dependencies",
  "missing_module",
  "missing_package",
  "needs_configuration",
  "dependencies_missing",
  "unavailable",
  "start_failed",
  "failed",
]);

let mountedRoot = null;
let disposed = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function safeState(value) {
  const state = String(value || "failed");
  return STATUS_STATES.has(state) ? state : "failed";
}

function appendField(form, labelText, input) {
  const label = element("label", undefined, "field");
  label.append(element("span", labelText), input);
  form.append(label);
}

function timeInput(value) {
  const input = element("input");
  input.type = "time";
  input.required = true;
  input.value = /^\d{2}:\d{2}$/.test(String(value || "")) ? String(value) : "";
  return input;
}

function numberInput(value, min, max) {
  const input = element("input");
  input.type = "number";
  input.required = true;
  input.min = String(min);
  input.max = String(max);
  input.step = "1";
  input.value = String(Number.isInteger(value) ? value : min);
  return input;
}

function toggleInput(checked) {
  const input = element("input");
  input.type = "checkbox";
  input.checked = checked === true;
  return input;
}

function moduleAvailable(catalog, key) {
  const modules = Array.isArray(catalog?.modules) ? catalog.modules : [];
  const item = modules.find(module => module?.key === key || module?.module_id === key);
  return Boolean(item?.enabled);
}

function dependencySummary(catalog) {
  const labels = [
    ["conversation", "普通聊天"],
    ["daily_briefing", "每日情报"],
    ["demon_slayer", "斩妖除魔"],
    ["fitness", "健身打卡"],
    ["focus", "专注计时"],
    ["calendar", "日历与修炼"],
    ["voice", "语音回复"],
    ["life_forecast", "生活预报"],
  ];
  return labels.map(([key, label]) => `${label}：${moduleAvailable(catalog, key) ? "可用" : "未安装或未启用"}`);
}

async function loadJson(context, path) {
  return context.request(path, { method: "GET" });
}

function renderError(target, message) {
  target.replaceChildren(element("p", message, "module-error"));
}

function featurePanel(panelId, title, summary, avatar) {
  const panel = element("section", undefined, "section");
  const heading = element("h2", title);
  const hint = element("p", summary, "hint");
  const body = element("div", undefined, "module-feature-body");
  panel.dataset.panelId = panelId;
  panel.dataset.panelSummary = summary;
  panel.dataset.panelAvatar = `/dashboard/static/default-avatars/${avatar}`;
  panel.dataset.panelAvatarAlt = `${title}组件插图`;
  panel.append(heading, hint, body);
  return { panel, body };
}

function configurationGuide(status) {
  const box = element("div", undefined, "module-configuration-guide");
  const text = element("p");
  const link = element("a", "打开 QQ 开放平台配置机器人");
  link.href = "https://q.qq.com/";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  if (status?.env_configured) {
    text.textContent = status?.dependencies_ready
      ? "已检测到本机 QQ 配置和当前模块依赖，无需重新填写凭证。"
      : "已检测到既有本机 QQ 配置，无需重新填写；请在项目根目录运行 setup.bat --profile qq，为当前模块版本补齐依赖部署。";
  } else {
    text.textContent = "尚未检测到本机 QQ 配置。请先在 QQ 开放平台创建或选择机器人，再使用下方本机受控表单保存 AppID 和 Secret；Secret 不会回显。";
  }
  box.append(text, link);
  return box;
}

function credentialInput(type, autocomplete) {
  const input = element("input");
  input.type = type;
  input.autocomplete = autocomplete;
  input.maxLength = type === "password" ? 256 : 128;
  input.spellcheck = false;
  input.value = "";
  return input;
}

async function renderConfiguration(context, target, refreshStatus) {
  let configuration;
  try {
    configuration = await loadJson(context, "/api/v1/qq-control/configuration");
  } catch {
    renderError(target, "QQ 凭证配置状态暂不可用。");
    return;
  }
  if (disposed) return;
  const summary = element(
    "p",
    configuration?.configured
      ? `已配置（AppID：${String(configuration?.appid_masked || "已设置")}；Secret：已设置且不会回显）。`
      : "尚未完整配置 AppID 和 Secret。Secret 不会回显或保存在浏览器中。",
    "hint",
  );
  const form = element("form", undefined, "module-form");
  const appid = credentialInput("text", "off");
  const secret = credentialInput("password", "new-password");
  appid.placeholder = configuration?.appid_configured
    ? "留空以保留现有 AppID"
    : "输入 QQBOT_APPID";
  secret.placeholder = configuration?.secret_configured
    ? "留空以保留现有 Secret"
    : "输入 QQBOT_SECRET";
  appendField(form, "AppID", appid);
  appendField(form, "Secret", secret);
  const initialCapability = ["unknown", "available", "unavailable", "denied"].includes(
    configuration?.qq_media_upload_capability,
  ) ? configuration.qq_media_upload_capability : "unknown";
  let capabilityChanged = false;
  const capabilitySelect = element("select");
  for (const [value, label] of [
    ["unknown", "未知（默认，禁止语音）"],
    ["available", "已确认可上传语音"],
    ["unavailable", "当前不可用"],
    ["denied", "权限被拒绝"],
  ]) {
    const option = element("option", label);
    option.value = value;
    option.selected = value === initialCapability;
    capabilitySelect.append(option);
  }
  appendField(form, "QQ 语音上传能力", capabilitySelect);
  form.append(element(
    "p",
    "这是管理员对当前机器人权限的明确声明，不是自动验证；保存不会联网、上传或发送消息。",
    "hint",
  ));
  const initialVoice = configuration?.reply_with_voice === true;
  let voiceChanged = false;
  const voiceToggle = toggleInput(initialVoice);
  const voiceAvailable = configuration?.voice_reply_available === true;
  voiceToggle.disabled = !voiceAvailable && !initialVoice;
  voiceToggle.setAttribute("aria-describedby", "qq-voice-reply-status");
  voiceToggle.addEventListener("change", () => { voiceChanged = true; });
  capabilitySelect.addEventListener("change", () => {
    capabilityChanged = true;
    const declaredAvailable = capabilitySelect.value === "available";
    voiceToggle.disabled = !declaredAvailable || configuration?.voice_profile_ready !== true;
    if (!declaredAvailable) {
      voiceToggle.checked = false;
      voiceChanged = true;
    }
  });
  appendField(form, "QQ 回复同时发送语音", voiceToggle);
  const voiceState = String(configuration?.voice_reply_state || "voice unavailable");
  const voiceStatus = element(
    "p",
    voiceAvailable
      ? "语音可用：仅普通聊天在文字发送成功后附带一条语音。"
      : `语音不可用（${voiceState}）；文字回复不受影响。`,
    "hint",
  );
  voiceStatus.id = "qq-voice-reply-status";
  form.append(voiceStatus);
  const initialLifeForecast = configuration?.life_forecast_enabled === true;
  let lifeForecastChanged = false;
  const lifeForecastToggle = toggleInput(initialLifeForecast);
  lifeForecastToggle.addEventListener("change", () => {
    lifeForecastChanged = true;
  });
  appendField(form, "启用 QQ 生活预报查询", lifeForecastToggle);
  form.append(element(
    "p",
    "仅响应菜单按钮和四个完整关键词，只读取当天本机缓存；不会刷新天气或增加定时推送。",
    "hint",
  ));
  const submit = element(
    "button",
    configuration?.configured ? "保存或替换配置" : "保存配置",
  );
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    const payload = {};
    if (appid.value.trim()) payload.appid = appid.value.trim();
    if (secret.value.trim()) payload.secret = secret.value.trim();
    if (capabilityChanged) payload.qq_media_upload_capability = capabilitySelect.value;
    if (voiceChanged) payload.reply_with_voice = voiceToggle.checked;
    if (lifeForecastChanged) {
      payload.life_forecast_enabled = lifeForecastToggle.checked;
    }
    if (capabilityChanged && capabilitySelect.value !== "available") {
      payload.reply_with_voice = false;
    }
    try {
      const saved = await context.request("/api/v1/qq-control/configuration", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      appid.value = "";
      secret.value = "";
      context.notify(saved?.restart_required
        ? "QQ 配置已安全保存；若 bridge 正在运行，请先在本机关闭后再从此处启动。"
        : "QQ 配置已保存。");
      if (!disposed) {
        await Promise.all([
          renderConfiguration(context, target, refreshStatus),
          refreshStatus(),
        ]);
      }
    } catch {
      secret.value = "";
      context.notify("QQ 配置保存失败；原配置保持不变。");
    } finally {
      if (!disposed) submit.disabled = false;
    }
  });
  target.replaceChildren(summary, form);
}

async function renderStatus(context, target, startButton, stopButton) {
  try {
    const status = await loadJson(context, "/api/v1/qq-control/status");
    if (disposed) return;
    const state = safeState(status?.state);
    const processText = status?.process_running === true
      ? "Bridge 进程：运行中"
      : "Bridge 进程：未运行";
    const gatewayHints = Object.freeze({
      gateway_failed: "QQ Gateway 连接失败，将有限重试。",
      gateway_hello_timeout: "QQ Gateway Hello 超时，将有限重试。",
      gateway_request_failed: "QQ Gateway 地址请求失败，将有限重试。",
      gateway_rejected: "QQ Gateway 地址请求被拒绝，请检查 QQ 应用权限。",
      gateway_response_invalid: "QQ Gateway 地址响应格式无效。",
      gateway_ready_timeout: "QQ Gateway READY 超时，将有限重试。",
      gateway_url_invalid: "QQ Gateway 返回了无效地址。",
      gateway_url_missing: "QQ Gateway 响应缺少连接地址。",
      gateway_url_rejected: "QQ Gateway 地址不在固定白名单内。",
      heartbeat_send_failed: "QQ Gateway 心跳发送失败。",
      heartbeat_timeout: "QQ Gateway 心跳超时，将有限重试。",
      identify_send_failed: "QQ Gateway 身份确认发送失败。",
      invalid_session: "QQ Gateway 会话无效，将有限重试。",
      server_reconnect: "QQ Gateway 要求重新连接。",
      token_rejected: "QQ 访问凭据被拒绝，请检查应用配置。",
      token_request_failed: "QQ 访问凭据请求失败，将有限重试。",
      token_response_invalid: "QQ 访问凭据响应格式无效。",
      websocket_closed: "QQ Gateway WebSocket 在就绪前关闭。",
      websocket_constructor_failed: "QQ Gateway WebSocket 无法创建。",
      websocket_error: "QQ Gateway WebSocket 连接失败。",
    });
    const gatewayCode = String(status?.gateway_last_error_code || "");
    const gatewayText = status?.gateway_ready === true
      ? "QQ Gateway：已连接"
      : (gatewayHints[gatewayCode] || `QQ Gateway：${String(status?.gateway_state || "未连接")}`);
    const voiceCode = String(status?.voice_last_result_code || "");
    const voiceText = voiceCode
      ? `QQ 语音最近结果：${voiceCode}${status?.voice_message ? `（${String(status.voice_message)}）` : ""}`
      : "QQ 语音最近结果：尚无尝试记录";
    target.replaceChildren(
      element("strong", `状态：${state}`),
      element("span", String(status?.message || "QQ bridge 状态暂不可用。")),
      element("span", processText),
      element("span", gatewayText),
      element("span", voiceText),
      configurationGuide(status),
    );
    startButton.disabled = !["ready"].includes(state);
    stopButton.disabled = status?.process_running !== true || status?.can_stop !== true;
    stopButton.title = status?.process_running === true && status?.can_stop !== true
      ? "该进程不是由当前控制台启动，不能从这里关闭。"
      : "";
  } catch {
    if (!disposed) {
      renderError(target, "QQ bridge 状态暂不可用。");
      startButton.disabled = true;
      stopButton.disabled = true;
    }
  }
}

async function renderDailySchedule(context, target) {
  let schedule;
  try {
    schedule = await loadJson(context, "/api/v1/qq-control/schedules/daily-briefing");
  } catch {
    renderError(target, "每日情报日程暂不可用。");
    return;
  }
  if (disposed) return;
  const form = element("form", undefined, "module-form");
  const enabled = toggleInput(schedule?.enabled);
  const prebuild = timeInput(schedule?.prebuild_time);
  const send = timeInput(schedule?.send_time);
  appendField(form, "启用每日推送", enabled);
  appendField(form, "预生成时间", prebuild);
  appendField(form, "发送时间", send);
  const submit = element("button", "保存每日情报日程");
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      await context.request("/api/v1/qq-control/schedules/daily-briefing", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: enabled.checked,
          prebuild_time: prebuild.value,
          send_time: send.value,
        }),
      });
      context.notify("每日情报日程已保存。");
    } catch {
      context.notify("每日情报日程保存失败。");
    } finally {
      if (!disposed) submit.disabled = false;
    }
  });
  target.replaceChildren(form);
}

async function renderLifeSchedule(context, target) {
  let schedule;
  try {
    schedule = await loadJson(context, "/api/v1/qq-control/schedules/life-support");
  } catch {
    renderError(target, "生命维持日程暂不可用。");
    return;
  }
  if (disposed) return;
  const form = element("form", undefined, "module-form");
  const enabled = toggleInput(schedule?.enabled);
  const start = timeInput(schedule?.start_time);
  const end = timeInput(schedule?.end_time);
  const hours = numberInput(schedule?.interval_hours, 0, 24);
  const minutes = numberInput(schedule?.interval_minutes, 0, 59);
  appendField(form, "启用生命维持提醒", enabled);
  appendField(form, "开始时间", start);
  appendField(form, "结束时间", end);
  appendField(form, "间隔小时", hours);
  appendField(form, "间隔分钟", minutes);
  const submit = element("button", "保存生命维持日程");
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      await context.request("/api/v1/qq-control/schedules/life-support", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: enabled.checked,
          start_time: start.value,
          end_time: end.value,
          interval_hours: Number.parseInt(hours.value, 10),
          interval_minutes: Number.parseInt(minutes.value, 10),
        }),
      });
      context.notify("生命维持日程已保存。");
    } catch {
      context.notify("生命维持日程保存失败。");
    } finally {
      if (!disposed) submit.disabled = false;
    }
  });
  target.replaceChildren(form);
}

export async function mount(context) {
  if (!context?.root || typeof context.request !== "function" || typeof context.notify !== "function") {
    throw new TypeError("QQ bridge 面板缺少受限挂载上下文");
  }
  disposed = false;
  mountedRoot = context.root;
  const root = element("div", undefined, `${ROOT_CLASS} module-owned-panels`);
  const status = element("div", "正在读取非秘密状态……", "module-status");
  const startButton = element("button", "启动 QQ Bridge");
  startButton.type = "button";
  startButton.disabled = true;
  startButton.addEventListener("click", async () => {
    startButton.disabled = true;
    try {
      await context.request("/api/v1/qq-control/start", { method: "POST" });
      context.notify("QQ Bridge 启动请求已提交。");
    } catch {
      context.notify("QQ Bridge 未能启动，请检查本机配置与依赖。");
    }
    if (!disposed) await renderStatus(context, status, startButton, stopButton);
  });
  const stopButton = element("button", "关闭 QQ Bridge");
  stopButton.type = "button";
  stopButton.disabled = true;
  stopButton.addEventListener("click", async () => {
    if (typeof globalThis.confirm !== "function" || !globalThis.confirm("确认关闭由当前控制台启动的 QQ Bridge？")) return;
    stopButton.disabled = true;
    try {
      await context.request("/api/v1/qq-control/stop", { method: "POST" });
      context.notify("QQ Bridge 已安全关闭。");
    } catch {
      context.notify("QQ Bridge 未能关闭；外部启动的实例不会被强制终止。");
    }
    if (!disposed) await renderStatus(context, status, startButton, stopButton);
  });

  const dependencyList = element("ul", undefined, "module-dependencies");
  for (const line of dependencySummary(context.catalog)) {
    dependencyList.append(element("li", line));
  }

  const launch = featurePanel(
    "module-qq_bridge",
    "QQ 功能启动",
    "只在明确点击后请求启动；不会自动安装依赖、读取凭证或创建第二个 bridge。",
    "qq-launch.png",
  );
  launch.panel.dataset.panelSettings = "QQ 凭证只由本机受控表单原子保存，Secret 永不回显|Node 依赖只由 setup.bat --profile qq 安装";
  const configuration = element("div", "正在读取配置状态……", "module-configuration");
  const refreshStatus = () => renderStatus(context, status, startButton, stopButton);
  launch.body.append(
    status,
    startButton,
    stopButton,
    element("h3", "QQ 开放平台与凭证"),
    configuration,
    element("h3", "菜单依赖"),
    dependencyList,
  );
  const daily = featurePanel(
    "module-qq-daily-push",
    "每日情报定时推送",
    "分别设置预生成与 QQ 发送时间；保存设置不会立即生成或发送。",
    "briefing-schedule.png",
  );
  daily.body.textContent = "正在读取……";
  const life = featurePanel(
    "module-qq-life-support",
    "生命维持系统",
    "设置提醒时段与间隔；需要 Core 和 QQ bridge 持续运行。",
    "life-support.png",
  );
  life.body.textContent = "正在读取……";

  root.append(
    launch.panel,
    daily.panel,
    life.panel,
  );
  context.root.replaceChildren(root);
  await Promise.all([
    refreshStatus(),
    renderConfiguration(context, configuration, refreshStatus),
    renderDailySchedule(context, daily.body),
    renderLifeSchedule(context, life.body),
  ]);
}

export function unmount() {
  disposed = true;
  if (mountedRoot) mountedRoot.replaceChildren();
  mountedRoot = null;
}
