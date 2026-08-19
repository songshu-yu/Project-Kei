# Project Kei QQ Bridge module

This package contains only the versioned QQ bridge program and its dashboard
entrypoint. QQ credentials, the C2C allowlist, schedules, delivery markers,
caches, logs and other personal data are not part of the package.

The immutable installed package is never modified after verification. The
explicit QQ setup profile copies the reviewed `sidecar/` allowlist to the
Core-derived dependency deployment root, runs locked dependency setup there,
and atomically publishes a strict `.project-kei-deployment.json` marker. The
Core-registered `qq_bridge` adapter accepts only the current deployment
descriptor and starts the fixed `<dependency-root>/src/index.mjs` entry. It
uses the existing persistent local configuration and state roots:

- `server/qq_bridge/.env`
- `server/qq_bridge/data/`

Updating or uninstalling the program package does not remove either path.
Readiness may check that `.env` exists, but it does not read or return its
values. The module-owned local configuration form can explicitly create or
update only `QQBOT_APPID` and `QQBOT_SECRET` at that fixed path. It preserves
other fields, writes atomically, never returns the Secret and never stores
credentials in browser storage. A blank Secret preserves an existing value.

The package intentionally contains `package.json` and `package-lock.json` but
not `node_modules` or the deployment marker. Node.js and the locked
dependencies are prepared only by the explicit Project Kei QQ setup profile.
Installing, enabling or opening the dashboard never runs npm. A missing,
partial, stale or tampered deployment fails closed with a finite non-secret
readiness state and never falls back to the source tree. Missing Node.js,
configuration or locked dependencies does not affect Core or other modules.

The dashboard can read non-secret readiness, save the two QQ credential fields,
explicitly opt in or out of `QQBOT_REPLY_WITH_VOICE`,
declare `QQBOT_MEDIA_UPLOAD_CAPABILITY` as
`unknown|available|unavailable|denied` (default `unknown`; an operator
declaration rather than an automatic permission probe),
and edit the two existing schedules through `/api/v1/qq-control`. Credential
saves require a real loopback client and exact trusted browser Origin. It
offers an explicit start action and does not invent a public stop action. QQ
Gateway, token and C2C traffic only begin after the sidecar is explicitly
enabled or started.

Voice replies default off and are available only when the installed voice
module reports the fixed `qq_c2c_voice_v1`/`audio/silk` profile ready and a
separate non-secret QQ media-upload capability is explicitly `available`.
Unknown capability fails closed. Eligible ordinary conversation replies send
text first, then request one bounded final utterance and use QQ's controlled
C2C multipart upload to obtain `file_info`; menus, errors, business actions and
all scheduled messages remain text-only. The sidecar never segments text,
joins PCM/WAV, chooses codec parameters or persists audio/file metadata.
The synthesis request, response headers, streamed body and final validation
share one deadline. Actual bytes are counted while streaming; the reader is
cancelled immediately above 8 MiB, including when Content-Length is deceptive.

Version 0.1.10 separates operating-system process health from QQ Gateway
health. The dashboard reports the process and the redacted Gateway state
independently, and calls the bridge connected only after both READY and a
heartbeat acknowledgement. The sidecar writes one strict, atomic, short-lived
`gateway_status.json` snapshot containing only process/session identity and
finite connection diagnostics. C2C replay identity combines `msg_id` with the
official `msg_seq` and/or `message_scene.ext.msg_idx`; only bounded text types
0 and 103 are routed after allowlist validation.

Version 0.1.11 installs the owned stdin shutdown channel before any asynchronous
startup refresh. Daily/life schedule bootstrap, token acquisition, Gateway URL
acquisition and WebSocket bootstrap share one abortable lifecycle. Stop settles
the caller-facing startup promises immediately even when a provider ignores
cancellation, while real local/QQ fetches also consume the AbortSignal. Late
provider or socket events cannot recreate status, timers, sockets or dispatch.
Repeated stop is idempotent and remains limited to the adapter-owned process.

