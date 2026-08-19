const MAX_GOALS_SHOWN = 4;
const MAX_ITEMS_SHOWN = 5;
const MAX_GOAL_ID = 64;
const MAX_TITLE = 80;
const MAX_SKILL = 40;
const MAX_PRACTICE_HOURS = 24;
const GOAL_CACHE_TTL_MS = 10 * 60 * 1000;
const GOAL_CACHE_USERS = 200;
const PENDING_GOAL_TTL_MS = 10 * 60 * 1000;
const PENDING_GOAL_USERS = 200;
const STREAK_UNIT_LABELS = Object.freeze({
  day: "天",
  week: "周",
  month: "月",
  year: "年",
});
const GOAL_CADENCE_LABELS = Object.freeze({
  daily: "日",
  weekly: "周",
  monthly: "月",
  yearly: "年",
});

export const BUSINESS_API_OPERATIONS = Object.freeze({
  demonStatus: Object.freeze({ method: "GET", path: "/api/v1/demon-slayer/status" }),
  demonCreateGoal: Object.freeze({ method: "POST", path: "/api/v1/demon-slayer/goals" }),
  demonCheckin: Object.freeze({ method: "POST", path: "/api/v1/demon-slayer/checkins" }),
  demonDailyReview: Object.freeze({ method: "GET", path: "/api/v1/demon-slayer/reviews/daily" }),
  fitnessStatus: Object.freeze({ method: "GET", path: "/api/v1/fitness/status" }),
  fitnessCheckin: Object.freeze({ method: "POST", path: "/api/v1/fitness/checkins" }),
  focusStatus: Object.freeze({ method: "GET", path: "/api/v1/focus/status" }),
  focusStart: Object.freeze({ method: "POST", path: "/api/v1/focus/start" }),
  focusStop: Object.freeze({ method: "POST", path: "/api/v1/focus/stop" }),
  calendarToday: Object.freeze({ method: "GET", path: "/api/v1/calendar/today" }),
  calendarStatus: Object.freeze({ method: "GET", path: "/api/v1/calendar/status" }),
  calendarEvent: Object.freeze({ method: "POST", path: "/api/v1/calendar/events" }),
  calendarPractice: Object.freeze({ method: "POST", path: "/api/v1/calendar/practice" }),
});

export const BUSINESS_ACTIONS = Object.freeze({
  main: "kei:menu:main",
  demonMenu: "kei:menu:demon",
  demonToday: "kei:demon:today",
  demonAdd: "kei:demon:add",
  demonAddDaily: "kei:demon:add:daily",
  demonAddWeekly: "kei:demon:add:weekly",
  demonAddMonthly: "kei:demon:add:monthly",
  demonAddYearly: "kei:demon:add:yearly",
  demonReview: "kei:demon:review",
  fitnessMenu: "kei:menu:fitness",
  fitnessStatus: "kei:fitness:status",
  fitnessConfirm: "kei:fitness:confirm",
  focusMenu: "kei:menu:focus",
  focusStatus: "kei:focus:status",
  focusStart: "kei:focus:start25",
  focusStartEncouragement: "kei:focus:start25:encourage10",
  focusStop: "kei:focus:stop",
  calendarMenu: "kei:menu:calendar",
  calendarToday: "kei:calendar:today",
  calendarPractice: "kei:calendar:practice",
});

const STATIC_ACTIONS = new Set(Object.values(BUSINESS_ACTIONS));
const GOAL_ACTION = /^kei:demon:goal:(done|missed):([A-Za-z0-9_-]{1,64})$/;
const PENDING_GOAL_ACTION = /^kei:demon:add:(confirm|cancel):([A-Za-z0-9_-]{1,64})$/;

