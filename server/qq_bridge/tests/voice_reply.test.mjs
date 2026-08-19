import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { createBridgeMessageHandler } from "../src/bridge_core.mjs";
import { createVoiceReplyController } from "../src/voice_reply.mjs";

const USER = "fictional-user-openid";
const SILK = Buffer.concat([Buffer.from("#!SILK_V3", "ascii"), Buffer.from([1, 2, 3, 4])]);

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function silkResponse(overrides = {}) {
  const audio = overrides.audio || SILK;
  return new Response(audio, {
    status: overrides.status || 200,
    headers: {
      "Content-Type": overrides.contentType || "audio/silk",
      "Content-Length": String(overrides.contentLength ?? audio.length),
      "X-Kei-Audio-Final": overrides.final || "true",
      "X-Kei-Audio-Profile": overrides.profile || "qq_c2c_voice_v1",
      "X-Kei-Utterance-Id": overrides.utteranceId || "utterance_fake_0001",
      ...(overrides.omitDuration ? {} : { "X-Kei-Audio-Duration-Ms": String(overrides.durationMs || 1200) }),
    },
  });
}

function readyConfiguration(overrides = {}) {
  return {
    reply_with_voice: true,
    voice_reply_available: true,
    voice_profile: "qq_c2c_voice_v1",
    voice_profile_ready: true,
    qq_media_upload_capability: "available",
    ...overrides,
  };
}

function fixture(options = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-voice-"));
  const calls = { fetch: [], qq: [] };
  const fetchImpl = options.fetchImpl || (async (url, request = {}) => {
    calls.fetch.push({ url: String(url), method: request.method || "GET", request });
    if (String(url).endsWith("/api/v1/qq-control/configuration")) {
      return jsonResponse(readyConfiguration(options.configuration));
    }
    if (String(url).endsWith("/api/v1/voice/synthesize")) return options.synthesis || silkResponse();
    if (String(url).startsWith("https://bucket.cos.ap-shanghai.myqcloud.com/")) return new Response(null, { status: 200 });
    throw new Error("unexpected fake URL");
  });
  const qqRequest = options.qqRequest || (async (method, requestPath, body) => {
    calls.qq.push({ method, path: requestPath, body });
    if (requestPath.endsWith("/files")) return options.fileResult ?? { file_info: "FAKE_FILE_INFO", ttl: 300 };
    if (requestPath.endsWith("/messages")) return { id: "fake-message" };
    throw new Error("unexpected fake QQ path");
  });
  const controller = createVoiceReplyController({
    enabled: options.enabled ?? true,
    allowedUsers: options.allowedUsers || new Set([USER]),
    projectKeiUrl: "http://127.0.0.1:8000",
    qqRequest,
    fetchImpl,
    statePath: path.join(root, "voice_reply_delivery_state.json"),
    timeoutMs: options.timeoutMs ?? 45_000,
    logger: { info() {}, warn() {}, error() {} },
  });
  return { root, calls, controller, fetchImpl, qqRequest };
}

test("voice replies default off with zero readiness, synthesis, upload, send, or state write", async () => {
  const value = fixture({ enabled: false });
  const result = await value.controller.deliver({ user: USER, inboundId: "message-1", text: "这是普通回复。" });
  assert.equal(result.sent, false);
  assert.equal(value.calls.fetch.length, 0);
  assert.equal(value.calls.qq.length, 0);
  assert.equal(fs.existsSync(path.join(value.root, "voice_reply_delivery_state.json")), false);
});

