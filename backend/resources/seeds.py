"""Learning resources as versioned, reproducible data.

The same problem the skill catalogue had, one layer up. After the Coursera
passes the development database holds 395 courses and 2,165 resources, and the
repository can rebuild none of them: a fresh deployment would show every
student "no resources for this skill" until somebody re-ran a scraper.

Re-running is not a fix. The scraper is non-deterministic by nature -- Coursera
re-ranks results, changes its markup, and blocks bots -- so two deployments
scraping on different days get different catalogues and therefore different
recommendations from identical code. It also needs Chrome, Selenium and
outbound network access, none of which belong in a production bootstrap.

So the resources travel as seed files, exactly as the skill catalogue does:

    export_resources   database -> CSV   (after a scrape and its review)
    import_resources   CSV -> database   (on deploy, offline, deterministic)

Two files, because they answer different questions and have different review
lifecycles:

``course_catalogue.csv``
    What was fetched. The evidence: title, type, the card text a mapping was
    derived from, and which search phrase surfaced it. Re-mapping runs over
    this without touching the network.

``learning_resources.csv``
    What a student is shown -- one row per (skill, course). Kept as data rather
    than always recomputed, because it is the reviewed artefact: a mapping
    someone rejected must stay rejected across a rebuild, and recomputation
    would silently reinstate it. It also carries the resources from platforms
    that never go through the catalogue at all (freeCodeCamp, Microsoft Learn,
    Codecademy), which have no course rows to recompute from.

``scraped_at`` is excluded throughout, for the reason ``created_at`` is
excluded from the skill catalogue: it records when a row was written, not what
the row says, so round-tripping it would make every export differ from the last
for no change in meaning.
"""

import csv
import hashlib
import json
from pathlib import Path

from scrape_jobs.catalogue import read_bool, read_rows, write_bool

from .models import CourseCatalogue, LearningResource, RejectedResourceMapping

DATA_DIR = Path(__file__).resolve().parent / "data"

COURSE_FIELDS = ["url", "title", "platform", "type", "categories",
                 "discovered_via", "card_text", "is_free", "is_active"]
RESOURCE_FIELDS = ["skill_name", "url", "title", "platform", "type", "is_active"]
REJECTION_FIELDS = ["skill_name", "url", "reason"]

COURSES_FILE = "course_catalogue.csv"
RESOURCES_FILE = "learning_resources.csv"
REJECTIONS_FILE = "rejected_resource_mappings.csv"

FILES = {
    "courses": (COURSES_FILE, COURSE_FIELDS),
    "resources": (RESOURCES_FILE, RESOURCE_FIELDS),
    # Third file, because a refusal is a reviewed decision and has to survive a
    # rebuild. Mapping is re-run offline whenever the extractor changes, and a
    # rejection that lived only in one database would be silently undone on
    # every fresh deployment.
    "rejections": (REJECTIONS_FILE, REJECTION_FIELDS),
}

#: Natural keys, and the single definition of order. Sorted in Python rather
#: than SQL for the reason the skill catalogue is: ORDER BY follows the
#: database's collation, and a seed file whose order depends on which database
#: exported it is not reproducible.
SORT_KEYS = {
    "courses": lambda row: row["url"],
    "resources": lambda row: (row["skill_name"], row["url"]),
    "rejections": lambda row: (row["skill_name"], row["url"]),
}

#: JSON-encoded columns. Lists in a CSV cell need one encoding that survives a
#: round trip; json keeps the empty list distinguishable from the empty string.
JSON_FIELDS = {"categories", "discovered_via"}


def course_rows():
    return [
        {
            "url": course.url,
            "title": course.title,
            "platform": course.platform,
            "type": course.type,
            "categories": json.dumps(course.categories or [], sort_keys=True),
            "discovered_via": json.dumps(sorted(course.discovered_via or [])),
            "card_text": course.card_text,
            # Three-state, so it cannot go through write_bool: "" is the
            # provider declining to say, and must survive a round trip as None
            # rather than collapsing into False.
            "is_free": "" if course.is_free is None else write_bool(course.is_free),
            "is_active": write_bool(course.is_active),
        }
        for course in CourseCatalogue.objects.all()
    ]


def resource_rows():
    return [
        {
            "skill_name": row.skill.skill_name,
            "url": row.url,
            "title": row.title,
            "platform": row.platform,
            "type": row.type,
            "is_active": write_bool(row.is_active),
        }
        for row in LearningResource.objects.select_related("skill")
    ]


def rejection_rows():
    return [
        {
            "skill_name": row.skill.skill_name,
            "url": row.url,
            "reason": row.reason,
        }
        # rejected_at is excluded for the reason scraped_at is: it records when
        # somebody decided, not what they decided.
        for row in RejectedResourceMapping.objects.select_related("skill")
    ]


def database_snapshot():
    snapshot = {"courses": course_rows(), "resources": resource_rows(),
                "rejections": rejection_rows()}
    for key, rows in snapshot.items():
        rows.sort(key=SORT_KEYS[key])
    return snapshot


def file_snapshot(data_dir=DATA_DIR):
    snapshot = {}
    for key, (filename, fields) in FILES.items():
        rows = [
            {field: row.get(field, "") for field in fields}
            for row in read_rows(data_dir / filename)
        ]
        for row in rows:
            if "is_active" in row:
                row["is_active"] = write_bool(read_bool(row["is_active"]))
            if "is_free" in row:
                raw = (row["is_free"] or "").strip()
                row["is_free"] = "" if raw == "" else write_bool(read_bool(raw))
            for field in JSON_FIELDS & set(row):
                # Re-encoded so a hand-edited file with different spacing still
                # compares equal to what the database would produce.
                try:
                    value = json.loads(row[field]) if row[field] else []
                except ValueError:
                    value = []
                row[field] = json.dumps(sorted(value) if field == "discovered_via"
                                        else value, sort_keys=True)
        rows.sort(key=SORT_KEYS[key])
        snapshot[key] = rows
    return snapshot


def snapshot_digest(snapshot):
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_files(snapshot, data_dir=DATA_DIR):
    data_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for key, (filename, fields) in FILES.items():
        path = data_dir / filename
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(snapshot[key])
        written[filename] = len(snapshot[key])
    return written
