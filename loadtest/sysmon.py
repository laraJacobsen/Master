"""Machine-side sampling for a load-test run: memory, swap activity, CPU, load,
backend RSS and the client's own event-loop lag, once a second.

These decide whether a run measured the app or the laptop. A run is flagged
machine-bound (and not used as an app result) when memory or swap crossed the
thresholds below; client-bound when the load generator itself fell behind.
"""

import asyncio
import os
import time

PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024

# Thresholds -- recorded in conditions.json next to every run.
THRESHOLDS = {
    # Pre-run: less free memory than this and the run starts already squeezed.
    "pre_run_min_mem_available_mb": 2048,
    # During the run: below this, the kernel is reclaiming hard.
    "min_mem_available_mb": 300,
    # During the run: swap-in averaged over any 5 s window above this means
    # processes were waiting on disk for their own memory.
    "max_swap_in_kb_per_s_5s": 1024,
    # Abort the run outright below this.
    "abort_mem_available_mb": 200,
    # Client event loop late by more than this = load generator fell behind.
    "max_client_loop_lag_s": 0.2,
}


def read_meminfo() -> dict:
    out = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, rest = line.split(":", 1)
            out[key] = int(rest.split()[0])  # kB
    return out


def _vmstat() -> dict:
    out = {}
    with open("/proc/vmstat") as f:
        for line in f:
            k, v = line.split()
            if k in ("pswpin", "pswpout"):
                out[k] = int(v)
    return out


def _cpu_times():
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    vals = list(map(int, parts))
    idle = vals[3] + vals[4]  # idle + iowait
    return sum(vals), idle, vals[4]


def _rss_kb(pid):
    if not pid:
        return None
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except FileNotFoundError:
        return None
    return None


def machine_snapshot() -> dict:
    mem = read_meminfo()
    return {
        "mem_total_mb": mem["MemTotal"] // 1024,
        "mem_available_mb": mem["MemAvailable"] // 1024,
        "swap_total_mb": mem["SwapTotal"] // 1024,
        "swap_used_mb": (mem["SwapTotal"] - mem["SwapFree"]) // 1024,
        "loadavg_1m": float(open("/proc/loadavg").read().split()[0]),
    }


class SysMon:
    def __init__(self, t0: float, backend_pid=None, abort_event: asyncio.Event = None):
        self.t0 = t0
        self.backend_pid = backend_pid
        self.abort_event = abort_event
        self.abort_reason = None
        self.samples = []
        self._stop = asyncio.Event()

    def stop(self):
        self._stop.set()

    async def run(self, interval=1.0):
        prev_vm, prev_cpu = _vmstat(), _cpu_times()
        expected = time.perf_counter() + interval
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(0, expected - time.perf_counter()))
                break
            except asyncio.TimeoutError:
                pass
            now = time.perf_counter()
            lag = now - expected
            expected += interval
            vm, cpu = _vmstat(), _cpu_times()
            dt_total = cpu[0] - prev_cpu[0] or 1
            mem = read_meminfo()
            sample = {
                "t": round(now - self.t0, 3),
                "mem_available_mb": mem["MemAvailable"] // 1024,
                "swap_used_mb": (mem["SwapTotal"] - mem["SwapFree"]) // 1024,
                "swap_in_kb_s": (vm["pswpin"] - prev_vm["pswpin"]) * PAGE_KB / interval,
                "swap_out_kb_s": (vm["pswpout"] - prev_vm["pswpout"]) * PAGE_KB / interval,
                "cpu_util_pct": round(100 * (1 - (cpu[1] - prev_cpu[1]) / dt_total), 1),
                "iowait_pct": round(100 * (cpu[2] - prev_cpu[2]) / dt_total, 1),
                "loadavg_1m": float(open("/proc/loadavg").read().split()[0]),
                "backend_rss_mb": (_rss_kb(self.backend_pid) or 0) // 1024,
                "client_loop_lag_s": round(max(0.0, lag), 4),
            }
            self.samples.append(sample)
            prev_vm, prev_cpu = vm, cpu
            if (
                self.abort_event is not None
                and sample["mem_available_mb"] < THRESHOLDS["abort_mem_available_mb"]
                and not self.abort_event.is_set()
            ):
                self.abort_reason = (
                    f"machine-bound: MemAvailable {sample['mem_available_mb']} MB "
                    f"< {THRESHOLDS['abort_mem_available_mb']} MB at t={sample['t']}s"
                )
                self.abort_event.set()


def evaluate(samples: list, pre_run: dict) -> dict:
    """Machine-bound / client-bound verdict for a finished run."""
    reasons = []
    if pre_run["mem_available_mb"] < THRESHOLDS["pre_run_min_mem_available_mb"]:
        reasons.append(
            f"pre-run MemAvailable {pre_run['mem_available_mb']} MB "
            f"< {THRESHOLDS['pre_run_min_mem_available_mb']} MB"
        )
    if samples:
        min_avail = min(s["mem_available_mb"] for s in samples)
        if min_avail < THRESHOLDS["min_mem_available_mb"]:
            reasons.append(f"MemAvailable fell to {min_avail} MB")
        worst = 0.0
        for i in range(len(samples)):
            window = samples[i : i + 5]
            worst = max(worst, sum(s["swap_in_kb_s"] for s in window) / len(window))
        if worst > THRESHOLDS["max_swap_in_kb_per_s_5s"]:
            reasons.append(f"swap-in peaked at {worst:.0f} kB/s (5 s avg)")
    lag = max((s["client_loop_lag_s"] for s in samples), default=0.0)
    client_bound = lag > THRESHOLDS["max_client_loop_lag_s"]
    return {
        "machine_bound": bool(reasons),
        "machine_bound_reasons": reasons,
        "client_bound": client_bound,
        "max_client_loop_lag_s": lag,
        "min_mem_available_mb": min((s["mem_available_mb"] for s in samples), default=None),
        "max_swap_in_kb_s": max((s["swap_in_kb_s"] for s in samples), default=None),
        "max_swap_out_kb_s": max((s["swap_out_kb_s"] for s in samples), default=None),
        "mean_cpu_util_pct": round(sum(s["cpu_util_pct"] for s in samples) / len(samples), 1) if samples else None,
        "max_backend_rss_mb": max((s["backend_rss_mb"] for s in samples), default=None),
    }
