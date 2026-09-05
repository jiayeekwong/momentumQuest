# Privacy Consent and Certificate Verification — Design Record

**Status:** implemented
**Privacy notice version at time of writing:** 1.0 (effective 24 August 2026)
**Source of truth for the text:** `backend/accounts/privacy_notice.py`

This document records the decisions behind MomentumQuest's handling of personal
data in certificate and examination-result verification — in particular the ones
that were made deliberately and would otherwise look like omissions.

---

## 1. MomentumQuest stores no identification number

There is no NRIC/MyKad or passport field on any model. There is no
`student_identity` table. The number exists in exactly one place: inside the
bytes of a document a student chose to upload.

It is never:

- extracted from the document,
- copied into a database column,
- written into a filename,
- placed in a URL,
- recorded in the audit log,
- returned by any API,
- included in analytics, or
- sent to a company.

### Why this is the right design, not a shortcut

Checking an identification number only means something if there is a **trusted
record to compare it against**. MomentumQuest has none — no verified university
identity feed, no prior administrator-established identity.

If a student typed their own IC number into a profile field and then uploaded a
document showing the same number, an administrator confirming that the two match
would have established only that the student is *self-consistent*. It would not
have established who they are. Storing the number would therefore create a
standing liability — a database of identity numbers worth stealing — in exchange
for a verification step that proves nothing.

So the trade is: no stored number, and no claim to verify one.

### What the administrator actually checks

| Check | Available? |
|---|---|
| Name on the document matches the student's registered name | Yes |
| Document is readable and legible | Yes |
| Issuing institution or organisation is identifiable | Yes |
| Qualification/skill information matches the submission | Yes |
| Identification number matches a stored identity record | **No — nothing to compare against** |

The admin verification checklist in `frontend/app/(admin)/endorse/page.tsx`
contains the four available checks and deliberately omits the fifth, with a note
on screen explaining why. `Certificate.RejectionReason` likewise has no
`IDENTITY_NUMBER_MISMATCH` option: offering a reason the system cannot support
would invite a decision an administrator has no basis to make.

An identification number *visible* on an uploaded document may of course be seen
by the administrator reading that document — that is unavoidable and is disclosed
in section 4 of the privacy notice. What must not happen is it being copied out.

### What verification does and does not mean

A verified certificate means: *an authorised administrator looked at the
submitted document and judged that it reasonably supports the claimed
qualification or skill.* It is **not** legal identity verification by a
government authority, and the privacy notice says so in section 5.

---

## 2. Consent is a record, not a flag

`accounts.UserConsent` is append-only. There is no unique constraint on
`(user, consent_type)`, and existing rows are never rewritten.

A consent record is a historical fact — *this person agreed to this text on this
date* — so it needs the notice version and a timestamp to mean anything at all.
Storing `consent = true` would be worthless: it could not answer which version
was agreed to, and a later notice revision would silently appear to have been
accepted by people who never saw it.

Consent is written in two places:

| Where | Type(s) | Source |
|---|---|---|
| Registration (`RegisterSerializer.create`) | both | `SIGNUP` |
| Every certificate upload | `DOCUMENT_VERIFICATION_CONSENT` | `CERTIFICATE_UPLOAD` |
| Every transcript upload | `DOCUMENT_VERIFICATION_CONSENT` | `CERTIFICATE_UPLOAD` |

Both are written inside `transaction.atomic()` together with the thing they
authorise. An account cannot exist without its consent rows, and a stored
document cannot exist without the consent that permitted it — `Certificate.
upload_consent` points at the specific row, which is what turns a transient
checkbox into durable evidence.

Upload consent is collected **per document** rather than inherited from
registration, because the student is consenting to *this* document being read.

**Transcripts are held to the same standard as certificates.** A transcript is
an examination result and is the document most likely to actually display an
NRIC, so it is acknowledged before upload, validated from its own bytes, linked
to its consent via `TranscriptUpload.upload_consent`, and logged
(`TRANSCRIPT_UPLOADED`, `TRANSCRIPT_VIEWED_BY_ADMIN`). Treating it more loosely
than a course certificate would have protected the less sensitive document
better than the more sensitive one.

### Pre-existing accounts

Migration `accounts/0006_backfill_pre_notice_consents.py` writes rows for
accounts created before the notice existed, with:

```
accepted = False,  accepted_at = None,  source = BACKFILL_PRE_NOTICE
```

These are **not consent**. Nobody who signed up before the notice existed agreed
to it, and writing `accepted=True` would manufacture the exact evidence the table
exists to provide. What the rows record is the true fact that the account
predates notice v1.0, which also makes the follow-up list a query:

