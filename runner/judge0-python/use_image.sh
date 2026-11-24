#!/usr/bin/env bash
# Points the local Judge0's server and workers at the test-runner image (or back).
#
#   use_image.sh            server + workers run judge0-pytest:latest
#   use_image.sh <tag>      server + workers run that tag
#   use_image.sh --revert   both back on the stock judge0/judge0:1.13.1
#
# Both run code: a wait=true submission (what the backend sends) runs inside the
# server container, a wait=false one in a worker. Only those two containers are
# recreated (db and redis keep running), so Judge0 is unreachable for a few
# seconds; queued jobs survive in redis. The compose file and the root-owned
# judge0.conf are only read, never changed: the image is swapped with a compose
# override file kept next to this script.
#
# The containers are removed before they're recreated: docker-compose 1.29
# can't recreate a container whose new image came from a newer Docker builder
# (KeyError: 'ContainerConfig'). Neither keeps state, so nothing is lost.
#
# JUDGE0_DIR (default ~/judge0-v1.13.1) is the folder with docker-compose.yml;
# JUDGE0_PROJECT (default judge0-v1131) its compose project name.
set -euo pipefail
remove_runners() {
  for service in server workers; do
    docker ps -aq --filter "label=com.docker.compose.project=$project" \
      --filter "label=com.docker.compose.service=$service" | xargs -r docker rm -f > /dev/null
  done
}
here="$(cd "$(dirname "$0")" && pwd)"
dir="${JUDGE0_DIR:-$HOME/judge0-v1.13.1}"
project="${JUDGE0_PROJECT:-judge0-v1131}"

if [ "${1:-}" = "--revert" ]; then
  remove_runners
  docker-compose -p "$project" -f "$dir/docker-compose.yml" up -d --no-deps server workers
  exit
fi

export JUDGE0_WORKER_IMAGE="${1:-judge0-pytest:latest}"
docker image inspect "$JUDGE0_WORKER_IMAGE" > /dev/null
remove_runners
docker-compose -p "$project" -f "$dir/docker-compose.yml" -f "$here/workers-image.override.yml" \
  up -d --no-deps server workers