test("one eligible reply performs one synthesis, official direct C2C upload, and one media send", async () => {
  const value = fixture();
  const result = await value.controller.deliver({ user: USER, inboundId: "message-2", text: "老师，今天也稳稳向前走。" });
  assert.equal(result.sent, true);
  assert.equal(value.calls.fetch.filter(call => call.url.endsWith("/api/v1/voice/synthesize")).length, 1);
  assert.deepEqual(value.calls.qq.map(call => call.path.split("/").at(-1)), [
    "files", "messages",
  ]);
  const upload = value.calls.qq[0];
  assert.equal(upload.method, "POST");
  assert.deepEqual(Object.keys(upload.body).sort(), ["file_data", "file_type", "srv_send_msg"]);
  assert.equal(upload.body.file_type, 3);
  assert.equal(upload.body.srv_send_msg, false);
  assert.deepEqual(Buffer.from(upload.body.file_data, "base64"), SILK);
  assert.equal(value.calls.qq.at(-1).body.content, " ");
  assert.equal(value.calls.qq.at(-1).body.msg_type, 7);
  assert.deepEqual(value.calls.qq.at(-1).body.media, { file_info: "FAKE_FILE_INFO" });
  const synthesis = value.calls.fetch.find(call => call.url.endsWith("/api/v1/voice/synthesize"));
  assert.deepEqual(JSON.parse(synthesis.request.body), { purpose: "qq_reply", text: "老师，今天也稳稳向前走。" });
  assert.match(synthesis.request.headers["Idempotency-Key"], /^qqv-[a-f0-9]{32}$/);
  const persisted = fs.readFileSync(path.join(value.root, "voice_reply_delivery_state.json"), "utf8");
  for (const forbidden of [USER, "老师", "FAKE_FILE_INFO", "myqcloud", "signature"]) assert.equal(persisted.includes(forbidden), false);
});

test("direct upload sends no path, URL, filename, hash, or chunk-control fields", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-voice-parts-"));
  const qqCalls = [];
  const putSizes = [];
  const qqRequest = async (method, requestPath, body) => {
    qqCalls.push({ method, path: requestPath, body });
    if (requestPath.endsWith("/upload_prepare")) return {
      upload_id: "upload_parts_0001",
      block_size: "7",
      parts: [
        { index: 0, block_size: "7", presigned_url: "https://a.cos.ap-shanghai.myqcloud.com/part0?signature=fake" },
        { index: 1, block_size: String(SILK.length - 7), presigned_url: "https://a.cos.ap-shanghai.myqcloud.com/part1?signature=fake" },
      ],
    };
    if (requestPath.endsWith("/upload_part_finish")) return {};
    if (requestPath.endsWith("/files")) return { file_info: "FAKE_FILE_INFO", ttl: 60 };
    if (requestPath.endsWith("/messages")) return {};
    throw new Error("unexpected QQ path");
  };
  const controller = createVoiceReplyController({
    enabled: true,
    allowedUsers: new Set([USER]),
    projectKeiUrl: "http://127.0.0.1:8000",
    statePath: path.join(root, "state.json"),
    qqRequest,
    fetchImpl: async (url, request = {}) => {
      if (String(url).endsWith("/configuration")) return jsonResponse(readyConfiguration());
      if (String(url).endsWith("/synthesize")) return silkResponse();
      if (request.method === "PUT") {
        putSizes.push(Buffer.from(request.body).length);
        return new Response(null, { status: 200 });
      }
      throw new Error("unexpected URL");
    },
  });
  const result = await controller.deliver({ user: USER, inboundId: "multipart", text: "分片仍保持顺序。" });
  assert.equal(result.sent, true);
  assert.deepEqual(putSizes, []);
  const upload = qqCalls.find(call => call.path.endsWith("/files"));
  assert.deepEqual(Object.keys(upload.body).sort(), ["file_data", "file_type", "srv_send_msg"]);
  assert.deepEqual(Buffer.from(upload.body.file_data, "base64"), SILK);
  for (const forbidden of ["file_name", "upload_id", "presigned_url", "md5", "sha1", "part_index"]) {
    assert.equal(Object.hasOwn(upload.body, forbidden), false);
  }
  assert.equal(qqCalls.filter(call => call.path.endsWith("/messages")).length, 1);
});

test("readiness unknown, profile unavailable, and allowlist rejection fail before synthesis", async () => {
  for (const configuration of [
    { qq_media_upload_capability: "unknown", voice_reply_available: false },
    { voice_profile_ready: false, voice_reply_available: false },
  ]) {
    const value = fixture({ configuration });
    const result = await value.controller.deliver({ user: USER, inboundId: cryptoRandom(), text: "有意义的回复。" });
    assert.equal(result.sent, false);
    assert.equal(value.calls.fetch.filter(call => call.url.endsWith("/api/v1/voice/synthesize")).length, 0);
    assert.equal(value.calls.qq.length, 0);
  }
  const blocked = fixture({ allowedUsers: new Set(["another-fictional-user"]) });
  await blocked.controller.deliver({ user: USER, inboundId: "blocked", text: "不会合成。" });
  assert.equal(blocked.calls.fetch.length, 0);
  assert.equal(blocked.calls.qq.length, 0);
});

