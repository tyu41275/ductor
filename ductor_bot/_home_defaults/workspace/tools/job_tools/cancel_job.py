#!/usr/bin/env python3
"""Cancel a durable job (running or scheduled): cancel_job.py JOB_ID"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _jobs import systemd_env, UNIT_PREFIX, job_dir, write_json  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    job_id = sys.argv[1]
    if not job_dir(job_id).is_dir():
        raise SystemExit(f"no such job: {job_id}")
    for suffix in (".timer", ".service"):
        subprocess.run(
            ["systemctl", "--user", "stop", UNIT_PREFIX + job_id + suffix],
            capture_output=True,
            check=False,
            env=systemd_env(),
        )
    write_json(job_dir(job_id) / "status.json", {"status": "cancelled"})
    print(json.dumps({"id": job_id, "status": "cancelled"}))


if __name__ == "__main__":
    main()
