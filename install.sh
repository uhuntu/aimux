#!/usr/bin/env bash
# Symlinks aimux's commands (ai, ai-sessions, plus optional short aliases)
# into a directory on your PATH.
#
# Run after cloning:
#   ./install.sh
#
# Or as a one-liner, which clones the repo first:
#   curl -fsSL https://raw.githubusercontent.com/uhuntu/aimux/master/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/uhuntu/aimux.git"
BIN_DIR="${AIMUX_BIN_DIR:-$HOME/.local/bin}"

# When piped via `curl | bash`, there's no script file, so BASH_SOURCE[0] is
# unset (not just non-matching) -- guard the lookup instead of dereferencing
# it directly under `set -u`.
SOURCE_PATH="${BASH_SOURCE[0]:-}"
if [[ -n "$SOURCE_PATH" && -f "$(dirname "$SOURCE_PATH")/bin/ai" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
else
  # Not running from inside a clone -- fetch one first, then re-run from there.
  REPO_DIR="${AIMUX_REPO_DIR:-$HOME/.local/share/aimux}"
  if [[ -d "$REPO_DIR/.git" ]]; then
    git -C "$REPO_DIR" pull --ff-only
  else
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
  fi
  exec "$REPO_DIR/install.sh"
fi

mkdir -p "$BIN_DIR"

for name in ai ai-sessions; do
  ln -sf "$SCRIPT_DIR/bin/$name" "$BIN_DIR/$name"
  echo "linked $BIN_DIR/$name -> $SCRIPT_DIR/bin/$name"
done

for alias_name in aim aimux; do
  ln -sf "$SCRIPT_DIR/bin/ai" "$BIN_DIR/$alias_name"
  echo "linked $BIN_DIR/$alias_name -> $SCRIPT_DIR/bin/ai (alias)"
done

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Note: $BIN_DIR is not on your PATH. Add it in your shell rc file, e.g.:" ;
     echo "  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo "Done. Try: ai --help"
