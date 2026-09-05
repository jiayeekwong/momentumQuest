# MomentumQuest

MomentumQuest is a student career-development platform covering job-market
data collection, occupation and skill standardization, student skill-gap
analysis, learning recommendations, job matching, company workflows, and
administration.

## Design references

- Functional Decomposition Diagram: [`docs/reference/MomentumQuest_FDD.pdf`](docs/reference/MomentumQuest_FDD.pdf)
- Original Entity Relationship Diagram: [`docs/reference/MomentumQuest_ERD.jpg`](docs/reference/MomentumQuest_ERD.jpg)
- Reference notes: [`docs/reference/README.md`](docs/reference/README.md)

The diagrams describe the intended design. Django models and applied migrations
remain the executable source of truth for the deployed database.

## Database change record — occupation standardization

Recorded on 18 August 2026.

The occupation-standardization implementation was added without removing or
renaming the original database entities or breaking their foreign keys. Raw job
titles continue to be preserved, while canonical MASCO information is stored in
separate fields.

### New entities

#### `OccupationConcept`

Stores versioned MASCO and ESCO concepts, including:

- taxonomy, official code and version;
- preferred and normalized labels;
- alternative labels and description;
- parent and ISCO metadata;
- active status.

The combination of taxonomy, code, and version is unique.

#### `OccupationMapping`

Stores explicit MASCO-to-ESCO crosswalks with:

- relationship type (`EXACT`, `CLOSE`, `BROAD`, or `NARROW`);
- confidence between `0` and `1`;
- verification status and review notes.

Each MASCO/ESCO pair is unique. Automatically generated candidates remain
unverified until reviewed by a human.

#### `StudentTargetOccupation`

Stores a student's stable MASCO target occupation, preferred seniority, and
preferred specialization. A student cannot target the same occupation twice.

Derived from the student's target role through the reviewed
`ICTRoleOccupation` bridge, and retained as an explicit target while most
roles have no bridge row yet.

#### `StudentTargetRole`

