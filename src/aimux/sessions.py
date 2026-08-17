"""Session listing/resuming across claude, codex, and kimi CLIs.
Invoked via `ai sessions` / `ai resume`, or standalone as `ai-sessions`.
"""
import glob
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CODEX_HOME = os.path.join(HOME, ".codex")
KIMI_HOME = os.path.join(HOME, ".kimi-code")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

TOOLS = ("claude", "codex", "kimi")


def read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def read_jsonl(path):
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except FileNotFoundError:
        return


# ---------- claude ----------

def claude_light_records():
    records = []
    if not os.path.isdir(CLAUDE_PROJECTS):
        return records
    for proj_dir in os.listdir(CLAUDE_PROJECTS):
        full_dir = os.path.join(CLAUDE_PROJECTS, proj_dir)
        if not os.path.isdir(full_dir):
            continue
        for path in glob.glob(os.path.join(full_dir, "*.jsonl")):
            sid = os.path.splitext(os.path.basename(path))[0]
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            cwd_guess = proj_dir.replace("-", "/") if proj_dir.startswith("-") else proj_dir
            records.append({"tool": "claude", "id": sid, "ts": mtime, "path": path, "cwd": cwd_guess})
    return records


def claude_title(path):
    try:
        with open(path) as fh:
            for i, line in enumerate(fh):
                if i > 40:
                    break
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "user":
                    continue
                msg = d.get("message", {})
                content = msg.get("content")
                text = None
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text")
                            break
                if text:
                    return text.strip().replace("\n", " ")[:70]
    except FileNotFoundError:
        pass
    return "(no title)"


def claude_resolve(prefix):
    matches = []
    for r in claude_light_records():
        if r["id"].startswith(prefix):
            matches.append(r["id"])
    return sorted(set(matches))


# ---------- codex ----------

def codex_index():
    path = os.path.join(CODEX_HOME, "session_index.jsonl")
    return list(read_jsonl(path))