function cryptoRandom() {
  return `message-${Math.random().toString(16).slice(2)}`;
}

test("invalid synth metadata and audio always preserve text-only behavior", async () => {
  const invalid = [
    { contentType: "audio/wav" },
    { profile: "arbitrary" },
    { final: "false" },
    { omitDuration: true },
    { durationMs: 60001 },
    { contentLength: SILK.length + 1 },
    { audio: Buffer.from("not-silk") },
  ];
  for (const override of invalid) {
    const value = fixture({ synthesis: silkResponse(override) });
    const result = await value.controller.deliver({ user: USER, inboundId: cryptoRandom(), text: "仍然保留文字。" });
    assert.equal(result.sent, false);
    assert.equal(value.calls.qq.length, 0);
  }
});

test("voice and QQ failures never expose upstream bodies, identities, or authorization", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-voice-redaction-"));
  const logs = [];
  const controller = createVoiceReplyController({
    enabled: true,
    allowedUsers: new Set([USER]),
    projectKeiUrl: "http://127.0.0.1:8000",
    statePath: path.join(root, "state.json"),
    qqRequest: async () => { throw new Error("should not upload"); },
    fetchImpl: async url => String(url).endsWith("/configuration")
      ? jsonResponse(readyConfiguration())
      : new Response("Authorization: Bearer FAKE_TOKEN " + USER, { status: 500 }),
    logger: { info: value => logs.push(value), warn: value => logs.push(value), error: value => logs.push(value) },
  });
  const result = await controller.deliver({ user: USER, inboundId: "redaction", text: "保留文字。" });
  assert.equal(result.sent, false);
  const serialized = JSON.stringify(logs);
  for (const forbidden of ["FAKE_TOKEN", USER, "Authorization", "保留文字"]) assert.equal(serialized.includes(forbidden), false);
});

test("direct upload response must contain bounded file_info before media send", async () => {
  for (const fileResult of [
    {},
    { file_info: "", ttl: 300 },
    { file_info: "x".repeat(4097), ttl: 300 },
    { file_info: "ok", ttl: -1 },
    { file_info: "ok", ttl: 1.5 },
    { file_info: "ok", ttl: Number.MAX_SAFE_INTEGER + 1 },
  ]) {
    const value = fixture({ fileResult });
    const result = await value.controller.deliver({ user: USER, inboundId: cryptoRandom(), text: "安全上传。" });
    assert.equal(result.sent, false);
    assert.equal(result.code, "voice_file_info_invalid");
    assert.equal(value.calls.qq.some(call => call.path.endsWith("/files")), true);
    assert.equal(value.calls.qq.some(call => call.path.endsWith("/messages")), false);
  }
});

test("direct upload accepts an omitted or long-lived ttl and sends the required media content", async () => {
  for (const fileResult of [
    { file_info: "FAKE_FILE_INFO" },
    { file_info: "FAKE_FILE_INFO", ttl: 0 },
    { file_info: "FAKE_FILE_INFO", ttl: 86_400 },
  ]) {
    const value = fixture({ fileResult });
    const result = await value.controller.deliver({
      user: USER,
      inboundId: "fictional-message-id",
      text: "hello",
    });
    assert.equal(result.code, "voice_sent");
    const message = value.calls.qq.at(-1);
    assert.equal(message.body.content, " ");
    assert.equal(message.body.msg_type, 7);
    assert.deepEqual(message.body.media, { file_info: "FAKE_FILE_INFO" });
  }
});

test("upload and media-send failures expose only fixed voice stage codes", async () => {
  const uploadFailure = fixture({
    qqRequest: async () => {
      throw Object.assign(new Error("PRIVATE_UPLOAD_BODY"), { code: "http_400" });
    },
  });
  const uploadResult = await uploadFailure.controller.deliver({
    user: USER,
    inboundId: "upload-failure",
    text: "upload stage",
  });
  assert.deepEqual(uploadResult, { sent: false, code: "voice_upload_failed" });

  const sendFailure = fixture({
    qqRequest: async (_method, requestPath) => {
      if (requestPath.endsWith("/files")) return { file_info: "FAKE_FILE_INFO", ttl: 300 };
      throw Object.assign(new Error("PRIVATE_MESSAGE_BODY"), { code: "http_400" });
    },
  });
  const sendResult = await sendFailure.controller.deliver({
    user: USER,
    inboundId: "message-failure",
    text: "message stage",
  });
  assert.deepEqual(sendResult, { sent: false, code: "voice_message_failed" });
  assert.equal(JSON.stringify([uploadResult, sendResult]).includes("PRIVATE_"), false);
});

