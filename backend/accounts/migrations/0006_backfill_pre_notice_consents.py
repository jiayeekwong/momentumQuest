"""Record that pre-existing accounts predate the privacy notice.

These rows carry ``accepted=False``. They are not consent -- nobody who signed
up before the notice existed agreed to it, and writing accepted=True here would
manufacture the exact evidence this table exists to provide. What they record
is the true fact that the account is older than notice v1.0, which also makes
"who still needs to acknowledge" a query rather than a guess:

    UserConsent.objects.filter(accepted=False, source='BACKFILL_PRE_NOTICE')

New sign-ups do not pass through here; they write accepted=True rows with a
real timestamp in RegisterSerializer.
"""

from django.db import migrations

NOTICE_VERSION = "1.0"
CONSENT_TYPES = (
    "PRIVACY_NOTICE_ACKNOWLEDGEMENT",
    "DOCUMENT_VERIFICATION_CONSENT",
)


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    UserConsent = apps.get_model("accounts", "UserConsent")

    existing = set(
        UserConsent.objects.values_list("user_id", "consent_type")
    )

    rows = [
        UserConsent(
            user_id=user_id,
            consent_type=consent_type,
            notice_version=NOTICE_VERSION,
            accepted=False,
            accepted_at=None,
            source="BACKFILL_PRE_NOTICE",
        )
        for user_id in User.objects.values_list("id", flat=True)
        for consent_type in CONSENT_TYPES
        if (user_id, consent_type) not in existing
    ]

    UserConsent.objects.bulk_create(rows, batch_size=500)


def unbackfill(apps, schema_editor):
    UserConsent = apps.get_model("accounts", "UserConsent")
    UserConsent.objects.filter(source="BACKFILL_PRE_NOTICE").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_student_matric_number_privacyauditlog_userconsent"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
