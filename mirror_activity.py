#!/usr/bin/env python3
"""
mirror_activity.py

Feed source repos (URLs or local paths) in; for each, append empty mirror
commits to a private "activity log" repo using your correct identity and
the original author dates. Source repos are never modified.

Two ways to run:

  Interactive:
      python mirror_activity.py
      # answers the prompts, then paste repos at `repo>` (q to finish)

  Non-interactive (script / scheduled task):
      python mirror_activity.py \
          --mirror https://github.com/yawhite1/Elza \
          --name "YasirW" \
          --email timeoztenounce@gmail.com \
          --old-email y.white005@gmail.com \
          --source C:/path/to/repoA --source https://github.com/u/repoB \
          --push --yes

The mirror argument can be either:
  * a local path (e.g. C:\\Users\\you\\code\\activity-log)
  * a GitHub URL — in which case the repo is cloned to ~/code/<repo-name>
    on first run and reused on later runs.

Requires git on PATH and Python 3.9+.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ─── shell helpers ────────────────────────────────────────────────────────

def run(cmd, cwd=None, env=None, check=True, capture=True):
    res = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        check=check,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return res.stdout if capture else ""


def is_git_repo(path):
    return (Path(path) / ".git").exists()


def looks_like_url(s):
    return s.startswith(("http://", "https://", "git@", "ssh://"))


# ─── mirror repo setup ────────────────────────────────────────────────────

def _basename_from_url(url):
    """https://github.com/u/Foo.git → 'Foo'.  git@github.com:u/Foo → 'Foo'."""
    # Strip query / fragment / trailing slash, then take last path component.
    s = url.rstrip("/").split("?")[0].split("#")[0]
    # Handle scp-style git@host:owner/repo
    if ":" in s and not s.startswith(("http://", "https://", "ssh://")):
        s = s.split(":", 1)[1]
    name = s.rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    # Replace anything ugly so the local dir name is safe.
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name) or "activity-log"
    return name


def _ensure_initial_commit(repo):
    """Make sure the repo has at least one commit (push needs a HEAD)."""
    out = run(["git", "log", "--oneline", "-1"], cwd=repo, check=False).strip()
    if not out:
        run(["git", "commit", "--allow-empty", "-m", "init mirror"], cwd=repo)


def _ensure_remote(repo, url):
    """Make sure `origin` points at `url`. Set or update as needed."""
    existing = run(["git", "remote", "get-url", "origin"], cwd=repo, check=False).strip()
    if not existing:
        run(["git", "remote", "add", "origin", url], cwd=repo)
    elif existing != url:
        # Don't silently rewrite — refuse rather than push to the wrong place.
        raise SystemExit(
            f"Mirror at {repo} has origin '{existing}', not '{url}'.\n"
            f"Either pass the matching URL or pick a different local path."
        )


def ensure_mirror_repo(mirror_arg):
    """
    Resolve the mirror to a usable local checkout.

    URL → cloned to ~/code/<basename>, or reused if already there.
    Path → used as-is; initialized if empty.
    """
    if looks_like_url(mirror_arg):
        local = (Path.home() / "code" / _basename_from_url(mirror_arg)).resolve()
        local.parent.mkdir(parents=True, exist_ok=True)

        if local.exists() and is_git_repo(local):
            _ensure_remote(local, mirror_arg)
        elif local.exists() and any(local.iterdir()):
            # Folder exists, has stuff, but isn't a git repo. Refuse rather
            # than `git init` on top of unknown files.
            raise SystemExit(
                f"Local dir {local} exists but isn't a git repo. "
                "Move it aside or point --mirror at a fresh path."
            )
        else:
            print(f"  cloning {mirror_arg} -> {local} ...")
            # Some clones print "warning: cloned an empty repository" but
            # still exit 0 and create the directory; that's fine.
            run(["git", "clone", mirror_arg, str(local)])
            _ensure_remote(local, mirror_arg)

        _ensure_initial_commit(local)
        return local

    # Local path branch.
    mirror = Path(mirror_arg).expanduser().resolve()
    mirror.mkdir(parents=True, exist_ok=True)
    if not is_git_repo(mirror):
        run(["git", "init", "-b", "main"], cwd=mirror)
        _ensure_initial_commit(mirror)
        print(f"  initialized new git repo at {mirror}")
    else:
        _ensure_initial_commit(mirror)
    return mirror


# ─── source repo reading + mirror commit ──────────────────────────────────

def get_mirrored_shas(mirror):
    """Parse mirror history for `mirror: <short-sha> -- ...` subjects."""
    out = run(["git", "log", "--pretty=format:%s"], cwd=mirror, check=False)
    shas = set()
    for line in out.splitlines():
        if line.startswith("mirror: "):
            token = line[len("mirror: "):].split(" ", 1)[0]
            shas.add(token)
    return shas


def clone_to_temp(url):
    tmp = tempfile.mkdtemp(prefix="mirror_src_")
    print(f"  cloning {url} ...")
    run(["git", "clone", "--no-tags", "--quiet", url, tmp])
    return tmp


def read_source_commits(src_path, old_email):
    """Oldest-first list of (sha, iso_date, subject) for matching commits."""
    fmt = "%H%x09%aI%x09%s"
    args = [
        "git", "log",
        "--reverse",
        "--all",
        f"--author={old_email}",
        f"--pretty=format:{fmt}",
    ]
    out = run(args, cwd=src_path)
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        sha, date, subject = parts
        commits.append((sha, date, subject))
    return commits


