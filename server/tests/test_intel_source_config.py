"""Focused checks for dashboard-managed daily briefing source targets."""
from __future__ import annotations

import asyncio
import contextlib
import io
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _path_setup  # noqa: F401

from intel import briefing
from intel.collectors.twitter import _rss_daily_posts, _rss_profile_name
from services.bilibili_profile_cache import resolve_bilibili_profiles
from services.intel_source_config import (
    default_intel_sources,
    load_intel_sources,
    normalize_intel_sources,
    save_intel_sources,
)
from services import qq_bridge_control
from services.x_daily_posts import (
    fetch_and_cache_x_daily_posts,
    get_x_daily_posts_cache,
    prepare_x_daily_posts_cache,
)
from services.x_profile_cache import resolve_x_profiles


async def check_bilibili_profile_cache() -> None:
    calls = []

    async def profile(uid):
        calls.append(uid)
        return {
            "uid": uid,
            "name": f"UP-{uid}",
            "avatar_url": f"//i.example.test/{uid}.jpg",
        }

    current_time = datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "bilibili_profiles.json"
        first = await resolve_bilibili_profiles(
            [123, "456", 123], path=path, fetcher=profile, now=current_time
        )
        assert calls == [123, 456]
        assert first["fetched"] == 2
        assert first["profiles"]["123"]["name"] == "UP-123"
        assert first["profiles"]["456"]["avatar_url"] == "https://i.example.test/456.jpg"

        second = await resolve_bilibili_profiles(
            [123, 456], path=path, fetcher=profile, now=current_time
        )
        assert calls == [123, 456]
        assert second["fetched"] == 0

        refreshed = await resolve_bilibili_profiles(
            [123], refresh=True, path=path, fetcher=profile, now=current_time
        )
        assert calls == [123, 456, 123]
        assert refreshed["fetched"] == 1

        failed_calls = []

        async def unavailable(uid):
            failed_calls.append(uid)
            raise RuntimeError("simulated anti-bot response")

        failed = await resolve_bilibili_profiles(
            [789], path=path, fetcher=unavailable, now=current_time
        )
        assert failed["profiles"]["789"]["status"] == "error"
        await resolve_bilibili_profiles(
            [789], path=path, fetcher=unavailable, now=current_time
        )
        assert failed_calls == [789]


async def check_x_profile_cache() -> None:
    calls = []

    async def profile(username):
        calls.append(username)
        return {
            "username": username,
            "name": f"Display {username}",
            "avatar_url": f"https://nitter.example.test/pic/{username}.jpg",
        }

    current_time = datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "x_profiles.json"
        first = await resolve_x_profiles(
            ["@Karpathy", "karpathy", "OpenAI"], path=path, fetcher=profile, now=current_time
        )
        assert calls == ["Karpathy", "OpenAI"]
        assert first["fetched"] == 2
        assert first["profiles"]["karpathy"]["name"] == "Display Karpathy"

        second = await resolve_x_profiles(
            ["karpathy", "openai"], path=path, fetcher=profile, now=current_time
        )
        assert calls == ["Karpathy", "OpenAI"]
        assert second["fetched"] == 0

        refreshed = await resolve_x_profiles(
            ["karpathy"], refresh=True, path=path, fetcher=profile, now=current_time
        )
        assert calls == ["Karpathy", "OpenAI", "karpathy"]
        assert refreshed["fetched"] == 1

        failed_calls = []

        async def unavailable(username):
            failed_calls.append(username)
            raise RuntimeError("simulated Nitter outage")

        failed = await resolve_x_profiles(
            ["temporarily_down"], path=path, fetcher=unavailable, now=current_time
        )
        assert failed["profiles"]["temporarily_down"]["status"] == "error"
        await resolve_x_profiles(
            ["temporarily_down"], path=path, fetcher=unavailable, now=current_time
        )
        assert failed_calls == ["temporarily_down"]


