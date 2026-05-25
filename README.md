# activity-log

Mirror real commits from any number of source repos into one private
"activity log" repo — re-stamped with **your** correct identity and the
**original** author dates — so a GitHub account that was missing
contributions (wrong email, since-deleted org, archived repo, etc.) ends
up with a complete green graph.

Source repos are never modified. The mirror is just a stream of empty
commits whose messages look like `mirror: <short-sha> -- <original subject>`,
so a re-run is a no-op for anything already mirrored.

## Requirements

- Git on PATH
- Python 3.9+
- Push access to the destination GitHub repo (HTTPS via Git Credential
  Manager, or SSH key — whatever you already use to push)

## Quick start

1. Create a repo on GitHub to act as the mirror (it can be public or
   private — if you go private, also flip
   **Settings → Profile → Include private contributions on my profile**).
2. Run the script:

```bash
python mirror_activity.py \
    --mirror   https://github.com/<you>/activity-log \
    --name     "Your Name" \
    --email    you@correct-email.com \
    --old-email old.wrong@email.com \
    --source   https://github.com/<org>/<repo> \
    --source   C:/path/to/local/repo \
    --push --yes
```

That's it. The script will:

1. Clone the mirror repo (or reuse the local checkout from last run).
2. For each `--source`, find every commit where `--old-email` was the
   author, and append a matching empty commit to the mirror with
   `--name` / `--email` and the original `GIT_AUTHOR_DATE`.
3. `git push -u origin HEAD` once everything is queued.

Re-runs are safe: commits already mirrored (matched by short SHA in the
mirror's history) are skipped.

## Arguments

| Flag | What it does |
|------|--------------|
| `--mirror` | Mirror repo — a GitHub URL (will be cloned) **or** a local path. |
| `--name` | Name to put on the mirror commits. |
| `--email` | Correct email to put on the mirror commits. |
| `--old-email` | Email to filter source commits by. Anything authored by this address gets mirrored. |
| `--source <url-or-path>` | Source repo. **Repeatable** — pass it once per repo. |
| `--push` / `--no-push` | Push (or skip) at the end. Defaults to asking. |
| `--yes`, `-y` | Skip the "Push to remote now? (y/n)" confirmation. |

Run with no flags for an interactive prompt-based flow.

## Examples

### One source, push

```bash
python mirror_activity.py \
    --mirror https://github.com/me/activity-log \
    --name "Me" --email me@new.com --old-email me@old.com \
    --source ~/code/big-old-project \
    --push --yes
```

### Many sources, mix of remote + local

```bash
python mirror_activity.py \
    --mirror https://github.com/me/activity-log \
    --name "Me" --email me@new.com --old-email me@old.com \
    --source https://github.com/team/repo-a \
    --source https://github.com/team/repo-b \
    --source C:/Users/me/code/local-repo \
    --push --yes
```

### Daily cron / Task Scheduler

Schedule the same command — re-runs only add new commits, so it's safe
to run nightly even with the same `--source` list.

## How the de-dupe works

The mirror's own commit subjects are scanned for the
`mirror: <8-char-sha> -- ...` prefix on startup. Any source commit whose
short SHA is already in that set is skipped. Don't rewrite mirror
history — if you do, run with a fresh mirror folder so the SHA-set is
rebuilt from scratch.

## Where the local checkout lives

When `--mirror` is a URL, the script clones it once to
`~/code/<repo-name>` and reuses that local checkout on every later run.
Delete that folder if you want a fresh clone (the script also refuses
to write into it if its `origin` doesn't match the `--mirror` URL).

## Caveats

- This is for personal contribution-graph backfill from repos *you
  actually wrote code in*. Don't point it at someone else's commits.
- The mirror commits land on the mirror's default branch. If you push
  the mirror to a repo that already has commits, mirror commits stack
  on top — that's fine for an activity-log repo but probably not what
  you want if the mirror repo also holds real code.
- Commit *dates* are preserved, but the SHAs are new. So this is a log
  of your activity, not a 1-to-1 backup.
