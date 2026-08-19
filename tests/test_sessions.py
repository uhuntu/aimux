import json
import os
import time

import pytest

from aimux import sessions


@pytest.fixture(autouse=True)
def _reset_codex_path_cache():
    # codex_rollout_path() lazily caches sessions.CODEX_HOME's rollout file
    # listing in a module-level global; reset it around every test so one
    # test's tmp_path can't leak into another's.
    sessions._codex_path_index = None
    yield
    sessions._codex_path_index = None


def write_codex_rollout(codex_home, sid, cwd=None, user_text=None, mtime=None):
    """Create a minimal codex rollout file, the actual on-disk source of
    truth codex_light_records() now scans directly (session_index.jsonl is
    only an optional title-enrichment source, not guaranteed to exist)."""
    day_dir = codex_home / "sessions" / "2026" / "08" / "14"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"rollout-2026-08-14T00-00-00-{sid}.jsonl"
    lines = [json.dumps({
        "timestamp": "2026-08-14T00:00:00.000Z", "type": "session_meta",
        "payload": {"id": sid, "cwd": cwd},
    })]
    if user_text is not None:
        lines.append(json.dumps({
            "type": "response_item",
            "payload": {
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": user_text}],
            },
        }))
    path.write_text("\n".join(lines) + "\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


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

def test_codex_thread_names_dedupes_reindexed_thread_rename_uses_utc(monkeypatch, tmp_path):
    """Regression test: codex appends a new session_index.jsonl line each
    time a thread gets auto-renamed, without removing the stale line for
    the same id, and updated_at is UTC ("...Z") -- timegm (not mktime, which
    would reinterpret it as local time) must be used so the *later* rename
    always wins regardless of local TZ."""
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "session_index.jsonl").write_text(
        json.dumps({
            "id": "019f5f6e-a0d0-71e0-9463-8158f339b400",
            "thread_name": "Understand current project",
            "updated_at": "2026-07-14T07:01:53.936145493Z",
        }) + "\n"
        + json.dumps({
            "id": "019f5f6e-a0d0-71e0-9463-8158f339b400",
            "thread_name": "Understand current project (2)",
            "updated_at": "2026-07-14T07:01:55.450675466Z",
        }) + "\n"
    )
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    assert sessions.codex_thread_names() == {
        "019f5f6e-a0d0-71e0-9463-8158f339b400": "Understand current project (2)",
    }


def test_codex_light_records_finds_sessions_with_no_index_entry(monkeypatch, tmp_path):
    """Regression test: session_index.jsonl is only populated by the bare
    CLI's own terminal/exec-mode session tracking. Sessions created via
    other integrations (VSCode, Codex Desktop) use an entirely different
    session store and never get an entry there, even though their rollout
    file exists on disk same as any other session -- codex_light_records
    must still find them by scanning ~/.codex/sessions directly, not by
    relying on session_index.jsonl (which may not even exist)."""
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    # deliberately no session_index.jsonl at all
    sid = "019ffdbe-12ce-7e22-9a7f-30237f491124"
    write_codex_rollout(codex_home, sid, cwd="/data/hunt/work", user_text="fix the login crash")
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    recs = sessions.codex_light_records()
    assert len(recs) == 1
    assert recs[0]["id"] == sid
    assert recs[0]["title"] is None  # no thread_name -- resolve_row falls back to codex_rollout_title
    assert recs[0]["ts"] > 0


def test_codex_light_records_prefers_index_title_when_available(monkeypatch, tmp_path):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    sid = "019ffdbe-12ce-7e22-9a7f-30237f491124"
    write_codex_rollout(codex_home, sid, cwd="/data/hunt/work")
    (codex_home / "session_index.jsonl").write_text(json.dumps({
        "id": sid, "thread_name": "Fix login crash", "updated_at": "2026-08-14T00:00:00Z",
    }) + "\n")
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    recs = sessions.codex_light_records()
    assert recs[0]["title"] == "Fix login crash"


def test_codex_rollout_title_skips_injected_boilerplate(monkeypatch, tmp_path):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    sid = "019ffdbe-12ce-7e22-9a7f-30237f491124"
    day_dir = codex_home / "sessions" / "2026" / "08" / "14"
    day_dir.mkdir(parents=True)
    path = day_dir / f"rollout-2026-08-14T00-00-00-{sid}.jsonl"
    path.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": "/x"}}) + "\n"
        + json.dumps({
            "type": "response_item",
            "payload": {"type": "message", "role": "developer",
                        "content": [{"type": "input_text", "text": "<permissions instructions>..."}]},
        }) + "\n"
        + json.dumps({
            "type": "response_item",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /x\n..."}]},
        }) + "\n"
        + json.dumps({
            "type": "response_item",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "<environment_context>\n  <cwd>/x</cwd>\n..."}]},
        }) + "\n"
        + json.dumps({
            "type": "response_item",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "please fix the login crash"}]},
        }) + "\n"
    )
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    assert sessions.codex_rollout_title(sid) == "please fix the login crash"


