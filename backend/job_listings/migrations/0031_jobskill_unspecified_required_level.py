from django.db import migrations, models


def classify_existing_level_sources(apps, schema_editor):
    JobSkill = apps.get_model('job_listings', 'JobSkill')

    # Company listings have always been editable by their owner and the
    # current form sends an explicit level per skill. Preserve those values.
    JobSkill.objects.filter(job__source_type='COMPANY').update(
        required_level_source='MANUAL')

    # Keep the legacy scraped values during the schema deployment. The old
    # application remains compatible while the new image builds. Once it is
    # live, reextract_job_skills replaces those guesses with an explicit cue
    # or null. Separating schema and data avoids a mixed-version deployment
    # where the old frontend receives null before it knows how to render it.
    JobSkill.objects.filter(job__source_type='SCRAPED').update(
        required_level_source='NOT_STATED')


def restore_legacy_default(apps, schema_editor):
    JobSkill = apps.get_model('job_listings', 'JobSkill')
    JobSkill.objects.filter(required_level__isnull=True).update(
        required_level='INTERMEDIATE')


class Migration(migrations.Migration):

    dependencies = [
        ('job_listings', '0030_one_application_per_cv_parse'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobskill',
            name='required_level_source',
            field=models.CharField(
                choices=[
                    ('NOT_STATED', 'Not stated in advert'),
                    ('EXPLICIT_TEXT', 'Explicit advert wording'),
                    ('MANUAL', 'Set by employer or reviewer'),
                ],
                default='NOT_STATED',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='jobskill',
            name='required_level',
            field=models.CharField(
                blank=True,
                choices=[
                    ('BEGINNER', 'Beginner'),
                    ('INTERMEDIATE', 'Intermediate'),
                    ('ADVANCED', 'Advanced'),
                ],
                default=None,
                max_length=20,
                null=True,
            ),
        ),
        migrations.RunPython(
            classify_existing_level_sources,
            restore_legacy_default,
        ),
    ]