function safeVisible(value, maxLength = 160) {
  const text = String(value ?? "")
    .replace(/\b(authorization|cookie|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+/gi, "$1=[redacted]")
    .replace(/\bbearer\s+[a-z0-9._~+\/-]+/gi, "Bearer [redacted]")
    .replace(/[A-Za-z]:\\[^\s]+/g, "[internal-path]")
    .replace(/\/(?:home|Users|var|tmp)\/[^\s]+/g, "[internal-path]")
    .replace(/\s+/g, " ")
    .trim();
  return text.length > maxLength ? `${text.slice(0, Math.max(0, maxLength - 1))}…` : text;
}

function safeMultiline(value, maxLength = 4000) {
  const text = String(value ?? "")
    .replace(/\b(authorization|cookie|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+/gi, "$1=[redacted]")
    .replace(/\bbearer\s+[a-z0-9._~+\/-]+/gi, "Bearer [redacted]")
    .replace(/[A-Za-z]:\\[^\s]+/g, "[internal-path]")
    .replace(/\/(?:home|Users|var|tmp)\/[^\s]+/g, "[internal-path]")
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map(line => line.replace(/[^\S\n]+/g, " ").trim())
    .join("\n")
    .trim();
  return text.length > maxLength ? `${text.slice(0, Math.max(0, maxLength - 1))}…` : text;
}

function escapeMarkdown(value, maxLength = 160) {
  return safeVisible(value, maxLength).replace(/[\\`*_{}[\]()#+!|>]/g, "\\$&");
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function displayNumber(value) {
  return finiteNumber(value).toFixed(2).replace(/\.?0+$/, "");
}

function integer(value, fallback = 0) {
  return Math.trunc(finiteNumber(value, fallback));
}

function nonNegativeIntegerOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? Math.trunc(number) : null;
}

function button(id, label, action, style = 0) {
  return {
    id,
    render_data: {
      label: safeVisible(label, 30),
      visited_label: safeVisible(label, 30),
      style,
    },
    action: {
      type: 1,
      data: action,
      permission: { type: 2 },
      click_limit: 1,
    },
  };
}

function card(markdown, rows) {
  return {
    kind: "card",
    markdown: safeMultiline(markdown, 1200),
    rows: rows.slice(0, 5).map(row => ({ buttons: row.slice(0, 5) })),
  };
}

function text(markdown) {
  return { kind: "text", markdown: safeMultiline(markdown, 4000) };
}

export function mainMenuCard() {
  return card("老师，需要我做什么？", [
    [
      button("kei-briefing", "每日情报", "kei:daily-briefing", 1),
      button("kei-demon-menu", "斩妖除魔", BUSINESS_ACTIONS.demonMenu),
    ],
    [
      button("kei-fitness-menu", "健身打卡", BUSINESS_ACTIONS.fitnessMenu),
      button("kei-focus-menu", "专注计时", BUSINESS_ACTIONS.focusMenu),
    ],
    [button("kei-calendar-menu", "日历与修炼", BUSINESS_ACTIONS.calendarMenu)],
  ]);
}

function demonMenuCard() {
  return card("斩妖除魔\n可查看、添加常驻目标，再对明确目标打卡；复盘需要单独点击。", [
    [
      button("kei-demon-today", "查看今日目标", BUSINESS_ACTIONS.demonToday, 1),
      button("kei-demon-add", "添加常驻目标", BUSINESS_ACTIONS.demonAdd),
    ],
    [
      button("kei-demon-review", "生成今日复盘", BUSINESS_ACTIONS.demonReview),
    ],
    [button("kei-demon-back", "返回主菜单", BUSINESS_ACTIONS.main)],
  ]);
}

function demonAddMenuCard() {
  return card("添加斩妖常驻目标\n请选择目标周期。点击后 Kei 会告诉你固定的标题输入格式。", [
    [
      button("kei-demon-add-daily", "添加日任务", BUSINESS_ACTIONS.demonAddDaily, 1),
      button("kei-demon-add-weekly", "添加周任务", BUSINESS_ACTIONS.demonAddWeekly),
    ],
    [
      button("kei-demon-add-monthly", "添加月任务", BUSINESS_ACTIONS.demonAddMonthly),
      button("kei-demon-add-yearly", "添加年任务", BUSINESS_ACTIONS.demonAddYearly),
    ],
    [button("kei-demon-add-back", "返回斩妖菜单", BUSINESS_ACTIONS.demonMenu)],
  ]);
}

function demonAddInstructionCard(cadence) {
  const label = GOAL_CADENCE_LABELS[cadence];
  return card(
    `添加${label}常驻目标\n请发送：添加${label}任务 目标名称\n例如：添加${label}任务 读一篇论文\n发送后仍需点击“确认添加”，不会直接写入。`,
    [
      [button("kei-demon-add-choose", "选择其他周期", BUSINESS_ACTIONS.demonAdd)],
      [button("kei-demon-add-instruction-back", "返回斩妖菜单", BUSINESS_ACTIONS.demonMenu)],
    ],
  );
}

function demonAddConfirmationCard(pending) {
  const label = GOAL_CADENCE_LABELS[pending.cadence];
  return card(
    `确认添加${label}常驻目标？\n目标：${escapeMarkdown(pending.title, MAX_TITLE)}\n妖怪种类由 PK-150 自动判断。`,
    [[
      button("kei-demon-add-confirm", "确认添加", `kei:demon:add:confirm:${pending.id}`, 1),
      button("kei-demon-add-cancel", "取消", `kei:demon:add:cancel:${pending.id}`),
    ]],
  );
}

function fitnessMenuCard() {
  return card("健身打卡\n查看状态不会写入；只有“确认今日健身打卡”会打卡。", [
    [button("kei-fitness-status", "查看今日状态", BUSINESS_ACTIONS.fitnessStatus, 1)],
    [button("kei-fitness-confirm", "确认今日健身打卡", BUSINESS_ACTIONS.fitnessConfirm)],
    [button("kei-fitness-back", "返回主菜单", BUSINESS_ACTIONS.main)],
  ]);
}

function focusMenuCard() {
  return card("专注计时\n普通启动不会调用模型；鼓励需要明确选择。也可发送：专注 25 鼓励 10", [
    [button("kei-focus-status", "查看当前状态", BUSINESS_ACTIONS.focusStatus, 1)],
    [
      button("kei-focus-start", "开始 25 分钟专注", BUSINESS_ACTIONS.focusStart),
      button("kei-focus-start-encourage", "25 分钟，10 分钟后鼓励", BUSINESS_ACTIONS.focusStartEncouragement),
    ],
    [
      button("kei-focus-stop", "停止当前专注", BUSINESS_ACTIONS.focusStop),
    ],
    [button("kei-focus-back", "返回主菜单", BUSINESS_ACTIONS.main)],
  ]);
}

function calendarMenuCard() {
  return card(
    "日历与修炼\n查看不会写入。新增只接受严格单消息命令：\n添加备忘 YYYY-MM-DD 标题\n记录修炼 技能 小时数",
    [
      [
        button("kei-calendar-today", "查看今日备忘", BUSINESS_ACTIONS.calendarToday, 1),
        button("kei-calendar-practice", "查看修炼进度", BUSINESS_ACTIONS.calendarPractice, 1),
      ],
      [button("kei-calendar-back", "返回主菜单", BUSINESS_ACTIONS.main)],
    ],
  );
}

function validGoalId(value) {
  const id = String(value ?? "");
  return id.length <= MAX_GOAL_ID && /^[A-Za-z0-9_-]+$/.test(id);
}

function formatDemonStatus(body) {
  const source = Array.isArray(body?.goals) ? body.goals : [];
  const goals = [];
  for (const goal of source) {
    if (!goal || typeof goal !== "object" || !validGoalId(goal.id)) continue;
    const title = safeVisible(goal.title, MAX_TITLE);
    if (!title) continue;
    goals.push({ id: String(goal.id), title, completed: goal.completed === true });
    if (goals.length >= MAX_GOALS_SHOWN) break;
  }
  const lines = [
    `今日目标 · ${escapeMarkdown(body?.date, 24) || "本机今日"}`,
    `积分：${integer(body?.points)}`,
  ];
  if (!goals.length) lines.push("今天没有可在 QQ 中打卡的目标。");
  for (const [index, goal] of goals.entries()) {
    lines.push(`${index + 1}. ${goal.completed ? "已完成" : "待完成"} · ${escapeMarkdown(goal.title, MAX_TITLE)}`);
  }
  if (source.length > goals.length) lines.push(`仅展示前 ${MAX_GOALS_SHOWN} 项；更多目标请在 Project Kei 中查看。`);
  const rows = goals.map((goal, index) => [
    button(`kei-demon-done-${index}`, `完成：${goal.title}`, `kei:demon:goal:done:${goal.id}`, 1),
    button(`kei-demon-missed-${index}`, `未完成：${goal.title}`, `kei:demon:goal:missed:${goal.id}`),
  ]);
  rows.push([button("kei-demon-status-back", "返回斩妖菜单", BUSINESS_ACTIONS.demonMenu)]);
  return { response: card(lines.join("\n"), rows), goals };
}

function formatDemonCheckin(body, goal, done) {
  const duplicate = body?.duplicate === true;
  const awarded = integer(body?.points_awarded);
  const total = integer(body?.total_points);
  const activeDays = nonNegativeIntegerOrNull(body?.active_days);
  const currentStreak = nonNegativeIntegerOrNull(body?.current_streak) ?? 0;
  const longestStreak = nonNegativeIntegerOrNull(body?.longest_streak) ?? 0;
  const unit = STREAK_UNIT_LABELS[String(body?.streak_unit || "")] || "周期";
  const activeLine = body?.repeat_mode === "once"
    ? "启用时长：临时目标不累计"
    : `启用时长：${activeDays === null ? "未知" : `${activeDays} 天`}`;
  const encouragement = safeVisible(body?.encouragement, 320);
  const lines = [
    `${done ? "已记录完成" : "已记录未完成"}：${escapeMarkdown(goal.title, MAX_TITLE)}`
    + `\n${duplicate ? "本周期已有记录，没有重复处理。" : `本次积分：${awarded}`}`,
    `当前总积分：${total}`,
    activeLine,
    `当前连续：${currentStreak} ${unit}`,
    `历史最长：${longestStreak} ${unit}`,
  ];
  if (encouragement) lines.push(encouragement);
  return text(lines.join("\n"));
}

function formatDemonReview(body) {
  const completed = Math.max(0, integer(body?.completed));
  const total = Math.max(0, integer(body?.total));
  const points = integer(body?.points_earned);
  const missed = Array.isArray(body?.missed)
    ? body.missed.slice(0, MAX_ITEMS_SHOWN).map(item => escapeMarkdown(item, MAX_TITLE)).filter(Boolean)
    : [];
  const lines = [`今日复盘：完成 ${completed}/${total}`, `本期积分：${points}`];
  if (missed.length) lines.push(`待改进：${missed.join("、")}`);
  if (Array.isArray(body?.missed) && body.missed.length > missed.length) lines.push("仅展示部分未完成目标。");
  return text(lines.join("\n"));
}

function formatFitnessStatus(body) {
  return text(
    `今日健身：${body?.checked_today === true ? "已打卡" : "未打卡"}`
    + `\n连续天数：${Math.max(0, integer(body?.streak))}`
    + `\n累计打卡：${Math.max(0, integer(body?.total_checkins))}`,
  );
}

function formatFitnessCheckin(body) {
  return text(
    `${body?.already_checked_in === true ? "今天已经打过卡，没有重复记录。" : "今日健身打卡成功。"}`
    + `\n连续天数：${Math.max(0, integer(body?.streak))}`
    + `\n累计打卡：${Math.max(0, integer(body?.total_checkins))}`,
  );
}

function formatFocus(body, suffix = "") {
  const active = body?.active === true;
  const remaining = Math.max(0, integer(body?.remaining_seconds));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return text(
    `专注状态：${active ? "进行中" : safeVisible(body?.status, 20) || "空闲"}`
    + (active ? `\n剩余：${minutes} 分 ${seconds} 秒` : "")
    + (suffix ? `\n${safeVisible(suffix, 120)}` : ""),
  );
}

function parseFocusCommand(content) {
  const raw = String(content ?? "").trim();
  if (!raw.startsWith("专注")) return { handled: false };
  if (raw === "专注计时") return { handled: false };
  const match = /^专注\s+(\d{1,3})\s+鼓励\s+(\d{1,3})$/.exec(raw);
  if (!match) return { handled: true, usage: "用法：专注 分钟数 鼓励 分钟数（例如：专注 25 鼓励 10）" };
  const durationMinutes = Number(match[1]);
  const encouragementAfterMinutes = Number(match[2]);
  if (
    !Number.isInteger(durationMinutes)
    || durationMinutes < 2
    || durationMinutes > 240
    || !Number.isInteger(encouragementAfterMinutes)
    || encouragementAfterMinutes < 1
    || encouragementAfterMinutes >= durationMinutes
  ) {
    return {
      handled: true,
      usage: "用法：专注时长须为 2-240 分钟，鼓励时间须大于 0 且早于专注结束。",
    };
  }
  return { handled: true, durationMinutes, encouragementAfterMinutes };
}

function formatCalendarToday(body) {
  const events = Array.isArray(body?.today_events) ? body.today_events : [];
  const shown = events.slice(0, MAX_ITEMS_SHOWN);
  const lines = [`今日备忘 · ${escapeMarkdown(body?.date, 24) || "本机今日"}`];
  if (!shown.length) lines.push("今天没有备忘。");
  shown.forEach((event, index) => lines.push(`${index + 1}. ${escapeMarkdown(event?.title, MAX_TITLE) || "未命名备忘"}`));
  if (events.length > shown.length) lines.push(`仅展示前 ${MAX_ITEMS_SHOWN} 项。`);
  return text(lines.join("\n"));
}

function formatPracticeStatus(body) {
  const skills = Array.isArray(body?.skills) ? body.skills : [];
  const shown = skills.slice(0, MAX_ITEMS_SHOWN);
  const lines = ["修炼进度"];
  if (!shown.length) lines.push("还没有修炼记录。");
  shown.forEach((skill, index) => {
    const name = escapeMarkdown(skill?.name, MAX_SKILL) || "未命名技能";
    const hours = Math.max(0, finiteNumber(skill?.total_hours)).toFixed(2).replace(/\.?0+$/, "");
    const level = escapeMarkdown(skill?.level?.name, 40);
    lines.push(`${index + 1}. ${name} · ${hours} 小时${level ? ` · ${level}` : ""}`);
  });
  if (skills.length > shown.length) lines.push(`仅展示前 ${MAX_ITEMS_SHOWN} 项。`);
  return text(lines.join("\n"));
}

function parseCalendarCommand(content) {
  const raw = String(content ?? "").trim();
  if (raw.startsWith("添加备忘")) {
    const match = /^添加备忘\s+(\d{4}-\d{2}-\d{2})\s+(.+)$/.exec(raw);
    if (!match) return { handled: true, usage: "用法：添加备忘 YYYY-MM-DD 标题" };
    const [, day, rawTitle] = match;
    const title = rawTitle.trim();
    if (!isValidDay(day) || !title || title.length > MAX_TITLE || /[\r\n]/.test(title)) {
      return { handled: true, usage: `用法：添加备忘 YYYY-MM-DD 标题（标题 1-${MAX_TITLE} 字）` };
    }
    return {
      handled: true,
      operation: "calendarEvent",
      payload: { title, date: day, repeat: "none", note: "", tags: [] },
      success: body => text(`已添加备忘：${escapeMarkdown(body?.event?.title || title, MAX_TITLE)}\n日期：${day}`),
    };
  }
  if (raw.startsWith("记录修炼")) {
    const match = /^记录修炼\s+(\S+)\s+([0-9]+(?:\.[0-9]{1,2})?)$/.exec(raw);
    if (!match) return { handled: true, usage: "用法：记录修炼 技能 小时数" };
    const [, skill, hoursText] = match;
    const hours = Number(hoursText);
    if (!skill || skill.length > MAX_SKILL || !Number.isFinite(hours) || hours <= 0 || hours > MAX_PRACTICE_HOURS) {
      return { handled: true, usage: `用法：记录修炼 技能 小时数（技能 1-${MAX_SKILL} 字，小时数大于 0 且不超过 ${MAX_PRACTICE_HOURS}）` };
    }
    return {
      handled: true,
      operation: "calendarPractice",
      payload: { skill, hours, date: null, note: "" },
      success: body => {
        const total = Math.max(0, finiteNumber(body?.skill?.total_hours, hours));
        return text(`已记录修炼：${escapeMarkdown(skill, MAX_SKILL)} ${displayNumber(hours)} 小时\n累计：${displayNumber(total)} 小时`);
      },
    };
  }
  return { handled: false };
}

function parseDemonAddCommand(content) {
  const raw = String(content ?? "").trim();
  const exactMenus = new Set([
    "添加斩妖任务",
    "添加斩妖目标",
    "添加日任务",
    "添加周任务",
    "添加月任务",
    "添加年任务",
    "添加日目标",
    "添加周目标",
    "添加月目标",
    "添加年目标",
  ]);
  if (exactMenus.has(raw)) return { handled: true, menu: true };
  if (!/^添加[日周月年](?:任务|目标)/.test(raw)) return { handled: false };
  const match = /^添加(日|周|月|年)(?:任务|目标)\s+(.+)$/.exec(raw);
  if (!match) {
    return {
      handled: true,
      usage: `用法：添加日任务 目标名称（目标名称 1-${MAX_TITLE} 字）`,
    };
  }
  const cadence = {
    日: "daily",
    周: "weekly",
    月: "monthly",
    年: "yearly",
  }[match[1]];
  const title = match[2].trim();
  if (!title || title.length > MAX_TITLE || /[\r\n]/.test(title)) {
    return {
      handled: true,
      usage: `用法：添加${match[1]}任务 目标名称（目标名称 1-${MAX_TITLE} 字）`,
    };
  }
  return { handled: true, cadence, title };
}

function isValidDay(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

export function businessFailureMessage(action, error) {
  const code = String(error?.code || error?.name || "");
  if (error?.name === "AbortError" || code === "AbortError" || code === "timeout") return "本地功能响应超时，请稍后重试。";
  if (code === "http_404" && String(action).startsWith("kei:focus:")) {
    return "专注计时模块未安装、未启用或路由不可用。QQ 不会自动安装、启用或重启模块。";
  }
  if (code === "http_404") return "该功能当前不可用，请稍后在本机检查。";
  if (code === "http_422") return "请求未被接受，状态可能已经变化。请重新查看后再操作。";
  return "该功能暂时不可用，请稍后再试。";
}

export function createBusinessMenuController({
  callApi,
  onFocusStarted = async () => {},
  onFocusStopped = async () => {},
  now = () => Date.now(),
} = {}) {
  if (typeof callApi !== "function") throw new TypeError("callApi is required");
  const goalViews = new Map();
  const pendingGoals = new Map();
  let pendingGoalSequence = 0;

  async function startFocus(user, minutes, encouragementAfterMinutes = null) {
    const body = await callApi("focusStart", {
      mode: "pomodoro",
      minutes,
      task: "",
      force: false,
      with_audio: false,
    });
    if (body?.started === true) {
      await onFocusStarted({
        userOpenId: user,
        sessionId: String(body?.session_id || ""),
        startAt: String(body?.start_at || ""),
        durationMinutes: minutes,
        encouragementAfterMinutes,
      });
    }
    const suffix = encouragementAfterMinutes !== null && body?.started === true
      ? `已登记：开始 ${encouragementAfterMinutes} 分钟后发送一次鼓励。`
      : "";
    return formatFocus(body, suffix);
  }

  function rememberGoals(user, goals) {
    goalViews.delete(user);
    goalViews.set(user, {
      expiresAt: now() + GOAL_CACHE_TTL_MS,
      goals: new Map(goals.map(goal => [goal.id, goal])),
    });
    while (goalViews.size > GOAL_CACHE_USERS) goalViews.delete(goalViews.keys().next().value);
  }

  function goalFor(user, goalId) {
    const view = goalViews.get(user);
    if (!view || now() > view.expiresAt) {
      goalViews.delete(user);
      return null;
    }
    return view.goals.get(goalId) || null;
  }

  function rememberPendingGoal(user, cadence, title) {
    pendingGoalSequence = (pendingGoalSequence + 1) % Number.MAX_SAFE_INTEGER;
    const id = `${Math.max(0, Math.trunc(now())).toString(36)}-${pendingGoalSequence.toString(36)}`;
    const pending = {
      id,
      cadence,
      title,
      expiresAt: now() + PENDING_GOAL_TTL_MS,
    };
    pendingGoals.delete(user);
    pendingGoals.set(user, pending);
    while (pendingGoals.size > PENDING_GOAL_USERS) pendingGoals.delete(pendingGoals.keys().next().value);
    return pending;
  }

  function takePendingGoal(user, id) {
    const pending = pendingGoals.get(user);
    if (!pending || pending.id !== id || now() > pending.expiresAt) {
      if (pending && (pending.id === id || now() > pending.expiresAt)) pendingGoals.delete(user);
      return null;
    }
    pendingGoals.delete(user);
    return pending;
  }

  const dispatch = new Map([
    [BUSINESS_ACTIONS.main, async () => mainMenuCard()],
    [BUSINESS_ACTIONS.demonMenu, async () => demonMenuCard()],
    [BUSINESS_ACTIONS.demonAdd, async () => demonAddMenuCard()],
    [BUSINESS_ACTIONS.demonAddDaily, async () => demonAddInstructionCard("daily")],
    [BUSINESS_ACTIONS.demonAddWeekly, async () => demonAddInstructionCard("weekly")],
    [BUSINESS_ACTIONS.demonAddMonthly, async () => demonAddInstructionCard("monthly")],
    [BUSINESS_ACTIONS.demonAddYearly, async () => demonAddInstructionCard("yearly")],
    [BUSINESS_ACTIONS.demonToday, async ({ user }) => {
      const formatted = formatDemonStatus(await callApi("demonStatus"));
      rememberGoals(user, formatted.goals);
      return formatted.response;
    }],
    [BUSINESS_ACTIONS.demonReview, async () => formatDemonReview(await callApi("demonDailyReview"))],
    [BUSINESS_ACTIONS.fitnessMenu, async () => fitnessMenuCard()],
    [BUSINESS_ACTIONS.fitnessStatus, async () => formatFitnessStatus(await callApi("fitnessStatus"))],
    [BUSINESS_ACTIONS.fitnessConfirm, async () => formatFitnessCheckin(await callApi("fitnessCheckin", { note: "" }))],
    [BUSINESS_ACTIONS.focusMenu, async () => focusMenuCard()],
    [BUSINESS_ACTIONS.focusStatus, async () => formatFocus(await callApi("focusStatus"))],
    [BUSINESS_ACTIONS.focusStart, async ({ user }) => startFocus(user, 25)],
    [BUSINESS_ACTIONS.focusStartEncouragement, async ({ user }) => startFocus(user, 25, 10)],
    [BUSINESS_ACTIONS.focusStop, async ({ user }) => {
      const body = await callApi("focusStop");
      await onFocusStopped(user);
      return formatFocus(body);
    }],
    [BUSINESS_ACTIONS.calendarMenu, async () => calendarMenuCard()],
    [BUSINESS_ACTIONS.calendarToday, async () => formatCalendarToday(await callApi("calendarToday"))],
    [BUSINESS_ACTIONS.calendarPractice, async () => formatPracticeStatus(await callApi("calendarStatus"))],
  ]);

  function recognizesAction(action) {
    const value = String(action ?? "");
    return STATIC_ACTIONS.has(value) || GOAL_ACTION.test(value) || PENDING_GOAL_ACTION.test(value);
  }

  async function handleAction(action, context) {
    const value = String(action ?? "");
    const staticHandler = dispatch.get(value);
    if (staticHandler) return staticHandler(context);
    const pendingMatch = PENDING_GOAL_ACTION.exec(value);
    if (pendingMatch) {
      const pending = takePendingGoal(context.user, pendingMatch[2]);
      if (!pending) return text("添加操作已过期、已处理或不属于当前用户。请重新发送添加任务命令。");
      if (pendingMatch[1] === "cancel") return text("已取消添加目标，没有写入任何斩妖状态。");
      const body = await callApi("demonCreateGoal", {
        title: pending.title,
        cadence: pending.cadence,
        category: "auto",
        repeat_mode: "recurring",
        target_date: null,
      });
      const goal = body?.goal && typeof body.goal === "object" ? body.goal : {};
      const label = GOAL_CADENCE_LABELS[pending.cadence];
      return text(
        `已添加${label}常驻目标：${escapeMarkdown(goal.title || pending.title, MAX_TITLE)}`
        + `\n妖怪：${escapeMarkdown(goal.rank || goal.demon, 40) || "已由 PK-150 判定"}`,
      );
    }
    const match = GOAL_ACTION.exec(value);
    if (!match) return null;
    const goal = goalFor(context.user, match[2]);
    if (!goal) return text("目标操作已过期或无效。请重新查看今日目标后再打卡。");
    const done = match[1] === "done";
    return formatDemonCheckin(
      await callApi("demonCheckin", {
        goal_id: goal.id,
        done,
        note: "",
        with_encouragement: done,
      }),
      goal,
      done,
    );
  }

  async function handleText(content, context = {}) {
    const normalized = String(content ?? "").trim().replace(/\s+/g, "");
    const menus = new Map([
      ["斩妖除魔", demonMenuCard],
      ["健身打卡", fitnessMenuCard],
      ["专注计时", focusMenuCard],
      ["日历与修炼", calendarMenuCard],
    ]);
    const menu = menus.get(normalized);
    if (menu) return { handled: true, response: menu() };
    const demonAddCommand = parseDemonAddCommand(content);
    if (demonAddCommand.handled) {
      if (demonAddCommand.menu) return { handled: true, response: demonAddMenuCard() };
      if (demonAddCommand.usage) return { handled: true, response: text(demonAddCommand.usage) };
      const pending = rememberPendingGoal(context.user, demonAddCommand.cadence, demonAddCommand.title);
      return { handled: true, response: demonAddConfirmationCard(pending) };
    }
    const focusCommand = parseFocusCommand(content);
    if (focusCommand.handled) {
      if (focusCommand.usage) return { handled: true, response: text(focusCommand.usage) };
      return {
        handled: true,
        response: await startFocus(
          context.user,
          focusCommand.durationMinutes,
          focusCommand.encouragementAfterMinutes,
        ),
      };
    }
    const command = parseCalendarCommand(content);
    if (!command.handled) return { handled: false };
    if (command.usage) return { handled: true, response: text(command.usage) };
    const body = await callApi(command.operation, command.payload);
    return { handled: true, response: command.success(body) };
  }

  return {
    recognizesAction,
    handleAction,
    handleText,
  };
}