def test_codex_rollout_title_missing_session_returns_placeholder(monkeypatch, tmp_path):
    monkeypatch.setattr(sessions, "CODEX_HOME", str(tmp_path / ".codex"))
    assert sessions.codex_rollout_title("no-such-id") == "(no title)"


def test_codex_resolve_finds_rollout_only_sessions(monkeypatch, tmp_path):
    """codex_resolve must find sessions that only exist as rollout files,
    not just ones present in session_index.jsonl (which may not exist)."""
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    sid = "019ffdbe-12ce-7e22-9a7f-30237f491124"
    write_codex_rollout(codex_home, sid, cwd="/x")
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    assert sessions.codex_resolve("019ffdbe") == [sid]


def test_resolve_row_codex_falls_back_to_rollout_title_and_cwd(monkeypatch, tmp_path):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    sid = "019ffdbe-12ce-7e22-9a7f-30237f491124"
    write_codex_rollout(codex_home, sid, cwd="/data/hunt/work", user_text="fix login crash")
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))

    recs = sessions.codex_light_records()
    row = sessions.resolve_row(recs[0])
    assert row[5] == "fix login crash"  # title
    assert row[4] == "/data/hunt/work"  # cwd


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

def test_claude_light_records_dedupes_same_session_across_project_dirs(monkeypatch, tmp_path):
    """Regression test: Claude Code stores a session's transcript under
    every project directory the session's cwd ever touched (e.g. via `cd`
    in tool calls), so the same session id can appear as multiple files.
    Only the most recently modified copy should be reported."""
    projects = tmp_path / "projects"
    dir_a = projects / "-home-hunt"
    dir_b = projects / "-home-hunt-work-aimux"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)

    sid = "cd385445-cec2-43c6-9919-69e87818d2dc"
    old_copy = dir_a / f"{sid}.jsonl"
    new_copy = dir_b / f"{sid}.jsonl"
    old_copy.write_text("{}\n")
    new_copy.write_text("{}\n")

    now = time.time()
    os.utime(old_copy, (now - 100, now - 100))
    os.utime(new_copy, (now, now))

    monkeypatch.setattr(sessions, "CLAUDE_PROJECTS", str(projects))

    recs = sessions.claude_light_records()
    assert len(recs) == 1
    assert recs[0]["path"] == str(new_copy)  # kept the more recently modified copy


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


def test_claude_snippet_finds_topic_past_old_80_line_cutoff(tmp_path):
    """Regression test: a real session had its relevant message at line 92
    of 191, past the old 80-line/3-message scan window, so `ai search`
    never saw it and wrongly reported no relevant sessions."""
    session_file = tmp_path / "s.jsonl"
    lines = [json.dumps({"type": "assistant", "message": {"content": "padding"}}) for _ in range(90)]
    lines.append(json.dumps({
        "type": "user",
        "message": {"content": "please change the default navigation bar mode from taskbar back"},
    }))
    session_file.write_text("\n".join(lines) + "\n")

    snippet = sessions.claude_snippet(str(session_file))
    assert "navigation bar mode" in snippet


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


def test_kimi_snippet_finds_topic_past_old_120_line_cutoff(tmp_path):
    sess_dir = tmp_path / "sessdir"
    (sess_dir / "agents" / "main").mkdir(parents=True)
    wire = sess_dir / "agents" / "main" / "wire.jsonl"
    lines = [json.dumps({"type": "llm.request"}) for _ in range(130)]
    lines.append(json.dumps({
        "type": "turn.prompt",
        "input": [{"type": "text", "text": "please change the default navigation bar mode"}],
    }))
    wire.write_text("\n".join(lines) + "\n")

    snippet = sessions.kimi_snippet(str(sess_dir))
    assert "navigation bar mode" in snippet


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


# ---------- kimi: older state.json schema (ISO timestamps, workDir not cwd) ----------

