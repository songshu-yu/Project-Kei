import assert from "node:assert/strict";
import test from "node:test";

import { BUSINESS_API_OPERATIONS } from "../src/business_menu.mjs";
import { BoundedMessageDeduper, createBridgeMessageHandler } from "../src/bridge_core.mjs";

const USER = "fictional-allowed-user";
const BASE = "http://127.0.0.1:8000";

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(body) };
}

function interaction(id, action, user = USER) {
  return { id, user_openid: user, data: { resolved: { button_data: action } } };
}

function createHarness({
  fetchImpl,
  focusEncouragements = null,
  now = () => Date.UTC(2030, 0, 2, 8, 0, 0),
  allowedUsers = new Set([USER]),
} = {}) {
  const fetches = [];
  const qqCalls = [];
  const order = [];
  const fakeFetch = fetchImpl || (async (url, options = {}) => {
    fetches.push({ url: String(url), options });
    order.push(`api:${new URL(String(url)).pathname}`);
    const path = new URL(String(url)).pathname;
    const bodies = {
      "/api/v1/briefing/today": { ready: true, date: "2030-01-02", script: "fictional briefing" },
      "/api/v1/demon-slayer/status": {
        date: "2030-01-02",
        points: 12,
        goals: [{ id: "goal_alpha", title: "虚构目标", completed: false }],
      },
      "/api/v1/demon-slayer/goals": {
        status: "ok",
        goal: { id: "goal_created", title: "虚构新增目标", rank: "大妖", demon: "学业妖" },
      },
      "/api/v1/demon-slayer/checkins": {
        done: true,
        points_awarded: 10,
        total_points: 22,
        duplicate: false,
        repeat_mode: "recurring",
        active_since: "2030-01-01",
        active_days: 2,
        current_streak: 2,
        longest_streak: 4,
        streak_unit: "day",
        encouragement: "Kei：已经连续完成 2 天。哼，确实有点厉害。下一次也别掉链子。",
        kei_generated: true,
      },
      "/api/v1/demon-slayer/reviews/daily": { completed: 1, total: 1, points_earned: 10, missed: [] },
      "/api/v1/fitness/status": { checked_today: false, streak: 2, total_checkins: 7 },
      "/api/v1/fitness/checkins": { already_checked_in: false, streak: 3, total_checkins: 8 },
      "/api/v1/focus/status": { active: false, status: "idle", remaining_seconds: 0 },
      "/api/v1/focus/start": {
        active: true,
        started: true,
        status: "active",
        mode: "pomodoro",
        session_id: "fictional-session",
        start_at: "2030-01-02T08:00:00",
        remaining_seconds: 1500,
      },
      "/api/v1/focus/stop": { active: false, status: "stopped", remaining_seconds: 0 },
      "/api/v1/calendar/today": { date: "2030-01-02", today_events: [{ title: "虚构备忘" }] },
      "/api/v1/calendar/status": { skills: [{ name: "虚构技能", total_hours: 12.5, level: { name: "练气" } }] },
      "/api/v1/calendar/events": { status: "ok", event: { title: "虚构备忘" } },
      "/api/v1/calendar/practice": { status: "ok", skill: { name: "虚构技能", total_hours: 13.5 } },
    };
    return response(200, bodies[path] || { text: "conversation reply" });
  });
  const handler = createBridgeMessageHandler({
    allowedUsers,
    qqRequest: async (method, path, body) => {
      qqCalls.push({ method, path, body });
      order.push(method === "PUT" ? "ack" : "send");
      return {};
    },
    projectKeiUrl: BASE,
    fetchImpl: async (url, options) => {
      if (fetchImpl) {
        fetches.push({ url: String(url), options });
        order.push(`api:${new URL(String(url)).pathname}`);
      }
      return fakeFetch(url, options);
    },
    deduper: new BoundedMessageDeduper(100),
    logger: { info() {}, warn() {}, error() {} },
    focusEncouragements,
    now,
  });
  return { handler, fetches, qqCalls, order };
}

function outgoingMessages(qqCalls) {
  return qqCalls.filter(call => call.method === "POST" && call.path.includes("/messages"));
}

