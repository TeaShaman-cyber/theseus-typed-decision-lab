#!/usr/bin/env python3
import os
import subprocess
import sys


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


def main() -> None:
    base = os.environ.get("GITHUB_BASE_REF")
    if base:
        base_ref = f"origin/{base}"
        if not commit_exists(base_ref):
            raise SystemExit(f"QA_BASE_REF_MISSING: {base_ref}")
        require_ok(run_git("diff", "--check", f"{base_ref}...HEAD"))
    elif os.environ.get("GITHUB_ACTIONS") == "true" and commit_exists("HEAD^"):
        require_ok(run_git("diff", "--check", "HEAD^", "HEAD"))

    require_ok(run_git("diff", "--check"))
    require_ok(run_git("diff", "--cached", "--check"))


if __name__ == "__main__":
    main()
