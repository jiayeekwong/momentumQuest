"""The skill catalogue as versioned, reproducible data.

The problem this solves: the development database held 2,102 skills and 3,684
aliases while the repository could rebuild only 162 and 39. Everything else --
the MTO import, the Malaysian market extensions, every provenance row and every
relationship -- existed in exactly one place, a database nobody can review in a
diff and nobody can recreate. A fresh deployment would compute different skill
gaps and different match scores from the same code.

So the direction is inverted here: the CSVs under ``data/`` are the source of
truth and the database is the derived artefact. ``export_skills`` writes the
files, ``import_skills`` rebuilds the database from them, and a test asserts the
round trip is exact rather than merely similar.

Both directions share this module deliberately. An exporter and an importer that
each own their column list drift the moment a field is added to one of them, and
the drift is invisible until a rebuild silently loses a column.

``created_at`` is excluded throughout. It records when a row was written, not
what the catalogue says, and round-tripping it would make every export differ
from the last for no change in meaning.
"""

import csv
import hashlib
import json
from pathlib import Path

from .models import Skill, SkillAlias, SkillRelationship, SkillSource

#: Where the seed files live. One definition, imported by both the exporter and
#: the importer, so the two can never read and write different directories.
DATA_DIR = Path(__file__).resolve().parent / "data"

#: Column order is part of the format: it keeps a re-export byte-identical when
#: nothing has changed, so `git diff` shows only real catalogue movement.
SKILL_FIELDS = ["skill_name", "skill_category", "skill_type",
                "technical_domain", "catalogue_status", "is_active"]
ALIAS_FIELDS = ["alias_name", "skill_name", "source", "requires_context",
                "is_active"]
SOURCE_FIELDS = ["skill_name", "source", "external_id", "external_label",
                 "source_version", "source_url", "source_type"]
RELATIONSHIP_FIELDS = ["from_skill", "to_skill", "relationship_type", "source"]

SKILLS_FILE = "cs_skills.csv"
ALIASES_FILE = "skill_aliases.csv"
SOURCES_FILE = "skill_sources.csv"
RELATIONSHIPS_FILE = "skill_relationships.csv"

FILES = {
    "skills": (SKILLS_FILE, SKILL_FIELDS),
    "aliases": (ALIASES_FILE, ALIAS_FIELDS),
    "sources": (SOURCES_FILE, SOURCE_FIELDS),
    "relationships": (RELATIONSHIPS_FILE, RELATIONSHIP_FIELDS),
}

#: Each table's natural key, and the single definition of snapshot order.
#:
#: Applied in Python on both sides rather than in SQL, because ORDER BY sorts
#: under the database's collation: PostgreSQL puts "a11y Ruby" before
#: "AB Tasty", Python's codepoint order puts it after, and the two snapshots
#: then differed by ordering alone while holding identical rows. A seed file
#: whose order depends on the collation of whichever database exported it is
#: not reproducible, so the ordering is decided here and nowhere else.
SORT_KEYS = {
    "skills": lambda row: row["skill_name"],
    "aliases": lambda row: row["alias_name"],
    "sources": lambda row: (row["skill_name"], row["source"],
                            row["external_label"]),
    "relationships": lambda row: (row["from_skill"], row["to_skill"],
                                  row["relationship_type"]),
}


def write_bool(value):
    """Booleans as 'true'/'false' -- never Python's 'True', which reads as data."""
    return "true" if value else "false"


def read_bool(text, default=True):
    """Parse a seed-file boolean.

    Strict about what it accepts. A typo'd flag silently defaulting is how an
    alias that must never match unguarded ends up matching unguarded, so
    anything unrecognised raises rather than guessing.
    """
    if text is None:
        return default
    cleaned = str(text).strip().casefold()
    if cleaned == "":
        return default
    if cleaned in ("true", "1", "yes", "y"):
        return True
    if cleaned in ("false", "0", "no", "n"):
        return False
    raise ValueError(f"Not a boolean: {text!r}")


def skill_rows():
    return [
        {
            "skill_name": skill.skill_name,
            "skill_category": skill.skill_category,
            "skill_type": skill.skill_type,
            "technical_domain": skill.technical_domain,
            "catalogue_status": skill.catalogue_status,
            "is_active": write_bool(skill.is_active),
        }
        # Unordered here: ids differ between any two databases and SQL order
        # follows the database's collation. SORT_KEYS decides the order.
        for skill in Skill.objects.all()
    ]


def alias_rows():
    return [
        {
            "alias_name": alias.alias_name,
            "skill_name": alias.skill.skill_name,
            "source": alias.source,
            "requires_context": write_bool(alias.requires_context),
            "is_active": write_bool(alias.is_active),
        }
        for alias in SkillAlias.objects.select_related("skill")
    ]


def source_rows():
    return [
        {
            "skill_name": row.skill.skill_name,
            "source": row.source,
            "external_id": row.external_id,
            "external_label": row.external_label,
            "source_version": row.source_version,
            "source_url": row.source_url,
            "source_type": row.source_type,
        }
        for row in SkillSource.objects.select_related("skill")
    ]


def relationship_rows():
    return [
        {
            "from_skill": row.from_skill.skill_name,
            "to_skill": row.to_skill.skill_name,
            "relationship_type": row.relationship_type,
            "source": row.source,
        }
        for row in SkillRelationship.objects.select_related("from_skill",
                                                            "to_skill")
    ]


def database_snapshot():
    """The catalogue as the database currently holds it, canonically ordered."""
    snapshot = {
        "skills": skill_rows(),
        "aliases": alias_rows(),
        "sources": source_rows(),
        "relationships": relationship_rows(),
    }
    for key, rows in snapshot.items():
        rows.sort(key=SORT_KEYS[key])
    return snapshot


def read_rows(path):
    """Rows of one seed file, or [] when the file is absent.

    Absent is legitimate: a checkout predating the provenance seeds still
    imports its skills and aliases. A file that exists but cannot be read is
    not handled here -- that is a broken checkout and should raise.
    """
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()
             if key is not None}
            for row in csv.DictReader(handle)
        ]


def file_snapshot(data_dir):
    """The catalogue as the seed files declare it.

    Normalised through the same sort and the same column list as
    ``database_snapshot`` so the two are comparable directly. Anything the
    files carry beyond the declared columns is dropped here rather than
    compared, because it is not part of the format.
    """
    snapshot = {}
    for key, (filename, fields) in FILES.items():
        rows = read_rows(data_dir / filename)
        normalised = [
            {field: row.get(field, "") for field in fields}
            for row in rows
        ]
        # Booleans are re-serialised so 'TRUE', 'True' and 'true' in a
        # hand-edited file compare equal to what the database would produce.
        for row in normalised:
            for field in ("is_active", "requires_context"):
                if field in row:
                    row[field] = write_bool(read_bool(row[field]))
        # The same key the database side uses, so a difference in the
        # comparison is a difference in content and never in order.
        normalised.sort(key=SORT_KEYS[key])
        snapshot[key] = normalised

    return snapshot


def snapshot_digest(snapshot):
    """A stable sha256 over a snapshot.

    ``sort_keys`` and an explicit separator so the digest depends on the
    catalogue's content and not on dictionary ordering or json's whitespace
    defaults.
    """
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
