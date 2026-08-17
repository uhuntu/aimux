# aimux

A tiny, dependency-free wrapper that unifies three AI coding-agent CLIs — [Claude Code](https://claude.com/product/claude-code), [OpenAI Codex CLI](https://github.com/openai/codex), and [Kimi CLI](https://www.kimi-cli.com/) — behind one set of flags, plus a cross-tool session list and resume.

No daemon, no config file, no build step. Two POSIX-ish scripts (`bin/ai` in Bash, `bin/ai-sessions` in Python 3) that read each tool's own on-disk session store directly.

## Install

```bash
git clone https://github.com/uhuntu/aimux.git
ln -s "$(pwd)/aimux/bin/ai" ~/.local/bin/ai
ln -s "$(pwd)/aimux/bin/ai-sessions" ~/.local/bin/ai-sessions
```

Requires `claude`, `codex`, and/or `kimi` already installed and on `PATH` (only the ones you actually use need to be present).

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
```

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

Titles are best-effort (scanned from the first user message / prompt in each session's log), and claude's displayed cwd is decoded from its project-directory name, so treat both as approximate.

## What this isn't

Not a TUI, not a worktree manager, not a multi-agent orchestrator. If you want any of that, look at [ccmanager](https://github.com/kbwo/ccmanager) (git-worktree-centric session manager, also supports Kimi CLI) or [claude-squad](https://github.com/smtg-ai/claude-squad).

## License

MIT — see [LICENSE](LICENSE).