def test_parse_kimi_timestamp_handles_epoch_ms_and_iso_string():
    assert sessions.parse_kimi_timestamp(1786944176340) == 1786944176340 / 1000.0
    assert sessions.parse_kimi_timestamp("2026-07-20T01:49:19.177Z") == 1784512159
    assert sessions.parse_kimi_timestamp(None) == 0
    assert sessions.parse_kimi_timestamp("") == 0
    assert sessions.parse_kimi_timestamp("not a date") == 0


def test_kimi_light_records_handles_older_schema(monkeypatch, tmp_path):
    """Regression test: older kimi-code sessions store updatedAt/createdAt
    as ISO-8601 strings (not epoch ms) and have no "cwd" key at all -- only
    "workDir". Both used to produce ts=0 / cwd=None ("?" in the listing)."""
    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    sess_dir = tmp_path / "sessdir"
    sess_dir.mkdir()
    (sess_dir / "state.json").write_text(json.dumps({
        "createdAt": "2026-07-19T01:14:01.737Z",
        "updatedAt": "2026-07-20T01:49:19.177Z",
        "title": "hi",
        "workDir": "/data/ThunderBird",
    }))
    (kimi_home / "session_index.jsonl").write_text(json.dumps({
        "sessionId": "session_old", "sessionDir": str(sess_dir), "workDir": "/data/ThunderBird",
    }) + "\n")
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))

    recs = sessions.kimi_light_records(show_all=False)
    assert len(recs) == 1
    assert recs[0]["ts"] > 0
    assert recs[0]["cwd"] == "/data/ThunderBird"


def test_kimi_light_records_falls_back_to_index_workdir_when_state_has_neither(monkeypatch, tmp_path):
    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    sess_dir = tmp_path / "sessdir"
    sess_dir.mkdir()
    (sess_dir / "state.json").write_text(json.dumps({"updatedAt": 1700000000000}))
    (kimi_home / "session_index.jsonl").write_text(json.dumps({
        "sessionId": "session_x", "sessionDir": str(sess_dir), "workDir": "/from/index",
    }) + "\n")
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))

    recs = sessions.kimi_light_records(show_all=False)
    assert recs[0]["cwd"] == "/from/index"


def test_kimi_session_cwd_reads_workdir_from_index(monkeypatch, tmp_path):
    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    (kimi_home / "session_index.jsonl").write_text(
        json.dumps({"sessionId": "session_a", "sessionDir": "/x", "workDir": "/mnt/win/ThunderBird"}) + "\n"
        + json.dumps({"sessionId": "session_b", "sessionDir": "/y", "workDir": "/home/hunt"}) + "\n"
    )
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))

    assert sessions.kimi_session_cwd("session_a") == "/mnt/win/ThunderBird"
    assert sessions.kimi_session_cwd("session_b") == "/home/hunt"
    assert sessions.kimi_session_cwd("session_unknown") is None


def test_cmd_resume_kimi_chdirs_into_session_workdir_first(monkeypatch, tmp_path, capsys):
    """Regression test: `kimi -S <id>` refuses to resume a session created
    under a different cwd. Rather than surfacing that raw error, ai resume
    should chdir into the session's own recorded workDir first."""
    other_dir = tmp_path / "other-project"
    other_dir.mkdir()

    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    (kimi_home / "session_index.jsonl").write_text(
        json.dumps({"sessionId": "session_abc", "sessionDir": "/x", "workDir": str(other_dir)}) + "\n"
    )
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))

    starting_dir = tmp_path
    monkeypatch.chdir(starting_dir)

    exec_calls = []
    monkeypatch.setattr(sessions, "exec_or_die", lambda argv: exec_calls.append(argv))

    sessions.cmd_resume(["kimi", "session_abc"])

    assert os.path.realpath(os.getcwd()) == os.path.realpath(str(other_dir))
    assert exec_calls == [["kimi", "-S", "session_abc"]]
    assert "switching there first" in capsys.readouterr().err


def test_cmd_resume_kimi_skips_chdir_when_already_in_workdir(monkeypatch, tmp_path, capsys):
    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    (kimi_home / "session_index.jsonl").write_text(
        json.dumps({"sessionId": "session_abc", "sessionDir": "/x", "workDir": str(tmp_path)}) + "\n"
    )
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))
    monkeypatch.chdir(tmp_path)

    exec_calls = []
    monkeypatch.setattr(sessions, "exec_or_die", lambda argv: exec_calls.append(argv))

    sessions.cmd_resume(["kimi", "session_abc"])

    assert exec_calls == [["kimi", "-S", "session_abc"]]
    assert "switching there first" not in capsys.readouterr().err


