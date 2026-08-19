import assert from "node:assert/strict";
import test from "node:test";

import { BoundedMessageDeduper, c2cEventIdentity, createBridgeMessageHandler, createQqApiClient, fetchWithTimeout, fixedQqEndpointBase, formatDailyBriefingMarkdown, readSafeJson, validateGatewayUrl } from "../src/bridge_core.mjs";

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(body) };
}

function hangingJsonResponse(status = 200, firstChunk = '{"partial":') {
  let reads = 0;
  let cancelled = 0;
  let releasePending;
  const pending = new Promise((resolve, reject) => { releasePending = { resolve, reject }; });
  return {
    response: {
      ok: status >= 200 && status < 300,
      status,
      body: {
        getReader() {
          return {
            read() {
              reads += 1;
              if (reads === 1) return Promise.resolve({ done: false, value: new TextEncoder().encode(firstChunk) });
              return pending;
            },
            cancel() { cancelled += 1; return Promise.resolve(); },
            releaseLock() {},
          };
        },
      },
    },
    reads: () => reads,
    cancelled: () => cancelled,
    releasePending,
  };
}

function nativePendingResponse(status = 200, chunks = []) {
  let cancels = 0;
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
    },
    cancel() { cancels += 1; },
  });
  return {
    response: new Response(stream, { status }),
    cancels: () => cancels,
  };
}

async function settlesWithin(promise, timeoutMs = 100) {
  return Promise.race([
    promise.then(value => ({ kind: "resolved", value }), error => ({ kind: "rejected", error })),
    new Promise(resolve => setTimeout(() => resolve({ kind: "timeout" }), timeoutMs)),
  ]);
}

test("QQ API and Gateway endpoints use a fixed official allowlist", () => {
  const apiBases = new Set(["https://api.bot.qq.com", "https://api.sgroup.qq.com"]);
  assert.equal(fixedQqEndpointBase(undefined, "https://api.bot.qq.com", apiBases), "https://api.bot.qq.com");
  assert.equal(fixedQqEndpointBase("https://api.sgroup.qq.com/", "https://api.bot.qq.com", apiBases), "https://api.sgroup.qq.com");
  assert.throws(() => fixedQqEndpointBase("https://attacker.invalid", "https://api.bot.qq.com", apiBases), /qq_endpoint_rejected/);
  assert.equal(validateGatewayUrl("wss://api.bot.qq.com/websocket"), "wss://api.bot.qq.com/websocket");
  assert.equal(validateGatewayUrl("wss://api.sgroup.qq.com/websocket"), "wss://api.sgroup.qq.com/websocket");
  for (const unsafe of [
    "ws://api.bot.qq.com/websocket",
    "wss://127.0.0.1/websocket",
    "wss://api.bot.qq.com/other",
    "wss://user:password@api.bot.qq.com/websocket",
    "wss://api.bot.qq.com/websocket?target=internal",
  ]) assert.throws(() => validateGatewayUrl(unsafe));
});

test("allowlist precedes forwarding, menus, buttons, and replies", async () => {
  let fetches = 0;
  let qqCalls = 0;
  const logs = [];
  const handler = createBridgeMessageHandler({
    allowedUsers: new Set(["allowed-user"]),
    qqRequest: async () => { qqCalls += 1; },
    projectKeiUrl: "http://127.0.0.1:8000",
    fetchImpl: async () => { fetches += 1; return response(200, { text: "reply" }); },
    logger: { info: value => logs.push(value), warn: value => logs.push(value), error: value => logs.push(value) },
  });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { id: "m1", content: "菜单", author: { user_openid: "blocked-user" } });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { id: "m2", content: "每日情报", author: { user_openid: "blocked-user" } });
  await handler.handleDispatch("INTERACTION_CREATE", { id: "i1", user_openid: "blocked-user", data: { resolved: { button_data: "kei:daily-briefing" } } });
  assert.equal(fetches, 0);
  assert.equal(qqCalls, 0);
  assert.ok(logs.every(value => !String(value).includes("blocked-user")));
});

