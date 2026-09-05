"""Carry every existing certificate's single skill into the evidence table.

No certificate loses its claim, and no approved skill loses its backing.

The level is the one the old endorsement path granted. That path wrote
INTERMEDIATE unconditionally -- a certificate proves working ability rather
than mastery, and the code had no per-skill level to record -- so INTERMEDIATE
is what the migrated rows carry. It is a faithful restatement of what the
database already meant, not a new judgement about the student.

Pending certificates get a PENDING evidence row with no approved_level:
nothing was decided about them, and inventing an approval here would grant a
skill no administrator ever looked at.

The old ``Certificate.skill`` column is deliberately left in place. It is
removed in a later migration, once these counts have been checked against the
originals.
"""

from django.db import migrations

#: What the previous CertificateEndorseView granted on approval.
LEGACY_ENDORSED_LEVEL = "INTERMEDIATE"


def backfill(apps, schema_editor):
    Certificate = apps.get_model("resources", "Certificate")
    Evidence = apps.get_model("resources", "CertificateSkillEvidence")

    rows = []
    for certificate in (Certificate.objects
                        .filter(skill__isnull=False)
                        .only("id", "skill_id", "verified_status", "verified_at")
                        .iterator(chunk_size=500)):
        approved = certificate.verified_status == "APPROVED"
        rejected = certificate.verified_status == "REJECTED"
        rows.append(Evidence(
            certificate_id=certificate.id,
            skill_id=certificate.skill_id,
            claimed_level=LEGACY_ENDORSED_LEVEL,
            approved_level=LEGACY_ENDORSED_LEVEL if approved else "",
            review_status=("APPROVED" if approved
                           else "REJECTED" if rejected else "PENDING"),
            review_note="Migrated from the single-skill certificate model."
                        if approved or rejected else "",
            reviewed_at=certificate.verified_at,
        ))

    # ignore_conflicts so re-running after a partial failure is safe; the
    # unique constraint on (certificate, skill) is what makes that correct.
    Evidence.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)


def unbackfill(apps, schema_editor):
    """Reversible: the source column is still present to rebuild from."""
    apps.get_model("resources", "CertificateSkillEvidence").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0011_alter_certificate_skill_certificateskillevidence"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
