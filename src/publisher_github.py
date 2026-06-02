import json
import os
import shutil
import subprocess
from pathlib import Path

from src.logger import log_info


DEFAULT_PUBLIC_URL = "https://ogelslamovuk.github.io/cl_afisha_parser/data/go2.json"


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
    output_file = root / "docs" / "data" / "go2.json"

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

        commit = _run_git(["commit", "-m", "Update published go2.json"], timeout=120)
        if commit.returncode != 0:
            result["errors"].append(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
            return result
        result["committed"] = True

        rev = _run_git(["rev-parse", "--short", "HEAD"])
        if rev.returncode == 0:
            result["commit"] = rev.stdout.strip()

        push = _run_git(["push", "origin", "master"], timeout=180)
        if push.returncode != 0:
            result["errors"].append(push.stderr.strip() or push.stdout.strip() or "git push failed")
            return result

        result["pushed"] = True
        result["published"] = True
        log_info("publish", f"pushed {rel_file}")
        return result
    except Exception as exc:
        result["errors"].append(str(exc))
        return result