# ---------- list cache / resume by number ----------

def test_cmd_list_writes_numbered_cache(monkeypatch, tmp_path, capsys):
    kimi_home = tmp_path / ".kimi-code"
    kimi_home.mkdir()
    sess_dir = tmp_path / "sessdir"
    sess_dir.mkdir()
    (sess_dir / "state.json").write_text(json.dumps({"cwd": "/home/hunt", "updatedAt": 1700000000000}))
    (kimi_home / "session_index.jsonl").write_text(json.dumps({
        "sessionId": "session_abc123", "sessionDir": str(sess_dir),
    }) + "\n")
    monkeypatch.setattr(sessions, "KIMI_HOME", str(kimi_home))
    monkeypatch.setattr(sessions, "CODEX_HOME", str(tmp_path / "no-codex"))
    monkeypatch.setattr(sessions, "CLAUDE_PROJECTS", str(tmp_path / "no-claude"))
    cache_file = tmp_path / "cache" / "last_list.json"
    monkeypatch.setattr(sessions, "LIST_CACHE_FILE", str(cache_file))

    sessions.cmd_list([])

    out = capsys.readouterr().out
    assert out.splitlines()[0].split()[0] == "#"
    assert out.splitlines()[1].split()[0] == "1"

    cached = json.loads(cache_file.read_text())
    assert cached == [{"tool": "kimi", "id": "session_abc123"}]


def test_resume_by_number_dispatches_correct_session(monkeypatch, tmp_path):
    cache_file = tmp_path / "last_list.json"
    cache_file.write_text(json.dumps([
        {"tool": "claude", "id": "aaaa"},
        {"tool": "kimi", "id": "session_bbbb"},
    ]))
    monkeypatch.setattr(sessions, "LIST_CACHE_FILE", str(cache_file))

    calls = []
    monkeypatch.setattr(sessions, "exec_or_die", lambda argv: calls.append(argv))

    sessions.resume_by_number(2, ["-p", "hi"])

    assert calls == [["kimi", "-S", "session_bbbb", "-p", "hi"]]


def test_resume_by_number_out_of_range(tmp_path, monkeypatch, capsys):
    cache_file = tmp_path / "last_list.json"
    cache_file.write_text(json.dumps([{"tool": "claude", "id": "aaaa"}]))
    monkeypatch.setattr(sessions, "LIST_CACHE_FILE", str(cache_file))

    with pytest.raises(SystemExit):
        sessions.resume_by_number(5, [])
    assert "out of range" in capsys.readouterr().err


def test_resume_by_number_no_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sessions, "LIST_CACHE_FILE", str(tmp_path / "does-not-exist.json"))

    with pytest.raises(SystemExit):
        sessions.resume_by_number(1, [])
    assert "no session list cached" in capsys.readouterr().err


def test_cmd_resume_routes_numeric_arg_to_resume_by_number(monkeypatch):
    calls = []
    monkeypatch.setattr(sessions, "resume_by_number", lambda n, extra: calls.append((n, extra)))

    sessions.cmd_resume(["3", "-p", "hi"])

    assert calls == [(3, ["-p", "hi"])]


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


def test_cmd_list_limit_all_shows_everything(monkeypatch, tmp_path, capsys):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    for i in range(30):
        write_codex_rollout(codex_home, f"0000000{i}-0000-0000-0000-00000000000{i}", cwd="/x", mtime=1000 + i)
    monkeypatch.setattr(sessions, "CODEX_HOME", str(codex_home))
    monkeypatch.setattr(sessions, "CLAUDE_PROJECTS", str(tmp_path / "no-claude"))
    monkeypatch.setattr(sessions, "KIMI_HOME", str(tmp_path / "no-kimi"))
    monkeypatch.setattr(sessions, "LIST_CACHE_FILE", str(tmp_path / "cache" / "last_list.json"))

    sessions.cmd_list(["--limit", "all"])

    # header + 30 rows, comfortably more than the usual 20-row default
    assert len(capsys.readouterr().out.splitlines()) == 31


# ---------- exec_or_die ----------

def test_exec_or_die_missing_binary_reports_cleanly(monkeypatch, capsys):
    def fake_execvp(*_a, **_kw):
        raise FileNotFoundError()
    monkeypatch.setattr(sessions.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit) as exc_info:
        sessions.exec_or_die(["not-a-real-binary", "--flag"])
    assert exc_info.value.code == 127
    assert "not found on PATH" in capsys.readouterr().err
