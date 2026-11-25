"""
Rate limits for the whole API (see main.py's `guard` middleware, which applies them).

Two strategies:
  - TokenBucket for request rates: a key may burst up to `capacity` requests, then
    gets `per_second` more. Fits polling clients (steady, with short bursts on load).
  - SlidingWindow for counting failures: at most `limit` recorded failures in the last
    `window_s` seconds. Fits password and join-code guessing, where only wrong answers
    should count, and a wait of exactly the window is easy to explain.

What a key is matters more than the numbers. A whole lecture hall can reach the server
from ONE address (campus NAT, or a reverse proxy run without --proxy-headers), so:
  - students are limited per join token (each browser's own budget),
  - the lecturer per session (one shared password, so one identity),
  - only traffic with neither falls back to the client address, with limits sized for a
    full class sharing it -- they stop one machine flooding the server, not more.

Everything is in memory: the server runs as a single process (README.md), and a
restart forgetting the counts is harmless. RATE_LIMITS=off turns all of it off (e.g.
for load tests far beyond a real class).
"""

import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass


def enabled() -> bool:
    """Read on every request (not at import), so tests can switch it."""
    return os.environ.get("RATE_LIMITS", "on").strip().lower() not in ("off", "0", "false", "no")


class RateLimited(Exception):
    """Raised where a limit is checked outside a request (the LLM budget)."""

    def __init__(self, retry_after: float):
        super().__init__(f"rate limited, retry in {retry_after:.0f}s")
        self.retry_after = retry_after


class _Keyed:
    """Per-key state in an OrderedDict, oldest-touched first, capped at max_keys so a
    flood of distinct keys (spoofed tokens, many addresses) can't grow memory forever.
    Dropping a key forgets its history, which only ever errs towards allowing."""

    def __init__(self, max_keys: int, clock):
        self._state = OrderedDict()
        self._lock = threading.Lock()
        self._max_keys = max_keys
        self._clock = clock

    def _touch(self, key, default):
        state = self._state.get(key)
        if state is None:
            state = self._state[key] = default()
            while len(self._state) > self._max_keys:
                self._state.popitem(last=False)
        else:
            self._state.move_to_end(key)
        return state


class TokenBucket(_Keyed):
    def __init__(self, capacity: float, per_second: float, max_keys: int = 20_000, clock=time.monotonic):
        super().__init__(max_keys, clock)
        self.capacity = capacity
        self.per_second = per_second

    def take(self, key, cost: float = 1.0) -> float:
        """Spends `cost` tokens. Returns 0 if allowed, else the seconds until it would be."""
        with self._lock:
            now = self._clock()
            state = self._touch(key, lambda: [self.capacity, now])
            tokens = min(self.capacity, state[0] + (now - state[1]) * self.per_second)
            state[1] = now
            if tokens >= cost:
                state[0] = tokens - cost
                return 0.0
            state[0] = tokens
            return (cost - tokens) / self.per_second


class SlidingWindow(_Keyed):
    def __init__(self, limit: int, window_s: float, max_keys: int = 20_000, clock=time.monotonic):
        super().__init__(max_keys, clock)
        self.limit = limit
        self.window_s = window_s

    def _events(self, key) -> deque:
        events = self._touch(key, deque)
        cutoff = self._clock() - self.window_s
        while events and events[0] <= cutoff:
            events.popleft()
        return events

    def retry_after(self, key) -> float:
        """0 if `key` is under the limit, else the seconds until its oldest failure expires."""
        with self._lock:
            events = self._events(key)
            if len(events) < self.limit:
                return 0.0
            return events[0] + self.window_s - self._clock()

    def record(self, key) -> None:
        with self._lock:
            self._events(key).append(self._clock())

    def reset(self, key) -> None:
        with self._lock:
            self._state.pop(key, None)


@dataclass
class Limits:
    """Every limit in one place. Normal use, for scale: the student page polls every 2 s
    and sends a heartbeat every 10 s (~0.6 requests/s); the live dashboard polls six
    endpoints every 3 s (~2/s) and the projector one every 2 s."""

    # Lecturer password guesses (login form AND the X-Lecturer-Token header). The
    # global window stops guessing spread over many addresses; it only blocks new
    # logins, never an existing session.
    login_failures_per_ip: SlidingWindow
    login_failures_global: SlidingWindow
    # Join-code guesses (6 digits). Sized for a class with typos behind one address:
    # 50 per 10 minutes is still ~7,000 guesses a day out of 1,000,000 codes.
    join_failures_per_ip: SlidingWindow
    # Successful joins, i.e. new student identities ("account creation"). A whole
    # class can join at once from one address; after that, one every 5 s.
    joins_per_ip: TokenBucket
    # Any API call with a valid student token, per token.
    student_requests: TokenBucket
    # Submit and Run (each one is a Judge0 job), per token: 20 a minute sustained.
    student_runs: TokenBucket
    # Any API call from the logged-in lecturer (one identity, several tabs).
    lecturer_requests: TokenBucket
    # Lecturer calls that run Judge0 (validate, projector Run).
    lecturer_runs: TokenBucket
    # Drafting hints with the LLM, a few clicks a minute.
    ai_drafts: TokenBucket
    # Every LLM call the server makes (labels, headlines, hint drafts), whoever
    # triggered it -- the cap on model spend. A refused label call just shows the
    # generic line until its retry (aggregation._LABEL_RETRY_SECONDS).
    llm_calls: TokenBucket
    # Calls with no valid student token and no lecturer session, per address: the
    # join page's polling for a class behind one NAT, so only a flood trips it.
    anonymous_per_ip: TokenBucket

    @classmethod
    def default(cls, clock=time.monotonic) -> "Limits":
        return cls(
            login_failures_per_ip=SlidingWindow(10, 15 * 60, clock=clock),
            login_failures_global=SlidingWindow(100, 15 * 60, clock=clock),
            join_failures_per_ip=SlidingWindow(50, 10 * 60, clock=clock),
            joins_per_ip=TokenBucket(400, 1 / 5, clock=clock),
            student_requests=TokenBucket(60, 3, clock=clock),
            student_runs=TokenBucket(10, 1 / 3, clock=clock),
            lecturer_requests=TokenBucket(300, 30, clock=clock),
            lecturer_runs=TokenBucket(30, 1, clock=clock),
            ai_drafts=TokenBucket(5, 1 / 20, clock=clock),
            llm_calls=TokenBucket(60, 1, clock=clock),
            anonymous_per_ip=TokenBucket(600, 150, clock=clock),
        )


LIMITS = Limits.default()


def reset() -> None:
    """Fresh state (tests)."""
    global LIMITS
    LIMITS = Limits.default()


def take_llm_call() -> None:
    """Called before every LLM request; raises RateLimited over the budget. Callers
    already treat any exception as a failed call (fallback text, or a 502 for drafts)."""
    if not enabled():
        return
    wait = LIMITS.llm_calls.take("global")
    if wait:
        raise RateLimited(wait)