test("duplicate and restart delivery markers prevent a second synthesis or send", async () => {
  const value = fixture();
  const delivery = { user: USER, inboundId: "stable-message", text: "只生成一次。" };
  const first = await value.controller.deliver(delivery);
  const duplicate = await value.controller.deliver(delivery);
  assert.equal(first.sent, true);
  assert.equal(duplicate.sent, false);
  const restarted = createVoiceReplyController({
    enabled: true,
    allowedUsers: new Set([USER]),
    projectKeiUrl: "http://127.0.0.1:8000",
    qqRequest: value.qqRequest,
    fetchImpl: value.fetchImpl,
    statePath: path.join(value.root, "voice_reply_delivery_state.json"),
    allowedUploadHostSuffixes: [".myqcloud.com"],
  });
  const replay = await restarted.deliver(delivery);
  assert.equal(replay.sent, false);
  assert.equal(value.calls.fetch.filter(call => call.url.endsWith("/api/v1/voice/synthesize")).length, 1);
  assert.equal(value.calls.qq.filter(call => call.path.endsWith("/messages")).length, 1);
});

test("concurrent delivery attempts claim once before paid synthesis", async () => {
  const value = fixture();
  const delivery = { user: USER, inboundId: "concurrent-message", text: "并发也只生成一次。" };
  const [first, second] = await Promise.all([
    value.controller.deliver(delivery),
    value.controller.deliver(delivery),
  ]);
  assert.equal(Number(first.sent) + Number(second.sent), 1);
  assert.equal(value.calls.fetch.filter(call => call.url.endsWith("/api/v1/voice/synthesize")).length, 1);
  assert.equal(value.calls.qq.filter(call => call.path.endsWith("/messages")).length, 1);
});

test("corrupt delivery state fails closed without overwrite or any network", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kei-qq-voice-corrupt-"));
  const statePath = path.join(root, "voice_reply_delivery_state.json");
  const oldBytes = Buffer.from(JSON.stringify({ version: 1, entries: { [USER]: { status: "sent", Authorization: "FAKE" } } }));
  fs.writeFileSync(statePath, oldBytes);
  let calls = 0;
  const controller = createVoiceReplyController({
    enabled: true,
    allowedUsers: new Set([USER]),
    projectKeiUrl: "http://127.0.0.1:8000",
    qqRequest: async () => { calls += 1; },
    fetchImpl: async () => { calls += 1; return jsonResponse(readyConfiguration()); },
    statePath,
  });
  const result = await controller.deliver({ user: USER, inboundId: "corrupt", text: "不会发送。" });
  assert.equal(result.sent, false);
  assert.equal(calls, 0);
  assert.deepEqual(fs.readFileSync(statePath), oldBytes);
});

test("QQ media send failure is not retried and persisted claim prevents replay", async () => {
  const value = fixture({
    qqRequest: async (method, requestPath, body) => {
      value?.calls.qq.push({ method, path: requestPath, body });
      if (requestPath.endsWith("/upload_prepare")) return {
        upload_id: "upload_fake_0001",
        block_size: String(SILK.length),
        parts: [{ index: 0, block_size: String(SILK.length), presigned_url: "https://bucket.cos.ap-shanghai.myqcloud.com/voice?signature=fake" }],
      };
      if (requestPath.endsWith("/upload_part_finish")) return {};
      if (requestPath.endsWith("/files")) return { file_info: "FAKE_FILE_INFO", ttl: 300 };
      if (requestPath.endsWith("/messages")) throw Object.assign(new Error("FAKE SECRET BODY"), { code: "http_500" });
      throw new Error("unexpected path");
    },
  });
  const delivery = { user: USER, inboundId: "send-failure", text: "文字已经发送。" };
  const first = await value.controller.deliver(delivery);
  const replay = await value.controller.deliver(delivery);
  assert.equal(first.sent, false);
  assert.equal(replay.sent, false);
  assert.equal(value.calls.qq.filter(call => call.path.endsWith("/messages")).length, 1);
  const persisted = fs.readFileSync(path.join(value.root, "voice_reply_delivery_state.json"), "utf8");
  assert.equal(persisted.includes("FAKE SECRET BODY"), false);
  assert.equal(persisted.includes("FAKE_FILE_INFO"), false);
});