def codex_light_records():
    records = []
    for entry in codex_index():
        sid = entry.get("id")
        if not sid:
            continue
        updated = entry.get("updated_at")
        try:
            ts = time.mktime(time.strptime(updated[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            ts = 0
        records.append({
            "tool": "codex", "id": sid, "ts": ts,
            "title": entry.get("thread_name") or "(no title)",
        })
    return records


_codex_path_index = None


def codex_rollout_path(sid):
    global _codex_path_index
    if _codex_path_index is None:
        _codex_path_index = {}
        sessions_dir = os.path.join(CODEX_HOME, "sessions")
        for path in glob.glob(os.path.join(sessions_dir, "**", "*.jsonl"), recursive=True):
            m = UUID_RE.search(os.path.basename(path))
            if m:
                _codex_path_index[m.group(0)] = path
    return _codex_path_index.get(sid)


def codex_cwd(sid):
    path = codex_rollout_path(sid)
    if not path:
        return None
    for d in read_jsonl(path):
        if d.get("type") == "session_meta":
            return d.get("payload", {}).get("cwd")
        break
    return None


def codex_resolve(prefix):
    return sorted({e["id"] for e in codex_index() if e.get("id", "").startswith(prefix)})


# ---------- kimi ----------

def kimi_index():
    path = os.path.join(KIMI_HOME, "session_index.jsonl")
    return list(read_jsonl(path))


def kimi_light_records(show_all):
    records = []
    for entry in kimi_index():
        sid = entry.get("sessionId")
        sdir = entry.get("sessionDir")
        if not sid or not sdir:
            continue
        state = read_json(os.path.join(sdir, "state.json")) or {}
        if state.get("archived") and not show_all:
            continue
        updated_ms = state.get("updatedAt") or state.get("createdAt") or 0
        try:
            updated_ms = float(updated_ms)
        except (TypeError, ValueError):
            updated_ms = 0
        records.append({
            "tool": "kimi", "id": sid, "ts": (updated_ms / 1000.0) if updated_ms else 0,
            "cwd": state.get("cwd"), "dir": sdir,
        })
    return records


def kimi_title(sdir):
    wire = os.path.join(sdir, "agents", "main", "wire.jsonl")
    try:
        with open(wire) as fh:
            for i, line in enumerate(fh):
                if i > 60:
                    break
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") == "turn.prompt":
                    for block in d.get("input", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            return block.get("text", "").strip().replace("\n", " ")[:70]
    except FileNotFoundError:
        pass
    return "(no title)"


def kimi_resolve(prefix):
    ids = [e.get("sessionId", "") for e in kimi_index()]
    matches = [i for i in ids if i.startswith(prefix)]
    if not matches and not prefix.startswith("session_"):
        alt = "session_" + prefix
        matches = [i for i in ids if i.startswith(alt)]
    return sorted(set(matches))


# ---------- shared ----------

def relative_time(ts):
    if not ts:
        return "?"
    delta = time.time() - ts
    if delta < 0:
        delta = 0
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    return f"{int(delta / 86400)}d ago"


def cmd_list(args):
    limit = 20
    tool_filter = None
    cwd_filter = False
    show_all = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit":
            limit = int(args[i + 1]); i += 2
        elif a == "--tool":
            tool_filter = args[i + 1]; i += 2
        elif a == "--cwd":
            cwd_filter = True; i += 1
        elif a == "--all":
            show_all = True; i += 1
        else:
            print(f"ai sessions: unknown option '{a}'", file=sys.stderr)
            sys.exit(1)

    light = []
    if tool_filter in (None, "claude"):
        light += claude_light_records()
    if tool_filter in (None, "codex"):
        light += codex_light_records()
    if tool_filter in (None, "kimi"):
        light += kimi_light_records(show_all)

    light.sort(key=lambda r: r["ts"], reverse=True)

    cwd = os.getcwd()
    if cwd_filter:
        light = [r for r in light if r.get("cwd") == cwd]

    top = light[:limit]

    rows = []
    for r in top:
        tool = r["tool"]
        if tool == "claude":
            title = claude_title(r["path"])
            cwd_show = r.get("cwd") or "?"
        elif tool == "codex":
            title = r.get("title", "(no title)")
            cwd_show = codex_cwd(r["id"]) or "?"
        else:
            title = kimi_title(r["dir"])
            cwd_show = r.get("cwd") or "?"
        rows.append((tool, relative_time(r["ts"]), r["id"][:12], cwd_show, title))

    if not rows:
        print("No sessions found.")
        return

    w_tool = max(4, max(len(r[0]) for r in rows))
    w_when = max(4, max(len(r[1]) for r in rows))
    w_id = max(2, max(len(r[2]) for r in rows))
    w_cwd = min(40, max(3, max(len(r[3]) for r in rows)))

    header = f"{'TOOL':<{w_tool}}  {'WHEN':<{w_when}}  {'ID':<{w_id}}  {'CWD':<{w_cwd}}  TITLE"
    print(header)
    for tool, when, sid, cwd_show, title in rows:
        cwd_disp = cwd_show if len(cwd_show) <= w_cwd else "…" + cwd_show[-(w_cwd - 1):]
        print(f"{tool:<{w_tool}}  {when:<{w_when}}  {sid:<{w_id}}  {cwd_disp:<{w_cwd}}  {title}")


def cmd_resume(args):
    if not args or args[0] not in TOOLS:
        print(f"Usage: ai resume <{'|'.join(TOOLS)}> [session-id-or-prefix]", file=sys.stderr)
        sys.exit(1)
    tool = args[0]
    rest = args[1:]

    if not rest:
        if tool == "claude":
            os.execvp("claude", ["claude", "--resume"])
        elif tool == "codex":
            os.execvp("codex", ["codex", "resume"])
        else:
            os.execvp("kimi", ["kimi", "-S"])
        return

    prefix, extra = rest[0], rest[1:]
    resolver = {"claude": claude_resolve, "codex": codex_resolve, "kimi": kimi_resolve}[tool]
    matches = resolver(prefix)

    if len(matches) == 1:
        full_id = matches[0]
    elif len(matches) == 0:
        full_id = prefix  # let the underlying tool decide
    else:
        print(f"ai resume: ambiguous id '{prefix}', matches:", file=sys.stderr)
        for m in matches:
            print(f"  {m}", file=sys.stderr)
        sys.exit(1)

    if tool == "claude":
        os.execvp("claude", ["claude", "--resume", full_id, *extra])
    elif tool == "codex":
        os.execvp("codex", ["codex", "resume", full_id, *extra])
    else:
        os.execvp("kimi", ["kimi", "-S", full_id, *extra])


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("Usage: ai-sessions <list|resume> [options]")
        sys.exit(0)
    sub, rest = sys.argv[1], sys.argv[2:]
    if sub == "list":
        cmd_list(rest)
    elif sub == "resume":
        cmd_resume(rest)
    else:
        print(f"ai-sessions: unknown subcommand '{sub}'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