```python
UserConsent.objects.filter(accepted=False, source="BACKFILL_PRE_NOTICE")
```

Deciding how those users are asked to acknowledge — a login gate, a banner, an
email — is an open project decision. Nothing currently blocks them.

### The wording is served, never copied

The sign-up form and both upload panels render the text returned by
`GET /api/auth/privacy-notice/current/` — `summary`, `consent_statements`,
`upload_notice`, `transcript_notice`. They previously held their own copies.

That was not a tidiness problem. The version written into `user_consents` comes
from the server at submit time, so a page showing a stale local copy would
record someone as having accepted text they never saw, which is precisely what
the versioning exists to prevent. The text and the version now come from the
same place.

The consent checkboxes stay **disabled until the wording arrives**, and the
upload buttons with them: a box ticked against text that has not loaded is not
informed consent. Shared client in `frontend/src/lib/privacyNotice.ts`.

## 3. Notice versioning

Versions live in `NOTICES` in `backend/accounts/privacy_notice.py`, keyed by
version string, served by `GET /api/auth/privacy-notice/current/`.

Kept in a module rather than a table because git already preserves version
history exactly, and a table would need its own admin CRUD to achieve less. The
frontend renders whatever the endpoint returns, so publishing a new version is a
backend change with no page redeploy.

**Rules when revising:**

1. Add a new entry. **Never edit a published one** — consent rows point at a
   version string, and rewriting that text would silently change what past users
   are recorded as having agreed to.
2. Move `CURRENT_VERSION`.
3. Decide whether existing users must re-acknowledge.

`contact_email` is injected at read time from `settings.PRIVACY_CONTACT_EMAIL`.
It is deployment configuration, not agreed text, so changing it must not require
a new version.

## 4. Document storage

Uploaded documents go to `PRIVATE_MEDIA_ROOT` (`backend/private_media/`), never
`MEDIA_ROOT` — `config/urls.py` serves everything under `MEDIA_ROOT` with no
authentication at all.

| Property | How |
|---|---|
| Unpredictable identifier | `cert_<uuid4 hex><ext>` |
| No public URL | Reachable only via `CertificateFileView` |
| Authorisation | Owner, or role `ADMIN`; checked server-side on every request |
| Real type validation | Magic-byte sniffing in `resources/file_validation.py` |
| Path containment | `realpath` + `commonpath` assertion before `open()` |
| Not cached or indexed | `Cache-Control: private, no-store`, `X-Robots-Tag: noindex` |

**Filenames.** The generated name is used for storage *and* for
`Content-Disposition`. `original_name` is kept for display in the UI only.
A student may well name their own file `040910101234_SPM.pdf`; echoing that back
would put an identification number into a response header, into any proxy log
along the way, and into the download folder of every administrator who opened it.

**File type is validated from the file's own bytes**, not its extension, so a
renamed executable is rejected before it is stored or later handed to an
administrator to open. Implemented in pure Python — `python-magic` needs a native
DLL on Windows, and the four accepted formats have short unambiguous signatures.

## 5. Retention: active account only

The project policy is that documents are retained while the account is active and
removed when it is deleted, with **no grace period**.

Prose alone would have been false here: deleting a row does not delete the bytes
it points at, and the files would have accumulated in `private_media`
indefinitely. `resources/signals.py` registers `post_delete` receivers on
`Certificate` and `TranscriptUpload` that unlink the stored file. Deleting a
`User` cascades to `Student` and then to both, so account deletion reaches them.

A student may also withdraw a submission themselves — but only while it is
`PENDING`. Deleting an approved certificate would remove the evidence behind a
skill the student already holds, leaving the granted `StudentSkill` standing with
nothing supporting it.

## 6. Audit logging

`accounts.PrivacyAuditLog`, written through `accounts/audit.py`.

**The table has no free-text column.** Its only `CharField`s are `action` and
`resource_type`, both enum-constrained. The guarantee that an identification
number never reaches the audit log rests on there being nowhere to put one,
rather than on every future call site remembering not to — there is a test
asserting the field set (`PrivacyAuditLogTests.test_the_log_has_no_field_that_
could_hold_document_contents`).

Recorded: `CERTIFICATE_UPLOADED`, `CERTIFICATE_VIEWED_BY_ADMIN`,
`CERTIFICATE_VERIFIED`, `CERTIFICATE_REJECTED`, `CERTIFICATE_DELETED`,
`TRANSCRIPT_UPLOADED`, `TRANSCRIPT_VIEWED_BY_ADMIN`, `CONSENT_ACCEPTED`. A
student opening their own document is not an access event and is not logged; an
admin opening someone else's is.