Version 0.1.12 keeps that same cancellation context alive through bounded JSON
body consumption. Token, Gateway URL, QQ OpenAPI, Project Kei and schedule bodies
are streamed with a 4 MiB actual-byte cap; timeout, shutdown, reader failure and
overflow abort the request and cancel the body without exposing upstream content.

Version 0.1.13 makes cancellation authoritative before body reader creation,
after every read settlement and before JSON return. Native stream cancel-to-done
cannot become an empty successful response. A QQ 401 can refresh once only after
its bounded valid body has fully settled as `http_401` while lifecycle remains
active; cancelled, invalid, failed, oversized or timed-out bodies never refresh.

Version 0.1.14 reports only finite, redacted Gateway phase codes for token
request/rejection/invalid response, Gateway discovery request/rejection/invalid
response or URL validation, WebSocket construction/transport/early close, and
Hello/READY timeouts. Process liveness remains distinct from Gateway readiness;
all failures retain bounded reconnect and shutdown generation isolation.

Version 0.1.15 sends Identify after Hello but defers the first heartbeat until
the first valid READY. It then sends exactly one immediate heartbeat and starts
the interval; only its ACK can enable dispatch and `gateway_ready`. Pre-READY or
unsolicited ACK, READY-before-Hello, duplicate Hello/READY and late events remain
fail-closed and cannot duplicate the initial heartbeat or revive a stopped client.

Version 0.1.16 advances the heartbeat sequence only for an accepted first READY
or an op-0 dispatch that is actually released after READY plus heartbeat ACK.
Ignored early/duplicate events, unsolicited ACK, pre-ACK dispatch, reconnect or
invalid payloads never alter the acknowledged sequence; ACK itself does not
consume a non-standard sequence value.

Version 0.1.17 preserves `last_error_code: null` for a healthy Gateway snapshot.

Version 0.1.18 uses the Tencent official SDK's bounded direct-media contract for ordinary
QQ voice replies: `/files` receives fixed `file_type=3`, `srv_send_msg=false`, and the
validated Silk bytes as `file_data`; the returned `file_info` is then sent once with
`msg_type=7`. It does not use the large-file chunk API for these replies.

Version 0.1.20 records only a finite, redacted result code and timestamp for the most
recent ordinary QQ voice attempt. Core status can distinguish synthesis, direct upload,
upload metadata, and final media-message stages without exposing message text, OpenID,
QQ response bodies, URLs, tokens, or credentials.

Version 0.1.21 follows the official C2C rich-media response contract: `file_info` remains
mandatory and bounded, while `ttl` may be omitted or zero and is validated only when
present. The final `msg_type=7` request includes the currently required single-space
`content` compatibility field. Neither field is logged or persisted.

Version 0.1.23 keeps sidecar launch explicitly user initiated and adds an explicit,
confirmed stop action. The stop action is available only for the process owned by the
current Core adapter; externally started Node processes are reported but never killed.

Version 0.1.24 keeps that explicit stop action available after a normal Core restart.
The sidecar publishes only a bounded PID and random generation marker. A new Core must
match that PID to the fixed reviewed `src/index.mjs` entry before it may write one fresh,
generation-bound shutdown request. The sidecar rejects stale, replayed, malformed,
oversized and symbolic-link requests; no broad Node or port-based termination is used.

Version 0.1.22 made sidecar launch explicitly user initiated. Enabling, installing or
updating the module, starting Core, loading or expanding the dashboard, and refreshing
status do not create a Node process. The accessible QQ avatar and the visible start
button reuse the same fixed local `POST /api/v1/qq-control/start` action; repeated or
concurrent requests remain single-instance, and a stopped bridge waits for the next click.
READY plus a valid heartbeat ACK therefore exposes no failure hint, while known
finite non-null codes remain available and unknown or sensitive values still
collapse to `gateway_failed`.
