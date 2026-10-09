# Durable Jobs

Run a shell command that keeps going after your CLI session ends (and across
bot restarts), optionally at a set time, and get its result back in this chat.
Use it for anything you promise to do or check later: waiting for CI, a
promotion at a given time, a long build or test run. Never rely on in-session
background shells for these; they die when your turn ends.

## Start

```bash
python3 tools/job_tools/run_job.py --name "dh promote" --at "2026-10-09 12:35:00 UTC" --timeout 1h -- relay promotion status
python3 tools/job_tools/run_job.py --name "suite" --in 5m -- "cd ~/repo && pytest -q"
python3 tools/job_tools/run_job.py --name "build" -- make image
```

- `--at` takes a systemd calendar time; `--in` a delay (`90s`, `30m`, `2h`); neither = now.
- `--timeout` kills the command after that long. `--cwd` sets the working directory.
- One argument after `--` is run as a bash script (`bash -lc`); several are quoted and joined.
- For "wait until X, then do Y", write the loop into the command itself (poll with
  `sleep`, stop at a deadline, exit non-zero if it gave up).

When the job ends, a `ductor-jobs` wake message arrives in this chat with the
status, exit code, duration and the last 30 lines of output. Tell the user the
result in plain language and do the follow-up you promised.

## Manage

```bash
python3 tools/job_tools/list_jobs.py          # newest 20 (--all for every job)
python3 tools/job_tools/cancel_job.py JOB_ID  # stop a running or scheduled job
```

Files: `~/.ductor/jobs/<id>/` holds `meta.json`, `status.json` and `out.log`.

## One-time setup

```bash
python3 tools/job_tools/run_job.py --setup
```

Creates the `ductor-jobs` wake webhook. Webhooks must be enabled
(`webhooks.enabled: true` in `config/config.json`, then restart the bot).
`run_job.py` prints `notify: NOT CONFIGURED` until both are true; the job
still runs, but you must check `list_jobs.py` yourself.
