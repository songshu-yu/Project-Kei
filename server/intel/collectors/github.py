import asyncio
import os
from dataclasses import dataclass

import httpx

from features.github_intel import GitHubCollector, GitHubCollectorSettings


@dataclass
class GithubEvent:
    source: str
    title: str
    description: str
    url: str
    event_type: str
    published: str


API_BASE = "https://api.github.com"
GITHUB_MIN_INTERVAL = float(os.getenv("GITHUB_MIN_INTERVAL", "2.0"))
GITHUB_RETRIES = int(os.getenv("GITHUB_RETRIES", "3"))
GITHUB_TRUST_ENV = os.getenv("GITHUB_TRUST_ENV", "true").strip().lower() in {"1", "true", "yes", "on"}

_github_rate_limit_lock = asyncio.Lock()
_github_last_request_at = 0.0


def _headers():
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ProjectKei/0.1 GitHub collector",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _wait_for_github_slot():
    global _github_last_request_at
    async with _github_rate_limit_lock:
        loop = asyncio.get_running_loop()
        now = loop.time()
        wait = GITHUB_MIN_INTERVAL - (now - _github_last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _github_last_request_at = loop.time()


async def _get_json(client, url, label):
    last_error = None
    for attempt in range(GITHUB_RETRIES + 1):
        try:
            await _wait_for_github_slot()
            resp = await client.get(url)
            if resp.status_code in {403, 429}:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 5.0 * (attempt + 1)
                print(f"[GitHub] WARN {label}: rate limited, waiting {delay:.1f}s")
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_error = exc
            if attempt < GITHUB_RETRIES:
                delay = 2.0 * (attempt + 1)
                print(f"[GitHub] WARN {label}: {exc}; retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
            else:
                raise last_error


async def fetch_github_user_events(users, hours=24):
    events = []
    async with httpx.AsyncClient(
        timeout=30.0,
        headers=_headers(),
        follow_redirects=True,
        trust_env=GITHUB_TRUST_ENV,
    ) as client:
        for user in users:
            try:
                data = await _get_json(client, f"{API_BASE}/users/{user}/events/public?per_page=20", user)
                for event in data:
                    event_type = event.get("type", "")
                    repo_name = event.get("repo", {}).get("name", "")
                    created_at = event.get("created_at", "")
                    repo_url = f"https://github.com/{repo_name}" if repo_name else ""

                    if event_type == "WatchEvent":
                        events.append(GithubEvent(user, f"{user} starred {repo_name}", repo_url, repo_url, event_type, created_at))
                    elif event_type == "PushEvent":
                        commits = event.get("payload", {}).get("commits") or []
                        message = (commits[0].get("message", "") if commits else "")[:100]
                        events.append(GithubEvent(user, f"{user} pushed to {repo_name}", message, repo_url, event_type, created_at))
                    elif event_type == "CreateEvent":
                        ref_type = event.get("payload", {}).get("ref_type", "")
                        events.append(GithubEvent(user, f"{user} created {ref_type}: {repo_name}", "", repo_url, event_type, created_at))
                print(f"[GitHub] OK {user}: events fetched")
            except Exception as exc:
                print(f"[GitHub] FAIL {user}: {exc}")
    return events


async def fetch_github_repo_releases(repos):
    events = []
    async with httpx.AsyncClient(
        timeout=30.0,
        headers=_headers(),
        follow_redirects=True,
        trust_env=GITHUB_TRUST_ENV,
    ) as client:
        for repo in repos:
            try:
                data = await _get_json(client, f"{API_BASE}/repos/{repo}/releases?per_page=3", repo)
                for release in data:
                    name = release.get("name") or release.get("tag_name", "")
                    events.append(GithubEvent(
                        repo,
                        f"{repo} released {name}",
                        (release.get("body") or "")[:200],
                        release.get("html_url", ""),
                        "release",
                        release.get("published_at", ""),
                    ))
                print(f"[GitHub] OK {repo}: releases checked")
            except Exception as exc:
                print(f"[GitHub] FAIL {repo}: {exc}")
    return events


__all__ = [
    "GithubEvent",
    "GitHubCollector",
    "GitHubCollectorSettings",
    "fetch_github_repo_releases",
    "fetch_github_user_events",
]