test("main menu exposes exactly five bounded features without business writes", async () => {
  const harness = createHarness();
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "menu-1",
    content: "菜单",
    author: { user_openid: USER },
  });
  assert.equal(harness.fetches.length, 0);
  const sent = outgoingMessages(harness.qqCalls);
  assert.equal(sent.length, 1);
  const rows = sent[0].body.keyboard.content.rows;
  assert.ok(rows.length <= 5);
  assert.ok(rows.every(row => row.buttons.length <= 5));
  const labels = rows.flatMap(row => row.buttons.map(item => item.render_data.label));
  assert.deepEqual(labels, ["每日情报", "斩妖除魔", "健身打卡", "专注计时", "日历与修炼"]);
});

test("all business main buttons only open bounded submenus and make no API request", async () => {
  const harness = createHarness();
  const actions = ["kei:menu:demon", "kei:menu:fitness", "kei:menu:focus", "kei:menu:calendar"];
  for (const [index, action] of actions.entries()) {
    await harness.handler.handleDispatch("INTERACTION_CREATE", interaction(`submenu-${index}`, action));
  }
  assert.equal(harness.fetches.length, 0);
  assert.equal(harness.qqCalls.filter(call => call.method === "PUT").length, actions.length);
  assert.equal(outgoingMessages(harness.qqCalls).length, actions.length);
  for (const call of outgoingMessages(harness.qqCalls)) {
    const rows = call.body.keyboard.content.rows;
    assert.ok(rows.length <= 5);
    assert.ok(rows.every(row => row.buttons.length <= 5));
  }
  const demonLabels = outgoingMessages(harness.qqCalls)[0].body.keyboard.content.rows
    .flatMap(row => row.buttons.map(item => item.render_data.label));
  assert.ok(demonLabels.includes("添加常驻目标"));
});

test("spoken demon add phrases open bounded cadence buttons without API or conversation", async () => {
  const harness = createHarness();
  const phrases = [
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
  ];
  for (const [index, content] of phrases.entries()) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `demon-add-menu-${index}`,
      content,
      author: { user_openid: USER },
    });
  }
  assert.equal(harness.fetches.length, 0);
  const messages = outgoingMessages(harness.qqCalls);
  assert.equal(messages.length, phrases.length);
  for (const message of messages) {
    const labels = message.body.keyboard.content.rows.flatMap(row => row.buttons.map(item => item.render_data.label));
    assert.deepEqual(labels, ["添加日任务", "添加周任务", "添加月任务", "添加年任务", "返回斩妖菜单"]);
  }
});

test("demon cadence buttons only show strict input instructions", async () => {
  const harness = createHarness();
  const cases = [
    ["kei:demon:add:daily", "添加日任务 目标名称"],
    ["kei:demon:add:weekly", "添加周任务 目标名称"],
    ["kei:demon:add:monthly", "添加月任务 目标名称"],
    ["kei:demon:add:yearly", "添加年任务 目标名称"],
  ];
  for (const [index, [action]] of cases.entries()) {
    await harness.handler.handleDispatch("INTERACTION_CREATE", interaction(`demon-add-instruction-${index}`, action));
  }
  assert.equal(harness.fetches.length, 0);
  const messages = outgoingMessages(harness.qqCalls);
  cases.forEach(([, expected], index) => assert.match(messages[index].body.markdown.content, new RegExp(expected)));
});

test("strict demon add command requires user-bound confirmation before one fixed recurring goal POST", async () => {
  const harness = createHarness();
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "demon-add-command",
    content: "添加周任务 每日情报整理",
    author: { user_openid: USER },
  });
  assert.equal(harness.fetches.length, 0);
  const confirmation = outgoingMessages(harness.qqCalls).at(-1);
  assert.match(confirmation.body.markdown.content, /确认添加周常驻目标/);
  const actions = confirmation.body.keyboard.content.rows.flatMap(row => row.buttons.map(item => item.action.data));
  const confirmAction = actions.find(value => value.startsWith("kei:demon:add:confirm:"));
  assert.ok(confirmAction);
  assert.equal(confirmAction.includes("每日情报整理"), false);

  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("demon-add-confirm", confirmAction));
  assert.deepEqual(
    harness.fetches.map(call => [new URL(call.url).pathname, call.options.method]),
    [["/api/v1/demon-slayer/goals", "POST"]],
  );
  assert.deepEqual(JSON.parse(harness.fetches[0].options.body), {
    title: "每日情报整理",
    cadence: "weekly",
    category: "auto",
    repeat_mode: "recurring",
    target_date: null,
  });
  assert.ok(harness.fetches.every(call => !call.url.includes("/api/v1/conversation")));

  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("demon-add-confirm-repeat", confirmAction));
  assert.equal(harness.fetches.length, 1);
  assert.match(outgoingMessages(harness.qqCalls).at(-1).body.markdown.content, /已过期、已处理或不属于当前用户/);
});