test("empty allowlist and duplicate message IDs produce zero extra forwarding", async () => {
  let fetches = 0;
  let sends = 0;
  const empty = createBridgeMessageHandler({
    allowedUsers: new Set(), qqRequest: async () => { sends += 1; }, projectKeiUrl: "http://127.0.0.1:8000",
    fetchImpl: async () => { fetches += 1; return response(200, { text: "reply" }); },
    logger: { info() {}, warn() {}, error() {} },
  });
  await empty.handleDispatch("C2C_MESSAGE_CREATE", { id: "m1", content: "hello", author: { user_openid: "nobody" } });
  assert.equal(fetches, 0);
  assert.equal(sends, 0);

  const allowed = createBridgeMessageHandler({
    allowedUsers: new Set(["fictional-openid"]), qqRequest: async () => { sends += 1; }, projectKeiUrl: "http://127.0.0.1:8000",
    fetchImpl: async () => { fetches += 1; return response(200, { text: "reply" }); },
    deduper: new BoundedMessageDeduper(2), logger: { info() {}, warn() {}, error() {} },
  });
  const event = { id: "same-id", content: "hello", author: { user_openid: "fictional-openid" } };
  await allowed.handleDispatch("C2C_MESSAGE_CREATE", event);
  await allowed.handleDispatch("C2C_MESSAGE_CREATE", event);
  assert.equal(fetches, 1);
  assert.equal(sends, 1);
});

test("C2C identity includes official sequence and scene index without collapsing valid deliveries", async () => {
  let conversations = 0;
  let sends = 0;
  const handler = createBridgeMessageHandler({
    allowedUsers: new Set(["fictional-user"]),
    qqRequest: async () => { sends += 1; },
    projectKeiUrl: "http://127.0.0.1:8000",
    fetchImpl: async () => { conversations += 1; return response(200, { text: "bounded reply" }); },
    logger: { info() {}, warn() {}, error() {} },
  });
  const base = { id: "same-message", content: "hello", message_type: 0, author: { user_openid: "fictional-user" } };
  const first = { ...base, msg_seq: 7, message_scene: { ext: { msg_idx: 1 } } };
  assert.equal(c2cEventIdentity(first), "c2c:same-message:seq:7:idx:1");
  await handler.handleDispatch("C2C_MESSAGE_CREATE", first);
  await handler.handleDispatch("C2C_MESSAGE_CREATE", structuredClone(first));
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { ...base, msg_seq: 8, message_scene: { ext: { msg_idx: 1 } } });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { ...base, msg_seq: 8, message_scene: { ext: { msg_idx: 2 } } });
  assert.equal(conversations, 3);
  assert.equal(sends, 3);
});

test("C2C text accepts only bounded text message types 0 and 103", async () => {
  let conversations = 0;
  let sends = 0;
  const forwarded = [];
  const handler = createBridgeMessageHandler({
    allowedUsers: new Set(["fictional-user"]),
    qqRequest: async () => { sends += 1; },
    projectKeiUrl: "http://127.0.0.1:8000",
    fetchImpl: async (_url, options) => {
      conversations += 1;
      forwarded.push(JSON.parse(options.body).message);
      return response(200, { text: "reply" });
    },
    logger: { info() {}, warn() {}, error() {} },
  });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "text-0", msg_seq: 1, message_type: 0, content: " current text ",
    message_reference: { content: "quoted text must not replace current text" },
    author: { user_openid: "fictional-user" },
  });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "text-103", msg_seq: 1, message_type: 103, content: "supported text",
    author: { user_openid: "fictional-user" },
  });
  for (const [id, message_type, content] of [
    ["image", 1, "not text"],
    ["file", 7, "not text"],
    ["object", 0, { text: "not a string" }],
  ]) {
    await handler.handleDispatch("C2C_MESSAGE_CREATE", {
      id, msg_seq: 1, message_type, content, author: { user_openid: "fictional-user" },
    });
  }
  assert.equal(conversations, 2);
  assert.equal(sends, 2);
  assert.deepEqual(forwarded, ["current text", "supported text"]);
});

