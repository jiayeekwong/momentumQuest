from django.db import migrations, models
from django.db.models import Count, Q


def detach_replayed_cv_receipts(apps, schema_editor):
    """Make legacy receipt replays safe before enforcing one-use ownership.

    The same stored object cannot safely belong to two applications: deleting
    or expiring either would remove it underneath the other. Keep the oldest
    claim and detach later replays. Their application and disclosure history
    remain; only the unsafe shared file/parse link is removed.
    """
    JobApplication = apps.get_model("job_listings", "JobApplication")

    duplicate_consents = (JobApplication.objects
                          .exclude(cv_processing_consent_id__isnull=True)
                          .values("cv_processing_consent_id")
                          .annotate(total=Count("pk"))
                          .filter(total__gt=1))
    for row in duplicate_consents.iterator():
        consent_id = row["cv_processing_consent_id"]
        applications = list(
            JobApplication.objects
            .filter(cv_processing_consent_id=consent_id)
            .order_by("applied_time", "pk")
            .values_list("pk", flat=True))
        if len(applications) > 1:
            JobApplication.objects.filter(pk__in=applications[1:]).update(
                cv_processing_consent_id=None,
                cv_path="",
                cv_original_name="",
            )

    duplicate_paths = (JobApplication.objects.exclude(cv_path="")
                       .values("cv_path")
                       .annotate(total=Count("pk"))
                       .filter(total__gt=1))
    for row in duplicate_paths.iterator():
        path = row["cv_path"]
        applications = list(
            JobApplication.objects.filter(cv_path=path)
            .order_by("applied_time", "pk")
            .values_list("pk", flat=True))
        if len(applications) > 1:
            JobApplication.objects.filter(pk__in=applications[1:]).update(
                cv_path="", cv_original_name="")


class Migration(migrations.Migration):

    dependencies = [
        ("job_listings", "0029_application_cv"),
    ]

    operations = [
        migrations.RunPython(
            detach_replayed_cv_receipts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="jobapplication",
            constraint=models.UniqueConstraint(
                fields=("cv_processing_consent",),
                condition=Q(cv_processing_consent__isnull=False),
                name="one_application_per_cv_parse",
            ),
        ),
        migrations.AddConstraint(
            model_name="jobapplication",
            constraint=models.UniqueConstraint(
                fields=("cv_path",),
                condition=~Q(cv_path=""),
                name="one_application_per_cv_file",
            ),
        ),
    ]
