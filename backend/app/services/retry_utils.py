import logging
import re
import time

logger = logging.getLogger("loreguard.retry")

RATE_LIMIT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "rate limit", "rate_limit")


def is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc)
    return any(marker.lower() in message.lower() for marker in RATE_LIMIT_MARKERS)


def extract_retry_delay(
    exc: Exception,
    default: float = 60.0,
    max_delay: float = 90.0,
) -> float:
    """
    Reads a suggested retry delay out of the error message when the
    provider gives one (Gemini includes things like
    "retryDelay': '40s'" or "Please retry in 10.36s"). Falls back to
    `default` otherwise. A couple of seconds are added as a buffer
    since these are estimates, not guarantees.
    """

    message = str(exc)

    match = re.search(
        r"retry[\s_]?[Dd]elay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)", message
    )

    if not match:
        match = re.search(r"retry in (\d+(?:\.\d+)?)", message, re.IGNORECASE)

    if match:
        return min(float(match.group(1)) + 2, max_delay)

    return default


def call_with_rate_limit_retry(func, *args, max_attempts: int = 3, **kwargs):
    """
    Calls func(*args, **kwargs), waiting and retrying if it raises a
    rate-limit (429) error -- "the first bulk run always hits the
    limit, everything after is incremental and much smaller" is
    exactly the case this is for. Any OTHER exception (bad JSON,
    auth error, network failure) is never retried -- it propagates
    immediately, same as before, so callers' existing per-document
    error handling (bulk endpoints' `failed: [...]`) still works.
    """

    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not is_rate_limit_error(exc) or attempt == max_attempts:
                raise

            delay = extract_retry_delay(exc)

            logger.warning(
                "Rate limit hit (attempt %d/%d), waiting %.0fs before "
                "retrying: %s",
                attempt, max_attempts, delay, exc,
            )

            time.sleep(delay)
            last_exc = exc

    raise last_exc  # pragma: no cover -- unreachable given the loop above