test("QQ 401 refreshes the token and retries exactly once", async () => {
  let tokenCalls = 0;
  let apiCalls = 0;
  const fakeFetch = async url => {
    if (String(url).includes("getAppAccessToken")) {
      tokenCalls += 1;
      return response(200, { access_token: `FAKE_TOKEN_${tokenCalls}`, expires_in: 7200 });
    }
    apiCalls += 1;
    return response(401, { Authorization: "QQBot FAKE_SECRET_TOKEN", body: "FAKE_UPSTREAM_BODY" });
  };
  const client = createQqApiClient({ appId: "fake-app", secret: "FAKE_SECRET_TOKEN", apiBase: "https://qq.invalid", tokenBase: "https://token.invalid", fetchImpl: fakeFetch });
  await assert.rejects(client.request("POST", "/send", {}), error => {
    assert.equal(error.code, "http_401");
    assert.ok(!error.message.includes("FAKE_SECRET_TOKEN"));
    assert.ok(!error.message.includes("FAKE_UPSTREAM_BODY"));
    return true;
  });
  assert.equal(tokenCalls, 2);
  assert.equal(apiCalls, 2);
});

test("QQ token fetch consumes the lifecycle abort signal and settles promptly", async () => {
  const controller = new AbortController();
  let observedSignal;
  const client = createQqApiClient({
    appId: "fictional-app",
    secret: "FICTIONAL_SECRET",
    apiBase: "https://api.bot.qq.com",
    tokenBase: "https://bots.qq.com",
    timeoutMs: 60_000,
    fetchImpl: async (_url, options) => {
      observedSignal = options.signal;
      return new Promise((_, reject) => {
        options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })), { once: true });
      });
    },
  });
  const pending = client.getAccessToken(controller.signal);
  while (!observedSignal) await Promise.resolve();
  controller.abort();
  await assert.rejects(pending, error => error.name === "AbortError");
  assert.equal(observedSignal.aborted, true);
});

