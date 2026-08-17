#!/usr/bin/env bash
# Symlinks aimux's commands (ai, ai-sessions, plus optional short aliases)
# into a directory on your PATH. Run after cloning:
#   ./install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${AIMUX_BIN_DIR:-$HOME/.local/bin}"

mkdir -p "$BIN_DIR"

for name in ai ai-sessions; do
  ln -sf "$SCRIPT_DIR/bin/$name" "$BIN_DIR/$name"
  echo "linked $BIN_DIR/$name -> $SCRIPT_DIR/bin/$name"
done

for alias_name in aim aimux; do
  if [[ ! -e "$BIN_DIR/$alias_name" ]]; then
    ln -sf "$SCRIPT_DIR/bin/ai" "$BIN_DIR/$alias_name"
    echo "linked $BIN_DIR/$alias_name -> $SCRIPT_DIR/bin/ai (alias)"
  fi
done

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Note: $BIN_DIR is not on your PATH. Add it in your shell rc file, e.g.:" ;
     echo "  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo "Done. Try: ai --help"
