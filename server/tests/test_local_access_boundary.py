from __future__ import annotations

import asyncio
import importlib
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.middleware.cors import CORSMiddleware


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.local_access import (  # noqa: E402
    LOCAL_ONLY_MESSAGE,
    LoopbackAccessMiddleware,
    TRUSTED_LOCAL_ORIGINS,
    is_loopback_host,
)


class ProtectedPathTripwire:
    """Reject default personal/runtime paths before their Path I/O methods run."""

    def __init__(self, server_root: Path):
        root = os.path.abspath(os.fspath(server_root)).casefold()
        self.protected = tuple(
            os.path.join(root, relative).casefold()
            for relative in (
                ".env",
                "cache",
                "data",
                "models",
                "output",
                "profiles",
                "qq_bridge/data",
                "reference_audio",
                "runtime",
                "systems/data",
                "voice_packs",
            )
        )
        self.rejected: list[tuple[str, str]] = []
        self.protected_resolve_shortcuts = 0
        self.allowed_calls = 0
        self._patchers = []

    def _is_protected(self, value: object) -> bool:
        try:
            candidate = os.path.abspath(os.fspath(value)).casefold()
        except TypeError:
            return False
        return any(
            candidate == prefix or candidate.startswith(prefix + os.sep)
            for prefix in self.protected
        )

    def __enter__(self):
        original_resolve = Path.resolve

        def guarded_resolve(path, *args, **kwargs):
            if self._is_protected(path):
                self.protected_resolve_shortcuts += 1
                return Path(os.path.abspath(os.fspath(path)))
            self.allowed_calls += 1
            return original_resolve(path, *args, **kwargs)

        resolve_patcher = patch.object(Path, "resolve", guarded_resolve)
        resolve_patcher.start()
        self._patchers.append(resolve_patcher)
        for method_name in (
            "exists",
            "is_dir",
            "is_file",
            "lstat",
            "open",
            "read_bytes",
            "read_text",
            "stat",
            "write_bytes",
            "write_text",
        ):
            original = getattr(Path, method_name)

            def guarded(path, *args, _name=method_name, _original=original, **kwargs):
                if self._is_protected(path):
                    self.rejected.append((_name, os.fspath(path)))
                    raise AssertionError(
                        f"protected path reached {_name} before request isolation"
                    )
                self.allowed_calls += 1
                return _original(path, *args, **kwargs)

            patcher = patch.object(Path, method_name, guarded)
            patcher.start()
            self._patchers.append(patcher)
        return self

    def __exit__(self, exc_type, exc, traceback):
        while self._patchers:
            self._patchers.pop().stop()
        return False


def _route_probe_path(path: str) -> str:
    return re.sub(r"\{[^{}]+\}", "synthetic", path) or "/"


async def _empty_http_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def _capture_send(messages: list[dict]):
    async def send(message: dict) -> None:
        messages.append(message)

    return send


class LocalAccessBoundaryTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="kei-local-access-")
        temp_root = Path(cls.temp.name)
        environment = {
            "PROJECT_KEI_ENV_FILE": str(temp_root / "absent.env"),
            "PROJECT_KEI_LLM_PROFILE_PATH": str(temp_root / "llm-profile.json"),
            "PROJECT_KEI_VOICE_PACK_REGISTRY": str(temp_root / "voice-pack.json"),
        }
        cls.import_tripwire = ProtectedPathTripwire(SERVER_ROOT)
        with patch.dict(os.environ, environment, clear=False), cls.import_tripwire:
            was_loaded = "api" in sys.modules
            import api
            if was_loaded:
                api = importlib.reload(api)

        cls.api = api
        cls.app = api.app
        cls.http_route_count = sum(
            1 for route in cls.app.routes if getattr(route, "methods", None)
        )
        cls.websocket_route_count = sum(
            1
            for route in cls.app.routes
            if route.__class__.__name__ in {"APIWebSocketRoute", "WebSocketRoute"}
        )
        if cls.import_tripwire.protected_resolve_shortcuts != 0:
            raise AssertionError("Core import resolved a protected user path")
        if cls.import_tripwire.rejected:
            raise AssertionError("Core import performed protected path I/O")

    @classmethod
    def tearDownClass(cls):
        print(
            "[PK-020] local_access_import_tripwire "
            f"protected_rejected={len(cls.import_tripwire.rejected)} "
            f"protected_resolve_shortcuts={cls.import_tripwire.protected_resolve_shortcuts} "
            f"allowed_io_calls={cls.import_tripwire.allowed_calls} "
            f"http_routes={cls.http_route_count} "
            f"websocket_routes={cls.websocket_route_count}"
        )
        sys.modules.pop("api", None)
        cls.temp.cleanup()

    def test_peer_address_and_middleware_order_are_fail_closed(self):
        for host in ("127.0.0.1", "127.0.0.2", "127.255.255.254", "::1"):
            with self.subTest(host=host):
                self.assertTrue(is_loopback_host(host))
        for host in (
            None,
            "",
            "localhost",
            "0.0.0.0",
            "192.168.1.20",
            "203.0.113.9",
            "::ffff:127.0.0.1",
        ):
            with self.subTest(host=host):
                self.assertFalse(is_loopback_host(host))

        middleware = self.app.user_middleware
        self.assertIs(middleware[0].cls, LoopbackAccessMiddleware)
        cors = next(item for item in middleware if item.cls is CORSMiddleware)
        options = getattr(cors, "kwargs", getattr(cors, "options", {}))
        self.assertEqual(
            set(options["allow_origins"]),
            set(TRUSTED_LOCAL_ORIGINS),
        )
        self.assertFalse(options["allow_credentials"])
        self.assertNotIn("*", options["allow_origins"])

    async def test_every_http_route_rejects_remote_before_downstream_and_data_io(self):
        routes = [
            route
            for route in self.app.routes
            if getattr(route, "methods", None)
        ]
        self.assertGreater(len(routes), 20)

        downstream_calls = []

        async def downstream(scope, receive, send):
            downstream_calls.append((scope["method"], scope["path"]))
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        boundary = LoopbackAccessMiddleware(downstream)
        for route in routes:
            methods = sorted(
                method
                for method in route.methods
                if method not in {"HEAD", "OPTIONS"}
            )
            method = methods[0] if methods else sorted(route.methods)[0]
            messages = []
            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "scheme": "http",
                "method": method,
                "path": _route_probe_path(route.path),
                "raw_path": _route_probe_path(route.path).encode("ascii", "ignore"),
                "query_string": b"",
                "root_path": "",
                "headers": [],
                "client": ("203.0.113.9", 54000),
                "server": ("127.0.0.1", 8000),
            }
            await boundary(scope, _empty_http_receive, _capture_send(messages))
            self.assertEqual(messages[0]["status"], 403, route.path)

        self.assertEqual(downstream_calls, [])

        with ProtectedPathTripwire(SERVER_ROOT) as request_tripwire:
            transport = httpx.ASGITransport(
                app=self.app,
                client=("203.0.113.9", 54001),
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://127.0.0.1:8000",
            ) as client:
                for route in routes:
                    response = await client.request(
                        "GET",
                        _route_probe_path(route.path),
                    )
                    self.assertEqual(response.status_code, 403, route.path)
                    self.assertEqual(
                        response.json(),
                        {"detail": LOCAL_ONLY_MESSAGE},
                        route.path,
                    )
        self.assertEqual(request_tripwire.rejected, [])

    async def test_headers_cannot_override_peer_and_cors_is_exact(self):
        remote = httpx.ASGITransport(
            app=self.app,
            client=("203.0.113.9", 54100),
        )
        forged = {
            "Host": "127.0.0.1:8000",
            "Origin": "http://127.0.0.1:8000",
            "X-Forwarded-For": "127.0.0.1",
            "Forwarded": "for=127.0.0.1;host=127.0.0.1:8000",
        }
        async with httpx.AsyncClient(
            transport=remote,
            base_url="http://127.0.0.1:8000",
        ) as client:
            response = await client.get("/", headers=forged)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {"detail": LOCAL_ONLY_MESSAGE})
            preflight = await client.options(
                "/chat",
                headers={
                    **forged,
                    "Access-Control-Request-Method": "POST",
                },
            )
            self.assertEqual(preflight.status_code, 403)

        for host in ("127.0.0.1", "127.0.0.2", "::1"):
            local = httpx.ASGITransport(app=self.app, client=(host, 54101))
            async with httpx.AsyncClient(
                transport=local,
                base_url="http://127.0.0.1:8000",
            ) as client:
                response = await client.get("/")
                self.assertEqual(response.status_code, 200, host)

        local = httpx.ASGITransport(
            app=self.app,
            client=("127.0.0.1", 54102),
        )
        async with httpx.AsyncClient(
            transport=local,
            base_url="http://127.0.0.1:8000",
        ) as client:
            trusted = await client.get(
                "/",
                headers={"Origin": "http://127.0.0.1:8000"},
            )
            self.assertEqual(trusted.status_code, 200)
            self.assertEqual(
                trusted.headers.get("access-control-allow-origin"),
                "http://127.0.0.1:8000",
            )
            for origin in (
                "",
                " ",
                "null",
                "http://192.168.1.20:8000",
                "https://127.0.0.1:8000",
                "http://evil.example",
            ):
                denied = await client.get("/", headers={"Origin": origin})
                self.assertEqual(denied.status_code, 403, origin)
                self.assertNotIn("access-control-allow-origin", denied.headers)

            duplicate_origin = await client.get(
                "/",
                headers=[
                    ("Origin", "http://127.0.0.1:8000"),
                    ("Origin", "http://evil.example"),
                ],
            )
            self.assertEqual(duplicate_origin.status_code, 403)
            self.assertNotIn(
                "access-control-allow-origin",
                duplicate_origin.headers,
            )

            preflight = await client.options(
                "/chat",
                headers={
                    "Origin": "http://localhost:8000",
                    "Access-Control-Request-Method": "POST",
                },
            )
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(
                preflight.headers.get("access-control-allow-origin"),
                "http://localhost:8000",
            )

    async def test_every_websocket_route_checks_peer_before_handshake(self):
        routes = [
            route
            for route in self.app.routes
            if route.__class__.__name__ in {"APIWebSocketRoute", "WebSocketRoute"}
        ]
        # A clean Core intentionally has no business WebSocket route.  Keep a
        # synthetic handshake probe so the global boundary remains permanent
        # even before the optional conversation module is installed.
        probe_paths = [
            _route_probe_path(route.path) for route in routes
        ] or ["/synthetic-module-websocket"]

        downstream = []

        async def websocket_app(scope, receive, send):
            downstream.append(scope["path"])
            await send({"type": "websocket.accept"})

        boundary = LoopbackAccessMiddleware(websocket_app)
        for path in probe_paths:
            remote_messages = []
            await boundary(
                self._websocket_scope(path, "203.0.113.9"),
                self._disconnect_receive,
                _capture_send(remote_messages),
            )
            self.assertEqual(
                remote_messages,
                [
                    {
                        "type": "websocket.close",
                        "code": 1008,
                        "reason": LOCAL_ONLY_MESSAGE,
                    }
                ],
                path,
            )
            for host in ("127.0.0.1", "127.0.0.2", "::1"):
                allowed_messages = []
                await boundary(
                    self._websocket_scope(path, host),
                    self._disconnect_receive,
                    _capture_send(allowed_messages),
                )
                self.assertEqual(
                    allowed_messages[0]["type"],
                    "websocket.accept",
                    (path, host),
                )
        self.assertEqual(len(downstream), len(probe_paths) * 3)

        for route in routes:
            path = _route_probe_path(route.path)
            remote_messages = await self._drive_actual_websocket(
                path,
                "203.0.113.9",
            )
            self.assertEqual(remote_messages[0]["type"], "websocket.close")
            self.assertNotIn(
                "websocket.accept",
                {message["type"] for message in remote_messages},
            )

            for host in ("127.0.0.1", "::1"):
                local_messages = await self._drive_actual_websocket(path, host)
                self.assertIn(
                    "websocket.accept",
                    {message["type"] for message in local_messages},
                    (route.path, host),
                )

            malicious = await self._drive_actual_websocket(
                path,
                "127.0.0.1",
                origin="http://evil.example",
            )
            self.assertEqual(malicious[0]["type"], "websocket.close")

    @staticmethod
    def _websocket_scope(path: str, host: str, origin: str | None = None) -> dict:
        headers = [] if origin is None else [(b"origin", origin.encode("ascii"))]
        return {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode("ascii", "ignore"),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": (host, 54200),
            "server": ("127.0.0.1", 8000),
            "subprotocols": [],
            "state": {},
        }

    @staticmethod
    async def _disconnect_receive() -> dict:
        return {"type": "websocket.disconnect", "code": 1000}

    async def _drive_actual_websocket(
        self,
        path: str,
        host: str,
        *,
        origin: str | None = None,
    ) -> list[dict]:
        incoming = [
            {"type": "websocket.connect"},
            {"type": "websocket.disconnect", "code": 1000},
        ]
        messages = []

        async def receive():
            return incoming.pop(0)

        async def send(message):
            messages.append(message)

        with patch("builtins.print"):
            await self.app(
                self._websocket_scope(path, host, origin),
                receive,
                send,
            )
        return messages


if __name__ == "__main__":
    unittest.main(verbosity=2)
