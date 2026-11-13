from django.db import migrations, models
import django.db.models.deletion


def backfill_published_announcements(apps, schema_editor):
    Announcement = apps.get_model("dashboard", "Announcement")
    rows = []
    for announcement in Announcement.objects.select_related(
            "admin__user").all().iterator(chunk_size=500):
        announcement.approval_status = "APPROVED"
        announcement.submitted_at = announcement.publish_time
        announcement.reviewed_at = announcement.publish_time
        if announcement.admin_id:
            announcement.submitted_by_id = announcement.admin.user_id
            announcement.reviewed_by_id = announcement.admin_id
        rows.append(announcement)
        if len(rows) >= 500:
            Announcement.objects.bulk_update(rows, [
                "approval_status", "submitted_at", "reviewed_at",
                "submitted_by", "reviewed_by",
            ])
            rows = []
    if rows:
        Announcement.objects.bulk_update(rows, [
            "approval_status", "submitted_at", "reviewed_at",
            "submitted_by", "reviewed_by",
        ])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_studentskillevent"),
        ("dashboard", "0006_announcement_attachment_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending review"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("WITHDRAWN", "Withdrawn"),
                ],
                db_index=True, default="APPROVED", max_length=10),
        ),
        migrations.AddField(
            model_name="announcement",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_announcements",
                to="accounts.adminprofile"),
        ),
        migrations.AddField(
            model_name="announcement",
            name="submitted_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="submitted_by",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="submitted_announcements",
                to="accounts.user"),
        ),
        migrations.AlterField(
            model_name="announcement",
            name="publish_time",
            field=models.DateTimeField(
                blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(
            backfill_published_announcements,
            migrations.RunPython.noop),
        migrations.AlterField(
            model_name="announcement",
            name="submitted_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterModelOptions(
            name="announcement",
            options={"ordering": ["-submitted_at"]},
        ),
    ]
