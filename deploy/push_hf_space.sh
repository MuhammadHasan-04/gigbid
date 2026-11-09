#!/usr/bin/env bash
# Usage: HF_TOKEN=... HF_SPACE=<user>/gigbid ./deploy/push_hf_space.sh
set -euo pipefail
TMP=$(mktemp -d)
git archive HEAD | tar -x -C "$TMP"
cp deploy/hf-space/Dockerfile "$TMP/Dockerfile"; cp deploy/hf-space/README.md "$TMP/README.md"
cd "$TMP" && git init -q -b main && git add -A && git commit -qm "deploy $(date +%F)"
git push -f "https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}" main
