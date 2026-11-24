# Judge0 worker image with a second Python (3.11) for test-graded tasks:
# pandas, numpy, pytest and pytest-timeout, pinned in versions.env.
#
# Only the Judge0 *workers* need this image (they run the code); the server can
# stay on the stock image. isolate exposes /usr read-only inside the sandbox, so
# /usr/local/python-3.11 is visible to a submission while nothing can be
# installed or changed at run time. The stock Python 3.8.1 and every other
# language are untouched, so stdout-graded tasks run exactly as before.
#
# Build with build.sh (it passes versions.env as build args), not directly.

ARG JUDGE0_IMAGE=judge0/judge0:1.13.1
FROM ${JUDGE0_IMAGE}

ARG PYTHON_VERSION
ARG PYTHON_SHA256
ARG PYTHON_PREFIX
ARG PANDAS_VERSION
ARG NUMPY_VERSION
ARG PYTEST_VERSION
ARG PYTEST_TIMEOUT_VERSION

# The stock image runs as the unprivileged user judge0; installing into /usr/local
# needs root, and the last line switches back.
USER root

# The stock image already carries the build dependencies (libssl, libffi, zlib,
# bz2, lzma, sqlite headers), so no apt-get -- buster's mirrors are archived.
RUN set -eux; \
    test -n "$PYTHON_VERSION" && test -n "$PYTHON_SHA256" && test -n "$PYTHON_PREFIX"; \
    cd /tmp; \
    curl -fsSLO "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"; \
    echo "${PYTHON_SHA256}  Python-${PYTHON_VERSION}.tgz" | sha256sum -c -; \
    tar xzf "Python-${PYTHON_VERSION}.tgz"; \
    cd "Python-${PYTHON_VERSION}"; \
    ./configure --prefix="$PYTHON_PREFIX" --with-ensurepip=install > /dev/null; \
    make -j"$(nproc)" > /dev/null; \
    make install > /dev/null; \
    cd /; rm -rf /tmp/Python-*; \
    "$PYTHON_PREFIX/bin/python3.11" --version

RUN set -eux; \
    "$PYTHON_PREFIX/bin/python3.11" -m pip install --no-cache-dir --disable-pip-version-check \
        "pandas==${PANDAS_VERSION}" \
        "numpy==${NUMPY_VERSION}" \
        "pytest==${PYTEST_VERSION}" \
        "pytest-timeout==${PYTEST_TIMEOUT_VERSION}"; \
    # Precompile everything: the sandbox's /usr is read-only, so a missing .pyc
    # would be recompiled (and thrown away) on every single submission.
    "$PYTHON_PREFIX/bin/python3.11" -m compileall -q "$PYTHON_PREFIX/lib/python3.11" || true; \
    "$PYTHON_PREFIX/bin/python3.11" -c "import pandas, numpy, pytest, pytest_timeout; print(pandas.__version__, numpy.__version__, pytest.__version__)"; \
    "$PYTHON_PREFIX/bin/python3.11" -m pip freeze > "$PYTHON_PREFIX/installed-packages.txt"

USER judge0
