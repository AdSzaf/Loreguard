"""
Tests call_with_rate_limit_retry: retries a rate-limited (429) call
after waiting, gives up after max_attempts, and never retries
unrelated errors. Patches time.sleep so this runs instantly.

Run with:
    python test_retry_utils.py
"""

from unittest.mock import patch

from app.services.retry_utils import (
    call_with_rate_limit_retry,
    extract_retry_delay,
    is_rate_limit_error,
)


passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


print("=" * 60)
print("CASE 1: rate-limit detection")
print("=" * 60)

check("429 detected", is_rate_limit_error(RuntimeError("429 RESOURCE_EXHAUSTED")))
check("RESOURCE_EXHAUSTED detected", is_rate_limit_error(RuntimeError("quota RESOURCE_EXHAUSTED")))
check("unrelated error not flagged", not is_rate_limit_error(RuntimeError("invalid JSON")))
check("auth error not flagged", not is_rate_limit_error(RuntimeError("401 Unauthorized")))

print()
print("=" * 60)
print("CASE 2: retry delay extraction from real Gemini error text")
print("=" * 60)

delay = extract_retry_delay(RuntimeError("...'retryDelay': '40s'..."))
check("extracts 40s + buffer from Gemini-style message", 40 < delay <= 42)

delay2 = extract_retry_delay(RuntimeError("Please retry in 10.36s"))
check("extracts ~10s from 'Please retry in' message", 10 < delay2 <= 13)

delay3 = extract_retry_delay(RuntimeError("something with no delay info"))
check("falls back to default when nothing found", delay3 == 60.0)

print()
print("=" * 60)
print("CASE 3: call_with_rate_limit_retry actually retries and succeeds")
print("=" * 60)

call_count = {"n": 0}


def flaky_call():
    call_count["n"] += 1
    if call_count["n"] < 3:
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
    return "success"


with patch("app.services.retry_utils.time.sleep") as mock_sleep:
    result = call_with_rate_limit_retry(flaky_call, max_attempts=3)

check("eventually succeeds after 2 rate-limit failures", result == "success")
check("called exactly 3 times", call_count["n"] == 3)
check("slept between retries (2 times)", mock_sleep.call_count == 2)

print()
print("=" * 60)
print("CASE 4: gives up after max_attempts on persistent rate limits")
print("=" * 60)

always_fails_count = {"n": 0}


def always_fails():
    always_fails_count["n"] += 1
    raise RuntimeError("429 RESOURCE_EXHAUSTED")


with patch("app.services.retry_utils.time.sleep"):
    try:
        call_with_rate_limit_retry(always_fails, max_attempts=3)
        raised = False
    except RuntimeError:
        raised = True

check("raises after exhausting attempts", raised)
check("attempted exactly max_attempts (3) times", always_fails_count["n"] == 3)

print()
print("=" * 60)
print("CASE 5: non-rate-limit errors are NEVER retried")
print("=" * 60)

other_error_count = {"n": 0}


def raises_other_error():
    other_error_count["n"] += 1
    raise ValueError("malformed response: unexpected token in JSON")


with patch("app.services.retry_utils.time.sleep") as mock_sleep_2:
    try:
        call_with_rate_limit_retry(raises_other_error, max_attempts=3)
        raised = False
    except ValueError:
        raised = True

check("non-rate-limit error propagates immediately", raised)
check("called only once, no retry attempted", other_error_count["n"] == 1)
check("never slept", mock_sleep_2.call_count == 0)

print()
print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 60)

if failed:
    raise SystemExit(1)