def mirror_commit(mirror, sha, date, subject, name, email):
    msg = f"mirror: {sha[:8]} -- {subject}"
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date
    env["GIT_COMMITTER_DATE"] = date
    env["GIT_AUTHOR_NAME"] = name
    env["GIT_COMMITTER_NAME"] = name
    env["GIT_AUTHOR_EMAIL"] = email
    env["GIT_COMMITTER_EMAIL"] = email
    run(["git", "commit", "--allow-empty", "-m", msg], cwd=mirror, env=env)


def process_source(src_input, mirror, mirrored_shas, name, email, old_email):
    is_url = looks_like_url(src_input)
    cleanup_path = None
    if is_url:
        src_path = clone_to_temp(src_input)
        cleanup_path = src_path
    else:
        src_path = str(Path(src_input).expanduser().resolve())

    try:
        if not is_git_repo(src_path):
            print(f"  ! not a git repo: {src_path}")
            return 0
        commits = read_source_commits(src_path, old_email)
        if not commits:
            print(f"  no commits by {old_email} found in this repo")
            return 0
        new_count = 0
        for sha, date, subject in commits:
            short = sha[:8]
            if short in mirrored_shas:
                continue
            mirror_commit(mirror, sha, date, subject, name, email)
            mirrored_shas.add(short)
            new_count += 1
        return new_count
    finally:
        if cleanup_path:
            shutil.rmtree(cleanup_path, ignore_errors=True)


# ─── push (sets upstream on first run) ────────────────────────────────────

def push_mirror(mirror):
    # Try a plain push first — works once upstream is set. Fall back to
    # `-u origin HEAD` so the very first push from a freshly-init'd repo
    # also works without the user wiring it up by hand.
    try:
        run(["git", "push"], cwd=mirror, capture=False)
    except subprocess.CalledProcessError:
        run(["git", "push", "-u", "origin", "HEAD"], cwd=mirror, capture=False)


# ─── interactive prompts ──────────────────────────────────────────────────

def prompt(text, default=None, required=False):
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"{text}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default
        if not required:
            return ""
        print("  (required)")


# ─── main / CLI ───────────────────────────────────────────────────────────

def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Mirror real commits from source repos into a private activity-log repo.",
    )
    p.add_argument("--mirror", help="Mirror repo: URL (cloned) or local path.")
    p.add_argument("--name", help="Your name (committer/author on the mirror).")
    p.add_argument("--email", help="Your CORRECT email for the mirror commits.")
    p.add_argument(
        "--old-email",
        dest="old_email",
        help="Email to filter source commits by (your old/wrong address).",
    )
    p.add_argument(
        "--source",
        dest="sources",
        action="append",
        default=[],
        help="A source repo URL or local path. Repeatable.",
    )
    push_grp = p.add_mutually_exclusive_group()
    push_grp.add_argument("--push", action="store_true", help="Push after mirroring.")
    push_grp.add_argument("--no-push", action="store_true", help="Skip the push step.")
    p.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Don't ask interactive questions when sources/credentials are passed.",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    print("=" * 64)
    print(" mirror_activity -- mirror real commits into a private repo")
    print("=" * 64)

    default_mirror = str(Path.home() / "code" / "activity-log")
    mirror_arg = args.mirror or prompt("Mirror repo path or URL", default=default_mirror)
    name = args.name or prompt("Your name (for mirror commits)", required=True)
    email = args.email or prompt("Your CORRECT email (for mirror commits)", required=True)
    old_email = args.old_email or prompt(
        "OLD/wrong email to filter source commits by", required=True
    )

    mirror = ensure_mirror_repo(mirror_arg)
    mirrored_shas = get_mirrored_shas(mirror)
    print(f"\nMirror repo: {mirror}")
    print(f"Already mirrored: {len(mirrored_shas)} commit(s)\n")

    sources = list(args.sources)
    if not sources and not args.yes:
        print("Paste a repo URL or local path. Type 'q' when done.\n")
        while True:
            src = input("repo> ").strip()
            if src.lower() in ("q", "quit", "exit"):
                break
            if src:
                sources.append(src)

    total_new = 0
    for src in sources:
        print(f"\n>> {src}")
        try:
            n = process_source(src, mirror, mirrored_shas, name, email, old_email)
            print(f"  + {n} new commit(s) mirrored")
            total_new += n
        except subprocess.CalledProcessError as e:
            err = (e.stderr or str(e)).strip()
            print(f"  x failed: {err}")

    print(f"\nDone. {total_new} new commit(s) added this session.")

    remotes = run(["git", "remote"], cwd=mirror, check=False).strip()
    if not remotes:
        print(
            "\nNo remote configured on the mirror repo. Create a PRIVATE repo on\n"
            "GitHub, then from the mirror directory run:\n"
            f"  cd {mirror}\n"
            "  git remote add origin <url>\n"
            "  git push -u origin HEAD\n"
            "Also enable Settings -> Profile -> 'Include private contributions on my profile'."
        )
        return

    if total_new == 0 and not args.push:
        return

    should_push = (
        args.push
        or (
            not args.no_push
            and (args.yes or prompt("Push to remote now? (y/n)", default="y").lower().startswith("y"))
        )
    )
    if should_push:
        print("pushing ...")
        try:
            push_mirror(mirror)
            print("pushed.")
        except subprocess.CalledProcessError as e:
            print(f"push failed: {(e.stderr or str(e)).strip()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\naborted.")
        sys.exit(1)
