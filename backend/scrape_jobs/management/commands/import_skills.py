"""Rebuild the skill catalogue from the versioned seed files.

The repository is authoritative. These files carry the whole catalogue -- not
only canonical names but every field the extractor and the skill-gap analysis
read: category, type, technical domain, catalogue status, active state, alias
provenance and the contextual-alias flag, plus the SkillSource rows that say
which external catalogue vouches for a skill and the SkillRelationship rows MTO
supplies.

Written to be idempotent. Importing twice is importing once, so it can run on
every deploy without a guard, and a partially-applied import can simply be run
again.

Ordering matters and is not incidental: aliases, sources and relationships all
name skills by string, so skills are loaded first and the rest resolve against
what is then present. A row naming a skill that no file declares is reported
rather than skipped silently -- that is a typo in one file or the other, and
swallowing it is how a catalogue quietly loses a mapping.
"""

import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from scrape_jobs.catalogue import (
    ALIASES_FILE, DATA_DIR, RELATIONSHIPS_FILE, SKILLS_FILE, SOURCES_FILE,
    read_bool, read_rows,
)
from scrape_jobs.models import Skill, SkillAlias, SkillRelationship, SkillSource


class Command(BaseCommand):
    help = "Import the skill catalogue from the versioned CSV seed files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune-aliases", action="store_true",
            help="Delete INTERNAL aliases that are no longer in the CSV.")
        parser.add_argument(
            "--prune", action="store_true",
            help=("Delete any catalogue row absent from the seed files, so the "
                  "database matches the repository exactly."))

    @transaction.atomic
    def handle(self, *args, **options):
        skills_created, skills_updated = self._load_skills()
        aliases_created, aliases_updated, alias_skipped = self._load_aliases()
        sources_created, sources_updated, source_skipped = self._load_sources()
        rel_created, rel_updated, rel_skipped = self._load_relationships()

        self.stdout.write(self.style.SUCCESS(
            f"Skills: {skills_created} created, {skills_updated} updated. "
            f"Aliases: {aliases_created} created, {aliases_updated} updated. "
            f"Sources: {sources_created} created, {sources_updated} updated. "
            f"Relationships: {rel_created} created, {rel_updated} updated."))

        pruned = 0
        if options["prune"]:
            pruned = self._prune_everything()
            self.stdout.write(self.style.WARNING(
                f"Pruned {pruned} row(s) not present in the seed files."))
        elif options["prune_aliases"]:
            keep = {row["alias_name"] for row in read_rows(DATA_DIR / ALIASES_FILE)}
            # Scoped to INTERNAL. Before the seed files carried every alias this
            # command owned only the curated ones, and an unscoped prune would
            # have deleted every MTO alias on the next run. --prune is the
            # unscoped version, and it is safe now only because the files are
            # complete.
            pruned = (SkillAlias.objects
                      .filter(source=SkillAlias.Source.INTERNAL)
                      .exclude(alias_name__in=keep)
                      .delete()[0])
            self.stdout.write(f"Pruned {pruned} internal alias(es).")

        for label, skipped in (("alias", alias_skipped),
                               ("provenance", source_skipped),
                               ("relationship", rel_skipped)):
            if skipped:
                self.stdout.write(self.style.WARNING(
                    "%d %s row(s) name a skill that is not in %s:\n    %s"
                    % (len(skipped), label, SKILLS_FILE,
                       "\n    ".join(skipped[:20]))))

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _rows(filename, required=False):
        path = DATA_DIR / filename
        if required and not path.exists():
            raise CommandError(f"CSV file not found: {path}")
        return read_rows(path)

    def _load_skills(self):
        created = updated = 0
        for row in self._rows(SKILLS_FILE, required=True):
            name = row.get("skill_name", "")
            if not name:
                continue

            # Only columns the file actually carries are written. A checkout
            # whose cs_skills.csv predates these fields still imports, and its
            # skills keep the model defaults rather than being blanked.
            defaults = {"skill_category": row.get("skill_category", "")}
            for field in ("skill_type", "technical_domain", "catalogue_status"):
                if field in row and row[field]:
                    defaults[field] = row[field]
            if row.get("is_active"):
                defaults["is_active"] = read_bool(row["is_active"])

            _skill, was_created = Skill.objects.update_or_create(
                skill_name=name, defaults=defaults)
            created += int(was_created)
            updated += int(not was_created)
        return created, updated

    def _skills_by_name(self):
        # One query, then dict lookups: every other file names skills by string
        # and a query per row would be thousands of round trips.
        return {skill.skill_name.casefold(): skill
                for skill in Skill.objects.all()}

    def _load_aliases(self):
        by_name = self._skills_by_name()
        created = updated = 0
        skipped = []

        for row in self._rows(ALIASES_FILE, required=True):
            alias = row.get("alias_name", "")
            canonical = row.get("skill_name", "")
            if not alias or not canonical:
                continue

            skill = by_name.get(canonical.casefold())
            if skill is None:
                skipped.append(f"{alias!r} -> {canonical!r}")
                continue

            defaults = {"skill": skill}
            if row.get("source"):
                defaults["source"] = row["source"]
            # requires_context decides whether an alias may match unguarded, so
            # a lost value is a behaviour change in the extractor, not a
            # cosmetic one. It is read whenever the column is present at all --
            # including when it says "false", which is why this tests for the
            # key rather than for a truthy value.
            if "requires_context" in row and row["requires_context"] != "":
                defaults["requires_context"] = read_bool(row["requires_context"])
            if "is_active" in row and row["is_active"] != "":
                defaults["is_active"] = read_bool(row["is_active"])

            _row, was_created = SkillAlias.objects.update_or_create(
                alias_name=alias, defaults=defaults)
            created += int(was_created)
            updated += int(not was_created)
        return created, updated, skipped

    def _load_sources(self):
        by_name = self._skills_by_name()
        created = updated = 0
        skipped = []

        for row in self._rows(SOURCES_FILE):
            canonical = row.get("skill_name", "")
            source = row.get("source", "")
            if not canonical or not source:
                continue

            skill = by_name.get(canonical.casefold())
            if skill is None:
                skipped.append(f"{source} -> {canonical!r}")
                continue

            # Keyed on the model's own uniqueness constraint, so a re-import
            # updates the row it wrote last time instead of failing on it.
            _row, was_created = SkillSource.objects.update_or_create(
                skill=skill,
                source=source,
                external_label=row.get("external_label", ""),
                defaults={
                    "external_id": row.get("external_id", ""),
                    "source_version": row.get("source_version", ""),
                    "source_url": row.get("source_url", ""),
                    "source_type": row.get("source_type", ""),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        return created, updated, skipped

    def _load_relationships(self):
        by_name = self._skills_by_name()
        created = updated = 0
        skipped = []

        for row in self._rows(RELATIONSHIPS_FILE):
            from_name = row.get("from_skill", "")
            to_name = row.get("to_skill", "")
            kind = row.get("relationship_type", "")
            if not from_name or not to_name or not kind:
                continue

            from_skill = by_name.get(from_name.casefold())
            to_skill = by_name.get(to_name.casefold())
            if from_skill is None or to_skill is None:
                missing = from_name if from_skill is None else to_name
                skipped.append(f"{from_name!r} -> {to_name!r} (missing {missing!r})")
                continue

            _row, was_created = SkillRelationship.objects.update_or_create(
                from_skill=from_skill,
                to_skill=to_skill,
                relationship_type=kind,
                defaults={"source": row.get("source", "") or "MTO"},
            )
            created += int(was_created)
            updated += int(not was_created)
        return created, updated, skipped

    # ------------------------------------------------------------------
    # Prune
    # ------------------------------------------------------------------

    def _prune_everything(self):
        """Delete catalogue rows the seed files do not declare.

        Skills are pruned last and by name, because deleting one cascades to its
        aliases, provenance and relationships -- so removing the skill first
        would make the earlier counts meaningless.
        """
        pruned = 0

        keep_aliases = {row["alias_name"] for row in self._rows(ALIASES_FILE)}
        pruned += (SkillAlias.objects
                   .exclude(alias_name__in=keep_aliases).delete()[0])

        keep_sources = {
            (row.get("skill_name", "").casefold(), row.get("source", ""),
             row.get("external_label", ""))
            for row in self._rows(SOURCES_FILE)
        }
        for row in SkillSource.objects.select_related("skill"):
            key = (row.skill.skill_name.casefold(), row.source,
                   row.external_label)
            if key not in keep_sources:
                row.delete()
                pruned += 1

        keep_relationships = {
            (row.get("from_skill", "").casefold(),
             row.get("to_skill", "").casefold(),
             row.get("relationship_type", ""))
            for row in self._rows(RELATIONSHIPS_FILE)
        }
        for row in SkillRelationship.objects.select_related("from_skill",
                                                            "to_skill"):
            key = (row.from_skill.skill_name.casefold(),
                   row.to_skill.skill_name.casefold(), row.relationship_type)
            if key not in keep_relationships:
                row.delete()
                pruned += 1

        keep_skills = {row["skill_name"].casefold()
                       for row in self._rows(SKILLS_FILE)}
        for skill in Skill.objects.all():
            if skill.skill_name.casefold() not in keep_skills:
                skill.delete()
                pruned += 1

        return pruned
