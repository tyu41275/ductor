#!/usr/bin/env python3
"""Start a durable job: a shell command that keeps running after this session ends.

    run_job.py --name "dh promote" [--at "2026-10-09 12:35" | --in 30m] [--timeout 2h] \
               [--cwd DIR] [--no-notify] -- COMMAND [ARGS...]
    run_job.py --setup     # create the ductor-jobs wake webhook (once)

Prints JSON: id, unit, log path, schedule. The result comes back into this chat
through the ductor-jobs wake webhook when the job ends.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _jobs import (
    CONFIG_PATH,
    HOOK_ID,
    HOOKS_PATH,
    UNIT_PREFIX,
    job_dir,
    new_job_id,
    systemd_env,
    read_json,
    webhook_endpoint,
    write_json,
)  # noqa: E402

PROMPT = (
    "Durable job {{name}} ({{id}}) ended: {{status}}, exit code {{exit_code}}, after {{duration}}.\n"
    "Command: {{command}}\nLast output:\n{{log_tail}}\n\n"
    "Tell the user the result in plain language and do any follow-up you promised for this job."
)
DURATION = re.compile(r"^(\d+)([smhd])$")


def seconds(text: str) -> int:
    match = DURATION.match(text.strip())
    if not match:
        raise SystemExit(f"bad duration {text!r}: use e.g. 90s, 30m, 2h, 1d")
    return int(match[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match[2]]


def setup() -> dict:
    if webhook_endpoint() is None:
        hooks = read_json(HOOKS_PATH).get("hooks", [])
        if not any(isinstance(h, dict) and h.get("id") == HOOK_ID for h in hooks):
            subprocess.run(
                [
                    sys.executable,
                    str(HERE.parent / "webhook_tools" / "webhook_add.py"),
                    "--name",
                    HOOK_ID,
                    "--title",
                    "Durable jobs",
                    "--description",
                    "Results of run_job.py jobs",
                    "--mode",
                    "wake",
                    "--prompt-template",
                    PROMPT,
                ],
                check=True,
            )
    enabled = bool(read_json(CONFIG_PATH).get("webhooks", {}).get("enabled"))
    return {
        "hook": HOOK_ID,
        "webhooks_enabled": enabled,
        "next": "ready"
        if enabled
        else "set webhooks.enabled=true in config.json, then restart the bot",
    }


def launch(args: argparse.Namespace) -> dict:
    if not args.command:
        raise SystemExit("give the command after --")
    if not shutil.which("systemd-run"):
        raise SystemExit("systemd-run not found: durable jobs need systemd user units")
    if args.timeout and seconds(args.timeout) <= 0:
        raise SystemExit("--timeout must be longer than 0")
    job_id = new_job_id(args.name)
    directory = job_dir(job_id)
    directory.mkdir(parents=True)
    command = args.command[0] if len(args.command) == 1 else shlex.join(args.command)
    meta = {
        "id": job_id,
        "name": args.name,
        "command": command,
        "cwd": str(Path(args.cwd or ".").resolve()),
        "timeout_seconds": seconds(args.timeout) if args.timeout else None,
        "notify": not args.no_notify,
        "at": args.at,
        "in": args.delay,
    }
    write_json(directory / "meta.json", meta)
    unit = UNIT_PREFIX + job_id
    cmd = [
        "systemd-run",
        "--user",
        f"--unit={unit}",
        "--collect",
        "--quiet",
        f"--description=ductor job {args.name}",
    ]
    if args.at:
        cmd.append(f"--on-calendar={args.at}")
    elif args.delay:
        cmd.append(f"--on-active={seconds(args.delay)}s")
    cmd += [sys.executable, str(HERE / "_job_runner.py"), str(directory)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=systemd_env())
    if result.returncode != 0:
        shutil.rmtree(directory, ignore_errors=True)
        raise SystemExit(f"systemd-run failed: {result.stderr.strip()}")
    return {
        "id": job_id,
        "unit": unit,
        "log": str(directory / "out.log"),
        "starts": args.at or (f"in {args.delay}" if args.delay else "now"),
        "notify": "ready"
        if (meta["notify"] and webhook_endpoint())
        else ("off" if not meta["notify"] else "NOT CONFIGURED: run run_job.py --setup"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--name", default="job")
    when = parser.add_mutually_exclusive_group()
    when.add_argument("--at", help="systemd calendar time, e.g. '2026-10-09 12:35:00 UTC'")
    when.add_argument("--in", dest="delay", help="delay, e.g. 30m")
    parser.add_argument("--timeout", help="kill after, e.g. 2h")
    parser.add_argument("--cwd")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    print(json.dumps(setup() if args.setup else launch(args), indent=2))


if __name__ == "__main__":
    main()
