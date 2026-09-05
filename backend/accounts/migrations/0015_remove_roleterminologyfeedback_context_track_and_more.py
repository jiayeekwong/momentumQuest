import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Point a student's career target at a Market Role.

    Operations are ordered by hand: the old (student, role_name) constraint
    has to go before role_name does, and the new (student, market_role) one
    cannot exist until market_role does. The rows were cleared in 0014, so the
    non-nullable foreign key needs no default.
    """

    dependencies = [
        ('accounts', '0014_clear_imda_targets'),
        ('scrape_jobs', '0012_marketrole_marketrolealias_remove_ictrole_track_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='studenttargetrole',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='studenttargetrole',
            name='market_role',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='targeting_students',
                to='scrape_jobs.marketrole',
            ),
        ),
        migrations.RemoveField(
            model_name='studenttargetrole',
            name='role_name',
        ),
        migrations.RemoveField(
            model_name='studenttargetrole',
            name='track',
        ),
        migrations.AlterUniqueTogether(
            name='studenttargetrole',
            unique_together={('student', 'market_role')},
        ),
        migrations.RemoveField(
            model_name='roleterminologyfeedback',
            name='context_track',
        ),
        migrations.AddField(
            model_name='roleterminologyfeedback',
            name='context_broad_area',
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
