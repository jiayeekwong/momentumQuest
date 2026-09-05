from django.db import models


class MarketRole(models.Model):
    """A standardized career group observed in the Malaysian ICT labour market.

    Market Roles are derived from the job titles employers actually advertise,
    not from an external occupational taxonomy. The pipeline is:

        Raw Job Title -> Normalized Job Title -> Market Role

    A Market Role is the last of those three and the only one a student is
    ever offered: "Frontend Developer", not "frontend engineer" (which is
    matching evidence) and not "Senior Front-End Engineer (Remote)" (which is
    one employer's advert).

    Roles are created where the scraped market gives evidence for them, and
    one employer-specific title variation does not earn its own role -- that
    is what MarketRoleAlias is for.
    """

    name = models.CharField(max_length=120, unique=True)
    #: ``name`` run through the same normalizer as an advert title, so the
    #: EXACT_MARKET_ROLE tier is a dict lookup rather than a second ruleset.
    normalized_name = models.CharField(max_length=200, unique=True, db_index=True)
    #: Presentation only -- UI grouping, filters and reporting. Deliberately
    #: not part of classification: an advert is matched to a Market Role
    #: directly, never to a broad area and then forced into a role under it.
    broad_area = models.CharField(max_length=80, blank=True, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    #: Where this role came from. Market Roles are derived from Malaysian
    #: adverts; one promoted out of the IMDA reference layer on Malaysian
    #: evidence is recorded as such rather than blending in.
    catalogue_origin = models.CharField(
        max_length=32,
        choices=[("MARKET_DERIVED", "Derived from Malaysian adverts"),
                 ("IMDA_MARKET_EXTENSION",
                  "IMDA role promoted on Malaysian evidence")],
        default="MARKET_DERIVED", db_default="MARKET_DERIVED")
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["broad_area", "display_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from .title_normalizer import normalize_title
        if not self.normalized_name:
            self.normalized_name = normalize_title(self.name)
        super().save(*args, **kwargs)


class MarketRoleAlias(models.Model):
    """A reviewed title variant that resolves to exactly one Market Role.

    Every row here is a human decision, never an inference. "Back End
    Developer" means Backend Developer because someone read both and said so;
    "Engineer" means nothing on its own and must never appear here, because a
    keyword that fits six roles resolves none of them.

    ``requires_body_context`` marks an alias plausible enough to record but too
    weak to fire on the title alone -- the advert body has to agree first.
    """

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Entered by hand"
        IMDA = "IMDA", "From the IMDA reference layer"
        MALAYSIA_TITLE_REVIEW = ("MALAYSIA_TITLE_REVIEW",
                                 "Reviewed from Malaysian advert titles")
        LEGACY = "LEGACY", "Predates alias provenance"

    class ReviewStatus(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        PENDING = "PENDING", "Pending review"
        REJECTED = "REJECTED", "Rejected"

    class MappingType(models.TextChoices):
        EXACT = "exact", "Normalized form of the Market Role name"
        REVIEWED_ALIAS = "reviewed_alias", "Reviewed naming variation"
        REVIEWED_SEGMENT = ("reviewed_segment",
                            "Reviewed compound-title segment")

    normalized_title = models.CharField(max_length=250, unique=True)
    market_role = models.ForeignKey(MarketRole, on_delete=models.CASCADE,
                                    related_name="aliases")
    mapping_type = models.CharField(max_length=20, choices=MappingType.choices,
                                    default=MappingType.REVIEWED_ALIAS)
    #: False marks a machine-proposed candidate awaiting a person. Only
    #: reviewed rows are allowed to classify an advert.
    reviewed = models.BooleanField(default=True)
    source = models.CharField(max_length=24, choices=Source.choices,
                              default=Source.LEGACY, db_default=Source.LEGACY)
    review_status = models.CharField(max_length=10,
                                     choices=ReviewStatus.choices,
                                     default=ReviewStatus.APPROVED,
                                     db_default=ReviewStatus.APPROVED)
    is_active = models.BooleanField(default=True, db_default=True)
    #: Recorded but not trusted on the title alone; the body must agree.
    requires_body_context = models.BooleanField(default=False, db_default=False)
    malaysia_advert_count = models.PositiveIntegerField(default=0, db_default=0)
    malaysia_company_count = models.PositiveIntegerField(default=0,
                                                         db_default=0)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    #: Why this mapping was accepted, read when someone later asks whether it
    #: is still right.
    notes = models.CharField(max_length=255, blank=True)
    created_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "market role aliases"
        ordering = ["normalized_title"]

    def __str__(self):
        return f"{self.normalized_title} -> {self.market_role.name}"

    def save(self, *args, **kwargs):
        from .title_normalizer import normalize_title
        self.normalized_title = normalize_title(self.normalized_title)
        super().save(*args, **kwargs)


class JobCategory(models.Model):
    category_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Job categories"

    def __str__(self):
        return self.category_name


class SkillQuerySet(models.QuerySet):

    def selectable(self):
        """Skills a person may attach a certificate, course or programme to.

        One definition, because there were two. The picker endpoint filtered
        retired and unreviewed skills out of what it offered, while the
        serializers behind it accepted any primary key at all -- so the rule
        held only for callers who used the form, and a hand-made request could
        attach evidence to a skill the catalogue does not stand behind.

        REVIEW_REQUIRED is the quarantine an employer-typed name lands in, so
        admitting it here would reopen the hole that quarantine exists to
        close: type "Pyhton" into a job form, then immediately certify it.
        """
        return self.filter(is_active=True).exclude(
            catalogue_status__in=(Skill.CatalogueStatus.REVIEW_REQUIRED,
                                  Skill.CatalogueStatus.DEPRECATED))


class Skill(models.Model):
    """One canonical technology or competence the system recognises.

    Catalogue membership and market activity are deliberately different
    questions. A skill exists here because some catalogue vouches for it; it
    is *market active* only when scraped Malaysian adverts actually ask for
    it, and that is computed from JobSkill rather than stored, so it cannot
    go stale. An imported skill with no Malaysian evidence is a valid
    catalogue entry, not a mistake to delete.
    """

    class CatalogueStatus(models.TextChoices):
        ACTIVE_INTERNAL = "ACTIVE_INTERNAL", "Curated internally"
        MTO_EXTENSION = "MTO_EXTENSION", "Added from the MIND Tech Ontology"
        MARKET_EXTENSION = "MARKET_EXTENSION", "Observed in Malaysian adverts"
        REVIEW_REQUIRED = "REVIEW_REQUIRED", "Awaiting a reviewer"
        DEPRECATED = "DEPRECATED", "Retired"

    skill_name = models.CharField(max_length=100, unique=True)
    skill_category = models.CharField(max_length=100, blank=True)

    # External classification, kept apart from skill_category because the two
    # taxonomies mean different things: category is ours ("Backend
    # Development"), skill_type is the source's ("Framework").
    # db_default as well as default throughout: a migration test that inserts
    # through a historical model state omits columns the state does not know
    # about, and a Python-side default never reaches that INSERT. Without a
    # database default the column is NOT NULL with nothing to fall back on.
    skill_type = models.CharField(max_length=60, blank=True, db_default="")
    technical_domain = models.CharField(max_length=120, blank=True,
                                        db_default="")

    catalogue_status = models.CharField(
        max_length=20, choices=CatalogueStatus.choices,
        default=CatalogueStatus.ACTIVE_INTERNAL,
        db_default=CatalogueStatus.ACTIVE_INTERNAL, db_index=True)
    is_active = models.BooleanField(default=True, db_default=True)

    objects = SkillQuerySet.as_manager()

    def __str__(self):
        return self.skill_name

    @property
    def market_active(self):
        """Whether Malaysian adverts have actually asked for this skill.

        Computed, never stored: an importer must not be able to assert market
        demand, and a stored flag would drift from the adverts it claims to
        summarise.
        """
        return self.job_skills.filter(job__source_type="SCRAPED").exists()


class SkillAlias(models.Model):
    """Alternate names for a skill (e.g. 'JS' -> JavaScript, 'k8s' -> Kubernetes).

    Used by the skill extractor so scraped job descriptions match the canonical
    Skill even when they use a shorthand.
    """
    class Source(models.TextChoices):
        INTERNAL = "INTERNAL", "Curated internally"
        MTO = "MTO", "MIND Tech Ontology"
        STACKOVERFLOW = "STACKOVERFLOW", "Stack Overflow tag synonym"

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="aliases")
    alias_name = models.CharField(max_length=100, unique=True)
    source = models.CharField(max_length=20, choices=Source.choices,
                              default=Source.INTERNAL,
                              db_default=Source.INTERNAL)
    # An alias too short or too overloaded to match on its own. Recorded now,
    # honoured by the extractor's context rules; never activated blindly.
    requires_context = models.BooleanField(default=False, db_default=False)
    is_active = models.BooleanField(default=True, db_default=True)

    class Meta:
        verbose_name_plural = "Skill aliases"
        ordering = ["alias_name"]

    def __str__(self):
        return f"{self.alias_name} -> {self.skill.skill_name}"


class SkillSource(models.Model):
    """Which external catalogue vouches for a skill, and under what name.

    A separate table rather than a column, because one canonical skill is
    routinely attested by several sources -- React is internal, MTO and O*NET
    at once -- and a single `source` field would force a false choice between
    them.
    """

    class Source(models.TextChoices):
        INTERNAL = "INTERNAL", "Curated internally"
        MTO = "MTO", "MIND Tech Skills & Concepts Ontology"
        ONET = "ONET", "O*NET Software Skills"
        LIGHTCAST = "LIGHTCAST", "Lightcast Open Skills"
        DATAMATA = "DATAMATA", "Datamata Skill Demand Index"
        MALAYSIA_JD = "MALAYSIA_JD", "Observed in the Malaysian corpus"
        TECH_JOBS = "TECH_JOBS", "Tech Jobs Dataset (corroboration)"
        QARERA_2026 = "QARERA_2026", "Qarera 2026 demand index (corroboration)"

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE,
                              related_name="sources")
    source = models.CharField(max_length=20, choices=Source.choices,
                              db_index=True)
    external_id = models.CharField(max_length=120, blank=True)
    external_label = models.CharField(max_length=200, blank=True)
    #: Pinned so a claim can be re-derived: a commit hash, a release number.
    source_version = models.CharField(max_length=120, blank=True)
    source_url = models.URLField(blank=True)
    source_type = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("skill", "source", "external_label")
        ordering = ["skill__skill_name", "source"]

    def __str__(self):
        return f"{self.skill.skill_name} <- {self.source}"


class SkillRelationship(models.Model):
    """A relation between two skills, stored but not yet acted on.

    MTO's ``impliesKnowingSkills`` says Svelte implies knowing JavaScript.
    That is a dependency, emphatically not an alias -- treating it as one
    would make every Svelte advert also a JavaScript advert. It is recorded
    here so a future recommender can use it deliberately, and it takes no
    part in extraction today.
    """

    class Type(models.TextChoices):
        IMPLIES_KNOWING = "IMPLIES_KNOWING", "Implies knowing"
        SUPPORTED_LANGUAGE = "SUPPORTED_LANGUAGE", "Supported language"
        RELATED_TECHNOLOGY = "RELATED_TECHNOLOGY", "Related technology"

    from_skill = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                   related_name="relationships_out")
    to_skill = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                 related_name="relationships_in")
    relationship_type = models.CharField(max_length=24, choices=Type.choices)
    source = models.CharField(max_length=20, default="MTO")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("from_skill", "to_skill", "relationship_type")
        ordering = ["from_skill__skill_name", "relationship_type"]

    def __str__(self):
        return (f"{self.from_skill.skill_name} --{self.relationship_type}--> "
                f"{self.to_skill.skill_name}")


