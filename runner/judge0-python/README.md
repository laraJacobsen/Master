# Judge0 image for test-graded Python tasks

`judge0/judge0:1.13.1` plus a second Python, `/usr/local/python-3.11`, with pandas,
numpy, pytest and pytest-timeout. Every version is pinned in `versions.env` (the
only place to change them). Stock languages, including the Python 3.8 that
stdout-graded tasks use, are unchanged.

```bash
runner/judge0-python/build.sh          # ~3 min: compiles CPython, installs the pins
runner/judge0-python/use_image.sh      # local Judge0 server + workers -> this image
python3 runner/judge0-python/measure.py   # per-submission CPU / wall / memory
runner/judge0-python/use_image.sh --revert   # back to the stock image
```

Both the Judge0 **server** and **workers** need the image: the backend submits with
`wait=true`, which Judge0 1.13 runs inside the server container
(`IsolateJob.perform_now`); only `wait=false` submissions reach a worker.

## Measured cost (2026-11-24, this laptop, sequential, 10 runs after a warm-up)

| Run | CPU s med/max | Wall s med/max | Peak MB |
|---|---|---|---|
| Stock Python 3.8, `print` (a stdout test run today) | 0.02 / 0.02 | 0.03 / 0.04 | 3.2 |
| Python 3.11, start and exit | 0.02 / 0.02 | 0.02 / 0.03 | 3.5 |
| Python 3.11, `import pandas, numpy` | 0.49 / 0.59 | 0.49 / 0.59 | 40 |
| pytest + JUnit XML: pandas solution, CSV, 5 tests | 0.84 / 0.93 | 0.85 / 0.94 | 50 |

Same at 128 MB and 256 MB memory limits. The first run after swapping images
(cold file cache) took 1.6 s CPU for the import alone.