Each row also stores the acting IP address. That is itself personal data, so
section 2D of the privacy notice discloses these access records explicitly --
collecting them without saying so would have made the notice inaccurate.

`record_privacy_event` swallows every exception and reports to the application
log. An audit write must never break the operation it is auditing — an
administrator should not see a 500 because the log table was briefly unavailable.

## 7. What companies receive

Companies get the verification **result** and nothing behind it.

`JobApplicationSerializer.get_student_skills` returns
`{skill_name, skill_level, verified}`, where `verified` means an administrator
approved a certificate for that skill. The certificate, the document, and any
identification number printed on it appear in no company-reachable payload.

Company accounts are refused by every certificate route:

| Route | Company |
|---|---|
| `GET/POST /api/resources/certificates/` | 403 |
| `GET /api/resources/certificates/<id>/` | 403 |
| `GET /api/resources/certificates/<id>/file/` | 403 |
| `PATCH /api/resources/certificates/<id>/endorse/` | 403 |

Enforced server-side in `get_permissions()` and `get_object()`, not by hiding
buttons. `CompanyVisibilityTests` asserts both the `verified` flags and the
absence of document and identity data.

## 8. Serializer split

| Serializer | Audience | Carries |
|---|---|---|
| `CertificateSerializer` | student | status, `rejection_reason`, `rejection_message` |
| `CertificateAdminSerializer` | admin only | the above plus `verification_notes`, `student_email`, `matric_number`, `mime_type`, consent metadata |

`verification_notes` is internal. An administrator's working note about a
suspicious submission is not written for the submitter to read, so the student
receives `rejection_message` instead — a plain-language explanation generated
from the reason code (`Certificate.REJECTION_MESSAGES`).

The endorse endpoint **requires a stated decision**. A PATCH carrying only
notes previously returned 200, stamped `verified_at` on a still-PENDING
certificate, and wrote a `CERTIFICATE_REJECTED` audit row for a rejection that
never happened -- a false entry in the one table that must be trustworthy.

## 9. Deliberate non-changes

**Rejecting a previously approved certificate does not revoke the granted
skill.** Changing a student's standing on re-review needs a defined project
policy, and there is none. The reversal is recorded in the audit log for a human
to act on. This is an open decision, not an oversight.

**`Student.matric_number` is not the prohibited field.** It is a university
enrolment number, collected so an administrator can tell which student a
submission belongs to, and disclosed in section 2A of the notice. It is not an
identity-document number and is not returned to companies.

**No `LOGGING` configuration was added.** Audit facts belong in the audit table.
Application logs must not carry identity data, so routing more into them would
work against the goal.

---

## Where things live

| Concern | File |
|---|---|
| Notice text and versions | `backend/accounts/privacy_notice.py` |
| Department lists (single source) | `backend/accounts/departments.py` |
| Notice + department client | `frontend/src/lib/privacyNotice.ts` |
| Consent + audit models | `backend/accounts/models.py` |
| Audit helper | `backend/accounts/audit.py` |
| Signup consent | `backend/accounts/serializers.py` (`RegisterSerializer`) |
| Backfill | `backend/accounts/migrations/0006_backfill_pre_notice_consents.py` |
| Upload consent, access control, audit wiring | `backend/resources/views.py` |
| File type validation | `backend/resources/file_validation.py` |
| Retention | `backend/resources/signals.py` |
| Company-facing verification status | `backend/job_listings/serializers.py` |
| Public notice page | `frontend/app/privacy-notice/page.tsx` |
| Signup consent UI | `frontend/app/(auth)/signup/page.tsx` |
| Upload consent UI | `frontend/src/components/SkillValidation.tsx` |
| Admin verification panel | `frontend/app/(admin)/endorse/page.tsx` |

**Endpoints**

```
GET    /api/auth/privacy-notice/current/     public
GET    /api/auth/departments/                public
GET    /api/auth/me/consents/                own consents only
POST   /api/auth/register/                   requires both consents

GET    /api/resources/certificates/          student: own; admin: all; company: 403
POST   /api/resources/certificates/          student only, requires upload consent
GET    /api/resources/certificates/<id>/     owner or admin
DELETE /api/resources/certificates/<id>/     owner, PENDING only
GET    /api/resources/certificates/<id>/file/    owner or admin
PATCH  /api/resources/certificates/<id>/endorse/ admin only
```
