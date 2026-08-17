import json
import time

import pytest

from aimux import sessions


# ---------- relative_time ----------

@pytest.mark.parametrize(
    "delta,expected",
    [
        (0, "0s ago"),
        (30, "30s ago"),
        (90, "1m ago"),
        (3661, "1h ago"),
        (90000, "1d ago"),
    ],
)
def test_relative_time(monkeypatch, delta, expected):
    now = 1_800_000_000
    monkeypatch.setattr(sessions.time, "time", lambda: now)
    assert sessions.relative_time(now - delta) == expected


def test_relative_time_missing_ts():
    assert sessions.relative_time(0) == "?"
    assert sessions.relative_time(None) == "?"


# ---------- codex ----------

def test_codex_timestamp_parsed_as_utc_not_local(monkeypatch, tmp_path):
    """Regression test: updated_at is UTC ("...Z"); the parser must not
    reinterpret it as local time (previously off by the local UTC offset)."""
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    index = codex_home / "session_index.jsonl"
    index.write_text(json.dumps({
        "id": "019ff51f-9ace-7e03-88bc-a782a5fcd9ab",
        "thread_name": "Find isnfcon",
        "updated_at": "2026-08-12T08:38:53.111355365Z",
    }) + "\n")
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    recs = sessions.codex_light_records()
    assert len(recs) == 1
    # Correct UTC epoch for 2026-08-12T08:38:53Z, independent of local TZ.
    assert recs[0]["ts"] == 1786523933


def test_codex_resolve_prefix_match(monkeypatch, tmp_path):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    index = codex_home / "session_index.jsonl"
    index.write_text(
        json.dumps({"id": "aaaa1111-0000-0000-0000-000000000000", "updated_at": "2026-01-01T00:00:00Z"}) + "\n"
        + json.dumps({"id": "aaaa2222-0000-0000-0000-000000000000", "updated_at": "2026-01-01T00:00:00Z"}) + "\n"
        + json.dumps({"id": "bbbb0000-0000-0000-0000-000000000000", "updated_at": "2026-01-01T00:00:00Z"}) + "\n"
    )
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    assert sessions.codex_resolve("bbbb") == ["bbbb0000-0000-0000-0000-000000000000"]
    assert sessions.codex_resolve("aaaa") == [
        "aaaa1111-0000-0000-0000-000000000000",
        "aaaa2222-0000-0000-0000-000000000000",
    ]
    assert sessions.codex_resolve("zzzz") == []


# ---------- claude ----------

def test_claude_title_and_cwd_prefers_real_cwd_over_dirname_guess(tmp_path):
    session_file = tmp_path / "abcd1234.jsonl"
    session_file.write_text(
        json.dumps({"type": "queue-operation", "content": "ignored"}) + "\n"
        + json.dumps({
            "type": "user",
            "cwd": "/home/hunt",
            "message": {"role": "user", "content": "hello there"},
        }) + "\n"
    )

    title, cwd = sessions.claude_title_and_cwd(str(session_file), cwd_fallback="/home/hunt/work/aimux")
    assert title == "hello there"
    assert cwd == "/home/hunt"  # real cwd wins over the directory-name guess


def test_claude_title_and_cwd_falls_back_when_no_cwd_field(tmp_path):
    session_file = tmp_path / "abcd1234.jsonl"
    session_file.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n"
    )
    title, cwd = sessions.claude_title_and_cwd(str(session_file), cwd_fallback="/guessed/path")
    assert title == "hi"
    assert cwd == "/guessed/path"


def test_claude_title_and_cwd_missing_file():
    title, cwd = sessions.claude_title_and_cwd("/no/such/file.jsonl", cwd_fallback="/fallback")
    assert title == "(no title)"
    assert cwd == "/fallback"


def test_claude_content_list_with_text_block(tmp_path):
    session_file = tmp_path / "s.jsonl"
    session_file.write_text(json.dumps({
        "type": "user",
        "message": {"content": [{"type": "image"}, {"type": "text", "text": "the real prompt"}]},
    }) + "\n")
    title, _ = sessions.claude_title_and_cwd(str(session_file), cwd_fallback=None)
    assert title == "the real prompt"


# ---------- kimi ----------

def test_kimi_resolve_tries_session_prefix_fallback(monkeypatch, tmp_path):
    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    index = kimi_home / "session_index.jsonl"
    index.write_text(json.dumps({
        "sessionId": "session_97946bc7-c5d4-4419-85d1-1316cb7f4295",
        "sessionDir": str(tmp_path / "sessdir"),
    }) + "\n")
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))

    # bare prefix, without the "session_" the id actually starts with
    assert sessions.kimi_resolve("97946bc7") == ["session_97946bc7-c5d4-4419-85d1-1316cb7f4295"]
    # already-prefixed also works
    assert sessions.kimi_resolve("session_97946bc7") == ["session_97946bc7-c5d4-4419-85d1-1316cb7f4295"]


def test_kimi_light_records_skips_archived_unless_all(monkeypatch, tmp_path):
    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    sess_dir = tmp_path / "sessdir"
    sess_dir.mkdir()
    (sess_dir / "state.json").write_text(json.dumps({
        "cwd": "/home/hunt", "updatedAt": 1700000000000, "archived": True,
    }))
    (kimi_home / "session_index.jsonl").write_text(json.dumps({
        "sessionId": "session_archived", "sessionDir": str(sess_dir),
    }) + "\n")
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))

    assert sessions.kimi_light_records(show_all=False) == []
    assert len(sessions.kimi_light_records(show_all=True)) == 1


# ---------- cmd_list argument validation ----------

def test_cmd_list_rejects_non_numeric_limit(capsys):
    with pytest.raises(SystemExit):
        sessions.cmd_list(["--limit", "not-a-number"])
    assert "expects a number" in capsys.readouterr().err


def test_cmd_list_rejects_unknown_tool(capsys):
    with pytest.raises(SystemExit):
        sessions.cmd_list(["--tool", "bogus"])
    assert "must be one of" in capsys.readouterr().err


def test_cmd_list_rejects_dangling_flag(capsys):
    with pytest.raises(SystemExit):
        sessions.cmd_list(["--limit"])
    assert "requires a value" in capsys.readouterr().err


# ---------- exec_or_die ----------

def test_exec_or_die_missing_binary_reports_cleanly(monkeypatch, capsys):
    def fake_execvp(*_a, **_kw):
        raise FileNotFoundError()
    monkeypatch.setattr(sessions.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit) as exc_info:
        sessions.exec_or_die(["not-a-real-binary", "--flag"])
    assert exc_info.value.code == 127
    assert "not found on PATH" in capsys.readouterr().err