test("token JSON body remains under lifecycle cancellation after response headers", async () => {
  const lifecycle = new AbortController();
  const hanging = hangingJsonResponse();
  let requestSignal;
  let abortEvents = 0;
  const client = createQqApiClient({
    appId: "fictional-app", secret: "FICTIONAL_SECRET",
    apiBase: "https://api.bot.qq.com", tokenBase: "https://bots.qq.com", timeoutMs: 60_000,
    fetchImpl: async (_url, options) => {
      requestSignal = options.signal;
      requestSignal.addEventListener("abort", () => { abortEvents += 1; });
      return hanging.response;
    },
  });
  const pending = client.getAccessToken(lifecycle.signal);
  while (!requestSignal || hanging.reads() < 2) await Promise.resolve();
  lifecycle.abort();
  lifecycle.abort();
  const settled = await settlesWithin(pending);
  assert.equal(settled.kind, "rejected");
  assert.equal(settled.error.name, "AbortError");
  assert.equal(requestSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.equal(hanging.cancelled(), 1);
  hanging.releasePending.resolve({ done: true });
});

test("Gateway URL OpenAPI body is cancelled rather than merely ignored on stop signal", async () => {
  const lifecycle = new AbortController();
  const hanging = hangingJsonResponse();
  let apiSignal;
  let abortEvents = 0;
  let tokenCalls = 0;
  const client = createQqApiClient({
    appId: "fictional-app", secret: "FICTIONAL_SECRET",
    apiBase: "https://api.bot.qq.com", tokenBase: "https://bots.qq.com", timeoutMs: 60_000,
    fetchImpl: async (url, options) => {
      if (String(url).includes("getAppAccessToken")) {
        tokenCalls += 1;
        return response(200, { access_token: "FICTIONAL_TOKEN", expires_in: 7200 });
      }
      apiSignal = options.signal;
      apiSignal.addEventListener("abort", () => { abortEvents += 1; });
      return hanging.response;
    },
  });
  const pending = client.request("GET", "/gateway", undefined, true, lifecycle.signal);
  while (!apiSignal || hanging.reads() < 2) await Promise.resolve();
  lifecycle.abort();
  const settled = await settlesWithin(pending);
  assert.equal(settled.kind, "rejected");
  assert.equal(tokenCalls, 1);
  assert.equal(apiSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.equal(hanging.cancelled(), 1);
  hanging.releasePending.reject(new Error("late private upstream body"));
});

test("bounded JSON reader aborts and cancels before accepting an oversized streamed body", async () => {
  let requestSignal;
  let abortEvents = 0;
  let cancels = 0;
  const chunks = [new Uint8Array([123, 34, 97, 34]), new Uint8Array([58, 49, 50, 51])];
  const responsePromise = fetchWithTimeout("https://example.invalid/fake", {}, 60_000, async (_url, options) => {
    requestSignal = options.signal;
    requestSignal.addEventListener("abort", () => { abortEvents += 1; });
    return {
      ok: true,
      status: 200,
      headers: { get: name => String(name).toLowerCase() === "content-length" ? "2" : null },
      body: { getReader: () => ({
        read: async () => chunks.length ? { done: false, value: chunks.shift() } : { done: true },
        cancel: async () => { cancels += 1; },
        releaseLock() {},
      }) },
    };
  });
  const streamed = await responsePromise;
  await assert.rejects(readSafeJson(streamed, "bounded", 6), error => error.code === "response_too_large");
  assert.equal(requestSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.equal(cancels, 1);
});

test("JSON reader timeout covers a reader.read that never completes", async () => {
  const hanging = hangingJsonResponse();
  let requestSignal;
  let abortEvents = 0;
  const streamed = await fetchWithTimeout("https://example.invalid/fake", {}, 20, async (_url, options) => {
    requestSignal = options.signal;
    requestSignal.addEventListener("abort", () => { abortEvents += 1; });
    return hanging.response;
  });
  const settled = await settlesWithin(readSafeJson(streamed, "timeout"), 100);
  assert.equal(settled.kind, "rejected");
  assert.equal(settled.error.code, "request_timeout");
  assert.equal(requestSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.equal(hanging.cancelled(), 1);
  hanging.releasePending.resolve({ done: true });
});

test("abort after headers but before body read still cancels the available reader once", async () => {
  const lifecycle = new AbortController();
  const hanging = hangingJsonResponse();
  let requestSignal;
  let abortEvents = 0;
  const streamed = await fetchWithTimeout("https://example.invalid/fake", { signal: lifecycle.signal }, 60_000, async (_url, options) => {
    requestSignal = options.signal;
    requestSignal.addEventListener("abort", () => { abortEvents += 1; });
    return hanging.response;
  });
  lifecycle.abort();
  lifecycle.abort();
  const settled = await settlesWithin(readSafeJson(streamed, "cancelled"));
  assert.equal(settled.kind, "rejected");
  assert.equal(settled.error.code, "request_cancelled");
  assert.equal(requestSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.equal(hanging.cancelled(), 1);
});

for (const [name, chunks] of [
  ["empty body cancel-to-done", []],
  ["partial JSON cancel-to-done", ['{"partial":']],
  ["complete JSON queued before cancellation", ['{"ready":true}']],
]) {
  test(`native Response ${name} remains request_cancelled when abort lands before getReader`, async () => {
    const lifecycle = new AbortController();
    const native = nativePendingResponse(200, chunks);
    let requestSignal;
    let abortEvents = 0;
    const streamed = await fetchWithTimeout("https://example.invalid/native", { signal: lifecycle.signal }, 60_000, async (_url, options) => {
      requestSignal = options.signal;
      requestSignal.addEventListener("abort", () => { abortEvents += 1; });
      return native.response;
    });
    lifecycle.abort();
    lifecycle.abort();
    const settled = await settlesWithin(readSafeJson(streamed, "native_cancel"));
    assert.equal(settled.kind, "rejected");
    assert.equal(settled.error.code, "request_cancelled");
    assert.equal(requestSignal.aborted, true);
    assert.equal(abortEvents, 1);
    assert.equal(native.cancels(), 1);
    assert.equal(native.response.body.locked, false);
  });
}

test("native uncancelled 200 response with a genuinely empty body keeps the existing empty-object contract", async () => {
  let requestSignal;
  const streamed = await fetchWithTimeout("https://example.invalid/empty", {}, 60_000, async (_url, options) => {
    requestSignal = options.signal;
    return new Response(null, { status: 200 });
  });
  assert.deepEqual(await readSafeJson(streamed, "empty"), {});
  assert.equal(requestSignal.aborted, false);
});

test("401 native body cancellation never starts token refresh or retry", async () => {
  const lifecycle = new AbortController();
  const pending401 = nativePendingResponse(401, ['{"error":']);
  let fetches = 0;
  let apiSignal;
  let apiAbortEvents = 0;
  const client = createQqApiClient({
    appId: "fictional-app", secret: "FICTIONAL_SECRET",
    apiBase: "https://api.bot.qq.com", tokenBase: "https://bots.qq.com", timeoutMs: 60_000,
    fetchImpl: async (url, options) => {
      fetches += 1;
      if (String(url).includes("getAppAccessToken")) {
        return new Response(JSON.stringify({ access_token: "FICTIONAL_TOKEN", expires_in: 7200 }), { status: 200 });
      }
      apiSignal = options.signal;
      apiSignal.addEventListener("abort", () => { apiAbortEvents += 1; });
      return pending401.response;
    },
  });
  const pending = client.request("GET", "/gateway", undefined, true, lifecycle.signal);
  while (!apiSignal || !pending401.response.body.locked) await Promise.resolve();
  lifecycle.abort();
  const settled = await settlesWithin(pending);
  assert.equal(settled.kind, "rejected");
  assert.equal(settled.error.code, "request_cancelled");
  assert.equal(fetches, 2);
  assert.equal(apiSignal.aborted, true);
  assert.equal(apiAbortEvents, 1);
  assert.equal(pending401.cancels(), 1);
  assert.equal(pending401.response.body.locked, false);
});

test("invalid, failed, oversized, and timed-out 401 bodies never refresh a token", async t => {
  const cases = [
    ["invalid", () => new Response("not-json", { status: 401 }), "invalid_response", 60_000],
    ["reader_error", () => new Response(new ReadableStream({
      pull(controller) { controller.error(new Error("Authorization: FICTIONAL_PRIVATE_BODY")); },
    }), { status: 401 }), "response_read_failed", 60_000],
    ["oversized", () => new Response(new ReadableStream({}), {
      status: 401,
      headers: { "Content-Length": String(4 * 1024 * 1024 + 1) },
    }), "response_too_large", 60_000],
    ["timeout", () => nativePendingResponse(401, ['{"error":']).response, "request_timeout", 20],
  ];
  for (const [name, makeResponse, expectedCode, timeoutMs] of cases) {
    await t.test(name, async () => {
      let fetches = 0;
      const client = createQqApiClient({
        appId: "fictional-app", secret: "FICTIONAL_SECRET",
        apiBase: "https://api.bot.qq.com", tokenBase: "https://bots.qq.com", timeoutMs,
        fetchImpl: async url => {
          fetches += 1;
          if (String(url).includes("getAppAccessToken")) {
            return new Response(JSON.stringify({ access_token: "FICTIONAL_TOKEN", expires_in: 7200 }), { status: 200 });
          }
          return makeResponse();
        },
      });
      const settled = await settlesWithin(client.request("GET", "/gateway"), 100);
      assert.equal(settled.kind, "rejected");
      assert.equal(settled.error.code, expectedCode);
      assert.equal(fetches, 2);
      assert.equal(String(settled.error).includes("FICTIONAL_PRIVATE_BODY"), false);
    });
  }
});

test("complete bounded native 401 refreshes once and retries only once", async () => {
  let tokenCalls = 0;
  let apiCalls = 0;
  const client = createQqApiClient({
    appId: "fictional-app", secret: "FICTIONAL_SECRET",
    apiBase: "https://api.bot.qq.com", tokenBase: "https://bots.qq.com", timeoutMs: 60_000,
    fetchImpl: async url => {
      if (String(url).includes("getAppAccessToken")) {
        tokenCalls += 1;
        return new Response(JSON.stringify({ access_token: `FICTIONAL_TOKEN_${tokenCalls}`, expires_in: 7200 }), { status: 200 });
      }
      apiCalls += 1;
      return new Response(JSON.stringify({ error: "fictional unauthorized" }), { status: 401 });
    },
  });
  await assert.rejects(client.request("GET", "/gateway"), error => error.code === "http_401");
  assert.equal(tokenCalls, 2);
  assert.equal(apiCalls, 2);
});

test("an initially aborted lifecycle performs zero token or API fetches", async () => {
  const lifecycle = new AbortController();
  lifecycle.abort();
  let fetches = 0;
  const client = createQqApiClient({
    appId: "fictional-app", secret: "FICTIONAL_SECRET",
    apiBase: "https://api.bot.qq.com", tokenBase: "https://bots.qq.com",
    fetchImpl: async () => { fetches += 1; return new Response("{}", { status: 200 }); },
  });
  await assert.rejects(client.getAccessToken(lifecycle.signal), error => error.code === "request_cancelled");
  await assert.rejects(client.request("GET", "/gateway", undefined, true, lifecycle.signal), error => error.code === "request_cancelled");
  assert.equal(fetches, 0);
});

test("abort during native token refresh prevents the second API request", async () => {
  const lifecycle = new AbortController();
  const pendingRefresh = nativePendingResponse(200, ['{"access_token":']);
  let tokenCalls = 0;
  let apiCalls = 0;
  let refreshSignal;
  let refreshAbortEvents = 0;
  const client = createQqApiClient({
    appId: "fictional-app", secret: "FICTIONAL_SECRET",
    apiBase: "https://api.bot.qq.com", tokenBase: "https://bots.qq.com", timeoutMs: 60_000,
    fetchImpl: async (url, options) => {
      if (String(url).includes("getAppAccessToken")) {
        tokenCalls += 1;
        if (tokenCalls === 1) {
          return new Response(JSON.stringify({ access_token: "FICTIONAL_TOKEN", expires_in: 7200 }), { status: 200 });
        }
        refreshSignal = options.signal;
        refreshSignal.addEventListener("abort", () => { refreshAbortEvents += 1; });
        return pendingRefresh.response;
      }
      apiCalls += 1;
      return new Response(JSON.stringify({ error: "fictional unauthorized" }), { status: 401 });
    },
  });
  const pending = client.request("GET", "/gateway", undefined, true, lifecycle.signal);
  while (!refreshSignal || !pendingRefresh.response.body.locked) await Promise.resolve();
  lifecycle.abort();
  const settled = await settlesWithin(pending);
  assert.equal(settled.kind, "rejected");
  assert.equal(settled.error.code, "request_cancelled");
  assert.equal(tokenCalls, 2);
  assert.equal(apiCalls, 1);
  assert.equal(refreshSignal.aborted, true);
  assert.equal(refreshAbortEvents, 1);
  assert.equal(pendingRefresh.cancels(), 1);
  assert.equal(pendingRefresh.response.body.locked, false);
});

test("JSON reader errors are sanitized and late completion cannot create an unhandled rejection", async () => {
  let reads = 0;
  let requestSignal;
  let abortEvents = 0;
  let cancels = 0;
  const streamed = await fetchWithTimeout("https://example.invalid/fake", {}, 60_000, async (_url, options) => {
    requestSignal = options.signal;
    requestSignal.addEventListener("abort", () => { abortEvents += 1; });
    return {
      ok: true,
      status: 200,
      body: { getReader: () => ({
        read: async () => {
          reads += 1;
          if (reads === 1) throw new Error("Authorization: FICTIONAL_SECRET private body");
          return { done: true };
        },
        cancel: async () => { cancels += 1; },
        releaseLock() {},
      }) },
    };
  });
  await assert.rejects(readSafeJson(streamed, "reader"), error => {
    assert.equal(error.code, "response_read_failed");
    assert.equal(String(error).includes("FICTIONAL_SECRET"), false);
    return true;
  });
  assert.equal(requestSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.equal(cancels, 1);
});

test("bridge lifecycle cancels an in-flight Project Kei JSON body before any QQ reply", async () => {
  const lifecycle = new AbortController();
  const hanging = hangingJsonResponse();
  let requestSignal;
  let abortEvents = 0;
  let sends = 0;
  const handler = createBridgeMessageHandler({
    allowedUsers: new Set(["fictional-user"]),
    qqRequest: async () => { sends += 1; },
    projectKeiUrl: "http://127.0.0.1:8000",
    lifecycleSignal: lifecycle.signal,
    fetchImpl: async (_url, options) => {
      requestSignal = options.signal;
      requestSignal.addEventListener("abort", () => { abortEvents += 1; });
      return hanging.response;
    },
    logger: { info() {}, warn() {}, error() {} },
  });
  const handling = handler.handleDispatch("C2C_MESSAGE_CREATE", {
    id: "fictional-message", content: "hello", author: { user_openid: "fictional-user" },
  });
  while (!requestSignal || hanging.reads() < 2) await Promise.resolve();
  lifecycle.abort();
  const settled = await settlesWithin(handling);
  assert.notEqual(settled.kind, "timeout");
  assert.equal(requestSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.equal(hanging.cancelled(), 1);
  assert.equal(sends, 0);
  hanging.releasePending.reject(new Error("late private reply body"));
});

test("upstream error bodies are never included in thrown errors", async () => {
  await assert.rejects(readSafeJson(response(500, { token: "FAKE_TOKEN", openid: "FAKE_OPENID", Authorization: "FAKE_AUTH" }), "project_kei"), error => {
    const serialized = `${error.name}:${error.message}`;
    assert.equal(serialized.includes("FAKE_TOKEN"), false);
    assert.equal(serialized.includes("FAKE_OPENID"), false);
    assert.equal(serialized.includes("FAKE_AUTH"), false);
    return true;
  });
});

test("oversized input is rejected before Project Kei or QQ", async () => {
  let calls = 0;
  const handler = createBridgeMessageHandler({
    allowedUsers: new Set(["fictional-openid"]), qqRequest: async () => { calls += 1; }, projectKeiUrl: "http://127.0.0.1:8000",
    fetchImpl: async () => { calls += 1; return response(200, { text: "reply" }); }, maxInputChars: 16,
    logger: { info() {}, warn() {}, error() {} },
  });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { id: "m1", content: "x".repeat(17), author: { user_openid: "fictional-openid" } });
  assert.equal(calls, 0);
});

test("briefing Markdown bounds and redacts warnings, URLs, and internal paths", () => {
  const markdown = formatDailyBriefingMarkdown({
    date: "2026-07-22",
    script: "safe summary",
    warnings: ["Authorization: Bearer FAKE_AUTH Cookie=FAKE_COOKIE C:\\private\\cache.json"],
    items: [{ category: "development", title: "title", summary: "Token=FAKE_TOKEN", url: "https://example.invalid/item?access_token=FAKE_QUERY", author: "source" }],
  }, 1000);
  for (const secret of ["FAKE_AUTH", "FAKE_COOKIE", "FAKE_TOKEN", "FAKE_QUERY", "private\\cache.json"]) assert.equal(markdown.includes(secret), false);
  assert.ok(markdown.length <= 1000);
});
