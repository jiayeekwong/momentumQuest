"""Acquisition resilience, tested against a provider that fails on demand.

The Coursera acquisition proved this machinery was needed, and proved it the
expensive way: an outage killed the WebDriver, the runner had no way to rebuild
one, and an hour of queries timed out against a dead session -- 0 of 265
completed. Waiting for a real outage is not a test, so the failures are scripted
here instead.

Hermetic: no network, no database, no sleeping. Every case runs with the
backoff delay set to zero.
"""

from django.test import SimpleTestCase

from .providers.base import CourseProvider
from .providers.runner import AcquisitionInterrupted, acquire


class FlakyProvider(CourseProvider):
    """Returns, raises, or recovers -- whatever the script says."""

    name = "Flaky"

    def __init__(self, script=None, **kwargs):
        super().__init__(**kwargs)
        #: phrase -> outcomes consumed one per attempt. An outcome is either an
        #: exception to raise or a list of rows to return.
        self.script = script or {}
        self.calls = []
        self.resets = 0

    def search(self, phrase):
        self.calls.append(phrase)
        outcomes = self.script.get(phrase)
        outcome = outcomes.pop(0) if outcomes else []
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def reset(self):
        self.resets += 1


def course(slug, title="A Real Course Title"):
    return {"url": f"https://flaky.example.com/{slug}", "title": title,
            "description": "Covers Python and SQL.", "provider": "Flaky",
            "type": "Course", "is_free": True}


class MemoryCheckpoint:
    """The checkpoint contract, without touching disk."""

    NOT_STARTED, SUCCESS, FAILED = "NOT_STARTED", "SUCCESS", "FAILED"

    def __init__(self):
        self.rows = {}

    def is_done(self, phrase):
        return self.rows.get(phrase, {}).get("status") == self.SUCCESS

    def record(self, phrase, status, attempts, reason=""):
        self.rows[phrase] = {"status": status, "attempts": attempts,
                             "reason": reason}