test("demon add cancellation, foreign user and expiry make no business write", async () => {
  const otherUser = "fictional-other-allowed-user";
  let current = Date.UTC(2030, 0, 2, 8, 0, 0);
  const harness = createHarness({
    allowedUsers: new Set([USER, otherUser]),
    now: () => current,
  });
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "demon-add-cancel-command",
    content: "添加月任务 虚构月目标",
    author: { user_openid: USER },
  });
  const firstCard = outgoingMessages(harness.qqCalls).at(-1);
  const firstActions = firstCard.body.keyboard.content.rows.flatMap(row => row.buttons.map(item => item.action.data));
  const firstConfirm = firstActions.find(value => value.includes(":confirm:"));
  const firstCancel = firstActions.find(value => value.includes(":cancel:"));

  await harness.handler.handleDispatch(
    "INTERACTION_CREATE",
    interaction("demon-add-foreign", firstConfirm, otherUser),
  );
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("demon-add-cancel", firstCancel));
  assert.equal(harness.fetches.length, 0);

  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "demon-add-expiry-command",
    content: "添加年任务 虚构年目标",
    author: { user_openid: USER },
  });
  const secondCard = outgoingMessages(harness.qqCalls).at(-1);
  const secondConfirm = secondCard.body.keyboard.content.rows
    .flatMap(row => row.buttons.map(item => item.action.data))
    .find(value => value.includes(":confirm:"));
  current += 10 * 60 * 1000 + 1;
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("demon-add-expired", secondConfirm));
  assert.equal(harness.fetches.length, 0);
});

test("invalid demon add commands stay deterministic and never reach API or conversation", async () => {
  const harness = createHarness();
  const commands = [
    "添加日任务 ",
    `添加日任务 ${"长".repeat(81)}`,
    "添加周任务 第一行\n第二行",
    "添加月任务目标名称",
  ];
  for (const [index, content] of commands.entries()) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `demon-add-invalid-${index}`,
      content,
      author: { user_openid: USER },
    });
  }
  assert.equal(harness.fetches.length, 0);
  assert.equal(outgoingMessages(harness.qqCalls).length, commands.length);
});

test("status buttons are read-only fixed versioned GETs and never reach conversation", async () => {
  const harness = createHarness();
  const cases = [
    ["kei:demon:today", "/api/v1/demon-slayer/status"],
    ["kei:fitness:status", "/api/v1/fitness/status"],
    ["kei:focus:status", "/api/v1/focus/status"],
    ["kei:calendar:today", "/api/v1/calendar/today"],
    ["kei:calendar:practice", "/api/v1/calendar/status"],
  ];
  for (const [index, [action]] of cases.entries()) {
    await harness.handler.handleDispatch("INTERACTION_CREATE", interaction(`status-${index}`, action));
  }
  assert.deepEqual(
    harness.fetches.map(call => [new URL(call.url).pathname, call.options.method]),
    cases.map(([, path]) => [path, "GET"]),
  );
  assert.ok(harness.fetches.every(call => !call.url.includes("/api/v1/conversation")));
  assert.ok(harness.fetches.every(call => call.options.body === undefined));
});

test("daily briefing and explicit daily review keep their fixed read paths", async () => {
  const harness = createHarness();
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("briefing-read", "kei:daily-briefing"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("review-read", "kei:demon:review"));
  assert.deepEqual(
    harness.fetches.map(call => [new URL(call.url).pathname, call.options.method]),
    [
      ["/api/v1/briefing/today", undefined],
      ["/api/v1/demon-slayer/reviews/daily", "GET"],
    ],
  );
  assert.ok(harness.fetches.every(call => call.options.body === undefined));
});

