# Project Kei Control Dashboard

## Start everything with one double-click

From the repository root, double-click `start.bat` to start Core only. Use
`start.bat --profile all` only when all installed optional components are
explicitly wanted. The legacy `server/start_all_services.bat` name delegates to
the same launcher.

The launcher checks ports 9880, 8010, and 8000 before starting GPT-SoVITS, ASR,
and the Project Kei API. It does not open duplicate service windows for services
that are already running. Once the API is available, it opens:

`http://127.0.0.1:8000/dashboard`

## What the dashboard shows

- API, ASR, GPT-SoVITS, and LLM configuration readiness
- Whether required local models, the GPT-SoVITS folder, and Kei's reference audio exist
- Whether optional GitHub, Semantic Scholar, and Bilibili credentials are configured
- Today's briefing cache, source counts, per-source coverage/retry time, and source warnings

No credential values are sent to the browser or displayed on the page.

## Controls

- **Refresh status** checks local service status again.
- **Generate today's briefing** prepares the briefing cache. It only accepts a request
  from the same computer, because it can call external information sources.
- **Daily briefing status** uses PK-110's read-only service and
  `/dashboard/briefing/status`; opening the panel does not parse cache JSON directly
  or trigger Collectors, PK-200, or PK-210.
- **Daily briefing source targets** add, edit, or remove X/Nitter users, GitHub
  users and repositories, Bilibili UIDs, YouTube channel IDs, and paper authors.
  These personal targets are stored locally without credentials and take effect on
  the next new collection; saving does not silently force a repeat Bilibili fetch.
  X/Nitter rows resolve display names and avatars through the existing Nitter RSS
  instances, then share one local cache across the normal and money-gap groups.
  Each X row can also fetch only that user's posts from the current local date.
  Its post list is independently collapsible, defaults closed with a cached-count
  summary, and only the freshly fetched user opens automatically. Today's result
  is cached; API startup and cache reads clear it when the date changes. Opening
  the dashboard reads the cache but does not fetch every user.
  Bilibili rows also show the cached nickname and avatar for each UID. Missing
  X or Bilibili profiles are resolved once, failed lookups cool down for six
  hours, and the per-row refresh button is the only success-cache bypass.
- **LLM model profile** tests then applies DeepSeek Flash, DeepSeek Pro, or an
  OpenAI-compatible custom profile without exposing the API key in the browser.
- **Daily briefing schedule** stores a prebuild time and QQ send time. The API and
  `qq_bridge` must both remain running for scheduled work to happen. The panel uses
  `/api/v1/qq-control/schedules/daily-briefing`; the legacy dashboard route delegates
  to the same service and repository.
- **Kei daily narration** shows the exact text prepared for Kei to read aloud.
  Only today's narration is cached; startup and the next daily generation remove
  a previous-day narration before showing or saving the new one.
- **Life support schedule** stores a daily time window and interval for QQ private
  chat reminders to hydrate, move, stretch, or rest through
  `/api/v1/qq-control/schedules/life-support`.
- **Personal systems** expose the existing affection, demon-slayer, fitness,
  focus timer, calendar/practice, and long-term-memory APIs. Demon-slayer goals
  can be added or individually removed, choose a demon category, and use daily,
  weekly, monthly, or yearly ranks. A goal can repeat every matching period or be
  a one-time target bound to one selected day/week/month/year; legacy goals remain
  recurring. Review buttons send factual completion data to Kei for balanced
  praise and criticism, with a deterministic local fallback.
  The dashboard does not provide destructive reset or clear-all actions.
- **Collapsible panels** keep each function independently expandable. The browser
  remembers which panels are open; no settings, source targets, or secrets are
  stored in that browser state.
- **Feature center and module loading** read `GET /api/v1/modules` without lifecycle
  writes. Only enabled modules with a trusted dashboard entrypoint are imported.
  A module exports `mount(context)` and may export `unmount()`; its request helper
  is limited to the module's declared API namespaces. A missing, timed-out, or
  failing module entry shows an isolated error while the legacy dashboard remains
  usable. The first-stage feature center does not expose install, enable, disable,
  uninstall, or purge controls.
- **Start QQ bridge** is the first feature card and uses `static/assets/qq-launch.png`
  as its clickable launch image. It checks the existing BAT, local `.env`,
  Node runtime, dependency folder, and running process before opening the fixed BAT
  in a new console. Status/start use `/api/v1/qq-control`; writes require a real
  loopback client and trusted same-origin dashboard Origin. It does not expose
  credentials, create configuration, install packages, or start a duplicate.

Public dashboard resources live in `static/dashboard/` and are served from
`/dashboard/static/`. `dashboard.html` remains the compatibility entry and keeps
the existing business element IDs and handlers until each feature task migrates
its own panel. Changes to either location require restarting the API.

## QQ bridge

Start the QQ bridge separately from `server\qq_bridge\start_qq_bridge.bat`, or
use the local-only button in the dashboard after the API is running.
Its `.env` contains local credentials and is deliberately excluded from Git.
The bridge serves allow-listed private chats, sends markdown briefing sections,
and reads the dashboard's saved briefing and reminder schedules.
