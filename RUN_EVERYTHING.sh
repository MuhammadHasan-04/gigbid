#!/usr/bin/env bash
# =====================================================================================
# GigBid - run everything that is left, from one file.
#   Windows: open Git Bash in this folder and run:  bash RUN_EVERYTHING.sh
#   macOS / Linux:  bash RUN_EVERYTHING.sh
#
# Works from anywhere: if it is not inside the gigbid repo, it clones the repo next to itself.
# Your Groq key goes into the git-ignored .env file, opened in an editor (never typed in the terminal).
# Then: setup -> 30 practice jobs (+ judge, + injection tests) -> held-out -> agent comparison -> real Upwork
# posts -> your 30 judge scores (skippable) -> qwen comparison -> README results -> push -> gigbid_source.zip
# Safe to rerun (finished model calls are cached) - rerun after Groq's daily quota resets if it runs out.
# =====================================================================================
set -uo pipefail
REPO_URL="https://github.com/MuhammadHasan-04/gigbid.git"
HERE="$(cd "$(dirname "$0")" && pwd)"

die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*"; exit 1; }
command -v git >/dev/null || die "Git is not installed (Windows: install Git for Windows from git-scm.com, then run this in Git Bash)."

# ---- find or get the repository
if [ -f "$HERE/scripts/run_everything.sh" ]; then
  REPO="$HERE"
else
  REPO="$HERE/gigbid"
  if [ ! -d "$REPO/.git" ]; then
    echo "Cloning the repository into $REPO ..."
    git clone "$REPO_URL" "$REPO" || die "clone failed"
  fi
fi
cd "$REPO" || die "cannot enter $REPO"
git config core.autocrlf false
echo "Getting the latest version ..."
git pull --ff-only || echo "(could not update - continuing with the local copy)"

# ---- the Groq key, in .env (git-ignored)
if ! grep -q '^GROQ_API_KEY=gsk_' .env 2>/dev/null || grep -q 'PASTE_YOUR_KEY' .env 2>/dev/null; then
  if [ -n "${GROQ_API_KEY:-}" ]; then
    printf 'GROQ_API_KEY=%s\nMODEL_PROFILE=open\n' "$GROQ_API_KEY" > .env
  else
    printf 'GROQ_API_KEY=gsk_PASTE_YOUR_KEY_HERE\nMODEL_PROFILE=open\n' > .env
    echo
    echo "An editor will open .env: replace gsk_PASTE_YOUR_KEY_HERE with your Groq key, save, and close the editor."
    if command -v notepad.exe >/dev/null 2>&1; then notepad.exe .env
    elif command -v notepad >/dev/null 2>&1; then notepad .env
    elif [ "$(uname)" = "Darwin" ]; then open -W -e .env
    else "${EDITOR:-nano}" .env
    fi
  fi
  grep -q '^GROQ_API_KEY=gsk_' .env && ! grep -q 'PASTE_YOUR_KEY' .env || die "No Groq key in .env - run this file again after adding it."
fi
grep -q '^MODEL_PROFILE=' .env || echo "MODEL_PROFILE=open" >> .env

echo
echo "Starting. This takes a few hours on the free Groq tier; leave the window open."
echo "A full log is written to data/runtime/laptop_*.log"
bash scripts/run_everything.sh