test("explicit business mutations call each fixed endpoint once with constrained bodies", async () => {
  const harness = createHarness();
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-read", "kei:demon:today"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-write", "kei:demon:goal:done:goal_alpha"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("fitness-write", "kei:fitness:confirm"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("focus-start", "kei:focus:start25"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("focus-stop", "kei:focus:stop"));

  const mutations = harness.fetches.filter(call => call.options.method === "POST");
  assert.deepEqual(mutations.map(call => new URL(call.url).pathname), [
    "/api/v1/demon-slayer/checkins",
    "/api/v1/fitness/checkins",
    "/api/v1/focus/start",
    "/api/v1/focus/stop",
  ]);
  assert.deepEqual(JSON.parse(mutations[0].options.body), {
    goal_id: "goal_alpha",
    done: true,
    note: "",
    with_encouragement: true,
  });
  assert.deepEqual(JSON.parse(mutations[1].options.body), { note: "" });
  assert.deepEqual(JSON.parse(mutations[2].options.body), {
    mode: "pomodoro",
    minutes: 25,
    task: "",
    force: false,
    with_audio: false,
  });
  assert.equal(mutations[3].options.body, "{}");
});

test("demon completion displays service-provided duration, cadence streak and Kei encouragement without extra API calls", async () => {
  const harness = createHarness();
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-feedback-read", "kei:demon:today"));
  await harness.handler.handleDispatch(
    "INTERACTION_CREATE",
    interaction("goal-feedback-write", "kei:demon:goal:done:goal_alpha"),
  );

  assert.deepEqual(
    harness.fetches.map(call => [new URL(call.url).pathname, call.options.method]),
    [
      ["/api/v1/demon-slayer/status", "GET"],
      ["/api/v1/demon-slayer/checkins", "POST"],
    ],
  );
  const markdown = outgoingMessages(harness.qqCalls).at(-1).body.markdown.content;
  assert.match(markdown, /启用时长：2 天/);
  assert.match(markdown, /当前连续：2 天/);
  assert.match(markdown, /历史最长：4 天/);
  assert.match(markdown, /Kei：已经连续完成 2 天/);
  assert.ok(harness.fetches.every(call => !call.url.includes("/api/v1/conversation")));
});

test("demon completion renders weekly and once zero/null facts without client-side streak calculation", async () => {
  const responses = [
    {
      done: true,
      points_awarded: 35,
      total_points: 35,
      duplicate: false,
      repeat_mode: "recurring",
      active_since: "2030-01-01",
      active_days: 8,
      current_streak: 2,
      longest_streak: 3,
      streak_unit: "week",
      encouragement: "Kei：已经连续完成 2 周。继续保持。",
      kei_generated: false,
    },
    {
      done: true,
      points_awarded: 120,
      total_points: 155,
      duplicate: false,
      repeat_mode: "once",
      active_since: null,
      active_days: null,
      current_streak: 0,
      longest_streak: 0,
      streak_unit: "month",
      encouragement: "Kei：这个临时目标已经完成。继续保持。",
      kei_generated: false,
    },
  ];
  let checkinIndex = 0;
  const harness = createHarness({
    fetchImpl: async (url) => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/v1/demon-slayer/status") {
        return response(200, {
          date: "2030-01-02",
          points: 0,
          goals: [
            { id: "goal_weekly", title: "虚构周目标", completed: false },
            { id: "goal_once", title: "虚构临时目标", completed: false },
          ],
        });
      }
      if (path === "/api/v1/demon-slayer/checkins") {
        return response(200, responses[checkinIndex++]);
      }
      return response(500, {});
    },
  });
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-units-read", "kei:demon:today"));
  await harness.handler.handleDispatch(
    "INTERACTION_CREATE",
    interaction("goal-weekly-write", "kei:demon:goal:done:goal_weekly"),
  );
  await harness.handler.handleDispatch(
    "INTERACTION_CREATE",
    interaction("goal-once-write", "kei:demon:goal:done:goal_once"),
  );

  const messages = outgoingMessages(harness.qqCalls);
  const weekly = messages.at(-2).body.markdown.content;
  const once = messages.at(-1).body.markdown.content;
  assert.match(weekly, /当前连续：2 周/);
  assert.match(weekly, /历史最长：3 周/);
  assert.match(once, /启用时长：临时目标不累计/);
  assert.match(once, /当前连续：0 月/);
  assert.match(once, /历史最长：0 月/);
  assert.doesNotMatch(`${weekly}\n${once}`, /undefined|NaN/);
});