class IMDARoleReference(models.Model):
    """The complete official IMDA role universe, kept apart from Market Roles.

    Two different questions were being answered by one table. "Is this a
    recognised ICT occupation?" is IMDA's to answer, and its answer includes
    118 roles. "Are Malaysian employers hiring for it?" is the market's, and
    its answer is much smaller. Merging them would either invent 80 Market
    Roles nobody advertises, or lose the fact that those occupations exist.

    So this layer holds every official role, evidenced or not, and points at a
    MarketRole only where Malaysian adverts justify one. A role with no
    evidence is not missing -- it is here, with ``NO_MARKET_EVIDENCE`` and a
    null mapping, which is a different and more honest statement than absence.

    ``official_name`` is the source record and is never rewritten. The
    normalised and base-role fields are derived metadata sitting beside it.
    """

    class MappingStatus(models.TextChoices):
        UNMAPPED = "UNMAPPED", "Not yet examined"
        MAPPED_EXISTING = "MAPPED_EXISTING", "Mapped to an existing Market Role"
        PROMOTED_MARKET_ROLE = ("PROMOTED_MARKET_ROLE",
                                "Promoted to a new Market Role")
        REVIEW_REQUIRED = "REVIEW_REQUIRED", "Needs a reviewer"
        NO_MARKET_EVIDENCE = ("NO_MARKET_EVIDENCE",
                              "Official role, no Malaysian adverts")

    class Seniority(models.TextChoices):
        CHIEF = "CHIEF", "Chief"
        SENIOR = "SENIOR", "Senior"
        ASSOCIATE = "ASSOCIATE", "Associate"
        JUNIOR = "JUNIOR", "Junior"
        ENTRY = "ENTRY", "Entry"

    #: Verbatim IMDA wording. Never overwritten by normalisation.
    official_name = models.CharField(max_length=200, unique=True)
    normalized_name = models.CharField(max_length=200, db_index=True)
    #: The occupation with any rank word removed -- "Senior Data Engineer"
    #: has a base role of "Data Engineer". Rank is not an occupation.
    base_role_name = models.CharField(max_length=200, blank=True, db_index=True)
    seniority_level = models.CharField(max_length=12, choices=Seniority.choices,
                                       blank=True, db_default="")

    imda_category = models.CharField(max_length=120, blank=True, db_default="")
    imda_subcategory = models.CharField(max_length=120, blank=True,
                                        db_default="")
    imda_source_id = models.CharField(max_length=60, blank=True, db_default="")

    market_role = models.ForeignKey("MarketRole", on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name="imda_references")

    #: Malaysian evidence, recomputed from scraped adverts -- never asserted.
    malaysia_advert_count = models.PositiveIntegerField(default=0, db_default=0)
    malaysia_company_count = models.PositiveIntegerField(default=0,
                                                         db_default=0)

    mapping_status = models.CharField(max_length=24,
                                      choices=MappingStatus.choices,
                                      default=MappingStatus.UNMAPPED,
                                      db_default=MappingStatus.UNMAPPED,
                                      db_index=True)

    source_version = models.CharField(max_length=120, blank=True, db_default="")
    source_reference = models.CharField(max_length=300, blank=True,
                                        db_default="")

    is_active = models.BooleanField(default=True, db_default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["official_name"]
        verbose_name = "IMDA role reference"

    def __str__(self):
        return self.official_name

    @property
    def has_market_evidence(self):
        return self.malaysia_advert_count > 0


class IMDARoleMarketMapping(models.Model):
    """Why one IMDA role points at one Market Role.

    A foreign key alone records the destination but not the reasoning, and
    "Senior Software Engineer maps to Software Engineer" is a claim someone
    should be able to challenge later. This row carries the kind of mapping,
    the evidence behind it, and who accepted it.
    """

    class MappingType(models.TextChoices):
        EXACT = "EXACT", "Names match exactly"
        NORMALIZED = "NORMALIZED", "Match after normalisation"
        SENIORITY_COLLAPSE = ("SENIORITY_COLLAPSE",
                              "Match after removing a rank word")
        REVIEWED_ALIAS = "REVIEWED_ALIAS", "Matched a reviewed alias"
        MARKET_PROMOTION = ("MARKET_PROMOTION",
                            "New Market Role created on Malaysian evidence")

    class ReviewStatus(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    imda_role = models.ForeignKey(IMDARoleReference, on_delete=models.CASCADE,
                                  related_name="mappings")
    market_role = models.ForeignKey("MarketRole", on_delete=models.CASCADE,
                                    related_name="imda_mappings")
    mapping_type = models.CharField(max_length=24, choices=MappingType.choices)
    review_status = models.CharField(max_length=10,
                                     choices=ReviewStatus.choices,
                                     default=ReviewStatus.PENDING,
                                     db_default=ReviewStatus.PENDING)
    evidence_count = models.PositiveIntegerField(default=0, db_default=0)
    evidence_company_count = models.PositiveIntegerField(default=0,
                                                         db_default=0)
    reviewed_by = models.CharField(max_length=120, blank=True, db_default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, db_default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("imda_role", "market_role")
        ordering = ["imda_role__official_name"]

    def __str__(self):
        return "%s -> %s (%s)" % (self.imda_role.official_name,
                                  self.market_role.name, self.mapping_type)


class JobTitle(models.Model):
    """Normalised job title (e.g. 'Junior React Developer'), grouped under a
    JobCategory. JobListing references this via job_title_ref, and students
    pick a career role, not a title; see accounts.StudentTargetRole.
    """
    title_name = models.CharField(max_length=255, unique=True)
    category = models.ForeignKey(
        JobCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_titles",
    )
    # The Market Role this title names, classified from the title itself.
    # Mirrors JobListing.market_role: a title is never blocked on
    # classification, so this is nullable.
    market_role = models.ForeignKey(
        "MarketRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_titles",
    )
    career_level = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["title_name"]

    def __str__(self):
        return self.title_name


# Scraped jobs were merged into job_listings.JobListing (source_type='SCRAPED').
# See job_listings/migrations/0003_migrate_scraped_jobs.py for the data move.
# ScrapeLog now lives in the job_listings app (job_listings.models.ScrapeLog).
