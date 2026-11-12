import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def record_existing_skill_baselines(apps, schema_editor):
    StudentSkill = apps.get_model('accounts', 'StudentSkill')
    StudentSkillEvent = apps.get_model('accounts', 'StudentSkillEvent')
    now = timezone.now()

    events = [
        StudentSkillEvent(
            student_id=row.student_id,
            skill_id=row.skill_id,
            skill_name=row.skill.skill_name,
            previous_level='',
            new_level=row.skill_level,
            change_type='BASELINE',
            source='BASELINE',
            occurred_at=now,
        )
        for row in StudentSkill.objects.select_related('skill').iterator()
    ]
    StudentSkillEvent.objects.bulk_create(events, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_cv_viewed_audit'),
        ('scrape_jobs', '0029_ai_coding_assistants'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentSkillEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False,
                                           verbose_name='ID')),
                ('skill_name', models.CharField(max_length=255)),
                ('previous_level', models.CharField(
                    blank=True,
                    choices=[('BEGINNER', 'Beginner'),
                             ('INTERMEDIATE', 'Intermediate'),
                             ('ADVANCED', 'Advanced')],
                    max_length=20)),
                ('new_level', models.CharField(
                    blank=True,
                    choices=[('BEGINNER', 'Beginner'),
                             ('INTERMEDIATE', 'Intermediate'),
                             ('ADVANCED', 'Advanced')],
                    max_length=20)),
                ('change_type', models.CharField(
                    choices=[('BASELINE', 'Tracking started'),
                             ('ACQUIRED', 'Skill acquired'),
                             ('UPGRADED', 'Level upgraded'),
                             ('DOWNGRADED', 'Level adjusted down'),
                             ('REMOVED', 'Skill removed')],
                    max_length=20)),
                ('source', models.CharField(
                    choices=[('BASELINE', 'Existing portfolio baseline'),
                             ('VERIFIED_EVIDENCE', 'Validated evidence'),
                             ('EVIDENCE_RECALCULATION',
                              'Evidence recalculation')],
                    max_length=30)),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('skill', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='student_skill_events',
                    to='scrape_jobs.skill')),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='skill_events', to='accounts.student')),
            ],
            options={
                'ordering': ['-occurred_at', '-id'],
                'indexes': [models.Index(
                    fields=['student', '-occurred_at'],
                    name='skill_event_student_time')],
            },
        ),
        migrations.RunPython(
            record_existing_skill_baselines, migrations.RunPython.noop),
    ]
