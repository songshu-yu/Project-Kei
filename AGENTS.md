# Project Kei — Agent Operating Instructions

This repository is a living Windows-local project, not a clean template. Preserve continuity, inspect actual files before making claims, and communicate with the user in Chinese unless asked otherwise.

## Mandatory startup protocol

Before any diagnosis, implementation, Git action, or request for missing context:

1. Read root `README.md` in full.
2. Read this file in full.
3. Read `README.local.md` if it exists. It is deliberately ignored and contains machine-specific paths; do not ask the user for a path already recorded there.
4. Read root `TASKS.md`. If the request maps to a listed `PK-xxx` task, read that complete task file before editing.
5. Run `git status --short`, identify the current branch, and inspect only task-relevant files.
6. Treat uncommitted changes as user-owned unless their source and purpose are clear. In particular, leave `vendor/` untouched unless the user explicitly scopes it.

If a required file is absent or unreadable, say exactly which file is missing and ask the user to provide/download it. Do not invent code, credentials, installed software, remote state, or file contents.

## Project invariants

- Main API: port `8000`; ASR: `8010`; GPT-SoVITS: `9880`.
- Main launcher: root `start.bat` (Core by default); legacy `server/start_*.bat` and `server/qq_bridge/start_qq_bridge.bat` remain compatibility launchers.
- QQ bridge directory uses an underscore: `server/qq_bridge`, never `qq-bridge`.
- Use `apply_patch` for file edits. Do not use destructive Git commands such as `git reset --hard` or `git checkout --`.
- Keep all existing functionality unless the user explicitly authorizes removal or redesign.
- Use `npm.cmd` when PowerShell execution policy blocks `npm.ps1`; do not ask the user to reinstall Node.js merely because of that policy.

## Secrets and local state

Never request, print, place in source, stage, or upload any of the following:

- API keys, QQ App Secret, QQ access token, Bilibili Cookie, `SESSDATA`, `BILI_JCT`, `BILI_BUVID3`;
- `server/.env`, `server/qq_bridge/.env`, or their values;
- any unknown credential, Cookie, Token, cache, model artifact, generated audio, `node_modules`, or QQ runtime state.

Runtime schedules and caches are normally local-only and must not be staged or uploaded unless the user explicitly asks to publish a deliberately sanitized example. The legacy files `server/data/affection_state.json`, `fitness_checkins.json`, `focus_timer.json`, and `memories.json` are already tracked by repository history. Treat them as user-owned data: do not reset, edit, print, or include a changed version in unrelated work. Do not assume they are ignored; changing them to local-only storage requires separate user authorization.

`README.local.md` contains paths only, not secrets. Keep it ignored. When handling the daily briefing, do not treat a Bilibili Cookie as a permanent anti-bot solution; preserve throttling, retry limits, and missing-source cooldown.

## External engines and local model assets

- GPT-SoVITS upstream source and its installation directory are external engine assets, not Project Kei source and not `vendor/`. Do not copy them into this repository.
- Unless the user explicitly scopes an engine diagnosis, upgrade, or provenance audit, agents must not recursively enumerate, search, read, index, or diff an external engine source tree. A path recorded in `README.local.md` is not authorization to scan that tree.
- Ordinary project work may inspect only the project-owned Provider, fixed engine descriptor and path-free local status. It may perform narrowly scoped existence, pinned-version and integrity checks against an explicitly named engine path, but must not inspect model weights, reference-audio contents or recursively enumerate the installation.
- GPT-SoVITS acquisition may accept only the project-owned, total-control-approved HTTPS source and pinned release/commit recorded in the descriptor. Do not add user-supplied Git URLs, download URLs, install commands, PowerShell/BAT input, remote-script pipelines, startup-time downloads, automatic dependency installation or archive-script execution.
- The GPT-SoVITS launcher may read the ignored local engine registration to locate fixed entry files. The actual absolute root stays only in local configuration/`README.local.md`; public README and tracked configuration must remain path-free. Existing installations may be registered without re-downloading, with an explicit unverified integrity state when their original archive was not checked.
- Never stage, upload, automatically move, rename, or repackage local weights, reference audio, Voice Pack configuration, or generated audio. Acquisition must be an explicit user action from an official pinned source, must verify integrity before installation, and must never execute a remote script silently.

## Implementation rules

1. For a requested change, first inspect the actual relevant files and explain the precise files to be changed when approval is required.
2. Keep changes incremental. Avoid speculative refactors, API rewrites, broad formatting churn, or unrelated cleanup.
3. After editing, run proportionate checks and report only checks actually executed:
   - Python: use root `scripts/python.ps1 -m pytest` for the complete classified offline suite and `scripts/python.ps1 -m ruff check server/tests scripts/check_python_test_inventory.py` for the phase-one quality baseline; focused `server/tests/` runs and `py_compile` remain valid while iterating.
   - Node: `node --check` for changed bridge files.
   - Dashboard: compile its `<script>` block with `new Function(...)` after UI changes.
   - Git: `git diff --check` before handoff or publishing.
4. Do not trigger paid LLM calls, real QQ messages, full external collection, or destructive data actions merely to test a code path unless the user explicitly authorizes it.
5. For QQ problems, distinguish platform-backend configuration, client-side rendering/cache behavior, and bridge protocol/code behavior.

## Project task protocol

