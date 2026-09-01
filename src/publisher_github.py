import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from src.logger import log_info


DEFAULT_PUBLIC_URL = "https://ogelslamovuk.github.io/cl_afisha_parser/data/go2.json"
DEFAULT_REPO = "ogelslamovuk/cl_afisha_parser"
DEFAULT_WORKFLOW = "Deploy GitHub Pages"
DEFAULT_PUBLISHED_FILE = "docs/data/go2.json"
DEFAULT_BRANCH = "master"


def _dump_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _run_git(args, timeout=60):
    return subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _run_gh(args, timeout=30):
    return subprocess.run(
        ["gh", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _deploy_job_status(run_id, repo, cfg):
    """Read Pages deploy job status even when GitHub leaves the workflow in progress."""
    job_name = str(cfg.get("deploy_job_name", "deploy")).casefold()
    result = _run_gh(
        [
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--json",
            "jobs",
        ]
    )
    if result.returncode != 0:
        return None

    try:
        jobs = json.loads(result.stdout or "{}").get("jobs", [])
    except (AttributeError, json.JSONDecodeError):
        return None

    for job in jobs:
        name = str(job.get("name", "")).casefold()
        if job_name in name and job.get("status") == "completed":
            conclusion = job.get("conclusion")
            return {
                "ok": conclusion == "success",
                "conclusion": conclusion,
                "name": job.get("name"),
            }
    return None


def _wait_for_pages_deploy(commit_sha, cfg):
    if shutil.which("gh") is None:
        return {"ok": False, "error": "gh executable not found; cannot verify Pages deploy"}

    repo = cfg.get("repo", DEFAULT_REPO)
    workflow = cfg.get("workflow", DEFAULT_WORKFLOW)
    timeout_seconds = max(1, int(cfg.get("deploy_timeout_seconds", 1200)))
    poll_seconds = max(1, int(cfg.get("deploy_poll_seconds", 10)))
    deadline = time.time() + timeout_seconds
    last_state = "not started"

    while time.time() < deadline:
        run = _run_gh(
            [
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                workflow,
                "--commit",
                commit_sha,
                "--limit",
                "1",
                "--json",
                "databaseId,status,conclusion,url",
            ]
        )
        if run.returncode != 0:
            last_state = run.stderr.strip() or run.stdout.strip() or "gh run list failed"
        else:
            try:
                runs = json.loads(run.stdout or "[]")
            except json.JSONDecodeError as exc:
                last_state = f"failed to parse gh run list output: {exc}"
            else:
                if runs:
                    item = runs[0]
                    status = item.get("status")
                    conclusion = item.get("conclusion")
                    url = item.get("url")
                    last_state = f"status={status} conclusion={conclusion}"
                    if status == "completed":
                        if conclusion == "success":
                            return {"ok": True, "run_url": url}
                        return {"ok": False, "error": f"Pages workflow concluded {conclusion}", "run_url": url}
                    if item.get("databaseId"):
                        deploy_job = _deploy_job_status(item["databaseId"], repo, cfg)
                        if deploy_job:
                            if deploy_job["ok"]:
                                return {"ok": True, "run_url": url, "confirmed_by": "deploy_job"}
                            return {
                                "ok": False,
                                "error": f"Pages deploy job concluded {deploy_job['conclusion']}",
                                "run_url": url,
                            }

        time.sleep(poll_seconds)

    return {"ok": False, "error": f"Timed out waiting for Pages workflow ({last_state})"}


def publish_to_github_pages(payload, report, config):
    cfg = (config or {}).get("github_pages", {})
    enabled = cfg.get("enabled", True)
    result = {
        "enabled": bool(enabled),
        "published": False,
        "committed": False,
        "pushed": False,
        "skipped": False,
        "errors": [],
        "file": None,
        "commit": None,
        "deploy_checked": False,
        "deploy_run_url": None,
        "url": cfg.get("public_url", DEFAULT_PUBLIC_URL),
    }

    if not enabled:
        result["skipped"] = True
        return result

    if report.get("status") != "success":
        result["skipped"] = True
        result["errors"].append("report status is not success")
        return result

    root = Path.cwd()
    output_file = root / cfg.get("file", DEFAULT_PUBLISHED_FILE)

    try:
        _dump_json(output_file, payload)
        rel_file = str(output_file.relative_to(root)).replace(os.sep, "/")
        result["file"] = rel_file
        log_info("publish", f"prepared {rel_file}")

        if shutil.which("git") is None:
            result["errors"].append("git executable not found")
            return result

        inside = _run_git(["rev-parse", "--is-inside-work-tree"])
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            result["errors"].append("current directory is not a git repository")
            return result

        add = _run_git(["add", rel_file])
        if add.returncode != 0:
            result["errors"].append(add.stderr.strip() or "git add failed")
            return result

        diff = _run_git(["diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            result["published"] = True
            result["skipped"] = True
            log_info("publish", "no changes")
            return result

        commit_message = cfg.get("commit_message", "Update published go2.json")
        commit = _run_git(["commit", "-m", commit_message], timeout=120)
        if commit.returncode != 0:
            result["errors"].append(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
            return result
        result["committed"] = True

        rev = _run_git(["rev-parse", "--short", "HEAD"])
        if rev.returncode == 0:
            result["commit"] = rev.stdout.strip()
        full_rev = _run_git(["rev-parse", "HEAD"])
        commit_sha = full_rev.stdout.strip() if full_rev.returncode == 0 else result["commit"]

        branch = cfg.get("branch", DEFAULT_BRANCH)
        push = _run_git(["push", "origin", branch], timeout=180)
        if push.returncode != 0:
            result["errors"].append(push.stderr.strip() or push.stdout.strip() or "git push failed")
            return result

        result["pushed"] = True
        log_info("publish", f"pushed {rel_file}")

        if cfg.get("wait_for_deploy", True):
            result["deploy_checked"] = True
            deploy = _wait_for_pages_deploy(commit_sha, cfg)
            result["deploy_run_url"] = deploy.get("run_url")
            if not deploy.get("ok"):
                result["errors"].append(deploy.get("error", "Pages workflow failed"))
                return result

        result["published"] = True
        return result
    except Exception as exc:
        result["errors"].append(str(exc))
        return result
