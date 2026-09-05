"""What has happened to a student that they would want to know about.

Derived, not stored. There is no Notification table and no per-row read flag,
because every event here is already recorded somewhere with a timestamp:

    application status decided  -> JobApplication.status_changed_at
    certificate decided         -> Certificate.verified_at
    transcript reviewed         -> TranscriptUpload.reviewed_at
    announcement published      -> Announcement.publish_time

Adding a Notification row per event would duplicate all of that and introduce a
second source of truth that can disagree with the first -- a notification
saying "shortlisted" beside an application that has since been rejected.
Reading the underlying records means the list cannot go stale.

The cost is that "unread" cannot be a server-side flag. The client keeps the
timestamp it last opened the panel and counts what is newer, which is accurate
per browser and wrong for nobody: the alternative was the hardcoded red dot
this replaces, which claimed unread items whether or not any existed.
"""

from itertools import chain

FEED_LIMIT = 20


def _iso(value):
    return value.isoformat() if value else None


def application_events(student):
    from job_listings.models import JobApplication

    decided = (
        JobApplication.objects
        .filter(student=student, status_changed_at__isnull=False)
        .exclude(status=JobApplication.Status.PENDING)
        .select_related("job", "job__company")
        .order_by("-status_changed_at")[:FEED_LIMIT]
    )

    for application in decided:
        employer = (application.job.company.company_name
                    if application.job.company_id else application.job.company_name)
        yield {
            "kind": "APPLICATION",
            "at": _iso(application.status_changed_at),
            "title": f"Application {application.get_status_display().lower()}",
            "detail": f"{application.job.job_title}"
                      + (f" at {employer}" if employer else ""),
            "status": application.status,
            "href": "/applications",
        }


def certificate_events(student):
    from resources.models import Certificate

    decided = (
        Certificate.objects
        .filter(student=student, verified_at__isnull=False)
        .exclude(verified_status=Certificate.VerifiedStatus.PENDING)
        .prefetch_related("skill_evidence__skill")
        .order_by("-verified_at")[:FEED_LIMIT]
    )

    for certificate in decided:
        approved = certificate.verified_status == Certificate.VerifiedStatus.APPROVED
        # Names what was actually granted, which is not always what was
        # claimed: an approved document can carry refused claims, and telling
        # the student every claim succeeded would be wrong.
        granted = [row.skill.skill_name for row in certificate.skill_evidence.all()
                   if row.review_status == "APPROVED"]
        skill = ", ".join(granted) if granted else (
            certificate.certificate_name or "your certificate")
        yield {
            "kind": "CERTIFICATE",
            "at": _iso(certificate.verified_at),
            "title": "Certificate approved" if approved else "Certificate not approved",
            # The student's plain-language reason, never the internal notes.
            "detail": (f"{skill} has been verified."
                       if approved else certificate.rejection_message or
                       f"{skill} could not be verified."),
            "status": certificate.verified_status,
            "href": "/profile",
        }


def transcript_events(student):
    from resources.models import TranscriptUpload

    decided = (
        TranscriptUpload.objects
        .filter(student=student, reviewed_at__isnull=False)
        .order_by("-reviewed_at")[:FEED_LIMIT]
    )

    for transcript in decided:
        verified = transcript.verification_status in (
            TranscriptUpload.VerificationStatus.AUTO_VERIFIED,
            TranscriptUpload.VerificationStatus.MANUALLY_VERIFIED,
        )
        yield {
            "kind": "TRANSCRIPT",
            "at": _iso(transcript.reviewed_at),
            "title": "Transcript approved" if verified else "Transcript not approved",
            "detail": (f"{transcript.skills_added} skill(s) added to your profile."
                       if verified
                       else transcript.rejection_reason or
                       "Your transcript could not be verified."),
            "status": transcript.verification_status,
            "href": "/profile",
        }


def announcement_events():
    from .models import Announcement

    for announcement in Announcement.objects.order_by("-publish_time")[:FEED_LIMIT]:
        yield {
            "kind": "ANNOUNCEMENT",
            "at": _iso(announcement.publish_time),
            "title": announcement.title,
            "detail": "",
            "status": None,
            "href": "/dashboard",
        }


def build_feed(student):
    """The student's most recent events, newest first."""
    events = chain(
        application_events(student),
        certificate_events(student),
        transcript_events(student),
        announcement_events(),
    )
    # Sorted on the ISO strings, which order correctly because they are all
    # produced by the same isoformat call with a timezone.
    return sorted(
        (event for event in events if event["at"]),
        key=lambda event: event["at"],
        reverse=True,
    )[:FEED_LIMIT]
