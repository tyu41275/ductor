"""Shared helpers for durable jobs (job_tools).

A job is a shell command that runs as a transient systemd user unit, so it
survives the agent's CLI session ending and bot restarts. When it ends, the
runner POSTs a summary to the ``ductor-jobs`` wake webhook, which puts the
result into the main chat so the agent can report it and follow up.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

DUCTOR_HOME = Path(os.environ.get("DUCTOR_HOME", Path.home() / ".ductor")).expanduser()
JOBS_DIR = DUCTOR_HOME / "jobs"
HOOKS_PATH = DUCTOR_HOME / "webhooks.json"
CONFIG_PATH = DUCTOR_HOME / "config" / "config.json"
HOOK_ID = "ductor-jobs"
UNIT_PREFIX = "ductor-job-"
LOG_TAIL_LINES = 30
LOG_TAIL_CHARS = 3000


def systemd_env() -> dict[str, str]:
    """Environment for ``systemd-run``/``systemctl --user``: agent shells often lack the user bus."""
    env = dict(os.environ)
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env.setdefault("XDG_RUNTIME_DIR", runtime)
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    return env


def new_job_id(name: str) -> str:
    slug = (
        "".join(c if c.isalnum() or c == "-" else "-" for c in name.lower()).strip("-")[:30]
        or "job"
    )
    return f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{slug}-{secrets.token_hex(2)}"


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def log_tail(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-LOG_TAIL_LINES:])[-LOG_TAIL_CHARS:]


def webhook_endpoint() -> tuple[str, str] | None:
    """(url, bearer token) of the ductor-jobs wake hook, or None when not usable."""
    config = read_json(CONFIG_PATH).get("webhooks", {})
    if not isinstance(config, dict) or not config.get("enabled"):
        return None
    hooks = read_json(HOOKS_PATH).get("hooks", [])
    hook = next((h for h in hooks if isinstance(h, dict) and h.get("id") == HOOK_ID), None)
    if not hook or not hook.get("enabled", True) or not hook.get("token"):
        return None
    host = config.get("host") or "127.0.0.1"
    port = config.get("port") or 8742
    return f"http://{host}:{port}/hooks/{HOOK_ID}", str(hook["token"])
