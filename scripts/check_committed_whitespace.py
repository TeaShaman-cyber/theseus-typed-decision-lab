#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

ZERO_SHA = "0" * 40


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def require_ok(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode:
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)


def commit_exists(rev: str) -> bool:
    return run_git("rev-parse", "--verify", f"{rev}^{{commit}}").returncode == 0


def github_push_before() -> str | None:
    if os.environ.get("GITHUB_EVENT_NAME") not in (None, "push"):
        return None
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    path = Path(event_path)
    if not path.is_file():
        raise SystemExit(f"QA_EVENT_PATH_MISSING: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"QA_EVENT_JSON_INVALID: {exc}")
    before = payload.get("before")
    if before is None:
        return None
    if not isinstance(before, str) or len(before) != 40:
        raise SystemExit("QA_PUSH_BEFORE_INVALID")
    return before



def check_commits(rev_range: str) -> None:
    commits = run_git("rev-list", "--reverse", rev_range)
    require_ok(commits)
    for commit in commits.stdout.splitlines():
        if commit:
            require_ok(run_git("show", "-m", "--check", "--pretty=format:", commit))

def check_push_range() -> None:
    before = github_push_before()
    if before and before != ZERO_SHA:
        if not commit_exists(before):
            raise SystemExit(f"QA_PUSH_BEFORE_MISSING: {before}")
        check_commits(f"{before}..HEAD")
        return

    if before == ZERO_SHA:
        # Initial main push has no remote predecessor. Check every commit
        # reachable from HEAD so the root/no-parent case is covered.
        check_commits("HEAD")
        return

    if commit_exists("HEAD^"):
        require_ok(run_git("diff", "--check", "HEAD^", "HEAD"))
    else:
        require_ok(run_git("show", "--check", "--pretty=format:", "HEAD"))


def main() -> None:
    base = os.environ.get("GITHUB_BASE_REF")
    if base:
        base_ref = f"origin/{base}"
        if not commit_exists(base_ref):
            raise SystemExit(f"QA_BASE_REF_MISSING: {base_ref}")
        require_ok(run_git("diff", "--check", f"{base_ref}...HEAD"))
    elif os.environ.get("GITHUB_ACTIONS") == "true":
        check_push_range()

    require_ok(run_git("diff", "--check"))
    require_ok(run_git("diff", "--cached", "--check"))


if __name__ == "__main__":
    main()
