#!/usr/bin/env bash
# Dev helper: wipe runtime state (GigSim, Postgres app tables, checkpoints, traces).
set -e
curl -s -XPOST -H "Authorization: Bearer ${GIGSIM_ADMIN_TOKEN:-gigsim-admin-token}" ${GIGSIM_BASE_URL:-http://localhost:8081}/v1/admin/reset >/dev/null || true
psql "${DATABASE_URL:-postgresql://gigbid:gigbid@localhost:5432/gigbid}" -q -c "truncate jobs_seen, run_events, pipeline, conversations, rejections; delete from checkpoints; delete from checkpoint_writes; delete from checkpoint_blobs; delete from store;" 2>/dev/null || true
rm -rf data/runtime/gigsim_state.json data/runtime/traces data/runtime/audit data/runtime/*_idempotency.sqlite data/runtime/workspace
echo reset
