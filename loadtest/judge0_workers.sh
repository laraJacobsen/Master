#!/usr/bin/env bash
# Switch the local Judge0's worker count (COUNT) for a load-test condition.
#
#   loadtest/judge0_workers.sh 4      # 4, 8 or 16
#   loadtest/judge0_workers.sh reset  # back to the original judge0.conf
#
# judge0.conf in ~/judge0-v1.13.1 is root-owned, and Judge0's load-config
# sources it AFTER the environment (so `COUNT=` there would win over an env
# var). But load-config prefers /api/judge0.conf when it exists, so a copy of
# the config with COUNT set (~/judge0-loadtest/judge0.countN.conf, outside the
# repo because it holds Judge0's DB passwords) is mounted there for the
# workers service only. Only the workers container is recreated.
set -euo pipefail
JUDGE0_DIR="${JUDGE0_DIR:-$HOME/judge0-v1.13.1}"
CONF_DIR="${CONF_DIR:-$HOME/judge0-loadtest}"
PROJECT=judge0-v1131

# docker-compose 1.29 can't *recreate* a container on newer Docker engines
# (KeyError: 'ContainerConfig'), so remove the workers container first and
# bring it up fresh.
compose_up() {
  docker-compose -p "$PROJECT" "$@" rm -s -f workers
  docker-compose -p "$PROJECT" "$@" up -d --no-deps workers
}

if [[ "${1:-}" == "reset" ]]; then
  compose_up -f "$JUDGE0_DIR/docker-compose.yml"
else
  n="${1:?usage: $0 COUNT|reset}"
  conf="$CONF_DIR/judge0.count$n.conf"
  if [[ ! -f "$conf" ]]; then
    sed "s/^COUNT=.*/COUNT=$n/" "$JUDGE0_DIR/judge0.conf" > "$conf"
    chmod 644 "$conf"
  fi
  override="$CONF_DIR/override.count$n.yml"
  cat > "$override" <<YML
services:
  workers:
    volumes:
      - $conf:/api/judge0.conf:ro
YML
  compose_up -f "$JUDGE0_DIR/docker-compose.yml" -f "$override"
fi

# Wait for the worker processes to come up, then report how many there are.
for _ in $(seq 30); do
  got=$(docker exec "${PROJECT}_workers_1" sh -c 'ps aux | grep -c "[r]esque-2.0.0: Waiting"' 2>/dev/null || true)
  [[ "${got:-0}" -gt 0 ]] && break
  sleep 1
done
sleep 2
docker exec "${PROJECT}_workers_1" sh -c 'echo "COUNT env: $(grep -o "COUNT=\"*[0-9]*" /api/environment | head -1)"; echo "worker processes: $(ps aux | grep -c "[r]esque-2.0.0")"'
