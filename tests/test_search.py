import json

import pytest

from aimux import search, sessions


def test_judge_calls_dont_persist_a_visible_session():
    """Regression test: without an ephemeral/no-persist flag, the judge
    call's own prompt (the whole candidate list) gets saved as a real
    session and shows up in `ai`/`ai full` with the raw prompt as its
    title -- the tool polluting the listing it reads from."""
    assert "--no-session-persistence" in search.JUDGE_CMD["claude"]
    assert "--ephemeral" in search.JUDGE_CMD["codex"]


def test_build_prompt_numbers_entries_in_order():
    prompt = search.build_prompt("nfc issue", [
        ("codex", "/a", "Find isnfcon", "Find isnfcon"),
        ("claude", "/b", "hi", "hi there"),
    ])
    assert "1. [codex] /a — Find isnfcon :: Find isnfcon" in prompt
    assert "2. [claude] /b — hi :: hi there" in prompt
    assert "'nfc issue'" in prompt
    assert "reply with the single word: none" in prompt


@pytest.mark.parametrize(
    "text,max_n,expected",
    [
        ("1, 3, 5", 5, {1, 3, 5}),
        ("1 and 3 and maybe also 5", 5, {1, 3, 5}),
        ("none", 5, set()),
        ("", 5, set()),
        ("7, 8", 5, set()),  # out of range, dropped
        ("2, 2, 2", 5, {2}),  # deduped
    ],
)
def test_parse_numbers(text, max_n, expected):
    assert search.parse_numbers(text, max_n) == expected


def test_gather_candidates_respects_tool_filter(monkeypatch):
    monkeypatch.setattr(sessions, "claude_light_records", lambda: [{"tool": "claude", "ts": 1}])
    monkeypatch.setattr(sessions, "codex_light_records", lambda: [{"tool": "codex", "ts": 2}])
    monkeypatch.setattr(sessions, "kimi_light_records", lambda show_all: [{"tool": "kimi", "ts": 3}])

    assert [r["tool"] for r in search.gather_candidates(None)] == ["kimi", "codex", "claude"]
    assert [r["tool"] for r in search.gather_candidates("codex")] == ["codex"]


def test_snippet_for_dispatches_per_tool(monkeypatch):
    monkeypatch.setattr(sessions, "claude_snippet", lambda path: f"claude:{path}")
    monkeypatch.setattr(sessions, "codex_rollout_snippet", lambda sid: f"codex:{sid}")
    monkeypatch.setattr(sessions, "kimi_snippet", lambda d: f"kimi:{d}")

    assert search.snippet_for({"tool": "claude", "path": "/x.jsonl"}) == "claude:/x.jsonl"
    assert search.snippet_for({"tool": "codex", "id": "abc123", "title": "Find isnfcon"}) == "codex:abc123"
    assert search.snippet_for({"tool": "kimi", "dir": "/y"}) == "kimi:/y"


def test_cmd_search_rejects_empty_topic(capsys):
    with pytest.raises(SystemExit):
        search.cmd_search([])
    assert "Usage" in capsys.readouterr().err


def test_cmd_search_rejects_bad_judge(capsys):
    with pytest.raises(SystemExit):
        search.cmd_search(["--judge", "bogus", "topic"])
    assert "must be one of" in capsys.readouterr().err


def test_cmd_search_filters_to_llm_picked_rows(monkeypatch, capsys):
    fake_candidates = [
        {"tool": "codex", "id": "id-1", "ts": 3, "title": "Find isnfcon"},
        {"tool": "claude", "id": "id-2", "ts": 2, "path": "/x.jsonl", "cwd": "/home/hunt"},
        {"tool": "kimi", "id": "id-3", "ts": 1, "dir": "/y"},
    ]
    monkeypatch.setattr(search, "gather_candidates", lambda tool_filter: fake_candidates)
    monkeypatch.setattr(sessions, "claude_snippet", lambda path: "irrelevant chat")
    monkeypatch.setattr(sessions, "kimi_snippet", lambda d: "irrelevant chat")

    monkeypatch.setattr(sessions, "resolve_row", lambda r: (
        r["tool"], r["id"], "1h ago", r["id"][:6], r.get("cwd") or "?", r.get("title", "(no title)"),
    ))

    rendered = []
    monkeypatch.setattr(sessions, "render_rows", lambda rows: rendered.append(rows))

    class FakeResult:
        returncode = 0
        stdout = "1"  # only the first (codex) candidate is relevant
        stderr = ""

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return FakeResult()

    monkeypatch.setattr(search.subprocess, "run", fake_run)

    search.cmd_search(["nfc", "frequency", "lock"])

    assert calls[0][:2] == ["claude", "-p"]
    assert "nfc frequency lock" in calls[0][-1]  # prompt is always the last arg
    assert len(rendered) == 1
    assert [row[1] for row in rendered[0]] == ["id-1"]


def test_cmd_search_uses_requested_judge_tool(monkeypatch):
    monkeypatch.setattr(search, "gather_candidates", lambda tool_filter: [
        {"tool": "codex", "id": "id-1", "ts": 1, "title": "x"},
    ])
    monkeypatch.setattr(sessions, "resolve_row", lambda r: (
        r["tool"], r["id"], "1h ago", r["id"][:6], "?", r.get("title", "(no title)"),
    ))
    monkeypatch.setattr(sessions, "render_rows", lambda rows: None)

    calls = []

    class FakeResult:
        returncode = 0
        stdout = "none"
        stderr = ""

    monkeypatch.setattr(search.subprocess, "run", lambda argv, **kw: calls.append(argv) or FakeResult())

    search.cmd_search(["--judge", "kimi", "topic"])

    assert calls[0][:2] == ["kimi", "-p"]


def test_cmd_search_missing_judge_binary_reports_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(search, "gather_candidates", lambda tool_filter: [
        {"tool": "codex", "id": "id-1", "ts": 1, "title": "x"},
    ])
    monkeypatch.setattr(sessions, "resolve_row", lambda r: (
        r["tool"], r["id"], "1h ago", r["id"][:6], "?", r.get("title", "(no title)"),
    ))

    def fake_run(argv, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(search.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        search.cmd_search(["topic"])
    assert exc_info.value.code == 127
    assert "not found on PATH" in capsys.readouterr().err


def test_cmd_search_no_candidates(monkeypatch, capsys):
    monkeypatch.setattr(search, "gather_candidates", lambda tool_filter: [])

    search.cmd_search(["topic"])

    assert "No sessions found" in capsys.readouterr().out
