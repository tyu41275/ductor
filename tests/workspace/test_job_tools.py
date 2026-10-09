"""Durable jobs (workspace tools/job_tools): the runner records the result and wakes the chat."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TOOLS = (
    Path(__file__).resolve().parents[2]
    / "ductor_bot"
    / "_home_defaults"
    / "workspace"
    / "tools"
    / "job_tools"
)


def _home(tmp_path: Path, port: int, *, enabled: bool = True) -> Path:
    home = tmp_path / "ductor"
    (home / "config").mkdir(parents=True)
    (home / "config" / "config.json").write_text(
        json.dumps({"webhooks": {"enabled": enabled, "host": "127.0.0.1", "port": port}})
    )
    (home / "webhooks.json").write_text(
        json.dumps(
            {"hooks": [{"id": "ductor-jobs", "mode": "wake", "enabled": True, "token": "tok"}]}
        )
    )
    return home


def _job(home: Path, command: str, **meta: object) -> Path:
    d = home / "jobs" / "j1"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": "j1", "name": "t", "command": command, **meta}))
    return d


def _server() -> tuple[HTTPServer, list[dict]]:
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(
                {"path": self.path, "auth": self.headers["Authorization"], "json": json.loads(body)}
            )
            self.send_response(202)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, received


def _run(home: Path, job: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DUCTOR_HOME": str(home)}
    return subprocess.run(
        [sys.executable, str(TOOLS / "_job_runner.py"), str(job)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_success_is_recorded_and_delivered_to_the_wake_hook(tmp_path: Path) -> None:
    srv, received = _server()
    home = _home(tmp_path, srv.server_port)
    job = _job(home, "echo hello; echo done")
    assert _run(home, job).returncode == 0
    srv.shutdown()
    status = json.loads((job / "status.json").read_text())
    assert status["status"] == "succeeded"
    assert status["exit_code"] == 0
    assert status["notify"].startswith("delivered")
    assert received[0]["path"] == "/hooks/ductor-jobs"
    assert received[0]["auth"] == "Bearer tok"
    assert received[0]["json"]["status"] == "succeeded"
    assert "done" in received[0]["json"]["log_tail"]


def test_failure_and_timeout_are_reported(tmp_path: Path) -> None:
    srv, received = _server()
    home = _home(tmp_path, srv.server_port)
    job = _job(home, "sleep 5", timeout_seconds=1)
    assert _run(home, job).returncode == 1
    srv.shutdown()
    assert json.loads((job / "status.json").read_text())["status"] == "timed out"
    assert received[0]["json"]["status"] == "timed out"


def test_disabled_webhooks_still_record_the_result(tmp_path: Path) -> None:
    home = _home(tmp_path, 9, enabled=False)
    job = _job(home, "exit 3")
    assert _run(home, job).returncode == 1
    status = json.loads((job / "status.json").read_text())
    assert status["status"] == "failed"
    assert status["exit_code"] == 3
    assert "webhook disabled" in status["notify"]


def test_no_notify_skips_delivery(tmp_path: Path) -> None:
    srv, received = _server()
    home = _home(tmp_path, srv.server_port)
    job = _job(home, "true", notify=False)
    _run(home, job)
    srv.shutdown()
    assert received == []
    assert "notify" not in json.loads((job / "status.json").read_text())
