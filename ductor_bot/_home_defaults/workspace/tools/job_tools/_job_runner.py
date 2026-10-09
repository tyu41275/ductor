"""Runs one durable job inside its systemd user unit, then reports the result.

Usage (by run_job.py only): _job_runner.py <job_dir>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _jobs import log_tail, read_json, webhook_endpoint, write_json  # noqa: E402


def notify(meta: dict, status: dict, tail: str) -> str:
    endpoint = webhook_endpoint()
    if endpoint is None:
        return "webhook disabled or ductor-jobs hook missing (run run_job.py --setup)"
    url, token = endpoint
    payload = {
        "id": meta["id"],
        "name": meta["name"],
        "status": status["status"],
        "exit_code": str(status.get("exit_code")),
        "duration": status["duration"],
        "command": meta["command"],
        "log_tail": tail or "(no output)",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return f"delivered ({resp.status})"
    except OSError as exc:
        return f"delivery failed: {exc}"


def main(directory: str) -> int:
    path = Path(directory)
    meta = read_json(path / "meta.json")
    log = path / "out.log"
    started = time.time()
    write_json(
        path / "status.json",
        {"status": "running", "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    )
    timeout = meta.get("timeout_seconds") or None
    with log.open("ab") as out:
        try:
            proc = subprocess.run(
                ["bash", "-lc", meta["command"]],
                stdout=out,
                stderr=subprocess.STDOUT,
                cwd=meta.get("cwd") or None,
                timeout=timeout,
                check=False,
            )
            code, state = proc.returncode, ("succeeded" if proc.returncode == 0 else "failed")
        except subprocess.TimeoutExpired:
            code, state = None, "timed out"
    mins, secs = divmod(int(time.time() - started), 60)
    status = {
        "status": state,
        "exit_code": code,
        "duration": f"{mins}m{secs:02d}s",
        "ended_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if meta.get("notify", True):
        status["notify"] = notify(meta, status, log_tail(log))
    write_json(path / "status.json", status)
    return 0 if state == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