class AcquisitionRunnerTests(SimpleTestCase):

    def test_a_transient_failure_is_retried_and_succeeds(self):
        provider = FlakyProvider({"python": [
            RuntimeError("Read timed out"), [course("a")],
        ]})
        checkpoint = MemoryCheckpoint()

        courses = acquire(provider, [("Python", "python")],
                          checkpoint=checkpoint, delay=(0, 0))

        self.assertEqual(len(courses), 1)
        self.assertEqual(checkpoint.rows["python"]["status"], "SUCCESS")
        self.assertEqual(checkpoint.rows["python"]["attempts"], 2)

    def test_a_dead_session_is_dropped_before_retrying_into_it(self):
        """The failure that cost an entire acquisition.

        Retrying against a session that has died only times out again. The
        recovery is to drop it so the next attempt builds a new one.
        """
        provider = FlakyProvider({"python": [
            RuntimeError("invalid session id"), [course("a")],
        ]})

        acquire(provider, [("Python", "python")], delay=(0, 0))

        self.assertGreaterEqual(provider.resets, 1)

    def test_exhausted_retries_record_the_reason_and_move_on(self):
        provider = FlakyProvider({"python": [ValueError("bad markup")] * 5})
        checkpoint = MemoryCheckpoint()

        acquire(provider, [("Python", "python")], checkpoint=checkpoint,
                delay=(0, 0), max_attempts=2)

        row = checkpoint.rows["python"]
        self.assertEqual(row["status"], "FAILED")
        self.assertIn("bad markup", row["reason"])

    def test_consecutive_network_failures_trip_the_breaker(self):
        """Stopping beats spending 265 timeouts to learn the network is down."""
        phrases = [(f"S{i}", f"q{i}") for i in range(40)]
        provider = FlakyProvider(
            {phrase: [RuntimeError("net::ERR_INTERNET_DISCONNECTED")] * 5
             for _, phrase in phrases})
        checkpoint = MemoryCheckpoint()

        with self.assertRaises(AcquisitionInterrupted):
            acquire(provider, phrases, checkpoint=checkpoint, delay=(0, 0),
                    max_attempts=1)

        self.assertLess(len(checkpoint.rows), len(phrases))
        self.assertTrue(checkpoint.rows)

    def test_a_non_network_failure_does_not_trip_the_breaker(self):
        """One malformed page is not an outage.

        Counting it toward the breaker would abandon a whole run over a single
        bad result.
        """
        phrases = [(f"S{i}", f"q{i}") for i in range(20)]
        provider = FlakyProvider({phrase: [ValueError("bad markup")]
                                  for _, phrase in phrases})

        acquire(provider, phrases, delay=(0, 0), max_attempts=1)

        self.assertEqual(len(provider.calls), len(phrases))

    def test_a_rerun_skips_successes_and_retries_failures(self):
        """Exactly what made the killed Coursera run recoverable."""
        checkpoint = MemoryCheckpoint()
        checkpoint.record("done", checkpoint.SUCCESS, 1)
        checkpoint.record("broken", checkpoint.FAILED, 3, "page did not load")
        provider = FlakyProvider({"broken": [[course("b")]]})

        acquire(provider, [("A", "done"), ("B", "broken")],
                checkpoint=checkpoint, delay=(0, 0))

        self.assertEqual(provider.calls, ["broken"])
        self.assertEqual(checkpoint.rows["broken"]["status"], "SUCCESS")

    def test_courses_are_persisted_before_a_query_is_called_done(self):
        """Otherwise SUCCESS could describe work that died with the process."""
        provider = FlakyProvider({"python": [[course("a")]]})
        saved = []

        acquire(provider, [("Python", "python")], delay=(0, 0),
                on_courses=saved.extend)

        self.assertEqual([row["url"] for row in saved],
                         ["https://flaky.example.com/a"])

    def test_unusable_rows_are_dropped_without_killing_the_query(self):
        provider = FlakyProvider({"python": [[
            {"url": "", "title": "No URL", "provider": "Flaky"},
            course("good"),
        ]]})

        courses = acquire(provider, [("Python", "python")], delay=(0, 0))

        self.assertEqual([row["url"] for row in courses],
                         ["https://flaky.example.com/good"])

    def test_one_course_found_twice_is_one_row_carrying_both_phrases(self):
        provider = FlakyProvider({
            "python": [[course("shared")]],
            "sql": [[course("shared")]],
        })

        courses = acquire(provider, [("Python", "python"), ("SQL", "sql")],
                          delay=(0, 0))

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["discovered_via"], ["python", "sql"])

    def test_the_session_is_released_even_when_the_run_raises(self):
        provider = FlakyProvider(
            {f"q{i}": [RuntimeError("getaddrinfo failed")] * 3
             for i in range(40)})

        with self.assertRaises(AcquisitionInterrupted):
            acquire(provider, [(f"S{i}", f"q{i}") for i in range(40)],
                    delay=(0, 0), max_attempts=1)

        self.assertGreaterEqual(provider.resets, 1)


class CheckpointPruneTests(SimpleTestCase):
    """A corrected search phrase must not leave a permanent false failure.

    The checkpoint is keyed by phrase, which is what makes resumption correct
    when the plan shrinks. The cost is that changing a skill's phrase orphans
    the old key -- and an orphaned FAILED entry reports a failure no rerun can
    ever clear, because nothing asks that question any more.
    """

    def _checkpoint(self, tmp):
        from .acquisition_state import AcquisitionCheckpoint
        return AcquisitionCheckpoint("test_prune", state_dir=tmp)

    def test_orphaned_entries_are_dropped_and_reported(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cp = self._checkpoint(tmp)
            cp.record("YAML", cp.SUCCESS, 1)
            cp.record("yaml ain't markup language", cp.FAILED, 3, "no results")

            dropped = cp.prune(["YAML"])

            self.assertEqual(dropped, ["yaml ain't markup language"])
            self.assertEqual(cp.summary()[cp.FAILED], 0)
            self.assertTrue(cp.is_done("YAML"))

    def test_pruning_survives_a_reload(self):
        """The drop must be written, not just held in memory."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cp = self._checkpoint(tmp)
            cp.record("live", cp.SUCCESS, 1)
            cp.record("stale", cp.FAILED, 3, "gone")
            cp.prune(["live"])

            reloaded = self._checkpoint(tmp)

            self.assertEqual(set(reloaded.queries), {"live"})

    def test_a_still_live_failure_is_kept(self):
        """Pruning removes what nothing asks for, never what merely failed."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cp = self._checkpoint(tmp)
            cp.record("still asked", cp.FAILED, 3, "timed out")

            self.assertEqual(cp.prune(["still asked"]), [])
            self.assertEqual(cp.summary()[cp.FAILED], 1)