test("shutdown during synthesis aborts and never uploads or sends old audio", async () => {
  let synthStarted;
  const started = new Promise(resolve => { synthStarted = resolve; });
  const value = fixture({
    fetchImpl: async (url, request = {}) => {
      if (String(url).endsWith("/api/v1/qq-control/configuration")) return jsonResponse(readyConfiguration());
      if (String(url).endsWith("/api/v1/voice/synthesize")) {
        synthStarted();
        return new Promise((_resolve, reject) => request.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { code: "aborted" }))));
      }
      throw new Error("unexpected URL");
    },
  });
  const delivery = value.controller.deliver({ user: USER, inboundId: "shutdown-message", text: "即将取消。" });
  await started;
  value.controller.stop();
  const result = await delivery;
  assert.equal(result.sent, false);
  assert.equal(value.calls.qq.length, 0);
});

function streamingSilkResponse(stream, contentLength = SILK.length) {
  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "audio/silk",
      "Content-Length": String(contentLength),
      "X-Kei-Audio-Final": "true",
      "X-Kei-Audio-Profile": "qq_c2c_voice_v1",
      "X-Kei-Utterance-Id": "utterance_stream_0001",
      "X-Kei-Audio-Duration-Ms": "1200",
    },
  });
}

test("synthesis deadline covers a body stream that never finishes after headers", async () => {
  let cancelled = 0;
  const hanging = new ReadableStream({ cancel() { cancelled += 1; } });
  const value = fixture({ synthesis: streamingSilkResponse(hanging), timeoutMs: 20 });
  const result = await value.controller.deliver({ user: USER, inboundId: "hung-body", text: "bounded" });
  assert.equal(result.sent, false);
  assert.equal(cancelled, 1);
  assert.equal(value.controller.snapshot().inFlight, 0);
  assert.equal(value.calls.qq.length, 0);
});

