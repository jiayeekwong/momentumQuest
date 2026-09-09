"""Where an acquisition run got to. Runtime state, never catalogue data.

The distinction is the whole design. ``CourseCatalogue`` records what the
catalogue contains and travels in the seed files; this records what *this
machine* has already fetched, and travels nowhere. Committing it would make one
developer's network outage part of the repository, and a fresh clone would skip
queries it has never run.

It exists because a 265-query acquisition is long enough to be interrupted, and
the first attempt was: the network dropped, the WebDriver session died with it,
and the run spent its remaining hour timing out against a dead browser --
0 of 265 completed, nothing recoverable. Rerunning without a checkpoint would
have refetched every query that had already succeeded.

Written after every query rather than at the end, because a file written at the
end is a file that is never written when it matters.
"""

import json
from pathlib import Path

#: Kept out of the repository, and out of the package directory, so it cannot
#: be mistaken for seed data or swept into an export.
STATE_DIR = Path(__file__).resolve().parent.parent / ".scrape_state"


class AcquisitionCheckpoint:
    """Per-query progress for one acquisition run.

    Statuses are deliberately three, not two. NOT_STARTED and FAILED both mean
    "run this next time", but they mean different things to a person reading
    the file: one query was never reached because the run stopped, the other
    was reached and refused. Collapsing them would hide a site that is blocking
    a specific search behind a run that simply ended early.
    """

    NOT_STARTED = "NOT_STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

    def __init__(self, name="coursera_skills", state_dir=STATE_DIR):
        self.path = Path(state_dir) / f"{name}.json"
        self.queries = {}
        self.load()

    # ------------------------------------------------------------------

    def load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                self.queries = json.load(handle).get("queries", {})
        except (OSError, ValueError):
            # A truncated checkpoint is worth less than no checkpoint: it would
            # silently skip queries it cannot prove succeeded. Starting over is
            # slower and correct.
            self.queries = {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"queries": self.queries}
        # Written whole and replaced, so an interrupted write cannot leave a
        # half-parsed file behind claiming queries succeeded.
        temporary = self.path.with_suffix(".json.tmp")
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        temporary.replace(self.path)

    # ------------------------------------------------------------------

    def record(self, phrase, status, attempts, reason=""):
        self.queries[phrase] = {
            "status": status,
            "attempts": attempts,
            "reason": reason[:300],
        }
        self.save()

    def status(self, phrase):
        return self.queries.get(phrase, {}).get("status", self.NOT_STARTED)

    def is_done(self, phrase):
        """Only SUCCESS is skipped on a rerun.

        FAILED is retried deliberately. Most failures here are transient --
        a dropped connection, a slow page, a bot-detection page that is gone an
        hour later -- and a permanent one costs three attempts to rediscover,
        which is cheaper than never retrying a query that would now work.
        """
        return self.status(phrase) == self.SUCCESS

    def summary(self):
        counts = {self.SUCCESS: 0, self.FAILED: 0}
        for row in self.queries.values():
            counts[row.get("status", self.NOT_STARTED)] = (
                counts.get(row.get("status", self.NOT_STARTED), 0) + 1)
        return counts

    def failures(self):
        return {phrase: row for phrase, row in sorted(self.queries.items())
                if row.get("status") == self.FAILED}

    def prune(self, live_phrases):
        """Drop entries for phrases nothing searches for any more.

        A checkpoint is keyed by phrase, which is what makes resumption correct
        when the plan shrinks -- a query that succeeded stays succeeded. But it
        also means correcting a skill's search phrase orphans the old key, and
        an orphaned FAILED entry is worse than useless: it reports a failure
        that no rerun can ever clear, because nothing asks that question now.

        Observed once already. YAML's only alias is "yaml ain't markup
        language" -- the recursive-acronym joke -- so that became its phrase and
        failed against every search. Overriding the phrase to "YAML" fixed the
        acquisition and left the old key behind claiming one query still
        failing.

        Returns the phrases removed, so a caller can say what it dropped rather
        than quietly rewriting history.
        """
        live = set(live_phrases)
        orphans = [phrase for phrase in self.queries if phrase not in live]
        for phrase in orphans:
            del self.queries[phrase]
        if orphans:
            self.save()
        return orphans

    def clear(self):
        self.queries = {}
        if self.path.exists():
            self.path.unlink()
