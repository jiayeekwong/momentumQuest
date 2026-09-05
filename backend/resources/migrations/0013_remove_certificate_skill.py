"""Drop the single-skill column now that every claim lives in its own row.

Ordered deliberately after 0012: the backfill has already copied each
certificate's skill into CertificateSkillEvidence, and the counts are asserted
by EvidenceBackfillTests. Removing the column before that would destroy the
only record of what each document was submitted as proof of.

Irreversible in practice -- a rollback would restore an empty column, since
one document can now evidence several skills and there is no single value to
put back.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0012_backfill_certificate_skill_evidence'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='certificate',
            name='skill',
        ),
    ]
