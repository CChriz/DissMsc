#!/usr/bin/env bash
# Setup for jwclone WSL env: user-local Go + git-lfs (no sudo), PATH hooks, lfs pull datasets.
set -uo pipefail
LOCAL="$HOME/.local"
BIN="$LOCAL/bin"
mkdir -p "$BIN"

echo "== [1/4] Go toolchain =="
if [ -x "$LOCAL/go/bin/go" ]; then
  echo "already installed: $("$LOCAL/go/bin/go" version)"
else
  GOVER=$(curl -fsSL 'https://go.dev/VERSION?m=text' | head -1)
  [ -n "$GOVER" ] || GOVER=go1.25.3
  echo "installing $GOVER ..."
  curl -fsSL -o /tmp/go.tgz "https://go.dev/dl/${GOVER}.linux-amd64.tar.gz" || { echo "GO DOWNLOAD FAILED"; exit 1; }
  rm -rf "$LOCAL/go"
  tar -C "$LOCAL" -xzf /tmp/go.tgz && rm -f /tmp/go.tgz
fi
ln -sf "$LOCAL/go/bin/go" "$BIN/go"
ln -sf "$LOCAL/go/bin/gofmt" "$BIN/gofmt"
"$BIN/go" version || { echo "GO INSTALL FAILED"; exit 1; }

echo "== [2/4] git-lfs =="
if command -v git-lfs >/dev/null 2>&1 || [ -x "$BIN/git-lfs" ]; then
  echo "already installed: $("$BIN/git-lfs" version 2>/dev/null || git-lfs version)"
else
  LFSVER=$(curl -fsSL https://api.github.com/repos/git-lfs/git-lfs/releases/latest | grep -oP '"tag_name":\s*"\K[^"]+' | head -1)
  [ -n "$LFSVER" ] || LFSVER=v3.6.1
  echo "installing git-lfs $LFSVER ..."
  curl -fsSL -o /tmp/lfs.tgz "https://github.com/git-lfs/git-lfs/releases/download/${LFSVER}/git-lfs-linux-amd64-${LFSVER}.tar.gz" || { echo "LFS DOWNLOAD FAILED"; exit 1; }
  mkdir -p /tmp/lfsx && tar -C /tmp/lfsx -xzf /tmp/lfs.tgz
  find /tmp/lfsx -name git-lfs -type f -exec cp {} "$BIN/git-lfs" \;
  chmod +x "$BIN/git-lfs"
  rm -rf /tmp/lfsx /tmp/lfs.tgz
fi
export PATH="$BIN:$PATH"
git-lfs version || { echo "GIT-LFS INSTALL FAILED"; exit 1; }

echo "== [3/4] PATH hooks =="
HOOK='export PATH="$HOME/.local/bin:$HOME/.local/go/bin:$PATH"'
for f in "$HOME/.profile" "$HOME/.bashrc" "$HOME/jwclone/jwrun/team.env"; do
  [ -f "$f" ] || continue
  if grep -qF '.local/go/bin' "$f"; then
    echo "hook already present in $f"
  else
    printf '\n# go + git-lfs (user-local, added by setup_env.sh)\n%s\n' "$HOOK" >> "$f"
    echo "hook appended to $f"
  fi
done

echo "== [4/4] TeamBench datasets (git lfs pull) =="
cd "$HOME/TeamBench" || { echo "TeamBench repo not found"; exit 1; }
git lfs install --skip-smudge >/dev/null 2>&1 || git lfs install >/dev/null 2>&1
git lfs pull || { echo "LFS PULL FAILED"; exit 1; }

echo "== verify =="
go version
for f in datasets/adult_income.csv datasets/ames_housing.csv datasets/online_retail.csv; do
  if head -c 40 "$f" | grep -q 'git-lfs'; then echo "STILL POINTER: $f"; else echo "OK ($(stat -c%s "$f") bytes): $f"; fi
done
echo "SETUP DONE"
