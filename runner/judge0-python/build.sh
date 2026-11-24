#!/usr/bin/env bash
# Builds the Judge0 worker image for test-graded Python tasks from versions.env.
# Tag: judge0-pytest:<pandas version>-py<python version>, plus judge0-pytest:latest.
# Takes a few minutes the first time (compiles CPython).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
set -a; . "$here/versions.env"; set +a

tag="judge0-pytest:${PANDAS_VERSION}-py${PYTHON_VERSION}"
docker build \
  --build-arg PYTHON_VERSION --build-arg PYTHON_SHA256 --build-arg PYTHON_PREFIX \
  --build-arg PANDAS_VERSION --build-arg NUMPY_VERSION \
  --build-arg PYTEST_VERSION --build-arg PYTEST_TIMEOUT_VERSION \
  -t "$tag" -t judge0-pytest:latest "$here"
echo "built $tag"