test("readiness deadline covers a JSON body stream that never finishes after headers", async () => {
  let cancelled = 0;
  let synthesisCalls = 0;
  const hanging = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('{"reply_with_voice":true'));
    },
    cancel() { cancelled += 1; },
  });
  const value = fixture({
    timeoutMs: 20,
    fetchImpl: async url => {
      if (String(url).endsWith("/api/v1/qq-control/configuration")) {
        return new Response(hanging, {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      synthesisCalls += 1;
      throw new Error("unexpected synthesis");
    },
  });
  const result = await value.controller.deliver({
    user: USER,
    inboundId: "hung-readiness-body",
    text: "bounded",
  });
  assert.equal(result.sent, false);
  assert.equal(cancelled, 1);
  assert.equal(synthesisCalls, 0);
  assert.equal(value.controller.snapshot().inFlight, 0);
  assert.equal(value.calls.qq.length, 0);
});

test("streaming synthesis rejects actual bytes above the cap despite a false content length", async () => {
  let cancelled = 0;
  const chunk = new Uint8Array(4 * 1024 * 1024);
  const oversized = new ReadableStream({
    start(controller) {
      controller.enqueue(chunk);
      controller.enqueue(chunk);
      controller.enqueue(new Uint8Array([1]));
    },
    cancel() { cancelled += 1; },
  });
  const value = fixture({ synthesis: streamingSilkResponse(oversized, 1) });
  const result = await value.controller.deliver({ user: USER, inboundId: "oversized-body", text: "bounded" });
  assert.equal(result.sent, false);
  assert.equal(cancelled, 1);
  assert.equal(value.calls.qq.length, 0);
});

test("shutdown and deadline race during body read clears delivery without later effects", async () => {
  let cancelled = 0;
  const hanging = new ReadableStream({ cancel() { cancelled += 1; } });
  const value = fixture({ synthesis: streamingSilkResponse(hanging), timeoutMs: 25 });
  const delivery = value.controller.deliver({ user: USER, inboundId: "stop-timeout-race", text: "bounded" });
  await new Promise(resolve => setTimeout(resolve, 5));
  value.controller.stop();
  const result = await delivery;
  assert.equal(result.sent, false);
  assert.equal(cancelled, 1);
  assert.equal(value.controller.snapshot().inFlight, 0);
  assert.equal(value.calls.qq.length, 0);
});

test("stream reader failure cancels safely with no upload or media send", async () => {
  let cancelled = 0;
  const broken = new ReadableStream({
    start(controller) {
      controller.enqueue(SILK.subarray(0, 4));
      controller.error(new Error("FAKE_AUTHORIZATION_BODY"));
    },
    cancel() { cancelled += 1; },
  });
  const value = fixture({ synthesis: streamingSilkResponse(broken) });
  const result = await value.controller.deliver({ user: USER, inboundId: "reader-error", text: "bounded" });
  assert.equal(result.sent, false);
  assert.equal(value.calls.qq.length, 0);
  assert.equal(value.controller.snapshot().inFlight, 0);
  assert.ok(cancelled === 0 || cancelled === 1);
});

test("shutdown while final QQ send is pending leaves claimed state and performs no later write", async () => {
  let sendStarted;
  let releaseSend;
  const started = new Promise(resolve => { sendStarted = resolve; });
  const release = new Promise(resolve => { releaseSend = resolve; });
  const value = fixture({
    qqRequest: async (method, requestPath, body) => {
      value.calls.qq.push({ method, path: requestPath, body });
      if (requestPath.endsWith("/upload_prepare")) return {
        upload_id: "upload_fake_0001",
        block_size: String(SILK.length),
        parts: [{ index: 0, block_size: String(SILK.length), presigned_url: "https://bucket.cos.ap-shanghai.myqcloud.com/voice?signature=fake" }],
      };
      if (requestPath.endsWith("/upload_part_finish")) return {};
      if (requestPath.endsWith("/files")) return { file_info: "FAKE_FILE_INFO", ttl: 300 };
      if (requestPath.endsWith("/messages")) {
        sendStarted();
        await release;
        return {};
      }
      throw new Error("unexpected path");
    },
  });
  const delivery = value.controller.deliver({ user: USER, inboundId: "shutdown-final-send", text: "文字已经完成。" });
  await started;
  const statePath = path.join(value.root, "voice_reply_delivery_state.json");
  const claimed = fs.readFileSync(statePath);
  value.controller.stop();
  releaseSend();
  const result = await delivery;
  assert.equal(result.sent, false);
  assert.deepEqual(fs.readFileSync(statePath), claimed);
  assert.equal(JSON.parse(claimed).entries[Object.keys(JSON.parse(claimed).entries)[0]].status, "claimed");
});

test("only ordinary conversation replies invoke the optional voice controller", async () => {
  let voices = 0;
  let conversations = 0;
  const voiceResults = [];
  const handler = createBridgeMessageHandler({
    allowedUsers: new Set([USER]),
    qqRequest: async () => ({}),
    projectKeiUrl: "http://127.0.0.1:8000",
    fetchImpl: async url => {
      if (String(url).endsWith("/api/v1/conversation")) {
        conversations += 1;
        return jsonResponse({ text: "普通聊天回复" });
      }
      if (String(url).endsWith("/api/v1/briefing/today")) return jsonResponse({ ready: true, text: "cached" });
      throw new Error("unexpected API");
    },
    voiceReplies: { deliver: async () => { voices += 1; return { sent: true, code: "voice_sent" }; } },
    onVoiceResult: code => voiceResults.push(code),
    logger: { info() {}, warn() {}, error() {} },
  });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { id: "menu", content: "菜单", author: { user_openid: USER } });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { id: "briefing", content: "每日情报", author: { user_openid: USER } });
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { id: "invalid", content: "专注 abc 鼓励 2", author: { user_openid: USER } });
  const ordinary = { id: "ordinary", content: "聊聊天", author: { user_openid: USER } };
  await handler.handleDispatch("C2C_MESSAGE_CREATE", ordinary);
  await handler.handleDispatch("C2C_MESSAGE_CREATE", ordinary);
  await handler.handleDispatch("C2C_MESSAGE_CREATE", { id: "blocked", content: "聊聊天", author: { user_openid: "blocked-user" } });
  assert.equal(conversations, 1);
  assert.equal(voices, 1);
  assert.deepEqual(voiceResults, ["voice_sent"]);
});
