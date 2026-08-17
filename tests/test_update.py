import pytest

from aimux import update


def test_detect_repo_dir_finds_git_root(tmp_path):
    repo = tmp_path / "aimux"
    (repo / ".git").mkdir(parents=True)
    package_dir = repo / "src" / "aimux"
    package_dir.mkdir(parents=True)

    assert update.detect_repo_dir(str(package_dir)) == str(repo)


def test_detect_repo_dir_none_for_pip_install(tmp_path):
    # No .git two levels up -- looks like a site-packages install.
    package_dir = tmp_path / "site-packages" / "aimux"
    package_dir.mkdir(parents=True)

    assert update.detect_repo_dir(str(package_dir)) is None


def test_cmd_update_git_install_runs_git_pull(monkeypatch, capsys):
    monkeypatch.setattr(update, "detect_repo_dir", lambda _pkg: "/some/repo")

    calls = []

    class FakeResult:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return FakeResult()

    monkeypatch.setattr(update.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        update.cmd_update([])

    assert exc_info.value.code == 0
    assert calls == [["git", "-C", "/some/repo", "pull", "--ff-only"]]
    assert "Updating git install" in capsys.readouterr().out


def test_cmd_update_pip_install_runs_pip_upgrade(monkeypatch, capsys):
    monkeypatch.setattr(update, "detect_repo_dir", lambda _pkg: None)

    calls = []

    class FakeResult:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return FakeResult()

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    monkeypatch.setattr(update.sys, "executable", "/fake/python")

    with pytest.raises(SystemExit) as exc_info:
        update.cmd_update([])

    assert exc_info.value.code == 0
    assert calls == [["/fake/python", "-m", "pip", "install", "--upgrade", "aimux-cli"]]
    assert "Updating pip install" in capsys.readouterr().out


def test_cmd_update_propagates_nonzero_exit(monkeypatch):
    monkeypatch.setattr(update, "detect_repo_dir", lambda _pkg: "/some/repo")

    class FakeResult:
        returncode = 1

    monkeypatch.setattr(update.subprocess, "run", lambda *a, **kw: FakeResult())

    with pytest.raises(SystemExit) as exc_info:
        update.cmd_update([])
    assert exc_info.value.code == 1


def test_cmd_update_rejects_extra_arguments(capsys):
    with pytest.raises(SystemExit) as exc_info:
        update.cmd_update(["--bogus"])
    assert exc_info.value.code == 1
    assert "unexpected argument" in capsys.readouterr().err
