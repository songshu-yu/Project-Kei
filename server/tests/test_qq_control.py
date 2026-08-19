from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from features.qq_control import (  # noqa: E402
    DailyBriefingScheduleUpdate,
    LifeSupportScheduleUpdate,
    QQControlOriginGuardMiddleware,
    QQControlService,
    QQScheduleRepository,
    SchedulePersistenceError,
    ScheduleStateError,
    create_qq_control_router,
)


class FakeProcess:
    pid = 4321

    def poll(self):
        return None


class QQControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.launcher = self.root / "start_qq_bridge.bat"
        self.env_path = self.root / ".env"
        self.dependency = self.root / "node_modules" / "ws"
        self.daily = self.root / "daily.json"
        self.life = self.root / "life.json"
        self.launcher.write_text("@echo off\n", encoding="utf-8")
        self.env_path.write_text("FAKE_NAME=\n", encoding="utf-8")
        self.dependency.mkdir(parents=True)
        self.popen_calls = []
        self.process_checks = 0

    def tearDown(self):
        self.temp.cleanup()

    def service(self, *, running=False, node=True):
        def process_checker():
            self.process_checks += 1
            return running

        def popen(*args, **kwargs):
            self.popen_calls.append((args, kwargs))
            return FakeProcess()

        return QQControlService(
            QQScheduleRepository(self.daily, self.life),
            launcher=self.launcher,
            env_path=self.env_path,
            dependency_path=self.dependency,
            process_checker=process_checker,
            popen_factory=popen,
            node_checker=lambda: node,
        )

    def test_status_is_read_only_and_non_secret(self):
        service = self.service()
        before = set(self.root.rglob("*"))
        result = service.status()
        self.assertEqual(result["state"], "ready")
        self.assertFalse(self.popen_calls)
        self.assertEqual(before, set(self.root.rglob("*")))
        serialized = json.dumps(result)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("FAKE_NAME", serialized)

    def test_project_launcher_only_redirects_to_explicit_dashboard_start(self):
        launcher = (SERVER_ROOT / "qq_bridge" / "start_qq_bridge.bat").read_text(encoding="utf-8").lower()
        self.assertIn("%~dp0", launcher)
        self.assertIn('set "project_kei_root=%~dp0..\\.."', launcher)
        self.assertIn("explicit click in the local dashboard", launcher)
        self.assertIn("http://127.0.0.1:8000/dashboard", launcher)
        self.assertIn("project-kei.pause.cmd", launcher)
        self.assertIn('set "_project_kei_exit=%errorlevel%"', launcher)
        self.assertIn(":manual_start_required", launcher)
        self.assertIn("exit /b 2", launcher)
        self.assertIn("exit /b %_project_kei_exit%", launcher)
        self.assertNotIn("start.bat", launcher)
        self.assertNotIn("--only qq", launcher)
        self.assertNotIn('copy ".env.example"', launcher)
        self.assertNotIn("notepad", launcher)
        self.assertNotIn("call npm.cmd", launcher)
        self.assertFalse(any(line.strip().startswith("npm.cmd") for line in launcher.splitlines()))
        self.assertNotIn("node src\\index.mjs", launcher)

    def test_missing_prerequisites_do_not_create_or_start(self):
        self.launcher.unlink()
        self.assertEqual(self.service().start()["state"], "missing_launcher")
        self.assertFalse(self.launcher.exists())

        self.launcher.write_text("@echo off\n", encoding="utf-8")
        self.env_path.unlink()
        self.assertEqual(self.service().start()["state"], "missing_env")
        self.assertFalse(self.env_path.exists())

        self.env_path.write_text("FAKE_NAME=\n", encoding="utf-8")
        self.assertEqual(self.service(node=False).start()["state"], "missing_node")
        self.dependency.rmdir()
        self.assertEqual(self.service().start()["state"], "missing_dependencies")
        self.assertFalse(self.dependency.exists())
        self.assertFalse(self.popen_calls)

    def test_concurrent_start_calls_popen_once(self):
        service = self.service()
        results = []
        threads = [threading.Thread(target=lambda: results.append(service.start())) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.popen_calls), 1)
        self.assertEqual(sum(bool(value["started"]) for value in results), 1)
        command = self.popen_calls[0][0][0]
        self.assertEqual(Path(command[-1]), self.launcher)

    def test_corrupt_schedule_fails_without_overwrite(self):
        self.daily.write_bytes(b"{broken")
        old = self.daily.read_bytes()
        service = self.service()
        with self.assertRaises(ScheduleStateError):
            service.get_daily_schedule()
        self.assertEqual(self.daily.read_bytes(), old)

    def test_corrupt_schedules_block_service_and_both_http_updates(self):
        daily_old = b'{"enabled":'
        life_old = (
            b'{"enabled":true,"start_time":"08:00","end_time":"22:00",'
            b'"interval_hours":2,"interval_minutes":0,"Authorization":"FAKE_TOKEN"}'
        )
        self.daily.write_bytes(daily_old)
        self.life.write_bytes(life_old)
        service = self.service()

        with self.assertRaises(ScheduleStateError) as daily_error:
            service.update_daily_schedule(DailyBriefingScheduleUpdate(
                enabled=True,
                prebuild_time="06:30",
                send_time="07:30",
            ))
        with self.assertRaises(ScheduleStateError) as life_error:
            service.update_life_support_schedule(LifeSupportScheduleUpdate(
                enabled=True,
                start_time="08:00",
                end_time="22:00",
                interval_hours=2,
                interval_minutes=0,
            ))
        self.assertIn(str(daily_error.exception), {"schedule_corrupt", "schedule_invalid_root"})
        self.assertEqual(str(life_error.exception), "life_support_schedule_invalid_fields")
        self.assertEqual(self.daily.read_bytes(), daily_old)
        self.assertEqual(self.life.read_bytes(), life_old)

        asyncio.run(self._assert_corrupt_http_updates(service, daily_old, life_old))
        self.assertFalse(list(self.root.glob(".*.tmp")))

    async def _assert_corrupt_http_updates(self, service, daily_old, life_old):
        app = FastAPI()
        app.add_middleware(QQControlOriginGuardMiddleware)
        app.include_router(create_qq_control_router(service))
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51000))
        headers = {"Origin": "http://127.0.0.1:8000"}
        daily_payload = {"enabled": True, "prebuild_time": "06:30", "send_time": "07:30"}
        life_payload = {
            "enabled": True,
            "start_time": "08:00",
            "end_time": "22:00",
            "interval_hours": 2,
            "interval_minutes": 0,
        }
        paths = [
            ("/api/v1/qq-control/schedules/daily-briefing", daily_payload, self.daily, daily_old),
            ("/dashboard/briefing/schedule", daily_payload, self.daily, daily_old),
            ("/api/v1/qq-control/schedules/life-support", life_payload, self.life, life_old),
            ("/dashboard/life-support/schedule", life_payload, self.life, life_old),
        ]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for route, payload, target, old_bytes in paths:
                response = await client.put(route, json=payload, headers=headers)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), {"detail": "schedule_state_invalid"})
                self.assertEqual(target.read_bytes(), old_bytes)

    def test_atomic_replace_failure_preserves_old_file(self):
        old = (
            b'{"enabled":false,"prebuild_time":"07:00","send_time":"08:00",'
            b'"updated_at":null}\n'
        )
        self.daily.write_bytes(old)
        service = self.service()
        with patch("features.qq_control.repository.os.replace", side_effect=OSError("FAKE_SECRET_TOKEN")):
            with self.assertRaises(SchedulePersistenceError) as captured:
                service.update_daily_schedule(DailyBriefingScheduleUpdate(
                    enabled=True,
                    prebuild_time="06:30",
                    send_time="07:30",
                ))
        self.assertEqual(str(captured.exception), "schedule_save_failed")
        self.assertEqual(self.daily.read_bytes(), old)
        self.assertFalse(list(self.root.glob(".*.tmp")))

    def test_new_and_legacy_routes_share_service_and_guards(self):
        asyncio.run(self._exercise_routes())

    async def _exercise_routes(self):
        service = self.service()
        app = FastAPI()
        app.add_middleware(QQControlOriginGuardMiddleware)
        app.include_router(create_qq_control_router(service))
        local = httpx.ASGITransport(app=app, client=("127.0.0.1", 51000))
        remote = httpx.ASGITransport(app=app, client=("203.0.113.9", 51000))
        trusted = {"Origin": "http://127.0.0.1:8000"}
        payload = {"enabled": True, "prebuild_time": "06:30", "send_time": "07:30"}
        async with httpx.AsyncClient(transport=local, base_url="http://test") as client:
            self.assertEqual((await client.get("/api/v1/qq-control/status")).status_code, 200)
            self.assertEqual((await client.put("/api/v1/qq-control/schedules/daily-briefing", json=payload)).status_code, 403)
            self.assertEqual((await client.put("/api/v1/qq-control/schedules/daily-briefing", json=payload, headers={"Origin": "https://evil.example"})).status_code, 403)
            saved = await client.put("/api/v1/qq-control/schedules/daily-briefing", json=payload, headers=trusted)
            self.assertEqual(saved.status_code, 200)
            arbitrary_start = await client.post(
                "/api/v1/qq-control/start",
                json={"bat": "C:/FAKE/evil.bat", "cwd": "C:/FAKE", "environment": {"QQBOT_SECRET": "FAKE_SECRET_TOKEN"}},
                headers=trusted,
            )
            self.assertEqual(arbitrary_start.status_code, 422)
            self.assertEqual(arbitrary_start.json(), {"detail": "invalid_request"})
            self.assertFalse(self.popen_calls)
            versioned = await client.get("/api/v1/qq-control/schedules/daily-briefing")
            legacy = await client.get("/dashboard/briefing/schedule")
            self.assertEqual(versioned.json(), legacy.json())
            rejected = await client.put(
                "/dashboard/briefing/schedule",
                json={**payload, "QQBOT_SECRET": "FAKE_SECRET_TOKEN"},
                headers=trusted,
            )
            self.assertEqual(rejected.status_code, 422)
            self.assertNotIn("FAKE_SECRET_TOKEN", rejected.text)
        async with httpx.AsyncClient(transport=remote, base_url="http://test") as client:
            self.assertEqual((await client.put("/dashboard/briefing/schedule", json=payload, headers=trusted)).status_code, 403)


if __name__ == "__main__":
    unittest.main()
