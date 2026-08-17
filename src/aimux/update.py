"""ai update - update aimux itself, detecting how it was installed."""
import os
import subprocess
import sys


def detect_repo_dir(package_dir):
    """If aimux was installed by symlinking into a git clone (the curl or
    git install path), return that clone's root so it can be `git pull`ed.
    Returns None for a pip install, where the package lives under
    site-packages with no .git anywhere nearby."""
    repo_candidate = os.path.dirname(os.path.dirname(os.path.abspath(package_dir)))
    if os.path.isdir(os.path.join(repo_candidate, ".git")):
        return repo_candidate
    return None


def cmd_update(argv):
    if argv:
        print(f"ai update: unexpected argument '{argv[0]}'", file=sys.stderr)
        sys.exit(1)

    package_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = detect_repo_dir(package_dir)

    if repo_dir:
        print(f"Updating git install at {repo_dir} ...", flush=True)
        result = subprocess.run(["git", "-C", repo_dir, "pull", "--ff-only"])
    else:
        print("Updating pip install of aimux-cli ...", flush=True)
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "aimux-cli"])

    sys.exit(result.returncode)
