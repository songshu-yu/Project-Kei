from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from features.qq_control.router import create_qq_control_router
from qq_bridge.configuration import (
    QQBridgeConfigurationStore,
    QQConfigurationError,
    create_qq_media_capability_provider,
)
from qq_bridge.control_facade import QQControlAdapterFacade


APP_ID = "1000000000123456"
SECRET = "FAKE-SECRET-NEVER-ECHO"


class _Schedules:
    def get_daily_schedule(self):
        return {"enabled": False}

    def get_life_support_schedule(self):
        return {"enabled": False}


class _Manager:
    def resolve_sidecar_deployment(self, _module_id):
        return SimpleNamespace(
            package_root=Path("package"),
            dependency_deployment_root=Path("dependencies"),
        )


class _Adapter:
    def __init__(self, env_path: Path):
        self.configuration_path = env_path

    def inspect(self, *_args):
        configured = self.configuration_path.is_file()
        return SimpleNamespace(
            state="ready" if configured else "needs_configuration",
            package_ready=True,
            env_configured=configured,
            node_ready=True,
            dependencies_ready=True,
        )


class QQConfigurationTests(unittest.TestCase):
    def test_status_is_read_only_and_never_returns_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            store = QQBridgeConfigurationStore(env_path)
            self.assertEqual(store.status()["state"], "missing")
            self.assertFalse(env_path.exists())

            env_path.write_text(
                f"OTHER_KEY=keep-me\nQQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            payload = store.status()
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertTrue(payload["configured"])
            self.assertNotIn(APP_ID, serialized)
            self.assertNotIn(SECRET, serialized)
            self.assertEqual(payload["appid_masked"].endswith("3456"), True)
            self.assertFalse(payload["reply_with_voice"])
            self.assertTrue(payload["voice_setting_valid"])
            self.assertEqual(payload["qq_media_upload_capability"], "unknown")
            self.assertTrue(payload["media_capability_valid"])
            self.assertFalse(payload["life_forecast_enabled"])

    def test_life_forecast_opt_in_defaults_off_and_persists_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"OTHER_KEY=keep-me\nQQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            store = QQBridgeConfigurationStore(env_path)
            self.assertFalse(store.status()["life_forecast_enabled"])
            enabled = store.update(
                appid=None,
                secret=None,
                life_forecast_enabled=True,
            )
            self.assertTrue(enabled["life_forecast_enabled"])
            self.assertIn(
                "QQBOT_LIFE_FORECAST_ENABLED=true",
                env_path.read_text(encoding="utf-8"),
            )
            self.assertIn("OTHER_KEY=keep-me", env_path.read_text(encoding="utf-8"))
            original = env_path.read_bytes()
            failing = QQBridgeConfigurationStore(
                env_path,
                replace=lambda _source, _destination: (_ for _ in ()).throw(
                    OSError("synthetic life forecast failure")
                ),
            )
            with self.assertRaisesRegex(
                QQConfigurationError, "configuration_save_failed"
            ):
                failing.update(
                    appid=None,
                    secret=None,
                    life_forecast_enabled=False,
                )
            self.assertEqual(env_path.read_bytes(), original)
            self.assertEqual(list(env_path.parent.glob(".*.tmp")), [])

    def test_explicit_update_preserves_other_keys_and_blank_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"# preserved\nOTHER_KEY=keep-me\nQQBOT_APPID=old-app\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            store = QQBridgeConfigurationStore(env_path)
            result = store.update(appid=APP_ID, secret="")
            updated = env_path.read_text(encoding="utf-8")
            self.assertTrue(result["configured"])
            self.assertTrue(result["restart_required"])
            self.assertIn("# preserved", updated)
            self.assertIn("OTHER_KEY=keep-me", updated)
            self.assertIn(f"QQBOT_APPID={APP_ID}", updated)
            self.assertIn(f"QQBOT_SECRET={SECRET}", updated)
            self.assertNotIn(SECRET, json.dumps(result))
            preserved = env_path.read_bytes()
            no_change = store.update(appid="", secret="")
            self.assertFalse(no_change["restart_required"])
            self.assertEqual(env_path.read_bytes(), preserved)

    def test_incomplete_or_failed_atomic_save_preserves_old_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            original = f"QQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n".encode()
            env_path.write_bytes(original)
            store = QQBridgeConfigurationStore(
                env_path,
                replace=lambda _source, _destination: (_ for _ in ()).throw(
                    OSError("synthetic replace failure")
                ),
            )
            with self.assertRaisesRegex(QQConfigurationError, "configuration_save_failed"):
                store.update(appid="1000000000999999", secret=None)
            self.assertEqual(env_path.read_bytes(), original)
            self.assertEqual(list(env_path.parent.glob(".*.tmp")), [])

            missing = QQBridgeConfigurationStore(Path(temp) / "missing" / ".env")
            with self.assertRaisesRegex(QQConfigurationError, "configuration_incomplete"):
                missing.update(appid=APP_ID, secret="")
            self.assertFalse((Path(temp) / "missing" / ".env").exists())

    def test_concurrent_updates_leave_one_complete_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"QQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            store = QQBridgeConfigurationStore(env_path)
            errors = []

            def update(value: str) -> None:
                try:
                    store.update(appid=value, secret=None)
                except Exception as exc:  # pragma: no cover - assertion captures it
                    errors.append(exc)

            threads = [
                threading.Thread(target=update, args=("1000000000111111",)),
                threading.Thread(target=update, args=("1000000000222222",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            text = env_path.read_text(encoding="utf-8")
            self.assertIn(f"QQBOT_SECRET={SECRET}", text)
            self.assertEqual(text.count("QQBOT_APPID="), 1)
            self.assertTrue(store.status()["configured"])

    def test_voice_opt_in_defaults_off_and_persists_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"OTHER_KEY=keep-me\nQQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            store = QQBridgeConfigurationStore(env_path)
            self.assertFalse(store.status()["reply_with_voice"])
            enabled = store.update(
                appid=None,
                secret=None,
                reply_with_voice=True,
                qq_media_upload_capability="available",
            )
            self.assertTrue(enabled["reply_with_voice"])
            self.assertTrue(enabled["restart_required"])
            updated = env_path.read_text(encoding="utf-8")
            self.assertIn("QQBOT_REPLY_WITH_VOICE=true", updated)
            self.assertIn("OTHER_KEY=keep-me", updated)
            refreshed = QQBridgeConfigurationStore(env_path).status()
            self.assertTrue(refreshed["reply_with_voice"])
            disabled = store.update(
                appid=None,
                secret=None,
                reply_with_voice=False,
            )
            self.assertFalse(disabled["reply_with_voice"])

            old_bytes = env_path.read_bytes()
            failing = QQBridgeConfigurationStore(
                env_path,
                replace=lambda _source, _destination: (_ for _ in ()).throw(
                    OSError("synthetic voice replace failure")
                ),
            )
            with self.assertRaisesRegex(QQConfigurationError, "configuration_save_failed"):
                failing.update(
                    appid=None,
                    secret=None,
                    reply_with_voice=True,
                )
            self.assertEqual(env_path.read_bytes(), old_bytes)
            self.assertEqual(list(env_path.parent.glob(".*.tmp")), [])

    def test_voice_readiness_unknown_fails_closed_and_available_can_enable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"QQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            unavailable = QQControlAdapterFacade(
                _Manager(),
                _Adapter(env_path),
                _Schedules(),
                configuration_store=QQBridgeConfigurationStore(env_path),
                voice_health_provider=lambda: {
                    "synthesis_profiles": {
                        "qq_c2c_voice_v1": {
                            "available": True,
                            "content_type": "audio/silk",
                            "final": True,
                            "max_bytes": 8 * 1024 * 1024,
                            "max_duration_seconds": 60,
                        }
                    }
                },
                qq_media_capability_provider=lambda: "unknown",
            )
            status = unavailable.get_configuration()
            self.assertFalse(status["voice_reply_available"])
            self.assertEqual(status["qq_media_upload_capability"], "unknown")
            with self.assertRaisesRegex(QQConfigurationError, "voice_unavailable"):
                unavailable.update_configuration(
                    appid=None,
                    secret=None,
                    reply_with_voice=True,
                )
            self.assertNotIn("QQBOT_REPLY_WITH_VOICE=true", env_path.read_text(encoding="utf-8"))

            available = QQControlAdapterFacade(
                _Manager(),
                _Adapter(env_path),
                _Schedules(),
                configuration_store=QQBridgeConfigurationStore(env_path),
                voice_health_provider=lambda: {
                    "synthesis_profiles": {
                        "qq_c2c_voice_v1": {
                            "available": True,
                            "content_type": "audio/silk",
                            "final": True,
                            "max_bytes": 8 * 1024 * 1024,
                            "max_duration_seconds": 60,
                        }
                    }
                },
            )
            saved = available.update_configuration(
                appid=None,
                secret=None,
                reply_with_voice=True,
                qq_media_upload_capability="available",
            )
            self.assertTrue(saved["voice_reply_available"])
            self.assertTrue(saved["reply_with_voice"])

    def test_router_consumes_async_readiness_without_side_effect_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"QQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            calls = {"health": 0, "capability": 0}

            async def health():
                calls["health"] += 1
                return {
                    "synthesis_profiles": {
                        "qq_c2c_voice_v1": {
                            "available": True,
                            "content_type": "audio/silk",
                            "final": True,
                            "max_bytes": 8 * 1024 * 1024,
                            "max_duration_seconds": 60,
                        }
                    }
                }

            async def capability():
                calls["capability"] += 1
                return "available"

            facade = QQControlAdapterFacade(
                _Manager(),
                _Adapter(env_path),
                _Schedules(),
                configuration_store=QQBridgeConfigurationStore(env_path),
                voice_health_provider=health,
                qq_media_capability_provider=capability,
            )
            app = FastAPI()
            app.include_router(create_qq_control_router(facade))

            async def exercise():
                transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43210))
                async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
                    status = await client.get("/api/v1/qq-control/configuration")
                    saved = await client.post(
                        "/api/v1/qq-control/configuration",
                        headers={"Origin": "http://127.0.0.1:8000"},
                        json={
                            "reply_with_voice": True,
                            "qq_media_upload_capability": "available",
                        },
                    )
                return status, saved

            status, saved = asyncio.run(exercise())
            self.assertEqual(status.status_code, 200)
            self.assertTrue(status.json()["voice_reply_available"])
            self.assertEqual(saved.status_code, 200)
            self.assertTrue(saved.json()["reply_with_voice"])
            self.assertGreaterEqual(calls["health"], 2)
            self.assertGreaterEqual(calls["capability"], 2)

    def test_operator_capability_provider_and_downgrade_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"QQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            store = QQBridgeConfigurationStore(env_path)
            provider = create_qq_media_capability_provider(store)
            self.assertEqual(provider(), "unknown")
            store.update(
                appid=None,
                secret=None,
                qq_media_upload_capability="available",
                reply_with_voice=True,
            )
            self.assertEqual(provider(), "available")
            self.assertTrue(store.status()["reply_with_voice"])
            for capability in ("denied", "unavailable", "unknown"):
                saved = store.update(
                    appid=None,
                    secret=None,
                    qq_media_upload_capability=capability,
                )
                self.assertEqual(saved["qq_media_upload_capability"], capability)
                self.assertFalse(saved["reply_with_voice"])

    def test_invalid_or_failed_capability_save_preserves_old_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"QQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n"
                "QQBOT_MEDIA_UPLOAD_CAPABILITY=available\n",
                encoding="utf-8",
            )
            old_bytes = env_path.read_bytes()
            store = QQBridgeConfigurationStore(env_path)
            with self.assertRaisesRegex(QQConfigurationError, "invalid_media_capability"):
                store.update(
                    appid=None,
                    secret=None,
                    qq_media_upload_capability="yes",
                )
            self.assertEqual(env_path.read_bytes(), old_bytes)

            failing = QQBridgeConfigurationStore(
                env_path,
                replace=lambda _source, _destination: (_ for _ in ()).throw(
                    OSError("synthetic capability failure")
                ),
            )
            with self.assertRaisesRegex(QQConfigurationError, "configuration_save_failed"):
                failing.update(
                    appid=None,
                    secret=None,
                    qq_media_upload_capability="denied",
                )
            self.assertEqual(env_path.read_bytes(), old_bytes)
            self.assertEqual(list(env_path.parent.glob(".*.tmp")), [])

    def test_concurrent_capability_updates_leave_one_valid_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                f"OTHER_KEY=keep\nQQBOT_APPID={APP_ID}\nQQBOT_SECRET={SECRET}\n",
                encoding="utf-8",
            )
            store = QQBridgeConfigurationStore(env_path)
            errors = []

            def update(capability: str) -> None:
                try:
                    store.update(
                        appid=None,
                        secret=None,
                        qq_media_upload_capability=capability,
                    )
                except Exception as exc:  # pragma: no cover
                    errors.append(exc)

            threads = [
                threading.Thread(target=update, args=("available",)),
                threading.Thread(target=update, args=("denied",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            status = store.status()
            self.assertIn(
                status["qq_media_upload_capability"], {"available", "denied"}
            )
            text = env_path.read_text(encoding="utf-8")
            self.assertEqual(text.count("QQBOT_MEDIA_UPLOAD_CAPABILITY="), 1)
            self.assertIn("OTHER_KEY=keep", text)

    def test_router_requires_loopback_origin_and_facade_becomes_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            facade = QQControlAdapterFacade(
                _Manager(),
                _Adapter(env_path),
                _Schedules(),
            )
            app = FastAPI()
            app.include_router(create_qq_control_router(facade))

            async def exercise():
                transport = httpx.ASGITransport(
                    app=app,
                    client=("127.0.0.1", 43210),
                )
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://127.0.0.1:8000",
                ) as client:
                    initial = await client.get("/api/v1/qq-control/configuration")
                    rejected = await client.post(
                        "/api/v1/qq-control/configuration",
                        headers={"Origin": "https://attacker.invalid"},
                        json={
                            "appid": APP_ID,
                            "secret": SECRET,
                            "life_forecast_enabled": True,
                        },
                    )
                    exists_after_rejected = env_path.exists()
                    saved = await client.post(
                        "/api/v1/qq-control/configuration",
                        headers={
                            "Origin": "http://127.0.0.1:8000",
                            "Content-Type": "application/json",
                        },
                        json={
                            "appid": APP_ID,
                            "secret": SECRET,
                            "life_forecast_enabled": True,
                        },
                    )
                    invalid = await client.post(
                        "/api/v1/qq-control/configuration",
                        headers={
                            "Origin": "http://127.0.0.1:8000",
                            "Content-Type": "application/json",
                        },
                        content=json.dumps({"appid": APP_ID, "secret": [SECRET]}),
                    )
                    invalid_life_forecast = await client.post(
                        "/api/v1/qq-control/configuration",
                        headers={
                            "Origin": "http://127.0.0.1:8000",
                            "Content-Type": "application/json",
                        },
                        json={"life_forecast_enabled": "true"},
                    )
                    status = await client.get("/api/v1/qq-control/status")
                return (
                    initial,
                    rejected,
                    exists_after_rejected,
                    saved,
                    invalid,
                    invalid_life_forecast,
                    status,
                )

            (
                initial,
                rejected,
                exists_after_rejected,
                saved,
                invalid,
                invalid_life_forecast,
                status,
            ) = asyncio.run(exercise())
            self.assertEqual(initial.status_code, 200)
            self.assertEqual(rejected.status_code, 403)
            self.assertFalse(exists_after_rejected)
            self.assertEqual(saved.status_code, 200)
            response_text = saved.text + initial.text + status.text
            self.assertNotIn(APP_ID, response_text)
            self.assertNotIn(SECRET, response_text)
            self.assertTrue(saved.json()["restart_required"])
            self.assertTrue(saved.json()["life_forecast_enabled"])
            self.assertEqual(invalid.status_code, 422)
            self.assertNotIn(SECRET, invalid.text)
            self.assertEqual(invalid_life_forecast.status_code, 422)
            self.assertEqual(status.json()["state"], "ready")

    def test_dashboard_uses_password_field_without_browser_storage(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "package_source"
            / "dashboard"
            / "index.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"/api/v1/qq-control/configuration"', source)
        self.assertIn('credentialInput("password", "new-password")', source)
        self.assertIn("QQ 回复同时发送语音", source)
        self.assertIn("voice_reply_available", source)
        self.assertIn("qq_media_upload_capability", source)
        self.assertIn("voice_last_result_code", source)
        self.assertIn("voice_message", source)
        self.assertIn("不是自动验证", source)
        self.assertIn("https://q.qq.com/", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("console.", source)


if __name__ == "__main__":
    unittest.main()