The career a student is aiming for, and the single source of a student's
target. `SkillGap.target` points here. Since superseded — see
[Market Role classification](#database-change-record---market-role-classification-31-august-2026),
which repointed it at a `MarketRole` foreign key.

Replaces `StudentTargetJob`, which pointed at a scraped `JobTitle`. A market
title is an advert; a role is a career. `JobTitle` itself remains, but only as
a listing-normalization concept.

### Fields added to `JobTitle`

- `canonical_occupation_id` — nullable MASCO foreign key;
- `seniority`;
- `occupation_match_method`;
- `occupation_match_confidence`.

### Fields added to `JobListing`

- `canonical_occupation_id` — nullable MASCO foreign key;
- `standardized_job_title`;
- `occupation_seniority`;
- `occupation_specialization`;
- `occupation_match_method`;
- `occupation_match_confidence`;
- `occupation_review_status`;
- `occupation_standardized_at`.

`JobListing.job_title` remains the original employer or scraper value and is
never replaced by the standardized title.

### Imported data snapshot

After the import and normalization run on 18 August 2026:

- 6,620 MASCO 2020 occupation concepts were imported;
- 2,942 ESCO v1.2.1 occupation concepts were imported;
- 273 conservative MASCO-to-ESCO candidates were imported as unverified;
- 11 of 151 `JobTitle` records were safely matched;
- 32 of 285 job listings were safely standardized;
- all 285 original listing titles were preserved.

Unresolved titles remain pending instead of receiving an uncertain automatic
classification.

### Migrations

- `backend/scrape_jobs/migrations/0006_occupation_taxonomies.py`
- `backend/accounts/migrations/0003_student_target_occupation.py`
- `backend/job_listings/migrations/0008_joblisting_canonical_occupation.py`

The migrations backfill canonical student targets and listing occupations only
when a valid canonical MASCO relationship already exists.

### Import and normalization workflow

The reproducible commands and source-data rules are documented in
[`backend/scrape_jobs/data/OCCUPATION_TAXONOMIES.md`](backend/scrape_jobs/data/OCCUPATION_TAXONOMIES.md).

Downloaded official taxonomy files and generated import CSVs are kept under
`backend/scrape_jobs/data/official/` and are intentionally excluded from Git.

### Validation completed

- Django system check passed;
- migration drift check passed;
- all 17 backend tests passed;
- taxonomy direction and mapping constraints passed;
- standardized listing labels matched their canonical occupations;
- no raw listing title was removed.

## Certificate OCR status

Certificate OCR and extracted certificate metadata have been discussed as a
future enhancement, but no OCR-related database fields or processing pipeline
have been implemented yet.

Note that OCR over a certificate or examination result would read the student's
NRIC/MyKad or passport number off the page. Any such work must not persist that
number: see the privacy design record below.

## Database change record - privacy consent and certificate verification (24 August 2026)

Additive change. No existing entity was renamed or removed and no foreign key
was altered.

New entities:

- `accounts.UserConsent` (`user_consents`) - append-only evidence that a user
  accepted a specific version of the privacy notice, with the version string,
  timestamp and source (`SIGNUP` / `CERTIFICATE_UPLOAD` / `BACKFILL_PRE_NOTICE`).
- `accounts.PrivacyAuditLog` (`privacy_audit_logs`) - who touched an
  identity-bearing document, and when. Deliberately has no free-text column.

New fields:

- `accounts.Student.matric_number` - university enrolment number (not an
  identity-document number).
- `resources.Certificate` - `certificate_type`, `certificate_name`, `mime_type`,
  `verified_at`, `rejection_reason`, `verification_notes`, `upload_consent`.
  The existing `admin` FK serves as the reviewer and `source` as the issuer;
  both were reused rather than duplicated.

Migrations: `accounts/0005_student_matric_number_privacyauditlog_userconsent.py`,
`accounts/0006_backfill_pre_notice_consents.py`,
`resources/0005_certificate_certificate_name_and_more.py`.

The rule that governs this change: **MomentumQuest stores no NRIC/MyKad or
passport number in any field.** The number remains only inside the bytes of a
document a student chose to upload, which is readable by that student and by
authorised administrators and by nobody else. Other modules and company accounts
receive the verification *result* only.

The backfill migration writes `accepted=False` rows for accounts that predate
the notice. They record that the account is older than notice v1.0 - they are
not consent, because nobody who signed up before the notice existed agreed to
it.

Design decisions, including what is deliberately **not** implemented and why,
are recorded in
[`docs/reference/privacy-consent-design.md`](docs/reference/privacy-consent-design.md).

### Validation completed

- Django system check passed;
- migration drift check passed;
- all backend tests passed (136 across accounts, resources and job_listings,
  including the pre-existing suites);
- frontend TypeScript check and production build passed.

## Database change record - consent, CV processing and application disclosure (31 August 2026)

Additive change. No existing entity was renamed or removed.

**Privacy notice 1.1** (`accounts/privacy_notice.py`). 1.0 is preserved
unedited and remains the version earlier acknowledgements refer to. 1.1 adds
what 1.0 never described: CV processing, disclosure to employers, that document
verification is a required student function, and what withdrawing consent
costs. Existing students are not blocked from logging in - the next document
action records the current version and is itself the re-acknowledgement.

**Two new consent types** on `accounts.UserConsent`: `CV_PROCESSING_CONSENT`
and `APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT`. **Three new sources**:
`TRANSCRIPT_UPLOAD`, `CV_PARSE`, `JOB_APPLICATION`. A transcript upload
previously recorded `CERTIFICATE_UPLOAD`, which named the wrong purpose.

**Two nullable FKs** on `JobApplication`: `cv_processing_consent` and
`disclosure_consent`. Legacy applications keep both NULL rather than being
given fabricated evidence.

Migrations: `accounts/0012_alter_userconsent_consent_type_and_more.py`,
`job_listings/0013_jobapplication_cv_processing_consent_and_more.py`.

### Behaviour changes worth knowing

- **A transcript's appearance no longer grants a skill.** Classification routes
  the administrator review queue; `UNCERTAIN` and `LIKELY_TRANSCRIPT` both wait
  for a person. `AUTO_VERIFIED` is reserved for mechanisms that establish the
  issuer and is unreachable from the upload path.
- **Employers see the submitted snapshot only.** Verified status is captured at
  submission and never recomputed, and an empty submitted skill list stays
  empty instead of falling back to the live profile.
- **CV processing requires consent and returns a signed, one-hour receipt.**
  The file is deleted after parsing, as before; the receipt is what links the
  application to the consented parse.
- **Application submission is validated by a serializer.** Malformed input is a
  400 naming the field. `bool("false")` no longer turns an unchecked
  work-permit box into True.
- **The two public upload endpoints validate file content.** They previously
  accepted any extension into unauthenticated media, so an `.html` or `.svg`
  would have been served from the application's own origin.

Design decisions, including what is deliberately not implemented, are in
[`docs/reference/privacy-consent-design.md`](docs/reference/privacy-consent-design.md).

## Correctness fixes - consent withdrawal, evidence and reporting (31 August 2026)

No schema change. The two migrations from the previous entry
(`accounts/0012`, `job_listings/0013`) must be applied before the new backend
starts; an unmigrated database fails every authenticated application request
with `column job_listings_jobapplication.cv_processing_consent_id does not
exist`.

**Consent withdrawal is now implemented**, not merely described.
`accounts/withdrawal.py` is the single entry point behind
`POST /api/auth/me/consents/withdraw/`. It stamps `withdrawn_at` without
deleting history, refuses further document uploads, rejects CV parse receipts
issued under the withdrawn consent, drops skills left without live evidence,
and writes a `CONSENT_WITHDRAWN` audit row - all in one transaction.

**Transcript-verified skills now reach employers as verified.** Snapshot
creation counted approved certificates only, so a skill established by
transcript review was submitted as `{"verified": false}` - the opposite of what
the review found. Both routes now go through one `verified_skill_ids` helper,
used by new snapshots and the legacy fallback alike.

**Dashboard occupation statistics no longer present guesses as results.**
Every canonical occupation was counted as "MASCO coverage" although 0 of 273
mappings and 0 of 245 auto-matched listings are verified. Verified and
auto-matched coverage are now separate figures, and provisional rankings say so
on screen.

**The CV confirmation screen showed five entries and submitted all of them**,
and offered no way to edit or remove any - which the privacy notice promises.
Every extracted line is now shown, each is editable and removable, and only the
confirmed lines are submitted.

Also fixed: an endorsement decision can no longer be reversed while skill
revocation is undefined; the transcript upload screen no longer claims "no
admin approval needed"; the career-role picker submits the track alongside the
role name (13 of 124 role names sit on more than one track) and the profile API
returns it; job selection considers company results, so a company-only search
no longer leaves the detail panel empty; and abandoned temporary CVs are swept,
because a `finally` block does not survive a hard kill.

## Database change record - MASCO and ESCO removed (31 August 2026)

**Destructive.** The occupation taxonomy layer was removed entirely: models,
foreign keys, import commands and data. IMDA's Skills Framework for ICT is now
the only occupation taxonomy in the project.

Deleted models: `OccupationConcept` (6,620 MASCO + 2,942 ESCO concepts),
`OccupationMapping` (273), `ICTRoleOccupation` (34),
`accounts.StudentTargetOccupation`.

Dropped columns: `JobListing.canonical_occupation`, `standardized_job_title`,
`occupation_specialization`, `occupation_match_method`,
`occupation_match_confidence`, `occupation_review_status`,
`occupation_standardized_at`; `JobTitle.canonical_occupation`,
`occupation_match_method`, `occupation_match_confidence`.
`JobListing.occupation_seniority` was **renamed** to `seniority`, preserving
its values.

Deleted commands: `import_masco_occupations`, `import_esco_occupations`,
`import_occupation_mappings`, `import_occupation_aliases`,
`import_ict_role_occupations`, `generate_occupation_mapping_candidates`,
`prepare_occupation_imports`, `normalize_job_titles`, `normalize_job_listings`,
`reconcile_target_occupations`.

Migrations: `accounts/0013`, `job_listings/0015`, `scrape_jobs/0010`.

### Why

MASCO placed 243 of 486 scraped adverts against an occupation; IMDA places 388
into a real career track. Every IMDA role assignment in the database came from
title matching - `EXACT_TITLE`, `NOISE_STRIPPED_TITLE`,
`SENIORITY_STRIPPED_TITLE` - and none from a MASCO bridge, so nothing depended
on the taxonomy by the time it was removed. What remained was a parallel
vocabulary with its own import pipeline, mapping table and review workflow that
no feature read.

`scrape_jobs/occupation_normalizer.py` became
[`title_normalizer.py`](backend/scrape_jobs/title_normalizer.py): the title
cleaning, abbreviation expansion and seniority stripping stayed, because the
IMDA role classifier is built on them. Only the matcher went.

## Database change record - Market Role classification (31 August 2026)

**Destructive.** IMDA's Skills Framework for ICT and the ESCO ICT subset were
both removed from the production classification pipeline and replaced by
**Market Roles**: standardized career groups derived from the job titles
Malaysian ICT employers actually advertise, rather than from any external
occupational taxonomy.

The pipeline is three distinct values, stored separately and never conflated:

```
Raw Job Title          "Senior Front-End Engineer (Remote)"
     -> Normalized Job Title   "senior frontend engineer"   (matching evidence)
     -> Market Role            Frontend Developer            (the career)
```

Only the Market Role is ever offered to a student. A Raw Job Title is one
employer's advert and a Normalized Job Title is a matching key; neither is a
career.

### New entities

#### `scrape_jobs.MarketRole`

`name`, `normalized_name`, `broad_area`, `description`, `is_active`,
`display_order`. 31 roles across six Broad Areas.

`broad_area` is **presentation metadata only** — UI grouping, filters,
reporting, and widening a measurement that has too little evidence at role
level. It never decides which role an advert belongs to: classification is
advert → Market Role directly, never advert → Broad Area → forced role.

#### `scrape_jobs.MarketRoleAlias`

`normalized_title` (unique), `market_role`, `mapping_type`, `reviewed`,
`notes`. 228 reviewed mappings.

An alias states that a market title is a *genuine naming variation* of a
Market Role. It never means the title merely resembles one: no alias is ever
created from edit distance, embeddings or word overlap.

#### `job_listings.MarketRoleCandidate`

Replaces `ICTRoleCandidate`. A title naming two careers, and any
similarity-ranked suggestion, land here for review rather than writing
`JobListing.market_role`.

### Source of truth

[`backend/scrape_jobs/data/market_roles.csv`](backend/scrape_jobs/data/market_roles.csv)
— one reviewable, diffable artifact holding every role and alias, rather than
mappings scattered through Python conditionals. `python manage.py
load_market_roles` makes the database match it.

### Deleted models

`ICTTrack` (9), `ICTRole` (173), `ICTRoleAlias` (7), `ICTRoleCandidate` (69),
and the derived IMDA career-hierarchy dataset under `docs/data/`.

### Fields on `JobListing`

Added: `normalized_job_title`, `market_role`, `career_level`,
`classification_method`, `matched_alias`, `classification_evidence`,
`classified_time`.

Dropped: `ict_track`, `ict_role`, `ict_role_name`, `ict_role_match_method`,
`ict_role_match_confidence`, `ict_role_review_status`, `seniority`.

`JobListing.job_title` remains the original employer or scraper value and is
never replaced.

### Fields on `JobTitle` and `StudentTargetRole`

`JobTitle.ict_track` → `market_role`; `JobTitle.seniority` → `career_level`.
`StudentTargetRole.role_name` + `track` → a `market_role` foreign key; Market
Role names are unique, so nothing else is needed to say which career was
meant.

`RoleTerminologyFeedback.context_track` → `context_broad_area`.

### Existing IMDA assignments were cleared, not converted

`accounts/0014_clear_imda_targets` deletes every `StudentTargetRole` and
`SkillGap` row rather than translating an IMDA rung into a Market Role by
name. The picker's vocabulary changed wholesale, so a name appearing in both
does not mean the student was offered the same thing. Every advert was
re-derived from its Raw Job Title and description; nothing scraped was
modified.

### Classification tiers

`EXACT_MARKET_ROLE`, `REVIEWED_TITLE_ALIAS`, `CAREER_LEVEL_NORMALIZED_ROLE`,
`CAREER_LEVEL_NORMALIZED_ALIAS`, `REVIEWED_SEGMENT_MATCH`, `JD_RESOLVED`,
`AMBIGUOUS`, `UNCLASSIFIED`. Every classified advert keeps its method, the
alias or segment it matched, and — for `JD_RESOLVED` — the responsibilities
that justified it.

### Career level is separated from occupational function

Only genuine levels are removable: intern, graduate, junior, associate, mid,
senior. **Manager, Head, Lead, Principal, Architect, Administrator,
Consultant, Specialist, Support, Officer, Engineer, Analyst, Developer and
Scientist are never stripped** — each names what the job is. Treating them as
levels is what previously reduced "IT Manager / Assistant Manager" to "IT
Assistant" and matched it to a support role; `CareerLevelTests` guards that
regression.

### Ambiguous titles go to advert-level resolution

"IT Executive", "IT Manager", "Technical Executive" and similar name a
department rather than a job, and the same wording covers different work at
different employers. They receive no title alias. Their adverts are resolved
from stated responsibilities instead, requiring three distinct functional
matches and a clear margin over the runner-up. Technologies are supporting
evidence only and never decisive: Python does not mean Data Scientist, and
these same technologies later become the role's measured skill demand.

Advert-level resolution runs **only** for such titles. An unmapped title is a
gap in the reviewed mapping, closed by review — not by the classifier reading
the body text.

### Migrations

- `backend/accounts/migrations/0014_clear_imda_targets.py`
- `backend/accounts/migrations/0015_remove_roleterminologyfeedback_context_track_and_more.py`
- `backend/job_listings/migrations/0018_*`, `0019_*`
- `backend/scrape_jobs/migrations/0012_marketrole_marketrolealias_remove_ictrole_track_and_more.py`
- `backend/scrape_jobs/migrations/0013_delete_icttrack.py`

### Result on the current dataset

486 scraped adverts: **320 classified (66%) into 31 Market Roles**, 22 of them
at or above the evidence floor of 5; 37 ambiguous, 129 unclassified. Ambiguous
and unclassified are valid outcomes and are not optimized away.

### IMDA and ESCO as references

Both remain available as research artifacts under
`backend/scrape_jobs/data/official/` for methodology comparison. Neither
determines a Market Role, renames one, rejects one, reduces coverage, or
controls the student picker.

## Security fixes - privilege escalation and stored XSS (1 September 2026)

Two pre-deployment blockers, both reachable by an unauthenticated attacker.

### Anyone could register themselves an administrator

`RegisterSerializer.role` accepted every `User.Role` choice, `create_role_profile`
had an `ADMIN` branch that created an `AdminProfile`, and `IsAdminUserRole`
checked only `user.role == "ADMIN"`. An attacker could POST `role: "ADMIN"`,
verify their own email, and reach certificate review, every student's identity
documents, and the admin dashboard.

**Fixed on four fronts, so no single writable field is enough:**

- public registration accepts `STUDENT` and `COMPANY` only, listed explicitly
  rather than derived from `User.Role.choices`;
- `create_role_profile` has no `ADMIN` branch and raises on anything else;
- an existing `ADMIN`/`is_staff` account can never be re-registered, closing
  the unverified-reuse path as a takeover route;
- `IsAdminUserRole` requires `role == "ADMIN"` **and** `is_staff`, which is
  only ever granted from a shell.

`accounts.permissions.is_platform_admin()` is the single definition, used by
the permission class and by the view code in `resources/views.py` that picks an
admin serializer or an unscoped queryset — those choices are access control
too, and were testing the role on their own.

Administrators are now created by `python manage.py create_admin --email ...
--name ...`, which sets both facts together. The one existing administrator was
created by `createsuperuser` and already had `is_staff`, so nobody was locked
out and no data migration was needed.

### Stored XSS could steal authentication tokens

Job descriptions, training-programme descriptions and announcements are written
by companies, administrators and a JobStreet scraper, then rendered with
`dangerouslySetInnerHTML` in **ten** places (the review named three). JWTs live
in `localStorage`, so injected script could read the token and take the account.

**Sanitized twice, independently:**

- **On write.** [`config/sanitization.py`](backend/config/sanitization.py)
  wraps `nh3` (the Rust `ammonia` allowlist sanitizer — a parse-and-reserialize
  filter, not a regex over markup). Called from `Model.save()` on `JobListing`,
  `TrainingProgramme` and `Announcement`, so the guarantee holds for the
  scraper and for a shell session, not only for the one HTTP endpoint someone
  remembered to guard. Titles and company names are stripped of markup
  entirely.
- **On render.** [`src/lib/richText.tsx`](frontend/src/lib/richText.tsx) exposes
  one `RichText` component that sanitizes with DOMPurify. `dangerouslySetInnerHTML`
  now appears in that file and nowhere else, so "is this string sanitized?"
  has one answer to check rather than ten call sites to audit.

The allowlist covers headings, paragraphs, lists, emphasis, links and tables.
It excludes `script`, `style`, `iframe`, `object`, `embed`, `form`, `svg`,
`math`, every `on*` handler, `style` attributes, and `javascript:`/`data:` URLs.

Three data migrations sanitize rows written before the sanitizer existed:
`job_listings/0020`, `resources/0010`, `dashboard/0004`.

**Tests:** [`backend/config/tests.py`](backend/config/tests.py) — 24 XSS
payloads (case variants, nested tags, `mXSS` via `math`/`noscript`, `svg`,
`data:` base64, event handlers) asserted inert both through the sanitizer and
after a database round trip; plus the registration and permission regressions.

## Database change record - certificate skill evidence (1 September 2026)

A certificate is a *document*; the skills it proves are separate facts about
it. `Certificate.skill` was a single foreign key, so a student whose "Data
Analytics Programme" certificate evidenced Python, SQL and Data Visualisation
had to upload the same file three times, and an administrator could only accept
or reject the whole thing.

### New entity: `CertificateSkillEvidence`

`certificate`, `skill`, `claimed_level`, `approved_level`, `review_status`,
`review_note`, `reviewed_at`, unique on `(certificate, skill)`, at most 10 per
certificate.

`claimed_level` is what the student asserted; `approved_level` is what the
administrator certified and may be lower. Both are kept: overwriting the claim
would destroy the evidence that it was ever corrected.

An approved certificate can legitimately carry rejected claims — that is the
normal outcome when a broad programme evidences only some of what was asked
for.

### `Certificate.skill` removed

`resources/0012` backfills one evidence row per existing certificate at
`INTERMEDIATE`, which is what the old endorsement path granted
unconditionally. `resources/0013` drops the column, after the counts are
asserted by `EvidenceBackfillTests`.

### StudentSkill is a materialized result

[`resources/skill_evidence.py`](backend/resources/skill_evidence.py) is the
authority. `recalculate_student_skills(student, skills=None)` reads every live
source — approved claims on approved certificates, `TranscriptSkillEvidence`
on verified transcripts, neither resting on a withdrawn consent — takes the
highest level per skill, and creates, updates or deletes accordingly. It never
consults the existing row: reading the current level to decide whether to keep
it is exactly how a level outlives its evidence.

Runs after certificate approval, certificate deletion, transcript
verification, and consent withdrawal. `accounts/withdrawal.py` now delegates to
it instead of keeping a second, boolean-only implementation that could drop a
skill but never lower one.

**Behaviour change worth knowing:** a skill whose only support was a transcript
uploaded before issuer verification existed has no recorded provenance. A
whole-profile recalculation leaves those alone rather than guessing; `python
manage.py recalculate_skills` reports them, and `--strict` removes them.

### Proficiency-aware skill gap

Holding a skill is not the same as being ready for it. Each demanded skill now
returns `required_level`, `student_level`, `readiness_status`
(`MATCHED`/`DEVELOPING`/`MISSING`) and `level_distribution`.

The requirement is the level *most* adverts ask for, not the highest any advert
asks for — one Advanced posting among eight Intermediate ones does not make
Advanced the market requirement. The distribution is returned so the figure can
be checked rather than trusted.

`match_percentage` now uses the same proficiency formula as the job
recommendations — `sum(min(student, required)) / sum(required)` — so a student
comparing "78% match" on a listing with "78% ready" for the role is comparing
like with like. It previously counted skills held, which reported a student
with Beginner Python against an Advanced requirement as a full match.

## Deployment readiness (2 September 2026)

Five findings from a pre-deployment review, all fixed. The first four were
code; the fifth is configuration the deployment has to supply.

### The monthly refresh called four deleted commands

[`schedule_scraper_monthly.bat`](backend/schedule_scraper_monthly.bat) still
invoked `normalize_job_titles`, `normalize_job_listings`, `classify_ict_tracks`
and `classify_ict_roles` months after all four were removed with the IMDA
taxonomy. Nothing failed loudly: the scheduled task wrote four "Unknown
command" lines into a log nobody reads and carried on, so every monthly run
silently skipped re-classification.

Rewritten around the current pipeline, in dependency order:

```
import_skills  ->  load_market_roles  ->  scrape_jobs  ->  dedupe
    ->  recategorize  ->  reextract_job_skills  ->  classify_market_roles
    ->  scrape_status  ->  scrape_resources  ->  purge_orphaned_documents
    ->  refresh_skill_gaps
```

Both taxonomies load *before* the scrape, because the scraper classifies each
advert as it saves it. `reextract_job_skills` and `classify_market_roles` run
after it, because adverts already stored hold the answer the old rules gave
and neither self-corrects. `MonthlyScheduleTests` asserts every command in the
file exists and that this ordering holds, so the drift cannot recur silently.

### Skill aliases were never seeded on a fresh database

`0004_seed_skill_aliases` and `0014_seed_enterprise_skill_aliases` created an
alias only when its canonical skill already existed. On a fresh deployment
migrations run before anything imports `cs_skills.csv`, so there were no
skills to point at and **every alias was skipped** — and nothing ran them
again. The comment claiming they would "wait for the next run" was wrong. A
new deployment got all 162 skills and none of the 39 aliases, so `JS`,
`Golang`, `k8s`, `D365` and `S/4HANA` matched nothing.

Aliases now live in
[`data/skill_aliases.csv`](backend/scrape_jobs/data/skill_aliases.csv) and are
loaded by `manage.py import_skills`, which does both halves in order: canonical
skills from `cs_skills.csv` first, aliases second. Idempotent, and it *reports*
any alias it could not resolve rather than dropping it silently. Both
migrations are now explicit no-ops — kept, not deleted, because they are
already applied on existing databases where they did seed correctly.

Verified on a genuinely fresh database: migrations alone give 0 skills and
0 aliases; `import_skills` gives 162 and 39.

### Django Admin could approve a certificate without granting anything

`CertificateAdmin` allowed editing `verified_status` directly, and the
evidence inline allowed setting `approved_level` and `review_status`. Either
writes the decision and nothing else: no `StudentSkill`, no highest-evidence
recalculation, no skill-gap refresh, no `PrivacyAuditLog` row. The certificate
would read "approved" on the student's profile while granting them no skill,
with no record of who approved it.

Certificates and their evidence inline are now read-only throughout, with
`has_change_permission` returning false so Django removes the Save buttons.
`POST /api/resources/certificates/<pk>/endorse/` does all four things in one
transaction and is the only path to a decision.

### Transcript review outlived the workflow

`TranscriptUploadAdmin` still offered Approve and Reject actions after
transcripts became automatic. Those actions would have offered a decision on a
document that no longer exists — the upload deletes the PDF before it
responds. Removed, along with `resources/transcript_verification.py`, which
nothing but its own tests still imported.

### Production configuration

The application defaulted to local HTTP throughout. What a deployment must
now set is documented in [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example), with the consequence of
each spelled out beside it. In summary:

| Setting | Why it matters |
|---|---|
| `DJANGO_DEBUG=false` | Also switches on HSTS, secure cookies, the SSL redirect, and a refusal to start on the development secret key |
| `DJANGO_ALLOWED_HOSTS` | Real hostnames, no wildcard |
| `CORS_ALLOWED_ORIGINS` | https only — the JWT is sent on every request |
| `FRONTEND_URL` | https; used in verification and password-reset emails |
| `DJANGO_PRIVATE_MEDIA_ROOT` | A mounted volume. The default is inside the checkout, so a rebuild would take every stored certificate with it |
| `NEXT_PUBLIC_API_URL` | Inlined at **build** time. Setting it after `npm run build` changes nothing |

Django Admin's own CSS and JS are served by WhiteNoise, added to
`requirements.txt` and wired directly after `SecurityMiddleware`. Django serves
those assets itself only while `DEBUG` is true, so without this the admin
renders as unstyled HTML behind waitress — and a separate static server for a
handful of admin files is more moving parts than this deployment needs.
`collectstatic` is verified working under `DEBUG=false`.

## Transcript verification

Uploading a transcript does **not** change a student's skills. Parsing and
verification are separate states:

| Field | Question it answers |
|---|---|
| `status` | Could examination rows be read out of the PDF? |
| `document_type_status` | Does it look like a transcript at all? |
| `verification_status` | Has the issuer been confirmed? |

Only `resources/transcript_verification.approve_transcript` may write a
`StudentSkill` from a transcript, and it refuses unless the document is
classified as a transcript **and** the identity matches the uploading student.

**Administrators review certificates, not transcripts.** A transcript is
verified automatically when the classifier clears every mandatory gate:

- a recognised institution,
- a matric number matching the uploading student,
- at least two module rows,
- grade-point arithmetic holding across at least 80% of them.

That is recorded as `VerificationMethod.CLASSIFICATION`, deliberately distinct
from `ADMIN_REVIEW`, because **classification is not issuer verification**: a
forgery carrying this student's own matric number and internally consistent
arithmetic would pass. Closing that needs a cryptographic or institutional
check — Phase 2's `DIGITAL_SIGNATURE` and `QR_VERIFICATION`.

A document that cannot be tied to the student (`UNCERTAIN`) is refused with an
actionable reason rather than parked as pending, since there is no transcript
review queue for it to wait in. One carrying someone else's matric number is
refused outright.

Phase 1 supports the Universiti Malaya text-layer format. There is no OCR, so
a scanned PDF is reported as unsupported rather than guessed at.

### Known limitation: legacy transcripts

Transcripts uploaded before this release applied skills immediately, with no
issuer check. Migration `resources/0008_flag_legacy_transcripts` marks them
`LEGACY_UNVERIFIED` and queues them for administrator review.

**Their skills were deliberately not revoked.** The old schema recorded no
link between a transcript and the skills it granted, so there is no way to
tell which `StudentSkill` rows came from an unverified transcript and which
came from an endorsed certificate. `TranscriptSkillEvidence` exists from this
release onwards to close that gap. Until the legacy queue is cleared, a
student's skills may include entries whose issuer was never verified.
