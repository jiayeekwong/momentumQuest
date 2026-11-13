from django.db import migrations, models
import django.db.models.deletion


STATUSES = [
    ("PENDING", "Pending"),
    ("REVIEWED", "Reviewed"),
    ("SHORTLISTED", "Shortlisted"),
    ("ACCEPTED", "Accepted"),
    ("REJECTED", "Rejected"),
]


def backfill_contact_and_history(apps, schema_editor):
    JobApplication = apps.get_model("job_listings", "JobApplication")
    StatusEvent = apps.get_model(
        "job_listings", "JobApplicationStatusEvent")

    contacts = []
    applications = JobApplication.objects.select_related(
        "student__user").all().iterator(chunk_size=500)
    for application in applications:
        application.contact_email = application.student.user.email
        contacts.append(application)
        if len(contacts) >= 500:
            JobApplication.objects.bulk_update(contacts, ["contact_email"])
            contacts = []

        if application.status_changed_at and application.status != "PENDING":
            event = StatusEvent.objects.create(
                application_id=application.pk,
                from_status="PENDING",
                to_status=application.status,
            )
            # auto_now_add is correct for new events.  This one represents a
            # historical transition, so retain the timestamp already recorded
            # on the application rather than making it look newly decided.
            StatusEvent.objects.filter(pk=event.pk).update(
                changed_at=application.status_changed_at)

    if contacts:
        JobApplication.objects.bulk_update(contacts, ["contact_email"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_studentskillevent"),
        ("job_listings", "0031_jobskill_unspecified_required_level"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobapplication",
            name="contact_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.CreateModel(
            name="JobApplicationStatusEvent",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID")),
                ("from_status", models.CharField(
                    choices=STATUSES, max_length=15)),
                ("to_status", models.CharField(
                    choices=STATUSES, max_length=15)),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="status_events",
                    to="job_listings.jobapplication")),
                ("changed_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="application_status_changes",
                    to="accounts.user")),
            ],
            options={
                "ordering": ["-changed_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="jobapplicationstatusevent",
            index=models.Index(
                fields=["application", "-changed_at"],
                name="application_status_recent"),
        ),
        migrations.RunPython(
            backfill_contact_and_history,
            migrations.RunPython.noop),
    ]
