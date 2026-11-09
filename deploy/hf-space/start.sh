#!/usr/bin/env bash
set -e
if [ -z "$DATABASE_URL" ]; then
  export PGDATA=/tmp/pg && mkdir -p $PGDATA
  /usr/lib/postgresql/*/bin/initdb -D $PGDATA -U gigbid --auth=trust >/dev/null
  /usr/lib/postgresql/*/bin/pg_ctl -D $PGDATA -o "-k /tmp -p ${PGPORT:-5432}" -l /tmp/pg.log start >/dev/null
  sleep 2; createdb -h /tmp -p ${PGPORT:-5432} -U gigbid gigbid || true
  export DATABASE_URL="postgresql://gigbid@localhost:${PGPORT:-5432}/gigbid"
fi
uvicorn gigsim.server:app --host 127.0.0.1 --port 8081 --log-level warning &
sleep 2
exec uvicorn apps.api.main:app --host 0.0.0.0 --port 7860
