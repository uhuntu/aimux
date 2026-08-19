"""ai search - ask an LLM which past sessions are relevant to a topic.

One batched call, not one call per session: doing that would mean up to
hundreds of separate LLM invocations (slow, and real token cost each
time). Instead we build a single prompt listing every candidate session's
title + a short content snippet, and ask the judge model to pick out the
relevant ones by number.
"""
import re
import subprocess
import sys

from . import sessions

JUDGE_CMD = {
    # --no-session-persistence / --ephemeral: the judge call's own prompt
    # (the whole candidate list) would otherwise get saved as a real,
    # visible session -- showing up in `ai`/`ai full` with the raw prompt
    # text as its title, polluting the very listing this command reads.
    # kimi has no equivalent flag, so `--judge kimi` will still leak one.
    "claude": ["claude", "-p", "--no-session-persistence"],
    "codex": ["codex", "exec", "--ephemeral"],
    "kimi": ["kimi", "-p"],
}
DEFAULT_JUDGE = "claude"


def gather_candidates(tool_filter):
    light = []
    if tool_filter in (None, "claude"):
        light += sessions.claude_light_records()
    if tool_filter in (None, "codex"):
        light += sessions.codex_light_records()
    if tool_filter in (None, "kimi"):
        light += sessions.kimi_light_records(show_all=False)
    light.sort(key=lambda r: r["ts"], reverse=True)
    return light


def snippet_for(r):
    tool = r["tool"]
    if tool == "claude":
        return sessions.claude_snippet(r["path"])
    if tool == "codex":
        return r.get("title") or sessions.codex_rollout_title(r["id"])
    return sessions.kimi_snippet(r["dir"])


def build_prompt(topic, entries):
    """entries: list of (tool, cwd, title, snippet), 1 per candidate,
    in the same order they'll be numbered."""
    lines = [
        f"{n}. [{tool}] {cwd} — {title} :: {snippet}"
        for n, (tool, cwd, title, snippet) in enumerate(entries, start=1)
    ]
    return (
        "You are filtering a list of past AI coding-assistant conversations to find "
        f"the ones relevant to this topic: {topic!r}\n\n"
        "Reply with ONLY a comma-separated list of the numbers below that are relevant. "
        "No other text, no explanation. If none are relevant, reply with the single "
        "word: none\n\n" + "\n".join(lines)
    )


def parse_numbers(text, max_n):
    nums = {int(m) for m in re.findall(r"\d+", text)}
    return {n for n in nums if 1 <= n <= max_n}


def cmd_search(argv):
    tool_filter = None
    judge = DEFAULT_JUDGE
    topic_parts = []

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--tool":
            if i + 1 >= len(argv):
                print("ai search: --tool requires a value", file=sys.stderr)
                sys.exit(1)
            tool_filter = argv[i + 1]
            if tool_filter not in sessions.TOOLS:
                print(f"ai search: --tool must be one of {', '.join(sessions.TOOLS)}", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif a == "--judge":
            if i + 1 >= len(argv):
                print("ai search: --judge requires a value", file=sys.stderr)
                sys.exit(1)
            judge = argv[i + 1]
            if judge not in JUDGE_CMD:
                print(f"ai search: --judge must be one of {', '.join(JUDGE_CMD)}", file=sys.stderr)
                sys.exit(1)
            i += 2
        else:
            topic_parts.append(a)
            i += 1

    topic = " ".join(topic_parts).strip()
    if not topic:
        print("Usage: ai search <topic> [--tool claude|codex|kimi] [--judge claude|codex|kimi]", file=sys.stderr)
        sys.exit(1)

    candidates = gather_candidates(tool_filter)
    if not candidates:
        print("No sessions found.")
        return

    rows = [sessions.resolve_row(r) for r in candidates]
    snippets = [snippet_for(r) for r in candidates]
    # row: (tool, full_id, when, short_id, cwd, title)
    entries = [(row[0], row[4], row[5], snippet) for row, snippet in zip(rows, snippets)]
    prompt = build_prompt(topic, entries)

    judge_cmd = JUDGE_CMD[judge]
    print(f"Asking {judge} to judge {len(rows)} sessions against: {topic!r} ...", file=sys.stderr, flush=True)
    try:
        result = subprocess.run([*judge_cmd, prompt], capture_output=True, text=True)
    except FileNotFoundError:
        print(f"ai search: '{judge_cmd[0]}' not found on PATH", file=sys.stderr)
        sys.exit(127)

    if result.returncode != 0:
        print(f"ai search: {judge} exited with an error", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    picked = parse_numbers(result.stdout, len(rows))
    matched = [row for n, row in enumerate(rows, start=1) if n in picked]

    if not matched:
        print("No relevant sessions found.")
        return

    sessions.render_rows(matched)