test("explicit encouragement preset and strict command register one bounded session without calling LLM immediately", async () => {
  const registrations = [];
  let cancellations = 0;
  const harness = createHarness({
    focusEncouragements: {
      register(value) { registrations.push(value); return true; },
      cancelUser() { cancellations += 1; },
    },
  });
  await harness.handler.handleDispatch(
    "INTERACTION_CREATE",
    interaction("focus-encourage-preset", "kei:focus:start25:encourage10"),
  );
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "focus-encourage-command",
    content: "专注 60 鼓励 20",
    author: { user_openid: USER },
  });
  assert.deepEqual(
    harness.fetches.map(call => [new URL(call.url).pathname, call.options.method]),
    [
      ["/api/v1/focus/start", "POST"],
      ["/api/v1/focus/start", "POST"],
    ],
  );
  assert.deepEqual(
    harness.fetches.map(call => JSON.parse(call.options.body).minutes),
    [25, 60],
  );
  assert.deepEqual(
    registrations.map(value => ({
      userOpenId: value.userOpenId,
      sessionId: value.sessionId,
      startAt: value.startAt,
      durationMinutes: value.durationMinutes,
      encouragementAfterMinutes: value.encouragementAfterMinutes,
    })),
    [
      {
        userOpenId: USER,
        sessionId: "fictional-session",
        startAt: "2030-01-02T08:00:00",
        durationMinutes: 25,
        encouragementAfterMinutes: 10,
      },
      {
        userOpenId: USER,
        sessionId: "fictional-session",
        startAt: "2030-01-02T08:00:00",
        durationMinutes: 60,
        encouragementAfterMinutes: 20,
      },
    ],
  );
  assert.equal(cancellations, 0);
  assert.ok(harness.fetches.every(call => !call.url.includes("/encouragement")));
  assert.ok(harness.fetches.every(call => !call.url.includes("/conversation")));
});

test("ordinary focus actions invoke no encouragement and strict invalid formats invoke no API or conversation", async () => {
  const calls = [];
  const harness = createHarness({
    focusEncouragements: {
      register() { calls.push("register"); },
      cancelUser() { calls.push("cancel"); },
    },
  });
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("focus-ordinary-start", "kei:focus:start25"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("focus-ordinary-status", "kei:focus:status"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("focus-ordinary-stop", "kei:focus:stop"));
  assert.deepEqual(calls, ["cancel", "cancel"]);
  const before = harness.fetches.length;
  for (const [index, content] of [
    "专注",
    "专注 1 鼓励 1",
    "专注 241 鼓励 10",
    "专注 25 鼓励 0",
    "专注 25 鼓励 25",
    "专注 二十五 鼓励 十",
    "专注 25 鼓励 10 任意prompt",
  ].entries()) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `focus-invalid-${index}`,
      content,
      author: { user_openid: USER },
    });
  }
  assert.equal(harness.fetches.length, before);
  assert.ok(outgoingMessages(harness.qqCalls).slice(-7).every(
    call => call.body.markdown.content.includes("用法"),
  ));
});

test("explicit incomplete goal check-in sends done=false exactly once", async () => {
  const harness = createHarness();
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-read-missed", "kei:demon:today"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-write-missed", "kei:demon:goal:missed:goal_alpha"));
  const calls = harness.fetches.filter(call => new URL(call.url).pathname === "/api/v1/demon-slayer/checkins");
  assert.equal(calls.length, 1);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    goal_id: "goal_alpha",
    done: false,
    note: "",
    with_encouragement: false,
  });
});