- `TASKS.md` is the project task index; detailed scope and handoff records live in `tasks/PK-xxx-*.md`.
- One Codex conversation should own one feature task by default. Use `PK-000` for architecture, prioritization, and cross-module interface decisions rather than mixing feature implementation into the control conversation.
- Before starting a listed task, change its state from `待开始` to `进行中` and record the conversation purpose. When implementation and focused tests are complete, use `待集成`; only the control/integration workflow may mark it `已完成`.
- Stay inside the task's responsible paths and data ownership. If completion requires changing another module's contract, stop that expansion, document the required contract in the task file, and route the decision through `PK-000`.
- New modules belong under `server/features/<module>/` with explicit router/service/repository boundaries. Preserve existing routes during migration and prefer `/api/v1/<module>` for new interfaces.
- Every task handoff must update its own work record with actual interfaces, side effects, validations, and remaining issues; chat-only handoffs are incomplete.

## Completion documentation gate

A task may not move to `待集成` or `已完成` until its `## 完成文档门禁` section contains all eight checked keys below. Use `[x]` for both an applied update and a verified non-applicable item; a non-applicable item must include a short reason.

| Key | Required documentation action |
|---|---|
| `TASK_RECORD` | Always update the matching `tasks/PK-xxx-*.md` work record with delivered behavior, interfaces, side effects, tests, and remaining issues. |
| `TASKS_BOARD` | Always synchronize task status, title, priority, and dependencies in `TASKS.md`. |
| `PUBLIC_README` | Update root `README.md` when user-visible behavior, endpoints, configuration, restart requirements, data effects, tests, or limitations changed; otherwise record why not applicable. |
| `MODULE_CATALOG` | Update the `/api/v1/modules` catalog when module/task mapping, current endpoints, target namespace, process boundary, or migration status changed; otherwise record why not applicable. |
| `ARCHITECTURE_DOCS` | Update `docs/architecture/` or a task-linked specialist document when module boundaries, dependencies, manifests, lifecycle, or protocols changed; otherwise record why not applicable. |
| `LOCAL_README` | Update `README.local.md` only for verified local paths, launchers, interpreters, ports, or environment locations; otherwise explicitly mark no local change. Never stage this file. |
| `AGENT_RULES` | Update `AGENTS.md` only when workflow, safety, validation, documentation, or Git policy changed; otherwise record why not applicable. |
| `VALIDATION` | Record the exact checks actually run and their results in the task file, including `git diff --check`. |

Do not duplicate the full feature description into every document. Each file owns the information listed above. Run `.\scripts\python.ps1 ..\scripts\check_task_docs.py` from the repository root before changing a task to `待集成`/`已完成`, before integration handoff, and before Git publication. A failing documentation check means the task is not complete.

## Dashboard rules

- Preserve existing element IDs and endpoint behavior unless the task requires a compatible change.
- Each feature panel must remain independently expandable/collapsible; do not reintroduce a permanently flat dashboard.
- The browser may store only UI state such as collapsed panels. Never put source lists, credentials, cookies, tokens, or API keys in browser storage.
- Daily briefing target management is for people/IDs/repositories. Advanced arXiv topic rules and RSS rules remain separate unless the user explicitly expands that scope.

## Daily briefing and QQ rules

- `GET /briefing/today?fetch=true&rewrite=true&cache=true&refresh=false` is the normal collection/cache route.
- Current-day cache reuse is intentional. Do not make a source-list save silently trigger a new Bilibili collection.
- When a user explicitly wants a fresh result, use an explicit confirmation and `refresh=true` rather than deleting cache behind their back.
- QQ private-chat requests for “每日情报” should preferentially send cached content and must not repeatedly patch failed Bilibili sources.
- Scheduled briefing and life-support features require both the API and QQ bridge to remain running.

## Required README and Git gate

This rule is mandatory for **every** future Git workflow. Before `git add`, `git commit`, `git push`, opening a PR, or telling the user that work is ready to publish:

1. Inspect the complete intended diff and separate it from unrelated user changes.
2. Update root `README.md` proactively for every user-visible capability, endpoint, configuration behavior, startup/restart requirement, safety boundary, test command, or known limitation changed by the work. Do this even when the user did not explicitly ask for README changes.
3. Update `README.local.md` only if verified local paths, launchers, interpreters, or environment locations changed. It must remain ignored.
4. Update this file if the operational handoff, safety, test, or Git policy itself changed.
5. Run relevant validation and `git diff --check` after documentation edits.
6. Run `.\scripts\python.ps1 ..\scripts\check_task_docs.py`; all `待集成` and `已完成` tasks must pass the completion documentation gate.
7. Stage explicit approved paths only. Never use `git add -A` in a mixed worktree without explicit permission for every included change.

Do not merely mention documentation in chat: edit the actual files before Git. A change is not ready for publication while README is stale.

## Publish and handoff

- If `main` is the starting branch, create a focused branch such as `agent/<feature>` unless the user explicitly requests direct main changes.
- Re-fetch remote state before publishing if GitHub freshness matters.
- Use a draft PR by default; summarize branch, commit, validation, excluded paths, and merge URL.
- At handoff, state what changed, what must be restarted, what was not tested, and the next safe action.
- Do not claim a service is running, a file was copied, or a remote branch was updated without current evidence.

## Copyable continuation prompt

```text
You are continuing Project Kei, a Windows-local AI companion project. Read the
repository root README.md, AGENTS.md, and (if present) README.local.md before
acting. Read TASKS.md and the matching tasks/PK-xxx-*.md when the request belongs
to a listed project task. Inspect git status and the actual relevant files; preserve dirty user
changes and never touch vendor/ unless explicitly asked. Communicate in Chinese.
Use apply_patch for edits, keep changes incremental, never expose secrets, and
run proportionate Python/Node/dashboard checks. Before any Git add/commit/push/
PR, proactively update README.md for all current user-visible functionality and
update README.local.md only for verified local-path changes; then run git diff
--check and stage explicit approved paths only.
```
