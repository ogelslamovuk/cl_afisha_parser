# VPS Pzz: CL Afisha Parser

## Goal

Move the scheduled `cl_afisha_parser` job from Windows Task Scheduler to VPS Pzz. It must keep publishing the existing public GitHub Pages JSON and Telegram report, run on the established timetable, and be manually launchable from CinemaLab Ops.

## Mandatory acceptance criteria

1. The job runs in a one-shot Docker container on VPS Pzz, never as a permanent process.
2. Cron uses `Europe/Minsk` and the six established times: 09:00, 12:00, 15:00, 18:40, 21:00, 23:59.
3. Only one run can own the output at a time.
4. Secrets stay outside Git and are readable only by the target runtime.
5. A successful run updates the existing public GitHub Pages JSON and emits the existing Telegram report.
6. CinemaLab Ops shows the last execution result and has an audited `Запустить сейчас` action for this job only.
7. Local Windows task remains enabled until the VPS production run passes; it is disabled only during the final cutover.

## QA and live test

Run local tests, independent QA, target-environment E2E checks, then one real VPS run with publication and Telegram delivery. Record evidence in `docs/` without secrets.