test("dynamic goal actions require a recent API-returned bounded goal id", async () => {
  let currentTime = Date.UTC(2030, 0, 2, 8, 0, 0);
  const manyGoals = Array.from({ length: 20 }, (_, index) => ({
    id: `goal_${index}`,
    title: `目标 ${index} ${"*".repeat(120)}`,
    completed: false,
  }));
  const harness = createHarness({
    now: () => currentTime,
    fetchImpl: async (url, options = {}) => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/v1/demon-slayer/status") return response(200, { date: "2030-01-02", points: 0, goals: manyGoals });
      if (path === "/api/v1/demon-slayer/checkins") return response(200, { points_awarded: 10, total_points: 10 });
      return response(200, {});
    },
  });
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goals-many", "kei:demon:today"));
  const statusCard = outgoingMessages(harness.qqCalls).at(-1).body;
  assert.equal(statusCard.keyboard.content.rows.length, 5);
  assert.ok(statusCard.markdown.content.length <= 1200);

  const before = harness.fetches.length;
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-not-shown", "kei:demon:goal:done:goal_19"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-injected", "kei:demon:goal:done:goal_attacker"));
  assert.equal(harness.fetches.length, before);
  assert.ok(outgoingMessages(harness.qqCalls).at(-1).body.markdown.content.includes("无效"));

  currentTime += 11 * 60 * 1000;
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("goal-expired", "kei:demon:goal:done:goal_0"));
  assert.equal(harness.fetches.length, before);
  assert.ok(outgoingMessages(harness.qqCalls).at(-1).body.markdown.content.includes("过期"));
});

test("strict calendar commands are deterministic and invalid formats never call API or conversation", async () => {
  const harness = createHarness();
  const valid = [
    ["cmd-event", "添加备忘 2030-02-28 虚构纪念日", "/api/v1/calendar/events"],
    ["cmd-practice", "记录修炼 虚构技能 1.25", "/api/v1/calendar/practice"],
  ];
  for (const [id, content] of valid) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", { id, content, author: { user_openid: USER } });
  }
  assert.deepEqual(harness.fetches.map(call => new URL(call.url).pathname), valid.map(([, , path]) => path));
  assert.deepEqual(JSON.parse(harness.fetches[0].options.body), {
    title: "虚构纪念日",
    date: "2030-02-28",
    repeat: "none",
    note: "",
    tags: [],
  });
  assert.deepEqual(JSON.parse(harness.fetches[1].options.body), {
    skill: "虚构技能",
    hours: 1.25,
    date: null,
    note: "",
  });

  const fetchCount = harness.fetches.length;
  for (const [index, content] of [
    "添加备忘 2030-02-30 不存在日期",
    "添加备忘 2030-01-01",
    "记录修炼 两个 技能 1",
    "记录修炼 技能 25",
    `添加备忘 2030-01-01 ${"长".repeat(81)}`,
  ].entries()) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `invalid-${index}`,
      content,
      author: { user_openid: USER },
    });
  }
  assert.equal(harness.fetches.length, fetchCount);
  assert.ok(outgoingMessages(harness.qqCalls).slice(-5).every(call => call.body.markdown.content.includes("用法")));
});

