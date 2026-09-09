"""Run one provider over a list of phrases, surviving its failures.

The same resilience the Coursera acquisition needed, written once for every
provider instead of once per adapter. That acquisition is the reason this
exists: a network drop killed its WebDriver, the runner had no way to rebuild
one, and it spent an hour timing out -- 0 of 265 queries completed and nothing
recoverable.

What is provider-agnostic here: bounded retries, exponential backoff, a
consecutive-network-failure circuit breaker, a checkpoint so a rerun skips what
already succeeded, and per-query persistence so a run that dies keeps its work.

What is not: how to search, and how to recover a broken session. A provider
that needs a browser implements ``reset()`` to drop it; an API-backed provider
inherits a no-op and never pays for machinery it does not need.

Nothing here decides skills. The runner stores evidence; mapping is a separate
pass over the stored catalogue, and can be re-run offline whenever the
canonical extractor changes.
"""

import logging
import random
import time

from resources.acquisition_state import AcquisitionCheckpoint
from .normalize import InvalidCourse, merge_course, normalize_course

logger = logging.getLogger(__name__)

MAX_QUERY_ATTEMPTS = 3
NETWORK_FAILURE_CIRCUIT_BREAKER = 8
BACKOFF_BASE = 4

#: Politeness between queries. An API-backed provider needs less than a
#: browser-driven one, so adapters may lower it; nobody should raise it to
#: zero.
DEFAULT_DELAY = (1.0, 3.0)


class AcquisitionInterrupted(RuntimeError):
    """The circuit breaker tripped. Progress is on disk; rerun to resume."""


NETWORK_MARKERS = (
    "err_internet_disconnected", "err_name_not_resolved", "err_connection",
    "err_network", "err_proxy", "err_address_unreachable",
    "temporary failure in name resolution", "getaddrinfo failed",
    "failed to resolve", "nameresolutionerror", "max retries exceeded",
    "connectionerror", "connection refused", "connection aborted",
    "connection reset", "read timed out", "timed out",
)

#: Failures that mean the provider's session is unusable rather than one query
#: having gone wrong. Recovering means dropping the session, not retrying into
#: it.
SESSION_MARKERS = (
    "invalid session id", "session deleted", "no such session",
    "chrome not reachable", "disconnected", "target crashed",
    "browser has closed", "webdriverexception", "max retries exceeded",
    "read timed out",
)


def _matches(reason, markers):
    text = str(reason).lower()
    return any(marker in text for marker in markers)


def acquire(provider, phrases, checkpoint=None, on_progress=None,
            on_courses=None, max_attempts=MAX_QUERY_ATTEMPTS,
            delay=DEFAULT_DELAY):
    """Search ``provider`` for each ``(skill_name, phrase)`` pair.

    Returns normalised course dicts keyed by canonical URL. Raises
    AcquisitionInterrupted when too many network failures arrive in a row --
    with the checkpoint saved, so rerunning resumes rather than restarts.
    """
    plan = list(phrases)
    by_url = {}
    rejected = 0
    consecutive_network_failures = 0

    try:
        for index, (skill_name, phrase) in enumerate(plan, start=1):
            if checkpoint is not None and checkpoint.is_done(phrase):
                if on_progress:
                    on_progress(index, len(plan), skill_name, phrase,
                                "skipped", 0, len(by_url))
                continue

            found, failure = 0, None
            for attempt in range(1, max_attempts + 1):
                try:
                    found, rejected_here = _run_one(
                        provider, skill_name, phrase, by_url)
                    rejected += rejected_here
                    failure = None
                except Exception as exc:      # noqa: BLE001 -- classified here
                    failure = f"{type(exc).__name__}: {exc}"
                    if _matches(failure, SESSION_MARKERS):
                        # Drop the session rather than retry into a dead one.
                        provider.reset()

                if failure is None:
                    break

                if _matches(failure, NETWORK_MARKERS):
                    consecutive_network_failures += 1
                    if (consecutive_network_failures
                            >= NETWORK_FAILURE_CIRCUIT_BREAKER):
                        if checkpoint is not None:
                            checkpoint.record(phrase, checkpoint.FAILED,
                                              attempt, failure)
                        raise AcquisitionInterrupted(
                            f"{consecutive_network_failures} consecutive "
                            f"network failures against {provider.name}; "
                            f"stopped with progress saved. Rerun to resume.")
                else:
                    consecutive_network_failures = 0

                if attempt < max_attempts:
                    time.sleep(BACKOFF_BASE * (2 ** (attempt - 1))
                               + random.uniform(0, 3))

            if failure is None:
                consecutive_network_failures = 0
                # Persist before the checkpoint calls it done, so SUCCESS never
                # describes work that died with the process.
                if on_courses:
                    on_courses([row for row in by_url.values()
                                if phrase in row["discovered_via"]])
                if checkpoint is not None:
                    checkpoint.record(phrase, checkpoint.SUCCESS, attempt, "")
            elif checkpoint is not None:
                checkpoint.record(phrase, checkpoint.FAILED, max_attempts,
                                  failure)

            if on_progress:
                on_progress(index, len(plan), skill_name, phrase,
                            "ok" if failure is None else "failed",
                            found, len(by_url))
            time.sleep(random.uniform(*delay))

    finally:
        provider.reset()

    if rejected:
        # A number rather than silence: an adapter producing unusable rows is a
        # bug in that adapter, and dropping them quietly hides it.
        logger.warning("%s: %d row(s) rejected as unusable.",
                       provider.name, rejected)
    logger.info("%s: %d distinct course(s) from %d quer(ies).",
                provider.name, len(by_url), len(plan))
    return list(by_url.values())


def _run_one(provider, skill_name, phrase, by_url):
    """One query, normalised and merged. Returns (new_count, rejected_count).

    A provider may want more than one string tried for a skill -- see
    CourseProvider.search_terms -- so every term it names is searched and the
    results merged. Provenance still records the phrase the plan asked for, not
    the term that happened to match, because the plan is what a reviewer reads.
    """
    new_count = rejected = 0
    rows = []
    for term in provider.search_terms(skill_name, phrase):
        rows.extend(provider.search(term))

    for raw in rows:
        try:
            course = normalize_course(raw)
        except InvalidCourse as exc:
            logger.debug("%s: %s", provider.name, exc)
            rejected += 1
            continue

        # The runner stamps the phrase, not the adapter. Retrieval provenance
        # is something the runner knows for certain and an adapter can forget;
        # leaving it to adapters made it a per-provider obligation that was
        # silently unmet, and a course with no recorded query is a course
        # nobody can audit the mapping of.
        if phrase not in course["discovered_via"]:
            course["discovered_via"] = sorted(
                set(course["discovered_via"]) | {phrase})

        key = course["url"]
        if key in by_url:
            # One course found by two phrases is one row carrying both.
            by_url[key] = merge_course(by_url[key], course)
        else:
            by_url[key] = course
            new_count += 1
    return new_count, rejected


def checkpoint_for(provider_name):
    """A checkpoint per provider, so one provider's failures never skip another's.

    Named from the provider, lowercased with spaces collapsed, because it
    becomes a filename.
    """
    slug = provider_name.strip().casefold().replace(" ", "_")
    return AcquisitionCheckpoint(f"provider_{slug}")