async def check_x_daily_posts_cache() -> None:
    china_tz = timezone(timedelta(hours=8))
    current_time = datetime(2026, 7, 17, 9, 30, tzinfo=china_tz)
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><title>Example (@example)</title>
      <item><title>today</title><description><![CDATA[<p>今天的第一条</p>]]></description><link>https://nitter.test/example/status/1</link><pubDate>Fri, 17 Jul 2026 00:15:00 GMT</pubDate></item>
      <item><title>old</title><description>昨天的内容</description><link>https://nitter.test/example/status/0</link><pubDate>Thu, 16 Jul 2026 00:15:00 GMT</pubDate></item>
    </channel></rss>"""
    parsed = _rss_daily_posts(xml_text, "example", current_time.date(), china_tz)
    assert len(parsed) == 1
    assert parsed[0]["content"] == "今天的第一条"
    assert parsed[0]["published"] == "2026-07-17 08:15"

    calls = []

    async def posts(username):
        calls.append(username)
        return parsed

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "x_daily_posts.json"
        initial = prepare_x_daily_posts_cache(path, now=current_time)
        assert initial["date"] == "2026-07-17"
        assert initial["users"] == {}

        entry = await fetch_and_cache_x_daily_posts(
            "@Example", path=path, fetcher=posts, now=current_time
        )
        assert calls == ["Example"]
        assert entry["count"] == 1
        cached = get_x_daily_posts_cache(["example", "not_cached"], path, now=current_time)
        assert cached["users"]["example"]["posts"][0]["content"] == "今天的第一条"

        next_day = datetime(2026, 7, 18, 7, 0, tzinfo=china_tz)
        cleared = prepare_x_daily_posts_cache(path, now=next_day)
        assert cleared["date"] == "2026-07-18"
        assert cleared["users"] == {}


def check_qq_bridge_control() -> None:
    class FakeProcess:
        pid = 4321

        def poll(self):
            return None

    calls = []

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    qq_bridge_control._launched_process = None
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "qq_bridge"
        launcher = root / "start_qq_bridge.bat"
        env_path = root / ".env"
        dependency_path = root / "node_modules" / "ws"
        root.mkdir(parents=True)

        missing = qq_bridge_control.qq_bridge_status(
            launcher=launcher,
            env_path=env_path,
            dependency_path=dependency_path,
            process_checker=lambda: False,
        )
        assert missing["state"] == "missing_launcher"

        launcher.write_text("@echo off\n", encoding="utf-8")
        env_path.write_text("configured-for-test=true\n", encoding="utf-8")
        dependency_path.mkdir(parents=True)
        ready = qq_bridge_control.qq_bridge_status(
            launcher=launcher,
            env_path=env_path,
            dependency_path=dependency_path,
            process_checker=lambda: False,
        )
        assert ready["state"] == "ready"

        started = qq_bridge_control.launch_qq_bridge(
            launcher=launcher,
            env_path=env_path,
            dependency_path=dependency_path,
            process_checker=lambda: False,
            popen_factory=fake_popen,
        )
        assert started["started"] is True
        assert started["pid"] == 4321
        assert calls[0][0][1] == "/c"
        assert calls[0][0][2] == str(launcher)

        duplicate = qq_bridge_control.launch_qq_bridge(
            launcher=launcher,
            env_path=env_path,
            dependency_path=dependency_path,
            process_checker=lambda: False,
            popen_factory=fake_popen,
        )
        assert duplicate["started"] is False
        assert duplicate["running"] is True
        assert len(calls) == 1
    qq_bridge_control._launched_process = None


async def check_briefing_reads_current_sources() -> None:
    captured = {}

    async def twitter(users, instances):
        captured["twitter"] = list(users)
        return []

    async def github_users(users):
        captured["github_users"] = list(users)
        return []

    async def github_repos(repos):
        captured["github_repos"] = list(repos)
        return []

    async def bilibili(uids, since_hours):
        captured["bilibili"] = list(uids)
        return []

    async def youtube(channel_ids):
        captured["youtube"] = list(channel_ids)
        return []

    source_config = {
        "twitter_users": ["KeiBot"],
        "money_twitter_users": ["keibot", "indiehackers"],
        "github_users": ["openai"],
        "github_repos": ["openai/openai-python"],
        "bilibili_uids": [123],
        "youtube_channel_ids": ["UC1234567890123456789012"],
        "paper_priority_authors": [],
        "paper_secondary_authors": [],
        "paper_ai_authors": [],
    }
    originals = {
        "load_intel_sources": briefing.load_intel_sources,
        "fetch_twitter": briefing.fetch_twitter,
        "fetch_github_user_events": briefing.fetch_github_user_events,
        "fetch_github_repo_releases": briefing.fetch_github_repo_releases,
        "fetch_bilibili": briefing.fetch_bilibili,
        "fetch_youtube": briefing.fetch_youtube,
        "clear_arxiv_failures": briefing.clear_arxiv_failures,
        "get_arxiv_failures": briefing.get_arxiv_failures,
    }
    try:
        briefing.load_intel_sources = lambda: source_config
        briefing.fetch_twitter = twitter
        briefing.fetch_github_user_events = github_users
        briefing.fetch_github_repo_releases = github_repos
        briefing.fetch_bilibili = bilibili
        briefing.fetch_youtube = youtube
        briefing.clear_arxiv_failures = lambda: None
        briefing.get_arxiv_failures = lambda: []
        with contextlib.redirect_stdout(io.StringIO()):
            await briefing.gather_all_intel(sources=["twitter", "github", "bilibili", "youtube"])
    finally:
        for name, value in originals.items():
            setattr(briefing, name, value)

    assert captured["twitter"] == ["KeiBot", "indiehackers"]
    assert captured["github_users"] == ["openai"]
    assert captured["github_repos"] == ["openai/openai-python"]
    assert captured["bilibili"] == [123]
    assert captured["youtube"] == ["UC1234567890123456789012"]


def main() -> int:
    assert _rss_profile_name("Andrej Karpathy (@karpathy)", "karpathy") == "Andrej Karpathy"
    assert _rss_profile_name("Andrej Karpathy / @karpathy", "karpathy") == "Andrej Karpathy"
    defaults = default_intel_sources()
    check_qq_bridge_control()
    partial = normalize_intel_sources({"twitter_users": ["@KeiBot", "keibot", "openai"]}, defaults)
    assert partial["twitter_users"] == ["KeiBot", "openai"]
    assert partial["github_repos"] == defaults["github_repos"]

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "intel_sources.json"
        initial = load_intel_sources(path)
        assert initial["using_local_override"] is False

        payload = {
            key: list(initial[key])
            for key in (
                "twitter_users",
                "money_twitter_users",
                "github_users",
                "github_repos",
                "bilibili_uids",
                "youtube_channel_ids",
                "paper_priority_authors",
                "paper_secondary_authors",
                "paper_ai_authors",
            )
        }
        payload.update({
            "twitter_users": ["@KeiBot", "keibot", "openai"],
            "github_users": ["openai"],
            "github_repos": ["openai/openai-python"],
            "bilibili_uids": ["123", 456, "123"],
            "youtube_channel_ids": ["UC1234567890123456789012"],
            "paper_priority_authors": ["Ada Lovelace"],
            "paper_secondary_authors": [],
            "paper_ai_authors": [],
            "money_twitter_users": [],
        })
        saved = save_intel_sources(payload, path)
        assert saved["using_local_override"] is True
        assert saved["twitter_users"] == ["KeiBot", "openai"]
        assert saved["bilibili_uids"] == [123, 456]
        assert load_intel_sources(path)["github_repos"] == ["openai/openai-python"]

        invalid = dict(payload)
        invalid["github_repos"] = ["not a repo"]
        try:
            save_intel_sources(invalid, path)
        except ValueError as exc:
            assert "owner/repository" in str(exc)
        else:
            raise AssertionError("invalid repository was accepted")

        path.write_text('{"twitter_users": 42}', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            recovered = load_intel_sources(path)
        assert recovered["using_local_override"] is False
        assert recovered["twitter_users"] == defaults["twitter_users"]

        path.write_text('{not valid json', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            assert load_intel_sources(path)["using_local_override"] is False

    asyncio.run(check_bilibili_profile_cache())
    asyncio.run(check_x_profile_cache())
    asyncio.run(check_x_daily_posts_cache())
    asyncio.run(check_briefing_reads_current_sources())
    print("intel source config tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