test("strict calendar commands win over every broad briefing keyword", async () => {
  const harness = createHarness();
  const keywords = ["每日情报", "今日情报", "今天情报", "今日简报", "dailybriefing"];
  for (const [index, keyword] of keywords.entries()) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `collision-event-${index}`,
      content: `添加备忘 2030-01-${String(index + 1).padStart(2, "0")} ${keyword}`,
      author: { user_openid: USER },
    });
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `collision-practice-${index}`,
      content: `记录修炼 ${keyword} 1`,
      author: { user_openid: USER },
    });
  }
  assert.deepEqual(
    harness.fetches.map(call => [new URL(call.url).pathname, call.options.method]),
    keywords.flatMap(() => [
      ["/api/v1/calendar/events", "POST"],
      ["/api/v1/calendar/practice", "POST"],
    ]),
  );
  assert.ok(harness.fetches.every(call => !call.url.includes("/api/v1/briefing/") && !call.url.includes("/api/v1/conversation")));

  const beforeInvalid = harness.fetches.length;
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "collision-invalid",
    content: "添加备忘 2030-02-30 每日情报",
    author: { user_openid: USER },
  });
  assert.equal(harness.fetches.length, beforeInvalid);
  assert.ok(outgoingMessages(harness.qqCalls).at(-1).body.markdown.content.includes("用法"));

  const duplicate = {
    id: "collision-duplicate",
    content: "添加备忘 2030-01-20 今日情报",
    author: { user_openid: USER },
  };
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", duplicate);
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", duplicate);
  assert.equal(
    harness.fetches.filter(call => new URL(call.url).pathname === "/api/v1/calendar/events").length,
    keywords.length + 1,
  );

  const blockedFetchCount = harness.fetches.length;
  const blockedSendCount = harness.qqCalls.length;
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "collision-blocked",
    content: "添加备忘 2030-01-21 今天情报",
    author: { user_openid: "blocked-fictional-user" },
  });
  assert.equal(harness.fetches.length, blockedFetchCount);
  assert.equal(harness.qqCalls.length, blockedSendCount);

  for (const [index, keyword] of ["每日情报", "今日情报"].entries()) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `plain-briefing-${index}`,
      content: keyword,
      author: { user_openid: USER },
    });
  }
  assert.deepEqual(
    harness.fetches.slice(-2).map(call => [new URL(call.url).pathname, call.options.method]),
    [
      ["/api/v1/briefing/today", undefined],
      ["/api/v1/briefing/today", undefined],
    ],
  );
});

test("feature text commands route before conversation while ordinary chat retains conversation fallback", async () => {
  const harness = createHarness();
  for (const [index, content] of ["斩妖除魔", "健身打卡", "专注计时", "日历与修炼"].entries()) {
    await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id: `feature-${index}`,
      content,
      author: { user_openid: USER },
    });
  }
  assert.equal(harness.fetches.length, 0);
  await harness.handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "ordinary-chat",
    content: "这是一条虚构的普通聊天",
    author: { user_openid: USER },
  });
  assert.equal(new URL(harness.fetches[0].url).pathname, "/api/v1/conversation");
  assert.equal(harness.fetches[0].options.method, "POST");
});

test("whitelist rejection and duplicate business interactions make zero extra API or sends", async () => {
  const harness = createHarness();
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("blocked", "kei:fitness:confirm", "blocked-fictional-user"));
  assert.equal(harness.fetches.length, 0);
  assert.equal(harness.qqCalls.length, 0);

  const event = interaction("duplicate", "kei:fitness:confirm");
  await harness.handler.handleDispatch("INTERACTION_CREATE", event);
  const counts = [harness.fetches.length, harness.qqCalls.length];
  await harness.handler.handleDispatch("INTERACTION_CREATE", event);
  assert.deepEqual([harness.fetches.length, harness.qqCalls.length], counts);
  assert.equal(harness.fetches.filter(call => new URL(call.url).pathname === "/api/v1/fitness/checkins").length, 1);
});

test("recognized interactions ACK before API and fixed failures never echo upstream bodies", async () => {
  const secretBody = "Authorization: Bearer FAKE_AUTH full-openid-FAKE_OPENID private message";
  const harness = createHarness({
    fetchImpl: async url => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/v1/focus/status") return response(404, { detail: secretBody });
      return response(500, { detail: secretBody });
    },
  });
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("focus-404", "kei:focus:status"));
  assert.deepEqual(harness.order.slice(0, 3), ["ack", "api:/api/v1/focus/status", "send"]);
  const focusText = outgoingMessages(harness.qqCalls).at(-1).body.content;
  assert.ok(focusText.includes("不会自动安装"));
  for (const leaked of ["FAKE_AUTH", "FAKE_OPENID", "private message"]) assert.equal(focusText.includes(leaked), false);

  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("fitness-500", "kei:fitness:status"));
  const genericText = outgoingMessages(harness.qqCalls).at(-1).body.content;
  assert.equal(genericText, "该功能暂时不可用，请稍后再试。");
  for (const leaked of ["FAKE_AUTH", "FAKE_OPENID", "private message"]) assert.equal(genericText.includes(leaked), false);
});

