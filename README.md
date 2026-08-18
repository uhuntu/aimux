# aimux

[![test](https://github.com/uhuntu/aimux/actions/workflows/test.yml/badge.svg)](https://github.com/uhuntu/aimux/actions/workflows/test.yml)

A tiny, dependency-free wrapper that unifies three AI coding-agent CLIs — [Claude Code](https://claude.com/product/claude-code), [OpenAI Codex CLI](https://github.com/openai/codex), and [Kimi CLI](https://www.kimi-cli.com/) — behind one set of flags, plus a cross-tool session list and resume.

No daemon, no config file, no build step — just a small Python package (`src/aimux/`) that reads each tool's own on-disk session store directly.

## Install

**Via pip** (the package is named `aimux-cli` on PyPI; the commands installed are `ai`, `aim`, `aimux`, `ai-sessions`):

```bash
pip install aimux-cli
```

**Via curl**, one line, no manual clone:

```bash
curl -fsSL https://raw.githubusercontent.com/uhuntu/aimux/master/install.sh | bash
```

**Via git**, if you'd rather clone it yourself first:

```bash
git clone https://github.com/uhuntu/aimux.git
cd aimux && ./install.sh
```

Either of the last two symlinks `ai`, `ai-sessions`, and the `aim`/`aimux` aliases into `~/.local/bin` (override with `AIMUX_BIN_DIR=/some/other/dir`). The curl form clones the repo to `~/.local/share/aimux` first (override with `AIMUX_REPO_DIR`). Nothing is copied — the clone stays the source of truth.

Requires `claude`, `codex`, and/or `kimi` already installed and on `PATH` (only the ones you actually use need to be present).

## Update

```bash
ai update        # update aimux itself
ai update tools  # update claude, codex, and kimi (whichever are installed)
ai update all    # both
```

`ai update` detects how aimux itself was installed and does the right thing: `git pull --ff-only` for a curl/git install, `pip install --upgrade aimux-cli` for a pip install.

`ai update tools` runs each CLI's own update command (`claude update`, `codex update`, `kimi update`), skipping any that aren't installed. If one fails, the others still run; the exit code reflects the worst failure.

Equivalent manual commands for updating aimux itself, if you'd rather:

- **pip**: `pip install --upgrade aimux-cli`
- **curl**: re-run the same one-liner — it fast-forwards the existing clone before relinking
- **git**: `git -C /path/to/aimux pull` — the symlinks point straight into the repo, so this alone is enough

## Usage

```bash
ai                          # recent sessions across all three tools (same as `ai sessions`)
ai claude -p "prompt"       # -> claude -p "prompt"
ai codex -p -m o3 "prompt"  # -> codex exec -m o3 "prompt"
ai kimi -c                  # -> kimi -c

ai sessions --limit 10      # list recent sessions, all tools
ai sessions --tool codex    # filter to one tool
ai sessions --cwd           # only sessions started in the current directory
ai sessions --all           # include archived sessions

ai resume kimi 97946bc7     # resume by short id / prefix (resolved against real session ids)
ai resume claude            # no id -> tool's own interactive picker
ai resume 3                 # resume row 3 from the last `ai`/`ai sessions` listing
```

Every `ai`/`ai sessions` listing is numbered and cached, so `ai resume <N>` is usually the fastest way in: run `ai`, glance at the row you want, `ai resume 3`. The cache is just the last listing you saw — it's overwritten by the next `ai sessions` call and doesn't try to detect if the underlying sessions changed since.

### Normalized flags (`ai <tool> ...`)

| Flag | Meaning | claude | codex | kimi |
|---|---|---|---|---|
| `-p`, `--print` | non-interactive, print and exit | `-p` | `exec` | `-p` |
| `-c`, `--continue` | continue most recent session in cwd | `--continue` | `exec resume --last` | `-c` |
| `-m`, `--model <model>` | model to use | `--model` | `-m` | `-m` |
| `--add-dir <dir>` | additional workspace directory (repeatable) | `--add-dir` | `--add-dir` | `--add-dir` |
| `-y`, `--yolo` | auto-approve tool calls | `--dangerously-skip-permissions` | `--approve-for-me` (stays sandboxed) | `-y` |

Anything after a literal `--`, or any flag this wrapper doesn't recognize, passes straight through to the underlying CLI unchanged.

## How session listing works

`ai-sessions` reads each tool's native session storage — no shared index, no background process:

- **claude**: `~/.claude/projects/*/*.jsonl`
- **codex**: `~/.codex/session_index.jsonl` + `~/.codex/sessions/**/*.jsonl` for cwd lookup
- **kimi**: `~/.kimi-code/session_index.jsonl` + each session's `state.json` / `agents/main/wire.jsonl`

Titles are best-effort (scanned from the first user message / prompt in each session's log). Claude's cwd is read from the session content itself when available, falling back to a guess decoded from the project-directory name only if that's missing.

## Development

```bash
pip install -e ".[test]"
pytest tests/ -v
```

## What this isn't

Not a TUI, not a worktree manager, not a multi-agent orchestrator. If you want any of that, look at [ccmanager](https://github.com/kbwo/ccmanager) (git-worktree-centric session manager, also supports Kimi CLI) or [claude-squad](https://github.com/smtg-ai/claude-squad).

## License

MIT — see [LICENSE](LICENSE).
