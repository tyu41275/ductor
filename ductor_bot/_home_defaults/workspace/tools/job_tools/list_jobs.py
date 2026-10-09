#!/usr/bin/env python3
"""List durable jobs (newest first): list_jobs.py [--all]  (default: last 20)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _jobs import systemd_env, JOBS_DIR, UNIT_PREFIX, read_json  # noqa: E402


def unit_state(job_id: str) -> str:
    out = subprocess.run(
        ["systemctl", "--user", "is-active", UNIT_PREFIX + job_id + ".service"],
        capture_output=True,
        text=True,
        check=False,
        env=systemd_env(),
    ).stdout.strip()
    timer = subprocess.run(
        ["systemctl", "--user", "is-active", UNIT_PREFIX + job_id + ".timer"],
        capture_output=True,
        text=True,
        check=False,
        env=systemd_env(),
    ).stdout.strip()
    return "scheduled" if timer == "active" and out != "active" else out


def main() -> None:
    dirs = (
        sorted((d for d in JOBS_DIR.glob("*") if d.is_dir()), reverse=True)
        if JOBS_DIR.exists()
        else []
    )
    if "--all" not in sys.argv:
        dirs = dirs[:20]
    rows = []
    for d in dirs:
        meta, status = read_json(d / "meta.json"), read_json(d / "status.json")
        rows.append(
            {
                "id": d.name,
                "name": meta.get("name"),
                "status": status.get("status") or unit_state(d.name),
                "exit_code": status.get("exit_code"),
                "duration": status.get("duration"),
                "notify": status.get("notify"),
                "log": str(d / "out.log"),
            }
        )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
