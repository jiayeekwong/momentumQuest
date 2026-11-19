from django.db import migrations, models


LEVEL_RANK = {
    "BEGINNER": 1,
    "INTERMEDIATE": 2,
    "ADVANCED": 3,
}


def convert_pending_claims(apps, schema_editor):
    """Make existing unreviewed claims live without lowering any skill."""
    Certificate = apps.get_model("resources", "Certificate")
    Evidence = apps.get_model("resources", "CertificateSkillEvidence")
    StudentSkill = apps.get_model("accounts", "StudentSkill")

    pending_certificate_ids = list(
        Certificate.objects.filter(verified_status="PENDING")
        .values_list("id", flat=True)
    )
    claims = list(
        Evidence.objects.filter(
            certificate_id__in=pending_certificate_ids,
            review_status="PENDING",
        ).values_list("certificate__student_id", "skill_id", "claimed_level")
    )

    Certificate.objects.filter(id__in=pending_certificate_ids).update(
        verified_status="SELF_DECLARED"
    )
    Evidence.objects.filter(
        certificate_id__in=pending_certificate_ids,
        review_status="PENDING",
    ).update(review_status="SELF_DECLARED")

    for student_id, skill_id, claimed_level in claims:
        current = StudentSkill.objects.filter(
            student_id=student_id,
            skill_id=skill_id,
        ).first()
        if current is None:
            StudentSkill.objects.create(
                student_id=student_id,
                skill_id=skill_id,
                skill_level=claimed_level,
            )
        elif LEVEL_RANK.get(claimed_level, 0) > LEVEL_RANK.get(
            current.skill_level, 0
        ):
            current.skill_level = claimed_level
            current.save(update_fields=["skill_level"])


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0026_trainingprogramme_attachment_path"),
    ]

    operations = [
        migrations.AlterField(
            model_name="certificate",
            name="verified_status",
            field=models.CharField(
                choices=[
                    ("SELF_DECLARED", "Self-declared"),
                    ("PENDING", "Pending"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                ],
                default="SELF_DECLARED",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="certificateskillevidence",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("SELF_DECLARED", "Self-declared"),
                    ("PENDING", "Pending"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                ],
                default="SELF_DECLARED",
                max_length=20,
            ),
        ),
        migrations.RunPython(convert_pending_claims, migrations.RunPython.noop),
    ]