test("timeouts and 422 return fixed bounded prompts", async () => {
  let call = 0;
  const harness = createHarness({
    fetchImpl: async () => {
      call += 1;
      if (call === 1) throw Object.assign(new Error("FAKE_SECRET_TIMEOUT"), { name: "AbortError" });
      return response(422, { detail: "Authorization FAKE_TOKEN FAKE_OPENID" });
    },
  });
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("timeout", "kei:calendar:today"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("invalid-state", "kei:fitness:confirm"));
  const texts = outgoingMessages(harness.qqCalls).slice(-2).map(item => item.body.content);
  assert.deepEqual(texts, [
    "本地功能响应超时，请稍后重试。",
    "请求未被接受，状态可能已经变化。请重新查看后再操作。",
  ]);
});

test("invalid JSON and invalid top-level payloads fail closed with fixed prompts", async () => {
  let call = 0;
  const harness = createHarness({
    fetchImpl: async () => {
      call += 1;
      if (call === 1) return { ok: true, status: 200, text: async () => "{FAKE_SECRET_BROKEN" };
      return { ok: true, status: 200, text: async () => "[\"FAKE_OPENID\"]" };
    },
  });
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("invalid-json", "kei:calendar:today"));
  await harness.handler.handleDispatch("INTERACTION_CREATE", interaction("invalid-shape", "kei:fitness:status"));
  assert.deepEqual(
    outgoingMessages(harness.qqCalls).slice(-2).map(item => item.body.content),
    ["该功能暂时不可用，请稍后再试。", "该功能暂时不可用，请稍后再试。"],
  );
});

test("business reply send failure uses one fixed fallback without logging sensitive details", async () => {
  const sent = [];
  const logs = [];
  let messageAttempts = 0;
  const handler = createBridgeMessageHandler({
    allowedUsers: new Set([USER]),
    qqRequest: async (method, path, body) => {
      if (method === "PUT") return {};
      messageAttempts += 1;
      if (messageAttempts === 1) throw new Error("Authorization: Bearer FAKE_TOKEN FAKE_OPENID");
      sent.push({ path, body });
      return {};
    },
    projectKeiUrl: BASE,
    fetchImpl: async () => response(200, { checked_today: false, streak: 0, total_checkins: 0 }),
    logger: { info: value => logs.push(value), warn: value => logs.push(value), error: value => logs.push(value) },
    now: () => Date.UTC(2030, 0, 2, 8, 0, 0),
  });
  await handler.handleDispatch("INTERACTION_CREATE", interaction("send-failure", "kei:fitness:status"));
  assert.equal(messageAttempts, 2);
  assert.equal(sent[0].body.content, "该功能暂时不可用，请稍后再试。");
  const serialized = JSON.stringify(logs);
  for (const secret of ["FAKE_TOKEN", "FAKE_OPENID", "Authorization"]) assert.equal(serialized.includes(secret), false);
});

test("operation table contains only fixed versioned allowlisted methods and no destructive surface", () => {
  const specs = Object.values(BUSINESS_API_OPERATIONS);
  assert.deepEqual(new Set(specs.map(spec => spec.method)), new Set(["GET", "POST"]));
  assert.ok(specs.every(spec => spec.path.startsWith("/api/v1/")));
  assert.ok(specs.every(spec => !/[?{}]/.test(spec.path)));
  for (const forbidden of ["reset", "force", "reward", "redeem", "delete", "patch", "http://", "https://", "/conversation"]) {
    assert.ok(specs.every(spec => !spec.path.toLowerCase().includes(forbidden)));
  }
});

test("unknown action data cannot become a URL, method, path, reset, or conversation call", async () => {
  const harness = createHarness();
  const actions = [
    "https://attacker.invalid/reset",
    "kei:reset",
    "kei:focus:force",
    "kei:calendar:../../private",
    "POST /api/v1/calendar/reset",
    "kei:demon:reward:redeem",
  ];
  for (const [index, action] of actions.entries()) {
    await harness.handler.handleDispatch("INTERACTION_CREATE", interaction(`unknown-${index}`, action));
  }
  assert.equal(harness.fetches.length, 0);
  assert.equal(harness.qqCalls.length, 0);
});
